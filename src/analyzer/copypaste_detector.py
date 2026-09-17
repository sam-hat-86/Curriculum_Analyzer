"""
備考欄コピペ疑い検出エンジン (仕様書§23)
"""
import re
import unicodedata
from typing import Dict, List, Set
from src.models.curriculum import CurriculumDetailData
from src.utils.constants import (
    WARN_COPY_PASTE_SUSPECTED,
    RULE_FIX_SUGGESTIONS,
    JACCARD_SIMILARITY_THRESHOLD,
    DUPLICATE_INFO_THRESHOLD,
)

def _clean_text_for_comparison(text: str) -> str:
    norm = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", norm)

def _get_char_ngrams(text: str, n: int = 2) -> Set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i+n] for i in range(len(text) - n + 1)}

def _calc_jaccard(s1: Set[str], s2: Set[str]) -> float:
    if not s1 and not s2:
        return 1.0
    union = s1 | s2
    if not union:
        return 0.0
    return len(s1 & s2) / len(union)

def detect_copy_paste(records: List[CurriculumDetailData]):
    """
    全レコードを同一作成者グループごとに比較し、3件以上の類似がある場合に
    WARN_COPY_PASTE_SUSPECTED を付与する
    """
    author_groups: Dict[str, List[CurriculumDetailData]] = {}

    for rec in records:
        if not rec.instruction_eval or not rec.instruction_eval.author:
            continue
        norm_author = re.sub(r"\s+", "", rec.instruction_eval.author).upper()
        if not norm_author:
            continue
        if norm_author not in author_groups:
            author_groups[norm_author] = []
        author_groups[norm_author].append(rec)

    for author, group in author_groups.items():
        if len(group) < DUPLICATE_INFO_THRESHOLD:
            continue

        # 各レコードの生徒情報テキスト
        info_texts = []
        for rec in group:
            st_info = rec.instruction_eval.student_info if rec.instruction_eval else ""
            cleaned = _clean_text_for_comparison(st_info)
            info_texts.append(cleaned)

        # 類似グラフの構築
        n = len(group)
        similar_sets: List[Set[int]] = [{i} for i in range(n)]

        for i in range(n):
            txt_i = info_texts[i]
            if not txt_i or len(txt_i) < 3:
                continue
            for j in range(i + 1, n):
                txt_j = info_texts[j]
                if not txt_j or len(txt_j) < 3:
                    continue

                is_similar = False
                if len(txt_i) < 15 or len(txt_j) < 15:
                    if txt_i == txt_j:
                        is_similar = True
                else:
                    ng_i = _get_char_ngrams(txt_i, 2)
                    ng_j = _get_char_ngrams(txt_j, 2)
                    if _calc_jaccard(ng_i, ng_j) >= JACCARD_SIMILARITY_THRESHOLD:
                        is_similar = True

                if is_similar:
                    # 連結成分
                    s = similar_sets[i] | similar_sets[j]
                    for idx in s:
                        similar_sets[idx] = s

        # 3件以上重複するクラスターに属するレコードへ警告付与
        flagged_indices = set()
        for s in similar_sets:
            if len(s) >= DUPLICATE_INFO_THRESHOLD:
                flagged_indices |= s

        for idx in flagged_indices:
            rec = group[idx]
            if rec.instruction_eval:
                if WARN_COPY_PASTE_SUSPECTED not in rec.instruction_eval.warnings:
                    rec.instruction_eval.warnings.append(WARN_COPY_PASTE_SUSPECTED)
                    rec.instruction_eval.fix_items.append(RULE_FIX_SUGGESTIONS[WARN_COPY_PASTE_SUSPECTED])
                    if rec.instruction_eval.severity == "PASS":
                        rec.instruction_eval.severity = "WARNING"
