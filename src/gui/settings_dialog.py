"""
GUI 設定変更ダイアログ (仕様書§35)
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDoubleSpinBox,
    QLineEdit, QPushButton, QFileDialog, QFormLayout, QDialogButtonBox, QMessageBox
)
from src.utils.config import AppConfig
from src.utils.constants import APP_VERSION

class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(f"システム設定 (v{APP_VERSION})")
        self.resize(480, 380)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 解析Worker数 (仕様書§6: 2〜4)
        self.sb_workers = QSpinBox(self)
        self.sb_workers.setRange(1, 8)
        self.sb_workers.setValue(self.config.worker_threads)
        form.addRow("HTML解析Worker数 (推奨 2〜4):", self.sb_workers)

        # Webアクセス間隔 (秒)
        self.dsb_interval = QDoubleSpinBox(self)
        self.dsb_interval.setRange(0.2, 10.0)
        self.dsb_interval.setSingleStep(0.5)
        self.dsb_interval.setValue(self.config.request_interval_sec)
        form.addRow("Webアクセス間隔 (秒):", self.dsb_interval)

        # 最大リトライ回数
        self.sb_retries = QSpinBox(self)
        self.sb_retries.setRange(0, 10)
        self.sb_retries.setValue(self.config.max_retries)
        form.addRow("最大リトライ回数:", self.sb_retries)

        # Excel中間保存間隔 (件)
        self.sb_checkpoint = QSpinBox(self)
        self.sb_checkpoint.setRange(10, 1000)
        self.sb_checkpoint.setSingleStep(50)
        self.sb_checkpoint.setValue(self.config.checkpoint_interval)
        form.addRow("Excel中間保存間隔 (件):", self.sb_checkpoint)

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
        self.txt_start_url.setPlaceholderText("https://... (未設定時は about:blank)")
        form.addRow("初期表示URL (任意):", self.txt_start_url)

        layout.addLayout(form)

        # ボタン
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self
        )
        buttons.accepted.connect(self._save_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "出力先フォルダを選択", self.txt_out_dir.text())
        if dir_path:
            self.txt_out_dir.setText(dir_path)

    def _save_settings(self):
        self.config.worker_threads = self.sb_workers.value()
        self.config.request_interval_sec = self.dsb_interval.value()
        self.config.max_retries = self.sb_retries.value()
        self.config.checkpoint_interval = self.sb_checkpoint.value()
        self.config.output_dir = self.txt_out_dir.text()
        self.config.start_url = self.txt_start_url.text().strip()
        self.config.save()
        self.accept()
