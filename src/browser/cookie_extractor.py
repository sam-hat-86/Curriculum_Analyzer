import os
import sqlite3
from typing import List, Dict, Any
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineCookieStore
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtNetwork import QNetworkCookie
from src.utils.logger import get_logger

def extract_cookies_from_storage(storage_path: str) -> List[Dict[str, Any]]:
    """
    WebEngineの永続プロファイルストレージ(SQLite)から直接Cookieを読み出す
    """
    logger = get_logger()
    cookies = []
    
    # 候補パスの探索 (Chrome / WebEngine の Cookies ファイル配置)
    cookie_paths = [
        os.path.join(storage_path, "Cookies"),
        os.path.join(storage_path, "Network", "Cookies"),
    ]
    
    target_path = None
    for p in cookie_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            target_path = p
            break
            
    if not target_path:
        return cookies

    try:
        # ロック競合を防ぐため immutable=1 URI で読み取り専用接続
        db_uri = f"file:{os.path.abspath(target_path).replace(os.sep, '/')}?immutable=1"
        con = sqlite3.connect(db_uri, uri=True, timeout=5.0)
        cur = con.cursor()
        
        # Chrome/WebEngine cookies テーブル構造
        cur.execute("SELECT host_key, name, path, is_secure, is_httponly, value FROM cookies")
        rows = cur.fetchall()
        for host, name, path, is_sec, is_http, val in rows:
            cookies.append({
                "name": name,
                "value": val,
                "domain": host,
                "path": path,
                "secure": bool(is_sec),
                "httpOnly": bool(is_http),
            })
        con.close()
        logger.info(f"SQLiteプロファイルストレージから直接Cookieを抽出しました: {len(cookies)} 件")
    except Exception as e:
        logger.warning(f"SQLiteストレージからのCookie直接読み出しで警告: {e}")

    return cookies

def extract_cookies_sync(profile: QWebEngineProfile, timeout_ms: int = 1500) -> List[Dict[str, Any]]:
    """
    WebEngineのCookieストアおよびプロファイルストレージからPlaywright互換Cookieを抽出
    """
    logger = get_logger()
    storage_path = profile.persistentStoragePath()
    
    # 1. まずSQLiteストレージから確実に取得
    cookies = extract_cookies_from_storage(storage_path) if storage_path else []

    # 2. メモリ内セッションCookieをQWebEngineCookieStoreから補完
    cookie_store: QWebEngineCookieStore = profile.cookieStore()

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
        # 重複更新または追加
        found = False
        for idx, existing in enumerate(cookies):
            if existing["name"] == c_dict["name"] and (existing["domain"] == c_dict["domain"] or not existing["domain"]):
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

    logger.info(f"最終Cookie抽出結果: {len(cookies)} 件")
    for c in cookies:
        logger.info(f"  Cookie検出: {c['name']} (domain: {c.get('domain')})")
    
    if not cookies:
        logger.warning("WebEngineからCookieが取得できませんでした。ログイン状態を確認してください。")

    return cookies

