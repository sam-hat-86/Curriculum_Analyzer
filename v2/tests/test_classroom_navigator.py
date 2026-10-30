"""
教室自動巡回 (ClassroomNavigator, ClassroomPatrolDialog, MainWindow連携) のユニットテスト
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QWidget, QDialog
from PySide6.QtCore import Signal, QUrl

from src.utils.config import AppConfig
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.browser.classroom_navigator import (
    ClassroomNavigator,
    CHECK_MODAL_ACTIVE_JS,
    OPEN_CLASS_MODAL_JS,
    FETCH_CLASSROOMS_JS,
    CLICK_SEARCH_BUTTON_JS,
    get_select_classroom_js,
)
from src.gui.classroom_dialog import ClassroomPatrolDialog
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
    db_path = str(tmp_path / "test_patrol.db")
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


def test_select_classroom_js_generation():
    """教室選択JSコード生成の検証 (教室コードのエスケープ等)"""
    js_code = get_select_classroom_js("31107")
    assert '"31107"' in js_code
    assert "targetRow.scrollIntoView" in js_code
    assert "clickTarget.click()" in js_code

    # 特殊文字のエスケープ検証
    js_special = get_select_classroom_js('FS"テスト\'教室')
    assert '\\"テスト' in js_special or 'FS\\"テスト' in js_special


def test_parse_json_safety():
    """ClassroomNavigator._parse_json の安全性テスト"""
    assert ClassroomNavigator._parse_json({"success": True}) == {"success": True}
    assert ClassroomNavigator._parse_json('{"active": true}') == {"active": True}
    assert ClassroomNavigator._parse_json("invalid json string") == {}
    assert ClassroomNavigator._parse_json(None) == {}


def test_classroom_patrol_dialog(qapp):
    """ClassroomPatrolDialogの初期化、全選択/全解除、件数計算の検証"""
    mock_classrooms = [
        {"classroom_code": "31107", "classroom_name": "FS津久野駅前", "area_name": "大阪南２", "block_name": "関西_大阪南"},
        {"classroom_code": "31198", "classroom_name": "FS和泉中央", "area_name": "大阪南２", "block_name": "関西_大阪南"},
        {"classroom_code": "31201", "classroom_name": "FS光明池", "area_name": "大阪南２", "block_name": "関西_大阪南"},
    ]

    dialog = ClassroomPatrolDialog(mock_classrooms)
    assert dialog.table.rowCount() == 3
    assert len(dialog.checkboxes) == 3

    # 初期状態は全選択
    selected = dialog.get_selected_classrooms()
    assert len(selected) == 3
    assert dialog.lbl_selected_count.text() == "巡回対象: 3 / 3 教室"
    assert dialog.btn_start.isEnabled() is True

    # すべて解除
    dialog._deselect_all()
    assert dialog.lbl_selected_count.text() == "巡回対象: 0 / 3 教室"
    assert dialog.btn_start.isEnabled() is False
    assert len(dialog.get_selected_classrooms()) == 0

    # 1つだけ選択
    dialog.checkboxes[1].setChecked(True)
    assert dialog.lbl_selected_count.text() == "巡回対象: 1 / 3 教室"
    assert dialog.btn_start.isEnabled() is True
    assert dialog.get_selected_classrooms() == [mock_classrooms[1]]

    # すべて選択
    dialog._select_all()
    assert len(dialog.get_selected_classrooms()) == 3
    dialog.close()


def test_on_classrooms_fetched_least_privilege_fallback(test_window):
    """モーダル起動失敗 (権限なしタイムアウト) 時に自教室単一解析へ自動フォールバックすることの検証"""
    with patch.object(test_window, "start_process") as mock_start, \
         patch("src.gui.main_window.QMessageBox.information") as mock_info:
        
        test_window._on_classrooms_fetched(
            False, [], "複数教室の選択権限がありません (自教室のみ閲覧可能)"
        )

        # 情報ポップアップが表示され、自教室解析 start_process() が呼び出されること
        mock_info.assert_called_once()
        mock_start.assert_called_once()
        assert test_window._is_patrol_mode is False


def test_on_classrooms_fetched_single_classroom_direct_start(test_window):
    """教室が1件のみの場合、ダイアログをスキップして直接解析開始されることの検証"""
    single_classroom = [
        {"classroom_code": "31107", "classroom_name": "FS津久野駅前", "area_name": "大阪南２", "block_name": "関西_大阪南"}
    ]

    with patch.object(test_window, "start_process") as mock_start, \
         patch("src.gui.classroom_dialog.ClassroomPatrolDialog") as mock_dialog:

        test_window._on_classrooms_fetched(True, single_classroom, "")

        # 1件のみの場合はダイアログを開かず直接 start_process() が呼ばれること
        mock_dialog.assert_not_called()
        mock_start.assert_called_once()


def test_patrol_queue_navigation(test_window):
    """巡回キューの設定と順次遷移の検証"""
    mock_classrooms = [
        {"classroom_code": "31107", "classroom_name": "FS津久野駅前"},
        {"classroom_code": "31198", "classroom_name": "FS和泉中央"},
    ]

    with patch.object(test_window.classroom_navigator, "select_and_search") as mock_select:
        test_window._setup_and_start_patrol(mock_classrooms)

        assert test_window._is_patrol_mode is True
        assert test_window._patrol_total_classrooms == 2
        assert len(test_window._patrol_classroom_queue) == 1  # 1件目は取り出されて実行中
        assert test_window._current_patrol_classroom["classroom_code"] == "31107"

        # select_and_search がコード "31107" で呼び出されていること
        mock_select.assert_called_once()
        args, kwargs = mock_select.call_args
        assert args[0] == "31107"


def test_prompt_next_classroom_or_export_skips_in_patrol_mode(test_window):
    """巡回モード時は確認ポップアップを表示せず、自動的に次教室へ遷移することの検証"""
    test_window._is_patrol_mode = True
    test_window._current_patrol_classroom = {"classroom_code": "31107", "classroom_name": "FS津久野駅前"}
    test_window._patrol_classroom_queue = [{"classroom_code": "31198", "classroom_name": "FS和泉中央"}]

    with patch("src.gui.main_window.QMessageBox.exec") as mock_msg_exec, \
         patch.object(test_window, "_navigate_next_patrol_classroom") as mock_next:

        test_window._prompt_next_classroom_or_export(total_pages=3)

        # ポップアップは表示されないこと
        mock_msg_exec.assert_not_called()
        # 次教室への準備状態 (_is_continuous_classroom_mode) になること
        assert test_window._is_continuous_classroom_mode is True
