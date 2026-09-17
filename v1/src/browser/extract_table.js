(() => {
    try {
        function normalizeText(text) {
            if (!text) return "";
            // NFKC normalization
            let norm = text.normalize("NFKC");
            // Uppercase
            norm = norm.toUpperCase();
            // Remove whitespace (including full width space)
            norm = norm.replace(/\s+/g, "");
            return norm;
        }

        const ALIASES = {
            studentId: ["生徒", "学生", "番号", "学籍番号", "ID"].map(normalizeText),
            division: ["受講区分", "区分"].map(normalizeText),
            subject: ["科目", "教科", "コース"].map(normalizeText),
            instruction: ["備考", "指示書", "指示", "メモ", "ノート"].map(normalizeText),
            grade: ["学年", "学齢", "学年/部活"].map(normalizeText)
        };

        const SELECTORS = window.__CURRICULUM_SELECTORS__ || {
            classroom_name: [
                "/html/body/div/div/div[2]/div/div[1]/div/table/tbody[2]/tr[1]/td[1]/div/div[2]/div/div/div[2]/div/span/span",
                ".search-branch .has-ellipsis",
                ".search-branch .tag",
                ".taginput .has-ellipsis",
                ".taginput .tag"
            ],
            classroom_code: [
                ".branch-code-input input",
                "input[placeholder*='教室コード']"
            ],
            school_year: [
                "select.school-year",
                "select"
            ],
            target_table: [
                "table.curriculum-table",
                "table.instruction-table",
                "table"
            ],
            loading_indicator: [
                ".loading", ".spinner", ".is-loading", ".loading-mask", "[aria-busy='true']"
            ]
        };

        function isVisible(el) {
            if (!el) return false;
            if (el.offsetParent === null) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none') return false;
            if (style.visibility === 'hidden') return false;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return false;
            return true;
        }

        function querySelectorOrXPath(selector, context = document) {
            if (!selector) return null;
            try {
                if (selector.startsWith("/") || selector.startsWith("(") || selector.startsWith("./")) {
                    const res = document.evaluate(selector, context, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    return res ? res.singleNodeValue : null;
                } else {
                    return context.querySelector(selector);
                }
            } catch (e) {
                return null;
            }
        }

        // --- 1. DOM安定判定 (v8 §9) ---
        // 1.1 ローディング中要素の確認
        const loadingCandidates = SELECTORS.loading_indicator || [];
        for (const lSel of loadingCandidates) {
            const el = querySelectorOrXPath(lSel);
            if (el && isVisible(el)) {
                return {
                    success: false,
                    notStable: true,
                    reason: "loading_in_progress",
                    error: "ページを読み込み中です。描画完了後にもう一度読み取ってください。"
                };
            }
        }

        // 1.2 直近の重要DOM変化チェック (初期値500ms)
        if (typeof window.__curriculumLastMutationTime === "undefined") {
            window.__curriculumLastMutationTime = 0;
        }
        if (!window.__curriculumDomObserverInstalled) {
            window.__curriculumDomObserverInstalled = true;
            try {
                const obs = new MutationObserver(() => {
                    window.__curriculumLastMutationTime = Date.now();
                });
                obs.observe(document.body || document.documentElement, {
                    childList: true,
                    subtree: true
                });
            } catch (e) {}
        }
        if (window.__curriculumLastMutationTime > 0) {
            const elapsed = Date.now() - window.__curriculumLastMutationTime;
            if (elapsed < 500) {
                return {
                    success: false,
                    notStable: true,
                    reason: "dom_mutating",
                    error: "ページを読み込み中です。描画完了後にもう一度読み取ってください。"
                };
            }
        }

        function getScore(text, logicalItem) {
            if (!text) return 0;
            const norm = normalizeText(text);
            let score = 0;
            for (const alias of ALIASES[logicalItem]) {
                if (norm === alias) {
                    return 2;
                } else if (norm.includes(alias)) {
                    score = Math.max(score, 1);
                }
            }
            return score;
        }

        function findBestMapping(headers, dataLabels) {
            const items = ['studentId', 'division', 'subject', 'instruction'];
            const n = headers.length;
            if (n < 4) return { score: -1, map: null };

            const colItemScores = [];
            for (let i = 0; i < n; i++) {
                const itemScores = [];
                for (const item of items) {
                    let score = getScore(dataLabels[i], item);
                    if (score === 0) {
                        score = getScore(headers[i], item);
                    }
                    itemScores.push(score);
                }
                colItemScores.push(itemScores);
            }

            let bestScore = -1;
            let bestMap = null;

            for (let c0 = 0; c0 < n; c0++) {
                for (let c1 = 0; c1 < n; c1++) {
                    if (c1 === c0) continue;
                    for (let c2 = 0; c2 < n; c2++) {
                        if (c2 === c0 || c2 === c1) continue;
                        for (let c3 = 0; c3 < n; c3++) {
                            if (c3 === c0 || c3 === c1 || c3 === c2) continue;

                            const s0 = colItemScores[c0][0];
                            const s1 = colItemScores[c1][1];
                            const s2 = colItemScores[c2][2];
                            const s3 = colItemScores[c3][3];

                            if (s0 > 0 && s1 > 0 && s2 > 0 && s3 > 0) {
                                const total = s0 + s1 + s2 + s3;
                                if (total > bestScore) {
                                    bestScore = total;
                                    bestMap = [c0, c1, c2, c3];
                                }
                            }
                        }
                    }
                }
            }

            if (bestScore > 0) {
                const resMap = {
                    studentId: bestMap[0],
                    division: bestMap[1],
                    subject: bestMap[2],
                    instruction: bestMap[3]
                };
                for (let i = 0; i < n; i++) {
                    if (bestMap.includes(i)) continue;
                    let gScore = getScore(dataLabels[i], 'grade');
                    if (gScore === 0) gScore = getScore(headers[i], 'grade');
                    if (gScore > 0) {
                        resMap.grade = i;
                        break;
                    }
                }
                return {
                    score: bestScore,
                    map: resMap
                };
            }
            return { score: -1, map: null };
        }

        // 対象テーブルの探索 (Candidates)
        const tableCandidates = SELECTORS.target_table || ["table"];
        let tables = [];
        for (const tSel of tableCandidates) {
            try {
                if (tSel.startsWith("/") || tSel.startsWith("(")) {
                    const res = document.evaluate(tSel, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    for (let i = 0; i < res.snapshotLength; i++) {
                        const node = res.snapshotItem(i);
                        if (node && !tables.includes(node)) tables.push(node);
                    }
                } else {
                    const found = document.querySelectorAll(tSel);
                    for (const t of found) {
                        if (!tables.includes(t)) tables.push(t);
                    }
                }
            } catch (e) {}
        }
        if (tables.length === 0) {
            tables = Array.from(document.querySelectorAll('table'));
        }

        let bestTableData = null;
        let maxTableScore = -1;

        for (const table of tables) {
            if (!isVisible(table)) continue;

            let theadRows = Array.from(table.querySelectorAll('thead > tr'));
            if (theadRows.length === 0) {
                const firstTr = table.querySelector('tr');
                if (firstTr) {
                    theadRows = [firstTr];
                }
            }

            let bestHeaderScore = -1;
            let bestHeaderData = null;

            for (const tr of theadRows) {
                const cells = Array.from(tr.children).filter(c => c.tagName === 'TH' || c.tagName === 'TD');
                if (cells.length < 4) continue;
                
                const headers = cells.map(c => c.innerText);
                
                let firstDataRow = Array.from(table.querySelectorAll('tbody > tr')).find(r => r !== tr);
                if (!firstDataRow) {
                    firstDataRow = Array.from(table.querySelectorAll('tr')).find(r => r !== tr);
                }

                let dataLabels = new Array(headers.length).fill("");
                if (firstDataRow) {
                    const dataCells = Array.from(firstDataRow.children).filter(c => c.tagName === 'TH' || c.tagName === 'TD');
                    for (let i = 0; i < Math.min(headers.length, dataCells.length); i++) {
                        dataLabels[i] = dataCells[i].getAttribute('data-label') || "";
                    }
                }

                const mappingResult = findBestMapping(headers, dataLabels);
                if (mappingResult.score > bestHeaderScore) {
                    bestHeaderScore = mappingResult.score;
                    bestHeaderData = {
                        headers: headers,
                        map: mappingResult.map,
                        tr: tr,
                        score: mappingResult.score
                    };
                }
            }

            if (bestHeaderData && bestHeaderData.score > maxTableScore) {
                maxTableScore = bestHeaderData.score;
                bestTableData = {
                    table: table,
                    headerRow: bestHeaderData.tr,
                    headers: bestHeaderData.headers,
                    map: bestHeaderData.map
                };
            }
        }

        let hasNext = false;
        const nextCandidates = document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"]');
        const nextTexts = ["次へ", "次", "NEXT", "次ページ", "＞", ">", "▶"];
        
        for (const el of nextCandidates) {
            if (el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled')) continue;
            const style = window.getComputedStyle(el);
            if (style.pointerEvents === 'none') continue;
            if (!isVisible(el)) continue;

            const text = el.innerText ? el.innerText.toUpperCase() : (el.value ? el.value.toUpperCase() : "");
            if (nextTexts.some(nt => text.includes(nt.toUpperCase()))) {
                hasNext = true;
                break;
            }
        }

        function extractClassroomInfo() {
            let schoolYear = "";
            let classroomCode = "";
            let classroomName = "";
            let matchedSelectors = {};

            // 1. 教室名 (Candidates)
            const nameCandidates = SELECTORS.classroom_name || [];
            for (const sel of nameCandidates) {
                const el = querySelectorOrXPath(sel);
                if (el) {
                    const clone = el.cloneNode(true);
                    const del = clone.querySelector('.delete, button');
                    if (del) del.remove();
                    const text = (clone.innerText || clone.textContent || "").trim();
                    if (text) {
                        classroomName = text;
                        matchedSelectors.classroomName = sel;
                        break;
                    } else if (el.getAttribute('title')) {
                        classroomName = el.getAttribute('title').trim();
                        matchedSelectors.classroomName = sel;
                        break;
                    }
                }
            }

            // 2. 教室コード (Candidates)
            const codeCandidates = SELECTORS.classroom_code || [];
            for (const sel of codeCandidates) {
                const el = querySelectorOrXPath(sel);
                if (el) {
                    const val = (el.value || el.innerText || el.textContent || "").trim();
                    if (val) {
                        classroomCode = val;
                        matchedSelectors.classroomCode = sel;
                        break;
                    }
                }
            }

            // 3. 年度 (Candidates)
            const yearCandidates = SELECTORS.school_year || [];
            for (const sel of yearCandidates) {
                const el = querySelectorOrXPath(sel);
                if (el) {
                    if (el.tagName === 'SELECT' && el.selectedOptions && el.selectedOptions.length > 0) {
                        const val = el.selectedOptions[0].innerText.trim();
                        if (val) {
                            schoolYear = val;
                            matchedSelectors.schoolYear = sel;
                            break;
                        }
                    } else {
                        const val = (el.innerText || el.value || "").trim();
                        if (/\d{4}年/.test(val)) {
                            schoolYear = val;
                            matchedSelectors.schoolYear = sel;
                            break;
                        }
                    }
                }
            }

            // フォールバック: ヘッダーラベル領域探索
            if (!classroomName || !classroomCode || !schoolYear) {
                try {
                    const allLabels = Array.from(document.querySelectorAll('th, td.label, label, div.label, span.label'));
                    const yearClassTh = allLabels.find(el => {
                        const t = (el.innerText || "").replace(/\s+/g, "");
                        return t.includes("年度/教室") || t.includes("年度・教室") || (t.includes("年度") && t.includes("教室"));
                    });
                    const searchScope = yearClassTh ? (yearClassTh.closest('tr') || yearClassTh.parentElement) : document;

                    if (!schoolYear) {
                        const yearSelect = searchScope.querySelector('select');
                        if (yearSelect && yearSelect.selectedOptions && yearSelect.selectedOptions.length > 0) {
                            schoolYear = yearSelect.selectedOptions[0].innerText.trim();
                            matchedSelectors.schoolYear = "fallback_searchScope_select";
                        }
                    }
                    if (!classroomCode) {
                        const codeInput = searchScope.querySelector('.branch-code-input input, input[placeholder*="教室コード"]');
                        if (codeInput && codeInput.value) {
                            classroomCode = codeInput.value.trim();
                            matchedSelectors.classroomCode = "fallback_searchScope_codeInput";
                        }
                    }
                    if (!classroomName) {
                        const tagEl = searchScope.querySelector('.search-branch .has-ellipsis, .search-branch .tag, .taginput .has-ellipsis, .taginput .tag');
                        if (tagEl) {
                            const clone = tagEl.cloneNode(true);
                            const del = clone.querySelector('.delete, button');
                            if (del) del.remove();
                            classroomName = (clone.innerText || "").trim();
                            matchedSelectors.classroomName = "fallback_searchScope_tag";
                        }
                    }
                } catch (e) {}
            }

            return {
                schoolYear: schoolYear,
                classroomCode: classroomCode,
                classroomName: classroomName,
                matchedSelectors: matchedSelectors
            };
        }

        const classroomInfo = extractClassroomInfo();

        if (!bestTableData) {
            return {
                success: false,
                notStable: true,
                reason: "table_not_found",
                error: "対象テーブルが見つかりませんでした。ページ描画が完了しているか確認してください。",
                headers: [],
                rows: [],
                columnMap: {},
                hasNext: hasNext,
                classroomInfo: {
                    schoolYear: classroomInfo.schoolYear,
                    classroomCode: classroomInfo.classroomCode,
                    classroomName: classroomInfo.classroomName
                },
                schoolYear: classroomInfo.schoolYear,
                classroomCode: classroomInfo.classroomCode,
                classroomName: classroomInfo.classroomName,
                matchedSelectors: classroomInfo.matchedSelectors
            };
        }

        const rows = [];
        const trs = bestTableData.table.querySelectorAll('tr');
        for (const tr of trs) {
            if (tr === bestTableData.headerRow) continue;
            if (tr.closest('table') !== bestTableData.table) continue;

            const cells = Array.from(tr.children).filter(c => c.tagName === 'TH' || c.tagName === 'TD');
            if (cells.length === 0) continue;

            const hasSpan = cells.some(c => c.rowSpan >= 2 || c.colSpan >= 2);
            if (hasSpan) continue;

            const rowData = cells.map(c => {
                const inputEl = c.querySelector('input, textarea');
                if (inputEl) {
                    return (inputEl.value || "").trim();
                }
                return c.innerText;
            });
            rows.push(rowData);
        }

        return {
            success: true,
            error: null,
            headers: bestTableData.headers,
            rows: rows,
            columnMap: bestTableData.map,
            hasNext: hasNext,
            classroomInfo: {
                schoolYear: classroomInfo.schoolYear,
                classroomCode: classroomInfo.classroomCode,
                classroomName: classroomInfo.classroomName
            },
            schoolYear: classroomInfo.schoolYear,
            classroomCode: classroomInfo.classroomCode,
            classroomName: classroomInfo.classroomName,
            matchedSelectors: classroomInfo.matchedSelectors
        };

    } catch (e) {
        return {
            success: false,
            error: e.message,
            headers: [],
            rows: [],
            columnMap: {},
            hasNext: false,
            classroomInfo: {
                schoolYear: "",
                classroomCode: "",
                classroomName: ""
            },
            schoolYear: "",
            classroomCode: "",
            classroomName: "",
            matchedSelectors: {}
        };
    }
})();
