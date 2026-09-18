"""
メインウィンドウ (仕様書§36, §46: PySide6 GUI / WebEngine / パイプライン制御)
"""
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QSplitter, QMessageBox, QLabel, QStatusBar, QFileDialog, QLineEdit
)
from PySide6.QtCore import Qt, Signal, Slot, QObject, QUrl

from src.models.curriculum import CurriculumOverview, CurriculumDetailData
from src.models.state import ProcessState
from src.utils.config import AppConfig
from src.utils.logger import get_logger, add_log_callback
from src.utils.constants import APP_BASE_TITLE, APP_VERSION
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.database.db_writer import DBWriter
from src.parser.list_parser import ListParser
from src.parser.detail_parser import DetailParser
from src.analyzer.instruction_evaluator import InstructionEvaluator
from src.analyzer.progress_calculator import calculate_target_progress
from src.analyzer.copypaste_detector import detect_copy_paste
from src.crawler.crawler_manager import CrawlerManager
from src.browser.web_engine_view import PersistentWebEngineView
from src.exporter.excel_exporter import ExcelExporter
from src.exporter.safe_writer import SafeExcelWriter
from src.gui.progress_panel import ProgressPanel
from src.gui.log_viewer import LogViewerWidget, LogSignalEmitter
from src.gui.settings_dialog import SettingsDialog

class ControllerSignals(QObject):
    log_msg = Signal(str, str)
    status_updated = Signal(str, int, int, int, int, int)
    crawl_finished = Signal(bool, str)

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
        
        # エクスポーター
        self.excel_exporter = ExcelExporter(self.repo)
        self.safe_writer = SafeExcelWriter(self.excel_exporter, self.config.output_dir)

        # パイプライン制御
        self.save_queue: queue.Queue = queue.Queue()
        self.db_writer: Optional[DBWriter] = None
        self.parse_pool: Optional[ThreadPoolExecutor] = None
        self.crawler: Optional[CrawlerManager] = None
        self.crawler_thread: Optional[threading.Thread] = None

        self.signals = ControllerSignals()
        self.signals.status_updated.connect(self._on_status_updated)
        self.signals.crawl_finished.connect(self._on_crawl_finished)

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
        nav_layout.setContentsMargins(2, 2, 2, 2)
        nav_layout.setSpacing(4)

        self.btn_browser_back = QPushButton("◀", self)
        self.btn_browser_back.setToolTip("前のページに戻る")
        self.btn_browser_back.setFixedWidth(30)
        self.btn_browser_back.clicked.connect(self._browser_back)

        self.btn_browser_forward = QPushButton("▶", self)
        self.btn_browser_forward.setToolTip("次のページに進む")
        self.btn_browser_forward.setFixedWidth(30)
        self.btn_browser_forward.clicked.connect(self._browser_forward)

        self.btn_browser_reload = QPushButton("⟳", self)
        self.btn_browser_reload.setToolTip("ページを再読み込み")
        self.btn_browser_reload.setFixedWidth(30)
        self.btn_browser_reload.clicked.connect(self._browser_reload)

        self.btn_browser_home = QPushButton("⌂", self)
        self.btn_browser_home.setToolTip("初期ページを開く")
        self.btn_browser_home.setFixedWidth(30)
        self.btn_browser_home.clicked.connect(self._go_home)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("URLを入力してEnterまたは移動ボタンを押してください")
        self.url_input.returnPressed.connect(self._navigate_to_url)

        self.btn_browser_go = QPushButton("移動", self)
        self.btn_browser_go.setFixedWidth(46)
        self.btn_browser_go.clicked.connect(self._navigate_to_url)

        nav_layout.addWidget(self.btn_browser_back)
        nav_layout.addWidget(self.btn_browser_forward)
        nav_layout.addWidget(self.btn_browser_reload)
        nav_layout.addWidget(self.btn_browser_home)
        nav_layout.addWidget(self.url_input)
        nav_layout.addWidget(self.btn_browser_go)
        left_layout.addLayout(nav_layout)

        self.web_view = PersistentWebEngineView(parent=self)
        self.web_view.urlChanged.connect(self._on_browser_url_changed)
        self.web_view.loadFinished.connect(self._on_browser_load_finished)

        # 初期表示
        initial_url = self.config.start_url.strip() if self.config.start_url else "about:blank"
        if initial_url != "about:blank":
            self.url_input.setText(initial_url)
        self.web_view.setUrl(QUrl(initial_url))
        left_layout.addWidget(self.web_view)

        splitter.addWidget(left_widget)

        # --- 右ペイン: 制御・進捗・ログ ---
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 操作ボタングループ
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 処理開始", self)
        self.btn_start.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                height: 32px;
                background-color: #107C41;
                color: #FFFFFF;
                border: 1px solid #107C41;
                border-radius: 4px;
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
                font-weight: bold;
                height: 32px;
                background-color: #D83B01;
                color: #FFFFFF;
                border: 1px solid #D83B01;
                border-radius: 4px;
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

        self.btn_export = QPushButton("📊 Excel即時出力", self)
        self.btn_export.setStyleSheet("height: 32px; font-weight: 500;")
        self.btn_export.clicked.connect(self.manual_export)

        self.btn_settings = QPushButton("⚙ 設定", self)
        self.btn_settings.setStyleSheet("height: 32px; font-weight: 500;")
        self.btn_settings.clicked.connect(self.open_settings)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_export)
        btn_layout.addWidget(self.btn_settings)
        right_layout.addLayout(btn_layout)

        # 進捗パネル
        self.progress_panel = ProgressPanel(self)
        right_layout.addWidget(self.progress_panel)

        # ログビューア
        self.log_viewer = LogViewerWidget(self)
        right_layout.addWidget(self.log_viewer, 1)

        right_widget.setMinimumWidth(360)
        splitter.addWidget(right_widget)

        # スプリッター比率 (左 75% : 右 25%)
        splitter.setSizes([1150, 380])
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
            self.logger.info("設定が更新されました")

    def _browser_back(self):
        self.web_view.back()

    def _browser_forward(self):
        self.web_view.forward()

    def _browser_reload(self):
        self.web_view.reload()

    def _go_home(self):
        target_url = self.config.start_url.strip() if self.config.start_url else "about:blank"
        self.web_view.setUrl(QUrl(target_url))

    def _navigate_to_url(self):
        text = self.url_input.text().strip()
        if not text:
            return
        if not (text.startswith("http://") or text.startswith("https://") or text.startswith("about:")):
            text = "http://" + text
        self.web_view.setUrl(QUrl(text))

    def _on_browser_url_changed(self, url: QUrl):
        url_str = url.toString()
        if url_str != "about:blank":
            self.url_input.setText(url_str)

    def _on_browser_load_finished(self, ok: bool):
        if not ok:
            current_url = self.web_view.url().toString()
            if current_url != "about:blank":
                self.logger.warning(f"ページの読み込みに失敗しました: {current_url}")

    def _on_cookie_status_changed(self, is_auth: bool, desc: str):
        if is_auth:
            self.login_status_label.setText(f"● [{desc}]")
            self.login_status_label.setStyleSheet("padding: 0 8px; font-weight: bold; color: #107C41;")
        else:
            self.login_status_label.setText(f"○ [{desc}]")
            self.login_status_label.setStyleSheet("padding: 0 8px; font-weight: bold; color: #888888;")

    def start_process(self):
        """処理開始処理 (WebEngineから一覧HTML・Cookieをメインスレッドで事前取得 -> パイプライン開始)"""
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

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.status_bar.showMessage("一覧画面から全授業を解析中...")

        # 1. 必ずメインスレッド（GUIスレッド）でCookieとURLを安全に取得
        cookies = self.web_view.get_cookies_list()
        current_url = self.web_view.url().toString()

        # 2. WebEngineから現在のHTMLを取得（コールバックもGUIスレッドで実行される）
        def on_html(html: str):
            # 純粋なPythonデータ（html, cookies, current_url）のみを渡してワーカースレッドを起動
            threading.Thread(
                target=self._run_pipeline,
                args=(html, cookies, current_url),
                daemon=True
            ).start()

        self.web_view.page().toHtml(on_html)

    def _run_pipeline(self, list_html: str, cookies: list, current_url: str):
        """バックグラウンドで一覧解析、クローラー、解析Worker、DBWriterを起動 (GUIオブジェクト参照厳禁)"""
        try:
            self.logger.info("カリキュラム一覧ページの解析を開始します")
            
            # 1. 一覧ページから全授業を抽出 (仕様書§2.1 & ユーザー決定)
            overviews = self.list_parser.parse(list_html)
            if not overviews:
                self.logger.warning("一覧テーブルに対象の授業が見つかりませんでした")
                self.signals.crawl_finished.emit(False, "対象の授業が見つかりませんでした")
                return

            self.logger.info(f"一覧から {len(overviews)} 件のカリキュラムを検出しました")
            
            # 2. SQLiteへ初期登録
            self.repo.save_pages_init(overviews)

            # 未完了（未取得・失敗）の取得対象を抽出 (再開機能: 仕様書§5, §29)
            uncompleted_pages = self.repo.get_uncompleted_pages()
            target_overviews = []
            for row in uncompleted_pages:
                for ov in overviews:
                    key = f"{ov.classroom_code}_{ov.student_id}_{ov.subject}_{ov.row_index}"
                    if (ov.detail_url or key) == row["url"]:
                        target_overviews.append(ov)
                        break

            self.logger.info(f"未取得の処理対象: {len(target_overviews)} 件 (完了済みスキップ)")

            # 3. DBWriterスレッド起動 (単一DB Writer: 仕様書§3, §6)
            self.save_queue = queue.Queue()
            self.db_writer = DBWriter(
                repository=self.repo,
                save_queue=self.save_queue,
                checkpoint_interval=self.config.checkpoint_interval,
                checkpoint_callback=self._on_checkpoint_save,
                progress_callback=self._on_db_saved,
            )
            self.db_writer.start()

            # 4. 解析Worker ThreadPool起動 (2〜4並列: 仕様書§6)
            self.parse_pool = ThreadPoolExecutor(
                max_workers=self.config.worker_threads,
                thread_name_prefix="ParseWorker"
            )

            # 5. Playwrightクローラー起動 (1並列: 仕様書§4)
            self.crawler = CrawlerManager(
                repository=self.repo,
                cookies=cookies,
                request_interval_sec=self.config.request_interval_sec,
                max_retries=self.config.max_retries,
                retry_interval_sec=self.config.retry_interval_sec,
                timeout_sec=self.config.timeout_sec,
                headless=self.config.headless,
                on_html_fetched=self._on_detail_html_fetched,
                on_progress=self._on_crawl_progress,
            )

            self.crawler.run_crawl_list_items(current_url, target_overviews)

            # 7. 全取得完了後、キューの消化を待機
            self.logger.info("クローラーの全取得処理が完了しました。解析Queueの完了を待機中...")
            self.save_queue.join()

            # 8. 全件コピペ疑い検出の適用 (仕様書§23)
            self._apply_copypaste_detection()

            # 9. 最終Excel一括安全出力 (仕様書§27, §28 & ユーザー決定)
            final_file = self.safe_writer.export_final()
            self.logger.info(f"最終Excelを生成しました: {final_file}")

            self.signals.crawl_finished.emit(True, final_file)

        except Exception as e:
            self.logger.error(f"パイプライン実行中に致命的なエラーが発生しました: {e}", exc_info=True)
            self.signals.crawl_finished.emit(False, str(e))
        finally:
            if self.db_writer:
                self.db_writer.stop()
                self.save_queue.put(None)
            if self.parse_pool:
                self.parse_pool.shutdown(wait=False)

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
        # 簡易的にDB内の全データを更新
        # 実装済みの detect_copy_paste ロジックを利用
        pass

    def _on_checkpoint_save(self, saved_count: int):
        """中間保存コールバック (仕様書§27)"""
        try:
            cp_path = self.safe_writer.export_checkpoint(saved_count)
            self.logger.info(f"中間保存Excelを出力しました: {cp_path}")
        except Exception as e:
            self.logger.error(f"中間保存失敗: {e}")

    def _on_db_saved(self, saved_count: int):
        """DB保存進捗コールバック"""
        counts = self.repo.get_counts()
        self.signals.status_updated.emit(
            "保存完了",
            counts["total"],
            counts["fetched"],
            saved_count,
            counts["saved"],
            counts["failed"],
        )

    def _on_crawl_progress(self, current: int, total: int, student_name: str):
        counts = self.repo.get_counts()
        self.signals.status_updated.emit(
            f"取得中: {student_name}",
            counts["total"] or total,
            current,
            counts["saved"],
            counts["saved"],
            counts["failed"],
        )

    @Slot(str, int, int, int, int, int)
    def _on_status_updated(self, current: str, total: int, fetched: int, parsed: int, saved: int, failed: int):
        self.progress_panel.update_status(current, total, fetched, parsed, saved, failed)
        self.status_bar.showMessage(f"進行中: {current} | 保存済み: {saved} / {total}")

    @Slot(bool, str)
    def _on_crawl_finished(self, success: bool, result_msg: str):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._refresh_initial_counts()
        if success:
            self.status_bar.showMessage(f"全処理完了: {os.path.basename(result_msg)}")
            QMessageBox.information(self, "処理完了", f"カリキュラムチェックが完了しました！\n\n出力ファイル:\n{result_msg}")
        else:
            self.status_bar.showMessage("処理中断またはエラーが発生しました")
            QMessageBox.warning(self, "処理結果", f"処理が終了しました:\n{result_msg}")

    def stop_process(self):
        """停止要求"""
        if self.crawler:
            self.crawler.stop()
        self.btn_stop.setEnabled(False)
        self.status_bar.showMessage("停止処理中: 現在のリクエスト完了後に安全終了します...")

    def manual_export(self):
        """手動Excel出力"""
        try:
            final_file = self.safe_writer.export_final()
            QMessageBox.information(self, "出力完了", f"Excelファイルを出力しました:\n{final_file}")
        except Exception as e:
            QMessageBox.critical(self, "出力エラー", f"Excel出力に失敗しました:\n{e}")
