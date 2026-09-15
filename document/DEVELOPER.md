# 開発者ガイド (Developer Guide)

本書は、「授業指示書・カリキュラム 精査ブラウザ (Curriculum Analyzer)」の開発環境構築、プロジェクト構成、テスト実行、ビルド手順、およびコーディング規約について説明する開発者向けガイドです。

開発および保守に際しては、ルートディレクトリに配置されている完全統合確定仕様書 **`Curriculum_Analyzer_Spec_v2.md`** を Single Source of Truth (SSOT) として厳格に遵守してください。

---

## 1. 開発環境のセットアップ

### 1.1 前提環境

- **OS**: Windows 10 (1809以降) または Windows 11 (x86-64 / AMD64)
- **Python**: Python 3.11.x (64-bit)
- **PowerShell**: pwsh / Windows PowerShell

### 1.2 仮想環境の作成とライブラリのインストール

プロジェクトルート（`C:\myPrograming\Python\Curriculum_Analyzer`）にて仮想環境を作成し、依存関係をインストールします。

```powershell
# 仮想環境の作成
python -m venv venv

# 仮想環境の有効化
.\venv\Scripts\Activate.ps1

# 仮想環境の有効化
.\venv\Scripts\Activate.ps1

# 依存ライブラリのインストール (実行・ビルド・テスト用)
pip install -r requirements.txt
```

### 1.3 依存パッケージ構成

- **`requirements.txt`**:
  - `PyQt6==6.7.1`: GUIフレームワーク
  - `PyQt6-WebEngine==6.7.0`: Chromiumベースの組み込みブラウザ
  - `openpyxl==3.1.5`: Excelファイル生成・操作
  - `nuitka>=2.4.8`: 単一EXE (Onefile) パッケージングツール
  - `zstandard>=0.23.0`: Nuitka Onefile圧縮モジュール
  - `pytest==7.4.3`: テストフレームワーク
  - `flake8==6.1.0`: 静的コード解析 (Linter)
  - `black==23.9.1`: コードフォーマッタ

---

## 2. プロジェクト構造

ソースコードおよび関連アセットは以下のディレクトリ構成で配置されます。

``` tree
Curriculum_Analyzer/
├── document/                       # 仕様書・ドキュメント類
├── doc/                            # 公開用ドキュメント (GitHub Pages用)
├── tools/                          # ビルド・開発支援ツール群
│   ├── build.py                    # Nuitka Onefile ビルドスクリプト
│   └── MSL分析ロゴ.ico             # 配布EXE用アイコン
├── config.ini                      # アプリケーション設定ファイル
├── selectors.json                  # DOM抽出セレクタ定義ファイル
├── requirements.txt                # 依存ライブラリ定義 (実行・ビルド・開発・テスト用)
├── .gitignore                      # Git除外設定
├── LICENSE                         # プロプライエタリライセンス
├── SECURITY.md                     # セキュリティポリシー
├── DEVELOPER.md                    # 本書 (開発者ガイド)
├── README.md                       # GitHub用概要ドキュメント
├── README.txt                      # 配布ZIP同梱用ドキュメント
├── src/                            # アプリケーションソースコード
│   ├── browser/                    # ブラウザ連携・JavaScript注入
│   │   └── extract_table.js        # テーブル要素・セルのDOM抽出スクリプト
│   ├── core/                       # ドメインモデル・判定・永続化ロジック (GUI非依存)
│   │   ├── __init__.py
│   │   ├── models.py               # データ構造定義 (CurriculumRecord等)
│   │   ├── normalization.py        # 学籍番号・受講区分・科目・本文の正規化
│   │   ├── parser.py               # 指示書本文のセクション解析
│   │   ├── evaluator.py            # ERROR / WARNING / PASS 判定エンジン (純粋関数群)
│   │   ├── repository.py           # レコードの蓄積・更新・Undo管理
│   │   ├── cache.py                # JSONLキャッシュ保存・復元
│   │   └── exporter.py             # BOM付きUTF-8固定15列CSV出力
│   └── gui/                        # PyQt6 GUI実装
│       ├── __init__.py
│       ├── main_window.py          # メインウィンドウ・状態機械・UIイベント制御
│       └── worker.py               # 集計処理のバックグラウンド非同期ワーカー
├── tests/                          # 自動テスト
│   ├── __init__.py
│   ├── fixtures/                   # テスト用入力データ
│   ├── expected/                   # 期待結果データ (Golden Test用)
│   └── mock_pages/                 # モックHTMLページ (ダミーデータ)
└── doc/                            # ユーザー向け総合操作マニュアル (Web形式)
    ├── index.html
    ├── style.css
    └── script.js
```

### アーキテクチャの基本方針

- **責務分離の徹底**: `DOM抽出 → CurriculumRecord → 判定エンジン → CSV出力`
- **純粋関数化**: `core/` の判定ロジック（`evaluator.py`）は GUI (`PyQt6`) およびブラウザ (`QtWebEngine`) に一切依存しない純粋関数群として実装します。
- **標準ライブラリの活用**: CSV生成には `pandas` などの外部データフレームライブラリを使用せず、Python標準の `csv` モジュールを使用します。

---

## 3. テストの実行

### 3.1 pytest による単体・結合テスト

すべてのユニットテストおよびGoldenテストは `pytest` を用いて実行します。

```powershell
# すべてのテストを実行
pytest

# 詳細な出力付きで実行
pytest -v

# 特定のテストモジュールを実行
pytest tests/test_evaluator.py
```

### 3.2 テスト対象範囲

- **Core判定エンジン**: ルール判定（ERROR/WARNING/PASS）の正確性、rule ID の出力順序
- **データ正規化 (`normalization`)**: 全角半角変換、不要空白除去、生徒セルからの学籍番号抽出
- **指示書解析 (`parser`)**: セクション（【予定】等）の分割と未分類テキストの保持
- **Repository / Undo**: 30世代の履歴管理、同一複合キーの統合
- **キャッシュ復元 (`cache`)**: 不正JSON行のスキップ、アトミック書き換え
- **設定検証 (`config`)**: `base_url` スキーム検証、`ignore_ssl_errors` の解釈
- **CSV出力 (`exporter`)**: 15列固定ヘッダー、BOM付きUTF-8、CRLF改行、Excel互換性

### 3.3 テストデータの規約

- **個人情報のコミット厳禁**: 公開リポジトリ（GitHub）に配置するテスト用HTMLおよびフィクスチャには、実在の学籍番号、氏名、機密情報を含む本番データを**絶対に含めないでください**。
- `tests/mock_pages/` には必ず架空のダミーデータ（テスト用データ）のみを格納します。

---

## 4. ビルド手順 (Onefile EXE)

本プロジェクトの正式配布バイナリは、Nuitka を用いて単一実行可能ファイル (`Curriculum_Analyzer.exe`) としてパッケージングします。

### 4.1 ビルドコマンド

仮想環境を有効化した状態で、以下のビルドスクリプトを実行します。

```powershell
python tools/build.py
```

※一時キャッシュや中間生成物の清掃のみを行う場合は `--clean` オプションを指定します：
```powershell
python tools/build.py --clean
```

```powershell
python -m nuitka `
    --onefile `
    --windows-console-mode=disable `
    --enable-plugin=pyqt6 `
    --include-data-dir=src/browser=browser `
    --windows-company-name="sam-hat-86" `
    --windows-product-name="Curriculum Analyzer" `
    --windows-file-version="1.0.0" `
    --windows-product-version="1.0.0" `
    --windows-file-description="カリキュラム分析ソフト" `
    --output-filename="Curriculum_Analyzer.exe" `
    src/main.py
```

### 4.2 配布ZIPアーカイブの作成

正式リリース資産は単一のZIPファイルとして作成します。

- **ZIPファイル名**: `Curriculum_Analyzer_v1.0.0.zip`
- **ZIP同梱ファイル**:
  - `Curriculum_Analyzer.exe`
  - `README.txt`
  - （※ `doc/` やソースコード、テストファイルは配布ZIPに含めません）

---

## 5. コーディング規約 (Coding Conventions)

### 5.1 基本原則

- **仕様外機能追加の禁止**: 仕様書（`Curriculum_Analyzer_Spec_v2.md`）に記載されていない業務ルールや機能を独自判断で追加してはなりません。
- **ドキュメントの維持**: 既存のコメントおよび docstring は原則として保持してください。

### 5.2 Python 規約とスタイル

- **Pythonバージョン**: Python 3.11
- **型ヒント (Type Hints)**: すべての関数、メソッド、引数、戻り値に Python 標準の型ヒントを明記してください。
- **データクラス**: ドメインモデル等でデータクラスを使用する場合は、パフォーマンス向上のため `@dataclass(slots=True)` を指定してください。
- **フォーマッタ**: `black==23.9.1` に準拠（行長 88 文字標準）。
- **Linter**: `flake8==6.1.0` をクリアすること。

```powershell
# フォーマットチェック
black --check src tests

# 自動フォーマット適用
black src tests

# 静的解析チェック
flake8 src tests
```

### 5.3 docstring およびコメント

- ユーザー向けメッセージ、ログメッセージ、docstring は日本語で記述します。
- 各モジュール、クラス、公開メソッドには目的、引数、戻り値、例外を明記した docstring を記載してください。

### 5.4 セキュリティ・プライバシー規約

- ソースコード内に本番サイトの認証情報（ユーザー名、パスワード、APIトークン等）をハードコードしないでください。
- ログ（`error.log`）出力時、URLのクエリパラメータや認証に関わるヘッダー・Cookie等は必ずマスク処理を行ってください。
