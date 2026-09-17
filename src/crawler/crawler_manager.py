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
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )

                # Cookieの設定
                if self.cookies:
                    # Playwrightの形式に整形
                    pw_cookies = []
                    for c in self.cookies:
                        cookie_dict = {
                            "name": c["name"],
                            "value": c["value"],
                            "domain": c.get("domain", ""),
                            "path": c.get("path", "/"),
                        }
                        if cookie_dict["domain"].startswith("."):
                            # valid domain
                            pass
                        pw_cookies.append(cookie_dict)
                    try:
                        context.add_cookies(pw_cookies)
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
                            # sampleMSL.htmlの構造: tbody > tr[row_index] 内のシミュレーションシートボタン
                            sim_btn = None
                            
                            # 方法1: 行インデックスで特定
                            row_locator = page.locator(f"tbody > tr:nth-child({ov.row_index + 1})")
                            if row_locator.count() > 0:
                                sim_btn = row_locator.locator("button:has-text('シミュレーションシート')")
                            
                            # 方法2: 生徒番号または行テキストから特定
                            if not sim_btn or sim_btn.count() == 0:
                                sim_btn = page.locator(f"tr:has-text('{ov.student_id}') button:has-text('シミュレーションシート')")

                            if not sim_btn or sim_btn.count() == 0:
                                # ボタンが見つからない場合
                                raise RuntimeError(f"行 {ov.row_index} (生徒: {ov.student_id}) のシミュレーションシートボタンが見つかりません")

                            # 別タブで開くか同一画面かを待機判定
                            # 多くのWebシステムでは window.open で別タブが開く
                            html_content = ""
                            fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                            try:
                                with context.expect_page(timeout=5000) as new_page_info:
                                    sim_btn.first.click()
                                new_page = new_page_info.value
                                new_page.wait_for_load_state("domcontentloaded")
                                new_page.wait_for_timeout(1000)
                                html_content = new_page.content()
                                new_page.close()
                            except Exception:
                                # 別タブが開かなかった場合は同一画面遷移またはモーダル
                                page.wait_for_timeout(1500)
                                html_content = page.content()
                                # 一覧画面に戻る
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
