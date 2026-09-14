import copy
import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

from core.constants import (
    CANONICAL_SECTIONS,
    CRIT_INSTRUCTION_EMPTY,
    ERR_AUTHOR_MISSING,
    ERR_COURSE_COUNT_MISSING,
    ERR_HOMEWORK_MISSING,
    ERR_INFO_MISSING,
    ERR_INFO_TOO_SHORT,
    ERR_INTERNAL_EVALUATION,
    ERR_PARSER_EXCEPTION,
    ERR_PLAN_MISSING,
    ERR_PLAN_TOO_SHORT,
    ERR_SCHOOL_REQUIRED_ELEM6,
    ERR_SCHOOL_REQUIRED_HIGH3,
    ERR_SCHOOL_REQUIRED_JUNIOR3,
    ERR_SECTION_EMPTY,
    ERR_SECTION_MISSING,
    ERR_TEST_MISSING,
    ERR_TEXTBOOK_MISSING,
    ERR_TEXTBOOK_STATUS_MISSING,
    REV_SCHOOL_UNCERTAIN,
    RULE_CONDITIONS,
    RULE_FIX_SUGGESTIONS,
    RULE_MESSAGES,
    RULE_ORDER,
    SCHOOL_TYPES,
    TEXTBOOK_STATUS_KEYWORDS,
    TEXTBOOK_STATUS_UNCERTAIN,
    WARN_COPY_PASTE_SUSPECTED,
    WARN_GOAL_MISSING,
    WARN_SCHOOL_NO_TYPE,
    WARN_TEXTBOOK_NO_STATUS,
    WARN_UNCLASSIFIED_TEXT,
    INFO_UNCLASSIFIED_TEXT,
)
from core.models import (
    AppConfig,
    CurriculumRecord,
    EvaluationIssue,
    EvaluationResult,
    ExclusionStats,
    SectionStatus,
    Severity,
    TextbookItem,
    UnclassifiedItem,
    UnclassifiedType,
)
from core.normalization import (
    clean_instruction,
    count_effective_chars,
    normalize_author,
    normalize_for_blacklist,
)
import core.parser as parser

SECTION_FIELD_MAP = {
    CRIT_INSTRUCTION_EMPTY: "備考欄",
    INFO_UNCLASSIFIED_TEXT: "未分類テキスト",
    ERR_AUTHOR_MISSING: "作成者",
    ERR_TEXTBOOK_MISSING: "教材",
    ERR_TEXTBOOK_STATUS_MISSING: "教材",
    ERR_PLAN_MISSING: "進め方",
    ERR_PLAN_TOO_SHORT: "進め方",
    ERR_INFO_MISSING: "生徒情報",
    ERR_INFO_TOO_SHORT: "生徒情報",
    ERR_TEST_MISSING: "小テスト",
    ERR_HOMEWORK_MISSING: "宿題",
    ERR_SCHOOL_REQUIRED_HIGH3: "志望校",
    ERR_SCHOOL_REQUIRED_JUNIOR3: "志望校",
    ERR_SCHOOL_REQUIRED_ELEM6: "志望校",
    ERR_COURSE_COUNT_MISSING: "講座数",
    ERR_SECTION_MISSING: "必須項目",
    ERR_SECTION_EMPTY: "必須項目",
    ERR_PARSER_EXCEPTION: "システム",
    ERR_INTERNAL_EVALUATION: "システム",
    REV_SCHOOL_UNCERTAIN: "志望校",
    WARN_TEXTBOOK_NO_STATUS: "教材",
    WARN_SCHOOL_NO_TYPE: "志望校",
    WARN_GOAL_MISSING: "目標",
    WARN_COPY_PASTE_SUSPECTED: "生徒情報",
    WARN_UNCLASSIFIED_TEXT: "未分類テキスト",
}

_HIGH3_RE = re.compile(r'(?:高|高校)\s*[3３]|高三|H3|K3', re.IGNORECASE)
_JUNIOR3_RE = re.compile(r'(?:中|中学)\s*[3３]|中三|J3', re.IGNORECASE)
_ELEM6_RE = re.compile(r'(?:小|小学)\s*[6６]|小六|E6', re.IGNORECASE)

_PUBLIC_SCHOOL_KW = ["公立", "市立", "都立", "府立", "県立", "区立", "村立", "町立"]
_PRIVATE_SCHOOL_KW = ["私立", "国立"]
_CHUJU_KW = ["中受", "中学受験", "中学入試", "受験"]


def _is_blacklisted_or_empty(text: str) -> bool:
    """Check if the text is empty or matches the blacklist."""
    from core.constants import BLACKLIST
    if not text:
        return True
    norm_text = normalize_for_blacklist(text)
    if not norm_text:
        return True
    
    # Check if normalized text is in normalized blacklist
    for bl_word in BLACKLIST:
        if norm_text == normalize_for_blacklist(bl_word):
            return True
            
    return False


def _detect_school_requirement(
    record: CurriculumRecord,
    parsed_sections: Dict[str, str]
) -> Tuple[bool, Optional[str]]:
    """
    志望校の条件付き必須判定 (§3.2, §18.2, v10 §3):
    - 高3: ERR_SCHOOL_REQUIRED_HIGH3
    - 公立中3: ERR_SCHOOL_REQUIRED_JUNIOR3
    - 小6中受: ERR_SCHOOL_REQUIRED_ELEM6
    - その他: 任意 (必須ではない)
    """
    from core.normalization import normalize_grade

    # 直接取得した学年が存在する場合は最優先で使用 (v10 §3.1)
    grade_val = normalize_grade(record.grade) if getattr(record, "grade", "") else ""
    if grade_val:
        school_sources = []
        chuju_sources = [record.division, record.subject]
        for k, v in record.meta_cells.items():
            k_norm = unicodedata.normalize('NFKC', str(k))
            v_norm = unicodedata.normalize('NFKC', str(v))
            if "学校" in k_norm or "コース" in k_norm or "school" in k_norm.lower():
                school_sources.append(v_norm)
            chuju_sources.append(v_norm)
        school_text = " ".join(school_sources)
        chuju_text = " ".join(chuju_sources)

        # 1. 高3チェック
        if _HIGH3_RE.search(grade_val):
            return True, ERR_SCHOOL_REQUIRED_HIGH3

        # 2. 公立中3チェック
        if _JUNIOR3_RE.search(grade_val):
            is_private = any(pkw in school_text for pkw in _PRIVATE_SCHOOL_KW)
            if not is_private:
                return True, ERR_SCHOOL_REQUIRED_JUNIOR3

        # 3. 小6中受チェック
        if _ELEM6_RE.search(grade_val):
            if any(ckw in chuju_text for ckw in _CHUJU_KW):
                return True, ERR_SCHOOL_REQUIRED_ELEM6

        # 直接取得した学年が存在し、上記条件外（高1, 高2, 中1, 中2, 小5等）の場合は推測せず任意 (v10 §3.1)
        return False, None

    # 学年直接取得がない場合のフォールバック探索
    grade_sources = [record.division, record.subject]
    school_sources = []
    chuju_sources = [record.division, record.subject]

    for k, v in record.meta_cells.items():
        k_norm = unicodedata.normalize('NFKC', str(k))
        v_norm = unicodedata.normalize('NFKC', str(v))
        if "学年" in k_norm or "grade" in k_norm.lower():
            grade_sources.insert(0, v_norm)
        elif "学校" in k_norm or "コース" in k_norm or "school" in k_norm.lower():
            school_sources.append(v_norm)
        else:
            grade_sources.append(v_norm)
            school_sources.append(v_norm)
        chuju_sources.append(v_norm)

    # 生徒情報も補助参照
    student_info = parsed_sections.get("生徒情報", "")
    if student_info:
        norm_info = unicodedata.normalize('NFKC', student_info)
        grade_sources.append(norm_info)
        school_sources.append(norm_info)
        chuju_sources.append(norm_info)

    grade_text = " ".join(grade_sources)
    school_text = " ".join(school_sources)
    chuju_text = " ".join(chuju_sources)

    # 1. 高3チェック
    if _HIGH3_RE.search(grade_text):
        return True, ERR_SCHOOL_REQUIRED_HIGH3

    # 2. 公立中3チェック
    if _JUNIOR3_RE.search(grade_text):
        is_public = False
        is_private = any(pkw in school_text for pkw in _PRIVATE_SCHOOL_KW)
        if not is_private:
            if any(pkw in school_text for pkw in _PUBLIC_SCHOOL_KW):
                is_public = True
            elif "中" in school_text:
                # 学校名に「中」が含まれ、私立・国立でなければ公立中と判定
                is_public = True
            elif any(pkw in grade_text for pkw in _PUBLIC_SCHOOL_KW):
                is_public = True
        if is_public:
            return True, ERR_SCHOOL_REQUIRED_JUNIOR3

    # 3. 小6中受チェック
    if _ELEM6_RE.search(grade_text):
        if any(ckw in chuju_text for ckw in _CHUJU_KW):
            return True, ERR_SCHOOL_REQUIRED_ELEM6

    return False, None


def check_record_exclusion(record: CurriculumRecord) -> Optional[str]:
    """
    集計対象除外の判定 (§4, v10 §8):
    - 名字が完全に「デモ」の生徒 ("DEMO")。名字以外にデモを含む場合は除外しない (例: デモ田 は対象)。
    - 在籍ステータスが「退塾」("WITHDRAWN")
    - 在籍ステータスが「見送り」("DECLINED")
    除外理由文字列、または None を返す。
    """
    # 1. 名字が完全に「デモ」の生徒 (v10 §8: student_name を優先)
    if getattr(record, "student_name", ""):
        sname = record.student_name.strip()
        parts = sname.split()
        if (parts and parts[0] == "デモ") or sname == "デモ":
            return "DEMO"

    name_candidates = []
    for k in ["生徒", "student_raw", "氏名", "生徒氏名", "生徒名", "名前"]:
        if k in record.meta_cells and record.meta_cells[k]:
            name_candidates.append(str(record.meta_cells[k]))
    for k, v in record.meta_cells.items():
        if ("生徒" in str(k) or "氏名" in str(k)) and v:
            name_candidates.append(str(v))

    for cand in name_candidates:
        cand_clean = re.sub(r'^[0-9０-９\s\-_\(\)（）]+', '', cand).strip()
        cand_clean = unicodedata.normalize('NFKC', cand_clean).strip()
        parts = cand_clean.split()
        if (parts and parts[0] == "デモ") or cand_clean == "デモ":
            return "DEMO"

    # 2. 在籍ステータスチェック
    for k, v in record.meta_cells.items():
        k_norm = unicodedata.normalize('NFKC', str(k))
        if any(w in k_norm for w in ["在籍", "ステータス", "状況", "区分"]) or "status" in k_norm.lower():
            v_norm = unicodedata.normalize('NFKC', str(v))
            if "退塾" in v_norm:
                return "WITHDRAWN"
            if "見送り" in v_norm:
                return "DECLINED"

    for v in record.meta_cells.values():
        v_str = unicodedata.normalize('NFKC', str(v))
        if "退塾" in v_str:
            return "WITHDRAWN"
        if "見送り" in v_str:
            return "DECLINED"

    return None


def filter_target_records(records: List[CurriculumRecord]) -> Tuple[List[CurriculumRecord], ExclusionStats]:
    """
    レコードリストから除外対象を除外し、集計対象レコードと除外統計を返す (§4)。
    """
    target_records: List[CurriculumRecord] = []
    demo_count = 0
    withdrawn_count = 0
    declined_count = 0

    for rec in records:
        reason = check_record_exclusion(rec)
        if reason == "DEMO":
            demo_count += 1
        elif reason == "WITHDRAWN":
            withdrawn_count += 1
        elif reason == "DECLINED":
            declined_count += 1
        else:
            target_records.append(rec)

    total_excluded = demo_count + withdrawn_count + declined_count
    stats = ExclusionStats(
        total_html_records=len(records),
        target_records=len(target_records),
        total_excluded=total_excluded,
        demo_excluded=demo_count,
        withdrawn_excluded=withdrawn_count,
        declined_excluded=declined_count,
    )
    return target_records, stats


def _evaluate_school_section(text: str, reviews: List[str], warnings: List[str]) -> None:
    """Evaluate 志望校 section according to v6 §19.1, §19.3 (区分の有無は判定条件から完全に廃止)"""
    norm_text = unicodedata.normalize('NFKC', text)
    items = re.split(r'[\n,、]', norm_text)
    vague_keywords = ["ところ", "未定", "検討中", "模索中", "進学希望", "未定です", "決まっていない", "大学進学"]
    for item in items:
        item = item.strip()
        if not item:
            continue
        if any(vkw in item for vkw in vague_keywords):
            reviews.append(REV_SCHOOL_UNCERTAIN)
            break


def _is_raw_instruction_empty(raw: Optional[str]) -> bool:
    """備考欄そのものが完全に空欄であるか判定する (§2.2, v6 §3)"""
    if raw is None:
        return True
    s = raw.strip()
    if not s or s in ["[DOM取得失敗]", "エラー", "[エラー]", "Error", "[Error]"] or "DOM取得失敗" in s:
        return True
    return all(unicodedata.category(c).startswith('Z') or c.isspace() for c in s)


def _is_supplementary_note(item_str: str) -> bool:
    """行または要素が教材ではなく補足事項・注意書きであるか判定する (v6 §13, §14)"""
    s = item_str.strip()
    if s.startswith(('※', '注', '注意', '備考', '◆', '■')):
        return True
    # 矢印プレフィックス (→, ⇒, -> 等)
    s_clean = s.lstrip("・- 　")
    if s_clean.startswith(('→', '⇒', '->', '=>')):
        return True
    # 日付+連絡・面談・保護者希望などの記録 (例: 7/31鈴木【親御さんより...】)
    if re.match(r'^(?:[→⇒]|->|=>)?\s*\d{1,2}/\d{1,2}', s_clean):
        return True
    if any(kw in s for kw in ["親御さん", "保護者", "学校課題", "サポートの希望", "ご家庭", "面談"]):
        return True
    supp_keywords = [
        "使用する予定", "変更する予定", "別教材", "適宜追記", "適宜変更",
        "移行する場合", "必要に応じて", "購入を検討", "確認の上",
        "予定なので", "終了次第", "終わり次第", "追記します", "追記予定",
        "使用予定"
    ]
    if any(kw in s for kw in supp_keywords):
        return True
    if len(s) >= 20 and any(s.endswith(end) for end in ["予定", "予定です", "追記", "参照", "方針", "こと", "ます"]):
        return True
    return False


def _evaluate_textbook_section_itemized(
    text: str,
    errors: List[str]
) -> Tuple[List[TextbookItem], SectionStatus]:
    """教材セクションを教材単位で構造化・評価する (v6 §12, §13, §14)"""
    norm_text = unicodedata.normalize('NFKC', text)
    lines = norm_text.split('\n')
    raw_items = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'^[・\-\*]\s*', '', line).strip()
        if not line:
            continue
        if _is_supplementary_note(line):
            raw_items.append(line)
            continue
        sub_items = re.split(r'、|(?<![a-zA-Z0-9]),(?![a-zA-Z0-9])', line)
        for s in sub_items:
            s = s.strip()
            if s:
                raw_items.append(s)

    if not raw_items:
        return [], SectionStatus.EMPTY

    possession_kws = ["所持(済)", "所持（済）", "所持済", "所持", "手持ち", "本人所持", "持込教材", "持込", "持ち込み"]
    purchase_kws = ["購入予定", "購入"]
    unpossessed_kws = ["未所持です", "未所持", "未購入"]
    copy_kws = ["コピー教材", "コピー", "複写"]
    uncertain_kws = ["所持?", "所持？", "所持か不明", "所持か要確認", "？", "?"]

    textbook_items: List[TextbookItem] = []
    has_invalid = False
    has_valid = False
    actual_textbook_count = 0

    for item_str in raw_items:
        if _is_supplementary_note(item_str):
            # 補足事項行: 教材名は空、補足列に記載、ステータス判定対象外 (v6 §13, §37)
            clean_supp = re.sub(r'^[→⇒\->\s・]+', '', item_str).strip()
            textbook_items.append(TextbookItem(
                name="",
                raw_status="",
                category="補足",
                is_valid=True,
                evaluation_note="補足事項",
                supplementary=clean_supp,
            ))
            continue

        actual_textbook_count += 1
        m_bracket = re.search(r'[（\(]([^）\)]+)[）\)]\s*$', item_str)
        if m_bracket:
            raw_status = m_bracket.group(1).strip()
            name = item_str[:m_bracket.start()].strip()
            if not name:
                name = item_str
        else:
            found_kw = ""
            for kw in possession_kws + purchase_kws + unpossessed_kws + copy_kws + uncertain_kws:
                if kw in item_str:
                    found_kw = kw
                    break
            if found_kw:
                raw_status = found_kw
                name = item_str.replace(found_kw, "").strip(" :：・-()（）")
                if not name:
                    name = item_str
            else:
                raw_status = "未記載"
                name = item_str

        # カテゴリ判定
        if any(unc in item_str or unc in raw_status for unc in uncertain_kws):
            cat = "未確定"
            is_valid = False
            note = "ステータス未確定（要確認）"
        elif any(kw in raw_status for kw in possession_kws):
            cat = "所持"
            is_valid = True
            note = "所持確認済み"
        elif any(kw in raw_status for kw in purchase_kws):
            cat = "購入"
            is_valid = True
            note = "購入予定"
        elif any(kw in raw_status for kw in unpossessed_kws):
            cat = "未所持"
            is_valid = True
            note = "未所持確認済み"
        elif any(kw in raw_status for kw in copy_kws):
            cat = "コピー"
            is_valid = True
            note = "コピー教材"
        else:
            cat = "不明"
            is_valid = False
            note = "ステータス未記載"

        if is_valid:
            has_valid = True
        else:
            has_invalid = True

        textbook_items.append(TextbookItem(
            name=name,
            raw_status=raw_status,
            category=cat,
            is_valid=is_valid,
            evaluation_note=note,
            supplementary="",
        ))

    if actual_textbook_count == 0:
        errors.append(ERR_TEXTBOOK_MISSING)
        sec_status = SectionStatus.INVALID
    elif has_invalid:
        errors.append(ERR_TEXTBOOK_STATUS_MISSING)
        sec_status = SectionStatus.PARTIAL if has_valid else SectionStatus.INVALID
    else:
        sec_status = SectionStatus.VALID

    return textbook_items, sec_status


def _is_lecture_class(record: CurriculumRecord) -> bool:
    """受講区分が講習授業（夏期、冬期、春期、講習等）であるか判定する"""
    div = record.division or ""
    return any(kw in div for kw in ["講習", "夏期", "冬期", "春期"])


FIX_FIELD_MAP = {
    CRIT_INSTRUCTION_EMPTY: "備考欄",
    ERR_AUTHOR_MISSING: "作成者",
    ERR_TEXTBOOK_MISSING: "教材",
    ERR_TEXTBOOK_STATUS_MISSING: "教材ステータス",
    ERR_PLAN_MISSING: "進め方",
    ERR_PLAN_TOO_SHORT: "進め方",
    ERR_INFO_MISSING: "生徒情報",
    ERR_INFO_TOO_SHORT: "生徒情報",
    ERR_TEST_MISSING: "小テスト",
    ERR_HOMEWORK_MISSING: "宿題",
    ERR_SCHOOL_REQUIRED_HIGH3: "志望校",
    ERR_SCHOOL_REQUIRED_JUNIOR3: "志望校",
    ERR_SCHOOL_REQUIRED_ELEM6: "志望校",
    ERR_COURSE_COUNT_MISSING: "講座数",
    ERR_SECTION_MISSING: "必須項目",
    ERR_SECTION_EMPTY: "必須項目",
    ERR_PARSER_EXCEPTION: "解析処理",
    ERR_INTERNAL_EVALUATION: "内部処理",
    REV_SCHOOL_UNCERTAIN: "志望校",
    WARN_TEXTBOOK_NO_STATUS: "教材ステータス",
    WARN_SCHOOL_NO_TYPE: "志望校",
    WARN_GOAL_MISSING: "目標",
    WARN_COPY_PASTE_SUSPECTED: "生徒情報",
    WARN_UNCLASSIFIED_TEXT: "未分類テキスト",
    INFO_UNCLASSIFIED_TEXT: "未分類テキスト",
}


def evaluate_single_record(record: CurriculumRecord, config: AppConfig) -> EvaluationResult:
    """Evaluate a single curriculum record according to v7 specification."""
    # 0. CRITICAL判定: 備考欄そのものが完全に空欄 (v7 §7)
    if _is_raw_instruction_empty(record.raw_instruction):
        crit_err = CRIT_INSTRUCTION_EMPTY
        issue = EvaluationIssue(
            severity=Severity.CRITICAL,
            rule_id=crit_err,
            field="備考欄",
            message=RULE_MESSAGES[crit_err],
            condition=RULE_CONDITIONS[crit_err],
            fix_suggestion=RULE_FIX_SUGGESTIONS[crit_err],
        )
        return EvaluationResult(
            severity=Severity.CRITICAL,
            errors=[crit_err],
            reviews=[],
            warnings=[],
            parsed_sections={},
            unclassified_count=0,
            unclassified_text="",
            primary_error=crit_err,
            fix_fields=["備考欄"],
            issues=[issue],
            parse_traces=[],
            textbook_items=[],
            unclassified_items=[],
            section_statuses={k: SectionStatus.EMPTY for k in CANONICAL_SECTIONS.keys()},
        )

    errors: List[str] = []
    reviews: List[str] = []
    warnings: List[str] = []
    parsed_sections: Dict[str, str] = {}
    unclassified_count = 0
    unclassified_text = ""
    parse_traces: List[Dict[str, str]] = []
    meta_parsed: Dict[str, str] = {}
    unclassified_items: List[UnclassifiedItem] = []
    textbook_items: List[TextbookItem] = []
    section_statuses: Dict[str, SectionStatus] = {}

    try:
        # Generate cleaned_instruction
        if record.cleaned_instruction is None:
            record.cleaned_instruction = clean_instruction(record.raw_instruction)

        # Detailed parse
        (
            parsed_sections,
            unclassified_count,
            unclassified_text,
            parse_traces,
            meta_parsed,
            unclassified_items,
        ) = parser.parse_sections_detailed(record.cleaned_instruction)

        # 1. 作成者 (常時必須)
        if "作成者" not in parsed_sections:
            errors.append(ERR_AUTHOR_MISSING)
            section_statuses["作成者"] = SectionStatus.MISSING
        elif _is_blacklisted_or_empty(parsed_sections["作成者"]):
            errors.append(ERR_AUTHOR_MISSING)
            section_statuses["作成者"] = SectionStatus.EMPTY
        else:
            parsed_sections["作成者"] = normalize_author(parsed_sections["作成者"])
            section_statuses["作成者"] = SectionStatus.VALID

        # 2. 教材 (常時必須) & 教材単位のステータス判定 (§9, §10)
        if "教材" not in parsed_sections:
            errors.append(ERR_TEXTBOOK_MISSING)
            section_statuses["教材"] = SectionStatus.MISSING
        elif _is_blacklisted_or_empty(parsed_sections["教材"]):
            errors.append(ERR_TEXTBOOK_MISSING)
            section_statuses["教材"] = SectionStatus.EMPTY
        else:
            textbook_items, tb_status = _evaluate_textbook_section_itemized(parsed_sections["教材"], errors)
            section_statuses["教材"] = tb_status

        # 3. 進め方 (常時必須 & 文字数)
        if "進め方" not in parsed_sections:
            errors.append(ERR_PLAN_MISSING)
            section_statuses["進め方"] = SectionStatus.MISSING
        elif _is_blacklisted_or_empty(parsed_sections["進め方"]):
            errors.append(ERR_PLAN_MISSING)
            section_statuses["進め方"] = SectionStatus.EMPTY
        else:
            plan_len = count_effective_chars(parsed_sections["進め方"])
            if plan_len < config.min_plan_length:
                errors.append(ERR_PLAN_TOO_SHORT)
                section_statuses["進め方"] = SectionStatus.INVALID
            else:
                section_statuses["進め方"] = SectionStatus.VALID

        # 4. 生徒情報 (常時必須 & 文字数)
        if "生徒情報" not in parsed_sections:
            errors.append(ERR_INFO_MISSING)
            section_statuses["生徒情報"] = SectionStatus.MISSING
        elif _is_blacklisted_or_empty(parsed_sections["生徒情報"]):
            errors.append(ERR_INFO_MISSING)
            section_statuses["生徒情報"] = SectionStatus.EMPTY
        else:
            info_len = count_effective_chars(parsed_sections["生徒情報"])
            if info_len < config.min_info_length:
                errors.append(ERR_INFO_TOO_SHORT)
                section_statuses["生徒情報"] = SectionStatus.INVALID
            else:
                section_statuses["生徒情報"] = SectionStatus.VALID

        # 5. 小テスト (常時必須、基準・範囲は任意 §14)
        if "小テスト" not in parsed_sections:
            errors.append(ERR_TEST_MISSING)
            section_statuses["小テスト"] = SectionStatus.MISSING
        elif _is_blacklisted_or_empty(parsed_sections["小テスト"]):
            errors.append(ERR_TEST_MISSING)
            section_statuses["小テスト"] = SectionStatus.EMPTY
        else:
            section_statuses["小テスト"] = SectionStatus.VALID

        # 6. 宿題 (常時必須 & 具体的内容 §15)
        if "宿題" not in parsed_sections:
            errors.append(ERR_HOMEWORK_MISSING)
            section_statuses["宿題"] = SectionStatus.MISSING
        elif _is_blacklisted_or_empty(parsed_sections["宿題"]):
            errors.append(ERR_HOMEWORK_MISSING)
            section_statuses["宿題"] = SectionStatus.EMPTY
        else:
            section_statuses["宿題"] = SectionStatus.VALID

        # 7. 志望校 (条件付き必須 §11, §12, §15.3)
        is_school_required, school_rule_id = _detect_school_requirement(record, parsed_sections)
        school_text = parsed_sections.get("志望校", "").strip()

        # 曖昧な志望校（未定、学べるところ等）の判定 (§15.3)
        vague_keywords = ["ところ", "未定", "検討中", "模索中", "進学希望", "未定です", "決まっていない", "大学進学"]
        is_vague_school = bool(school_text and any(vkw in school_text for vkw in vague_keywords))

        invalid_blank_values = [normalize_for_blacklist(b) for b in ["なし", "特になし", "同上", "-", "―", "ー"]]
        is_invalid_blank = not school_text or (normalize_for_blacklist(school_text) in invalid_blank_values)

        if is_school_required:
            if "志望校" not in parsed_sections:
                if school_rule_id:
                    errors.append(school_rule_id)
                section_statuses["志望校"] = SectionStatus.MISSING
            elif is_invalid_blank:
                if school_rule_id:
                    errors.append(school_rule_id)
                section_statuses["志望校"] = SectionStatus.EMPTY
            elif is_vague_school:
                reviews.append(REV_SCHOOL_UNCERTAIN)
                section_statuses["志望校"] = SectionStatus.PARTIAL
            else:
                section_statuses["志望校"] = SectionStatus.VALID
        else:
            if is_vague_school:
                reviews.append(REV_SCHOOL_UNCERTAIN)
                section_statuses["志望校"] = SectionStatus.PARTIAL
            else:
                section_statuses["志望校"] = SectionStatus.VALID

        # 志望校が記載されていて、かつ空欄・曖昧でない場合の学校区分チェック (§18.2)
        if school_text and not is_invalid_blank and not is_vague_school:
            _evaluate_school_section(school_text, reviews, warnings)

        # 8. 講習授業の講座数・目標チェック (§13)
        if _is_lecture_class(record):
            course_count = meta_parsed.get("course_count", "")
            if _is_blacklisted_or_empty(course_count):
                errors.append(ERR_COURSE_COUNT_MISSING)

            goal = meta_parsed.get("goal", "")
            if _is_blacklisted_or_empty(goal):
                warnings.append(WARN_GOAL_MISSING)

        # 9. 未分類テキスト警告の出し方改善 (§7)
        # FREE_TEXTのみ → 原則情報保持 (WARNINGにしない)
        # UNKNOWN_HEADING / PARSER_CANDIDATE → WARNING候補 (ただし既知メタ項目の目標・講座数等は除く)
        has_unknown_headings = any(
            item.item_type in (UnclassifiedType.UNKNOWN_HEADING, UnclassifiedType.PARSER_CANDIDATE)
            and item.estimated_section not in ("目標", "講座数")
            and not any(k in item.candidate_heading for k in ["目標", "講座", "コマ"])
            for item in unclassified_items
        )
        if has_unknown_headings and unclassified_count > 0:
            warnings.append(WARN_UNCLASSIFIED_TEXT)

    except Exception:
        errors.append(ERR_PARSER_EXCEPTION)

    # Deduplicate rule IDs within same record
    errors = list(dict.fromkeys(errors))
    reviews = list(dict.fromkeys(reviews))
    warnings = list(dict.fromkeys(warnings))

    # Remove from warnings if in errors or reviews
    warnings = [w for w in warnings if w not in errors and w not in reviews]

    # Order by RULE_ORDER
    errors.sort(key=lambda x: RULE_ORDER.index(x) if x in RULE_ORDER else 999)
    reviews.sort(key=lambda x: RULE_ORDER.index(x) if x in RULE_ORDER else 999)
    warnings.sort(key=lambda x: RULE_ORDER.index(x) if x in RULE_ORDER else 999)

    # 最重要エラーの決定 (§4)
    from core.constants import PRIMARY_RULE_PRIORITY
    primary_error = ""
    for r in PRIMARY_RULE_PRIORITY:
        if r in errors:
            primary_error = r
            break
    if not primary_error:
        for r in PRIMARY_RULE_PRIORITY:
            if r in reviews:
                primary_error = r
                break
    if not primary_error:
        for r in PRIMARY_RULE_PRIORITY:
            if r in warnings:
                primary_error = r
                break

    # 修正項目の特定 (§3, §10)
    fix_fields = []
    for err in errors + reviews:
        f = FIX_FIELD_MAP.get(err)
        if f and f not in fix_fields:
            fix_fields.append(f)

    # Severity判定 (v7 §3: CRITICAL > ERROR > REVIEW > WARNING > INFO > PASS)
    if any(e == CRIT_INSTRUCTION_EMPTY for e in errors):
        severity = Severity.CRITICAL
    elif errors:
        severity = Severity.ERROR
    elif reviews:
        severity = Severity.REVIEW
    elif warnings:
        severity = Severity.WARNING
    elif unclassified_count > 0 or unclassified_text.strip():
        severity = Severity.INFO
        if not primary_error:
            primary_error = INFO_UNCLASSIFIED_TEXT
    else:
        severity = Severity.PASS

    # Create EvaluationIssue objects
    issues: List[EvaluationIssue] = []
    if severity == Severity.INFO:
        issues.append(EvaluationIssue(
            severity=Severity.INFO,
            rule_id=INFO_UNCLASSIFIED_TEXT,
            field=SECTION_FIELD_MAP.get(INFO_UNCLASSIFIED_TEXT, "未分類テキスト"),
            message=RULE_MESSAGES.get(INFO_UNCLASSIFIED_TEXT, "未分類のテキストが存在します"),
            condition=RULE_CONDITIONS.get(INFO_UNCLASSIFIED_TEXT, ""),
            fix_suggestion=RULE_FIX_SUGGESTIONS.get(INFO_UNCLASSIFIED_TEXT, ""),
        ))
    for err in errors:
        field_name = SECTION_FIELD_MAP.get(err, "その他")
        msg = RULE_MESSAGES.get(err, "必須項目に不備があります")
        cond = RULE_CONDITIONS.get(err, "")
        sug = RULE_FIX_SUGGESTIONS.get(err, "")
        sev = Severity.CRITICAL if err == CRIT_INSTRUCTION_EMPTY else Severity.ERROR
        issues.append(EvaluationIssue(
            severity=sev,
            rule_id=err,
            field=field_name,
            message=msg,
            condition=cond,
            fix_suggestion=sug
        ))

    for rev in reviews:
        field_name = SECTION_FIELD_MAP.get(rev, "志望校")
        msg = RULE_MESSAGES.get(rev, "確認を推奨します")
        cond = RULE_CONDITIONS.get(rev, "")
        sug = RULE_FIX_SUGGESTIONS.get(rev, "")
        issues.append(EvaluationIssue(
            severity=Severity.REVIEW,
            rule_id=rev,
            field=field_name,
            message=msg,
            condition=cond,
            fix_suggestion=sug
        ))

    for warn in warnings:
        field_name = SECTION_FIELD_MAP.get(warn, "その他")
        msg = RULE_MESSAGES.get(warn, "確認を推奨します")
        cond = RULE_CONDITIONS.get(warn, "")
        sug = RULE_FIX_SUGGESTIONS.get(warn, "")
        issues.append(EvaluationIssue(
            severity=Severity.WARNING,
            rule_id=warn,
            field=field_name,
            message=msg,
            condition=cond,
            fix_suggestion=sug
        ))

    # 機械的判定根拠の生成 (v8 §19)
    reasons: List[str] = []
    if CRIT_INSTRUCTION_EMPTY in errors:
        reasons.append("備考欄そのものが未入力または取得不能です。")

    if ERR_AUTHOR_MISSING in errors:
        if "作成者" not in parsed_sections:
            reasons.append("作成者見出しを検出できず、必須項目が未記載です。")
        else:
            reasons.append(f"作成者「{parsed_sections['作成者']}」が空欄または無効値です。")

    if ERR_TEXTBOOK_MISSING in errors:
        if "教材" not in parsed_sections:
            reasons.append("教材見出しを検出できず、必須項目が未記載です。")
        else:
            reasons.append("教材見出しの内容が空欄または無効値です。")

    if ERR_TEXTBOOK_STATUS_MISSING in errors or WARN_TEXTBOOK_NO_STATUS in warnings:
        invalid_tbs = [t.name for t in textbook_items if (not t.is_valid or t.category in ("不明", "未確定")) and t.name]
        if invalid_tbs:
            reasons.append(f"教材「{invalid_tbs[0]}」を検出しましたが、有効な教材ステータスを検出できませんでした。")
        else:
            reasons.append("教材を検出しましたが、有効な教材ステータスを検出できませんでした。")

    if ERR_PLAN_MISSING in errors:
        if "進め方" not in parsed_sections:
            reasons.append("進め方見出しを検出できず、必須項目が未記載です。")
        else:
            reasons.append("進め方見出しの内容が空欄または無効値です。")
    elif ERR_PLAN_TOO_SHORT in errors:
        plan_chars = count_effective_chars(parsed_sections.get("進め方", ""))
        reasons.append(f"進め方見出しの内容（{plan_chars}文字）が基準長（{config.min_plan_length}文字）未満です。")

    if ERR_INFO_MISSING in errors:
        if "生徒情報" not in parsed_sections:
            reasons.append("生徒情報見出しを検出できず、必須項目が空です。")
        else:
            reasons.append("生徒情報見出しの内容が空欄または無効値です。")
    elif ERR_INFO_TOO_SHORT in errors:
        info_chars = count_effective_chars(parsed_sections.get("生徒情報", ""))
        reasons.append(f"生徒情報見出しの内容（{info_chars}文字）が基準長（{config.min_info_length}文字）未満です。")

    if ERR_TEST_MISSING in errors:
        if "小テスト" not in parsed_sections:
            reasons.append("小テスト見出しを検出できず、必須項目が未記載です。")
        else:
            reasons.append("小テスト見出しの内容が空欄または無効値です。")

    if ERR_HOMEWORK_MISSING in errors:
        if "宿題" not in parsed_sections:
            reasons.append("宿題見出しを検出できず、必須項目が未記載です。")
        else:
            hw_content = parsed_sections.get("宿題", "").strip()
            reasons.append(f"宿題見出しの内容「{hw_content[:20]}」に具体的な指導内容が記載されていません。")

    if any(e in errors for e in (ERR_SCHOOL_REQUIRED_HIGH3, ERR_SCHOOL_REQUIRED_JUNIOR3, ERR_SCHOOL_REQUIRED_ELEM6)):
        grade_str = "高3" if ERR_SCHOOL_REQUIRED_HIGH3 in errors else ("公立中3" if ERR_SCHOOL_REQUIRED_JUNIOR3 in errors else "小6中受")
        reasons.append(f"志望校が必要な学年条件（{grade_str}）に該当しますが、該当セクションがありません。")

    if REV_SCHOOL_UNCERTAIN in reviews:
        sch_text = parsed_sections.get("志望校", "").strip()
        reasons.append(f"志望校に「{sch_text[:20]}」等の曖昧な表現が含まれており確認が必要です。")

    if ERR_COURSE_COUNT_MISSING in errors:
        reasons.append("講習授業ですが、講座数・授業数の記載がありません。")

    if WARN_GOAL_MISSING in warnings:
        reasons.append("講習授業ですが、目標の記載がありません（推奨）。")

    return EvaluationResult(
        severity=severity,
        errors=errors,
        reviews=reviews,
        warnings=warnings,
        parsed_sections=parsed_sections,
        unclassified_count=unclassified_count,
        unclassified_text=unclassified_text,
        primary_error=primary_error,
        fix_fields=fix_fields,
        issues=issues,
        reasons=reasons,
        parse_traces=parse_traces,
        textbook_items=textbook_items,
        unclassified_items=unclassified_items,
        section_statuses=section_statuses,
    )


def _get_bigrams(text: str) -> Set[str]:
    """Get character bigrams from text."""
    return set(text[i:i+2] for i in range(len(text) - 1))


def _calculate_jaccard(text1: str, text2: str) -> float:
    """Calculate character bigram Jaccard similarity between two texts."""
    if not text1 or not text2:
        return 0.0
    bigrams1 = _get_bigrams(text1)
    bigrams2 = _get_bigrams(text2)
    
    if not bigrams1 or not bigrams2:
        return 0.0
        
    intersection = bigrams1.intersection(bigrams2)
    union = bigrams1.union(bigrams2)
    
    return len(intersection) / len(union)


def evaluate_batch_duplicates(
    records: List[CurriculumRecord],
    results: List[EvaluationResult],
    config: AppConfig
) -> List[EvaluationResult]:
    """Evaluate copy-paste suspects across a batch of records."""
    # Do NOT modify input results - return new copies
    new_results = [copy.deepcopy(res) for res in results]
    
    # Group by normalized author name
    from collections import defaultdict
    import re
    
    author_groups = defaultdict(list)
    
    # Pre-process info texts
    _WHITESPACE_RE = re.compile(r'\s+')
    
    for i, res in enumerate(new_results):
        # Skip if parse failed
        if ERR_PARSER_EXCEPTION in res.errors:
            continue
            
        author = res.parsed_sections.get("作成者", "")
        # normalization is already done in evaluate_single_record, but just in case
        norm_author = normalize_author(author)
        
        if not norm_author:
            continue
            
        student_info = res.parsed_sections.get("生徒情報", "")
        if _is_blacklisted_or_empty(student_info):
            continue
            
        # Remove whitespace/newlines for comparison text
        cmp_text = _WHITESPACE_RE.sub("", student_info)
        if not cmp_text:
            continue
            
        author_groups[norm_author].append({
            'index': i,
            'cmp_text': cmp_text
        })
        
    # Find duplicates
    for author, group in author_groups.items():
        if len(group) < config.duplicate_info_threshold:
            continue
            
        # We need to find groups of similar records within this author
        # A simple approach: build connected components of similarity
        n = len(group)
        adj = [[] for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                text1 = group[i]['cmp_text']
                text2 = group[j]['cmp_text']
                
                is_similar = False
                if text1 == text2:
                    is_similar = True
                else:
                    if len(text1) >= 15 and len(text2) >= 15:
                        sim = _calculate_jaccard(text1, text2)
                        if sim >= 0.8:
                            is_similar = True
                            
                if is_similar:
                    adj[i].append(j)
                    adj[j].append(i)
                    
        # Find components
        visited = set()
        for i in range(n):
            if i not in visited:
                comp = []
                stack = [i]
                while stack:
                    curr = stack.pop()
                    if curr not in visited:
                        visited.add(curr)
                        comp.append(curr)
                        for neighbor in adj[curr]:
                            if neighbor not in visited:
                                stack.append(neighbor)
                                
                if len(comp) >= config.duplicate_info_threshold:
                    for idx in comp:
                        res_idx = group[idx]['index']
                        res = new_results[res_idx]
                        if WARN_COPY_PASTE_SUSPECTED not in res.warnings:
                            res.warnings.append(WARN_COPY_PASTE_SUSPECTED)
                            # Re-sort warnings
                            res.warnings.sort(key=lambda x: RULE_ORDER.index(x) if x in RULE_ORDER else 999)
                            # Add to issues
                            res.issues.append(EvaluationIssue(
                                severity=Severity.WARNING,
                                rule_id=WARN_COPY_PASTE_SUSPECTED,
                                field="生徒情報",
                                message=RULE_MESSAGES.get(WARN_COPY_PASTE_SUSPECTED, "類似内容のコピー＆ペーストが疑われます")
                            ))
                            # Update severity if it was PASS
                            if res.severity == Severity.PASS:
                                res.severity = Severity.WARNING
                                
    return new_results
