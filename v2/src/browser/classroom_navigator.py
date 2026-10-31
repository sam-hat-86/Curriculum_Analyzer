"""
教室自動巡回用ブラウザ操作モジュール (ClassroomNavigator - 確定版 v4)
- 初回モーダル起動成功時点で権限あり確定 (permission_confirmed = True)
- モーダル起動の誤クローズ防止:
  ① 既存タグがあれば「×」クリック後、タグ消滅をポーリングで確認 (最大3秒)
  ② input 押下 & blur 後、余白を触らずまず1.5秒間モーダル出現を観察
  ③ まだモーダルが出ていない場合のみ余白を1回クリックし、最大15秒間気長にモーダル出現を待機
- モーダル表示後、300件表示設定 & 対象教室の行が描画されるまで最大15秒間ポーリング待機してからクリック
- 検索ボタン押下後、カリキュラム一覧テーブル描画完了まで最大30秒間気長に待機
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

# 行選択完了の判定JS (.taginput .tag の出現・教室名の合致)
CHECK_CLASSROOM_SELECTED_JS = """
JSON.stringify((function() {
    var tag = document.querySelector(".search-branch .taginput .tag") ||
              document.querySelector(".search-branch .tag") ||
              document.querySelector(".taginput .tag");
    if (!tag) {
        return { selected: false, reason: "タグ要素未検出" };
    }

    var textEl = tag.querySelector(".has-ellipsis") || tag;
    var name = (textEl.innerText || textEl.textContent || tag.getAttribute("title") || "").trim();

    var codeInput = document.querySelector(".branch-code-input input") ||
                    document.querySelector("input[placeholder*='教室コード']");
    var code = codeInput ? codeInput.value.trim() : "";

    return {
        selected: true,
        classroom_name: name,
        classroom_code: code
    };
})());
"""

# Step 1: ページ最上部へスクロールし、既存タグがあれば「×」(delete) をクリックするJS
CLEAR_CLASSROOM_TAG_JS = """
JSON.stringify((function() {
    window.scrollTo(0, 0);
    var delBtn = document.querySelector(".taginput .delete") ||
                 document.querySelector(".tag .delete") ||
                 document.querySelector(".search-branch .delete") ||
                 document.querySelector(".taginput-container a.delete") ||
                 document.querySelector("a.delete.is-small");
    if (delBtn) {
        delBtn.click();
        return { success: true, hadTag: true };
    }
    return { success: true, hadTag: false };
})());
"""

# Step 2: 教室検索inputにフォーカス＆クリックし、少し後にblurのみ発火するJS (余白クリックはしない)
FOCUS_AND_CLICK_INPUT_JS = """
JSON.stringify((function() {
    window.scrollTo(0, 0);
    var selectors = [
        ".taginput input",
        ".taginput-container input",
        ".search-branch .taginput input",
        ".search-branch input[placeholder*='教室検索']",
        "input[placeholder*='教室検索']",
        ".taginput-container",
        ".taginput",
        ".search-branch .taginput-container",
        ".autocomplete input",
        "input[readonly].input",
        "input[placeholder*='教室']",
        ".search-branch input"
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

    if (typeof input.scrollIntoView === 'function') {
        input.scrollIntoView({ block: 'nearest' });
    }
    if (typeof input.focus === 'function') {
        input.focus();
    }
    var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    eventNames.forEach(function(name) {
        input.dispatchEvent(new MouseEvent(name, { bubbles: true, cancelable: true, view: window }));
    });
    input.click();

    setTimeout(function() {
        var modal = document.querySelector(".modal.is-active");
        if (modal) {
            var style = window.getComputedStyle(modal);
            if (style.display !== 'none' && style.visibility !== 'hidden') {
                return;
            }
        }
        if (typeof input.blur === 'function') {
            input.blur();
            input.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }, 100);

    return { success: true, selector: matchedSelector };
})());
"""

# Step 3: モーダルがまだ開いていない場合のみ、安全な画面余白をクリックするJS
CLICK_SAFE_BACKGROUND_JS = """
JSON.stringify((function() {
    function isModalOpen() {
        var cands = [
            document.querySelector(".modal.is-active"),
            document.querySelector(".modal-card"),
            document.querySelector("[role='dialog']")
        ];
        for (var i = 0; i < cands.length; i++) {
            var el = cands[i];
            if (el) {
                var st = window.getComputedStyle(el);
                var rect = el.getBoundingClientRect();
                if (st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0' && rect.width > 0 && rect.height > 0) {
                    return true;
                }
            }
        }
        return false;
    }

    if (isModalOpen()) {
        return { success: true, skipped: true, reason: "modal_already_open" };
    }

    var bgTarget = document.querySelector(".wrapper") ||
                   document.querySelector(".container") ||
                   document.body;
    var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
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
    return { success: true, skipped: false };
})());
"""

# 後方互換・単体テスト用の統合JS定義 (内部でもモーダル表示中はbgTarget.click()をスキップする安全ガード付き)
TRIGGER_INPUT_AND_BACKGROUND_CLICK_JS = """
JSON.stringify((function() {
    window.scrollTo(0, 0);
    var delBtn = document.querySelector(".taginput .delete") ||
                 document.querySelector(".tag .delete") ||
                 document.querySelector(".search-branch .delete") ||
                 document.querySelector(".taginput-container a.delete") ||
                 document.querySelector("a.delete.is-small");

    function clickInputAndBg() {
        var selectors = [
            ".taginput input",
            ".taginput-container input",
            ".taginput-container",
            ".taginput",
            ".search-branch .taginput input",
            ".search-branch .taginput-container",
            ".search-branch input[placeholder*='教室検索']",
            "input[placeholder*='教室検索']",
            ".autocomplete input",
            "input[readonly].input",
            "input[placeholder*='教室']",
            ".search-branch input"
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

        if (typeof input.focus === 'function') {
            input.focus();
        }
        var eventNames = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
        eventNames.forEach(function(name) {
            input.dispatchEvent(new MouseEvent(name, { bubbles: true, cancelable: true, view: window }));
        });
        input.click();

        setTimeout(function() {
            var activeModal = document.querySelector(".modal.is-active");
            if (activeModal) {
                var st = window.getComputedStyle(activeModal);
                if (st.display !== 'none' && st.visibility !== 'hidden') {
                    return;
                }
            }
            if (typeof input.blur === 'function') {
                input.blur();
                input.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }

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

        return { success: true, selector: matchedSelector, action: "click_input_bg" };
    }

    if (delBtn) {
        delBtn.click();
        setTimeout(clickInputAndBg, 150);
        return { success: true, action: "delete_and_click" };
    } else {
        return clickInputAndBg();
    }
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
    """
    モーダル内の表示件数を300件に保ちつつ、指定行の教室名セルをクリックするJSコードを生成。
    テーブル行がまだ描画されていない場合は retryable: true を返してポーリング待機させる。
    """
    escaped_code = json.dumps(target_code, ensure_ascii=False)
    return f"""
JSON.stringify((function(targetIndex, targetCode) {{
    var modal = document.querySelector(".modal.is-active") ||
                document.querySelector(".modal-card") ||
                document.querySelector("[role='dialog']") ||
                document.querySelector(".modal");
    if (!modal) {{
        return {{ success: false, retryable: false, reason: "モーダルが表示されていません" }};
    }}

    // 表示件数が300件でなければ300件に設定して次回ポーリングで行を待つ
    var selectEl = modal.querySelector(".pagination select, select");
    if (selectEl && selectEl.value !== "300") {{
        var opt = selectEl.querySelector("option[value='300']");
        if (opt) {{
            selectEl.value = "300";
            selectEl.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
    }}

    var rows = modal.querySelectorAll(".selectable-table table tbody tr, table.is-striped tbody tr, table tbody tr");
    if (rows.length === 0) {{
        return {{ success: false, retryable: true, reason: "テーブルに行が存在しません (描画待機中)" }};
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
        return {{
            success: false,
            retryable: true,
            reason: "対象の行が見つかりません (描画待機中): index=" + targetIndex + ", code=" + targetCode
        }};
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

    // 全テーブルから「生徒」ヘッダーを持つカリキュラムテーブルを特定 (検索フォームテーブル除外)
    var tables = document.querySelectorAll("table");
    var targetTable = null;
    for (var i = 0; i < tables.length; i++) {
        var tbl = tables[i];
        if (tbl.closest(".modal") || tbl.closest("[role='dialog']")) continue;
        var headers = tbl.querySelectorAll("th");
        var hasStudent = false;
        var hasCurriculum = false;
        for (var j = 0; j < headers.length; j++) {
            var h = (headers[j].innerText || headers[j].textContent || "").trim();
            if (h.indexOf("生徒") !== -1) hasStudent = true;
            if (h.indexOf("シミュレーション") !== -1 || h.indexOf("カリキュラム") !== -1) hasCurriculum = true;
        }
        if (hasStudent && hasCurriculum) {
            targetTable = tbl;
            break;
        }
    }
    if (!targetTable && tables.length > 1) {
        targetTable = tables[1];
    } else if (!targetTable && tables.length > 0) {
        targetTable = tables[0];
    }

    if (!targetTable) {
        return { ready: false, reason: "カリキュラム一覧テーブル未検出" };
    }

    var rows = targetTable.querySelectorAll("tbody tr");
    if (rows.length > 0) {
        return {
            ready: true,
            rowCount: rows.length
        };
    }

    // 0件メッセージや空テーブルの判定
    var emptyNotice = document.querySelector(".empty, .has-text-centered, .is-empty");
    if (emptyNotice && (emptyNotice.innerText || emptyNotice.textContent || "").indexOf("ありません") !== -1) {
        return {
            ready: true,
            rowCount: 0
        };
    }

    return { ready: false, reason: "一覧テーブルの行がまだ描画されていません" };
})());
"""


class ClassroomNavigator(QObject):
    """
    教室自動巡回用ブラウザコントローラー (確定版 v4)
    - 初回モーダル起動成功により権限あり確定 (permission_confirmed = True)
    - タグ削除確認 → input押下＆1.5秒観察 → 未表示時のみ余白1回クリック＆最大15秒気長待機
    - モーダル内テーブルの300件設定＆行描画完了まで最大15秒ポーリング待機してから行クリック
    - 検索ボタン押下後、一覧テーブル描画完了まで最大30秒気長待機
    """

    def __init__(self, target: Any, parent: Optional[QObject] = None):
        super().__init__(parent)
        if hasattr(target, "page") and callable(getattr(target, "page")):
            self.view = target
            self.page = target.page()
        else:
            self.page = target
            self.view = getattr(target, "parent", lambda: None)() if hasattr(target, "parent") else None
        self.logger = get_logger()
        self.permission_confirmed: bool = False

    def open_class_modal(
        self,
        callback: Callable[[bool, str], None],
        max_attempts: int = 3,
        is_patrol_confirmed: bool = False,
    ):
        """
        段階的かつ安全に教室選択モーダルを開く。
        モーダルが既に表示されている場合は余白クリックを一切発火せず即成功とする。
        """
        if is_patrol_confirmed:
            self.permission_confirmed = True

        current_attempt = 0

        def _on_modal_opened():
            self.permission_confirmed = True
            self.logger.info(f"教室選択モーダルの表示を確認しました (試行 {max(1, current_attempt)})")
            callback(True, "")

        # まず既に開いているか確認
        def _check_already_open(initial_res):
            init_data = self._parse_json(initial_res)
            if init_data.get("active", False):
                self.permission_confirmed = True
                self.logger.info("モーダルは既に開いています")
                callback(True, "")
                return

            _try_open_sequence()

        def _try_open_sequence():
            nonlocal current_attempt

            # リトライ開始時にも、前の試行で遅れてモーダルが開いていないか必ず確認する
            def _check_before_attempt(pre_res):
                nonlocal current_attempt
                pre_data = self._parse_json(pre_res)
                if pre_data.get("active", False):
                    _on_modal_opened()
                    return

                current_attempt += 1
                self.logger.info(
                    f"モーダル起動試行 {current_attempt}/{max_attempts}: タグ確認 → インプット押下を実行中..."
                )

                if self.view and hasattr(self.view, "setFocus"):
                    try:
                        self.view.setFocus()
                    except Exception:
                        pass

                # Step 1: 既存タグがあれば「×」をクリックして消えるのを待つ
                self.page.runJavaScript(CLEAR_CLASSROOM_TAG_JS, _on_tag_clear_triggered)

            def _on_tag_clear_triggered(clear_res):
                c_data = self._parse_json(clear_res)
                if not c_data.get("hadTag", False):
                    # タグがなかった場合は直ちに input 押下へ
                    _trigger_input_click()
                    return

                self.logger.info("既存の教室タグの削除ボタン(×)を押下しました。タグ消去を確認中...")
                tag_polls = 0
                max_tag_polls = 20  # 最大3.0秒 (150ms * 20)

                def _poll_tag_gone():
                    nonlocal tag_polls
                    tag_polls += 1

                    def _on_tag_check(t_res):
                        t_data = self._parse_json(t_res)
                        if not t_data.get("selected", False) or tag_polls >= max_tag_polls:
                            # タグが消えたので少し安定待ちを入れてから input を押す
                            QTimer.singleShot(150, _trigger_input_click)
                        else:
                            QTimer.singleShot(150, _poll_tag_gone)

                    self.page.runJavaScript(CHECK_CLASSROOM_SELECTED_JS, _on_tag_check)

                QTimer.singleShot(150, _poll_tag_gone)

            # Step 2: input 押下 & blur し、余白を触らずにまず 1.5秒間モーダル出現を待つ
            def _trigger_input_click():
                def _on_input_clicked(in_res):
                    in_data = self._parse_json(in_res)
                    if not in_data.get("success", False):
                        self.logger.warning(f"インプット操作失敗: {in_data.get('reason')}")
                        _handle_failure(in_data.get("reason", "インプットが見つかりません"))
                        return

                    _poll_stage1_without_bg_click()

                self.page.runJavaScript(FOCUS_AND_CLICK_INPUT_JS, _on_input_clicked)

            def _poll_stage1_without_bg_click():
                stage1_polls = 0
                max_stage1_polls = 10  # 1.5秒 (150ms * 10)
                interval_ms = 150

                def _do_stage1_poll():
                    nonlocal stage1_polls
                    stage1_polls += 1

                    def _on_s1_check(m_res):
                        m_data = self._parse_json(m_res)
                        if m_data.get("active", False):
                            # 余白クリックなしでモーダルが開いた！
                            _on_modal_opened()
                        elif stage1_polls >= max_stage1_polls:
                            # 1.5秒待っても開かない場合のみ、Step 3 (余白1回クリック + 気長な待機) へ
                            _trigger_safe_background_click_once()
                        else:
                            QTimer.singleShot(interval_ms, _do_stage1_poll)

                    self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _on_s1_check)

                QTimer.singleShot(interval_ms, _do_stage1_poll)

            # Step 3: まだモーダルが開いていない場合のみ余白を1回クリックし、気長に待つ
            def _trigger_safe_background_click_once():
                def _on_bg_js(bg_res):
                    bg_data = self._parse_json(bg_res)
                    if bg_data.get("skipped", False):
                        # 直前にモーダルが開いていた場合はネイティブクリックもスキップして即成功
                        _on_modal_opened()
                        return

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

                    # 権限確認済みなら最大15秒、初回未確認でも最大5秒じっくり待機する
                    wait_ms = 15000 if self.permission_confirmed else 5000
                    _poll_modal_active_patiently(timeout_ms=wait_ms)

                self.page.runJavaScript(CLICK_SAFE_BACKGROUND_JS, _on_bg_js)

            def _poll_modal_active_patiently(timeout_ms: int):
                poll_attempts = 0
                interval_ms = 200
                max_polls = max(1, timeout_ms // interval_ms)

                def _do_poll():
                    nonlocal poll_attempts
                    poll_attempts += 1

                    def _on_check(m_res):
                        m_data = self._parse_json(m_res)
                        if m_data.get("active", False):
                            _on_modal_opened()
                        elif poll_attempts >= max_polls:
                            _handle_failure("タイムアウト (モーダル未検出)")
                        else:
                            QTimer.singleShot(interval_ms, _do_poll)

                    self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _on_check)

                QTimer.singleShot(interval_ms, _do_poll)

            def _handle_failure(reason: str):
                self.logger.warning(f"モーダル起動試行 {current_attempt} 失敗: {reason}")
                if current_attempt < max_attempts:
                    retry_wait = 600 + (current_attempt * 400)
                    self.logger.info(f"モーダル起動を再試行します ({retry_wait}ms後)...")
                    QTimer.singleShot(retry_wait, _try_open_sequence)
                else:
                    if self.permission_confirmed:
                        self.logger.error(
                            f"モーダルが {max_attempts} 回の試行で開かなかったためタイムアウトしました"
                        )
                        callback(False, "教室選択モーダルの表示待機がタイムアウトしました。")
                    else:
                        self.logger.info(
                            f"モーダルが {max_attempts} 回の試行で開かなかったため、最小権限（自教室のみ閲覧権限）と判定しました"
                        )
                        callback(
                            False,
                            "教室選択モーダルが開かないため、教室巡回は利用できません（自教室のみの閲覧権限です）。"
                            "\n現在の所属教室を解析する場合は『▶ 処理開始』をご利用ください。"
                        )

            self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _check_before_attempt)

        self.page.runJavaScript(CHECK_MODAL_ACTIVE_JS, _check_already_open)

    def init_classroom_table(
        self,
        callback: Callable[[bool, List[Dict[str, Any]], str], None],
    ):
        """
        モーダル内の表示件数を300件に設定し、テーブル内の全教室行を取得する。
        """
        self.permission_confirmed = True
        fetch_attempts = 0
        max_fetch = 30  # 最大9秒 (300ms * 30)
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
        指定行の「教室名」セルをクリックして教室を設定し、
        .taginput .tag の出現により行選択完了を確認後、検索ボタンを押下して一覧ロードを待機する。
        巡回中に呼ばれるため、常に permission_confirmed = True として気長に待機する。
        """
        self.permission_confirmed = True
        current_attempt = 0

        def _execute_attempt():
            nonlocal current_attempt
            current_attempt += 1
            self.logger.info(
                f"教室選択・検索実行: 行 {row_index} / コード '{classroom_code}' (試行 {current_attempt}/{max_retries + 1})"
            )

            # モーダル表示後、300件表示＆対象行の描画完了まで最大15秒ポーリングしてからクリック
            def _on_modal_ready():
                row_polls = 0
                max_row_polls = 50  # 最大15秒 (300ms * 50)
                row_interval_ms = 300
                click_js = get_click_classroom_cell_js(row_index, classroom_code)

                def _poll_and_click_row():
                    nonlocal row_polls
                    row_polls += 1

                    def _on_click_res(c_res):
                        c_data = self._parse_json(c_res)
                        if c_data.get("success", False):
                            self.logger.info(
                                f"行 {row_index} (コード: {classroom_code}) の教室名セルをクリックしました。行選択完了 (.tag の反映) を確認中..."
                            )
                            _wait_for_selection_confirmed()
                        elif c_data.get("retryable", False) and row_polls < max_row_polls:
                            QTimer.singleShot(row_interval_ms, _poll_and_click_row)
                        else:
                            _handle_failure(c_data.get("reason", "教室名セルのクリックに失敗"))

                    self.page.runJavaScript(click_js, _on_click_res)

                _poll_and_click_row()

            def _wait_for_selection_confirmed():
                sel_attempts = 0
                max_sel = 40  # 最大8秒 (200ms * 40)
                interval_ms = 200

                def _poll_tag():
                    nonlocal sel_attempts
                    sel_attempts += 1

                    def _on_tag_res(t_res):
                        t_data = self._parse_json(t_res)
                        if t_data.get("selected", False):
                            c_name = t_data.get("classroom_name", "")
                            self.logger.info(
                                f"行選択の完了を確認しました: タグ '{c_name}' (コード: {t_data.get('classroom_code')})"
                            )
                            QTimer.singleShot(150, _click_search)
                        elif sel_attempts >= max_sel:
                            self.logger.warning("行選択タグの確定タイムアウト。検索ボタン押下へ進みます")
                            QTimer.singleShot(100, _click_search)
                        else:
                            QTimer.singleShot(interval_ms, _poll_tag)

                    self.page.runJavaScript(CHECK_CLASSROOM_SELECTED_JS, _on_tag_res)

                QTimer.singleShot(100, _poll_tag)

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
                max_wait = 120  # 最大30秒 (250ms * 120)
                interval_ms = 250
                no_spinner_empty_polls = 0

                def _poll_ready():
                    nonlocal wait_attempts, no_spinner_empty_polls
                    wait_attempts += 1

                    def _on_wait_res(w_res):
                        nonlocal no_spinner_empty_polls
                        w_data = self._parse_json(w_res)
                        reason = w_data.get("reason", "")
                        if w_data.get("ready", False):
                            self.logger.info(
                                f"教室 (コード: {classroom_code}) のカリキュラム一覧描画完了を確認しました (行数: {w_data.get('rowCount')})"
                            )
                            callback(True, "")
                            return

                        if not reason.startswith("検索結果読み込み中") and not reason.startswith("モーダル"):
                            no_spinner_empty_polls += 1
                        else:
                            no_spinner_empty_polls = 0

                        if no_spinner_empty_polls >= 40:
                            # スピナー消滅から10秒経過しても行が0件なら、0件の教室として確定完了へ
                            self.logger.info(
                                f"教室 (コード: {classroom_code}) のデータ読み込み完了を確認しました (対象データ0件)"
                            )
                            callback(True, "")
                        elif wait_attempts >= max_wait:
                            _handle_failure(f"検索結果のロード待機タイムアウト: {reason}")
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
                    QTimer.singleShot(800, _execute_attempt)
                else:
                    self.logger.error("教室切り替えが最大試行回数に達したため失敗と判定します")
                    callback(False, reason)

            # モーダルが既に開いているか確認し、開いていなければ開く (権限確認済みモード)
            def _check_modal_status(m_res):
                m_data = self._parse_json(m_res)
                if m_data.get("active", False):
                    _on_modal_ready()
                else:
                    self.open_class_modal(
                        lambda ok, err: _on_modal_ready() if ok else _handle_failure(err),
                        max_attempts=3,
                        is_patrol_confirmed=True,
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
