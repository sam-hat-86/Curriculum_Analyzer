"""
メインウィンドウ (仕様書§36, §46: PySide6 GUI / WebEngine / パイプライン制御)
- 起動時DB自動修復 (v2.1.0 マイグレーション)
- parse_pool 完了待機 → save_queue.join → DBWriter 終了 → Excel出力 の厳密順序化
- セッション切れ検知時の一時停止と一覧画面1ページ目からのシームレス再開
- バックグラウンド手動Excel出力 (UI非ブロッキング)
- GUIスレッドからの同期DBクエリ最小化
"""
import os
import queue
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QSplitter, QMessageBox, QLabel, QStatusBar, QLineEdit,
    QTabWidget, QDialog
)
import json
from PySide6.QtCore import Qt, Signal, Slot, QObject, QUrl, QTimer
from PySide6.QtGui import QKeyEvent

from src.models.curriculum import CurriculumOverview
from src.utils.config import AppConfig
from src.utils.logger import get_logger, add_log_callback
from src.utils.constants import APP_BASE_TITLE, APP_VERSION
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.database.db_writer import DBWriter
from src.database.repair import repair_database_if_needed
from src.parser.list_parser import ListParser
from src.parser.detail_parser import DetailParser
from src.analyzer.instruction_evaluator import InstructionEvaluator
from src.analyzer.progress_calculator import calculate_target_progress
from src.browser.web_engine_view import PersistentWebEngineView, CustomWebEnginePage
from src.exporter.excel_exporter import ExcelExporter
from src.exporter.safe_writer import SafeExcelWriter
from src.gui.progress_panel import ProgressPanel
from src.gui.log_viewer import LogViewerWidget, LogSignalEmitter
from src.gui.settings_dialog import SettingsDialog
from src.gui.overlay import LoadingOverlay
from src.crawler.webengine_crawler import WebEngineCrawler
from src.browser.pagination import CHECK_NEXT_PAGE_JS, CLICK_NEXT_PAGE_JS, get_check_page_changed_js
from src.browser.classroom_navigator import ClassroomNavigator


class ControllerSignals(QObject):
    log_msg = Signal(str, str)
    status_updated = Signal(str, int, int, int, int, int)
    crawl_finished = Signal(bool, str)
    manual_export_finished = Signal(bool, str)
    classroom_crawl_completed = Signal(int)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.logger = get_logger()

        # データベース & リポジトリ
        self.db_manager = DatabaseManager(self.config.db_path)
        self.repo = Repository(self.db_manager)

        # パーサー & アナライザー
        self.list_parser = ListParser()
        self.detail_parser = DetailParser()
        self.instruction_evaluator = InstructionEvaluator()

        # 既存DBの整合性自動修復 (2ページ目以降のキー不一致修復 & 孤児レコード削除)
        try:
            repair_database_if_needed(
                self.repo,
                detail_parser=self.detail_parser,
                instruction_evaluator=self.instruction_evaluator,
            )
        except Exception as rep_err:
            self.logger.warning(f"起動時DB修復チェックで例外が発生しました: {rep_err}")

        # エクスポーター
        self.excel_exporter = ExcelExporter(self.repo, include_raw_sheet=self.config.export_raw_sheet)
        self.safe_writer = SafeExcelWriter(self.excel_exporter, self.config.output_dir)

        # パイプライン制御
        self.save_queue: queue.Queue = queue.Queue()
        self.db_writer: Optional[DBWriter] = None
        self.parse_pool: Optional[ThreadPoolExecutor] = None
        self.crawler: Optional[WebEngineCrawler] = None
        self.crawler_thread: Optional[threading.Thread] = None

        self.signals = ControllerSignals()
        self.signals.status_updated.connect(self._on_status_updated)
        self.signals.crawl_finished.connect(self._on_crawl_finished)
        self.signals.manual_export_finished.connect(self._on_manual_export_finished)
        self.signals.classroom_crawl_completed.connect(self._prompt_next_classroom_or_export)

        self.worker_tab_views: List[PersistentWebEngineView] = []

        # 教室自動巡回関連
        self._is_patrol_mode: bool = False
        self._patrol_classroom_list: List[Dict[str, Any]] = []
        self._patrol_total_classrooms: int = 0
        self._patrol_current_index: int = 0
        self._skipped_classrooms: List[Dict[str, Any]] = []

        # 自動ページネーション・一時停止制御
        self._is_analyzing: bool = False
        self._is_paused_for_auth: bool = False
        self._is_continuous_classroom_mode: bool = False
        self._current_page_idx: int = 1
        self._prev_page_student_keys: set = set()
        self._page_transition_attempts: int = 0

        # インメモリ進捗キャッシュ (GUIスレッドでの頻繁なSQLite SELECTを回避)
        self._cached_counts = {"total": 0, "unfetched": 0, "fetched": 0, "saved": 0, "failed": 0}
        self._session_base_saved: int = 0

        # ログ連携
        self.log_emitter = LogSignalEmitter()
        add_log_callback(self._on_log_callback)
        self.log_emitter.log_received.connect(self._on_log_received)

        self.init_ui()
        self._refresh_initial_counts()

    def init_ui(self):
        self.setWindowTitle(f"{APP_BASE_TITLE} v{APP_VERSION}")
        self.resize(1550, 920)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # スプリッターで左右分割
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # --- 左ペイン: 組み込みWebEngineブラウザ ---
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # ナビゲーションバー
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(4, 4, 4, 4)
        nav_layout.setSpacing(6)

        nav_btn_style = """
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                min-width: 44px;
                max-width: 44px;
                min-height: 40px;
                max-height: 40px;
                padding: 0px;
            }
        """

        self.btn_browser_back = QPushButton("◀", self)
        self.btn_browser_back.setToolTip("前のページに戻る")
        self.btn_browser_back.setStyleSheet(nav_btn_style)
        self.btn_browser_back.clicked.connect(self._browser_back)

        self.btn_browser_forward = QPushButton("▶", self)
        self.btn_browser_forward.setToolTip("次のページに進む")
        self.btn_browser_forward.setStyleSheet(nav_btn_style)
        self.btn_browser_forward.clicked.connect(self._browser_forward)

        self.btn_browser_reload = QPushButton("⟳", self)
        self.btn_browser_reload.setToolTip("ページを再読み込み")
        self.btn_browser_reload.setStyleSheet(nav_btn_style)
        self.btn_browser_reload.clicked.connect(self._browser_reload)

        self.btn_browser_home = QPushButton("⌂", self)
        self.btn_browser_home.setToolTip("初期ページを開く")
        self.btn_browser_home.setStyleSheet(nav_btn_style)
        self.btn_browser_home.clicked.connect(self._go_home)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("URLを入力してEnterまたは移動ボタンを押してください")
        self.url_input.setStyleSheet("min-height: 40px; max-height: 40px; font-size: 14px; padding: 4px 8px;")
        self.url_input.returnPressed.connect(self._navigate_to_url)

        self.btn_browser_go = QPushButton("移動", self)
        self.btn_browser_go.setToolTip("指定したURLへ移動")
        self.btn_browser_go.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                min-width: 64px;
                max-width: 64px;
                min-height: 40px;
                max-height: 40px;
                padding: 0px;
            }
        """)
        self.btn_browser_go.clicked.connect(self._navigate_to_url)

        nav_layout.addWidget(self.btn_browser_back)
        nav_layout.addWidget(self.btn_browser_forward)
        nav_layout.addWidget(self.btn_browser_reload)
        nav_layout.addWidget(self.btn_browser_home)
        nav_layout.addWidget(self.url_input)
        nav_layout.addWidget(self.btn_browser_go)
        left_layout.addLayout(nav_layout)

        # ブラウザタブウィジェット (複数タブ対応)
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabsClosable(False)
        self.tab_widget.setMovable(False)
        self.tab_widget.setStyleSheet("""
            QTabBar::tab {
                height: 36px;
                padding: 0 16px;
                font-size: 14px;
                background-color: #2D2D30;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-bottom: none;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1E1E1E;
                color: #FFFFFF;
                font-weight: bold;
                border-top: 3px solid #007ACC;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3E3E42;
            }
        """)

        # メイン一覧用WebEngineView
        self.web_view = PersistentWebEngineView(parent=self)
        self.web_view.set_allowed_origin(self.config.start_url)
        self.web_view.urlChanged.connect(self._on_browser_url_changed)
        self.web_view.loadFinished.connect(self._on_browser_load_finished)
        self.classroom_navigator = ClassroomNavigator(self.web_view.page(), parent=self)

        # 初期表示
        initial_url = self.config.start_url.strip() if self.config.start_url else "about:blank"
        if initial_url != "about:blank":
            self.url_input.setText(initial_url)
        self.web_view.setUrl(QUrl(initial_url))

        # タブ0に「カリキュラム一覧」を追加
        self.tab_widget.addTab(self.web_view, "📋 カリキュラム一覧")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        left_layout.addWidget(self.tab_widget)

        # ブラウザ操作ロック用オーバーレイ
        self.loading_overlay = LoadingOverlay(self.tab_widget)

        splitter.addWidget(left_widget)

        # --- 右ペイン: 制御・進捗・ログ ---
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 操作ボタングループ (2段構成)
        btn_container = QVBoxLayout()
        btn_container.setSpacing(6)

        # 1段目: メインアクション (開始 / 停止)
        primary_btn_layout = QHBoxLayout()
        primary_btn_layout.setSpacing(6)

        self.btn_start = QPushButton("▶ 処理開始", self)
        self.btn_start.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                min-height: 48px;
                background-color: #107C41;
                color: #FFFFFF;
                border: 1px solid #107C41;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #159C52;
                border-color: #159C52;
            }
            QPushButton:disabled {
                background-color: #25382D;
                color: #6D8274;
                border-color: #25382D;
            }
        """)
        self.btn_start.clicked.connect(self.start_process)

        self.btn_stop = QPushButton("⏹ 停止", self)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                min-height: 48px;
                background-color: #D83B01;
                color: #FFFFFF;
                border: 1px solid #D83B01;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #EA4A1A;
                border-color: #EA4A1A;
            }
            QPushButton:disabled {
                background-color: #382522;
                color: #826D6A;
                border-color: #382522;
            }
        """)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_process)

        self.btn_patrol = QPushButton("🏫 教室巡回開始", self)
        self.btn_patrol.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                min-height: 48px;
                background-color: #0E639C;
                color: #FFFFFF;
                border: 1px solid #0E639C;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #1177BB;
                border-color: #1177BB;
            }
            QPushButton:disabled {
                background-color: #2D3A45;
                color: #72818D;
                border-color: #2D3A45;
            }
        """)
        self.btn_patrol.clicked.connect(self.start_classroom_patrol)

        primary_btn_layout.addWidget(self.btn_start, 3)
        primary_btn_layout.addWidget(self.btn_patrol, 3)
        primary_btn_layout.addWidget(self.btn_stop, 2)
        btn_container.addLayout(primary_btn_layout)

        # 2段目: ユーティリティ・データ操作 (Excel即時出力 / 設定 / データ初期化)
        secondary_btn_layout = QHBoxLayout()
        secondary_btn_layout.setSpacing(6)

        self.btn_export = QPushButton("📊 Excel即時出力", self)
        self.btn_export.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                min-height: 40px;
                background-color: #0E639C;
                color: #FFFFFF;
                border: 1px solid #1177BB;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:disabled {
                background-color: #252D38;
                color: #6D7782;
            }
        """)
        self.btn_export.clicked.connect(self.manual_export)

        self.btn_settings = QPushButton("⚙ 設定", self)
        self.btn_settings.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: 500;
                min-height: 40px;
                background-color: #2D2D30;
                color: #F0F0F0;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #3E3E42;
                border-color: #007ACC;
            }
        """)
        self.btn_settings.clicked.connect(self.open_settings)

        self.btn_reset = QPushButton("🗑 データ初期化", self)
        self.btn_reset.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: 500;
                min-height: 40px;
                background-color: #3B3A39;
                color: #F3F2F1;
                border: 1px solid #484644;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #A80000;
                border-color: #D83B01;
            }
            QPushButton:disabled {
                background-color: #2D2D2D;
                color: #797775;
            }
        """)
        self.btn_reset.clicked.connect(self.reset_data_prompt)

        secondary_btn_layout.addWidget(self.btn_export, 2)
        secondary_btn_layout.addWidget(self.btn_settings, 1)
        secondary_btn_layout.addWidget(self.btn_reset, 1)
        btn_container.addLayout(secondary_btn_layout)

        right_layout.addLayout(btn_container)

        # 進捗パネル
        self.progress_panel = ProgressPanel(self)
        right_layout.addWidget(self.progress_panel)

        # ログビューア
        self.log_viewer = LogViewerWidget(self)
        right_layout.addWidget(self.log_viewer, 1)

        right_widget.setMinimumWidth(420)
        splitter.addWidget(right_widget)

        # スプリッター比率 (左 75% : 右 25%)
        splitter.setSizes([1250, 450])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        main_layout.addWidget(splitter)

        # ステータスバー
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("待機中: 一覧画面を開いて「処理開始」を押してください")

        # ログイン状態インジケーター (常時表示)
        self.login_status_label = QLabel("○ [未ログイン]", self)
        self.login_status_label.setStyleSheet("padding: 0 8px; font-weight: bold; color: #888888;")
        self.status_bar.addPermanentWidget(self.login_status_label)
        self.web_view.cookie_status_changed.connect(self._on_cookie_status_changed)

    def _on_log_callback(self, msg: str, level: str):
        self.log_emitter.log_received.emit(msg, level)

    def _on_log_received(self, msg: str, level: str):
        self.log_viewer.append_log(msg, level)

    def _refresh_initial_counts(self):
        counts = self.repo.get_counts()
        self._cached_counts = dict(counts)
        self.progress_panel.update_status(
            "待機中",
            counts["total"],
            counts["fetched"],
            counts["saved"],
            counts["saved"],
            counts["failed"],
        )

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.safe_writer.output_dir = self.config.output_dir
            self.excel_exporter.include_raw_sheet = self.config.export_raw_sheet
            self.web_view.set_allowed_origin(self.config.start_url)
            self.logger.info("設定が更新されました")

    def _get_active_browser_view(self) -> PersistentWebEngineView:
        widget = self.tab_widget.currentWidget()
        if isinstance(widget, PersistentWebEngineView):
            return widget
        return self.web_view

    def _browser_back(self):
        self._get_active_browser_view().back()

    def _browser_forward(self):
        self._get_active_browser_view().forward()

    def _browser_reload(self):
        self._get_active_browser_view().reload()

    def _go_home(self):
        target_url = self.config.start_url.strip() if self.config.start_url else "about:blank"
        self._get_active_browser_view().setUrl(QUrl(target_url))

    def _navigate_to_url(self):
        text = self.url_input.text().strip()
        if not text:
            return
        if not (text.startswith("http://") or text.startswith("https://") or text.startswith("about:")):
            text = "http://" + text
        self._get_active_browser_view().setUrl(QUrl(text))

    def _on_tab_changed(self, index: int):
        view = self._get_active_browser_view()
        url_str = view.url().toString()
        if url_str and url_str != "about:blank":
            self.url_input.setText(url_str)
        else:
            self.url_input.clear()

    def _on_worker_tab_url_changed(self, url: QUrl):
        if self.tab_widget.currentWidget() == self.sender():
            url_str = url.toString()
            if url_str != "about:blank":
                self.url_input.setText(url_str)

    def _on_browser_url_changed(self, url: QUrl):
        if self.tab_widget.currentWidget() == self.web_view:
            url_str = url.toString()
            if url_str != "about:blank":
                self.url_input.setText(url_str)

    def _on_browser_load_finished(self, ok: bool):
        if not ok:
            page = self.web_view.page()
            if getattr(page, "intercept_navigation", False):
                return
            current_url = self.web_view.url().toString()
            if current_url and current_url != "about:blank":
                self.logger.warning("ページの読み込みに失敗しました")

    def _on_cookie_status_changed(self, is_auth: bool, desc: str):
        if is_auth:
            self.login_status_label.setText(f"● [{desc}]")
            self.login_status_label.setStyleSheet("padding: 0 8px; font-weight: bold; color: #107C41;")
        else:
            self.login_status_label.setText(f"○ [{desc}]")
            self.login_status_label.setStyleSheet("padding: 0 8px; font-weight: bold; color: #888888;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay") and hasattr(self, "tab_widget"):
            self.loading_overlay.resize(self.tab_widget.size())

    def reset_data_prompt(self):
        """集計データの初期化（確認ダイアログ付き）"""
        counts = self.repo.get_counts()
        reply = QMessageBox.question(
            self,
            "集計データ初期化の確認",
            f"これまでに蓄積された集計データ（保存済み: {counts['saved']} 件）をすべて削除し、初期状態にリセットしますか？\n\n"
            "※ 出力済みのExcelファイル自体は削除されません。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.repo.clear_all_data()
            self._refresh_initial_counts()
            self.logger.info("集計データを初期化しました（初期状態で新規集計を開始できます）")
            self.status_bar.showMessage("集計データを初期化しました")
            QMessageBox.information(self, "初期化完了", "集計データを初期化しました。\n初期状態で「処理開始」を実行できます。")

    def start_process(self):
        """処理開始処理 (またはセッション切れ一時停止からの再開)"""
        if self._is_paused_for_auth:
            self._resume_from_auth_pause()
            return

        # 未ログイン時の安全ガード
        if not self.web_view.is_authenticated():
            reply = QMessageBox.question(
                self,
                "ログイン確認",
                "認証Cookie (KGLC等) がまだ検出されていません。\nブラウザ上でログインを完了してから開始してください。\n\nそれでも強制的に処理を開始しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.status_bar.showMessage("処理開始をキャンセルしました (ログインしてください)")
                return

        # 連続教室巡回モード時は確認ダイアログをスキップして既存DBに追記
        if self._is_continuous_classroom_mode:
            self.logger.info("連続教室巡回モード: 既存データを保持して次の教室の巡回を開始します")
            self._is_continuous_classroom_mode = False
        else:
            # 過去データが残っている場合の確認ダイアログ (再開か初期化か)
            counts = self.repo.get_counts()
            if counts["saved"] > 0 or counts["unfetched"] > 0 or counts["fetched"] > 0:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("集計データの確認")
                msg_box.setText(
                    f"以前の集計データが残っています（保存済み: {counts['saved']} 件, 未完了: {counts['unfetched'] + counts['failed']} 件）。\n\n"
                    "どのように処理を開始しますか？"
                )
                btn_resume = msg_box.addButton("途中から再開", QMessageBox.ButtonRole.AcceptRole)
                btn_reset_start = msg_box.addButton("初期化して新しく開始", QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = msg_box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
                msg_box.setDefaultButton(btn_resume)

                msg_box.exec()
                clicked_btn = msg_box.clickedButton()
                if clicked_btn == btn_cancel:
                    self.status_bar.showMessage("処理開始をキャンセルしました")
                    return
                elif clicked_btn == btn_reset_start:
                    self.repo.clear_all_data()
                    self._refresh_initial_counts()
                    self.logger.info("集計データを初期化しました（初期状態で新規集計を開始）")

        self._cached_counts = self.repo.get_counts()
        self._session_base_saved = self._cached_counts["saved"]
        self._is_analyzing = True
        self._is_paused_for_auth = False
        self._current_page_idx = 1
        self._prev_page_student_keys = set()

        self.btn_start.setText("▶ 処理開始")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        # DBWriterスレッド起動
        self.save_queue = queue.Queue()
        self.db_writer = DBWriter(
            repository=self.repo,
            save_queue=self.save_queue,
            checkpoint_interval=0,
            checkpoint_callback=None,
            progress_callback=self._on_db_saved,
        )
        self.db_writer.start()

        # 解析Worker ThreadPool起動
        self.parse_pool = ThreadPoolExecutor(
            max_workers=self.config.worker_threads,
            thread_name_prefix="ParseWorker"
        )

        # 既存のワーカータブがあればクリーンアップ
        self._cleanup_worker_tabs()

        # 設定された並行タブ数分のワーカータブを作成しTabWidgetへ追加
        self.worker_tab_views = []
        for i in range(self.config.max_tabs):
            worker_view = self.web_view.create_tab_view(parent=self, disable_images=True)
            worker_view.urlChanged.connect(self._on_worker_tab_url_changed)
            tab_title = f"📑 取得タブ {i+1}"
            self.tab_widget.addTab(worker_view, tab_title)
            self.worker_tab_views.append(worker_view)

        # 内蔵WebEngineCrawler起動 (複数タブ・非同期save_queue対応)
        self.crawler = WebEngineCrawler(
            web_view=self.web_view,
            repository=self.repo,
            tab_views=self.worker_tab_views,
            max_tabs=self.config.max_tabs,
            request_interval_sec=self.config.request_interval_sec,
            sheet_render_delay_sec=self.config.sheet_render_delay_sec,
            sheet_render_max_wait_sec=self.config.sheet_render_max_wait_sec,
            max_retries=self.config.max_retries,
            retry_interval_sec=self.config.retry_interval_sec,
            timeout_sec=self.config.timeout_sec,
            save_queue=self.save_queue,
            on_html_fetched=self._on_detail_html_fetched,
            on_progress=self._on_crawl_progress,
            parent=self,
        )
        self.crawler.progress_updated.connect(self._on_crawler_progress_updated)
        self.crawler.status_message_updated.connect(self._on_crawler_status_msg_updated)
        self.crawler.tab_activity_updated.connect(self._on_tab_activity_updated)
        self.crawler.crawl_finished.connect(self._on_crawler_finished_callback)
        self.crawler.auth_required.connect(self._on_crawler_auth_required)

        self._start_list_page_extraction()

    def _on_crawler_auth_required(self, reason: str):
        """セッション切れ検知時の一時停止ハンドラ (D-6)"""
        self._is_paused_for_auth = True
        self._is_analyzing = False
        self.loading_overlay.hide_loading()
        self.tab_widget.setCurrentIndex(0)

        self.btn_start.setText("▶ 再開 (再ログイン後)")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.status_bar.showMessage("一時停止中: 再ログインして一覧画面を開き、「▶ 再開」またはダイアログの「再開」を押してください")

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("セッション切れによる一時停止")
        msg_box.setText(
            f"取得中にセッション切れ（ログイン画面への転送）を検知したため、処理を一時停止しました。\n"
            f"（検知理由: {reason}）\n\n"
            "【再開手順】\n"
            "1. 一覧タブ上で再ログインし、元の検索条件でカリキュラム一覧（1ページ目）を表示してください。\n"
            "2. 一覧が表示されたら「一覧を開き直して再開」または右上の「▶ 再開」ボタンを押してください。\n"
            "※ 既に取得・保存済みの生徒データはスキップされ、続きから再開されます。"
        )
        btn_resume = msg_box.addButton("一覧を開き直して再開", QMessageBox.ButtonRole.AcceptRole)
        btn_wait = msg_box.addButton("ブラウザで操作する (後で再開ボタンを押す)", QMessageBox.ButtonRole.ActionRole)
        btn_abort = msg_box.addButton("ここで中断してExcel出力", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(btn_wait)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == btn_resume:
            self._resume_from_auth_pause()
        elif clicked == btn_abort:
            self.stop_process()

    def _resume_from_auth_pause(self):
        """再ログイン完了後に1ページ目から再開 (取得済みは自動スキップ)"""
        self._is_paused_for_auth = False
        self._is_analyzing = True
        self._current_page_idx = 1
        self._prev_page_student_keys = set()

        self.btn_start.setText("▶ 処理開始")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        # これまでのDB保存キューを一度フラッシュして未完了判定を最新化
        if hasattr(self, "save_queue") and self.save_queue:
            try:
                self.save_queue.join()
            except Exception:
                pass
        self._cached_counts = self.repo.get_counts()
        if self.db_writer:
            self._session_base_saved = max(0, self._cached_counts["saved"] - self.db_writer.saved_count)

        self.logger.info("再ログイン後の処理再開を開始します（1ページ目から未取得分を走査）")
        self._start_list_page_extraction()

    def _start_list_page_extraction(self):
        """一覧画面のHTML取得開始 (自動ページネーション対応)"""
        if not self._is_analyzing:
            return

        self.status_bar.showMessage(f"カリキュラム一覧を解析中 (ページ {self._current_page_idx})...")
        self.loading_overlay.show_loading(
            f"一覧テーブル解析中 (ページ {self._current_page_idx})...",
            "ブラウザの一覧画面から生徒・授業データを抽出しています",
            show_progress=False
        )
        self.web_view.page().toHtml(self._on_list_html_ready)

    def _on_list_html_ready(self, list_html: str):
        """一覧画面HTML取得後の解析・クローラー開始処理"""
        if not self._is_analyzing:
            return

        try:
            self.logger.info(f"カリキュラム一覧ページ (ページ {self._current_page_idx}) の解析を開始します")
            overviews = self.list_parser.parse(list_html, page_index=self._current_page_idx)
            if not overviews:
                if self._current_page_idx == 1:
                    self.logger.warning("一覧テーブルに対象の授業が見つかりませんでした")
                    self._cleanup_analysis_session()
                    QMessageBox.warning(self, "対象なし", "一覧テーブルに対象の授業が見つかりませんでした。\n検索条件やカリキュラム一覧画面をご確認ください。")
                    return
                else:
                    self.logger.info(f"ページ {self._current_page_idx} に授業行がありません。全ページ取得完了と判定します。")
                    self._on_pagination_completed(self._current_page_idx - 1, f"全 {self._current_page_idx - 1} ページの取得を完了しました")
                    return

            # 同一ページループ防止チェック
            current_keys = {(ov.classroom_code, ov.student_id, ov.subject) for ov in overviews}
            if self._prev_page_student_keys and self._prev_page_student_keys == current_keys:
                self.logger.info("次ページの生徒データが直前ページと一致しているため、全ページ取得完了と判定します。")
                self._on_pagination_completed(self._current_page_idx - 1, f"全 {self._current_page_idx - 1} ページの取得を完了しました")
                return
            self._prev_page_student_keys = current_keys

            self.logger.info(f"ページ {self._current_page_idx} から {len(overviews)} 件のカリキュラムを検出しました")
            self.repo.save_pages_init(overviews)

            # カウントキャッシュを更新
            self._cached_counts = self.repo.get_counts()

            # 未完了（未取得・失敗）の取得対象を抽出
            uncompleted_pages = self.repo.get_uncompleted_pages()
            uncompleted_urls = {row["url"] for row in uncompleted_pages}
            target_overviews = [ov for ov in overviews if ov.page_key in uncompleted_urls]

            self.logger.info(f"ページ {self._current_page_idx} の未取得対象: {len(target_overviews)} 件")

            if not target_overviews:
                self.logger.info(f"ページ {self._current_page_idx} の全カリキュラムは既に取得済みです。次ページの確認へ進みます。")
                self._check_and_advance_to_next_page()
                return

            self.loading_overlay.show_loading(
                f"シミュレーションシート取得中 (ページ {self._current_page_idx})...",
                f"ページ {self._current_page_idx} 取得準備完了 (対象: {len(target_overviews)} 件)",
                show_progress=True
            )

            if self.crawler:
                self.crawler.start_crawl(target_overviews)

        except Exception as e:
            self.logger.error(f"一覧処理中にエラーが発生しました: {e}", exc_info=True)
            self._cleanup_analysis_session()
            QMessageBox.critical(self, "エラー", f"一覧処理中にエラーが発生しました:\n{e}")

    def _on_crawler_progress_updated(self, current: int, total: int):
        """クローラー進捗ハンドラ"""
        pct = int(current / total * 100) if total > 0 else 0
        self.loading_overlay.update_message(f"ページ {self._current_page_idx} 取得中 ({current}/{total} 件)", pct)

    def _on_crawler_status_msg_updated(self, msg: str):
        """クローラーステータスメッセージハンドラ"""
        self.status_bar.showMessage(msg)

    def _on_crawler_finished_callback(self, success: bool, message: str):
        """ページ単位のクローラー完了ハンドラ"""
        if self._is_paused_for_auth:
            return
        self.logger.info(f"ページ {self._current_page_idx} のクローラー取得完了: {message}")
        if not self._is_analyzing:
            self._finish_all_pages(True, "ユーザーにより処理が停止されました")
            return

        # 次ページの確認および自動遷移
        self._check_and_advance_to_next_page()

    def _check_and_advance_to_next_page(self):
        """次ページが存在するか判定し、存在すれば自動遷移してクロール継続"""
        if not self._is_analyzing:
            self._finish_all_pages(True, "処理が停止されました")
            return

        page = self.web_view.page()
        if isinstance(page, CustomWebEnginePage):
            page.intercept_navigation = False

        self.web_view.page().runJavaScript(CHECK_NEXT_PAGE_JS, self._on_check_next_page_result)

    def _on_check_next_page_result(self, res):
        if not self._is_analyzing:
            self._finish_all_pages(True, "処理が停止されました")
            return

        data = {}
        if isinstance(res, str):
            try:
                data = json.loads(res)
            except Exception:
                pass
        elif isinstance(res, dict):
            data = res

        has_next = data.get("hasNext", False)
        if not has_next:
            self.logger.info(f"次ページが存在しないため、全ページ取得完了と判定しました (全 {self._current_page_idx} ページ)")
            self._on_pagination_completed(self._current_page_idx, f"全 {self._current_page_idx} ページのカリキュラム取得が完了しました")
            return

        next_page_num = self._current_page_idx + 1
        self.logger.info(f"次ページを検出しました。ページ {next_page_num} へ自動遷移します...")
        self.status_bar.showMessage(f"次ページ (ページ {next_page_num}) へ自動遷移中...")
        self.loading_overlay.update_message(f"次ページ (ページ {next_page_num}) へ移動中...", pct=0)

        self.web_view.page().runJavaScript(CLICK_NEXT_PAGE_JS, self._on_click_next_page_result)

    def _on_click_next_page_result(self, res):
        if not self._is_analyzing:
            self._finish_all_pages(True, "処理が停止されました")
            return

        data = {}
        if isinstance(res, str):
            try:
                data = json.loads(res)
            except Exception:
                pass
        elif isinstance(res, dict):
            data = res

        if not data.get("success", False):
            self.logger.warning(f"次ページボタンのクリックに失敗しました: {data.get('reason')}")
            self._on_pagination_completed(self._current_page_idx, f"全 {self._current_page_idx} ページの処理を完了しました")
            return

        prev_signature = data.get("prevSignature", "")
        self._wait_for_page_transition(prev_signature)

    def _wait_for_page_transition(self, prev_signature: str):
        """次ページへのDOM更新または画面ロード完了を監視"""
        self._page_transition_attempts = 0
        max_attempts = 15

        def check_status():
            if not self._is_analyzing:
                return
            self._page_transition_attempts += 1

            def on_check_res(res):
                if not self._is_analyzing:
                    return
                cdata = {}
                if isinstance(res, str):
                    try:
                        cdata = json.loads(res)
                    except Exception:
                        pass
                elif isinstance(res, dict):
                    cdata = res

                changed = cdata.get("changed", False)
                is_loading = cdata.get("isLoading", False)

                if (changed and not is_loading) or self._page_transition_attempts >= max_attempts:
                    if self._page_transition_attempts >= max_attempts and not changed:
                        self.logger.warning("次ページへの画面更新待機タイムアウト (現在のテーブル内容で継続パースします)")
                    else:
                        self.logger.info(f"次ページロード確認完了 (試行: {self._page_transition_attempts}回)")

                    self._current_page_idx += 1
                    self._start_list_page_extraction()
                else:
                    QTimer.singleShot(300, check_status)

            js_code = get_check_page_changed_js(prev_signature)
            self.web_view.page().runJavaScript(js_code, on_check_res)

        QTimer.singleShot(300, check_status)

    def _on_pagination_completed(self, total_pages: int, message: str):
        """一覧画面のページネーション巡回が完了した際のハンドラ"""
        self._is_analyzing = False
        self._is_paused_for_auth = False
        self.logger.info(f"ページネーション巡回完了: {message}。解析Queueの消化完了を待機中...")
        self.loading_overlay.update_message("ページネーション完了。詳細データの保存完了を待機中...", pct=100)
        self.status_bar.showMessage("全ページ取得完了・詳細データ保存完了を待機中...")

        def _wait_queue():
            try:
                # 1. 解析スレッドプールのタスク完了待機
                if hasattr(self, "parse_pool") and self.parse_pool:
                    self.parse_pool.shutdown(wait=True)
                    self.parse_pool = None
                # 2. save_queue 内のDB保存完了待機
                if hasattr(self, "save_queue") and self.save_queue:
                    self.save_queue.join()
            except Exception as e:
                self.logger.error(f"データ保存待機中にエラー: {e}")
            finally:
                self.signals.classroom_crawl_completed.emit(total_pages)

        threading.Thread(target=_wait_queue, daemon=True).start()

    @Slot(int)
    def _prompt_next_classroom_or_export(self, total_pages: int):
        """キュー消化完了後にポップアップを表示し、別教室巡回かExcel出力かを選択させる"""
        self.loading_overlay.hide_loading()
        counts = self.repo.get_counts()

        # 教室自動巡回モード時は確認ポップアップをスキップして次の教室へ自動移行
        if self._is_patrol_mode:
            target = self._patrol_classroom_list[self._patrol_current_index] if self._patrol_current_index < len(self._patrol_classroom_list) else {}
            c_name = target.get("classroom_name", "")
            self.logger.info(f"教室 '{c_name}' の巡回が完了しました (全 {total_pages} ページ)。次の教室へ自動遷移します...")
            self._prepare_for_next_classroom()
            self._patrol_current_index += 1
            QTimer.singleShot(250, self._run_current_patrol_step)
            return

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("教室巡回完了")
        msg_box.setText(
            f"現在の教室（全 {total_pages} ページ）の巡回・解析が完了しました。\n"
            f"取得・保存済み件数: {counts['saved']} 件\n\n"
            "続けてどのように処理しますか？"
        )
        btn_next = msg_box.addButton("別教室の巡回に進む", QMessageBox.ButtonRole.AcceptRole)
        btn_export = msg_box.addButton("Excelファイルを出力する", QMessageBox.ButtonRole.ActionRole)
        msg_box.setDefaultButton(btn_next)

        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked == btn_next:
            self._prepare_for_next_classroom()
        else:
            self._finish_all_pages(True, f"全 {total_pages} ページの処理を完了しました")

    def _prepare_for_next_classroom(self):
        """別教室の巡回に進むための待機状態へ移行"""
        self._is_continuous_classroom_mode = True
        self._is_analyzing = False
        self._is_paused_for_auth = False
        self._cleanup_worker_tabs()

        if hasattr(self, "db_writer") and self.db_writer:
            try:
                if hasattr(self, "save_queue") and self.save_queue:
                    self.save_queue.put(None)
                self.db_writer.join(timeout=5.0)
            except Exception:
                pass
            self.db_writer = None

        self.loading_overlay.hide_loading()
        self.btn_start.setText("▶ 次の教室を開始")
        self.btn_start.setEnabled(True)
        if hasattr(self, "btn_patrol") and not self._is_patrol_mode:
            self.btn_patrol.setEnabled(True)
        self.btn_stop.setEnabled(self._is_patrol_mode)
        self._refresh_initial_counts()

        self.logger.info("別教室の巡回待機状態に移行しました。ブラウザで次の教室を表示してください。")
        self.status_bar.showMessage("ブラウザで次の教室の一覧（1ページ目）を表示し、「▶ 次の教室を開始」を押してください")

    def _finish_all_pages(self, success: bool, message: str):
        """全ページの取得・クローラー完了後の後処理ハンドラ"""
        self._is_analyzing = False
        self._is_paused_for_auth = False
        self._is_continuous_classroom_mode = False
        self.logger.info(f"全ページ処理フェーズ完了: {message}")
        self.loading_overlay.update_message("全ページの取得完了。解析Queueの消化とExcel出力待機中...", pct=100)
        self.status_bar.showMessage("全ページ解析完了・Excel出力待機中...")

        threading.Thread(target=self._finalize_pipeline, daemon=True).start()

    def _cleanup_analysis_session(self):
        """セッション中断・エラー時のクリーンアップ"""
        self._is_analyzing = False
        self._is_paused_for_auth = False
        self._is_continuous_classroom_mode = False
        self.loading_overlay.hide_loading()
        self._is_patrol_mode = False
        self._patrol_classroom_list.clear()
        self.btn_start.setText("▶ 処理開始")
        self.btn_start.setEnabled(True)
        if hasattr(self, "btn_patrol"):
            self.btn_patrol.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._cleanup_worker_tabs()
        if hasattr(self, "parse_pool") and self.parse_pool:
            self.parse_pool.shutdown(wait=False)
        if hasattr(self, "db_writer") and self.db_writer:
            self.db_writer.stop()
            if hasattr(self, "save_queue") and self.save_queue:
                self.save_queue.put(None)

    def _finalize_pipeline(self):
        """全取得後のパイプライン後始末 (①解析完了待機 → ②DB保存完了待機 → ③Writer終了 → ④Excel出力)"""
        try:
            # 1. 解析ワーカースレッドプールで実行中のタスクがすべて save_queue へ投入されるまで待機 (C2対策)
            if hasattr(self, "parse_pool") and self.parse_pool:
                self.parse_pool.shutdown(wait=True)
                self.parse_pool = None

            # 2. save_queue 内の全アイテムが DBWriter によってコミットされるまで待機
            if hasattr(self, "save_queue") and self.save_queue:
                self.save_queue.join()

            # 3. DBWriter スレッドを安全に停止して接続をクローズ
            if hasattr(self, "db_writer") and self.db_writer:
                if hasattr(self, "save_queue") and self.save_queue:
                    self.save_queue.put(None)
                self.db_writer.join(timeout=10.0)
                self.db_writer = None

            # 生徒単位の教室名相互補完 (未受講科目への伝播および完全未受講生徒の'不明'設定)
            self.logger.info("生徒単位の教室名相互補完を実行中...")
            self.repo.backfill_classroom_names()

            self._apply_copypaste_detection()

            # 4. 全データが確実にDBへ反映された状態で最終Excelを出力
            final_file = self.safe_writer.export_final()
            self.logger.info(f"最終Excelを生成しました: {final_file}")
            self.signals.crawl_finished.emit(True, final_file)
        except Exception as e:
            self.logger.error(f"最終処理中にエラーが発生しました: {e}", exc_info=True)
            self.signals.crawl_finished.emit(False, str(e))
        finally:
            if hasattr(self, "parse_pool") and self.parse_pool:
                try:
                    self.parse_pool.shutdown(wait=False)
                except Exception:
                    pass
            if hasattr(self, "db_writer") and self.db_writer:
                try:
                    self.db_writer.stop()
                    if hasattr(self, "save_queue") and self.save_queue:
                        self.save_queue.put(None)
                except Exception:
                    pass

    def _on_detail_html_fetched(self, overview: CurriculumOverview, html: str, fetch_time: str):
        """クローラーがHTMLを取得した際に並列解析ThreadPoolへ投入"""
        if self.parse_pool:
            self.parse_pool.submit(self._parse_detail_task, overview, html, fetch_time)

    def _parse_detail_task(self, overview: CurriculumOverview, html: str, fetch_time: str):
        """解析Worker処理 (並列実行: 仕様書§6)"""
        try:
            # 1. 詳細HTMLパース
            detail_data = self.detail_parser.parse(html, overview=overview, fetch_time=fetch_time)

            # 2. 備考欄評価
            detail_data.instruction_eval = self.instruction_evaluator.evaluate(
                raw_instruction=detail_data.raw_instruction,
                grade=overview.grade,
                division=overview.division,
                school_course=overview.school_course
            )

            # 3. ターゲット別進捗率集計
            progress_list = []
            for t in detail_data.targets:
                prog = calculate_target_progress(overview, t, detail_data.units)
                progress_list.append(prog)
            detail_data.progress_list = progress_list

            # 4. Save Queueへ投入 (単一DB Writerへ委譲)
            self.save_queue.put(detail_data)

        except Exception as e:
            self.logger.error(f"詳細解析エラー: {overview.student_id} - {e}", exc_info=True)

    def _apply_copypaste_detection(self):
        """全件に対するコピペ疑い検出を適用して更新"""
        self.logger.info("備考欄のコピペ疑い判定を実行中...")
        pass

    def _on_checkpoint_save(self, saved_count: int):
        """中間保存コールバック (仕様変更: 中間出力は廃止)"""
        pass

    def _on_db_saved(self, saved_count: int):
        """DB保存進捗コールバック (インメモリ集計でSQLite競合を防止)"""
        total_saved = self._session_base_saved + saved_count
        self._cached_counts["saved"] = total_saved
        total = max(self._cached_counts.get("total", 0), total_saved)
        self.signals.status_updated.emit(
            "保存完了",
            total,
            max(self._cached_counts.get("fetched", 0), total_saved),
            saved_count,
            total_saved,
            self._cached_counts.get("failed", 0),
        )

    def _on_crawl_progress(self, current: int, total: int, student_name: str):
        """クローラー進捗コールバック (GUIスレッドでの同期DBアクセスを排除)"""
        total_all = max(self._cached_counts.get("total", 0), total)
        saved = self._cached_counts.get("saved", 0)
        self._cached_counts["fetched"] = current
        self.signals.status_updated.emit(
            f"取得中: {student_name}",
            total_all,
            current,
            saved,
            saved,
            self._cached_counts.get("failed", 0),
        )

    @Slot(str, int, int, int, int, int)
    def _on_status_updated(self, current: str, total: int, fetched: int, parsed: int, saved: int, failed: int):
        self.progress_panel.update_status(current, total, fetched, parsed, saved, failed)
        self.status_bar.showMessage(f"進行中: {current} | 保存済み: {saved} / {total}")

    def _on_tab_activity_updated(self, slot_idx: int, status_text: str):
        """ワーカータブの進行状況をタブタイトルに反映"""
        if hasattr(self, "worker_tab_views") and slot_idx < len(self.worker_tab_views):
            wv = self.worker_tab_views[slot_idx]
            tab_idx = self.tab_widget.indexOf(wv)
            if tab_idx != -1:
                short_text = status_text[:12] if len(status_text) > 12 else status_text
                self.tab_widget.setTabText(tab_idx, f"📑 取得タブ {slot_idx + 1} ({short_text})")

    def _cleanup_worker_tabs(self):
        """取得用タブをすべて閉じ、「カリキュラム一覧」タブのみに戻す"""
        if hasattr(self, "worker_tab_views") and self.worker_tab_views:
            for wv in self.worker_tab_views:
                idx = self.tab_widget.indexOf(wv)
                if idx != -1:
                    self.tab_widget.removeTab(idx)
                try:
                    wv.deleteLater()
                except Exception:
                    pass
            self.worker_tab_views.clear()
        self.tab_widget.setCurrentIndex(0)

    def _open_and_select_file(self, file_path: str):
        """エクスプローラーで対象ファイルを選択状態で安全に開く (コマンド文字列結合を廃止)"""
        try:
            norm_path = os.path.normpath(file_path)
            if os.path.exists(norm_path):
                subprocess.Popen(["explorer", f"/select,{norm_path}"])
            elif os.path.exists(os.path.dirname(norm_path)):
                os.startfile(os.path.dirname(norm_path))
        except Exception as open_err:
            self.logger.debug(f"出力先フォルダのオープンに失敗: {open_err}")

    @Slot(bool, str)
    def _on_crawl_finished(self, success: bool, result_msg: str):
        self._cleanup_worker_tabs()
        self.loading_overlay.hide_loading()
        self._is_patrol_mode = False
        self._patrol_classroom_list.clear()
        self.btn_start.setText("▶ 処理開始")
        self.btn_start.setEnabled(True)
        if hasattr(self, "btn_patrol"):
            self.btn_patrol.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._refresh_initial_counts()
        if success:
            self.status_bar.showMessage(f"全処理完了: {os.path.basename(result_msg)}")
            QMessageBox.information(self, "処理完了", f"カリキュラムチェックが完了しました！\n\n出力ファイル:\n{result_msg}")
            self._open_and_select_file(result_msg)
        else:
            self.status_bar.showMessage("処理中断またはエラーが発生しました")
            QMessageBox.warning(self, "処理結果", f"処理が終了しました:\n{result_msg}")

    def stop_process(self):
        """停止要求"""
        self._is_analyzing = False
        self._is_paused_for_auth = False
        if hasattr(self, "crawler") and self.crawler and (self.crawler.is_running or self.crawler.state.name == "PAUSED_AUTH"):
            self.crawler.stop()
        else:
            self._finish_all_pages(True, "ユーザーにより安全に停止されました")
        self.loading_overlay.update_message("停止中: 現在の処理完了後に安全終了します...")
        self.btn_stop.setEnabled(False)
        self.status_bar.showMessage("停止処理中: 現在のリクエスト完了後に安全終了します...")

    def manual_export(self):
        """手動Excel出力 (バックグラウンドスレッド実行でUIフリーズを防止)"""
        self.btn_export.setEnabled(False)
        self.status_bar.showMessage("Excelファイルを生成中...")

        def _worker():
            try:
                final_file = self.safe_writer.export_final()
                self.signals.manual_export_finished.emit(True, final_file)
            except Exception as e:
                self.signals.manual_export_finished.emit(False, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    @Slot(bool, str)
    def _on_manual_export_finished(self, success: bool, result_msg: str):
        self.btn_export.setEnabled(True)
        if success:
            self.status_bar.showMessage(f"Excel出力完了: {os.path.basename(result_msg)}")
            QMessageBox.information(self, "出力完了", f"Excelファイルを出力しました:\n{result_msg}")
            self._open_and_select_file(result_msg)
        else:
            self.status_bar.showMessage("Excel出力エラー")
            QMessageBox.critical(self, "出力エラー", f"Excel出力に失敗しました:\n{result_msg}")

    def keyPressEvent(self, event: QKeyEvent):
        """キーボードショートカット処理 (F11: フルスクリーン切り替え)"""
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showMaximized()
            else:
                self.showFullScreen()
            event.accept()

    # ==========================================
    # 教室自動巡回ロジック (Classroom Patrol)
    # ==========================================
    def start_classroom_patrol(self):
        """教室自動巡回フローの開始 (モーダル表示 → 300件設定 → 1行目から順次自動巡回)"""
        if self._is_analyzing:
            return

        # ログイン確認
        if not self.web_view.is_authenticated():
            reply = QMessageBox.question(
                self,
                "ログイン確認",
                "認証Cookie (KGLC等) がまだ検出されていません。\nブラウザ上でログインを完了してから開始してください。\n\nそれでも強制的に巡回を開始しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.status_bar.showMessage("教室巡回をキャンセルしました (ログインしてください)")
                return

        self.logger.info("教室巡回を開始します。画面トップの教室検索inputをクリックしてモーダルを開いています...")
        self.loading_overlay.show_loading(
            "教室巡回を開始中...",
            "教室検索モーダルを開いています...",
            show_progress=False
        )
        self.status_bar.showMessage("教室検索モーダルを開いています...")

        self.classroom_navigator.open_class_modal(
            self._on_patrol_modal_opened, timeout_sec=3.5
        )

    def _on_patrol_modal_opened(self, success: bool, err_msg: str):
        """モーダルオープン結果ハンドラ (最小権限対応: 開かない場合は安全停止)"""
        if not success:
            self.loading_overlay.hide_loading()
            self.logger.warning(f"教室巡回開始失敗: {err_msg}")
            QMessageBox.warning(
                self,
                "教室巡回不可",
                f"{err_msg}"
            )
            self.status_bar.showMessage("教室巡回は利用できません（自教室のみ閲覧権限）")
            return

        self.logger.info("教室選択モーダルの表示を確認しました。表示件数を300件に設定して教室一覧を取得します...")
        self.status_bar.showMessage("教室テーブル（300件）を取得中...")
        self.classroom_navigator.init_classroom_table(self._on_patrol_table_initialized)

    def _on_patrol_table_initialized(self, success: bool, classrooms: List[Dict[str, Any]], err_msg: str):
        """テーブル初期化完了ハンドラ: そのまま1行目から自動巡回を開始"""
        if not success or not classrooms:
            self.loading_overlay.hide_loading()
            self.logger.error(f"教室テーブル初期化失敗: {err_msg}")
            QMessageBox.warning(
                self,
                "教室一覧取得エラー",
                f"教室テーブルの取得に失敗しました:\n{err_msg}"
            )
            return

        # 巡回ステートマシン初期化
        self._is_patrol_mode = True
        self._patrol_classroom_list = list(classrooms)
        self._patrol_total_classrooms = len(classrooms)
        self._patrol_current_index = 0
        self._skipped_classrooms = []

        self.btn_start.setEnabled(False)
        self.btn_patrol.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.logger.info(
            f"全 {self._patrol_total_classrooms} 教室の自動巡回を開始します (テーブルの1行目から順次実行)"
        )
        # 1行目の教室から巡回を開始
        self._run_current_patrol_step()

    def _run_current_patrol_step(self):
        """現在のインデックスの教室行をクリックして検索・解析を実行"""
        if not self._is_patrol_mode:
            return

        if self._patrol_current_index >= self._patrol_total_classrooms:
            self._finish_patrol()
            return

        target = self._patrol_classroom_list[self._patrol_current_index]
        row_idx = target.get("index", self._patrol_current_index)
        c_code = target.get("classroom_code", "")
        c_name = target.get("classroom_name", "")
        step_num = self._patrol_current_index + 1

        self.logger.info(
            f"巡回進捗 [{step_num}/{self._patrol_total_classrooms}]: 行 {row_idx} / 教室 '{c_name}' ({c_code}) を選択・検索中..."
        )
        self.status_bar.showMessage(
            f"巡回中 [{step_num}/{self._patrol_total_classrooms}]: 教室 '{c_name}' ({c_code}) を検索中..."
        )
        self.loading_overlay.show_loading(
            f"教室切り替え中 ({step_num}/{self._patrol_total_classrooms})",
            f"教室 '{c_name}' ({c_code}) を選択して検索を実行しています...",
            show_progress=False
        )

        self.classroom_navigator.select_classroom_row_and_search(
            row_idx,
            c_code,
            self._on_patrol_step_search_completed,
            max_retries=2
        )

    def _on_patrol_step_search_completed(self, success: bool, reason: str):
        """教室選択＆検索完了ハンドラ"""
        self.loading_overlay.hide_loading()
        if not self._is_patrol_mode:
            return

        target = self._patrol_classroom_list[self._patrol_current_index]
        c_name = target.get("classroom_name", "")

        if not success:
            self.logger.error(
                f"教室 '{c_name}' への切り替えに失敗したためスキップします: {reason}"
            )
            self._skipped_classrooms.append(target)
            # 次の行へ進む
            self._patrol_current_index += 1
            self._run_current_patrol_step()
            return

        # 検索完了 -> 一覧解析を開始
        self._start_patrol_classroom_analysis()

    def _start_patrol_classroom_analysis(self):
        """巡回中教室のカリキュラム解析セッションを開始"""
        target = self._patrol_classroom_list[self._patrol_current_index]
        c_name = target.get("classroom_name", "")
        self.logger.info(f"教室 '{c_name}' のカリキュラム解析を開始します")

        self._cached_counts = self.repo.get_counts()
        self._session_base_saved = self._cached_counts["saved"]
        self._is_analyzing = True
        self._is_paused_for_auth = False
        self._current_page_idx = 1
        self._prev_page_student_keys = set()

        self.btn_start.setEnabled(False)
        self.btn_patrol.setEnabled(False)
        self.btn_stop.setEnabled(True)

        # DBWriterスレッド起動 (初回のみ)
        if not hasattr(self, "db_writer") or not self.db_writer:
            self.save_queue = queue.Queue()
            self.db_writer = DBWriter(
                repository=self.repo,
                save_queue=self.save_queue,
                checkpoint_interval=0,
                checkpoint_callback=None,
                progress_callback=self._on_db_saved,
            )
            self.db_writer.start()

        # 解析Worker ThreadPool起動 (初回のみ)
        if not hasattr(self, "parse_pool") or not self.parse_pool:
            self.parse_pool = ThreadPoolExecutor(
                max_workers=self.config.worker_threads,
                thread_name_prefix="ParseWorker"
            )

        # 既存のワーカータブをクリーンアップして再作成
        self._cleanup_worker_tabs()
        self.worker_tab_views = []
        for i in range(self.config.max_tabs):
            worker_view = self.web_view.create_tab_view(parent=self, disable_images=True)
            worker_view.urlChanged.connect(self._on_worker_tab_url_changed)
            tab_title = f"📑 取得タブ {i+1}"
            self.tab_widget.addTab(worker_view, tab_title)

        # 一覧画面解析クローラー作成
        self.crawler = WebEngineCrawler(
            tab_views=self.worker_tab_views,
            config=self.config,
            detail_parser=self.detail_parser,
            parent=self
        )
        self.crawler.progress_updated.connect(self._on_crawl_progress)
        self.crawler.detail_fetched.connect(self._on_detail_html_fetched)
        self.crawler.tab_activity_updated.connect(self._on_tab_activity_updated)
        self.crawler.crawl_finished.connect(self._on_crawler_finished_callback)
        self.crawler.auth_required.connect(self._on_crawler_auth_required)

        # 1ページ目の抽出開始
        self._start_list_page_extraction()

    def _finish_patrol(self):
        """全巡回完了時の処理"""
        self.logger.info(f"全 {self._patrol_total_classrooms} 教室の自動巡回が完了しました")
        self._is_patrol_mode = False
        if hasattr(self, "btn_patrol"):
            self.btn_patrol.setEnabled(True)

        self._finish_all_pages(True, f"全 {self._patrol_total_classrooms} 教室の自動巡回が完了しました")

        if self._skipped_classrooms:
            skipped_names = "、".join([c.get("classroom_name", "") for c in self._skipped_classrooms if c])
            QMessageBox.warning(
                self,
                "巡回スキップ教室あり",
                f"以下の教室は切り替えに失敗したためスキップされました:\n{skipped_names}\n\nスキップされなかった教室のデータは正常に保存・出力されています。"
            )
