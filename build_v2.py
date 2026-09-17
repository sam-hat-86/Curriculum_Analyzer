"""
カリキュラムチェックシステム v2.0.0 Nuitkaビルドスクリプト (仕様書§51, §52)
"""
import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

VERSION = "2.0.0"
APP_NAME = "Curriculum_Analyzer_v2.0.0"
OUTPUT_DIR = Path("output/v2")
BUILD_DIR = Path("build/v2")

REQUIRED_PACKAGES = [
    "PySide6",
    "playwright",
    "bs4",
    "lxml",
    "httpx",
    "openpyxl",
    "nuitka",
]

def check_dependencies():
    """依存パッケージの存在確認"""
    print("--- 依存パッケージ確認中 ---")
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
            print(f"  [OK] {pkg}")
        except ImportError:
            print(f"  [MISSING] {pkg}")
            missing.append(pkg)
    if missing:
        print(f"\nエラー: 以下のパッケージが不足しています: {', '.join(missing)}")
        print("pip install -r requirements.txt を実行してください。")
        sys.exit(1)
    print("依存パッケージの確認が完了しました。\n")

def run_build():
    """Nuitkaによるビルド実行"""
    check_dependencies()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    main_script = Path("src/main.py")
    if not main_script.exists():
        print(f"エラー: {main_script} が存在しません。")
        sys.exit(1)

    print(f"=== {APP_NAME} のビルドを開始します (Version {VERSION}) ===")

    cmd = [
        sys.executable,
        "-m", "nuitka",
        "--standalone",
        "--windows-console-mode=disable",
        "--enable-plugin=pyside6",
        "--include-data-dir=config=config",
        f"--output-dir={BUILD_DIR}",
        f"--output-filename={APP_NAME}.exe",
        "--assume-yes-for-downloads",
        str(main_script)
    ]

    # アイコンが存在すれば追加
    icon_path = Path("v1/src/gui/assets/app_icon.ico")
    if icon_path.exists():
        cmd.append(f"--windows-icon-from-ico={icon_path}")

    print(f"実行コマンド: {' '.join(cmd)}\n")
    res = subprocess.run(cmd)

    if res.returncode != 0:
        print("\nビルドに失敗しました。")
        sys.exit(res.returncode)

    dist_dir = BUILD_DIR / "main.dist"
    exe_file = dist_dir / f"{APP_NAME}.exe"
    if not exe_file.exists():
        # main.exe の場合
        exe_file = dist_dir / "main.exe"
        if exe_file.exists():
            exe_file.rename(dist_dir / f"{APP_NAME}.exe")
            exe_file = dist_dir / f"{APP_NAME}.exe"

    if not exe_file.exists():
        print(f"エラー: 生成されたEXEが見つかりません: {exe_file}")
        sys.exit(1)

    print(f"\nビルド成功: {exe_file}")

    # 配布用ZIPの作成 (仕様書§52)
    zip_path = OUTPUT_DIR / f"{APP_NAME}.zip"
    print(f"配布ZIPを作成中: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in dist_dir.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(dist_dir)
                zf.write(file, arcname=f"{APP_NAME}/{arcname}")

    print(f"=== ビルドおよびパッケージングが完了しました ===")
    print(f"出力ファイル: {zip_path}")

if __name__ == "__main__":
    run_build()
