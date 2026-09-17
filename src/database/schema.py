"""
SQLiteデータベーススキーマ定義 (仕様書§5, §7)
"""

CREATE_TABLES_SQL = """
-- ページ取得・キャッシュ状態
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY,
    curriculum_key TEXT,
    row_index INTEGER DEFAULT 0,
    classroom_name TEXT,
    classroom_code TEXT,
    school_year TEXT,
    student_id TEXT,
    student_name TEXT,
    grade TEXT,
    division TEXT,
    subject TEXT,
    school_course TEXT,
    status TEXT NOT NULL,
    html TEXT,
    fetch_time TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ターゲット定義
CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url TEXT,
    student_id TEXT,
    target_no TEXT,
    target_name TEXT,
    start_date TEXT,
    end_date TEXT,
    period_str TEXT,
    is_current INTEGER,
    target_score TEXT,
    current_score TEXT,
    site_progress_rate TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 単元実施記録
CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url TEXT,
    student_id TEXT,
    unit_no TEXT,
    unit_name TEXT,
    middle_unit TEXT,
    textbook TEXT,
    problem_code TEXT,
    score TEXT,
    max_score TEXT,
    score_rate TEXT,
    execution_date TEXT,
    timing TEXT,
    is_executed INTEGER,
    today_textbook TEXT,
    execution_division TEXT,
    confirm_test TEXT,
    target_checks_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 進捗率集計結果
CREATE TABLE IF NOT EXISTS progress_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url TEXT,
    classroom TEXT,
    student_id TEXT,
    grade TEXT,
    student_name TEXT,
    division TEXT,
    subject TEXT,
    target_no TEXT,
    target_name TEXT,
    start_date TEXT,
    end_date TEXT,
    period_str TEXT,
    is_current INTEGER,
    textbooks_used TEXT,
    target_score TEXT,
    current_score TEXT,
    target_unit_count INTEGER,
    executed_count INTEGER,
    executed_rate TEXT,
    on_time_count INTEGER,
    on_time_rate TEXT,
    before_count INTEGER,
    before_rate TEXT,
    after_count INTEGER,
    after_rate TEXT,
    unexecuted_count INTEGER,
    unexecuted_rate TEXT,
    latest_execution_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 備考欄評価結果
CREATE TABLE IF NOT EXISTS instruction_evaluations (
    page_url TEXT PRIMARY KEY,
    student_id TEXT,
    severity TEXT,
    fix_items_json TEXT,
    errors_json TEXT,
    warnings_json TEXT,
    reviews_json TEXT,
    author TEXT,
    target_school TEXT,
    textbook TEXT,
    plan TEXT,
    student_info TEXT,
    test TEXT,
    homework TEXT,
    unclassified_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status);
CREATE INDEX IF NOT EXISTS idx_pages_student ON pages(student_id);
CREATE INDEX IF NOT EXISTS idx_targets_page ON targets(page_url);
CREATE INDEX IF NOT EXISTS idx_units_page ON units(page_url);
CREATE INDEX IF NOT EXISTS idx_progress_page ON progress_summary(page_url);
"""
