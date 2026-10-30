"""
QtWebEngine 複数タブ並行ワーカー型クローラー (v2.1.0)。
- 二重クリック廃止・FIFOワーカーページルーティングによる別タブ競合根絶
- attempt_id 世代管理による遅延コールバック破棄
- 生徒情報テーブル必須 + ローディング消滅確認による確実なDOM描画待機
- 失敗率に応じた自動スロットル (AdaptiveThrottle) & 指数バックオフ再試行
- セッション切れ (login画面転送) 検知による安全一時停止 (PAUSED_AUTH)
- DBWriter キューへの非同期オフロードによるGUIスレッドブロッキング解消
"""
from collections import Counter, deque
import json
import queue
import random
from enum import Enum, auto
from typing import Dict, List, Optional, Callable
from datetime import datetime
from PySide6.QtCore import QObject, QTimer, Signal, QUrl

from src.browser.web_engine_view import PersistentWebEngineView, CustomWebEnginePage
from src.database.repository import Repository
from src.database.db_writer import FetchedHtmlItem, FetchFailedItem
from src.models.curriculum import CurriculumOverview
from src.parser.lesson_card_parser import LessonCardParser
from src.utils.logger import get_logger
from src.utils.normalization import is_demo_student


class CrawlerState(Enum):
    """クローラーのライフサイクル状態"""
    IDLE = auto()               # 待機中
    RUNNING = auto()            # クロール実行中
    PAUSED_AUTH = auto()        # セッション切れによる再ログイン待機中
    STOPPING = auto()           # 安全停止待機中 (進行中リクエストの保存待ち)


class AdaptiveThrottle:
    """直近の失敗率と連続成功数に応じて並行タブ数とリクエスト間隔を自動調整"""
    def __init__(
        self,
        base_max_tabs: int,
        base_interval_sec: float,
        window_size: int = 10,
        fail_threshold: int = 3,
        recovery_streak: int = 20,
        max_interval_sec: float = 2.0,
    ):
        self.base_max_tabs = max(1, min(4, base_max_tabs))
        self.base_interval_sec = max(0.1, base_interval_sec)
        self.window_size = max(3, window_size)
        self.fail_threshold = max(1, fail_threshold)
        self.recovery_streak = max(5, recovery_streak)
        self.max_interval_sec = max(self.base_interval_sec, max_interval_sec)

        self.active_tabs: int = self.base_max_tabs
        self.current_interval_sec: float = self.base_interval_sec
        self._recent_outcomes: deque[bool] = deque(maxlen=self.window_size)
        self._consecutive_successes: int = 0

    def reset(self):
        self.active_tabs = self.base_max_tabs
        self.current_interval_sec = self.base_interval_sec
        self._recent_outcomes.clear()
        self._consecutive_successes = 0

    def record_success(self) -> Optional[str]:
        """成功を記録し、回復が発生した場合はログメッセージを返す"""
        self._recent_outcomes.append(True)
        self._consecutive_successes += 1

        if (
            self._consecutive_successes >= self.recovery_streak
            and (self.active_tabs < self.base_max_tabs or self.current_interval_sec > self.base_interval_sec)
        ):
            prev_tabs = self.active_tabs
            prev_int = self.current_interval_sec
            self.active_tabs = min(self.base_max_tabs, self.active_tabs + 1)
            self.current_interval_sec = max(
                self.base_interval_sec, round(self.current_interval_sec / 2.0, 2)
            )
            self._consecutive_successes = 0
            if self.active_tabs != prev_tabs or self.current_interval_sec != prev_int:
                return (
                    f"自動スロットル回復: 並行タブ数 {prev_tabs}→{self.active_tabs}, "
                    f"間隔 {prev_int:.2f}s→{self.current_interval_sec:.2f}s"
                )
        return None

    def record_failure(self) -> Optional[str]:
        """失敗を記録し、減速が発生した場合はログメッセージを返す"""
        self._recent_outcomes.append(False)
        self._consecutive_successes = 0

        fail_count = sum(1 for ok in self._recent_outcomes if not ok)
        if fail_count >= self.fail_threshold:
            prev_tabs = self.active_tabs
            prev_int = self.current_interval_sec
            self.active_tabs = max(1, self.active_tabs - 1)
            self.current_interval_sec = min(
                self.max_interval_sec, round(self.current_interval_sec * 2.0, 2)
            )
            self._recent_outcomes.clear()
            if self.active_tabs != prev_tabs or self.current_interval_sec != prev_int:
                return (
                    f"自動スロットル減速 (直近失敗 {fail_count}件): 並行タブ数 {prev_tabs}→{self.active_tabs}, "
                    f"間隔 {prev_int:.2f}s→{self.current_interval_sec:.2f}s"
                )
        return None


_DOM_CHECK_JS = """
JSON.stringify((function() {
    try {
        var href = (window.location && window.location.href) ? window.location.href.toLowerCase() : "";
        var hasPw = Boolean(document.querySelector('input[type="password"]'));
        var isLogin = hasPw || (href.indexOf("login") !== -1);
        var busyEl = document.querySelector('.loading, .spinner, .is-loading, .loading-mask, [aria-busy="true"]');
        var isBusy = false;
        if (busyEl) {
            var st = window.getComputedStyle ? window.getComputedStyle(busyEl) : null;
            isBusy = !st || (st.display !== "none" && st.visibility !== "hidden" && st.opacity !== "0");
        }
        var studentTbl = Boolean(document.querySelector("table.sc2-student-info, table[class*='student-info']"));
        var targetTbl = Boolean(document.querySelector("table.sc2-sim-target, table[class*='sim-target']"));
        var unitTbl = Boolean(document.querySelector("table.is-bordered, table[class*='is-bordered']"));
        var anyTbl = Boolean(document.querySelector("table"));
        return {
            ready: document.readyState === "complete" && !isBusy,
            login: isLogin,
            student: studentTbl,
            target: targetTbl,
            unit: unitTbl,
            anyTable: anyTbl
        };
    } catch (e) {
        return { ready: true, login: false, student: false, target: false, unit: false, anyTable: Boolean(document.querySelector("table")) };
    }
})());
"""


class WorkerSlot:
    """複数タブ運用のための個別ワーカータブ管理スロット (attempt_id 世代管理対応)"""
    POLL_INTERVAL_MS = 80
    OPTIONAL_TABLES_GRACE_POLLS = 6  # 約0.5秒 (80ms * 6)

    def __init__(self, slot_idx: int, view: PersistentWebEngineView, parent_crawler: "WebEngineCrawler"):
        self.slot_idx = slot_idx
        self.view = view
        self.crawler = parent_crawler
        self.is_busy = False
        self.current_overview: Optional[CurriculumOverview] = None
        self.retry_count = 0
        self.attempt_id = 0
        self._student_table_seen_polls = 0

        # タイムアウトタイマー
        self.timeout_timer = QTimer(parent_crawler)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        # DOM描画安定待機タイマー & ポーリング
        self.render_timer = QTimer(parent_crawler)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self._on_render_ready)

        self._poll_attempts = 0
        self._max_poll_attempts = 60
        self._poll_timer = QTimer(parent_crawler)
        self._poll_timer.setSingleShot(True)
        self._poll_timer.timeout.connect(self._check_dom_ready)

        try:
            self.view.loadFinished.connect(self._on_load_finished)
        except Exception:
            pass

    def start_item(self, overview: CurriculumOverview, timeout_sec: float) -> int:
        """生徒のシミュレーションシート取得を開始し、今回の attempt_id を返す"""
        self.attempt_id += 1
        self.is_busy = True
        self.current_overview = overview
        self._poll_attempts = 0
        self._student_table_seen_polls = 0
        self.render_timer.stop()
        self._poll_timer.stop()
        self.timeout_timer.start(int(timeout_sec * 1000))
        return self.attempt_id

    def _on_load_finished(self, ok: bool):
        if not self.is_busy or not self.crawler.is_running:
            return

        current_url = ""
        try:
            u = self.view.url()
            current_url = u.toString() if hasattr(u, "toString") else str(u or "")
        except Exception:
            pass

        if not current_url or current_url == "about:blank":
            return

        active_attempt = self.attempt_id
        self.timeout_timer.stop()

        if "login" in current_url.lower():
            self.crawler.handle_auth_required(self, "ログイン画面への転送を検知しました")
            return

        if not ok:
            self.crawler.handle_slot_failure(
                self, "ページの読み込みに失敗しました (loadFinished=False)", attempt_id=active_attempt
            )
            return

        # 動的DOMのポーリング待機 (最大 sheet_render_max_wait_sec までポーリング)
        self._poll_attempts = 0
        self._student_table_seen_polls = 0
        max_wait_ms = max(
            int(self.crawler.sheet_render_delay_sec * 1000),
            int(getattr(self.crawler, "sheet_render_max_wait_sec", 5.0) * 1000),
        )
        self._max_poll_attempts = max(4, int(max_wait_ms / self.POLL_INTERVAL_MS))
        self._check_dom_ready()

    def _check_dom_ready(self):
        if not self.is_busy or not self.crawler.is_running:
            return

        expected_attempt = self.attempt_id

        def on_check_result(res):
            if not self.is_busy or not self.crawler.is_running or self.attempt_id != expected_attempt:
                return

            # 単体テスト等で boolean が返された場合の互換ハンドリング
            if isinstance(res, bool):
                if res or self._poll_attempts >= self._max_poll_attempts:
                    self._on_render_ready(expected_attempt)
                else:
                    self._poll_attempts += 1
                    self._poll_timer.start(self.POLL_INTERVAL_MS)
                return

            data = None
            if isinstance(res, str):
                try:
                    data = json.loads(res)
                except Exception:
                    data = None
            elif isinstance(res, dict):
                data = res

            if not isinstance(data, dict):
                self._on_render_ready(expected_attempt)
                return

            if data.get("login"):
                self.crawler.handle_auth_required(self, "シミュレーションシート画面でセッション切れを検知しました")
                return

            is_ready = bool(data.get("ready"))
            has_student = bool(data.get("student"))
            has_target = bool(data.get("target"))
            has_unit = bool(data.get("unit"))

            if is_ready and has_student:
                if has_target and has_unit:
                    # 全テーブル描画完了 -> 即座にHTML抽出へ
                    self._on_render_ready(expected_attempt)
                    return
                # 生徒情報表はあるがターゲット表または単元表がまだ無い場合、約0.5秒(6回)待ってから保存
                self._student_table_seen_polls += 1
                if self._student_table_seen_polls >= self.OPTIONAL_TABLES_GRACE_POLLS:
                    self._on_render_ready(expected_attempt)
                    return

            self._poll_attempts += 1
            if self._poll_attempts >= self._max_poll_attempts:
                if has_student:
                    self._on_render_ready(expected_attempt)
                else:
                    self.crawler.handle_slot_failure(
                        self,
                        "生徒情報テーブル (sc2-student-info) の描画を確認できませんでした",
                        attempt_id=expected_attempt,
                    )
            else:
                self._poll_timer.start(self.POLL_INTERVAL_MS)

        page = self.view.page() if hasattr(self.view, "page") else None
        if page and hasattr(page, "runJavaScript"):
            page.runJavaScript(_DOM_CHECK_JS, on_check_result)
        else:
            self._on_render_ready(expected_attempt)

    def _on_render_ready(self, expected_attempt: Optional[int] = None):
        if not self.is_busy or not self.crawler.is_running:
            return
        active_attempt = self.attempt_id if expected_attempt is None else expected_attempt
        if active_attempt != self.attempt_id:
            return

        ov = self.current_overview

        def on_html(html: str):
            if not self.is_busy or not self.crawler.is_running or self.attempt_id != active_attempt:
                return
            if not html or len(html) < 200:
                self.crawler.handle_slot_failure(
                    self, "取得されたHTMLが空または短すぎます", attempt_id=active_attempt
                )
                return

            self.crawler.handle_slot_success(self, html, attempt_id=active_attempt)

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
        if not page:
            self.crawler.handle_slot_failure(
                self, "ページオブジェクトが無効です", attempt_id=active_attempt
            )
            return

        def proceed_to_serialize():
            if not self.is_busy or not self.crawler.is_running or self.attempt_id != active_attempt:
                return
            if hasattr(page, "runJavaScript"):
                page.runJavaScript(sync_checkbox_js, lambda _: page.toHtml(on_html))
            elif hasattr(page, "toHtml"):
                page.toHtml(on_html)
            else:
                self.crawler.handle_slot_failure(
                    self, "ページオブジェクトが無効です", attempt_id=active_attempt
                )

        # 既に同生徒の教室名が判明している場合は追加通信なしで即時適用
        if ov and ov.student_id:
            s_id = ov.student_id
            if s_id in self.crawler.student_classrooms:
                ov.classroom_name = self.crawler.student_classrooms[s_id]
                proceed_to_serialize()
                return

        # 最初に見つかった1件の学習カード(lesson_card_id)から教室名を取得
        fetch_card_js = r"""
        (async function() {
            try {
                let cardId = null;
                // 1. スクリプトタグ内の JSON から探索
                let scripts = document.querySelectorAll('script');
                for (let i = 0; i < scripts.length; i++) {
                    let m = scripts[i].textContent.match(/"lesson_card_id"\s*:\s*([0-9]+)/);
                    if (m && m[1] && m[1] !== "0") {
                        cardId = m[1];
                        break;
                    }
                }
                // 2. cardId があれば非同期 fetch で学習カードHTMLを取得
                if (cardId) {
                    let resp = await fetch('/scube2/student/card?lessonCardId=' + cardId, { credentials: 'include' });
                    if (resp.ok) {
                        let text = await resp.text();
                        return { found: true, cardId: cardId, cardHtml: text };
                    }
                }
                return { found: false, cardId: null, cardHtml: "" };
            } catch (e) {
                return { found: false, error: e.toString() };
            }
        })();
        """

        def on_card_result(res):
            if not self.is_busy or not self.crawler.is_running or self.attempt_id != active_attempt:
                return
            if isinstance(res, dict) and res.get("found") and res.get("cardHtml"):
                card_html = res["cardHtml"]
                cr_name = self.crawler.lesson_card_parser.parse_classroom_name(card_html)
                if cr_name and ov:
                    self.crawler.student_classrooms[ov.student_id] = cr_name
                    ov.classroom_name = cr_name
                    self.crawler.logger.info(f"学習カードより教室名取得: {cr_name} (生徒: {ov.student_name})")

            proceed_to_serialize()

        if hasattr(page, "runJavaScript"):
            page.runJavaScript(fetch_card_js, on_card_result)
        else:
            proceed_to_serialize()

    def _on_timeout(self):
        if not self.is_busy or not self.crawler.is_running:
            return
        active_attempt = self.attempt_id
        self.render_timer.stop()
        self._poll_timer.stop()
        self.crawler.handle_slot_failure(
            self,
            f"取得タイムアウト ({self.crawler.timeout_sec}秒超過)",
            attempt_id=active_attempt,
        )

    def stop_timers_only(self):
        """タイマーのみ停止"""
        self.timeout_timer.stop()
        self.render_timer.stop()
        self._poll_timer.stop()

    def cleanup(self):
        """タイマー停止と状態リセット"""
        self.attempt_id += 1
        self.stop_timers_only()
        self.is_busy = False
        self.current_overview = None
        self.retry_count = 0
        self._student_table_seen_polls = 0
        try:
            if hasattr(self.crawler.web_view, "remove_target_worker_page"):
                self.crawler.web_view.remove_target_worker_page(self.view.page())
        except Exception:
            pass
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
    auth_required = Signal(str)                  # セッション切れ通知 (D-6)

    def __init__(
        self,
        web_view: PersistentWebEngineView,
        repository: Repository,
        tab_views: Optional[List[PersistentWebEngineView]] = None,
        max_tabs: int = 2,
        request_interval_sec: float = 0.5,
        sheet_render_delay_sec: float = 0.8,
        sheet_render_max_wait_sec: float = 5.0,
        max_retries: int = 3,
        retry_interval_sec: float = 2.0,
        timeout_sec: float = 15.0,
        save_queue: Optional[queue.Queue] = None,
        on_html_fetched: Optional[Callable[[CurriculumOverview, str, str], None]] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.web_view = web_view
        self.repo = repository
        self.save_queue = save_queue
        self.max_tabs = max(1, min(4, max_tabs))
        self.request_interval_sec = max(0.1, request_interval_sec)
        self.sheet_render_delay_sec = max(0.1, sheet_render_delay_sec)
        self.sheet_render_max_wait_sec = max(0.5, sheet_render_max_wait_sec)
        self.max_retries = max_retries
        self.retry_interval_sec = max(0.1, retry_interval_sec)
        self.timeout_sec = max(5.0, timeout_sec)
        self.on_html_fetched = on_html_fetched
        self.on_progress = on_progress
        self.logger = get_logger()
        self.student_classrooms: dict[str, str] = {}
        self.lesson_card_parser = LessonCardParser()

        # 自動スロットル (D-5)
        self.throttle = AdaptiveThrottle(
            base_max_tabs=self.max_tabs,
            base_interval_sec=self.request_interval_sec,
        )

        self.target_overviews: List[CurriculumOverview] = []
        self._queue: List[CurriculumOverview] = []
        self._occurrence_map: Dict[int, int] = {}
        self._retry_reasons: Counter = Counter()
        self._total_retries_triggered: int = 0
        self._total_count: int = 0
        self._completed_count: int = 0
        self._state: CrawlerState = CrawlerState.IDLE
        self._stop_requested: bool = False

        # ワーカータブスロット
        self.worker_slots: List[WorkerSlot] = []
        self._created_views: List[PersistentWebEngineView] = []
        self._pending_route_slots: deque[WorkerSlot] = deque()
        self._active_dispatch_slot: Optional[WorkerSlot] = None

        if tab_views:
            for idx, tv in enumerate(tab_views):
                self.worker_slots.append(WorkerSlot(idx, tv, self))
        else:
            for idx in range(self.max_tabs):
                tv = self.web_view.create_tab_view(parent=self, disable_images=True)
                self._created_views.append(tv)
                self.worker_slots.append(WorkerSlot(idx, tv, self))

        # ナビゲーション傍受接続（一覧画面の誤遷移を防止）
        page = self.web_view.page()
        if isinstance(page, CustomWebEnginePage):
            page.navigation_intercepted.connect(self._on_navigation_intercepted)

        if hasattr(self.web_view, "worker_page_routed"):
            try:
                self.web_view.worker_page_routed.connect(self._on_worker_page_routed)
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._state in (CrawlerState.RUNNING, CrawlerState.STOPPING)

    @property
    def state(self) -> CrawlerState:
        return self._state

    def _precompute_occurrences(self, overviews: List[CurriculumOverview]):
        """同一 (student_id, division, subject) が一覧内で何番目に出現するかを O(N) で事前計算"""
        self._occurrence_map.clear()
        seen_counts: Dict[tuple, int] = {}
        for ov in overviews:
            k = (ov.student_id or "", ov.division or "", ov.subject or "")
            idx = seen_counts.get(k, 0)
            self._occurrence_map[id(ov)] = idx
            seen_counts[k] = idx + 1

    def start_crawl(self, target_overviews: List[CurriculumOverview]):
        """クローラーを開始する"""
        target_overviews = [ov for ov in target_overviews if not is_demo_student(ov.student_name)]
        if not target_overviews:
            self.logger.info("取得対象カリキュラムが0件です")
            self.crawl_finished.emit(True, "処理対象カリキュラムがありません")
            return

        self.target_overviews = list(target_overviews)
        self._queue = list(target_overviews)
        self._precompute_occurrences(self.target_overviews)
        self._retry_reasons.clear()
        self._total_retries_triggered = 0
        self._pending_route_slots.clear()
        self._active_dispatch_slot = None
        self.throttle.reset()

        self._total_count = len(target_overviews)
        self._completed_count = 0
        self._stop_requested = False
        self._state = CrawlerState.RUNNING

        # 一覧画面の誤遷移をインターセプト有効化
        page = self.web_view.page()
        if isinstance(page, CustomWebEnginePage):
            page.intercept_navigation = True

        self.logger.info(f"カリキュラム取得開始: 対象 {self._total_count} 件 (並行タブ数: {len(self.worker_slots)})")

        # 最初のタスクをディスパッチ
        self._dispatch_next()

    def stop(self):
        """安全停止要求（進行中のタブのHTML保存を待って終了）"""
        if self._state in (CrawlerState.RUNNING, CrawlerState.PAUSED_AUTH):
            was_paused = (self._state == CrawlerState.PAUSED_AUTH)
            self._stop_requested = True
            self._state = CrawlerState.STOPPING
            self._queue.clear()
            self._pending_route_slots.clear()
            self.logger.info("クローラーに停止要求が送信されました。進行中の取得完了を待機しています...")
            self.status_message_updated.emit("停止処理中: 現在の生徒の保存完了を待機しています...")

            busy_slots = [s for s in self.worker_slots if s.is_busy]
            if not busy_slots or was_paused:
                self._finish_crawl(True, "ユーザーにより安全に停止されました")

    def handle_auth_required(self, slot: WorkerSlot, reason: str):
        """セッション切れ検知時にクロールを一時停止し、再ログイン要求シグナルを発行 (D-6)"""
        if self._state != CrawlerState.RUNNING:
            return

        self._state = CrawlerState.PAUSED_AUTH
        self._pending_route_slots.clear()
        self._active_dispatch_slot = None

        # 一覧画面のナビゲーション傍受を解除してユーザーが再ログイン操作できるようにする
        page = self.web_view.page()
        if isinstance(page, CustomWebEnginePage):
            page.intercept_navigation = False

        # 進行中だったスロットの生徒をキュー先頭に戻し、スロットをクリーンアップ
        requeued: List[CurriculumOverview] = []
        for s in self.worker_slots:
            if s.is_busy and s.current_overview is not None:
                requeued.append(s.current_overview)
            s.cleanup()
        self._queue = requeued + self._queue

        self.logger.warning(f"[一時停止] セッション切れを検知しました ({reason})。再ログイン後に再開してください。")
        self.status_message_updated.emit("一時停止中: セッション切れを検知しました。再ログイン後に再開してください。")
        self.auth_required.emit(reason)

    def _dispatch_next(self):
        """空いているワーカースロットへ順番にタスクを投入 (AdaptiveThrottle の active_tabs 上限を遵守)"""
        if self._state != CrawlerState.RUNNING or self._stop_requested:
            self._check_all_finished()
            return

        busy_count = sum(1 for s in self.worker_slots if s.is_busy)
        if busy_count >= self.throttle.active_tabs:
            return

        target_slot = None
        for slot in self.worker_slots:
            if not slot.is_busy:
                target_slot = slot
                break

        if target_slot and self._queue:
            ov = self._queue.pop(0)
            self._assign_item_to_slot(target_slot, ov)

            new_busy_count = sum(1 for s in self.worker_slots if s.is_busy)
            if new_busy_count < self.throttle.active_tabs and self._queue and not self._stop_requested:
                stagger_ms = max(120, int(self.throttle.current_interval_sec * 1000))
                QTimer.singleShot(stagger_ms, self._dispatch_next)

        self._check_all_finished()

    def _assign_item_to_slot(self, slot: WorkerSlot, ov: CurriculumOverview):
        """1件の生徒アイテムを特定のスロットに割り当てて取得開始"""
        slot.retry_count = 0
        attempt_id = slot.start_item(ov, self.timeout_sec)

        current_idx = self._total_count - len(self._queue)
        msg_header = f"[着手 {current_idx}/{self._total_count}] {ov.student_name} ({ov.subject})"
        self.logger.info(f"{msg_header}: シミュレーションシート取得中...")
        self.status_message_updated.emit(f"取得中 ({current_idx}/{self._total_count} 件): {ov.student_name} ({ov.subject})")
        self.progress_updated.emit(self._completed_count + 1, self._total_count)
        if self.on_progress:
            self.on_progress(self._completed_count + 1, self._total_count, ov.student_name)

        self.tab_activity_updated.emit(slot.slot_idx, f"取得中: {ov.student_name}")

        # FIFOルーティング予約に登録
        self._enqueue_slot_for_routing(slot)

        # 一覧画面上の該当生徒行のボタンをクリックするJavaScriptを実行
        self._click_button_for_overview(ov, slot, attempt_id)

    def _enqueue_slot_for_routing(self, slot: WorkerSlot):
        if slot not in self._pending_route_slots:
            self._pending_route_slots.append(slot)
        self._active_dispatch_slot = self._pending_route_slots[0]
        self.web_view.set_target_worker_page(slot.view.page())

    def _remove_slot_from_routing(self, slot: WorkerSlot):
        try:
            self._pending_route_slots.remove(slot)
        except ValueError:
            pass
        if hasattr(self.web_view, "remove_target_worker_page"):
            try:
                self.web_view.remove_target_worker_page(slot.view.page())
            except Exception:
                pass
        self._active_dispatch_slot = self._pending_route_slots[0] if self._pending_route_slots else None

    def _on_worker_page_routed(self, page_obj):
        """createWindow でワーカーページが消費された際にルーティング待ちキューを更新"""
        for s in list(self._pending_route_slots):
            if s.view.page() == page_obj:
                try:
                    self._pending_route_slots.remove(s)
                except ValueError:
                    pass
                break
        self._active_dispatch_slot = self._pending_route_slots[0] if self._pending_route_slots else None

    def _click_button_for_overview(self, ov: CurriculumOverview, slot: WorkerSlot, expected_attempt: Optional[int] = None):
        """一覧画面上で該当生徒行の「シミュレーションシート」ボタンをクリック (単一クリック・textContent高速照合)"""
        active_attempt = slot.attempt_id if expected_attempt is None else expected_attempt

        occurrence_idx = self._occurrence_map.get(id(ov))
        if occurrence_idx is None:
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

                var allRows = document.querySelectorAll("table tbody tr, tr");
                var matchedRows = [];

                for (var i = 0; i < allRows.length; i++) {{
                    var txt = allRows[i].textContent || "";
                    var matchId = !studentId || txt.indexOf(studentId) !== -1;
                    var matchDiv = !division || txt.indexOf(division) !== -1;
                    var matchSub = !subject || txt.indexOf(subject) !== -1;

                    if (matchId && matchDiv && matchSub) {{
                        matchedRows.push(allRows[i]);
                    }}
                }}

                if (matchedRows.length === 0 && studentName) {{
                    for (var i = 0; i < allRows.length; i++) {{
                        var txt = allRows[i].textContent || "";
                        if (txt.indexOf(studentName) !== -1 &&
                            (!division || txt.indexOf(division) !== -1) &&
                            (!subject || txt.indexOf(subject) !== -1)) {{
                            matchedRows.push(allRows[i]);
                        }}
                    }}
                }}

                if (matchedRows.length === 0 && studentId && subject) {{
                    for (var i = 0; i < allRows.length; i++) {{
                        var txt = allRows[i].textContent || "";
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
                    var bText = (allButtons[b].textContent || allButtons[b].value || "").replace(/\\s+/g, "");
                    if (bText.indexOf("シミュレーションシート") !== -1 || bText.indexOf("シミュレーション") !== -1) {{
                        btn = allButtons[b];
                        break;
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

                var linkUrl = "";
                if (btn.tagName.toLowerCase() === "a" && btn.href) {{
                    linkUrl = btn.href;
                }} else {{
                    var parentA = btn.closest("a");
                    if (parentA && parentA.href) {{
                        linkUrl = parentA.href;
                    }}
                }}

                // 単一クリックのみ実行 (dispatchEvent との二重発火によるロード中断・孤児ページ生成を防止)
                btn.click();

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
            if not self.is_running or not slot.is_busy or slot.attempt_id != active_attempt:
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
                    self._remove_slot_from_routing(slot)
                    slot.view.load(QUrl(direct_url))
            else:
                self._remove_slot_from_routing(slot)
                err = data.get("error", "ボタンクリックに失敗しました") if data else "JS結果が無効です"
                self.logger.debug(f"生徒 {ov.student_id} 行探索: {err}")
                self.handle_slot_failure(slot, err, attempt_id=active_attempt)

        self.web_view.page().runJavaScript(js_click_code, on_js_result)

    def _on_navigation_intercepted(self, url: QUrl):
        """一覧画面からの画面遷移を阻止し、待機中またはディスパッチ中のスロットへFIFOルーティング"""
        slot = self._pending_route_slots.popleft() if self._pending_route_slots else self._active_dispatch_slot
        self._active_dispatch_slot = self._pending_route_slots[0] if self._pending_route_slots else None
        if slot and slot.is_busy:
            if hasattr(self.web_view, "remove_target_worker_page"):
                try:
                    self.web_view.remove_target_worker_page(slot.view.page())
                except Exception:
                    pass
            self.logger.debug(f"ナビゲーションを傍受しスロット {slot.slot_idx} へルーティング: {url.toString()[:40]}")
            slot.view.load(url)

    def handle_slot_success(self, slot: WorkerSlot, html: str, attempt_id: Optional[int] = None):
        """スロットでHTML取得成功時の処理"""
        if attempt_id is not None and attempt_id != slot.attempt_id:
            return
        ov = slot.current_overview
        if not ov:
            return

        self._remove_slot_from_routing(slot)
        self._completed_count += 1
        self._save_and_emit(ov, html)

        throttle_msg = self.throttle.record_success()
        if throttle_msg:
            self.logger.info(throttle_msg)

        self.logger.info(f"[完了 {self._completed_count}/{self._total_count}] {ov.student_name} ({ov.subject}): 解析完了")
        self.tab_activity_updated.emit(slot.slot_idx, f"完了: {ov.student_name}")

        slot.cleanup()

        # 全タスク終了確認
        self._check_all_finished()

        # 後続タスクがあれば待機後にディスパッチ
        if self._state == CrawlerState.RUNNING and self._queue:
            wait_ms = int(self.throttle.current_interval_sec * 1000)
            QTimer.singleShot(wait_ms, self._dispatch_next)

    def handle_slot_failure(self, slot: WorkerSlot, error_msg: str, attempt_id: Optional[int] = None):
        """スロットで取得失敗時の処理（指数バックオフ再試行またはスキップ）"""
        if attempt_id is not None and attempt_id != slot.attempt_id:
            return
        ov = slot.current_overview
        if not ov:
            return

        self._remove_slot_from_routing(slot)
        reason_key = error_msg or "不明なエラー"
        self._retry_reasons[reason_key] += 1

        throttle_msg = self.throttle.record_failure()
        if throttle_msg:
            self.logger.warning(throttle_msg)

        slot.retry_count += 1
        if slot.retry_count <= self.max_retries and not self._stop_requested:
            self._total_retries_triggered += 1
            self.logger.warning(
                f"[警告] [再試行 {self._completed_count + 1}/{self._total_count}] "
                f"{ov.student_name} ({ov.subject}) [タブ{slot.slot_idx + 1}]: "
                f"取得失敗のため再試行します ({slot.retry_count}/{self.max_retries}) - 原因: {reason_key}"
            )
            self.tab_activity_updated.emit(slot.slot_idx, f"再試行待ち: {ov.student_name}")
            slot.stop_timers_only()
            # 進行中だった遅延コールバックを無効化するため attempt_id を進める
            slot.attempt_id += 1
            retry_token = slot.attempt_id
            try:
                slot.view.setUrl(QUrl("about:blank"))
            except Exception:
                pass

            # 指数バックオフ + ジッター (retry_interval * 2^(n-1) * 0.85..1.15, 上限15秒)
            backoff_sec = min(15.0, self.retry_interval_sec * (2 ** (slot.retry_count - 1)))
            jitter = random.uniform(0.85, 1.15)
            wait_ms = max(50, int(backoff_sec * jitter * 1000))
            QTimer.singleShot(wait_ms, lambda: self._retry_slot(slot, ov, retry_token))
        else:
            self.logger.error(
                f"[エラー] [スキップ {self._completed_count + 1}/{self._total_count}] "
                f"{ov.student_name} ({ov.subject}): 最大リトライ回数超過のためスキップします (最終原因: {reason_key})"
            )
            url_key = ov.page_key
            if self.save_queue is not None:
                self.save_queue.put(FetchFailedItem(page_key=url_key, error_message=reason_key))
            else:
                self.repo.update_page_fetch_failed(url_key, reason_key)

            self._completed_count += 1
            self.tab_activity_updated.emit(slot.slot_idx, f"スキップ: {ov.student_name}")
            slot.cleanup()

            self._check_all_finished()

            if self._state == CrawlerState.RUNNING and self._queue:
                wait_ms = int(self.throttle.current_interval_sec * 1000)
                QTimer.singleShot(wait_ms, self._dispatch_next)

    def _retry_slot(self, slot: WorkerSlot, ov: CurriculumOverview, expected_token: Optional[int] = None):
        if self._state != CrawlerState.RUNNING or self._stop_requested:
            if self._state != CrawlerState.PAUSED_AUTH:
                slot.cleanup()
                self._check_all_finished()
            return
        if expected_token is not None and slot.attempt_id != expected_token:
            return
        attempt_id = slot.start_item(ov, self.timeout_sec)
        self._enqueue_slot_for_routing(slot)
        self._click_button_for_overview(ov, slot, attempt_id)

    def _save_and_emit(self, ov: CurriculumOverview, html: str):
        """DB保存とシグナル発行 (save_queue 指定時はGUIスレッドのDB書き込みをゼロ化)"""
        url_key = ov.page_key
        fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.save_queue is not None:
            self.save_queue.put(FetchedHtmlItem(page_key=url_key, html=html, fetch_time=fetch_time))
        else:
            self.repo.update_page_fetched(url_key, html, fetch_time)

        if self.on_html_fetched:
            self.on_html_fetched(ov, html, fetch_time)
        self.html_fetched.emit(ov, html, fetch_time)

    def _check_all_finished(self):
        """全タスクおよび全スロットの稼働状況を確認して完了判定"""
        if self._state == CrawlerState.PAUSED_AUTH:
            return
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
        self._pending_route_slots.clear()
        self._active_dispatch_slot = None

        page = self.web_view.page()
        if isinstance(page, CustomWebEnginePage):
            page.intercept_navigation = False

        for slot in self.worker_slots:
            slot.cleanup()

        if self._total_retries_triggered > 0:
            breakdown = ", ".join(f"{k}: {v}回" for k, v in self._retry_reasons.most_common(5))
            self.logger.info(f"再試行サマリー: 総発生 {self._total_retries_triggered} 回 ({breakdown})")

        self.logger.info(message)
        self.crawl_finished.emit(success, message)
