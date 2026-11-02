/**
 * script.js - Curriculum Analyzer
 * ドキュメントポータル & バージョン別マニュアル共通スクリプト
 * 
 * - Releases 共通 Prefix（/releases/）の自動挿入
 * - ver/ver.json の非同期取得とリンク自動バインド
 * - ポータル画面でのカード情報同期（Hydration）
 * - マニュアル画面での Version Switcher 制御 & ダウンロードリンク自動反映
 * - ページ内スムーススクロール & アクセシビリティ対応
 * - ダークモード / ライトモード管理（OS設定自動追従 + 手動トグル + localStorage）
 * - 上部読書プログレスバー & Scroll Spy（目次追従ハイライト）
 * - ページ内クイック検索（セクションフィルタリング + ショートカットキー /）
 * - コードブロックのワンクリックコピーボタン
 * - トップへ戻るフローティングボタン
 */

(function () {
    'use strict';

    // デフォルトリポジトリURL（フォールバック用）
    const DEFAULT_REPO = 'https://github.com/sam-hat-86/Curriculum_Analyzer';

    // パス判定（マニュアル画面 ver/*.html か ポータル画面 index.html か）
    const isManualPage = window.location.pathname.includes('/ver/') || 
                         window.location.href.includes('/ver/');
    const jsonPath = isManualPage ? './ver.json' : './ver/ver.json';

    // DOMContentLoaded 時の初期化
    document.addEventListener('DOMContentLoaded', function () {
        // (1) テーマ管理の初期化
        initTheme();

        // (2) 初期状態で data-release-path 属性に Prefix を即時補完（ローカルフォールバック保護）
        applyReleasePrefix(DEFAULT_REPO);

        // (3) ページ内スムーススクロール初期化
        initSmoothScroll();

        // (4) 読書進捗バー & Scroll Spy
        initScrollSpyAndProgress();

        // (5) コードブロックのコピー機能
        initCodeCopy();

        // (6) トップへ戻るボタン
        initBackToTop();

        // (7) マニュアルページの場合：ページ内クイック検索
        if (isManualPage) {
            initDocSearch();
        }

        // (8) ver.json の読み込みと動的バインド
        loadVersionData();
    });

    /**
     * テーマ管理（OS連動 + 手動切替 + localStorage保持）
     */
    function initTheme() {
        const THEME_STORAGE_KEY = 'ca-docs-theme';
        const html = document.documentElement;
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

        function getPreferredTheme() {
            const saved = localStorage.getItem(THEME_STORAGE_KEY);
            if (saved === 'light' || saved === 'dark') {
                return saved;
            }
            return mediaQuery.matches ? 'dark' : 'light';
        }

        function applyTheme(theme) {
            html.setAttribute('data-theme', theme);
            updateToggleButtons(theme);
        }

        function updateToggleButtons(theme) {
            const btns = document.querySelectorAll('.theme-toggle-btn');
            btns.forEach(function (btn) {
                if (theme === 'dark') {
                    btn.innerHTML = '🌙';
                    btn.setAttribute('title', 'ライトモードに切り替え');
                    btn.setAttribute('aria-label', 'ライトモードに切り替え');
                } else {
                    btn.innerHTML = '☀️';
                    btn.setAttribute('title', 'ダークモードに切り替え');
                    btn.setAttribute('aria-label', 'ダークモードに切り替え');
                }
            });
        }

        // 初期適用
        const currentTheme = getPreferredTheme();
        applyTheme(currentTheme);

        // OS/ブラウザ設定変更の監視（手動設定がない場合のみ自動追従）
        mediaQuery.addEventListener('change', function (e) {
            const saved = localStorage.getItem(THEME_STORAGE_KEY);
            if (!saved) {
                applyTheme(e.matches ? 'dark' : 'light');
            }
        });

        // ボタンクリックイベントの設定
        document.addEventListener('click', function (e) {
            const btn = e.target.closest('.theme-toggle-btn');
            if (!btn) return;
            e.preventDefault();

            const cur = html.getAttribute('data-theme') || (mediaQuery.matches ? 'dark' : 'light');
            const nextTheme = cur === 'dark' ? 'light' : 'dark';

            localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
            applyTheme(nextTheme);
        });
    }

    /**
     * 上部読書プログレスバー & Scroll Spy (目次自動アクティブ化)
     */
    function initScrollSpyAndProgress() {
        let progressBar = document.querySelector('.reading-progress-bar');
        if (!progressBar) {
            progressBar = document.createElement('div');
            progressBar.className = 'reading-progress-bar';
            document.body.prepend(progressBar);
        }

        const sections = document.querySelectorAll('article section[id]');
        const tocLinks = document.querySelectorAll('.note-toc .toc a[href^="#"]');

        function updateProgress() {
            const scrollTop = window.scrollY || document.documentElement.scrollTop;
            const docHeight = document.documentElement.scrollHeight - window.innerHeight;
            const progress = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
            progressBar.style.width = Math.min(100, Math.max(0, progress)) + '%';

            // Scroll Spy
            if (sections.length > 0 && tocLinks.length > 0) {
                let activeId = '';
                const scrollPos = scrollTop + 160;

                sections.forEach(function (sec) {
                    if (sec.offsetTop <= scrollPos) {
                        activeId = sec.getAttribute('id');
                    }
                });

                if (activeId) {
                    tocLinks.forEach(function (link) {
                        const href = link.getAttribute('href');
                        if (href === '#' + activeId) {
                            link.classList.add('active');
                            // 親サブメニューの場合は親リンクもアクティブ維持
                            const parentSub = link.closest('.toc-sub');
                            if (parentSub) {
                                const parentLi = parentSub.closest('li');
                                const parentLink = parentLi ? parentLi.querySelector('a') : null;
                                if (parentLink && parentLink !== link) {
                                    parentLink.classList.add('active');
                                }
                            }
                        } else {
                            link.classList.remove('active');
                        }
                    });
                }
            }
        }

        window.addEventListener('scroll', updateProgress, { passive: true });
        updateProgress();
    }

    /**
     * ページ内クイック検索
     */
    function initDocSearch() {
        const searchInput = document.getElementById('doc-search');
        const statusEl = document.getElementById('doc-search-status');
        const sections = document.querySelectorAll('article section');
        if (!searchInput) return;

        // キーボードショートカット "/" で検索フォーカス、Escで解除
        document.addEventListener('keydown', function (e) {
            if (e.key === '/' && document.activeElement !== searchInput && 
                !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
            } else if (e.key === 'Escape' && document.activeElement === searchInput) {
                searchInput.value = '';
                filterSections('');
                searchInput.blur();
            }
        });

        searchInput.addEventListener('input', function () {
            filterSections(this.value.trim().toLowerCase());
        });

        function filterSections(query) {
            let matchedCount = 0;

            sections.forEach(function (sec) {
                if (!query) {
                    sec.classList.remove('search-hidden');
                    matchedCount++;
                    return;
                }

                const text = sec.textContent.toLowerCase();
                if (text.includes(query)) {
                    sec.classList.remove('search-hidden');
                    matchedCount++;
                } else {
                    sec.classList.add('search-hidden');
                }
            });

            if (statusEl) {
                if (!query) {
                    statusEl.classList.remove('visible');
                    statusEl.textContent = '';
                } else {
                    statusEl.classList.add('visible');
                    statusEl.textContent = `${matchedCount} 件のセクションが一致`;
                }
            }
        }
    }

    /**
     * コードブロックのコピー機能
     */
    function initCodeCopy() {
        const preElements = document.querySelectorAll('pre');
        preElements.forEach(function (pre) {
            if (pre.parentNode && pre.parentNode.classList.contains('pre-wrapper')) {
                return;
            }

            const wrapper = document.createElement('div');
            wrapper.className = 'pre-wrapper';
            pre.parentNode.insertBefore(wrapper, pre);
            wrapper.appendChild(pre);

            const copyBtn = document.createElement('button');
            copyBtn.type = 'button';
            copyBtn.className = 'code-copy-btn';
            copyBtn.innerHTML = '📋 コピー';
            copyBtn.setAttribute('aria-label', 'コードをクリップボードにコピー');

            copyBtn.addEventListener('click', function () {
                const code = pre.querySelector('code');
                const text = code ? code.innerText : pre.innerText;

                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).then(function () {
                        copyBtn.classList.add('copied');
                        copyBtn.innerHTML = '✓ コピー完了';
                        setTimeout(function () {
                            copyBtn.classList.remove('copied');
                            copyBtn.innerHTML = '📋 コピー';
                        }, 2000);
                    }).catch(function (err) {
                        console.warn('Clipboard write failed:', err);
                    });
                }
            });

            wrapper.appendChild(copyBtn);
        });
    }

    /**
     * トップへ戻るボタン
     */
    function initBackToTop() {
        let btn = document.querySelector('.back-to-top');
        if (!btn) {
            btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'back-to-top';
            btn.innerHTML = '↑';
            btn.setAttribute('title', 'ページの先頭へ戻る');
            btn.setAttribute('aria-label', 'ページの先頭へ戻る');
            document.body.appendChild(btn);
        }

        window.addEventListener('scroll', function () {
            if (window.scrollY > 350) {
                btn.classList.add('visible');
            } else {
                btn.classList.remove('visible');
            }
        }, { passive: true });

        btn.addEventListener('click', function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    /**
     * Releases の共通 Prefix を生成
     */
    function getReleasesPrefix(repoUrl) {
        const repo = (repoUrl || DEFAULT_REPO).replace(/\/+$/, '');
        return `${repo}/releases/`;
    }

    /**
     * data-release-path 属性を持つ全要素の href に Prefix を補完
     */
    function applyReleasePrefix(repoUrl) {
        const prefix = getReleasesPrefix(repoUrl);
        document.querySelectorAll('[data-release-path]').forEach(function (el) {
            const relPath = el.getAttribute('data-release-path') || '';
            el.href = prefix + relPath;
        });
    }

    /**
     * ページ内アンカーのスムーススクロール
     */
    function initSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(function (link) {
            link.addEventListener('click', function (e) {
                const href = this.getAttribute('href');
                if (!href || href === '#') return;
                const target = document.getElementById(href.slice(1));
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    target.setAttribute('tabindex', '-1');
                    target.focus({ preventScroll: true });
                    if (window.history && window.history.pushState) {
                        window.history.pushState(null, '', href);
                    }
                }
            });
        });
    }

    /**
     * ver.json を fetch して各画面にバインド
     */
    function loadVersionData() {
        fetch(jsonPath)
            .then(function (res) {
                if (!res.ok) throw new Error(`HTTP ${res.status} for ${jsonPath}`);
                return res.json();
            })
            .then(function (data) {
                // リポジトリ URL が指定されている場合は最新 Prefix で再適用
                if (data.repo) {
                    applyReleasePrefix(data.repo);
                }

                if (isManualPage) {
                    applyManualPageData(data);
                } else {
                    applyPortalPageData(data);
                }
            })
            .catch(function (err) {
                // file:// やオフライン時は静的フォールバックがそのまま動作
                console.info('Static fallback in use:', err.message);
                setupDropdownFallback();
            });
    }

    /**
     * ポータル画面 (docs/index.html) のデータ反映
     */
    function applyPortalPageData(data) {
        const prefix = getReleasesPrefix(data.repo);

        // (1) ヒーローの最新版ダウンロードボタン
        const latestDlBtn = document.querySelector('[data-bind="latest-download-btn"]');
        if (latestDlBtn && data.latestTag && data.latestFile) {
            latestDlBtn.href = `${prefix}download/${data.latestTag}/${data.latestFile}`;
            latestDlBtn.setAttribute('download', data.latestFile);
            const label = document.querySelector('[data-bind="latest-download-text"]');
            if (label) {
                label.textContent = `${data.latestFile} を直接ダウンロード`;
            }
        }

        // (2) ヒーローの最新版マニュアルボタン
        const latestManualBtn = document.querySelector('[data-bind="latest-manual-btn"]');
        if (latestManualBtn && data.latest) {
            const latestVerObj = Array.isArray(data.versions)
                ? data.versions.find(function (v) { return v.version === data.latest; })
                : null;
            const manualFile = (latestVerObj && latestVerObj.file) ? latestVerObj.file : `${data.latest}.html`;
            latestManualBtn.href = `./ver/${manualFile}`;
            latestManualBtn.textContent = `📖 最新版 (v${data.latest}) マニュアルを読む`;
        }

        // (3) バージョンカードの更新（既存要素の Hydrate ＋ 未定義バージョンの追加）
        const grid = document.getElementById('version-card-grid');
        if (!grid || !Array.isArray(data.versions)) return;

        data.versions.forEach(function (v) {
            let card = grid.querySelector(`[data-version="${v.version}"]`);
            const isLatest = v.version === data.latest;
            const manualUrl = `./ver/${v.file || (v.version + '.html')}`;
            const dlUrl = (v.tag && v.downloadFile) 
                ? `${prefix}download/${v.tag}/${v.downloadFile}` 
                : '#';
            const dlFilename = v.downloadFile || '';
            const relUrl = v.tag ? `${prefix}tag/${v.tag}` : prefix.replace(/\/$/, '');

            if (card) {
                // 既存カードの更新
                card.className = `version-card ${isLatest ? 'card-latest' : 'card-legacy'}`;
                const titleEl = card.querySelector('[data-field="title"]');
                if (titleEl && v.title) titleEl.textContent = v.title;

                const badgeEl = card.querySelector('[data-field="badge"]');
                if (badgeEl && v.badge) {
                    badgeEl.textContent = v.badge;
                    badgeEl.className = `card-badge ${v.badgeClass || ''}`;
                }

                const releaseEl = card.querySelector('[data-field="release"]');
                if (releaseEl && v.releaseDate) releaseEl.textContent = `リリース: ${v.releaseDate}`;

                const descEl = card.querySelector('[data-field="desc"]');
                if (descEl && v.description) descEl.textContent = v.description;

                const manualEl = card.querySelector('[data-field="manual"]');
                if (manualEl) {
                    manualEl.href = manualUrl;
                    manualEl.className = `btn-card btn-manual ${isLatest ? 'btn-primary' : 'btn-secondary'}`;
                }

                const dlEl = card.querySelector('[data-field="download"]');
                if (dlEl && dlUrl !== '#') {
                    dlEl.href = dlUrl;
                    dlEl.setAttribute('download', dlFilename);
                    dlEl.textContent = `📦 ZIP をダウンロード (${v.tag || ('v' + v.version)})`;
                }

                const relEl = card.querySelector('[data-field="releaseNotes"]');
                if (relEl) relEl.href = relUrl;
            } else {
                // 新規バージョンのカードを追加
                const newCard = document.createElement('div');
                newCard.className = `version-card ${isLatest ? 'card-latest' : 'card-legacy'}`;
                newCard.setAttribute('data-version', v.version);
                newCard.innerHTML = `
                    <div class="card-header">
                        <div class="card-title-wrap">
                            <h3 class="card-title">${escapeHtml(v.title || ('Version ' + v.version))}</h3>
                            <span class="card-badge ${escapeHtml(v.badgeClass || '')}">${escapeHtml(v.badge || '')}</span>
                        </div>
                        <span class="card-release-date">リリース: ${escapeHtml(v.releaseDate || '')}</span>
                    </div>
                    <p class="card-desc">${escapeHtml(v.description || '')}</p>
                    <div class="card-actions">
                        <a href="${manualUrl}" class="btn-card btn-manual ${isLatest ? 'btn-primary' : 'btn-secondary'}">
                            📖 操作マニュアルを読む
                        </a>
                        ${dlUrl !== '#' ? `
                        <a href="${dlUrl}" class="btn-card btn-download" download="${escapeHtml(dlFilename)}">
                            📦 ZIP をダウンロード (${escapeHtml(v.tag || ('v' + v.version))})
                        </a>` : ''}
                        <a href="${relUrl}" target="_blank" rel="noopener noreferrer" class="link-release-notes">
                            リリースノートを見る ↗
                        </a>
                    </div>`;
                grid.appendChild(newCard);
            }
        });
    }

    /**
     * マニュアル画面 (docs/ver/*.html) のデータ反映
     */
    function applyManualPageData(data) {
        const prefix = getReleasesPrefix(data.repo);
        const switcherBox = document.querySelector('.version-switcher-box');
        let currentVer = switcherBox?.getAttribute('data-current-ver') || '';
        if (!currentVer) {
            const m = window.location.pathname.match(/\/(\d+\.\d+)\.html/);
            if (m) currentVer = m[1];
        }

        // (0) 旧版マニュアル案内バナー (archive-banner) の自動生成・制御
        const isLatest = (currentVer === data.latest);
        let archiveBanner = document.querySelector('.archive-banner');

        if (isLatest) {
            if (archiveBanner) {
                archiveBanner.remove();
            }
        } else if (data.latest) {
            const latestVerObj = Array.isArray(data.versions)
                ? data.versions.find(function (v) { return v.version === data.latest; })
                : null;
            const latestFile = (latestVerObj && latestVerObj.file) ? latestVerObj.file : `${data.latest}.html`;
            const latestTitle = (latestVerObj && latestVerObj.title) ? latestVerObj.title : `v${data.latest}`;
            const latestUrl = `./${latestFile}`;

            const bannerHtml = `⚠️ これは <strong>旧バージョン (v${escapeHtml(currentVer)})</strong> のマニュアルです。最新機能を利用できる現行マニュアルは <a href="${escapeHtml(latestUrl)}" class="banner-link">👉 こちら (${escapeHtml(latestTitle)})</a> をご覧ください。`;

            if (archiveBanner) {
                archiveBanner.innerHTML = bannerHtml;
                archiveBanner.style.display = '';
            } else {
                archiveBanner = document.createElement('div');
                archiveBanner.className = 'archive-banner';
                archiveBanner.innerHTML = bannerHtml;
                document.body.prepend(archiveBanner);
            }
        }

        // (0.5) メタバーのバージョンチップ自動更新
        const chip = document.querySelector('.doc-meta-chips .doc-chip:first-child');
        if (chip && currentVer) {
            chip.textContent = isLatest ? `最新バージョン: v${currentVer}` : `バージョン: v${currentVer} (旧版)`;
        }

        // (1) ドロップダウンを ver.json で最新化
        const dropdown = document.getElementById('ver-select');
        if (dropdown && Array.isArray(data.versions)) {
            dropdown.innerHTML = '';
            data.versions.forEach(function (v) {
                const opt = document.createElement('option');
                opt.value = `./${v.file || (v.version + '.html')}`;
                opt.textContent = `${v.title} [${v.badge || ''}]`;
                if (v.version === currentVer) opt.selected = true;
                dropdown.appendChild(opt);
            });
            const topOpt = document.createElement('option');
            topOpt.value = '../';
            topOpt.textContent = '🏠 ポータルトップへ';
            dropdown.appendChild(topOpt);

            dropdown.onchange = function () {
                window.location.href = this.value;
            };
        }

        // (2) サイドバーおよびヒーローのダウンロードボタンを、このバージョンに対応する URL にバインド
        if (Array.isArray(data.versions)) {
            const verInfo = data.versions.find(function (v) { return v.version === currentVer; });
            if (verInfo && verInfo.tag && verInfo.downloadFile) {
                const dlUrl = `${prefix}download/${verInfo.tag}/${verInfo.downloadFile}`;
                const dlBtn = document.querySelector('.toc-download-button');
                if (dlBtn) {
                    dlBtn.href = dlUrl;
                    dlBtn.setAttribute('download', verInfo.downloadFile);
                    dlBtn.innerHTML = `ZIP を<br>直接ダウンロード<span style="font-size:0.75rem; display:block; opacity:0.9;">(${verInfo.tag})</span>`;
                }
                const heroDlBtn = document.querySelector('.download-hero');
                if (heroDlBtn) {
                    heroDlBtn.href = dlUrl;
                    heroDlBtn.setAttribute('download', verInfo.downloadFile);
                    const heroText = heroDlBtn.querySelector('[data-link-text]');
                    if (heroText) {
                        heroText.textContent = `${verInfo.downloadFile} をダウンロード`;
                    }
                }
            }
        }
    }

    /**
     * 静的フォールバック用ドロップダウンイベント
     */
    function setupDropdownFallback() {
        const dropdown = document.getElementById('ver-select');
        if (dropdown) {
            dropdown.onchange = function () {
                window.location.href = this.value;
            };
        }
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
})();
