"""
JSONLキャッシュ管理
"""
import json
import os
import time
from datetime import datetime, timezone
import logging
from typing import List, Tuple, Dict

from core.constants import CACHE_SCHEMA_VERSION, CACHE_FILENAME, CACHE_TMP_FILENAME, CACHE_RETRY_MAX, CACHE_RETRY_INTERVAL_MS
from core.models import CurriculumRecord

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = cache_dir

    @property
    def cache_path(self) -> str:
        return os.path.join(self.cache_dir, CACHE_FILENAME)

    @property
    def _tmp_path(self) -> str:
        return os.path.join(self.cache_dir, CACHE_TMP_FILENAME)

    def exists(self) -> bool:
        return os.path.exists(self.cache_path)

    def delete(self) -> bool:
        """キャッシュファイルを物理削除する"""
        if self.exists():
            try:
                os.remove(self.cache_path)
                return True
            except Exception as e:
                logger.error(f"Cache delete failed: {e}")
                return False
        return True

    def save(self, records: List[CurriculumRecord], app_version: str) -> None:
        """アトミック保存: tmpへ書き込み、flush, fsync, replace"""
        tmp_path = self._tmp_path
        target_path = self.cache_path

        meta_line = {
            "__meta__": True,
            "schema_version": CACHE_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(records),
            "app_version": app_version
        }

        for attempt in range(CACHE_RETRY_MAX):
            try:
                with open(tmp_path, "w", encoding="utf-8", newline="") as f:
                    # write meta
                    f.write(json.dumps(meta_line, ensure_ascii=False) + "\n")
                    
                    # write records
                    for rec in records:
                        rec_dict = {
                            "student_id": rec.student_id,
                            "division": rec.division,
                            "subject": rec.subject,
                            "raw_instruction": rec.raw_instruction,
                            "meta_cells": rec.meta_cells,
                            "school_year": getattr(rec, "school_year", ""),
                            "classroom_code": getattr(rec, "classroom_code", ""),
                            "classroom_name": getattr(rec, "classroom_name", ""),
                            "student_name": getattr(rec, "student_name", ""),
                            "grade": getattr(rec, "grade", ""),
                        }
                        f.write(json.dumps(rec_dict, ensure_ascii=False) + "\n")
                    
                    f.flush()
                    os.fsync(f.fileno())
                
                os.replace(tmp_path, target_path)
                return
            except Exception as e:
                logger.error(f"Cache save attempt {attempt+1} failed: {e}")
                if attempt < CACHE_RETRY_MAX - 1:
                    time.sleep(CACHE_RETRY_INTERVAL_MS / 1000.0)
                else:
                    raise

    def cleanup_orphan_tmp_files(self) -> int:
        """クラッシュや強制終了等で残された一時ファイル (.tmp) を検出し整理する (v9 §37.4)。

        Returns:
            削除した一時ファイルの数
        """
        cleaned = 0
        if os.path.exists(self._tmp_path):
            try:
                os.remove(self._tmp_path)
                logger.info("孤立したキャッシュ一時ファイル %s を削除しました", self._tmp_path)
                cleaned += 1
            except Exception as e:
                logger.warning("キャッシュ一時ファイルの削除に失敗: %s", e)
        return cleaned

    def load(self) -> Tuple[List[CurriculumRecord], int, str]:
        """
        キャッシュ復元 (v9 §33.4: 各行個別検証・部分復旧対応)
        Returns: (records, skip_count, status)
        status = 'ok', 'partial', 'meta_corrupt', 'not_found'
        """
        if not self.exists():
            return [], 0, "not_found"

        records_dict: Dict[Tuple[str, str, str], CurriculumRecord] = {}
        skip_count = 0
        status = "ok"

        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if not lines:
                return [], 0, "meta_corrupt"

            # 1行目のメタデータ検証
            first_line = lines[0].strip()
            meta_valid = False
            expected_count = -1
            try:
                meta = json.loads(first_line)
                if meta.get("__meta__"):
                    schema_ver = meta.get("schema_version")
                    if isinstance(schema_ver, int) and 1 <= schema_ver <= CACHE_SCHEMA_VERSION:
                        meta_valid = True
                        expected_count = meta.get("record_count", -1)
            except Exception:
                meta_valid = False

            data_lines = lines[1:] if meta_valid else lines
            if not meta_valid:
                status = "partial"
                logger.warning("キャッシュのメタデータ行が無効です。残りの行からレコードの復元を試みます。")

            # 各行を個別にパース・復元 (v9 §33.4)
            for line in data_lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict) or data.get("__meta__"):
                        continue
                    sid = str(data.get("student_id", "")).strip()
                    div = str(data.get("division", "")).strip()
                    sub = str(data.get("subject", "")).strip()
                    if not sid or not sub:
                        skip_count += 1
                        status = "partial"
                        continue

                    key = (sid, div, sub)
                    record = CurriculumRecord(
                        student_id=key[0],
                        division=key[1],
                        subject=key[2],
                        raw_instruction=str(data.get("raw_instruction", "")),
                        meta_cells=data.get("meta_cells", {}),
                        school_year=str(data.get("school_year", "")),
                        classroom_code=str(data.get("classroom_code", "")),
                        classroom_name=str(data.get("classroom_name", "")),
                        student_name=str(data.get("student_name", "")),
                        grade=str(data.get("grade", "")),
                    )
                    records_dict[key] = record
                except Exception:
                    skip_count += 1
                    status = "partial"

            actual_count = len(records_dict)
            if not meta_valid and actual_count == 0:
                return [], skip_count, "meta_corrupt"

            if meta_valid and expected_count != -1 and actual_count != expected_count:
                logger.warning(f"Cache record_count mismatch. expected: {expected_count}, actual: {actual_count}")
                status = "partial"

            if skip_count > 0:
                status = "partial"

            return list(records_dict.values()), skip_count, status

        except Exception as e:
            logger.error(f"Cache load failed entirely: {e}")
            return [], 0, "meta_corrupt"
