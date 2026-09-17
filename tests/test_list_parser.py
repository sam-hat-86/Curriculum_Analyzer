"""
カリキュラム一覧HTML (sampleMSL.html) パーステスト
"""
import os
import pytest
from src.parser.list_parser import ListParser

SAMPLE_MSL = "v1/sampleMSL.html"

def test_parse_sample_msl():
    """sampleMSL.html から全授業行を抽出できるかテスト"""
    assert os.path.exists(SAMPLE_MSL), "sampleMSL.htmlが存在しません"
    with open(SAMPLE_MSL, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    parser = ListParser()
    overviews = parser.parse(html, classroom_name="天王寺本校", classroom_code="43210", school_year="2026年度")

    assert len(overviews) == 11
    # 1件目の確認: '00000001山田太郎'
    ov0 = overviews[0]
    assert ov0.student_id == "00000001"
    assert "山田" in ov0.student_name
    assert "太郎" in ov0.student_name
    assert "高" in ov0.grade
    assert ov0.division == "春期講習"
    assert ov0.subject == "数学IA"
    assert ov0.classroom_name == "天王寺本校"

    # 2件目の確認: '00000002田中二郎'
    ov1 = overviews[1]
    assert ov1.student_id == "00000002"
    assert "田中" in ov1.student_name
    assert "二郎" in ov1.student_name
    assert "中" in ov1.grade
    assert ov1.division == "春期講習"
    assert ov1.subject == "中学数学"
