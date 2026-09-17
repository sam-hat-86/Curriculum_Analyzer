"""
コピペ疑い検出テスト (仕様書§23)
- 15文字未満: 完全一致
- 15文字以上: 2-gram Jaccard類似度 >= 0.8
- 3件以上で警告付与
"""
import pytest
from src.models.curriculum import CurriculumOverview, CurriculumDetailData
from src.models.evaluation import InstructionEvaluation
from src.analyzer.copypaste_detector import detect_copy_paste
from src.utils.constants import WARN_COPY_PASTE_SUSPECTED

def _create_mock_detail(author: str, student_info: str, student_id: str) -> CurriculumDetailData:
    ov = CurriculumOverview(
        classroom_name="本校", classroom_code="101", school_year="2026",
        student_id=student_id, student_name=f"生徒{student_id}", grade="中2",
        division="通常", subject="数学"
    )
    ev = InstructionEvaluation(
        severity="PASS",
        author=author,
        student_info=student_info
    )
    return CurriculumDetailData(
        overview=ov,
        raw_html="",
        fetch_time="",
        raw_instruction="",
        instruction_eval=ev
    )

def test_copypaste_detection_3_duplicates():
    """同一作成者で3件以上類似した生徒情報がある場合に警告が付与される"""
    text1 = "真面目で理解力があり、宿題もしっかりこなせています。"
    text2 = "真面目で理解力があり、宿題もしっかりこなせています。"
    text3 = "真面目で理解力があり、宿題もしっかりこなせています。"
    text4 = "計算スピードが速くケアレスミスが課題です。"

    rec1 = _create_mock_detail("山田", text1, "STU1")
    rec2 = _create_mock_detail("山田", text2, "STU2")
    rec3 = _create_mock_detail("山田", text3, "STU3")
    rec4 = _create_mock_detail("山田", text4, "STU4")

    records = [rec1, rec2, rec3, rec4]
    detect_copy_paste(records)

    assert WARN_COPY_PASTE_SUSPECTED in rec1.instruction_eval.warnings
    assert WARN_COPY_PASTE_SUSPECTED in rec2.instruction_eval.warnings
    assert WARN_COPY_PASTE_SUSPECTED in rec3.instruction_eval.warnings
    assert WARN_COPY_PASTE_SUSPECTED not in rec4.instruction_eval.warnings
    assert rec1.instruction_eval.severity == "WARNING"

def test_copypaste_different_author():
    """作成者が異なる場合は3件類似していてもコピペ警告は付与されない"""
    text = "真面目で理解力があり、宿題もしっかりこなせています。"
    rec1 = _create_mock_detail("山田", text, "STU1")
    rec2 = _create_mock_detail("佐藤", text, "STU2")
    rec3 = _create_mock_detail("鈴木", text, "STU3")

    records = [rec1, rec2, rec3]
    detect_copy_paste(records)

    assert WARN_COPY_PASTE_SUSPECTED not in rec1.instruction_eval.warnings
    assert WARN_COPY_PASTE_SUSPECTED not in rec2.instruction_eval.warnings
    assert WARN_COPY_PASTE_SUSPECTED not in rec3.instruction_eval.warnings
