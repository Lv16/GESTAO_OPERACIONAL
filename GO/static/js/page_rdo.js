(function () {
    'use strict';

    function qs(sel, ctx) { try { return (ctx || document).querySelector(sel); } catch { return null; } }
    function qsa(sel, ctx) { try { return Array.from((ctx || document).querySelectorAll(sel)); } catch { return []; } }

    function parseBoolish(v) {
        if (v === true || v === 1 || v === '1') return true;
        if (v === false || v === 0 || v === '0') return false;
        if (typeof v === 'string') {
            const s = v.trim().toLowerCase();
            if (['sim', 's', 'true', 'yes', 'y'].includes(s)) return true;
            if (['nao', 'não', 'n', 'false', 'no'].includes(s)) return false;
        }
        return null;
    }

    let page = qs('#rdo') || null;

    /* ================= PRINT ZOOM ================= */

    function mmToPx(mm) {
        const d = document.createElement('div');
        d.style.height = mm + 'mm';
        d.style.position = 'absolute';
        d.style.visibility = 'hidden';
        document.body.appendChild(d);
        const px = d.getBoundingClientRect().height;
        document.body.removeChild(d);
        return px || 0;
    }

    function computeTwoPageZoom(el) {
        if (!el) return 1;
        const usableMm = (210 - 12) * 2;
        const targetPx = mmToPx(usableMm);
        const actualPx = el.scrollHeight || el.getBoundingClientRect().height;
        if (!targetPx || !actualPx) return 1;
        return Math.min(1, (targetPx / actualPx) * 0.98);
    }

    let prevZoom = null;
    function applyPrintZoom() {
        if (!page) return;
        prevZoom = document.documentElement.style.getPropertyValue('--print-zoom');
        document.documentElement.style.setProperty('--print-zoom', computeTwoPageZoom(page));
    }
    function resetPrintZoom() {
        if (prevZoom == null) document.documentElement.style.removeProperty('--print-zoom');
        else document.documentElement.style.setProperty('--print-zoom', prevZoom);
        prevZoom = null;
    }

    window.addEventListener('beforeprint', applyPrintZoom);
    window.addEventListener('afterprint', resetPrintZoom);

    /* ================= OVERLAY ================= */

    const overlayId = 'rdo-print-overlay';
    let overlay = qs('#' + overlayId);

    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = overlayId;
        Object.assign(overlay.style, {
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,.6)',
            zIndex: 99999,
            display: 'none',
            alignItems: 'center',
            justifyContent: 'center'
        });
        document.body.appendChild(overlay);
    }

    let placeholder = null;
    let currentRdoId = null;

    function openPage(rdoId) {
        if (!page) return;
        currentRdoId = rdoId;

        if (!placeholder) {
            placeholder = document.createElement('div');
            page.parentNode.insertBefore(placeholder, page);
        }

        overlay.innerHTML = '';
        overlay.style.display = 'flex';

        const container = document.createElement('div');
        Object.assign(container.style, {
            background: '#fff',
            maxWidth: '1100px',
            width: '95%',
            maxHeight: '95vh',
            display: 'flex',
            flexDirection: 'column',
            borderRadius: '6px'
        });

        const toolbar = document.createElement('div');
        Object.assign(toolbar.style, {
            padding: '8px 12px',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '8px',
            background: '#f5f5f5',
            borderBottom: '1px solid #ddd'
        });

        const printBtn = document.createElement('button');
        printBtn.textContent = 'Exportar PDF';
        printBtn.onclick = function () {
            if (!currentRdoId) {
                alert('RDO não identificado');
                return;
            }
            const url = `/rdo/${encodeURIComponent(currentRdoId)}/print/?auto=1`;
            const w = window.open(url, '_blank');
            if (!w) window.location.href = url;
            closePage();
        };

        const closeBtn = document.createElement('button');
        closeBtn.textContent = 'Fechar';
        closeBtn.onclick = closePage;

        toolbar.append(printBtn, closeBtn);

        const content = document.createElement('div');
        content.style.overflow = 'auto';
        content.style.padding = '16px';
        content.appendChild(page);

        container.append(toolbar, content);
        overlay.appendChild(container);

        page.style.display = '';
        document.addEventListener('keydown', escHandler);
    }

    function closePage() {
        overlay.style.display = 'none';
        if (placeholder && placeholder.parentNode) {
            placeholder.parentNode.insertBefore(page, placeholder);
            placeholder.remove();
        }
        page.style.display = 'none';
        placeholder = null;
        document.removeEventListener('keydown', escHandler);
    }

    function escHandler(e) {
        if (e.key === 'Escape') closePage();
    }

    /* ================= LISTAGEM ================= */

    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.action-btn.view');
        if (!btn) return;
        e.preventDefault();

        const tr = btn.closest('tr');
        const rid = tr?.dataset?.rdoId;
        if (!rid) return;

        const url = `/rdo/${encodeURIComponent(rid)}/page/`;
        const w = window.open(url, '_blank');
        if (!w) window.location.href = url;
    }, true);

    window.pageRdo = { open: openPage, close: closePage };

})();
