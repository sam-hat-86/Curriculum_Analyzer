"""CSVエクスポーターモジュール。

分析結果を固定15列のCSVとして出力する。
仕様書 §28-30 に準拠し、安全なアトミック出力・検証を行う。
"""

import csv
import os
import time
import uuid
from datetime import datetime
from typing import List

from core.constants import CSV_HEADERS, RULE_MESSAGES, RULE_ORDER
from core.models import CurriculumRecord, EvaluationResult
from core.normalization import sanitize_csv_value


class CsvExporter:
    """CSV出力を行うクラス。"""

    def export(
        self,
        output_dir: str,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
    ) -> str:
        """CSVを出力し、最終的なファイルパスを返す。

        失敗した場合は例外を送出する。
        """
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        if len(records) != len(results):
            raise ValueError("recordsとresultsの要素数が一致しません。")

        final_filepath = self.generate_filename(output_dir)

        pid = os.getpid()
        timestamp = int(time.time())
        uid = uuid.uuid4().hex[:8]
        tmp_filename = f"_tmp_output_{pid}_{timestamp}_{uid}.csv"
        tmp_filepath = os.path.join(output_dir, tmp_filename)

        try:
            with open(tmp_filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(
                    f, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL
                )
                
                # ヘッダー出力
                writer.writerow(CSV_HEADERS)

                # データ出力
                for record, result in zip(records, results):
                    row = self._create_row(record, result)
                    # Formula Injection保護
                    sanitized_row = [sanitize_csv_value(cell) for cell in row]
                    # セル内改行をCRLFに統一
                    crlf_row = [self._fix_newlines(cell) for cell in sanitized_row]
                    writer.writerow(crlf_row)

                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_filepath, final_filepath)

        except Exception as e:
            if os.path.exists(tmp_filepath):
                try:
                    os.remove(tmp_filepath)
                except OSError:
                    pass
            raise RuntimeError(f"CSV出力中にエラーが発生しました: {e}") from e

        if not self.verify_csv(final_filepath, len(records)):
            raise RuntimeError("CSVの出力後検証に失敗しました。")

        return final_filepath

    def generate_filename(self, output_dir: str) -> str:
        """衝突しないファイル名を生成する。"""
        now = datetime.now()
        base_name = f"カリキュラムチェック_{now.strftime('%Y%m%d-%H%M%S')}"

        filepath = os.path.join(output_dir, f"{base_name}.csv")
        if not os.path.exists(filepath):
            return filepath

        for i in range(1, 1000):
            filepath = os.path.join(output_dir, f"{base_name}_{i}.csv")
            if not os.path.exists(filepath):
                return filepath

        raise RuntimeError("ファイル名の衝突が多すぎます。")

    def verify_csv(self, filepath: str, expected_count: int) -> bool:
        """書き込み後の検証を行う。"""
        if not os.path.exists(filepath):
            return False

        if os.path.getsize(filepath) <= 0:
            return False

        try:
            with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)
                except StopIteration:
                    return False

                if header != CSV_HEADERS:
                    return False

                row_count = sum(1 for _ in reader)
                if row_count != expected_count:
                    return False

        except Exception:
            return False

        return True

    def _create_row(self, record: CurriculumRecord, result: EvaluationResult) -> List[str]:
        """出力用の15列のリストを作成する。"""
        def get_section(name: str) -> str:
            return result.parsed_sections.get(name, "")

        errors = self._format_messages(result.errors)
        warnings = self._format_messages(result.warnings)

        return [
            record.student_id if record.student_id else "",
            record.division if record.division else "",
            record.subject if record.subject else "",
            result.severity.value,
            errors,
            warnings,
            get_section("作成者"),
            get_section("志望校"),
            get_section("教材"),
            get_section("進め方"),
            get_section("生徒情報"),
            get_section("小テスト"),
            get_section("宿題"),
            result.unclassified_text if result.unclassified_text else "",
            record.raw_instruction if record.raw_instruction else "",
        ]

    def _format_messages(self, rule_ids: List[str]) -> str:
        """ルールIDのリストをカンマ区切りのメッセージ文字列に変換する。"""
        msgs = []
        rule_set = set(rule_ids)
        for rule in RULE_ORDER:
            if rule in rule_set:
                msgs.append(RULE_MESSAGES.get(rule, rule))
        return ", ".join(msgs)

    def _fix_newlines(self, text: str) -> str:
        """セル内の改行をCRLFに統一する。"""
        if not text:
            return text
        return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
