"""
教室自動巡回用ブラウザ操作モジュール (ClassroomNavigator)
- 教室検索inputクリックによるモーダル起動
- モーダル内表示件数を「300件」に設定
- モーダル内テーブルの全教室行の抽出
- 指定行（列）クリックによる教室設定 & 検索ボタン押下
- 検索結果テーブルの描画監視
- 最小権限対応: モーダルが開かない場合は権限なしとして安全終了
"""
import json
from typing import List, Dict, Optional, Callable, Any
from PySide6.QtCore import QObject, QTimer
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

    // 1. inputへフォーカス & 多層マウスクリックイベント
    input.focus();
    var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    eventNames.forEach(function(name) {
        input.dispatchEvent(new MouseEvent(name, { bubbles: true, cancelable: true, view: window }));
    });
    input.click();

    // 2. 親要素 (control, field) に対してもクリック発火 (Buefy / Vue ラッパー対策)
    var cur = input.parentElement;
    for (var depth = 0; depth < 3 && cur; depth++) {
        eventNames.forEach(function(name) {
            cur.dispatchEvent(new MouseEvent(name, { bubbles: true, cancelable: true, view: window }));
        });
        cur.click();
        cur = cur.parentElement;
    }

    return { success: true, selector: matchedSelector };
})());
"""

INIT_TABLE_300_AND_FETCH_JS = """
JSON.stringify((function() {
    var modal = document.querySelector(".modal.is-active") ||
                document.querySelector(".modal-card") ||
                document.querySelector("[role='dialog']") ||
                document.querySelector(".modal");
    if (!modal) {
        return { success: false, reason: "モーダルが表示されていません" };
    }

    // 表示件数を「300件」に設定
    var selectEl = modal.querySelector(".pagination select, select");
    var changedCount = false;
    if (selectEl && selectEl.value !== "300") {
        var opt = selectEl.querySelector("option[value='300']");
        if (opt) {
            selectEl.value = "300";
            selectEl.dispatchEvent(new Event('change', { bubbles: true }));
            changedCount = true;
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

    return {
        success: true,
        changedCount: changedCount,
        classrooms: classrooms,
        count: classrooms.length
    };
})());
"""

def get_click_row_js(row_index: int, target_code: str = "") -> str:
    """指定行インデックス（または教室コード）の列をクリックするJSコードを生成"""
    escaped_code = json.dumps(target_code, ensure_ascii=False)
    return f"""
JSON.stringify((function(targetIndex, targetCode) {{
    var modal = document.querySelector(".modal.is-active") ||
                document.querySelector(".modal-card") ||
                document.querySelector("[role='dialog']") ||
                document.querySelector(".modal");
    if (!modal) {{
        return {{ success: false, reason: "モーダルが表示されていません" }};
    }}

    var rows = modal.querySelectorAll(".selectable-table table tbody tr, table.is-striped tbody tr, table tbody tr");
    if (rows.length === 0) {{
        return {{ success: false, reason: "テーブルに行が存在しません" }};
    }}

    var targetRow = null;
    // 1. 教室コードが一致する行を優先探索
    if (targetCode) {{
        for (var i = 0; i < rows.length; i++) {{
            var tr = rows[i];
            var codeEl = tr.querySelector("td[data-label='教室コード'], td:nth-child(4)");
            var code = (codeEl ? (codeEl.innerText || codeEl.textContent) : "").trim();
            if (code === targetCode) {{
                targetRow = tr;
                break;
            }}
        }}
    }}

    // 2. コード一致がなければインデックスで特定
    if (!targetRow && targetIndex >= 0 && targetIndex < rows.length) {{
        targetRow = rows[targetIndex];
    }}

    if (!targetRow) {{
        return {{ success: false, reason: "対象の行が見つかりません: index=" + targetIndex + ", code=" + targetCode }};
    }}

    targetRow.scrollIntoView({{ block: 'nearest' }});
    // 「テーブルの列を押すことで、教室が設定されます」 -> td をクリック
    var clickTarget = targetRow.querySelector("td[data-label='教室名']") ||
                      targetRow.querySelector("td") ||
                      targetRow;

    var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    eventNames.forEach(function(name) {{
        clickTarget.dispatchEvent(new MouseEvent(name, {{ bubbles: true, cancelable: true, view: window }}));
    }});
    clickTarget.click();

    return {{ success: true, rowIndex: targetIndex, targetCode: targetCode }};
}})({row_index}, {escaped_code}));
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


class ClassroomNavigator(QObject):
    """
    教室自動巡回用ブラウザコントローラー
    - モーダル起動 & 最小権限判定 (安全停止)
    - 300件設定 & テーブル行数・教室リスト取得
    - 指定行クリック & 検索ボタン押下 & 一覧ロード完了待機
    """

    def __init__(self, page: QWebEnginePage, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.page = page
        self.logger = get_logger()

    def open_class_modal(
        self,
        callback: Callable[[bool, str], None],
        timeout_sec: float = 3.5,
    ):
        """
        教室検索inputをクリックしてモーダルを開く。
        モーダルが開かない場合は権限なし (has_permission=False) として安全終了コールバック。
        """
        # 既に開いているかチェック
        def _check_already_open(initial_res):
            init_data = self._parse_json(initial_res)
            if init_data.get("active", False):
                self.logger.info("モーダルは既に表示されています")
                callback(True, "")
                return

            self.logger.info("画面トップの教室検索inputをクリックしてモーダル表示を試行中...")

            def _on_click_open(res):
                data = self._parse_json(res)
                if not data.get("success", False):
                    self.logger.warning(f"教室検索inputのクリック失敗: {data.get('reason')}")
                    callback(False, data.get("reason", "教室検索inputが見つかりません"))
                    return

                # モーダル出現待機ポーリング
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
                            self.logger.info(f"教室選択モーダルの表示を確認しました ({elapsed:.1f}s)")
                            callback(True, "")
                        elif attempts >= max_attempts:
                            self.logger.info(
                                f"教室検索モーダルが表示されませんでした ({timeout_sec:.1f}秒経過・最小権限)"
                            )
                            callback(
                                False,
                                "教室選択モーダルが開かないため、教室巡回は利用できません（自教室のみの閲覧権限です）。"
                                "\n現在の所属教室を解析する場合は『▶ 処理開始』をご利用ください。"
                            )
                        else:
                            QTimer.singleShot(interval_ms, _poll_modal)

                    self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _on_check_modal)

                QTimer.singleShot(interval_ms, _poll_modal)

            self.page.runJavaScript(OPEN_CLASS_MODAL_JS, _on_click_open)

        self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _check_already_open)

    def init_classroom_table(
        self,
        callback: Callable[[bool, List[Dict[str, Any]], str], None],
    ):
        """
        モーダル内の表示件数を300件に設定し、テーブル内の全教室行を取得する。
        """
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
                    self.logger.info(
                        f"モーダルから全 {len(classrooms)} 件の教室行を取得しました (表示件数: 300件)"
                    )
                    callback(True, classrooms, "")
                elif fetch_attempts < max_fetch:
                    self.logger.info(f"テーブル描画を待機中... ({fetch_attempts}/{max_fetch})")
                    QTimer.singleShot(interval_ms, _do_fetch)
                else:
                    err = data.get("reason", "教室テーブルの行が見つかりませんでした")
                    self.logger.warning(err)
                    callback(False, [], err)

            self.page.runJavaScript(INIT_TABLE_300_AND_FETCH_JS, _on_fetch_res)

        _do_fetch()

    def select_classroom_row_and_search(
        self,
        row_index: int,
        classroom_code: str,
        callback: Callable[[bool, str], None],
        max_retries: int = 2,
    ):
        """
        モーダルの指定行（列）をクリックして教室を設定し、検索ボタンを押下して一覧ロードを待機する。
        """
        current_attempt = 0

        def _execute_attempt():
            nonlocal current_attempt
            current_attempt += 1
            self.logger.info(
                f"教室選択・検索実行: 行 {row_index} / コード '{classroom_code}' (試行 {current_attempt}/{max_retries + 1})"
            )

            def _on_modal_ready():
                click_js = get_click_row_js(row_index, classroom_code)

                def _on_click_res(c_res):
                    c_data = self._parse_json(c_res)
                    if not c_data.get("success", False):
                        _handle_failure(c_data.get("reason", "教室行のクリックに失敗"))
                        return

                    self.logger.info(
                        f"行 {row_index} (コード: {classroom_code}) の列をクリックしました。検索ボタンを押下します..."
                    )
                    QTimer.singleShot(200, _click_search)

                self.page.runJavaScript(click_js, _on_click_res)

            def _click_search():
                def _on_search_res(s_res):
                    s_data = self._parse_json(s_res)
                    if not s_data.get("success", False):
                        _handle_failure(s_data.get("reason", "検索ボタンのクリック失敗"))
                        return

                    self.logger.info("検索ボタンを押下しました。検索結果テーブルの描画を待機中...")
                    _wait_for_search_result()

                self.page.runJavaScript(CLICK_SEARCH_BUTTON_JS, _on_search_res)

            def _wait_for_search_result():
                wait_attempts = 0
                max_wait = 30  # 6秒
                interval_ms = 200

                def _poll_ready():
                    nonlocal wait_attempts
                    wait_attempts += 1

                    def _on_wait_res(w_res):
                        w_data = self._parse_json(w_res)
                        if w_data.get("ready", False):
                            self.logger.info(
                                f"教室 (コード: {classroom_code}) のカリキュラム一覧描画完了を確認しました"
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
                    f"教室切り替え失敗 ({reason}) - 試行 {current_attempt}/{max_retries + 1}"
                )
                if current_attempt <= max_retries:
                    self.logger.info("教室切り替えを再試行します...")
                    QTimer.singleShot(500, _execute_attempt)
                else:
                    self.logger.error("教室切り替えが最大試行回数に達したため失敗と判定します")
                    callback(False, reason)

            # モーダルが既に開いているか確認し、開いていなければ開く
            def _check_modal_status(m_res):
                m_data = self._parse_json(m_res)
                if m_data.get("active", False):
                    _on_modal_ready()
                else:
                    self.open_class_modal(
                        lambda ok, err: _on_modal_ready() if ok else _handle_failure(err),
                        timeout_sec=3.5,
                    )

            self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _check_modal_status)

        _execute_attempt()

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
