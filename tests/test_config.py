import os
import configparser
from pathlib import Path
from src.utils.constants import DEFAULT_OUTPUT_DIR
from src.utils.config import AppConfig
from src.exporter.safe_writer import SafeExcelWriter

def test_default_output_dir_is_user_downloads():
    expected = str(Path.home() / "Downloads")
    assert DEFAULT_OUTPUT_DIR == expected

def test_app_config_output_dir_default_and_not_in_ini(tmp_path):
    ini_file = tmp_path / "config.ini"
    selectors_file = tmp_path / "selectors.json"
    
    # 新規設定のロード
    config = AppConfig(config_path=str(ini_file), selectors_path=str(selectors_file))
    assert config.output_dir == DEFAULT_OUTPUT_DIR
    
    # 保存した config.ini に output_dir が含まれていないこと
    config.save()
    assert ini_file.exists()
    
    parser = configparser.ConfigParser()
    parser.read(str(ini_file), encoding="utf-8")
    assert "export" in parser
    assert "output_dir" not in parser["export"]
    assert "checkpoint_interval" in parser["export"]

def test_app_config_ignores_legacy_output_dir_in_ini(tmp_path):
    # 仮に古い config.ini に output_dir が書かれていても読み込まないこと
    ini_file = tmp_path / "config.ini"
    ini_file.write_text("[export]\noutput_dir = /some/old/path\ncheckpoint_interval = 200\n", encoding="utf-8")
    
    config = AppConfig(config_path=str(ini_file), selectors_path=str(tmp_path / "selectors.json"))
    assert config.output_dir == DEFAULT_OUTPUT_DIR
    assert config.checkpoint_interval == 200

def test_safe_excel_writer_default_output_dir():
    writer = SafeExcelWriter(exporter=None)
    assert writer.output_dir == DEFAULT_OUTPUT_DIR
