"""
ソフト更新確認ユーティリティ (updater.py) のユニットテスト
"""
from unittest.mock import MagicMock, patch
import httpx

from src.utils.constants import APP_VERSION, PORTAL_PAGE_URL
from src.utils.updater import (
    parse_version,
    is_newer_version,
    check_for_updates,
)


def test_parse_version():
    assert parse_version("v2.2.0") == (2, 2, 0)
    assert parse_version("2.1.0") == (2, 1, 0)
    assert parse_version("v2.2") == (2, 2, 0)
    assert parse_version("") == (0, 0, 0)


def test_is_newer_version():
    assert is_newer_version("2.2.0", "v2.3.0") is True
    assert is_newer_version("2.2.0", "2.2.1") is True
    assert is_newer_version("2.2.0", "v2.2.0") is False
    assert is_newer_version("2.2.0", "v2.1.0") is False
    assert is_newer_version("2.2.0", "1.1.0") is False


def test_check_for_updates_from_ver_json_has_update():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "latest": "2.3",
        "latestTag": "v2.3.0",
        "versions": [
            {
                "version": "2.3",
                "tag": "v2.3.0",
                "description": "新機能テストリリース",
            }
        ],
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value.get.return_value = mock_resp

    with patch("src.utils.updater.httpx.Client", return_value=mock_client):
        res = check_for_updates(current_version="2.2.0")
        assert res.error is None
        assert res.has_update is True
        assert res.current_version == "2.2.0"
        assert res.latest_version == "2.3.0"
        assert res.download_url == PORTAL_PAGE_URL
        assert "新機能テストリリース" in res.release_notes


def test_check_for_updates_from_ver_json_already_latest():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "latest": "2.2",
        "latestTag": "v2.2.0",
        "versions": [],
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value.get.return_value = mock_resp

    with patch("src.utils.updater.httpx.Client", return_value=mock_client):
        res = check_for_updates(current_version="2.2.0")
        assert res.error is None
        assert res.has_update is False
        assert res.latest_version == "2.2.0"


def test_check_for_updates_fallback_to_github_api():
    # 1回目 (ver.json) は例外、2回目 (GitHub Releases API) は成功
    mock_api_resp = MagicMock()
    mock_api_resp.raise_for_status.return_value = None
    mock_api_resp.json.return_value = {
        "tag_name": "v2.4.0",
        "body": "API経由のリリースノート",
    }

    call_count = {"n": 0}

    def side_effect_get(url):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.ConnectError("ver.json unreachable")
        return mock_api_resp

    mock_client = MagicMock()
    mock_client.__enter__.return_value.get.side_effect = side_effect_get

    with patch("src.utils.updater.httpx.Client", return_value=mock_client):
        res = check_for_updates(current_version="2.2.0")
        assert res.error is None
        assert res.has_update is True
        assert res.latest_version == "2.4.0"
        assert res.release_notes == "API経由のリリースノート"
        assert call_count["n"] == 2


def test_check_for_updates_both_fail_returns_error():
    mock_client = MagicMock()
    mock_client.__enter__.return_value.get.side_effect = httpx.ConnectTimeout("timeout")

    with patch("src.utils.updater.httpx.Client", return_value=mock_client):
        res = check_for_updates(current_version=APP_VERSION)
        assert res.has_update is False
        assert res.error is not None

