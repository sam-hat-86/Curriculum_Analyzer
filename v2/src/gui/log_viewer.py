"""
GUI リアルタイムログビューア & 使い方表示コンポーネント (v2.3.1)
QStackedWidget による「使い方」と「ログ」の非破壊切り替えをサポート。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton, QCheckBox, QStackedWidget
)
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtCore import Qt, Signal, QObject
from src.gui.icons import get_mdi_icon


class LogSignalEmitter(QObject):
    log_received = Signal(str, str)


HELP_HTML_CONTENT = """
<div style="padding: 14px 20px; font-family: 'Segoe UI', 'Meiryo', sans-serif;">
    <h3 style="color: #4FC1FF; border-bottom: 2px solid #007ACC; padding-bottom: 6px; margin-top: 0; margin-bottom: 12px; font-size: 18px;">
        使い方
    </h3>
    <p style="margin: 8px 0; color: #F0F0F0; font-weight: bold; font-size: 14px;">
        <span style="color: #107C41; font-size: 16px; margin-right: 4px;">1.</span>ログインする
    </p>
    <p style="margin: 8px 0; color: #F0F0F0; font-weight: bold; font-size: 14px;">
        <span style="color: #107C41; font-size: 16px; margin-right: 4px;">2.</span>「生徒カリキュラム一覧」にアクセス
    </p>
    <p style="margin: 8px 0; color: #F0F0F0; font-weight: bold; font-size: 14px;">
        <span style="color: #107C41; font-size: 16px; margin-right: 4px;">3.</span>在籍区分・受講区分を選択<br>
        <span style="color: #A0A0A0; font-weight: normal; font-size: 12px;">（必要であれば教室指定・BM,AMは巡回時不要）</span>
    </p>
    <p style="margin: 8px 0; color: #F0F0F0; font-weight: bold; font-size: 14px;">
        <span style="color: #107C41; font-size: 16px; margin-right: 4px;">4.</span>「処理開始」をクリック<br>
        <span style="color: #A0A0A0; font-weight: normal; font-size: 12px;">（BM,AMは「教室巡回開始」をクリック）</span>
    </p>
</div>
"""


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
        tb_layout.setContentsMargins(4, 2, 4, 4)

        self.auto_scroll_cb = QCheckBox("自動スクロール", self)
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.stateChanged.connect(self._on_auto_scroll_changed)
        tb_layout.addWidget(self.auto_scroll_cb)

        tb_layout.addStretch()

        # 使い方 / ログ切替ボタン
        self.toggle_view_btn = QPushButton(" ログ表示", self)
        self.toggle_view_btn.setIcon(get_mdi_icon("view_list"))
        self.toggle_view_btn.setStyleSheet("min-height: 28px; padding: 2px 10px; font-size: 12px;")
        self.toggle_view_btn.clicked.connect(self.toggle_view)
        tb_layout.addWidget(self.toggle_view_btn)

        # ログクリアボタン
        self.clear_btn = QPushButton(" ログクリア", self)
        self.clear_btn.setIcon(get_mdi_icon("delete_sweep"))
        self.clear_btn.setStyleSheet("min-height: 28px; padding: 2px 10px; font-size: 12px;")
        self.clear_btn.clicked.connect(self.clear)
        tb_layout.addWidget(self.clear_btn)

        layout.addLayout(tb_layout)

        # QStackedWidget によるビュー管理 (0: 使い方, 1: ログ)
        self.stacked_widget = QStackedWidget(self)

        # --- ページ 0: 使い方 ---
        self.help_edit = QTextEdit(self)
        self.help_edit.setReadOnly(True)
        self.help_edit.setStyleSheet(
            "background-color: #181818; color: #E0E0E0; border: 1px solid #3E3E42; border-radius: 4px;"
        )
        self.help_edit.setHtml(HELP_HTML_CONTENT)
        self.stacked_widget.addWidget(self.help_edit)

        # --- ページ 1: リアルタイムログ ---
        self.log_edit = QTextEdit(self)
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        self.log_edit.setStyleSheet(
            "background-color: #181818; color: #E0E0E0; border: 1px solid #3E3E42; border-radius: 4px; padding: 4px;"
        )
        self.stacked_widget.addWidget(self.log_edit)

        layout.addWidget(self.stacked_widget)

        # 初期表示は「使い方」
        self.switch_to_help()

    def switch_to_help(self):
        """使い方ページを表示し、ツールバーの不要項目を非表示にする"""
        self.stacked_widget.setCurrentIndex(0)
        self.auto_scroll_cb.setVisible(False)
        self.clear_btn.setVisible(False)
        self.toggle_view_btn.setText(" ログ表示")
        self.toggle_view_btn.setIcon(get_mdi_icon("view_list"))
        self.toggle_view_btn.setToolTip("実行ログの表示に切り替えます")

    def switch_to_log(self):
        """ログページを表示し、ツールバーの全項目を表示する"""
        self.stacked_widget.setCurrentIndex(1)
        self.auto_scroll_cb.setVisible(True)
        self.clear_btn.setVisible(True)
        self.toggle_view_btn.setText(" 使い方")
        self.toggle_view_btn.setIcon(get_mdi_icon("help_outline"))
        self.toggle_view_btn.setToolTip("使い方（操作手順）の表示に切り替えます")

    def toggle_view(self):
        """使い方とログ表示をトグル切り替え"""
        if self.stacked_widget.currentIndex() == 0:
            self.switch_to_log()
        else:
            self.switch_to_help()

    @property
    def is_showing_help(self) -> bool:
        return self.stacked_widget.currentIndex() == 0

    def append_log(self, message: str, level: str = "INFO"):
        """ログを追加する（常にログ用QTextEditに記録され、破棄されない）"""
        if level == "DEBUG":
            return

        import re
        clean_msg = re.sub(r"https?://[^\s\"'>)]+", "", message)
        clean_msg = re.sub(r"\s{2,}", " ", clean_msg).strip()

        color = "#ECEFF4"
        if level == "WARNING":
            color = "#EBCB8B"
        elif level in ["ERROR", "CRITICAL"]:
            color = "#BF616A"
        elif "完了" in clean_msg or "成功" in clean_msg:
            color = "#A3BE8C"

        safe_msg = clean_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f"<div style='color: {color}; margin: 2px 0; line-height: 1.4;'>{safe_msg}</div>"
        self.log_edit.append(html)

        if self.auto_scroll:
            self.log_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _on_auto_scroll_changed(self, state):
        self.auto_scroll = (state == Qt.CheckState.Checked.value)

    def clear(self):
        """ログをクリアする"""
        self.log_edit.clear()
