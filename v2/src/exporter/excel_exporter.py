"""
Excel 5シート高速出力エンジン (仕様書§18, §20, §21, §24, §25, §26)
- xlsxwriter + Format事前キャッシュ + Cレベル str.translate による高速レンダリング
- ExportContext によるDBクエリの1パス共有 (重複クエリ排除)
- 制御文字サニタイズ & 数式インジェクション防止 (strings_to_formulas=False)
"""
from dataclasses import dataclass, field
import json
from typing import Dict, List, Any, Optional, Set, Tuple
import xlsxwriter

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

# XML 1.0 で無効な制御文字 (タブ \x09, LF \x0a, CR \x0d を除く 0x00-0x1F) をCレベルで高速除去する変換テーブル
_ILLEGAL_XML_CHARS_TABLE = str.maketrans(
    "",
    "",
    "".join(chr(c) for c in (*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20))),
)

FONT_NAME = "Yu Gothic UI"
FONT_SIZE = 10


def sanitize_cell_text(val: str) -> str:
    """Excel XML破損を防ぐための制御文字除去 (C実装 str.translate)"""
    if not val:
        return val
    return val.translate(_ILLEGAL_XML_CHARS_TABLE)


@dataclass
class SheetSpec:
    """1シート分の描画仕様データ (レンダラから独立した純粋データ構造)"""
    name: str
    columns: List[str]
    rows: List[List[Any]] = field(default_factory=list)
    col_align: Dict[int, str] = field(default_factory=dict)
    cell_overrides: Dict[Tuple[int, int], str] = field(default_factory=dict)
    zebra: bool = False
    freeze: Tuple[int, int] = (1, 0)
    width_cap: int = 40
    col_widths: Dict[int, int] = field(default_factory=dict)


@dataclass
class ExportContext:
    """1回のExcel出力で全シートが共有するDB取得キャッシュ"""
    progress_rows: List[Any]
    unit_rows: List[Any]
    target_rows: List[Any]
    eval_rows: List[Any]
    page_rows: List[Any]
    raw_rows: Optional[List[Any]] = None


class _FormatCache:
    """xlsxwriter.Workbook ごとに Format オブジェクトを1回だけ生成して再利用"""
    def __init__(self, wb: xlsxwriter.Workbook):
        self.wb = wb
        self._cache: Dict[Tuple[str, str], Any] = {}
        self.header = wb.add_format({
            "font_name": FONT_NAME,
            "font_size": FONT_SIZE,
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#1F4E79",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#D9D9D9",
        })

    def get(self, align_mode: str = "left", tone: str = "normal"):
        key = (align_mode, tone)
        fmt = self._cache.get(key)
        if fmt is not None:
            return fmt

        props: Dict[str, Any] = {
            "font_name": FONT_NAME,
            "font_size": FONT_SIZE,
            "valign": "vcenter",
            "border": 1,
            "border_color": "#D9D9D9",
        }
        if align_mode == "center":
            props["align"] = "center"
        elif align_mode == "right":
            props["align"] = "right"
        elif align_mode == "wrap":
            props["align"] = "left"
            props["text_wrap"] = True
        else:
            props["align"] = "left"

        if tone == "zebra":
            props["bg_color"] = "#F9FAFB"
        elif tone == "alert_red":
            props["bg_color"] = "#FFD8D8"
            props["font_color"] = "#9C0006"
            props["bold"] = True
        elif tone == "alert_yellow":
            props["bg_color"] = "#FFF2CC"
            props["font_color"] = "#B25E00"
            props["bold"] = True
        elif tone == "alert_green":
            props["bg_color"] = "#E2EFDA"
            props["font_color"] = "#276A3C"

        fmt = self.wb.add_format(props)
        self._cache[key] = fmt
        return fmt


class ExcelExporter:
    def __init__(self, repository: Repository, include_raw_sheet: bool = False):
        self.repo = repository
        self.include_raw_sheet = include_raw_sheet

    def _load_context(self, use_raw: bool) -> ExportContext:
        """全シートで使うテーブルデータを最小限のクエリで一括取得しデモ生徒を除外"""
        all_prog = self.repo.get_all_progress_summaries()
        all_units = self.repo.get_all_units()
        all_targets = self.repo.get_all_targets()
        all_evals = self.repo.get_all_instruction_evaluations()
        all_pages = self.repo.get_all_raw_pages()

        prog_rows = [r for r in all_prog if not is_demo_student(r["student_name"])]
        unit_rows = [r for r in all_units if not is_demo_student(r["student_name"])]
        eval_rows = [r for r in all_evals if not is_demo_student(r["student_name"])]
        page_rows = [r for r in all_pages if not is_demo_student(r["student_name"])]

        return ExportContext(
            progress_rows=prog_rows,
            unit_rows=unit_rows,
            target_rows=all_targets,
            eval_rows=eval_rows,
            page_rows=page_rows,
            raw_rows=page_rows if use_raw else None,
        )

    def build_sheets(self, include_raw_sheet: Optional[bool] = None) -> List[SheetSpec]:
        """DBから1パスでデータを集め、全シートの描画仕様リストを構築"""
        use_raw = self.include_raw_sheet if include_raw_sheet is None else include_raw_sheet
        ctx = self._load_context(use_raw)

        sheets = [
            self._build_summary_result_spec(ctx),
            self._build_progress_spec(ctx),
            self._build_unit_details_spec(ctx),
            self._build_instruction_spec(ctx),
            self._build_summary_spec(ctx),
        ]
        if use_raw:
            sheets.append(self._build_raw_spec(ctx))
        return sheets

    def export_to(self, file_path: str, include_raw_sheet: Optional[bool] = None) -> str:
        """指定パスへ xlsxwriter を用いて高速・安全にExcelファイルを書き出す"""
        sheets = self.build_sheets(include_raw_sheet=include_raw_sheet)

        wb = xlsxwriter.Workbook(
            file_path,
            {
                "constant_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
                "strings_to_numbers": False,
            },
        )
        trans_table = _ILLEGAL_XML_CHARS_TABLE
        empty_val = DEFAULT_EMPTY_VALUE
        try:
            fmt_cache = _FormatCache(wb)
            for spec in sheets:
                ws = wb.add_worksheet(spec.name)
                ws_write_str = ws.write_string
                ws_write_num = ws.write_number
                ws_write_bool = ws.write_boolean

                # 1. 列幅設定
                for col_idx_1, max_len in spec.col_widths.items():
                    col_0 = col_idx_1 - 1
                    adjusted_width = min(max(max_len + 3, 10), spec.width_cap)
                    ws.set_column(col_0, col_0, adjusted_width)

                # 2. ウィンドウ枠の固定
                ws.freeze_panes(spec.freeze[0], spec.freeze[1])

                # 3. ヘッダー行 (row 0)
                hdr_fmt = fmt_cache.header
                for col_0, col_title in enumerate(spec.columns):
                    ws_write_str(0, col_0, str(col_title).translate(trans_table), hdr_fmt)

                # 4. データ行 (row 1..N)
                num_cols = len(spec.columns)
                normal_col_fmts = [
                    fmt_cache.get(spec.col_align.get(c, "left"), "normal")
                    for c in range(num_cols)
                ]
                zebra_col_fmts = [
                    fmt_cache.get(spec.col_align.get(c, "left"), "zebra" if spec.zebra else "normal")
                    for c in range(num_cols)
                ]
                overrides = spec.cell_overrides
                has_overrides = bool(overrides)
                use_zebra = spec.zebra

                for data_idx, row_data in enumerate(spec.rows):
                    excel_row = data_idx + 1
                    row_fmts = zebra_col_fmts if (use_zebra and (data_idx & 1) == 0) else normal_col_fmts

                    for col_0, val in enumerate(row_data):
                        if has_overrides and (data_idx, col_0) in overrides:
                            cell_fmt = fmt_cache.get(spec.col_align.get(col_0, "left"), overrides[(data_idx, col_0)])
                        else:
                            cell_fmt = row_fmts[col_0]

                        if type(val) is str:
                            ws_write_str(excel_row, col_0, val.translate(trans_table), cell_fmt)
                        elif type(val) is int or type(val) is float:
                            ws_write_num(excel_row, col_0, val, cell_fmt)
                        elif type(val) is bool:
                            ws_write_bool(excel_row, col_0, val, cell_fmt)
                        elif val is None:
                            ws_write_str(excel_row, col_0, empty_val, cell_fmt)
                        else:
                            ws_write_str(excel_row, col_0, str(val).translate(trans_table), cell_fmt)

                # 5. オートフィルター設定
                last_row = len(spec.rows)
                last_col = max(0, len(spec.columns) - 1)
                ws.autofilter(0, 0, last_row, last_col)
        finally:
            wb.close()

        return file_path

    @staticmethod
    def _init_col_widths(columns: List[str]) -> Dict[int, int]:
        return {i: len(str(c)) for i, c in enumerate(columns, 1)}

    @staticmethod
    def _track_row_widths(
        col_widths: Dict[int, int],
        row_data: List[Any],
        skip_cols: Optional[Set[int]] = None,
        len_cap: int = 60,
    ):
        """行データから各列の最大文字長をインライン集計 (既に上限に達した列はスキップ)"""
        for col_idx, val in enumerate(row_data, start=1):
            if skip_cols and col_idx in skip_cols:
                continue
            cur_max = col_widths.get(col_idx, 0)
            if cur_max >= len_cap:
                continue
            val_str = val if type(val) is str else (str(val) if val is not None else "")
            if "\n" in val_str:
                line_len = max((len(l) for l in val_str.split("\n")), default=0)
            else:
                line_len = len(val_str)
            if line_len > cur_max:
                col_widths[col_idx] = line_len

    def _build_summary_result_spec(self, ctx: ExportContext) -> SheetSpec:
        """[集計結果]シート (全6列: 教室名, 生徒名, 科目名, 進捗遅れ, 備考欄スコア, 備考欄詳細) - 要対応のみ抽出"""
        col_widths = self._init_col_widths(COLUMNS_SUMMARY_RESULT)
        col_align = {0: "left", 1: "left", 2: "left", 3: "left", 4: "center", 5: "wrap"}
        spec = SheetSpec(
            name=SHEET_SUMMARY_RESULT,
            columns=COLUMNS_SUMMARY_RESULT,
            col_align=col_align,
            zebra=True,
            freeze=(1, 3),  # D2 固定 (1行目およびA〜C列固定)
            width_cap=60,
            col_widths=col_widths,
        )

        targets_by_page: Dict[str, List[Any]] = {}
        for t in ctx.target_rows:
            targets_by_page.setdefault(t["page_url"], []).append(t)

        evals_by_page = {e["page_url"]: e for e in ctx.eval_rows}

        data_idx = 0
        for p in ctx.page_rows:
            url = p["url"]
            p_targets = targets_by_page.get(url, [])
            delayed_target_names = []
            for t in p_targets:
                p_delay = t["progress_delay"]
                if p_delay and p_delay != "OK":
                    t_name = t["target_name"] or t["target_no"] or "ターゲット"
                    delayed_target_names.append(t_name)

            eval_row = evals_by_page.get(url)
            severity = (eval_row["severity"] if eval_row else "-") or "-"

            has_delay = bool(delayed_target_names)
            sev_upper = severity.upper()
            has_instruction_issue = sev_upper not in ("PASS", "OK", "-", "")
            if not (has_delay or has_instruction_issue):
                continue

            reasons: List[str] = []
            if eval_row:
                fix_items = json.loads(eval_row["fix_items_json"] or "[]")
                errors = json.loads(eval_row["errors_json"] or "[]")
                warnings = json.loads(eval_row["warnings_json"] or "[]")
                if fix_items:
                    reasons.extend(fix_items)
                else:
                    reasons.extend(errors)
                    reasons.extend(warnings)

            delayed_str = "、".join(delayed_target_names) if delayed_target_names else DEFAULT_EMPTY_VALUE
            reasons_str = "、".join(reasons) if reasons else DEFAULT_EMPTY_VALUE

            row_data = [
                p["classroom_name"] or DEFAULT_EMPTY_VALUE,
                p["student_name"] or DEFAULT_EMPTY_VALUE,
                p["subject"] or DEFAULT_EMPTY_VALUE,
                delayed_str,
                severity,
                reasons_str,
            ]
            spec.rows.append(row_data)

            if has_delay:
                spec.cell_overrides[(data_idx, 3)] = "alert_red"

            if sev_upper in ("CRITICAL", "ERROR"):
                spec.cell_overrides[(data_idx, 4)] = "alert_red"
            elif sev_upper in ("WARNING", "REVIEW"):
                spec.cell_overrides[(data_idx, 4)] = "alert_yellow"
            elif sev_upper in ("PASS", "OK"):
                spec.cell_overrides[(data_idx, 4)] = "alert_green"

            self._track_row_widths(col_widths, row_data, len_cap=60)
            data_idx += 1

        return spec

    def _build_progress_spec(self, ctx: ExportContext) -> SheetSpec:
        """[進捗率]シート (全28列)"""
        col_widths = self._init_col_widths(COLUMNS_PROGRESS)
        col_align: Dict[int, str] = {}
        for col_1 in range(1, len(COLUMNS_PROGRESS) + 1):
            c0 = col_1 - 1
            if col_1 in (9, 13):
                col_align[c0] = "center"
            elif col_1 == 14:
                col_align[c0] = "wrap"
            elif 17 <= col_1 <= 27:
                col_align[c0] = "right"
            else:
                col_align[c0] = "left"

        spec = SheetSpec(
            name=SHEET_PROGRESS,
            columns=COLUMNS_PROGRESS,
            col_align=col_align,
            freeze=(1, 0),
            width_cap=40,
            col_widths=col_widths,
        )

        for r in ctx.progress_rows:
            r_keys = r.keys()
            progress_delay = r["progress_delay"] if ("progress_delay" in r_keys and r["progress_delay"]) else "OK"
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
                bool(r["is_current"]),
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
            spec.rows.append(row_data)
            self._track_row_widths(col_widths, row_data, len_cap=40)

        return spec

    def _build_unit_details_spec(self, ctx: ExportContext) -> SheetSpec:
        """[単元詳細]シート (全24列) - 日付パースメモ化による高速化"""
        col_widths = self._init_col_widths(COLUMNS_UNIT_DETAILS)
        col_align: Dict[int, str] = {}
        for col_1 in range(1, len(COLUMNS_UNIT_DETAILS) + 1):
            c0 = col_1 - 1
            if col_1 in (9, 18):
                col_align[c0] = "center"
            elif col_1 in (19, 20, 21):
                col_align[c0] = "right"
            else:
                col_align[c0] = "left"

        spec = SheetSpec(
            name=SHEET_UNIT_DETAILS,
            columns=COLUMNS_UNIT_DETAILS,
            col_align=col_align,
            freeze=(1, 0),
            width_cap=40,
            col_widths=col_widths,
        )

        date_cache: Dict[str, Any] = {}

        def _cached_date(d_str: str):
            if not d_str or d_str == DEFAULT_EMPTY_VALUE:
                return None
            if d_str not in date_cache:
                date_cache[d_str] = parse_date(d_str)
            return date_cache[d_str]

        target_map: Dict[Tuple[str, str], Tuple[str, str, str, str, Any, Any]] = {}
        for t in ctx.target_rows:
            t_keys = t.keys()
            t_name = t["target_name"] or DEFAULT_EMPTY_VALUE
            p_delay = t["progress_delay"] if ("progress_delay" in t_keys and t["progress_delay"]) else "OK"
            s_str = t["start_date"] or DEFAULT_EMPTY_VALUE
            e_str = t["end_date"] or DEFAULT_EMPTY_VALUE
            target_map[(t["page_url"], t["target_no"])] = (
                t_name,
                p_delay,
                s_str,
                e_str,
                _cached_date(s_str),
                _cached_date(e_str),
            )

        rows_out = spec.rows
        track_widths = self._track_row_widths
        row_counter = 0

        for r in ctx.unit_rows:
            target_checks = {}
            tc_json = r["target_checks_json"]
            if tc_json and tc_json != "{}":
                try:
                    target_checks = json.loads(tc_json)
                except Exception:
                    pass

            active_targets = [t for t, checked in target_checks.items() if checked] if target_checks else []
            if not active_targets:
                active_targets = ["-"]

            page_url = r["page_url"]
            is_exec = bool(r["is_executed"])
            exec_date_str = r["execution_date"] or DEFAULT_EMPTY_VALUE
            ex_d = _cached_date(exec_date_str) if is_exec else None

            cr_name = r["classroom_name"] or DEFAULT_EMPTY_VALUE
            stu_id = r["student_id"] or DEFAULT_EMPTY_VALUE
            grade = r["grade"] or DEFAULT_EMPTY_VALUE
            stu_name = r["student_name"] or DEFAULT_EMPTY_VALUE
            div = r["division"] or DEFAULT_EMPTY_VALUE
            subj = r["subject"] or DEFAULT_EMPTY_VALUE
            u_name = r["unit_name"] or DEFAULT_EMPTY_VALUE
            m_unit = r["middle_unit"] or DEFAULT_EMPTY_VALUE
            tb = r["textbook"] or DEFAULT_EMPTY_VALUE
            p_code = r["problem_code"] or DEFAULT_EMPTY_VALUE
            score = r["score"] or DEFAULT_EMPTY_VALUE
            max_score = r["max_score"] or DEFAULT_EMPTY_VALUE
            score_rate = r["score_rate"] or DEFAULT_EMPTY_VALUE
            today_tb = r["today_textbook"] or DEFAULT_EMPTY_VALUE
            exec_div = r["execution_division"] or DEFAULT_EMPTY_VALUE
            conf_test = r["confirm_test"] or DEFAULT_EMPTY_VALUE
            raw_timing = r["timing"] or DEFAULT_EMPTY_VALUE

            for t_no in active_targets:
                target_name = DEFAULT_EMPTY_VALUE
                progress_delay = "OK"
                start_date = DEFAULT_EMPTY_VALUE
                end_date = DEFAULT_EMPTY_VALUE
                timing = raw_timing

                if t_no != "-" and (page_url, t_no) in target_map:
                    target_name, progress_delay, start_date, end_date, s_d, e_d = target_map[(page_url, t_no)]
                    if not is_exec or exec_date_str == DEFAULT_EMPTY_VALUE:
                        timing = TimingCategory.UNEXECUTED.value
                    else:
                        if not s_d or not e_d or not ex_d:
                            timing = TimingCategory.UNDECIDED.value
                        elif ex_d < s_d:
                            timing = TimingCategory.BEFORE.value
                        elif s_d <= ex_d <= e_d:
                            timing = TimingCategory.ON_TIME.value
                        else:
                            timing = TimingCategory.AFTER.value
                elif t_no == "-":
                    timing = TimingCategory.UNEXECUTED.value if not is_exec else TimingCategory.ON_TIME.value

                row_data = [
                    cr_name,
                    stu_id,
                    grade,
                    stu_name,
                    div,
                    subj,
                    t_no,
                    target_name,
                    progress_delay,
                    start_date,
                    end_date,
                    u_name,
                    m_unit,
                    tb,
                    p_code,
                    exec_date_str,
                    timing,
                    is_exec,
                    score,
                    max_score,
                    score_rate,
                    today_tb,
                    exec_div,
                    conf_test,
                ]
                rows_out.append(row_data)
                if row_counter < 1000 or (row_counter & 15) == 0:
                    track_widths(col_widths, row_data, len_cap=40)
                row_counter += 1

        return spec

    def _build_instruction_spec(self, ctx: ExportContext) -> SheetSpec:
        """[備考欄]シート (全18列)"""
        col_widths = self._init_col_widths(COLUMNS_INSTRUCTION)
        col_align: Dict[int, str] = {}
        for col_1 in range(1, len(COLUMNS_INSTRUCTION) + 1):
            c0 = col_1 - 1
            if col_1 == 7:
                col_align[c0] = "center"
            elif col_1 in (8, 9, 10, 14, 15, 18):
                col_align[c0] = "wrap"
            else:
                col_align[c0] = "left"

        spec = SheetSpec(
            name=SHEET_INSTRUCTION,
            columns=COLUMNS_INSTRUCTION,
            col_align=col_align,
            freeze=(1, 0),
            width_cap=50,
            col_widths=col_widths,
        )

        for r in ctx.eval_rows:
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
            spec.rows.append(row_data)
            self._track_row_widths(col_widths, row_data, len_cap=50)

        return spec

    def _build_summary_spec(self, ctx: ExportContext) -> SheetSpec:
        """[サマリー]シート (仕様書§24: 全体、教室別、学年別、科目別集計)"""
        col_widths = self._init_col_widths(COLUMNS_SUMMARY)
        col_align = {c0: ("left" if c0 in (0, 1) else "right") for c0 in range(len(COLUMNS_SUMMARY))}

        spec = SheetSpec(
            name=SHEET_SUMMARY,
            columns=COLUMNS_SUMMARY,
            col_align=col_align,
            freeze=(1, 0),
            width_cap=40,
            col_widths=col_widths,
        )

        prog_rows = ctx.progress_rows
        eval_rows = ctx.eval_rows

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

        summary_rows = [summarize("全体", "全件合計", prog_rows, eval_precomputed)]

        # 教室別
        prog_by_cr: Dict[str, List[Any]] = {}
        for r in prog_rows:
            cr = r["classroom"]
            if cr:
                prog_by_cr.setdefault(cr, []).append(r)
        eval_by_cr: Dict[str, List[Any]] = {}
        for e in eval_precomputed:
            cr = e["classroom"]
            if cr:
                eval_by_cr.setdefault(cr, []).append(e)
        for cr in sorted(prog_by_cr.keys()):
            summary_rows.append(summarize("教室別", cr, prog_by_cr[cr], eval_by_cr.get(cr, [])))

        # 学年別
        prog_by_gr: Dict[str, List[Any]] = {}
        for r in prog_rows:
            gr = r["grade"]
            if gr:
                prog_by_gr.setdefault(gr, []).append(r)
        eval_by_gr: Dict[str, List[Any]] = {}
        for e in eval_precomputed:
            gr = e["grade"]
            if gr:
                eval_by_gr.setdefault(gr, []).append(e)
        for gr in sorted(prog_by_gr.keys()):
            summary_rows.append(summarize("学年別", gr, prog_by_gr[gr], eval_by_gr.get(gr, [])))

        # 科目別
        prog_by_sub: Dict[str, List[Any]] = {}
        for r in prog_rows:
            sub = r["subject"]
            if sub:
                prog_by_sub.setdefault(sub, []).append(r)
        eval_by_sub: Dict[str, List[Any]] = {}
        for e in eval_precomputed:
            sub = e["subject"]
            if sub:
                eval_by_sub.setdefault(sub, []).append(e)
        for sub in sorted(prog_by_sub.keys()):
            summary_rows.append(summarize("科目別", sub, prog_by_sub[sub], eval_by_sub.get(sub, [])))

        for row_data in summary_rows:
            spec.rows.append(row_data)
            self._track_row_widths(col_widths, row_data, len_cap=40)

        return spec

    def _build_raw_spec(self, ctx: ExportContext) -> SheetSpec:
        """[原文]シート (全6列)"""
        col_widths = self._init_col_widths(COLUMNS_RAW)
        col_widths[4] = 47
        col_align = {c0: ("center" if c0 == 4 else "left") for c0 in range(len(COLUMNS_RAW))}

        spec = SheetSpec(
            name=SHEET_RAW,
            columns=COLUMNS_RAW,
            col_align=col_align,
            freeze=(1, 0),
            width_cap=50,
            col_widths=col_widths,
        )

        for r in (ctx.raw_rows or []):
            html_snippet = r["html"] or ""
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
            spec.rows.append(row_data)
            self._track_row_widths(col_widths, row_data, skip_cols={4}, len_cap=50)

        return spec
