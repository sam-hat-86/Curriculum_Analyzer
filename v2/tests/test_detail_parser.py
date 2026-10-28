from pathlib import Path
"""
実サンプルHTML (me.html / late.html) による詳細パーステスト
"""
import os
import pytest
from src.parser.detail_parser import DetailParser

SAMPLE_ME = str(Path(__file__).resolve().parent.parent.parent / "v1" / "me.html")
SAMPLE_LATE = str(Path(__file__).resolve().parent.parent.parent / "v1" / "late.html")

@pytest.fixture
def parser():
    return DetailParser()

@pytest.mark.skipif(not os.path.exists(SAMPLE_ME), reason='me.html not found')
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

@pytest.mark.skipif(not os.path.exists(SAMPLE_LATE), reason='late.html not found')
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


def test_parse_checkbox_variations(parser):
    """チェックボックスの様々なHTML表現形式（checked属性、aria-checked、Buefyクラス）のパース検証"""
    html = """
    <html><body>
    <table class="is-bordered">
        <thead>
            <tr>
                <th>No</th>
                <th>T1中間</th>
                <th>T2期末</th>
                <th>T3夏期</th>
                <th>単元情報</th>
                <th>得点/配点</th>
                <th>実施日</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>1</td>
                <!-- T1: checked属性 -->
                <td><input type="checkbox" checked="checked"></td>
                <!-- T2: aria-checked="true" -->
                <td><input type="checkbox" aria-checked="true"></td>
                <!-- T3: Buefyのis-checkedラッパー -->
                <td><span class="b-checkbox is-checked"><input type="checkbox"></span></td>
                <td>単元：展開公式<br>中単元：多項式</td>
                <td>10/10</td>
                <td>2026/04/10</td>
            </tr>
            <tr>
                <td>2</td>
                <!-- T1: 未チェック -->
                <td><input type="checkbox"></td>
                <!-- T2: checked属性 -->
                <td><input type="checkbox" checked></td>
                <!-- T3: 未チェック -->
                <td><span class="b-checkbox"><input type="checkbox"></span></td>
                <td>単元：因数分解</td>
                <td>-</td>
                <td>-</td>
            </tr>
        </tbody>
    </table>
    </body></html>
    """
    data = parser.parse(html)
    assert len(data.units) == 2

    # 行1
    u1 = data.units[0]
    assert u1.target_checks.get("T1") is True
    assert u1.target_checks.get("T2") is True
    assert u1.target_checks.get("T3") is True

    # 行2
    u2 = data.units[1]
    assert u2.target_checks.get("T1") is False
    assert u2.target_checks.get("T2") is True
    assert u2.target_checks.get("T3") is False



def test_parse_target_progress_delay(parser):
    """ターゲット名から「進捗遅れ」を摘出し、progress_delayに設定するテスト"""
    html = """
    <html><body>
    <table class="table-overview">
        <tbody>
            <tr><th>学籍番号</th><td>00000001</td><th>生徒名</th><td>テスト生徒</td></tr>
            <tr><th>学年</th><td>中1</td><th>受講区分</th><td>通常</td></tr>
            <tr><th>科目</th><td>英語</td><th>コース</th><td>標準</td></tr>
        </tbody>
    </table>
    <table class="sc2-sim-target">
        <tbody>
            <!-- T1: 進捗遅れあり -->
            <tr>
                <td>T1</td>
                <td>1学期中間/前期中間  進捗遅れ</td>
                <td>2026/04/01～2026/05/31</td>
                <td>80</td>
            </tr>
            <tr><td>50%</td></tr>
            <tr><td>70</td></tr>
            <!-- T2: 進捗遅れなし (通常) -->
            <tr>
                <td>T2</td>
                <td>1学期期末/前期中間2</td>
                <td>2026/06/01～2026/07/15</td>
                <td>85</td>
            </tr>
            <tr><td>100%</td></tr>
            <tr><td>85</td></tr>
            <!-- T3: 進捗遅れあり -->
            <tr>
                <td>T3</td>
                <td>2学期中間/前期期末  進捗遅れ</td>
                <td>2026/09/01～2026/10/20</td>
                <td>90</td>
            </tr>
            <tr><td>30%</td></tr>
            <tr><td>40</td></tr>
        </tbody>
    </table>
    </body></html>
    """
    data = parser.parse(html)
    assert len(data.targets) == 3

    # T1
    assert data.targets[0].target_no == "T1"
    assert data.targets[0].target_name == "1学期中間/前期中間"
    assert data.targets[0].progress_delay == "進捗遅れ"

    # T2
    assert data.targets[1].target_no == "T2"
    assert data.targets[1].target_name == "1学期期末/前期中間2"
    assert data.targets[1].progress_delay == "OK"

    # T3
    assert data.targets[2].target_no == "T3"
    assert data.targets[2].target_name == "2学期中間/前期期末"
    assert data.targets[2].progress_delay == "進捗遅れ"
