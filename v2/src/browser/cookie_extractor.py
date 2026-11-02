"""
PySide6 WebEngine Cookie 抽出・クリーンアップユーティリティ
- ソフト再起動時は再ログインとなるため、ディスクへのCookie保存は行わずオンメモリで管理
- 過去バージョンで残存した session_cookies.json や web_profile フォルダのクリーンアップを提供
"""
import os
import shutil
from typing import List, Dict, Any, Optional
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtNetwork import QNetworkCookie
from src.utils.logger import get_logger

DEFAULT_SESSION_COOKIES_PATH = os.path.join("user_data", "session_cookies.json")
DEFAULT_WEB_PROFILE_PATH = os.path.join("user_data", "web_profile")


def format_qcookie(cookie: QNetworkCookie) -> Dict[str, Any]:
    """QNetworkCookie を 標準Cookie辞書形式へ変換"""
    return {
        "name": bytes(cookie.name().data()).decode("utf-8", errors="ignore"),
        "value": bytes(cookie.value().data()).decode("utf-8", errors="ignore"),
        "domain": cookie.domain(),
        "path": cookie.path() or "/",
        "secure": cookie.isSecure(),
        "httpOnly": cookie.isHttpOnly(),
    }


def cleanup_legacy_cookie_files(
    cookie_filepath: str = DEFAULT_SESSION_COOKIES_PATH,
    profile_dirpath: str = DEFAULT_WEB_PROFILE_PATH,
) -> None:
    """ディスク上に残存している不要な Cookie JSON および永続プロファイルフォルダを削除"""
    logger = get_logger()
    if cookie_filepath and os.path.exists(cookie_filepath):
        try:
            os.remove(cookie_filepath)
            logger.debug(f"残存Cookieファイルを削除しました: {cookie_filepath}")
        except Exception as e:
            logger.debug(f"残存Cookieファイルの削除スキップ: {e}")

    if profile_dirpath and os.path.exists(profile_dirpath):
        try:
            shutil.rmtree(profile_dirpath, ignore_errors=True)
            logger.debug(f"残存ブラウザプロファイルフォルダを削除しました: {profile_dirpath}")
        except Exception as e:
            logger.debug(f"残存ブラウザプロファイルフォルダの削除スキップ: {e}")


def save_cookies_to_json(cookies: List[Dict[str, Any]], filepath: str = DEFAULT_SESSION_COOKIES_PATH) -> bool:
    """後方互換性スタブ（ディスク保存は行わず残存ファイルを削除）"""
    cleanup_legacy_cookie_files(cookie_filepath=filepath, profile_dirpath="")
    return True


def load_cookies_from_json(filepath: str = DEFAULT_SESSION_COOKIES_PATH) -> List[Dict[str, Any]]:
    """後方互換性スタブ（ディスクからのCookie復元は行わない）"""
    cleanup_legacy_cookie_files(cookie_filepath=filepath, profile_dirpath="")
    return []


def extract_cookies_sync(profile: Optional[QWebEngineProfile] = None, timeout_ms: int = 500) -> List[Dict[str, Any]]:
    """後方互換性関数"""
    return []
