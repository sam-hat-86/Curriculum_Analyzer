"""
データベースリポジトリ (CRUD・集計・再開クエリ)
"""
import json
import sqlite3
from typing import Dict, List, Optional, Tuple, Any
from src.database.db_manager import DatabaseManager
from src.models.curriculum import (
    CurriculumOverview,
    TargetInfo,
    UnitRecord,
    TargetProgress,
    CurriculumDetailData,
)
from src.models.evaluation import InstructionEvaluation
from src.models.state import ProcessState, TimingCategory

class Repository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def save_pages_init(self, overviews: List[CurriculumOverview]):
        """一覧取得時の授業レコード初期登録 (既存のSAVEDは維持)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for ov in overviews:
                p_idx = getattr(ov, "page_index", 1)
                page_suffix = f"_{p_idx}" if p_idx > 1 else ""
                key = f"{ov.classroom_code}_{ov.student_id}_{ov.subject}{page_suffix}_{ov.row_index}"
                url = ov.detail_url or key
                
                # 既存確認
                cursor.execute("SELECT status FROM pages WHERE url = ?", (url,))
                row = cursor.fetchone()
                if row:
                    # 既にSAVEDまたはPARSEDならステータスは上書きしない
                    continue

                cursor.execute("""
                    INSERT OR REPLACE INTO pages (
                        url, curriculum_key, row_index, classroom_name, classroom_code,
                        school_year, student_id, student_name, grade, division, subject,
                        school_course, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url, key, ov.row_index, ov.classroom_name, ov.classroom_code,
                    ov.school_year, ov.student_id, ov.student_name, ov.grade, ov.division,
                    ov.subject, ov.school_course, ProcessState.UNFETCHED.value
                ))
            conn.commit()

    def update_page_fetched(self, url: str, html: str, fetch_time: str):
        """HTML取得成功ステータス更新"""
        with self.db.get_connection() as conn:
            conn.execute("""
                UPDATE pages SET
                    status = ?,
                    html = ?,
                    fetch_time = ?,
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE url = ?
            """, (ProcessState.FETCHED.value, html, fetch_time, url))
            conn.commit()

    def update_page_fetch_failed(self, url: str, error_message: str):
        """HTML取得失敗ステータス更新"""
        with self.db.get_connection() as conn:
            conn.execute("""
                UPDATE pages SET
                    status = ?,
                    error_message = ?,
                    retry_count = retry_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE url = ?
            """, (ProcessState.FETCH_FAILED.value, error_message, url))
            conn.commit()

    def save_parsed_result(self, detail_data: CurriculumDetailData):
        """解析結果の一括アトミック保存"""
        ov = detail_data.overview
        key = f"{ov.classroom_code}_{ov.student_id}_{ov.subject}_{ov.row_index}"
        url = ov.detail_url or key

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # 既存の子レコードを削除
            cursor.execute("DELETE FROM targets WHERE page_url = ?", (url,))
            cursor.execute("DELETE FROM units WHERE page_url = ?", (url,))
            cursor.execute("DELETE FROM progress_summary WHERE page_url = ?", (url,))
            cursor.execute("DELETE FROM instruction_evaluations WHERE page_url = ?", (url,))

            # 1. targets
            for t in detail_data.targets:
                cursor.execute("""
                    INSERT INTO targets (
                        page_url, student_id, target_no, target_name, progress_delay, start_date, end_date,
                        period_str, is_current, target_score, current_score, site_progress_rate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url, ov.student_id, t.target_no, t.target_name, getattr(t, 'progress_delay', 'OK'), t.start_date, t.end_date,
                    t.period_str, 1 if t.is_current else 0, t.target_score, t.current_score,
                    t.site_progress_rate
                ))

            # 2. units
            for u in detail_data.units:
                cursor.execute("""
                    INSERT INTO units (
                        page_url, student_id, unit_no, unit_name, middle_unit, textbook,
                        problem_code, score, max_score, score_rate, execution_date, timing,
                        is_executed, today_textbook, execution_division, confirm_test, target_checks_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url, ov.student_id, u.unit_no, u.unit_name, u.middle_unit, u.textbook,
                    u.problem_code, u.score, u.max_score, u.score_rate, u.execution_date,
                    u.timing.value, 1 if u.is_executed else 0, u.today_textbook,
                    u.execution_division, u.confirm_test, json.dumps(u.target_checks, ensure_ascii=False)
                ))

            # 3. progress_summary
            for p in detail_data.progress_list:
                cursor.execute("""
                    INSERT INTO progress_summary (
                        page_url, classroom, student_id, grade, student_name, division, subject,
                        target_no, target_name, progress_delay, start_date, end_date, period_str, is_current,
                        textbooks_used, target_score, current_score, target_unit_count,
                        executed_count, executed_rate, on_time_count, on_time_rate,
                        before_count, before_rate, after_count, after_rate,
                        unexecuted_count, unexecuted_rate, latest_execution_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url, p.classroom, p.student_id, p.grade, p.student_name, p.division, p.subject,
                    p.target_no, p.target_name, getattr(p, 'progress_delay', 'OK'), p.start_date, p.end_date, p.period_str,
                    1 if p.is_current else 0, p.textbooks_used, p.target_score, p.current_score,
                    p.target_unit_count, p.executed_count, p.executed_rate, p.on_time_count,
                    p.on_time_rate, p.before_count, p.before_rate, p.after_count, p.after_rate,
                    p.unexecuted_count, p.unexecuted_rate, p.latest_execution_date
                ))

            # 4. instruction_evaluations
            ev = detail_data.instruction_eval
            if ev:
                cursor.execute("""
                    INSERT OR REPLACE INTO instruction_evaluations (
                        page_url, student_id, severity, fix_items_json, errors_json,
                        warnings_json, reviews_json, author, target_school, textbook,
                        plan, student_info, test, homework, unclassified_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url, ov.student_id, ev.severity, json.dumps(ev.fix_items, ensure_ascii=False),
                    json.dumps(ev.errors, ensure_ascii=False), json.dumps(ev.warnings, ensure_ascii=False),
                    json.dumps(ev.reviews, ensure_ascii=False), ev.author, ev.target_school,
                    ev.textbook, ev.plan, ev.student_info, ev.test, ev.homework, ev.unclassified_text
                ))

            # 5. pages ステータス更新
            cursor.execute("""
                UPDATE pages SET
                    status = ?,
                    student_name = COALESCE(NULLIF(student_name, ''), ?),
                    grade = COALESCE(NULLIF(grade, ''), ?),
                    division = COALESCE(NULLIF(division, ''), ?),
                    subject = COALESCE(NULLIF(subject, ''), ?),
                    school_course = COALESCE(NULLIF(school_course, ''), ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE url = ?
            """, (
                ProcessState.SAVED.value, ov.student_name, ov.grade, ov.division,
                ov.subject, ov.school_course, url
            ))

            conn.commit()

    def get_uncompleted_pages(self) -> List[sqlite3.Row]:
        """未完了（未取得・失敗）のページ一覧を取得"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM pages
                WHERE status IN (?, ?)
                ORDER BY row_index ASC
            """, (ProcessState.UNFETCHED.value, ProcessState.FETCH_FAILED.value))
            return cursor.fetchall()

    def get_counts(self) -> Dict[str, int]:
        """各状態の件数を取得"""
        counts = {
            "total": 0,
            "unfetched": 0,
            "fetched": 0,
            "saved": 0,
            "failed": 0,
        }
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as cnt FROM pages GROUP BY status")
            for row in cursor.fetchall():
                st = row["status"]
                c = row["cnt"]
                counts["total"] += c
                if st == ProcessState.UNFETCHED.value:
                    counts["unfetched"] = c
                elif st in [ProcessState.FETCHED.value, ProcessState.PARSED.value]:
                    counts["fetched"] += c
                elif st == ProcessState.SAVED.value:
                    counts["saved"] = c
                elif st in [ProcessState.FETCH_FAILED.value, ProcessState.PARSE_FAILED.value]:
                    counts["failed"] += c
        return counts

    def get_all_progress_summaries(self) -> List[sqlite3.Row]:
        """[進捗率]シート出力用の全レコード取得"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM progress_summary ORDER BY id ASC")
            return cursor.fetchall()

    def get_all_units(self) -> List[sqlite3.Row]:
        """[単元詳細]シート出力用の全レコード取得"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.*, p.classroom_name, p.grade, p.student_name, p.division, p.subject
                FROM units u
                JOIN pages p ON u.page_url = p.url
                ORDER BY u.id ASC
            """)
            return cursor.fetchall()

    def get_all_targets(self) -> List[sqlite3.Row]:
        """全ターゲットレコード取得"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM targets ORDER BY id ASC")
            return cursor.fetchall()

    def get_all_instruction_evaluations(self) -> List[sqlite3.Row]:
        """[備考欄]シート出力用の全レコード取得"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.*, p.classroom_name, p.grade, p.student_name, p.division, p.subject
                FROM instruction_evaluations e
                JOIN pages p ON e.page_url = p.url
                ORDER BY p.row_index ASC
            """)
            return cursor.fetchall()

    def get_all_raw_pages(self) -> List[sqlite3.Row]:
        """[原文]シート出力用の全レコード取得"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pages ORDER BY row_index ASC")
            return cursor.fetchall()

    def get_all_summary_results(self) -> List[Dict[str, Any]]:
        """[集計結果]シート用（生徒の受講科目ごと）のデータ取得"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.url, p.classroom_name, p.student_name, p.subject, p.row_index
                FROM pages p
                ORDER BY p.row_index ASC
            """)
            pages = cursor.fetchall()

            cursor.execute("""
                SELECT page_url, target_no, target_name, progress_delay
                FROM targets
                ORDER BY id ASC
            """)
            all_targets = cursor.fetchall()
            targets_by_page: Dict[str, List[sqlite3.Row]] = {}
            for t in all_targets:
                targets_by_page.setdefault(t["page_url"], []).append(t)

            cursor.execute("""
                SELECT page_url, severity, fix_items_json, errors_json, warnings_json
                FROM instruction_evaluations
            """)
            all_evals = cursor.fetchall()
            evals_by_page = {e["page_url"]: e for e in all_evals}

            results = []
            for p in pages:
                url = p["url"]
                p_targets = targets_by_page.get(url, [])
                delayed_target_names = []
                for t in p_targets:
                    p_delay = t["progress_delay"]
                    if p_delay and p_delay != "OK":
                        t_name = t["target_name"] or t["target_no"] or "ターゲット"
                        delayed_target_names.append(t_name)

                eval_row = evals_by_page.get(url)
                severity = eval_row["severity"] if eval_row else "-"
                reasons = []
                if eval_row:
                    fix_items = json.loads(eval_row["fix_items_json"] or "[]")
                    errors = json.loads(eval_row["errors_json"] or "[]")
                    warnings = json.loads(eval_row["warnings_json"] or "[]")
                    if fix_items:
                        reasons.extend(fix_items)
                    else:
                        reasons.extend(errors)
                        reasons.extend(warnings)

                results.append({
                    "classroom_name": p["classroom_name"] or "-",
                    "student_name": p["student_name"] or "-",
                    "subject": p["subject"] or "-",
                    "delayed_targets": delayed_target_names,
                    "severity": severity or "-",
                    "reasons": reasons,
                })

            return results

    def clear_all_data(self):
        """蓄積された全データを消去して初期状態にリセット"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM targets")
            cursor.execute("DELETE FROM units")
            cursor.execute("DELETE FROM progress_summary")
            cursor.execute("DELETE FROM instruction_evaluations")
            cursor.execute("DELETE FROM pages")
            conn.commit()
            try:
                cursor.execute("VACUUM")
            except Exception:
                pass
