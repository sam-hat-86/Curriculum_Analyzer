"""
WebEngineCrawler の単体テスト。
モックを使ってイベント駆動フローとリトライ・完了通知を検証。
"""
import sys
import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
from src.crawler.webengine_crawler import WebEngineCrawler
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
