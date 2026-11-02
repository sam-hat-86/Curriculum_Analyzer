"""
ソフトウェア更新確認ユーティリティ (v2.2.0)
- 第1候補: GitHub Pages の ver.json (API回数制限なし・高速)
- 第2候補: GitHub Releases API (フォールバック)
"""
from dataclasses import dataclass
import re
from typing import Optional, Tuple

import httpx

from src.utils.constants import (
    APP_VERSION,
    PORTAL_PAGE_URL,
    UPDATE_CHECK_VER_JSON_URL,
    UPDATE_CHECK_API_URL,
)
from src.utils.logger import get_logger


@dataclass
class UpdateCheckResult:
    has_update: bool
    current_version: str
    latest_version: str
    download_url: str = PORTAL_PAGE_URL
    release_notes: str = ""
    error: Optional[str] = None


def parse_version(ver_str: str) -> Tuple[int, ...]:
    """
    バージョン文字列 (例: 'v2.2.0', '2.1.0', '2.2') を整数タプル (2, 2, 0) に変換する。
    """
    if not ver_str:
        return (0, 0, 0)
    cleaned = ver_str.strip().lstrip("vV")
    nums = [int(x) for x in re.findall(r"\d+", cleaned)]
    if not nums:
        return (0, 0, 0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def is_newer_version(current_ver: str, latest_ver: str) -> bool:
    """
    latest_ver が current_ver より新しいバージョンであるか判定する。
    """
    return parse_version(latest_ver) > parse_version(current_ver)


def _normalize_version_str(ver_str: str) -> str:
    cleaned = (ver_str or "").strip().lstrip("vV")
    return cleaned if cleaned else APP_VERSION


def check_for_updates(
    current_version: str = APP_VERSION,
    timeout: float = 5.0,
    ver_json_url: str = UPDATE_CHECK_VER_JSON_URL,
    api_url: str = UPDATE_CHECK_API_URL,
) -> UpdateCheckResult:
    """
    最新バージョンを確認し、UpdateCheckResult を返す。
    1. GitHub Pages の ver.json を確認
    2. 失敗時は GitHub Releases API にフォールバック
    """
    logger = get_logger()
    headers = {
        "User-Agent": f"Curriculum-Analyzer/{current_version}",
        "Accept": "application/json",
    }

    # 1. 第1候補: ver.json (GitHub Pages)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(ver_json_url)
            resp.raise_for_status()
            data = resp.json()
            latest_tag = data.get("latestTag") or data.get("latest") or ""
            if latest_tag:
                latest_norm = _normalize_version_str(str(latest_tag))
                has_upd = is_newer_version(current_version, latest_norm)
                desc = ""
                versions = data.get("versions", [])
                if isinstance(versions, list) and versions:
                    first_ver = versions[0]
                    if isinstance(first_ver, dict):
                        desc = str(first_ver.get("description", ""))
                return UpdateCheckResult(
                    has_update=has_upd,
                    current_version=_normalize_version_str(current_version),
                    latest_version=latest_norm,
                    download_url=PORTAL_PAGE_URL,
                    release_notes=desc,
                )
    except Exception as e:
        logger.debug(f"ver.json からの更新確認に失敗 (APIへフォールバックします): {e}")

    # 2. 第2候補: GitHub Releases API
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(api_url)
            resp.raise_for_status()
            data = resp.json()
            tag_name = data.get("tag_name") or data.get("name") or ""
            if tag_name:
                latest_norm = _normalize_version_str(str(tag_name))
                has_upd = is_newer_version(current_version, latest_norm)
                body = str(data.get("body") or "")
                return UpdateCheckResult(
                    has_update=has_upd,
                    current_version=_normalize_version_str(current_version),
                    latest_version=latest_norm,
                    download_url=PORTAL_PAGE_URL,
                    release_notes=body,
                )
            raise ValueError("レスポンスにバージョン情報が含まれていません")
    except Exception as api_err:
        logger.debug(f"GitHub Releases API からの更新確認に失敗: {api_err}")
        return UpdateCheckResult(
            has_update=False,
            current_version=_normalize_version_str(current_version),
            latest_version=_normalize_version_str(current_version),
            download_url=PORTAL_PAGE_URL,
            error=str(api_err),
        )

