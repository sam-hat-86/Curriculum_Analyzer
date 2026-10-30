"""
PySide6 WebEngine ブラウザビュー (永続プロファイル & リアルタイムCookieトラッカー対応)
- FIFO ワーカーページキューによる複数タブ window.open 競合防止
- 証明書エラー受諾の対象ホスト限定 (セキュリティ強化)
- Cookie JSON 保存のデバウンスによるディスクI/O削減
"""
from collections import deque
import os
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlparse
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
from PySide6.QtCore import QUrl, QTimer, Signal
from PySide6.QtNetwork import QNetworkCookie

from src.browser.cookie_extractor import (
    format_qcookie, save_cookies_to_json, load_cookies_from_json
)
from src.utils.logger import get_logger


class CustomWebEnginePage(QWebEnginePage):
    navigation_intercepted = Signal(QUrl)

    def __init__(self, profile, parent=None, allowed_cert_hosts: Optional[Set[str]] = None):
        super().__init__(profile, parent)
        self.intercept_navigation = False
        self.allowed_cert_hosts: Set[str] = allowed_cert_hosts if allowed_cert_hosts is not None else set()

    def certificateError(self, certificateError):
        # 許可された社内ホスト (またはホスト未指定時) のみ自己署名証明書等を受諾
        try:
            err_url = certificateError.url()
            host = (err_url.host() or "").lower() if err_url else ""
        except Exception:
            host = ""

        if not self.allowed_cert_hosts or not host or host in self.allowed_cert_hosts:
            certificateError.acceptCertificate()
            return True

        certificateError.rejectCertificate()
        return False

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
    # ワーカーページへ window.open がルーティングされた際の通知シグナル
    worker_page_routed = Signal(object)

    def createWindow(self, window_type: QWebEnginePage.WebWindowType) -> Optional[QWebEnginePage]:
        """社内システムが window.open や target='_blank' で別タブを開いた際に捕捉"""
        if self._target_worker_pages:
            target = self._target_worker_pages.popleft()
            self._target_worker_page = self._target_worker_pages[0] if self._target_worker_pages else None
            self.worker_page_routed.emit(target)
            return target

        if self._target_worker_page is not None:
            target = self._target_worker_page
            self._target_worker_page = None
            self.worker_page_routed.emit(target)
            return target

        # クロール中に予約されていない余分な window.open が発生した場合は孤児ページを作らず破棄
        if getattr(self.custom_page, "intercept_navigation", False):
            self.logger.debug("予約外のため余分な window.open 要求を無視しました")
            return None

        sheet_page = CustomWebEnginePage(
            self.custom_profile, self, allowed_cert_hosts=self.allowed_cert_hosts
        )
        self.new_window_requested.emit(sheet_page)
        return sheet_page

    def set_target_worker_page(self, page: Optional[QWebEnginePage]):
        """次に発生するwindow.openのロード先Pageを予約設定 (FIFOキュー対応)"""
        if page is None:
            self._target_worker_pages.clear()
            self._target_worker_page = None
            return
        if page not in self._target_worker_pages:
            self._target_worker_pages.append(page)
        self._target_worker_page = self._target_worker_pages[0]

    def remove_target_worker_page(self, page: Optional[QWebEnginePage]):
        """特定ページの予約を取り消す"""
        if page is None:
            return
        try:
            self._target_worker_pages.remove(page)
        except ValueError:
            pass
        self._target_worker_page = self._target_worker_pages[0] if self._target_worker_pages else None

    def set_allowed_origin(self, url_str: str):
        """自己署名証明書を許可する社内システムのホストを登録"""
        if not url_str:
            return
        try:
            parsed = urlparse(url_str)
            if parsed.hostname:
                self.allowed_cert_hosts.add(parsed.hostname.lower())
        except Exception:
            pass

    def create_background_page(self) -> QWebEnginePage:
        """同じ認証プロファイルを共有するバックグラウンド取得用Pageを作成"""
        return CustomWebEnginePage(
            self.custom_profile, self, allowed_cert_hosts=self.allowed_cert_hosts
        )

    def create_tab_view(self, parent=None, disable_images: bool = False) -> "PersistentWebEngineView":
        """同じ認証プロファイルを共有するタブ用Viewを作成"""
        view = PersistentWebEngineView(
            profile=self.custom_profile,
            parent=parent,
            allowed_cert_hosts=self.allowed_cert_hosts,
        )
        if disable_images:
            view.settings().setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, False)
        return view

    def __init__(
        self,
        profile_path: str = "user_data/web_profile",
        profile: Optional[QWebEngineProfile] = None,
        parent=None,
        allowed_cert_hosts: Optional[Set[str]] = None,
    ):
        super().__init__(parent)
        self.logger = get_logger()
        self._target_worker_page: Optional[QWebEnginePage] = None
        self._target_worker_pages: deque[QWebEnginePage] = deque()
        self.allowed_cert_hosts: Set[str] = (
            set(allowed_cert_hosts) if allowed_cert_hosts is not None else {"10.200.5.191", "localhost", "127.0.0.1"}
        )

        # Cookie保存のデバウンス用タイマー
        self._cookie_save_timer = QTimer(self)
        self._cookie_save_timer.setSingleShot(True)
        self._cookie_save_timer.setInterval(500)
        self._cookie_save_timer.timeout.connect(self._flush_cookies_to_disk)

        is_root_view = (profile is None)
        if profile is not None:
            self.custom_profile = profile
            self.profile_path = profile.persistentStoragePath()
        else:
            self.profile_path = os.path.abspath(profile_path)
            os.makedirs(self.profile_path, exist_ok=True)
            # 永続プロファイルの作成 (ログイン情報・Cookie・LocalStorage保持)
            self.custom_profile = QWebEngineProfile("CurriculumAnalyzerProfile", self)
            self.custom_profile.setPersistentStoragePath(self.profile_path)
            self.custom_profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
            )

            # Web設定
            settings = self.custom_profile.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)

        # ページ作成 (証明書エラー制御付き)
        self.custom_page = CustomWebEnginePage(
            self.custom_profile, self, allowed_cert_hosts=self.allowed_cert_hosts
        )
        self.setPage(self.custom_page)

        # リアルタイムCookieキャッシュ (ルートViewのみCookieStore監視を行って重複保存を防止)
        self.cookies_cache: Dict[str, Dict[str, Any]] = {}
        if is_root_view:
            self._load_cached_cookies_from_file()
            cookie_store = self.custom_profile.cookieStore()
            cookie_store.cookieAdded.connect(self._on_cookie_added)
            cookie_store.cookieRemoved.connect(self._on_cookie_removed)
            cookie_store.loadAllCookies()

    def _load_cached_cookies_from_file(self):
        """前回保存されたJSONから初期Cookieを復元"""
        saved = load_cookies_from_json()
        for c in saved:
            if isinstance(c, dict) and "name" in c:
                self.cookies_cache[c["name"]] = c
        self._emit_status()

    def _schedule_cookie_flush(self):
        """短時間に連続発生するCookie更新をまとめてディスクへ書き込む"""
        if not self._cookie_save_timer.isActive():
            self._cookie_save_timer.start()

    def _flush_cookies_to_disk(self):
        save_cookies_to_json(list(self.cookies_cache.values()))

    def _on_cookie_added(self, cookie: QNetworkCookie):
        """Cookie追加・更新時のリアルタイムハンドラ"""
        c_dict = format_qcookie(cookie)
        name = c_dict["name"]
        prev = self.cookies_cache.get(name)
        self.cookies_cache[name] = c_dict
        if not prev or prev.get("value") != c_dict.get("value"):
            self._schedule_cookie_flush()
            if name in ("KGLC", "PHPSESSID", "session", "JSESSIONID"):
                self.logger.info(f"認証Cookieを捕捉しました: {name}")
        self._emit_status()

    def _on_cookie_removed(self, cookie: QNetworkCookie):
        """Cookie削除時のリアルタイムハンドラ"""
        c_dict = format_qcookie(cookie)
        name = c_dict["name"]
        if name in self.cookies_cache:
            del self.cookies_cache[name]
            self._schedule_cookie_flush()
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
        for name, c in self.cookies_cache.items():
            if any(key in name.lower() for key in ["session", "auth", "token", "kglc"]) and c.get("value"):
                return True
        return False

    def get_cookies_list(self) -> List[Dict[str, Any]]:
        """現在の全Cookieリストを即座に返却 (待機時間0ms・スレッドセーフ)"""
        if self._cookie_save_timer.isActive():
            self._cookie_save_timer.stop()
            self._flush_cookies_to_disk()
        cookies = list(self.cookies_cache.values())
        if not cookies:
            cookies = load_cookies_from_json()
        self.logger.info(f"Cookieリストを提供: {len(cookies)} 件 (認証: {self.is_authenticated()})")
        return cookies
