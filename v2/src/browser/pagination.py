"""
カリキュラム一覧ページの自動ページネーション制御モジュール
"""
import json

CHECK_NEXT_PAGE_JS = """
JSON.stringify((function() {
    function isVisible(el) {
        if (!el) return false;
        var style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        if (style.pointerEvents === 'none') return false;
        var rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function isDisabled(el) {
        if (!el) return true;
        if (el.disabled) return true;
        if (el.getAttribute('aria-disabled') === 'true') return true;
        var cls = (el.className || '').toString().toLowerCase();
        if (cls.indexOf('disabled') !== -1 || cls.indexOf('is-disabled') !== -1) return true;
        var parent = el.closest('.disabled, .is-disabled, [aria-disabled="true"], li.disabled');
        if (parent) return true;
        return false;
    }

    // 1. 一般的な次ページセレクタを優先探索
    var selectors = [
        ".pagination .btn-next",
        "button.btn-next",
        "a.btn-next",
        ".btn-next",
        ".pagination li:not(.disabled) a[rel='next']",
        "a[rel='next']",
        ".pagination a.next",
        ".pagination button.next",
        ".pagination li.next a",
        "button.pagination-next",
        "a.pagination-next",
        ".pagination-next:not(.is-disabled):not([disabled])",
        "li.page-item.next:not(.disabled) a",
        "li.page-item.next:not(.disabled) button"
    ];

    for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el && isVisible(el) && !isDisabled(el)) {
            return { hasNext: true, selector: selectors[i] };
        }
    }

    // 2. 「次へ」「次ページ」などのテキストを持つ操作可能要素を走査
    var candidates = document.querySelectorAll("a, button, input[type='button'], input[type='submit'], [role='button'], .page-link");
    var nextKeywords = ["次へ", "次ページ", "次頁", "NEXT", "次 >", "次へ >", "次へ »", ">", "＞", "▶", "→", "»", "›"];

    for (var j = 0; j < candidates.length; j++) {
        var c = candidates[j];
        if (!isVisible(c) || isDisabled(c)) continue;
        var txt = (c.innerText || c.textContent || c.value || "").trim().toUpperCase();
        // 前へ、戻る等は除外
        if (txt.indexOf("前") !== -1 || txt.indexOf("PREV") !== -1 || txt.indexOf("戻る") !== -1 || txt.indexOf("最初") !== -1) continue;

        for (var k = 0; k < nextKeywords.length; k++) {
            var kw = nextKeywords[k].toUpperCase();
            if (txt === kw || txt === (" " + kw) || txt.indexOf(kw) === 0 || txt.endsWith(kw)) {
                return { hasNext: true, text: txt };
            }
        }
    }

    // 3. ページ番号リンク（現在のアクティブページ番号+1）
    var activePageEl = document.querySelector(".pagination .active, .pagination .is-current, .pagination .current, [aria-current='page']");
    if (activePageEl) {
        var currentNum = parseInt((activePageEl.innerText || activePageEl.textContent || "").trim(), 10);
        if (!isNaN(currentNum)) {
            var nextNumStr = (currentNum + 1).toString();
            var pageLinks = document.querySelectorAll(".pagination a, .pagination button, .page-link");
            for (var p = 0; p < pageLinks.length; p++) {
                var pLink = pageLinks[p];
                if ((pLink.innerText || pLink.textContent || "").trim() === nextNumStr && isVisible(pLink) && !isDisabled(pLink)) {
                    return { hasNext: true, nextPageNum: currentNum + 1 };
                }
            }
        }
    }

    return { hasNext: false };
})());
"""

CLICK_NEXT_PAGE_JS = """
JSON.stringify((function() {
    function isVisible(el) {
        if (!el) return false;
        var style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        if (style.pointerEvents === 'none') return false;
        var rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function isDisabled(el) {
        if (!el) return true;
        if (el.disabled) return true;
        if (el.getAttribute('aria-disabled') === 'true') return true;
        var cls = (el.className || '').toString().toLowerCase();
        if (cls.indexOf('disabled') !== -1 || cls.indexOf('is-disabled') !== -1) return true;
        var parent = el.closest('.disabled, .is-disabled, [aria-disabled="true"], li.disabled');
        if (parent) return true;
        return false;
    }

    var targetEl = null;
    var selectors = [
        ".pagination .btn-next",
        "button.btn-next",
        "a.btn-next",
        ".btn-next",
        ".pagination li:not(.disabled) a[rel='next']",
        "a[rel='next']",
        ".pagination a.next",
        ".pagination button.next",
        ".pagination li.next a",
        "button.pagination-next",
        "a.pagination-next",
        ".pagination-next:not(.is-disabled):not([disabled])",
        "li.page-item.next:not(.disabled) a",
        "li.page-item.next:not(.disabled) button"
    ];

    for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el && isVisible(el) && !isDisabled(el)) {
            targetEl = el;
            break;
        }
    }

    if (!targetEl) {
        var candidates = document.querySelectorAll("a, button, input[type='button'], input[type='submit'], [role='button'], .page-link");
        var nextKeywords = ["次へ", "次ページ", "次頁", "NEXT", "次 >", "次へ >", "次へ »", ">", "＞", "▶", "→", "»", "›"];
        for (var j = 0; j < candidates.length; j++) {
            var c = candidates[j];
            if (!isVisible(c) || isDisabled(c)) continue;
            var txt = (c.innerText || c.textContent || c.value || "").trim().toUpperCase();
            if (txt.indexOf("前") !== -1 || txt.indexOf("PREV") !== -1 || txt.indexOf("戻る") !== -1 || txt.indexOf("最初") !== -1) continue;
            for (var k = 0; k < nextKeywords.length; k++) {
                var kw = nextKeywords[k].toUpperCase();
                if (txt === kw || txt === (" " + kw) || txt.indexOf(kw) === 0 || txt.endsWith(kw)) {
                    targetEl = c;
                    break;
                }
            }
            if (targetEl) break;
        }
    }

    if (!targetEl) {
        var activePageEl = document.querySelector(".pagination .active, .pagination .is-current, .pagination .current, [aria-current='page']");
        if (activePageEl) {
            var currentNum = parseInt((activePageEl.innerText || activePageEl.textContent || "").trim(), 10);
            if (!isNaN(currentNum)) {
                var nextNumStr = (currentNum + 1).toString();
                var pageLinks = document.querySelectorAll(".pagination a, .pagination button, .page-link");
                for (var p = 0; p < pageLinks.length; p++) {
                    var pLink = pageLinks[p];
                    if ((pLink.innerText || pLink.textContent || "").trim() === nextNumStr && isVisible(pLink) && !isDisabled(pLink)) {
                        targetEl = pLink;
                        break;
                    }
                }
            }
        }
    }

    if (!targetEl) {
        return { success: false, reason: "次へボタンが見つかりません" };
    }

    // クリック前のテーブル署名取得
    var tbody = document.querySelector("table tbody") || document.querySelector("table");
    var signature = tbody ? (tbody.innerText || "").trim().substring(0, 100) : "";

    if (targetEl.scrollIntoView) {
        targetEl.scrollIntoView({ behavior: 'instant', block: 'center' });
    }
    targetEl.click();
    targetEl.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));

    return { success: true, prevSignature: signature };
})());
"""

def get_check_page_changed_js(prev_signature: str) -> str:
    """ページ遷移・更新の確認スクリプト (直前署名と比較)"""
    escaped_sig = json.dumps(prev_signature or "")
    return f"""
    JSON.stringify((function() {{
        var loadingSelectors = [
            ".loading", ".spinner", ".is-loading", ".loading-mask", "[aria-busy='true']"
        ];
        var isLoading = false;
        for (var i = 0; i < loadingSelectors.length; i++) {{
            var el = document.querySelector(loadingSelectors[i]);
            if (el) {{
                var style = window.getComputedStyle(el);
                if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {{
                    isLoading = true;
                    break;
                }}
            }}
        }}

        var tbody = document.querySelector("table tbody") || document.querySelector("table");
        var currentSig = tbody ? (tbody.innerText || "").trim().substring(0, 100) : "";
        var prevSig = {escaped_sig};
        var changed = (currentSig !== "" && currentSig !== prevSig);

        return {{
            changed: changed,
            isLoading: isLoading,
            currentSignature: currentSig
        }};
    }})());
    """

