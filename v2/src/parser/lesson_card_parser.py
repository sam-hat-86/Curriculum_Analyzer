"""
学習カード (class_report.html) HTMLパーサー (v2.0.2)
個人のカリキュラムテーブルにある学習カードから教室名等のメタデータを抽出する。
"""
from typing import Union
from bs4 import BeautifulSoup, Tag
from src.utils.normalization import normalize_text, clean_classroom_name
from src.utils.logger import get_logger


class LessonCardParser:
    """学習カードHTMLの解析クラス"""

    def __init__(self):
        self.logger = get_logger()

    def parse_classroom_name(self, html: str) -> str:
        """
        学習カードHTMLから教室名を抽出。
        例: table.my-lesson-card-left-table の <tr><th>教室</th><td>ＦＳ和泉中央</td></tr>
        見つからない場合は空文字列を返す。
        """
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, "lxml")

            # 1. table.my-lesson-card-left-table を優先探索
            tbl = soup.find("table", class_=lambda c: bool(c and "my-lesson-card-left-table" in c))
            if tbl:
                name = self._extract_classroom_from_table(tbl)
                if name:
                    return name

            # 2. 任意のテーブルから「教室」ヘッダーを探索 (フォールバック)
            for t in soup.find_all("table"):
                name = self._extract_classroom_from_table(t)
                if name:
                    return name

        except Exception as e:
            self.logger.warning(f"学習カードの教室名パースでエラーが発生しました: {e}")

        return ""

    def _extract_classroom_from_table(self, table_soup: Union[Tag, BeautifulSoup]) -> str:
        """テーブル内の行から '教室' に対応する td テキストを取得"""
        for tr in table_soup.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td:
                th_text = normalize_text(th.get_text())
                if "教室" in th_text:
                    return clean_classroom_name(td.get_text())
        return ""


def parse_lesson_card_classroom(html: str) -> str:
    """便利関数: HTMLから教室名を抽出"""
    parser = LessonCardParser()
    return parser.parse_classroom_name(html)

