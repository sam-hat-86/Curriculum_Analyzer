"""
進捗率集計・整合性検証エンジン (仕様書§14, §18, §19, §40 & ユーザー合意決定)
"""
from datetime import date
from typing import List, Tuple
from src.models.curriculum import (
    CurriculumOverview,
    TargetInfo,
    UnitRecord,
    TargetProgress,
)
from src.models.state import TimingCategory
from src.analyzer.unit_analyzer import evaluate_unit_timing
from src.analyzer.target_analyzer import extract_target_textbooks
from src.utils.constants import DEFAULT_EMPTY_VALUE
from src.utils.normalization import parse_date, format_date

def calculate_target_progress(
    overview: CurriculumOverview,
    target: TargetInfo,
    units: List[UnitRecord]
) -> TargetProgress:
    """
    1ターゲットに対する進捗率を集計・計算
    """
    # 対象ターゲットに割り当てられている単元を抽出
    assigned_units = [u for u in units if u.target_checks.get(target.target_no, False)]
    target_unit_count = len(assigned_units)

    # 教材一覧の取得
    textbooks = extract_target_textbooks(target.target_no, units)
    textbooks_str = "\n".join(textbooks) if textbooks else DEFAULT_EMPTY_VALUE

    if target_unit_count == 0:
        return TargetProgress(
            classroom=overview.classroom_name or DEFAULT_EMPTY_VALUE,
            student_id=overview.student_id or DEFAULT_EMPTY_VALUE,
            grade=overview.grade or DEFAULT_EMPTY_VALUE,
            student_name=overview.student_name or DEFAULT_EMPTY_VALUE,
            division=overview.division or DEFAULT_EMPTY_VALUE,
            subject=overview.subject or DEFAULT_EMPTY_VALUE,
            target_no=target.target_no,
            target_name=target.target_name,
            start_date=target.start_date or DEFAULT_EMPTY_VALUE,
            end_date=target.end_date or DEFAULT_EMPTY_VALUE,
            period_str=target.period_str or DEFAULT_EMPTY_VALUE,
            is_current=target.is_current,
            textbooks_used=textbooks_str,
            target_score=target.target_score or DEFAULT_EMPTY_VALUE,
            current_score=target.current_score or DEFAULT_EMPTY_VALUE,
            target_unit_count=0,
            executed_count=0,
            executed_rate=DEFAULT_EMPTY_VALUE,
            on_time_count=0,
            on_time_rate=DEFAULT_EMPTY_VALUE,
            before_count=0,
            before_rate=DEFAULT_EMPTY_VALUE,
            after_count=0,
            after_rate=DEFAULT_EMPTY_VALUE,
            unexecuted_count=0,
            unexecuted_rate=DEFAULT_EMPTY_VALUE,
            latest_execution_date=DEFAULT_EMPTY_VALUE,
        )

    # 分類ごとのカウント
    on_time_cnt = 0
    before_cnt = 0
    after_cnt = 0
    unexecuted_cnt = 0
    executed_cnt = 0
    dates: List[date] = []

    for u in assigned_units:
        timing = evaluate_unit_timing(u, target)
        if timing == TimingCategory.ON_TIME:
            on_time_cnt += 1
            executed_cnt += 1
        elif timing == TimingCategory.BEFORE:
            before_cnt += 1
            executed_cnt += 1
        elif timing == TimingCategory.AFTER:
            after_cnt += 1
            executed_cnt += 1
        elif timing == TimingCategory.UNDECIDED:
            # ユーザー合意決定: 判定保留（期間外）は「実施済み数」に算入し、4分類では「期間後実施（期間外）」枠に集約
            after_cnt += 1
            executed_cnt += 1
        else: # UNEXECUTED
            unexecuted_cnt += 1

        if u.is_executed and u.execution_date and u.execution_date != DEFAULT_EMPTY_VALUE:
            d = parse_date(u.execution_date)
            if d:
                dates.append(d)

    # 仕様書§14.4 整合性チェック
    # 対象単元数 = 期間内 + 期間前 + 期間後 + 未実施
    assert target_unit_count == (on_time_cnt + before_cnt + after_cnt + unexecuted_cnt), "単元数合計不整合"
    # 実施済み数 = 期間内 + 期間前 + 期間後
    assert executed_cnt == (on_time_cnt + before_cnt + after_cnt), "実施済み数不整合"

    # パーセント計算
    def to_pct(cnt: int) -> str:
        pct = round((cnt / target_unit_count) * 100, 1)
        return str(int(pct)) if pct.is_integer() else str(pct)

    executed_rate = to_pct(executed_cnt)
    on_time_rate = to_pct(on_time_cnt)
    before_rate = to_pct(before_cnt)
    after_rate = to_pct(after_cnt)
    unexecuted_rate = to_pct(unexecuted_cnt)

    # 最終実施日 (仕様書§19: 対象単元の実施日のうち最も新しい日付)
    latest_date_str = DEFAULT_EMPTY_VALUE
    if dates:
        latest_date_str = format_date(max(dates))

    return TargetProgress(
        classroom=overview.classroom_name or DEFAULT_EMPTY_VALUE,
        student_id=overview.student_id or DEFAULT_EMPTY_VALUE,
        grade=overview.grade or DEFAULT_EMPTY_VALUE,
        student_name=overview.student_name or DEFAULT_EMPTY_VALUE,
        division=overview.division or DEFAULT_EMPTY_VALUE,
        subject=overview.subject or DEFAULT_EMPTY_VALUE,
        target_no=target.target_no,
        target_name=target.target_name,
        start_date=target.start_date or DEFAULT_EMPTY_VALUE,
        end_date=target.end_date or DEFAULT_EMPTY_VALUE,
        period_str=target.period_str or DEFAULT_EMPTY_VALUE,
        is_current=target.is_current,
        textbooks_used=textbooks_str,
        target_score=target.target_score or DEFAULT_EMPTY_VALUE,
        current_score=target.current_score or DEFAULT_EMPTY_VALUE,
        target_unit_count=target_unit_count,
        executed_count=executed_cnt,
        executed_rate=executed_rate,
        on_time_count=on_time_cnt,
        on_time_rate=on_time_rate,
        before_count=before_cnt,
        before_rate=before_rate,
        after_count=after_cnt,
        after_rate=after_rate,
        unexecuted_count=unexecuted_cnt,
        unexecuted_rate=unexecuted_rate,
        latest_execution_date=latest_date_str,
    )
