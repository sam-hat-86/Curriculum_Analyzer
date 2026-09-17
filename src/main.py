"""
カリキュラムチェックシステム v2.0.0 エントリーポイント
"""
import sys
import os

# プロジェクトルートをPythonパスに追加
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from src.utils.config import AppConfig
from src.utils.logger import setup_logger
from src.utils.constants import APP_BASE_TITLE, APP_VERSION, MUTEX_NAME
from src.gui.main_window import MainWindow

def main():
    # 多重起動防止 (Windows Mutex)
    mutex_handle = None
    if sys.platform == "win32":
        try:
            import win32event
            import win32api
            import winerror
            mutex_handle = win32event.CreateMutex(None, False, MUTEX_NAME)
            if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                # 既に起動している場合
                print("アプリケーションは既に起動しています。")
                sys.exit(0)
        except ImportError:
            pass

    # 設定読み込み
    config = AppConfig()

    # ロガーセットアップ
    logger = setup_logger(log_dir=config.log_dir, log_level=config.log_level)
    logger.info(f"=== {APP_BASE_TITLE} v{APP_VERSION} 起動 ===")

    # 高DPIスケーリング
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName(f"{APP_BASE_TITLE} v{APP_VERSION}")

    # メインウィンドウ起動
    window = MainWindow(config)
    window.show()

    exit_code = app.exec()
    logger.info("=== アプリケーション終了 ===")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
