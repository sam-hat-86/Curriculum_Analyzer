"""
システム全体で使用する定数定義
"""

# Application
APP_BASE_TITLE = "授業指示書・カリキュラム 精査ブラウザ"
__version__ = "1.0.0"
RULE_VERSION = "1.0.0"
EXE_NAME = "Curriculum_Analyzer.exe"
MUTEX_NAME = "Local\\CurriculumCheckerAppSingleInstanceMutex"

# Cache
CACHE_SCHEMA_VERSION = 1
CACHE_FILENAME = "_session_cache.jsonl"
CACHE_TMP_FILENAME = "_session_cache.jsonl.tmp"

# Limits & Windows settings
WINDOW_INITIAL_WIDTH = 1380
WINDOW_INITIAL_HEIGHT = 880
WINDOW_MINIMUM_WIDTH = 1024
WINDOW_MINIMUM_HEIGHT = 700

ZOOM_MIN = 0.5
ZOOM_MAX = 2.0
ZOOM_STEP = 0.1

PAGE_LOAD_TIMEOUT = 10
SCREEN_TRANSITION_WAIT = 5
POLLING_INTERVAL_MS = 100
CACHE_RETRY_MAX = 3
CACHE_RETRY_INTERVAL_MS = 100

UNDO_MAX_HISTORY = 30
MIN_PLAN_LENGTH = 5
MIN_INFO_LENGTH = 3
DUPLICATE_INFO_THRESHOLD = 3

# Rule IDs (CRITICAL) - 授業実施・引継ぎに重大な問題 (§2)
CRIT_INSTRUCTION_EMPTY = "CRIT_INSTRUCTION_EMPTY"

# Rule IDs (ERROR) - 具体化された新エラー体系 (§10, §16)
ERR_SECTION_MISSING = "ERR_SECTION_MISSING"
ERR_SECTION_EMPTY = "ERR_SECTION_EMPTY"
ERR_AUTHOR_MISSING = "ERR_AUTHOR_MISSING"
ERR_TEXTBOOK_MISSING = "ERR_TEXTBOOK_MISSING"
ERR_TEXTBOOK_STATUS_MISSING = "ERR_TEXTBOOK_STATUS_MISSING"
ERR_PLAN_MISSING = "ERR_PLAN_MISSING"
ERR_PLAN_TOO_SHORT = "ERR_PLAN_TOO_SHORT"
ERR_INFO_MISSING = "ERR_INFO_MISSING"
ERR_INFO_TOO_SHORT = "ERR_INFO_TOO_SHORT"
ERR_TEST_MISSING = "ERR_TEST_MISSING"
ERR_HOMEWORK_MISSING = "ERR_HOMEWORK_MISSING"
ERR_SCHOOL_REQUIRED_HIGH3 = "ERR_SCHOOL_REQUIRED_HIGH3"
ERR_SCHOOL_REQUIRED_JUNIOR3 = "ERR_SCHOOL_REQUIRED_JUNIOR3"
ERR_SCHOOL_REQUIRED_ELEM6 = "ERR_SCHOOL_REQUIRED_ELEM6"
ERR_COURSE_COUNT_MISSING = "ERR_COURSE_COUNT_MISSING"
ERR_PARSER_EXCEPTION = "ERR_PARSER_EXCEPTION"
ERR_INTERNAL_EVALUATION = "ERR_INTERNAL_EVALUATION"

# Rule IDs (REVIEW) - 人間による確認が必要な状態 (§2, §15.3)
REV_SCHOOL_UNCERTAIN = "REV_SCHOOL_UNCERTAIN"

# Rule IDs (WARNING)
WARN_TEXTBOOK_NO_STATUS = "WARN_TEXTBOOK_NO_STATUS"
WARN_SCHOOL_NO_TYPE = "WARN_SCHOOL_NO_TYPE"
WARN_TEST_CRITERIA_MISSING = "WARN_TEST_CRITERIA_MISSING"
WARN_GOAL_MISSING = "WARN_GOAL_MISSING"
WARN_COPY_PASTE_SUSPECTED = "WARN_COPY_PASTE_SUSPECTED"
WARN_UNCLASSIFIED_TEXT = "WARN_UNCLASSIFIED_TEXT"

# Rule IDs (INFO) - エラー・レビュー・警告がなく未分類テキストのみ存在する場合 (v7 §3)
INFO_UNCLASSIFIED_TEXT = "INFO_UNCLASSIFIED_TEXT"

# RULE_MESSAGES (§10, §16, §24, v7 §7, §35)
RULE_MESSAGES = {
    CRIT_INSTRUCTION_EMPTY: "備考欄が未作成です",
    ERR_SECTION_MISSING: "必須項目が不足しています",
    ERR_SECTION_EMPTY: "必須項目が空欄です",
    ERR_AUTHOR_MISSING: "作成者が未記載です",
    ERR_TEXTBOOK_MISSING: "教材が未記載です",
    ERR_TEXTBOOK_STATUS_MISSING: "教材の所持状態が未記載です",
    ERR_PLAN_MISSING: "進め方が未記載です",
    ERR_PLAN_TOO_SHORT: "進め方の文字数が不足しています",
    ERR_INFO_MISSING: "生徒情報が未記載です",
    ERR_INFO_TOO_SHORT: "生徒情報の文字数が不足しています",
    ERR_TEST_MISSING: "小テストが未記載です",
    ERR_HOMEWORK_MISSING: "宿題の内容が未記載です",
    ERR_SCHOOL_REQUIRED_HIGH3: "高3のため志望校が必須です",
    ERR_SCHOOL_REQUIRED_JUNIOR3: "公立中3のため志望校が必須です",
    ERR_SCHOOL_REQUIRED_ELEM6: "小6中受のため志望校が必須です",
    ERR_COURSE_COUNT_MISSING: "講習授業のため講座数が必須です",
    ERR_PARSER_EXCEPTION: "解析処理中に例外が発生しました",
    ERR_INTERNAL_EVALUATION: "内部評価エラー",
    REV_SCHOOL_UNCERTAIN: "志望校の記載内容に確認が必要です",
    WARN_TEXTBOOK_NO_STATUS: "教材の所持状態が未記載です",
    WARN_SCHOOL_NO_TYPE: "学校の区分が不明です",
    WARN_TEST_CRITERIA_MISSING: "小テストの範囲または合格基準が不明です",
    WARN_GOAL_MISSING: "講習授業の目標の記載が推奨されます",
    WARN_COPY_PASTE_SUSPECTED: "類似内容のコピー＆ペーストが疑われます",
    WARN_UNCLASSIFIED_TEXT: "未分類のテキストが存在します",
    INFO_UNCLASSIFIED_TEXT: "未分類のテキストが存在します",
}

# 発生条件 (§21, §28, v7 §7)
RULE_CONDITIONS = {
    CRIT_INSTRUCTION_EMPTY: "備考欄が空文字、空白のみ、または取得失敗",
    ERR_AUTHOR_MISSING: "作成者見出しがない、または空欄・ブラックリスト",
    ERR_TEXTBOOK_MISSING: "教材見出しがない、または空欄・ブラックリスト",
    ERR_TEXTBOOK_STATUS_MISSING: "教材に有効なステータスがない、または未確定（所持?等）",
    ERR_PLAN_MISSING: "進め方見出しがない、または空欄・ブラックリスト",
    ERR_PLAN_TOO_SHORT: "進め方の有効文字数が設定未満",
    ERR_INFO_MISSING: "生徒情報見出しがない、または空欄・ブラックリスト",
    ERR_INFO_TOO_SHORT: "生徒情報の有効文字数が設定未満",
    ERR_TEST_MISSING: "小テスト見出しがない、または空欄・ブラックリスト",
    ERR_HOMEWORK_MISSING: "宿題見出しがない、または空欄・ブラックリスト（なし等）",
    ERR_SCHOOL_REQUIRED_HIGH3: "高3で志望校見出しがない、または空欄",
    ERR_SCHOOL_REQUIRED_JUNIOR3: "公立中3で志望校見出しがない、または空欄",
    ERR_SCHOOL_REQUIRED_ELEM6: "小6中受で志望校見出しがない、または空欄",
    ERR_COURSE_COUNT_MISSING: "受講区分が講習で講座数・授業数の記載がない",
    REV_SCHOOL_UNCERTAIN: "志望校に学校名と判断できない曖昧な記述がある",
    WARN_GOAL_MISSING: "受講区分が講習で目標の記載がない",
    WARN_SCHOOL_NO_TYPE: "志望校に私立/公立/都立等の区分表記がない",
    WARN_COPY_PASTE_SUSPECTED: "同一作成者内で生徒情報が類似",
    WARN_UNCLASSIFIED_TEXT: "解析で未分類の行が存在する",
    INFO_UNCLASSIFIED_TEXT: "エラー・警告はないが未分類テキストが存在する",
    ERR_PARSER_EXCEPTION: "解析処理中に例外が発生",
    ERR_INTERNAL_EVALUATION: "内部評価エラー",
    ERR_SECTION_MISSING: "必須項目が不足している",
    ERR_SECTION_EMPTY: "必須項目が空欄",
}

# 修正方法・推奨アクション (§24, §28, v7 §7)
RULE_FIX_SUGGESTIONS = {
    CRIT_INSTRUCTION_EMPTY: "備考欄を入力してください",
    ERR_AUTHOR_MISSING: "作成者（担当講師名）を記載してください",
    ERR_TEXTBOOK_MISSING: "使用教材を記載してください",
    ERR_TEXTBOOK_STATUS_MISSING: "教材の所持・未所持・持込・購入・コピー等を記載してください",
    ERR_PLAN_MISSING: "進め方を記載してください",
    ERR_PLAN_TOO_SHORT: "進め方の指導方針を具体的に記載してください",
    ERR_INFO_MISSING: "生徒情報を記載してください",
    ERR_INFO_TOO_SHORT: "生徒の学力状況や性格などを具体的に記載してください",
    ERR_TEST_MISSING: "小テストの実施内容を記載してください",
    ERR_HOMEWORK_MISSING: "宿題の内容を具体的に記載してください",
    ERR_SCHOOL_REQUIRED_HIGH3: "高3のため志望校を記載してください",
    ERR_SCHOOL_REQUIRED_JUNIOR3: "公立中3のため志望校を記載してください",
    ERR_SCHOOL_REQUIRED_ELEM6: "小6中受のため志望校を記載してください",
    ERR_COURSE_COUNT_MISSING: "講習授業のため講座数・授業数を記載してください",
    REV_SCHOOL_UNCERTAIN: "志望校を正式な学校名（大学・高校・中学名）で記載してください",
    WARN_GOAL_MISSING: "講習授業の目標の記載を推奨します",
    WARN_SCHOOL_NO_TYPE: "学校区分（私立/公立/都立等）を記載してください",
    WARN_COPY_PASTE_SUSPECTED: "他生徒との重複記述がないか確認してください",
    WARN_UNCLASSIFIED_TEXT: "見出しの表記揺れまたは記載内容を確認してください",
    INFO_UNCLASSIFIED_TEXT: "必要に応じて見出しの表記揺れまたは記載内容を確認してください",
}

# 最重要エラー判定の優先順位 (§2, §4)
PRIMARY_RULE_PRIORITY = [
    CRIT_INSTRUCTION_EMPTY,
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
    ERR_SECTION_MISSING,
    ERR_SECTION_EMPTY,
    ERR_PARSER_EXCEPTION,
    ERR_INTERNAL_EVALUATION,
    REV_SCHOOL_UNCERTAIN,
    WARN_TEXTBOOK_NO_STATUS,
    WARN_SCHOOL_NO_TYPE,
    WARN_GOAL_MISSING,
    WARN_COPY_PASTE_SUSPECTED,
    WARN_UNCLASSIFIED_TEXT,
    INFO_UNCLASSIFIED_TEXT,
]

# RULE_ORDER (集計・ソート用 v7 §3: CRITICAL > ERROR > REVIEW > WARNING > INFO)
RULE_ORDER = [
    CRIT_INSTRUCTION_EMPTY,
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
    ERR_SECTION_MISSING,
    ERR_SECTION_EMPTY,
    ERR_PARSER_EXCEPTION,
    ERR_INTERNAL_EVALUATION,
    REV_SCHOOL_UNCERTAIN,
    WARN_TEXTBOOK_NO_STATUS,
    WARN_SCHOOL_NO_TYPE,
    WARN_GOAL_MISSING,
    WARN_COPY_PASTE_SUSPECTED,
    WARN_UNCLASSIFIED_TEXT,
    INFO_UNCLASSIFIED_TEXT,
]

# CANONICAL_SECTIONS (§3)
CANONICAL_SECTIONS = {
    "作成者": {"required": True},
    "志望校": {"required": False},  # 条件付き必須 (高3, 公立中3, 小6中受)
    "教材": {"required": True},
    "進め方": {"required": True},
    "生徒情報": {"required": True},
    "小テスト": {"required": True},
    "宿題": {"required": True},
}

# SECTION_ALIASES (v7 §4.3)
SECTION_ALIASES = {
    "作成者": [
        "作成者・作成日",
        "作成者",
        "制作者",
        "担当者",
        "担当",
        "作成",
        "記入者",
        "講師名",
        "講師",
    ],
    "志望校": [
        "目標、志望校",
        "目標・志望校",
        "生徒情報、志望校",
        "現時点での志望校",
        "志望校",
        "受験校",
        "第一志望",
        "第1志望",
    ],
    "教材": [
        "設定教材について",
        "教材",
        "使用教材",
        "メイン教材",
        "補助教材",
        "教材名",
        "テキスト",
    ],
    "小テスト": [
        "小テスト・単語テスト",
        "小テスト・確認テスト",
        "単語テスト・小テスト",
        "小テストスケジュール",
        "授業確認テスト",
        "小テスト内容",
        "小テスト",
        "単語テスト",
        "確認テスト",
        "テスト",
    ],
    "宿題": [
        "宿題スケジュール",
        "宿題",
        "課題",
        "家庭学習",
    ],
    "進め方": [
        "授業スケジュール",
        "授業ごとの指示",
        "授業の流れ",
        "内容、進め方",
        "内容・進め方",
        "授業の進め方",
        "進め方",
        "進み方",
        "授業",
        "指導方針",
        "授業方針",
        "計画",
        "カリキュラム",
    ],
    "生徒情報": [
        "生徒情報、特記事項",
        "生徒情報・特記事項",
        "生徒情報／特記事項",
        "生徒情報(特記事項)",
        "生徒情報（特記事項）",
        "生徒の特徴",
        "授業の注意点",
        "生徒情報",
        "生徒備考",
        "特記事項",
        "生徒状況",
    ],
}

# BLACKLIST
BLACKLIST = [
    "未定", "なし", "特になし", "特にありません", "特に問題ありません", 
    "問題なし", "問題ありません", "問題ありません。", 
    "前回と同じ", "前回と同じです", "不要", "N/A", "NULL", "おまかせ", "良好",
    "-", "ー", "―", "−", "－", "_"
]

# SUMMARY_ROW_LABELS
SUMMARY_ROW_LABELS = ["合計", "総計", "計", "小計", "平均", "件数"]

# HONORIFICS
HONORIFICS = ["先生", "講師", "さん", "氏", "様"]

# SCHOOL_TYPES
SCHOOL_TYPES = ["私立", "公立", "国立", "都立", "府立", "県立", "市立", "専願", "併願"]

# TEXTBOOK_STATUS_KEYWORDS (§6)
# 所持系, 購入系, 未所持系, コピー系
TEXTBOOK_STATUS_KEYWORDS = [
    # 所持系
    "所持(済)", "所持（済）", "所持済", "所持", "手持ち", "本人所持", "持込教材", "持込", "持ち込み",
    # 購入系
    "購入予定", "購入",
    # 未所持系
    "未所持です", "未所持", "未購入",
    # コピー系
    "コピー教材", "コピー", "複写",
]

# 教材の未確定ステータス表現 (これらが含まれる場合はステータス未確定としてERROR) (§6.2)
TEXTBOOK_STATUS_UNCERTAIN = ["所持?", "所持？", "所持か不明", "所持か要確認", "？", "?"]

# CSV_HEADERS
CSV_HEADERS = [
    "学籍番号",
    "受講区分",
    "科目",
    "判定ランク",
    "要修正エラー",
    "確認推奨警告",
    "作成者",
    "志望校",
    "教材",
    "進め方",
    "生徒情報",
    "小テスト",
    "宿題",
    "未分類テキスト",
    "原文指示書",
]

# FORMULA_INJECTION_CHARS
FORMULA_INJECTION_CHARS = ["=", "+", "-", "@"]

# NEXT_PAGE_KEYWORDS
NEXT_PAGE_KEYWORDS = ["次へ", "次", "Next", "NEXT", "次ページ", "＞", ">", "▶"]
