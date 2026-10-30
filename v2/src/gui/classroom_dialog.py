"""
教室自動巡回 対象選択ダイアログ (ClassroomPatrolDialog)
- モーダルから抽出した教室一覧をテーブル表示
- チェックボックスによる巡回対象の個別/一括選択
- 選択件数表示と巡回開始/キャンセル制御
"""
from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QCheckBox,
    QWidget,
)
from PySide6.QtCore import Qt


class ClassroomPatrolDialog(QDialog):
    """巡回対象教室の選択ダイアログ"""

    def __init__(self, classrooms: List[Dict[str, Any]], parent: QWidget = None):
        super().__init__(parent)
        self.classrooms = classrooms
        self._selected_classrooms: List[Dict[str, Any]] = []

        self.setWindowTitle("教室自動巡回 - 対象教室の選択")
        self.resize(750, 520)
        self.setModal(True)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # 説明ヘッダー
        info_label = QLabel(
            "自動巡回する教室を選択してください。\n"
            "「巡回開始」を押すと、選択された教室を1教室ずつ自動で切り替え、カリキュラムの全ページ取得・詳細解析を実行します。",
            self,
        )
        info_label.setStyleSheet("font-size: 13px; color: #CCCCCC; line-height: 1.4;")
        layout.addWidget(info_label)

        # 選択ボタングループ
        btn_select_layout = QHBoxLayout()
        btn_select_layout.setSpacing(8)

        self.btn_select_all = QPushButton("すべて選択", self)
        self.btn_select_all.clicked.connect(self._select_all)
        btn_select_layout.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("すべて解除", self)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        btn_select_layout.addWidget(self.btn_deselect_all)

        btn_select_layout.addStretch()

        self.lbl_selected_count = QLabel(f"巡回対象: {len(self.classrooms)} / {len(self.classrooms)} 教室", self)
        self.lbl_selected_count.setStyleSheet("font-size: 13px; font-weight: bold; color: #107C41;")
        btn_select_layout.addWidget(self.lbl_selected_count)

        layout.addLayout(btn_select_layout)

        # 教室一覧テーブル
        self.table = QTableWidget(len(self.classrooms), 5, self)
        self.table.setHorizontalHeaderLabels(["選択", "教室コード", "教室名", "エリア名", "ブロック名"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        self.checkboxes: List[QCheckBox] = []

        for row, c in enumerate(self.classrooms):
            # チェックボックス (中央配置)
            chk = QCheckBox(self)
            chk.setChecked(True)
            chk.stateChanged.connect(self._on_check_state_changed)
            self.checkboxes.append(chk)

            chk_container = QWidget(self)
            chk_layout = QHBoxLayout(chk_container)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, chk_container)

            code_item = QTableWidgetItem(c.get("classroom_code", ""))
            code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, code_item)

            name_item = QTableWidgetItem(c.get("classroom_name", ""))
            self.table.setItem(row, 2, name_item)

            area_item = QTableWidgetItem(c.get("area_name", ""))
            area_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, area_item)

            block_item = QTableWidgetItem(c.get("block_name", ""))
            block_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, block_item)

        layout.addWidget(self.table)

        # 下部ボタングループ (開始 / キャンセル)
        btn_action_layout = QHBoxLayout()
        btn_action_layout.setSpacing(10)
        btn_action_layout.addStretch()

        self.btn_cancel = QPushButton("キャンセル", self)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                min-width: 100px;
                min-height: 38px;
                padding: 4px 16px;
                background-color: #3E3E42;
                color: #FFFFFF;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4E4E52;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_action_layout.addWidget(self.btn_cancel)

        self.btn_start = QPushButton("▶ 巡回開始", self)
        self.btn_start.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                min-width: 140px;
                min-height: 38px;
                padding: 4px 16px;
                background-color: #107C41;
                color: #FFFFFF;
                border: 1px solid #107C41;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #159C52;
            }
            QPushButton:disabled {
                background-color: #25382D;
                color: #6D8274;
                border-color: #25382D;
            }
        """)
        self.btn_start.clicked.connect(self._on_start_clicked)
        btn_action_layout.addWidget(self.btn_start)

        layout.addLayout(btn_action_layout)

    def _select_all(self):
        for chk in self.checkboxes:
            chk.setChecked(True)
        self._update_count()

    def _deselect_all(self):
        for chk in self.checkboxes:
            chk.setChecked(False)
        self._update_count()

    def _on_check_state_changed(self):
        self._update_count()

    def _update_count(self):
        selected_count = sum(1 for chk in self.checkboxes if chk.isChecked())
        total = len(self.classrooms)
        self.lbl_selected_count.setText(f"巡回対象: {selected_count} / {total} 教室")
        self.btn_start.setEnabled(selected_count > 0)

    def _on_start_clicked(self):
        self._selected_classrooms = [
            self.classrooms[i]
            for i, chk in enumerate(self.checkboxes)
            if chk.isChecked()
        ]
        self.accept()

    def get_selected_classrooms(self) -> List[Dict[str, Any]]:
        """選択された教室リストを返す"""
        return [
            self.classrooms[i]
            for i, chk in enumerate(self.checkboxes)
            if chk.isChecked()
        ]
