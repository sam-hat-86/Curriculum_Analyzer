"""
備考欄テキスト見出し分割パーサー (v1準拠)
"""
import re
import unicodedata
from typing import Tuple, Dict, Optional, List, Any
from src.utils.constants import SECTION_ALIASES, CANONICAL_SECTIONS

# 正規化されたエイリアスリストの構築
_NORMALIZED_ALIASES = []
for canonical, aliases in SECTION_ALIASES.items():
    for alias in aliases:
        norm_alias = unicodedata.normalize('NFKC', alias).upper()
        norm_alias = re.sub(r'\s+', '', norm_alias)
        is_compound = any(sep in alias for sep in ['、', '・', '／', '(', '（', '特記事項'])
        _NORMALIZED_ALIASES.append((norm_alias, canonical, is_compound))

# 最長一致優先
_NORMALIZED_ALIASES.sort(key=lambda x: len(x[0]), reverse=True)

# 装飾記号
_HEADING_DECORATOR_PREFIX_RE = re.compile(r'^[\s#\-\*・○●◎■◆▼▶【\[<『「(（★☆⚠※\uFE0F]+')
_NUMBERED_HEADING_PREFIX_RE = re.compile(r'^\s*(?:[0-9０-９]+|[①-⑳])(?![回講節コマ期周日度])[.)）\]】\s、・]?\s*')
_KNOWN_SEP_RE = re.compile(r'^([】\]>』」)）]+)(?:\s*(:|：|\t)|\s*-\s*|\s*|$)|^([】\]>』」)）]*)(?:\s*(:|：|\t)|\s+-\s+|$)')
_COLON_RE = re.compile(r'[:：]')

def _match_known_heading(line: str) -> Optional[Tuple[str, str, str]]:
    """既知セクションの見出し照合。マッチ時は (canonical_name, body_text, matched_alias) を返す"""
    stripped = line.strip()
    if not stripped:
        return None

    m_prefix = _HEADING_DECORATOR_PREFIX_RE.match(stripped)
    prefix_len = m_prefix.end() if m_prefix else 0
    core_text = stripped[prefix_len:]

    m_num = _NUMBERED_HEADING_PREFIX_RE.match(core_text)
    if m_num:
        core_text = core_text[m_num.end():]

    for norm_alias, canonical, is_compound in _NORMALIZED_ALIASES:
        # エイリアスでの前方一致を判定
        temp_core = unicodedata.normalize('NFKC', core_text)
        temp_no_space = re.sub(r'^\s+', '', temp_core)
        upper_core = temp_no_space.upper()

        if upper_core.startswith(norm_alias):
            after_alias = temp_no_space[len(norm_alias):]
            m_sep = _KNOWN_SEP_RE.match(after_alias)
            if m_sep:
                body = after_alias[m_sep.end():].strip()
                return canonical, body, norm_alias
            elif not after_alias or after_alias[0] in ' :：\t-':
                body = re.sub(r'^[ :：\t\-]+', '', after_alias).strip()
                return canonical, body, norm_alias

    return None

def parse_instruction_sections(raw_text: Optional[str]) -> Tuple[Dict[str, str], List[str]]:
    """
    備考欄本文を行ごとに解析し、(セクション辞書, 未分類行リスト) を返す
    """
    if not raw_text:
        return {}, []

    sections: Dict[str, List[str]] = {}
    unclassified_lines: List[str] = []
    current_section: Optional[str] = None

    lines = raw_text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        match = _match_known_heading(stripped)
        if match:
            canonical, body, _ = match
            current_section = canonical
            if current_section not in sections:
                sections[current_section] = []
            if body:
                sections[current_section].append(body)
        else:
            if current_section is not None:
                sections[current_section].append(stripped)
            else:
                unclassified_lines.append(stripped)

    # リストを改行で結合
    result_sections = {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}
    return result_sections, unclassified_lines
