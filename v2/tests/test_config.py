import configparser
import os
import re
from datetime import datetime
from pathlib import Path
from src.utils.constants import DEFAULT_OUTPUT_DIR, DEFAULT_EXCEL_FILENAME_FORMAT
from src.utils.config import AppConfig
from src.exporter.safe_writer import SafeExcelWriter, format_excel_filename


def test_default_output_dir_is_user_downloads():
    expected = str(Path.home() / "Downloads")
    assert DEFAULT_OUTPUT_DIR == expected


def test_default_excel_filename_format_constant():
    assert DEFAULT_EXCEL_FILENAME_FORMAT == "分析結果_yymmdd-hhmmss.xlsx"


def test_app_config_output_dir_and_filename_format_default_and_not_in_ini(tmp_path):
    ini_file = tmp_path / "config.ini"
    selectors_file = tmp_path / "selectors.json"

    # 新規設定のロード
    config = AppConfig(config_path=str(ini_file), selectors_path=str(selectors_file))
    assert config.output_dir == DEFAULT_OUTPUT_DIR
    assert config.excel_filename_format == "分析結果_yymmdd-hhmmss.xlsx"

    # 保存した config.ini に output_dir や excel_filename_format が含まれていないこと
    config.save()
    assert ini_file.exists()

    parser = configparser.ConfigParser()
    parser.read(str(ini_file), encoding="utf-8")
    assert "export" in parser
    assert "output_dir" not in parser["export"]
    assert "excel_filename_format" not in parser["export"]
    assert "checkpoint_interval" in parser["export"]


def test_app_config_ignores_legacy_output_dir_and_filename_format_in_ini(tmp_path):
    # 仮に config.ini に output_dir や excel_filename_format が書かれていても読み込まないこと
    ini_file = tmp_path / "config.ini"
    ini_file.write_text(
        "[export]\noutput_dir = /some/old/path\nexcel_filename_format = custom.xlsx\ncheckpoint_interval = 200\n",
        encoding="utf-8",
    )

    config = AppConfig(config_path=str(ini_file), selectors_path=str(tmp_path / "selectors.json"))
    assert config.output_dir == DEFAULT_OUTPUT_DIR
    assert config.excel_filename_format == "分析結果_yymmdd-hhmmss.xlsx"
    assert config.checkpoint_interval == 200


def test_format_excel_filename_yymmdd_hhmmss():
    fixed_dt = datetime(2026, 11, 2, 17, 39, 19)
    filename = format_excel_filename("分析結果_yymmdd-hhmmss.xlsx", now=fixed_dt)
    assert filename == "分析結果_261102-173919.xlsx"


def test_safe_excel_writer_default_output_dir_and_filename_format():
    writer = SafeExcelWriter(exporter=None)
    assert writer.output_dir == DEFAULT_OUTPUT_DIR
    assert writer.filename_format == "分析結果_yymmdd-hhmmss.xlsx"


def test_safe_excel_writer_export_final_filename_pattern(tmp_path):
    from src.database.db_manager import DatabaseManager
    from src.database.repository import Repository
    from src.exporter.excel_exporter import ExcelExporter

    db_manager = DatabaseManager(str(tmp_path / "test_fn.db"))
    repo = Repository(db_manager)
    exporter = ExcelExporter(repo)
    out_dir = tmp_path / "out"
    writer = SafeExcelWriter(exporter=exporter, output_dir=str(out_dir))

    xlsx_path = writer.export_final()
    basename = os.path.basename(xlsx_path)
    assert re.match(r"^分析結果_\d{6}-\d{6}\.xlsx$", basename), f"Unexpected filename: {basename}"
