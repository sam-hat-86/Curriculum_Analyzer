import os
from pathlib import Path
from src.parser.lesson_card_parser import LessonCardParser, parse_lesson_card_classroom


def test_parse_classroom_name_from_class_report():
    """v2/class_report.html から教室名 '和泉中央' (NFKC正規化) が抽出できることをテスト"""
    report_path = Path(__file__).resolve().parent.parent / "class_report.html"
    assert report_path.exists(), f"class_report.html not found at {report_path}"

    with open(report_path, "r", encoding="utf-8") as f:
        html = f.read()

    parser = LessonCardParser()
    classroom = parser.parse_classroom_name(html)
    assert classroom == "和泉中央"

    # 便利関数経由でも一致することを確認
    assert parse_lesson_card_classroom(html) == "和泉中央"


def test_parse_classroom_fallback():
    """フォールバックテーブル構造からの教室名抽出テスト"""
    mock_html = """
    <html>
        <body>
            <div class="other-container">
                <table>
                    <tr><th>担当講師</th><td>山田太郎</td></tr>
                    <tr><th>教室名</th><td>梅田本校</td></tr>
                </table>
            </div>
        </body>
    </html>
    """
    classroom = parse_lesson_card_classroom(mock_html)
    assert classroom == "梅田本校"


def test_parse_classroom_empty_on_invalid():
    """空HTMLや教室情報がない場合の挙動テスト"""
    assert parse_lesson_card_classroom("") == ""
    assert parse_lesson_card_classroom("<html><body><p>No table</p></body></html>") == ""


from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.models.curriculum import CurriculumOverview


def test_repository_backfill_classroom_names(tmp_path):
    """同一生徒の教室名相互補完と未受講生徒の'不明'フォールバックテスト"""
    db_file = str(tmp_path / "test_backfill.db")
    db_mgr = DatabaseManager(db_file)
    repo = Repository(db_mgr)

    # 生徒A: 数学(受講済・教室判明: '和泉中央'), 英語(未受講: 空欄)
    ov_a_math = CurriculumOverview(
        classroom_name="和泉中央",
        classroom_code="",
        school_year="2026",
        student_id="STU_001",
        student_name="生徒A",
        grade="中3",
        division="通常",
        subject="数学",
        school_course="",
        row_index=0,
        detail_url="url_a_math"
    )
    ov_a_eng = CurriculumOverview(
        classroom_name="",
        classroom_code="",
        school_year="2026",
        student_id="STU_001",
        student_name="生徒A",
        grade="中3",
        division="通常",
        subject="英語",
        school_course="",
        row_index=1,
        detail_url="url_a_eng"
    )

    # 生徒B: 国語(全科目未受講: 空欄)
    ov_b_jp = CurriculumOverview(
        classroom_name="",
        classroom_code="",
        school_year="2026",
        student_id="STU_002",
        student_name="生徒B",
        grade="中2",
        division="通常",
        subject="国語",
        school_course="",
        row_index=2,
        detail_url="url_b_jp"
    )

    repo.save_pages_init([ov_a_math, ov_a_eng, ov_b_jp])

    # 相互補完の実行
    repo.backfill_classroom_names()

    with db_mgr.get_connection() as conn:
        cursor = conn.cursor()
        rows = dict(cursor.execute("SELECT url, classroom_name FROM pages").fetchall())

    # 生徒Aの英語が '和泉中央' に補完されていること
    assert rows["url_a_math"] == "和泉中央"
    assert rows["url_a_eng"] == "和泉中央"

    # 生徒Bの国語が '不明' に設定されていること
    assert rows["url_b_jp"] == "不明"


import openpyxl
from src.exporter.excel_exporter import ExcelExporter
from src.models.curriculum import TargetProgress, TargetInfo
from src.analyzer.progress_calculator import calculate_target_progress


def test_e2e_classroom_backfill_and_excel_export(tmp_path):
    """DB相互補完からExcel全シート出力までの統合検証"""
    db_file = str(tmp_path / "test_e2e_cr.db")
    excel_file = str(tmp_path / "test_out.xlsx")
    db_mgr = DatabaseManager(db_file)
    repo = Repository(db_mgr)

    # 1. 生徒A (数学: 受講済 '和泉中央', 英語: 未受講 空欄)
    ov_a_math = CurriculumOverview(
        classroom_name="和泉中央",
        classroom_code="",
        school_year="2026",
        student_id="STU_A",
        student_name="生徒A",
        grade="中3",
        division="通常",
        subject="数学",
        school_course="",
        row_index=0,
        detail_url="url_a_math"
    )
    ov_a_eng = CurriculumOverview(
        classroom_name="",
        classroom_code="",
        school_year="2026",
        student_id="STU_A",
        student_name="生徒A",
        grade="中3",
        division="通常",
        subject="英語",
        school_course="",
        row_index=1,
        detail_url="url_a_eng"
    )

    # 生徒B (全科目未受講: 空欄)
    ov_b_jp = CurriculumOverview(
        classroom_name="",
        classroom_code="",
        school_year="2026",
        student_id="STU_B",
        student_name="生徒B",
        grade="中2",
        division="通常",
        subject="国語",
        school_course="",
        row_index=2,
        detail_url="url_b_jp"
    )

    repo.save_pages_init([ov_a_math, ov_a_eng, ov_b_jp])

    # progress_summary レコードを投入
    prog_a_math = TargetProgress(
        classroom=ov_a_math.classroom_name or "不明",
        student_id=ov_a_math.student_id,
        grade=ov_a_math.grade,
        student_name=ov_a_math.student_name,
        division=ov_a_math.division,
        subject=ov_a_math.subject,
        target_no="T1",
        target_name="テスト対策",
        progress_delay="OK",
        start_date="2026/09/01",
        end_date="2026/10/31",
        period_str="2026/09/01〜2026/10/31",
        is_current=True,
        textbooks_used="フォレスタ",
        target_score="80",
        current_score="75",
        target_unit_count=5,
        executed_count=4,
        executed_rate=80.0,
        on_time_count=4,
        on_time_rate=80.0,
        before_count=0,
        before_rate=0.0,
        after_count=0,
        after_rate=0.0,
        unexecuted_count=1,
        unexecuted_rate=20.0,
        latest_execution_date="2026/09/20"
    )

    prog_a_eng = TargetProgress(
        classroom=ov_a_eng.classroom_name or "不明",
        student_id=ov_a_eng.student_id,
        grade=ov_a_eng.grade,
        student_name=ov_a_eng.student_name,
        division=ov_a_eng.division,
        subject=ov_a_eng.subject,
        target_no="T1",
        target_name="テスト対策",
        progress_delay="OK",
        start_date="2026/09/01",
        end_date="2026/10/31",
        period_str="2026/09/01〜2026/10/31",
        is_current=True,
        textbooks_used="フォレスタ",
        target_score="80",
        current_score="-",
        target_unit_count=5,
        executed_count=0,
        executed_rate=0.0,
        on_time_count=0,
        on_time_rate=0.0,
        before_count=0,
        before_rate=0.0,
        after_count=0,
        after_rate=0.0,
        unexecuted_count=5,
        unexecuted_rate=100.0,
        latest_execution_date="-"
    )

    prog_b_jp = TargetProgress(
        classroom=ov_b_jp.classroom_name or "不明",
        student_id=ov_b_jp.student_id,
        grade=ov_b_jp.grade,
        student_name=ov_b_jp.student_name,
        division=ov_b_jp.division,
        subject=ov_b_jp.subject,
        target_no="T1",
        target_name="テスト対策",
        progress_delay="OK",
        start_date="2026/09/01",
        end_date="2026/10/31",
        period_str="2026/09/01〜2026/10/31",
        is_current=True,
        textbooks_used="新演習",
        target_score="70",
        current_score="-",
        target_unit_count=3,
        executed_count=0,
        executed_rate=0.0,
        on_time_count=0,
        on_time_rate=0.0,
        before_count=0,
        before_rate=0.0,
        after_count=0,
        after_rate=0.0,
        unexecuted_count=3,
        unexecuted_rate=100.0,
        latest_execution_date="-"
    )

    with db_mgr.get_connection() as conn:
        cursor = conn.cursor()
        for url, p in [("url_a_math", prog_a_math), ("url_a_eng", prog_a_eng), ("url_b_jp", prog_b_jp)]:
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
                p.target_no, p.target_name, p.progress_delay, p.start_date, p.end_date, p.period_str,
                1 if p.is_current else 0, p.textbooks_used, p.target_score, p.current_score,
                p.target_unit_count, p.executed_count, p.executed_rate, p.on_time_count,
                p.on_time_rate, p.before_count, p.before_rate, p.after_count, p.after_rate,
                p.unexecuted_count, p.unexecuted_rate, p.latest_execution_date
            ))
        conn.commit()

    # 2. 相互補完の実行
    repo.backfill_classroom_names()

    # 3. Excel出力
    exporter = ExcelExporter(repo)
    wb = exporter.generate_workbook()

    # [進捗一覧] シートの検証
    ws_prog = wb["進捗率"]
    prog_rows = list(ws_prog.iter_rows(values_only=True))[1:]
    # 各行の1列目(教室)を確認
    cr_values = {f"{r[1]}_{r[5]}": r[0] for r in prog_rows}  # {student_id_subject: classroom}
    assert cr_values["STU_A_数学"] == "和泉中央"
    assert cr_values["STU_A_英語"] == "和泉中央"
    assert cr_values["STU_B_国語"] == "不明"

    # [サマリー] シートの教室別集計の検証
    ws_summary = wb["サマリー"]
    summary_rows = list(ws_summary.iter_rows(values_only=True))[1:]
    cr_summaries = [r[1] for r in summary_rows if r[0] == "教室別"]
    assert "和泉中央" in cr_summaries
    assert "不明" in cr_summaries


def test_clean_classroom_name():
    """clean_classroom_name のプレフィックス・全角半角・空白除去テスト"""
    from src.utils.normalization import clean_classroom_name

    assert clean_classroom_name("FS和泉中央") == "和泉中央"
    assert clean_classroom_name("ＦＳ和泉中央") == "和泉中央"
    assert clean_classroom_name("fs和泉中央") == "和泉中央"
    assert clean_classroom_name("FS  津久野駅前") == "津久野駅前"
    assert clean_classroom_name("和泉中央") == "和泉中央"
    assert clean_classroom_name("") == ""
    assert clean_classroom_name(None) == ""
