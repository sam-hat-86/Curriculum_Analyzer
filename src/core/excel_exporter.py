"""
Excel出力モジュール (openpyxl)
改善案 v4 に準拠し、7つの高機能シートを出力する。
1. チェック結果 (全件・最重要エラー・修正項目・CRITICAL/ERROR/WARNING色分け・自動改行・オートフィルター・ウィンドウ枠固定)
2. 判定一覧 (全Rule IDの発生条件・メッセージ・修正方法・件数)
3. 解析詳細 (Parser Debug Mode: 行番号・見出し・割当・信頼度 HIGH/MEDIUM/LOW・本文)
4. 原文 (原文そのままの指示書)
5. サマリー (KPI・最重要エラー別集計・修正項目別集計・作成者別集計)
6. 未知表記 (未知見出しの自動収集・出現頻度・推定セクション・改善候補)
7. 教材詳細 (教材単位の構造化データ・ステータス区分・個別判定)
"""
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.constants import (
    ERR_AUTHOR_MISSING,
    ERR_COURSE_COUNT_MISSING,
    ERR_HOMEWORK_MISSING,
    ERR_INFO_MISSING,
    ERR_INFO_TOO_SHORT,
    ERR_PLAN_MISSING,
    ERR_PLAN_TOO_SHORT,
    ERR_SCHOOL_REQUIRED_ELEM6,
    ERR_SCHOOL_REQUIRED_HIGH3,
    ERR_SCHOOL_REQUIRED_JUNIOR3,
    ERR_TEXTBOOK_MISSING,
    ERR_TEXTBOOK_STATUS_MISSING,
    ERR_TEST_MISSING,
    FORMULA_INJECTION_CHARS,
    INFO_UNCLASSIFIED_TEXT,
    PRIMARY_RULE_PRIORITY,
    REV_SCHOOL_UNCERTAIN,
    RULE_CONDITIONS,
    RULE_FIX_SUGGESTIONS,
    RULE_MESSAGES,
    RULE_ORDER,
    WARN_GOAL_MISSING,
    WARN_TEXTBOOK_NO_STATUS,
)
from core.models import (
    CurriculumRecord,
    EvaluationResult,
    ExclusionStats,
    Severity,
    UnclassifiedType,
)


def sanitize_excel_value(val: any) -> any:
    """数式インジェクション防止 (§28)"""
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in FORMULA_INJECTION_CHARS:
        return "'" + s
    return s


def format_sentence_newlines(text: str) -> str:
    """
    句点（。！？!?）の直後に改行を挿入し、長文中の【】の前後を適切に改行して読みやすくする (v7 §24)。
    既に直後に改行がある場合は重複挿入しない。
    """
    if not text:
        return ""
    res = re.sub(r'([。！？!?])(?!\r?\n|$)', r'\1\n', text)
    res = re.sub(r'(?<!^)(?<!\n)\s*(?=【)', r'\n', res)
    res = re.sub(r'\n{3,}', '\n\n', res)
    return res.strip()


class ExcelExporter:
    """Multi-sheet Excel Exporter using openpyxl (v7)."""

    # Colors (§16, §26)
    COLOR_HEADER_BG = "1F4E78"       # Deep Steel Blue
    COLOR_HEADER_FG = "FFFFFF"       # White
    COLOR_CRITICAL_BG = "FFCDD2"     # Strong Red
    COLOR_CRITICAL_FG = "9A0007"     # Dark Red Text
    COLOR_ERROR_BG = "FFEBEE"        # Soft Pink / Red
    COLOR_REVIEW_BG = "FFE0B2"       # Soft Orange / Peach
    COLOR_WARNING_BG = "FFFDE7"      # Soft Cream / Yellow
    COLOR_INFO_BG = "E3F2FD"         # Soft Light Blue (v7 §16)
    COLOR_PASS_BG = "FFFFFF"         # White
    COLOR_BORDER = "D9D9D9"          # Light Gray Border

    def __init__(self):
        self.header_font = Font(name="Meiryo UI", size=10, bold=True, color=self.COLOR_HEADER_FG)
        self.header_fill = PatternFill(start_color=self.COLOR_HEADER_BG, end_color=self.COLOR_HEADER_BG, fill_type="solid")
        self.body_font = Font(name="Meiryo UI", size=9)
        self.body_bold_font = Font(name="Meiryo UI", size=9, bold=True)
        self.critical_font = Font(name="Meiryo UI", size=9, bold=True, color=self.COLOR_CRITICAL_FG)
        self.title_font = Font(name="Meiryo UI", size=14, bold=True, color="1F4E78")
        self.subtitle_font = Font(name="Meiryo UI", size=11, bold=True, color="333333")

        self.fill_critical = PatternFill(start_color=self.COLOR_CRITICAL_BG, end_color=self.COLOR_CRITICAL_BG, fill_type="solid")
        self.fill_error = PatternFill(start_color=self.COLOR_ERROR_BG, end_color=self.COLOR_ERROR_BG, fill_type="solid")
        self.fill_review = PatternFill(start_color=self.COLOR_REVIEW_BG, end_color=self.COLOR_REVIEW_BG, fill_type="solid")
        self.fill_warning = PatternFill(start_color=self.COLOR_WARNING_BG, end_color=self.COLOR_WARNING_BG, fill_type="solid")
        self.fill_info = PatternFill(start_color=self.COLOR_INFO_BG, end_color=self.COLOR_INFO_BG, fill_type="solid")
        self.fill_pass = PatternFill(start_color=self.COLOR_PASS_BG, end_color=self.COLOR_PASS_BG, fill_type="solid")

        self.thin_border = Border(
            left=Side(style="thin", color=self.COLOR_BORDER),
            right=Side(style="thin", color=self.COLOR_BORDER),
            top=Side(style="thin", color=self.COLOR_BORDER),
            bottom=Side(style="thin", color=self.COLOR_BORDER),
        )

        self.align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        self.align_left = Alignment(horizontal="left", vertical="top", wrap_text=True)
        self.align_right = Alignment(horizontal="right", vertical="top", wrap_text=True)

    def export(
        self,
        output_dir: str,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
        timestamp: Optional[str] = None,
        exclusion_stats: Optional[ExclusionStats] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> str:
        """
        7つのシートを持つExcelブックを出力する (v7 §16-§25)。
        """
        if progress_callback:
            progress_callback("Excel準備中", 10)

        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"Curriculum_Analysis_{timestamp}.xlsx"
        filepath = os.path.join(output_dir, filename)

        wb = openpyxl.Workbook()
        default_sheet = wb.active
        default_sheet.title = "チェック結果"

        if progress_callback:
            progress_callback("Excel書き込み中 (チェック結果)", 25)
        # 1. チェック結果 (Main)
        self._build_check_results_sheet(default_sheet, records, results)

        if progress_callback:
            progress_callback("Excel書き込み中 (判定一覧・解析詳細)", 45)
        # 2. 判定一覧
        ws_issues = wb.create_sheet(title="判定一覧")
        self._build_rules_sheet(ws_issues, records, results)

        # 3. 解析詳細 (Parser Debug Mode)
        ws_trace = wb.create_sheet(title="解析詳細")
        self._build_traces_sheet(ws_trace, records, results)

        # 4. 原文 (Raw instructions)
        ws_raw = wb.create_sheet(title="原文")
        self._build_raw_sheet(ws_raw, records, results)

        if progress_callback:
            progress_callback("Excel書き込み中 (サマリー・教材詳細)", 65)
        # 5. サマリー (KPI & Summary)
        ws_summary = wb.create_sheet(title="サマリー")
        self._build_summary_sheet(ws_summary, records, results, exclusion_stats)

        # 6. 未知表記 (Alias improvement)
        ws_unknown = wb.create_sheet(title="未知表記")
        self._build_unknown_headings_sheet(ws_unknown, records, results)

        # 7. 教材詳細 (Textbook Itemized Breakdown)
        ws_textbooks = wb.create_sheet(title="教材詳細")
        self._build_textbooks_sheet(ws_textbooks, records, results)

        if progress_callback:
            progress_callback("Excel保存中", 85)

        # 一時ファイルへ保存 (v9 §43.1)
        base_d = os.path.dirname(filepath)
        orig_name = os.path.basename(filepath)
        name_root, ext = os.path.splitext(orig_name)
        tmp_filepath = os.path.join(
            base_d,
            f"~tmp_{name_root}_{os.getpid()}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
        )

        try:
            wb.save(tmp_filepath)
        except Exception as e:
            logger.error("Excel一時ファイルへの保存に失敗: %s", e)
            if os.path.exists(tmp_filepath):
                try:
                    os.remove(tmp_filepath)
                except Exception:
                    pass
            raise

        # 保存後検証 (v9 §43.3)
        self._verify_exported_excel(tmp_filepath)

        # 最終ファイルへのアトミック置換 / ロック検知時の別名保存 (v8 §16, v9 §43.1)
        self.was_renamed = False
        saved_filepath = filepath
        try:
            os.replace(tmp_filepath, filepath)
        except (PermissionError, OSError) as e:
            logger.warning("既存Excelファイルへの置換に失敗 (ロックの可能性): %s。別名で保存を試行します。", e)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            saved_filepath = os.path.join(base_d, f"{name_root}_{ts}{ext}")
            try:
                os.replace(tmp_filepath, saved_filepath)
            except Exception:
                wb.save(saved_filepath)
                if os.path.exists(tmp_filepath):
                    try:
                        os.remove(tmp_filepath)
                    except Exception:
                        pass
            self.was_renamed = True
            logger.info("別名でExcelを保存しました: %s", saved_filepath)
        finally:
            if os.path.exists(tmp_filepath):
                try:
                    os.remove(tmp_filepath)
                except Exception:
                    pass

        if not os.path.exists(saved_filepath) or os.path.getsize(saved_filepath) == 0:
            raise RuntimeError(f"保存されたExcelファイルが存在しないか空です: {saved_filepath}")

        if progress_callback:
            progress_callback("Excel出力完了", 100)

        return saved_filepath

    def _verify_exported_excel(self, file_path: str) -> None:
        """保存後検証 (v9 §43.3)。
        ファイル存在、サイズ、および必要7シートの存在を検証する。
        """
        if not os.path.exists(file_path):
            raise RuntimeError(f"一時Excelファイルが存在しません: {file_path}")
        if os.path.getsize(file_path) < 1000:
            raise RuntimeError(f"一時Excelファイルのサイズが不正です ({os.path.getsize(file_path)} bytes)")

        required_sheets = {"チェック結果", "判定一覧", "解析詳細", "原文", "サマリー", "未知表記", "教材詳細"}
        try:
            wb_check = openpyxl.load_workbook(file_path, read_only=True)
            sheet_names = set(wb_check.sheetnames)
            wb_check.close()
            missing = required_sheets - sheet_names
            if missing:
                raise RuntimeError(f"Excel出力の必須シートが不足しています: {missing}")
        except Exception as e:
            raise RuntimeError(f"Excel出力ファイルの整合性検証に失敗しました: {e}") from e

    def _build_check_results_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
    ) -> None:
        """チェック結果シートを構築する (v7 §16: 18列、教室名・教室コード・年度追加、INFO色分け)"""
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        headers = [
            "教室名", "教室コード", "年度", "学籍番号", "生徒名", "学年", "受講区分", "科目", "判定", "修正項目",
            "エラー", "警告", "作成者", "志望校", "教材", "進め方",
            "生徒情報", "小テスト", "宿題", "未分類テキスト"
        ]
        ws.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.align_center
            cell.border = self.thin_border

        row_num = 1
        for rec, res in zip(records, results):
            row_num += 1

            fix_fields_str = "\n".join(res.fix_fields)
            if res.reasons:
                err_msgs_list = list(res.reasons)
            else:
                err_msgs_list = [RULE_MESSAGES.get(e, e) for e in res.errors]
                for rev in res.reviews:
                    err_msgs_list.append(f"[確認] {RULE_MESSAGES.get(rev, rev)}")
            error_msgs = "\n".join(err_msgs_list)
            warn_msgs = "\n".join(RULE_MESSAGES.get(w, w) for w in res.warnings)

            plan_formatted = format_sentence_newlines(res.parsed_sections.get("進め方", ""))
            info_formatted = format_sentence_newlines(res.parsed_sections.get("生徒情報", ""))
            unclassified_formatted = format_sentence_newlines(res.unclassified_text)

            row_values = [
                sanitize_excel_value(rec.classroom_name),
                sanitize_excel_value(rec.classroom_code),
                sanitize_excel_value(rec.school_year),
                sanitize_excel_value(rec.student_id),
                sanitize_excel_value(rec.student_name),
                sanitize_excel_value(rec.grade),
                sanitize_excel_value(rec.division),
                sanitize_excel_value(rec.subject),
                res.severity.value,
                fix_fields_str,
                error_msgs,
                warn_msgs,
                sanitize_excel_value(res.parsed_sections.get("作成者", "")),
                sanitize_excel_value(res.parsed_sections.get("志望校", "")),
                sanitize_excel_value(res.parsed_sections.get("教材", "")),
                sanitize_excel_value(plan_formatted),
                sanitize_excel_value(info_formatted),
                sanitize_excel_value(res.parsed_sections.get("小テスト", "")),
                sanitize_excel_value(res.parsed_sections.get("宿題", "")),
                sanitize_excel_value(unclassified_formatted),
            ]

            ws.append(row_values)

            # 行の色分け (v7 §16)
            if res.severity == Severity.CRITICAL:
                row_fill = self.fill_critical
                cell_font = self.critical_font
            elif res.severity == Severity.ERROR:
                row_fill = self.fill_error
                cell_font = self.body_font
            elif res.severity == Severity.REVIEW:
                row_fill = self.fill_review
                cell_font = self.body_font
            elif res.severity == Severity.WARNING:
                row_fill = self.fill_warning
                cell_font = self.body_font
            elif res.severity == Severity.INFO:
                row_fill = self.fill_info
                cell_font = self.body_font
            else:
                row_fill = self.fill_pass
                cell_font = self.body_font

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_num, column=col_idx)
                cell.font = cell_font
                cell.fill = row_fill
                cell.border = self.thin_border
                if col_idx in [1, 2, 3, 4, 6, 7, 8, 9]:
                    cell.alignment = self.align_center
                else:
                    cell.alignment = self.align_left

        if row_num > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{row_num}"

        self._adjust_column_widths(ws, min_width=10, max_width=50)

    def _build_rules_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
    ) -> None:
        """判定一覧シートを構築する (§28)"""
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        headers = ["判定", "Rule ID", "対象項目", "発生条件", "表示メッセージ", "修正方法", "件数", "発生率"]
        ws.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.align_center
            cell.border = self.thin_border

        # ルール別件数集計
        rule_counter = Counter()
        for res in results:
            for err in res.errors:
                rule_counter[err] += 1
            for rev in res.reviews:
                rule_counter[rev] += 1
            for warn in res.warnings:
                rule_counter[warn] += 1
            if res.severity == Severity.INFO:
                rule_counter[INFO_UNCLASSIFIED_TEXT] += 1

        total_records = len(records)
        row_num = 1

        all_rules = [r for r in RULE_ORDER]
        for extra in rule_counter:
            if extra not in all_rules:
                all_rules.append(extra)

        from core.evaluator import SECTION_FIELD_MAP

        for rule_id in all_rules:
            cnt = rule_counter[rule_id]
            pct = (cnt / total_records * 100) if total_records > 0 else 0.0

            if rule_id.startswith("CRIT_"):
                sev_label = "CRITICAL"
                row_fill = self.fill_critical
            elif rule_id.startswith("ERR_"):
                sev_label = "ERROR"
                row_fill = self.fill_error
            elif rule_id.startswith("REV_"):
                sev_label = "REVIEW"
                row_fill = self.fill_review
            elif rule_id.startswith("INFO_"):
                sev_label = "INFO"
                row_fill = self.fill_info
            else:
                sev_label = "WARNING"
                row_fill = self.fill_warning

            field_name = SECTION_FIELD_MAP.get(rule_id, "その他")
            condition = RULE_CONDITIONS.get(rule_id, "-")
            msg = RULE_MESSAGES.get(rule_id, rule_id)
            fix_sug = RULE_FIX_SUGGESTIONS.get(rule_id, "-")

            row_num += 1
            row_values = [
                sev_label,
                rule_id,
                field_name,
                condition,
                msg,
                fix_sug,
                cnt,
                f"{pct:.1f}%",
            ]
            ws.append(row_values)

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_num, column=col_idx)
                cell.font = self.body_font
                cell.fill = row_fill
                cell.border = self.thin_border
                if col_idx in [1, 2, 3]:
                    cell.alignment = self.align_center
                elif col_idx in [7, 8]:
                    cell.alignment = self.align_right
                else:
                    cell.alignment = self.align_left

        if row_num > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{row_num}"

        self._adjust_column_widths(ws, min_width=12, max_width=45)

    def _build_traces_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
    ) -> None:
        """解析詳細シートを構築する (v10 §6.3: 10列)"""
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        headers = ["学籍番号", "生徒名", "学年", "行番号", "原文行", "検出見出し", "正規化見出し", "割当セクション", "信頼度", "本文"]
        ws.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.align_center
            cell.border = self.thin_border

        row_num = 1
        for rec, res in zip(records, results):
            for trace in res.parse_traces:
                row_num += 1
                row_values = [
                    sanitize_excel_value(rec.student_id),
                    sanitize_excel_value(rec.student_name),
                    sanitize_excel_value(rec.grade),
                    trace.get("line", ""),
                    sanitize_excel_value(trace.get("raw", "")),
                    sanitize_excel_value(trace.get("heading", "")),
                    sanitize_excel_value(trace.get("normalized", "")),
                    sanitize_excel_value(trace.get("section", "")),
                    trace.get("confidence", "-"),
                    sanitize_excel_value(trace.get("body", "")),
                ]
                ws.append(row_values)

                for col_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=row_num, column=col_idx)
                    cell.font = self.body_font
                    cell.border = self.thin_border
                    if col_idx in [1, 3, 4, 6, 7, 8, 9]:
                        cell.alignment = self.align_center
                    else:
                        cell.alignment = self.align_left

        if row_num > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{row_num}"

        fixed_widths = {
            "A": 14,  # 学籍番号
            "B": 16,  # 生徒名
            "C": 10,  # 学年
            "D": 8,   # 行番号
            "E": 40,  # 原文行
            "F": 16,  # 検出見出し
            "G": 16,  # 正規化見出し
            "H": 16,  # 割当セクション
            "I": 10,  # 信頼度
            "J": 50,  # 本文
        }
        for col_let, w in fixed_widths.items():
            ws.column_dimensions[col_let].width = w

    def _build_raw_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
    ) -> None:
        """原文一覧シートを構築する (v10 §6.2: 10列 教室名・教室コード・年度・学籍番号・生徒名・学年・受講区分・科目・判定・原文備考欄)"""
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        headers = ["教室名", "教室コード", "年度", "学籍番号", "生徒名", "学年", "受講区分", "科目", "判定", "原文備考欄"]
        ws.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.align_center
            cell.border = self.thin_border

        row_num = 1
        for rec, res in zip(records, results):
            row_num += 1
            row_values = [
                sanitize_excel_value(rec.classroom_name),
                sanitize_excel_value(rec.classroom_code),
                sanitize_excel_value(rec.school_year),
                sanitize_excel_value(rec.student_id),
                sanitize_excel_value(rec.student_name),
                sanitize_excel_value(rec.grade),
                sanitize_excel_value(rec.division),
                sanitize_excel_value(rec.subject),
                res.severity.value,
                sanitize_excel_value(rec.raw_instruction or ""),
            ]
            ws.append(row_values)

            if res.severity == Severity.CRITICAL:
                row_fill = self.fill_critical
            elif res.severity == Severity.ERROR:
                row_fill = self.fill_error
            elif res.severity == Severity.REVIEW:
                row_fill = self.fill_review
            elif res.severity == Severity.WARNING:
                row_fill = self.fill_warning
            elif res.severity == Severity.INFO:
                row_fill = self.fill_info
            else:
                row_fill = self.fill_pass

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_num, column=col_idx)
                cell.font = self.body_font
                cell.fill = row_fill
                cell.border = self.thin_border
                if col_idx in [1, 2, 3, 4, 6, 7, 8, 9]:
                    cell.alignment = self.align_center
                else:
                    cell.alignment = self.align_left

        if row_num > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{row_num}"

        fixed_widths = {
            "A": 14,  # 教室名
            "B": 12,  # 教室コード
            "C": 10,  # 年度
            "D": 14,  # 学籍番号
            "E": 16,  # 生徒名
            "F": 10,  # 学年
            "G": 12,  # 受講区分
            "H": 14,  # 科目
            "I": 12,  # 判定
            "J": 80,  # 原文備考欄
        }
        for col_let, w in fixed_widths.items():
            ws.column_dimensions[col_let].width = w

    def _build_summary_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
        exclusion_stats: Optional[ExclusionStats] = None,
    ) -> None:
        """サマリー (KPI & 各種集計) シートを構築する (§30)"""
        ws.views.sheetView[0].showGridLines = True

        total_count = len(records)
        critical_count = sum(1 for r in results if r.severity == Severity.CRITICAL)
        error_count = sum(1 for r in results if r.severity == Severity.ERROR)
        review_count = sum(1 for r in results if r.severity == Severity.REVIEW)
        warning_count = sum(1 for r in results if r.severity == Severity.WARNING)
        info_count = sum(1 for r in results if r.severity == Severity.INFO)
        pass_count = sum(1 for r in results if r.severity == Severity.PASS)

        critical_pct = (critical_count / total_count * 100) if total_count > 0 else 0.0
        error_pct = (error_count / total_count * 100) if total_count > 0 else 0.0
        review_pct = (review_count / total_count * 100) if total_count > 0 else 0.0
        warning_pct = (warning_count / total_count * 100) if total_count > 0 else 0.0
        info_pct = (info_count / total_count * 100) if total_count > 0 else 0.0
        pass_pct = (pass_count / total_count * 100) if total_count > 0 else 0.0

        ws.cell(row=2, column=2, value="Curriculum Analyzer 精査集計サマリー").font = self.title_font
        ws.cell(row=3, column=2, value=f"集計日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}").font = self.body_font

        curr_row = 5

        # 0. 除外統計 (Exclusion Stats) (§4, §30)
        if exclusion_stats:
            ws.cell(row=curr_row, column=2, value="【集計対象除外統計】").font = self.subtitle_font
            curr_row += 1
            ex_headers = ["区分", "件数", "比率"]
            for c_idx, h in enumerate(ex_headers, start=2):
                c = ws.cell(row=curr_row, column=c_idx, value=h)
                c.font = self.header_font
                c.fill = self.header_fill
                c.alignment = self.align_center
                c.border = self.thin_border

            curr_row += 1
            tot_html = exclusion_stats.total_html_records
            ex_rows = [
                ("HTML取得件数", tot_html, "100.0%"),
                ("集計対象件数", exclusion_stats.target_records, f"{(exclusion_stats.target_records / tot_html * 100):.1f}%" if tot_html > 0 else "0.0%"),
                ("総除外件数", exclusion_stats.total_excluded, f"{(exclusion_stats.total_excluded / tot_html * 100):.1f}%" if tot_html > 0 else "0.0%"),
                ("  - デモ除外", exclusion_stats.demo_excluded, f"{(exclusion_stats.demo_excluded / tot_html * 100):.1f}%" if tot_html > 0 else "0.0%"),
                ("  - 退塾除外", exclusion_stats.withdrawn_excluded, f"{(exclusion_stats.withdrawn_excluded / tot_html * 100):.1f}%" if tot_html > 0 else "0.0%"),
                ("  - 見送り除外", exclusion_stats.declined_excluded, f"{(exclusion_stats.declined_excluded / tot_html * 100):.1f}%" if tot_html > 0 else "0.0%"),
            ]
            for label, cnt, pct in ex_rows:
                c1 = ws.cell(row=curr_row, column=2, value=label)
                c2 = ws.cell(row=curr_row, column=3, value=cnt)
                c3 = ws.cell(row=curr_row, column=4, value=pct)
                for c in [c1, c2, c3]:
                    c.font = self.body_bold_font if label in ["HTML取得件数", "集計対象件数", "総除外件数"] else self.body_font
                    c.border = self.thin_border
                c1.alignment = self.align_left
                c2.alignment = self.align_right
                c3.alignment = self.align_right
                curr_row += 1
            curr_row += 1

        # 1. KPIテーブル (v7 §20)
        ws.cell(row=curr_row, column=2, value="【全体判定ステータス】").font = self.subtitle_font
        curr_row += 1
        kpi_headers = ["判定ランク", "件数", "比率"]
        for c_idx, h in enumerate(kpi_headers, start=2):
            c = ws.cell(row=curr_row, column=c_idx, value=h)
            c.font = self.header_font
            c.fill = self.header_fill
            c.alignment = self.align_center
            c.border = self.thin_border

        kpi_rows = [
            ("重大 (CRITICAL)", critical_count, f"{critical_pct:.1f}%", self.fill_critical),
            ("要修正 (ERROR)", error_count, f"{error_pct:.1f}%", self.fill_error),
            ("要確認 (REVIEW)", review_count, f"{review_pct:.1f}%", self.fill_review),
            ("確認推奨 (WARNING)", warning_count, f"{warning_pct:.1f}%", self.fill_warning),
            ("情報 (INFO)", info_count, f"{info_pct:.1f}%", self.fill_info),
            ("合格 (PASS)", pass_count, f"{pass_pct:.1f}%", self.fill_pass),
            ("集計対象レコード数", total_count, "100.0%", None),
        ]

        curr_row += 1
        for label, cnt, pct, fill in kpi_rows:
            c1 = ws.cell(row=curr_row, column=2, value=label)
            c2 = ws.cell(row=curr_row, column=3, value=cnt)
            c3 = ws.cell(row=curr_row, column=4, value=pct)
            for c in [c1, c2, c3]:
                c.font = self.body_bold_font if label == "集計対象レコード数" else self.body_font
                c.border = self.thin_border
                if fill:
                    c.fill = fill
            c1.alignment = self.align_left
            c2.alignment = self.align_right
            c3.alignment = self.align_right
            curr_row += 1

        # 2. 教室別集計マトリックス (v7 §20: 列=教室名、行=項目名、右端=全体)
        curr_row += 1
        ws.cell(row=curr_row, column=2, value="【教室別集計マトリックス】").font = self.subtitle_font
        curr_row += 1

        def _get_classroom_label(rec: CurriculumRecord) -> str:
            return rec.classroom_name if rec.classroom_name else "（未取得）"

        unique_classrooms = sorted(list({_get_classroom_label(r) for r in records}))
        matrix_headers = ["項目名"] + unique_classrooms + ["全体"]
        for c_idx, h in enumerate(matrix_headers, start=2):
            c = ws.cell(row=curr_row, column=c_idx, value=h)
            c.font = self.header_font
            c.fill = self.header_fill
            c.alignment = self.align_center
            c.border = self.thin_border

        curr_row += 1

        cls_stats = defaultdict(lambda: {
            "total": 0, "critical": 0, "error": 0, "review": 0, "warning": 0, "info": 0, "pass": 0,
            "author_err": 0, "school_err": 0, "textbook_err": 0, "tb_status_err": 0,
            "plan_err": 0, "info_err": 0, "test_err": 0, "hw_err": 0,
            "course_err": 0, "goal_warn": 0, "unclass": 0
        })
        for rec, res in zip(records, results):
            c_label = _get_classroom_label(rec)
            st = cls_stats[c_label]
            st["total"] += 1
            if res.severity == Severity.CRITICAL:
                st["critical"] += 1
            elif res.severity == Severity.ERROR:
                st["error"] += 1
            elif res.severity == Severity.REVIEW:
                st["review"] += 1
            elif res.severity == Severity.WARNING:
                st["warning"] += 1
            elif res.severity == Severity.INFO:
                st["info"] += 1
            else:
                st["pass"] += 1

            all_errs = res.errors + res.reviews
            if ERR_AUTHOR_MISSING in all_errs:
                st["author_err"] += 1
            if any(e in all_errs for e in (ERR_SCHOOL_REQUIRED_HIGH3, ERR_SCHOOL_REQUIRED_JUNIOR3, ERR_SCHOOL_REQUIRED_ELEM6, REV_SCHOOL_UNCERTAIN)):
                st["school_err"] += 1
            if ERR_TEXTBOOK_MISSING in all_errs:
                st["textbook_err"] += 1
            if ERR_TEXTBOOK_STATUS_MISSING in all_errs or WARN_TEXTBOOK_NO_STATUS in res.warnings:
                st["tb_status_err"] += 1
            if ERR_PLAN_MISSING in all_errs or ERR_PLAN_TOO_SHORT in all_errs:
                st["plan_err"] += 1
            if ERR_INFO_MISSING in all_errs or ERR_INFO_TOO_SHORT in all_errs:
                st["info_err"] += 1
            if ERR_TEST_MISSING in all_errs:
                st["test_err"] += 1
            if ERR_HOMEWORK_MISSING in all_errs:
                st["hw_err"] += 1
            if ERR_COURSE_COUNT_MISSING in all_errs:
                st["course_err"] += 1
            if WARN_GOAL_MISSING in res.warnings:
                st["goal_warn"] += 1
            if res.unclassified_count > 0 or res.unclassified_text.strip():
                st["unclass"] += 1

        tot_author = sum(cls_stats[c]["author_err"] for c in unique_classrooms)
        tot_school = sum(cls_stats[c]["school_err"] for c in unique_classrooms)
        tot_textbook = sum(cls_stats[c]["textbook_err"] for c in unique_classrooms)
        tot_tb_status = sum(cls_stats[c]["tb_status_err"] for c in unique_classrooms)
        tot_plan = sum(cls_stats[c]["plan_err"] for c in unique_classrooms)
        tot_info = sum(cls_stats[c]["info_err"] for c in unique_classrooms)
        tot_test = sum(cls_stats[c]["test_err"] for c in unique_classrooms)
        tot_hw = sum(cls_stats[c]["hw_err"] for c in unique_classrooms)
        tot_course = sum(cls_stats[c]["course_err"] for c in unique_classrooms)
        tot_goal = sum(cls_stats[c]["goal_warn"] for c in unique_classrooms)
        tot_unclass = sum(cls_stats[c]["unclass"] for c in unique_classrooms)

        matrix_rows = [
            ("対象件数", [cls_stats[c]["total"] for c in unique_classrooms], total_count, None, False),
            ("CRITICAL", [cls_stats[c]["critical"] for c in unique_classrooms], critical_count, self.fill_critical, True),
            ("ERROR", [cls_stats[c]["error"] for c in unique_classrooms], error_count, self.fill_error, False),
            ("REVIEW", [cls_stats[c]["review"] for c in unique_classrooms], review_count, self.fill_review, False),
            ("WARNING", [cls_stats[c]["warning"] for c in unique_classrooms], warning_count, self.fill_warning, False),
            ("INFO", [cls_stats[c]["info"] for c in unique_classrooms], info_count, self.fill_info, False),
            ("PASS", [cls_stats[c]["pass"] for c in unique_classrooms], pass_count, self.fill_pass, False),
            (
                "合格率",
                [f"{(cls_stats[c]['pass'] / cls_stats[c]['total'] * 100):.1f}%" if cls_stats[c]["total"] > 0 else "0.0%" for c in unique_classrooms],
                f"{pass_pct:.1f}%",
                None,
                False,
            ),
            ("作成者", [cls_stats[c]["author_err"] for c in unique_classrooms], tot_author, None, False),
            ("志望校", [cls_stats[c]["school_err"] for c in unique_classrooms], tot_school, None, False),
            ("教材", [cls_stats[c]["textbook_err"] for c in unique_classrooms], tot_textbook, None, False),
            ("教材ステータス", [cls_stats[c]["tb_status_err"] for c in unique_classrooms], tot_tb_status, None, False),
            ("進め方", [cls_stats[c]["plan_err"] for c in unique_classrooms], tot_plan, None, False),
            ("生徒情報", [cls_stats[c]["info_err"] for c in unique_classrooms], tot_info, None, False),
            ("小テスト", [cls_stats[c]["test_err"] for c in unique_classrooms], tot_test, None, False),
            ("宿題", [cls_stats[c]["hw_err"] for c in unique_classrooms], tot_hw, None, False),
            ("講座数", [cls_stats[c]["course_err"] for c in unique_classrooms], tot_course, None, False),
            ("目標", [cls_stats[c]["goal_warn"] for c in unique_classrooms], tot_goal, None, False),
            ("未分類テキストあり", [cls_stats[c]["unclass"] for c in unique_classrooms], tot_unclass, None, False),
        ]

        for item_name, vals, tot_val, fill, is_crit in matrix_rows:
            c_label = ws.cell(row=curr_row, column=2, value=item_name)
            c_label.font = self.critical_font if is_crit else (self.body_bold_font if item_name in ["レコード数", "合格率"] else self.body_font)
            c_label.alignment = self.align_left
            c_label.border = self.thin_border
            if fill:
                c_label.fill = fill

            for idx, v in enumerate(vals, start=3):
                c = ws.cell(row=curr_row, column=idx, value=v)
                c.font = self.critical_font if is_crit else (self.body_bold_font if item_name in ["レコード数", "合格率"] else self.body_font)
                c.alignment = self.align_right
                c.border = self.thin_border
                if fill:
                    c.fill = fill

            # 全体列 (右端)
            tot_col_idx = 3 + len(vals)
            c_tot = ws.cell(row=curr_row, column=tot_col_idx, value=tot_val)
            c_tot.font = self.critical_font if is_crit else self.body_bold_font
            c_tot.alignment = self.align_right
            c_tot.border = self.thin_border
            if fill:
                c_tot.fill = fill

            curr_row += 1

        # 3. 修正項目別集計
        curr_row += 1
        ws.cell(row=curr_row, column=2, value="【修正項目別件数】").font = self.subtitle_font
        curr_row += 1
        field_headers = ["修正項目", "要修正件数", "比率"]
        for c_idx, h in enumerate(field_headers, start=2):
            c = ws.cell(row=curr_row, column=c_idx, value=h)
            c.font = self.header_font
            c.fill = self.header_fill
            c.alignment = self.align_center
            c.border = self.thin_border

        curr_row += 1
        field_counter = Counter()
        for r in results:
            for f in r.fix_fields:
                field_counter[f] += 1

        for f_name, cnt in field_counter.most_common():
            pct = (cnt / total_count * 100) if total_count > 0 else 0.0
            c1 = ws.cell(row=curr_row, column=2, value=f_name)
            c2 = ws.cell(row=curr_row, column=3, value=cnt)
            c3 = ws.cell(row=curr_row, column=4, value=f"{pct:.1f}%")
            for c in [c1, c2, c3]:
                c.font = self.body_font
                c.border = self.thin_border
            c1.alignment = self.align_left
            c2.alignment = self.align_right
            c3.alignment = self.align_right
            curr_row += 1

        # 4. 作成者別集計 (v7 §20: 情報列追加)
        curr_row += 1
        ws.cell(row=curr_row, column=2, value="【作成者別集計】").font = self.subtitle_font
        curr_row += 1
        author_headers = ["作成者", "総件数", "重大", "要修正", "要確認", "警告", "情報", "合格率"]
        for c_idx, h in enumerate(author_headers, start=2):
            c = ws.cell(row=curr_row, column=c_idx, value=h)
            c.font = self.header_font
            c.fill = self.header_fill
            c.alignment = self.align_center
            c.border = self.thin_border

        curr_row += 1
        author_stats = defaultdict(lambda: {"total": 0, "critical": 0, "error": 0, "review": 0, "warning": 0, "info": 0, "pass": 0})
        for res in results:
            author = res.parsed_sections.get("作成者", "（未記載）") or "（未記載）"
            st = author_stats[author]
            st["total"] += 1
            if res.severity == Severity.CRITICAL:
                st["critical"] += 1
            elif res.severity == Severity.ERROR:
                st["error"] += 1
            elif res.severity == Severity.REVIEW:
                st["review"] += 1
            elif res.severity == Severity.WARNING:
                st["warning"] += 1
            elif res.severity == Severity.INFO:
                st["info"] += 1
            else:
                st["pass"] += 1

        for author, st in sorted(author_stats.items(), key=lambda x: x[1]["total"], reverse=True):
            tot = st["total"]
            pass_rt = (st["pass"] / tot * 100) if tot > 0 else 0.0
            c1 = ws.cell(row=curr_row, column=2, value=author)
            c2 = ws.cell(row=curr_row, column=3, value=tot)
            c3 = ws.cell(row=curr_row, column=4, value=st["critical"])
            c4 = ws.cell(row=curr_row, column=5, value=st["error"])
            c5 = ws.cell(row=curr_row, column=6, value=st["review"])
            c6 = ws.cell(row=curr_row, column=7, value=st["warning"])
            c7 = ws.cell(row=curr_row, column=8, value=st["info"])
            c8 = ws.cell(row=curr_row, column=9, value=f"{pass_rt:.1f}%")

            for c in [c1, c2, c3, c4, c5, c6, c7, c8]:
                c.font = self.body_font
                c.border = self.thin_border

            c1.alignment = self.align_left
            c2.alignment = self.align_right
            c3.alignment = self.align_right
            c4.alignment = self.align_right
            c5.alignment = self.align_right
            c6.alignment = self.align_right
            c7.alignment = self.align_right
            c8.alignment = self.align_right
            curr_row += 1

        self._adjust_column_widths(ws, min_width=12, max_width=45)

    def _build_unknown_headings_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
    ) -> None:
        """未知表記シートを構築する (§31: [元表記, 出現件数, 推定分類, 現在の分類, 採用候補, 採用後のalias, 備考])"""
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        headers = ["元表記", "出現件数", "推定分類", "現在の分類", "採用候補", "採用後のalias", "備考"]
        ws.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.align_center
            cell.border = self.thin_border

        # 集計
        heading_counts = Counter()
        heading_estimates = {}
        heading_current_types = {}
        heading_samples = {}

        for rec, res in zip(records, results):
            for item in res.unclassified_items:
                if item.item_type in (UnclassifiedType.UNKNOWN_HEADING, UnclassifiedType.PARSER_CANDIDATE):
                    h = item.candidate_heading
                    if h:
                        heading_counts[h] += 1
                        if item.estimated_section and h not in heading_estimates:
                            heading_estimates[h] = item.estimated_section
                        if h not in heading_current_types:
                            heading_current_types[h] = "パーサー候補" if item.item_type == UnclassifiedType.PARSER_CANDIDATE else "未知見出し"
                        if h not in heading_samples:
                            heading_samples[h] = rec.student_id

        row_num = 1
        for heading, cnt in heading_counts.most_common():
            row_num += 1
            est = heading_estimates.get(heading, "（未推定）")
            cur_type = heading_current_types.get(heading, "未知見出し")
            candidate_status = "○ (推奨)" if est != "（未推定）" else "要確認"
            after_alias = f"{est} ({heading})" if est != "（未推定）" else "-"
            sample_id = heading_samples.get(heading, "-")

            row_values = [
                sanitize_excel_value(heading),
                cnt,
                est,
                cur_type,
                candidate_status,
                after_alias,
                f"学籍番号: {sample_id}",
            ]
            ws.append(row_values)

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_num, column=col_idx)
                cell.font = self.body_font
                cell.border = self.thin_border
                if col_idx in [2, 4, 5]:
                    cell.alignment = self.align_center
                else:
                    cell.alignment = self.align_left

        if row_num > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{row_num}"

        self._adjust_column_widths(ws, min_width=12, max_width=45)

    def _build_textbooks_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        records: List[CurriculumRecord],
        results: List[EvaluationResult],
    ) -> None:
        """教材詳細シートを構築する (v10 §6.4: 13列 [学籍番号, 生徒名, 学年, 受講区分, 科目, 教室名, 教室コード, 年度, 教材, ステータス, ステータス分類, 判定, 補足])"""
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        headers = [
            "学籍番号", "生徒名", "学年", "受講区分", "科目", "教室名", "教室コード", "年度",
            "教材", "ステータス", "ステータス分類", "判定", "補足"
        ]
        ws.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.align_center
            cell.border = self.thin_border

        row_num = 1
        for rec, res in zip(records, results):
            for tb in res.textbook_items:
                row_num += 1
                if tb.supplementary:
                    judge_str = "補足"
                    row_fill = self.fill_pass
                else:
                    judge_str = "OK" if tb.is_valid else "ERROR"
                    row_fill = self.fill_pass if tb.is_valid else self.fill_error

                row_values = [
                    sanitize_excel_value(rec.student_id),
                    sanitize_excel_value(rec.student_name),
                    sanitize_excel_value(rec.grade),
                    sanitize_excel_value(rec.division),
                    sanitize_excel_value(rec.subject),
                    sanitize_excel_value(rec.classroom_name),
                    sanitize_excel_value(rec.classroom_code),
                    sanitize_excel_value(rec.school_year),
                    sanitize_excel_value(tb.name),
                    sanitize_excel_value(tb.raw_status),
                    tb.category,
                    judge_str,
                    sanitize_excel_value(tb.supplementary),
                ]
                ws.append(row_values)

                for col_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=row_num, column=col_idx)
                    cell.font = self.body_font
                    cell.fill = row_fill
                    cell.border = self.thin_border
                    if col_idx in [1, 3, 4, 5, 6, 7, 8, 10, 11, 12]:
                        cell.alignment = self.align_center
                    else:
                        cell.alignment = self.align_left

        if row_num > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{row_num}"

        self._adjust_column_widths(ws, min_width=12, max_width=50)

    def _adjust_column_widths(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        min_width: int = 10,
        max_width: int = 50,
        max_sample_rows: int = 100,
    ) -> None:
        """各カラムの幅を内容に合わせて高速自動調整する (最大100行サンプリング、80文字キャップ)"""
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            sample_cells = col[:max_sample_rows]
            for cell in sample_cells:
                val = str(cell.value or "")
                lines = val.split("\n")
                cell_max = max(self._calc_string_width(line[:80]) for line in lines) if lines else 0
                if cell_max > max_len:
                    max_len = cell_max
            adjusted_width = max(min_width, min(max_len + 3, max_width))
            ws.column_dimensions[col_letter].width = adjusted_width

    @staticmethod
    def _calc_string_width(s: str) -> int:
        """全角文字を幅2、半角文字を幅1として計算する"""
        import unicodedata
        w = 0
        for ch in s:
            if unicodedata.east_asian_width(ch) in ('F', 'W', 'A'):
                w += 2
            else:
                w += 1
        return w
