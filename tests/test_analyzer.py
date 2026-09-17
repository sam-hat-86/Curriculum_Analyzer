"""
進捗率集計・整合性・タイミング分析テスト (仕様書§14, §18, §40 & ユーザー合意決定)
"""
from datetime import date
import pytest
from src.models.curriculum import CurriculumOverview, TargetInfo, UnitRecord
from src.models.state import TimingCategory
from src.analyzer.progress_calculator import calculate_target_progress

@pytest.fixture
def mock_overview():
    return CurriculumOverview(
        classroom_name="本校",
        classroom_code="1001",
        school_year="2026",
        student_id="STU001",
        student_name="テスト生徒",
        grade="中2",
        division="通常",
        subject="数学",
    )

def test_progress_calculation_and_integrity(mock_overview):
    """
    対象単元数 = 期間内 + 期間前 + 期間後 + 未実施
    実施済み数 = 期間内 + 期間前 + 期間後
    の完全整合性テスト
    """
    target = TargetInfo(
        target_no="T1",
        target_name="1学期中間",
        start_date="2026/04/01",
        end_date="2026/05/31",
        period_str="2026/04/01～2026/05/31",
        is_current=True,
        target_score="80",
        current_score="75",
        site_progress_rate="80%",
    )

    # 単元データ:
    # 1. 期間前 (2026/03/25)
    # 2. 期間内 (2026/04/15)
    # 3. 期間内 (2026/05/10)
    # 4. 期間後 (2026/06/05)
    # 5. 未実施 (実施日なし)
    units = [
        UnitRecord(
            unit_no="1", unit_name="単元1", middle_unit="中1", textbook="テキストA",
            problem_code="P1", score="10", max_score="10", score_rate="100",
            execution_date="2026/03/25", timing=TimingCategory.BEFORE, is_executed=True,
            today_textbook="", execution_division="", confirm_test="",
            target_checks={"T1": True}
        ),
        UnitRecord(
            unit_no="2", unit_name="単元2", middle_unit="中1", textbook="テキストA",
            problem_code="P2", score="8", max_score="10", score_rate="80",
            execution_date="2026/04/15", timing=TimingCategory.ON_TIME, is_executed=True,
            today_textbook="", execution_division="", confirm_test="",
            target_checks={"T1": True}
        ),
        UnitRecord(
            unit_no="3", unit_name="単元3", middle_unit="中1", textbook="テキストB",
            problem_code="P3", score="5", max_score="10", score_rate="50",
            execution_date="2026/05/10", timing=TimingCategory.ON_TIME, is_executed=True,
            today_textbook="", execution_division="", confirm_test="",
            target_checks={"T1": True}
        ),
        UnitRecord(
            unit_no="4", unit_name="単元4", middle_unit="中1", textbook="テキストB",
            problem_code="P4", score="7", max_score="10", score_rate="70",
            execution_date="2026/06/05", timing=TimingCategory.AFTER, is_executed=True,
            today_textbook="", execution_division="", confirm_test="",
            target_checks={"T1": True}
        ),
        UnitRecord(
            unit_no="5", unit_name="単元5", middle_unit="中1", textbook="テキストB",
            problem_code="P5", score="-", max_score="-", score_rate="-",
            execution_date="-", timing=TimingCategory.UNEXECUTED, is_executed=False,
            today_textbook="", execution_division="", confirm_test="",
            target_checks={"T1": True}
        ),
    ]

    prog = calculate_target_progress(mock_overview, target, units)

    assert prog.target_unit_count == 5
    assert prog.executed_count == 4
    assert prog.executed_rate == "80"
    assert prog.on_time_count == 2
    assert prog.on_time_rate == "40"
    assert prog.before_count == 1
    assert prog.before_rate == "20"
    assert prog.after_count == 1
    assert prog.after_rate == "20"
    assert prog.unexecuted_count == 1
    assert prog.unexecuted_rate == "20"
    assert prog.latest_execution_date == "2026/06/05"
    assert "テキストA" in prog.textbooks_used
    assert "テキストB" in prog.textbooks_used

def test_undecided_period_mapping(mock_overview):
    """
    ユーザー合意決定:
    対策期間が未設定の場合、実施日があっても判定保留（期間外）とし、
    実施済み数に算入し、4分類では「期間後実施（期間外）」枠に集約する
    """
    target = TargetInfo(
        target_no="T1",
        target_name="対策期間なしターゲット",
        start_date="",
        end_date="",
        period_str="-",
        is_current=False,
        target_score="-",
        current_score="-",
        site_progress_rate="-",
    )

    units = [
        UnitRecord(
            unit_no="1", unit_name="単元1", middle_unit="", textbook="テキストA",
            problem_code="", score="-", max_score="-", score_rate="-",
            execution_date="2026/04/10", timing=TimingCategory.UNDECIDED, is_executed=True,
            today_textbook="", execution_division="", confirm_test="",
            target_checks={"T1": True}
        ),
        UnitRecord(
            unit_no="2", unit_name="単元2", middle_unit="", textbook="テキストA",
            problem_code="", score="-", max_score="-", score_rate="-",
            execution_date="-", timing=TimingCategory.UNEXECUTED, is_executed=False,
            today_textbook="", execution_division="", confirm_test="",
            target_checks={"T1": True}
        ),
    ]

    prog = calculate_target_progress(mock_overview, target, units)

    assert prog.target_unit_count == 2
    assert prog.executed_count == 1
    assert prog.after_count == 1 # 判定保留分が集約
    assert prog.unexecuted_count == 1
    assert prog.on_time_count == 0
    assert prog.before_count == 0
    assert prog.latest_execution_date == "2026/04/10"
