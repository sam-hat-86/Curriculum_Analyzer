"""
GUI リアルタイムログビューア
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton, QCheckBox
from PySide6.QtGui import QFont, QTextCursor, QColor
from PySide6.QtCore import Qt, Signal, QObject

class LogSignalEmitter(QObject):
    log_received = Signal(str, str)

class LogViewerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.auto_scroll = True
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ツールバー
        tb_layout = QHBoxLayout()
        self.auto_scroll_cb = QCheckBox("自動スクロール", self)
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.stateChanged.connect(self._on_auto_scroll_changed)
        tb_layout.addWidget(self.auto_scroll_cb)

        tb_layout.addStretch()

        self.clear_btn = QPushButton("ログクリア", self)
        self.clear_btn.clicked.connect(self.clear)
        tb_layout.addWidget(self.clear_btn)

        layout.addLayout(tb_layout)

        # テキストエリア
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 9))
        self.text_edit.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.text_edit)

    def append_log(self, message: str, level: str = "INFO"):
        color = "#D4D4D4"
        if level == "WARNING":
            color = "#CCA700"
        elif level in ["ERROR", "CRITICAL"]:
            color = "#F44747"
        elif level == "DEBUG":
            color = "#808080"

        # HTMLタグエスケープ
        safe_msg = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f"<span style='color: {color};'>{safe_msg}</span>"
        self.text_edit.append(html)

        if self.auto_scroll:
            self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _on_auto_scroll_changed(self, state):
        self.auto_scroll = (state == Qt.CheckState.Checked.value)

    def clear(self):
        self.text_edit.clear()
