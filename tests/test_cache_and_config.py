"""
キャッシュ復旧および設定ファイル安全性のテスト (仕様書 v9 §33, §34, §40.6, §44)
"""

import json
import os
from pathlib import Path
from typing import Any
import pytest

from core.constants import CACHE_FILENAME, CACHE_TMP_FILENAME, CACHE_SCHEMA_VERSION
from core.models import CurriculumRecord
from core.cache import CacheManager
from core.config import (
    DEFAULT_SELECTORS,
    validate_selectors,
    load_selectors,
    run_startup_self_diagnosis,
)


def test_cache_normal_save_and_load(tmp_path):
    """キャッシュの正常なアトミック保存と復元"""
    mgr = CacheManager(str(tmp_path))
    records = [
        CurriculumRecord(
            student_id="1001",
            division="通常",
            subject="英語",
            raw_instruction="作成者:田中",
            classroom_name="本校",
        ),
        CurriculumRecord(
            student_id="1002",
            division="通常",
            subject="数学",
            raw_instruction="作成者:佐藤",
            classroom_name="分校",
        ),
    ]

    mgr.save(records, "1.0.0")
    assert mgr.exists()

    loaded, skip_count, status = mgr.load()
    assert status == "ok"
    assert skip_count == 0
    assert len(loaded) == 2
    assert loaded[0].student_id == "1001"
    assert loaded[0].classroom_name == "本校"


def test_cache_partial_corrupted_lines_recovery(tmp_path):
    """v9 §33.4: 不正行が存在しても有効行を最大限復元できること"""
    mgr = CacheManager(str(tmp_path))
    cache_file = tmp_path / CACHE_FILENAME

    lines = [
        json.dumps({"__meta__": True, "schema_version": CACHE_SCHEMA_VERSION, "record_count": 2}),
        json.dumps({"student_id": "REC_1", "division": "通常", "subject": "国語", "raw_instruction": "inst1"}),
        "THIS_IS_A_CORRUPTED_NON_JSON_LINE",
        json.dumps({"student_id": "REC_2", "division": "通常", "subject": "理科", "raw_instruction": "inst2"}),
        json.dumps({"student_id": "", "division": "通常", "subject": "社会"}),  # student_id欠損行
    ]
    cache_file.write_text("\n".join(lines), encoding="utf-8")

    loaded, skip_count, status = mgr.load()
    assert status == "partial"
    assert len(loaded) == 2
    assert skip_count == 2
    assert loaded[0].student_id == "REC_1"
    assert loaded[1].student_id == "REC_2"


def test_cache_corrupted_meta_line_recovery(tmp_path):
    """v9 §33.4: メタ行破損時でも後続の有効データ行から復旧できること"""
    mgr = CacheManager(str(tmp_path))
    cache_file = tmp_path / CACHE_FILENAME

    lines = [
        "BROKEN_META_HEADER_LINE",
        json.dumps({"student_id": "REC_RECOVERED", "division": "通常", "subject": "英語", "raw_instruction": "test"}),
    ]
    cache_file.write_text("\n".join(lines), encoding="utf-8")

    loaded, skip_count, status = mgr.load()
    assert status == "partial"
    assert len(loaded) == 1
    assert loaded[0].student_id == "REC_RECOVERED"
    # 復旧不能でも即時削除されないこと
    assert cache_file.exists()


def test_cache_orphan_tmp_cleanup(tmp_path):
    """v9 §37.4: クラッシュ等で残された一時ファイル (.tmp) の自動整理"""
    mgr = CacheManager(str(tmp_path))
    tmp_file = tmp_path / CACHE_TMP_FILENAME
    tmp_file.write_text("orphan content", encoding="utf-8")
    assert tmp_file.exists()

    cleaned = mgr.cleanup_orphan_tmp_files()
    assert cleaned == 1
    assert not tmp_file.exists()


def test_selectors_validation():
    """v9 §34.1: selectors.json の構文・必須キー・型検証"""
    # 1. 正常系
    valid, err = validate_selectors(DEFAULT_SELECTORS)
    assert valid is True
    assert err == ""

    # 2. ルートがオブジェクトでない
    valid, err = validate_selectors(["not_a_dict"])
    assert valid is False
    assert "辞書型" in err

    # 3. 必須キー欠落
    incomplete = {
        "classroom_name": ["div"],
        "classroom_code": ["input"],
        # school_year, target_table 欠落
    }
    valid, err = validate_selectors(incomplete)
    assert valid is False
    assert "必須キー" in err

    # 4. 値の型がリストでない
    bad_type: dict[str, Any] = dict(DEFAULT_SELECTORS)
    bad_type["classroom_name"] = ".branch-name"
    valid, err = validate_selectors(bad_type)
    assert valid is False
    assert "配列（リスト）" in err

    # 5. 空リスト
    empty_list = dict(DEFAULT_SELECTORS)
    empty_list["classroom_name"] = []
    valid, err = validate_selectors(empty_list)
    assert valid is False
    assert "空です" in err


def test_startup_self_diagnosis(tmp_path):
    """v9 §44: 起動時の自己診断テスト"""
    user_data = tmp_path / "user_data"
    output_dir = tmp_path / "Downloads"
    selectors_file = tmp_path / "selectors.json"
    selectors_file.write_text(json.dumps(DEFAULT_SELECTORS), encoding="utf-8")

    # 正常な環境
    errors = run_startup_self_diagnosis(
        base_dir=str(tmp_path),
        selectors_path=str(selectors_file),
        user_data_dir=str(user_data),
        output_dir=str(output_dir),
    )
    assert len(errors) == 0

    # 壊れた selectors.json が存在する場合
    selectors_file.write_text("{ broken json", encoding="utf-8")
    errors2 = run_startup_self_diagnosis(
        base_dir=str(tmp_path),
        selectors_path=str(selectors_file),
        user_data_dir=str(user_data),
        output_dir=str(output_dir),
    )
    assert len(errors2) == 1
    assert "セレクタ設定ファイルに異常があります" in errors2[0]


def test_config_manager_cp932_fallback(tmp_path):
    """Windowsメモ帳等でShift-JIS(CP932)保存されたconfig.iniが正常に読めることの検証"""
    from core.config import ConfigManager
    config_file = tmp_path / "config.ini"
    cp932_text = (
        "# 日本語コメント\n"
        "[General]\n"
        "base_url = http://10.200.5.191/\n"
        "ignore_ssl_errors = false\n\n"
        "[Display]\n"
        "zoom_factor = 1.0\n"
    )
    config_file.write_bytes(cp932_text.encode("cp932"))

    mgr = ConfigManager(str(config_file))
    config = mgr.load()
    assert config.base_url == "http://10.200.5.191/"
    # バックアップが作成されていない（破損扱いになっていない）こと
    assert not (tmp_path / "config.ini.bak").exists()


def test_resolve_base_dir_with_sys_argv(monkeypatch, tmp_path):
    """Nuitka Onefile環境でsys.argv[0]からEXE配置ディレクトリが解決されることの検証"""
    import sys
    from main import _resolve_base_dir

    fake_exe = tmp_path / "Curriculum_Analyzer.exe"
    fake_exe.touch()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", [str(fake_exe)])
    monkeypatch.setattr(sys, "executable", "C:\\Temp\\onefile_123\\Curriculum_Analyzer.exe")

    resolved = _resolve_base_dir()
    assert resolved == str(tmp_path)


def test_create_release_zip_bundles_existing_config(tmp_path, monkeypatch):
    """build.pyのcreate_release_zipが手元のconfig.ini（URL設定済み）をそのまま同梱することの検証"""
    import zipfile
    import build

    # ダミー環境構築
    monkeypatch.setattr(build, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(build, "BASE_DIR", tmp_path)
    zip_target = tmp_path / build.ZIP_NAME
    monkeypatch.setattr(build, "ZIP_NAME", zip_target.name)

    # ダミーEXE
    fake_exe = tmp_path / "Curriculum_Analyzer.exe"
    fake_exe.write_bytes(b"dummy_exe_content")

    # 手元のconfig.ini (ローカルIP設定)
    config_ini = tmp_path / "config.ini"
    config_ini.write_text("[General]\nbase_url = http://10.200.5.191/\n", encoding="utf-8")

    out_zip = build.create_release_zip(fake_exe)
    assert out_zip.exists()

    # ZIP内を検証
    with zipfile.ZipFile(out_zip, "r") as zf:
        assert "config.ini" in zf.namelist()
        bundled_config = zf.read("config.ini").decode("utf-8")
        assert "base_url = http://10.200.5.191/" in bundled_config


def test_prompt_for_base_url_input(monkeypatch):
    """_prompt_for_base_url の入力成功およびキャンセルのテスト"""
    from PyQt6.QtWidgets import QInputDialog
    from main import _prompt_for_base_url

    # 1. 正常入力
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("http://10.200.5.191/", True))
    url, ok = _prompt_for_base_url()
    assert ok is True
    assert url == "http://10.200.5.191/"

    # 2. キャンセル
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("", False))
    url, ok = _prompt_for_base_url()
    assert ok is False
    assert url == ""


def test_cache_student_name_and_grade_persistence(tmp_path):
    """キャッシュ (JSONL) への生徒名・学年の保存と完全復元テスト"""
    mgr = CacheManager(str(tmp_path))
    records = [
        CurriculumRecord(
            student_id="STU_1001",
            student_name="山田 太郎",
            grade="高3",
            division="通常授業",
            subject="英語",
            raw_instruction="作成者:講師A",
            classroom_name="天王寺校",
            classroom_code="C01",
            school_year="2026年度",
        ),
        CurriculumRecord(
            student_id="STU_1002",
            student_name="佐藤 花子",
            grade="中2",
            division="夏期講習",
            subject="数学",
            raw_instruction="作成者:講師B",
            classroom_name="梅田校",
            classroom_code="C02",
            school_year="2026年度",
        ),
    ]

    mgr.save(records, "1.0.0")
    assert mgr.exists()

    loaded, skip_count, status = mgr.load()
    assert status == "ok"
    assert skip_count == 0
    assert len(loaded) == 2

    assert loaded[0].student_id == "STU_1001"
    assert loaded[0].student_name == "山田 太郎"
    assert loaded[0].grade == "高3"
    assert loaded[0].classroom_name == "天王寺校"

    assert loaded[1].student_id == "STU_1002"
    assert loaded[1].student_name == "佐藤 花子"
    assert loaded[1].grade == "中2"



