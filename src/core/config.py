"""config.ini読み込み・管理モジュール。

仕様書 §9 に準拠したconfig.iniの読み込み・検証・保存を行う。
"""

import configparser
import copy
import json
import logging
import os
import shutil
import tempfile
from typing import Optional

from core.models import AppConfig

logger = logging.getLogger(__name__)

# 有効なBool表記
_TRUTHY: set[str] = {"true", "1", "yes"}
_FALSY: set[str] = {"false", "0", "no"}

# 許可スキーム
_ALLOWED_SCHEMES: tuple[str, ...] = ("http://", "https://", "file:///")

# 安全な上限
_MAX_CHAR_THRESHOLD = 1000
_MAX_COPYPASTE_THRESHOLD = 100


def _parse_bool(value: str, default: bool = False) -> bool:
    """ブール値を解析する。不正値はデフォルトへフォールバック。"""
    v = value.strip().lower()
    if v in _TRUTHY:
        return True
    if v in _FALSY:
        return False
    logger.warning("不正なブール値: '%s' → デフォルト %s へフォールバック", value, default)
    return default


def _validate_base_url(url: str) -> str:
    """base_urlの検証を行う。

    許可スキーム: http://, https://, file:///
    空文字、不正URL、不正スキームは起動エラーとする。
    """
    if not url or not url.strip():
        raise ValueError("base_urlが空です")

    url = url.strip()
    if not any(url.startswith(scheme) for scheme in _ALLOWED_SCHEMES):
        raise ValueError(
            f"base_urlのスキームが不正です: {url}\n"
            f"許可: {', '.join(_ALLOWED_SCHEMES)}"
        )

    return url


def _parse_float_in_range(
    value: str,
    min_val: float,
    max_val: float,
    default: float,
    name: str,
) -> float:
    """数値設定を範囲内で解析する。"""
    try:
        v = float(value.strip())
        if v < min_val or v > max_val:
            logger.warning(
                "%s の値 %s が範囲外 (%s-%s) → デフォルト %s",
                name, v, min_val, max_val, default,
            )
            return default
        return v
    except (ValueError, TypeError):
        logger.warning(
            "%s の値 '%s' が不正 → デフォルト %s", name, value, default
        )
        return default


class ConfigManager:
    """config.iniの読み込み・検証・保存を管理する。"""

    DEFAULT_CONFIG = {
        "General": {
            "base_url": "",
            "ignore_ssl_errors": "false",
        },
        "Display": {
            "zoom_factor": "1.0",
        },
    }

    def __init__(self, config_path: str) -> None:
        self._config_path = config_path
        self._parser = configparser.ConfigParser()
        # 大文字小文字を保持
        self._parser.optionxform = str  # type: ignore[assignment]
        self._raw_lines: Optional[list[str]] = None

    @property
    def config_path(self) -> str:
        return self._config_path

    def load(self) -> AppConfig:
        """config.iniを読み込み、AppConfigを返す。

        仕様書 §9.1:
        - UTF-8 BOMなし/BOM付きの両方を正式対応
        - NULL文字を含む場合は不正
        - Unicodeデコード失敗は破損扱い
        - 破損時はバックアップ退避後にデフォルト設定で再生成
        - 不明キー・不明セクションは保持
        - 不足キーはメモリ上でデフォルト補完
        """
        if not os.path.exists(self._config_path):
            logger.info("config.ini が存在しないため、デフォルト設定で作成します")
            self._create_default()
            return self._build_config_from_defaults()

        try:
            raw_bytes = self._read_file_bytes()
            content = self._decode_content(raw_bytes)
            self._validate_content(content)
            self._raw_lines = content.splitlines(keepends=True)
            self._parser.read_string(content)
        except Exception as e:
            logger.error("config.ini の読み込みに失敗: %s", e)
            self._backup_and_recreate()
            return self._build_config_from_defaults()

        return self._build_config()

    def _read_file_bytes(self) -> bytes:
        """ファイルをバイトとして読み込む。"""
        with open(self._config_path, "rb") as f:
            return f.read()

    def _decode_content(self, raw_bytes: bytes) -> str:
        """UTF-8(BOMあり/なし)でデコードする。"""
        # BOM付きUTF-8
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            return raw_bytes[3:].decode("utf-8")
        # BOMなしUTF-8
        return raw_bytes.decode("utf-8")

    def _validate_content(self, content: str) -> None:
        """コンテンツの検証。NULL文字チェック。"""
        if "\x00" in content:
            raise ValueError("config.ini にNULL文字が含まれています")

    def _backup_and_recreate(self) -> None:
        """破損時のバックアップ退避と再生成。"""
        if os.path.exists(self._config_path):
            backup_path = self._config_path + ".bak"
            try:
                shutil.copy2(self._config_path, backup_path)
                logger.info("破損した config.ini を %s にバックアップしました", backup_path)
            except OSError as e:
                logger.error("バックアップの作成に失敗: %s", e)

        self._create_default()

    def _create_default(self) -> None:
        """デフォルトのconfig.iniを作成する。"""
        self._parser.clear()
        for section, values in self.DEFAULT_CONFIG.items():
            if not self._parser.has_section(section):
                self._parser.add_section(section)
            for key, value in values.items():
                self._parser.set(section, key, value)
        self._save()

    def _build_config_from_defaults(self) -> AppConfig:
        """デフォルト値からAppConfigを生成する。"""
        # base_urlが空ならエラー
        base_url = self.DEFAULT_CONFIG["General"]["base_url"]
        if base_url:
            base_url = _validate_base_url(base_url)
        return AppConfig(
            base_url=base_url,
            ignore_ssl_errors=False,
            zoom_factor=1.0,
        )

    def _build_config(self) -> AppConfig:
        """parserからAppConfigを生成する。"""
        # base_url
        base_url_raw = self._get("General", "base_url", "")
        base_url = _validate_base_url(base_url_raw)

        # ignore_ssl_errors
        ssl_raw = self._get("General", "ignore_ssl_errors", "false")
        ignore_ssl = _parse_bool(ssl_raw, default=False)

        # zoom_factor
        zoom_raw = self._get("Display", "zoom_factor", "1.0")
        zoom = _parse_float_in_range(zoom_raw, 0.5, 2.0, 1.0, "zoom_factor")

        return AppConfig(
            base_url=base_url,
            ignore_ssl_errors=ignore_ssl,
            zoom_factor=zoom,
        )

    def _get(self, section: str, key: str, default: str) -> str:
        """設定値を取得する。不足キーはデフォルト補完。"""
        try:
            return self._parser.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def _save(self) -> None:
        """config.iniをatomicに保存する。

        仕様書 §9.1: tmp→flush→fsync→os.replace
        """
        dir_path = os.path.dirname(self._config_path)
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=dir_path, prefix="_config_", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                self._parser.write(f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._config_path)
        except OSError as e:
            logger.error("config.ini の保存に失敗: %s", e)
            # tmpファイルが残っている場合は削除を試みる
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def update_value(self, section: str, key: str, value: str) -> None:
        """設定値を更新して保存する。

        仕様書 §9.1: 設定値の安全な追記は行ベースの軽量マージ
        """
        if not self._parser.has_section(section):
            self._parser.add_section(section)
        self._parser.set(section, key, value)
        self._save()


DEFAULT_SELECTORS = {
    "classroom_name": [
        "/html/body/div/div/div[2]/div/div[1]/div/table/tbody[2]/tr[1]/td[1]/div/div[2]/div/div/div[2]/div/span/span",
        ".search-branch .has-ellipsis",
        ".search-branch .tag",
        ".taginput .has-ellipsis",
        ".taginput .tag",
        "[data-testid*='classroom-name']",
        ".classroom-name",
    ],
    "classroom_code": [
        ".branch-code-input input",
        "input[placeholder*='教室コード']",
        "input[name*='branch_code']",
        "input[name*='classroom_code']",
    ],
    "school_year": [
        "select.school-year",
        "select[name*='year']",
        "select",
    ],
    "target_table": [
        "table.curriculum-table",
        "table.instruction-table",
        "table",
    ],
    "loading_indicator": [
        ".loading",
        ".spinner",
        ".is-loading",
        ".loading-mask",
        "[aria-busy='true']",
    ],
}


REQUIRED_SELECTOR_KEYS = {
    "classroom_name",
    "classroom_code",
    "school_year",
    "target_table",
}

KNOWN_SELECTOR_KEYS = REQUIRED_SELECTOR_KEYS | {
    "loading_indicator",
}


def validate_selectors(data: any) -> tuple[bool, str]:
    """selectors.jsonの構文・必須キー・型を検証する (v9 §34.1)。

    Returns:
        (is_valid: bool, error_message: str)
    """
    if not isinstance(data, dict):
        return False, "設定のルートはJSONオブジェクト（辞書型）である必要があります"

    for req_key in REQUIRED_SELECTOR_KEYS:
        if req_key not in data:
            return False, f"必須キー '{req_key}' が存在しません"

    for k, v in data.items():
        if k not in KNOWN_SELECTOR_KEYS:
            logger.warning("selectors.json に未知のキー '%s' が存在します（無視して継続します）", k)
        if not isinstance(v, list):
            return False, f"キー '{k}' の値はセレクタ文字列の配列（リスト）である必要があります"
        if not v:
            return False, f"キー '{k}' のセレクタ候補リストが空です"
        for idx, sel in enumerate(v):
            if not isinstance(sel, str) or not sel.strip():
                return False, f"キー '{k}' のインデックス {idx} のセレクタは空でない文字列である必要があります"

    return True, ""


def load_selectors(selectors_path: str) -> tuple[dict, Optional[str]]:
    """selectors.jsonを読み込み、検証する (v8 §8, v9 §34.1)。

    ファイル不在時はデフォルト値で新規生成。
    JSON構文エラーや検証失敗時はデフォルトセレクタとエラーメッセージを返す。

    Returns:
        (selectors_dict, error_message)
    """
    if not os.path.exists(selectors_path):
        logger.info("selectors.json が存在しないため、デフォルトセレクタを生成して使用します")
        try:
            with open(selectors_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_SELECTORS, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return copy.deepcopy(DEFAULT_SELECTORS), None

    try:
        with open(selectors_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        err_msg = f"selectors.json のJSON構文エラー: {e}"
        logger.error(err_msg)
        return copy.deepcopy(DEFAULT_SELECTORS), err_msg

    is_valid, err_msg = validate_selectors(data)
    if not is_valid:
        logger.error("selectors.json の検証エラー: %s", err_msg)
        return copy.deepcopy(DEFAULT_SELECTORS), err_msg

    merged = copy.deepcopy(DEFAULT_SELECTORS)
    for k, v in data.items():
        if isinstance(v, list):
            merged[k] = v
    return merged, None


def run_startup_self_diagnosis(
    base_dir: str,
    selectors_path: str,
    user_data_dir: str,
    output_dir: Optional[str] = None,
) -> list[str]:
    """起動時の自己診断を行う (v9 §44)。

    Returns:
        重大な初期化失敗のエラーメッセージ一覧（空なら正常）
    """
    critical_errors: list[str] = []

    # 1. user_data (キャッシュディレクトリ) への書き込み可否チェック
    try:
        os.makedirs(user_data_dir, exist_ok=True)
        test_file = os.path.join(user_data_dir, ".test_write_perm")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
    except Exception as e:
        critical_errors.append(f"キャッシュディレクトリへの書き込み権限がありません ({user_data_dir}): {e}")

    # 2. 出力ディレクトリへの書き込み可否チェック
    if output_dir:
        try:
            os.makedirs(output_dir, exist_ok=True)
            test_file = os.path.join(output_dir, ".test_output_perm")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_file)
        except Exception as e:
            critical_errors.append(f"Excel出力先ディレクトリへの書き込み権限がありません ({output_dir}): {e}")

    # 3. selectors.json の構文チェック（存在する場合）
    if os.path.exists(selectors_path):
        _, sel_err = load_selectors(selectors_path)
        if sel_err:
            critical_errors.append(f"セレクタ設定ファイルに異常があります: {sel_err}")

    return critical_errors


