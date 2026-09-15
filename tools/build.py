"""Nuitka Onefileビルドスクリプト。

仕様書 §43 および DEVELOPER.md §4 に準拠:
- __file__基準でパスを解決
- cwdへ依存しない
- venv利用を推奨/チェック
- 必須ライブラリ事前確認 (nuitka, PyQt6, PyQt6.QtWebEngineWidgets, openpyxl)
- コンソール画面非表示 (--windows-console-mode=disable)
- アプリアイコン指定 (--windows-icon-from-ico)
- JSファイル多重配置 (--include-data-files)
- stdout/stderrをリアルタイム表示
- ビルド用生成物を清掃
- ファイルロック時は中止
- バージョン付きEXE (Curriculum_Analyzer_v{VERSION}.exe) および配布用ZIPアーカイブの自動生成
"""

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
# バージョン・ビルド設定
# ==========================================

# バージョン番号を変更する場合はここを変更してください（EXE名・ZIP名・メタデータに一括反映）
VERSION = "1.1.0"
APP_NAME = "Curriculum_Analyzer"

# __file__基準でパス解決 (tools/ の親 = プロジェクトルート)
BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
MAIN_PY = SRC_DIR / "main.py"
EXE_NAME = f"{APP_NAME}_v{VERSION}.exe"
ZIP_NAME = f"{APP_NAME}_v{VERSION}.zip"
OUTPUT_DIR = BASE_DIR
ICON_PATH = Path(__file__).resolve().parent / "MSL分析ロゴ.ico"



def check_venv() -> None:
    """venv環境を確認する。"""
    if sys.prefix == sys.base_prefix:
        print("WARNING: 仮想環境(venv)が有効ではありません。")
        print("  推奨: python -m venv venv && venv\\Scripts\\activate")
        # 非対話環境や引数指定に対応
        if "--yes" in sys.argv or "-y" in sys.argv or not sys.stdin.isatty():
            print("  自動継続フラグまたは非対話環境を検知しました。続行します。")
            return
        response = input("続行しますか? (y/N): ").strip().lower()
        if response != "y":
            print("ビルドを中止しました。")
            sys.exit(1)


def check_dependencies() -> None:
    """必須ライブラリの存在確認。"""
    required = ["nuitka", "PyQt6", "PyQt6.QtWebEngineWidgets", "openpyxl"]
    missing = []

    for pkg in required:
        try:
            if pkg == "PyQt6.QtWebEngineWidgets":
                import PyQt6.QtWebEngineWidgets
            elif pkg == "nuitka":
                import nuitka
            elif pkg == "PyQt6":
                import PyQt6
            elif pkg == "openpyxl":
                import openpyxl
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"ERROR: 以下のライブラリが不足しています: {', '.join(missing)}")
        print("  pip install -r requirements.txt を実行してください。")
        sys.exit(1)


def check_file_lock() -> None:
    """出力EXEのファイルロック確認。"""
    exe_path = OUTPUT_DIR / EXE_NAME
    if exe_path.exists():
        try:
            with open(exe_path, "ab") as f:
                pass
        except (PermissionError, OSError):
            print(f"ERROR: {EXE_NAME} がロックされています。")
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


def create_release_zip(exe_path: Path) -> Path:
    """配布用ZIPアーカイブを作成する (DEVELOPER.md §4.2)。"""
    zip_path = OUTPUT_DIR / ZIP_NAME
    print(f"\n配布用ZIPアーカイブを作成中: {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. EXE本体
        zf.write(exe_path, arcname=exe_path.name)
        # 2. selectors.json
        selectors_path = BASE_DIR / "selectors.json"
        if selectors_path.exists():
            zf.write(selectors_path, arcname="selectors.json")
        # 3. config.ini (手元の実ファイルが存在する場合はそのまま同梱、未存在時は初期テンプレート)
        config_path = BASE_DIR / "config.ini"
        if config_path.exists():
            zf.write(config_path, arcname="config.ini")
        else:
            default_config_ini = (
                "[General]\n"
                "base_url =\n"
                "ignore_ssl_errors = false\n\n"
                "[Display]\n"
                "zoom_factor = 1.0\n"
            )
            zf.writestr("config.ini", default_config_ini)

    zip_size = zip_path.stat().st_size
    print(f"  [OK] {ZIP_NAME} ({zip_size / 1024 / 1024:.1f} MB)")
    return zip_path


def build() -> None:
    """Nuitka Onefileビルドを実行する。"""
    print("=" * 60)
    print("Curriculum Analyzer - Nuitka Onefile ビルド")
    print("=" * 60)

    # 事前チェック
    check_venv()
    check_dependencies()
    check_file_lock()

    # ビルド前清掃
    print("\n[1/4] ビルド生成物を清掃中...")
    clean_build_artifacts()

    # Nuitkaコマンド構築
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--standalone",
        "--windows-console-mode=disable",  # GUI専用（黒い画面非表示）
        "--assume-yes-for-downloads",      # ツールチェーン自動承認
        f"--output-filename={EXE_NAME}",
        f"--output-dir={OUTPUT_DIR}",
        # PyQt6プラグイン
        "--enable-plugin=pyqt6",
        # WebEngineリソース組み込み
        "--include-qt-plugins=all",
        # Windows EXEメタデータ
        "--windows-company-name=sam-hat-86",
        "--windows-product-name=Curriculum Analyzer",
        "--windows-file-description=カリキュラム分析ソフト",
        f"--windows-file-version={VERSION}",
        f"--windows-product-version={VERSION}",
    ]

    # アイコン適用
    if ICON_PATH.exists():
        cmd.append(f"--windows-icon-from-ico={ICON_PATH}")
        print(f"  [OK] アプリアイコン: {ICON_PATH.name}")

    # JSファイル同梱 (browser/ と src/browser/ の両方に配置)
    js_src = SRC_DIR / "browser" / "extract_table.js"
    cmd.append(f"--include-data-files={js_src}=browser/extract_table.js")
    cmd.append(f"--include-data-files={js_src}=src/browser/extract_table.js")

    # メインスクリプト
    cmd.append(str(MAIN_PY))

    print("\n[2/4] Nuitka ビルド実行中 (これには数分かかります)...")
    print(f"  コマンド: {' '.join(cmd[:6])} ...")

    # stdout/stderrをリアルタイム表示
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

    # ビルド後確認
    print("\n[3/4] ビルド結果を確認中...")
    exe_path = OUTPUT_DIR / EXE_NAME
    if not exe_path.exists():
        print(f"ERROR: {EXE_NAME} が見つかりません。")
        sys.exit(1)

    file_size = exe_path.stat().st_size
    print(f"  [OK] {EXE_NAME} ({file_size / 1024 / 1024:.1f} MB)")

    # 配布用ZIPアーカイブ作成
    print("\n[4/4] 配布パッケージを生成中...")
    zip_path = create_release_zip(exe_path)

    # ビルド後清掃
    print("\n  ビルド生成物を清掃中...")
    clean_build_artifacts()

    print("\n" + "=" * 60)
    print("ビルド完了!")
    print(f"  EXE出力: {exe_path}")
    print(f"  ZIP出力: {zip_path}")
    print("=" * 60)


if __name__ == "__main__":
    if "--clean" in sys.argv or "-c" in sys.argv:
        print("=" * 60)
        print("Curriculum Analyzer - キャッシュ・ビルド生成物の清掃")
        print("=" * 60)
        clean_build_artifacts()
        print("清掃完了!")
    else:
        build()
