"""ローディングオーバーレイウィジェット。
ブラウザ領域を半透明マスクで覆い、操作をロックしながら進捗を表示する。
"""
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar


class LoadingOverlay(QWidget):
    """ブラウザ中央に表示し全操作をロックするローディングマスク。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 120);")

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.box = QWidget(self)
        self.box.setFixedWidth(400)
        self.box.setStyleSheet("""
            QWidget {
                background-color: #FFFFFF;
                border-radius: 10px;
                border: 2px solid #1F4E78;
            }
        """)
        box_layout = QVBoxLayout(self.box)
        box_layout.setContentsMargins(24, 24, 24, 24)
        box_layout.setSpacing(14)
        box_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label_title = QLabel("シミュレーションシート取得中...", self.box)
        self.label_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F4E78; border: none;")
        self.label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(self.label_title)

        self.progress_bar = QProgressBar(self.box)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #CCCCCC;
                border-radius: 5px;
                text-align: center;
                height: 22px;
                background-color: #F0F0F0;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #1F4E78;
                border-radius: 4px;
            }
        """)
        box_layout.addWidget(self.progress_bar)

        self.label_message = QLabel("しばらくお待ちください", self.box)
        self.label_message.setStyleSheet("font-size: 13px; font-weight: 500; color: #1E293B; border: none;")
        self.label_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(self.label_message)

        main_layout.addWidget(self.box)
        self.hide()

    def show_loading(self, title: str, message: str = "しばらくお待ちください", show_progress: bool = True):
        self.label_title.setText(title)
        self.label_message.setText(message)
        self.progress_bar.setVisible(show_progress)
        self.progress_bar.setValue(0)
        p = self.parentWidget()
        if p is not None:
            self.resize(p.size())
        self.show()
        self.raise_()

    def update_message(self, message: str, pct: int = -1):
        self.label_message.setText(message)
        if pct >= 0:
            self.progress_bar.setValue(pct)

    def hide_loading(self):
        self.hide()
