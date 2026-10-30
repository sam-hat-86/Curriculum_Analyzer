"""
既存DBの整合性自動修復サービス (v2.1.0 マイグレーション)
- 2ページ目以降の page_key 不一致により status='FETCHED' のまま残されたページを、保存済みHTMLから再解析して SAVED へ昇格
- pages.url に対応する親が存在しない孤児レコード (targets, units, progress_summary, instruction_evaluations) を削除
- 修復完了後 PRAGMA user_version = 1 を記録し、次回以降はO(1)でスキップ
"""
import re
from typing import Optional
from src.database.repository import Repository
from src.models.curriculum import CurriculumOverview
from src.models.state import ProcessState
from src.parser.detail_parser import DetailParser
from src.analyzer.instruction_evaluator import InstructionEvaluator
from src.analyzer.progress_calculator import calculate_target_progress
from src.utils.logger import get_logger

REPAIR_SCHEMA_VERSION = 1
_PAGE_SUFFIX_RE = re.compile(r"^.+_(\d+)_\d+$")


def _extract_page_index(url_or_key: str) -> int:
    """キー文字列 (..._{subject}_{page_idx}_{row_idx}) から page_index を復元"""
    if not url_or_key:
        return 1
    parts = url_or_key.split("_")
    # 標準形式: classroom_student_subject_page_row (5要素以上) vs classroom_student_subject_row (4要素)
    if len(parts) >= 5:
        try:
            candidate = int(parts[-2])
            if candidate >= 2:
                return candidate
        except ValueError:
            pass
    return 1


def repair_database_if_needed(
    repo: Repository,
    detail_parser: Optional[DetailParser] = None,
    instruction_evaluator: Optional[InstructionEvaluator] = None,
    force: bool = False,
) -> dict:
    """
    起動時に1回だけ既存DBの不整合を検査・自動修復する。
    戻り値: {"repaired_pages": int, "removed_orphans": int, "skipped": bool}
    """
    logger = get_logger()
    result = {"repaired_pages": 0, "removed_orphans": 0, "skipped": False}

    with repo.db.connect() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")
        row = cur.fetchone()
        current_ver = row[0] if row else 0

        # FETCHED のまま html が残っているページがあるか確認 (user_version 済みでも残っていれば修復)
        cur.execute(
            "SELECT COUNT(*) FROM pages WHERE status IN (?, ?) AND html IS NOT NULL AND LENGTH(html) > 200",
            (ProcessState.FETCHED.value, ProcessState.PARSED.value),
        )
        pending_fetched = cur.fetchone()[0]

        if current_ver >= REPAIR_SCHEMA_VERSION and pending_fetched == 0 and not force:
            result["skipped"] = True
            return result

        # 1. FETCHED / PARSED で HTML が保存されているページを取得
        cur.execute("""
            SELECT url, curriculum_key, row_index, classroom_name, classroom_code,
                   school_year, student_id, student_name, grade, division, subject,
                   school_course, html, fetch_time
            FROM pages
            WHERE status IN (?, ?) AND html IS NOT NULL AND LENGTH(html) > 200
        """, (ProcessState.FETCHED.value, ProcessState.PARSED.value))
        fetched_rows = cur.fetchall()

    parser = detail_parser or DetailParser()
    evaluator = instruction_evaluator or InstructionEvaluator()

    repaired_count = 0
    if fetched_rows:
        with repo.db.connect() as conn:
            for r in fetched_rows:
                try:
                    url = r["url"]
                    ckey = r["curriculum_key"] or url
                    p_idx = _extract_page_index(ckey)
                    ov = CurriculumOverview(
                        classroom_name=r["classroom_name"] or "",
                        classroom_code=r["classroom_code"] or "",
                        school_year=r["school_year"] or "",
                        student_id=r["student_id"] or "",
                        student_name=r["student_name"] or "",
                        grade=r["grade"] or "",
                        division=r["division"] or "",
                        subject=r["subject"] or "",
                        school_course=r["school_course"] or "",
                        row_index=r["row_index"] or 0,
                        page_index=p_idx,
                        detail_url=url,
                        status=ProcessState.SAVED,
                    )
                    detail_data = parser.parse(r["html"], overview=ov, fetch_time=r["fetch_time"] or "")
                    detail_data.instruction_eval = evaluator.evaluate(
                        raw_instruction=detail_data.raw_instruction,
                        grade=ov.grade,
                        division=ov.division,
                        school_course=ov.school_course,
                    )
                    detail_data.progress_list = [
                        calculate_target_progress(ov, t, detail_data.units)
                        for t in detail_data.targets
                    ]
                    repo.save_parsed_result(detail_data, conn=conn, commit=False)
                    repaired_count += 1
                except Exception as err:
                    logger.warning(f"DB修復中の再解析スキップ ({r['url']}): {err}")

    # 2. pages.url に存在しない孤児レコードのクリーンアップ
    removed_orphans = 0
    with repo.db.connect() as conn:
        cur = conn.cursor()
        for table in ("targets", "units", "progress_summary", "instruction_evaluations"):
            cur.execute(f"DELETE FROM {table} WHERE page_url NOT IN (SELECT url FROM pages)")
            removed_orphans += max(0, cur.rowcount or 0)

        cur.execute(f"PRAGMA user_version = {REPAIR_SCHEMA_VERSION}")

    result["repaired_pages"] = repaired_count
    result["removed_orphans"] = removed_orphans
    if repaired_count > 0 or removed_orphans > 0:
        logger.info(
            f"DB整合性修復が完了しました (再解析によるSAVED昇格: {repaired_count} 件, 孤児レコード削除: {removed_orphans} 件)"
        )
    return result

