"""
GUI 処理進捗・統計表示パネル (仕様書§36)
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QGridLayout, QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class ProgressPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # グループボックス
        group = QGroupBox("処理ステータス", self)
        g_layout = QVBoxLayout(group)

        # 現在処理中の対象
        curr_layout = QHBoxLayout()
        curr_title = QLabel("処理中対象:", self)
        curr_title.setStyleSheet("font-weight: bold;")
        self.current_label = QLabel("待機中", self)
        self.current_label.setStyleSheet("color: #0078D7;")
        curr_layout.addWidget(curr_title)
        curr_layout.addWidget(self.current_label, 1)
        g_layout.addLayout(curr_layout)

        # プログレスバー
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #C0C0C0;
                border-radius: 4px;
                text-align: center;
                height: 22px;
            }
            QProgressBar::chunk {
                background-color: #107C41;
            }
        """)
        g_layout.addWidget(self.progress_bar)

        # カウンターグリッド
        grid = QGridLayout()
        grid.setContentsMargins(0, 5, 0, 0)

        self.lbl_total = QLabel("総件数: 0", self)
        self.lbl_fetched = QLabel("取得件数: 0", self)
        self.lbl_parsed = QLabel("解析件数: 0", self)
        self.lbl_saved = QLabel("保存件数: 0", self)
        self.lbl_success = QLabel("成功: 0", self)
        self.lbl_error = QLabel("エラー: 0", self)
        self.lbl_error.setStyleSheet("color: #D83B01; font-weight: bold;")

        grid.addWidget(self.lbl_total, 0, 0)
        grid.addWidget(self.lbl_fetched, 0, 1)
        grid.addWidget(self.lbl_parsed, 0, 2)
        grid.addWidget(self.lbl_saved, 1, 0)
        grid.addWidget(self.lbl_success, 1, 1)
        grid.addWidget(self.lbl_error, 1, 2)

        g_layout.addLayout(grid)
        layout.addWidget(group)

    def update_status(
        self,
        current_item: str,
        total: int,
        fetched: int,
        parsed: int,
        saved: int,
        failed: int
    ):
        self.current_label.setText(current_item)
        self.lbl_total.setText(f"総件数: {total}")
        self.lbl_fetched.setText(f"取得件数: {fetched}")
        self.lbl_parsed.setText(f"解析件数: {parsed}")
        self.lbl_saved.setText(f"保存件数: {saved}")
        self.lbl_success.setText(f"成功: {saved}")
        self.lbl_error.setText(f"エラー: {failed}")

        if total > 0:
            pct = int((saved / total) * 100)
            self.progress_bar.setValue(min(100, pct))
            self.progress_bar.setFormat(f"{saved} / {total} ({pct}%)")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0 / 0 (0%)")
