"""
安全Excelファイル書き出しエンジン (仕様書§28 & ユーザー合意決定)
- xlsxwriter 直接書き出し + zipfile による軽量・ミリ秒単位の健全性検証 (openpyxl 二重読み込み廃止)
- threading.Lock による並行エクスポート排他保護
"""
import os
import shutil
import threading
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from typing import List, Optional

from src.exporter.excel_exporter import ExcelExporter
from src.utils.logger import get_logger
from src.utils.constants import DEFAULT_OUTPUT_DIR, DEFAULT_EXCEL_SHEETS, APP_NAME


def read_xlsx_sheet_names_fast(xlsx_path: str) -> List[str]:
    """xlsxファイル (ZIPアーカイブ) の xl/workbook.xml からシート名一覧を高速抽出"""
    with zipfile.ZipFile(xlsx_path, "r") as zf:
        with zf.open("xl/workbook.xml") as f:
            tree = ET.parse(f)
    root = tree.getroot()
    sheet_names: List[str] = []
    for elem in root.iter():
        if elem.tag.endswith("sheet"):
            name = elem.attrib.get("name")
            if name:
                sheet_names.append(name)
    return sheet_names


class SafeExcelWriter:
    def __init__(self, exporter: Optional[ExcelExporter] = None, output_dir: Optional[str] = None):
        self.exporter = exporter
        self.output_dir = output_dir if output_dir is not None else DEFAULT_OUTPUT_DIR
        self.logger = get_logger()
        self._lock = threading.Lock()
        os.makedirs(self.output_dir, exist_ok=True)

    def export_final(self) -> str:
        """
        最終Excelファイルを安全に出力
        命名: Curriculum_Analyzer_YYYYMMDD_HHMMSS.xlsx
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{APP_NAME}_{timestamp}.xlsx"
        target_path = os.path.join(self.output_dir, filename)
        return self._safe_write(target_path, is_checkpoint=False)

    def export_checkpoint(self, checkpoint_count: int) -> str:
        """
        中間保存Excelファイルを出力 (非推奨: 中間出力廃止)
        """
        self.logger.debug(f"中間出力は廃止されたためスキップします (count: {checkpoint_count})")
        return ""

    def _safe_write(self, target_path: str, is_checkpoint: bool = False) -> str:
        """一時ファイル書き出し -> 軽量ZIP/XML健全性検証 -> 正式ファイルへの配置"""
        if self.exporter is None:
            raise RuntimeError("ExcelExporterが設定されていないため書き出しできません")

        with self._lock:
            os.makedirs(self.output_dir, exist_ok=True)
            tmp_filename = f"~tmp_{os.path.basename(target_path)}"
            tmp_path = os.path.join(self.output_dir, tmp_filename)

            try:
                self.logger.info(f"Excel生成開始: {os.path.basename(target_path)}")
                self.exporter.export_to(tmp_path)

                # 健全性検証 (仕様書§28: シート欠落・ZIP破損チェック)
                sheet_names = read_xlsx_sheet_names_fast(tmp_path)
                missing_sheets = [s for s in DEFAULT_EXCEL_SHEETS if s not in sheet_names]
                if missing_sheets:
                    raise ValueError(f"生成されたExcelに必要なシートが見つかりません (欠落: {missing_sheets}): {sheet_names}")

                # 正式ファイルへの配置 (ロックされている場合は別名保存)
                final_path = target_path
                try:
                    if os.path.exists(final_path):
                        os.replace(tmp_path, final_path)
                    else:
                        shutil.move(tmp_path, final_path)
                except (PermissionError, OSError):
                    alt_filename = f"conflict_{datetime.now().strftime('%H%M%S')}_{os.path.basename(target_path)}"
                    final_path = os.path.join(self.output_dir, alt_filename)
                    self.logger.warning(f"ファイルがロックされているため別名で保存します: {alt_filename}")
                    shutil.move(tmp_path, final_path)

                self.logger.info(f"Excel出力が正常に完了しました: {final_path}")
                return final_path

            except Exception as e:
                self.logger.error(f"Excel生成中にエラーが発生しました: {e}", exc_info=True)
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                raise
