"""
キャッシュ復旧および設定ファイル安全性のテスト (仕様書 v9 §33, §34, §40.6, §44)
"""

import json
import os
from pathlib import Path
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
    bad_type = dict(DEFAULT_SELECTORS)
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
