"""
単元実施タイミング・実施状況分析 (仕様書§12, §13 & ユーザー合意決定)
"""
from datetime import date
from typing import Optional, Tuple
from src.models.curriculum import TargetInfo, UnitRecord
from src.models.state import TimingCategory
from src.utils.normalization import parse_date

def evaluate_unit_timing(unit: UnitRecord, target: TargetInfo) -> TimingCategory:
    """
    対象ターゲットに対する単元の実施タイミングを判定
    - 実施日なし: UNEXECUTED (未実施)
    - 対策期間未設定かつ実施日あり: UNDECIDED (判定保留 - 期間外)
    - 実施日 < 開始日: BEFORE (期間前)
    - 開始日 <= 実施日 <= 終了日: ON_TIME (期間内)
    - 実施日 > 終了日: AFTER (期間後)
    """
    if not unit.is_executed or not unit.execution_date or unit.execution_date == "-":
        return TimingCategory.UNEXECUTED

    exec_date = parse_date(unit.execution_date)
    if not exec_date:
        return TimingCategory.UNEXECUTED

    start_date = parse_date(target.start_date)
    end_date = parse_date(target.end_date)

    # 対策期間未設定の場合 (ユーザー合意決定)
    if not start_date or not end_date:
        return TimingCategory.UNDECIDED

    if exec_date < start_date:
        return TimingCategory.BEFORE
    elif start_date <= exec_date <= end_date:
        return TimingCategory.ON_TIME
    else:
        return TimingCategory.AFTER
