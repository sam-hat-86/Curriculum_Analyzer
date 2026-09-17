"""
データモデル定義
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Tuple, Any

class Severity(Enum):
    """判定ランク (v7 §3)"""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    REVIEW = "REVIEW"
    WARNING = "WARNING"
    INFO = "INFO"
    PASS = "PASS"

class ConfidenceLevel(Enum):
    """パーサー認識信頼度 (§5, §23)"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class SectionStatus(Enum):
    """項目状態 (§8)"""
    MISSING = "MISSING"
    EMPTY = "EMPTY"
    INVALID = "INVALID"
    VALID = "VALID"
    PARTIAL = "PARTIAL"

class UnclassifiedType(Enum):
    """未分類テキスト分類 (§6, §20)"""
    UNKNOWN_HEADING = "UNKNOWN_HEADING"
    FREE_TEXT = "FREE_TEXT"
    PARSER_CANDIDATE = "PARSER_CANDIDATE"

@dataclass(slots=True)
class TextbookItem:
    """教材単位の評価情報 (§13, §14, §32)"""
    name: str
    raw_status: str
    category: str  # 所持, 購入, 未所持, コピー, 未確定, 不明
    is_valid: bool
    evaluation_note: str = ""
    supplementary: str = ""  # 教材補足情報 (§14)

@dataclass(slots=True)
class UnclassifiedItem:
    """未分類テキスト情報 (§6, §17, §22)"""
    line_number: int
    raw_text: str
    item_type: UnclassifiedType
    candidate_heading: str = ""
    estimated_section: str = ""

@dataclass(slots=True)
class ExclusionStats:
    """集計対象除外の集計情報 (§4.3, §31)"""
    total_html_records: int = 0
    target_records: int = 0
    total_excluded: int = 0
    demo_excluded: int = 0
    withdrawn_excluded: int = 0   # 退塾
    declined_excluded: int = 0    # 見送り

@dataclass(slots=True)
class CurriculumRecord:
    """カリキュラムの1行データ (v7 §9, v10 §4)"""
    student_id: str
    division: str
    subject: str
    raw_instruction: str
    meta_cells: Dict[str, str] = field(default_factory=dict)
    cleaned_instruction: Optional[str] = None
    school_year: str = ""
    classroom_code: str = ""
    classroom_name: str = ""
    student_name: str = ""
    grade: str = ""

@dataclass(slots=True)
class EvaluationIssue:
    """個別のルール違反・判定情報 (§11, §21, §24, §28)"""
    severity: Severity
    rule_id: str
    field: str
    message: str
    condition: str = ""
    fix_suggestion: str = ""

@dataclass(slots=True)
class EvaluationResult:
    """指示書の評価結果"""
    severity: Severity
    errors: List[str]
    warnings: List[str]
    parsed_sections: Dict[str, str]
    unclassified_count: int
    unclassified_text: str
    reviews: List[str] = field(default_factory=list)
    primary_error: str = ""
    fix_fields: List[str] = field(default_factory=list)
    issues: List[EvaluationIssue] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    parse_traces: List[Dict[str, str]] = field(default_factory=list)
    textbook_items: List[TextbookItem] = field(default_factory=list)
    unclassified_items: List[UnclassifiedItem] = field(default_factory=list)
    section_statuses: Dict[str, SectionStatus] = field(default_factory=dict)
    rule_version: str = "1.0.0"

@dataclass(slots=True)
class AppConfig:
    """アプリケーション設定"""
    base_url: str
    ignore_ssl_errors: bool = False
    zoom_factor: float = 1.0
    min_plan_length: int = 5
    min_info_length: int = 3
    duplicate_info_threshold: int = 3
    max_char_threshold: int = 1000
    max_copypaste_threshold: int = 100
    max_row_failure_rate: float = 0.5

@dataclass(slots=True)
class UndoRecord:
    """Undoのための履歴情報"""
    added_keys: List[Tuple[str, str, str]]
    previous_records: Dict[Tuple[str, str, str], CurriculumRecord]
