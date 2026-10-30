"""
教室自動巡回 (ClassroomNavigator, MainWindow連続巡回ステートマシン - 確定版) のユニットテスト
"""
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Signal, QUrl

from src.utils.config import AppConfig
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.browser.classroom_navigator import (
    ClassroomNavigator,
    get_click_classroom_cell_js,
    TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS,
    CHECK_CLASSROOM_SELECTED_JS,
    WAIT_FOR_SEARCH_LOAD_JS,
)
from src.gui.main_window import MainWindow


class DummyWebEngineView(QWidget):
    urlChanged = Signal(QUrl)
    loadFinished = Signal(bool)
    cookie_status_changed = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mock_page = MagicMock()

    def set_allowed_origin(self, origin):
        pass

    def setUrl(self, url):
        pass

    def page(self):
        return self._mock_page

    def has_auth_cookies(self):
        return True

    def is_authenticated(self):
        return True

    def create_tab_view(self, parent=None, disable_images=True):
        return DummyWebEngineView(parent)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_window(qapp, tmp_path):
    db_path = str(tmp_path / "test_patrol_final.db")
    db_mgr = DatabaseManager(db_path)
    repo = Repository(db_mgr)
    config = AppConfig()
    config.start_url = "https://example.com/login"
    config.max_tabs = 1

    with patch("src.gui.main_window.PersistentWebEngineView", DummyWebEngineView):
        window = MainWindow(config=config)
        window.repo = repo
        yield window
        window.close()


def test_click_classroom_cell_js_generation():
    """教室名セルクリックJS生成の検証"""
    js_code = get_click_classroom_cell_js(0, "31107")
    assert "targetIndex, targetCode" in js_code
    assert '"31107"' in js_code
    assert "targetRow.scrollIntoView" in js_code
    assert "cell.click()" in js_code
    assert "data-label='教室名'" in js_code


def test_trigger_input_and_background_click_js_syntax():
    """インプット押下 & 画面余白クリックJSの検証"""
    assert "input.focus()" in TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS
    assert "input.blur()" in TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS
    assert "bgTarget.click()" in TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS


def test_check_classroom_selected_js_syntax():
    """行選択完了判定JS (.taginput .tag の出現・教室名取得) の検証"""
    assert ".taginput .tag" in CHECK_CLASSROOM_SELECTED_JS
    assert "has-ellipsis" in CHECK_CLASSROOM_SELECTED_JS
    assert "selected: true" in CHECK_CLASSROOM_SELECTED_JS



def test_parse_json_safety():
    """ClassroomNavigator._parse_json の安全性テスト"""
    assert ClassroomNavigator._parse_json({"success": True}) == {"success": True}
    assert ClassroomNavigator._parse_json('{"active": true}') == {"active": True}
    assert ClassroomNavigator._parse_json("invalid json string") == {}
    assert ClassroomNavigator._parse_json(None) == {}


def test_on_patrol_modal_opened_least_privilege_safe_exit(test_window):
    """モーダル起動失敗 (権限なし) 時に勝手に解析を開始せず安全終了することの検証"""
    with patch.object(test_window, "start_process") as mock_start, \
         patch("src.gui.main_window.QMessageBox.warning") as mock_warn:

        test_window._on_patrol_modal_opened(
            False, "教室選択モーダルが開かないため、教室巡回は利用できません（自教室のみの閲覧権限です）。"
        )

        mock_warn.assert_called_once()
        mock_start.assert_not_called()
        assert test_window._is_patrol_mode is False


def test_on_patrol_table_initialized_starts_patrol_directly(test_window):
    """テーブル初期化完了後、ダイアログを挟まず即座に1行目から巡回が開始されることの検証"""
    mock_classrooms = [
        {"index": 0, "classroom_code": "31107", "classroom_name": "FS津久野駅前"},
        {"index": 1, "classroom_code": "31198", "classroom_name": "FS和泉中央"},
    ]

    with patch.object(test_window, "_run_current_patrol_step") as mock_step:
        test_window._on_patrol_table_initialized(True, mock_classrooms, "")

        assert test_window._is_patrol_mode is True
        assert test_window._patrol_total_classrooms == 2
        assert test_window._patrol_current_index == 0
        mock_step.assert_called_once()


def test_run_current_patrol_step_calls_navigator(test_window):
    """_run_current_patrol_step が対象行の選択・検索を実行することの検証"""
    test_window._is_patrol_mode = True
    test_window._patrol_total_classrooms = 2
    test_window._patrol_current_index = 0
    test_window._patrol_classroom_list = [
        {"index": 0, "classroom_code": "31107", "classroom_name": "FS津久野駅前"},
        {"index": 1, "classroom_code": "31198", "classroom_name": "FS和泉中央"},
    ]

    with patch.object(test_window.classroom_navigator, "select_classroom_row_and_search") as mock_select:
        test_window._run_current_patrol_step()

        mock_select.assert_called_once()
        args, kwargs = mock_select.call_args
        assert args[0] == 0  # row_idx
        assert args[1] == "31107"  # classroom_code


def test_prompt_next_classroom_advances_to_next_row(test_window):
    """1教室完了後、ポップアップを出さずに次の行インデックスへ自動進行することの検証"""
    test_window._is_patrol_mode = True
    test_window._patrol_total_classrooms = 2
    test_window._patrol_current_index = 0
    test_window._patrol_classroom_list = [
        {"index": 0, "classroom_code": "31107", "classroom_name": "FS津久野駅前"},
        {"index": 1, "classroom_code": "31198", "classroom_name": "FS和泉中央"},
    ]

    with patch("src.gui.main_window.QMessageBox.exec") as mock_msg_exec:
        test_window._prompt_next_classroom_or_export(total_pages=2)

        mock_msg_exec.assert_not_called()
        assert test_window._patrol_current_index == 1
        assert test_window._is_continuous_classroom_mode is True


def test_finish_patrol_when_all_rows_completed(test_window):
    """全行完了時に _finish_patrol が呼び出されることの検証"""
    test_window._is_patrol_mode = True
    test_window._patrol_total_classrooms = 2
    test_window._patrol_current_index = 2
    test_window._patrol_classroom_list = [
        {"index": 0, "classroom_code": "31107", "classroom_name": "FS津久野駅前"},
        {"index": 1, "classroom_code": "31198", "classroom_name": "FS和泉中央"},
    ]

    with patch.object(test_window, "_finish_patrol") as mock_finish:
        test_window._run_current_patrol_step()
        mock_finish.assert_called_once()


def test_wait_for_search_load_js_identifies_curriculum_table():
    """検索結果待機JSが「生徒」ヘッダーのカリキュラムテーブルを特定するロジックを持つことの検証"""
    assert "生徒" in WAIT_FOR_SEARCH_LOAD_JS
    assert "カリキュラム" in WAIT_FOR_SEARCH_LOAD_JS
    assert "targetTable" in WAIT_FOR_SEARCH_LOAD_JS
    assert "ready: true" in WAIT_FOR_SEARCH_LOAD_JS


def test_trigger_input_and_bg_click_supports_delete_tag():
    """既存タグ削除連携およびセレクタ群の検証"""
    assert "delBtn" in TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS
    assert ".taginput input" in TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS
    assert ".taginput-container" in TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS
    assert "delete_and_click" in TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS


def test_patrol_mode_skips_empty_classroom_without_popup(test_window):
    """巡回モード時、対象授業が0件でも警告ポップアップを出さずに次教室へ進むことの検証"""
    test_window._is_patrol_mode = True
    test_window._is_analyzing = True
    test_window._current_page_idx = 1
    test_window._patrol_total_classrooms = 2
    test_window._patrol_current_index = 0
    test_window._patrol_classroom_list = [
        {"index": 0, "classroom_code": "31107", "classroom_name": "FS津久野駅前"},
        {"index": 1, "classroom_code": "31198", "classroom_name": "FS和泉中央"},
    ]

    with patch.object(test_window.list_parser, "parse", return_value=[]), \
         patch.object(test_window, "_prompt_next_classroom_or_export") as mock_prompt, \
         patch("src.gui.main_window.QMessageBox.warning") as mock_warn:

        test_window._on_list_html_ready("<html><body>空テーブル</body></html>")

        mock_warn.assert_not_called()
        mock_prompt.assert_called_once_with(total_pages=0)


def _set_single_patrol_target(window):
    window._is_patrol_mode = True
    window._patrol_total_classrooms = 2
    window._patrol_current_index = 0
    window._skipped_classrooms = []
    window._patrol_classroom_list = [
        {"index": 0, "classroom_code": "31107", "classroom_name": "FS津久野駅前"},
        {"index": 1, "classroom_code": "31198", "classroom_name": "FS和泉中央"},
    ]


def _stop_db_writer(window):
    if getattr(window, "save_queue", None):
        window.save_queue.put(None)


def test_start_patrol_classroom_analysis_initializes_crawler(test_window):
    """巡回解析開始時、実クローラー(モックなし)で取得タブが登録されリスト抽出に進むことの検証"""
    _set_single_patrol_target(test_window)

    try:
        with patch.object(test_window, "_start_list_page_extraction") as mock_extract:
            test_window._start_patrol_classroom_analysis()

            assert test_window._is_analyzing is True
            assert len(test_window.worker_tab_views) == test_window.config.max_tabs
            assert test_window.crawler is not None
            assert len(test_window.crawler.worker_slots) == test_window.config.max_tabs
            mock_extract.assert_called_once()
            assert test_window._skipped_classrooms == []
    finally:
        _stop_db_writer(test_window)


def test_setup_crawl_session_disposes_previous_crawler(test_window):
    """共通セットアップを2回呼ぶと、前回のクローラーが破棄され新しいものに置き換わることの検証"""
    try:
        test_window._setup_crawl_session()
        first = test_window.crawler

        with patch.object(first, "deleteLater") as mock_delete:
            test_window._setup_crawl_session()
            mock_delete.assert_called_once()

        assert test_window.crawler is not first
        assert len(test_window.worker_tab_views) == test_window.config.max_tabs
    finally:
        _stop_db_writer(test_window)


def test_patrol_analysis_start_exception_skips_to_next_classroom(test_window):
    """解析開始で例外が起きた場合、ログ出力・スキップ登録・次教室への進行が行われることの検証"""
    _set_single_patrol_target(test_window)

    with patch.object(test_window, "_setup_crawl_session", side_effect=RuntimeError("boom")), \
         patch.object(test_window.logger, "exception") as mock_log, \
         patch("src.gui.main_window.QTimer.singleShot") as mock_timer:

        test_window._start_patrol_classroom_analysis()

        mock_log.assert_called_once()
        assert test_window._is_analyzing is False
        assert len(test_window._skipped_classrooms) == 1
        assert test_window._skipped_classrooms[0]["classroom_code"] == "31107"
        assert test_window._patrol_current_index == 1
        mock_timer.assert_called_once()
        assert mock_timer.call_args[0][1] == test_window._run_current_patrol_step


