"""
Playwright Webクローラーマネージャー (仕様書§3, §4, §33, §37 & ユーザー合意決定)
"""
import time
import threading
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime
from urllib.parse import urlparse

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

                # Cookieの設定 (セッション引き継ぎ)
                if self.cookies:
                    parsed = urlparse(list_url) if list_url else None
                    host = parsed.hostname if (parsed and parsed.hostname) else "10.200.5.191"

                    pw_cookies = []
                    for c in self.cookies:
                        cookie_domain = c.get("domain") or host
                        if ":" in cookie_domain:
                            cookie_domain = cookie_domain.split(":")[0]

                        pw_cookies.append({
                            "name": c["name"],
                            "value": c["value"],
                            "domain": cookie_domain,
                            "path": c.get("path") or "/",
                        })
                    try:
                        context.add_cookies(pw_cookies)
                        self.logger.info(f"PlaywrightにCookieを適用しました: {len(pw_cookies)} 件 (ホスト: {host})")
                    except Exception as e:
                        self.logger.warning(f"一括Cookie適用エラー、個別/URLフォールバック試行: {e}")
                        for sc in pw_cookies:
                            try:
                                context.add_cookies([sc])
                            except Exception:
                                try:
                                    context.add_cookies([{
                                        "name": sc["name"],
                                        "value": sc["value"],
                                        "url": f"http://{host}/"
                                    }])
                                except Exception as err2:
                                    self.logger.error(f"Cookie追加失敗 ({sc.get('name')}): {err2}")

                page = context.new_page()
                page.set_default_timeout(self.timeout_sec * 1000)

                # 1. 一覧ページへ遷移
                if list_url and list_url.startswith("http"):
                    self.logger.info(f"一覧ページへアクセス: {list_url}")
                    page.goto(list_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                    # ログイン画面への転送チェック (セッション切れの即時検知)
                    if "login" in page.url.lower():
                        err_msg = f"ログインセッションが無効です (ログイン画面へ転送されました: {page.url})。ブラウザ上で再ログインしてください。"
                        self.logger.error(err_msg)
                        raise RuntimeError(err_msg)

                    # テーブル表示待機 (最大10秒)
                    try:
                        page.wait_for_selector("table tbody tr", timeout=10000)
                        self.logger.info(f"一覧テーブル検出完了 (行数: {page.locator('table tbody tr').count()})")
                    except Exception:
                        self.logger.warning(f"一覧テーブルの表示待機タイムアウト (現在URL: {page.url})")

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
                            # 1. 対象行 (tr) の特定
                            row_locator = None
                            
                            # 方法A: 生徒番号で特定 (最優先)
                            if ov.student_id:
                                r = page.locator(f"tr:has-text('{ov.student_id}')")
                                if r.count() > 0:
                                    row_locator = r.first
                            
                            # 方法B: Playwright nth インデックスで特定
                            if not row_locator:
                                trs = page.locator("table tbody tr")
                                if trs.count() > ov.row_index:
                                    row_locator = trs.nth(ov.row_index)
                            
                            # 方法C: tbody > tr:nth-child で特定
                            if not row_locator:
                                r = page.locator(f"tbody > tr:nth-child({ov.row_index + 1})")
                                if r.count() > 0:
                                    row_locator = r.first

                            if not row_locator:
                                raise RuntimeError(f"行 {ov.row_index} (生徒: {ov.student_id} {ov.student_name}) の行要素が見つかりません")

                            # 2. ボタンの特定 (ユーザー指定: テーブルの6列目にボタンがある)
                            sim_btn = None

                            # 優先1: テーブルの6列目 (td:nth-child(6)) のボタン・リンク・要素
                            column_candidates = [
                                "td:nth-child(6) button",
                                "td:nth-child(6) a",
                                "td:nth-child(6) [role='button']",
                                "td:nth-child(6) input[type='button']",
                                "td:nth-child(6)",
                                "td:nth-child(7) button",
                                "td:nth-child(7) a",
                                "td:nth-child(5) button",
                            ]
                            for col_sel in column_candidates:
                                candidate = row_locator.locator(col_sel)
                                if candidate.count() > 0:
                                    sim_btn = candidate.first
                                    break

                            # 優先2: セレクタテキスト/クラスによるフォールバック
                            if not sim_btn:
                                text_candidates = [
                                    "button:has-text('シミュレーションシート')",
                                    "a:has-text('シミュレーションシート')",
                                    "button.btnColor-gray",
                                    "button.btn-hight-2rows",
                                    "button[class*='btnColor']",
                                    "button",
                                    "a.button",
                                ]
                                for b_sel in text_candidates:
                                    candidate = row_locator.locator(b_sel)
                                    if candidate.count() > 0:
                                        sim_btn = candidate.first
                                        break

                            if not sim_btn:
                                row_text = ""
                                td_count = 0
                                try:
                                    row_text = row_locator.inner_text()
                                    td_count = row_locator.locator("td").count()
                                except Exception:
                                    pass
                                raise RuntimeError(
                                    f"行 {ov.row_index} (生徒: {ov.student_id} {ov.student_name}) のシミュレーションシートボタンが見つかりません "
                                    f"(列数: {td_count}, 行テキスト: {row_text[:50]})"
                                )

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
                                self.logger.warning(f"別タブオープンが検出されませんでした (10秒タイムアウト): {open_err}")
                                # 同一画面での画面遷移チェック
                                if page.url != list_url:
                                    page.wait_for_load_state("domcontentloaded")
                                    page.wait_for_timeout(1000)
                                    html_content = page.content()
                                    page.go_back(wait_until="domcontentloaded")
                                    page.wait_for_timeout(1000)
                                else:
                                    raise RuntimeError(f"シミュレーションシートの別タブオープンに失敗しました (ボタン押下後に別タブもURL変化も未検出): {open_err}")

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
