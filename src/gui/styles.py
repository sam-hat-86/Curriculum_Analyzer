"""
ダークテーマ用スタイルシートおよびパレット定義
"""
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

DARK_STYLE_SHEET = """
/* 全体基本スタイル */
QWidget {
    background-color: #1E1E1E;
    color: #E0E0E0;
    font-size: 13px;
    selection-background-color: #264F78;
    selection-color: #FFFFFF;
}

/* ダイアログ */
QDialog {
    background-color: #1E1E1E;
    color: #E0E0E0;
}

/* ラベル */
QLabel {
    color: #E0E0E0;
    background-color: transparent;
}

/* 通常プッシュボタン */
QPushButton {
    background-color: #2D2D30;
    color: #F0F0F0;
    border: 1px solid #3E3E42;
    border-radius: 4px;
    padding: 5px 12px;
    min-height: 22px;
}

QPushButton:hover {
    background-color: #3E3E42;
    border-color: #007ACC;
}

QPushButton:pressed {
    background-color: #0E639C;
    border-color: #007ACC;
}

QPushButton:disabled {
    background-color: #252526;
    color: #6D6D6D;
    border-color: #2D2D30;
}

/* テキスト入力・数値入力 */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #252526;
    color: #FFFFFF;
    border: 1px solid #3E3E42;
    border-radius: 4px;
    padding: 4px 6px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #007ACC;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #2D2D30;
    border: none;
    width: 16px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #3E3E42;
}

/* チェックボックス */
QCheckBox {
    color: #E0E0E0;
    background-color: transparent;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3E3E42;
    border-radius: 3px;
    background-color: #252526;
}

QCheckBox::indicator:checked {
    background-color: #007ACC;
    border-color: #007ACC;
}

/* グループボックス */
QGroupBox {
    border: 1px solid #3E3E42;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 12px;
    font-weight: bold;
    color: #4FC1FF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #4FC1FF;
}

/* プログレスバー */
QProgressBar {
    background-color: #252526;
    border: 1px solid #3E3E42;
    border-radius: 4px;
    text-align: center;
    color: #FFFFFF;
    font-weight: bold;
    height: 22px;
}

QProgressBar::chunk {
    background-color: #107C41;
    border-radius: 3px;
}

/* テキストエリア / ログビューア */
QTextEdit {
    background-color: #181818;
    color: #D4D4D4;
    border: 1px solid #3E3E42;
    border-radius: 4px;
}

/* スプリッター */
QSplitter::handle {
    background-color: #2D2D30;
}

QSplitter::handle:hover {
    background-color: #007ACC;
}

/* スクロールバー */
QScrollBar:vertical {
    border: none;
    background: #1E1E1E;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3E3E42;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #1E1E1E;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #3E3E42;
    min-width: 20px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: #555555;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ステータスバー */
QStatusBar {
    background-color: #007ACC;
    color: #FFFFFF;
    font-weight: normal;
}

QStatusBar QLabel {
    color: #FFFFFF;
}

/* ツールチップ */
QToolTip {
    background-color: #252526;
    color: #FFFFFF;
    border: 1px solid #3E3E42;
    padding: 4px;
}
"""

def setup_dark_theme(app):
    """
    QApplicationにダークパレットとダークスタイルシートを適用する
    """
    # QPaletteの設定 (ネイティブダイアログや描画の一貫性を担保)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1E1E1E"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#E0E0E0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#252526"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1E1E1E"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#252526"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2D2D30"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FF6B6B"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#007ACC"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#6D6D6D"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#6D6D6D"))

    app.setPalette(palette)
    app.setStyleSheet(DARK_STYLE_SHEET)
