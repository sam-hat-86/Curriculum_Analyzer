"""テキスト正規化モジュール。

DOM抽出後のテキストに対して、学籍番号・受講区分・科目・指示書本文の
正規化処理を提供する。
"""

import html
import re
import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# 制御文字・不可視文字除去
# ---------------------------------------------------------------------------

# 改行・タブ以外のCc/Cf文字を除去するための正規表現
# \t, \n, \r は意味を持つため保持し、後段の処理へ回す
_CONTROL_CHARS_RE = re.compile(
    r"[^\S \t\n\r]"  # placeholder – 後述の関数内で個別判定
)

# BOM, ZWNBSP, ZWS, ZWSP, 双方向制御文字等
_INVISIBLE_CODEPOINTS: set[int] = {
    0xFEFF,   # BOM / ZWNBSP
    0x200B,   # Zero Width Space
    0x200C,   # Zero Width Non-Joiner
    0x200D,   # Zero Width Joiner
    0x200E,   # Left-to-Right Mark
    0x200F,   # Right-to-Left Mark
    0x202A,   # Left-to-Right Embedding
    0x202B,   # Right-to-Left Embedding
    0x202C,   # Pop Directional Formatting
    0x202D,   # Left-to-Right Override
    0x202E,   # Right-to-Left Override
    0x2060,   # Word Joiner
    0x2061,   # Function Application
    0x2062,   # Invisible Times
    0x2063,   # Invisible Separator
    0x2064,   # Invisible Plus
    0x2066,   # Left-to-Right Isolate
    0x2067,   # Right-to-Left Isolate
    0x2068,   # First Strong Isolate
    0x2069,   # Pop Directional Isolate
    0x00AD,   # Soft Hyphen
}


def _remove_control_and_invisible(text: str) -> str:
    """Cc/Cf制御文字と不可視文字を除去する。

    改行(\\n, \\r)とタブ(\\t)は保持し、後段の処理に回す。
    """
    result: list[str] = []
    for ch in text:
        cp = ord(ch)
        # 明示的に保持する文字
        if ch in ("\n", "\r", "\t"):
            result.append(ch)
            continue
        # 不可視コードポイント
        if cp in _INVISIBLE_CODEPOINTS:
            continue
        # NUL
        if cp == 0:
            continue
        # Unicodeカテゴリ Cc (制御文字) / Cf (書式文字)
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf"):
            continue
        result.append(ch)
    return "".join(result)


# ---------------------------------------------------------------------------
# cleaned_instruction 生成
# ---------------------------------------------------------------------------

# Unicode空白文字 (タブ以外) → 半角スペースへ変換するパターン
_UNICODE_WHITESPACE_RE = re.compile(
    r"[\t\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]"
)

# 1行中の連続スペースを1個に圧縮
_MULTI_SPACE_RE = re.compile(r" {2,}")

# 3つ以上の連続改行を2つに圧縮
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_instruction(raw: str) -> str:
    """raw_instructionからcleaned_instructionを生成する。

    仕様書 §15 に準拠した前処理を行う:
    1. NUL等の不可視/制御文字処理
    2. HTML entityを1回だけhtml.unescape
    3. NFKC
    4. 改行を単一\\nへ正規化
    5. タブ・Unicode空白を半角スペースへ
    6. 1行中の連続空白を1個へ
    7. 各行trim
    8. 3つ以上の連続改行を2つへ圧縮
    9. 全体trim
    """
    if not raw:
        return ""

    text = raw

    # 1. 制御文字・不可視文字除去
    text = _remove_control_and_invisible(text)

    # 2. HTML entity を1回だけunescape
    text = html.unescape(text)

    # 3. NFKC正規化
    text = unicodedata.normalize("NFKC", text)

    # 4. 改行を単一 \n へ正規化 (CRLF → LF, CR → LF)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 5. タブ・Unicode空白を半角スペースへ
    text = _UNICODE_WHITESPACE_RE.sub(" ", text)

    # 6. 1行中の連続空白を1個へ
    lines = text.split("\n")
    lines = [_MULTI_SPACE_RE.sub(" ", line) for line in lines]

    # 7. 各行trim
    lines = [line.strip() for line in lines]

    text = "\n".join(lines)

    # 8. 3つ以上の連続改行を2つへ圧縮
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)

    # 9. 全体trim
    text = text.strip()

    return text


# ---------------------------------------------------------------------------
# raw_instruction 前処理
# ---------------------------------------------------------------------------

def sanitize_raw_instruction(raw: str) -> str:
    """raw_instruction保存前のNUL除去のみ行う。

    仕様書 §14.2: 保存前にNULのみ除去する。
    trim、空白統一、改行圧縮はraw_instructionには行わない。
    """
    if not raw:
        return ""
    return raw.replace("\x00", "")


# ---------------------------------------------------------------------------
# 学籍番号 正規化
# ---------------------------------------------------------------------------

# ASCII英数字以外を除去するパターン
_NON_ASCII_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


def normalize_student_id(raw: Optional[str]) -> Optional[str]:
    """学籍番号を正規化する。

    仕様書 §14.1:
    - NFKC
    - ASCII英数字以外を除去
    - ハイフン除去 (ASCII英数字以外除去に含まれる)
    - 全空白除去 (ASCII英数字以外除去に含まれる)
    - 空文字になった場合はNoneを返す
    """
    if not raw:
        return None

    text = unicodedata.normalize("NFKC", raw)
    text = _NON_ASCII_ALNUM_RE.sub("", text)

    if not text:
        return None

    return text


def extract_student_id_from_cell(cell_text: str) -> Optional[str]:
    """生徒セルのテキストから学籍番号を抽出する。

    仕様書 §13.1.4:
    生徒セルは学籍番号と氏名が同一セル内に複数行で配置される。
    最初の有効な識別文字列から学籍番号を確定する。
    氏名は抽出結果へ保存せず、キーにも使用しない。
    """
    if not cell_text:
        return None

    # NFKC正規化
    text = unicodedata.normalize("NFKC", cell_text)

    # 行分割して最初の有効な英数字列を探す
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # ASCII英数字のみを抽出
        candidate = _NON_ASCII_ALNUM_RE.sub("", line)
        if candidate:
            return candidate

    return None


# 姓名から除外するボタン・アイコン等のラベル (v10 §2.1)
_NAME_EXCLUDE_WORDS = {"詳細", "編集", "削除", "変更", "確認", "表示", "SELECT", "VIEW", "EDIT"}


def extract_student_name_from_cell(cell_text: str, student_id: Optional[str] = None) -> str:
    """生徒セルから生徒氏名を抽出・正規化する (v10 §2.1, §5.1)。

    - 姓と名を半角ASCIIスペース1個で結合
    - 前後の空白を除去
    - Unicode空白（全角スペース等）を正規化
    - 装飾・アイコン・ボタン文字列等を除外
    - 取得できない場合は空文字列を返す
    """
    if not cell_text:
        return ""

    text = _remove_control_and_invisible(cell_text)
    text = unicodedata.normalize("NFKC", text)

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return ""

    # student_id が指定されている場合、または1行目が学籍番号らしき英数字のみの場合、それを除外
    name_lines = []
    for idx, line in enumerate(lines):
        line_clean = line.strip()
        # student_id と完全一致、または先頭行が英数字記号のみの場合は学籍番号行とみなす
        if student_id and line_clean == student_id.strip():
            continue
        if idx == 0 and re.fullmatch(r"[A-Za-z0-9_\-]+", line_clean):
            continue
        # もし1行目に学籍番号と氏名が同居している場合 (例: "00000001 山田 太郎")
        if idx == 0 and student_id and line_clean.startswith(student_id.strip()):
            rem = line_clean[len(student_id.strip()):].strip()
            if rem:
                name_lines.append(rem)
            continue
        name_lines.append(line_clean)

    if not name_lines:
        return ""

    combined_text = " ".join(name_lines)
    # 全角スペースやタブを半角スペースに正規化し、分割
    raw_tokens = re.split(r"[\s\u3000\t]+", combined_text)
    tokens = []
    for tok in raw_tokens:
        tok = tok.strip()
        if not tok:
            continue
        # 角括弧や丸括弧のボタン文字列を除外
        tok_clean = re.sub(r"^[\[\(（【]|[\]\)）】]$", "", tok).strip()
        if tok_clean in _NAME_EXCLUDE_WORDS:
            continue
        tokens.append(tok)

    return " ".join(tokens)


def normalize_grade(raw: str) -> str:
    """学年を正規化する (v10 §2.2)。

    - NFKC正規化（全角数字を半角数字へ: 高２→高2, 中３→中3）
    - 前後の空白除去
    - 複数学年表記（高1・2等）は取得値を保持
    - 空欄は推測せず空欄のまま保持
    """
    if not raw:
        return ""

    text = unicodedata.normalize("NFKC", str(raw))
    text = text.strip()
    # 連続スペースを1個に
    text = re.sub(r"[\s\u3000]+", " ", text)
    return text



# ---------------------------------------------------------------------------
# 受講区分 正規化
# ---------------------------------------------------------------------------

def normalize_division(raw: str) -> str:
    """受講区分を正規化する。

    仕様書 §14.1:
    - NFKC
    - 大文字化
    - 前後空白除去
    - 空文字を許可
    """
    if not raw:
        return ""

    text = unicodedata.normalize("NFKC", raw)
    text = text.upper()
    text = text.strip()

    return text


# ---------------------------------------------------------------------------
# 科目 正規化
# ---------------------------------------------------------------------------

# 末尾の中黒・句読点・ダッシュ・ハイフン・空白を除去するパターン
_SUBJECT_TRAILING_RE = re.compile(
    r"[·・、，,\-−－―─–—\s]+$"
)

# 内部空白除去用
_ALL_WHITESPACE_RE = re.compile(r"\s+")


def normalize_subject(raw: str) -> Optional[str]:
    """科目名を正規化する。

    仕様書 §14.1:
    - NFKC
    - 大文字化
    - 前後および内部空白除去
    - 末尾の中黒・、dashes、hyphen、空白等の指定記号を除去
    - 空文字は行スキップ → Noneを返す
    """
    if not raw:
        return None

    text = unicodedata.normalize("NFKC", raw)
    text = text.upper()
    # 前後空白除去
    text = text.strip()
    # 内部空白除去
    text = _ALL_WHITESPACE_RE.sub("", text)
    # 末尾の指定記号を除去
    text = _SUBJECT_TRAILING_RE.sub("", text)

    if not text:
        return None

    return text


# ---------------------------------------------------------------------------
# header 正規化 (DOM抽出時のheader照合用)
# ---------------------------------------------------------------------------

def normalize_header(raw: str) -> str:
    """header照合用の正規化を行う。

    仕様書 §13.6:
    - NFKC
    - 大文字化
    - 改行を半角スペースへ
    - 前後trim
    - 空白の除去
    """
    if not raw:
        return ""

    text = unicodedata.normalize("NFKC", raw)
    text = text.upper()
    text = text.replace("\n", " ").replace("\r", " ")
    text = text.strip()
    text = _ALL_WHITESPACE_RE.sub("", text)

    return text


# ---------------------------------------------------------------------------
# ブラックリスト判定
# ---------------------------------------------------------------------------

# ブラックリスト判定用の句読点除去パターン
_BLACKLIST_PUNCTUATION_RE = re.compile(r"[。、．，.!！?？…]")


def normalize_for_blacklist(text: str) -> str:
    """ブラックリスト比較用の正規化を行う。

    仕様書 §17:
    - NFKC
    - 空白除去
    - 指定句読点除去
    """
    if not text:
        return ""

    result = unicodedata.normalize("NFKC", text)
    result = _ALL_WHITESPACE_RE.sub("", result)
    result = _BLACKLIST_PUNCTUATION_RE.sub("", result)

    return result


# ---------------------------------------------------------------------------
# 作成者 正規化
# ---------------------------------------------------------------------------

# 末尾の括弧書き除去パターン
_TRAILING_PAREN_RE = re.compile(r"[（(][^）)]*[）)]$")


def normalize_author(raw: str) -> str:
    """作成者名を正規化する。

    仕様書 §18.1:
    1. NFKC
    2. 前後空白・連続空白処理
    3. 末尾敬称の除去
    4. 末尾括弧書き除去
    5. 再度末尾敬称除去
    6. 大文字化
    7. 内部空白除去
    """
    if not raw:
        return ""

    # 敬称リスト
    honorifics = ["先生", "講師", "さん", "氏", "様"]

    text = unicodedata.normalize("NFKC", raw)

    # 2. 前後空白・連続空白処理
    text = _MULTI_SPACE_RE.sub(" ", text).strip()

    # 3. 末尾敬称の除去
    text = _remove_trailing_honorifics(text, honorifics)

    # 4. 末尾括弧書き除去（連続して除去）
    while True:
        new_text = _TRAILING_PAREN_RE.sub("", text).strip()
        if new_text == text:
            break
        text = new_text

    # 5. 再度末尾敬称除去
    text = _remove_trailing_honorifics(text, honorifics)

    # 6. 大文字化
    text = text.upper()

    # 7. 内部空白除去
    text = _ALL_WHITESPACE_RE.sub("", text)

    return text


def _remove_trailing_honorifics(text: str, honorifics: list[str]) -> str:
    """末尾の敬称を繰り返し除去する。"""
    changed = True
    while changed:
        changed = False
        for h in honorifics:
            if text.endswith(h):
                text = text[:-len(h)].strip()
                changed = True
    return text


# ---------------------------------------------------------------------------
# 有効文字数カウント
# ---------------------------------------------------------------------------

# 記号、空白、改行、制御文字等を除去して有効文字数を数えるパターン
_EFFECTIVE_CHAR_RE = re.compile(
    r"[\s\u3000\-−－―─–—=＝+＋*＊/／\\＼|｜#＃@＠!！?？"
    r"。、．，.・:：;；~～^＾`「」『』【】〔〕〈〉《》"
    r"（）()\[\]{}<>""''\"'…_＿▽△▼▲○●◎◇◆□■★☆→←↑↓]"
)


def count_effective_chars(text: str) -> int:
    """有効文字数を数える。

    仕様書 §18.5, §18.6:
    記号、空白、改行、制御文字等を除去した有効文字数をlen()で数える。
    """
    if not text:
        return 0

    normalized = unicodedata.normalize("NFKC", text)
    effective = _EFFECTIVE_CHAR_RE.sub("", normalized)
    return len(effective)


# ---------------------------------------------------------------------------
# summary row 判定
# ---------------------------------------------------------------------------

# summary row判定用の正規化
_SUMMARY_LABELS: set[str] = {"合計", "総計", "計", "小計", "平均", "件数"}


def is_summary_row(student_id_cell: str) -> bool:
    """student_idセルがsummary rowかどうか判定する。

    仕様書 §13.9:
    NFKC・大文字化・trim・内部空白除去した値が指定ラベルに一致する場合、
    summary rowとして除外する。
    """
    if not student_id_cell:
        return False

    text = unicodedata.normalize("NFKC", student_id_cell)
    text = text.upper()
    text = text.strip()
    text = _ALL_WHITESPACE_RE.sub("", text)

    return text in _SUMMARY_LABELS


# ---------------------------------------------------------------------------
# Formula Injection 防止
# ---------------------------------------------------------------------------

# Unicode空白を含むtrim用パターン
_TRIM_WHITESPACE_RE = re.compile(
    r"^[\s\t\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]+"
    r"|[\s\t\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]+$"
)

FORMULA_INJECTION_CHARS: set[str] = {"=", "+", "-", "@"}


def sanitize_csv_value(value: str) -> str:
    """CSV出力直前にFormula Injection対策を行う。

    仕様書 §28.4:
    前後の空白、タブ、Unicode空白をtrimした後の先頭文字が
    =, +, -, @ のいずれかなら先頭に ' を付与する。
    """
    if not value:
        return value

    trimmed = _TRIM_WHITESPACE_RE.sub("", value)
    if trimmed and trimmed[0] in FORMULA_INJECTION_CHARS:
        return "'" + value

    return value
