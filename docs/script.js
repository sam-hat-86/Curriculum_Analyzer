/**
 * script.js - Curriculum Analyzer
 * ドキュメントポータル & バージョン別マニュアル共通スクリプト
 * 
 * - Releases 共通 Prefix（/releases/）の自動挿入
 * - ver/ver.json の非同期取得とリンク自動バインド
 * - ポータル画面でのカード情報同期（Hydration）
 * - マニュアル画面での Version Switcher 制御 & ダウンロードリンク自動反映
 * - ページ内スムーススクロール & アクセシビリティ対応
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
        // (1) 初期状態で data-release-path 属性に Prefix を即時補完（ローカルフォールバック保護）
        applyReleasePrefix(DEFAULT_REPO);

        // (2) ページ内スムーススクロール初期化
        initSmoothScroll();

        // (3) ver.json の読み込みと動的バインド
        loadVersionData();
    });

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
            latestManualBtn.href = `./ver/${data.latest}.html`;
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

        // (2) サイドバーのダウンロードボタンを、このバージョンに対応する URL にバインド
        const dlBtn = document.querySelector('.toc-download-button');
        if (dlBtn && Array.isArray(data.versions)) {
            const verInfo = data.versions.find(function (v) { return v.version === currentVer; });
            if (verInfo && verInfo.tag && verInfo.downloadFile) {
                dlBtn.href = `${prefix}download/${verInfo.tag}/${verInfo.downloadFile}`;
                dlBtn.setAttribute('download', verInfo.downloadFile);
                dlBtn.innerHTML = `ZIP を<br>直接ダウンロード<span style="font-size:0.75rem; display:block; opacity:0.9;">(${verInfo.tag})</span>`;
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
