"""
QtWebEngine専用のイベント駆動型クローラー。
外部Playwrightを使用せず、同一WebEngineProfile(認証セッション共有)のバックグラウンドPageで
各生徒のシミュレーションシートを安全・確実に連続取得する。
"""
import json
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
        on_progress: Optional[Callable[[int, int, str], None]] = None,
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
        self._list_url = self.web_view.url().toString()

        self.logger.info(f"QtWebEngineクローラー開始: 対象 {len(target_overviews)} 件")
        self.web_view.new_window_requested.connect(self._on_new_window_requested)
        try:
            self.web_view.loadFinished.connect(self._on_web_view_load_finished)
        except Exception:
            pass

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
            self.on_progress(self._current_index + 1, total, ov.student_name)

        # タイムアウト監視開始 (15秒)
        self._timeout_timer.start(int(self.timeout_sec * 1000))

        # 同一生徒・同一区分・同一科目が複数行ある場合のN番目インデックスを算出
        occurrence_idx = 0
        for i in range(self._current_index):
            prev_ov = self.target_overviews[i]
            if (prev_ov.student_id == ov.student_id and
                prev_ov.division == ov.division and
                prev_ov.subject == ov.subject):
                occurrence_idx += 1

        sid_json = json.dumps(ov.student_id or "")
        div_json = json.dumps(ov.division or "")
        sub_json = json.dumps(ov.subject or "")
        name_json = json.dumps(ov.student_name or "")
        row_idx = ov.row_index

        js_click_code = f"""
        JSON.stringify((function() {{
            try {{
                var studentId = {sid_json}.trim();
                var division  = {div_json}.trim();
                var subject   = {sub_json}.trim();
                var studentName = {name_json}.trim();
                var occurrenceIdx = {occurrence_idx};

                var allRows = document.querySelectorAll("tr");
                var matchedRows = [];

                // 1. 学籍番号・受講区分・科目の3条件がすべて部分一致する行を探索
                for (var i = 0; i < allRows.length; i++) {{
                    var txt = allRows[i].innerText || "";
                    var matchId = !studentId || txt.indexOf(studentId) !== -1;
                    var matchDiv = !division || txt.indexOf(division) !== -1;
                    var matchSub = !subject || txt.indexOf(subject) !== -1;

                    if (matchId && matchDiv && matchSub) {{
                        matchedRows.push(allRows[i]);
                    }}
                }}

                // フォールバック1: 生徒名 ＋ 受講区分 ＋ 科目
                if (matchedRows.length === 0 && studentName) {{
                    for (var i = 0; i < allRows.length; i++) {{
                        var txt = allRows[i].innerText || "";
                        if (txt.indexOf(studentName) !== -1 && 
                            (!division || txt.indexOf(division) !== -1) && 
                            (!subject || txt.indexOf(subject) !== -1)) {{
                            matchedRows.push(allRows[i]);
                        }}
                    }}
                }}

                // フォールバック2: 学籍番号 ＋ 科目
                if (matchedRows.length === 0 && studentId && subject) {{
                    for (var i = 0; i < allRows.length; i++) {{
                        var txt = allRows[i].innerText || "";
                        if (txt.indexOf(studentId) !== -1 && txt.indexOf(subject) !== -1) {{
                            matchedRows.push(allRows[i]);
                        }}
                    }}
                }}

                var targetRow = null;
                if (matchedRows.length > 0) {{
                    targetRow = (occurrenceIdx < matchedRows.length) ? matchedRows[occurrenceIdx] : matchedRows[0];
                }}

                // フォールバック3: 一覧テーブル行インデックス
                if (!targetRow) {{
                    var rows = document.querySelectorAll("table tbody tr");
                    if ({row_idx} >= 0 && {row_idx} < rows.length) {{
                        targetRow = rows[{row_idx}];
                    }}
                }}

                if (!targetRow) {{
                    return {{
                        found: false,
                        error: "対象行が見つかりません (学籍番号: " + studentId + ", 受講区分: " + division + ", 科目: " + subject + ")"
                    }};
                }}

                // 2. 行内の 6列目 (td:nth-child(6)) のボタン探索
                var tds = targetRow.querySelectorAll("td");
                var btn = null;
                if (tds.length >= 6) {{
                    btn = tds[5].querySelector("button, a, input[type='button'], [role='button']");
                    if (!btn) {{
                        var anyClickable = tds[5].querySelector("*");
                        btn = anyClickable ? anyClickable : tds[5];
                    }}
                }}
                if (!btn) {{
                    btn = targetRow.querySelector("td:nth-child(6) button, td:nth-child(6) a, td:nth-child(6) input, button, a");
                }}

                if (!btn) {{
                    return {{
                        found: false,
                        error: "6列目にシミュレーションシートボタンが見つかりません (td数: " + tds.length + ", 行テキスト: " + (targetRow.innerText || "").substring(0, 40) + ")"
                    }};
                }}

                // 3. クリックの多重発火
                btn.click();
                btn.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));

                return {{
                    found: true,
                    btnTag: btn.tagName,
                    btnText: (btn.innerText || "").trim(),
                    rowText: (targetRow.innerText || "").replace(/\\s+/g, " ").trim().substring(0, 60),
                    matchCount: matchedRows.length,
                    usedOccurrence: occurrenceIdx
                }};

            }} catch (e) {{
                return {{ found: false, error: "JS例外: " + e.toString() }};
            }}
        }})());
        """

        def on_js_result(res):
            if not self._is_running or self._stop_requested:
                return
            data = None
            if isinstance(res, str):
                try:
                    data = json.loads(res)
                except Exception as parse_err:
                    self.logger.warning(f"JSONパースエラー: {parse_err} (生データ: {res[:100]})")
            elif isinstance(res, dict):
                data = res

            if data and data.get("found"):
                self.logger.info(
                    f"対象行・ボタン検出成功: {data.get('btnTag')} (テキスト: '{data.get('btnText')}') "
                    f"| 行抜粋: '{data.get('rowText')}' (該当 {data.get('matchCount')} 件中 {data.get('usedOccurrence', 0)+1} 件目を操作)"
                )
            else:
                err = data.get("error", "ボタンクリックに失敗しました") if data else f"JavaScript実行結果が空または無効です: {res}"
                self.logger.warning(f"生徒 {ov.student_id} ({ov.subject}) 行探索失敗: {err}")
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

        # SPA等のDOM描画完了を考慮して1000ms(1.0秒)待ってからHTMLを抽出 (合意仕様)
        page = self._active_sheet_page
        if page:
            QTimer.singleShot(1000, lambda: self._extract_html_from_page(page))

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

    def _on_web_view_load_finished(self, ok: bool):
        """同一画面での画面遷移フォールバックハンドラ (二重防御)"""
        if not self._is_running or self._stop_requested:
            return
        current_url = self.web_view.url().toString()
        if ok and hasattr(self, "_list_url") and current_url != self._list_url:
            self.logger.info(f"同一画面での画面遷移を検知しました: {current_url}")
            QTimer.singleShot(1000, self._extract_html_from_main_view_and_go_back)

    def _extract_html_from_main_view_and_go_back(self):
        """同一画面からHTMLを取得し、一覧画面へ戻る"""
        if not self._is_running or self._stop_requested:
            return

        def on_html(html: str):
            if not self._is_running or self._stop_requested:
                return
            if html and len(html) >= 200:
                self._on_fetch_success(html)
                self.web_view.back()
            else:
                self._handle_failure("同一画面遷移後のHTMLが空または短すぎます")

        self.web_view.page().toHtml(on_html)

    def _finish_crawl(self, success: bool, message: str):
        """クローラー全体の終了処理"""
        self._is_running = False
        self._cleanup_active_page()
        try:
            self.web_view.new_window_requested.disconnect(self._on_new_window_requested)
        except Exception:
            pass
        try:
            self.web_view.loadFinished.disconnect(self._on_web_view_load_finished)
        except Exception:
            pass

        self.logger.info(f"QtWebEngineクローラー終了: {message}")
        self.crawl_finished.emit(success, message)
