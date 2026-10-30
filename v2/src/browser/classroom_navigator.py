"""
教室自動巡回用ブラウザ操作モジュール (ClassroomNavigator - 確定版)
- 教室検索input押下 → 画面余白クリック (JSイベント + Qtネイティブ実マウスクリックの二重発火、最大3回リトライ)
- モーダル内表示件数を「300件」に設定 & 全教室行の抽出
- td[data-label='教室名'] 最優先クリック & trイベント伝播による確実な教室設定
- 検索ボタン押下 & スピナー消滅 + 一覧テーブル行描画の確定監視
- 最小権限対応: 3回試行後も開かない場合は安全終了
"""
import json
from typing import List, Dict, Optional, Callable, Any
from PySide6.QtCore import QObject, QTimer, QPoint, QEvent, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QMouseEvent
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

TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS = """
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

    // 1. inputへフォーカス & クリック
    input.focus();
    var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    eventNames.forEach(function(name) {
        input.dispatchEvent(new MouseEvent(name, { bubbles: true, cancelable: true, view: window }));
    });
    input.click();

    // 2. 120ms後に input.blur() および画面余白 (body / document) のクリックを発火
    setTimeout(function() {
        input.blur();
        input.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));

        // 画面の安全な余白位置 (ヘッダーやボタンのない場所) をクリック
        var bgTarget = document.querySelector(".wrapper") ||
                       document.querySelector(".container") ||
                       document.body;
        eventNames.forEach(function(name) {
            bgTarget.dispatchEvent(new MouseEvent(name, {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: 100,
                clientY: 80
            }));
        });
        bgTarget.click();
    }, 120);

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

def get_click_classroom_cell_js(row_index: int, target_code: str = "") -> str:
    """指定行の教室名セルをクリックし、行全体にも伝播させるJSコードを生成"""
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

    if (!targetRow && targetIndex >= 0 && targetIndex < rows.length) {{
        targetRow = rows[targetIndex];
    }}

    if (!targetRow) {{
        return {{ success: false, reason: "対象の行が見つかりません: index=" + targetIndex + ", code=" + targetCode }};
    }}

    targetRow.scrollIntoView({{ block: 'nearest' }});

    // 「教室名」セルを最優先でクリック
    var cell = targetRow.querySelector("td[data-label='教室名']") ||
               targetRow.querySelector("td:nth-child(3)") ||
               targetRow.querySelector("td") ||
               targetRow;

    var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    eventNames.forEach(function(name) {{
        cell.dispatchEvent(new MouseEvent(name, {{ bubbles: true, cancelable: true, view: window }}));
    }});
    cell.click();

    // 行 tr にも念のためクリック伝播
    if (cell !== targetRow) {{
        targetRow.click();
    }}

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

    var loading = document.querySelector(".loading-overlay, .is-loading, .loading, .loading-mask");
    if (loading) {
        var style = window.getComputedStyle(loading);
        if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
            return { ready: false, reason: "検索結果読み込み中 (スピナー検出)" };
        }
    }

    var table = document.querySelector(".my-table, .b-table table, table.my-search-table ~ table, table");
    if (!table) {
        return { ready: false, reason: "一覧テーブル未検出" };
    }

    var rows = table.querySelectorAll("tbody tr");
    if (rows.length === 0) {
        return { ready: false, reason: "一覧テーブルの行がまだ描画されていません" };
    }

    return {
        ready: true,
        rowCount: rows.length
    };
})());
"""


class ClassroomNavigator(QObject):
    """
    教室自動巡回用ブラウザコントローラー (確定版)
    - インプット押下 → 画面余白クリック (JS + Qtネイティブ実マウスクリック、最大3回リトライ)
    - 300件テーブル初期化
    - td[data-label='教室名'] 最優先クリック & trイベント伝播
    - 検索ボタン押下 & スピナー消滅 + 一覧テーブル行描画待機
    """

    def __init__(self, target: Any, parent: Optional[QObject] = None):
        super().__init__(parent)
        # target は QWebEngineView または QWebEnginePage のいずれにも対応
        if hasattr(target, "page") and callable(getattr(target, "page")):
            self.view = target
            self.page = target.page()
        else:
            self.page = target
            self.view = getattr(target, "parent", lambda: None)() if hasattr(target, "parent") else None
        self.logger = get_logger()

    def open_class_modal(
        self,
        callback: Callable[[bool, str], None],
        max_attempts: int = 3,
    ):
        """
        インプット押下 → 画面余白クリック（JS + Qtネイティブマウスクリック）によりモーダルを開く。
        最大3回リトライし、それでも開かない場合は最小権限安全停止。
        """
        current_attempt = 0

        # まず既に開いているか確認
        def _check_already_open(initial_res):
            init_data = self._parse_json(initial_res)
            if init_data.get("active", False):
                self.logger.info("モーダルは既に開いています")
                callback(True, "")
                return

            _try_open_sequence()

        def _try_open_sequence():
            nonlocal current_attempt
            current_attempt += 1
            self.logger.info(
                f"モーダル起動試行 {current_attempt}/{max_attempts}: インプット押下 → 画面余白クリックを実行中..."
            )

            # Qt側でWebEngineViewに確実にフォーカスを当てる
            if self.view and hasattr(self.view, "setFocus"):
                try:
                    self.view.setFocus()
                except Exception:
                    pass

            # 1. JS側でインプット押下 & 120ms後画面余白クリック
            def _on_js_triggered(res):
                data = self._parse_json(res)
                if not data.get("success", False):
                    self.logger.warning(f"インプット操作失敗: {data.get('reason')}")
                    _handle_failure(data.get("reason", "インプットが見つかりません"))
                    return

                # 2. Qtネイティブマウスクリックも余白座標 (x=100, y=80) に送信
                QTimer.singleShot(150, _send_native_background_click)

            def _send_native_background_click():
                if self.view and hasattr(self.view, "mapToGlobal"):
                    target_widget = (
                        self.view.focusProxy()
                        if hasattr(self.view, "focusProxy") and self.view.focusProxy()
                        else self.view
                    )
                    safe_pos = QPoint(100, 80)
                    try:
                        press_ev = QMouseEvent(
                            QEvent.Type.MouseButtonPress,
                            safe_pos,
                            target_widget.mapToGlobal(safe_pos),
                            Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier,
                        )
                        release_ev = QMouseEvent(
                            QEvent.Type.MouseButtonRelease,
                            safe_pos,
                            target_widget.mapToGlobal(safe_pos),
                            Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier,
                        )
                        QApplication.sendEvent(target_widget, press_ev)
                        QApplication.sendEvent(target_widget, release_ev)
                    except Exception as e:
                        self.logger.warning(f"ネイティブマウスクリック送信スキップ: {e}")

                # 3. モーダル出現監視 (最大1.5秒待機)
                _poll_modal_active(timeout_ms=1500)

            def _poll_modal_active(timeout_ms: int):
                poll_attempts = 0
                interval_ms = 150
                max_polls = timeout_ms // interval_ms

                def _do_poll():
                    nonlocal poll_attempts
                    poll_attempts += 1

                    def _on_check(m_res):
                        m_data = self._parse_json(m_res)
                        if m_data.get("active", False):
                            self.logger.info(
                                f"教室選択モーダルの表示を確認しました (試行 {current_attempt})"
                            )
                            callback(True, "")
                        elif poll_attempts >= max_polls:
                            _handle_failure("タイムアウト (モーダル未検出)")
                        else:
                            QTimer.singleShot(interval_ms, _do_poll)

                    self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _on_check)

                QTimer.singleShot(interval_ms, _do_poll)

            def _handle_failure(reason: str):
                self.logger.warning(f"モーダル起動試行 {current_attempt} 失敗: {reason}")
                if current_attempt < max_attempts:
                    retry_wait = 400 + (current_attempt * 300)
                    self.logger.info(f"モーダル起動を再試行します ({retry_wait}ms後)...")
                    QTimer.singleShot(retry_wait, _try_open_sequence)
                else:
                    self.logger.info(
                        f"モーダルが {max_attempts} 回の試行で開かなかったため、最小権限（自教室のみ閲覧権限）と判定しました"
                    )
                    callback(
                        False,
                        "教室選択モーダルが開かないため、教室巡回は利用できません（自教室のみの閲覧権限です）。"
                        "\n現在の所属教室を解析する場合は『▶ 処理開始』をご利用ください。"
                    )

            self.page.runJavaScript(TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS, _on_js_triggered)

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
        指定行の「教室名」セルをクリックして教室を設定し、検索ボタンを押下して一覧ロードを待機する。
        """
        current_attempt = 0

        def _execute_attempt():
            nonlocal current_attempt
            current_attempt += 1
            self.logger.info(
                f"教室選択・検索実行: 行 {row_index} / コード '{classroom_code}' (試行 {current_attempt}/{max_retries + 1})"
            )

            def _on_modal_ready():
                click_js = get_click_classroom_cell_js(row_index, classroom_code)

                def _on_click_res(c_res):
                    c_data = self._parse_json(c_res)
                    if not c_data.get("success", False):
                        _handle_failure(c_data.get("reason", "教室名セルのクリックに失敗"))
                        return

                    self.logger.info(
                        f"行 {row_index} (コード: {classroom_code}) の教室名セルをクリックしました。検索ボタンを押下します..."
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
                max_wait = 35  # 最大7秒
                interval_ms = 200

                def _poll_ready():
                    nonlocal wait_attempts
                    wait_attempts += 1

                    def _on_wait_res(w_res):
                        w_data = self._parse_json(w_res)
                        if w_data.get("ready", False):
                            self.logger.info(
                                f"教室 (コード: {classroom_code}) のカリキュラム一覧描画完了を確認しました (行数: {w_data.get('rowCount')})"
                            )
                            callback(True, "")
                        elif wait_attempts >= max_wait:
                            _handle_failure(f"検索結果のロード待機タイムアウト: {w_data.get('reason')}")
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
                    QTimer.singleShot(600, _execute_attempt)
                else:
                    self.logger.error("教室切り替えが最大試行回数に達したため失敗と判定します")
                    callback(False, reason)

            # モーダルが既に開いているか確認し、開いていなければ新シーケンスで開く
            def _check_modal_status(m_res):
                m_data = self._parse_json(m_res)
                if m_data.get("active", False):
                    _on_modal_ready()
                else:
                    self.open_class_modal(
                        lambda ok, err: _on_modal_ready() if ok else _handle_failure(err),
                        max_attempts=3,
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
