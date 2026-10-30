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
