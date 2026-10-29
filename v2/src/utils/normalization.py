"""
データ正規化・パースユーティリティ (v2.0.0)
"""
import re
import unicodedata
from datetime import date
from typing import Optional, Tuple
from src.utils.constants import BLACKLIST, DEFAULT_EMPTY_VALUE

def normalize_text(text: Optional[str]) -> str:
    """不要な空白・改行を整理しNFKC正規化を行う"""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", str(text))
    # 前後の空白を削除
    return norm.strip()

def normalize_for_blacklist(text: Optional[str]) -> str:
    """ブラックリスト判定用に正規化"""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", str(text))
    # 全ての空白・改行を削除し小文字化
    return re.sub(r"\s+", "", norm).lower()

def is_blacklisted_or_empty(text: Optional[str]) -> bool:
    """空またはブラックリストに該当するか判定"""
    cleaned = normalize_for_blacklist(text)
    if not cleaned:
        return True
    for item in BLACKLIST:
        if cleaned == normalize_for_blacklist(item):
            return True
    return False

def clean_classroom_name(name: Optional[str]) -> str:
    """教室名から 'FS' / 'ＦＳ' (大文字・小文字・全角・半角) および余分な空白を除去"""
    if not name:
        return ""
    norm = normalize_text(name)
    cleaned = re.sub(r"^[FfＦｆ][SsＳｓ]\s*", "", norm)
    cleaned = re.sub(r"[FfＦｆ][SsＳｓ]", "", cleaned).strip()
    return cleaned

def parse_date(date_str: Optional[str]) -> Optional[date]:
    """日付文字列 (YYYY/MM/DD, YYYY-MM-DD, YYYY.MM.DD) を date オブジェクトに変換"""
    if not date_str:
        return None
    cleaned = re.sub(r"\s+", "", str(date_str))
    # YYYY/MM/DD
    m = re.search(r"(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", cleaned)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None

def format_date(d: Optional[date]) -> str:
    """date オブジェクトを YYYY/MM/DD 形式でフォーマット"""
    if not d:
        return DEFAULT_EMPTY_VALUE
    return d.strftime("%Y/%m/%d")

def parse_period(period_str: Optional[str]) -> Tuple[Optional[date], Optional[date], str]:
    """
    対策期間文字列 (例: '2026/03/01～2026/05/22' または '2026/03/01-2026/05/22') をパース
    戻り値: (start_date, end_date, formatted_period_str)
    """
    if not period_str:
        return None, None, DEFAULT_EMPTY_VALUE
    parts = re.split(r"[～~〜\-]+", str(period_str))
    if len(parts) >= 2:
        s_date = parse_date(parts[0])
        e_date = parse_date(parts[1])
        if s_date and e_date:
            formatted = f"{format_date(s_date)}～{format_date(e_date)}"
            return s_date, e_date, formatted
        elif s_date:
            return s_date, None, f"{format_date(s_date)}～"
        elif e_date:
            return None, e_date, f"～{format_date(e_date)}"
    elif len(parts) == 1:
        s_date = parse_date(parts[0])
        if s_date:
            return s_date, None, format_date(s_date)
    return None, None, DEFAULT_EMPTY_VALUE

def parse_score_and_max(text: Optional[str]) -> Tuple[str, str, str]:
    """
    '0 / 0' や '4 / 7' 等の得点/配点文字列をパースし、(得点, 配点, 得点率) を返す
    配点が0より大きい場合: 得点 / 配点 * 100
    それ以外: DEFAULT_EMPTY_VALUE
    """
    if not text:
        return DEFAULT_EMPTY_VALUE, DEFAULT_EMPTY_VALUE, DEFAULT_EMPTY_VALUE
    m = re.search(r"(\d+(?:\.\d+)?)\s*[/／]\s*(\d+(?:\.\d+)?)", str(text))
    if m:
        score_val = float(m.group(1))
        max_val = float(m.group(2))
        score_str = str(int(score_val)) if score_val.is_integer() else str(score_val)
        max_str = str(int(max_val)) if max_val.is_integer() else str(max_val)
        if max_val > 0:
            rate = round((score_val / max_val) * 100, 1)
            rate_str = str(int(rate)) if rate.is_integer() else str(rate)
            return score_str, max_str, rate_str
        else:
            return score_str, max_str, DEFAULT_EMPTY_VALUE
    return DEFAULT_EMPTY_VALUE, DEFAULT_EMPTY_VALUE, DEFAULT_EMPTY_VALUE

def count_effective_chars(text: Optional[str]) -> int:
    """空白・改行・記号を除いた有効文字数をカウント"""
    if not text:
        return 0
    norm = unicodedata.normalize("NFKC", str(text))
    # 空白、改行、代表的な装飾記号を除去
    cleaned = re.sub(r"[\s\r\n・\-\*\#【】\[\]\(\)（）:：、。／/〜~]+", "", norm)
    return len(cleaned)

def is_demo_student(student_name: Optional[str]) -> bool:
    """
    デモ生徒かどうかを判定する。
    「デモ 一（デモ イチ）」およびその表記揺れ（「デモ 一」「デモ一」等）、
    または名字が完全に「デモ」である生徒を判定。
    「デモ田」「デモ川」など姓がデモ単体でない生徒は False を返す。
    """
    if not student_name:
        return False
    norm = unicodedata.normalize("NFKC", str(student_name)).strip()
    if not norm:
        return False

    # 空白を除去した文字列で判定
    no_spaces = re.sub(r"\s+", "", norm)
    if no_spaces in ("デモ一(デモイチ)", "デモ一（デモイチ）", "デモ一", "デモ"):
        return True

    # 名字（空白区切りの先頭要素）が完全に「デモ」
    parts = norm.split()
    if parts and parts[0] == "デモ":
        return True

    # 空白がない場合でも「デモ一...」で始まる場合（例: デモ一(デモ イチ)）
    if no_spaces.startswith("デモ一(") or no_spaces.startswith("デモ一（") or no_spaces == "デモ一":
        return True

    return False
