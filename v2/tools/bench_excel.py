r"""
Excel 5シート出力パフォーマンステスト・ベンチマークスクリプト
使い方:
    cd v2
    ..\.venv\Scripts\python.exe tools/bench_excel.py --units 60000
"""
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.exporter.excel_exporter import ExcelExporter
from src.exporter.safe_writer import SafeExcelWriter
from src.models.curriculum import (
    CurriculumOverview,
    TargetInfo,
    UnitRecord,
    TargetProgress,
    CurriculumDetailData,
)
from src.models.evaluation import InstructionEvaluation
from src.models.state import ProcessState, TimingCategory


def run_benchmark(total_units: int = 30000, units_per_student: int = 30):
    num_students = max(1, total_units // max(1, units_per_student))
    print(f"=== Excel Export Benchmark (Students: {num_students}, Total Units: {num_students * units_per_student}) ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "bench.db")
        out_dir = os.path.join(tmpdir, "out")
        db_manager = DatabaseManager(db_path)
        repo = Repository(db_manager)

        t0 = time.perf_counter()
        overviews = []
        for i in range(num_students):
            ov = CurriculumOverview(
                classroom_name=f"教室{(i % 10) + 1}",
                classroom_code=f"{1000 + (i % 10)}",
                school_year="2026",
                student_id=f"STU{i:05d}",
                student_name=f"テスト生徒{i:05d}",
                grade=["中1", "中2", "中3", "高1", "高2", "高3"][i % 6],
                division="通常",
                subject=["英語", "数学", "国語", "理科", "社会"][i % 5],
                row_index=i % 50,
                page_index=(i // 50) + 1,
                status=ProcessState.SAVED,
            )
            overviews.append(ov)

        repo.save_pages_init(overviews)

        with db_manager.connect() as conn:
            for i, ov in enumerate(overviews):
                has_delay = (i % 4 == 0)
                t1 = TargetInfo(
                    target_no="T1",
                    target_name="1学期中間",
                    progress_delay="進捗遅れ" if has_delay else "OK",
                    start_date="2026/04/01",
                    end_date="2026/05/31",
                    period_str="2026/04/01～2026/05/31",
                    is_current=True,
                    target_score="80",
                    current_score="75",
                    site_progress_rate="80%",
                )
                units = [
                    UnitRecord(
                        unit_no=str(u_idx + 1),
                        unit_name=f"単元_{u_idx + 1}",
                        middle_unit=f"セクション_{(u_idx % 5) + 1}",
                        textbook="標準テキストI",
                        problem_code=f"P{u_idx:03d}",
                        score="8",
                        max_score="10",
                        score_rate="80",
                        execution_date="2026/04/15",
                        timing=TimingCategory.ON_TIME,
                        is_executed=True,
                        today_textbook="標準テキストI",
                        execution_division="通常",
                        confirm_test="合格",
                        target_checks={"T1": True},
                    )
                    for u_idx in range(units_per_student)
                ]
                prog = TargetProgress(
                    classroom=ov.classroom_name,
                    student_id=ov.student_id,
                    grade=ov.grade,
                    student_name=ov.student_name,
                    division=ov.division,
                    subject=ov.subject,
                    target_no="T1",
                    target_name="1学期中間",
                    progress_delay="進捗遅れ" if has_delay else "OK",
                    start_date="2026/04/01",
                    end_date="2026/05/31",
                    period_str="2026/04/01～2026/05/31",
                    is_current=True,
                    textbooks_used="標準テキストI",
                    target_score="80",
                    current_score="75",
                    target_unit_count=units_per_student,
                    executed_count=units_per_student,
                    executed_rate="100",
                    on_time_count=units_per_student,
                    on_time_rate="100",
                    before_count=0,
                    before_rate="0",
                    after_count=0,
                    after_rate="0",
                    unexecuted_count=0,
                    unexecuted_rate="0",
                    latest_execution_date="2026/04/15",
                )
                ev = InstructionEvaluation(
                    severity="WARNING" if (i % 3 == 0) else "PASS",
                    author="担当講師",
                    target_school="公立高校",
                    textbook="標準テキストI (所持)",
                    plan="毎回1単元ずつ進める",
                    student_info="意欲的に取り組んでいる",
                    test="確認テスト80点基準",
                    homework="演習問題2ページ",
                    warnings=["WARN_TEST_CRITERIA_MISSING"] if (i % 3 == 0) else [],
                    fix_items=["小テスト基準を明記"] if (i % 3 == 0) else [],
                )
                detail = CurriculumDetailData(
                    overview=ov,
                    raw_html="<html><body>benchmark</body></html>",
                    fetch_time="2026-10-29 12:00:00",
                    targets=[t1],
                    units=units,
                    instruction_eval=ev,
                    progress_list=[prog],
                )
                repo.save_parsed_result(detail, conn=conn, commit=False)

        t_seed = time.perf_counter() - t0
        print(f"[1] DB Seed Time      : {t_seed:.2f} sec")

        exporter = ExcelExporter(repo)
        writer = SafeExcelWriter(exporter, out_dir)

        t1_start = time.perf_counter()
        out_path = writer.export_final()
        t_export = time.perf_counter() - t1_start
        size_mb = os.path.getsize(out_path) / (1024 * 1024)

        print(f"[2] Excel Export Time : {t_export:.2f} sec (File size: {size_mb:.2f} MB)")
        print(f"[3] Throughput        : {(num_students * units_per_student) / max(0.001, t_export):,.0f} unit-rows/sec")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=int, default=30000, help="Total unit rows to benchmark")
    args = parser.parse_args()
    run_benchmark(total_units=args.units)

