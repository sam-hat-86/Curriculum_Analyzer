"""
QtWebEngine 複数タブ並行ワーカー型クローラー (v2.0.2)。
一覧画面（Tab 0）を常時保持・再読込不要とし、複数の取得用タブでシミュレーションシートを並行・安全に取得する。
URL等の内部ノイズを排除し、直感的な進捗ログを出力する。
"""
import json
from enum import Enum, auto
from typing import List, Optional, Callable, Any, Dict
from datetime import datetime
from PySide6.QtCore import QObject, QTimer, Signal, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage

from src.browser.web_engine_view import PersistentWebEngineView, CustomWebEnginePage
from src.database.repository import Repository
from src.models.curriculum import CurriculumOverview
from src.utils.logger import get_logger


class CrawlerState(Enum):
    """クローラーのライフサイクル状態"""
    IDLE = auto()               # 待機中
    RUNNING = auto()            # クロール実行中
    STOPPING = auto()           # 安全停止待機中 (進行中リクエストの保存待ち)


class WorkerSlot:
    """複数タブ運用のための個別ワーカータブ管理スロット"""
    def __init__(self, slot_idx: int, view: PersistentWebEngineView, parent_crawler: "WebEngineCrawler"):
        self.slot_idx = slot_idx
        self.view = view
        self.crawler = parent_crawler
        self.is_busy = False
        self.current_overview: Optional[CurriculumOverview] = None
        self.retry_count = 0

        # タイムアウトタイマー
        self.timeout_timer = QTimer(parent_crawler)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        # DOM描画安定待機タイマー
        self.render_timer = QTimer(parent_crawler)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self._on_render_ready)

        # ロード完了シグナル接続
        try:
            self.view.loadFinished.connect(self._on_load_finished)
        except Exception:
            pass

    def start_item(self, overview: CurriculumOverview, timeout_sec: float):
        """生徒のシミュレーションシート取得を開始"""
        self.is_busy = True
        self.current_overview = overview
        self.timeout_timer.start(int(timeout_sec * 1000))

    def _on_load_finished(self, ok: bool):
        if not self.is_busy or not self.crawler.is_running:
            return

        current_url = self.view.url().toString()
        if not current_url or current_url == "about:blank":
            return

        self.timeout_timer.stop()
        if not ok:
            self.crawler.handle_slot_failure(self, "ページの読み込みに失敗しました")
            return

        # SPAや動的DOMの描画完了を待機
        delay_ms = int(self.crawler.sheet_render_delay_sec * 1000)
        self.render_timer.start(max(100, delay_ms))

    def _on_render_ready(self):
        if not self.is_busy or not self.crawler.is_running:
            return

        def on_html(html: str):
            if not self.is_busy or not self.crawler.is_running:
                return
            if not html or len(html) < 200:
                self.crawler.handle_slot_failure(self, "取得されたHTMLが空または短すぎます")
                return

            self.crawler.handle_slot_success(self, html)

        # SPAやBuefyで動的変更されたinput.checkedをHTML属性に同期してからシリアライズ
        sync_checkbox_js = """
        (function() {
            try {
                var inputs = document.querySelectorAll('input[type="checkbox"], input[type="radio"]');
                for (var i = 0; i < inputs.length; i++) {
                    if (inputs[i].checked) {
                        inputs[i].setAttribute('checked', 'checked');
                    } else {
                        inputs[i].removeAttribute('checked');
                    }
                }
            } catch (e) {}
        })();
        """
        page = self.view.page() if hasattr(self.view, "page") else None
        if page and hasattr(page, "runJavaScript"):
            page.runJavaScript(sync_checkbox_js, lambda _: page.toHtml(on_html))
        elif page and hasattr(page, "toHtml"):
            page.toHtml(on_html)
        else:
            self.crawler.handle_slot_failure(self, "ページオブジェクトが無効です")

    def _on_timeout(self):
        if not self.is_busy or not self.crawler.is_running:
            return
        self.render_timer.stop()
        self.crawler.handle_slot_failure(self, f"取得タイムアウト ({self.crawler.timeout_sec}秒超過)")

    def cleanup(self):
        """タイマー停止と状態リセット"""
        self.timeout_timer.stop()
        self.render_timer.stop()
        self.is_busy = False
        self.current_overview = None
        self.retry_count = 0
        try:
            self.view.setUrl(QUrl("about:blank"))
        except Exception:
            pass


class WebEngineCrawler(QObject):
    """複数タブ対応・QtWebEngineイベント駆動型クローラー"""

    progress_updated = Signal(int, int)          # current, total
    status_message_updated = Signal(str)         # メッセージ
    html_fetched = Signal(object, str, str)      # overview, html, fetch_time
    crawl_finished = Signal(bool, str)           # success, message
    tab_activity_updated = Signal(int, str)      # slot_idx, status_text

    def __init__(
        self,
        web_view: PersistentWebEngineView,
        repository: Repository,
        tab_views: Optional[List[PersistentWebEngineView]] = None,
        max_tabs: int = 2,
        request_interval_sec: float = 0.5,
        sheet_render_delay_sec: float = 0.8,
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
        self.max_tabs = max(1, min(4, max_tabs))
        self.request_interval_sec = max(0.1, request_interval_sec)
        self.sheet_render_delay_sec = max(0.1, sheet_render_delay_sec)
        self.max_retries = max_retries
        self.retry_interval_sec = max(0.5, retry_interval_sec)
        self.timeout_sec = max(5.0, timeout_sec)
        self.on_html_fetched = on_html_fetched
        self.on_progress = on_progress
        self.logger = get_logger()

        self.target_overviews: List[CurriculumOverview] = []
        self._queue: List[CurriculumOverview] = []
        self._total_count: int = 0
        self._completed_count: int = 0
        self._state: CrawlerState = CrawlerState.IDLE
        self._stop_requested: bool = False

        # ワーカータブスロット
        self.worker_slots: List[WorkerSlot] = []
        self._created_views: List[PersistentWebEngineView] = []
        self._active_dispatch_slot: Optional[WorkerSlot] = None

        if tab_views:
            for idx, tv in enumerate(tab_views):
                self.worker_slots.append(WorkerSlot(idx, tv, self))
        else:
            # 外部から渡されない場合は指定数分のタブを生成
            for idx in range(self.max_tabs):
                tv = self.web_view.create_tab_view(parent=self)
                self._created_views.append(tv)
                self.worker_slots.append(WorkerSlot(idx, tv, self))

        # ナビゲーション傍受接続（一覧画面の誤遷移を防止）
        page = self.web_view.page()
        if isinstance(page, CustomWebEnginePage):
            page.navigation_intercepted.connect(self._on_navigation_intercepted)

    @property
    def is_running(self) -> bool:
        return self._state in (CrawlerState.RUNNING, CrawlerState.STOPPING)

    @property
    def state(self) -> CrawlerState:
        return self._state

    def start_crawl(self, target_overviews: List[CurriculumOverview]):
        """クローラーを開始する"""
        if not target_overviews:
            self.logger.info("取得対象カリキュラムが0件です")
            self.crawl_finished.emit(True, "処理対象カリキュラムがありません")
            return

        self.target_overviews = list(target_overviews)
        self._queue = list(target_overviews)
        self._total_count = len(target_overviews)
        self._completed_count = 0
        self._stop_requested = False
        self._state = CrawlerState.RUNNING

        # 一覧画面の誤遷移をインターセプト有効化
        page = self.web_view.page()
        if isinstance(page, CustomWebEnginePage):
            page.intercept_navigation = True

        self.logger.info(f"カリキュラム取得開始: 対象 {self._total_count} 件 (並行タブ数: {len(self.worker_slots)})")

        # 最初のタスク群を各空きスロットへ割り当て
        self._dispatch_next()

    def stop(self):
        """安全停止要求（進行中のタブのHTML保存を待って終了）"""
        if self._state == CrawlerState.RUNNING:
            self._stop_requested = True
            self._state = CrawlerState.STOPPING
            # キューに残っている未開始タスクをクリア
            self._queue.clear()
            self.logger.info("クローラーに停止要求が送信されました。進行中の取得完了を待機しています...")
            self.status_message_updated.emit("停止処理中: 現在の生徒の保存完了を待機しています...")

            # もし現在稼働中のスロットがなければ直ちに終了
            busy_slots = [s for s in self.worker_slots if s.is_busy]
            if not busy_slots:
                self._finish_crawl(True, "ユーザーにより安全に停止されました")

    def _dispatch_next(self):
        """空いているワーカースロットへ順番にタスクを投入 (複数スロット時は時差ディスパッチで競合回避)"""
        if not self.is_running or self._stop_requested:
            self._check_all_finished()
            return

        target_slot = None
        for slot in self.worker_slots:
            if not slot.is_busy:
                target_slot = slot
                break

        if target_slot and self._queue:
            ov = self._queue.pop(0)
            self._assign_item_to_slot(target_slot, ov)

            # 他にも空きスロットがあり、かつ未処理キューがあれば350ms後に時差ディスパッチ
            has_other_free = any(not s.is_busy for s in self.worker_slots)
            if has_other_free and self._queue and not self._stop_requested:
                QTimer.singleShot(350, self._dispatch_next)

        self._check_all_finished()

    def _assign_item_to_slot(self, slot: WorkerSlot, ov: CurriculumOverview):
        """1件の生徒アイテムを特定のスロットに割り当てて取得開始"""
        slot.start_item(ov, self.timeout_sec)

        current_idx = self._total_count - len(self._queue)
        msg_header = f"[着手 {current_idx}/{self._total_count}] {ov.student_name} ({ov.subject})"
        self.logger.info(f"{msg_header}: シミュレーションシート取得中...")
        self.status_message_updated.emit(f"取得中 ({current_idx}/{self._total_count} 件): {ov.student_name} ({ov.subject})")
        self.progress_updated.emit(self._completed_count + 1, self._total_count)
        if self.on_progress:
            self.on_progress(self._completed_count + 1, self._total_count, ov.student_name)

        self.tab_activity_updated.emit(slot.slot_idx, f"取得中: {ov.student_name}")

        # 次のwindow.openのロード先Pageとして予約設定
        self.web_view.set_target_worker_page(slot.view.page())
        self._active_dispatch_slot = slot

        # 一覧画面上の該当生徒行のボタンをクリックするJavaScriptを実行
        self._click_button_for_overview(ov, slot)

    def _click_button_for_overview(self, ov: CurriculumOverview, slot: WorkerSlot):
        """一覧画面上で該当生徒行の「シミュレーションシート」ボタンをクリック"""
        # 同一条件行のN番目インデックス算出
        occurrence_idx = 0
        for i in range(self.target_overviews.index(ov) if ov in self.target_overviews else 0):
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

                for (var i = 0; i < allRows.length; i++) {{
                    var txt = allRows[i].innerText || "";
                    var matchId = !studentId || txt.indexOf(studentId) !== -1;
                    var matchDiv = !division || txt.indexOf(division) !== -1;
                    var matchSub = !subject || txt.indexOf(subject) !== -1;

                    if (matchId && matchDiv && matchSub) {{
                        matchedRows.push(allRows[i]);
                    }}
                }}

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

                if (!targetRow) {{
                    var rows = document.querySelectorAll("table tbody tr");
                    if ({row_idx} >= 0 && {row_idx} < rows.length) {{
                        targetRow = rows[{row_idx}];
                    }}
                }}

                if (!targetRow) {{
                    return {{ found: false, error: "対象行が見つかりません" }};
                }}

                var btn = null;
                var allButtons = targetRow.querySelectorAll("button, a, input[type='button'], input[type='submit'], [role='button']");
                for (var b = 0; b < allButtons.length; b++) {{
                    var bText = (allButtons[b].innerText || allButtons[b].textContent || allButtons[b].value || "").replace(/\\s+/g, "");
                    if (bText.indexOf("シミュレーションシート") !== -1 || bText.indexOf("シミュレーション") !== -1) {{
                        btn = allButtons[b];
                        break;
                    }}
                }}

                if (!btn) {{
                    var allElements = targetRow.querySelectorAll("*");
                    for (var e = 0; e < allElements.length; e++) {{
                        var el = allElements[e];
                        var elText = (el.innerText || el.textContent || "").replace(/\\s+/g, "");
                        if (elText.indexOf("シミュレーションシート") !== -1 || elText.indexOf("シミュレーション") !== -1) {{
                            btn = el.closest("button, a, input, [role='button']") || el;
                            break;
                        }}
                    }}
                }}

                if (!btn) {{
                    btn = targetRow.querySelector("button.btn-hight-2rows, button.btnColor-gray.btn-hight-2rows");
                }}

                if (!btn) {{
                    var tds = targetRow.querySelectorAll("td");
                    if (tds.length >= 8) {{
                        btn = tds[7].querySelector("button, a, input[type='button'], [role='button']");
                    }}
                }}

                if (!btn) {{
                    return {{ found: false, error: "シミュレーションシートボタンが見つかりません" }};
                }}

                // 直接リンク(href)が存在する場合はURLも返却
                var linkUrl = "";
                if (btn.tagName.toLowerCase() === "a" && btn.href) {{
                    linkUrl = btn.href;
                }} else {{
                    var parentA = btn.closest("a");
                    if (parentA && parentA.href) {{
                        linkUrl = parentA.href;
                    }}
                }}

                if (btn.scrollIntoView) {{
                    btn.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                }}
                btn.click();
                btn.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));

                return {{
                    found: true,
                    url: linkUrl
                }};

            }} catch (e) {{
                return {{ found: false, error: "JS例外: " + e.toString() }};
            }}
        }})());
        """

        def on_js_result(res):
            if not self.is_running or not slot.is_busy:
                return
            data = None
            if isinstance(res, str):
                try:
                    data = json.loads(res)
                except Exception:
                    pass
            elif isinstance(res, dict):
                data = res

            if data and data.get("found"):
                direct_url = data.get("url")
                if direct_url and direct_url.startswith("http"):
                    self.logger.debug(f"直接リンク検出、スロットへロード指示: {ov.student_name}")
                    slot.view.load(QUrl(direct_url))
            else:
                err = data.get("error", "ボタンクリックに失敗しました") if data else "JS結果が無効です"
                self.logger.debug(f"生徒 {ov.student_id} 行探索: {err}")
                self.handle_slot_failure(slot, err)

        self.web_view.page().runJavaScript(js_click_code, on_js_result)

    def _on_navigation_intercepted(self, url: QUrl):
        """一覧画面からの画面遷移を阻止し、待機中またはディスパッチ中のスロットへルーティング"""
        slot = self._active_dispatch_slot
        if slot and slot.is_busy:
            self.logger.debug(f"ナビゲーションを傍受しスロット {slot.slot_idx} へルーティング: {url.toString()[:40]}")
            slot.view.load(url)
            self._active_dispatch_slot = None

    def handle_slot_success(self, slot: WorkerSlot, html: str):
        """スロットでHTML取得成功時の処理"""
        ov = slot.current_overview
        if not ov:
            return

        self._completed_count += 1
        self._save_and_emit(ov, html)

        self.logger.info(f"[完了 {self._completed_count}/{self._total_count}] {ov.student_name} ({ov.subject}): 解析完了")
        self.tab_activity_updated.emit(slot.slot_idx, f"完了: {ov.student_name}")

        slot.cleanup()

        # 全タスク終了確認
        self._check_all_finished()

        # 後続タスクがあれば待機後にディスパッチ
        if self.is_running and self._queue:
            wait_ms = int(self.request_interval_sec * 1000)
            QTimer.singleShot(wait_ms, self._dispatch_next)

    def handle_slot_failure(self, slot: WorkerSlot, error_msg: str):
        """スロットで取得失敗時の処理（リトライまたはスキップ）"""
        ov = slot.current_overview
        if not ov:
            return

        slot.retry_count += 1
        if slot.retry_count <= self.max_retries and not self._stop_requested:
            self.logger.warning(
                f"[警告] [再試行 {self._completed_count + 1}/{self._total_count}] {ov.student_name} ({ov.subject}): 取得失敗のため再試行します ({slot.retry_count}/{self.max_retries})"
            )
            self.tab_activity_updated.emit(slot.slot_idx, f"再試行待ち: {ov.student_name}")
            slot.timeout_timer.stop()
            slot.render_timer.stop()
            try:
                slot.view.setUrl(QUrl("about:blank"))
            except Exception:
                pass

            wait_ms = int(self.retry_interval_sec * 1000)
            QTimer.singleShot(wait_ms, lambda: self._retry_slot(slot, ov))
        else:
            self.logger.error(
                f"[エラー] [スキップ {self._completed_count + 1}/{self._total_count}] {ov.student_name} ({ov.subject}): 最大リトライ回数超過のためスキップします"
            )
            url_key = ov.detail_url or f"{ov.classroom_code}_{ov.student_id}_{ov.subject}_{ov.row_index}"
            self.repo.update_page_fetch_failed(url_key, error_msg)

            self._completed_count += 1
            self.tab_activity_updated.emit(slot.slot_idx, f"スキップ: {ov.student_name}")
            slot.cleanup()

            self._check_all_finished()

            if self.is_running and self._queue:
                wait_ms = int(self.request_interval_sec * 1000)
                QTimer.singleShot(wait_ms, self._dispatch_next)

    def _retry_slot(self, slot: WorkerSlot, ov: CurriculumOverview):
        if not self.is_running or self._stop_requested:
            slot.cleanup()
            self._check_all_finished()
            return
        slot.start_item(ov, self.timeout_sec)
        self.web_view.set_target_worker_page(slot.view.page())
        self._active_dispatch_slot = slot
        self._click_button_for_overview(ov, slot)

    def _save_and_emit(self, ov: CurriculumOverview, html: str):
        """DB保存とシグナル発行"""
        url_key = ov.detail_url or f"{ov.classroom_code}_{ov.student_id}_{ov.subject}_{ov.row_index}"
        fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.repo.update_page_fetched(url_key, html, fetch_time)

        if self.on_html_fetched:
            self.on_html_fetched(ov, html, fetch_time)
        self.html_fetched.emit(ov, html, fetch_time)

    def _check_all_finished(self):
        """全タスクおよび全スロットの稼働状況を確認して完了判定"""
        busy_slots = [s for s in self.worker_slots if s.is_busy]
        if not self._queue and not busy_slots:
            if self._stop_requested:
                self._finish_crawl(True, f"停止要求により安全に処理を終了しました (処理完了: {self._completed_count}/{self._total_count} 件)")
            else:
                self._finish_crawl(True, f"全 {self._total_count} 件のデータ取得と解析が完了しました")

    def _finish_crawl(self, success: bool, message: str):
        """クローラー終了処理とスロット解放"""
        self._state = CrawlerState.IDLE
        self._stop_requested = False
        self._queue.clear()

        # ナビゲーション傍受解除
        page = self.web_view.page()
        if isinstance(page, CustomWebEnginePage):
            page.intercept_navigation = False

        for slot in self.worker_slots:
            slot.cleanup()

        self.logger.info(message)
        self.crawl_finished.emit(success, message)
