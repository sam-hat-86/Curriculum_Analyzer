"""授業指示書・カリキュラム 精査ブラウザ - エントリーポイント。

仕様書 §7 に準拠した起動処理を行う。
"""

import os
import sys
import ctypes
import ctypes.wintypes
import logging
import traceback
from logging.handlers import RotatingFileHandler


def _resolve_base_dir() -> str:
    """base_dirを解決する。

    仕様書 §7.1:
    - Onefile実行時: ユーザーが実行したEXE自身の所在ディレクトリ (sys.argv[0])
    - 開発環境: __file__を基準
    """
    if getattr(sys, "frozen", False) or "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        if sys.argv and sys.argv[0]:
            exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            return exe_dir
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 開発環境: src/main.py → 親ディレクトリ = プロジェクトルート
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _setup_sys_path(base_dir: str) -> None:
    """srcディレクトリをsys.pathに追加する。"""
    src_dir = os.path.join(base_dir, "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)


def _setup_logging(base_dir: str) -> None:
    """ログの初期設定。

    仕様書 §40:
    - UTF-8 BOMなし
    - RotatingFileHandler
    - maxBytes=1048576 (1MB)
    - backupCount=3
    """
    log_path = os.path.join(base_dir, "error.log")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    try:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1048576,
            backupCount=3,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except Exception:
        # ログ書き込み失敗時はstderrへ出力
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(handler)
        logger.warning("error.logへの書き込みに失敗。stderrへ出力します。")


def _try_create_mutex() -> bool:
    """Windows Mutexによる多重起動防止。

    仕様書 §8:
    - CreateMutexW直後にGetLastError()を評価
    - ERROR_ALREADY_EXISTSの場合はCloseHandleし新規プロセスを正常終了
    - NULLの場合は起動中止
    """
    from core.constants import MUTEX_NAME, APP_BASE_TITLE

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex:
        logging.error("CreateMutexW がNULLを返しました。起動を中止します。")
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            _app = QApplication(sys.argv)
            QMessageBox.critical(
                None, "起動エラー",
                "Mutexの作成に失敗しました。アプリを起動できません。"
            )
        except Exception:
            pass
        return False

    last_error = kernel32.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(mutex)

        # 既存ウィンドウの前面化を試みる
        try:
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.wintypes.HWND,
                ctypes.wintypes.LPARAM,
            )

            def _enum_callback(hwnd: int, _lparam: int) -> bool:
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if APP_BASE_TITLE in buf.value:
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    if not user32.SetForegroundWindow(hwnd):
                        # FlashWindowEx
                        class FLASHWINFO(ctypes.Structure):
                            _fields_ = [
                                ("cbSize", ctypes.wintypes.UINT),
                                ("hwnd", ctypes.wintypes.HWND),
                                ("dwFlags", ctypes.wintypes.DWORD),
                                ("uCount", ctypes.wintypes.UINT),
                                ("dwTimeout", ctypes.wintypes.DWORD),
                            ]
                        finfo = FLASHWINFO()
                        finfo.cbSize = ctypes.sizeof(FLASHWINFO)
                        finfo.hwnd = hwnd
                        finfo.dwFlags = 0x03  # FLASHW_ALL
                        finfo.uCount = 3
                        finfo.dwTimeout = 0
                        user32.FlashWindowEx(ctypes.byref(finfo))
                    return False
                return True

            user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
        except Exception as e:
            logging.warning("既存ウィンドウの前面化に失敗: %s", e)

        return False

    return True

def _prompt_for_base_url(parent=None) -> tuple[str, bool]:
    """base_urlが未設定または空の場合に入力ダイアログを表示してURLを取得する。"""
    from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
    from core.config import _validate_base_url

    default_text = ""
    while True:
        url, ok = QInputDialog.getText(
            parent,
            "接続先URLの設定",
            "接続先のURL (base_url) が設定されていません。\n"
            "アクセスするシステムのURLを入力してください:\n"
            "(例: http://10.200.5.191/ または https://example.com/)",
            QLineEdit.EchoMode.Normal,
            default_text,
        )
        if not ok:
            return "", False
        url = url.strip()
        if not url:
            QMessageBox.warning(parent, "入力エラー", "URLが入力されていません。もう一度入力してください。")
            continue
        try:
            valid_url = _validate_base_url(url)
            return valid_url, True
        except ValueError as e:
            QMessageBox.warning(
                parent,
                "入力エラー",
                f"入力されたURLが不正です:\n{e}\n\nもう一度入力してください。"
            )
            default_text = url
            continue


def main() -> None:
    """アプリケーションのメインエントリーポイント。"""
    # 1. base_dir解決
    base_dir = _resolve_base_dir()

    # 2. sys.path設定
    _setup_sys_path(base_dir)

    # 3. 最低限のfallback logger初期化
    _setup_logging(base_dir)
    logging.info("アプリケーション起動中...")

    # MemoryErrorハンドラ (§32)
    def _memory_error_handler(exctype, value, tb):
        if issubclass(exctype, MemoryError):
            logging.critical("MemoryError: %s", value)
            sys.stderr.write(f"MemoryError: {value}\n")
            sys.exit(1)
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = _memory_error_handler

    # 4. Mutex生成 (§8)
    if not _try_create_mutex():
        logging.info("既存インスタンスを検出。終了します。")
        return

    # 遅延インポート (sys.path設定後)
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import QUrl
    from core.constants import __version__
    from core.config import ConfigManager, run_startup_self_diagnosis
    from core.repository import Repository
    from core.cache import CacheManager
    from gui.main_window import MainWindow

    # 5. QApplication生成 (High-DPI: Qt6標準に委ねる §7.3)
    app = QApplication(sys.argv)

    # 6. config.ini読み込み・検証 (§9)
    config_path = os.path.join(base_dir, "config.ini")
    config_manager = ConfigManager(config_path)
    config = None
    try:
        config = config_manager.load()
    except ValueError as e:
        if "base_url" in str(e):
            url, ok = _prompt_for_base_url()
            if ok and url:
                try:
                    config_manager.update_value("General", "base_url", url)
                    config = config_manager.load()
                except Exception as save_err:
                    QMessageBox.critical(None, "設定エラー", f"URLの保存に失敗しました: {save_err}")
                    return
            else:
                QMessageBox.information(None, "終了", "URLが設定されていないため終了します。")
                return
        else:
            QMessageBox.critical(None, "設定エラー", str(e))
            return

    # 万一 load() 側で空文字列のまま AppConfig が返ってきた場合のガード
    if not config or not config.base_url:
        url, ok = _prompt_for_base_url()
        if ok and url:
            try:
                config_manager.update_value("General", "base_url", url)
                config = config_manager.load()
            except Exception as save_err:
                QMessageBox.critical(None, "設定エラー", f"URLの保存に失敗しました: {save_err}")
                return
        else:
            QMessageBox.information(None, "終了", "URLが設定されていないため終了します。")
            return

    # 7. user_data初期化
    user_data_dir = os.path.join(base_dir, "user_data")
    os.makedirs(user_data_dir, exist_ok=True)

    # 7.5. 起動時の自己診断 (v9 §44)
    from pathlib import Path
    downloads_path = Path.home() / "Downloads"
    output_dir = str(downloads_path) if downloads_path.is_dir() else base_dir
    diag_errors = run_startup_self_diagnosis(
        base_dir=base_dir,
        selectors_path=os.path.join(base_dir, "selectors.json"),
        user_data_dir=user_data_dir,
        output_dir=output_dir,
    )
    if diag_errors:
        err_msg = "起動前自己診断で重大なエラーが検出されました:\n\n" + "\n".join(f"・{e}" for e in diag_errors)
        logging.critical(err_msg)
        QMessageBox.critical(None, "起動前診断エラー", err_msg)
        return

    # 8. Repository & CacheManager
    repository = Repository()
    cache_manager = CacheManager(user_data_dir)

    # 9. cache復元確認 (§25.5)
    if cache_manager.exists():
        records, skip_count, status = cache_manager.load()

        if status == "meta_corrupt":
            QMessageBox.critical(
                None, "キャッシュエラー",
                "キャッシュファイルのヘッダー情報が破損しているため、復元できません。",
            )
        elif records:
            if skip_count > 0:
                msg = (
                    f"前回の未集計データ（{len(records)}件）が見つかりました。\n"
                    f"（※破損データ {skip_count}件 を除外）\n"
                    f"復元して作業を継続しますか？"
                )
            else:
                msg = (
                    f"前回の未集計データ（{len(records)}件）が見つかりました。\n"
                    f"復元して作業を継続しますか？"
                )
            reply = QMessageBox.question(
                None, "データ復元",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                repository.add_batch(records)
                logging.info("キャッシュから%d件を復元しました", len(records))
            # 「いいえ」の場合もcacheを削除せず残す (§25.5)

    # 10. MainWindow生成
    window = MainWindow(config, repository, cache_manager, user_data_dir)
    window.show()

    # 11. base_url読み込み
    if config.base_url:
        window.web_view.load(QUrl(config.base_url))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
