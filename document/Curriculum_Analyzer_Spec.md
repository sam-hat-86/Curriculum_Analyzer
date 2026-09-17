# 授業指示書・カリキュラム 精査ブラウザシステム

## 完全統合確定仕様書（HTMLサンプル統合版）

- 文書名: `Curriculum_Analyzer_Spec.md`
- サンプルHTML統合: `sampleMSL.html` を実装・テスト設計へ反映
- アプリ名: 授業指示書・カリキュラム 精査ブラウザ
- ProductName: `Curriculum Analyzer`
- EXE名: `Curriculum_Analyzer.exe`
- 初期アプリバージョン: `1.0.0`
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

本書は、本システムの実装・テスト・ビルド・配布・保守におけるSingle Source of Truth（SSOT）である。

実装担当者は、本書にない仕様を勝手に追加してはならない。技術的に複数の実装方法が存在しても、最終結果が同一であり、既存仕様と矛盾せず、テスト方法も一意である場合に限り内部実装上の裁量を認める。

仕様訂正が必要になった場合は、既存回答を直接改変せず、新しい仕様番号として追記し、最新番号の仕様を優先する。

実装開始条件は以下をすべて満たすこととする。

- 仕様矛盾が0件
- 未確定仕様が0件
- 参照漏れが0件
- 禁止事項の確認完了
- テスト計画およびトレーサビリティ方針の確定
- 実装開始確認書への仕様書SHA-256記録

---

## 2. 目的

Web上の授業指示書・カリキュラム画面を、ユーザーが組み込みブラウザで手動操作しながら収集する。

現在表示中のHTMLテーブルから、以下の4項目を抽出する。

1. 学籍番号
2. 受講区分
3. 科目
4. 指示書

抽出したデータは内部Repositoryへ蓄積し、同一キーを統合した後、指示書本文を解析してエラー・警告を付与する。

最終成果物はBOM付きUTF-8 CSVとする。

---

## 3. 技術構成

### 3.1 実行環境

- OS: Windows 10 (1809以降) / Windows 11
- CPU: x86-64（Intel 64 / AMD64）
- Python: 3.11.x
- GUI: PyQt6
- Browser: PyQt6-WebEngine
- CSV: Python標準 `csv`
- テスト: pytest
- フォーマッタ: `black==23.9.1`
- リンター: `flake8==6.1.0`
- 型ヒント: Python標準の型ヒントを付与する。mypy等は必須としない。
- ビルド: Nuitka
- 配布形式: Onefile

### 3.2 アーキテクチャ

今回の実HTMLサンプルを基準として、抽出処理を以下の責務へ分割する。

- `browser/extract_table.js`: 可視table候補の列・行・data-label・innerTextのみ取得
- `core/normalization.py`: 学籍番号・division・subject・本文の正規化
- `core/parser.py`: 指示書section解析
- `core/evaluator.py`: ERROR/WARNING/PASS判定
- `core/repository.py`: (student_id, division, subject)単位の蓄積・更新・Undo
- `core/cache.py`: JSONL cacheの保存・復元
- `core/exporter.py`: 固定15列CSV生成
- `gui/worker.py`: 集計非同期実行
- `gui/main_window.py`: 状態機械・操作制御・通知

以下のレイヤーを分離する。

`DOM抽出 → CurriculumRecord → 判定エンジン → CSV出力`

判定エンジンはGUI・WebEngineへ依存しない純粋関数群とする。

---

## 4. 配布・GitHub設計

### 4.1 GitHub Repository

- Repository名: `Curriculum_Analyzer`
- 公開範囲: Public
- デフォルトブランチ: `main`
- GitHub Releaseを唯一の正式配布経路とする。
- Release以外の再配布物は正式配布対象外とする。
- 本番サイトの `base_url` のみ公開Repositoryへ保存可能とする。
- 認証情報、Cookie、Token、秘密鍵、実データ、個人情報はRepositoryおよびGit履歴へ保存しない。

実データを含むテストデータはローカル環境に秘匿する。Public Repositoryへ置くmock HTML / fixtureはダミーデータのみとする。

公開前に、最新ファイルだけでなくGit履歴も含めて秘密情報・個人情報が存在しないことを確認する。

一度でも秘密情報をGit履歴へ入れた場合は、公開前に履歴から完全除去する。公開後に漏えいが判明した場合は、当該credential等を速やかに失効・変更する。

### 4.2 Release

- Releaseは安定版のみ
- Pre-releaseは使用しない
- タグ形式: `v1.0.0`
- Release作成・Publishは手動
- GitHub Actionsによる自動Publishは行わない
- Latest Releaseを正式配布対象とする
- 過去Releaseは履歴・旧版取得用として残す
- Release資産はZIP 1ファイルのみ
- checksumファイルは作成しない

Release資産名:

`Curriculum_Analyzer_v1.0.0.zip`

GitHub上では英数字、アンダースコア、ハイフンを基本とし、日本語ファイル名をRelease資産名に使用しない。

### 4.3 Release ZIP

ZIPはNuitka Onefileで生成された単一EXEを中心とし、最低限以下を含む。

- `Curriculum_Analyzer.exe`
- `selectors.json`
- `config.ini`

インストール・導入および操作説明書はリポジトリの `README.md` に集約・一元化する。

総合的な使い方・操作説明はRepository側に以下を配置する。

- `doc/index.html`
- `doc/style.css`
- `doc/script.js`

`doc/` はRelease ZIPには含めない。

### 4.4 Repository README

`README.md` はGitHub上の概要説明を担う。

内容は少なくとも以下を含む。

- ソフト概要
- 対応OS
- 主要機能
- 最新Releaseへの案内
- License概要
- 公開データの扱いに関する注意

詳細な操作方法は `doc/index.html` に集約する。

### 4.5 License

ソースコード、EXE、README、ドキュメント等を含む本プロジェクトの成果物は、すべて独自Licenseの対象とする。

Public Repositoryであっても、公開そのものを第三者への利用権許諾とはみなさない。

無断使用、複製、改変、再配布、販売等を許可しない独自Licenseとして管理する。

`LICENSE` ファイルをRepositoryへ配置する。

---

## 5. Windows EXEメタデータ

以下をEXEへ設定する。

- CompanyName: `sam-hat-86`
- ProductName: `Curriculum Analyzer`
- FileDescription: `カリキュラム分析ソフト`
- OriginalFilename: `Curriculum_Analyzer.exe`
- FileVersion: `1.0.0`
- ProductVersion: `1.0.0`

EXE名:

`Curriculum_Analyzer.exe`

---

## 6. バージョン管理

アプリバージョンとcache schema versionは別定数として管理する。

- app version: `1.0.0`
- release tag: `v1.0.0`
- cache schema: `1`

アプリバージョンはSemVerのMAJOR.MINOR.PATCHで管理する。

`config.ini`にはアプリバージョンを保存しない。

GitHub Releaseのバージョン、EXE Version情報、アプリ表示version、ZIP名は同一アプリバージョンへ対応させる。

---

## 7. アプリ起動

### 7.1 パス

Onefile実行時の `base_dir` は、Onefile EXE自身の所在ディレクトリを基準とする。

開発環境では `__file__` を基準とする。

主なファイル配置:

- `Curriculum_Analyzer.exe`
- `config.ini`
- `user_data/`
- `_session_cache.jsonl`
- `error.log`
- CSV成果物

### 7.2 起動順序

基本的な起動順序は以下とする。

1. `base_dir` 解決
2. 最低限のfallback logger初期化
3. Mutex生成
4. `config.ini` 読み込み・検証
5. `user_data` 初期化
6. `QApplication` 生成
7. 既存ショートカット/既存起動の処理
8. cache復元確認
9. MainWindow生成
10. WebEngine Profile生成
11. Browser生成
12. `base_url` 読み込み

### 7.3 High-DPI

Qt 6標準のDPIスケーリングへ委ね、旧式のHigh-DPI属性を明示設定しない。

---

## 8. 多重起動防止

Mutex名:

`Local\\CurriculumCheckerAppSingleInstanceMutex`

`CreateMutexW`直後に`GetLastError()`を評価する。

`ERROR_ALREADY_EXISTS`の場合は取得したMutexハンドルを直ちに`CloseHandle`し、新規プロセスを正常終了する。

`CreateMutexW`がNULLを返した場合は、安全のため起動中止とし、error.log記録を試み、critical dialog表示後に終了する。

Mutexセキュリティ属性はNULL（Windows標準）とする。

既存起動を検知した場合は、既存ウィンドウの前面化を試みる。

- 最小化中なら `ShowWindow(hwnd, SW_RESTORE)`
- `SetForegroundWindow` を実行
- 拒否時は `FlashWindowEx`
- Win32 APIが失敗しても新規プロセスは起動せず終了
- 仮想デスクトップ切替はOS制約に従い保証対象外
- 既存プロセスがハングしていても新規起動は許可しない

Mutexを多重起動防止の絶対的根拠とし、ウィンドウ探索はUI補助として扱う。

---

## 9. config.ini

### 9.1 基本

- UTF-8 BOMなし/BOM付きの両方を正式対応
- UTF-16 / Shift-JIS等は非対応
- NULL文字を含む場合は不正
- Unicodeデコード失敗は破損扱い
- 破損時はバックアップ退避後にデフォルト設定で再生成
- 不明キー・不明セクションは保持
- コメント・インデントを可能な限り保持
- 不足キーはメモリ上でデフォルト補完
- 設定値の安全な追記は行ベースの軽量マージ
- 更新はtmp→flush→fsync→os.replace

公開Repositoryへ保存する設定値は、本番の `base_url` のみとする。認証情報は保持しない。

### 9.2 base_url

許可スキーム:

- `http://`
- `https://`
- `file:///`

`base_url` 空文字、不正URL、不正スキームは起動エラーとする。

存在しない `file:///` はWebEngineのload failureとして通常処理する。

### 9.3 SSL

`ignore_ssl_errors` を設定可能とする。

- `true`: 証明書エラーを無条件に無視して継続
- `false`: WebEngine標準の証明書エラー動作
- 不正値: 安全のため `false` へフォールバック

許可するBoolean表記:

- true / false
- 1 / 0
- yes / no

大文字小文字は無視する。

数値設定が不正または範囲外の場合は、WARNINGを記録して安全なデフォルト値へフォールバックする。

文字数閾値は最大1000、コピペ件数閾値は最大100等、安全な上限を設ける。

---

## 10. WebEngine

### 10.1 Profile

- `QWebEngineProfile` は1個
- `QWebEnginePage` は1個
- `QWebEngineView` は1個
- タブなし
- `ForcePersistentCookies`
- `setPersistentStoragePath(user_data)`
- `setCachePath(user_data)`

user_dataにはCookie、LocalStorage、セッション情報、HTTPキャッシュ等を保存する。

ユーザー自身がログアウトした場合は、次回起動でもログアウト状態を維持する。

ブラウザデータ初期化UIは設けず、必要時はユーザー自身が`user_data`を削除する。

同一Windowsアカウントでの複数人共有運用はサポートしない。

### 10.2 WebEngine権限

以下は自動拒否する。

- 通知
- Clipboard API
- カメラ
- マイク
- Geolocation
- Fullscreen

通常のテキスト選択＋Ctrl+Cは許可する。

`navigator.clipboard.writeText()`等は拒否し、Web側のPromise rejectとして扱う。

### 10.3 JavaScript dialog

`alert()`、`confirm()`、`prompt()`等の最小限のダイアログを許可する。

- alert: 最大500文字、超過時は末尾を`...`で省略
- confirm: OK=true / Cancel=false
- prompt: Qt標準の入力ダイアログを使用し、Cancelはnull相当

### 10.4 window.open / target

新規Window・新規Tabは作らない。

`createWindow()`等を捕捉し、許可されたURLを既存QWebEngineViewへ統合する。

`about:blank` の新規window要求は拒否する。

`target="_blank"`、`_new`、その他未知のtargetは同一QWebEngineViewへ統合する。

外部protocol（mailto、tel、カスタムURI等）はOS外部アプリを起動せず、静かに拒否する。

`javascript:`、`data:`、`blob:`等の直接navigationは拒否する。

`http` / `https` / `file` は許可する。

別ホストへの遷移も許可する。

---

## 11. ナビゲーション

URLバーは設けない。

画面上のリンク遷移は制限せず、ユーザーが手動で操作する。

自動ページ遷移は行わない。

### 11.1 ロード世代

すべてのnavigation開始時に`load_generation_id`をインクリメントする。

同一イベントループ内で複数navigationが発生した場合は、最後のgenerationだけを有効とする。

10秒timeoutは`loadStarted`受信時から計測する。

リダイレクトが同一generation内であればtimeout時計をリセットしない。

timeout後の古い`loadFinished`は無効世代として破棄する。

Escでロードを停止した場合、現在generationを無効化する。

### 11.2 F5

F5は再読み込みとして許可する。

F5は画面遷移待機5秒の対象外とし、loadFinished時点でREADYへ戻す。

### 11.3 戻る・進む

Alt+Left / Alt+Rightおよびツールバーの戻る・進むは同じQWebEngineHistory操作へ統一する。

戻る・進むによるnavigationではロード完了後に画面変化監視を行う。

### 11.4 ホーム

ホームは`base_url`へ遷移する。

現在URLとbase_urlが`NormalizePathSegments`後の文字列として同一ならreloadせず何もしない。

---

## 12. 画面遷移待機・変化検知

### 12.1 基本

F9によるDOM取得完了後、5秒の画面遷移待機へ入る。

ポーリングはQTimerで100ms間隔とする。

ポーリングは画面遷移待機中のみ動作し、通常待機中・読み込み中・集計中は停止する。

前回pollingのJS callbackが未完了なら次回実行をスキップする`is_polling_busy`ガードを持つ。

### 12.2 URL比較

比較対象:

`QUrl.toString(QUrl.UrlFormattingOption.NormalizePathSegments)`

これ以外の独自URL正規化を行わない。

### 12.3 DOMハッシュ

F9実行時のDOM抽出結果から基準ハッシュを作成する。

各行について次を順序どおりに連結する。

`学籍番号|受講区分|科目|指示書MD5\n`

その全文をSHA-256でハッシュ化する。

指示書MD5は、Python側でcleaned_instructionに対してMD5を求めた32文字の値を使用する。

画面全体hashはSHA-256、行指示書fingerprintはMD5であり、用途は独立する。

行順変更は画面変化とみなす。

URL変化またはDOM hash変化のどちらか一方でも検知した瞬間にアンロックする。

テーブル外の装飾やバナーだけの変更は、URL/テーブルhashが変化しない限り画面変化としない。

### 12.4 待機終了

- URL変化またはDOM hash変化: 即時READY
- 5秒間変化なし: READY
- 5秒timeout時のトースト: 「遷移を検知できませんでしたがロックを解除しました」
- hash取得失敗: 100ms後に再試行
- 5秒間hash取得不能: READYへ復帰

### 12.5 F9 request_id

F9ごとに一意の`request_id`を発行する。

callback受信時に`current_request_id`と一致しない結果は破棄する。

終了処理中のcallbackは`is_shutting_down`で即returnする。

callbackはtry/exceptで囲み、例外はログへ記録する。

---

## 13. DOMテーブル抽出

### 13.1 実HTMLサンプルに基づく具体化

本仕様は、実際のHTMLサンプル `sampleMSL(1).html` を基準に、DOM抽出の責務と実装上の判断を具体化する。

ただし、サンプルHTMLのDOM構造そのものを固定するのではない。サンプルは代表fixtureとして使用し、実際の画面では本章の論理項目・照合規則に従って対象tableを決定する。

#### 13.1.1 サンプルの構造

サンプルには複数の `table` が存在し、先頭側には検索・絞り込み用UI、別のtableには授業データの一覧が配置されている。

授業データ一覧側では、概ね以下の列が存在する。

| 目的 | 実DOM上の代表ラベル | 取得方針 |
| --- | --- | --- |
| 在籍等の補助情報 | `在籍` | `meta_cells`等の補助情報。必須4項目には使用しない |
| 学校情報 | `学校/コース` | 補助情報。必須4項目には使用しない |
| 学年 | `学年` | 補助情報。必須4項目には使用しない |
| 受講区分 | `受講区分` | `division`へ使用 |
| 科目 | `科目` | `subject`へ使用 |
| 生徒 | `生徒` | `student_id`を抽出。氏名はキーに使用しない |
| 受講 | `受講` | 補助情報。必須4項目には使用しない |
| シミュレーション関連 | `シミュレーションシート`等 | 補助情報。必須4項目には使用しない |
| 備考 | `備考` | `raw_instruction`の正式な取得元 |
| 操作用列 | `テンプレート適用`、`一括入力`等 | 補助情報。必須4項目には使用しない |

サンプルの授業データtableでは、実データ行に `00000001`～`00000011` の学籍番号が存在する。これはfixture上の検証値であり、実装へ固定値として埋め込んではならない。

#### 13.1.2 対象table選択の考え方

対象tableはDOM上の先頭tableを採用してはならない。

以下の順で判定する。

1. 可視tableのみ候補にする。
2. headerから4必須論理項目を1対1で割り当てられるtableを候補にする。
3. 総合一致スコア最大のtableを採用する。
4. 同点時はDOM上で先に出現したtableを採用する。

サンプルでは検索・絞り込みUI用tableと授業データtableが併存するため、このtable選択ロジックを必須とする。

#### 13.1.3 data-label優先

実データセルに `data-label` が存在する場合、論理項目との対応付けには `data-label` を第一候補として利用する。

`data-label` が存在しないheaderについては、既存のheader行照合規則へフォールバックする。

`data-label`は業務値ではなくDOM上の列識別補助情報として扱い、最終的に4項目を抽出する際は必ず物理列位置との対応を確定する。

#### 13.1.4 生徒セルからの学籍番号抽出

サンプルの `生徒` 列は、学籍番号と氏名が同一セル内に複数行で配置される構造を持つ。

抽出では `生徒` セルの表示テキストを取得し、最初の有効な識別文字列から学籍番号を確定する。氏名は抽出結果へ保存せず、キーにも使用しない。

学籍番号の正規化規則は以下とする。

- NFKC
- ASCII英数字以外を除去
- 空文字なら当該行をスキップ
- スキップ時はWARNINGログへ記録

同一セル内に氏名が続く場合でも、氏名の文字を学籍番号へ混入させない。

#### 13.1.5 備考セルを指示書の正式ソースとする

サンプルでは `備考` セルに指示書本文が格納されているため、`備考` を `raw_instruction` の正式な取得元とする。

`シミュレーションシート`、`テンプレート適用`、`一括入力`等の操作列は、指示書本文の代替ソースとして使用しない。

`raw_instruction` はDOM取得直後の `innerText` を基礎とし、Python側で定義したNUL除去だけを行う。

#### 13.1.6 サンプルに含まれる多様な指示書をテスト対象とする

サンプルには、以下のような状態が混在しているため、実装テストへ明示的に含める。

- 必須sectionを含む通常の指示書
- `備考` が空の行
- 見出しを持たない自由記述のみの行
- `担当:`、`作成者:`等の表記差
- `小テスト・単語テスト:` のような複合alias
- `教材：`、`進め方：`等の全角コロン
- `講座 : 2` 等、正準section外の情報
- 長文の指示書
- typo・不完全な記述を含む指示書

これらを用いて、section parserが未知項目を勝手に新sectionへ追加せず、`unclassified_text`へ保持することを検証する。

#### 13.1.7 サンプルHTMLの位置付け

`sampleMSL(1).html` は、DOM抽出、table選択、生徒番号抽出、備考取得、section parser、CSV長文セル、異常系を横断して検証する主要fixtureとする。

ただし、実際のサイトがサンプルと異なるDOM構造へ変更された場合でも、以下の論理契約を満たす限り実装を継続できる。

- 4必須論理項目を1対1で識別できる
- 生徒列から学籍番号を抽出できる
- 備考列から指示書を取得できる
- 可視tableとして取得できる

論理契約を満たさない場合は、F9抽出失敗として扱い、推測補完を行わない。

### 13.2 抽出責務

JavaScriptはRaw DOM抽出のみ担当し、業務上の正規化・判定はPython側で行う。

返却形式:

```text
{
  success: bool,
  error: str|null,
  headers: list[str],
  rows: list[list[str]],
  hasNext: bool
}
```

JS例外時は`success=false`とする。

`success=false`なら、headers/rowsが一部返っていても全件破棄する。

### 13.3 対象table

画面内のすべての`table`を候補とし、可視tableのみ対象とする。

以下は除外する。

- `offsetParent === null`
- `display === 'none'`
- `visibility === 'hidden'`
- `width === 0`
- `height === 0`

opacity:0は可視扱いとする。

### 13.4 header

`thead`がある場合は、その中の全`tr`から最も一致スコアが高い単一行をheaderとする。

`thead`がない場合は最初の`tr`をheader候補とする。

`thead`が空ならtbody最初の`tr`へフォールバックする。

headerとして必要な物理列は4つ以上必要とする。

### 13.5 4項目マッピング

必須論理項目:

- 学籍番号
- 受講区分
- 科目
- 指示書

4項目は必ず4つの異なる物理列へ1対1で割り当てる。

同一物理列を複数論理項目へ割り当てる組み合わせは採用しない。

マッチスコア:

- 完全一致: 2点
- 部分一致: 1点
- 物理列あたり最大2点
- 二重加点なし

4項目を重複なく割り当て可能な組み合わせのうち、総合スコア最大を採用する。

完全一致を優先する。

同点時は左から右の物理列インデックスの若い順で決定する。

tableの最終選定で同点になった場合はDOM順の先頭を採用する。

### 13.6 header正規化

header照合前に以下を行う。

- NFKC
- 大文字化
- 改行を半角スペースへ
- 前後trim
- 空白の除去

エイリアスも同様にNFKC・大文字化・空白除去して内部登録する。

### 13.7 指示書セル

DOM抽出では生の`innerText`を取得する。

JavaScript側では`trim()`を行わない。

通常の表示テキストを取得し、HTML属性値・href・title・aria-label・画像alt等を個別取得しない。

`script`、`style`、コメントは対象外とする。

`input` / `textarea`等の値取得については、実データ上存在しない前提とし、特別なフォーム値マッピングは設けない。

### 13.8 rowspan / colspan

DOM上の`cell.rowSpan` / `cell.colSpan`を利用する。

`rowSpan >= 2`または`colSpan >= 2`のセルを含む行はスキップする。

そのような行が存在してもtable自体は採択できる。

### 13.9 summary row

student_idセルをNFKC・大文字化・trim・内部空白除去した値が以下に一致する場合、summary rowとして除外する。

- 合計
- 総計
- 計
- 小計
- 平均
- 件数

summary rowは他列に値があっても行全体を除外する。

### 13.10 次ページ判定

対象要素:

- `a`
- `button`
- `input[type=button]`
- `input[type=submit]`
- `role=button`

span等に「次へ」がある場合は直近の操作可能親を判定する。

認識文字列には少なくとも「次へ」「次」「Next」「NEXT」「次ページ」「＞」「>」「▶」等を含める。

有効な候補が1つでもあれば`hasNext=true`とする。

disabled属性、`aria-disabled="true"`、disabledクラス、pointer-events:none等は無効とする。

`onclick`属性の有無は判定基準としない。

`href="#"`でもdisabledでなければ有効候補とする。

hasNextは「次ページ要素が画面上で検知された」というUI補助情報であり、遷移先を保証しない。

自動で次ページへ移動しない。

---

## 14. CurriculumRecord

内部キー:

`(student_id, division, subject)`

一意性はこの3要素で担保する前提とする。

Recordはmutable、`slots=True`のdataclassとする。

主要フィールド:

- `student_id: str`
- `division: str`
- `subject: str`
- `raw_instruction: str`
- `meta_cells: ...`
- `cleaned_instruction`は必要に応じて再生成する内部値

### 14.1 キー正規化

#### student_id

- NFKC
- ASCII英数字以外を除去
- ハイフン除去
- 全空白除去
- 空文字になった行はスキップしWARNINGログへ記録

#### division

- NFKC
- 大文字化
- 前後空白除去
- 空文字を許可

#### subject

- NFKC
- 大文字化
- 前後および内部空白除去
- 末尾の中黒・、dashes、hyphen、空白等の指定記号を除去
- 空文字は行スキップ

同一正規化値になった元データは、正規化後の値を内部・CSVへ使用する。

### 14.2 raw_instruction

`innerText`取得直後の生テキストを保存する。

保存前にNULのみ除去する。

trim、空白統一、改行圧縮はraw_instructionには行わない。

Repository/cacheではCRLF/LF/CR混在を保持してよい。

---

## 15. Python側テキスト前処理

cleaned_instructionの生成では以下を行う。

1. NUL等の不可視/制御文字処理
2. HTML entityを1回だけ`html.unescape`
3. NFKC
4. 改行を単一`\n`へ正規化
5. タブ・Unicode空白を半角スペースへ
6. 1行中の連続空白を1個へ
7. 各行trim
8. 3つ以上の連続改行を2つへ圧縮
9. 全体trim

Unicodeカテゴリ`Cc` / `Cf`の制御文字のうち、改行・タブ等の意味を持つものは上記処理へ回し、それ以外を除去する。

Zero Width SpaceやBOM等の不可視文字、双方向制御文字も除去する。

---

## 16. 指示書section parser

### 16.1 正準section

必須:

- 作成者
- 志望校
- 教材
- 進め方
- 生徒情報

任意:

- 小テスト
- 宿題

### 16.2 alias

作成者:

- 作成者
- 担当者
- 記入者
- 講師名

志望校:

- 志望校
- 受験校
- 第一志望
- 第1志望

教材:

- 教材
- テキスト
- 使用教材

小テスト:

- 小テスト
- 単語テスト
- 確認テスト
- テスト

宿題:

- 宿題
- 課題
- 家庭学習

進め方:

- 進め方
- 指導方針
- 授業方針
- 計画
- カリキュラム

生徒情報:

- 生徒情報
- 生徒備考
- 特記事項
- 生徒状況

単独の「生徒」「作成」は誤爆防止のためaliasとして使用しない。

### 16.3 見出し判定

見出し照合は最長一致優先とする。

同長の場合はalias登録順とする。

行頭のMarkdown #、箇条書き・装飾記号、括弧、コロン等を許容範囲内で除去してから照合する。

見出し語と完全一致、または見出し語直後に区切り記号がある場合のみ見出しと判定する。

「生徒情報補足」のような複合語を「生徒情報」と誤認しない。

区切りとして以下を認識する。

- `:`
- `：`
- tab
- 空白＋ハイフン＋空白
- コロン直後の空白

`教材：英語 - 単語帳` は最初のコロンで分離し、残り全体を本文とする。

同一行内に別section名が現れても、インライン分割は行わず現在section本文として扱う。

### 16.4 本文帰属

見出しでない行は現在アクティブsection本文へ追加する。

最初の見出しより前のテキストはunclassifiedとする。

見出しが一つもない指示書全体もunclassifiedとする。

unknown headingとその本文はunclassifiedとして保持する。

本文中の「教材:」等の文字列は、既にsection本文として取り込まれている場合は本文として扱う。

### 16.5 重複section

同一sectionが複数回現れた場合は、出現順に本文をCRLFで結合する。

### 16.6 任意section

小テスト・宿題が存在しない、または空欄でもERROR/WARNINGを発行しない。

記載がある場合のみ個別バリデーションを行う。

---

## 17. ブラックリスト

現在の代表的ブラックリスト:

- 未定
- なし
- 特になし
- 特にありません
- 特に問題ありません
- 問題なし
- 問題ありません
- 問題ありません。
- 前回と同じ
- 前回と同じです
- 不要
- N/A
- NULL
- おまかせ
- 良好
- `-`
- `ー`
- `―`
- `−`
- `－`
- `_`

比較前にNFKC、空白除去、指定句読点除去等を行う。

完全正規化一致のみ無効値とする。曖昧な部分一致は行わない。

ブラックリスト判定を先に行い、該当する場合は空内容として扱う。

---

## 18. section評価

### 18.1 作成者

正規化順序:

1. NFKC
2. 前後空白・連続空白処理
3. 末尾敬称の除去
4. 末尾括弧書き除去
5. 再度末尾敬称除去
6. 大文字化
7. 内部空白除去

対象敬称:

- 先生
- 講師
- さん
- 氏
- 様

対象括弧:

- `()`
- `（）`

末尾の括弧書きは連続して除去する。

末尾にない括弧部分は除去しない。

複数名の作成者やスラッシュ区切りは分割せず、1キーとして扱う。

空の作成者はコピペコーパスへ登録しない。

### 18.2 志望校

学校名アイテムは改行、読点、カンマを主な区切りとして分割する。

中黒はインライン分割記号には使用せず、行頭や改行直後の箇条書き記号として必要に応じて除去する。

有効な学校区分:

- 私立
- 公立
- 国立
- 都立
- 府立
- 県立
- 市立
- 専願
- 併願

「私立・併願」のような複数属性も有効。

区分の記載がないアイテムが1つでもあれば、そのrecordへWARNINGを1件発行する。

### 18.3 教材

教材は改行、カンマ、読点等でアイテム分割する。

ステータスキーワード例:

- 所持
- 未所持
- 手持ち
- 購入

「所持（済）」「未所持です」「購入予定」等もキーワード包含で有効とする。

各アイテムを個別評価し、状態記載がないものが存在すればWARNINGを1件発行する。

### 18.4 小テスト

数字と、範囲または合格基準を確認する。

有効な合格基準例:

- 80点以上
- 80点
- 8割
- 80%

「第3回」のように数字と対象情報があれば有効。

範囲と合格基準が別行でもsection全体で両方検出できれば有効。

片方欠損時はWARNINGを1件発行する。

### 18.5 進め方

ブラックリスト判定後、文字数を判定する。

`min_plan_length = 5`

文字数は、NFKC・空白・改行・記号等を除去した有効文字数をPython `len()`で数える。

複数行は連結して数える。

### 18.6 生徒情報

ブラックリスト判定後、文字数を判定する。

`min_info_length = 3`

記号、空白、改行、制御文字等を除去した有効文字数をPython `len()`で数える。

複数行は連結して判定する。

---

## 19. 未分類text

unclassified textには以下を含める。

- 最初のknown headingより前の本文
- unknown heading
- unknown headingの本文
- どの見出しにも属さない独立行

空行のみ、装飾線のみの行は除外する。

有効文字が1文字でもある行は未分類行として数える。

行順は出現順を保持する。

`unclassified_count` と `unclassified_text` は内部整合性を維持する。

CSVではCRLF結合した`unclassified_text`を1セルに出力する。

WARNINGは1recordにつき1件のみ:

`WARN_UNCLASSIFIED_TEXT`

メッセージ例:

`未分類行あり(3行)`

---

## 20. コピペ判定

### 20.1 基本

`duplicate_info_threshold = 3`

同一作成者内だけで比較する。

担当者名の正規化済み文字列を完全一致グループキーとする。

空作成者や無効生徒情報はコーパスへ登録しない。

### 20.2 比較text

空白・改行を除去した生徒情報を比較する。

短文処理:

- 15文字未満: 完全一致のみ
- 15文字以上: 2-gram Jaccard係数
- 類似度閾値: 0.8

2-gramは文字単位のbi-gram集合とし、重複は除去する。

完全一致はJaccard計算を待たず類似とする。

同一生徒・別科目も比較対象に含む。

### 20.3 WARNING

同一作成者内で同一または類似情報が3record以上のグループとなった場合、該当グループのrecordすべてへ:

`WARN_COPY_PASTE_SUSPECTED`

を付与する。

集計は全蓄積データへ対して一括実行し、ページ順等の時系列概念へ依存しない。

---

## 21. 判定エンジン

純粋関数として以下へ分離する。

```text
evaluate_single_record(record: CurriculumRecord, config: AppConfig) -> EvaluationResult

evaluate_batch_duplicates(
    records: list[CurriculumRecord],
    results: list[EvaluationResult],
    config: AppConfig
) -> list[EvaluationResult]
```

EvaluationResult:

- `severity: Severity`
- `errors: list[str]`
- `warnings: list[str]`
- `parsed_sections: dict[str, str]`
- `unclassified_count: int`
- `unclassified_text: str`

`errors` / `warnings`にはrule IDを保持し、自然言語メッセージは辞書から解決する。

batch duplicate処理は入力resultsを破壊的に変更せず、新しいlistまたは新規copyを返す。

Severity:

- errorsあり → ERROR
- errorsなし、warningsあり → WARNING
- 両方なし → PASS

---

## 22. Rule ID

現在の固定rule ID:

### ERROR

- `ERR_SECTION_MISSING`
- `ERR_SECTION_EMPTY`
- `ERR_PLAN_TOO_SHORT`
- `ERR_INFO_TOO_SHORT`
- `ERR_PARSER_EXCEPTION`
- `ERR_INTERNAL_EVALUATION`

### WARNING

- `WARN_TEXTBOOK_NO_STATUS`
- `WARN_SCHOOL_NO_TYPE`
- `WARN_TEST_CRITERIA_MISSING`
- `WARN_COPY_PASTE_SUSPECTED`
- `WARN_UNCLASSIFIED_TEXT`

rule IDは永久的に文言から分離する。

`RULE_MESSAGES: dict[str, str]` を`core/constants.py`で一元管理する。

同一record内ではrule ID重複を削除する。

errorsとwarnings両方に同一rule IDを入れない。

複数ERRORがあってもすべて保持する。

rule定義順をもって表示・CSV出力順を決定する。

---

## 23. Repository

Repository操作はGUIメインスレッドだけから行う。

集計開始時に全recordsを`copy.deepcopy()`したsnapshotへ変換する。

Workerはsnapshotのみを参照し、GUI側Repositoryへ直接アクセスしない。

records順は初回追加順を維持する。

同一キー更新時も位置は変えない。

新規キーはDOM行順で末尾へ追加する。

### 23.1 重複

同一キーは更新扱いとし、件数を増やさない。

instructionは新データで完全置換する。

Undo用に更新前Record全体を保存する。

同一batch内の同一キーも後勝ちとする。

---

## 24. Undo

Undoは読み込みbatch単位とする。

最大30batch。

Undo recordには以下を保持する。

- 新規追加キーリスト
- 更新前Record snapshot

Undo時:

1. 更新前Recordを差し戻す
2. 新規追加キーを削除
3. それ以外は維持
4. cacheをアトミック保存

Undo中に例外、またはcache保存失敗があった場合はUndo前の状態へ完全ロールバックする。

Undo履歴はcacheへ保存しない。

起動時cache復元後のUndo履歴は空。

Undo成功後はcache保存を必須とする。

Repository件数が0になった場合はcacheファイルを物理削除し、削除成功後に0件状態を確定する。

---

## 25. cache

ファイル名:

`_session_cache.jsonl`

tmp:

`_session_cache.jsonl.tmp`

### 25.1 meta

1行目固定構造:

```text
{"__meta__": true, "schema_version": 1, "created_at": "ISO8601日時", "record_count": レコード総数, "app_version": "1.0.0"}
```

未知のmetaキーは無視する。

schema_versionは厳密なintのみ許可する。

`schema_version < 1` は破損扱い。

現在versionより大きいschemaは拒否する。

### 25.2 record

レコードJSONキーを次に固定する。

- `student_id`
- `division`
- `subject`
- `raw_instruction`
- `meta_cells`

`ensure_ascii=False` を使用する。

JSONL各行末尾はLF固定とする。

cleaned_instructionやparsed resultは保存せず、復元時に再生成する。

### 25.3 atomic save

1. `_session_cache.jsonl.tmp` を開く
2. 全snapshotを書き込む
3. `flush()`
4. `os.fsync()`
5. `os.replace()`

親ディレクトリfsyncは要求しない。

### 25.4 復元

meta行JSON decode失敗・schema不正はcache全破損とし、2行目以降を復元しない。

2行目以降のJSON破損はその行のみスキップし、残りを復元する。

重複キーは後勝ち。

Repository順は初回出現位置順を維持する。

record_count不一致時はWARNINGログを記録し、実データを優先して復元する。

### 25.5 復元確認

正常:

`前回の未集計データ（{count}件）が見つかりました。\n復元して作業を継続しますか？`

部分破損:

`前回の未集計データ（{count}件）が見つかりました。\n（※破損データ {skip_count}件 を除外）\n復元して作業を継続しますか？`

「いいえ」の場合もcacheを削除せず残す。

meta破損時:

`キャッシュファイルのヘッダー情報が破損しているため、復元できません。`

critical dialogを表示し、新規状態で起動する。

### 25.6 schema migration

将来versionで新フィールドが追加された場合、旧レコードへデフォルト値を補完する。

既存フィールド値を勝手に改変しない。

migration前に`.bak`を保持し、migration失敗時は`.bak`から復元する。

`.bak`は通常起動時には復元対象にせず、自動削除しない。

---

## 26. cache_is_dirty

状態遷移:

- 起動時: False
- 読み込みbatchがMemoryへ反映された瞬間: True
- cache atomic save成功: False
- CSV成功後cache削除失敗: True

cache保存が失敗した場合はRepositoryを保持する。

次回以降のF9読み込みだけを禁止する。

集計、Undo、Reset、終了は引き続き許可する。

---

## 27. F9読み込み

F9はREADY時のみ有効。

集計中、ロード中等は無効。

1回のF9で取得した全行を1batchとする。

### 27.1 成功

- DOM抽出成功
- table/header成立
- 有効行を処理
- Repositoryへbulk反映
- cacheをatomic save

### 27.2 0件

テーブル・header抽出成功後に有効行0件、または全行が既存値と完全一致で更新なしの場合:

`変更なし（0件）`

をトースト表示し、Repository/cache/Undoを変更しない。

対象table自体が見つからない場合は:

`対象テーブルが見つかりません`

とし、「0件」と区別する。

### 27.3 行エラー

student_id空、subject空等のキー不成立行はスキップしログへ記録する。

batch処理全体は継続する。

---

## 28. CSV

### 28.1 形式

- UTF-8 with BOM
- RFC 4180準拠
- Python標準`csv`を使用
- 手動エスケープ禁止
- 行終端CRLF
- セル内改行もCRLF
- `csv.writer(..., lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)` を標準とする

### 28.2 固定15列

1. `学籍番号` → `CurriculumRecord.student_id`
2. `受講区分` → `CurriculumRecord.division`
3. `科目` → `CurriculumRecord.subject`
4. `判定ランク` → `EvaluationResult.severity.value`
5. `要修正エラー` → `EvaluationResult.errors` の自然文連結
6. `確認推奨警告` → `EvaluationResult.warnings` の自然文連結
7. `作成者` → parsed_sections["作成者"]
8. `志望校` → parsed_sections["志望校"]
9. `教材` → parsed_sections["教材"]
10. `進め方` → parsed_sections["進め方"]
11. `生徒情報` → parsed_sections["生徒情報"]
12. `小テスト` → parsed_sections["小テスト"]
13. `宿題` → parsed_sections["宿題"]
14. `未分類テキスト` → `unclassified_text`
15. `原文指示書` → `raw_instruction`

存在しない値・Noneは空文字へ統一する。

### 28.3 メッセージ

CSVにはrule IDではなく自然言語メッセージを出力する。

カンマを含まないmessage規約とし、複数messageは`,`で連結する。

ルール定義順で出力する。

### 28.4 Formula Injection

CSV出力直前に全列へ適用する。

前後の空白、タブ、Unicode空白をtrimした後の先頭文字が次のいずれかなら先頭に`'`を付与する。

- `=`
- `+`
- `-`
- `@`

Repositoryの値自体は変更しない。

`="00123"`等の数式偽装は使用しない。

### 28.5 ファイル名

基本:

`カリキュラムチェック_YYYYMMDD-HHMMSS.csv`

同名存在時:

`_1` ～ `_999`

最初に存在しない名前を採用する。

`_999`まで衝突する場合はERRORで中断する。

CSV filenameにはアプリversionを含めない。

### 28.6 atomic output

1. tmp CSV作成
2. 書き込み
3. `flush()`
4. `os.fsync()`
5. `os.replace()`
6. 正式ファイル検証

一時ファイル:

`_tmp_output_{pid}_{timestamp}_{uuid4().hex[:8]}.csv`

### 28.7 成功検証

以下をすべて満たす必要がある。

1. ファイルサイズ > 0
2. os.replace成功
3. `utf-8-sig`で読み、CSVとして15列ヘッダー配列が完全一致
4. `csv.reader`で論理record件数を数え、蓄積件数+1と一致
5. 書き込み成功レコード件数カウンタと蓄積件数が一致

全文のデータ評価や再解析は行わず、件数確認だけを行う。

CSV出力失敗時はformal CSVを作成せずcacheを保持する。

---

## 29. 集計Worker

WorkerはQThreadベースとする。

入力:

`list[CurriculumRecord]`

Repositoryの順序を完全維持するdeepcopy snapshotを渡す。

Worker内部でsortしない。

### 29.1 signals

```text
progress_changed = pyqtSignal(int)
finished = pyqtSignal(list)
error_occurred = pyqtSignal(str)
```

進捗は10件ごと、または全体の1%ごとに間引く。最終100%は必ず正常完了時に発行する。

`total=0`なら即時完了し100%を発行する。

### 29.2 exception

個別record例外は、そのrecordのみ`ERR_PARSER_EXCEPTION`として記録して全体を完走する。

Worker全体の予期せぬ例外は:

`集計ワーカーの実行中に予期せぬエラーが発生しました。詳細はログを確認してください。`

CSVは作成せずcacheを保持してREADYへ復帰する。

`ERR_INTERNAL_EVALUATION`は致命的内部エラーとしてerror signalで通知する。

---

## 30. 集計・CSV後処理

集計対象は全Repository records。

Worker完了後、メインスレッドでsnapshot件数とresults件数を厳密比較する。

不一致の場合:

- `ERR_INTERNAL_EVALUATION`
- CSV出力中止
- cache保持
- critical dialog

正常にCSV出力・検証できた場合:

1. cache削除
2. cache削除成功を確認
3. Repository memoryをclear
4. 件数を0へ戻す

cache削除失敗時はRepositoryをclearしない。

---

## 31. Reset

確認文言:

`蓄積データを削除しますか？（※ログイン状態や出力済みCSVは削除されません）`

Resetでは以下を削除対象とする。

- Repository
- Undo stack
- cache
- コピペコーパス等の蓄積データ

削除しない。

- user_data
- ログイン状態
- 出力済みCSV

cacheが存在しない場合も成功扱いとする。

cache削除に失敗した場合はメモリを変更しない。

Reset完了後にRepository件数0、コピペコーパス空、Undo stack空をassertする。

---

## 32. 終了処理

通常終了時:

- timer停止
- WebEngine停止
- callback無効化
- 最大2秒のcleanup待機
- 完了しない場合はプロセス終了を優先

`cache_is_dirty=True`なら:

`未保存のデータがあるため終了すると消失します`

等の終了確認を表示する。

「終了」でcacheを保持したまま終了、「キャンセル」で復帰する。

集計中の終了要求では、未完成CSVを作成せず、cacheを残したまま終了を優先する。

MemoryErrorの場合はGUIダイアログを表示せず、stderrおよび可能な限りerror.logへ記録し`sys.exit(1)`で終了する。cacheを操作しない。

---

## 33. Renderer crash

`renderProcessTerminated`を検知した場合:

- error.logへERROR
- Repository/cacheは保持
- `ブラウザエンジンがクラッシュしました。アプリを再起動してください`
- critical dialog
- 安全終了

---

## 34. キーボード・ショートカット

### 通常

- F9: ページ読み込み
- Ctrl+Z: アプリUndo
- Ctrl+Enter: 集計・出力
- F5: 再読み込み
- Esc: ページロード停止
- Alt+Left: 戻る
- Alt+Right: 進む
- Ctrl+Plus: zoom in
- Ctrl+Minus: zoom out
- Ctrl+0: config zoomへ一時リセット
- Ctrl+C: コピー
- Ctrl+A: 全選択

### 禁止

- Ctrl+S: 保存
- Ctrl+P: 印刷
- Ctrl+F: 検索
- タブ系shortcut

集計中はF9、Ctrl+Z、Ctrl+Enterだけでなく、F5、Esc、Alt+Left、Alt+Rightを含むアプリ/ブラウザ操作shortcutを全面禁止する。

---

## 35. ズーム

- 範囲: 0.5 ～ 2.0
- 刻み: 0.1
- メインキーボード`+/-`対応
- テンキーPlus/Minus対応
- Ctrl+0はQt側でイベントを消費
- 起動時はconfigのzoom
- Ctrl+0の変更は再起動時にconfig値へ戻る

---

## 36. Browser context menu

右クリックメニューは以下だけ。

- コピー
- 戻る
- 進む
- 再読み込み

コピーは選択文字がない場合disabled。

戻る・進むはhistory状態に応じてdisabled。

再読み込みはロード中も使用可能。

全選択、新しいタブで開く、保存、印刷等は表示しない。

---

## 37. PDF / Download / Print

PDFのinline表示は許可する。

保存・ダウンロードはすべてキャンセルする。

Ctrl+S、PDF viewerの保存UI、download属性、Download要求を遮断する。

PDF viewerの印刷要求も遮断する。

ダウンロード拒否時は:

`本ブラウザからのファイルダウンロードは無効化されています`

をtoast表示する。

---

## 38. UI

### 38.1 ウィンドウ

初期サイズ:

`1380x880`

最小サイズ:

`1024x700`

### 38.2 toolbar

左から:

1. `◀ 戻る`
2. `進む ▶`
3. `🔄 再読み込み`
4. `🏠 ホーム`
5. separator
6. `📥 ページ読み込み (F9)`
7. `↩ 取消 (直前 N件)`
8. `📊 集計・出力 (N件)`
9. stretch space
10. `🗑 リセット`

ブラウザ領域はtoolbar/statusbar以外をすべて利用する。

### 38.3 statusbar

- 待機中
- DOM走査中...
- 画面遷移待機中...
- 集計処理中 (XX%)...
- 集計完了

### 38.4 title

`[蓄積: N件] 授業指示書・カリキュラム 精査ブラウザ v1.0.0`

### 38.5 toast

- 最大1件
- 新規発生で即上書き
- 中央下部固定
- mouse transparent
- 最大80文字程度
- 超過時末尾`...`
- OS通知は使用しない

### 38.6 notification channel

Toast:

- tableなし
- 0件
- 読み込み完了
- Undo完了
- reset完了
- download拒否
- 画面変化未検知timeout等

Dialog:

- cache破損
- permission error
- CSV保存失敗
- 終了確認
- reset確認
- 集計summary
- renderer crash

重大エラーが複数あっても画面ダイアログは最初の1件のみとし、付随情報はログへ記録する。

---

## 39. Explorer連携

CSV正式保存成功後、Explorerで正式CSVを選択表示できる。

対象ファイルは`os.path.exists`で存在確認してから実行する。

CSV出力失敗時はExplorerを起動しない。

WindowsではExplorerの`/select`形式を使用する。

---

## 40. ログ

ファイル:

`error.log`

設定:

- UTF-8 BOMなし
- `RotatingFileHandler`
- `maxBytes=1048576`
- `backupCount=3`

最大4ファイル相当の世代管理を許容する。

ログ対象:

- システム例外
- SSL警告
- DOM解析失敗
- 行スキップ
- cache保存失敗
- migration警告
- renderer crash
- 内部rule ID

ログへURLを出す場合はscheme + hostだけ残し、path/query/fragmentを除去する。

トレースバック内もURL query/parameterをmaskする。

ローカル実行ファイルパス、例外クラス名はデバッグ性のため保持する。

ログ書き込み失敗時はstderrへ出力しlogging handlerを無効化して業務処理を継続する。

---

## 41. 個人情報保護

cacheには未集計の以下情報が一時保存されることをREADMEへ明記する。

- 学籍番号
- 受講区分
- 科目
- 指示書本文

CSV出力成功後、cacheを削除する。

CSVが最終成果物、cacheは未集計データ保護用の一時退避領域と位置付ける。

GitHub公開資料・mock・fixture・README・画面画像等へ実在個人情報を含めない。

---

## 42. ファイルシステム・実行環境

正式サポート:

- Windows 10 1809+
- Windows 11
- x64
- NTFS
- ローカルディスク

非対応/保証対象外:

- Windows Server
- ARM64 Windows
- Linux
- macOS
- 特殊な圧縮/暗号化属性付きディレクトリ

ネットワークドライブ、USB、同期クラウド上での実行は非推奨・保証対象外とする。

ネットワークドライブから意図的に実行した場合でも、同一ディレクトリへの出力を試みる。

OneDrive等への生成済みCSVの手動コピー・移動は許可する。

---

## 43. Build

### 43.1 tools/build.py

- `__file__`基準でパスを解決
- cwdへ依存しない
- venv利用を推奨/チェック
- 不足ライブラリを自動installしない
- 不足時はエラー終了
- stdout/stderrをリアルタイム表示
- ビルド用生成物を清掃
- ファイルロック時は中止

### 43.2 Onefile

NuitkaはOnefileで生成する。

正式成果物:

`Curriculum_Analyzer.exe`

Standaloneのフォルダ配布は廃止。

QtWebEngineの関連リソースはOnefileへ組み込む。

ビルド後にEXEの存在を確認する。

### 43.3 requirements

`requirements.txt`:

- PyQt6（固定version）
- PyQt6-WebEngine（固定version）
- openpyxl（固定version）
- Nuitka
- zstandard
- pytest
- flake8
- black

---

## 44. テスト

### 44.1 pytest対象

- core判定エンジン
- normalization
- data model
- Repository
- cache復元
- config validation
- CSV生成

### 44.2 手動対象

Windows実機で:

- GUI表示
- F9
- shortcut
- WebEngine rendering
- Explorer
- renderer crash対応
- Release版起動

### 44.3 fixtures

Repository:

- `tests/fixtures/`
- `tests/expected/`
- `tests/mock_pages/`

主要fixture: `tests/mock_pages/sampleMSL(1).html`（公開Repositoryへ置く場合は実データを含まないダミー版に差し替える）

mock HTMLには最低限以下を含める。

- 通常table
- hidden table
- 複数table
- Ajax更新
- summary row
- rowspan/colspan
- 次へ要素
- 0件
- UTF-8
- Shift-JIS
- LF/CRLF/CR
- 不可視文字
- entity
- script/style/comment

実サンプル `sampleMSL(1).html` に対して以下を個別確認する。

| ケース | 期待結果 |
| --- | --- |
| `生徒` + `受講区分` + `科目` + `備考` の通常行 | 1 recordとして抽出 |
| `生徒`セル内の学籍番号+氏名 | 学籍番号のみを`student_id`へ格納 |
| `備考`が空 | `raw_instruction`は空。後段で必須section不足として評価 |
| 見出しなし自由記述 | 未分類textとして保持し、必須section不足も評価 |
| `data-label`付きセル | `data-label`を優先して論理列へ対応付け |
| 複数table | 必須4項目の一致スコア最大tableを採択 |
| 操作用列が多数存在 | 操作用列を必須4項目へ誤採用しない |
| 長文`備考` | 改行・セル内部改行を保持してCSVへ出力 |

### 44.4 Golden test

内部テストではrule IDを比較する。

CSV生成テストでは自然言語メッセージも比較する。

rule IDの順序は定義順と一致することを検証する。

dictは意味的内容を比較し、キー順そのものを比較しない。

### 44.5 Acceptance

主要シナリオ:

1. 起動
2. login
3. page1読み込み
4. 次ページへ手動移動
5. page2読み込み
6. Undo
7. 集計
8. CSV生成
9. CSV内容・Excel互換性確認

機能・異常系テストは100% PASSを要求する。

性能目標（SLO）は、軽微な超過を即失格とはしない。

---

## 45. トレーサビリティ

`仕様番号 → 対応コード箇所 → pytestテストID → 実機確認結果 → 状態（有効/廃止/変更）`

を追跡可能にする。

仕様更新時は影響するテストをトレーサビリティから手動抽出・更新する。

---

## 46. ドキュメント

Repository:

- `README.md`: GitHub概要および取扱・導入説明 (SSOT)
- `doc/index.html`: 総合操作説明
- `doc/style.css`
- `doc/script.js`
- `DEVELOPER.md`
- `LICENSE`
- `.gitignore`
- `SECURITY.md`
- 必要に応じ `CHANGELOG.md`

`README.md`には少なくとも以下を含める。

- 対応OS
- 導入方法
- 起動方法
- config.ini
- base_url
- ログイン
- F9読み込み
- Undo
- 集計・CSV
- cache
- データ保持
- EXE/Qt等のライセンス
- GitHub Releaseからの更新方法
- キャッシュ・個人情報に関する注意

---

## 47. 更新運用

正式な更新方法:

1. GitHub Releaseから新しいZIPを取得
2. 新しいフォルダへ展開
3. 旧フォルダから`config.ini`をコピー
4. 旧フォルダから`user_data/`をコピー
5. 新しい`Curriculum_Analyzer.exe`を起動

自動アップデートは実装しない。

起動時にGitHub APIへアクセスして最新versionを確認する機能も設けない。

オフライン環境でもcore機能が動作することを保証する。

ダウングレード可否はcache schemaとの互換性に従う。新schemaを旧EXEが読めない場合は正常な制約として扱う。

---

## 48. Release作成手順

正式Releaseは手動で作成する。

基本手順:

1. `main` を最新安定状態にする
2. versionを確定
3. pytest
4. lint
5. build
6. `Curriculum_Analyzer.exe`確認
7. ZIP生成
8. ZIP内容確認
9. Windows実機確認
10. 個人情報・秘密情報レビュー
11. Git tag `vX.Y.Z`
12. Draft Release作成
13. ZIPを1ファイル添付
14. Release Notesを日本語で記述
15. 最終確認
16. 手動Publish

Pre-releaseは使用しない。

---

## 49. Release Notes

相手は日本人を想定し、説明は日本語を基本とする。

Release Notesでは最低限以下を説明する。

- version
- 概要
- 主な変更点
- 修正点
- 注意事項
- 対応OS
- ZIPダウンロード案内

GitHub READMEはLatest Releaseへの導線を持つ。

過去Releaseは削除・上書きせず、旧版取得用として残す。

公開済みtagの付け替えは行わず、重大修正は新しいPATCH versionを発行する。

---

## 50. セキュリティ公開方針

Public Repositoryのため、以下を公開前必須チェックとする。

- 実データがない
- 学籍番号等の個人情報がない
- 認証情報がない
- Cookie/Tokenがない
- 秘密鍵がない
- 本番base_url以外の秘密情報がない
- Git履歴にも上記がない

GitHub公開後の脆弱性報告窓口はRepositoryの`SECURITY.md`で定義する。

Issueを利用する場合も、個人情報を投稿しない注意書きを設ける。

---

## 51. 起動・エラー状態の原則

エラー状態でも可能な限りRepository/cacheを保護する。

データを失う可能性がある場合は、処理中断・cache保持を優先する。

特に以下ではcacheを削除しない。

- Worker全体例外
- CSV出力失敗
- internal evaluation error
- renderer crash
- MemoryError
- Reset時cache削除失敗
- Undo時atomic save失敗

---

## 52. 内部状態機械

状態:

- READY
- PAGE_LOADING
- SCREEN_TRANSITION_WAIT
- AGGREGATING

状態遷移の競合を防止し、非同期callbackにはgeneration/request_idを付ける。

集計中はブラウザ閲覧自体は許可する方針だが、アプリ操作shortcutは全面遮断する。

UIボタンとshortcutの有効/無効は同一状態管理から決定する。

---

## 53. 主要定数

### Application

- `APP_BASE_TITLE = 授業指示書・カリキュラム 精査ブラウザ`
- `__version__ = "1.0.0"`
- `EXE_NAME = "Curriculum_Analyzer.exe"`
- `MUTEX_NAME = "Local\\CurriculumCheckerAppSingleInstanceMutex"`

### Limits

- window initial: 1380x880
- window minimum: 1024x700
- zoom min: 0.5
- zoom max: 2.0
- zoom step: 0.1
- page load timeout: 10s
- screen transition wait: 5s
- polling: 100ms
- cache retry: 最大3回、100ms間隔
- Undo history: 30batch
- min_plan_length: 5
- min_info_length: 3
- duplicate_info_threshold: 3

---

## 54. 実装禁止事項

- 仕様にない業務ルールをAIが勝手に追加しない
- pandasをCSV処理へ使用しない
- 自動ページ遷移しない
- URLバーを実装しない
- タブを実装しない
- 自動ログインを実装しない
- 自動アップデートを実装しない
- 外部protocolをOSへ渡さない
- download保存を許可しない
- Web検索・テレメトリ・監査ログを追加しない
- 本番実データをGitHubへ追加しない
- Releaseへchecksumを追加しない
- Pre-releaseを使用しない
- Standalone folder配布へ戻さない
- EXE名を`app.exe`へ戻さない

---

## 55. 仕様変更履歴の重要点

### 2131

EXE名称を以下へ変更。

`Curriculum_Analyzer.exe`

### 2132

EXEメタデータを確定。

- CompanyName: `sam-hat-86`
- ProductName: `Curriculum Analyzer`
- FileDescription: `カリキュラム分析ソフト`
- OriginalFilename: `Curriculum_Analyzer.exe`

### 2271以降

GitHub Repository/Release設計を追加。

- Repository: Public
- `Curriculum_Analyzer`
- Releaseが唯一の正式配布場所
- Release ZIP 1ファイル
- checksumなし
- 日本語説明
- 実データはローカル秘匿
- Latest Releaseを正式配布対象

### 2283以降

Nuitka配布方式をOnefileへ変更。

### 2289

`doc/script.jp` を `doc/script.js` へ変更。

### 2291以降

成果物全体を独自Licenseとし、`sam-hat-86`に権利を帰属させる。

### サンプルHTML統合

実HTML `sampleMSL(1).html` の構造を分析し、以下を現行仕様へ組み込んだ。

- 複数tableからの論理項目スコアによる対象table選択
- `data-label` 優先の列対応
- `生徒`セルからの学籍番号抽出
- `備考`を指示書の正式ソースとして固定
- 操作用列を業務項目へ誤採用しない境界
- 実サンプルの多様な指示書を用いたfixtureテスト

---

## 56. 最終凍結

実装開始時、完全統合確定仕様書そのもののUTF-8テキストへSHA-256を算出し、実装開始確認書へ記録する。

実装開始確認書には少なくとも以下を記録する。

- 仕様書SHA-256
- アプリversion
- schema_version
- 最終確定仕様番号
- 作成日時

完全統合確定仕様書には現行仕様のみを掲載し、廃止仕様は履歴版へ分離する。

質問番号1800以降も、「未確定仕様が完全に0件」であることを実装開始条件とする原則を維持する。

---

## 57. 実装担当AIへの最終指示

本書を実装の正本として扱うこと。

実装前に本書全体を読み、仕様の重複・矛盾・参照漏れを確認すること。

不明点が本書から機械的に導出できない場合は、コードを書く前に新しい仕様番号で質問すること。

過去回答に存在した旧仕様が本書と異なる場合は、本書の現行仕様を使用すること。

実装・テスト・ビルド・配布物はすべて本書の現行仕様に適合させること。
