"""
システム全体で使用する定数定義 (Version 2.0.0)
"""

from pathlib import Path

# アプリケーション情報
APP_BASE_TITLE = "個別指導塾 カリキュラムチェックシステム"
APP_NAME = "Curriculum_Analyzer"

# ★★★ プロジェクト全体のバージョン定義（今後変更するのはこの1行のみ） ★★★
APP_VERSION = "2.0.0"

# バージョン連動定数（APP_VERSION から自動生成）
RULE_VERSION = APP_VERSION
EXE_NAME = f"{APP_NAME}_v{APP_VERSION}.exe"
ZIP_NAME = f"{APP_NAME}_v{APP_VERSION}.zip"
MUTEX_NAME = "Local\\CurriculumAnalyzerV2AppSingleInstanceMutex"

# デフォルトファイル出力先 (ユーザーのダウンロードフォルダ)
DEFAULT_OUTPUT_DIR = str(Path.home() / "Downloads")

# Excel シート名
SHEET_PROGRESS = "進捗率"
SHEET_UNIT_DETAILS = "単元詳細"
SHEET_INSTRUCTION = "備考欄"
SHEET_SUMMARY = "サマリー"
SHEET_RAW = "原文"

EXCEL_SHEETS = [
    SHEET_PROGRESS,
    SHEET_UNIT_DETAILS,
    SHEET_INSTRUCTION,
    SHEET_SUMMARY,
    SHEET_RAW,
]

# [進捗率] シート列定義 (仕様書§18: 全27列)
COLUMNS_PROGRESS = [
    "教室",
    "学籍番号",
    "学年",
    "氏名",
    "受講区分",
    "科目",
    "ターゲット",
    "ターゲット名",
    "開始日",
    "終了日",
    "実施期間",
    "実施中",
    "使用教材",
    "目標点",
    "現状の点数",
    "対象単元数",
    "実施済み数",
    "実施済み％",
    "期間内実施数",
    "期間内実施％",
    "期間前実施数",
    "期間前実施％",
    "期間後実施数",
    "期間後実施％",
    "未実施数",
    "未実施％",
    "最終実施日",
]

# [単元詳細] シート列定義 (仕様書§20: 全23列)
COLUMNS_UNIT_DETAILS = [
    "教室",
    "学籍番号",
    "学年",
    "氏名",
    "受講区分",
    "科目",
    "ターゲット",
    "ターゲット名",
    "開始日",
    "終了日",
    "単元",
    "中単元",
    "教材",
    "問題コード",
    "実施日",
    "実施タイミング",
    "実施済み",
    "得点",
    "配点",
    "得点率",
    "本日の教材",
    "実施区分",
    "確認テスト",
]

# [備考欄] シート列定義 (仕様書§21: 全18列)
COLUMNS_INSTRUCTION = [
    "教室",
    "学籍番号",
    "学年",
    "氏名",
    "受講区分",
    "科目",
    "判定",
    "修正項目",
    "エラー",
    "警告",
    "作成者",
    "志望校",
    "教材",
    "進め方",
    "生徒情報",
    "小テスト",
    "宿題",
    "未分類テキスト",
]

# [サマリー] シート列定義 (仕様書§24)
COLUMNS_SUMMARY = [
    "集計区分",
    "名称",
    "生徒数",
    "ターゲット数",
    "対象単元数",
    "実施済み数",
    "未実施数",
    "期間内実施数",
    "期間前実施数",
    "期間後実施数",
    "備考欄エラー数",
    "備考欄警告数",
]

# [原文] シート列定義 (仕様書§25)
COLUMNS_RAW = [
    "URL",
    "取得日時",
    "ページ種別",
    "HTML",
    "取得状態",
    "エラー情報",
]

# 欠損値表記 (仕様書§41)
DEFAULT_EMPTY_VALUE = "-"

# 判定ランク
RANK_CRITICAL = "CRITICAL"
RANK_ERROR = "ERROR"
RANK_REVIEW = "REVIEW"
RANK_WARNING = "WARNING"
RANK_INFO = "INFO"
RANK_PASS = "PASS"

# Rule IDs (CRITICAL)
CRIT_INSTRUCTION_EMPTY = "CRIT_INSTRUCTION_EMPTY"

# Rule IDs (ERROR)
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

# Rule IDs (REVIEW)
REV_SCHOOL_UNCERTAIN = "REV_SCHOOL_UNCERTAIN"

# Rule IDs (WARNING)
WARN_TEXTBOOK_NO_STATUS = "WARN_TEXTBOOK_NO_STATUS"
WARN_SCHOOL_NO_TYPE = "WARN_SCHOOL_NO_TYPE"
WARN_TEST_CRITERIA_MISSING = "WARN_TEST_CRITERIA_MISSING"
WARN_GOAL_MISSING = "WARN_GOAL_MISSING"
WARN_COPY_PASTE_SUSPECTED = "WARN_COPY_PASTE_SUSPECTED"
WARN_UNCLASSIFIED_TEXT = "WARN_UNCLASSIFIED_TEXT"

# Rule IDs (INFO)
INFO_UNCLASSIFIED_TEXT = "INFO_UNCLASSIFIED_TEXT"

# ルールメッセージ
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

# 修正提案
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
    WARN_TEST_CRITERIA_MISSING: "小テストの実施範囲や合格基準を記載してください",
    WARN_TEXTBOOK_NO_STATUS: "教材の所持状態を明記してください",
    WARN_COPY_PASTE_SUSPECTED: "生徒ごとに個別の学習状況を記載してください",
    WARN_UNCLASSIFIED_TEXT: "未分類行の書式を見直してください",
    INFO_UNCLASSIFIED_TEXT: "未分類行の書式を見直してください",
}

# 備考欄の標準セクション名
CANONICAL_SECTIONS = [
    "作成者",
    "志望校",
    "教材",
    "進め方",
    "生徒情報",
    "小テスト",
    "宿題",
    "講座数",
    "目標",
]

# セクションのエイリアス定義 (v1完全準拠)
SECTION_ALIASES = {
    "作成者": ["作成者", "担当", "講師", "担当講師", "記入者", "指導者", "作成", "文責", "記載者"],
    "志望校": ["志望校", "第一志望", "第1志望", "志望大学", "志望高校", "志望中学", "受験校", "進路", "目標校", "志望", "専攻"],
    "教材": ["教材", "使用教材", "テキスト", "ワーク", "参考書", "問題集", "テキスト教材", "教科書", "教材名", "教材テキスト"],
    "進め方": ["進め方", "指導方針", "授業計画", "進度", "授業の進め方", "指導計画", "方針", "授業方針", "カリキュラム", "計画", "指導方法", "進め方方針"],
    "生徒情報": ["生徒情報", "備考", "特記事項", "生徒の様子", "生徒状況", "生徒備考", "性格", "特徴", "生徒特徴", "状況", "様子", "生徒", "本人情報"],
    "小テスト": ["小テスト", "テスト", "単語テスト", "確認テスト", "ミニテスト", "プレテスト", "ラップテスト", "チェックテスト"],
    "宿題": ["宿題", "課題", "家庭学習", "次回までの宿題", "宿題課題", "次回までの課題", "自主学習", "家庭課題"],
    "講座数": ["講座数", "授業数", "回数", "コマ数", "受講回数", "予定回数", "総回数", "講座", "コマ"],
    "目標": ["目標", "講習目標", "受講目標", "今期の目標", "達成目標", "到達目標", "ゴール", "授業目標"],
}

# 教材ステータス定義
TEXTBOOK_STATUS_KEYWORDS = {
    "所持": ["所持", "持っている", "持ち", "あり", "所持中", "持参", "持込", "持ち込み"],
    "未所持": ["未所持", "持っていない", "なし", "持ってない", "未持参"],
    "購入": ["購入", "購入予定", "買い", "買う", "購入済", "購入済み", "買美"],
    "コピー": ["コピー", "印刷", "プリント", "抜粋"],
}

TEXTBOOK_STATUS_UNCERTAIN = ["所持?", "未定", "確認中", "不明", "要確認", "相談", "所持？"]

# 学校種別
SCHOOL_TYPES = ["公立", "私立", "国立", "都立", "府立", "県立", "市立", "道立"]

# ブラックリスト (未記載と同等とみなす表現)
BLACKLIST = [
    "-", "--", "---", "/", "／", "なし", "特になし", "特段なし", "未定", "未記入", "未記載", "空欄", "特記なし",
    "・", "...", "…", "ー", "―", "−", "None", "null", "該当なし", "無し"
]

# コピペ検出閾値
MIN_PLAN_LENGTH = 5
MIN_INFO_LENGTH = 3
DUPLICATE_INFO_THRESHOLD = 3
JACCARD_SIMILARITY_THRESHOLD = 0.8
