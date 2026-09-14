import copy
import logging
import os
import traceback
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.constants import (
    ERR_INTERNAL_EVALUATION,
    ERR_PARSER_EXCEPTION,
    RULE_MESSAGES,
)
from core.evaluator import (
    evaluate_batch_duplicates,
    evaluate_single_record,
    filter_target_records,
)
from core.excel_exporter import ExcelExporter
from core.exporter import CsvExporter
from core.models import AppConfig, CurriculumRecord, EvaluationResult, ExclusionStats, Severity

logger = logging.getLogger(__name__)


class AggregationWorker(QThread):
    """集計・出力ワーカー (v7 §10, §12, §13, §14)。

    - バックグラウンドスレッドで個別レコード評価、重複チェック、CSV出力、Excel出力を完結
    - フェーズ進捗 (phase_changed) と パーセンテージ進捗 (progress_changed) を発行
    - 完了時に finished(results, target_records, exclusion_stats, csv_filepath, excel_filepath) を発行
    """

    phase_changed = pyqtSignal(str, int)
    progress_changed = pyqtSignal(int)
    finished = pyqtSignal(list, list, object, str, str, bool)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        records: list[CurriculumRecord],
        config: AppConfig,
        output_dir: str,
        parent: Optional[QThread] = None,
    ) -> None:
        super().__init__(parent)
        self._records = records
        self._config = config
        self._output_dir = output_dir

    def run(self) -> None:
        """集計およびファイル出力を実行する。"""
        try:
            self.phase_changed.emit("集計準備中", 0)
            target_records, exclusion_stats = filter_target_records(self._records)
            total = len(target_records)

            if total == 0:
                self.progress_changed.emit(100)
                self.phase_changed.emit("完了", 100)
                self.finished.emit([], [], exclusion_stats, "", "")
                return

            results: list[EvaluationResult] = []
            report_interval = max(1, min(10, total // 100))

            self.phase_changed.emit("集計中", 5)

            # 1. 個別レコード評価 (進捗 5% - 45%)
            for i, record in enumerate(target_records):
                try:
                    result = evaluate_single_record(record, self._config)
                    results.append(result)
                except Exception as e:
                    logger.error(
                        "レコード評価中に例外: student_id=%s, error=%s\n%s",
                        record.student_id,
                        str(e),
                        traceback.format_exc(),
                    )
                    error_result = EvaluationResult(
                        severity=Severity.ERROR,
                        errors=[ERR_PARSER_EXCEPTION],
                        reviews=[],
                        warnings=[],
                        parsed_sections={},
                        unclassified_count=0,
                        unclassified_text="",
                    )
                    results.append(error_result)

                if (i + 1) % report_interval == 0 or (i + 1) == total:
                    eval_pct = 5 + int((i + 1) / total * 40)
                    self.progress_changed.emit(eval_pct)
                    self.phase_changed.emit(f"精査中 ({i + 1}/{total}件)", eval_pct)

            # 2. バッチ重複チェック (進捗 45% - 50%)
            self.phase_changed.emit("重複チェック中", 48)
            try:
                results = evaluate_batch_duplicates(
                    target_records, results, self._config
                )
            except Exception as e:
                logger.error(
                    "バッチ重複チェック中に例外: %s\n%s",
                    str(e),
                    traceback.format_exc(),
                )

            # 3. CSV出力 (進捗 50% - 55%)
            self.phase_changed.emit("CSV書き込み中", 52)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_exporter = CsvExporter()
            csv_filepath = csv_exporter.export(self._output_dir, target_records, results)

            # 4. Excel出力 (進捗 55% - 95%)
            self.phase_changed.emit("Excel準備中", 55)
            excel_exporter = ExcelExporter()

            def _excel_progress_cb(msg: str, pct: int):
                overall_pct = 55 + int(pct * 0.40)
                self.progress_changed.emit(min(overall_pct, 98))
                self.phase_changed.emit(msg, min(overall_pct, 98))

            excel_filepath = ""
            try:
                excel_filepath = excel_exporter.export(
                    self._output_dir,
                    target_records,
                    results,
                    timestamp=timestamp,
                    exclusion_stats=exclusion_stats,
                    progress_callback=_excel_progress_cb,
                )
            except Exception as ex_err:
                logger.error("Excel出力中に例外: %s\n%s", ex_err, traceback.format_exc())

            was_renamed = getattr(excel_exporter, "was_renamed", False)
            self.progress_changed.emit(100)
            self.phase_changed.emit("出力完了", 100)
            self.finished.emit(results, target_records, exclusion_stats, csv_filepath, excel_filepath, was_renamed)

        except Exception as e:
            logger.error(
                "集計ワーカーの実行中に予期せぬエラー: %s\n%s",
                str(e),
                traceback.format_exc(),
            )
            self.error_occurred.emit(
                f"集計・出力処理中に予期せぬエラーが発生しました:\n{e}"
            )
