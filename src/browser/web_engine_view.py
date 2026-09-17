"""
PySide6 WebEngine ブラウザビュー (永続プロファイル対応)
"""
import os
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
from PySide6.QtCore import QUrl

class PersistentWebEngineView(QWebEngineView):
    def __init__(self, profile_path: str = "user_data/web_profile", parent=None):
        super().__init__(parent)
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

        # ページ作成
        self.custom_page = QWebEnginePage(self.custom_profile, self)
        self.setPage(self.custom_page)

    def get_cookies_list(self) -> list:
        """Cookieリストを抽出"""
        from src.browser.cookie_extractor import extract_cookies_sync
        return extract_cookies_sync(self.custom_profile)
