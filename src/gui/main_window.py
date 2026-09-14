import hashlib
import json
import logging
import os
import subprocess
import sys
from enum import Enum
from typing import Optional, Any

from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSlot, QEvent
from PyQt6.QtGui import QIcon, QKeySequence, QAction, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QStatusBar,
    QLabel, QMessageBox, QFileDialog, QInputDialog, QApplication, QMenu
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings
)

from core.constants import (
    APP_BASE_TITLE, WINDOW_INITIAL_WIDTH, WINDOW_INITIAL_HEIGHT,
    WINDOW_MINIMUM_WIDTH, WINDOW_MINIMUM_HEIGHT, __version__,
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, SCREEN_TRANSITION_WAIT,
    POLLING_INTERVAL_MS, PAGE_LOAD_TIMEOUT
)
from core.models import AppConfig, CurriculumRecord
from core.repository import Repository
from core.cache import CacheManager
from core.normalization import (
    extract_student_id_from_cell, extract_student_name_from_cell,
    normalize_student_id, normalize_grade,
    normalize_division, normalize_subject, is_summary_row,
    clean_instruction, sanitize_raw_instruction
)
from core.config import load_selectors
from gui.toast import ToastWidget
from gui.worker import AggregationWorker
from gui.overlay import LoadingOverlay
from gui.guide_dialog import StartupGuideDialog

logger = logging.getLogger(__name__)



def _get_extract_table_js_path() -> str:
    """開発環境およびNuitka Onefile展開環境から extract_table.js を探索・解決する。"""
    candidates = []
    # 1. Nuitka Onefile 展開環境
    onefile_dir = os.environ.get("NUITKA_ONEFILE_DIRECTORY")
    if onefile_dir:
        candidates.append(os.path.join(onefile_dir, "browser", "extract_table.js"))
        candidates.append(os.path.join(onefile_dir, "src", "browser", "extract_table.js"))
    # 2. 実行ファイル同階層
    exe_dir = os.path.dirname(sys.executable)
    candidates.append(os.path.join(exe_dir, "browser", "extract_table.js"))
    candidates.append(os.path.join(exe_dir, "src", "browser", "extract_table.js"))
    # 3. 開発環境 (__file__ 基準)
    base_src = os.path.dirname(os.path.dirname(__file__))
    candidates.append(os.path.join(base_src, "browser", "extract_table.js"))
    candidates.append(os.path.join(base_src, "src", "browser", "extract_table.js"))

    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return candidates[-2]


class AppState(Enum):
    READY = "READY"
    PAGE_LOADING = "PAGE_LOADING"
    SCREEN_TRANSITION_WAIT = "SCREEN_TRANSITION_WAIT"
    AGGREGATING = "AGGREGATING"


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, repository: Repository, cache_manager: CacheManager, user_data_dir: str):
        super().__init__()
        self.config = config
        self.repository = repository
        self.cache_manager = cache_manager
        self.user_data_dir = user_data_dir

        self.state = AppState.READY
        self.load_generation_id = 0
        self.current_request_id = 0

        # セレクタ設定の読み込み (v8 §8, v9 §34.1)
        base_dir = os.path.dirname(user_data_dir) if user_data_dir else os.getcwd()
        self.selectors_path = os.path.join(base_dir, "selectors.json")
        self.selectors, self.selectors_error = load_selectors(self.selectors_path)

        # 孤立した一時ファイルの整理 (v9 §37.4)
        self.cache_manager.cleanup_orphan_tmp_files()

        # 読み取り件数監視 (v8 §11)
        self.last_page_record_count = 0

        # 教室・年度の保持 (v7 §9, v8 §7)
        self.current_classroom_name = ""
        self.current_classroom_code = ""
        self.current_school_year = ""
        records = self.repository.get_all_records()
        if records:
            last_rec = records[-1]
            self.current_classroom_name = last_rec.classroom_name
            self.current_classroom_code = last_rec.classroom_code
            self.current_school_year = last_rec.school_year
            self.last_page_record_count = len(records)
        
        self.polling_timer = QTimer(self)
        self.polling_timer.setInterval(POLLING_INTERVAL_MS)
        self.polling_timer.timeout.connect(self._on_polling)
        self.is_polling_busy = False
        self.transition_wait_elapsed = 0
        self.last_url = ""
        self.last_dom_hash = ""

        self.load_timeout_timer = QTimer(self)
        self.load_timeout_timer.setSingleShot(True)
        self.load_timeout_timer.setInterval(PAGE_LOAD_TIMEOUT * 1000)
        self.load_timeout_timer.timeout.connect(self._on_load_timeout)

        self.worker: Optional[AggregationWorker] = None
        self.is_shutting_down = False

        self._setup_ui()
        self._setup_webengine()
        self._setup_shortcuts()
        self._update_title()
        self._update_status()

        # 起動時案内ダイアログの表示判定 (v7 §11.1)
        QTimer.singleShot(150, self._check_show_startup_guide)

    def _check_show_startup_guide(self):
        """起動時案内ダイアログを表示する (v7 §11.1)"""
        if StartupGuideDialog.should_show(self.user_data_dir):
            dlg = StartupGuideDialog(self, user_data_dir=self.user_data_dir)
            dlg.exec()

    def _setup_ui(self):
        self.resize(WINDOW_INITIAL_WIDTH, WINDOW_INITIAL_HEIGHT)
        self.setMinimumSize(WINDOW_MINIMUM_WIDTH, WINDOW_MINIMUM_HEIGHT)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("""
            QToolBar {
                spacing: 6px;
                padding: 4px;
                background-color: #F8F9FA;
                border-bottom: 1px solid #D0D7DE;
            }
            QToolButton {
                font-family: 'Meiryo UI', sans-serif;
                font-size: 13px;
                font-weight: bold;
                color: #1E293B;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #CBD5E1;
                background-color: #FFFFFF;
            }
            QToolButton:hover {
                background-color: #F1F5F9;
                border-color: #1F4E78;
                color: #0D3A66;
            }
            QToolButton:pressed {
                background-color: #E2E8F0;
                border-color: #0D3A66;
                color: #0D3A66;
            }
            QToolButton:disabled {
                color: #94A3B8;
                background-color: #F1F5F9;
                border-color: #E2E8F0;
            }
        """)
        self.addToolBar(self.toolbar)

        # ボタンの配置と表記 (v7 §11.2, §11.3)
        self.action_back = QAction("← 戻る", self)
        self.action_back.triggered.connect(self._go_back)
        self.toolbar.addAction(self.action_back)

        self.action_forward = QAction("→ 進む", self)
        self.action_forward.triggered.connect(self._go_forward)
        self.toolbar.addAction(self.action_forward)

        self.action_reload = QAction("↻ 再読み込み", self)
        self.action_reload.triggered.connect(self._reload)
        self.toolbar.addAction(self.action_reload)

        self.action_home = QAction("ホーム", self)
        self.action_home.triggered.connect(self._go_home)
        self.toolbar.addAction(self.action_home)

        self.toolbar.addSeparator()

        self.action_read = QAction("このページを読み取る (F9)", self)
        self.action_read.triggered.connect(self._on_read_page)
        self.toolbar.addAction(self.action_read)

        self.action_undo = QAction("↶ 1つ戻す (Ctrl+Z)", self)
        self.action_undo.triggered.connect(self._on_undo)
        self.toolbar.addAction(self.action_undo)

        self.action_aggregate = QAction("集計してExcel出力 (0件)", self)
        self.action_aggregate.setEnabled(False)
        self.action_aggregate.triggered.connect(self._on_aggregate)
        self.toolbar.addAction(self.action_aggregate)

        empty = QWidget()
        empty.setSizePolicy(empty.sizePolicy().Policy.Expanding, empty.sizePolicy().Policy.Preferred)
        self.toolbar.addWidget(empty)

        self.action_reset = QAction("蓄積データをクリア", self)
        self.action_reset.triggered.connect(self._on_reset)
        self.toolbar.addAction(self.action_reset)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)

        self.statusbar = QStatusBar()
        self.statusbar.setStyleSheet("""
            QStatusBar {
                background-color: #F8F9FA;
                border-top: 1px solid #D0D7DE;
                color: #1E293B;
            }
        """)
        self.setStatusBar(self.statusbar)

        # ステータスバー常時表示情報 (v7 §11.5)
        self.status_permanent_label = QLabel(self)
        self.status_permanent_label.setStyleSheet("font-family: 'Meiryo UI'; font-size: 12px; font-weight: bold; color: #0D3A66; margin-right: 12px;")
        self.statusbar.addPermanentWidget(self.status_permanent_label)
        
        self.toast = ToastWidget(self)

        # 全画面ローディングオーバーレイ (v7 §11.4)
        self.loading_overlay = LoadingOverlay(self.centralWidget())

    def _setup_webengine(self):
        profile = QWebEngineProfile("MyProfile", self.web_view)
        profile.setPersistentStoragePath(self.user_data_dir)
        profile.setCachePath(self.user_data_dir)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        
        settings = profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        # Block permissions via profile
        profile.setNotificationPresenter(lambda notification: None)
        # Cannot easily hook all permissions in PyQt6 without overriding, but we can set defaults if possible.

        page = CustomWebPage(profile, self.web_view)
        self.web_view.setPage(page)

        self.web_view.setZoomFactor(self.config.zoom_factor)

        self.web_view.loadStarted.connect(self._on_load_started)
        self.web_view.loadFinished.connect(self._on_load_finished)

        # Renderer crash (§33)
        page.renderProcessTerminated.connect(self._on_renderer_crash)

        # Download blocking (§37)
        profile.downloadRequested.connect(self._on_download_requested)

        # Custom context menu (§36)
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.web_view.customContextMenuRequested.connect(self._on_context_menu)

    def _setup_shortcuts(self):
        # F9
        QShortcut(QKeySequence("F9"), self, self._on_read_page)
        # Ctrl+Z
        QShortcut(QKeySequence("Ctrl+Z"), self, self._on_undo)
        # Ctrl+Enter
        QShortcut(QKeySequence("Ctrl+Return"), self, self._on_aggregate)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self._on_aggregate)
        # F5
        QShortcut(QKeySequence("F5"), self, self._reload)
        # Esc
        QShortcut(QKeySequence("Esc"), self, self._stop_load)
        # Alt+Left/Right
        QShortcut(QKeySequence("Alt+Left"), self, self._go_back)
        QShortcut(QKeySequence("Alt+Right"), self, self._go_forward)
        # Zoom
        QShortcut(QKeySequence("Ctrl++"), self, self._zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, self._zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self, self._zoom_reset)

    def _update_title(self):
        title = f"[蓄積: {self.repository.count:,}件] {APP_BASE_TITLE} v{__version__}"
        self.setWindowTitle(title)
        undo_count = len(self.repository._undo_stack)
        undo_str = f" ({undo_count})" if undo_count > 0 else ""
        self.action_undo.setText(f"↶ 1つ戻す (Ctrl+Z){undo_str}")
        self.action_undo.setEnabled(undo_count > 0)
        self.action_aggregate.setText(f"集計してExcel出力 ({self.repository.count:,}件)")
        self.action_aggregate.setEnabled(self.repository.count > 0)

    def _update_status(self):
        cls_name = self.current_classroom_name or "未取得"
        year_name = self.current_school_year or "未取得"
        count_str = f"{self.repository.count:,}件"
        last_str = f"{self.last_page_record_count:,}件"
        if hasattr(self, 'status_permanent_label'):
            self.status_permanent_label.setText(f"教室：{cls_name}　年度：{year_name}　今回：{last_str}　累計：{count_str}")
        self.statusbar.showMessage(self.state.value)

    def set_state(self, new_state: AppState):
        self.state = new_state
        self._update_status()

    def _on_load_started(self):
        if self.state == AppState.AGGREGATING:
            return
        self.load_generation_id += 1
        self.set_state(AppState.PAGE_LOADING)
        self.load_timeout_timer.start()

    def _on_load_finished(self, ok: bool):
        if self.state == AppState.AGGREGATING:
            return
        self.load_timeout_timer.stop()
        if self.state == AppState.PAGE_LOADING:
            self.set_state(AppState.READY)

    def _on_load_timeout(self):
        if self.state == AppState.PAGE_LOADING:
            self.web_view.stop()
            self.load_generation_id += 1 # invalidate
            self.set_state(AppState.READY)
            self.toast.show_message("読み込みがタイムアウトしました")

    def _stop_load(self):
        if self.state == AppState.PAGE_LOADING:
            self.web_view.stop()
            self.load_generation_id += 1
            self.load_timeout_timer.stop()
            self.set_state(AppState.READY)

    def _go_back(self):
        if self.state == AppState.READY or self.state == AppState.SCREEN_TRANSITION_WAIT:
            self.web_view.back()

    def _go_forward(self):
        if self.state == AppState.READY or self.state == AppState.SCREEN_TRANSITION_WAIT:
            self.web_view.forward()

    def _reload(self):
        if self.state != AppState.AGGREGATING:
            self.web_view.reload()

    def _go_home(self):
        if self.state == AppState.READY or self.state == AppState.SCREEN_TRANSITION_WAIT:
            current_url = self.web_view.url().toString(QUrl.UrlFormattingOption.NormalizePathSegments)
            base = QUrl(self.config.base_url).toString(QUrl.UrlFormattingOption.NormalizePathSegments)
            if current_url != base:
                self.web_view.load(QUrl(self.config.base_url))

    def _zoom_in(self):
        new_zoom = min(ZOOM_MAX, self.web_view.zoomFactor() + ZOOM_STEP)
        self.web_view.setZoomFactor(new_zoom)

    def _zoom_out(self):
        new_zoom = max(ZOOM_MIN, self.web_view.zoomFactor() - ZOOM_STEP)
        self.web_view.setZoomFactor(new_zoom)

    def _zoom_reset(self):
        self.web_view.setZoomFactor(self.config.zoom_factor)

    def _on_read_page(self):
        if self.state != AppState.READY:
            return

        if self.selectors_error:
            self.toast.show_message(f"設定エラー: {self.selectors_error}。読み取りを開始できません。")
            logger.error("読み取り中止: selectors.json の設定エラー (%s)", self.selectors_error)
            return
        
        js_path = _get_extract_table_js_path()
        try:
            with open(js_path, 'r', encoding='utf-8') as f:
                js_code = f.read()
        except Exception as e:
            logger.error(f"Failed to read JS: {e}")
            self.toast.show_message("抽出スクリプトの読み込みに失敗しました")
            return

        self.current_request_id += 1
        req_id = self.current_request_id
        
        self.loading_overlay.show_loading("ページ読み取り中", "データを抽出しています...", show_progress=False)
        selectors_json = json.dumps(self.selectors, ensure_ascii=False)
        full_js = f"window.__CURRICULUM_SELECTORS__ = {selectors_json};\n" + js_code
        self.web_view.page().runJavaScript(full_js, lambda res: self._on_f9_callback(req_id, res))

    def _on_f9_callback(self, req_id: int, res: dict):
        self.loading_overlay.hide_loading()
        if self.is_shutting_down or req_id != self.current_request_id:
            return
        
        if not res or not res.get("success"):
            if res and res.get("notStable"):
                self.toast.show_message("ページを読み込み中です。描画完了後にもう一度読み取ってください。")
            else:
                err_msg = res.get("error") if (res and res.get("error")) else "抽出に失敗しました"
                self.toast.show_message(err_msg)
            return
        
        # 教室情報チェック (v8 §7.1, §7.4)
        classroom_info = res.get("classroomInfo") or {}
        classroom_name = (
            classroom_info.get("classroomName")
            or res.get("classroomName")
            or ""
        ).strip()
        classroom_code = (
            classroom_info.get("classroomCode")
            or res.get("classroomCode")
            or ""
        ).strip()
        school_year = (
            classroom_info.get("schoolYear")
            or res.get("schoolYear")
            or ""
        ).strip()

        if not classroom_name or not classroom_code:
            self.toast.show_message("教室情報を取得できませんでした。このページは読み取り対象として登録しません。")
            logger.warning("教室情報の取得失敗: classroom_name=%r, classroom_code=%r", classroom_name, classroom_code)
            return

        # 採用セレクタの記録 (v8 §25)
        matched_sel = res.get("matchedSelectors") or {}
        logger.info("DOM抽出成功: 採用セレクタ = %s, 教室=%s (%s), 年度=%s", matched_sel, classroom_name, classroom_code, school_year)

        self.current_classroom_name = classroom_name
        self.current_classroom_code = classroom_code
        self.current_school_year = school_year
        self._update_status()

        col_map = res.get("columnMap")
        if not col_map or 'studentId' not in col_map:
            self.toast.show_message("テーブルを抽出できませんでした")
            return
            
        rows = res.get("rows", [])
        records = []
        skipped_count = 0
        non_summary_count = 0
        for row in rows:
            if len(row) <= max(col_map.values()):
                skipped_count += 1
                continue
                
            student_cell = row[col_map['studentId']]
            div_cell = row[col_map['division']]
            sub_cell = row[col_map['subject']]
            inst_cell = row[col_map['instruction']]
            
            if is_summary_row(student_cell):
                continue
            non_summary_count += 1
                
            student_id_raw = extract_student_id_from_cell(student_cell)
            student_id = normalize_student_id(student_id_raw)
            if not student_id:
                skipped_count += 1
                continue
                
            division = normalize_division(div_cell)
            subject = normalize_subject(sub_cell)
            if not subject:
                skipped_count += 1
                continue
                
            raw_inst = sanitize_raw_instruction(inst_cell)
            
            # create meta_cells
            headers = res.get("headers", [])
            meta_cells = {}
            for i, val in enumerate(row):
                if i not in col_map.values():
                    meta_cells[f"col_{i}"] = val
                    if i < len(headers) and headers[i]:
                        meta_cells[headers[i].strip()] = val

            grade_raw = ""
            if "grade" in col_map and len(row) > col_map["grade"]:
                grade_raw = row[col_map["grade"]]
            elif "学年" in meta_cells:
                grade_raw = meta_cells["学年"]
            elif "grade" in meta_cells:
                grade_raw = meta_cells["grade"]

            student_name = extract_student_name_from_cell(student_cell, student_id)
            grade = normalize_grade(grade_raw)

            meta_cells["生徒"] = student_cell
            meta_cells["student_raw"] = student_cell
            meta_cells["生徒名"] = student_name
            meta_cells["学年"] = grade
                    
            record = CurriculumRecord(
                student_id=student_id,
                student_name=student_name,
                grade=grade,
                division=division,
                subject=subject,
                raw_instruction=raw_inst,
                meta_cells=meta_cells,
                school_year=school_year,
                classroom_code=classroom_code,
                classroom_name=classroom_name,
            )
            records.append(record)

        # 行単位異常の閾値チェック (v9 §36.3)
        total_eval_rows = non_summary_count + skipped_count
        failure_rate = (skipped_count / total_eval_rows) if total_eval_rows > 0 else 0.0
        max_rate = getattr(self.config, "max_row_failure_rate", 0.5)
        if total_eval_rows >= 5 and failure_rate > max_rate:
            self.toast.show_message(
                f"テーブル行の大部分（{skipped_count}/{total_eval_rows}行）でデータ取得に失敗しました。ページ構造を確認してください。"
            )
            logger.warning(
                "行取得失敗率が閾値超過: total=%d, skipped=%d, rate=%.2f, max_rate=%.2f",
                total_eval_rows, skipped_count, failure_rate, max_rate
            )
            return
            
        if not records:
            self.toast.show_message("有効なデータがありません")
            return
            
        undo_rec = self.repository.add_batch(records)
        self.repository.push_undo(undo_rec)
        self.cache_manager.save(self.repository.get_all_records(), __version__)
        
        new_count = len(records)
        # 読み取り件数の妥当性監視・通知 (v8 §11)
        if self.last_page_record_count >= 10 and new_count <= max(1, self.last_page_record_count // 3):
            self.toast.show_message(
                f"今回の読み取り件数（{new_count}件）が前回（{self.last_page_record_count}件）と比べて大幅に少なくなっています。ページ内容を確認してください。"
            )
        else:
            self.toast.show_message(f"{new_count}件を抽出しました ({classroom_name})")
        self.last_page_record_count = new_count
        self._update_title()
        self._update_status()
        
        self.last_url = self.web_view.url().toString(QUrl.UrlFormattingOption.NormalizePathSegments)
        self.last_dom_hash = self._compute_dom_hash(records)
        
        self.transition_wait_elapsed = 0
        self.set_state(AppState.SCREEN_TRANSITION_WAIT)
        self.polling_timer.start()

    def _compute_dom_hash(self, records: list[CurriculumRecord]) -> str:
        content = ""
        for r in records:
            cleaned = clean_instruction(r.raw_instruction)
            m = hashlib.md5(cleaned.encode('utf-8')).hexdigest()
            content += f"{r.student_id}|{r.division}|{r.subject}|{m}\n"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _on_polling(self):
        if self.state != AppState.SCREEN_TRANSITION_WAIT:
            self.polling_timer.stop()
            return
            
        self.transition_wait_elapsed += POLLING_INTERVAL_MS
        if self.transition_wait_elapsed >= SCREEN_TRANSITION_WAIT * 1000:
            self.polling_timer.stop()
            self.set_state(AppState.READY)
            self.toast.show_message("遷移を検知できませんでしたがロックを解除しました")
            return
            
        if self.is_polling_busy:
            return
            
        current_url = self.web_view.url().toString(QUrl.UrlFormattingOption.NormalizePathSegments)
        if current_url != self.last_url:
            self.polling_timer.stop()
            self.set_state(AppState.READY)
            return
            
        self.is_polling_busy = True
        js_path = _get_extract_table_js_path()
        try:
            with open(js_path, 'r', encoding='utf-8') as f:
                js_code = f.read()
        except Exception as e:
            logger.error(f"Failed to read JS for polling: {e}")
            self.is_polling_busy = False
            return
        selectors_json = json.dumps(self.selectors, ensure_ascii=False)
        full_js = f"window.__CURRICULUM_SELECTORS__ = {selectors_json};\n" + js_code
        self.web_view.page().runJavaScript(full_js, self._on_polling_callback)
        
    def _on_polling_callback(self, res: dict):
        self.is_polling_busy = False
        if self.state != AppState.SCREEN_TRANSITION_WAIT:
            return
            
        if not res or not res.get("success"):
            return
            
        col_map = res.get("columnMap")
        if not col_map or 'studentId' not in col_map:
            return
            
        rows = res.get("rows", [])
        records = []
        for row in rows:
            if len(row) <= max(col_map.values()):
                continue
            student_cell = row[col_map['studentId']]
            div_cell = row[col_map['division']]
            sub_cell = row[col_map['subject']]
            inst_cell = row[col_map['instruction']]
            
            if is_summary_row(student_cell):
                continue
                
            student_id = normalize_student_id(extract_student_id_from_cell(student_cell))
            if not student_id: continue
            subject = normalize_subject(sub_cell)
            if not subject: continue
            
            r = CurriculumRecord(student_id, normalize_division(div_cell), subject, sanitize_raw_instruction(inst_cell))
            records.append(r)
            
        current_hash = self._compute_dom_hash(records)
        if current_hash != self.last_dom_hash:
            self.polling_timer.stop()
            self.set_state(AppState.READY)

    def _on_undo(self):
        if self.state != AppState.READY:
            return
        try:
            undo_rec = self.repository.pop_undo()
            self.repository.undo(undo_rec)
            self.cache_manager.save(self.repository.get_all_records(), __version__)
            self._update_title()
            self._update_status()
            self.toast.show_message("直前の抽出を取り消しました")
        except IndexError:
            self.toast.show_message("取消できる履歴がありません")

    def _on_reset(self):
        if self.state != AppState.READY:
            return
        reply = QMessageBox.question(self, "リセット確認", "蓄積したすべてのデータを削除しますか？\nこの操作は元に戻せません。", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.repository.clear()
            self.cache_manager.delete()
            self.current_classroom_name = ""
            self.current_classroom_code = ""
            self.current_school_year = ""
            self._update_title()
            self._update_status()
            self.toast.show_message("データをリセットしました")

    def _on_aggregate(self):
        if self.state != AppState.READY:
            return
        if self.repository.count == 0:
            self.toast.show_message("蓄積されたデータがありません")
            return
            
        reply = QMessageBox.question(
            self, "集計確認",
            f"{self.repository.count:,}件のデータを集計してExcel出力しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        self.set_state(AppState.AGGREGATING)

        # 出力先はユーザーのダウンロードフォルダ (v7 §34)
        from pathlib import Path
        downloads_path = Path.home() / "Downloads"
        if downloads_path.is_dir():
            output_dir = str(downloads_path)
        else:
            output_dir = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
            if getattr(sys, "frozen", False):
                output_dir = os.path.dirname(sys.executable)

        self.loading_overlay.show_loading("集計・Excel出力中", "集計処理を開始しています...", show_progress=True)
        
        snapshot = self.repository.get_snapshot()
        self.worker = AggregationWorker(snapshot, self.config, output_dir)
        self.worker.phase_changed.connect(self._on_worker_phase_changed)
        self.worker.finished.connect(self._on_aggregate_finished)
        self.worker.error_occurred.connect(self._on_aggregate_error)
        self.worker.start()

    def _on_worker_phase_changed(self, phase_name: str, pct: int):
        self.loading_overlay.update_message(f"{phase_name} ({pct}%)", pct)
        self.statusbar.showMessage(f"{phase_name}... {pct}%")

    def _on_aggregate_finished(self, results, target_records, exclusion_stats, csv_filepath, excel_filepath, was_renamed=False):
        self.loading_overlay.hide_loading()
        self.set_state(AppState.READY)
        
        try:
            excel_exists = bool(excel_filepath and os.path.exists(excel_filepath))
            csv_exists = bool(csv_filepath and os.path.exists(csv_filepath))

            if not (excel_exists or csv_exists):
                raise RuntimeError("出力ファイルが生成されませんでした")

            # 成功: cache削除 → Repository clear (v7 §14, v8 §16.4)
            if self.cache_manager.delete():
                self.repository.clear()
                self._update_title()
                self._update_status()

                from core.models import Severity
                crit_cnt = sum(1 for r in results if r.severity == Severity.CRITICAL)
                err_cnt = sum(1 for r in results if r.severity == Severity.ERROR)
                rev_cnt = sum(1 for r in results if r.severity == Severity.REVIEW)
                warn_cnt = sum(1 for r in results if r.severity == Severity.WARNING)
                info_cnt = sum(1 for r in results if r.severity == Severity.INFO)
                pass_cnt = sum(1 for r in results if r.severity == Severity.PASS)
                ex_str = f" (除外{exclusion_stats.total_excluded}件)" if exclusion_stats else ""
                
                if was_renamed:
                    self.toast.show_message("既存ファイルが使用中のため、別名で保存しました。")
                else:
                    self.toast.show_message(
                        f"出力完了: 重大{crit_cnt}件, 要修正{err_cnt}件, 要確認{rev_cnt}件, 警告{warn_cnt}件, 情報{info_cnt}件, 合格{pass_cnt}件{ex_str}"
                    )

                # Explorer連携: Excelファイル、またはCSVファイルを選択状態で開く (v7 §14)
                target_file = excel_filepath if excel_exists else csv_filepath
                if target_file and os.path.exists(target_file):
                    try:
                        subprocess.Popen(
                            ["explorer", "/select,", target_file],
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                    except Exception as e:
                        logger.warning("Explorer起動失敗: %s", e)
            else:
                logger.error("cache削除に失敗しました")
                QMessageBox.warning(
                    self, "警告",
                    "ファイルは出力されましたが、キャッシュの削除に失敗しました。"
                )
        except Exception as e:
            logger.error("集計出力失敗: %s", e)
            QMessageBox.critical(self, "出力エラー", f"ファイルの出力に失敗しました:\n{e}")

    def _on_aggregate_error(self, err_msg):
        self.loading_overlay.hide_loading()
        self.set_state(AppState.READY)
        QMessageBox.critical(self, "集計エラー", err_msg)

    def _on_renderer_crash(self, terminationStatus, exitCode):
        """仕様書 §33: Renderer crash検知。"""
        logger.error(
            "ブラウザエンジンがクラッシュしました (status=%s, code=%s)",
            terminationStatus, exitCode,
        )
        QMessageBox.critical(
            self, "致命的エラー",
            "ブラウザエンジンがクラッシュしました。アプリを再起動してください。",
        )
        self.is_shutting_down = True
        self.close()

    def _on_download_requested(self, download):
        """仕様書 §37: すべてのダウンロードをキャンセル。"""
        download.cancel()
        self.toast.show_message(
            "本ブラウザからのファイルダウンロードは無効化されています"
        )

    def _on_context_menu(self, pos):
        """仕様書 §36: 右クリックメニューは コピー/戻る/進む/再読み込み のみ。"""
        menu = QMenu(self)

        # コピー (選択テキストがない場合disabled)
        copy_action = menu.addAction("コピー")
        copy_action.triggered.connect(
            lambda: self.web_view.page().triggerAction(
                QWebEnginePage.WebAction.Copy
            )
        )
        copy_action.setEnabled(self.web_view.hasSelection())

        menu.addSeparator()

        # 戻る
        back_action = menu.addAction("戻る")
        back_action.triggered.connect(self._go_back)
        back_action.setEnabled(self.web_view.history().canGoBack())

        # 進む
        forward_action = menu.addAction("進む")
        forward_action.triggered.connect(self._go_forward)
        forward_action.setEnabled(self.web_view.history().canGoForward())

        # 再読み込み
        reload_action = menu.addAction("再読み込み")
        reload_action.triggered.connect(self._reload)

        menu.exec(self.web_view.mapToGlobal(pos))

    def resizeEvent(self, event):
        """リサイズ時にトーストとローディングマスクの位置を更新する。"""
        super().resizeEvent(event)
        if hasattr(self, 'loading_overlay') and self.loading_overlay:
            self.loading_overlay.resize(self.centralWidget().size())
        self.toast.on_parent_resize()

    def closeEvent(self, event):
        """仕様書 §32: 終了処理。"""
        if self.repository.count > 0:
            reply = QMessageBox.question(
                self, "終了確認",
                "未保存のデータがあるため終了すると消失します。\n終了しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        self.is_shutting_down = True
        self.polling_timer.stop()
        self.load_timeout_timer.stop()
        event.accept()

class CustomWebPage(QWebEnginePage):
    """カスタムWebEngineページ。

    仕様書 §10.3, §10.4, §36:
    - JSダイアログ制御
    - window.open/targetの統合
    - ナビゲーション制御
    - カスタムコンテキストメニュー
    """

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)

    def javaScriptAlert(self, securityOrigin, msg):
        """仕様書 §10.3: alert最大500文字、超過時は末尾...で省略"""
        if len(msg) > 500:
            msg = msg[:497] + "..."
        QMessageBox.information(self.view(), "Alert", msg)

    def javaScriptConfirm(self, securityOrigin, msg):
        """仕様書 §10.3: confirm OK=true / Cancel=false"""
        reply = QMessageBox.question(
            self.view(), "Confirm", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def javaScriptPrompt(self, securityOrigin, msg, defaultText):
        """仕様書 §10.3: prompt Cancel→null相当"""
        text, ok = QInputDialog.getText(
            self.view(), "Prompt", msg, text=defaultText
        )
        return (True, text) if ok else (False, "")

    def createWindow(self, _type):
        """仕様書 §10.4: 新規Window作らず同一ページへ統合"""
        return self

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        """仕様書 §10.4: http/https/file以外を拒否"""
        scheme = url.scheme().lower()
        if scheme in ("javascript", "data", "blob"):
            return False
        if scheme not in ("http", "https", "file"):
            return False
        return True

