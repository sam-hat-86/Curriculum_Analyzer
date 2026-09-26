"""
WebEngineCrawler の単体テスト。
モックを使ってイベント駆動フローとリトライ・完了通知・状態マシンを検証。
"""
import sys
import json
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from src.crawler.webengine_crawler import WebEngineCrawler, CrawlerState
from src.models.curriculum import CurriculumOverview


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_webengine_crawler_init(qapp):
    mock_view = MagicMock()
    mock_repo = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        request_interval_sec=0.5,
        max_retries=2,
        retry_interval_sec=1.0,
        timeout_sec=5.0
    )

    assert crawler.max_retries == 2
    assert crawler.request_interval_sec == 0.5
    assert crawler.timeout_sec == 5.0
    assert crawler._is_running is False
    assert crawler.state == CrawlerState.IDLE


def test_webengine_crawler_empty_targets(qapp):
    mock_view = MagicMock()
    mock_repo = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
    )

    finished_called = []
    crawler.crawl_finished.connect(lambda ok, msg: finished_called.append((ok, msg)))

    crawler.start_crawl([])

    assert len(finished_called) == 1
    assert finished_called[0][0] is True
    assert crawler.state == CrawlerState.IDLE


def test_webengine_crawler_state_machine_transition(qapp):
    """状態マシンの状態遷移と同一画面遷移のハンドリングを検証"""
    mock_view = MagicMock()
    mock_view.url.return_value = QUrl("http://10.200.5.191/scube2/curriculum/list")
    mock_repo = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        request_interval_sec=0.5,
    )

    dummy_item = CurriculumOverview(
        classroom_name="テスト校",
        classroom_code="C001",
        school_year="2026",
        student_id="12345",
        student_name="テスト生徒",
        grade="中3",
        division="通常",
        subject="中学数学",
        row_index=1,
    )

    # クロール開始
    crawler.start_crawl([dummy_item])
    assert crawler._is_running is True
    assert crawler._list_url == "http://10.200.5.191/scube2/curriculum/list"

    # アイテム処理中状態へ移行
    crawler._state = CrawlerState.WAIT_SHEET_LOAD

    # 1. 一覧画面と同じURLでの loadFinished は無視されること
    mock_view.url.return_value = QUrl("http://10.200.5.191/scube2/curriculum/list")
    crawler._on_web_view_load_finished(True)
    assert crawler.state == CrawlerState.WAIT_SHEET_LOAD

    # 2. シート画面への遷移を検知して EXTRACTING へ移行すること
    mock_view.url.return_value = QUrl("http://10.200.5.191/scube2/student/sheet?id=12345")
    crawler._on_web_view_load_finished(True)
    assert crawler.state == CrawlerState.EXTRACTING

    # 3. EXTRACTING 状態での余分な loadFinished は無視されること
    crawler._on_web_view_load_finished(True)
    assert crawler.state == CrawlerState.EXTRACTING


def test_webengine_crawler_return_to_list_and_dom_check(qapp):
    """一覧画面への直接復帰ロードとシミュレーションボタン検出による描画同期の検証"""
    mock_view = MagicMock()
    mock_page = MagicMock()
    mock_view.page.return_value = mock_page
    mock_view.url.return_value = QUrl("http://10.200.5.191/scube2/student/sheet?id=12345")
    mock_repo = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        request_interval_sec=0.5,
    )
    crawler.target_overviews = [
        CurriculumOverview(
            classroom_name="テスト校",
            classroom_code="C001",
            school_year="2026",
            student_id="12345",
            student_name="テスト生徒",
            grade="中3",
            division="通常",
            subject="中学数学",
            row_index=1,
        )
    ]
    crawler._is_running = True
    crawler._list_url = "http://10.200.5.191/scube2/curriculum/list"
    crawler._state = CrawlerState.EXTRACTING

    # HTMLを返却して復帰を実行
    html_sample = "<html><body>" + "A" * 300 + "</body></html>"
    def fake_to_html(callback):
        callback(html_sample)
    mock_page.toHtml.side_effect = fake_to_html

    crawler._extract_html_from_main_view_and_go_back()

    # DBに保存され、back() は呼ばれず、直接 load(一覧URL) が呼ばれていること
    assert mock_repo.update_page_fetched.called
    assert mock_view.back.call_count == 0
    assert mock_view.load.called
    assert mock_view.load.call_args[0][0] == QUrl("http://10.200.5.191/scube2/curriculum/list")
    assert crawler.state == CrawlerState.RETURNING_TO_LIST

    # 1. hasSimBtn が False の場合はまだ復帰完了にならないこと
    def fake_run_js_loading(script, callback):
        result = json.dumps({
            "rowCount": 4,
            "hasSimBtn": False,
            "url": "http://10.200.5.191/scube2/curriculum/list"
        })
        callback(result)
    mock_page.runJavaScript.side_effect = fake_run_js_loading
    crawler._check_returned_to_list()
    assert crawler.state == CrawlerState.RETURNING_TO_LIST
    assert crawler._current_index == 0

    # 2. hasSimBtn が True になったら描画完了として復帰完了になること
    def fake_run_js_loaded(script, callback):
        result = json.dumps({
            "rowCount": 10,
            "hasSimBtn": True,
            "url": "http://10.200.5.191/scube2/curriculum/list"
        })
        callback(result)
    mock_page.runJavaScript.side_effect = fake_run_js_loaded
    crawler._check_returned_to_list()

    # 復帰成功し、WAIT_INTERVAL 状態へ移行していること
    assert crawler.state == CrawlerState.WAIT_INTERVAL
    assert crawler._current_index == 1


def test_webengine_crawler_recovery_and_safe_stop(qapp):
    """5秒タイムアウト時の最大2回再ロードおよび安全停止の検証"""
    mock_view = MagicMock()
    mock_repo = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
    )
    crawler._is_running = True
    crawler._list_url = "http://10.200.5.191/scube2/curriculum/list"
    crawler._state = CrawlerState.RETURNING_TO_LIST

    finished_called = []
    crawler.crawl_finished.connect(lambda ok, msg: finished_called.append((ok, msg)))

    # 1回目タイムアウト: 再ロード試行 (1/2)
    crawler._on_return_to_list_timeout()
    assert crawler._recovery_retry_count == 1
    assert mock_view.load.call_count == 1

    # 2回目タイムアウト: 再ロード試行 (2/2)
    crawler._on_return_to_list_timeout()
    assert crawler._recovery_retry_count == 2
    assert mock_view.load.call_count == 2
    assert crawler._is_running is True

    # 3回目タイムアウト: 上限超過で安全停止
    crawler._on_return_to_list_timeout()
    assert len(finished_called) == 1
    assert finished_called[0][0] is False
    assert crawler._is_running is False
    assert crawler.state == CrawlerState.IDLE

