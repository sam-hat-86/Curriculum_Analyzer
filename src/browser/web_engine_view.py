"""
PySide6 WebEngine ブラウザビュー (永続プロファイル & リアルタイムCookieトラッカー対応)
"""
import os
from typing import List, Dict, Any, Optional
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
from PySide6.QtCore import QUrl, Signal
from PySide6.QtNetwork import QNetworkCookie

from src.browser.cookie_extractor import (
    format_qcookie, save_cookies_to_json, load_cookies_from_json
)
from src.utils.logger import get_logger

class CustomWebEnginePage(QWebEnginePage):
    navigation_intercepted = Signal(QUrl)

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.intercept_navigation = False

    def certificateError(self, certificateError):
        # 自己署名証明書等のエラーを自動受諾して表示を許可
        certificateError.acceptCertificate()
        return True

    def acceptNavigationRequest(self, url: QUrl, nav_type: QWebEnginePage.NavigationType, isMainFrame: bool) -> bool:
        if self.intercept_navigation and isMainFrame:
            url_str = url.toString()
            # about:blank は無視
            if url_str and url_str != "about:blank":
                self.navigation_intercepted.emit(url)
                return False
        return super().acceptNavigationRequest(url, nav_type, isMainFrame)

class PersistentWebEngineView(QWebEngineView):
    # (認証状態OK/NG, 検出されたCookie概要)
    cookie_status_changed = Signal(bool, str)
    # 別タブ・別ウィンドウオープン要求捕捉シグナル (QWebEnginePageを渡す)
    new_window_requested = Signal(object)

    def createWindow(self, window_type: QWebEnginePage.WebWindowType) -> QWebEnginePage:
        """社内システムが window.open や target='_blank' で別タブを開いた際に捕捉"""
        if hasattr(self, "_target_worker_page") and self._target_worker_page is not None:
            target = self._target_worker_page
            self._target_worker_page = None
            return target

        sheet_page = CustomWebEnginePage(self.custom_profile, self)
        self.new_window_requested.emit(sheet_page)
        return sheet_page

    def set_target_worker_page(self, page: Optional[QWebEnginePage]):
        """次に発生するwindow.openのロード先Pageを予約設定"""
        self._target_worker_page = page

    def create_background_page(self) -> QWebEnginePage:
        """同じ認証プロファイルを共有するバックグラウンド取得用Pageを作成"""
        return CustomWebEnginePage(self.custom_profile, self)

    def create_tab_view(self, parent=None, disable_images: bool = False) -> "PersistentWebEngineView":
        """同じ認証プロファイルを共有するタブ用Viewを作成"""
        view = PersistentWebEngineView(profile=self.custom_profile, parent=parent)
        if disable_images:
            view.settings().setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, False)
        return view

    def __init__(self, profile_path: str = "user_data/web_profile", profile: Optional[QWebEngineProfile] = None, parent=None):
        super().__init__(parent)
        self.logger = get_logger()
        self._target_worker_page: Optional[QWebEnginePage] = None

        if profile is not None:
            self.custom_profile = profile
            self.profile_path = profile.persistentStoragePath()
        else:
            self.profile_path = os.path.abspath(profile_path)
            os.makedirs(self.profile_path, exist_ok=True)
            # 永続プロファイルの作成 (ログイン情報・Cookie・LocalStorage保持)
            self.custom_profile = QWebEngineProfile("CurriculumAnalyzerProfile", self)
            self.custom_profile.setPersistentStoragePath(self.profile_path)
            self.custom_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)

            # Web設定
            settings = self.custom_profile.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)

        # ページ作成 (証明書エラー自動受諾)
        self.custom_page = CustomWebEnginePage(self.custom_profile, self)
        self.setPage(self.custom_page)

        # リアルタイムCookieキャッシュ
        self.cookies_cache: Dict[str, Dict[str, Any]] = {}
        self._load_cached_cookies_from_file()

        # CookieStoreのイベント常時監視 (ログイン・通信発生時にリアルタイム捕捉)
        cookie_store = self.custom_profile.cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)
        cookie_store.cookieRemoved.connect(self._on_cookie_removed)

        # プロファイル初期ロードをキック
        cookie_store.loadAllCookies()

    def _load_cached_cookies_from_file(self):
        """前回保存されたJSONから初期Cookieを復元"""
        saved = load_cookies_from_json()
        for c in saved:
            if isinstance(c, dict) and "name" in c:
                self.cookies_cache[c["name"]] = c
        self._emit_status()

    def _on_cookie_added(self, cookie: QNetworkCookie):
        """Cookie追加・更新時のリアルタイムハンドラ"""
        c_dict = format_qcookie(cookie)
        name = c_dict["name"]
        self.cookies_cache[name] = c_dict
        save_cookies_to_json(list(self.cookies_cache.values()))
        if name in ("KGLC", "PHPSESSID", "session", "JSESSIONID"):
            self.logger.info(f"認証Cookieを捕捉しました: {name}")
        self._emit_status()

    def _on_cookie_removed(self, cookie: QNetworkCookie):
        """Cookie削除時のリアルタイムハンドラ"""
        c_dict = format_qcookie(cookie)
        name = c_dict["name"]
        if name in self.cookies_cache:
            del self.cookies_cache[name]
            save_cookies_to_json(list(self.cookies_cache.values()))
            self._emit_status()

    def _emit_status(self):
        """現在のCookie状態から認証シグナルを発行"""
        is_auth = self.is_authenticated()
        if "KGLC" in self.cookies_cache:
            desc = "認証済み (KGLC検出)"
        elif any("session" in k.lower() for k in self.cookies_cache):
            desc = "認証済み (セッションCookie検出)"
        elif self.cookies_cache:
            desc = f"Cookie保持中 ({len(self.cookies_cache)}件)"
        else:
            desc = "未ログイン"
        self.cookie_status_changed.emit(is_auth, desc)

    def is_authenticated(self) -> bool:
        """社内システム(KGLC等)または主要セッションCookieが保持されているか"""
        if "KGLC" in self.cookies_cache and self.cookies_cache["KGLC"].get("value"):
            return True
        # 汎用セッションCookieチェック
        for name, c in self.cookies_cache.items():
            if any(key in name.lower() for key in ["session", "auth", "token", "kglc"]) and c.get("value"):
                return True
        return False

    def get_cookies_list(self) -> List[Dict[str, Any]]:
        """現在の全Cookieリストを即座に返却 (待機時間0ms・スレッドセーフ)"""
        cookies = list(self.cookies_cache.values())
        if not cookies:
            cookies = load_cookies_from_json()
        self.logger.info(f"Cookieリストを提供: {len(cookies)} 件 (認証: {self.is_authenticated()})")
        return cookies
