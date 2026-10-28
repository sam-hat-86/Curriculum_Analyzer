"""
GUI リアルタイムログビューア
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton, QCheckBox
from PySide6.QtGui import QFont, QTextCursor
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

        self.clear_btn = QPushButton("🗑 ログクリア", self)
        self.clear_btn.setStyleSheet("min-height: 28px; padding: 2px 12px; font-size: 12px;")
        self.clear_btn.clicked.connect(self.clear)
        tb_layout.addWidget(self.clear_btn)

        layout.addLayout(tb_layout)

        # テキストエリア
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 9))
        self.text_edit.setStyleSheet("background-color: #181818; color: #E0E0E0; border: 1px solid #3E3E42; border-radius: 4px; padding: 4px;")
        layout.addWidget(self.text_edit)

    def append_log(self, message: str, level: str = "INFO"):
        if level == "DEBUG":
            # GUIにはDEBUGレベルの詳細な内部技術ログは表示せずノイズを抑止
            return

        import re
        # URLを念のため二重除去
        clean_msg = re.sub(r"https?://[^\s\"'>)]+", "", message)
        clean_msg = re.sub(r"\s{2,}", " ", clean_msg).strip()

        color = "#ECEFF4"
        if level == "WARNING":
            color = "#EBCB8B"
        elif level in ["ERROR", "CRITICAL"]:
            color = "#BF616A"
        elif "完了" in clean_msg or "成功" in clean_msg:
            color = "#A3BE8C"

        # HTMLタグエスケープ
        safe_msg = clean_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f"<div style='color: {color}; margin: 2px 0; line-height: 1.4;'>{safe_msg}</div>"
        self.text_edit.append(html)

        if self.auto_scroll:
            self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _on_auto_scroll_changed(self, state):
        self.auto_scroll = (state == Qt.CheckState.Checked.value)

    def clear(self):
        self.text_edit.clear()
