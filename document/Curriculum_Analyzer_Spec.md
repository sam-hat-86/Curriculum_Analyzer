# カリキュラム備考欄チェックシステム (Curriculum Analyzer)

## 完全統合確定仕様書 (v1.1.0 正本)

- 文書名: `Curriculum_Analyzer_Spec.md`
- アプリ名: カリキュラム備考欄チェックシステム
- ProductName: `Curriculum Analyzer`
- EXE名: `Curriculum_Analyzer_v1.1.0.exe`（Onefileビルド成果物）
- 配布ZIP名: `Curriculum_Analyzer_v1.1.0.zip`
- アプリバージョン: `1.1.0`
- ルールバージョン: `1.0.0`
- キャッシュスキーマ: `schema_version = 1`
- 作成者 / CompanyName: `sam-hat-86`
- FileDescription: `カリキュラム分析ソフト`
- OriginalFilename: `Curriculum_Analyzer.exe`
- 対象OS: Windows 10 (1809以降) / Windows 11、x64
- 配布方式: GitHub Release / Nuitka Onefile
- 正式配布先: GitHub Release（唯一の正式配布場所）
- ライセンス: 独自License、著作権その他の権利は `sam-hat-86` に帰属

---

## 1. 仕様の位置付け

本書は、本システム「カリキュラム備考欄チェックシステム (Curriculum Analyzer)」の実装・テスト・ビルド・配布・保守における Single Source of Truth（SSOT、正本）である。

実装担当者および保守担当者は、本書に記載のない仕様を勝手に追加してはならない。技術的に複数の実装方法が存在しても、最終結果が同一であり、既存仕様と矛盾せず、テスト方法も一意である場合に限り内部実装上の裁量を認める。

本仕様書はバージョン `1.1.0` に向けた全新機能（Excel 7シート出力、6段階Severity、条件付き志望校判定、集計対象除外ルール、外部セレクタ設定、教室・年度・生徒氏名・学年の抽出、DOM安定判定、起動時診断および案内ダイアログなど）を漏れなく完全に統合・確定したものである。

仕様開始・改訂条件は以下をすべて満たすこととする。

- 仕様矛盾が0件
- 未確定仕様が0件
- 参照漏れが0件
- 禁止事項の確認完了
- テスト計画（全61件のpytestテスト合格）の整合性確認完了

---

## 2. 目的・主要機能

Web上のカリキュラム画面を、ユーザーが組み込みブラウザ（PyQt6-WebEngine）で手動操作しながら収集・蓄積し、カリキュラム備考欄の整合性を自動チェックして成果物ファイルを出力する。

### 2.1 収集データ項目

画面上のカリキュラムテーブルおよび画面コンテキストから以下の項目を安全に抽出・正規化・蓄積する。

1. **学籍番号** (`student_id`): 必須キー（生徒セルから抽出）
2. **受講区分** (`division`): 必須キー（通常、夏期講習、冬期講習など）
3. **科目** (`subject`): 必須キー（中学数学、英語など）
4. **指示書（備考欄）本文** (`raw_instruction`): 必須対象
5. **教室名** (`classroom_name`): コンテキスト情報（セレクタ外部定義対応）
6. **教室コード** (`classroom_code`): コンテキスト情報（セレクタ外部定義対応）
7. **年度** (`school_year`): コンテキスト情報（セレクタ外部定義対応）
8. **生徒氏名** (`student_name`): 生徒セルから抽出・正規化
9. **学年** (`grade`): 学年列またはメタセルから抽出・正規化

### 2.2 データ処理と成果物出力

- 抽出したデータは内部リポジトリ（Repository）へ蓄積し、同一キー `(student_id, division, subject)` 単位で統合・更新する。
- 集計実行時、集計対象外生徒（名字がデモ、在籍が退塾・見送り）を自動除外して統計を記録する。
- 指示書本文を構文解析（Section Parser）し、6段階のSeverity判定ランクとRule IDを付与する。
- **メイン成果物**: `openpyxl` による **高機能Excelブック（7シート構成）** を出力する。
- **サブ成果物**: システム連携・互換用の **BOM付きUTF-8固定15列CSV** を並列出力する。
- 出力完了後、Windows Explorerを自動起動し、生成されたExcelファイル（またはCSV）を選択状態で表示する。

---

## 3. 技術構成

### 3.1 実行環境

- **OS**: Windows 10 (1809以降) / Windows 11
- **CPU**: x86-64（Intel 64 / AMD64）
- **Python**: 3.11.x
- **GUIフレームワーク**: `PyQt6==6.7.1`
- **組み込みブラウザ**: `PyQt6-WebEngine==6.7.0`
- **Excel生成**: `openpyxl==3.1.5`
- **CSV生成**: Python標準 `csv` モジュール
- **テストフレームワーク**: `pytest==7.4.3`
- **フォーマッタ**: `black==23.9.1`
- **リンター**: `flake8==6.1.0`
- **ビルドツール**: `nuitka>=2.4.8`, `zstandard>=0.23.0`
- **配布形式**: Nuitka Onefile 単一実行ファイル

### 3.2 アーキテクチャと責務分離

本システムは以下のレイヤーに明確に責務を分離する。

`DOM抽出 (JavaScript) → CurriculumRecord (データモデル) → 判定エンジン (純粋関数群) → Excel / CSV 出力`

- `src/browser/extract_table.js`: 可視テーブル候補の探索、教室・年度・ヘッダー・セルのDOM抽出、DOM安定判定
- `src/core/models.py`: 内部データ構造定義（CurriculumRecord, Severity, EvaluationResult 等）
- `src/core/constants.py`: システム全体で使用する定数、Rule ID、メッセージ、セクション定義
- `src/core/normalization.py`: 学籍番号・氏名・学年・受講区分・科目・本文・見出しの正規化処理
- `src/core/parser.py`: 指示書セクション解析、番号付き見出し照合、論理改行復元、未知見出し分類
- `src/core/evaluator.py`: 6段階Severity判定、個別ルールチェック、コピペ判定、除外ルール判定（純粋関数群）
- `src/core/repository.py`: レコードの蓄積・同一キー更新・Undoスタック管理
- `src/core/cache.py`: JSONLセッションキャッシュの保存・復元・耐障害救済処理
- `src/core/config.py`: config.ini および selectors.json の読み込み・検証・自己診断
- `src/core/exporter.py`: BOM付きUTF-8固定15列CSVエクスポーター
- `src/core/excel_exporter.py`: openpyxlによる7シート高機能Excelエクスポーター
- `src/gui/main_window.py`: メインウィンドウ、状態機械、UIイベント制御、ポーリング監視
- `src/gui/worker.py`: 集計・出力バックグラウンド非同期ワーカー（QThread）
- `src/gui/overlay.py`: 全画面ローディングオーバーレイ（操作ロック・進捗表示）
- `src/gui/guide_dialog.py`: 起動時使い方・ショートカット案内ダイアログ
- `src/gui/toast.py`: 画面中央下部トースト通知ウィジェット

コア判定エンジン（`evaluator.py`）は PyQt6 および WebEngine に一切依存しない純粋関数群として実装し、完全な単体テスト可能性を保証する。

---

## 4. 配布・GitHub設計

### 4.1 GitHub Repository

- **Repository名**: `Curriculum_Analyzer`
- **公開範囲**: Public
- **デフォルトブランチ**: `main`
- GitHub Releaseを唯一の正式配布経路とする。
- 認証情報、Cookie、トークン、秘密鍵、実データ、実在個人情報はRepositoryおよびGit履歴へ一切保存しない。
- テスト用fixtureおよびモックHTMLはダミーデータのみで構成する。

### 4.2 Release

- 安定版のみを手動Publishする（Pre-releaseおよびGitHub Actionsによる自動Publishは不使用）。
- タグ形式: `v1.1.0`
- Release資産名: `Curriculum_Analyzer_v1.1.0.zip`
- checksumファイルは作成しない。

### 4.3 Release ZIP 構成

Release ZIPは単一フォルダ展開でそのまま実行可能な構成とし、以下を同梱する。

1. `Curriculum_Analyzer_v1.1.0.exe` (Nuitka Onefile EXE)
2. `selectors.json` (DOM抽出セレクタ定義ファイル)
3. `config.ini` (初期設定ファイルテンプレート)

ドキュメント（`docs/` や `document/`）はZIPには同梱せず、リポジトリおよびGitHub Pagesにて公開・一元管理する。

---

## 5. Windows EXEメタデータ

Nuitkaビルド時に以下のWindows実行可能ファイル属性を設定する。

- **CompanyName**: `sam-hat-86`
- **ProductName**: `Curriculum Analyzer`
- **FileDescription**: `カリキュラム分析ソフト`
- **OriginalFilename**: `Curriculum_Analyzer.exe`
- **FileVersion**: `1.1.0`
- **ProductVersion**: `1.1.0`
- **アイコン**: `tools/MSL分析ロゴ.ico`
- **コンソール表示**: `--windows-console-mode=disable` (GUI専用、黒いコンソール画面を非表示)

---

## 6. バージョン管理

- **アプリバージョン**: `1.1.0` (`__version__ = "1.1.0"`)
- **ルールバージョン**: `1.0.0` (`RULE_VERSION = "1.0.0"`)
- **リリースバージョン (Git Tag)**: `v1.1.0`
- **キャッシュスキーマバージョン**: `1` (`CACHE_SCHEMA_VERSION = 1`)

アプリバージョンとキャッシュスキーマバージョンは独立した定数として管理する。`config.ini` にはアプリバージョンを記録しない。

---

## 7. アプリ起動シーケンス

### 7.1 ベースパス解決

Onefile実行時の `base_dir` は、ユーザーが実行したEXE自身の所在ディレクトリ（`sys.argv[0]`基準）を解決する。開発環境では `__file__` 基準（プロジェクトルート）とする。

ファイル・フォルダの配置構成:

- `Curriculum_Analyzer_v1.1.0.exe`
- `config.ini`
- `selectors.json`
- `user_data/` (Cookie, LocalStorage, キャッシュ, `_session_cache.jsonl`)
- `error.log`

### 7.2 起動順序

1. `base_dir` 解決および `src/` の `sys.path` 追加
2. 最低限のフォールバックロガー初期化（`error.log`）
3. `MemoryError` ハンドラの設定（GUIダイアログを出さずstderrとログへ記録し即時終了）
4. Win32 Mutex 生成・多重起動チェック
5. `QApplication` インスタンス生成
6. `config.ini` 読み込み・検証（`base_url` 未設定時は対話入力ダイアログ表示）
7. `user_data/` ディレクトリ初期化
8. 起動時自己診断（`run_startup_self_diagnosis`: ディレクトリ書き込み権限、`selectors.json` 構文の検証）
9. 孤立一時ファイル（`.tmp`）のクリーンアップ
10. Repository および CacheManager 生成
11. キャッシュ復元確認ダイアログの表示（キャッシュ存在時）
12. MainWindow 生成（WebEngine Profile, カスタムPage, ツールバー, ステータスバー構築）
13. `base_url` への自動ロード開始
14. 起動時案内ダイアログの表示判定（初回起動時または設定有効時）

### 7.3 High-DPI

Qt 6 標準の DPI スケーリングに委ね、非推奨の旧式属性設定は明示的に行わない。

---

## 8. 多重起動防止

- Mutex名: `Local\\CurriculumCheckerAppSingleInstanceMutex`
- `CreateMutexW` 直後に `GetLastError()` を評価する。
- `ERROR_ALREADY_EXISTS (183)` の場合は、取得したMutexハンドルを直ちに `CloseHandle` し、新規プロセスを正常終了する。
- 既存インスタンス検知時、既存ウィンドウを前面化する:
  - 最小化中の場合は `ShowWindow(hwnd, SW_RESTORE)` (コマンド値: 9)
  - `SetForegroundWindow(hwnd)` を実行
  - 前面化がOSに拒否された場合は `FlashWindowEx` によりタスクバーを点滅させてユーザーへ通知する。

---

## 9. 設定管理 (config.ini & selectors.json)

### 9.1 config.ini の仕様

- **文字コード**: UTF-8（BOMあり/BOMなし対応）、CP932(Shift-JIS)への自動フォールバック対応
- **NULL文字検知**: ファイル内にNULL文字（`\x00`）が含まれる場合は破損として扱い、`.bak` バックアップを作成してデフォルト設定で再生成する。
- **不足キー補完**: 不足キーはメモリ上で安全なデフォルト値で補完する。
- **アトミック保存**: 設定値の更新・保存は `tempfile.mkstemp` → `flush` → `os.fsync` → `os.replace` で行う。
- **許可スキーム**: `http://`, `https://`, `file:///`
- **対話入力フォールバック**: 初回起動時や `base_url` が空文字列の場合、起動を中止せず `QInputDialog` による対話入力ダイアログを表示してURLを取得し、`config.ini` に保存して起動を継続する。
- **設定キー一覧**:
  - `[General] base_url`: 接続先URL
  - `[General] ignore_ssl_errors`: SSLエラー無視フラグ (`true` / `false` / `1` / `0` / `yes` / `no`)
  - `[Display] zoom_factor`: 画面初期倍率 (`0.5` ～ `2.0`、標準: `1.0`)

### 9.2 selectors.json の仕様（外部セレクタ定義）

WebサイトのDOM変更にコード変更なしで柔軟に対応するため、セレクタ定義を外部JSONファイルとして分離・提供する。

- **配置パス**: `base_dir/selectors.json`
- **必須キー一覧**:
  1. `classroom_name`: 教室名抽出用セレクタ候補リスト（CSSセレクタ / XPath）
  2. `classroom_code`: 教室コード抽出用セレクタ候補リスト
  3. `school_year`: 年度抽出用セレクタ候補リスト
  4. `target_table`: カリキュラムテーブル抽出用セレクタ候補リスト
  5. `loading_indicator`: ローディング表示検知用セレクタ候補リスト
- **検証と耐障害性**:
  - ファイル不在時は内部の `DEFAULT_SELECTORS` を用いて自動生成する。
  - JSON構文エラーまたは必須キー欠損時は、警告ログを記録した上で内部デフォルトセレクタへ安全にフォールバックする。

---

## 10. WebEngine・セキュリティ仕様

### 10.1 Profile & Storage

- 単一の `QWebEngineProfile`、`QWebEnginePage`、`QWebEngineView` で構成する（タブ機能は設けない）。
- `PersistentCookiesPolicy`: `ForcePersistentCookies`
- `user_data` ディレクトリにCookie、LocalStorage、セッションデータ、HTTPキャッシュを永続化する。

### 10.2 権限管理 (Permissions)

以下のWeb API機能は自動的に拒否・ブロックする。

- プッシュ通知 (Notifications)
- Clipboard API (`navigator.clipboard.writeText` 等はPromise reject)
- カメラ・マイク (Media stream)
- 位置情報 (Geolocation)
- 全画面表示 (Fullscreen)
※ブラウザ上の通常テキスト選択および Ctrl+C によるコピーは許可する。

### 10.3 JavaScript ダイアログ制御

- `alert()`: 最大500文字とし、超過分は末尾を `...` で省略表示する。
- `confirm()`: OK=true, Cancel=false を返す。
- `prompt()`: Qt標準の入力ダイアログを表示し、Cancel時は null 相当（空文字列）を返す。

### 10.4 画面遷移・ウィンドウ制御

- 新規Window、新規Tabの生成は遮断する（`createWindow` は自身のPageを返して同一Viewへ統合する）。
- `about:blank` の新規ウィンドウ要求は拒否する。
- `target="_blank"` や未定義targetのリンクはすべて同一Viewで遷移する。
- 外部プロトコル（`mailto:`, `tel:` 等）や直接スクリプト実行（`javascript:`, `data:`, `blob:`）への直接遷移は拒否する。
- `http`, `https`, `file` スキームのみ遷移を許可する。別ホストへの遷移も手動操作に限り許可する。

---

## 11. ナビゲーション制御

- 誤操作・不正遷移を防ぐため、アドレスバー（URLバー）は設けない。
- 自動画面遷移は一切実装せず、ユーザーの手動操作のみでナビゲーションする。
- **ロード世代管理 (`load_generation_id`)**: ナビゲーション開始（`loadStarted`）ごとにインクリメントし、タイムアウトや古い世代の `loadFinished` イベントを無効化・破棄する。
- **ロードタイムアウト**: 10秒とし、超過時はロードを停止（`web_view.stop()`）してトースト通知を表示する。
- **キー操作**:
  - `F5`: 再読み込み
  - `Esc`: ロード停止
  - `Alt+Left` / `Alt+Right`: 戻る / 進む
  - ツールバー「ホーム」: `config.base_url` へ戻る（URL同一時はリロードしない）

---

## 12. 画面遷移待機・DOM変化検知

F9によるデータ読み取り完了後、5秒間の画面遷移待機モード（`SCREEN_TRANSITION_WAIT`）へ移行する。

1. **ポーリング制御**:
   - `QTimer` により 100ms 間隔でポーリングを実行する。
   - 非同期JavaScript callbackの完了待ちガード（`is_polling_busy`）を設け、callback未完了時の多重実行を防止する。
2. **早期アンロック条件**:
   - **URL変化**: 現在URLと直前URLが不一致となった場合、即座にタイマーを停止して READY 状態へ復帰する。
   - **DOMハッシュ変化**: テーブル行データから算出したハッシュが直前ハッシュと異なる場合、即座に READY 状態へ復帰する。
3. **DOMハッシュ計算式**:
   各行について以下を順序通り連結した文字列を作成し、SHA-256でハッシュ化する。
   `学籍番号|受講区分|科目|指示書MD5\n`
   （指示書MD5は前処理後の `cleaned_instruction` に対する32文字のMD5ダイジェスト）
4. **待機終了時トースト**:
   5秒間URL・DOMハッシュともに変化が検知されなかった場合はタイマーを停止し、「遷移を検知できませんでしたがロックを解除しました」とトースト表示して通常READY状態へ戻す。

---

## 13. DOMテーブル抽出仕様 (extract_table.js)

### 13.1 DOM安定判定（ローディング中ガード）

1. **ローディング表示検知**:
   `selectors.json` の `loading_indicator` に定義された要素（`.loading`, `.spinner`, `[aria-busy='true']` 等）が存在かつ可視状態である場合、読み取りを行わず即時 `{success: false, notStable: true}` を返却する。
2. **直近DOM変化監視 (`MutationObserver`)**:
   `document.body` にインストールした MutationObserver により、直近 500ms 以内にDOM変更（子要素の増減等）が発生していた場合は描画中とみなし、即時 `{success: false, notStable: true}` を返却する。
   Python側はこれを受け、「ページを読み込み中です。描画完了後にもう一度読み取ってください。」とトースト表示する。

### 13.2 教室情報・年度の抽出

`selectors.json` で定義されたセレクタリストを優先度順に探索し、以下の3情報を抽出する。

1. **教室名 (`classroom_name`)**: 候補要素のテキストを取得。タグ内の削除ボタン（`.delete`, `button`）のテキストはクローンノードから除去して正確な名称を抽出する。
2. **教室コード (`classroom_code`)**: 入力欄（input）の `value` またはテキストから抽出する。
3. **年度 (`school_year`)**: select要素の選択中オプション（`selectedOptions`）または「YYYY年」形式のテキストから抽出する。
※候補セレクタで見つからない場合は、画面内のラベル要素（`th`, `label`）から「年度/教室」ラベルを探索するフォールバックを備える。
※教室名または教室コードのいずれかが取得できない場合は、誤抽出防止のため「教室情報を取得できませんでした。このページは読み取り対象として登録しません。」と通知し、データ登録を行わない。

### 13.3 対象テーブル探索と可視判定

- 画面内のすべての `table` 要素を候補とし、可視テーブルのみを対象とする。
- 非表示要素（`display: none`, `visibility: hidden`, 幅0または高さ0, `offsetParent === null`）は除外する。
- ヘッダーセル（`th`, `td`）から4必須論理項目（学籍番号、受講区分、科目、指示書）とのマッチング総合スコアを計算し、最大スコアのテーブルを採用する。

### 13.4 論理列マッピングと優先順位

- セル属性 `data-label` が存在する場合、ヘッダー文字列よりも `data-label` を優先して論理項目と照合する。
- ヘッダー文字列・エイリアスは、NFKC正規化・大文字化・空白除去を行って照合する。
- 完全一致（2点）、部分一致（1点）とし、4論理項目を重複なく割り当てられる最適な組み合わせを選択する。
- 学年列（`grade`）のエイリアス（学年, 学齢, 学年/部活 等）が存在する場合は、補助列インデックスとして `columnMap.grade` を記録する。

### 13.5 生徒セルからの学籍番号および生徒氏名の抽出

生徒セル内に学籍番号と氏名が同居する構造に対応する。

1. **学籍番号 (`student_id`)**:
   セルの行ごとに探索し、最初の有効なASCII英数字列を学籍番号として確定する。
2. **生徒氏名 (`student_name`)**:
   学籍番号行を除外した残りの行からテキストを取得し、全角スペース・タブを正規化して半角スペース1個で姓と名を結合する。角括弧やボタンラベル（詳細, 編集, 削除 等）は自動的に除外する。

### 13.6 学年 (`grade`) の抽出と正規化

`columnMap.grade` またはメタセルから学年文字列を取得し、NFKC正規化（全角数字を半角数字に統一: 高２→高2, 中３→中3）を行い前後の空白を除去する。

### 13.7 指示書（備考欄）本文の取得

- 指示書列のセルから表示テキスト（`innerText`）を取得する。
- セル内に `input` や `textarea` が存在する場合は、その `.value` をフォールバック取得する。
- 生テキストから NUL文字（`\x00`）のみを除去して `raw_instruction` として保持する。

### 13.8 行の除外判定

- **セル結合行**: セル内に `rowSpan >= 2` または `colSpan >= 2` を含む行は自動スキップする。
- **サマリー行**: 学籍番号セルの正規化テキストが「合計」「総計」「計」「小計」「平均」「件数」に一致する行は除外する。

### 13.9 次ページ判定 (`hasNext`)

画面内の操作可能要素（`a`, `button`, `input[type=button]`, `[role=button]`）から、「次へ」「次」「NEXT」「次ページ」「＞」「>」「▶」等のテキストを持つ有効な要素を検出し、`hasNext` フラグとして返却する。

### 13.10 行単位異常率ガード

テーブル内の行のうち、データ取得に失敗（スキップ）した行の割合が 50% を超えた場合（有効評価行5行以上）は、ページ構造の異常と判断してデータ登録を中断し、「テーブル行の大部分（X/Y行）でデータ取得に失敗しました。ページ構造を確認してください。」とトースト警告する。

---

## 14. データモデル (models.py)

```python
class Severity(Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    REVIEW = "REVIEW"
    WARNING = "WARNING"
    INFO = "INFO"
    PASS = "PASS"

class ConfidenceLevel(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class SectionStatus(Enum):
    MISSING = "MISSING"
    EMPTY = "EMPTY"
    INVALID = "INVALID"
    VALID = "VALID"
    PARTIAL = "PARTIAL"

class UnclassifiedType(Enum):
    UNKNOWN_HEADING = "UNKNOWN_HEADING"
    FREE_TEXT = "FREE_TEXT"
    PARSER_CANDIDATE = "PARSER_CANDIDATE"

@dataclass(slots=True)
class TextbookItem:
    name: str
    raw_status: str
    category: str  # 所持, 購入, 未所持, コピー, 未確定, 不明, 補足
    is_valid: bool
    evaluation_note: str = ""
    supplementary: str = ""

@dataclass(slots=True)
class UnclassifiedItem:
    line_number: int
    raw_text: str
    item_type: UnclassifiedType
    candidate_heading: str = ""
    estimated_section: str = ""

@dataclass(slots=True)
class ExclusionStats:
    total_html_records: int = 0
    target_records: int = 0
    total_excluded: int = 0
    demo_excluded: int = 0
    withdrawn_excluded: int = 0
    declined_excluded: int = 0

@dataclass(slots=True)
class CurriculumRecord:
    student_id: str
    division: str
    subject: str
    raw_instruction: str
    meta_cells: Dict[str, str] = field(default_factory=dict)
    cleaned_instruction: Optional[str] = None
    school_year: str = ""
    classroom_code: str = ""
    classroom_name: str = ""
    student_name: str = ""
    grade: str = ""

@dataclass(slots=True)
class EvaluationIssue:
    severity: Severity
    rule_id: str
    field: str
    message: str
    condition: str = ""
    fix_suggestion: str = ""

@dataclass(slots=True)
class EvaluationResult:
    severity: Severity
    errors: List[str]
    warnings: List[str]
    parsed_sections: Dict[str, str]
    unclassified_count: int
    unclassified_text: str
    reviews: List[str] = field(default_factory=list)
    primary_error: str = ""
    fix_fields: List[str] = field(default_factory=list)
    issues: List[EvaluationIssue] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    parse_traces: List[Dict[str, str]] = field(default_factory=list)
    textbook_items: List[TextbookItem] = field(default_factory=list)
    unclassified_items: List[UnclassifiedItem] = field(default_factory=list)
    section_statuses: Dict[str, SectionStatus] = field(default_factory=dict)
    rule_version: str = "1.0.0"
```

---

## 15. テキスト前処理 (normalization.py)

### 15.1 clean_instruction

指示書本文の正規化は以下の9工程を順序通りに実行する。

1. **制御文字・不可視文字除去**: BOM（`\uFEFF`）、ゼロ幅スペース（`\u200B`等）、双方向制御文字、Unicode `Cc`/`Cf` 文字を除去する（`\n`, `\r`, `\t` は意味を持つため保持）。
2. **HTML Entity デコード**: `html.unescape()` を1回実行する。
3. **NFKC 正規化**: 全角英数・記号の正規化。
4. **改行統一**: `\r\n` および `\r` を単一の `\n` へ変換する。
5. **Unicode空白変換**: タブおよびUnicode特殊空白を半角スペースへ変換する。
6. **行内連続空白圧縮**: 2つ以上の半角スペースを1つに圧縮する。
7. **各行 trim**: 各行の前後の空白を除去する。
8. **連続空行圧縮**: 3つ以上の連続改行（`\n{3,}`）を2つの改行（`\n\n`）へ圧縮する。
9. **全体 trim**: テキスト全体の前後の空白を除去する。

### 15.2 句点後改行の自動挿入 (format_sentence_newlines)

Excel出力表示時、可読性を高めるため、句点（`。`, `！`, `？`, `!`, `?`）の直後に改行を自動挿入する。長文中の見出し記号（`【`）の前にも自動改行を挿入する。

---

## 16. 指示書セクション解析 (parser.py)

### 16.1 正準セクション定義

- **常時必須セクション**:
  - `作成者` (`required=True`)
  - `教材` (`required=True`)
  - `進め方` (`required=True`)
  - `生徒情報` (`required=True`)
  - `小テスト` (`required=True`)
  - `宿題` (`required=True`)
- **条件付き必須セクション**:
  - `志望校` (`required=False`、学年条件に応じて動的に必須化)

### 16.2 見出しエイリアス

最長一致優先で照合する。

- **作成者**: 作成者・作成日, 作成者, 制作者, 担当者, 担当, 作成, 記入者, 講師名, 講師
- **志望校**: 目標、志望校, 目標・志望校, 生徒情報、志望校, 現時点での志望校, 志望校, 受験校, 第一志望, 第1志望
- **教材**: 設定教材について, 教材, 使用教材, メイン教材, 補助教材, 教材名, テキスト
- **小テスト**: 小テスト・単語テスト, 小テスト・確認テスト, 単語テスト・小テスト, 小テストスケジュール, 授業確認テスト, 小テスト内容, 小テスト, 単語テスト, 確認テスト, テスト
- **宿題**: 宿題スケジュール, 宿題, 課題, 家庭学習
- **進め方**: 授業スケジュール, 授業ごとの指示, 授業の流れ, 内容、進め方, 内容・進め方, 授業の進め方, 進め方, 進み方, 授業, 指導方針, 授業方針, 計画, カリキュラム
- **生徒情報**: 生徒情報、特記事項, 生徒情報・特記事項, 生徒情報／特記事項, 生徒情報(特記事項), 生徒情報（特記事項）, 生徒の特徴, 授業の注意点, 生徒情報, 生徒備考, 特記事項, 生徒状況

### 16.3 番号付き見出しおよび見出し照合規則

- **行頭装飾**: `#`, `-`, `*`, `・`, `【`, `[`, `(`, `★`, `⚠`, `※` 等の記号を除去してから見出し語と照合する。
- **番号付き見出し**: `1作成者`, `2志望校`, `1.作成者`, `①作成者` 等の番号プレフィックスを除去して見出しを照合する。ただし、「1回目」「1講」「1コマ目」等の授業回数表記は通常本文として扱い、見出しから除外する。
- **コロン区切り**: 見出し語直後の `:` または `：` で区切られた行頭テキストを見出しラベルとして認識する。

### 16.4 論理改行の自動復元 (restore_logical_newlines)

HTMLコピー時に改行が失われ、`【作成者】山田【教材】ウイニング【進め方】...` のように一行に連続している場合、既知見出しキーワードの直前に自動で論理改行（`\n`）を挿入して分割する。

### 16.5 生徒情報からの志望校補助抽出

指示書内に独立した志望校見出しが存在せず、かつ生徒情報セクション内に「志望校：〇〇高校」「志望校は〇〇大学」等の記述が含まれている場合、志望校を補助抽出して登録する（パーストレース信頼度: `LOW`）。

### 16.6 未知見出しの分類と推定

未知の見出し行を検知した場合、未分類テキスト（`unclassified_text`）として保持し、以下の3つに分類する。

1. `UNKNOWN_HEADING`: 独立した見出し構文を持つ行
2. `FREE_TEXT`: 通常の自由記述行
3. `PARSER_CANDIDATE`: キーワードから正準セクションへの割り当て候補と推定される行

### 16.7 パーストレース記録 (parse_traces)

各行の解析過程（行番号、原文行、検出見出し、正規化見出し、割当セクション、信頼度 HIGH/MEDIUM/LOW、本文）を構造化トレースとして保持する。

---

## 17. ブラックリスト判定

以下の文字列は、前処理後に完全一致した場合に「無効値（未記載・空欄相当）」として判定する。

`未定`, `なし`, `特になし`, `特にありません`, `特に問題ありません`, `問題なし`, `問題ありません`, `問題ありません。`, `前回と同じ`, `前回と同じです`, `不要`, `N/A`, `NULL`, `おまかせ`, `良好`, `-`, `ー`, `―`, `−`, `－`, `_`

比較時は `normalize_for_blacklist`（NFKC正規化、全空白除去、指定句読点除去）を施した上で完全一致判定を行う。

---

## 18. セクション評価仕様

### 18.1 作成者

- **正規化**: NFKC → 空白処理 → 末尾敬称除去（先生, 講師, さん, 氏, 様） → 末尾括弧除去 → 再度敬称除去 → 大文字化 → 内部空白除去
- **判定**: 見出し欠損または空欄・ブラックリスト時は `ERR_AUTHOR_MISSING`。

### 18.2 志望校（学年条件付き必須判定）

- **条件付き必須判定**:
  1. **高校3年生**（学年表記が高3, 高校3, 高三, H3, K3等）: 必須 → 欠損時は `ERR_SCHOOL_REQUIRED_HIGH3`
  2. **公立中学3年生**（中3かつ私立・国立でない）: 必須 → 欠損時は `ERR_SCHOOL_REQUIRED_JUNIOR3`
  3. **小学6年生中学受験**（小6かつ中受・中学受験・中学入試キーワードあり）: 必須 → 欠損時は `ERR_SCHOOL_REQUIRED_ELEM6`
  4. **その他の学年**（高1, 高2, 中1, 中2, 小5等）: 任意セクション
- **曖昧表現の検知 (REV_SCHOOL_UNCERTAIN)**:
  学校名区分（私立/公立等）の有無は不問とするが、「ところ」「未定」「検討中」「模索中」「進学希望」「未定です」「決まっていない」「大学進学」などの曖昧な表現が含まれる場合は `REV_SCHOOL_UNCERTAIN`（要確認、REVIEWランク）を発行する。

### 18.3 教材（教材単位の構造化評価）

教材セクションを行・カンマ・読点で分割し、教材ごとにステータスを評価する。

1. **補足事項行の自動分離**: 行頭が `※`, `注`, `注意`, `備考`, 矢印プレフィックス（`→`, `=>`）、日付面談連絡、保護者要望等の記述である場合、教材ではなく「補足事項」として分類し、ステータス評価対象から除外する。
2. **ステータスカテゴリ判定**:
   - **所持**: 所持(済), 所持済, 所持, 手持ち, 本人所持, 持込教材, 持込, 持ち込み
   - **購入**: 購入予定, 購入
   - **未所持**: 未所持です, 未所持, 未購入
   - **コピー**: コピー教材, コピー, 複写
   - **未確定 (エラー)**: `所持?`, `所持？`, `所持か不明`, `所持か要確認`, `？`, `?`
   - **不明 (エラー)**: ステータスキーワードの記載がないもの
3. **エラー発行**:
   - 教材見出し欠損または空欄: `ERR_TEXTBOOK_MISSING`
   - 有効な教材に未確定・不明のものが1つでもある場合: `ERR_TEXTBOOK_STATUS_MISSING`

### 18.4 進め方

- 見出し欠損または空欄・ブラックリスト: `ERR_PLAN_MISSING`
- 記号・空白を除去した有効文字数が `min_plan_length = 5` 文字未満: `ERR_PLAN_TOO_SHORT`

### 18.5 生徒情報

- 見出し欠損または空欄・ブラックリスト: `ERR_INFO_MISSING`
- 記号・空白を除去した有効文字数が `min_info_length = 3` 文字未満: `ERR_INFO_TOO_SHORT`

### 18.6 小テスト

- 見出し欠損または空欄・ブラックリスト: `ERR_TEST_MISSING`

### 18.7 宿題

- 見出し欠損または空欄・ブラックリスト: `ERR_HOMEWORK_MISSING`

### 18.8 講習授業判定

受講区分（`division`）に「講習」「夏期」「冬期」「春期」が含まれる場合:

- 講座数（コマ数・授業数）の記載がない場合: `ERR_COURSE_COUNT_MISSING` (ERROR)
- 目標の記載がない場合: `WARN_GOAL_MISSING` (WARNING)

---

## 19. 未分類テキストの評価

1. 未分類行が存在し、それが `UNKNOWN_HEADING` または `PARSER_CANDIDATE` である場合（既知メタ見出しの目標・講座数等を除く）:
   `WARN_UNCLASSIFIED_TEXT` (WARNING) を発行する。
2. エラー・レビュー・警告がなく、未分類の自由記述（`FREE_TEXT`）のみが存在する場合:
   警告（WARNING）とせず、情報（`Severity.INFO`）として判定し、`INFO_UNCLASSIFIED_TEXT` を付与する。

---

## 20. コピペ判定 (Duplicate Info)

- **条件**: 同一の担当者（正規化済み作成者名）グループ内でのみ比較を行う。
- **比較対象**: 空白・改行を除去した生徒情報テキスト。
- **類似度計算**:
  - 15文字未満: 完全一致のみを重複とみなす。
  - 15文字以上: 文字単位の 2-gram Jaccard 係数を計算し、類似度 `>= 0.8` を重複と判定する。
- **警告発行**: 同一グループ内で重複・類似レコードが 3 件以上存在する場合、該当する全レコードに `WARN_COPY_PASTE_SUSPECTED` を付与する。

---

## 21. 集計対象除外ルール (filter_target_records)

集計処理開始時、以下の条件に該当するレコードを自動除外し、除外統計（`ExclusionStats`）へ集計する。

1. **デモ生徒除外 (`DEMO`)**: 生徒氏名（`student_name`）または生徒セルの名字が完全に「デモ」である生徒（「デモ田」など名字以外にデモを含む生徒は除外しない）。
2. **退塾生徒除外 (`WITHDRAWN`)**: 在籍ステータスに「退塾」が含まれる生徒。
3. **見送り生徒除外 (`DECLINED`)**: 在籍ステータスに「見送り」が含まれる生徒。

---

## 22. 判定エンジンアーキテクチャ

判定エンジンは以下の関数で構成される純粋関数群とする。

```python
def evaluate_single_record(record: CurriculumRecord, config: AppConfig) -> EvaluationResult:
    """単一レコードの独立判定を行う"""

def evaluate_batch_duplicates(
    records: List[CurriculumRecord],
    results: List[EvaluationResult],
    config: AppConfig
) -> List[EvaluationResult]:
    """バッチ全体のコピペ重複判定を行う（入力オブジェクトを破壊せず新しいコピーを返す）"""

def filter_target_records(
    records: List[CurriculumRecord]
) -> Tuple[List[CurriculumRecord], ExclusionStats]:
    """集計対象外レコードの除外と除外統計集計を行う"""
```

### 22.1 Severity 決定階層

1. 備考欄完全空欄（`CRIT_INSTRUCTION_EMPTY`）あり → **`CRITICAL`**
2. `errors` が1件以上あり → **`ERROR`**
3. `errors` なし、`reviews` が1件以上あり → **`REVIEW`**
4. `errors`/`reviews` なし、`warnings` が1件以上あり → **`WARNING`**
5. 上記不備がなく、未分類テキストのみが存在 → **`INFO`**
6. 不備・未分類なし → **`PASS`**

### 22.2 最重要エラー (`primary_error`) と修正項目 (`fix_fields`)

- `PRIMARY_RULE_PRIORITY` に従い、レコード内で最も優先度の高いエラー・警告を `primary_error` として決定する。
- レコード内のエラー・レビューに対応する対象項目（作成者、教材ステータス、進め方、生徒情報、志望校、小テスト、宿題、講座数など）を `fix_fields` として特定する。
- 自然言語による機械的判定根拠（`reasons`）を生成する。

---

## 23. Rule ID 体系

| Severity | Rule ID | 対象項目 | 表示メッセージ | 発生条件 | 修正方法 |

|---|---|---|---|---|---|

| **CRITICAL** | `CRIT_INSTRUCTION_EMPTY` | 備考欄 | 備考欄が未作成です | 備考欄が空文字・空白のみ、または取得失敗 | 備考欄を入力してください |
| **ERROR** | `ERR_SECTION_MISSING` | 必須項目 | 必須項目が不足しています | 必須項目が不足している | 不足している必須項目を記載してください |
| **ERROR** | `ERR_SECTION_EMPTY` | 必須項目 | 必須項目が空欄です | 必須項目が空欄 | 必須項目の内容を記載してください |
| **ERROR** | `ERR_AUTHOR_MISSING` | 作成者 | 作成者が未記載です | 作成者見出しがない、または空欄・ブラックリスト | 作成者（担当講師名）を記載してください |
| **ERROR** | `ERR_TEXTBOOK_MISSING` | 教材 | 教材が未記載です | 教材見出しがない、または空欄・ブラックリスト | 使用教材を記載してください |
| **ERROR** | `ERR_TEXTBOOK_STATUS_MISSING` | 教材 | 教材の所持状態が未記載です | 教材に有効なステータスがない、または未確定（所持?等） | 教材の所持・未所持・持込・購入・コピー等を記載してください |
| **ERROR** | `ERR_PLAN_MISSING` | 進め方 | 進め方が未記載です | 進め方見出しがない、または空欄・ブラックリスト | 進め方を記載してください |
| **ERROR** | `ERR_PLAN_TOO_SHORT` | 進め方 | 進め方の文字数が不足しています | 進め方の有効文字数が設定（5文字）未満 | 進め方の指導方針を具体的に記載してください |
| **ERROR** | `ERR_INFO_MISSING` | 生徒情報 | 生徒情報が未記載です | 生徒情報見出しがない、または空欄・ブラックリスト | 生徒情報を記載してください |
| **ERROR** | `ERR_INFO_TOO_SHORT` | 生徒情報 | 生徒情報の文字数が不足しています | 生徒情報の有効文字数が設定（3文字）未満 | 生徒の学力状況や性格などを具体的に記載してください |
| **ERROR** | `ERR_TEST_MISSING` | 小テスト | 小テストが未記載です | 小テスト見出しがない、または空欄・ブラックリスト | 小テストの実施内容を記載してください |
| **ERROR** | `ERR_HOMEWORK_MISSING` | 宿題 | 宿題の内容が未記載です | 宿題見出しがない、または空欄・ブラックリスト | 宿題の内容を具体的に記載してください |
| **ERROR** | `ERR_SCHOOL_REQUIRED_HIGH3` | 志望校 | 高3のため志望校が必須です | 高3で志望校見出しがない、または空欄 | 高3のため志望校を記載してください |
| **ERROR** | `ERR_SCHOOL_REQUIRED_JUNIOR3` | 志望校 | 公立中3のため志望校が必須です | 公立中3で志望校見出しがない、または空欄 | 公立中3のため志望校を記載してください |
| **ERROR** | `ERR_SCHOOL_REQUIRED_ELEM6` | 志望校 | 小6中受のため志望校が必須です | 小6中受で志望校見出しがない、または空欄 | 小6中受のため志望校を記載してください |
| **ERROR** | `ERR_COURSE_COUNT_MISSING` | 講座数 | 講習授業のため講座数が必須です | 受講区分が講習で講座数・授業数の記載がない | 講習授業のため講座数・授業数を記載してください |
| **ERROR** | `ERR_PARSER_EXCEPTION` | システム | 解析処理中に例外が発生しました | 解析処理中に例外が発生 | 開発元へお問い合わせください |
| **ERROR** | `ERR_INTERNAL_EVALUATION` | システム | 内部評価エラー | 内部評価エラー | 開発元へお問い合わせください |
| **REVIEW** | `REV_SCHOOL_UNCERTAIN` | 志望校 | 志望校の記載内容に確認が必要です | 志望校に学校名と判断できない曖昧な記述（未定、ところ等）がある | 志望校を正式な学校名（大学・高校・中学名）で記載してください |
| **WARNING** | `WARN_TEXTBOOK_NO_STATUS` | 教材 | 教材の所持状態が未記載です | 教材のステータスが未記載 | 教材の所持状態を記載してください |
| **WARNING** | `WARN_SCHOOL_NO_TYPE` | 志望校 | 学校の区分が不明です | 志望校に学校区分がない | 学校区分を記載してください |
| **WARNING** | `WARN_TEST_CRITERIA_MISSING` | 小テスト | 小テストの範囲または合格基準が不明です | 範囲または基準が欠損 | 範囲または合格基準を記載してください |
| **WARNING** | `WARN_GOAL_MISSING` | 目標 | 講習授業の目標の記載が推奨されます | 受講区分が講習で目標の記載がない | 講習授業の目標の記載を推奨します |
| **WARNING** | `WARN_COPY_PASTE_SUSPECTED` | 生徒情報 | 類似内容のコピー＆ペーストが疑われます | 同一作成者内で生徒情報が類似・重複（3件以上） | 他生徒との重複記述がないか確認してください |
| **WARNING** | `WARN_UNCLASSIFIED_TEXT` | 未分類テキスト | 未分類のテキストが存在します | 未知の見出しが存在する | 見出しの表記揺れまたは記載内容を確認してください |
| **INFO** | `INFO_UNCLASSIFIED_TEXT` | 未分類テキスト | 未分類のテキストが存在します | エラー・警告はないが自由記述が存在する | 必要に応じて見出しの表記揺れまたは記載内容を確認してください |

---

## 24. Repository & Undo 管理

- 操作は GUI メインスレッドでのみ実行する。
- 順序は初回追加順（`OrderedDict`）を維持する。同一キー更新時もキーの位置は変更しない。
- **Undo履歴**: 読み込みバッチ単位で管理し、最大30バッチ（`UNDO_MAX_HISTORY = 30`）まで保持する。
- 各UndoRecordには新規追加キーリストと更新前Recordのスナップショットを保持し、Undo実行時は完全な差し戻しを行う。
- Undo実行後はキャッシュをアトミックに再保存する。データが0件になった場合はキャッシュファイルを物理削除する。

---

## 25. キャッシュ管理 (cache.py)

- **ファイル名**: `user_data/_session_cache.jsonl`
- **一時ファイル名**: `user_data/_session_cache.jsonl.tmp`
- **メタデータ行（1行目）**:

  ```json
  {"__meta__": true, "schema_version": 1, "created_at": "ISO8601日時", "record_count": 総件数, "app_version": "1.1.0"}
  ```

- **レコード行（2行目以降）**:
  `student_id`, `division`, `subject`, `raw_instruction`, `meta_cells`, `school_year`, `classroom_code`, `classroom_name`, `student_name`, `grade` を含む辞書をJSONL形式で書き込む。
- **耐障害性復元**: メタ行が破損していても、残りの行から有効なレコードを救済復元する。破損行はスキップしてスキップ件数をユーザーに通知する。
- **孤立一時ファイル清掃**: アプリ起動時にクラッシュ等で残された `_session_cache.jsonl.tmp` を検出して自動削除する。

---

## 26. cache_is_dirty 状態遷移

- 起動時: `False`
- バッチデータがメモリに追加された瞬間: `True`
- キャッシュのアトミック保存成功時: `False`
- キャッシュ保存失敗時は、次回のF9読み込みのみを禁止し、既存データの集計・Undo・リセット・終了は許可する。

---

## 27. F9読み込みバッチ処理

- READY状態でのみ有効（集計中、ロード中は無効）。
- 有効データが0件の場合は「有効なデータがありません」とトースト表示し、リポジトリやキャッシュを変更しない。
- **読み取り件数の妥当性監視**: 直前の読み取り件数が10件以上あった場合において、今回の読み取り件数が前回の 1/3 以下に激減したときは、「今回の読み取り件数（X件）が前回（Y件）と比べて大幅に少なくなっています。ページ内容を確認してください。」とトースト警告する。

---

## 28. 成果物出力仕様 (Excel & CSV)

集計実行時、ユーザーの「ダウンロード」フォルダ（`Path.home() / "Downloads"`）に以下の2種類の成果物ファイルを同時に出力する。

### 28.1 メイン成果物: openpyxl 高機能Excel出力 (.xlsx)

ファイル名: `Curriculum_Analysis_YYYYMMDD_HHMMSS.xlsx`

以下の 7 つの専用シートを構築する。

1. **`チェック結果` シート** (全件メイン):
   - 18列構成: `教室名`, `教室コード`, `年度`, `学籍番号`, `生徒名`, `学年`, `受講区分`, `科目`, `判定`, `修正項目`, `エラー`, `警告`, `作成者`, `志望校`, `教材`, `進め方`, `生徒情報`, `小テスト`, `宿題`, `未分類テキスト`
   - 行全体を Severity 判定ランクに応じて色分け（CRITICAL: 濃赤, ERROR: 薄赤, REVIEW: 薄橙, WARNING: 薄黄, INFO: 薄青, PASS: 白）
   - 長文テキスト（進め方、生徒情報、未分類テキスト）は句点後の自動改行を適用
   - 1行目にヘッダー背景色（`#1F4E78`、白文字太字）、オートフィルター設定、A2セルでのウィンドウ枠固定
2. **`判定一覧` シート**:
   - 8列構成: `判定`, `Rule ID`, `対象項目`, `発生条件`, `表示メッセージ`, `修正方法`, `件数`, `発生率`
   - 全Rule IDの発生状況を網羅集計
3. **`解析詳細` シート** (Parser Debug Mode):
   - 10列構成: `学籍番号`, `生徒名`, `学年`, `行番号`, `原文行`, `検出見出し`, `正規化見出し`, `割当セクション`, `信頼度`, `本文`
   - パーストレースを全行出力
4. **`原文` シート**:
   - 10列構成: `教室名`, `教室コード`, `年度`, `学籍番号`, `生徒名`, `学年`, `受講区分`, `科目`, `判定`, `原文備考欄`
   - 取得した生データをそのまま確認可能
5. **`サマリー` シート**:
   - 集計対象除外統計（HTML取得件数、集計対象件数、デモ除外、退塾除外、見送り除外）
   - 全体判定ステータス（CRITICAL, ERROR, REVIEW, WARNING, INFO, PASS 件数と比率）
   - 教室別集計マトリックス（列=教室名、行=各項目エラー件数・合格率、右端=全体）
6. **`未知表記` シート**:
   - 未知見出しの自動収集、出現頻度、推定セクション、改善候補一覧
7. **`教材詳細` シート**:
   - 教材ごとの構造化データ（教材名、ステータス、カテゴリ、個別判定、補足事項）

#### Excel出力の安全性と耐障害性

- **一時ファイル経由の保存**: `~tmp_...xlsx` に書き込み、保存後検証（ファイルサイズおよび必須7シートの存在確認）を実行した上で正式ファイルへアトミック置換する。
- **ファイルロック検知時の自動別名保存**: 出力先ExcelファイルがExcelソフト等で開かれていてロックされている場合、エラーで中断せず自動的に `Curriculum_Analysis_YYYYMMDD_HHMMSS_1.xlsx` のように別名で保存を完遂し、「既存ファイルが使用中のため、別名で保存しました。」と通知する。

### 28.2 サブ成果物: BOM付きUTF-8固定15列CSV出力 (.csv)

ファイル名: `カリキュラムチェック_YYYYMMDD-HHMMSS.csv` (同名存在時は `_1` ～ `_999`)

- **文字コード**: UTF-8 with BOM (`utf-8-sig`)
- **改行コード**: CRLF（セル内改行もCRLF統一）
- **列構成 (固定15列)**:
  1. `学籍番号`
  2. `受講区分`
  3. `科目`
  4. `判定ランク`
  5. `要修正エラー`
  6. `確認推奨警告`
  7. `作成者`
  8. `志望校`
  9. `教材`
  10. `進め方`
  11. `生徒情報`
  12. `小テスト`
  13. `宿題`
  14. `未分類テキスト`
  15. `原文指示書`
- **Formula Injection 保護**: セル先頭が `=`, `+`, `-`, `@` の場合、先頭に `'` を付加して出力する。
- **アトミック保存と検証**: 一時CSV作成 → flush → fsync → os.replace → ヘッダー配列および件数の出力後検証。

### 28.3 Explorer連携

出力完了後、Windows Explorerを `/select` オプション付きで起動し、生成されたExcelファイル（存在しない場合はCSVファイル）を選択状態で開く。

---

## 29. 集計Worker (worker.py)

- `QThread` をベースとしたバックグラウンド非同期処理。
- **シグナル**:
  - `phase_changed = pyqtSignal(str, int)`: フェーズ名とパーセンテージを発行
  - `progress_changed = pyqtSignal(int)`: 全体進捗率を発行
  - `finished = pyqtSignal(list, list, object, str, str, bool)`: results, target_records, exclusion_stats, csv_path, excel_path, was_renamed
  - `error_occurred = pyqtSignal(str)`
- **進捗フェーズ**:
  - 0% - 5%: 集計準備・除外フィルタリング
  - 5% - 45%: 個別レコード評価
  - 45% - 50%: バッチ重複チェック
  - 50% - 55%: CSV出力
  - 55% - 95%: Excel出力（7シート構築）
  - 100%: 出力完了

---

## 30. 集計・出力後処理

1. 出力成功の検証後、キャッシュファイル（`_session_cache.jsonl`）を物理削除する。
2. キャッシュ削除成功を確認後、リポジトリの全レコードをクリアし、件数を0に戻す。
3. 完了トースト通知を表示する（重大X件, 要修正Y件, 要確認Z件, 警告W件, 情報V件, 合格U件, 除外T件）。
4. キャッシュ削除に失敗した場合は、データ消失防止のためリポジトリをクリアせず警告ダイアログを表示する。

---

## 31. リセット処理

「蓄積データをクリア」ボタン押下時:

- 確認ダイアログを表示: 「蓄積したすべてのデータを削除しますか？\nこの操作は元に戻せません。」
- 「はい」の場合、Repository、Undoスタック、キャッシュファイルを完全削除し、教室・年度情報も初期化する。ログイン状態（Cookie）および既に出力されたExcel/CSVファイルは削除しない。

---

## 32. 終了処理

- 通常終了時、ポーリングタイマーおよびロードタイマーを停止する。
- 未集計データが存在する場合、「未保存のデータがあるため終了すると消失します。\n終了しますか？」と確認ダイアログを表示する。
- `MemoryError` 発生時はGUIダイアログを出さず、stderrおよびログへ出力して直ちに `sys.exit(1)` で終了する。

---

## 33. Rendererクラッシュ対応

WebEngineのレンダリングプロセスがクラッシュ（`renderProcessTerminated`）した場合:

- `error.log` へ重大エラーを記録する。
- 「ブラウザエンジンがクラッシュしました。アプリを再起動してください。」と警告ダイアログを表示し、安全に終了する。
- リポジトリデータおよびキャッシュは削除せず保持する。

---

## 34. キーボードショートカット

- `F9`: このページを読み取る
- `Ctrl+Z`: 直前の読み取りを取り消し (Undo)
- `Ctrl+Enter` / `Ctrl+Return`: 集計してExcel出力
- `F5`: 再読み込み
- `Esc`: 読み込み停止
- `Alt+Left`: 戻る
- `Alt+Right`: 進む
- `Ctrl + +`: 拡大 (Zoom in)
- `Ctrl + -`: 縮小 (Zoom out)
- `Ctrl + 0`: 拡大率リセット (config初期値)
※集計処理（AGGREGATING）中は、すべてのアプリ操作ショートカットを無効化する。

---

## 35. ズーム仕様

- 拡大率範囲: `0.5` ～ `2.0`
- 刻み幅: `0.1`
- 起動時は `config.ini` の `zoom_factor` を適用する。

---

## 36. ブラウザ右クリックコンテキストメニュー

右クリックメニューは以下の項目のみに制限する。

- `コピー` (テキスト選択時のみ有効)
- `戻る` (履歴がある場合のみ有効)
- `進む` (履歴がある場合のみ有効)
- `再読み込み`
※保存、印刷、ソース表示、検証（Inspect）等は非表示とする。

---

## 37. PDF / ダウンロード / 印刷遮断

- PDFのインライン閲覧は許可する。
- WebEngineからのファイルダウンロード要求はすべてキャンセルし、「本ブラウザからのファイルダウンロードは無効化されています」とトースト通知する。
- 印刷ダイアログの呼び出しも遮断する。

---

## 38. UI・画面設計

### 38.1 メインウィンドウ

- 初期サイズ: `1380 x 880`
- 最小サイズ: `1024 x 700`
- ウィンドウタイトル: `[蓄積: N件] カリキュラム備考欄チェックシステム v1.1.0`

### 38.2 ツールバー構成

左から順に配置:

1. `← 戻る`
2. `→ 進む`
3. `↻ 再読み込み`
4. `ホーム`
5. （区切り線）
6. `このページを読み取る (F9)`
7. `↶ 1つ戻す (Ctrl+Z) (N)` (履歴0件時は無効化)
8. `集計してExcel出力 (N件)` (蓄積0件時は無効化)
9. （伸縮スペース）
10. `蓄積データをクリア`

### 38.3 ステータスバー常時表示

ステータスバーの右側に以下の情報を常時表示する。
`教室：〇〇　年度：〇〇　今回：N件　累計：M件`

### 38.4 全画面ローディングオーバーレイ (LoadingOverlay)

読み取り中および集計実行中、WebEngineの上に全画面の半透明マスクを表示し、全マウス・キー操作をロックする。中央ボックスに進捗プログレスバーと現在のフェーズ名を表示する。

### 38.5 起動時案内ダイアログ (StartupGuideDialog)

初回起動時、基本操作手順およびショートカット一覧を案内するダイアログを表示する。「次回からこの案内を表示しない」チェックボックスを備え、設定は `user_data/guide_settings.json` に保存する。

### 38.6 トースト通知 (ToastWidget)

画面中央下部に配置し、マウス透過（`WA_TransparentForMouseEvents`）で操作を妨げない。最大80文字、表示時間4秒、新規通知発生時は即時上書きする。

---

## 39. ログ仕様 (error.log)

- 出力先: `base_dir/error.log`
- 形式: `RotatingFileHandler`、UTF-8
- 最大サイズ: `1,048,576 bytes` (1MB)、世代数: `3` (最大4ファイル)
- 記録対象: システム例外、セレクタ異常、行スキップ、キャッシュエラー、クラッシュログ

---

## 40. セキュリティ・個人情報保護

- **ローカル完結**: 抽出された学籍番号、生徒氏名、カリキュラム備考欄データは、利用者のローカル端末内でのみ処理される。外部通信、テレメトリ、Web検索は一切行わない。
- **公開リポジトリ秘匿**: 本リポジトリのソースコード、テストデータ、ドキュメントに実在個人情報は含めない。
- **キャッシュの破棄**: セッションキャッシュはExcel/CSV出力完了時に物理削除される。

---

## 41. ビルド仕様 (tools/build.py)

- ビルドコマンド: `python tools/build.py`
- パッケージング方式: Nuitka Onefile 単一実行ファイル
- 成果物: `output/Curriculum_Analyzer_v1.1.0.exe` および `output/Curriculum_Analyzer_v1.1.0.zip`
- `--windows-console-mode=disable` により実行時の黒いコンソール画面を非表示化
- アプリアイコン（`tools/MSL分析ロゴ.ico`）をEXEに埋め込み
- `extract_table.js` を `--include-data-files` でEXE内部に確実に同梱
- 配布ZIPには EXE本体、`selectors.json`、`config.ini` を同梱

---

## 42. テスト仕様

全61件の自動単体・統合・回帰テストを `pytest` で常時パスすることを必須とする。

- `test_cache_and_config.py`: キャッシュ保存・復元、部分破損救済、孤立tmp清掃、セレクタ検証、起動前診断、config読み込み
- `test_dom_extraction.py`: テーブル抽出、セレクタフォールバック、ローディング検知、教室情報取得
- `test_excel_export.py`: Excel 7シートヘッダー・出力検証、ファイルロック検知時自動別名保存、生徒氏名配置
- `test_performance_and_safety.py`: 100件・500件ベンチマーク、再現性テスト
- `test_regression_sample.py`: 実サンプルに基づく全回帰テスト（見出し分離、教材ステータス、志望校条件付き必須、講習判定、除外ルール、論理改行復元、番号付き見出し等）

---

## 43. 仕様変更履歴 (Changelog)

### v1.1.0 完全統合改訂（現行版）

- **アプリ名称・バージョン更新**: `カリキュラム備考欄チェックシステム`、`v1.1.0`
- **Excel 7シート出力追加**: `openpyxl` による高機能マルチシートExcel（チェック結果、判定一覧、解析詳細、原文、サマリー、未知表記、教材詳細）をメイン成果物として出力。ファイルロック時の自動別名保存対応。
- **Severity 6段階化**: `CRITICAL`, `ERROR`, `REVIEW`, `WARNING`, `INFO`, `PASS`
- **Rule ID体系の拡張**: `CRIT_INSTRUCTION_EMPTY`, `ERR_TEXTBOOK_STATUS_MISSING`, `ERR_SCHOOL_REQUIRED_HIGH3/JUNIOR3/ELEM6`, `ERR_COURSE_COUNT_MISSING`, `REV_SCHOOL_UNCERTAIN`, `WARN_GOAL_MISSING`, `INFO_UNCLASSIFIED_TEXT` 等を追加
- **生徒氏名・学年・教室情報の抽出**: `selectors.json` による外部セレクタ定義、生徒氏名抽出・正規化、学年抽出・正規化
- **集計対象除外機能**: 名字が「デモ」、在籍が「退塾」「見送り」の自動除外と除外統計
- **志望校の学年条件付き必須化**: 高3、公立中3、小6中受のみ必須化、他は任意化
- **パーサー高度化**: 番号付き見出しプレフィックス対応、論理改行の自動復元、生徒情報内志望校補助抽出
- **GUI改善**: 起動時案内ダイアログ、全画面ローディングマスク、ステータスバー常時表示、読み取り妥当性監視トースト
- **起動時自己診断 & URL対話入力**: 起動前診断、`base_url` 未設定時の対話入力ダイアログ

### v1.0.0 初期リリース

- 初回確定版仕様書策定
- PyQt6-WebEngine組み込みブラウザ、テーブル抽出、4項目収集
- BOM付きUTF-8固定15列CSV出力
- Nuitka Onefile化

---

## 44. 最終凍結宣言 (v1.1.0 確定)

本書は、バージョン `1.1.0` の全実装、全テスト、ビルドスクリプト、設定体系と完全に一致する「完全統合確定仕様書」である。
本書をもって、仕様の重複・矛盾・未確定事項・参照漏れは完全に0件として凍結する。

---

## 45. 実装・保守担当への最終指示

本書をシステムの正本（Single Source of Truth）として扱うこと。
いかなる変更や機能追加を行う場合も、必ず本書の規定との整合性を確認し、変更がある場合は本書を更新した上でテストを100%パスさせること。
