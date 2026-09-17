"""
カリキュラム一覧HTMLパーサー (v2.0.0)
"""
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

from src.models.curriculum import CurriculumOverview
from src.models.state import ProcessState
from src.utils.normalization import normalize_text

class ListParser:
    def parse(self, html: str, classroom_name: str = "", classroom_code: str = "", school_year: str = "") -> List[CurriculumOverview]:
        """一覧画面HTMLから全授業行を抽出"""
        soup = BeautifulSoup(html, "lxml")
        results: List[CurriculumOverview] = []

        # 教室名・教室コード・年度の抽出 (HTML内に存在する場合)
        if not classroom_name:
            cr_el = soup.find(class_=lambda c: c and any(k in c for k in ["branch-name", "classroom-name", "search-branch"]))
            if cr_el:
                classroom_name = normalize_text(cr_el.get_text())

        if not classroom_code:
            code_input = soup.find("input", attrs={"placeholder": re.compile(r"教室コード")})
            if code_input and code_input.get("value"):
                classroom_code = normalize_text(code_input["value"])

        if not school_year:
            year_sel = soup.find("select", class_=lambda c: c and "school-year" in c)
            if year_sel:
                opt = year_sel.find("option", selected=True)
                if opt:
                    school_year = normalize_text(opt.get_text())

        # 対象テーブルの探索
        tables = soup.find_all("table")
        target_table = None
        for tbl in tables:
            headers = [normalize_text(th.get_text()) for th in tbl.find_all("th")]
            if any("生徒" in h for h in headers) and any("シミュレーションシート" in h or "カリキュラム" in h for h in headers):
                target_table = tbl
                break

        if not target_table and len(tables) > 1:
            target_table = tables[1]
        elif not target_table and tables:
            target_table = tables[0]

        if not target_table:
            return results

        # ヘッダー列インデックスの決定
        header_map: Dict[str, int] = {}
        thead = target_table.find("thead")
        header_row = thead.find("tr") if thead else target_table.find("tr")
        if header_row:
            for idx, th in enumerate(header_row.find_all(["th", "td"])):
                txt = normalize_text(th.get_text())
                if "学校" in txt or "コース" in txt:
                    header_map["school_course"] = idx
                elif "学年" in txt:
                    header_map["grade"] = idx
                elif "受講区分" in txt:
                    header_map["division"] = idx
                elif "科目" in txt:
                    header_map["subject"] = idx
                elif "生徒" in txt:
                    header_map["student"] = idx

        tbody = target_table.find("tbody")
        rows = tbody.find_all("tr") if tbody else target_table.find_all("tr")[1:]

        for r_idx, tr in enumerate(rows):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 5:
                continue

            school_course = ""
            grade = ""
            division = ""
            subject = ""
            student_raw = ""
            student_id = ""
            student_name = ""

            # ヘッダーマップを利用
            if "school_course" in header_map and header_map["school_course"] < len(tds):
                school_course = normalize_text(tds[header_map["school_course"]].get_text())
            if "grade" in header_map and header_map["grade"] < len(tds):
                grade = normalize_text(tds[header_map["grade"]].get_text())
            if "division" in header_map and header_map["division"] < len(tds):
                division = normalize_text(tds[header_map["division"]].get_text())
            if "subject" in header_map and header_map["subject"] < len(tds):
                subject = normalize_text(tds[header_map["subject"]].get_text())
            if "student" in header_map and header_map["student"] < len(tds):
                student_raw = normalize_text(tds[header_map["student"]].get_text())
            else:
                # フォールバック (sampleMSL.htmlの構造: [在籍, 学校/コース, 学年, 受講区分, 科目, 生徒, 受講, ...])
                if len(tds) >= 6:
                    school_course = normalize_text(tds[1].get_text())
                    grade = normalize_text(tds[2].get_text())
                    division = normalize_text(tds[3].get_text())
                    subject = normalize_text(tds[4].get_text())
                    student_raw = normalize_text(tds[5].get_text())

            # 生徒番号と生徒名の分割 (例: '00000001山田太郎' または '00000001 山田太郎')
            m = re.search(r"^([A-Za-z0-9_\-]+)\s*(.*)", student_raw)
            if m:
                student_id = m.group(1).strip()
                student_name = m.group(2).strip()
            else:
                student_id = student_raw
                student_name = student_raw

            results.append(CurriculumOverview(
                classroom_name=classroom_name,
                classroom_code=classroom_code,
                school_year=school_year,
                student_id=student_id,
                student_name=student_name,
                grade=grade,
                division=division,
                subject=subject,
                school_course=school_course,
                row_index=r_idx,
                status=ProcessState.UNFETCHED,
            ))

        return results
