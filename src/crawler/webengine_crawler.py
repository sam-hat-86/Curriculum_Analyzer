"""
QtWebEngine専用のイベント駆動型クローラー。
外部Playwrightを使用せず、同一WebEngineProfile(認証セッション共有)のバックグラウンドPageで
各生徒のシミュレーションシートを安全・確実に連続取得する。
"""
from typing import List, Optional, Callable, Any
from datetime import datetime
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWebEngineCore import QWebEnginePage

from src.browser.web_engine_view import PersistentWebEngineView
from src.database.repository import Repository
from src.models.curriculum import CurriculumOverview
from src.utils.logger import get_logger


class WebEngineCrawler(QObject):
    """QtWebEngine上で各生徒のシミュレーションシートを順次取得するクローラー"""

    progress_updated = Signal(int, int)          # current, total
    status_message_updated = Signal(str)         # メッセージ
    html_fetched = Signal(object, str, str)      # overview, html, fetch_time
    crawl_finished = Signal(bool, str)           # success, message

    def __init__(
        self,
        web_view: PersistentWebEngineView,
        repository: Repository,
        request_interval_sec: float = 1.0,
        max_retries: int = 3,
        retry_interval_sec: float = 2.0,
        timeout_sec: float = 15.0,
        on_html_fetched: Optional[Callable[[CurriculumOverview, str, str], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.web_view = web_view
        self.repo = repository
        self.request_interval_sec = max(0.5, request_interval_sec)
        self.max_retries = max_retries
        self.retry_interval_sec = max(1.0, retry_interval_sec)
        self.timeout_sec = max(5.0, timeout_sec)
        self.on_html_fetched = on_html_fetched
        self.on_progress = on_progress
        self.logger = get_logger()

        self.target_overviews: List[CurriculumOverview] = []
        self._current_index: int = 0
        self._retry_count: int = 0
        self._is_running: bool = False
        self._stop_requested: bool = False

        self._active_sheet_page: Optional[QWebEnginePage] = None
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_item_timeout)

    def start_crawl(self, target_overviews: List[CurriculumOverview]):
        """クローラーを開始する"""
        if not target_overviews:
            self.logger.info("取得対象カリキュラムが0件です")
            self.crawl_finished.emit(True, "処理対象カリキュラムがありません")
            return

        self.target_overviews = target_overviews
        self._current_index = 0
        self._retry_count = 0
        self._is_running = True
        self._stop_requested = False

        self.logger.info(f"QtWebEngineクローラー開始: 対象 {len(target_overviews)} 件")
        self.web_view.new_window_requested.connect(self._on_new_window_requested)

        # 最初のアイテムを処理
        QTimer.singleShot(100, self._process_current_item)

    def stop(self):
        """クローラーを安全に停止する"""
        if self._is_running:
            self._stop_requested = True
            self.logger.info("クローラーに停止要求が送信されました")
            self._cleanup_active_page()
            self._finish_crawl(True, "ユーザーにより停止されました")

    def _cleanup_active_page(self):
        """アクティブなバックグラウンドページの解放とタイマー停止"""
        self._timeout_timer.stop()
        if self._active_sheet_page:
            try:
                self._active_sheet_page.deleteLater()
            except Exception:
                pass
            self._active_sheet_page = None

    def _process_current_item(self):
        """現在インデックスの生徒のシミュレーションシートを取得開始"""
        if not self._is_running or self._stop_requested:
            return

        total = len(self.target_overviews)
        if self._current_index >= total:
            self.logger.info("全対象カリキュラムの取得が完了しました")
            self._finish_crawl(True, f"全 {total} 件のシミュレーションシート取得が完了しました")
            return

        ov = self.target_overviews[self._current_index]
        self.logger.info(f"[{self._current_index + 1}/{total}] 取得開始: {ov.student_name} ({ov.student_id}) - 行 {ov.row_index}")
        
        msg = f"シミュレーションシート取得中 ({self._current_index + 1}/{total} 件): {ov.student_name}"
        self.status_message_updated.emit(msg)
        self.progress_updated.emit(self._current_index + 1, total)
        if self.on_progress:
            self.on_progress(self._current_index + 1, total)

        # タイムアウト監視開始 (15秒)
        self._timeout_timer.start(int(self.timeout_sec * 1000))

        # 一覧画面のテーブル6列目ボタンをクリックするJavaScriptを実行
        row_idx = ov.row_index
        js_click_code = f"""
        (function() {{
            var rows = document.querySelectorAll("table tbody tr");
            var idx = {row_idx};
            if (idx < 0 || idx >= rows.length) {{
                return {{found: false, error: "行インデックス " + idx + " が見つかりません (全行数: " + rows.length + ")"}} ;
            }}
            var row = rows[idx];
            
            // ユーザー指定: 6列目のボタンを優先探索
            var btn = row.querySelector("td:nth-child(6) button, td:nth-child(6) a, td:nth-child(6) input[type='button'], td:nth-child(6) [role='button']");
            if (!btn) {{
                // 念のためテキストによるフォールバック
                var allBtns = row.querySelectorAll("button, a");
                for (var i = 0; i < allBtns.length; i++) {{
                    var txt = (allBtns[i].innerText || "").trim();
                    if (txt.indexOf("シミュレーション") !== -1) {{
                        btn = allBtns[i];
                        break;
                    }}
                }}
            }}
            
            if (!btn) {{
                var tdCount = row.querySelectorAll("td").length;
                return {{found: false, error: "6列目にシミュレーションシートボタンがありません (td数: " + tdCount + ")"}} ;
            }}
            
            btn.click();
            return {{found: true}};
        }})();
        """

        def on_js_result(res):
            if not self._is_running or self._stop_requested:
                return
            if not isinstance(res, dict) or not res.get("found"):
                err = res.get("error", "ボタンクリックに失敗しました") if isinstance(res, dict) else "JavaScriptの実行に失敗しました"
                self.logger.warning(f"行 {row_idx} ボタン探索失敗: {err}")
                self._handle_failure(err)

        self.web_view.page().runJavaScript(js_click_code, on_js_result)

    def _on_new_window_requested(self, sheet_page: QWebEnginePage):
        """社内システムが window.open 等で別タブを開いた際のハンドラ"""
        if not self._is_running or self._stop_requested:
            return

        self.logger.debug("シミュレーションシートの別タブオープンを捕捉しました")
        self._cleanup_active_page()
        self._active_sheet_page = sheet_page

        # ページロード完了を待機
        sheet_page.loadFinished.connect(self._on_sheet_page_loaded)

    def _on_sheet_page_loaded(self, ok: bool):
        """別タブのHTMLロード完了ハンドラ"""
        if not self._is_running or self._stop_requested:
            return

        if not ok:
            self._handle_failure("シミュレーションシートの読み込みに失敗しました (loadFinished: False)")
            return

        # SPA等のDOM描画完了を考慮して500ms待ってからHTMLを抽出
        page = self._active_sheet_page
        if page:
            QTimer.singleShot(500, lambda: self._extract_html_from_page(page))

    def _extract_html_from_page(self, page: QWebEnginePage):
        """ページからHTMLテキストを抽出"""
        if not self._is_running or self._stop_requested or page != self._active_sheet_page:
            return

        def on_html(html: str):
            if not self._is_running or self._stop_requested:
                return
            if not html or len(html) < 200:
                self._handle_failure("取得されたHTMLが空または短すぎます")
                return

            self._on_fetch_success(html)

        page.toHtml(on_html)

    def _on_fetch_success(self, html: str):
        """1件のシミュレーションシート取得成功時の処理"""
        self._timeout_timer.stop()
        self._cleanup_active_page()

        ov = self.target_overviews[self._current_index]
        url_key = ov.detail_url or f"{ov.classroom_code}_{ov.student_id}_{ov.subject}_{ov.row_index}"
        fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # DBへ保存
        self.repo.update_page_fetched(url_key, html, fetch_time)
        self.logger.info(f"[{self._current_index + 1}/{len(self.target_overviews)}] 取得成功: {ov.student_name} ({ov.student_id})")

        # コールバックおよびシグナル発行 (解析パイプラインへ)
        if self.on_html_fetched:
            self.on_html_fetched(ov, html, fetch_time)
        self.html_fetched.emit(ov, html, fetch_time)

        # リトライカウンタリセット & 次のアイテムへ
        self._retry_count = 0
        self._current_index += 1

        # サーバー負荷対策のインターバル待機 (仕様書§4.1)
        wait_ms = int(self.request_interval_sec * 1000)
        QTimer.singleShot(wait_ms, self._process_current_item)

    def _on_item_timeout(self):
        """タイムアウト時のハンドラ"""
        if not self._is_running or self._stop_requested:
            return
        self._handle_failure(f"取得タイムアウト ({self.timeout_sec}秒超過)")

    def _handle_failure(self, error_msg: str):
        """取得失敗時のハンドラ (リトライまたはスキップ)"""
        self._timeout_timer.stop()
        self._cleanup_active_page()

        if self._current_index >= len(self.target_overviews):
            return

        ov = self.target_overviews[self._current_index]
        url_key = ov.detail_url or f"{ov.classroom_code}_{ov.student_id}_{ov.subject}_{ov.row_index}"

        self._retry_count += 1
        if self._retry_count <= self.max_retries:
            self.logger.warning(
                f"取得失敗 ({self._retry_count}/{self.max_retries} リトライ待ち): {ov.student_id} {ov.student_name} - {error_msg}"
            )
            wait_ms = int(self.retry_interval_sec * 1000)
            QTimer.singleShot(wait_ms, self._process_current_item)
        else:
            # 仕様書§4.3準拠: 1ページの取得失敗で全体処理を止めずスキップして最後まで完走
            self.logger.error(
                f"最大リトライ回数超過 (取得失敗・スキップ): {ov.student_id} {ov.student_name} - {error_msg}"
            )
            self.repo.update_page_fetch_failed(url_key, error_msg)
            self._retry_count = 0
            self._current_index += 1
            # 次の生徒へ進む
            QTimer.singleShot(500, self._process_current_item)

    def _finish_crawl(self, success: bool, message: str):
        """クローラー全体の終了処理"""
        self._is_running = False
        self._cleanup_active_page()
        try:
            self.web_view.new_window_requested.disconnect(self._on_new_window_requested)
        except Exception:
            pass

        self.logger.info(f"QtWebEngineクローラー終了: {message}")
        self.crawl_finished.emit(success, message)
