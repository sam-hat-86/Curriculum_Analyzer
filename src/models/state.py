"""
処理状態およびタイミング分類 Enum
"""
from enum import Enum

class ProcessState(str, Enum):
    """取得・解析・保存の状態 (仕様書§5)"""
    UNFETCHED = "未取得"
    FETCHING = "取得中"
    FETCHED = "取得済み"
    FETCH_FAILED = "取得失敗"
    PARSE_PENDING = "解析待ち"
    PARSING = "解析中"
    PARSED = "解析済み"
    PARSE_FAILED = "解析失敗"
    SAVED = "保存済み"

class TimingCategory(str, Enum):
    """単元の実施タイミング分類 (仕様書§13)"""
    ON_TIME = "期間内"
    BEFORE = "期間前"
    AFTER = "期間後"
    UNDECIDED = "判定保留"
    UNEXECUTED = "未実施"
