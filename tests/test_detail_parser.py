"""
実サンプルHTML (me.html / late.html) による詳細パーステスト
"""
import os
import pytest
from src.parser.detail_parser import DetailParser
from src.models.state import TimingCategory

SAMPLE_ME = "v1/me.html"
SAMPLE_LATE = "v1/late.html"

@pytest.fixture
def parser():
    return DetailParser()

def test_parse_me_html(parser):
    """me.htmlの解析テスト"""
    assert os.path.exists(SAMPLE_ME), "me.htmlが存在しません"
    with open(SAMPLE_ME, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    data = parser.parse(html)
    assert data.overview.student_id == "00000000"
    assert "山田" in data.overview.student_name
    assert data.overview.grade == "高3"
    assert data.overview.division == "通常"
    assert data.overview.subject == "数学IIB"
    assert "大阪府立" in data.overview.school_course

    # 教材 & 備考
    assert len(data.materials_listed) >= 1
    assert "チャート式" in data.materials_listed[0]
    assert "[作成者]田中" in data.raw_instruction

    # ターゲット
    assert len(data.targets) >= 1
    t1 = data.targets[0]
    assert t1.target_no == "T1"
    assert "1学期" in t1.target_name

    # 単元
    assert len(data.units) > 0
    u1 = data.units[0]
    assert "定積分" in u1.unit_name
    assert u1.execution_date == "2022/03/07"
    assert u1.is_executed is True
    assert u1.score == "0"
    assert u1.max_score == "0"
    assert u1.score_rate == "-" # 配点0は"-"

def test_parse_late_html(parser):
    """late.html (複数ターゲットT1〜T5) の解析テスト"""
    assert os.path.exists(SAMPLE_LATE), "late.htmlが存在しません"
    with open(SAMPLE_LATE, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    data = parser.parse(html)
    assert data.overview.student_id == "00000000"
    assert "田中" in data.overview.student_name
    assert data.overview.grade == "中2"
    assert data.overview.subject == "中学数学"

    # ターゲット数 (T1〜T5)
    assert len(data.targets) == 5
    t1 = data.targets[0]
    assert t1.target_no == "T1"
    assert t1.start_date == "2026/03/01"
    assert t1.end_date == "2026/05/22"
    assert t1.period_str == "2026/03/01～2026/05/22"
    assert "83%" in t1.site_progress_rate

    # 単元
    assert len(data.units) > 0
    u1 = data.units[0]
    assert "多項式" in u1.unit_name
    assert u1.execution_date == "2026/04/08"
    assert u1.is_executed is True
    # T1チェックがTrueであること
    assert u1.target_checks.get("T1") is True
    assert u1.target_checks.get("T2") is False

    u2 = data.units[1]
    assert u2.score == "4"
    assert u2.max_score == "7"
    assert u2.score_rate == "57.1"
