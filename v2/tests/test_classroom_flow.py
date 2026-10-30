"""
教室巡回フローおよびポップアップ選択ロジックのユニットテスト
"""
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget, QPushButton
from PySide6.QtCore import Signal, QUrl

from src.utils.config import AppConfig
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.models.curriculum import CurriculumOverview
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
    """QApplicationインスタンスの生成 (セッションスコープ)"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_window(qapp, tmp_path):
    """テスト用MainWindowインスタンス"""
    db_path = str(tmp_path / "test_flow.db")
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


def test_prepare_for_next_classroom(test_window):
    """別教室巡回待機状態へ正常に遷移し、データが保持されることの検証"""
    # モックデータ投入
    test_window.repo.save_pages_init([
        CurriculumOverview(
            classroom_name="教室A",
            classroom_code="C1",
            school_year="2026",
            student_id="S1",
            student_name="生徒1",
            subject="英語",
            grade="中1",
            division="個別",
            detail_url="url1",
            row_index=0,
            page_index=1
        )
    ])
    assert test_window.repo.get_counts()["total"] == 1

    # 別教室巡回待機への遷移呼び出し
    test_window._prepare_for_next_classroom()

    # フラグとUIボタンの検証
    assert test_window._is_continuous_classroom_mode is True
    assert test_window._is_analyzing is False
    assert test_window.btn_start.text() == "▶ 次の教室を開始"
    assert test_window.btn_start.isEnabled() is True
    assert test_window.btn_stop.isEnabled() is False

    # DBデータがクリアされずに保持されていることの検証
    assert test_window.repo.get_counts()["total"] == 1


def test_continuous_classroom_start_process(test_window):
    """連続教室巡回モード時にダイアログをスキップしてスムーズに巡回開始できることの検証"""
    test_window._is_continuous_classroom_mode = True

    with patch.object(test_window, "_start_list_page_extraction") as mock_extract, \
         patch("src.gui.main_window.QMessageBox.exec") as mock_msgbox:
        
        test_window.start_process()

        # 確認ダイアログが表示されず、フラグがリセットされて開始されたことを検証
        mock_msgbox.assert_not_called()
        assert test_window._is_continuous_classroom_mode is False
        assert test_window._is_analyzing is True
        assert test_window._current_page_idx == 1
        assert test_window.btn_start.text() == "▶ 処理開始"
        mock_extract.assert_called_once()


def test_prompt_next_classroom_choice_next(test_window):
    """ポップアップで「別教室の巡回に進む」を選択した場合の検証"""
    with patch.object(QMessageBox, "exec", return_value=0), \
         patch.object(QMessageBox, "clickedButton") as mock_clicked, \
         patch.object(test_window, "_prepare_for_next_classroom") as mock_prepare, \
         patch.object(test_window, "_finish_all_pages") as mock_finish:

        # msg_box.addButton で追加されたボタンが返されるようにシミュレート
        btn_mock = QPushButton("別教室の巡回に進む")
        mock_clicked.return_value = btn_mock

        # _prompt_next_classroom_or_export 内で addButton されたボタンと一致するように
        with patch.object(QMessageBox, "addButton", return_value=btn_mock):
            test_window._prompt_next_classroom_or_export(total_pages=3)

        mock_prepare.assert_called_once()
        mock_finish.assert_not_called()


def test_prompt_next_classroom_choice_export(test_window):
    """ポップアップで「Excelファイルを出力する」を選択した場合の検証"""
    with patch.object(QMessageBox, "exec", return_value=0), \
         patch.object(QMessageBox, "clickedButton") as mock_clicked, \
         patch.object(test_window, "_prepare_for_next_classroom") as mock_prepare, \
         patch.object(test_window, "_finish_all_pages") as mock_finish:

        btn_export_mock = QPushButton("Excelファイルを出力する")
        mock_clicked.return_value = btn_export_mock

        # addButtonの2回目の呼び出しで返るボタンとclickedButtonを合わせる
        btn_next_mock = QPushButton("別教室の巡回に進む")
        with patch.object(QMessageBox, "addButton", side_effect=[btn_next_mock, btn_export_mock]):
            test_window._prompt_next_classroom_or_export(total_pages=3)

        mock_prepare.assert_not_called()
        mock_finish.assert_called_once_with(True, "全 3 ページの処理を完了しました")
