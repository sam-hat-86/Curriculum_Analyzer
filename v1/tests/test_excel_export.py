"""
Excel出力およびファイルロック安全性のテスト (仕様書 v9 §40.4, §40.5, §43)
"""

import os
from pathlib import Path
import pytest
import openpyxl

from core.models import AppConfig, CurriculumRecord, Severity
from core.evaluator import evaluate_single_record
from core.excel_exporter import ExcelExporter, sanitize_excel_value


@pytest.fixture
def sample_records_and_results():
    config = AppConfig(base_url="https://example.com")
    rec1 = CurriculumRecord(
        student_id="=1+1",  # 数式インジェクション検証用
        division="通常授業",
        subject="英語",
        raw_instruction="""作成者:山田
教材:フォレスタ(所持)
進め方:演習を進めます
生徒情報:真面目
小テスト:単語
宿題:p.10""",
        school_year="2026年度",
        classroom_code="C01",
        classroom_name="天王寺校",
    )
    rec2 = CurriculumRecord(
        student_id="STU_002",
        division="夏期講習",
        subject="数学",
        raw_instruction="""教材:新演習(未所持)
進め方:演習
生徒情報:良好
小テスト:計算
宿題:p.20
講座数:5回
目標:点数アップ""",
        school_year="2026年度",
        classroom_code="C02",
        classroom_name="梅田校",
    )
    recs = [rec1, rec2]
    res1 = evaluate_single_record(rec1, config)
    res2 = evaluate_single_record(rec2, config)
    return recs, [res1, res2]


def test_excel_export_sheets_headers_and_safety(tmp_path, sample_records_and_results):
    """v9 §40.4: 7シートの存在、シート名、ヘッダー順、数式インジェクション対策の検証"""
    records, results = sample_records_and_results
    exporter = ExcelExporter()
    out_file = exporter.export(str(tmp_path), records, results, timestamp="20260914_test")

    assert os.path.exists(out_file)
    assert out_file.endswith(".xlsx")
    assert exporter.was_renamed is False

    wb = openpyxl.load_workbook(out_file)
    expected_sheets = ["チェック結果", "判定一覧", "解析詳細", "原文", "サマリー", "未知表記", "教材詳細"]
    assert wb.sheetnames == expected_sheets
    assert "要修正" not in wb.sheetnames
    assert "警告" not in wb.sheetnames

    # 1. チェック結果シート検証 (v10 §6.1: 20列)
    ws_check = wb["チェック結果"]
    headers = [ws_check.cell(row=1, column=c).value for c in range(1, 21)]
    expected_headers = [
        "教室名", "教室コード", "年度", "学籍番号", "生徒名", "学年", "受講区分", "科目", "判定", "修正項目",
        "エラー", "警告", "作成者", "志望校", "教材", "進め方",
        "生徒情報", "小テスト", "宿題", "未分類テキスト"
    ]
    assert headers == expected_headers
    assert "最重要エラー" not in headers

    # 教室情報が先頭列に正しく出力されていること
    assert ws_check.cell(row=2, column=1).value == "天王寺校"
    assert ws_check.cell(row=2, column=2).value == "C01"
    assert ws_check.cell(row=2, column=3).value == "2026年度"

    # 数式インジェクション対策: =1+1 が '=1+1 としてサニタイズされていること
    assert ws_check.cell(row=2, column=4).value == "'=1+1"

    # 原文シート検証 (v10 §6.2: 10列)
    ws_raw = wb["原文"]
    raw_headers = [ws_raw.cell(row=1, column=c).value for c in range(1, 11)]
    expected_raw_headers = [
        "教室名", "教室コード", "年度", "学籍番号", "生徒名", "学年", "受講区分", "科目", "判定", "原文備考欄"
    ]
    assert raw_headers == expected_raw_headers

    # 解析詳細シート検証 (v10 §6.3: 10列)
    ws_trace = wb["解析詳細"]
    trace_headers = [ws_trace.cell(row=1, column=c).value for c in range(1, 11)]
    expected_trace_headers = [
        "学籍番号", "生徒名", "学年", "行番号", "原文行", "検出見出し", "正規化見出し", "割当セクション", "信頼度", "本文"
    ]
    assert trace_headers == expected_trace_headers

    # 教材詳細シート検証 (v10 §6.4: 13列)
    ws_tb = wb["教材詳細"]
    tb_headers = [ws_tb.cell(row=1, column=c).value for c in range(1, 14)]
    expected_tb_headers = [
        "学籍番号", "生徒名", "学年", "受講区分", "科目", "教室名", "教室コード", "年度",
        "教材", "ステータス", "ステータス分類", "判定", "補足"
    ]
    assert tb_headers == expected_tb_headers

    # 2. サマリーシート検証 (教室別マトリックス)
    ws_sum = wb["サマリー"]
    matrix_found = False
    for r in range(1, 80):
        val = str(ws_sum.cell(row=r, column=2).value or "")
        if "【教室別集計マトリックス】" in val:
            matrix_found = True
            m_h = [ws_sum.cell(row=r+1, column=c).value for c in range(2, 6)]
            assert "項目名" in m_h
            assert "天王寺校" in m_h
            assert "梅田校" in m_h
            assert "全体" in m_h
            break
    assert matrix_found


def test_excel_export_file_lock_auto_rename(tmp_path, sample_records_and_results):
    """v9 §40.5, §16: ファイルロック時のタイムスタンプ付き別名保存フォールバック検証"""
    records, results = sample_records_and_results
    exporter = ExcelExporter()

    # 先に通常保存
    out_file1 = exporter.export(str(tmp_path), records, results, timestamp="20260914_locktest")
    assert os.path.exists(out_file1)
    assert exporter.was_renamed is False

    # out_file1 を排他モードで開きっぱなしにしてロックを再現
    with open(out_file1, "r+b") as lock_f:
        # ロック中に同じパスへ再度エクスポート実行
        out_file2 = exporter.export(str(tmp_path), records, results, timestamp="20260914_locktest")

        # ロックを検知して別名で保存され、was_renamed が True になっていること
        assert exporter.was_renamed is True
        assert os.path.exists(out_file2)
        assert out_file2 != out_file1
        assert "20260914_locktest" in out_file2

    # ロック解除後、out_file2 が正常なExcelブックとして読み込めること
    wb = openpyxl.load_workbook(out_file2)
    assert "チェック結果" in wb.sheetnames


def test_excel_post_save_verification_failure(tmp_path):
    """v9 §43.3, §43.4: 保存後検証で異常ファイル（空・必須シート欠落）を検知して例外発生すること"""
    exporter = ExcelExporter()

    # 存在しないファイル
    with pytest.raises(RuntimeError, match="一時Excelファイルが存在しません"):
        exporter._verify_exported_excel(str(tmp_path / "non_existent.xlsx"))

    # サイズが極端に小さい空ファイル
    tiny_file = tmp_path / "tiny.xlsx"
    tiny_file.write_bytes(b"PK\x03\x04")
    with pytest.raises(RuntimeError, match="サイズが不正です"):
        exporter._verify_exported_excel(str(tiny_file))

    # シートが不足しているExcelファイル
    bad_wb = openpyxl.Workbook()
    bad_wb.active.title = "チェック結果のみ"
    bad_wb_path = tmp_path / "bad_sheets.xlsx"
    bad_wb.save(str(bad_wb_path))

    with pytest.raises(RuntimeError, match="必須シートが不足しています"):
        exporter._verify_exported_excel(str(bad_wb_path))


def test_excel_export_student_name_alignment(tmp_path, sample_records_and_results):
    """生徒名セルが全対象シート（チェック結果、原文、解析詳細、教材詳細）で中央揃えになっていることの検証"""
    records, results = sample_records_and_results
    exporter = ExcelExporter()
    out_file = exporter.export(str(tmp_path), records, results, timestamp="20260915_align_test")

    wb = openpyxl.load_workbook(out_file)

    # 1. チェック結果シート (列5: 生徒名)
    ws_check = wb["チェック結果"]
    cell_check = ws_check.cell(row=2, column=5)
    assert cell_check.alignment.horizontal == "center"
    assert cell_check.alignment.vertical == "center"

    # 2. 原文シート (列5: 生徒名)
    ws_raw = wb["原文"]
    cell_raw = ws_raw.cell(row=2, column=5)
    assert cell_raw.alignment.horizontal == "center"
    assert cell_raw.alignment.vertical == "center"

    # 3. 解析詳細シート (列2: 生徒名)
    ws_trace = wb["解析詳細"]
    if ws_trace.max_row >= 2:
        cell_trace = ws_trace.cell(row=2, column=2)
        assert cell_trace.alignment.horizontal == "center"
        assert cell_trace.alignment.vertical == "center"

    # 4. 教材詳細シート (列2: 生徒名)
    ws_tb = wb["教材詳細"]
    if ws_tb.max_row >= 2:
        cell_tb = ws_tb.cell(row=2, column=2)
        assert cell_tb.alignment.horizontal == "center"
        assert cell_tb.alignment.vertical == "center"


def test_excel_export_sheets_and_student_columns(tmp_path):
    """Excel出力全対象シートに生徒名・学年が正しく配置されることの検証"""
    config = AppConfig(base_url="https://example.com")
    rec = CurriculumRecord(
        student_id="STU_8888",
        student_name="田中 一郎",
        grade="高3",
        division="通常授業",
        subject="英語",
        raw_instruction="""作成者:山田
志望校:京都大学
教材:体系数学(所持)
進め方:第1回から基本問題の演習を進めます
生徒情報:真面目で学習態度は大変良好です
小テスト:英単語
宿題:p.15""",
        classroom_name="京都校",
        classroom_code="K01",
        school_year="2026年度",
    )
    res = evaluate_single_record(rec, config)

    exporter = ExcelExporter()
    out_file = exporter.export(str(tmp_path), [rec], [res], timestamp="20260914_sheet_test")
    assert os.path.exists(out_file)

    wb = openpyxl.load_workbook(out_file)

    # 1. チェック結果 (20列)
    # [教室名, 教室コード, 年度, 学籍番号, 生徒名, 学年, 受講区分, 科目, 判定, ...]
    ws_check = wb["チェック結果"]
    assert ws_check.cell(row=2, column=1).value == "京都校"
    assert ws_check.cell(row=2, column=2).value == "K01"
    assert ws_check.cell(row=2, column=3).value == "2026年度"
    assert ws_check.cell(row=2, column=4).value == "STU_8888"
    assert ws_check.cell(row=2, column=5).value == "田中 一郎"
    assert ws_check.cell(row=2, column=6).value == "高3"
    assert ws_check.cell(row=2, column=7).value == "通常授業"
    assert ws_check.cell(row=2, column=8).value == "英語"
    assert ws_check.cell(row=2, column=9).value == "PASS"

    # 2. 原文 (10列)
    # [教室名, 教室コード, 年度, 学籍番号, 生徒名, 学年, 受講区分, 科目, 判定, 原文備考欄]
    ws_raw = wb["原文"]
    assert ws_raw.cell(row=2, column=1).value == "京都校"
    assert ws_raw.cell(row=2, column=2).value == "K01"
    assert ws_raw.cell(row=2, column=3).value == "2026年度"
    assert ws_raw.cell(row=2, column=4).value == "STU_8888"
    assert ws_raw.cell(row=2, column=5).value == "田中 一郎"
    assert ws_raw.cell(row=2, column=6).value == "高3"
    assert ws_raw.cell(row=2, column=7).value == "通常授業"
    assert ws_raw.cell(row=2, column=8).value == "英語"
    assert ws_raw.cell(row=2, column=9).value == "PASS"

    # 3. 解析詳細 (10列)
    # [学籍番号, 生徒名, 学年, 行番号, 原文行, 検出見出し, 正規化見出し, 割当セクション, 信頼度, 本文]
    ws_trace = wb["解析詳細"]
    assert ws_trace.cell(row=2, column=1).value == "STU_8888"
    assert ws_trace.cell(row=2, column=2).value == "田中 一郎"
    assert ws_trace.cell(row=2, column=3).value == "高3"

    # 4. 教材詳細 (13列)
    # [学籍番号, 生徒名, 学年, 受講区分, 科目, 教室名, 教室コード, 年度, 教材, ステータス, ステータス分類, 判定, 補足]
    ws_tb = wb["教材詳細"]
    assert ws_tb.cell(row=2, column=1).value == "STU_8888"
    assert ws_tb.cell(row=2, column=2).value == "田中 一郎"
    assert ws_tb.cell(row=2, column=3).value == "高3"
    assert ws_tb.cell(row=2, column=4).value == "通常授業"
    assert ws_tb.cell(row=2, column=5).value == "英語"
    assert ws_tb.cell(row=2, column=6).value == "京都校"
    assert ws_tb.cell(row=2, column=7).value == "K01"
    assert ws_tb.cell(row=2, column=8).value == "2026年度"
    assert ws_tb.cell(row=2, column=9).value == "体系数学"
    assert ws_tb.cell(row=2, column=10).value == "所持"


