"""
安全Excelファイル書き出しエンジン (仕様書§28 & ユーザー合意決定)
"""
import os
import shutil
from datetime import datetime
from typing import Optional
import openpyxl

from src.exporter.excel_exporter import ExcelExporter
from src.utils.logger import get_logger
from src.utils.constants import DEFAULT_OUTPUT_DIR

class SafeExcelWriter:
    def __init__(self, exporter: ExcelExporter, output_dir: Optional[str] = None):
        self.exporter = exporter
        self.output_dir = output_dir if output_dir is not None else DEFAULT_OUTPUT_DIR
        self.logger = get_logger()
        os.makedirs(self.output_dir, exist_ok=True)

    def export_final(self) -> str:
        """
        最終Excelファイルを安全に出力
        命名: Curriculum_Analyzer_v2.0.0_YYYYMMDD_HHMMSS.xlsx
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Curriculum_Analyzer_v2.0.0_{timestamp}.xlsx"
        target_path = os.path.join(self.output_dir, filename)
        return self._safe_write(target_path, is_checkpoint=False)

    def export_checkpoint(self, checkpoint_count: int) -> str:
        """
        中間保存Excelファイルを出力
        命名: Curriculum_Analyzer_v2.0.0_checkpoint_{count}_{timestamp}.xlsx
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Curriculum_Analyzer_v2.0.0_checkpoint_{checkpoint_count}_{timestamp}.xlsx"
        target_path = os.path.join(self.output_dir, filename)
        return self._safe_write(target_path, is_checkpoint=True)

    def _safe_write(self, target_path: str, is_checkpoint: bool = False) -> str:
        """一時ファイル書き出し -> 健全性検証 -> 正式ファイルへの配置"""
        tmp_filename = f"~tmp_{os.path.basename(target_path)}"
        tmp_path = os.path.join(self.output_dir, tmp_filename)

        try:
            self.logger.info(f"Excel生成開始: {os.path.basename(target_path)}")
            wb = self.exporter.generate_workbook()
            wb.save(tmp_path)
            wb.close()

            # 健全性検証 (仕様書§28)
            verify_wb = openpyxl.load_workbook(tmp_path, read_only=True)
            sheet_names = verify_wb.sheetnames
            verify_wb.close()

            if len(sheet_names) != 5:
                raise ValueError(f"生成されたExcelのシート数が不正です: {sheet_names}")

            # 正式ファイルへの配置 (ロックされている場合は別名保存)
            final_path = target_path
            try:
                if os.path.exists(final_path):
                    os.replace(tmp_path, final_path)
                else:
                    shutil.move(tmp_path, final_path)
            except (PermissionError, OSError) as pe:
                # ファイルがExcel等で開かれている場合
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
