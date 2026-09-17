"""
性能・再現性・ログ安全性テスト (仕様書 v9 §38, §39, §42)
"""

import time
from pathlib import Path
import pytest

from core.models import AppConfig, CurriculumRecord, Severity
from core.evaluator import evaluate_single_record
from core.excel_exporter import ExcelExporter


def test_evaluation_reproducibility():
    """v9 §39.1, §39.3: 同一入力・同一設定であれば常に完全に同一の判定結果が生成されること（時間非依存）"""
    config = AppConfig(base_url="https://example.com")
    rec = CurriculumRecord(
        student_id="REP_001",
        division="通常授業",
        subject="英語",
        raw_instruction="""作成者:山田
教材:フォレスタ(所持)
進め方:基礎演習を進めます
生徒情報:真面目に学習しています
小テスト:単語テスト
宿題:p.1-10""",
        school_year="2026年度",
        classroom_code="C01",
        classroom_name="天王寺校",
    )

    res1 = evaluate_single_record(rec, config)
    time.sleep(0.01)
    res2 = evaluate_single_record(rec, config)

    assert res1.severity == res2.severity
    assert res1.errors == res2.errors
    assert res1.warnings == res2.warnings
    assert res1.reviews == res2.reviews
    assert res1.parsed_sections == res2.parsed_sections
    assert res1.reasons == res2.reasons
    assert res1.rule_version == res2.rule_version


def test_performance_benchmark_100_and_500_records(tmp_path):
    """v9 §42.1: 100件、500件の一括評価およびExcel出力の処理時間計測"""
    config = AppConfig(base_url="https://example.com")

    # 100件のレコード生成
    records_100 = [
        CurriculumRecord(
            student_id=f"PERF_{i:04d}",
            division="通常授業" if i % 2 == 0 else "夏期講習",
            subject="数学" if i % 2 == 0 else "英語",
            raw_instruction=f"""作成者:講師_{i % 5}
教材:フォレスタ_{i % 3}(所持)
進め方:第{i % 10 + 1}単元の演習と解説
生徒情報:集中して取り組めています
小テスト:計算テスト
宿題:p.{i % 20 + 1}-{i % 20 + 5}
{"講座数:5回" if i % 2 != 0 else ""}
{"目標:合格" if i % 2 != 0 else ""}""",
            school_year="2026年度",
            classroom_code=f"CLS_{i % 3:02d}",
            classroom_name=f"教室_{i % 3}",
        )
        for i in range(100)
    ]

    # 100件の評価時間
    t0 = time.perf_counter()
    results_100 = [evaluate_single_record(r, config) for r in records_100]
    t_eval_100 = time.perf_counter() - t0

    # 100件のExcel出力時間
    exporter = ExcelExporter()
    t1 = time.perf_counter()
    out_100 = exporter.export(str(tmp_path), records_100, results_100, timestamp="perf100")
    t_export_100 = time.perf_counter() - t1

    assert t_eval_100 < 2.0, f"100件の評価が遅すぎます: {t_eval_100:.2f}s"
    assert t_export_100 < 5.0, f"100件のエクスポートが遅すぎます: {t_export_100:.2f}s"

    # 500件のスケール計測
    records_500 = records_100 * 5
    t2 = time.perf_counter()
    results_500 = [evaluate_single_record(r, config) for r in records_500]
    t_eval_500 = time.perf_counter() - t2

    t3 = time.perf_counter()
    out_500 = exporter.export(str(tmp_path), records_500, results_500, timestamp="perf500")
    t_export_500 = time.perf_counter() - t3

    assert t_eval_500 < 5.0, f"500件の評価が遅すぎます: {t_eval_500:.2f}s"
    assert t_export_500 < 15.0, f"500件のエクスポートが遅すぎます: {t_export_500:.2f}s"
