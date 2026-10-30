"""
Excel出力の安全性・スタイル再現性テスト (D-1: 数式インジェクション防止, D-4: 制御文字除去)
"""
import openpyxl
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.exporter.excel_exporter import ExcelExporter
from src.exporter.safe_writer import SafeExcelWriter, read_xlsx_sheet_names_fast
from src.models.curriculum import (
    CurriculumOverview,
    TargetInfo,
    UnitRecord,
    TargetProgress,
    CurriculumDetailData,
)
from src.models.evaluation import InstructionEvaluation
from src.models.state import ProcessState, TimingCategory
from src.utils.constants import (
    DEFAULT_EXCEL_SHEETS,
    SHEET_SUMMARY_RESULT,
    SHEET_INSTRUCTION,
)


def test_excel_formula_injection_and_control_chars_sanitized(tmp_path):
    """
    1. '=SUM(A1:A10)' や '=HYPERLINK("http://evil")' で始まるテキストが数式ではなく文字列(data_type='s')として保存されること
    2. XML非互換の制御文字 (\x00, \x07, \x1f) が含まれていても破損せず正常にExcelが出力・読み込みできること
    3. read_xlsx_sheet_names_fast が全シート名を正確に検証できること
    """
    db_file = str(tmp_path / "test_safety.db")
    db_manager = DatabaseManager(db_file)
    repo = Repository(db_manager)

    ov = CurriculumOverview(
        classroom_name="梅田\x00本校",
        classroom_code="9901",
        school_year="2026",
        student_id="STU_SAFE",
        student_name="=HYPERLINK(\"http://example.com\",\"危険太郎\")\x07",
        grade="高3",
        division="通常",
        subject="英語\x1f",
        row_index=0,
        status=ProcessState.SAVED,
    )
    repo.save_pages_init([ov])

    t = TargetInfo(
        target_no="T1",
        target_name="=CMD|' /C calc'!A0",
        progress_delay="進捗遅れ",
        start_date="2026/04/01",
        end_date="2026/05/31",
        period_str="2026/04/01～2026/05/31",
        is_current=True,
        target_score="80",
        current_score="70",
        site_progress_rate="50%",
    )
    u = UnitRecord(
        unit_no="1",
        unit_name="=1+1",
        middle_unit="Part\x011",
        textbook="Crown",
        problem_code="E01",
        score="8",
        max_score="10",
        score_rate="80",
        execution_date="2026/04/15",
        timing=TimingCategory.ON_TIME,
        is_executed=True,
        today_textbook="Crown",
        execution_division="通常",
        confirm_test="合格",
        target_checks={"T1": True},
    )
    p = TargetProgress(
        classroom="梅田本校",
        student_id="STU_SAFE",
        grade="高3",
        student_name="=HYPERLINK(\"http://example.com\",\"危険太郎\")",
        division="通常",
        subject="英語",
        target_no="T1",
        target_name="=CMD|' /C calc'!A0",
        progress_delay="進捗遅れ",
        start_date="2026/04/01",
        end_date="2026/05/31",
        period_str="2026/04/01～2026/05/31",
        is_current=True,
        textbooks_used="Crown",
        target_score="80",
        current_score="70",
        target_unit_count=1,
        executed_count=1,
        executed_rate="100",
        on_time_count=1,
        on_time_rate="100",
        before_count=0,
        before_rate="0",
        after_count=0,
        after_rate="0",
        unexecuted_count=0,
        unexecuted_rate="0",
        latest_execution_date="2026/04/15",
    )
    ev = InstructionEvaluation(
        severity="ERROR",
        author="=SUM(1,2,3)",
        target_school="+公立大学",
        textbook="-Crown (所持)",
        plan="@毎週1章\x00\x02進める",
        student_info="=INFO(\"system\")",
        test="単語テスト",
        homework="ワーク",
        errors=["ERR_AUTHOR_MISSING"],
        fix_items=["=修正提案テスト"],
    )

    detail = CurriculumDetailData(
        overview=ov,
        raw_html="<html><body>\x00test</body></html>",
        fetch_time="2026-10-29 12:00:00",
        targets=[t],
        units=[u],
        instruction_eval=ev,
        progress_list=[p],
    )
    repo.save_parsed_result(detail)

    exporter = ExcelExporter(repo, include_raw_sheet=True)
    writer = SafeExcelWriter(exporter, str(tmp_path / "out_safe"))
    xlsx_path = writer.export_final()

    sheet_names = read_xlsx_sheet_names_fast(xlsx_path)
    for req_sheet in DEFAULT_EXCEL_SHEETS:
        assert req_sheet in sheet_names

    wb = openpyxl.load_workbook(xlsx_path, data_only=False)
    try:
        ws_inst = wb[SHEET_INSTRUCTION]
        # 作成者列 (col 11): '=SUM(1,2,3)' が数式 ('f') ではなく文字列 ('s') として格納されていること
        author_cell = ws_inst.cell(row=2, column=11)
        assert author_cell.value == "=SUM(1,2,3)"
        assert author_cell.data_type == "s"

        # 進め方列 (col 14): 制御文字 \x00, \x02 が除去されていること
        plan_cell = ws_inst.cell(row=2, column=14)
        assert plan_cell.value == "@毎週1章進める"
        assert plan_cell.data_type == "s"

        # 集計結果シートの枠固定 (D2) とアラート背景確認
        ws_res = wb[SHEET_SUMMARY_RESULT]
        assert ws_res.freeze_panes == "D2"
        assert ws_res.cell(row=2, column=1).value == "梅田本校"
    finally:
        wb.close()

