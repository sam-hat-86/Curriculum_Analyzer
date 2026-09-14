"""起動時案内ダイアログ (v7 §11.1)。"""
import json
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


def _ensure_check_icon() -> str:
    """チェックマーク用SVGアイコンのパスを取得・生成する。"""
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(assets_dir, exist_ok=True)
    icon_path = os.path.join(assets_dir, "check.svg")
    if not os.path.exists(icon_path):
        svg_content = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
            '<path fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" '
            'd="M3 8.5l3.5 3.5L13 4"/>'
            '</svg>'
        )
        try:
            with open(icon_path, "w", encoding="utf-8") as f:
                f.write(svg_content)
        except Exception:
            pass
    return icon_path.replace("\\", "/")


class StartupGuideDialog(QDialog):
    """起動時に操作手順を案内するダイアログ。"""

    def __init__(self, parent=None, user_data_dir: str = ""):
        super().__init__(parent)
        self.user_data_dir = user_data_dir
        self.settings_file = os.path.join(user_data_dir, "guide_settings.json") if user_data_dir else ""
        self.setWindowTitle("授業指示書・カリキュラム 精査ブラウザシステム - 使い方ガイド")
        self.setFixedSize(560, 480)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title_label = QLabel("授業指示書・カリキュラム 精査システム - 使い方ガイド", self)
        title_label.setStyleSheet("""
            QLabel {
                font-family: 'Meiryo UI', sans-serif;
                font-size: 15px;
                font-weight: bold;
                color: #0D3A66;
                background: transparent;
            }
        """)
        layout.addWidget(title_label)

        guide_browser = QTextBrowser(self)
        guide_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #F8FAFC;
                color: #1A202C;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 14px;
            }
        """)
        guide_browser.setHtml("""
        <div style="font-family: 'Meiryo UI', sans-serif; font-size: 13px; line-height: 1.7; color: #1A202C;">
            <p style="margin-top: 0; font-size: 14px; font-weight: bold; color: #0F172A; border-bottom: 2px solid #0D3A66; padding-bottom: 4px;">
                【基本的な使い方】
            </p>
            <ol style="margin-left: 20px; padding-left: 4px; margin-bottom: 14px; color: #1E293B;">
                <li style="margin-bottom: 6px;">ブラウザで対象の授業指示書・カリキュラム画面を表示します。</li>
                <li style="margin-bottom: 6px;">
                    ツールバーの <b style="color: #0D3A66; background-color: #E2E8F0; padding: 2px 6px; border-radius: 3px;">「このページを読み取る (F9)」</b> ボタンを押してデータを蓄積します。<br>
                    <span style="color: #475569; font-size: 12px;">※ 画面遷移や検索条件変更を行いながら、複数ページを繰り返し蓄積できます。</span>
                </li>
                <li style="margin-bottom: 6px;">
                    蓄積が完了したら <b style="color: #0D3A66; background-color: #E2E8F0; padding: 2px 6px; border-radius: 3px;">「集計してExcel出力」</b> ボタンを押します。
                </li>
                <li style="margin-bottom: 4px;">自動的に精査・判定が行われ、ExcelファイルおよびCSVファイルが出力されます。</li>
            </ol>

            <p style="margin-top: 14px; font-size: 14px; font-weight: bold; color: #0F172A; border-bottom: 2px solid #0D3A66; padding-bottom: 4px;">
                【ショートカットキー】
            </p>
            <ul style="margin-left: 20px; padding-left: 4px; list-style-type: square; color: #1E293B;">
                <li style="margin-bottom: 5px;">
                    <span style="background-color: #EDF2F7; color: #0F172A; border: 1px solid #CBD5E1; border-radius: 3px; padding: 1px 6px; font-weight: bold; font-family: monospace;">F9</span>
                    ： 現在のページを読み取り・蓄積
                </li>
                <li style="margin-bottom: 5px;">
                    <span style="background-color: #EDF2F7; color: #0F172A; border: 1px solid #CBD5E1; border-radius: 3px; padding: 1px 6px; font-weight: bold; font-family: monospace;">Ctrl + Z</span>
                    ： 直前の読み取りを取り消し
                </li>
                <li style="margin-bottom: 5px;">
                    <span style="background-color: #EDF2F7; color: #0F172A; border: 1px solid #CBD5E1; border-radius: 3px; padding: 1px 6px; font-weight: bold; font-family: monospace;">Ctrl + Enter</span>
                    ： 集計してExcel出力
                </li>
                <li style="margin-bottom: 2px;">
                    <span style="background-color: #EDF2F7; color: #0F172A; border: 1px solid #CBD5E1; border-radius: 3px; padding: 1px 6px; font-weight: bold; font-family: monospace;">F5</span>
                    ： 画面の再読み込み
                </li>
            </ul>
        </div>
        """)
        layout.addWidget(guide_browser)

        # 区切り線
        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none;")
        layout.addWidget(divider)

        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 4, 0, 0)

        check_icon_url = _ensure_check_icon()
        self.checkbox_hide = QCheckBox("次回からこの案内を表示しない", self)
        self.checkbox_hide.setStyleSheet(f"""
            QCheckBox {{
                font-family: 'Meiryo UI', sans-serif;
                font-size: 13px;
                font-weight: 500;
                color: #1E293B;
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid #475569;
                border-radius: 4px;
                background-color: #FFFFFF;
            }}
            QCheckBox::indicator:hover {{
                border-color: #1F4E78;
                background-color: #F8FAFC;
            }}
            QCheckBox::indicator:checked {{
                background-color: #1F4E78;
                border: 2px solid #1F4E78;
                image: url("{check_icon_url}");
            }}
        """)
        bottom_layout.addWidget(self.checkbox_hide)

        bottom_layout.addStretch()

        btn_close = QPushButton("閉じる", self)
        btn_close.setFixedWidth(110)
        btn_close.setFixedHeight(36)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #1F4E78;
                color: #FFFFFF;
                font-family: 'Meiryo UI', sans-serif;
                font-size: 13px;
                font-weight: bold;
                border-radius: 5px;
                border: 1px solid #163857;
            }
            QPushButton:hover {
                background-color: #163857;
                border-color: #0F2942;
            }
            QPushButton:pressed {
                background-color: #0F2942;
            }
        """)
        btn_close.clicked.connect(self._on_close)
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

    @classmethod
    def should_show(cls, user_data_dir: str) -> bool:
        if not user_data_dir:
            return True
        path = os.path.join(user_data_dir, "guide_settings.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return not data.get("hide_startup_guide", False)
            except Exception:
                return True
        return True

    def _on_close(self):
        if self.checkbox_hide.isChecked() and self.user_data_dir:
            try:
                os.makedirs(self.user_data_dir, exist_ok=True)
                with open(self.settings_file, "w", encoding="utf-8") as f:
                    json.dump({"hide_startup_guide": True}, f)
            except Exception:
                pass
        self.accept()
