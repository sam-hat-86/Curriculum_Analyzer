"""
Excel 5シート出力エンジン (仕様書§18, §20, §21, §24, §25, §26)
"""
import json
from typing import Dict, List, Any, Optional, Set
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from src.database.repository import Repository
from src.models.state import TimingCategory
from src.utils.normalization import parse_date, is_demo_student
from src.utils.constants import (
    SHEET_SUMMARY_RESULT,
    SHEET_PROGRESS,
    SHEET_UNIT_DETAILS,
    SHEET_INSTRUCTION,
    SHEET_SUMMARY,
    SHEET_RAW,
    COLUMNS_SUMMARY_RESULT,
    COLUMNS_PROGRESS,
    COLUMNS_UNIT_DETAILS,
    COLUMNS_INSTRUCTION,
    COLUMNS_SUMMARY,
    COLUMNS_RAW,
    DEFAULT_EMPTY_VALUE,
)

# スタイル定義
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid") # 濃紺
HEADER_FONT = Font(name="Yu Gothic UI", size=10, bold=True, color="FFFFFF")
DATA_FONT = Font(name="Yu Gothic UI", size=10)
BORDER_THIN = Side(border_style="thin", color="D9D9D9")
CELL_BORDER = Border(left=BORDER_THIN, right=BORDER_THIN, top=BORDER_THIN, bottom=BORDER_THIN)
ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_LEFT = Alignment(horizontal="left", vertical="center")
ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")
ALIGN_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)

# アラート・ステータス用スタイル
ALERT_FILL_RED = PatternFill(start_color="FFD8D8", end_color="FFD8D8", fill_type="solid") # 薄赤
ALERT_FONT_RED = Font(name="Yu Gothic UI", size=10, bold=True, color="9C0006") # 濃赤太字
ALERT_FILL_YELLOW = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid") # 薄黄
ALERT_FONT_YELLOW = Font(name="Yu Gothic UI", size=10, bold=True, color="B25E00") # 濃茶
ALERT_FILL_GREEN = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid") # 薄緑
ALERT_FONT_GREEN = Font(name="Yu Gothic UI", size=10, color="276A3C") # 濃緑
ZEBRA_FILL = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid") # 極薄グレー

class ExcelExporter:
    def __init__(self, repository: Repository, include_raw_sheet: bool = False):
        self.repo = repository
        self.include_raw_sheet = include_raw_sheet

    def generate_workbook(self, include_raw_sheet: Optional[bool] = None) -> openpyxl.Workbook:
        """データベースから全データを取得し、集計結果＋各分析シートを持つWorkbookを構築"""
        use_raw = self.include_raw_sheet if include_raw_sheet is None else include_raw_sheet
        wb = openpyxl.Workbook()
        # デフォルトシートを集計結果シートに設定
        ws_res = wb.active
        assert ws_res is not None
        ws_res.title = SHEET_SUMMARY_RESULT
        
        ws_prog = wb.create_sheet(title=SHEET_PROGRESS)
        ws_unit = wb.create_sheet(title=SHEET_UNIT_DETAILS)
        ws_inst = wb.create_sheet(title=SHEET_INSTRUCTION)
        ws_sum = wb.create_sheet(title=SHEET_SUMMARY)

        # 0. 集計結果シート（要対応科目のみ抽出）
        self._write_summary_result_sheet(ws_res)

        # 1. 進捗率シート
        self._write_progress_sheet(ws_prog)

        # 2. 単元詳細シート
        self._write_unit_details_sheet(ws_unit)

        # 3. 備考欄シート
        self._write_instruction_sheet(ws_inst)

        # 4. サマリーシート
        self._write_summary_sheet(ws_sum)

        # 5. 原文シート (オプション指定時のみ)
        if use_raw:
            ws_raw = wb.create_sheet(title=SHEET_RAW)
            self._write_raw_sheet(ws_raw)

        return wb

    def _write_summary_result_sheet(self, ws):
        """[集計結果]シート出力 (全6列: 教室名, 生徒名, 科目名, 進捗遅れ, 備考欄スコア, 備考欄詳細) - 要対応のみ抽出"""
        self._apply_header_style(ws, COLUMNS_SUMMARY_RESULT)
        col_widths = {i: len(str(c)) for i, c in enumerate(COLUMNS_SUMMARY_RESULT, 1)}
        all_rows = self.repo.get_all_summary_results()
        rows = [r for r in all_rows if not is_demo_student(r["student_name"])]

        # 要対応のみ抽出（進捗遅れあり、または備考欄不備あり）
        target_rows = []
        for r in rows:
            has_delay = bool(r["delayed_targets"])
            severity = (r["severity"] or "").upper()
            has_instruction_issue = severity not in ["PASS", "OK", "-", ""]
            if has_delay or has_instruction_issue:
                target_rows.append(r)

        for r_idx, r in enumerate(target_rows, start=2):
            delayed_str = "、".join(r["delayed_targets"]) if r["delayed_targets"] else DEFAULT_EMPTY_VALUE
            reasons_str = "、".join(r["reasons"]) if r["reasons"] else DEFAULT_EMPTY_VALUE
            severity = r["severity"] or DEFAULT_EMPTY_VALUE

            row_data = [
                r["classroom_name"] or DEFAULT_EMPTY_VALUE,
                r["student_name"] or DEFAULT_EMPTY_VALUE,
                r["subject"] or DEFAULT_EMPTY_VALUE,
                delayed_str,
                severity,
                reasons_str,
            ]
            ws.append(row_data)

            is_even = (r_idx % 2 == 0)
            for col_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=r_idx, column=col_idx)
                cell.font = DATA_FONT
                cell.border = CELL_BORDER

                # デフォルト背景（ゼブラストライプ）
                if is_even:
                    cell.fill = ZEBRA_FILL

                if col_idx in [1, 2, 3]: # 教室名, 生徒名, 科目名
                    cell.alignment = ALIGN_LEFT
                elif col_idx == 4: # 進捗遅れ
                    cell.alignment = ALIGN_LEFT
                    if r["delayed_targets"]:
                        cell.fill = ALERT_FILL_RED
                        cell.font = ALERT_FONT_RED
                elif col_idx == 5: # 備考欄スコア
                    cell.alignment = ALIGN_CENTER
                    sev_upper = severity.upper()
                    if sev_upper in ["CRITICAL", "ERROR"]:
                        cell.fill = ALERT_FILL_RED
                        cell.font = ALERT_FONT_RED
                    elif sev_upper in ["WARNING", "REVIEW"]:
                        cell.fill = ALERT_FILL_YELLOW
                        cell.font = ALERT_FONT_YELLOW
                    elif sev_upper in ["PASS", "OK"]:
                        cell.fill = ALERT_FILL_GREEN
                        cell.font = ALERT_FONT_GREEN
                elif col_idx == 6: # 備考欄詳細
                    cell.alignment = ALIGN_WRAP

            self._track_row_widths(col_widths, row_data)

        # ウィンドウ枠固定: 1行目およびA〜C列を固定（D2を指定）
        ws.freeze_panes = "D2"
        self._auto_column_widths(ws, max_len_cap=60, col_widths=col_widths)

    def _apply_header_style(self, ws, columns: List[str]):
        """ヘッダー行の書式設定"""
        ws.append(columns)
        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = ALIGN_CENTER
            cell.border = CELL_BORDER
        ws.freeze_panes = "A2"

    def _track_row_widths(self, col_widths: Dict[int, int], row_data: List[Any], skip_cols: Optional[Set[int]] = None):
        """行データから各列の最大文字長をインライン集計 (全セル走査を回避)"""
        for col_idx, val in enumerate(row_data, start=1):
            if skip_cols and col_idx in skip_cols:
                continue
            val_str = str(val) if val is not None else ""
            if "\n" in val_str:
                line_len = max((len(l) for l in val_str.split("\n")), default=0)
            else:
                line_len = len(val_str)
            if line_len > col_widths.get(col_idx, 0):
                col_widths[col_idx] = line_len

    def _auto_column_widths(self, ws, max_len_cap: int = 40, col_widths: Optional[Dict[int, int]] = None):
        """列幅の自動調整 (col_widths 集計辞書が存在する場合は全セル走査をスキップして高速適用)"""
        if col_widths is not None:
            for col_idx, max_len in col_widths.items():
                col_letter = get_column_letter(col_idx)
                adjusted_width = min(max(max_len + 3, 10), max_len_cap)
                ws.column_dimensions[col_letter].width = adjusted_width
        else:
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val = str(cell.value or "")
                    lines = val.split("\n")
                    line_max = max(len(l) for l in lines) if lines else 0
                    max_len = max(max_len, line_max)
                adjusted_width = min(max(max_len + 3, 10), max_len_cap)
                ws.column_dimensions[col_letter].width = adjusted_width

        # オートフィルター設定
        if ws.max_row >= 1 and ws.max_column >= 1:
            ws.auto_filter.ref = ws.dimensions

    def _write_progress_sheet(self, ws):
        """[進捗率]シート出力 (全28列) - デモ生徒は除外"""
        self._apply_header_style(ws, COLUMNS_PROGRESS)
        col_widths = {i: len(str(c)) for i, c in enumerate(COLUMNS_PROGRESS, 1)}
        all_rows = self.repo.get_all_progress_summaries()
        rows = [r for r in all_rows if not is_demo_student(r["student_name"])]

        for r_idx, r in enumerate(rows, start=2):
            progress_delay = r["progress_delay"] if ("progress_delay" in r.keys() and r["progress_delay"]) else "OK"
            row_data = [
                r["classroom"] or DEFAULT_EMPTY_VALUE,
                r["student_id"] or DEFAULT_EMPTY_VALUE,
                r["grade"] or DEFAULT_EMPTY_VALUE,
                r["student_name"] or DEFAULT_EMPTY_VALUE,
                r["division"] or DEFAULT_EMPTY_VALUE,
                r["subject"] or DEFAULT_EMPTY_VALUE,
                r["target_no"] or DEFAULT_EMPTY_VALUE,
                r["target_name"] or DEFAULT_EMPTY_VALUE,
                progress_delay,
                r["start_date"] or DEFAULT_EMPTY_VALUE,
                r["end_date"] or DEFAULT_EMPTY_VALUE,
                r["period_str"] or DEFAULT_EMPTY_VALUE,
                bool(r["is_current"]), # Boolean
                r["textbooks_used"] or DEFAULT_EMPTY_VALUE,
                r["target_score"] or DEFAULT_EMPTY_VALUE,
                r["current_score"] or DEFAULT_EMPTY_VALUE,
                r["target_unit_count"],
                r["executed_count"],
                r["executed_rate"],
                r["on_time_count"],
                r["on_time_rate"],
                r["before_count"],
                r["before_rate"],
                r["after_count"],
                r["after_rate"],
                r["unexecuted_count"],
                r["unexecuted_rate"],
                r["latest_execution_date"] or DEFAULT_EMPTY_VALUE,
            ]
            ws.append(row_data)
            for col_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=r_idx, column=col_idx)
                cell.font = DATA_FONT
                cell.border = CELL_BORDER
                if col_idx in [9, 13]: # 進捗遅れ, 実施中 (Boolean)
                    cell.alignment = ALIGN_CENTER
                elif col_idx in [14]: # 使用教材 (改行あり)
                    cell.alignment = ALIGN_WRAP
                elif col_idx in [17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]: # 数値・割合
                    cell.alignment = ALIGN_RIGHT
                else:
                    cell.alignment = ALIGN_LEFT

            self._track_row_widths(col_widths, row_data)

        self._auto_column_widths(ws, max_len_cap=40, col_widths=col_widths)

    def _write_unit_details_sheet(self, ws):
        """[単元詳細]シート出力 (全24列) - デモ生徒は除外"""
        self._apply_header_style(ws, COLUMNS_UNIT_DETAILS)
        col_widths = {i: len(str(c)) for i, c in enumerate(COLUMNS_UNIT_DETAILS, 1)}
        all_rows = self.repo.get_all_units()
        rows = [r for r in all_rows if not is_demo_student(r["student_name"])]
        target_rows = self.repo.get_all_targets()
        # (page_url, target_no) -> target_row
        target_map = {(t["page_url"], t["target_no"]): t for t in target_rows}

        for r in rows:
            target_checks = {}
            if r["target_checks_json"]:
                try:
                    target_checks = json.loads(r["target_checks_json"])
                except Exception:
                    pass

            # ターゲットごとの展開 (1単元が複数ターゲットに該当する場合、それぞれ別行)
            # target_checks で True のターゲット、または単元単体
            active_targets = [t for t, checked in target_checks.items() if checked]
            if not active_targets:
                active_targets = ["-"]

            for t_no in active_targets:
                target_name = DEFAULT_EMPTY_VALUE
                progress_delay = "OK"
                start_date = DEFAULT_EMPTY_VALUE
                end_date = DEFAULT_EMPTY_VALUE
                timing = r["timing"] or DEFAULT_EMPTY_VALUE

                if t_no != "-" and (r["page_url"], t_no) in target_map:
                    t_info = target_map[(r["page_url"], t_no)]
                    target_name = t_info["target_name"] or DEFAULT_EMPTY_VALUE
                    progress_delay = t_info["progress_delay"] if ("progress_delay" in t_info.keys() and t_info["progress_delay"]) else "OK"
                    start_date = t_info["start_date"] or DEFAULT_EMPTY_VALUE
                    end_date = t_info["end_date"] or DEFAULT_EMPTY_VALUE

                    # ターゲットごとの期間に対してタイミングを再判定
                    if not r["is_executed"] or not r["execution_date"] or r["execution_date"] == DEFAULT_EMPTY_VALUE:
                        timing = TimingCategory.UNEXECUTED.value
                    else:
                        s_d = parse_date(start_date)
                        e_d = parse_date(end_date)
                        ex_d = parse_date(r["execution_date"])
                        if not s_d or not e_d or not ex_d:
                            timing = TimingCategory.UNDECIDED.value
                        elif ex_d < s_d:
                            timing = TimingCategory.BEFORE.value
                        elif s_d <= ex_d <= e_d:
                            timing = TimingCategory.ON_TIME.value
                        else:
                            timing = TimingCategory.AFTER.value
                elif t_no == "-":
                    timing = TimingCategory.UNEXECUTED.value if not r["is_executed"] else TimingCategory.ON_TIME.value

                row_data = [
                    r["classroom_name"] or DEFAULT_EMPTY_VALUE,
                    r["student_id"] or DEFAULT_EMPTY_VALUE,
                    r["grade"] or DEFAULT_EMPTY_VALUE,
                    r["student_name"] or DEFAULT_EMPTY_VALUE,
                    r["division"] or DEFAULT_EMPTY_VALUE,
                    r["subject"] or DEFAULT_EMPTY_VALUE,
                    t_no,
                    target_name,
                    progress_delay,
                    start_date,
                    end_date,
                    r["unit_name"] or DEFAULT_EMPTY_VALUE,
                    r["middle_unit"] or DEFAULT_EMPTY_VALUE,
                    r["textbook"] or DEFAULT_EMPTY_VALUE,
                    r["problem_code"] or DEFAULT_EMPTY_VALUE,
                    r["execution_date"] or DEFAULT_EMPTY_VALUE,
                    timing,
                    bool(r["is_executed"]),
                    r["score"] or DEFAULT_EMPTY_VALUE,
                    r["max_score"] or DEFAULT_EMPTY_VALUE,
                    r["score_rate"] or DEFAULT_EMPTY_VALUE,
                    r["today_textbook"] or DEFAULT_EMPTY_VALUE,
                    r["execution_division"] or DEFAULT_EMPTY_VALUE,
                    r["confirm_test"] or DEFAULT_EMPTY_VALUE,
                ]
                ws.append(row_data)
                curr_row = ws.max_row
                for col_idx in range(1, len(row_data) + 1):
                    cell = ws.cell(row=curr_row, column=col_idx)
                    cell.font = DATA_FONT
                    cell.border = CELL_BORDER
                    if col_idx in [9, 18]: # 進捗遅れ, 実施済み (Boolean)
                        cell.alignment = ALIGN_CENTER
                    elif col_idx in [19, 20, 21]: # 得点, 配点, 得点率
                        cell.alignment = ALIGN_RIGHT
                    else:
                        cell.alignment = ALIGN_LEFT

                self._track_row_widths(col_widths, row_data)

        self._auto_column_widths(ws, max_len_cap=40, col_widths=col_widths)

    def _write_instruction_sheet(self, ws):
        """[備考欄]シート出力 (全18列) - デモ生徒は除外"""
        self._apply_header_style(ws, COLUMNS_INSTRUCTION)
        col_widths = {i: len(str(c)) for i, c in enumerate(COLUMNS_INSTRUCTION, 1)}
        all_rows = self.repo.get_all_instruction_evaluations()
        rows = [r for r in all_rows if not is_demo_student(r["student_name"])]

        for r_idx, r in enumerate(rows, start=2):
            fix_items = json.loads(r["fix_items_json"] or "[]")
            errors = json.loads(r["errors_json"] or "[]")
            warnings = json.loads(r["warnings_json"] or "[]")

            row_data = [
                r["classroom_name"] or DEFAULT_EMPTY_VALUE,
                r["student_id"] or DEFAULT_EMPTY_VALUE,
                r["grade"] or DEFAULT_EMPTY_VALUE,
                r["student_name"] or DEFAULT_EMPTY_VALUE,
                r["division"] or DEFAULT_EMPTY_VALUE,
                r["subject"] or DEFAULT_EMPTY_VALUE,
                r["severity"] or DEFAULT_EMPTY_VALUE,
                "\n".join(fix_items) if fix_items else DEFAULT_EMPTY_VALUE,
                "\n".join(errors) if errors else DEFAULT_EMPTY_VALUE,
                "\n".join(warnings) if warnings else DEFAULT_EMPTY_VALUE,
                r["author"] or DEFAULT_EMPTY_VALUE,
                r["target_school"] or DEFAULT_EMPTY_VALUE,
                r["textbook"] or DEFAULT_EMPTY_VALUE,
                r["plan"] or DEFAULT_EMPTY_VALUE,
                r["student_info"] or DEFAULT_EMPTY_VALUE,
                r["test"] or DEFAULT_EMPTY_VALUE,
                r["homework"] or DEFAULT_EMPTY_VALUE,
                r["unclassified_text"] or DEFAULT_EMPTY_VALUE,
            ]
            ws.append(row_data)
            for col_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=r_idx, column=col_idx)
                cell.font = DATA_FONT
                cell.border = CELL_BORDER
                if col_idx in [7]: # 判定
                    cell.alignment = ALIGN_CENTER
                elif col_idx in [8, 9, 10, 14, 15, 18]: # 複数行テキスト
                    cell.alignment = ALIGN_WRAP
                else:
                    cell.alignment = ALIGN_LEFT

            self._track_row_widths(col_widths, row_data)

        self._auto_column_widths(ws, max_len_cap=50, col_widths=col_widths)

    def _write_summary_sheet(self, ws):
        """[サマリー]シート出力 (仕様書§24: 全体、教室別、学年別、科目別集計) - デモ生徒は除外 (1パス事前集計)"""
        self._apply_header_style(ws, COLUMNS_SUMMARY)
        col_widths = {i: len(str(c)) for i, c in enumerate(COLUMNS_SUMMARY, 1)}

        all_prog_rows = self.repo.get_all_progress_summaries()
        all_eval_rows = self.repo.get_all_instruction_evaluations()

        prog_rows = [r for r in all_prog_rows if not is_demo_student(r["student_name"])]
        eval_rows = [e for e in all_eval_rows if not is_demo_student(e["student_name"])]

        # 1パスで eval_rows のエラー・警告数を事前パース
        eval_precomputed = []
        for e in eval_rows:
            try:
                err_cnt = len(json.loads(e["errors_json"] or "[]"))
            except Exception:
                err_cnt = 0
            try:
                warn_cnt = len(json.loads(e["warnings_json"] or "[]"))
            except Exception:
                warn_cnt = 0
            eval_precomputed.append({
                "classroom": e["classroom_name"] or "",
                "grade": e["grade"] or "",
                "subject": e["subject"] or "",
                "err_cnt": err_cnt,
                "warn_cnt": warn_cnt,
            })

        # グループ集計補助
        def summarize(group_key: str, key_name: str, records: List[Any], evals: List[Any]) -> List[Any]:
            student_ids = set()
            target_count = len(records)
            target_unit_count = 0
            executed_count = 0
            unexecuted_count = 0
            on_time_count = 0
            before_count = 0
            after_count = 0

            for r in records:
                student_ids.add(r["student_id"])
                target_unit_count += r["target_unit_count"] or 0
                executed_count += r["executed_count"] or 0
                unexecuted_count += r["unexecuted_count"] or 0
                on_time_count += r["on_time_count"] or 0
                before_count += r["before_count"] or 0
                after_count += r["after_count"] or 0

            error_cnt = sum(e["err_cnt"] for e in evals)
            warn_cnt = sum(e["warn_cnt"] for e in evals)

            return [
                group_key,
                key_name,
                len(student_ids),
                target_count,
                target_unit_count,
                executed_count,
                unexecuted_count,
                on_time_count,
                before_count,
                after_count,
                error_cnt,
                warn_cnt,
            ]

        # 1. 全体集計
        summary_rows = []
        summary_rows.append(summarize("全体", "全件合計", prog_rows, eval_precomputed))

        # 2. 教室別集計 (インデックス化して高速走査)
        prog_by_cr = {}
        for r in prog_rows:
            cr = r["classroom"]
            if cr:
                prog_by_cr.setdefault(cr, []).append(r)
        eval_by_cr = {}
        for e in eval_precomputed:
            cr = e["classroom"]
            if cr:
                eval_by_cr.setdefault(cr, []).append(e)

        for cr in sorted(prog_by_cr.keys()):
            summary_rows.append(summarize("教室別", cr, prog_by_cr[cr], eval_by_cr.get(cr, [])))

        # 3. 学年別集計
        prog_by_gr = {}
        for r in prog_rows:
            gr = r["grade"]
            if gr:
                prog_by_gr.setdefault(gr, []).append(r)
        eval_by_gr = {}
        for e in eval_precomputed:
            gr = e["grade"]
            if gr:
                eval_by_gr.setdefault(gr, []).append(e)

        for gr in sorted(prog_by_gr.keys()):
            summary_rows.append(summarize("学年別", gr, prog_by_gr[gr], eval_by_gr.get(gr, [])))

        # 4. 科目別集計
        prog_by_sub = {}
        for r in prog_rows:
            sub = r["subject"]
            if sub:
                prog_by_sub.setdefault(sub, []).append(r)
        eval_by_sub = {}
        for e in eval_precomputed:
            sub = e["subject"]
            if sub:
                eval_by_sub.setdefault(sub, []).append(e)

        for sub in sorted(prog_by_sub.keys()):
            summary_rows.append(summarize("科目別", sub, prog_by_sub[sub], eval_by_sub.get(sub, [])))

        for r_idx, row_data in enumerate(summary_rows, start=2):
            ws.append(row_data)
            self._track_row_widths(col_widths, row_data)
            for col_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=r_idx, column=col_idx)
                cell.font = DATA_FONT
                cell.border = CELL_BORDER
                if col_idx in [1, 2]:
                    cell.alignment = ALIGN_LEFT
                else:
                    cell.alignment = ALIGN_RIGHT

        self._auto_column_widths(ws, max_len_cap=40, col_widths=col_widths)

    def _write_raw_sheet(self, ws):
        """[原文]シート出力 (全6列) - デモ生徒は除外"""
        self._apply_header_style(ws, COLUMNS_RAW)
        col_widths = {i: len(str(c)) for i, c in enumerate(COLUMNS_RAW, 1)}
        col_widths[4] = 47  # HTML列は固定幅 (上限50) に事前設定
        all_rows = self.repo.get_all_raw_pages()
        rows = [r for r in all_rows if not is_demo_student(r["student_name"])]

        for r_idx, r in enumerate(rows, start=2):
            html_snippet = r["html"] or ""
            # HTMLが巨大な場合はExcelセル制限(32767文字)を考慮し安全に格納
            if len(html_snippet) > 32000:
                html_snippet = html_snippet[:32000] + "... (truncated)"

            row_data = [
                r["url"] or DEFAULT_EMPTY_VALUE,
                r["fetch_time"] or str(r["created_at"]),
                "詳細ページ" if "detail" in (r["url"] or "") or "sim" in (r["url"] or "") else "授業データ",
                html_snippet or DEFAULT_EMPTY_VALUE,
                r["status"] or DEFAULT_EMPTY_VALUE,
                r["error_message"] or DEFAULT_EMPTY_VALUE,
            ]
            ws.append(row_data)
            for col_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=r_idx, column=col_idx)
                cell.font = DATA_FONT
                cell.border = CELL_BORDER
                if col_idx in [5]:
                    cell.alignment = ALIGN_CENTER
                else:
                    cell.alignment = ALIGN_LEFT

            self._track_row_widths(col_widths, row_data, skip_cols={4})

        self._auto_column_widths(ws, max_len_cap=50, col_widths=col_widths)
