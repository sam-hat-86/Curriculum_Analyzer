"""
カリキュラム・ターゲット・単元データモデル (v2.0.0)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from src.models.state import ProcessState, TimingCategory
from src.models.evaluation import InstructionEvaluation

@dataclass(slots=True)
class CurriculumOverview:
    """一覧画面から抽出される授業概要情報"""
    classroom_name: str
    classroom_code: str
    school_year: str
    student_id: str
    student_name: str
    grade: str
    division: str
    subject: str
    school_course: str = ""
    row_index: int = 0
    detail_url: str = ""
    detail_html: str = ""
    status: ProcessState = ProcessState.UNFETCHED
    error_message: str = ""

@dataclass(slots=True)
class TargetInfo:
    """ターゲット定義情報 (T1, T2...)"""
    target_no: str             # T1, T2...
    target_name: str           # 1学期中間 など
    start_date: str            # YYYY/MM/DD または ""
    end_date: str              # YYYY/MM/DD または ""
    period_str: str            # YYYY/MM/DD～YYYY/MM/DD または "-"
    is_current: bool           # 実施中判定 (Boolean)
    target_score: str          # 目標点 または "-"
    current_score: str         # 現状の点数 (テスト合計得点) または "-"
    site_progress_rate: str    # サイト上の表示値 (例: 5枚/6枚 83%) または "-"
    textbooks: List[str] = field(default_factory=list) # 使用教材リスト

@dataclass(slots=True)
class UnitRecord:
    """単元テーブルの1行データ"""
    unit_no: str               # No.
    unit_name: str             # 単元名
    middle_unit: str           # 中単元
    textbook: str              # 教材名
    problem_code: str          # 問題コード
    score: str                 # 得点 または "-"
    max_score: str             # 配点 または "-"
    score_rate: str            # 得点率 (%) または "-"
    execution_date: str        # 実施日 (YYYY/MM/DD) または "-"
    timing: TimingCategory     # 期間前 / 期間内 / 期間後 / 判定保留 / 未実施
    is_executed: bool          # 実施済み (実施日の有無)
    today_textbook: str        # 本日の教材
    execution_division: str    # 実施区分
    confirm_test: str          # 確認テスト
    target_checks: Dict[str, bool] = field(default_factory=dict) # {"T1": True, "T2": False, ...}

@dataclass(slots=True)
class TargetProgress:
    """ターゲット単位の進捗率集計結果 (仕様書§14, §18)"""
    classroom: str
    student_id: str
    grade: str
    student_name: str
    division: str
    subject: str
    target_no: str
    target_name: str
    start_date: str
    end_date: str
    period_str: str
    is_current: bool
    textbooks_used: str        # 改行区切り
    target_score: str
    current_score: str
    target_unit_count: int     # 対象単元数
    executed_count: int        # 実施済み数
    executed_rate: str         # 実施済み％
    on_time_count: int         # 期間内実施数
    on_time_rate: str          # 期間内実施％
    before_count: int          # 期間前実施数
    before_rate: str           # 期間前実施％
    after_count: int           # 期間後実施数 (判定保留合算)
    after_rate: str            # 期間後実施％
    unexecuted_count: int      # 未実施数
    unexecuted_rate: str       # 未実施％
    latest_execution_date: str # 最終実施日 または "-"

@dataclass(slots=True)
class CurriculumDetailData:
    """カリキュラム詳細ページの完全解析データ"""
    overview: CurriculumOverview
    raw_html: str
    fetch_time: str
    raw_instruction: str = ""
    materials_listed: List[str] = field(default_factory=list)
    targets: List[TargetInfo] = field(default_factory=list)
    units: List[UnitRecord] = field(default_factory=list)
    instruction_eval: Optional[InstructionEvaluation] = None
    progress_list: List[TargetProgress] = field(default_factory=list)
