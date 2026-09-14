"""
実サンプルHTML (sampleMSL.html) に基づく回帰テスト。
仕様書および改善指示書で指摘された不具合の再発防止と改善の検証を行う。
"""

import os
import sys
from pathlib import Path

# src を sys.path に追加
base_dir = Path(__file__).resolve().parent.parent
src_dir = base_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from core.models import AppConfig, CurriculumRecord, Severity
from core.constants import (
    WARN_TEXTBOOK_NO_STATUS,
    WARN_UNCLASSIFIED_TEXT,
    CSV_HEADERS,
)
from core.normalization import (
    clean_instruction,
    normalize_student_id,
    normalize_division,
    normalize_subject,
    extract_student_id_from_cell,
    sanitize_raw_instruction,
)
from core.parser import parse_sections
from core.evaluator import evaluate_single_record, evaluate_batch_duplicates
from core.exporter import CsvExporter


# ---------------------------------------------------------------------------
# 実サンプルから抽出された指示書テキスト (Fixture)
# ---------------------------------------------------------------------------

SAMPLE_INSTRUCTION_1 = """作成者：講師１

講座・授業数：1講座 (4回)

目標：2年生に向けて基礎を身につける

教材：
・Lodestar 数Ⅰ vol1,vol2（未所持）

小テスト：
・Lapテスト（出来るだけやってください）

宿題：
・Lodestar（各単元の演習用ページの問題）

授業ごとの指示：
・1回目：1〜2回目で関数のグラフの内容を行います。進めるだけ進んでもらって構いません。
・2回目：1〜2回目で関数のグラフの内容を行います。進めるだけ進んでもらって構いません。
・3回目：3〜4回目で三角比の内容を行います。進めるだけ進んでもらって構いません。
・4回目：3〜4回目で三角比の内容を行います。進めるだけ進んでもらって構いません。

進め方：
・左上を説明→右上を演習→丸付け→解説→左下を説明→右下を演習→丸付け→解説で進んでいきます。

生徒情報：
・素直な性格ですが、適当な部分と見落としが多いので、応答だけでなく回答している様子などをしっかりと確認してあげてください。
・部活が毎日(週7)あるので、遅刻してきますが許してあげてください。
・集中が切れやすいので、定期的に話しかけるなどしてあげてください。"""

SAMPLE_INSTRUCTION_3 = """BUILDERやります
一から進めていきます。
数学はもちろん勉強というものが嫌いな人です。"""

SAMPLE_INSTRUCTION_4 = """担当:講師２

講座数（授業数）：1講座（5回）

目標:数学の基礎を固める

教材:ウイニングサマー（所持）

進め方:プレテストははじめに行ってください。ページごとに解説をしてください。理解力があるので説明すればある程度できると思います。手が止まっていたら声をかけてあげてください。

小テスト:プレテスト

宿題:ウィンパス該当範囲、残りの問題"""

SAMPLE_INSTRUCTION_5 = """作成者:講師２

講座数: 1

教材：ウイニングサマー(所持)

進め方： 本日の単元の説明 → この夏覚える単語 → 練習問題
⚠️単語力がないので、この夏覚える単語は必ずやってください

小テスト：ラップテスト

宿題：授業の残り、本日の単元のプレテストとホームワーク

生徒情報: 英語は本当に苦手だと思います！丁寧に説明お願いします！"""

SAMPLE_INSTRUCTION_6 = """作成者：講師４

講座・授業数：1講座 (5回)

目標：一学期範囲の定着を目指す

教材：
・ウイニングサマー（所持）

小テスト・単語テスト：
・Lapテスト

宿題：
・授業の残り

進め方：
・宿題確認→1授業につき1単元を進める→ラップテスト→次回の宿題指定

生徒情報：
・比較的大人しいですが、説明したらきちんと吸収してくれます。丁寧に教えてあげてください。"""

SAMPLE_INSTRUCTION_7 = """作成者：講師５
講座:授業数:1講座5回）
目標:基礎をしっかり固める
教材:ウイニングサマー英語 中2
小テスト:lapテスト授業範囲）
宿題:授業の残り.ホームワーク
進め方:初めに単語を軽く確認
 例題を解いて練習問題Aを取り組む苦手な子なので時間があればBまで、ゆっくりAを進めてあげてください"""


# ---------------------------------------------------------------------------
# 単体・回帰テスト
# ---------------------------------------------------------------------------

def test_record_1_author_and_unknown_heading_separation():
    """要件1 & 要件2: 作成者欄に『講座・授業数』や『目標』が混入せず、unclassified_text に送られること"""
    cleaned = clean_instruction(SAMPLE_INSTRUCTION_1)
    sections, uc_count, uc_text = parse_sections(cleaned)

    # 作成者が「講師1」のみであること
    assert sections["作成者"] == "講師1"

    # 未知見出しが unclassified_text に正しく分離されていること
    assert "講座・授業数:1講座 (4回)" in uc_text
    assert "目標:2年生に向けて基礎を身につける" in uc_text
    assert "関数のグラフ" in sections["進め方"]
    assert uc_count > 0


def test_record_4_alias_tantou_and_separation():
    """要件2: 『担当:講師２』が作成者として認識され、後続の未知見出しが分離されること"""
    cleaned = clean_instruction(SAMPLE_INSTRUCTION_4)
    sections, uc_count, uc_text = parse_sections(cleaned)

    assert sections["作成者"] == "講師2"
    assert "講座数(授業数):1講座(5回)" in uc_text
    assert "目標:数学の基礎を固める" in uc_text
    assert sections["教材"] == "ウイニングサマー(所持)"


def test_record_6_subtest_alias_and_textbook_status():
    """要件3 & 要件4: 『小テスト・単語テスト：』が小テストに分離され、教材の(所持)が正しく判定されること"""
    cleaned = clean_instruction(SAMPLE_INSTRUCTION_6)
    sections, uc_count, uc_text = parse_sections(cleaned)

    # 作成者
    assert sections["作成者"] == "講師4"
    # 小テスト
    assert "Lapテスト" in sections["小テスト"]
    # 教材
    assert "ウイニングサマー(所持)" in sections["教材"]

    # 評価実行
    config = AppConfig(base_url="https://example.com")
    rec = CurriculumRecord(
        student_id="00000006",
        division="夏期講習",
        subject="中学数学",
        raw_instruction=SAMPLE_INSTRUCTION_6,
    )
    result = evaluate_single_record(rec, config)

    # 教材ステータス警告が出ないこと
    # 未分類テキスト警告が出ないこと（v7 §3: 未分類テキストのみが残る場合は INFO 判定）
    assert WARN_UNCLASSIFIED_TEXT not in result.warnings
    assert result.severity == Severity.INFO


from core.constants import (
    ERR_AUTHOR_MISSING,
    ERR_COURSE_COUNT_MISSING,
    ERR_HOMEWORK_MISSING,
    ERR_INFO_MISSING,
    ERR_PLAN_MISSING,
    ERR_SCHOOL_REQUIRED_ELEM6,
    ERR_SCHOOL_REQUIRED_HIGH3,
    ERR_SCHOOL_REQUIRED_JUNIOR3,
    ERR_TEST_MISSING,
    ERR_TEXTBOOK_MISSING,
    ERR_TEXTBOOK_STATUS_MISSING,
    WARN_GOAL_MISSING,
    WARN_SCHOOL_NO_TYPE,
    WARN_TEXTBOOK_NO_STATUS,
    WARN_UNCLASSIFIED_TEXT,
    CSV_HEADERS,
)
from core.excel_exporter import ExcelExporter


def test_textbook_status_detection():
    """v3: 教材ステータスの各種表記（所持、所持済、所持（済）、持込、コピー、未所持等）が有効判定され、
    未記載または未確定（所持?）の場合は ERR_TEXTBOOK_STATUS_MISSING (ERROR) となること"""
    config = AppConfig(base_url="https://example.com")

    # 有効ステータスありのケース: ウイニングサマー(所持)
    rec_ok = CurriculumRecord(
        student_id="00000005",
        division="夏期講習",
        subject="中学英語",
        raw_instruction=SAMPLE_INSTRUCTION_5,
    )
    res_ok = evaluate_single_record(rec_ok, config)
    assert ERR_TEXTBOOK_STATUS_MISSING not in res_ok.errors

    # 持込・コピー教材が有効判定されるケース
    inst_mochikomi = """作成者：講師1
教材：新演習（持込）、英単語ターゲット（コピー教材）
進め方：テキストを中心に演習を繰り返します。
生徒情報：真面目に学習に取り組めます。
小テスト：ターゲット単語テスト
宿題：新演習 p.20-25"""
    rec_mochikomi = CurriculumRecord(
        student_id="00000008",
        division="通常授業",
        subject="高校英語",
        raw_instruction=inst_mochikomi,
    )
    res_mochikomi = evaluate_single_record(rec_mochikomi, config)
    assert ERR_TEXTBOOK_STATUS_MISSING not in res_mochikomi.errors

    # 有効ステータスなしのケース: ウイニングサマー英語 中2 (ステータス記載なし) -> ERROR
    rec_no_status = CurriculumRecord(
        student_id="00000007",
        division="夏期講習",
        subject="中学英語",
        raw_instruction=SAMPLE_INSTRUCTION_7,
    )
    res_no_status = evaluate_single_record(rec_no_status, config)
    assert ERR_TEXTBOOK_STATUS_MISSING in res_no_status.errors
    assert res_no_status.severity == Severity.ERROR

    # 未確定表現のケース: 「所持?」 -> ERROR
    inst_uncertain = """作成者：講師1
教材：チャート式青（所持?）
進め方：例題を順番に解いていきます。
生徒情報：計算力があります。
小テスト：計算小テスト
宿題：練習問題1-10"""
    rec_uncertain = CurriculumRecord(
        student_id="00000009",
        division="通常授業",
        subject="高校数学",
        raw_instruction=inst_uncertain,
    )
    res_uncertain = evaluate_single_record(rec_uncertain, config)
    assert ERR_TEXTBOOK_STATUS_MISSING in res_uncertain.errors


def test_conditional_school_requirement():
    """v3: 志望校の条件付き必須判定
    - 高3: 志望校なしで ERR_SCHOOL_REQUIRED_HIGH3 (ERROR)
    - 公立中3: 志望校なしで ERR_SCHOOL_REQUIRED_JUNIOR3 (ERROR)
    - 小6中受: 志望校なしで ERR_SCHOOL_REQUIRED_ELEM6 (ERROR)
    - 高1・中1等: 志望校なしでも任意のため PASS
    - 記載時は学校区分（私立/公立/都立等）がないと WARN_SCHOOL_NO_TYPE
    """
    config = AppConfig(base_url="https://example.com")
    base_inst = """作成者：講師1
教材：新演習（所持）
進め方：テキストを中心に演習を繰り返します。
生徒情報：真面目に学習に取り組みます。
小テスト：確認テスト
宿題：p.10-15"""

    # 1. 高3（学年に高3指定）で志望校なし -> エラー
    rec_h3 = CurriculumRecord(
        student_id="00000010",
        division="通常授業",
        subject="英語",
        raw_instruction=base_inst,
        meta_cells={"学年": "高3", "学校/コース": "都立日比谷高校"},
    )
    res_h3 = evaluate_single_record(rec_h3, config)
    assert ERR_SCHOOL_REQUIRED_HIGH3 in res_h3.errors
    assert res_h3.severity == Severity.ERROR

    # 2. 公立中3（学年が中3、公立中学校）で志望校なし -> エラー
    rec_j3 = CurriculumRecord(
        student_id="00000011",
        division="通常授業",
        subject="数学",
        raw_instruction=base_inst,
        meta_cells={"学年": "中3", "学校/コース": "練馬区立開進第一中学校"},
    )
    res_j3 = evaluate_single_record(rec_j3, config)
    assert ERR_SCHOOL_REQUIRED_JUNIOR3 in res_j3.errors

    # 3. 小6中受（学年が小6、科目に中受含む）で志望校なし -> エラー
    rec_e6 = CurriculumRecord(
        student_id="00000012",
        division="通常授業",
        subject="小6中受算数",
        raw_instruction=base_inst,
        meta_cells={"学年": "小6"},
    )
    res_e6 = evaluate_single_record(rec_e6, config)
    assert ERR_SCHOOL_REQUIRED_ELEM6 in res_e6.errors

    # 4. 高1（任意対象）で志望校なし -> 志望校エラーなし
    rec_h1 = CurriculumRecord(
        student_id="00000013",
        division="通常授業",
        subject="英語",
        raw_instruction=base_inst,
        meta_cells={"学年": "高1", "学校/コース": "都立日比谷高校"},
    )
    res_h1 = evaluate_single_record(rec_h1, config)
    assert ERR_SCHOOL_REQUIRED_HIGH3 not in res_h1.errors
    assert ERR_SCHOOL_REQUIRED_JUNIOR3 not in res_h1.errors
    assert ERR_SCHOOL_REQUIRED_ELEM6 not in res_h1.errors
    assert res_h1.severity == Severity.PASS

    # 5. 志望校記載あり（学校区分キーワードなしでもPASS: v6 §19.1）
    inst_no_type = base_inst + "\n志望校：早稲田大学"
    rec_type_warn = CurriculumRecord(
        student_id="00000014",
        division="通常授業",
        subject="英語",
        raw_instruction=inst_no_type,
        meta_cells={"学年": "高3"},
    )
    res_type_warn = evaluate_single_record(rec_type_warn, config)
    assert ERR_SCHOOL_REQUIRED_HIGH3 not in res_type_warn.errors
    assert WARN_SCHOOL_NO_TYPE not in res_type_warn.warnings
    assert res_type_warn.severity == Severity.PASS

    # 6. 志望校記載ありで学校区分キーワード（私立）あり -> 正常
    inst_with_type = base_inst + "\n志望校：私立早稲田大学"
    rec_ok_school = CurriculumRecord(
        student_id="00000015",
        division="通常授業",
        subject="英語",
        raw_instruction=inst_with_type,
        meta_cells={"学年": "高3"},
    )
    res_ok_school = evaluate_single_record(rec_ok_school, config)
    assert ERR_SCHOOL_REQUIRED_HIGH3 not in res_ok_school.errors
    assert WARN_SCHOOL_NO_TYPE not in res_ok_school.warnings
    assert res_ok_school.severity == Severity.PASS


def test_lecture_requirements():
    """v3: 講習授業の場合、講座数・授業数が必須(ERROR)、目標が推奨(WARNING)となること"""
    config = AppConfig(base_url="https://example.com")
    base_inst = """作成者：講師1
教材：新演習（所持）
進め方：テキストを中心に演習を繰り返します。
生徒情報：真面目に学習に取り組みます。
小テスト：確認テスト
宿題：p.10-15"""

    # 講習区分で講座数・目標の記載がない -> ERR_COURSE_COUNT_MISSING & WARN_GOAL_MISSING
    rec_lecture_missing = CurriculumRecord(
        student_id="00000016",
        division="夏期講習",
        subject="英語",
        raw_instruction=base_inst,
    )
    res_lecture_missing = evaluate_single_record(rec_lecture_missing, config)
    assert ERR_COURSE_COUNT_MISSING in res_lecture_missing.errors
    assert WARN_GOAL_MISSING in res_lecture_missing.warnings

    # 講習区分で講座数・目標が記載されている -> PASS
    inst_lecture_ok = base_inst + "\n講座数：1講座 (5回)\n目標：一学期の復習と基礎定着"
    rec_lecture_ok = CurriculumRecord(
        student_id="00000017",
        division="夏期講習",
        subject="英語",
        raw_instruction=inst_lecture_ok,
    )
    res_lecture_ok = evaluate_single_record(rec_lecture_ok, config)
    assert ERR_COURSE_COUNT_MISSING not in res_lecture_ok.errors
    assert WARN_GOAL_MISSING not in res_lecture_ok.warnings


def test_evaluation_issues_and_traces():
    """v3: EvaluationIssue と parse_traces が詳細に格納されること"""
    config = AppConfig(base_url="https://example.com")
    rec = CurriculumRecord(
        student_id="00000018",
        division="夏期講習",
        subject="数学",
        raw_instruction=SAMPLE_INSTRUCTION_6,
    )
    res = evaluate_single_record(rec, config)

    # parse_traces に行単位のパーストレースが記録されていること
    assert len(res.parse_traces) > 0
    first_trace = res.parse_traces[0]
    assert "line" in first_trace
    assert "heading" in first_trace
    assert "section" in first_trace

    # issues リストに EvaluationIssue が格納されていること
    for issue in res.issues:
        assert issue.rule_id
        assert issue.field
        assert issue.message
        assert issue.severity in (Severity.ERROR, Severity.WARNING, Severity.INFO, Severity.REVIEW, Severity.CRITICAL)


def test_free_text_instruction():
    """見出しなし自由記述（Record 3）がすべて unclassified_text に入ること"""
    cleaned = clean_instruction(SAMPLE_INSTRUCTION_3)
    sections, uc_count, uc_text = parse_sections(cleaned)

    # 全セクションが空
    for k, v in sections.items():
        assert v == ""
    assert uc_count == 3
    assert "BUILDERやります" in uc_text


def test_csv_export_format_and_clean_columns(tmp_path):
    """要件8: CSV出力時に作成者欄に余計な見出しが混入せず、15列が正確に出力されること"""
    config = AppConfig(base_url="https://example.com")
    rec1 = CurriculumRecord(
        student_id="00000001",
        division="春期講習",
        subject="数学IA",
        raw_instruction=SAMPLE_INSTRUCTION_1,
    )
    rec6 = CurriculumRecord(
        student_id="00000006",
        division="夏期講習",
        subject="中学数学",
        raw_instruction=SAMPLE_INSTRUCTION_6,
    )

    res1 = evaluate_single_record(rec1, config)
    res6 = evaluate_single_record(rec6, config)

    records = [rec1, rec6]
    results = [res1, res6]

    exporter = CsvExporter()
    out_file = exporter.export(str(tmp_path), records, results)
    assert os.path.exists(out_file)

    # CSVの検証
    import csv
    with open(out_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    assert len(rows) == 3  # ヘッダー + 2行
    assert rows[0] == CSV_HEADERS

    author_col_idx = CSV_HEADERS.index("作成者")
    assert rows[1][author_col_idx] == "講師1"
    subtest_col_idx = CSV_HEADERS.index("小テスト")
    assert "Lapテスト" in rows[1][subtest_col_idx]
    uc_col_idx = CSV_HEADERS.index("未分類テキスト")
    assert "講座・授業数" in rows[1][uc_col_idx]

    assert rows[2][author_col_idx] == "講師4"
    assert "Lapテスト" in rows[2][subtest_col_idx]


def test_excel_export_multi_sheets(tmp_path):
    """v4: ExcelExporter により要修正・警告を除外した7つのシートを備えたブックが正常に出力されること (§20)"""
    import openpyxl
    config = AppConfig(base_url="https://example.com")
    rec1 = CurriculumRecord(
        student_id="00000001",
        division="春期講習",
        subject="数学IA",
        raw_instruction=SAMPLE_INSTRUCTION_1,
    )
    rec6 = CurriculumRecord(
        student_id="00000006",
        division="夏期講習",
        subject="中学数学",
        raw_instruction=SAMPLE_INSTRUCTION_6,
    )

    res1 = evaluate_single_record(rec1, config)
    res6 = evaluate_single_record(rec6, config)

    records = [rec1, rec6]
    results = [res1, res6]

    exporter = ExcelExporter()
    out_file = exporter.export(str(tmp_path), records, results, timestamp="20260914_010000")

    assert os.path.exists(out_file)
    assert out_file.endswith(".xlsx")

    wb = openpyxl.load_workbook(out_file)
    expected_sheets = ["チェック結果", "判定一覧", "解析詳細", "原文", "サマリー", "未知表記", "教材詳細"]
    assert wb.sheetnames == expected_sheets
    assert "要修正" not in wb.sheetnames
    assert "警告" not in wb.sheetnames

    # チェック結果シートの検証 (v10 §6.1: 20列、最重要エラー列削除、修正項目列の存在、教室名・教室コード・年度・生徒名・学年)
    ws_main = wb["チェック結果"]
    headers = [ws_main.cell(row=1, column=c).value for c in range(1, 21)]
    assert "判定" in headers
    assert "最重要エラー" not in headers
    assert "修正項目" in headers
    assert "教室名" in headers
    assert "教室コード" in headers
    assert "年度" in headers
    assert "生徒名" in headers
    assert "学年" in headers
    assert ws_main.freeze_panes == "A2"
    assert ws_main.auto_filter.ref is not None

    # 未知表記シートの検証 (§31)
    ws_unknown = wb["未知表記"]
    assert ws_unknown.cell(row=1, column=1).value == "元表記"
    assert ws_unknown.cell(row=1, column=3).value == "推定分類"

    # 教材詳細シートの検証 (v10 §6.4: 13列 [学籍番号, 生徒名, 学年, 受講区分, 科目, 教室名, 教室コード, 年度, 教材, ステータス, ステータス分類, 判定, 補足])
    ws_tb = wb["教材詳細"]
    assert ws_tb.cell(row=1, column=6).value == "教室名"
    assert ws_tb.cell(row=1, column=7).value == "教室コード"
    assert ws_tb.cell(row=1, column=8).value == "年度"
    assert ws_tb.cell(row=1, column=9).value == "教材"
    assert ws_tb.cell(row=1, column=12).value == "判定"
    assert ws_tb.cell(row=1, column=13).value == "補足"

    # サマリーシートの検証 (§30)
    ws_sum = wb["サマリー"]
    assert "Curriculum Analyzer 精査集計サマリー" in str(ws_sum.cell(row=2, column=2).value)


def test_critical_empty_instruction():
    """v4 §2: 備考欄そのものが完全に空欄の場合、CRITICAL判定となること (v7 §7, §35: 用語は備考欄)"""
    from core.constants import CRIT_INSTRUCTION_EMPTY
    config = AppConfig(base_url="https://example.com")

    # 完全空文字
    rec_empty = CurriculumRecord(student_id="10000001", division="通常授業", subject="英語", raw_instruction="")
    res_empty = evaluate_single_record(rec_empty, config)
    assert res_empty.severity == Severity.CRITICAL
    assert CRIT_INSTRUCTION_EMPTY in res_empty.errors
    assert res_empty.primary_error == CRIT_INSTRUCTION_EMPTY
    assert res_empty.fix_fields == ["備考欄"]

    # 空白・改行・全角スペースのみ
    rec_spaces = CurriculumRecord(student_id="10000002", division="通常授業", subject="数学", raw_instruction="  \n\t  \u3000\u3000\n")
    res_spaces = evaluate_single_record(rec_spaces, config)
    assert res_spaces.severity == Severity.CRITICAL
    assert CRIT_INSTRUCTION_EMPTY in res_spaces.errors


def test_itemized_textbooks_evaluation():
    """v4 §9, §10, §26: 教材を教材単位で構造化し、部分OKやステータス区分を判定すること"""
    config = AppConfig(base_url="https://example.com")
    inst = """作成者：講師1
教材：ロードスター（所持）、ウィンパス、青チャート（所持?）、新演習（コピー）
進め方：各テキストを並行して演習します。
生徒情報：意欲的に学習できます。
小テスト：英単語テスト
宿題：ロードスター p.10-15"""
    rec = CurriculumRecord(student_id="10000003", division="通常授業", subject="数学", raw_instruction=inst)
    res = evaluate_single_record(rec, config)

    assert len(res.textbook_items) == 4
    items_by_name = {item.name: item for item in res.textbook_items}

    # ロードスター (所持) -> OK
    assert items_by_name["ロードスター"].is_valid is True
    assert items_by_name["ロードスター"].category == "所持"

    # ウィンパス (ステータス未記載) -> ERROR
    assert items_by_name["ウィンパス"].is_valid is False
    assert items_by_name["ウィンパス"].category == "不明"

    # 青チャート (所持?) -> ERROR
    assert items_by_name["青チャート"].is_valid is False
    assert items_by_name["青チャート"].category == "未確定"

    # 新演習 (コピー) -> OK
    assert items_by_name["新演習"].is_valid is True
    assert items_by_name["新演習"].category == "コピー"

    # 全体としてはステータス不足 (PARTIAL)
    from core.models import SectionStatus
    assert res.section_statuses["教材"] == SectionStatus.PARTIAL
    assert ERR_TEXTBOOK_STATUS_MISSING in res.errors


def test_auxiliary_school_extraction_from_student_info():
    """v4 §11: 生徒情報内の明確な志望校記載から補助抽出を行い、高3の志望校必須エラーを回避できること"""
    config = AppConfig(base_url="https://example.com")
    inst = """作成者：講師1
教材：数学エクスプレス（所持）
進め方：過去問を中心に解説を進めます。
生徒情報：現時点での志望校は、大阪公立大学工学部です。真面目に取り組んでいます。
小テスト：計算テスト
宿題：過去問2023年分"""
    rec = CurriculumRecord(
        student_id="10000004",
        division="通常授業",
        subject="高校数学",
        raw_instruction=inst,
        meta_cells={"学年": "高3"},
    )
    res = evaluate_single_record(rec, config)

    # 生徒情報から補助抽出され、志望校必須エラーが回避されていること
    assert ERR_SCHOOL_REQUIRED_HIGH3 not in res.errors
    assert "大阪公立大学" in res.parsed_sections["志望校"]


def test_primary_error_and_fix_fields():
    """v4 §3, §4: 最重要エラーと修正項目が優先度順に特定されること"""
    config = AppConfig(base_url="https://example.com")
    # 作成者なし、教材なし
    inst = """進め方：テキストを中心に演習を繰り返します。
生徒情報：真面目に学習に取り組めます。
小テスト：単語テスト
宿題：p.10-15"""
    rec = CurriculumRecord(student_id="10000005", division="通常授業", subject="英語", raw_instruction=inst)
    res = evaluate_single_record(rec, config)

    assert ERR_AUTHOR_MISSING in res.errors
    assert ERR_TEXTBOOK_MISSING in res.errors
    # 最重要エラーは優先度最上位の作成者未記載
    assert res.primary_error == ERR_AUTHOR_MISSING
    # 修正項目に作成者と教材が含まれること
    assert "作成者" in res.fix_fields
    assert "教材" in res.fix_fields


def test_golden_cases_compound_headings_and_homework_blacklist():
    """v4 §30 Golden Tests:
    - 【使用教材】、【生徒情報、特記事項】の認識
    - 宿題：なし、特になし -> ERR_HOMEWORK_MISSING
    - FREE_TEXTのみでは WARN_UNCLASSIFIED_TEXT を出さない (§7)
    - 未知見出しが存在する場合は WARN_UNCLASSIFIED_TEXT を出す
    """
    config = AppConfig(base_url="https://example.com")

    # 1. 複合ブラケット見出しの認識
    inst_bracket = """【作成者】山本大貴
【使用教材】ウイニングサマー(所持)
【進め方】基礎から標準レベルの演習を行います。
【生徒情報、特記事項】集中力が続きやすいです。
【小テスト】確認小テスト
【宿題】ウィンパス該当単元"""
    rec_bracket = CurriculumRecord(student_id="10000006", division="通常授業", subject="数学", raw_instruction=inst_bracket)
    res_bracket = evaluate_single_record(rec_bracket, config)
    assert res_bracket.parsed_sections["作成者"] == "山本大貴"
    assert "ウイニングサマー(所持)" in res_bracket.parsed_sections["教材"]
    assert "集中力が続きやすいです" in res_bracket.parsed_sections["生徒情報"]
    assert res_bracket.severity == Severity.PASS

    # 2. 宿題：なし、特になし -> ERR_HOMEWORK_MISSING
    inst_hw_none = """作成者：講師1
教材：新演習（所持）
進め方：テキストを中心に演習を繰り返します。
生徒情報：真面目に学習に取り組めます。
小テスト：英単語テスト
宿題：なし"""
    rec_hw_none = CurriculumRecord(student_id="10000007", division="通常授業", subject="英語", raw_instruction=inst_hw_none)
    res_hw_none = evaluate_single_record(rec_hw_none, config)
    assert ERR_HOMEWORK_MISSING in res_hw_none.errors

    inst_hw_tokuni = inst_hw_none.replace("宿題：なし", "宿題：特になし")
    rec_hw_tokuni = CurriculumRecord(student_id="10000008", division="通常授業", subject="英語", raw_instruction=inst_hw_tokuni)
    res_hw_tokuni = evaluate_single_record(rec_hw_tokuni, config)
    assert ERR_HOMEWORK_MISSING in res_hw_tokuni.errors

    # 3. 未分類警告の改善 (§7):
    # 見出しのない自由記述テキストのみの場合、WARN_UNCLASSIFIED_TEXT は出ない
    inst_free = """作成者：講師1
教材：新演習（所持）
進め方：テキストを中心に演習を繰り返します。
生徒情報：真面目に学習に取り組めます。
小テスト：英単語テスト
宿題：p.10-15
自由記述の補足メモです。次回もよろしくお願いします。"""
    rec_free = CurriculumRecord(student_id="10000009", division="通常授業", subject="英語", raw_instruction=inst_free)
    res_free = evaluate_single_record(rec_free, config)
    assert WARN_UNCLASSIFIED_TEXT not in res_free.warnings

    # 未知見出し（【特別指導】等）がある場合、WARN_UNCLASSIFIED_TEXT が出る
    inst_unknown = inst_free + "\n【特別指導】：重点的に弱点を補強します。"
    rec_unknown = CurriculumRecord(student_id="10000010", division="通常授業", subject="英語", raw_instruction=inst_unknown)
    res_unknown = evaluate_single_record(rec_unknown, config)
    assert WARN_UNCLASSIFIED_TEXT in res_unknown.warnings


def test_v5_exclusion_rules():
    """v5 §4: 集計対象除外 (デモ、退塾、見送り) の検証"""
    from core.evaluator import check_record_exclusion, filter_target_records

    # 1. 名字が完全に「デモ」の生徒 -> 除外
    rec_demo1 = CurriculumRecord(student_id="D001", division="通常授業", subject="英語", raw_instruction="...", meta_cells={"生徒": "デモ 太郎"})
    rec_demo2 = CurriculumRecord(student_id="D002", division="通常授業", subject="英語", raw_instruction="...", meta_cells={"生徒": "デモ"})
    rec_demo3 = CurriculumRecord(student_id="D003", division="通常授業", subject="英語", raw_instruction="...", meta_cells={"student_raw": "12345 デモ 太郎"})
    assert check_record_exclusion(rec_demo1) == "DEMO"
    assert check_record_exclusion(rec_demo2) == "DEMO"
    assert check_record_exclusion(rec_demo3) == "DEMO"

    # 2. 名字以外に「デモ」を含む生徒 (例: デモ田, デモ川) -> 除外しない
    rec_demoda = CurriculumRecord(student_id="D004", division="通常授業", subject="英語", raw_instruction="...", meta_cells={"生徒": "デモ田 太郎"})
    rec_demokawa = CurriculumRecord(student_id="D005", division="通常授業", subject="英語", raw_instruction="...", meta_cells={"生徒": "デモ川 次郎"})
    assert check_record_exclusion(rec_demoda) is None
    assert check_record_exclusion(rec_demokawa) is None

    # 3. 在籍ステータスが「退塾」 -> 除外
    rec_withdrawn = CurriculumRecord(student_id="D006", division="通常授業", subject="英語", raw_instruction="...", meta_cells={"生徒": "佐藤 健", "在籍": "退塾"})
    assert check_record_exclusion(rec_withdrawn) == "WITHDRAWN"

    # 4. 在籍ステータスが「見送り」 -> 除外
    rec_declined = CurriculumRecord(student_id="D007", division="通常授業", subject="英語", raw_instruction="...", meta_cells={"生徒": "鈴木 一郎", "状況": "見送り"})
    assert check_record_exclusion(rec_declined) == "DECLINED"

    # 5. 通常生徒 -> 対象
    rec_normal = CurriculumRecord(student_id="D008", division="通常授業", subject="英語", raw_instruction="...", meta_cells={"生徒": "山田 太郎", "在籍": "在籍中"})
    assert check_record_exclusion(rec_normal) is None

    # 6. filter_target_records の統計集計検証
    all_recs = [rec_demo1, rec_demoda, rec_withdrawn, rec_declined, rec_normal]
    target_recs, stats = filter_target_records(all_recs)
    assert len(target_recs) == 2  # demoda and normal
    assert target_recs[0].student_id == "D004"
    assert target_recs[1].student_id == "D008"
    assert stats.total_html_records == 5
    assert stats.target_records == 2
    assert stats.total_excluded == 3
    assert stats.demo_excluded == 1
    assert stats.withdrawn_excluded == 1
    assert stats.declined_excluded == 1


def test_v5_decorator_and_numbered_headings():
    """v5 §5: 装飾記号 (★☆⚠⚠️※) および番号付き見出し (1作成者、①作成者等) の対応検証"""
    config = AppConfig(base_url="https://example.com")

    # 1. 装飾記号
    inst_decor = """★作成者：山田太郎
☆教材：高校新演習スタンダード（所持）
⚠進め方：テキストの例題を中心に丁寧に復習を行います。
⚠️生徒情報：自発的に学習を進める姿勢が見られます。
※小テスト：単語小テスト
宿題：ワークp.10-15"""
    rec_decor = CurriculumRecord(student_id="DEC01", division="通常授業", subject="英語", raw_instruction=inst_decor)
    res_decor = evaluate_single_record(rec_decor, config)
    assert res_decor.parsed_sections["作成者"] == "山田太郎"
    assert "高校新演習スタンダード" in res_decor.parsed_sections["教材"]
    assert "丁寧に復習を行います" in res_decor.parsed_sections["進め方"]
    assert "自発的に学習を進める" in res_decor.parsed_sections["生徒情報"]
    assert "単語小テスト" in res_decor.parsed_sections["小テスト"]
    assert res_decor.severity == Severity.PASS

    # 原文テキストは改変されていないこと
    assert "★作成者" in rec_decor.raw_instruction

    # 2. 番号付き見出し (1作成者、2教材、3.進め方、④生徒情報 など)
    inst_num = """1作成者：鈴木一郎
2教材：フォレスタ数学（所持）
3.進め方：章末の応用問題を解説しながら進めます。
④生徒情報：計算スピードが向上してきています。
5小テスト：計算テスト
6.宿題：大問3から大問6まで"""
    rec_num = CurriculumRecord(student_id="NUM01", division="通常授業", subject="数学", raw_instruction=inst_num)
    res_num = evaluate_single_record(rec_num, config)
    assert res_num.parsed_sections["作成者"] == "鈴木一郎"
    assert "フォレスタ数学" in res_num.parsed_sections["教材"]
    assert "章末の応用問題を解説" in res_num.parsed_sections["進め方"]
    assert "計算スピードが向上" in res_num.parsed_sections["生徒情報"]
    assert "計算テスト" in res_num.parsed_sections["小テスト"]
    assert res_num.severity == Severity.PASS


def test_v5_textbook_supplementary_separation():
    """v5 §14, §32: 教材と補足事項の分離および教材詳細への出力検証"""
    config = AppConfig(base_url="https://example.com")
    inst = """作成者：講師A
教材：高校新演習スタンダードC（所持）
共通テスト対策に移行する場合は別教材を使用する予定なので、適宜追記
進め方：基礎から標準レベルへのステップアップを目指します。
生徒情報：意欲的に取り組んでおり質問も多いです。
小テスト：英単語1-100
宿題：演習問題A"""
    rec = CurriculumRecord(student_id="TB001", division="通常授業", subject="英語", raw_instruction=inst)
    res = evaluate_single_record(rec, config)

    # 補足事項がステータス未記載エラーを引き起こさないこと
    assert res.severity == Severity.PASS
    assert ERR_TEXTBOOK_STATUS_MISSING not in res.errors

    # textbook_itemsの検証: 教材1件 + 補足1件
    assert len(res.textbook_items) == 2
    tb1 = res.textbook_items[0]
    assert tb1.name == "高校新演習スタンダードC"
    assert tb1.raw_status == "所持"
    assert tb1.category == "所持"
    assert tb1.is_valid is True
    assert tb1.supplementary == ""

    tb2 = res.textbook_items[1]
    assert tb2.name == ""
    assert tb2.category == "補足"
    assert "共通テスト対策に移行する場合は別教材を使用する予定" in tb2.supplementary
    assert tb2.is_valid is True


def test_v5_school_review_evaluation():
    """v5 §15.3, §2: 曖昧な志望校のREVIEW判定検証"""
    from core.constants import REV_SCHOOL_UNCERTAIN, WARN_SCHOOL_NO_TYPE
    config = AppConfig(base_url="https://example.com")

    # 1. 高3で志望校が抽象的な希望「理学療法を学べるところ」 -> REV_SCHOOL_UNCERTAIN (REVIEW)
    inst_vague = """作成者：講師B
志望校：理学療法を学べるところ
教材：重要問題集（所持）
進め方：志望分野に沿った重要テーマを中心に演習します。
生徒情報：目標に向かって学習計画を立てています。
小テスト：確認テスト
宿題：第2章全問"""
    rec_vague = CurriculumRecord(student_id="SCH01", division="高3", subject="生物", raw_instruction=inst_vague)
    res_vague = evaluate_single_record(rec_vague, config)
    assert REV_SCHOOL_UNCERTAIN in res_vague.reviews
    assert res_vague.severity == Severity.REVIEW
    assert "志望校" in res_vague.fix_fields

    # 2. 志望校が「未定」 -> REV_SCHOOL_UNCERTAIN (REVIEW)
    inst_undecided = inst_vague.replace("理学療法を学べるところ", "未定")
    rec_undecided = CurriculumRecord(student_id="SCH02", division="高3", subject="生物", raw_instruction=inst_undecided)
    res_undecided = evaluate_single_record(rec_undecided, config)
    assert REV_SCHOOL_UNCERTAIN in res_undecided.reviews
    assert res_undecided.severity == Severity.REVIEW

    # 3. 志望校の区分（私立/公立等）有無判定は完全廃止 (v6 §19.1: 早稲田でも早稲田大学でも区分不問でPASS)
    inst_notype = inst_vague.replace("理学療法を学べるところ", "早稲田")
    rec_notype = CurriculumRecord(student_id="SCH03", division="高3", subject="生物", raw_instruction=inst_notype)
    res_notype = evaluate_single_record(rec_notype, config)
    assert WARN_SCHOOL_NO_TYPE not in res_notype.warnings
    assert res_notype.severity == Severity.PASS

    # 4. 正式な大学名 -> PASS
    inst_valid = inst_vague.replace("理学療法を学べるところ", "早稲田大学")
    rec_valid = CurriculumRecord(student_id="SCH04", division="高3", subject="生物", raw_instruction=inst_valid)
    res_valid = evaluate_single_record(rec_valid, config)
    assert res_valid.severity == Severity.PASS


def test_v5_severity_hierarchy():
    """v5/v6 §2: 判定レベル順序 (CRITICAL > ERROR > REVIEW > WARNING > PASS) の検証"""
    config = AppConfig(base_url="https://example.com")

    # 1. CRITICAL: 備考欄空欄
    rec_crit = CurriculumRecord(student_id="SEV01", division="通常授業", subject="英語", raw_instruction="")
    res_crit = evaluate_single_record(rec_crit, config)
    assert res_crit.severity == Severity.CRITICAL

    # 2. ERROR: 作成者欠落 (他の警告やREVIEWがあってもERRORが勝つ)
    inst_err = """志望校：未定
教材：新演習（所持）
進め方：テキスト演習を進めます。
生徒情報：真面目に取り組んでいます。
小テスト：単語テスト
宿題：p.10"""
    rec_err = CurriculumRecord(student_id="SEV02", division="高3", subject="英語", raw_instruction=inst_err)
    res_err = evaluate_single_record(rec_err, config)
    assert res_err.severity == Severity.ERROR

    # 3. REVIEW: ERRORなし、志望校未定 (警告があってもREVIEWが勝つ)
    inst_rev = """作成者：講師C
志望校：未定
教材：新演習（所持）
進め方：テキスト演習を進めます。
生徒情報：真面目に取り組んでいます。
小テスト：単語テスト
宿題：p.10"""
    rec_rev = CurriculumRecord(student_id="SEV03", division="高3", subject="英語", raw_instruction=inst_rev)
    res_rev = evaluate_single_record(rec_rev, config)
    assert res_rev.severity == Severity.REVIEW

    # 4. WARNING: 講習授業で目標未記載 (WARN_GOAL_MISSING)
    inst_warn = """作成者：講師C
講座数：10コマ
教材：新演習（所持）
進め方：テキスト演習を進めます。
生徒情報：真面目に取り組んでいます。
小テスト：単語テスト
宿題：p.10"""
    rec_warn = CurriculumRecord(student_id="SEV04", division="夏期講習", subject="英語", raw_instruction=inst_warn)
    res_warn = evaluate_single_record(rec_warn, config)
    assert res_warn.severity == Severity.WARNING

    # 5. PASS: 不備なし
    inst_pass = """作成者：講師C
志望校：早稲田大学
教材：新演習（所持）
進め方：テキスト演習を進めます。
生徒情報：真面目に取り組んでいます。
小テスト：単語テスト
宿題：p.10"""
    rec_pass = CurriculumRecord(student_id="SEV05", division="高3", subject="英語", raw_instruction=inst_pass)
    res_pass = evaluate_single_record(rec_pass, config)
    assert res_pass.severity == Severity.PASS


def test_v6_logical_newline_restoration():
    """v6 §5.3, §42: 改行欠落指示書の論理改行復元
    1行に【作成者】...【目標】...【教材】... と連なっている場合でも、正しく各見出しが分離・解析されること
    """
    config = AppConfig(base_url="https://example.com")
    raw = "【作成者】山田【目標】定期テスト対策【教材】ロードスター（所持）【進め方】基礎から標準レベルへのステップアップを目指します【生徒情報】真面目に取り組んでいます【小テスト】確認テスト【宿題】p.1-5"
    rec = CurriculumRecord(student_id="V6_01", division="通常授業", subject="数学", raw_instruction=raw)
    res = evaluate_single_record(rec, config)

    assert res.parsed_sections["作成者"] == "山田"
    assert "基礎から標準レベル" in res.parsed_sections["進め方"]
    assert "真面目に取り組んでいます" in res.parsed_sections["生徒情報"]
    assert res.parsed_sections["小テスト"] == "確認テスト"
    assert res.parsed_sections["宿題"] == "p.1-5"
    assert "ロードスター" in res.parsed_sections["教材"]
    # v7 §3: エラー・警告なしだが【目標】が未分類テキストとして残るため INFO 判定
    assert res.severity == Severity.INFO
    assert len(res.errors) == 0


def test_v6_bracket_and_colon_body_handling():
    """v6 §6.4, §10, §42: 本文中の【1】【2】や「1回目：...」が未知見出しとして誤認識されないこと"""
    config = AppConfig(base_url="https://example.com")
    raw = """【作成者】佐藤
【教材】フォレスタ（所持）
【進め方】
【1】教材説明
【2】問題演習
1回目：新演習 p1～5
第2回：章末問題演習
【生徒情報】意欲的に取り組んでいます。
【小テスト】単語テスト
【宿題】p.10"""
    rec = CurriculumRecord(student_id="V6_02", division="通常授業", subject="英語", raw_instruction=raw)
    res = evaluate_single_record(rec, config)

    # 【1】, 【2】, 1回目：などが未知見出し扱いされず、進め方の本文に格納されていること
    assert WARN_UNCLASSIFIED_TEXT not in res.warnings
    assert res.unclassified_count == 0
    assert "【1】教材説明" in res.parsed_sections["進め方"]
    assert "【2】問題演習" in res.parsed_sections["進め方"]
    assert "1回目" in res.parsed_sections["進め方"] and "新演習" in res.parsed_sections["進め方"]
    assert "第2回" in res.parsed_sections["進め方"] and "章末問題演習" in res.parsed_sections["進め方"]
    assert res.severity == Severity.PASS


def test_v6_alias_and_lesson_heading():
    """v6 §8, §11, §42: 【授業】や【進み方】が「進め方」に、【メイン教材】【補助教材】が「教材」に対応すること"""
    config = AppConfig(base_url="https://example.com")
    raw = """【作成者】鈴木
【メイン教材】フォレスタ英語（所持）
【補助教材】英単語ターゲット（所持）
【授業】
①教材の要点解説
②基本問題の反復
【生徒情報】質問が積極的です。
【小テスト】ターゲット1-50
【宿題】フォレスタ p.20-25"""
    rec = CurriculumRecord(student_id="V6_03", division="通常授業", subject="英語", raw_instruction=raw)
    res = evaluate_single_record(rec, config)

    assert "フォレスタ英語" in res.parsed_sections["教材"]
    assert "英単語ターゲット" in res.parsed_sections["教材"]
    assert "教材の要点解説" in res.parsed_sections["進め方"]
    assert res.severity == Severity.PASS


def test_v6_textbook_arrow_and_parent_note_separation():
    """v6 §13, §40, §42: 教材欄における矢印（→）や日付、親御さん要望等の補足行の分離"""
    config = AppConfig(base_url="https://example.com")
    raw = """作成者：高橋
教材：トレーニングノートα 英文法（所持）
→7/31鈴木【親御さんより学校課題サポートの希望あり】
進め方：テキスト演習を中心に進めます。
生徒情報：意欲的に取り組んでいます。
小テスト：確認テスト
宿題：ノートp.5-10"""
    rec = CurriculumRecord(student_id="V6_04", division="通常授業", subject="英語", raw_instruction=raw)
    res = evaluate_single_record(rec, config)

    assert res.severity == Severity.PASS
    assert len(res.textbook_items) == 2
    tb1 = res.textbook_items[0]
    assert tb1.name == "トレーニングノートα 英文法"
    assert tb1.category == "所持"
    assert tb1.is_valid is True

    tb2 = res.textbook_items[1]
    assert tb2.category == "補足"
    assert "親御さんより学校課題サポートの希望あり" in tb2.supplementary


def test_v6_homework_valid_and_invalid_patterns():
    """v6 §17, §42: 宿題の有効記述（「授業の残り」「Winpass、単語勉強」等）と無効（なし、特になし）の判定"""
    config = AppConfig(base_url="https://example.com")

    # 1. 授業の残り -> PASS
    raw1 = """作成者：講師D
教材：新演習（所持）
進め方：テキストの例題を中心に丁寧に解説を進めます。
生徒情報：学習に対して意欲的に取り組んでいます。
小テスト：単語テスト
宿題：授業の残り"""
    rec1 = CurriculumRecord(student_id="V6_05A", division="通常授業", subject="数学", raw_instruction=raw1)
    res1 = evaluate_single_record(rec1, config)
    assert ERR_HOMEWORK_MISSING not in res1.errors
    assert res1.severity == Severity.PASS

    # 2. Winpass、単語勉強 -> PASS
    raw2 = raw1.replace("宿題：授業の残り", "宿題：Winpass、単語勉強")
    rec2 = CurriculumRecord(student_id="V6_05B", division="通常授業", subject="英語", raw_instruction=raw2)
    res2 = evaluate_single_record(rec2, config)
    assert ERR_HOMEWORK_MISSING not in res2.errors
    assert res2.severity == Severity.PASS

    # 3. なし -> ERROR
    raw3 = raw1.replace("宿題：授業の残り", "宿題：なし")
    rec3 = CurriculumRecord(student_id="V6_05C", division="通常授業", subject="数学", raw_instruction=raw3)
    res3 = evaluate_single_record(rec3, config)
    assert ERR_HOMEWORK_MISSING in res3.errors
    assert res3.severity == Severity.ERROR


def test_v6_critical_dom_failure_and_empty():
    """v6 §3, §42: [DOM取得失敗]、空文字、空白のみは CRITICAL (CRIT_INSTRUCTION_EMPTY)"""
    from core.constants import CRIT_INSTRUCTION_EMPTY
    config = AppConfig(base_url="https://example.com")

    for raw in ["[DOM取得失敗]", " [DOM取得失敗] ", "[エラー]", "", "   \n\t  "]:
        rec = CurriculumRecord(student_id="V6_06", division="通常授業", subject="数学", raw_instruction=raw)
        res = evaluate_single_record(rec, config)
        assert res.severity == Severity.CRITICAL
        assert CRIT_INSTRUCTION_EMPTY in res.errors


def test_v6_sentence_newlines_in_excel():
    """v6 §32: Excel表示用の文末・見出し前改行フォーマット (句点および行途中の【見出し】)"""
    from core.excel_exporter import format_sentence_newlines

    # 句点での改行
    text1 = "第1講を演習します。次に確認テストを行います！質問も受け付けます。"
    formatted1 = format_sentence_newlines(text1)
    assert "第1講を演習します。\n次に確認テストを行います！\n質問も受け付けます。" == formatted1

    # 行途中の【見出し】の前での改行
    text2 = "山田太郎【教材】フォレスタ（所持）【進め方】基礎演習"
    formatted2 = format_sentence_newlines(text2)
    assert "山田太郎\n【教材】フォレスタ（所持）\n【進め方】基礎演習" == formatted2


# ---------------------------------------------------------------------------
# 仕様書 v7 新機能テスト
# ---------------------------------------------------------------------------

def test_v7_severity_info_when_only_unclassified_text():
    """v7 §2, §3: エラー・レビュー・警告が0件で未分類テキストのみ存在する場合、判定ランクは INFO となること"""
    from core.constants import INFO_UNCLASSIFIED_TEXT
    config = AppConfig(base_url="https://example.com")

    # 未分類テキスト（目標）のみが残る完全な指示書
    raw_info = """作成者：鈴木
教材：フォレスタ（所持）
進め方：第1単元から順番に演習と解説を進めます
生徒情報：集中力があり真面目に取り組みます
小テスト：毎回の確認テスト
宿題：ワーク10ページから15ページ
目標：期末テスト80点以上"""

    rec = CurriculumRecord(student_id="V7_01", division="通常授業", subject="数学", raw_instruction=raw_info)
    res = evaluate_single_record(rec, config)

    assert len(res.errors) == 0
    assert len(res.reviews) == 0
    assert len(res.warnings) == 0
    assert res.unclassified_count > 0
    assert res.severity == Severity.INFO
    assert res.primary_error == INFO_UNCLASSIFIED_TEXT
    assert any(i.severity == Severity.INFO and i.rule_id == INFO_UNCLASSIFIED_TEXT for i in res.issues)

    # 未分類テキストも一切ない完全な指示書は PASS となること
    raw_pass = """作成者：鈴木
教材：フォレスタ（所持）
進め方：第1単元から順番に演習と解説を進めます
生徒情報：集中力があり真面目に取り組みます
小テスト：毎回の確認テスト
宿題：ワーク10ページから15ページ"""

    rec_pass = CurriculumRecord(student_id="V7_02", division="通常授業", subject="数学", raw_instruction=raw_pass)
    res_pass = evaluate_single_record(rec_pass, config)
    assert res_pass.severity == Severity.PASS
    assert res_pass.unclassified_count == 0


def test_v7_classroom_and_school_year_metadata_persistence(tmp_path):
    """v7 §7, §9, §16: 教室名・教室コード・年度の保持およびキャッシュ永続化"""
    from core.cache import CacheManager
    cache_mgr = CacheManager(cache_dir=str(tmp_path))

    records = [
        CurriculumRecord(
            student_id="V7_101",
            division="通常授業",
            subject="英語",
            raw_instruction="作成者:田中",
            school_year="2026年度",
            classroom_code="31198",
            classroom_name="天王寺校",
        ),
        CurriculumRecord(
            student_id="V7_102",
            division="通常授業",
            subject="数学",
            raw_instruction="作成者:佐藤",
            school_year="2026年度",
            classroom_code="31200",
            classroom_name="梅田校",
        ),
    ]

    # キャッシュ保存と復元
    cache_mgr.save(records, "1.0.0")
    loaded_records, corrupt_lines, status = cache_mgr.load()

    assert loaded_records is not None
    assert len(loaded_records) == 2
    assert loaded_records[0].classroom_name == "天王寺校"
    assert loaded_records[0].classroom_code == "31198"
    assert loaded_records[0].school_year == "2026年度"
    assert loaded_records[1].classroom_name == "梅田校"
    assert loaded_records[1].classroom_code == "31200"
    assert loaded_records[1].school_year == "2026年度"


def test_v7_excel_classroom_matrix_and_info_column(tmp_path):
    """v7 §16, §20, §22: 教室別集計マトリックス、チェック結果18列、教材詳細11列、INFO水色スタイリングの検証"""
    import openpyxl
    config = AppConfig(base_url="https://example.com")

    # 教室A: PASSとINFO
    rec1 = CurriculumRecord(
        student_id="V7_201",
        division="通常授業",
        subject="英語",
        raw_instruction="""作成者:田中
教材:フォレスタ(所持)
進め方:第1単元から順番に基礎演習と解説を進めます
生徒情報:真面目に取り組めています
小テスト:単語テスト
宿題:p.1-10""",
        school_year="2026年度",
        classroom_code="C01",
        classroom_name="天王寺校",
    )
    # 教室B: ERROR (作成者欠落)
    rec2 = CurriculumRecord(
        student_id="V7_202",
        division="通常授業",
        subject="数学",
        raw_instruction="""教材:フォレスタ(所持)
進め方:第1単元から順番に基礎演習と解説を進めます
生徒情報:真面目に取り組めています
小テスト:計算テスト
宿題:p.1-10""",
        school_year="2026年度",
        classroom_code="C02",
        classroom_name="梅田校",
    )
    # 教室A: INFO (目標あり)
    rec3 = CurriculumRecord(
        student_id="V7_203",
        division="通常授業",
        subject="国語",
        raw_instruction="""作成者:田中
教材:新演習(所持)
進め方:第1単元から順番に基礎演習と解説を進めます
生徒情報:真面目に取り組めています
小テスト:漢字テスト
宿題:p.1-5
目標:得点アップ""",
        school_year="2026年度",
        classroom_code="C01",
        classroom_name="天王寺校",
    )

    recs = [rec1, rec2, rec3]
    res1 = evaluate_single_record(rec1, config)
    res2 = evaluate_single_record(rec2, config)
    res3 = evaluate_single_record(rec3, config)
    results = [res1, res2, res3]

    assert res1.severity == Severity.PASS
    assert res2.severity == Severity.ERROR
    assert res3.severity == Severity.INFO

    exporter = ExcelExporter()
    out_file = exporter.export(str(tmp_path), recs, results, timestamp="20260914_v7test")
    wb = openpyxl.load_workbook(out_file)

    # 1. チェック結果シート (v10 §6.1: 20列 + INFO水色)
    ws_check = wb["チェック結果"]
    headers = [ws_check.cell(row=1, column=c).value for c in range(1, 21)]
    expected_headers = [
        "教室名", "教室コード", "年度", "学籍番号", "生徒名", "学年", "受講区分", "科目", "判定", "修正項目",
        "エラー", "警告", "作成者", "志望校", "教材", "進め方",
        "生徒情報", "小テスト", "宿題", "未分類テキスト"
    ]
    assert headers == expected_headers

    # 行の色判定: rec3 (行4) は INFO (#E3F2FD) - 判定列は第9列
    cell_info_severity = ws_check.cell(row=4, column=9)
    assert cell_info_severity.value == "INFO"
    fill_color = cell_info_severity.fill.start_color.rgb
    # openpyxl color string may be '00E3F2FD' or 'E3F2FD'
    assert "E3F2FD" in str(fill_color)

    # 2. サマリーシート (教室別集計マトリックス & 作成者別集計のINFO列)
    ws_sum = wb["サマリー"]
    matrix_found = False
    author_info_found = False

    for r in range(1, 80):
        val = str(ws_sum.cell(row=r, column=2).value or "")
        if "【教室別集計マトリックス】" in val:
            matrix_found = True
            # 次行のヘッダー確認
            m_h = [ws_sum.cell(row=r+1, column=c).value for c in range(2, 6)]
            assert "項目名" in m_h
            assert "天王寺校" in m_h
            assert "梅田校" in m_h
            assert "全体" in m_h
        if "【作成者別集計】" in val:
            # 次行のヘッダー確認 (8列)
            a_h = [ws_sum.cell(row=r+1, column=c).value for c in range(2, 10)]
            assert "情報" in a_h
            author_info_found = True

    assert matrix_found
    assert author_info_found

    # 3. 教材詳細シート (v10 §6.4: 13列)
    ws_tb = wb["教材詳細"]
    tb_headers = [ws_tb.cell(row=1, column=c).value for c in range(1, 14)]
    expected_tb_headers = [
        "学籍番号", "生徒名", "学年", "受講区分", "科目", "教室名", "教室コード", "年度",
        "教材", "ステータス", "ステータス分類", "判定", "補足"
    ]
    assert tb_headers == expected_tb_headers


def test_v7_new_section_aliases():
    """v7 §4.1: 追加された表記揺れエイリアスの認識検証"""
    test_cases = [
        ("小テスト内容：計算テスト", "小テスト", "計算テスト"),
        ("授業確認テスト：単語100問", "小テスト", "単語100問"),
        ("小テストスケジュール：毎回実施", "小テスト", "毎回実施"),
        ("宿題スケジュール：テキストp.10-20", "宿題", "テキストp.10-20"),
        ("授業の流れ：解説から演習", "進め方", "解説から演習"),
        ("内容、進め方：一問一答形式", "進め方", "一問一答形式"),
        ("授業スケジュール：第1講から第5講", "進め方", "第1講から第5講"),
        ("生徒の特徴：集中力が高い", "生徒情報", "集中力が高い"),
        ("授業の注意点：途中式を書かせる", "生徒情報", "途中式を書かせる"),
        ("作成者・作成日：山田 (2026/09/14)", "作成者", "山田 (2026/09/14)"),
        ("制作者：高橋", "作成者", "高橋"),
        ("現時点での志望校：神戸大学", "志望校", "神戸大学"),
        ("設定教材について：フォレスタ（所持）", "教材", "フォレスタ（所持）"),
    ]

    for line, expected_section, expected_body in test_cases:
        sections, _, _ = parse_sections(line)
        assert expected_section in sections
        assert expected_body in sections[expected_section]


def test_v7_unknown_bracket_annotation_not_heading():
    """v7 §4.5: 未知の【...】は未知見出しではなく本文・注記として扱われること"""
    raw = """作成者：吉田
教材：フォレスタ（所持）
進め方：
【親御さんからのご要望】
基礎的な計算力を定着させてほしいとのことです。
生徒情報：真面目に取り組めています
小テスト：計算テスト
宿題：p.10-15"""

    sections, uc_count, uc_text = parse_sections(clean_instruction(raw))
    # 【親御さんからのご要望】は進め方の本文に入り、未知見出しにならないこと
    assert "親御さんからのご要望" in sections["進め方"]
    assert "基礎的な計算力" in sections["進め方"]
    assert "親御さんからのご要望" not in uc_text
    assert uc_count == 0






