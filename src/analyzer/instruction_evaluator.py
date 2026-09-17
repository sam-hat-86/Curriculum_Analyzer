"""
備考欄ルール評価エンジン (仕様書§21, §22: v1.1.0準拠)
"""
import re
from typing import Dict, List, Optional
from src.models.evaluation import InstructionEvaluation, EvaluationIssue
from src.parser.instruction_parser import parse_instruction_sections
from src.utils.constants import (
    RANK_CRITICAL,
    RANK_ERROR,
    RANK_REVIEW,
    RANK_WARNING,
    RANK_INFO,
    RANK_PASS,
    CRIT_INSTRUCTION_EMPTY,
    ERR_SECTION_MISSING,
    ERR_SECTION_EMPTY,
    ERR_AUTHOR_MISSING,
    ERR_TEXTBOOK_MISSING,
    ERR_TEXTBOOK_STATUS_MISSING,
    ERR_PLAN_MISSING,
    ERR_PLAN_TOO_SHORT,
    ERR_INFO_MISSING,
    ERR_INFO_TOO_SHORT,
    ERR_TEST_MISSING,
    ERR_HOMEWORK_MISSING,
    ERR_SCHOOL_REQUIRED_HIGH3,
    ERR_SCHOOL_REQUIRED_JUNIOR3,
    ERR_SCHOOL_REQUIRED_ELEM6,
    ERR_COURSE_COUNT_MISSING,
    REV_SCHOOL_UNCERTAIN,
    WARN_TEXTBOOK_NO_STATUS,
    WARN_SCHOOL_NO_TYPE,
    WARN_TEST_CRITERIA_MISSING,
    WARN_GOAL_MISSING,
    WARN_UNCLASSIFIED_TEXT,
    INFO_UNCLASSIFIED_TEXT,
    RULE_MESSAGES,
    RULE_FIX_SUGGESTIONS,
    TEXTBOOK_STATUS_KEYWORDS,
    TEXTBOOK_STATUS_UNCERTAIN,
    SCHOOL_TYPES,
    MIN_PLAN_LENGTH,
    MIN_INFO_LENGTH,
)
from src.utils.normalization import (
    normalize_text,
    is_blacklisted_or_empty,
    count_effective_chars,
)

class InstructionEvaluator:
    def evaluate(
        self,
        raw_instruction: Optional[str],
        grade: str = "",
        division: str = "",
        school_course: str = ""
    ) -> InstructionEvaluation:
        """備考欄本文を評価して InstructionEvaluation を返す"""
        eval_res = InstructionEvaluation()

        if not raw_instruction or is_blacklisted_or_empty(raw_instruction):
            eval_res.severity = RANK_CRITICAL
            eval_res.errors.append(CRIT_INSTRUCTION_EMPTY)
            eval_res.fix_items.append("備考欄を入力してください")
            return eval_res

        sections, unclassified_lines = parse_instruction_sections(raw_instruction)
        eval_res.parsed_sections = sections
        eval_res.unclassified_count = len(unclassified_lines)
        eval_res.unclassified_text = "\n".join(unclassified_lines)

        eval_res.author = sections.get("作成者", "")
        eval_res.target_school = sections.get("志望校", "")
        eval_res.textbook = sections.get("教材", "")
        eval_res.plan = sections.get("進め方", "")
        eval_res.student_info = sections.get("生徒情報", "")
        eval_res.test = sections.get("小テスト", "")
        eval_res.homework = sections.get("宿題", "")

        errors: List[str] = []
        warnings: List[str] = []
        reviews: List[str] = []
        fix_items: List[str] = []

        # 1. 作成者
        if not eval_res.author or is_blacklisted_or_empty(eval_res.author):
            errors.append(ERR_AUTHOR_MISSING)
            fix_items.append(RULE_FIX_SUGGESTIONS[ERR_AUTHOR_MISSING])

        # 2. 教材
        if not eval_res.textbook or is_blacklisted_or_empty(eval_res.textbook):
            errors.append(ERR_TEXTBOOK_MISSING)
            fix_items.append(RULE_FIX_SUGGESTIONS[ERR_TEXTBOOK_MISSING])
        else:
            # 教材ステータスチェック
            has_status = False
            for cat, kws in TEXTBOOK_STATUS_KEYWORDS.items():
                if any(kw in eval_res.textbook for kw in kws):
                    has_status = True
                    break
            is_uncertain = any(kw in eval_res.textbook for kw in TEXTBOOK_STATUS_UNCERTAIN)
            if not has_status or is_uncertain:
                errors.append(ERR_TEXTBOOK_STATUS_MISSING)
                fix_items.append(RULE_FIX_SUGGESTIONS[ERR_TEXTBOOK_STATUS_MISSING])

        # 3. 進め方
        if not eval_res.plan or is_blacklisted_or_empty(eval_res.plan):
            errors.append(ERR_PLAN_MISSING)
            fix_items.append(RULE_FIX_SUGGESTIONS[ERR_PLAN_MISSING])
        elif count_effective_chars(eval_res.plan) < MIN_PLAN_LENGTH:
            errors.append(ERR_PLAN_TOO_SHORT)
            fix_items.append(RULE_FIX_SUGGESTIONS[ERR_PLAN_TOO_SHORT])

        # 4. 生徒情報
        if not eval_res.student_info or is_blacklisted_or_empty(eval_res.student_info):
            errors.append(ERR_INFO_MISSING)
            fix_items.append(RULE_FIX_SUGGESTIONS[ERR_INFO_MISSING])
        elif count_effective_chars(eval_res.student_info) < MIN_INFO_LENGTH:
            errors.append(ERR_INFO_TOO_SHORT)
            fix_items.append(RULE_FIX_SUGGESTIONS[ERR_INFO_TOO_SHORT])

        # 5. 小テスト
        if not eval_res.test or is_blacklisted_or_empty(eval_res.test):
            errors.append(ERR_TEST_MISSING)
            fix_items.append(RULE_FIX_SUGGESTIONS[ERR_TEST_MISSING])

        # 6. 宿題
        if not eval_res.homework or is_blacklisted_or_empty(eval_res.homework):
            errors.append(ERR_HOMEWORK_MISSING)
            fix_items.append(RULE_FIX_SUGGESTIONS[ERR_HOMEWORK_MISSING])

        # 7. 学年別 志望校必須チェック
        norm_grade = normalize_text(grade)
        is_high3 = any(k in norm_grade for k in ["高3", "高３", "高校3", "高校３"])
        is_junior3 = any(k in norm_grade for k in ["中3", "中３", "中学3", "中学３"])
        is_elem6 = any(k in norm_grade for k in ["小6", "小６", "小学6", "小学６"])

        if is_high3:
            if not eval_res.target_school or is_blacklisted_or_empty(eval_res.target_school):
                errors.append(ERR_SCHOOL_REQUIRED_HIGH3)
                fix_items.append(RULE_FIX_SUGGESTIONS[ERR_SCHOOL_REQUIRED_HIGH3])
        elif is_junior3 and "公立" in school_course:
            if not eval_res.target_school or is_blacklisted_or_empty(eval_res.target_school):
                errors.append(ERR_SCHOOL_REQUIRED_JUNIOR3)
                fix_items.append(RULE_FIX_SUGGESTIONS[ERR_SCHOOL_REQUIRED_JUNIOR3])
        elif is_elem6 and any(k in school_course for k in ["中受", "受験"]):
            if not eval_res.target_school or is_blacklisted_or_empty(eval_res.target_school):
                errors.append(ERR_SCHOOL_REQUIRED_ELEM6)
                fix_items.append(RULE_FIX_SUGGESTIONS[ERR_SCHOOL_REQUIRED_ELEM6])

        # 志望校レビュー・警告
        if eval_res.target_school and not is_blacklisted_or_empty(eval_res.target_school):
            if any(amb in eval_res.target_school for amb in ["未定", "相談中", "検討中", "未定?", "？", "?"]):
                reviews.append(REV_SCHOOL_UNCERTAIN)
                fix_items.append(RULE_FIX_SUGGESTIONS[REV_SCHOOL_UNCERTAIN])
            elif not any(st in eval_res.target_school for st in SCHOOL_TYPES):
                warnings.append(WARN_SCHOOL_NO_TYPE)

        # 8. 講習授業チェック
        norm_div = normalize_text(division)
        if "講習" in norm_div:
            course_count = sections.get("講座数", "")
            if not course_count or is_blacklisted_or_empty(course_count):
                errors.append(ERR_COURSE_COUNT_MISSING)
                fix_items.append(RULE_FIX_SUGGESTIONS[ERR_COURSE_COUNT_MISSING])

            goal = sections.get("目標", "")
            if not goal or is_blacklisted_or_empty(goal):
                warnings.append(WARN_GOAL_MISSING)

        # 9. 未分類テキスト
        if eval_res.unclassified_count > 0:
            if errors or warnings or reviews:
                warnings.append(WARN_UNCLASSIFIED_TEXT)
            else:
                warnings.append(INFO_UNCLASSIFIED_TEXT)

        # 総合判定
        eval_res.errors = errors
        eval_res.warnings = warnings
        eval_res.reviews = reviews
        eval_res.fix_items = list(dict.fromkeys(fix_items))

        if errors:
            eval_res.severity = RANK_ERROR
        elif reviews:
            eval_res.severity = RANK_REVIEW
        elif warnings:
            eval_res.severity = RANK_WARNING
        else:
            eval_res.severity = RANK_PASS

        return eval_res
