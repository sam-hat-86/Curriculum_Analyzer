"""
カリキュラム詳細HTMLパーサー (v2.0.0)
"""
import re
from datetime import date
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from src.models.curriculum import (
    CurriculumOverview,
    TargetInfo,
    UnitRecord,
    CurriculumDetailData,
)
from src.models.state import TimingCategory
from src.utils.constants import DEFAULT_EMPTY_VALUE
from src.utils.normalization import (
    normalize_text,
    parse_date,
    format_date,
    parse_period,
    parse_score_and_max,
)

class DetailParser:
    def __init__(self, today: Optional[date] = None):
        self.today = today or date.today()

    def parse(self, html: str, overview: Optional[CurriculumOverview] = None, fetch_time: str = "") -> CurriculumDetailData:
        """詳細HTMLを解析し CurriculumDetailData を構築"""
        soup = BeautifulSoup(html, "lxml")
        
        # 1. 生徒基本情報の抽出
        student_info = self._parse_student_info(soup)
        if overview is None:
            overview = CurriculumOverview(
                classroom_name=student_info.get("classroom_name", ""),
                classroom_code=student_info.get("classroom_code", ""),
                school_year=student_info.get("school_year", ""),
                student_id=student_info.get("student_id", ""),
                student_name=student_info.get("student_name", ""),
                grade=student_info.get("grade", ""),
                division=student_info.get("division", ""),
                subject=student_info.get("subject", ""),
                school_course=student_info.get("school_course", ""),
            )
        else:
            # 詳細側で補完
            if not overview.student_name and student_info.get("student_name"):
                overview.student_name = student_info["student_name"]
            if not overview.school_year and student_info.get("school_year"):
                overview.school_year = student_info["school_year"]
            if not overview.grade and student_info.get("grade"):
                overview.grade = student_info["grade"]
            if not overview.division and student_info.get("division"):
                overview.division = student_info["division"]
            if not overview.subject and student_info.get("subject"):
                overview.subject = student_info["subject"]
            if not overview.school_course and student_info.get("school_course"):
                overview.school_course = student_info["school_course"]

        # 2. カリキュラム備考 & 教材リスト
        raw_instruction, materials_listed = self._parse_def_form(soup)

        # 3. ターゲット表
        targets = self._parse_targets(soup)

        # 4. 単元テーブル
        units = self._parse_units(soup, targets)

        return CurriculumDetailData(
            overview=overview,
            raw_html=html,
            fetch_time=fetch_time,
            raw_instruction=raw_instruction,
            materials_listed=materials_listed,
            targets=targets,
            units=units,
        )

    def _parse_student_info(self, soup: BeautifulSoup) -> Dict[str, str]:
        """生徒情報テーブル (table.sc2-student-info) を解析"""
        info = {}
        st_tbl = soup.find("table", class_=lambda c: c and "sc2-student-info" in c)
        if not st_tbl:
            return info

        for tr in st_tbl.find_all("tr"):
            ths = tr.find_all("th")
            tds = tr.find_all("td")
            for th, td in zip(ths, tds):
                th_text = normalize_text(th.get_text())
                td_text = normalize_text(td.get_text())
                if "年度" in th_text:
                    info["school_year"] = td_text
                elif "生徒" in th_text:
                    # '00000000 山田 太郎（ヤマダ タロウ）'
                    m = re.search(r"^([A-Za-z0-9_\-]+)\s+(.*)", td_text)
                    if m:
                        info["student_id"] = m.group(1).strip()
                        raw_name = m.group(2).strip()
                        # ふりがな括弧を除去
                        raw_name = re.sub(r"[（\(][^）\)]+[）\)]", "", raw_name).strip()
                        info["student_name"] = raw_name
                    else:
                        info["student_name"] = td_text
                elif "学年" in th_text:
                    info["grade"] = td_text
                elif "受講区分" in th_text:
                    info["division"] = td_text
                elif "科目" in th_text:
                    info["subject"] = td_text
                elif "学校" in th_text or "コース" in th_text:
                    info["school_course"] = td_text

        return info

    def _parse_def_form(self, soup: BeautifulSoup) -> Tuple[str, List[str]]:
        """カリキュラム備考・教材リスト (table.def-form-table) を解析"""
        raw_instruction = ""
        materials = []
        def_tbl = soup.find("table", class_=lambda c: c and "def-form-table" in c)
        if not def_tbl:
            return raw_instruction, materials

        for tr in def_tbl.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if not th or not td:
                continue
            th_text = normalize_text(th.get_text())
            if "使用教材" in th_text:
                for li in td.find_all("li"):
                    mat_text = normalize_text(li.get_text())
                    if mat_text and mat_text not in materials:
                        materials.append(mat_text)
            elif "カリキュラム備考" in th_text or "備考" in th_text:
                # <br> を改行に変換して本文を取得
                for br in td.find_all("br"):
                    br.replace_with("\n")
                raw_instruction = td.get_text().strip()

        return raw_instruction, materials

    def _parse_targets(self, soup: BeautifulSoup) -> List[TargetInfo]:
        """ターゲット表 (table.sc2-sim-target) を解析"""
        targets = []
        t_tbl = soup.find("table", class_=lambda c: c and "sc2-sim-target" in c)
        if not t_tbl:
            return targets

        tbody = t_tbl.find("tbody")
        if not tbody:
            return targets

        rows = tbody.find_all("tr")
        i = 0
        while i < len(rows):
            tr1 = rows[i]
            tds1 = tr1.find_all(["td", "th"])
            # T1行: [No(T1), ターゲット名, 対策期間, 目標点]
            target_no = ""
            target_name = ""
            period_str = ""
            target_score = DEFAULT_EMPTY_VALUE
            site_progress = DEFAULT_EMPTY_VALUE
            current_score = DEFAULT_EMPTY_VALUE

            if len(tds1) >= 4:
                target_no = normalize_text(tds1[0].get_text())
                target_name = normalize_text(tds1[1].get_text())
                raw_period = normalize_text(tds1[2].get_text())
                raw_score = normalize_text(tds1[3].get_text())
                target_score = raw_score if raw_score else DEFAULT_EMPTY_VALUE
            elif len(tds1) >= 2:
                target_no = normalize_text(tds1[0].get_text())
                target_name = normalize_text(tds1[1].get_text())
            else:
                i += 1
                continue

            # 進捗率行 (tr2)
            if i + 1 < len(rows):
                tr2 = rows[i + 1]
                td2 = tr2.find("td")
                if td2:
                    dl_data = td2.find("div", class_="dl-data")
                    if dl_data:
                        site_progress = normalize_text(dl_data.get_text())
                    else:
                        txt = normalize_text(td2.get_text())
                        site_progress = txt if txt else DEFAULT_EMPTY_VALUE

            # テスト合計得点行 (tr3)
            if i + 2 < len(rows):
                tr3 = rows[i + 2]
                td3 = tr3.find("td")
                if td3:
                    dl_data3 = td3.find("div", class_="dl-data")
                    if dl_data3:
                        current_score = normalize_text(dl_data3.get_text())
                    else:
                        txt3 = normalize_text(td3.get_text())
                        current_score = txt3 if txt3 else DEFAULT_EMPTY_VALUE

            # 対策期間のパース
            s_date, e_date, formatted_period = parse_period(raw_period if 'raw_period' in locals() else "")
            
            # 実施中判定 (仕様書§10.2: 現在日付が開始日以上、終了日以下の場合True)
            is_current = False
            if s_date and e_date:
                is_current = (s_date <= self.today <= e_date)

            targets.append(TargetInfo(
                target_no=target_no,
                target_name=target_name,
                start_date=format_date(s_date) if s_date else "",
                end_date=format_date(e_date) if e_date else "",
                period_str=formatted_period,
                is_current=is_current,
                target_score=target_score,
                current_score=current_score,
                site_progress_rate=site_progress,
            ))

            # 各ターゲットは3行で構成される
            i += 3

        return targets

    def _parse_units(self, soup: BeautifulSoup, targets: List[TargetInfo]) -> List[UnitRecord]:
        """単元テーブル (table.is-bordered) を解析"""
        units = []
        u_tbl = soup.find("table", class_=lambda c: c and "is-bordered" in c)
        if not u_tbl:
            return units

        thead = u_tbl.find("thead")
        target_col_map: Dict[int, str] = {} # col_index -> "T1"
        header_names: List[str] = []

        if thead:
            header_tr = thead.find("tr")
            if header_tr:
                ths = header_tr.find_all("th")
                for col_idx, th in enumerate(ths):
                    h_text = normalize_text(th.get_text())
                    header_names.append(h_text)
                    # T1, T2... 列の判定
                    m = re.search(r"^(T\d+)", h_text, re.IGNORECASE)
                    if m:
                        target_col_map[col_idx] = m.group(1).upper()

        tbody = u_tbl.find("tbody")
        if not tbody:
            return units

        # ターゲットごとの開始・終了日マップ
        target_dates = {t.target_no: (parse_date(t.start_date), parse_date(t.end_date)) for t in targets}

        rows = tbody.find_all("tr")
        for r_idx, tr in enumerate(rows):
            tds = tr.find_all(["td", "th"])
            if not tds or len(tds) < 4:
                continue

            unit_no = str(r_idx + 1)
            target_checks: Dict[str, bool] = {}

            # T1..Tn列のチェック状態抽出
            for col_idx, t_name in target_col_map.items():
                if col_idx < len(tds):
                    cell = tds[col_idx]
                    # <input type="checkbox" checked ...> または checked 属性があるか
                    cb = cell.find("input", attrs={"type": "checkbox"})
                    is_checked = False
                    if cb:
                        is_checked = cb.has_attr("checked") or cb.get("checked") is not None
                    target_checks[t_name] = is_checked

            # 各情報セルのマッピング
            # 通常構成: [No, T1.., 学習カード, 問題表示, 解説動画, テスト修正, 教材・単元情報, 得点/配点, 実施日, 本日の教材, 実施区分, 確認テスト]
            info_cell = None
            score_cell = None
            date_cell = None
            today_mat_cell = None
            exec_div_cell = None
            confirm_test_cell = None

            # 列名からインデックス特定、なければ末尾側から特定
            for col_idx, cell in enumerate(tds):
                h = header_names[col_idx] if col_idx < len(header_names) else ""
                if "教材・単元情報" in h or "単元情報" in h:
                    info_cell = cell
                elif "得点/配点" in h or "得点" in h:
                    score_cell = cell
                elif "実施日" in h:
                    date_cell = cell
                elif "本日の教材" in h:
                    today_mat_cell = cell
                elif "実施区分" in h:
                    exec_div_cell = cell
                elif "確認テスト" in h:
                    confirm_test_cell = cell

            # ヘッダーで見つからなかった場合のフォールバック（後ろからの相対位置）
            if not info_cell:
                # 倒数6番目前後
                for cell in tds:
                    c_text = cell.get_text()
                    if "単元：" in c_text or "単元:" in c_text:
                        info_cell = cell
                        break

            # 教材・単元情報のパース
            unit_name = DEFAULT_EMPTY_VALUE
            middle_unit = DEFAULT_EMPTY_VALUE
            textbook = DEFAULT_EMPTY_VALUE
            problem_code = DEFAULT_EMPTY_VALUE

            if info_cell:
                info_text = info_cell.get_text("\n")
                lines = [normalize_text(l) for l in info_text.splitlines() if normalize_text(l)]
                for line in lines:
                    if line.startswith("単元：") or line.startswith("単元:"):
                        unit_name = re.sub(r"^単元[：:]\s*", "", line).strip() or DEFAULT_EMPTY_VALUE
                    elif line.startswith("中単元：") or line.startswith("中単元:"):
                        middle_unit = re.sub(r"^中単元[：:]\s*", "", line).strip() or DEFAULT_EMPTY_VALUE
                    elif line.startswith("教材：") or line.startswith("教材:"):
                        textbook = re.sub(r"^教材[：:]\s*", "", line).strip() or DEFAULT_EMPTY_VALUE
                    elif line.startswith("問題コード：") or line.startswith("問題コード:"):
                        problem_code = re.sub(r"^問題コード[：:]\s*", "", line).strip() or DEFAULT_EMPTY_VALUE

            # 得点・配点・得点率
            score, max_score, score_rate = DEFAULT_EMPTY_VALUE, DEFAULT_EMPTY_VALUE, DEFAULT_EMPTY_VALUE
            if score_cell:
                score, max_score, score_rate = parse_score_and_max(score_cell.get_text())

            # 実施日
            exec_date_obj = None
            exec_date_str = DEFAULT_EMPTY_VALUE
            if date_cell:
                exec_date_obj = parse_date(date_cell.get_text())
                if exec_date_obj:
                    exec_date_str = format_date(exec_date_obj)

            # 実施中判定 (仕様書§12: 実施日に有効な日付が存在する場合 True、なければ False)
            is_executed = (exec_date_obj is not None)

            # 実施タイミング判定 (仕様書§13 & ユーザー決定)
            # 単元自体は複数ターゲットに対応するため、レコード単位の初期タイミングを一旦計算
            timing = TimingCategory.UNEXECUTED
            if not is_executed:
                timing = TimingCategory.UNEXECUTED
            else:
                timing = TimingCategory.ON_TIME # 後でターゲット別に正確に再判定

            today_textbook = normalize_text(today_mat_cell.get_text()) if today_mat_cell else DEFAULT_EMPTY_VALUE
            if not today_textbook:
                today_textbook = DEFAULT_EMPTY_VALUE

            execution_division = normalize_text(exec_div_cell.get_text()) if exec_div_cell else DEFAULT_EMPTY_VALUE
            if not execution_division:
                execution_division = DEFAULT_EMPTY_VALUE

            confirm_test = normalize_text(confirm_test_cell.get_text()) if confirm_test_cell else DEFAULT_EMPTY_VALUE
            if not confirm_test:
                confirm_test = DEFAULT_EMPTY_VALUE

            units.append(UnitRecord(
                unit_no=unit_no,
                unit_name=unit_name,
                middle_unit=middle_unit,
                textbook=textbook,
                problem_code=problem_code,
                score=score,
                max_score=max_score,
                score_rate=score_rate,
                execution_date=exec_date_str,
                timing=timing,
                is_executed=is_executed,
                today_textbook=today_textbook,
                execution_division=execution_division,
                confirm_test=confirm_test,
                target_checks=target_checks,
            ))

        return units
