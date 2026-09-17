"""トースト通知ウィジェット。

仕様書 §38.5:
- 最大1件
- 新規発生で即上書き
- 中央下部固定
- mouse transparent
- 最大80文字程度
- 超過時末尾...
- OS通知は使用しない
"""

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QWidget


class ToastWidget(QLabel):
    """中央下部に表示されるトースト通知。"""

    MAX_LENGTH: int = 80
    DEFAULT_DURATION_MS: int = 4000
    FADE_DURATION_MS: int = 300

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

        self._setup_style()
        self.hide()

        # mouse transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def _setup_style(self) -> None:
        """スタイルの初期設定。"""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)

        font = QFont()
        font.setPointSize(11)
        self.setFont(font)

        self.setStyleSheet(
            """
            QLabel {
                background-color: rgba(50, 50, 50, 220);
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                margin: 10px;
            }
            """
        )

    def show_message(self, message: str, duration_ms: int = DEFAULT_DURATION_MS) -> None:
        """トーストメッセージを表示する。

        Args:
            message: 表示するメッセージ
            duration_ms: 表示時間（ミリ秒）
        """
        # 既存のタイマーを停止
        self._timer.stop()

        # 最大80文字に切り詰め
        if len(message) > self.MAX_LENGTH:
            message = message[:self.MAX_LENGTH - 1] + "..."

        self.setText(message)
        self.adjustSize()
        self._reposition()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()

        # タイマー設定
        self._timer.start(duration_ms)

    def _reposition(self) -> None:
        """親ウィジェット内で中央下部に配置する。"""
        parent = self.parentWidget()
        if parent is None:
            return

        parent_rect = parent.rect()
        self_width = min(self.sizeHint().width() + 40, parent_rect.width() - 40)
        self_height = self.sizeHint().height() + 20

        x = (parent_rect.width() - self_width) // 2
        y = parent_rect.height() - self_height - 60

        self.setGeometry(x, y, self_width, self_height)

    def _fade_out(self) -> None:
        """フェードアウトして非表示にする。"""
        self.hide()

    def on_parent_resize(self) -> None:
        """親ウィジェットのリサイズ時に再配置する。"""
        if self.isVisible():
            self._reposition()
