"""
PySide6 WebEngine Cookie 抽出ユーティリティ
"""
from typing import List, Dict, Callable
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineCookieStore
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtNetwork import QNetworkCookie

def extract_cookies_sync(profile: QWebEngineProfile, timeout_ms: int = 2000) -> List[Dict[str, Any]]:
    """
    WebEngineのCookieストアからPlaywright互換のCookieリストを同期抽出
    """
    cookie_store: QWebEngineCookieStore = profile.cookieStore()
    cookies: List[Dict[str, Any]] = []

    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)

    def on_cookie_added(cookie: QNetworkCookie):
        c_dict = {
            "name": cookie.name().data().decode("utf-8", errors="ignore"),
            "value": cookie.value().data().decode("utf-8", errors="ignore"),
            "domain": cookie.domain(),
            "path": cookie.path(),
            "secure": cookie.isSecure(),
            "httpOnly": cookie.isHttpOnly(),
        }
        # 重複除外
        existing = [c for c in cookies if c["name"] == c_dict["name"] and c["domain"] == c_dict["domain"]]
        if not existing:
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

    return cookies
