"""Nuitka ビルドスクリプト (Standalone / Onefile 対応)。

バージョンは../src/utils/constants.py で一元管理。

仕様書 §43, §52 および DEVELOPER.md §4 に準拠:
- __file__基準でパスを解決
- cwdへ依存しない
- venv利用を推奨/チェック
- 必須ライブラリ事前確認 (nuitka, PySide6, playwright, openpyxl 等)
- コンソール画面非表示 (--windows-console-mode=disable)
- アプリアイコン指定 (--windows-icon-from-ico)
- stdout/stderrをリアルタイム表示
- ビルド用生成物を清掃
- ファイルロック時は中止
- Standalone（フォルダ形式ZIP・推奨）および Onefile（単一EXE）の両モードに対応
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# Windowsコンソール文字化け・例外防止
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ==========================================
# バージョン・ビルド設定 (src/utils/constants.py と連動)
# ==========================================

# __file__基準でパス解決 (tools/ の親 = プロジェクトルート)
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# constants.py からバージョン・定数を一元インポート
from src.utils.constants import APP_VERSION, APP_NAME, EXE_NAME, ZIP_NAME

VERSION = APP_VERSION
SRC_DIR = BASE_DIR / "src"
MAIN_PY = SRC_DIR / "main.py"
MAJOR_VERSION = VERSION.split(".")[0]
OUTPUT_DIR = BASE_DIR / "output" / f"v{MAJOR_VERSION}"
ICON_PATH = Path(__file__).resolve().parent / "MSL分析ロゴ.ico"

# スタンドアロン配布用名称
STANDALONE_DIR_NAME = f"{APP_NAME}_v{VERSION}"
STANDALONE_ZIP_NAME = f"{APP_NAME}_v{VERSION}_standalone.zip"


def sync_docs_version() -> None:
    """docs/script.js のバージョンおよびダウンロードファイル名を constants.py と同期する。"""
    import re
    script_js_path = BASE_DIR / "docs" / "script.js"
    if not script_js_path.exists():
        return

    content = script_js_path.read_text(encoding="utf-8")
    content = re.sub(
        r"const APP_VERSION = ['\"].*?['\"];",
        f"const APP_VERSION = '{VERSION}';",
        content,
    )
    content = re.sub(
        r"const DOWNLOAD_FILENAME = .*?;",
        r"const DOWNLOAD_FILENAME = `Curriculum_Analyzer_v${APP_VERSION}_standalone.zip`;",
        content,
    )
    script_js_path.write_text(content, encoding="utf-8")
    print(f"  [OK] docs/script.js のバージョンを v{VERSION} に同期しました。")


def check_venv(auto_yes: bool = False) -> None:
    """venv環境を確認する。"""
    if sys.prefix == sys.base_prefix:
        print("WARNING: 仮想環境(venv)が有効ではありません。")
        print("  推奨: python -m venv venv && venv\\Scripts\\activate")
        if auto_yes or not sys.stdin.isatty():
            print("  自動継続フラグまたは非対話環境を検知しました。続行します。")
            return
        response = input("続行しますか? (y/N): ").strip().lower()
        if response != "y":
            print("ビルドを中止しました。")
            sys.exit(1)


def check_dependencies() -> None:
    """必須ライブラリの存在確認。"""
    required = ["nuitka", "PySide6", "PySide6.QtWebEngineWidgets", "playwright", "bs4", "lxml", "httpx", "openpyxl"]
    missing = []

    for pkg in required:
        try:
            if pkg == "PySide6.QtWebEngineWidgets":
                import PySide6.QtWebEngineWidgets
            elif pkg == "PySide6":
                import PySide6
            elif pkg == "nuitka":
                import nuitka
            elif pkg == "playwright":
                import playwright
            elif pkg == "bs4":
                import bs4
            elif pkg == "lxml":
                import lxml
            elif pkg == "httpx":
                import httpx
            elif pkg == "openpyxl":
                import openpyxl
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"ERROR: 以下のライブラリが不足しています: {', '.join(missing)}")
        print("  pip install -r requirements.txt を実行してください。")
        sys.exit(1)


def check_file_lock(target_path: Path) -> None:
    """出力ファイルのファイルロック確認。"""
    if target_path.exists():
        try:
            if target_path.is_file():
                with open(target_path, "ab"):
                    pass
        except (PermissionError, OSError):
            print(f"ERROR: {target_path.name} がロックされています。")
            print("  実行中のアプリを終了してから再実行してください。")
            sys.exit(1)


def clean_build_artifacts() -> None:
    """ビルド用生成物およびキャッシュ（__pycache__, .pytest_cache）を清掃する。"""
    patterns = [
        BASE_DIR / "main.build",
        BASE_DIR / "main.dist",
        BASE_DIR / "main.onefile-build",
        BASE_DIR / f"{APP_NAME}.build",
        BASE_DIR / f"{APP_NAME}.dist",
        BASE_DIR / f"{APP_NAME}.onefile-build",
        BASE_DIR / f"{APP_NAME}_v{VERSION}.build",
        BASE_DIR / f"{APP_NAME}_v{VERSION}.dist",
        BASE_DIR / f"{APP_NAME}_v{VERSION}.onefile-build",
        BASE_DIR / ".pytest_cache",
        OUTPUT_DIR / "main.build",
        OUTPUT_DIR / "main.dist",
        OUTPUT_DIR / "main.onefile-build",
        OUTPUT_DIR / STANDALONE_DIR_NAME,
    ]

    for pattern in patterns:
        if pattern.exists():
            print(f"  清掃: {pattern.name}")
            shutil.rmtree(pattern, ignore_errors=True)

    # ワイルドカードによるビルド中間ディレクトリの清掃 (*.build, *.dist, *.onefile-build)
    for ext in ["*.build", "*.dist", "*.onefile-build"]:
        for p in BASE_DIR.glob(ext):
            if p.is_dir():
                print(f"  清掃: {p.name}")
                shutil.rmtree(p, ignore_errors=True)
        for p in OUTPUT_DIR.glob(ext):
            if p.is_dir():
                print(f"  清掃: output/v{MAJOR_VERSION}/{p.name}")
                shutil.rmtree(p, ignore_errors=True)

    # __pycache__ ディレクトリの再帰的清掃 (.venv, .git を除外)
    for root, dirs, _ in os.walk(BASE_DIR):
        if ".venv" in root or ".git" in root:
            continue
        for d in dirs:
            if d == "__pycache__":
                p = Path(root) / d
                try:
                    rel_p = p.relative_to(BASE_DIR)
                except ValueError:
                    rel_p = p
                print(f"  清掃: {rel_p}")
                shutil.rmtree(p, ignore_errors=True)


def copy_config_files(target_dir: Path) -> None:
    """設定ファイル (config.ini / selectors.json) を target_dir/config にコピーする。"""
    target_config_dir = target_dir / "config"
    target_config_dir.mkdir(parents=True, exist_ok=True)

    config_dir = BASE_DIR / "config"
    selectors_path = config_dir / "selectors.json"
    if not selectors_path.exists():
        selectors_path = BASE_DIR / "selectors.json"
    if selectors_path.exists():
        shutil.copy2(selectors_path, target_config_dir / "selectors.json")

    config_path = config_dir / "config.ini"
    if not config_path.exists():
        config_path = BASE_DIR / "config.ini"
    if config_path.exists():
        shutil.copy2(config_path, target_config_dir / "config.ini")
    else:
        default_config_ini = (
            "[General]\n"
            "base_url =\n"
            "ignore_ssl_errors = false\n\n"
            "[Display]\n"
            "zoom_factor = 1.0\n"
        )
        (target_config_dir / "config.ini").write_text(default_config_ini, encoding="utf-8")


def create_standalone_zip(standalone_dir: Path) -> Path:
    """スタンドアロンフォルダを ZIP アーカイブにする (フォルダ構造を保持)。"""
    zip_path = OUTPUT_DIR / STANDALONE_ZIP_NAME
    print(f"\n配布用スタンドアロン ZIP を作成中: {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(standalone_dir):
            for file in files:
                file_path = Path(root) / file
                # アーカイブ内では STANDALONE_DIR_NAME/相対パス とする
                rel_path = file_path.relative_to(standalone_dir)
                arcname = Path(STANDALONE_DIR_NAME) / rel_path
                zf.write(file_path, arcname=str(arcname))

    zip_size = zip_path.stat().st_size
    print(f"  [OK] {STANDALONE_ZIP_NAME} ({zip_size / 1024 / 1024:.1f} MB)")
    return zip_path


def create_onefile_zip(exe_path: Path) -> Path:
    """配布用 Onefile ZIP アーカイブを作成する (DEVELOPER.md §4.2)。"""
    zip_path = OUTPUT_DIR / ZIP_NAME
    print(f"\n配布用 Onefile ZIP アーカイブを作成中: {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. EXE本体
        zf.write(exe_path, arcname=exe_path.name)

        # 2. config/ フォルダ構造で設定ファイルを同梱
        config_dir = BASE_DIR / "config"
        selectors_path = config_dir / "selectors.json"
        if not selectors_path.exists():
            selectors_path = BASE_DIR / "selectors.json"
        if selectors_path.exists():
            zf.write(selectors_path, arcname="config/selectors.json")

        config_path = config_dir / "config.ini"
        if not config_path.exists():
            config_path = BASE_DIR / "config.ini"
        if config_path.exists():
            zf.write(config_path, arcname="config/config.ini")
        else:
            default_config_ini = (
                "[General]\n"
                "base_url =\n"
                "ignore_ssl_errors = false\n\n"
                "[Display]\n"
                "zoom_factor = 1.0\n"
            )
            zf.writestr("config/config.ini", default_config_ini)

    zip_size = zip_path.stat().st_size
    print(f"  [OK] {ZIP_NAME} ({zip_size / 1024 / 1024:.1f} MB)")
    return zip_path


def execute_nuitka(cmd: list) -> None:
    """Nuitka コマンドを実行し、出力をリアルタイム表示する。"""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(BASE_DIR),
    )

    if process.stdout:
        for line in process.stdout:
            print(line, end="")

    return_code = process.wait()
    if return_code != 0:
        print(f"\nERROR: ビルドが失敗しました (return code: {return_code})")
        sys.exit(1)


def build_standalone() -> None:
    """Nuitka Standalone ビルド (フォルダ形式ZIP) を実行する。"""
    print("\n" + "=" * 60)
    print("▶ Standalone モード ビルド (フォルダ形式 / 推奨)")
    print("=" * 60)

    target_dir = OUTPUT_DIR / STANDALONE_DIR_NAME
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--windows-console-mode=disable",
        "--assume-yes-for-downloads",
        f"--output-filename={EXE_NAME}",
        f"--output-dir={OUTPUT_DIR}",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=all",
        "--windows-company-name=sam-hat-86",
        "--windows-product-name=Curriculum Analyzer",
        "--windows-file-description=カリキュラム分析ソフト",
        f"--windows-file-version={VERSION}",
        f"--windows-product-version={VERSION}",
    ]

    if ICON_PATH.exists():
        cmd.append(f"--windows-icon-from-ico={ICON_PATH}")
        print(f"  [OK] アプリアイコン: {ICON_PATH.name}")

    cmd.append(str(MAIN_PY))

    print("\n[ビルド実行中 (Standalone)]...")
    execute_nuitka(cmd)

    # Nuitkaが出力した dist ディレクトリを探す (通常は main.dist)
    dist_dir = OUTPUT_DIR / "main.dist"
    if not dist_dir.exists():
        # もし別名の場合のフォールバック
        for p in OUTPUT_DIR.glob("*.dist"):
            dist_dir = p
            break

    if not dist_dir.exists():
        print("ERROR: ビルド成果物 (.dist フォルダ) が見つかりません。")
        sys.exit(1)

    # dist ディレクトリを STANDALONE_DIR_NAME にリネーム
    if dist_dir != target_dir:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        dist_dir.rename(target_dir)

    # 実行ファイル名の確認とリネーム (main.exe の場合を EXE_NAME に変更)
    exe_file = target_dir / EXE_NAME
    if not exe_file.exists():
        main_exe = target_dir / "main.exe"
        if main_exe.exists():
            main_exe.rename(exe_file)

    if not exe_file.exists():
        print(f"ERROR: 実行ファイル ({EXE_NAME}) が見つかりません。")
        sys.exit(1)

    print(f"  [OK] 実行ファイル確認: {exe_file.name}")

    # 設定ファイルをアプリフォルダ内に同梱
    copy_config_files(target_dir)
    print("  [OK] 設定ファイル同梱: config/config.ini, selectors.json")

    # 配布用 ZIP アーカイブ作成
    zip_path = create_standalone_zip(target_dir)

    # Standalone 展開フォルダを削除して ZIP のみを残す (成果物整理)
    print("  Standalone 展開フォルダを清掃中 (Zipのみ保持)...")
    shutil.rmtree(target_dir, ignore_errors=True)

    print("\n" + "=" * 60)
    print("Standalone ビルド完了!")
    print(f"  ZIP出力: {zip_path}")
    print("=" * 60)


def build_onefile() -> None:
    """Nuitka Onefile ビルド (単一EXE) を実行する。"""
    print("\n" + "=" * 60)
    print("▶ Onefile モード ビルド (単一EXE)")
    print("=" * 60)

    exe_path = OUTPUT_DIR / EXE_NAME
    check_file_lock(exe_path)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--standalone",
        "--windows-console-mode=disable",
        "--assume-yes-for-downloads",
        f"--output-filename={EXE_NAME}",
        f"--output-dir={OUTPUT_DIR}",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=all",
        "--windows-company-name=sam-hat-86",
        "--windows-product-name=Curriculum Analyzer",
        "--windows-file-description=カリキュラム分析ソフト",
        f"--windows-file-version={VERSION}",
        f"--windows-product-version={VERSION}",
    ]

    if ICON_PATH.exists():
        cmd.append(f"--windows-icon-from-ico={ICON_PATH}")
        print(f"  [OK] アプリアイコン: {ICON_PATH.name}")

    cmd.append(str(MAIN_PY))

    print("\n[ビルド実行中 (Onefile)]...")
    execute_nuitka(cmd)

    if not exe_path.exists():
        print(f"ERROR: {EXE_NAME} が見つかりません。")
        sys.exit(1)

    file_size = exe_path.stat().st_size
    print(f"  [OK] {EXE_NAME} ({file_size / 1024 / 1024:.1f} MB)")

    zip_path = create_onefile_zip(exe_path)

    print("\n" + "=" * 60)
    print("Onefile ビルド完了!")
    print(f"  EXE出力: {exe_path}")
    print(f"  ZIP出力: {zip_path}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Curriculum Analyzer ビルドスクリプト")
    parser.add_argument(
        "--mode",
        choices=["standalone", "onefile", "all"],
        default="standalone",
        help="ビルドモードの選択 (デフォルト: standalone)",
    )
    parser.add_argument(
        "-s", "--standalone",
        action="store_const",
        dest="mode",
        const="standalone",
        help="Standaloneモード (フォルダ形式ZIP) でビルド (推奨)",
    )
    parser.add_argument(
        "-o", "--onefile",
        action="store_const",
        dest="mode",
        const="onefile",
        help="Onefileモード (単一EXE) でビルド",
    )
    parser.add_argument(
        "-a", "--all",
        action="store_const",
        dest="mode",
        const="all",
        help="StandaloneとOnefileの両方をビルド",
    )
    parser.add_argument(
        "-c", "--clean",
        action="store_true",
        help="キャッシュとビルド中間生成物の清掃のみ実行",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="確認プロンプトを自動承認する",
    )
    parser.add_argument(
        "--sync-docs",
        action="store_true",
        help="docs/script.js のバージョン設定を同期して終了する",
    )

    args = parser.parse_args()

    if args.sync_docs:
        print("=" * 60)
        print("docs/script.js のバージョン同期")
        print("=" * 60)
        sync_docs_version()
        return

    if args.clean:
        print("=" * 60)
        print("Curriculum Analyzer - キャッシュ・ビルド生成物の清掃")
        print("=" * 60)
        clean_build_artifacts()
        print("清掃完了!")
        return

    print("=" * 60)
    print(f"Curriculum Analyzer - Nuitka ビルド (モード: {args.mode})")
    print("=" * 60)

    # ドキュメントのバージョン自動同期
    sync_docs_version()

    # 事前チェック
    check_venv(auto_yes=args.yes)
    check_dependencies()

    # ビルド前清掃
    print("\n[準備] ビルド生成物を清掃中...")
    clean_build_artifacts()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.mode in ["standalone", "all"]:
        build_standalone()

    if args.mode in ["onefile", "all"]:
        build_onefile()

    # ビルド後清掃 (中間ファイル)
    print("\n[完了後清掃] 中間生成物を清掃中...")
    clean_build_artifacts()


if __name__ == "__main__":
    main()
