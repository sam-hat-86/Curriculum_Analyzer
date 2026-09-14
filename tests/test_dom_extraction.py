"""
モックHTMLを用いたDOM抽出テスト (仕様書 v8 §24)
- 教室名・教室コード・年度の抽出テスト
- テーブル行の抽出テスト
- セレクタフォールバック動作テスト
- 次へボタン検知テスト
- DOM安定性判定（ローディング表示時の動作）テスト
"""

import json
import os
import sys
from pathlib import Path
import pytest

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineCore import QWebEnginePage


@pytest.fixture(scope="session")
def qapp():
    """QApplication instance for WebEngine tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def js_script():
    """Load extract_table.js"""
    js_path = Path(__file__).resolve().parent.parent / "src" / "browser" / "extract_table.js"
    with open(js_path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def mock_html_path():
    """Path to mock HTML file"""
    path = Path(__file__).resolve().parent / "fixtures" / "mock_curriculum_page.html"
    return path


def run_extraction(page: QWebEnginePage, js_code: str, custom_selectors: dict = None, timeout_ms: int = 5000) -> dict:
    """Helper to inject selectors and run extract_table.js synchronously with event loop"""
    if custom_selectors is not None:
        selectors_json = json.dumps(custom_selectors, ensure_ascii=False)
        full_js = f"window.__CURRICULUM_SELECTORS__ = {selectors_json};\n" + js_code
    else:
        full_js = "delete window.__CURRICULUM_SELECTORS__;\n" + js_code

    result = None
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(timeout_ms)

    def on_finished(res):
        nonlocal result
        result = res
        if timer.isActive():
            timer.stop()
        loop.quit()

    def on_timeout():
        loop.quit()

    timer.timeout.connect(on_timeout)
    timer.start()
    page.runJavaScript(full_js, on_finished)
    loop.exec()
    return result


def load_page(page: QWebEnginePage, file_path: Path, timeout_ms: int = 5000):
    """Helper to load HTML file into page synchronously"""
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(timeout_ms)

    def on_load(ok):
        if timer.isActive():
            timer.stop()
        loop.quit()

    timer.timeout.connect(loop.quit)
    timer.start()
    page.loadFinished.connect(on_load)
    page.load(QUrl.fromLocalFile(str(file_path)))
    loop.exec()


def test_dom_extraction_basic_table_and_classroom(qapp, js_script, mock_html_path):
    """v8 §24.2: 教室名・教室コード・年度の抽出およびテーブル行抽出テスト"""
    page = QWebEnginePage()
    load_page(page, mock_html_path)

    res = run_extraction(page, js_script)
    assert res is not None
    assert res.get("success") is True, f"Extraction failed: {res}"

    # 教室情報の検証
    cls_info = res.get("classroomInfo", {})
    assert cls_info.get("classroomName") == "天王寺本校"
    assert cls_info.get("classroomCode") == "43210"
    assert cls_info.get("schoolYear") == "2026年度"

    # テーブル行の抽出検証
    rows = res.get("rows", [])
    assert len(rows) == 2
    col_map = res.get("columnMap", {})
    assert "studentId" in col_map
    assert "division" in col_map
    assert "subject" in col_map
    assert "instruction" in col_map

    first_row = rows[0]
    assert first_row[col_map["studentId"]] == "STU_001"
    assert first_row[col_map["division"]] == "通常授業"
    assert first_row[col_map["subject"]] == "英語"
    assert "作成者：山田" in first_row[col_map["instruction"]]

    # 次へボタン検知 (v8 §24.2)
    assert res.get("hasNext") is True

    # 採用セレクタの記録 (v8 §25)
    matched = res.get("matchedSelectors", {})
    assert "classroomName" in matched
    assert "classroomCode" in matched
    assert "schoolYear" in matched


def test_dom_extraction_selector_fallback(qapp, js_script, mock_html_path):
    """v8 §24.2: セレクタフォールバック動作テスト (第1候補が不一致でも第2候補やフォールバックで抽出)"""
    page = QWebEnginePage()
    load_page(page, mock_html_path)

    # 第1候補にあえて存在しないセレクタを指定し、第2候補で抽出できるかテスト
    custom_selectors = {
        "classroom_name": [
            ".non-existent-selector",
            ".branch-name-text"
        ],
        "classroom_code": [
            "#non-existent-code",
            ".branch-code-input input"
        ],
        "school_year": [
            ".non-existent-year",
            "select.school-year"
        ],
        "target_table": [
            "table.non-existent",
            "table.curriculum-table"
        ]
    }

    res = run_extraction(page, js_script, custom_selectors=custom_selectors)
    assert res is not None
    assert res.get("success") is True

    assert res.get("classroomName") == "天王寺本校"
    assert res.get("classroomCode") == "43210"
    assert res.get("schoolYear") == "2026年度"

    matched = res.get("matchedSelectors", {})
    assert matched.get("classroomName") == ".branch-name-text"
    assert matched.get("classroomCode") == ".branch-code-input input"
    assert matched.get("schoolYear") == "select.school-year"


def test_dom_extraction_stability_loading_indicator(qapp, js_script, mock_html_path):
    """v8 §9, §24.2: DOM安定性判定（ローディング表示時の動作）テスト"""
    page = QWebEnginePage()
    load_page(page, mock_html_path)

    # ローディング要素を表示状態にする (display: block)
    loop = QEventLoop()
    page.runJavaScript(
        "document.getElementById('loadingIndicator').style.display = 'block';",
        lambda _: loop.quit()
    )
    loop.exec()

    # extract_table.js を実行すると、ローディング中を検知して notStable=true を返すこと
    res = run_extraction(page, js_script)
    assert res is not None
    assert res.get("success") is False
    assert res.get("notStable") is True
    assert res.get("reason") == "loading_in_progress"

    # ローディング要素を非表示に戻す (display: none)
    loop2 = QEventLoop()
    page.runJavaScript(
        "document.getElementById('loadingIndicator').style.display = 'none';",
        lambda _: loop2.quit()
    )
    loop2.exec()

    # 再度実行すると正常に抽出できること
    res_stable = run_extraction(page, js_script)
    assert res_stable is not None
    assert res_stable.get("success") is True


def test_dom_extraction_missing_classroom_info(qapp, js_script, mock_html_path):
    """v9 §40.3: 教室名・教室コードが欠落している場合の抽出挙動テスト"""
    page = QWebEnginePage()
    load_page(page, mock_html_path)

    # 教室情報要素をDOMから除去
    loop = QEventLoop()
    page.runJavaScript("""
        const b = document.querySelector('.search-branch');
        if (b) b.remove();
        const c = document.querySelector('.branch-code-input');
        if (c) c.remove();
    """, lambda _: loop.quit())
    loop.exec()

    res = run_extraction(page, js_script)
    assert res is not None
    # 教室名・コードが空文字であることを確認
    assert res.get("classroomName") == ""
    assert res.get("classroomCode") == ""


def test_dom_extraction_last_page_no_next(qapp, js_script, mock_html_path):
    """v9 §40.3: 最終ページで「次へ」ボタンが存在しない／無効化されている場合のテスト"""
    page = QWebEnginePage()
    load_page(page, mock_html_path)

    # 次へボタンを除去
    loop = QEventLoop()
    page.runJavaScript("""
        const nextBtn = document.querySelector('.btn-next');
        if (nextBtn) nextBtn.remove();
    """, lambda _: loop.quit())
    loop.exec()

    res = run_extraction(page, js_script)
    assert res is not None
    assert res.get("success") is True
    assert res.get("hasNext") is False


def test_dom_extraction_zero_rows_table(qapp, js_script, mock_html_path):
    """v9 §40.3: データ行が0件（ヘッダーのみ）のテーブル抽出テスト"""
    page = QWebEnginePage()
    load_page(page, mock_html_path)

    # tbody内の行を空にする
    loop = QEventLoop()
    page.runJavaScript("""
        const tbody = document.querySelector('.curriculum-table tbody');
        if (tbody) tbody.innerHTML = '';
    """, lambda _: loop.quit())
    loop.exec()

    res = run_extraction(page, js_script)
    assert res is not None
    assert res.get("success") is True
    assert len(res.get("rows", [])) == 0


def test_dom_extraction_missing_essential_columns(qapp, js_script, mock_html_path):
    """v9 §40.3: 必須列（学籍番号など）が認識できないテーブルのテスト"""
    page = QWebEnginePage()
    load_page(page, mock_html_path)

    # ヘッダーをすべて無関係な文字列に書き換える
    loop = QEventLoop()
    page.runJavaScript("""
        const ths = document.querySelectorAll('.curriculum-table th');
        ths.forEach(th => th.innerText = 'ダミー項目');
    """, lambda _: loop.quit())
    loop.exec()

    res = run_extraction(page, js_script)
    assert res is not None
    # 必須列 studentId がマッピングできないため success は false または columnMap に studentId なし
    col_map = res.get("columnMap") or {}
    assert "studentId" not in col_map or res.get("success") is False

