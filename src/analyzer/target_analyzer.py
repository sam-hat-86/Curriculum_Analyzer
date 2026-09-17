"""
ターゲット使用教材・属性分析 (仕様書§10, §15)
"""
from typing import List
from src.models.curriculum import TargetInfo, UnitRecord

def extract_target_textbooks(target_no: str, units: List[UnitRecord]) -> List[str]:
    """
    対象ターゲットに割り当てられた単元で使用されている教材リストを抽出 (重複除外)
    """
    textbooks = []
    for u in units:
        if u.target_checks.get(target_no, False):
            tb = u.textbook.strip()
            if tb and tb != "-" and tb not in textbooks:
                textbooks.append(tb)
    return textbooks
