"""
v2.3.0 GUI コンポーネントおよび新機能の単体テスト
- Material Design Icons ベクターアイコンの正常生成テスト
- LogViewerWidget の「使い方」表示と非破壊ログ切り替え、ツールバー連動テスト
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication

# テスト実行用の QApplication インスタンス取得
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_mdi_icons_all_rendered(qapp):
    """全 12 種類の MDI アイコンが正常に QIcon として生成されることをテスト"""
    from src.gui.icons import get_mdi_icon, MDI_SVG_PATHS

    assert len(MDI_SVG_PATHS) >= 12

    for name in MDI_SVG_PATHS:
        icon = get_mdi_icon(name)
        assert not icon.isNull(), f"Icon '{name}' should not be null"
        
        # 異なるカラー・サイズ指定でも正常に生成されること
        colored_icon = get_mdi_icon(name, color="#107C41", size=32)
        assert not colored_icon.isNull(), f"Colored icon '{name}' should not be null"


def test_log_viewer_help_initial_state_and_toolbar(qapp):
    """LogViewerWidget の初期状態（使い方表示、ツールバー制御）をテスト"""
    from src.gui.log_viewer import LogViewerWidget

    widget = LogViewerWidget()

    # 初期状態は「使い方」表示
    assert widget.is_showing_help is True
    assert widget.stacked_widget.currentIndex() == 0

    # 「使い方」表示中は「自動スクロール」と「ログクリア」が非表示設定 (isHidden() == True)
    assert widget.auto_scroll_cb.isHidden() is True
    assert widget.clear_btn.isHidden() is True
    assert "ログ表示" in widget.toggle_view_btn.text()

    # 使い方 HTML 内にご指定の4ステップが含まれていること
    help_html = widget.help_edit.toHtml()
    assert "1." in help_html and "ログインする" in help_html
    assert "2." in help_html and "生徒カリキュラム一覧" in help_html
    assert "3." in help_html and "在籍区分・受講区分を選択" in help_html
    assert "4." in help_html and "処理開始" in help_html


def test_log_viewer_switch_and_log_persistence(qapp):
    """ログへの切り替えと裏でのログ蓄積・保持、トグル動作をテスト"""
    from src.gui.log_viewer import LogViewerWidget

    widget = LogViewerWidget()

    # 使い方表示中に裏でシステムログを追加
    widget.append_log("起動時の自動更新確認: 最新版です", level="INFO")
    widget.append_log("警告メッセージテスト", level="WARNING")

    # この時点でも表示は使い方のまま
    assert widget.is_showing_help is True

    # ログ表示に切り替え
    widget.switch_to_log()
    assert widget.is_showing_help is False
    assert widget.stacked_widget.currentIndex() == 1

    # ログ表示中はツールバーの全項目が表示設定 (isHidden() == False)
    assert widget.auto_scroll_cb.isHidden() is False
    assert widget.clear_btn.isHidden() is False
    assert "使い方" in widget.toggle_view_btn.text()

    # 裏で追加されたログが消えずに保持されていること
    log_text = widget.log_edit.toPlainText()
    assert "起動時の自動更新確認: 最新版です" in log_text
    assert "警告メッセージテスト" in log_text

    # トグルで使い方に戻す
    widget.toggle_view()
    assert widget.is_showing_help is True
    assert widget.auto_scroll_cb.isHidden() is True

    # 再度トグルでログに戻す（ログが維持されていること）
    widget.toggle_view()
    assert widget.is_showing_help is False
    assert "起動時の自動更新確認: 最新版です" in widget.log_edit.toPlainText()


def test_settings_dialog_no_headless_checkbox(qapp):
    """設定ダイアログから Playwright 用の不要な headless チェックボックスが削除されていることをテスト"""
    from src.utils.config import AppConfig
    from src.gui.settings_dialog import SettingsDialog

    config = AppConfig()
    dialog = SettingsDialog(config)

    # chk_show_browser 属性が存在しないこと
    assert not hasattr(dialog, "chk_show_browser")
    # 更新ボタンに refresh アイコンが設定されていること
    assert not dialog.btn_check_update.icon().isNull()


def test_in_memory_cookie_cleanup(tmp_path):
    """残存Cookieファイルおよびプロファイルフォルダの自動クリーンアップをテスト"""
    from src.browser.cookie_extractor import cleanup_legacy_cookie_files, save_cookies_to_json, load_cookies_from_json

    dummy_cookie = tmp_path / "session_cookies.json"
    dummy_cookie.write_text('[{"name": "KGLC", "value": "123"}]', encoding="utf-8")
    dummy_profile = tmp_path / "web_profile"
    dummy_profile.mkdir()
    (dummy_profile / "Cookies").write_text("dummy", encoding="utf-8")

    cleanup_legacy_cookie_files(str(dummy_cookie), str(dummy_profile))
    assert not dummy_cookie.exists()
    assert not dummy_profile.exists()

    # save / load スタブもファイルを作らず空を返すこと
    dummy_cookie.write_text("[]", encoding="utf-8")
    assert save_cookies_to_json([], str(dummy_cookie)) is True
    assert not dummy_cookie.exists()
    assert load_cookies_from_json(str(dummy_cookie)) == []


def test_v2_config_ini_exists_and_loads():
    """v2/config/config.ini が存在し、設定値で読み込めることをテスト"""
    import os
    from src.utils.config import AppConfig, BASE_V2_DIR

    v2_config_path = os.path.join(BASE_V2_DIR, "config", "config.ini")
    assert os.path.exists(v2_config_path)

    cfg = AppConfig()
    assert cfg.version == "2.3.1"
    assert not hasattr(cfg, "headless")
    assert cfg.enable_notifications is True
    assert cfg.enable_notification_sound is True


def test_settings_dialog_notification_checkboxes(qapp):
    """設定ダイアログにWindows通知設定チェックボックスが存在することをテスト"""
    from src.utils.config import AppConfig
    from src.gui.settings_dialog import SettingsDialog

    config = AppConfig()
    dialog = SettingsDialog(config)

    assert hasattr(dialog, "chk_enable_notifications")
    assert hasattr(dialog, "chk_enable_sound")
    assert dialog.chk_enable_notifications.isChecked() is True
    assert dialog.chk_enable_sound.isChecked() is True


def test_close_event_does_not_popup_dialog_in_tests(qapp, tmp_path):
    """テスト実行時やコードからの close() 呼び出し時に終了確認ダイアログがポップアップしないことをテスト"""
    from unittest.mock import patch, MagicMock
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import Signal, QUrl
    from src.utils.config import AppConfig
    from src.gui.main_window import MainWindow
    from PySide6.QtGui import QCloseEvent

    class DummyView(QWidget):
        urlChanged = Signal(QUrl)
        loadFinished = Signal(bool)
        cookie_status_changed = Signal(bool, str)
        def set_allowed_origin(self, o): pass
        def setUrl(self, u): pass
        def is_authenticated(self): return True
        def clear_all_cookies(self): pass

    config = AppConfig()
    config.db_path = str(tmp_path / "test_close.db")

    with patch("src.gui.main_window.PersistentWebEngineView", DummyView):
        window = MainWindow(config)
        window._is_analyzing = True

        with patch("src.gui.main_window.QMessageBox.question") as mock_question:
            event = QCloseEvent()
            window.closeEvent(event)
            # テスト環境では確認ダイアログが出ず、イベントが受諾されること
            mock_question.assert_not_called()
            assert event.isAccepted() is True



