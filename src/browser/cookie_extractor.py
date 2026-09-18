"""
PySide6 WebEngine Cookie 抽出・JSON永続化ユーティリティ
"""
import os
import json
from typing import List, Dict, Any
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtNetwork import QNetworkCookie
from src.utils.logger import get_logger

DEFAULT_SESSION_COOKIES_PATH = os.path.join("user_data", "session_cookies.json")

def format_qcookie(cookie: QNetworkCookie) -> Dict[str, Any]:
    """QNetworkCookie を Playwright 互換の辞書形式へ変換"""
    return {
        "name": bytes(cookie.name().data()).decode("utf-8", errors="ignore"),
        "value": bytes(cookie.value().data()).decode("utf-8", errors="ignore"),
        "domain": cookie.domain(),
        "path": cookie.path() or "/",
        "secure": cookie.isSecure(),
        "httpOnly": cookie.isHttpOnly(),
    }

def save_cookies_to_json(cookies: List[Dict[str, Any]], filepath: str = DEFAULT_SESSION_COOKIES_PATH) -> bool:
    """CookieリストをJSONファイルへ安全に保存"""
    logger = get_logger()
    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning(f"CookieのJSON保存失敗: {e}")
        return False

def load_cookies_from_json(filepath: str = DEFAULT_SESSION_COOKIES_PATH) -> List[Dict[str, Any]]:
    """JSONファイルから保存済みCookieリストを復元"""
    logger = get_logger()
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            cookies = json.load(f)
            if isinstance(cookies, list):
                return cookies
    except Exception as e:
        logger.warning(f"CookieのJSON読み出し失敗: {e}")
    return []

def extract_cookies_sync(profile: QWebEngineProfile = None, timeout_ms: int = 500) -> List[Dict[str, Any]]:
    """
    JSONキャッシュからCookieを取得 (後方互換性関数)
    """
    return load_cookies_from_json()
