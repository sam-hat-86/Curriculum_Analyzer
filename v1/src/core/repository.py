"""
内部RepositoryとUndo管理
"""
import copy
from collections import OrderedDict
from typing import List, Tuple, Dict
from core.models import CurriculumRecord, UndoRecord
from core.constants import UNDO_MAX_HISTORY

class Repository:
    def __init__(self) -> None:
        self.records: OrderedDict[Tuple[str, str, str], CurriculumRecord] = OrderedDict()
        self._undo_stack: List[UndoRecord] = []

    def add_batch(self, records: List[CurriculumRecord]) -> UndoRecord:
        """バッチ追加し、UndoRecordを返す。同一キーは後勝ち。"""
        added_keys: List[Tuple[str, str, str]] = []
        previous_records: Dict[Tuple[str, str, str], CurriculumRecord] = {}

        for record in records:
            key = (record.student_id, record.division, record.subject)
            if key in self.records:
                if key not in previous_records:
                    previous_records[key] = copy.deepcopy(self.records[key])
                self.records[key] = record
            else:
                self.records[key] = record
                if key not in added_keys:
                    added_keys.append(key)
        
        undo_record = UndoRecord(
            added_keys=added_keys,
            previous_records=previous_records
        )
        return undo_record

    def undo(self, undo_record: UndoRecord) -> None:
        """指定したUndoRecordでRepositoryを元の状態へ戻す。"""
        # 更新前のレコードを差し戻す
        for key, prev_record in undo_record.previous_records.items():
            if key in self.records:
                self.records[key] = prev_record
                
        # 新規追加キーを削除
        for key in undo_record.added_keys:
            if key in self.records:
                del self.records[key]

    def get_all_records(self) -> List[CurriculumRecord]:
        """全レコードを挿入順にリストで返す"""
        return list(self.records.values())

    def get_snapshot(self) -> List[CurriculumRecord]:
        """ディープコピーした全レコードを挿入順にリストで返す"""
        return copy.deepcopy(self.get_all_records())

    @property
    def count(self) -> int:
        return len(self.records)

    def clear(self) -> None:
        """Repositoryを空にする"""
        self.records.clear()
        self._undo_stack.clear()

    def push_undo(self, undo_record: UndoRecord) -> None:
        """Undo履歴を追加する"""
        self._undo_stack.append(undo_record)
        if len(self._undo_stack) > UNDO_MAX_HISTORY:
            self._undo_stack.pop(0)

    def pop_undo(self) -> UndoRecord:
        """直近のUndo履歴を取り出す"""
        if not self._undo_stack:
            raise IndexError("Undo stack is empty")
        return self._undo_stack.pop()

    @property
    def records_order(self) -> List[Tuple[str, str, str]]:
        return list(self.records.keys())
