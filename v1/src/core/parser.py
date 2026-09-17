"""
指示書section parser
改善案 v4 に準拠し、既知セクションと未知見出しを厳密に分離し、
パーサー認識信頼度 (HIGH/MEDIUM/LOW)、未分類テキスト分類 (UNKNOWN_HEADING/FREE_TEXT/PARSER_CANDIDATE)、
生徒情報からの志望校補助抽出、および診断モード (Parser Debug Mode) を提供する。
"""
import re
import unicodedata
from typing import Tuple, Dict, Optional, List, Any

from core.constants import SECTION_ALIASES, CANONICAL_SECTIONS
from core.models import ConfidenceLevel, UnclassifiedType, UnclassifiedItem

# 正規化されたエイリアスリストの構築 (モジュールロード時1回)
# [(normalized_alias, canonical_name, is_compound), ...]
_NORMALIZED_ALIASES = []
for canonical, aliases in SECTION_ALIASES.items():
    for alias in aliases:
        norm_alias = unicodedata.normalize('NFKC', alias).upper()
        norm_alias = re.sub(r'\s+', '', norm_alias)
        is_compound = any(sep in alias for sep in ['、', '・', '／', '(', '（', '特記事項'])
        _NORMALIZED_ALIASES.append((norm_alias, canonical, is_compound))

# 最長一致優先のため、エイリアス長の降順でソート
_NORMALIZED_ALIASES.sort(key=lambda x: len(x[0]), reverse=True)

# 既知見出し用の行頭装飾記号 (Markdown #、箇条書き、括弧、記号、★☆⚠⚠️※など)
_HEADING_DECORATOR_PREFIX_RE = re.compile(r'^[\s#\-\*・○●◎■◆▼▶【\[<『「(（★☆⚠※\uFE0F]+')

# 番号付き見出しプレフィックス (1作成者、2志望校、1.作成者、①作成者 など) (§5.2)
# ※1回目、1講などの講義回数プレフィックスは除外する
_NUMBERED_HEADING_PREFIX_RE = re.compile(r'^\s*(?:[0-9０-９]+|[①-⑳])(?![回講節コマ期周日度])[.)）\]】\s、・]?\s*')

# 既知見出しの終端パターン
_KNOWN_SEP_RE = re.compile(r'^([】\]>』」)）]+)(?:\s*(:|：|\t)|\s*-\s*|\s*|$)|^([】\]>』」)）]*)(?:\s*(:|：|\t)|\s+-\s+|$)')

# 漢字・ひらがな・カタカナ・英数字 (複合語の誤爆防止用)
_FOLLOWING_WORD_RE = re.compile(r'^[a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]')

# 未知見出し用の装飾プレフィックス (見出しマーク等。括弧自体は括弧囲み見出し判定で照合するため含めない)
_UNKNOWN_DECORATOR_RE = re.compile(r'^[\s#■◆▼▶★☆⚠※\uFE0F]+')

# コロン記号
_COLON_RE = re.compile(r'[:：]')

# 講座数・目標の抽出用正規表現 (§13)
_COURSE_COUNT_RE = re.compile(r'(?:講座数|講座・授業数|講座:授業数|講座：授業数)\s*[:：]?\s*(.+)', re.IGNORECASE)
_GOAL_RE = re.compile(r'目標\s*[:：]?\s*(.+)', re.IGNORECASE)

# 生徒情報内の志望校補助抽出用正規表現 (§11)
_SCHOOL_AUX_RE = re.compile(r'(?:現時点での)?志望校(?:は|：|:|\s)\s*[、,]?\s*([^\s、。\n]{2,30})')

# 未知見出しから推定されるセクション候補 (§17)
_SECTION_CANDIDATE_KEYWORDS = {
    "作成者": ["作成", "担当", "講師", "記入"],
    "志望校": ["志望", "受験", "進路", "第一志望", "第1志望"],
    "教材": ["教材", "テキスト", "ワーク", "問題集", "参考書"],
    "進め方": ["進め方", "方針", "指導", "計画", "カリキュラム", "授業方針", "指導方針"],
    "生徒情報": ["生徒", "備考", "特記事項", "状況", "様子", "生徒備考"],
    "小テスト": ["テスト", "単語", "確認", "単語テスト", "小テスト"],
    "宿題": ["宿題", "課題", "家庭学習"],
    "講座数": ["講座", "コマ", "授業数"],
    "目標": ["目標", "ゴール"],
}


def _estimate_section(norm_heading: str) -> str:
    """未知見出しが既知セクションに類似しているか推定する"""
    for sec, kws in _SECTION_CANDIDATE_KEYWORDS.items():
        if any(kw in norm_heading for kw in kws):
            return sec
    return ""


def is_decoration_only(line: str) -> bool:
    """行が空行、または装飾記号のみで構成されているか判定する"""
    text = re.sub(r'\s+', '', line)
    if not text:
        return True
    return all(c in '-=_*~ー―−－〜・+#' for c in text)


def _match_known_heading(line: str) -> Optional[Tuple[str, str, str, str]]:
    """
    行が既知セクションの見出しであるか照合する。
    マッチした場合は (canonical_name, body_text, matched_alias, confidence) を返し、
    マッチしなければ None を返す。
    """
    stripped = line.strip()
    if not stripped:
        return None

    # 装飾記号を除去
    m_prefix = _HEADING_DECORATOR_PREFIX_RE.match(stripped)
    prefix_len = m_prefix.end() if m_prefix else 0
    core_text = stripped[prefix_len:]

    # 番号付き見出しプレフィックス (1作成者、2志望校、1.作成者、①作成者 など) の除去 (§5.2)
    m_num = _NUMBERED_HEADING_PREFIX_RE.match(core_text)
    if m_num:
        num_len = m_num.end()
        prefix_len += num_len
        core_text = core_text[num_len:]
        # 番号の後に装飾記号が続く場合 (e.g. 1.【作成者】)
        m_prefix2 = _HEADING_DECORATOR_PREFIX_RE.match(core_text)
        if m_prefix2:
            prefix_len += m_prefix2.end()
            core_text = core_text[m_prefix2.end():]

    upper_core = unicodedata.normalize('NFKC', core_text).upper()
    upper_core_no_space = re.sub(r'\s+', '', upper_core)

    for norm_alias, canonical, is_compound in _NORMALIZED_ALIASES:
        if upper_core_no_space.startswith(norm_alias):
            alias_len_in_core = 0
            accum_norm = ""
            for idx, ch in enumerate(core_text):
                ch_norm = unicodedata.normalize('NFKC', ch).upper()
                if not ch_norm.isspace():
                    accum_norm += ch_norm
                if accum_norm == norm_alias:
                    alias_len_in_core = idx + 1
                    break

            if alias_len_in_core == 0:
                continue

            remainder = core_text[alias_len_in_core:]

            # 複合語誤認防止
            if remainder and not remainder[0] in '】]>』」)）':
                if _FOLLOWING_WORD_RE.match(remainder):
                    continue

            m_sep = _KNOWN_SEP_RE.match(remainder)
            if m_sep:
                sep_len = m_sep.end()
                body_start = prefix_len + alias_len_in_core + sep_len
                body = stripped[body_start:].strip()
                conf = ConfidenceLevel.MEDIUM.value if is_compound else ConfidenceLevel.HIGH.value
                return (canonical, body, norm_alias, conf)

    return None


def _is_unknown_heading(line: str) -> Optional[Tuple[str, str]]:
    """
    行が未知の見出し（unknown heading）の構文パターンを持つか判定する。
    マッチした場合は (heading_label, body_text) を返し、マッチしなければ None を返す。
    """
    s = line.strip()
    if not s:
        return None

    if s.startswith(('http://', 'https://', 'file:///')):
        return None

    if s.startswith(('・', '-', '*', '−', '―', '–', '—')):
        return None

    m_dec = _UNKNOWN_DECORATOR_RE.match(s)
    core = s[m_dec.end():] if m_dec else s

    m_num = _NUMBERED_HEADING_PREFIX_RE.match(core)
    if m_num:
        core = core[m_num.end():]
        m_dec2 = _UNKNOWN_DECORATOR_RE.match(core)
        if m_dec2:
            core = core[m_dec2.end():]

    # v7 §4.5: 既知のメタ見出し（【目標】、【講座数】等）は補助情報・未分類として扱う
    bracket_match = re.match(r'^[【\[<『「(（](.+?)[】\]>』」)）]\s*(.*)$', core)
    if bracket_match:
        label = bracket_match.group(1).strip()
        after = bracket_match.group(2).strip()
        norm_label = unicodedata.normalize('NFKC', label)
        if any(mkw in norm_label for mkw in ["目標", "講座", "授業数", "コマ数"]):
            return (label, after)

    # v7 §4.5: 【既知見出し】以外の【】で囲まれた文字列は、通常本文中の注釈・自由記述として扱う。
    # したがって、未知の括弧囲みのみの行は未知見出しとせず通常本文とする。
    
    # コロン区切り見出し (v7 §4.4: 行頭・短い・明確な区切り・ラベルらしさ)
    col_match = _COLON_RE.search(core)
    if col_match:
        label = core[:col_match.start()].strip()
        label_clean = re.sub(r'^[【\[<『「(（]+|[】\]>』」)）]+$', '', label).strip()
        if 2 <= len(label_clean) <= 15 and not any(c in '。、！？!?…' for c in label_clean):
            after = core[col_match.end():].strip()
            # 数字のみは除外
            if label_clean.isdigit():
                return None
            # v7 §4.4: 番号＋コロン (1回目：, 第1回：, 1講：, 1コマ目：, 1日目：, 回目： 等) は通常本文とする
            if re.match(r'^(?:[第]?[0-9０-９]+|[①-⑳])*[回講節コマ期周日度](?:目)?$', label_clean) or label_clean in ["回目", "講目", "コマ目", "日目"]:
                return None
            # v7 §4.4: 教材名らしい表記やURL等は未知見出しとしない
            if any(kw in label_clean for kw in ["テキスト", "ワーク", "ドリル", "問題集", "ノート", "チャート", "新演習", "フォレスタ", "ウインパス", "教科書"]):
                return None
            # 単なるURLやパスは除外
            if any(kw in label_clean.lower() for kw in ["http", "https", "www", "file"]):
                return None
            return (label_clean, after)

    return None


# 全見出しキーワード (論理改行復元用 v6 §5.3)
_ALL_HEADING_KEYWORDS = set()
for _canon, _aliases in SECTION_ALIASES.items():
    for _al in _aliases:
        _ALL_HEADING_KEYWORDS.add(_al)
_ALL_HEADING_KEYWORDS.update(["目標", "講座数", "講座・授業数", "授業数", "講座"])
_HEADING_KW_PATTERN = "|".join(re.escape(k) for k in sorted(_ALL_HEADING_KEYWORDS, key=len, reverse=True))

_LOGICAL_NEWLINE_RE = re.compile(
    rf'(?<!^)(?<!\n)\s*(?=(?:[★☆⚠※\uFE0F]|\b[0-9０-９]+[.)）\]】\s、・]?\s*)?(?:[【\[<『「](?:{_HEADING_KW_PATTERN})[】\]>』」]|(?<=\s)(?:{_HEADING_KW_PATTERN})\s*[:：]))'
)


def restore_logical_newlines(text: str) -> str:
    """
    元のHTMLに改行がなくても、既知見出しの開始位置を検出した場合は論理的に分割する (v6 §5.3)。
    例：【作成者】山田【目標】定期テスト対策【教材】ロードスター
    →
    【作成者】山田
    【目標】定期テスト対策
    【教材】ロードスター
    """
    if not text:
        return ""
    return _LOGICAL_NEWLINE_RE.sub("\n", text)


def parse_sections_detailed(
    cleaned_instruction: str
) -> Tuple[Dict[str, str], int, str, List[Dict[str, str]], Dict[str, str], List[UnclassifiedItem]]:
    """
    指示書テキストを詳細解析し、正準セクション辞書、未分類行数、未分類テキスト、
    行単位のパーストレース、抽出された補助メタ情報、および未分類アイテムリストを返す。
    """
    parsed_sections: Dict[str, List[str]] = {k: [] for k in CANONICAL_SECTIONS.keys()}
    unclassified_lines: List[str] = []
    unclassified_count = 0
    parse_traces: List[Dict[str, str]] = []
    meta_parsed: Dict[str, str] = {}
    unclassified_items: List[UnclassifiedItem] = []

    current_section: Optional[str] = None

    if not cleaned_instruction:
        return (
            {k: "" for k in CANONICAL_SECTIONS.keys()},
            0,
            "",
            [],
            {},
            []
        )

    # 論理改行の復元 (v6 §5.3)
    restored_instruction = restore_logical_newlines(cleaned_instruction)
    lines = restored_instruction.split('\n')

    for line_idx, line in enumerate(lines, 1):
        stripped_line = line.strip()
        if not stripped_line:
            continue

        # 1. 既知見出しの照合
        known_match = _match_known_heading(line)
        if known_match:
            canonical_name, body, matched_alias, conf = known_match
            current_section = canonical_name
            if body:
                parsed_sections[current_section].append(body)

            parse_traces.append({
                "line": str(line_idx),
                "raw": line,
                "heading": matched_alias,
                "normalized": canonical_name,
                "section": canonical_name,
                "confidence": conf,
                "body": body,
            })
            continue

        # 2. 未知見出しの照合
        unknown_match = _is_unknown_heading(line)
        if unknown_match:
            heading_label, body = unknown_match
            current_section = "UNKNOWN"
            unclassified_lines.append(line)
            if not is_decoration_only(line):
                unclassified_count += 1

            norm_label = unicodedata.normalize('NFKC', heading_label)
            if "講座" in norm_label:
                meta_parsed["course_count"] = body or line
            elif "目標" in norm_label:
                meta_parsed["goal"] = body or line

            est_sec = _estimate_section(norm_label)
            item_type = UnclassifiedType.PARSER_CANDIDATE if est_sec else UnclassifiedType.UNKNOWN_HEADING
            unclassified_items.append(UnclassifiedItem(
                line_number=line_idx,
                raw_text=line,
                item_type=item_type,
                candidate_heading=heading_label,
                estimated_section=est_sec,
            ))

            parse_traces.append({
                "line": str(line_idx),
                "raw": line,
                "heading": heading_label,
                "normalized": f"未分類({heading_label})",
                "section": "unclassified",
                "confidence": "-",
                "body": body or line,
            })
            continue

        # 3. 通常本文行の処理
        if current_section == "UNKNOWN" or current_section is None:
            unclassified_lines.append(line)
            if not is_decoration_only(line):
                unclassified_count += 1

            m_cc = _COURSE_COUNT_RE.search(line)
            if m_cc and "course_count" not in meta_parsed:
                meta_parsed["course_count"] = m_cc.group(1).strip()
            m_goal = _GOAL_RE.search(line)
            if m_goal and "goal" not in meta_parsed:
                meta_parsed["goal"] = m_goal.group(1).strip()

            unclassified_items.append(UnclassifiedItem(
                line_number=line_idx,
                raw_text=line,
                item_type=UnclassifiedType.FREE_TEXT,
                candidate_heading="",
                estimated_section="",
            ))

            parse_traces.append({
                "line": str(line_idx),
                "raw": line,
                "heading": "-",
                "normalized": "-",
                "section": "unclassified",
                "confidence": "-",
                "body": line,
            })
        else:
            parsed_sections[current_section].append(line)
            parse_traces.append({
                "line": str(line_idx),
                "raw": line,
                "heading": "-",
                "normalized": "-",
                "section": current_section,
                "confidence": "-",
                "body": line,
            })

    final_sections = {k: '\r\n'.join(v) for k, v in parsed_sections.items()}

    # 4. 生徒情報内の志望校補助抽出 (§11)
    if not final_sections.get("志望校") and final_sections.get("生徒情報"):
        student_info_text = final_sections["生徒情報"]
        m_aux = _SCHOOL_AUX_RE.search(student_info_text)
        if m_aux:
            aux_school = m_aux.group(1).strip()
            aux_school = re.sub(r'(?:です|だ|等|など|を希望|希望|志望)$', '', aux_school).strip()
            from core.normalization import normalize_for_blacklist
            from core.constants import BLACKLIST
            norm_aux = normalize_for_blacklist(aux_school)
            if norm_aux and norm_aux not in [normalize_for_blacklist(b) for b in BLACKLIST]:
                final_sections["志望校"] = aux_school
                meta_parsed["aux_school"] = aux_school
                parse_traces.append({
                    "line": "AUX",
                    "raw": m_aux.group(0),
                    "heading": "生徒情報内志望校",
                    "normalized": "志望校",
                    "section": "志望校",
                    "confidence": ConfidenceLevel.LOW.value,
                    "body": aux_school,
                })

    unclassified_text = '\r\n'.join(unclassified_lines)

    return final_sections, unclassified_count, unclassified_text, parse_traces, meta_parsed, unclassified_items


def parse_sections(cleaned_instruction: str) -> Tuple[Dict[str, str], int, str]:
    """
    指示書テキストを解析し、正準セクション辞書、未分類行数、未分類テキストを返す。
    既存インターフェースとの完全互換ラッパー。
    """
    sections, count, text, _, _, _ = parse_sections_detailed(cleaned_instruction)
    return sections, count, text
