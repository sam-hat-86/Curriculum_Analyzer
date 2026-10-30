"""
教室自動巡回用ブラウザ操作モジュール (ClassroomNavigator)
- 教室検索inputクリックによるモーダル起動 (マルチイベント発火 & 祖先要素クリック対応)
- モーダル検知 (複数セレクタ対応 & 描画完了待機)
- 最小権限判定 (6.0秒タイムアウトによる権限なしフォールバック)
- モーダル内の教室一覧テーブル抽出
- 教室行クリックによる教室設定 & 検索ボタン押下
- 検索結果テーブルの描画完了監視
"""
import json
from typing import List, Dict, Optional, Callable, Any
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWebEngineCore import QWebEnginePage

from src.utils.logger import get_logger


CHECK_MODAL_ACTIVE_JS = """
JSON.stringify((function() {
    function isVisible(el) {
        if (!el) return false;
        var style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        var rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    // 候補セレクタ群
    var candidates = [
        document.querySelector(".modal.is-active"),
        document.querySelector(".modal-card"),
        document.querySelector("[role='dialog']"),
        document.querySelector(".selectable-table"),
        document.querySelector(".modal")
    ];

    for (var i = 0; i < candidates.length; i++) {
        var c = candidates[i];
        if (c && isVisible(c)) {
            var table = c.querySelector("table") || document.querySelector(".modal table, .selectable-table table");
            var rows = table ? table.querySelectorAll("tbody tr").length : 0;
            return {
                active: true,
                matchedSelector: c.className || c.tagName,
                hasTable: !!table,
                rowCount: rows
            };
        }
    }

    return { active: false };
})());
"""

OPEN_CLASS_MODAL_JS = """
JSON.stringify((function() {
    var selectors = [
        ".search-branch input[placeholder*='教室検索']",
        "input[placeholder*='教室検索']",
        ".search-branch .control:not(.branch-code-input) input",
        ".search-branch input:not([maxlength='5'])",
        ".search-branch input",
        "input[placeholder*='教室']"
    ];

    var input = null;
    var matchedSelector = null;
    for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el) {
            input = el;
            matchedSelector = selectors[i];
            break;
        }
    }

    if (!input) {
        return { success: false, reason: "教室検索inputが見つかりません" };
    }

    var details = {
        selector: matchedSelector,
        placeholder: input.placeholder,
        value: input.value
    };

    // 1. inputへフォーカス & 多層イベント発火
    input.focus();
    var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    eventNames.forEach(function(name) {
        input.dispatchEvent(new MouseEvent(name, { bubbles: true, cancelable: true, view: window }));
    });
    input.click();

    // 2. 親要素 (control, field) に対してもクリック発火 (Buefy / Vue のラッパー対策)
    var cur = input.parentElement;
    for (var depth = 0; depth < 3 && cur; depth++) {
        eventNames.forEach(function(name) {
            cur.dispatchEvent(new MouseEvent(name, { bubbles: true, cancelable: true, view: window }));
        });
        cur.click();
        cur = cur.parentElement;
    }

    return { success: true, details: details };
})());
"""

FETCH_CLASSROOMS_JS = """
JSON.stringify((function() {
    var modal = document.querySelector(".modal.is-active") ||
                document.querySelector(".modal-card") ||
                document.querySelector("[role='dialog']") ||
                document.querySelector(".modal");
    if (!modal) {
        return { success: false, reason: "モーダルが表示されていません" };
    }

    // 表示件数selectがある場合、300件を選択
    var selectEl = modal.querySelector(".pagination select, select");
    if (selectEl && selectEl.value !== "300") {
        var opt = selectEl.querySelector("option[value='300']");
        if (opt) {
            selectEl.value = "300";
            selectEl.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    var rows = modal.querySelectorAll(".selectable-table table tbody tr, table.is-striped tbody tr, table tbody tr");
    var classrooms = [];
    for (var i = 0; i < rows.length; i++) {
        var tr = rows[i];
        var codeEl = tr.querySelector("td[data-label='教室コード'], td:nth-child(4)");
        var nameEl = tr.querySelector("td[data-label='教室名'], td:nth-child(3)");
        var areaEl = tr.querySelector("td[data-label='エリア名'], td:nth-child(2)");
        var blockEl = tr.querySelector("td[data-label='ブロック名'], td:nth-child(1)");

        var code = (codeEl ? (codeEl.innerText || codeEl.textContent) : "").trim();
        var name = (nameEl ? (nameEl.innerText || nameEl.textContent) : "").trim();
        var area = (areaEl ? (areaEl.innerText || areaEl.textContent) : "").trim();
        var block = (blockEl ? (blockEl.innerText || blockEl.textContent) : "").trim();

        if (code || name) {
            classrooms.push({
                index: i,
                classroom_code: code,
                classroom_name: name,
                area_name: area,
                block_name: block
            });
        }
    }
    return { success: true, classrooms: classrooms, count: classrooms.length };
})());
"""

def get_select_classroom_js(target_code: str) -> str:
    """指定教室コードまたは教室名の行をクリックするJSコードを生成"""
    escaped_target = json.dumps(target_code, ensure_ascii=False)
    return f"""
JSON.stringify((function(targetCode) {{
    var modal = document.querySelector(".modal.is-active") ||
                document.querySelector(".modal-card") ||
                document.querySelector("[role='dialog']") ||
                document.querySelector(".modal");
    if (!modal) {{
        return {{ success: false, reason: "モーダルが表示されていません" }};
    }}
    var rows = modal.querySelectorAll(".selectable-table table tbody tr, table.is-striped tbody tr, table tbody tr");
    var targetRow = null;
    for (var i = 0; i < rows.length; i++) {{
        var tr = rows[i];
        var codeEl = tr.querySelector("td[data-label='教室コード'], td:nth-child(4)");
        var code = (codeEl ? (codeEl.innerText || codeEl.textContent) : "").trim();
        if (code === targetCode) {{
            targetRow = tr;
            break;
        }}
        var nameEl = tr.querySelector("td[data-label='教室名'], td:nth-child(3)");
        var name = (nameEl ? (nameEl.innerText || nameEl.textContent) : "").trim();
        if (name === targetCode) {{
            targetRow = tr;
            break;
        }}
    }}

    if (!targetRow) {{
        return {{ success: false, reason: "対象の教室コードが見つかりません: " + targetCode }};
    }}

    targetRow.scrollIntoView({{ block: 'nearest' }});
    var clickTarget = targetRow.querySelector("td[data-label='教室名']") || targetRow.querySelector("td") || targetRow;
    var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    eventNames.forEach(function(name) {{
        clickTarget.dispatchEvent(new MouseEvent(name, {{ bubbles: true, cancelable: true, view: window }}));
    }});
    clickTarget.click();
    return {{ success: true, selectedCode: targetCode }};
}})({escaped_target}));
"""

CLICK_SEARCH_BUTTON_JS = """
JSON.stringify((function() {
    var btn = document.querySelector(".btn-search") ||
              document.querySelector("button.btn-search") ||
              document.querySelector(".field.has-addons-centered button");
    if (!btn) {
        var buttons = document.querySelectorAll("button");
        for (var i = 0; i < buttons.length; i++) {
            if ((buttons[i].innerText || buttons[i].textContent || "").trim() === "検索") {
                btn = buttons[i];
                break;
            }
        }
    }
    if (!btn) {
        return { success: false, reason: "検索ボタンが見つかりません" };
    }
    btn.click();
    return { success: true };
})());
"""

WAIT_FOR_SEARCH_LOAD_JS = """
JSON.stringify((function() {
    var modal = document.querySelector(".modal.is-active");
    if (modal) {
        var mStyle = window.getComputedStyle(modal);
        if (mStyle.display !== 'none' && mStyle.visibility !== 'hidden') {
            return { ready: false, reason: "モーダルがまだ閉じていません" };
        }
    }

    var loading = document.querySelector(".loading-overlay, .is-loading, .loading");
    if (loading) {
        var style = window.getComputedStyle(loading);
        if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
            return { ready: false, reason: "検索結果読み込み中" };
        }
    }

    var table = document.querySelector(".my-table, .b-table table, table.my-search-table ~ table, table");
    var hasTable = !!table;
    var rowCount = table ? table.querySelectorAll("tbody tr").length : 0;

    return {
        ready: hasTable,
        rowCount: rowCount
    };
})());
"""

CLOSE_MODAL_JS = """
JSON.stringify((function() {
    var modal = document.querySelector(".modal.is-active") ||
                document.querySelector(".modal-card") ||
                document.querySelector("[role='dialog']") ||
                document.querySelector(".modal");
    if (!modal) return { success: true };
    var closeBtn = modal.querySelector(".modal-card-foot button, button.delete, button.modal-close, button:has-text('キャンセル')");
    if (closeBtn) {
        closeBtn.click();
        return { success: true };
    }
    return { success: false };
})());
"""


class ClassroomNavigator(QObject):
    """
    教室選択モーダルの自動化コントローラー
    - 権限判定 (6.0秒タイムアウト)
    - 教室リスト取得
    - 教室選択 & 検索実行 & 待機
    """

    def __init__(self, page: QWebEnginePage, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.page = page
        self.logger = get_logger()

    def open_and_fetch_classrooms(
        self,
        callback: Callable[[bool, List[Dict[str, Any]], str], None],
        timeout_sec: float = 6.0,
    ):
        """
        教室検索モーダルを開き、教室一覧を取得する。
        6.0秒以内にモーダルが開かない場合は権限なし (has_permission=False) と判定して自教室解析へフォールバック。
        """
        # 0. まず既にモーダルが開いていないかチェック
        def _check_already_open(initial_res):
            init_data = self._parse_json(initial_res)
            if init_data.get("active", False) and init_data.get("rowCount", 0) > 0:
                self.logger.info("モーダルは既に開いています。教室一覧の抽出に進みます。")
                self._fetch_classrooms_from_modal(callback)
                return

            self.logger.info("教室検索inputをクリックしてモーダル起動を試行中...")

            def _on_click_open(res):
                data = self._parse_json(res)
                if not data.get("success", False):
                    self.logger.warning(f"教室検索inputのクリック失敗: {data.get('reason')}")
                    callback(False, [], data.get("reason", "教室検索inputが見つかりません"))
                    return

                self.logger.info(f"教室検索inputをクリックしました: {data.get('details')}")

                # モーダル出現待機タイマー (最大 timeout_sec 秒)
                attempts = 0
                interval_ms = 250
                max_attempts = int(timeout_sec * 1000 / interval_ms)

                def _poll_modal():
                    nonlocal attempts
                    attempts += 1

                    def _on_check_modal(m_res):
                        m_data = self._parse_json(m_res)
                        if m_data.get("active", False):
                            elapsed = attempts * interval_ms / 1000
                            self.logger.info(
                                f"教室選択モーダルの表示を確認しました ({elapsed:.1f}s, 要素: {m_data.get('matchedSelector')}, 行数: {m_data.get('rowCount')})"
                            )
                            # テーブルがまだ描画されていなければ少し待機
                            if m_data.get("rowCount", 0) == 0 and attempts < max_attempts:
                                QTimer.singleShot(interval_ms, _poll_modal)
                            else:
                                self._fetch_classrooms_from_modal(callback)
                        elif attempts >= max_attempts:
                            self.logger.info(
                                f"教室検索モーダルが表示されませんでした ({timeout_sec:.1f}秒経過・権限なしタイムアウト)"
                            )
                            callback(False, [], "複数教室の選択権限がありません (自教室のみ閲覧可能)")
                        else:
                            # 途中経過ログ
                            if attempts % 4 == 0:
                                self.logger.info(f"モーダル出現待機中... ({attempts * interval_ms / 1000:.1f}s)")
                            QTimer.singleShot(interval_ms, _poll_modal)

                    self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _on_check_modal)

                QTimer.singleShot(interval_ms, _poll_modal)

            self.page.runJavaScript(OPEN_CLASS_MODAL_JS, _on_click_open)

        self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _check_already_open)

    def _fetch_classrooms_from_modal(
        self, callback: Callable[[bool, List[Dict[str, Any]], str], None]
    ):
        """モーダル内のテーブルから教室一覧を取得"""
        fetch_attempts = 0
        max_fetch = 10
        interval_ms = 300

        def _do_fetch():
            nonlocal fetch_attempts
            fetch_attempts += 1

            def _on_fetch_res(res):
                data = self._parse_json(res)
                classrooms = data.get("classrooms", [])

                if data.get("success", False) and len(classrooms) > 0:
                    self.logger.info(f"モーダルから {len(classrooms)} 件の教室情報を取得しました")
                    callback(True, classrooms, "")
                elif fetch_attempts < max_fetch:
                    # まだテーブル描画が完了していない可能性があるので少し待って再取得
                    self.logger.info(f"教室テーブルの行描画を待機中... (試行 {fetch_attempts}/{max_fetch})")
                    QTimer.singleShot(interval_ms, _do_fetch)
                else:
                    err = data.get("reason", "教室一覧の取得に失敗しました (テーブル行が見つかりません)")
                    self.logger.warning(err)
                    callback(False, [], err)

            self.page.runJavaScript(FETCH_CLASSROOMS_JS, _on_fetch_res)

        _do_fetch()

    def select_and_search(
        self,
        classroom_code: str,
        callback: Callable[[bool, str], None],
        max_retries: int = 2,
    ):
        """
        教室コードを指定してモーダルで選択し、検索ボタンを押下して一覧ロードを待機する。
        失敗時は最大 max_retries 回再試行する。
        """
        current_attempt = 0

        def _execute_attempt():
            nonlocal current_attempt
            current_attempt += 1
            self.logger.info(
                f"教室選択・検索実行: コード '{classroom_code}' (試行 {current_attempt}/{max_retries + 1})"
            )

            # 1. まずモーダルが開いていなければ開く
            def _on_modal_ready():
                # 2. 教室行をクリック
                select_js = get_select_classroom_js(classroom_code)

                def _on_select_res(s_res):
                    s_data = self._parse_json(s_res)
                    if not s_data.get("success", False):
                        _handle_failure(s_data.get("reason", "教室行のクリックに失敗"))
                        return

                    self.logger.info(f"教室 '{classroom_code}' を選択しました。検索ボタンを押下します...")
                    # 少し待って検索ボタンを押下
                    QTimer.singleShot(200, _click_search)

                self.page.runJavaScript(select_js, _on_select_res)

            def _click_search():
                def _on_search_res(sc_res):
                    sc_data = self._parse_json(sc_res)
                    if not sc_data.get("success", False):
                        _handle_failure(sc_data.get("reason", "検索ボタンの押下失敗"))
                        return

                    self.logger.info("検索ボタンを押下しました。検索結果テーブルの描画を待機中...")
                    _wait_for_search_result()

                self.page.runJavaScript(CLICK_SEARCH_BUTTON_JS, _on_search_res)

            def _wait_for_search_result():
                wait_attempts = 0
                max_wait = 30  # 30 * 200ms = 6秒
                interval_ms = 200

                def _poll_ready():
                    nonlocal wait_attempts
                    wait_attempts += 1

                    def _on_wait_res(w_res):
                        w_data = self._parse_json(w_res)
                        if w_data.get("ready", False):
                            self.logger.info(
                                f"教室 '{classroom_code}' の検索結果ロード完了を確認しました"
                            )
                            callback(True, "")
                        elif wait_attempts >= max_wait:
                            _handle_failure("検索結果のロード待機タイムアウト")
                        else:
                            QTimer.singleShot(interval_ms, _poll_ready)

                    self.page.runJavaScript(WAIT_FOR_SEARCH_LOAD_JS, _on_wait_res)

                QTimer.singleShot(300, _poll_ready)

            def _handle_failure(reason: str):
                self.logger.warning(
                    f"教室 '{classroom_code}' への切り替え失敗 ({reason}) - 試行 {current_attempt}"
                )
                if current_attempt <= max_retries:
                    self.logger.info(f"教室切り替えを再試行します (残り {max_retries - current_attempt + 1} 回)...")
                    QTimer.singleShot(500, _execute_attempt)
                else:
                    self.logger.error(
                        f"教室 '{classroom_code}' への切り替えが最大試行回数に達したため失敗と判定します"
                    )
                    callback(False, reason)

            # モーダルが既に開いているか確認
            def _check_modal_for_select(m_res):
                m_data = self._parse_json(m_res)
                if m_data.get("active", False):
                    _on_modal_ready()
                else:
                    # モーダルを開いてから実行
                    def _on_open_res(o_res):
                        o_data = self._parse_json(o_res)
                        if not o_data.get("success", False):
                            _handle_failure(o_data.get("reason", "モーダルオープン失敗"))
                            return
                        QTimer.singleShot(350, _on_modal_ready)

                    self.page.runJavaScript(OPEN_CLASS_MODAL_JS, _on_open_res)

            self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _check_modal_for_select)

        _execute_attempt()

    def close_modal(self, callback: Optional[Callable[[bool], None]] = None):
        """モーダルを閉じる"""
        def _on_close_res(res):
            data = self._parse_json(res)
            if callback:
                callback(data.get("success", False))

        self.page.runJavaScript(CLOSE_MODAL_JS, _on_close_res)

    @staticmethod
    def _parse_json(res: Any) -> Dict[str, Any]:
        """JavaScript返却値の安全なJSONパース"""
        if isinstance(res, dict):
            return res
        if isinstance(res, str):
            try:
                return json.loads(res)
            except Exception:
                pass
        return {}
