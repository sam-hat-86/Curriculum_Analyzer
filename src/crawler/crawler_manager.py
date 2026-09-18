"""
Playwright Webクローラーマネージャー (仕様書§3, §4, §33, §37 & ユーザー合意決定)
"""
import time
import threading
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime

from src.models.curriculum import CurriculumOverview
from src.models.state import ProcessState
from src.database.repository import Repository
from src.utils.logger import get_logger

class CrawlerManager:
    def __init__(
        self,
        repository: Repository,
        cookies: Optional[List[Dict[str, Any]]] = None,
        request_interval_sec: float = 1.0,
        max_retries: int = 3,
        retry_interval_sec: float = 2.0,
        timeout_sec: int = 30,
        headless: bool = True,
        on_html_fetched: Optional[Callable[[CurriculumOverview, str, str], None]] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ):
        self.repo = repository
        self.cookies = cookies or []
        self.request_interval_sec = request_interval_sec
        self.max_retries = max_retries
        self.retry_interval_sec = retry_interval_sec
        self.timeout_sec = timeout_sec
        self.headless = headless
        self.on_html_fetched = on_html_fetched
        self.on_progress = on_progress
        
        self.is_running = False
        self.is_paused = False
        self.logger = get_logger()
        self._stop_requested = threading.Event()

    def stop(self):
        """クロール停止要求"""
        self._stop_requested.set()
        self.is_running = False
        self.logger.info("クローラーに停止要求が送信されました")

    def run_crawl_list_items(self, list_url: str, overviews: List[CurriculumOverview]):
        """
        一覧画面の各行にある「シミュレーションシート」ボタンを1並列で順次クリックしてHTMLを取得
        """
        self.is_running = True
        self._stop_requested.clear()
        self.logger.info(f"Playwrightクローラー起動: 対象 {len(overviews)} 件 (1並列)")

        # Playwrightの動的インポート
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.logger.error("Playwrightがインストールされていません")
            return

        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    ignore_https_errors=True
                )

                # Cookieの設定
                if self.cookies:
                    pw_cookies = []
                    for c in self.cookies:
                        cookie_dict = {
                            "name": c["name"],
                            "value": c["value"],
                            "path": c.get("path", "/"),
                        }
                        domain = c.get("domain", "").strip()
                        # ドメインが有効なFQDN形式の場合のみdomainをセット、IPや空の場合はurlをセット
                        if domain and not domain.replace(".", "").isdigit() and not ":" in domain:
                            cookie_dict["domain"] = domain
                        elif list_url and list_url.startswith("http"):
                            cookie_dict["url"] = list_url
                        pw_cookies.append(cookie_dict)
                    try:
                        context.add_cookies(pw_cookies)
                        self.logger.info(f"PlaywrightにCookieを適用しました: {len(pw_cookies)} 件")
                    except Exception as e:
                        self.logger.warning(f"Cookieの適用中に警告: {e}")

                page = context.new_page()
                page.set_default_timeout(self.timeout_sec * 1000)

                # 1. 一覧ページへ遷移
                if list_url and list_url.startswith("http"):
                    self.logger.info(f"一覧ページへアクセス: {list_url}")
                    page.goto(list_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(1000)

                total_items = len(overviews)
                button_selectors = [
                    "button:has-text('シミュレーションシート')",
                    "button.btnColor-gray",
                    "button.btn-hight-2rows",
                    "button[class*='btnColor']",
                    "a:has-text('シミュレーションシート')",
                ]

                for idx, ov in enumerate(overviews):
                    if self._stop_requested.is_set():
                        self.logger.info("クローラー処理が中断されました")
                        break

                    # 既取得チェック (再開機能: 仕様書§5, §29)
                    url_key = ov.detail_url or f"{ov.classroom_code}_{ov.student_id}_{ov.subject}_{ov.row_index}"
                    
                    if self.on_progress:
                        self.on_progress(idx + 1, total_items, f"{ov.student_name} ({ov.student_id})")

                    # 取得処理 (リトライ付き: 仕様書§4.3)
                    success = False
                    retry_cnt = 0
                    last_error = ""

                    while retry_cnt <= self.max_retries and not success:
                        if self._stop_requested.is_set():
                            break
                        try:
                            # 「シミュレーションシート」ボタンを探してクリック
                            sim_btn = None
                            
                            # 方法1: 生徒番号または生徒名が含まれる行から特定 (最優先)
                            if ov.student_id:
                                row_by_id = page.locator(f"tr:has-text('{ov.student_id}')")
                                if row_by_id.count() > 0:
                                    for b_sel in button_selectors:
                                        btn_candidate = row_by_id.first.locator(b_sel)
                                        if btn_candidate.count() > 0:
                                            sim_btn = btn_candidate.first
                                            break

                            # 方法2: 行インデックスで特定
                            if not sim_btn or sim_btn.count() == 0:
                                row_locator = page.locator(f"tbody > tr:nth-child({ov.row_index + 1})")
                                if row_locator.count() > 0:
                                    for b_sel in button_selectors:
                                        btn_candidate = row_locator.locator(b_sel)
                                        if btn_candidate.count() > 0:
                                            sim_btn = btn_candidate.first
                                            break

                            if not sim_btn or sim_btn.count() == 0:
                                raise RuntimeError(f"行 {ov.row_index} (生徒: {ov.student_id} {ov.student_name}) のシミュレーションシートボタンが見つかりません")

                            # 別タブ（別ウィンドウ）オープン待機 (ユーザー指定挙動)
                            html_content = ""
                            fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                            try:
                                with context.expect_page(timeout=10000) as new_page_info:
                                    sim_btn.click()
                                new_page = new_page_info.value
                                new_page.wait_for_load_state("domcontentloaded")
                                new_page.wait_for_timeout(1000)
                                html_content = new_page.content()
                                new_page.close()
                            except Exception as open_err:
                                self.logger.debug(f"別タブ待機タイムアウト、同一画面/フォールバック待機: {open_err}")
                                page.wait_for_timeout(1500)
                                html_content = page.content()
                                # 一覧画面から別画面に遷移していた場合は復帰
                                if page.url != list_url:
                                    page.go_back(wait_until="domcontentloaded")
                                    page.wait_for_timeout(1000)

                            if not html_content or len(html_content) < 200:
                                raise ValueError("取得されたHTMLが空または不完全です")

                            # 取得成功の保存
                            self.repo.update_page_fetched(url_key, html_content, fetch_time)
                            success = True
                            self.logger.info(f"[{idx+1}/{total_items}] 取得成功: {ov.student_name} ({ov.student_id})")

                            if self.on_html_fetched:
                                self.on_html_fetched(ov, html_content, fetch_time)

                        except Exception as e:
                            last_error = str(e)
                            retry_cnt += 1
                            if retry_cnt <= self.max_retries:
                                self.logger.warning(f"取得失敗 ({retry_cnt}/{self.max_retries} リトライ待ち): {ov.student_id} - {e}")
                                time.sleep(self.retry_interval_sec)
                            else:
                                self.logger.error(f"最大リトライ回数超過 (取得失敗): {ov.student_id} - {e}")
                                self.repo.update_page_fetch_failed(url_key, last_error)

                    # アクセス間隔の遵守 (仕様書§4.1: 1並列負荷軽減)
                    time.sleep(self.request_interval_sec)

            except Exception as e:
                self.logger.error(f"Playwrightクローラー全体エラー: {e}", exc_info=True)
            finally:
                if browser:
                    browser.close()
                self.is_running = False
                self.logger.info("Playwrightクローラーが停止しました")
