// script.js
// Curriculum Analyzer - ドキュメント用スクリプト
// 直接ダウンロードリンクの管理、スムーススクロール、スクロールスパイ

const APP_VERSION = '1.1.0';
const GITHUB_REPO = 'https://github.com/sam-hat-86/Curriculum_Analyzer';
const DOWNLOAD_FILENAME = `Curriculum_Analyzer_v${APP_VERSION}.zip`;
const DOWNLOAD_URL = `${GITHUB_REPO}/releases/download/v${APP_VERSION}/${DOWNLOAD_FILENAME}`;

const SITE_LINKS = {
    appDownload: DOWNLOAD_URL,
    repoReleases: `${GITHUB_REPO}/releases/latest`,
    repoHome: GITHUB_REPO
};

document.addEventListener('DOMContentLoaded', function () {
    // 1. data-link-key 属性を持つリンクへ URL を自動反映
    (function applySiteLinks() {
        document.querySelectorAll('[data-link-key]').forEach(function (el) {
            const key = el.getAttribute('data-link-key');
            if (!key) return;
            const url = SITE_LINKS[key];
            if (url) {
                if (el.tagName.toLowerCase() === 'a') {
                    el.setAttribute('href', url);
                }
                const labelEl = el.querySelector('[data-link-text]');
                if (labelEl) {
                    labelEl.textContent = `${DOWNLOAD_FILENAME} をダウンロード`;
                }
            }
        });
    })();

    // 2. ページ内アンカーのスムーススクロール
    document.querySelectorAll('a[href^="#"]').forEach(function (link) {
        link.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (!href || href === '#') return;
            const targetId = href.slice(1);
            const target = document.getElementById(targetId);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                // キーボードアクセシビリティ
                target.setAttribute('tabindex', '-1');
                target.focus({ preventScroll: true });
                history.pushState(null, '', href);
            }
        });
    });

    // 3. スクロールスパイ (目次のカレント表示)
    const sections = document.querySelectorAll('main section[id], article > section[id]');
    const navLinks = document.querySelectorAll('.note-toc a[href^="#"]');

    function onScroll() {
        const fromTop = window.scrollY + 120;
        let currentId = null;

        sections.forEach(function (section) {
            const top = section.offsetTop;
            const height = section.offsetHeight;
            if (top <= fromTop && (top + height) > fromTop) {
                currentId = section.id;
            }
        });

        navLinks.forEach(function (link) {
            const href = link.getAttribute('href').slice(1);
            if (href === currentId) {
                link.classList.add('active');
                link.setAttribute('aria-current', 'true');
            } else {
                link.classList.remove('active');
                link.removeAttribute('aria-current');
            }
        });
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
});