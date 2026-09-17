"""
備考欄ルール評価テスト
"""
import pytest
from src.analyzer.instruction_evaluator import InstructionEvaluator
from src.utils.constants import (
    RANK_CRITICAL,
    RANK_ERROR,
    RANK_REVIEW,
    RANK_WARNING,
    RANK_PASS,
    CRIT_INSTRUCTION_EMPTY,
    ERR_AUTHOR_MISSING,
    ERR_TEXTBOOK_MISSING,
    ERR_TEXTBOOK_STATUS_MISSING,
    ERR_PLAN_MISSING,
    ERR_INFO_MISSING,
    ERR_TEST_MISSING,
    ERR_HOMEWORK_MISSING,
    ERR_SCHOOL_REQUIRED_HIGH3,
    REV_SCHOOL_UNCERTAIN,
    WARN_SCHOOL_NO_TYPE,
)

@pytest.fixture
def evaluator():
    return InstructionEvaluator()

def test_empty_instruction(evaluator):
    """空の備考欄でCRITICAL"""
    res = evaluator.evaluate("")
    assert res.severity == RANK_CRITICAL
    assert CRIT_INSTRUCTION_EMPTY in res.errors

def test_valid_instruction(evaluator):
    """すべての必須項目が揃っている場合"""
    text = (
        "作成者：山田太郎\n"
        "志望校：公立A高校\n"
        "教材：フォレスタ数学（所持）\n"
        "進め方：第1講から第5講まで演習を実施する\n"
        "生徒情報：非常に真面目で意欲的\n"
        "小テスト：毎回単語テストを実施\n"
        "宿題：テキストp.10～15"
    )
    res = evaluator.evaluate(text, grade="中2", division="通常", school_course="普通科")
    assert res.severity == RANK_PASS
    assert not res.errors
    assert res.author == "山田太郎"
    assert res.target_school == "公立A高校"
    assert res.test == "毎回単語テストを実施"

def test_missing_sections(evaluator):
    """作成者・進め方などの欠落でERROR"""
    text = "教材：ワーク\n生徒情報：真面目"
    res = evaluator.evaluate(text, grade="中2")
    assert res.severity == RANK_ERROR
    assert ERR_AUTHOR_MISSING in res.errors
    assert ERR_PLAN_MISSING in res.errors
    assert ERR_TEST_MISSING in res.errors
    assert ERR_HOMEWORK_MISSING in res.errors
    assert ERR_TEXTBOOK_STATUS_MISSING in res.errors

def test_high3_school_required(evaluator):
    """高3で志望校なしでERROR"""
    text = (
        "作成者：山田\n"
        "教材：フォレスタ（所持）\n"
        "進め方：演習を中心に進める\n"
        "生徒情報：集中力がある\n"
        "小テスト：確認テスト\n"
        "宿題：問題集1章"
    )
    res = evaluator.evaluate(text, grade="高3")
    assert res.severity == RANK_ERROR
    assert ERR_SCHOOL_REQUIRED_HIGH3 in res.errors
