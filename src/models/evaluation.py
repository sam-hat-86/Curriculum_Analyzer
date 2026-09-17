"""
備考欄評価データモデル (v1準拠)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass(slots=True)
class EvaluationIssue:
    """個別のルール違反・判定情報"""
    severity: str
    rule_id: str
    field: str
    message: str
    condition: str = ""
    fix_suggestion: str = ""

@dataclass(slots=True)
class InstructionEvaluation:
    """備考欄全体の評価結果"""
    severity: str = "PASS"
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reviews: List[str] = field(default_factory=list)
    fix_items: List[str] = field(default_factory=list)
    parsed_sections: Dict[str, str] = field(default_factory=dict)
    unclassified_text: str = ""
    unclassified_count: int = 0
    author: str = ""
    target_school: str = ""
    textbook: str = ""
    plan: str = ""
    student_info: str = ""
    test: str = ""
    homework: str = ""
