"""
Excel 5シート出力および安全書き込みテスト (仕様書§18, §20, §21, §24, §25, §26, §28)
"""
import os
import pytest
import openpyxl
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.exporter.excel_exporter import ExcelExporter
from src.exporter.safe_writer import SafeExcelWriter
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
    SHEET_PROGRESS,
    SHEET_UNIT_DETAILS,
    SHEET_INSTRUCTION,
    SHEET_SUMMARY,
    SHEET_RAW,
    COLUMNS_PROGRESS,
    COLUMNS_UNIT_DETAILS,
    COLUMNS_INSTRUCTION,
    COLUMNS_SUMMARY,
    COLUMNS_RAW,
)

@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_curriculum.db")
    db_manager = DatabaseManager(db_file)
    return db_manager

@pytest.fixture
def repo(temp_db):
    return Repository(temp_db)

def test_excel_five_sheets_export(repo, tmp_path):
    """5シート構成の生成テスト"""
    # モックデータの準備
    ov = CurriculumOverview(
        classroom_name="梅田本校",
        classroom_code="9901",
        school_year="2026",
        student_id="STU100",
        student_name="佐藤花子",
        grade="高1",
        division="通常",
        subject="英語",
        school_course="普通科",
        row_index=0,
        status=ProcessState.SAVED,
    )
    repo.save_pages_init([ov])

    target = TargetInfo(
        target_no="T1", target_name="1学期中間", start_date="2026/04/01", end_date="2026/05/31",
        period_str="2026/04/01～2026/05/31", is_current=True, target_score="90", current_score="85",
        site_progress_rate="100%",
    )

    unit = UnitRecord(
        unit_no="1", unit_name="Lesson 1", middle_unit="Part 1", textbook="Crown I",
        problem_code="E01", score="9", max_score="10", score_rate="90",
        execution_date="2026/04/15", timing=TimingCategory.ON_TIME, is_executed=True,
        today_textbook="Crown I", execution_division="通常", confirm_test="合格",
        target_checks={"T1": True}
    )

    progress = TargetProgress(
        classroom="梅田本校", student_id="STU100", grade="高1", student_name="佐藤花子",
        division="通常", subject="英語", target_no="T1", target_name="1学期中間",
        start_date="2026/04/01", end_date="2026/05/31", period_str="2026/04/01～2026/05/31",
        is_current=True, textbooks_used="Crown I", target_score="90", current_score="85",
        target_unit_count=1, executed_count=1, executed_rate="100", on_time_count=1,
        on_time_rate="100", before_count=0, before_rate="0", after_count=0, after_rate="0",
        unexecuted_count=0, unexecuted_rate="0", latest_execution_date="2026/04/15",
    )

    eval_res = InstructionEvaluation(
        severity="PASS", author="田中", target_school="公立高校", textbook="Crown I (所持)",
        plan="予定通り進める", student_info="意欲的", test="単語テスト", homework="ワークp.10"
    )

    detail_data = CurriculumDetailData(
        overview=ov,
        raw_html="<html><body>mock detail</body></html>",
        fetch_time="2026-09-18 10:00:00",
        raw_instruction="作成者：田中...",
        materials_listed=["Crown I"],
        targets=[target],
        units=[unit],
        instruction_eval=eval_res,
        progress_list=[progress],
    )
    repo.save_parsed_result(detail_data)

    # Excel出力テスト
    exporter = ExcelExporter(repo)
    safe_writer = SafeExcelWriter(exporter, str(tmp_path / "output"))

    # 1. 最終出力
    final_path = safe_writer.export_final()
    assert os.path.exists(final_path)

    # 2. シート検証
    wb = openpyxl.load_workbook(final_path)
    assert wb.sheetnames == [
        SHEET_PROGRESS,
        SHEET_UNIT_DETAILS,
        SHEET_INSTRUCTION,
        SHEET_SUMMARY,
        SHEET_RAW,
    ]

    # 進捗率シートの列数・データ確認
    ws_prog = wb[SHEET_PROGRESS]
    assert ws_prog.max_column == len(COLUMNS_PROGRESS)
    assert ws_prog.max_row == 2 # ヘッダー + 1行データ
    assert ws_prog.cell(row=2, column=1).value == "梅田本校"
    assert ws_prog.cell(row=2, column=4).value == "佐藤花子"
    assert ws_prog.cell(row=2, column=16).value == 1 # 対象単元数

    # 単元詳細シートの列数・データ確認
    ws_unit = wb[SHEET_UNIT_DETAILS]
    assert ws_unit.max_column == len(COLUMNS_UNIT_DETAILS)
    assert ws_unit.max_row == 2
    assert ws_unit.cell(row=2, column=11).value == "Lesson 1"

    # 備考欄シートの確認
    ws_inst = wb[SHEET_INSTRUCTION]
    assert ws_inst.max_column == len(COLUMNS_INSTRUCTION)
    assert ws_inst.max_row == 2
    assert ws_inst.cell(row=2, column=7).value == "PASS"

    # サマリーシートの確認
    ws_sum = wb[SHEET_SUMMARY]
    assert ws_sum.max_column == len(COLUMNS_SUMMARY)
    assert ws_sum.max_row >= 2

    # 原文シートの確認
    ws_raw = wb[SHEET_RAW]
    assert ws_raw.max_column == len(COLUMNS_RAW)
    assert ws_raw.max_row == 2

    wb.close()
