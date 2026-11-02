"""
GUI 設定変更ダイアログ (仕様書§35)
"""
from typing import Callable, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSpinBox, QDoubleSpinBox,
    QLineEdit, QPushButton, QFileDialog, QFormLayout, QDialogButtonBox,
    QCheckBox, QLabel
)
from src.gui.icons import get_mdi_icon
from src.utils.config import AppConfig
from src.utils.constants import APP_VERSION


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        parent=None,
        on_check_update: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.config = config
        self.on_check_update = on_check_update
        self.setWindowTitle(f"システム設定 (v{APP_VERSION})")
        self.resize(500, 380)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 解析Worker数 (仕様書§6: 2〜4)
        self.sb_workers = QSpinBox(self)
        self.sb_workers.setRange(1, 8)
        self.sb_workers.setValue(self.config.worker_threads)
        form.addRow("HTML解析Worker数 (推奨 2〜4):", self.sb_workers)

        # 同時取得タブ数 (1〜4タブ)
        self.sb_tabs = QSpinBox(self)
        self.sb_tabs.setRange(1, 4)
        self.sb_tabs.setValue(self.config.max_tabs)
        form.addRow("同時取得タブ数 (推奨 2タブ):", self.sb_tabs)

        # Webアクセス間隔 (秒)
        self.dsb_interval = QDoubleSpinBox(self)
        self.dsb_interval.setRange(0.1, 5.0)
        self.dsb_interval.setSingleStep(0.1)
        self.dsb_interval.setValue(self.config.request_interval_sec)
        form.addRow("リクエスト間隔 (秒):", self.dsb_interval)

        # シート描画安定待機 (秒)
        self.dsb_render_delay = QDoubleSpinBox(self)
        self.dsb_render_delay.setRange(0.1, 5.0)
        self.dsb_render_delay.setSingleStep(0.1)
        self.dsb_render_delay.setValue(self.config.sheet_render_delay_sec)
        form.addRow("シート描画安定待機 (秒):", self.dsb_render_delay)

        # 最大リトライ回数
        self.sb_retries = QSpinBox(self)
        self.sb_retries.setRange(0, 10)
        self.sb_retries.setValue(self.config.max_retries)
        form.addRow("最大リトライ回数:", self.sb_retries)

        # 出力先フォルダ
        out_layout = QHBoxLayout()
        self.txt_out_dir = QLineEdit(self.config.output_dir, self)
        self.btn_browse = QPushButton("参照...", self)
        self.btn_browse.clicked.connect(self._browse_dir)
        out_layout.addWidget(self.txt_out_dir)
        out_layout.addWidget(self.btn_browse)
        form.addRow("Excel出力先フォルダ:", out_layout)

        # 初期表示URL
        self.txt_start_url = QLineEdit(self.config.start_url, self)
        self.txt_start_url.setPlaceholderText("http://... (未設定時は about:blank)")
        form.addRow("初期表示URL (任意):", self.txt_start_url)

        # 原文シート出力オプション
        self.chk_export_raw = QCheckBox("原文シートを出力する (HTMLソース確認・デバッグ用)", self)
        self.chk_export_raw.setChecked(self.config.export_raw_sheet)
        form.addRow("特殊シート出力:", self.chk_export_raw)

        # バージョン情報・ソフト更新確認
        update_layout = QHBoxLayout()
        self.lbl_version = QLabel(text=f"現在のバージョン: v{APP_VERSION}", parent=self)
        self.btn_check_update = QPushButton(" 更新を確認", self)
        self.btn_check_update.setIcon(get_mdi_icon("refresh"))
        self.btn_check_update.clicked.connect(self._trigger_update_check)
        update_layout.addWidget(self.lbl_version)
        update_layout.addStretch(1)
        update_layout.addWidget(self.btn_check_update)
        form.addRow("ソフト更新:", update_layout)

        layout.addLayout(form)

        # ボタン
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self
        )
        buttons.accepted.connect(self._save_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _trigger_update_check(self):
        if callable(self.on_check_update):
            self.on_check_update()
        else:
            parent_obj = self.parent()
            if parent_obj is not None and hasattr(parent_obj, "run_update_check"):
                check_func = getattr(parent_obj, "run_update_check")
                check_func(is_manual=True)

    def _browse_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "出力先フォルダを選択", self.txt_out_dir.text())
        if dir_path:
            self.txt_out_dir.setText(dir_path)

    def _save_settings(self):
        self.config.worker_threads = self.sb_workers.value()
        self.config.max_tabs = self.sb_tabs.value()
        self.config.request_interval_sec = self.dsb_interval.value()
        self.config.sheet_render_delay_sec = self.dsb_render_delay.value()
        self.config.max_retries = self.sb_retries.value()
        self.config.output_dir = self.txt_out_dir.text()
        self.config.start_url = self.txt_start_url.text().strip()
        self.config.export_raw_sheet = self.chk_export_raw.isChecked()
        self.config.save()
        self.accept()
