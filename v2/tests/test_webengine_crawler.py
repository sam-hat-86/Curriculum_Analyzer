"""
WebEngineCrawler 複数タブ並行ワーカーの単体テスト。
モックを使って複数タブへのタスク割り当て、完了通知、安全停止、リトライ・スキップを検証。
"""
import sys
import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
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
    mock_worker1 = MagicMock()
    mock_worker2 = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        tab_views=[mock_worker1, mock_worker2],
        max_tabs=2,
        request_interval_sec=0.5,
        sheet_render_delay_sec=0.8,
        max_retries=2,
        retry_interval_sec=1.0,
        timeout_sec=5.0
    )

    assert crawler.max_tabs == 2
    assert crawler.request_interval_sec == 0.5
    assert crawler.sheet_render_delay_sec == 0.8
    assert crawler.max_retries == 2
    assert crawler.timeout_sec == 5.0
    assert len(crawler.worker_slots) == 2
    assert crawler.state == CrawlerState.IDLE
    assert crawler.is_running is False


def test_webengine_crawler_empty_targets(qapp):
    mock_view = MagicMock()
    mock_repo = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        tab_views=[MagicMock()],
    )

    finished_called = []
    crawler.crawl_finished.connect(lambda ok, msg: finished_called.append((ok, msg)))

    crawler.start_crawl([])

    assert len(finished_called) == 1
    assert finished_called[0][0] is True
    assert crawler.state == CrawlerState.IDLE


def test_webengine_crawler_multitab_dispatch_and_success(qapp):
    """複数タブへのタスク分散とHTML抽出・保存の完了フロー検証"""
    mock_view = MagicMock()
    mock_repo = MagicMock()
    mock_worker1 = MagicMock()
    mock_worker2 = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        tab_views=[mock_worker1, mock_worker2],
        max_tabs=2,
        request_interval_sec=0.1,
        sheet_render_delay_sec=0.1,
    )

    dummy_item1 = CurriculumOverview(
        classroom_name="テスト校", classroom_code="C001", school_year="2026",
        student_id="S001", student_name="生徒1", grade="中1", division="通常", subject="数学", row_index=0
    )
    dummy_item2 = CurriculumOverview(
        classroom_name="テスト校", classroom_code="C001", school_year="2026",
        student_id="S002", student_name="生徒2", grade="中2", division="通常", subject="英語", row_index=1
    )

    crawler.start_crawl([dummy_item1, dummy_item2])
    assert crawler.is_running is True
    assert len(crawler.worker_slots) == 2

    # スロット0がまず割り当てられる
    slot0 = crawler.worker_slots[0]
    slot1 = crawler.worker_slots[1]
    assert slot0.is_busy is True
    assert slot0.current_overview == dummy_item1

    # 時差ディスパッチでスロット1も割り当てられる
    crawler._dispatch_next()
    assert slot1.is_busy is True
    assert slot1.current_overview == dummy_item2

    # スロット0がHTML取得完了
    html_sample = "<html><body>" + "A" * 300 + "</body></html>"
    crawler.handle_slot_success(slot0, html_sample)
    assert mock_repo.update_page_fetched.call_count == 1
    assert crawler._completed_count == 1
    assert slot0.is_busy is False

    # スロット1がHTML取得完了
    finished_results = []
    crawler.crawl_finished.connect(lambda ok, msg: finished_results.append((ok, msg)))

    crawler.handle_slot_success(slot1, html_sample)
    assert mock_repo.update_page_fetched.call_count == 2
    assert crawler._completed_count == 2
    assert len(finished_results) == 1
    assert finished_results[0][0] is True
    assert crawler.state == CrawlerState.IDLE


def test_webengine_crawler_safe_stop(qapp):
    """安全停止: 進行中のスロット完了を待って停止することの検証"""
    mock_view = MagicMock()
    mock_repo = MagicMock()
    mock_worker = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        tab_views=[mock_worker],
        max_tabs=1,
    )

    items = [
        CurriculumOverview(
            classroom_name="テスト校", classroom_code="C001", school_year="2026",
            student_id="S1", student_name="生徒1", grade="高1", division="通常", subject="国語", row_index=0
        ),
        CurriculumOverview(
            classroom_name="テスト校", classroom_code="C001", school_year="2026",
            student_id="S2", student_name="生徒2", grade="高2", division="通常", subject="英語", row_index=1
        ),
    ]

    crawler.start_crawl(items)
    slot = crawler.worker_slots[0]
    assert slot.is_busy is True

    # 停止要求送信
    crawler.stop()
    assert crawler.state == CrawlerState.STOPPING
    assert crawler._stop_requested is True
    assert len(crawler._queue) == 0  # 後続キューはクリア

    finished_called = []
    crawler.crawl_finished.connect(lambda ok, msg: finished_called.append((ok, msg)))

    # 進行中だった生徒1が完了した時点で全停止すること
    crawler.handle_slot_success(slot, "<html><body>" + "B" * 300 + "</body></html>")
    assert len(finished_called) == 1
    assert finished_called[0][0] is True
    assert crawler.state == CrawlerState.IDLE


def test_webengine_crawler_retry_and_skip(qapp):
    """取得失敗時のリトライと上限超過スキップの検証"""
    mock_view = MagicMock()
    mock_repo = MagicMock()
    mock_worker = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        tab_views=[mock_worker],
        max_retries=1,
        retry_interval_sec=0.1,
    )

    item = CurriculumOverview(
        classroom_name="テスト校", classroom_code="C001", school_year="2026",
        student_id="S_FAIL", student_name="失敗生徒", grade="中3", division="通常", subject="数学", row_index=0
    )
    crawler.start_crawl([item])

    slot = crawler.worker_slots[0]

    # 1回目失敗 (リトライ対象)
    crawler.handle_slot_failure(slot, "通信エラー")
    assert slot.retry_count == 1
    assert mock_repo.update_page_fetch_failed.call_count == 0

    # 2回目失敗 (上限1回超過 -> スキップ)
    finished_called = []
    crawler.crawl_finished.connect(lambda ok, msg: finished_called.append((ok, msg)))

    crawler.handle_slot_failure(slot, "2回目失敗")
    assert mock_repo.update_page_fetch_failed.call_count == 1
    assert len(finished_called) == 1
    assert finished_called[0][0] is True


def test_worker_slot_checkbox_sync_on_render_ready(qapp):
    """WorkerSlot._on_render_ready が JavaScript によるチェックボックス属性同期を実行することを検証"""
    mock_view = MagicMock()
    mock_page = MagicMock()
    mock_view.page.return_value = mock_page
    mock_repo = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        tab_views=[mock_view],
        max_tabs=1,
    )
    slot = crawler.worker_slots[0]
    slot.is_busy = True
    slot.current_overview = CurriculumOverview(
        classroom_name="テスト校", classroom_code="C001", school_year="2026",
        student_id="S001", student_name="生徒1", grade="中1", division="通常", subject="数学", row_index=0
    )
    crawler._state = CrawlerState.RUNNING

    # runJavaScriptのコールバックを即時実行するモック (教室名取得JS -> チェックボックス同期JS)
    scripts_called = []
    def mock_run_js(script, callback):
        scripts_called.append(script)
        if "lesson_card_id" in script:
            callback({"found": False})
        else:
            assert "querySelectorAll" in script
            assert "checked" in script
            callback(None)

    mock_page.runJavaScript.side_effect = mock_run_js

    def mock_to_html(callback):
        callback("<html><body>" + "A" * 300 + "</body></html>")

    mock_page.toHtml.side_effect = mock_to_html

    slot._on_render_ready()

    assert mock_page.runJavaScript.call_count == 2
    assert any("checked" in s for s in scripts_called)
    assert mock_page.toHtml.call_count == 1
    assert mock_repo.update_page_fetched.call_count == 1



def test_worker_slot_ignores_stale_attempt_id(qapp):
    """古い attempt_id の遅延コールバックが到着しても二重失敗や誤保存が起きないことを検証 (A3)"""
    mock_view = MagicMock()
    mock_repo = MagicMock()
    mock_worker = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        tab_views=[mock_worker],
        max_retries=3,
    )
    item = CurriculumOverview(
        classroom_name="テスト校", classroom_code="C001", school_year="2026",
        student_id="S_STALE", student_name="遅延生徒", grade="中3", division="通常", subject="数学", row_index=0
    )
    crawler.start_crawl([item])
    slot = crawler.worker_slots[0]
    first_attempt = slot.attempt_id

    # 1回目の失敗処理により slot.attempt_id が進む
    crawler.handle_slot_failure(slot, "1回目タイムアウト", attempt_id=first_attempt)
    assert slot.retry_count == 1
    assert slot.attempt_id != first_attempt

    # 同じ古い first_attempt を持った遅延コールバックが後から発火しても無視されること
    crawler.handle_slot_failure(slot, "遅延した古い失敗通知", attempt_id=first_attempt)
    assert slot.retry_count == 1
    crawler.handle_slot_success(slot, "<html><body>" + "X" * 300 + "</body></html>", attempt_id=first_attempt)
    assert crawler._completed_count == 0


def test_crawler_pauses_on_auth_required(qapp):
    """セッション切れ検知時に PAUSED_AUTH 状態へ遷移し、進行中だった生徒がキュー先頭へ戻されることを検証 (D-6)"""
    mock_view = MagicMock()
    mock_repo = MagicMock()
    mock_worker1 = MagicMock()

    crawler = WebEngineCrawler(
        web_view=mock_view,
        repository=mock_repo,
        tab_views=[mock_worker1],
        max_tabs=1,
    )
    item1 = CurriculumOverview(
        classroom_name="テスト校", classroom_code="C001", school_year="2026",
        student_id="S1", student_name="生徒1", grade="中1", division="通常", subject="数学", row_index=0
    )
    item2 = CurriculumOverview(
        classroom_name="テスト校", classroom_code="C001", school_year="2026",
        student_id="S2", student_name="生徒2", grade="中2", division="通常", subject="英語", row_index=1
    )
    auth_signals = []
    crawler.auth_required.connect(lambda reason: auth_signals.append(reason))

    crawler.start_crawl([item1, item2])
    slot0 = crawler.worker_slots[0]
    assert slot0.current_overview == item1
    assert len(crawler._queue) == 1

    # セッション切れ発生
    crawler.handle_auth_required(slot0, "login画面へ転送")
    assert crawler.state == CrawlerState.PAUSED_AUTH
    assert len(auth_signals) == 1
    assert slot0.is_busy is False
    # 進行中だった item1 がキュー先頭に戻され、合計2件が保持されていること
    assert len(crawler._queue) == 2
    assert crawler._queue[0] == item1
