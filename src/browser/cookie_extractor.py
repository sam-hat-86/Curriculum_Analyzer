"""
PySide6 WebEngine Cookie 抽出ユーティリティ
"""
from typing import List, Dict, Any
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineCookieStore
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtNetwork import QNetworkCookie
from src.utils.logger import get_logger

def extract_cookies_sync(profile: QWebEngineProfile, timeout_ms: int = 2000) -> List[Dict[str, Any]]:
    """
    WebEngineのCookieストアからPlaywright互換のCookieリストを同期抽出
    """
    logger = get_logger()
    cookie_store: QWebEngineCookieStore = profile.cookieStore()
    cookies: List[Dict[str, Any]] = []

    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)

    def on_cookie_added(cookie: QNetworkCookie):
        c_dict = {
            "name": bytes(cookie.name().data()).decode("utf-8", errors="ignore"),
            "value": bytes(cookie.value().data()).decode("utf-8", errors="ignore"),
            "domain": cookie.domain(),
            "path": cookie.path(),
            "secure": cookie.isSecure(),
            "httpOnly": cookie.isHttpOnly(),
        }
        # 既存Cookieがあれば最新値で更新、なければ追加
        found = False
        for idx, existing in enumerate(cookies):
            if existing["name"] == c_dict["name"] and existing["domain"] == c_dict["domain"]:
                cookies[idx] = c_dict
                found = True
                break
        if not found:
            cookies.append(c_dict)

    cookie_store.cookieAdded.connect(on_cookie_added)
    cookie_store.loadAllCookies()

    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    loop.exec()

    try:
        cookie_store.cookieAdded.disconnect(on_cookie_added)
    except Exception:
        pass

    logger.info(f"WebEngineからCookieを抽出しました: {len(cookies)} 件")
    if not cookies:
        logger.warning("WebEngineからCookieが取得できませんでした。ログイン状態を確認してください。")

    return cookies

