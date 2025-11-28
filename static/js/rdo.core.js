/* rdo.core.js
   Núcleo mínimo e seguro do fluxo do Supervisor (modal), independente do rdo.js legado.
   Funcionalidades:
   - Abrir/fechar modal (#modal-supervisor-overlay)
   - Aplicar contexto (labels e hiddens)
   - Buscar detalhes via /rdo/<id>/detail/
   - Montar FormData (usa window.buildSupervisorFormDataExternal se existir)
   - Enviar POST para /rdo/create_ajax/ e /rdo/update_ajax/ com CSRF
   - Emitir CustomEvents: 'rdo:saved' e 'rdo:save:error'
   - Expor APIs públicas: window.rdoOpenSupervisorModal, window.computeModalAggregates, window.ai (stub)
*/

;(function(){
  'use strict';

  // ---------- Utils ----------
  function qs(sel, ctx){ return (ctx || document).querySelector(sel); }
  function qsa(sel, ctx){ return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function onReady(fn){ if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn); else fn(); }

  function showToast(message, type){
    try {
      var id = 'rdo-core-toast';
      var e = document.getElementById(id);
      if (e) e.remove();
      var div = document.createElement('div');
      div.id = id;
      div.className = 'rdo-toast ' + (type || 'info');
      div.textContent = message;
      Object.assign(div.style, {
        position: 'fixed', right: '20px', bottom: '20px', padding: '10px 14px',
        borderRadius: '6px', boxShadow: '0 2px 6px rgba(0,0,0,.2)', zIndex: 99999,
        background: (type === 'success' ? '#2e7d32' : type === 'error' ? '#c62828' : '#333'),
        color: '#fff'
      });
      document.body.appendChild(div);
      setTimeout(function(){ try { div.style.opacity = '0'; setTimeout(function(){ try{ div.remove(); }catch(_){} }, 300); } catch(_){} }, 2800);
    } catch(_){}
  }

  function getCSRF(container){
    var el = (container || document).querySelector('input[name="csrfmiddlewaretoken"]');
    return el ? el.value : '';
  }

  // ---------- Desktop notifications popover ----------
  function _isDesktop(){
    return window.innerWidth >= 900;
  }

  function _buildOsLabel(os){
    var parts = [];
    if (os.empresa) parts.push(os.empresa);
    if (os.unidade) parts.push(os.unidade);
    return parts.join(' • ');
  }

  function _updateNotificationCount(count){
    try {
      var btn = qs('#rdo-notification-btn');
      var badge = btn && btn.querySelector('.count');
      if (badge) badge.textContent = String(count || 0);
    } catch(_){ }
  }

  async function _fetchPendingOs(){
    // Reusar a mesma lógica consolidada de fetchPending (abaixo),
    // garantindo que contador e lista usem a mesma fonte de dados.
    try {
      // first try: real fetchPending() if available
      if (typeof fetchPending === 'function') {
        try {
          var items = await fetchPending();
          if (items && items.length) return items;
        } catch(_){ }
      }
      // second try: data already populated in memory by legacy code
      if (window.__rdo_pending_list && Array.isArray(window.__rdo_pending_list) && window.__rdo_pending_list.length) {
        return window.__rdo_pending_list;
      }
      // third try: localStorage snapshot
      try {
        var raw = localStorage.getItem('rdo_pending_list');
        if (raw) {
          var parsed = JSON.parse(raw);
          if (Array.isArray(parsed) && parsed.length) return parsed;
        }
      } catch(_){ }
    } catch(_){ }
    // Fallback: leitura direta da tabela, como antes
    return extractOpenOsFromTable();
  }

  function _renderDesktopPopover(list){
    var pop = qs('#rdo-desktop-notification-popover');
    if (!pop) return;
    var body = qs('#rdo-popover-list', pop);
    var summary = pop.querySelector('[data-role="summary"]');
    var countEl = pop.querySelector('[data-role="count"]');
    if (!body) return;

    body.innerHTML = '';
    var items = Array.isArray(list) ? list : [];
    // preserve the canonical full list on the popover so search can use it
    try { if (!pop.__allItemsOriginal || !Array.isArray(pop.__allItemsOriginal) || pop.__allItemsOriginal.length === 0) pop.__allItemsOriginal = Array.isArray(list) ? list.slice() : []; } catch(_){ }
    var allItems = (pop.__allItemsOriginal && Array.isArray(pop.__allItemsOriginal)) ? pop.__allItemsOriginal : items.slice();
    // order by id desc when possible to show most recent first
    try { items = items.slice().sort(function(a,b){ return (Number(b.id)||0) - (Number(a.id)||0); }); } catch(_){ }
    var total = items.length;
    if (countEl) countEl.textContent = total + ' OS';

    if (!total){
      var empty = document.createElement('div');
      empty.className = 'rdo-empty-state';
      // Provide a helpful message including debug hints when empty
      var hint = 'Nenhuma OS com RDO em aberto.';
      try {
        if (window.__rdo_pending_last_status) hint += ' (status: ' + window.__rdo_pending_last_status + ')';
      } catch(_){ }
      empty.textContent = hint;
      body.appendChild(empty);
      if (summary) summary.textContent = 'Sem pendências.';
      _updateNotificationCount(0);
      return;
    }

    // Render using the same simple list markup as the legacy CTA to guarantee behavior
    var ul = document.createElement('ul');
    ul.style.listStyle = 'none'; ul.style.padding = '8px'; ul.style.margin = '0'; ul.style.maxHeight='320px'; ul.style.overflow='auto';

    // Only show a limited number of items in the popover (most recent)
    var visualLimit = 5; // show top 5
    var visible = items.slice(0, visualLimit);
    var remaining = items.slice(visualLimit);

    visible.forEach(function(it){
      try {
        var li = document.createElement('li'); li.style.margin='6px 0';
        var btn = document.createElement('button'); btn.type='button'; btn.className='btn-rdo small';
        // marcar como item pesquisável dentro do popover
        try { btn.classList.add('rdo-os-item'); } catch(_){ }
        var osNum = it.numero_os || it.os || it.os_id || it.id || '-';
        var empresa = it.empresa || it.cliente || '';
        var unidade = it.unidade || it.unidade || '';
        btn.textContent = [osNum, empresa, unidade].filter(Boolean).join(' • ');
        btn.addEventListener('click', function(ev){
          try {
            ev.stopPropagation();
            var ctx = {
              rdo_id: it.rdo_id || it.id || '',
              os_id: it.os_id || it.id || '',
              numero_os: osNum,
              os: osNum,
              empresa: empresa,
              unidade: unidade,
              supervisor: it.supervisor || ''
            };
            if (typeof window.rdoOpenSupervisorModal === 'function') window.rdoOpenSupervisorModal(ctx);
            else if (typeof openSupervisorModal === 'function') openSupervisorModal(ctx);
          } catch(_){ }
        });
        li.appendChild(btn); ul.appendChild(li);
      } catch(_){ }
    });

    body.appendChild(ul);
    if (summary) summary.textContent = total + ' OS abertas.';
    try { _updateNotificationCount(total); } catch(_){ }
    // Update footer: if there are remaining items, update Ver todas label to include count
    try {
      var verBtn = pop.querySelector('#rdo-popover-ver-todas');
      if (verBtn) {
        // show remaining count based on the original full list, not the filtered/visible subset
        var remainingCount = (allItems && allItems.length) ? Math.max(0, allItems.length - visualLimit) : 0;
        if (remainingCount) verBtn.textContent = 'Ver todas (' + remainingCount + ')';
        else verBtn.textContent = 'Ver todas';
        if (!verBtn.__boundFull) {
          verBtn.addEventListener('click', function(){ try { _openFullListModal(allItems); } catch(_){ } });
          verBtn.__boundFull = true;
        }
      }
    } catch(_){ }
    // debug trace (safe) to help during testing
    try { console.debug && console.debug('rdo: renderDesktopPopover - items length', total, items && items[0]); } catch(_){ }
  }

    // Abre modal com a lista completa de OS não finalizadas
    function _openFullListModal(items){
      try {
        var list = Array.isArray(items) ? items : (window.__rdo_pending_list || []);
        if (!list || !list.length) {
          // fallback: rolar até a tabela principal
          try { var table = document.querySelector('.tabela_conteiner'); if (table) table.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch(_){ }
          return;
        }

        // evitar múltiplas instâncias
        var existing = document.getElementById('rdo-full-list-overlay');
        if (existing) {
          try { existing.parentNode.removeChild(existing); } catch(_){ }
        }

        // inject minimal styles if necessary
        try {
          if (!document.getElementById('rdo-full-list-style')){
            var css = '\n#rdo-full-list-overlay{position:fixed;z-index:12000;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;padding:20px;}\n#rdo-full-list-overlay .rdo-full-list-modal{background:#fff;max-width:820px;width:100%;max-height:80vh;overflow:auto;border-radius:8px;padding:16px;box-shadow:0 8px 24px rgba(0,0,0,0.2);}\n#rdo-full-list-overlay .rdo-full-list-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}\n#rdo-full-list-overlay .rdo-full-list-body{max-height:64vh;overflow:auto;}\n#rdo-full-list-overlay .rdo-full-list-item{display:block;width:100%;text-align:left;padding:10px;border-radius:6px;border:1px solid #eee;margin-bottom:8px;background:#fafafa;}\n#rdo-full-list-overlay .rdo-full-list-item:hover{background:#f3f3f3;}\n#rdo-full-list-overlay .rdo-full-list-close{background:transparent;border:0;font-size:18px;cursor:pointer;}\n';
            var s = document.createElement('style'); s.id = 'rdo-full-list-style'; s.type = 'text/css'; s.appendChild(document.createTextNode(css)); document.head.appendChild(s);
          }
        } catch(_){ }

        var overlay = document.createElement('div'); overlay.id = 'rdo-full-list-overlay'; overlay.setAttribute('role','dialog'); overlay.setAttribute('aria-modal','true'); overlay.setAttribute('aria-label','Lista de OS abertas');
        // garantir que o overlay seja visível com as regras CSS que usam aria-hidden
        overlay.setAttribute('aria-hidden', 'false');
        console.debug && console.debug('rdo: _openFullListModal - overlay created, items=', (list && list.length) || 0);
        var modal = document.createElement('div'); modal.className = 'rdo-full-list-modal';
        var header = document.createElement('div'); header.className = 'rdo-full-list-header';
        var title = document.createElement('div'); title.textContent = (list.length || 0) + ' OS abertas'; title.style.fontWeight = '600';
        var closeBtn = document.createElement('button'); closeBtn.type = 'button'; closeBtn.className = 'rdo-full-list-close'; closeBtn.setAttribute('aria-label','Fechar'); closeBtn.textContent = '✕';
        header.appendChild(title); header.appendChild(closeBtn);
        var body = document.createElement('div'); body.className = 'rdo-full-list-body';

        // build list
        list.forEach(function(it){ try {
          var btn = document.createElement('button'); btn.type='button'; btn.className='rdo-full-list-item';
          var osNum = it.numero_os || it.os || it.os_id || it.id || '-';
          var empresa = it.empresa || it.cliente || '';
          var unidade = it.unidade || '';
          btn.textContent = [osNum, empresa, unidade].filter(Boolean).join(' • ');
          btn.addEventListener('click', function(ev){ try {
            ev.preventDefault();
            var ctx = { rdo_id: it.rdo_id || it.id || '', os_id: it.os_id || it.id || '', numero_os: osNum, os: osNum, empresa: empresa, unidade: unidade, supervisor: it.supervisor || '' };
            try { if (typeof window.rdoOpenSupervisorModal === 'function') window.rdoOpenSupervisorModal(ctx); else if (typeof openSupervisorModal === 'function') openSupervisorModal(ctx); } catch(_){ }
            try { document.body.removeChild(overlay); } catch(_){ }
          } catch(_){ } });
          body.appendChild(btn);
        } catch(_){ } });

        modal.appendChild(header); modal.appendChild(body); overlay.appendChild(modal); document.body.appendChild(overlay);
        // garantir animação / visibilidade caso CSS utilize selectors por atributo
        try { overlay.classList.add('open'); } catch(_){ }

        function close(){ try { if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); } catch(_){ } }
        closeBtn.addEventListener('click', function(ev){ ev.preventDefault(); close(); });
        overlay.addEventListener('click', function(ev){ try { if (ev.target === overlay) close(); } catch(_){ } });
        document.addEventListener('keydown', function onEsc(ev){ try { if (ev.key === 'Escape'){ document.removeEventListener('keydown', onEsc); close(); } } catch(_){ } });
      } catch(e){ console.warn('rdo: _openFullListModal failed', e); }
    }

  function openModal(){
    var overlay = qs('#supv-modal-overlay');
    if (!overlay) return false;
    overlay.classList.remove('is-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden','false');
    var focusable = overlay.querySelector('input,select,textarea,button');
    if (focusable) try { focusable.focus(); } catch(_){}
    return true;
  }

  function closeModal(){
    var overlay = qs('#supv-modal-overlay');
    if (!overlay) return false;
    overlay.classList.remove('open');
    overlay.classList.add('is-hidden');
    overlay.setAttribute('aria-hidden','true');
    return true;
  }

  // Toggle do popover ao clicar no sino (desktop)
  onReady(function(){
    try {
      var btn = qs('#rdo-notification-btn');
      var pop = qs('#rdo-desktop-notification-popover');
      if (!btn || !pop) return;

      var isOpen = false;

      function closePop(){
        if (!isOpen) return;
        isOpen = false;
        pop.classList.remove('open');
        pop.setAttribute('aria-hidden','true');
        document.removeEventListener('click', onDocClick, true);
        document.removeEventListener('keydown', onKey,
          true);
      }

      function onDocClick(ev){
        if (!isOpen) return;
        if (btn.contains(ev.target) || pop.contains(ev.target)) return;
        closePop();
      }

      function onKey(ev){
        if (ev.key === 'Escape') closePop();
      }

      btn.addEventListener('click', async function(ev){
        ev.preventDefault();
        if (!_isDesktop()) return; // em mobile, apenas o CTA padrão deve atuar

        // Evitar que outros listeners globais no botão executem em paralelo
        ev.stopPropagation();

        if (isOpen){
          closePop();
          return;
        }

        isOpen = true;
        pop.classList.add('open');
        pop.setAttribute('aria-hidden','false');
        document.addEventListener('click', onDocClick, true);
        document.addEventListener('keydown', onKey, true);

        // Em desktop, mantenha o CTA móvel oculto para não sobrepor o popover
        try {
          var cta = qs('#rdo-mobile-cta');
          if (cta){
            cta.setAttribute('aria-hidden','true');
            cta.classList.remove('active');
          }
        } catch(_){ }

        var summary = pop.querySelector('[data-role="summary"]');
        if (summary) summary.textContent = 'Carregando OS…';
        try {
          var list = await _fetchPendingOs();
          _renderDesktopPopover(list || []);
        } catch(_){
          _renderDesktopPopover([]);
        }
      });

      // Filtro de busca local
      var search = qs('#rdo-popover-search-input', pop);
      if (search){
        search.addEventListener('input', function(){
          try {
            var term = (search.value || '').toLowerCase().trim();
            var canonical = (pop.__allItemsOriginal && Array.isArray(pop.__allItemsOriginal)) ? pop.__allItemsOriginal : [];
            if (!term) {
              // restore full visible set (top ones)
              _renderDesktopPopover((canonical && canonical.slice) ? canonical.slice(0,5) : canonical);
              return;
            }
            // filter across fields: numero_os, os, empresa, unidade
            var matched = canonical.filter(function(it){
              try {
                var osNum = String(it.numero_os || it.os || it.os_id || it.id || '').toLowerCase();
                var empresa = String(it.empresa || it.cliente || '').toLowerCase();
                var unidade = String(it.unidade || it.unidade || '').toLowerCase();
                var hay = [osNum, empresa, unidade].join(' ');
                return hay.indexOf(term) !== -1;
              } catch(_){ return false; }
            });
            // render all matches (no visualLimit) so user sees the matching hidden OS
            _renderDesktopPopover(matched);
          } catch(_){ }
        });
      }

      // Botão "Ver todas": somente aplicar fallback (rolar até tabela) quando
      // a função _openFullListModal não estiver disponível.
      var verTodas = qs('#rdo-popover-ver-todas', pop);
      if (verTodas){
        if (typeof _openFullListModal !== 'function') {
          verTodas.addEventListener('click', function(){
            try {
              var table = document.querySelector('.tabela_conteiner');
              if (table) table.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } catch(_){ }
            closePop();
          });
        }
      }
    } catch(_){ }
  });

  // Fallback global helper: extrai OS abertas da tabela quando endpoints não responderem.
  // Definimos no escopo superior para evitar ReferenceError quando outras rotinas chamam
  // extractOpenOsFromTable() antes de applyContext() ser executado.
  function extractOpenOsFromTable(){
    try {
      var rows = document.querySelectorAll('table tbody tr[data-os-id]');
      if (!rows || !rows.length) return [];
      var map = Object.create(null);
      Array.prototype.forEach.call(rows, function(tr){
        try {
          var osId = tr.getAttribute('data-os-id') || '';
          if (!osId) return;
          var status = (tr.getAttribute('data-status-geral') || (tr.dataset && (tr.dataset.statusGeral || tr.dataset.status_geral)) || '').toString().toLowerCase();
          var isClosed = /conclu|cancel|finaliz|encerrad|fechad/.test(status);
          if (isClosed) return;
          if (map[osId]) return;
          var numero_os = tr.getAttribute('data-numero-os') || (tr.dataset && (tr.dataset.numeroOs || tr.dataset.numero_os)) || '';
          var empresa = tr.getAttribute('data-empresa') || (tr.dataset && tr.dataset.empresa) || '';
          var unidade = tr.getAttribute('data-unidade') || (tr.dataset && tr.dataset.unidade) || '';
          var supervisor = tr.getAttribute('data-supervisor') || (tr.dataset && tr.dataset.supervisor) || '';
          var rdoId = tr.getAttribute('data-rdo-id') || (tr.dataset && (tr.dataset.rdoId || tr.dataset.rdo_id)) || '';
          map[osId] = {
            os_id: osId,
            numero_os: numero_os || osId,
            empresa: empresa,
            unidade: unidade,
            supervisor: supervisor,
            rdo_id: rdoId
          };
        } catch(_){ }
      });
      return Object.keys(map).map(function(k){ return map[k]; });
    } catch(_){ return []; }
  }

  function applyContext(ctx){
    try {
      try { console.log && console.log('rdo: applyContext start', ctx); } catch(_){}
  if (!ctx) return;
  // expose previous_compartimentos from context to the global scope so
  // other components (rdo.compartment.js) can read the baseline values.
  try { window.rdo_previous_compartimentos = ctx.previous_compartimentos || window.rdo_previous_compartimentos || []; } catch(_){ }
      var setText = function(id, v){ var el = document.getElementById(id); if (el) el.textContent = (v == null ? '-' : String(v)); };
      setText('sup-context-os', ctx.numero_os || ctx.os || '');
      setText('sup-context-empresa', ctx.empresa || '');
      setText('sup-context-unidade', ctx.unidade || '');
      setText('sup-context-supervisor', ctx.supervisor || ctx.supervisor_fullname || ctx.supervisor_login || '');
  setText('sup-context-rdo', (typeof ctx.rdo_count !== 'undefined' && ctx.rdo_count !== '') ? ctx.rdo_count : (ctx.rdo || ''));

  var form = qs('#form-supervisor');
      if (form) {
        var hidRdo = document.getElementById('sup-rdo-id');
        // Only set the hidden rdo id when the caller explicitly wants to edit an existing RDO.
        // When opening the modal to create the "next" RDO (rdo_count + 1), ctx.rdo_id may
        // contain the current RDO's id — we must NOT set it, otherwise submission will go to update.
        if (hidRdo) {
          if (ctx && (ctx.edit === true || ctx.action === 'edit' || ctx.forceEdit === true)) {
            hidRdo.value = ctx.rdo_id || '';
          } else {
            hidRdo.value = '';
          }
        }
        var hidOs = document.getElementById('sup-ordem-id');
        if (!hidOs) {
          hidOs = document.createElement('input');
          hidOs.type = 'hidden'; hidOs.name = 'ordem_servico_id'; hidOs.id = 'sup-ordem-id';
          form.appendChild(hidOs);
        }
        hidOs.value = ctx.os_id || '';
        // Preencher contrato/PO se disponível; se ausente, tentar extrair da tabela procurando rdo_count correspondente
        try {
          var contratoEl = document.getElementById('sup-contrato-po');
          if (contratoEl) {
            if (typeof ctx.contrato_po !== 'undefined' && String(ctx.contrato_po || '').trim() !== '') {
              contratoEl.value = ctx.contrato_po || '';
            } else if (ctx.rdo_count != null && String(ctx.rdo_count).trim() !== '') {
              // procurar row correspondente na tabela por data-rdo-count
              try {
                var selector = 'tr[data-rdo-count="' + String(ctx.rdo_count) + '"]';
                var tr = document.querySelector(selector);
                if (tr) {
                  var po = tr.getAttribute('data-po') || (tr.dataset && (tr.dataset.po || tr.dataset.po)) || '';
                  if (po) contratoEl.value = po;
                }
              } catch(_){ }
              // If still empty, try to find the PO by matching OS id or numero_os on table rows
              try {
                if (!contratoEl.value || String(contratoEl.value).trim() === '') {
                  var tr2 = null;
                  if (ctx.os_id) {
                    try { tr2 = document.querySelector('tr[data-os-id="' + String(ctx.os_id) + '"]'); } catch(_){ tr2 = null; }
                  }
                  if (!tr2 && ctx.numero_os) {
                    try { tr2 = document.querySelector('tr[data-numero-os="' + String(ctx.numero_os) + '"]'); } catch(_){ tr2 = null; }
                  }
                  if (tr2) {
                    var po2 = tr2.getAttribute('data-po') || (tr2.dataset && (tr2.dataset.po || tr2.dataset.po)) || '';
                    if (po2) contratoEl.value = po2;
                  }
                }
              } catch(_){ }
            }
          }
        } catch(_){ }
        // Debug: report contrato/PO resolution result
        try {
          var _cEl = document.getElementById('sup-contrato-po');
          var _final = _cEl ? (_cEl.value || '') : '';
          console.debug && console.debug('rdo: applyContext contrato resolution final', { ctx: ctx, finalPo: _final });
        } catch(_){ }
        // If this is RDO > 1, prefer to copy the PO from RDO 1 for the same OS (if available)
        try {
          var contratoEl2 = document.getElementById('sup-contrato-po');
          if (contratoEl2) {
            var rawCount = (ctx && (ctx.rdo_count || ctx.rdo)) || '';
            var n = parseInt(String(rawCount).replace(/[^0-9]/g,''), 10);
            if (isFinite(n) && n > 1) {
              // try to find RDO 1 row for same OS id or same numero_os
              var foundPo = '';
              if (ctx && ctx.os_id) {
                try {
                  var firstRow = document.querySelector('tr[data-os-id="' + String(ctx.os_id) + '"][data-rdo-count="1"]');
                  if (firstRow) foundPo = firstRow.getAttribute('data-po') || (firstRow.dataset && firstRow.dataset.po) || '';
                } catch(_){ }
              }
              if (!foundPo && ctx && ctx.numero_os) {
                try {
                  var firstRow2 = document.querySelector('tr[data-numero-os="' + String(ctx.numero_os) + '"][data-rdo-count="1"]');
                  if (firstRow2) foundPo = firstRow2.getAttribute('data-po') || (firstRow2.dataset && firstRow2.dataset.po) || '';
                } catch(_){ }
              }
              if (foundPo) {
                contratoEl2.value = foundPo;
                contratoEl2.readOnly = true;
                contratoEl2.setAttribute('aria-readonly','true');
                contratoEl2.classList.add('readonly');
              } else {
                // If we cannot find the PO, close the input to avoid forcing the user to type it.
                contratoEl2.readOnly = true;
                contratoEl2.setAttribute('aria-readonly','true');
                contratoEl2.classList.add('readonly');
              }
            } else {
              // RDO 1: ensure field is editable
              contratoEl2.readOnly = false;
              contratoEl2.removeAttribute('aria-readonly');
              contratoEl2.classList.remove('readonly');
            }
          }
        } catch(_){ }
      }
      // Bloquear visualmente campos de "Previsões" quando já houver valor no contexto
      try {
        var lockField = function(inputEl, value){
          if (!inputEl) return;
          if (typeof value !== 'undefined' && value !== null && String(value).toString().trim() !== '') {
            try { inputEl.value = String(value); } catch(_){}
            try { inputEl.readOnly = true; inputEl.setAttribute('aria-readonly','true'); inputEl.classList.add('readonly'); } catch(_){}
            try { var wrapper = inputEl.closest('.form-field'); if (wrapper) wrapper.classList.add('rdo-auto-locked'); } catch(_){}
          } else {
            try { inputEl.readOnly = false; inputEl.removeAttribute('aria-readonly'); inputEl.classList.remove('readonly'); } catch(_){}
            try { var wrapper2 = inputEl.closest('.form-field'); if (wrapper2) wrapper2.classList.remove('rdo-auto-locked'); } catch(_){}
          }
        };

        // suportar múltiplas chaves possíveis vindas do contexto (nomes antigos/novos)
        var ensacEl = qs('#sup-prev-ensac');
        var icaEl = qs('#sup-prev-ica');
        var cambaEl = qs('#sup-prev-camba');
        // procurar valores no contexto com várias chaves possíveis
        var ensacVal = (ctx.ensacamento_prev !== undefined ? ctx.ensacamento_prev : (ctx.ensacamento_previsao !== undefined ? ctx.ensacamento_previsao : (ctx.ensacamento_prevision || ctx.ensacamento || null)));
        var icaVal = (ctx.icamento_prev !== undefined ? ctx.icamento_prev : (ctx.icamento_previsao !== undefined ? ctx.icamento_previsao : (ctx.icamento_prevision || null)));
        var cambaVal = (ctx.cambagem_prev !== undefined ? ctx.cambagem_prev : (ctx.cambagem_previsao !== undefined ? ctx.cambagem_previsao : (ctx.cambagem || null)));

        // se o backend enviar somente ensacamento_previsao e icamento_previsao deve ficar espelhado
        // aplicar bloqueio: se existe valor no contexto, bloquear o campo correspondente
        lockField(ensacEl, ensacVal);
        // Se icamento não veio, mas veio ensacamento e icamento está vazio no DOM, copiar e bloquear (comportamento one-time)
        if ((icaVal === null || typeof icaVal === 'undefined' || String(icaVal).trim() === '') && (ensacVal !== null && typeof ensacVal !== 'undefined' && String(ensacVal).trim() !== '')) {
          lockField(icaEl, ensacVal);
        } else {
          lockField(icaEl, icaVal);
        }
        lockField(cambaEl, cambaVal);
      } catch(e){ console.warn('applyContext: lock previsoes failed', e); }

      // Bloquear visualmente o número de compartimentos quando já existir no contexto
      try {
        var ncompEl = qs('#sup-n-comp');
        var compSelector = qs('#sup-comp-selector');
        var ncompVal = (ctx.numero_compartimentos !== undefined ? ctx.numero_compartimentos : (ctx.numero_compartimento !== undefined ? ctx.numero_compartimento : null));
        if (ncompEl) {
          if (typeof ncompVal !== 'undefined' && ncompVal !== null && String(ncompVal).toString().trim() !== '') {
            try { ncompEl.value = String(ncompVal); } catch(_){ }
            try { ncompEl.readOnly = true; ncompEl.setAttribute('aria-readonly','true'); ncompEl.classList.add('readonly'); } catch(_){ }
            try { var w = ncompEl.closest('.form-field'); if (w) w.classList.add('rdo-auto-locked'); } catch(_){ }
            // Nota: não desabilitar o seletor de compartimentos — o usuário deve poder
            // marcar quais compartimentos tiveram avanço, apenas não pode alterar o
            // número total de compartimentos. O renderer do seletor deve usar o valor
            // de `#sup-n-comp` para gerar as opções correspondentes.
          } else {
            try { ncompEl.readOnly = false; ncompEl.removeAttribute('aria-readonly'); ncompEl.classList.remove('readonly'); } catch(_){ }
            try { var w2 = ncompEl.closest('.form-field'); if (w2) w2.classList.remove('rdo-auto-locked'); } catch(_){ }
            // manter o seletor ativo quando não houver número definido
          }
        }
      } catch(e) { console.warn('applyContext: lock numero_compartimentos failed', e); }

      // Mostrar acumulados em tempo real: prev (do contexto) + valor diário atual
      try {
        // obter valores prévios vindos do contexto (várias chaves possíveis)
        var prevEnsac = (typeof ctx.ensacamento_acu !== 'undefined' ? ctx.ensacamento_acu : (typeof ctx.ensacamento_cumulativo !== 'undefined' ? ctx.ensacamento_cumulativo : (typeof ctx.ensacamento_total !== 'undefined' ? ctx.ensacamento_total : null)));
        var prevIca = (typeof ctx.icamento_acu !== 'undefined' ? ctx.icamento_acu : (typeof ctx.icamento_cumulativo !== 'undefined' ? ctx.icamento_cumulativo : null));
        var prevCamba = (typeof ctx.cambagem_acu !== 'undefined' ? ctx.cambagem_acu : (typeof ctx.cambagem_cumulativo !== 'undefined' ? ctx.cambagem_cumulativo : null));

        var ensacDiaEl = qs('#sup-ensac');
        var icaDiaEl = qs('#sup-ica');
        var cambaDiaEl = qs('#sup-camba');

        var ensacAcuEl = qs('#sup-ensac-acu');
        var icaAcuEl = qs('#sup-ica-acu');
        var cambaAcuEl = qs('#sup-camba-acu');

        function toIntSafe(v){ try { if (v === null || typeof v === 'undefined' || String(v).trim() === '') return 0; return parseInt(String(v).replace(/[^0-9\-]/g,''),10) || 0; } catch(e){ return 0; } }

        function recomputeAccumulates(){
          try{
            var baseEns = toIntSafe(prevEnsac);
            var baseIca = toIntSafe(prevIca);
            var baseCamba = toIntSafe(prevCamba);
            var curEns = ensacDiaEl ? toIntSafe(ensacDiaEl.value) : 0;
            var curIca = icaDiaEl ? toIntSafe(icaDiaEl.value) : 0;
            var curCamba = cambaDiaEl ? toIntSafe(cambaDiaEl.value) : 0;
            if (ensacAcuEl) ensacAcuEl.value = String(baseEns + curEns);
            if (icaAcuEl) icaAcuEl.value = String(baseIca + curIca);
            if (cambaAcuEl) cambaAcuEl.value = String(baseCamba + curCamba);
          }catch(e){/* noop */}
        }

        // bind events (idempotente)
        try{
          if (ensacDiaEl && !ensacDiaEl.__accBound) { ensacDiaEl.addEventListener('input', recomputeAccumulates); ensacDiaEl.__accBound = true; }
          if (icaDiaEl && !icaDiaEl.__accBound) { icaDiaEl.addEventListener('input', recomputeAccumulates); icaDiaEl.__accBound = true; }
          if (cambaDiaEl && !cambaDiaEl.__accBound) { cambaDiaEl.addEventListener('input', recomputeAccumulates); cambaDiaEl.__accBound = true; }
        }catch(e){/* noop */}

        // executar cálculo inicial
        recomputeAccumulates();
      } catch(e){ console.warn('applyContext: realtime accumulates failed', e); }

        // Fallback: extrair OS "abertas" da tabela quando API não retornar itens
    function extractOpenOsFromTable(){
          try {
            var rows = document.querySelectorAll('table tbody tr[data-os-id]');
            if (!rows || !rows.length) return [];
            var map = Object.create(null); // dedupe por os_id
            Array.prototype.forEach.call(rows, function(tr){
              try {
                var osId = tr.getAttribute('data-os-id') || '';
                if (!osId) return;
                var status = (tr.getAttribute('data-status-geral') || (tr.dataset && (tr.dataset.statusGeral || tr.dataset.statusGeral)) || '').toString().toLowerCase();
                // Heurística: considerar "abertas" tudo que NÃO parece concluído/cancelado/finalizado
                var isClosed = /conclu|cancel|finaliz|encerrad|fechad/.test(status);
                if (isClosed) return;
                // Se já existe, manter o primeiro encontrado
                if (map[osId]) return;
                var numero_os = tr.getAttribute('data-numero-os') || (tr.dataset && (tr.dataset.numeroOs || tr.dataset.numero_os)) || '';
                var empresa = tr.getAttribute('data-empresa') || (tr.dataset && tr.dataset.empresa) || '';
                var unidade = tr.getAttribute('data-unidade') || (tr.dataset && tr.dataset.unidade) || '';
                var supervisor = tr.getAttribute('data-supervisor') || (tr.dataset && tr.dataset.supervisor) || '';
                var rdoId = tr.getAttribute('data-rdo-id') || (tr.dataset && (tr.dataset.rdoId || tr.dataset.rdo_id)) || '';
                map[osId] = {
                  os_id: osId,
                  numero_os: numero_os || osId,
                  empresa: empresa,
                  unidade: unidade,
                  supervisor: supervisor,
                  rdo_id: rdoId
                };
              } catch(_){ }
            });
            return Object.keys(map).map(function(k){ return map[k]; });
          } catch(_){ return []; }
        }
    try {
      // after applying visual/context values, attempt to populate the next RDO
      try { populateNextRdoIfNeeded(ctx); } catch(_) { /* best-effort */ }
    } catch(_) {}
    } catch(e){ console.warn('applyContext failed', e); }
  }

  async function fetchAndPopulateRdo(rdoId){
    if (!rdoId) return;
    try {
      var url = '/rdo/' + encodeURIComponent(rdoId) + '/detail/';
      var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) {
        // When RDO is not found (404) it's normal during RDO creation flows;
        // suppress the toast so the user doesn't see "RDO não encontrado".
        if (resp.status === 404) return;
        // For other errors (403, 500, network issues) show helpful message
        try {
          var txt = null;
          try { var j = await resp.json(); if (j && (j.error || j.message)) txt = j.error || j.message; } catch(_){ }
          if (!txt) {
            try { txt = (await resp.text()) || (resp.status + ' ' + resp.statusText); } catch(_){ txt = (resp.status + ' ' + resp.statusText); }
          }
          if (txt) showToast(txt, 'error');
        } catch(_){ }
        return;
      }
      var data = await resp.json();
      if (!data || !data.success || !data.rdo) return;
      var r = data.rdo || {};
      // Expose previous_compartimentos globally so compartment UI can read it
      try{ window.rdo_previous_compartimentos = r.previous_compartimentos || window.rdo_previous_compartimentos || []; }catch(_){ }
      // Preencher alguns campos agregados básicos se existirem no DOM
      // Preencher agregados principais. NOTE: não preenchermos 'fora' automaticamente
      // porque agora o campo 'não-efetivo confinado' é editável pelo usuário.
      var pairs = [
        ['sup-total-atividades','total_atividade_min'],
        ['sup-total-confinado','total_confinado_min'],
        ['sup-total-abertura-pt','total_abertura_pt_min'],
        ['sup-total-atividades-efetivas','total_atividades_efetivas_min']
      ];
      pairs.forEach(function(p){ var el = document.getElementById(p[0]); if (el && (r[p[1]] != null)) el.value = String(r[p[1]]); });

      // Preencher acumulados (várias chaves possíveis no payload do backend)
      try {
        var ensAcu = (r.ensacamento_cumulativo != null ? r.ensacamento_cumulativo : (r.ensacamento_acu != null ? r.ensacamento_acu : (r.ensacamento_total != null ? r.ensacamento_total : null)));
        var icaAcu = (r.icamento_cumulativo != null ? r.icamento_cumulativo : (r.icamento_acu != null ? r.icamento_acu : null));
        var cambAcu = (r.cambagem_cumulativo != null ? r.cambagem_cumulativo : (r.cambagem_acu != null ? r.cambagem_acu : null));
        var ensAcuEl = document.getElementById('sup-ensac-acu');
        var icaAcuEl = document.getElementById('sup-ica-acu');
        var cambAcuEl = document.getElementById('sup-camba-acu');
        if (ensAcuEl && ensAcu != null) ensAcuEl.value = String(ensAcu);
        if (icaAcuEl && icaAcu != null) icaAcuEl.value = String(icaAcu);
        if (cambAcuEl && cambAcu != null) cambAcuEl.value = String(cambAcu);
      } catch(e) { /* noop */ }
      // Preencher campos de Limpeza no modal Supervisor (se presentes)
      try {
        var _pick = function(obj, keys){ for (var i=0;i<keys.length;i++){ var k = keys[i]; if (typeof obj[k] !== 'undefined' && obj[k] !== null) return obj[k]; } return null; };
        var pl = _pick(r, ['percentual_limpeza', 'avanco_limpeza', 'limpeza', 'percentual_limpeza_diario']);
        var plc = _pick(r, ['percentual_limpeza_cumulativo', 'limpeza_acu', 'limpeza_acumulado', 'percentual_limpeza_acu']);
        var plf = _pick(r, ['percentual_limpeza_fina', 'avanco_limpeza_fina', 'limpeza_fina']);
        var plfc = _pick(r, ['percentual_limpeza_fina_cumulativo', 'limpeza_fina_acu', 'limpeza_fina_acumulado']);
        try { var supL = document.getElementById('sup-limp'); if (supL && pl != null) supL.value = String(pl); } catch(_){ }
        try { var supLA = document.getElementById('sup-limp-acu'); if (supLA && plc != null) supLA.value = String(plc); } catch(_){ }
        try { var supLF = document.getElementById('sup-limp-fina'); if (supLF && plf != null) supLF.value = String(plf); } catch(_){ }
        try { var supLFA = document.getElementById('sup-limp-fina-acu'); if (supLFA && plfc != null) supLFA.value = String(plfc); } catch(_){ }
      } catch(_) { /* noop */ }
      // Popular o campo editável de não-efetivo confinado se o backend enviar o valor
      try {
        var confEl = document.getElementById('sup-total-n-efetivo-confinado');
        if (confEl) {
          // o backend pode enviar tanto a chave com '_min' quanto o valor simples
          var v = (r.total_n_efetivo_confinado_min != null) ? r.total_n_efetivo_confinado_min : (r.total_n_efetivo_confinado != null ? r.total_n_efetivo_confinado : null);
          if (v != null) confEl.value = String(v);
        }
      } catch(e) { /* noop */ }
    } catch(e){ console.warn('fetchAndPopulateRdo failed', e); }
  }

  // Preencher o campo RDO com rdo_count + 1 quando possível.
  async function populateNextRdoIfNeeded(ctx){
    try {
      if (!ctx) ctx = {};
      var supRdoEl = document.getElementById('sup-rdo');
      var contratoEl = document.getElementById('sup-contrato-po');
      if (contratoEl && typeof ctx.contrato_po !== 'undefined') { try { contratoEl.value = ctx.contrato_po || ''; } catch(_){} }
      if (!supRdoEl) return;
      var rc = ctx.rdo_count || '';
      // Se temos os_id, preferimos consultar o servidor (fonte de verdade)
      // porque a marcação local data-rdo-count pode refletir um RDO antigo
      // (por exemplo: a linha exibida na tabela pode ser o RDO 1 mesmo que já
      // existam RDOs 1 e 2). Só usar o incremento local quando NÃO houver
      // os_id disponível.
      var osId = ctx.os_id || '';
      // se não temos os_id e rdo_count é número, usar +1 localmente
      if ((!osId || String(osId).trim() === '') && rc != null && String(rc).trim() !== '' && /^\d+$/.test(String(rc).trim())) {
        try { supRdoEl.value = String(parseInt(String(rc).trim(),10) + 1); return; } catch(_){ }
      }
  if (!osId) return;
  // mostrar placeholder de carregamento na UI para feedback visual
  try { supRdoEl.dataset.prev = supRdoEl.value || ''; supRdoEl.value = 'Carregando...'; } catch(_){}
      // tentar múltiplos caminhos possíveis para o endpoint, por compatibilidade
      var candidates = [
        '/rdo/next_rdo/?os_id=',
        '/rdo/next/?os_id=',
        '/api/rdo/next/?os_id=',
        '/api/rdo/next_rdo/?os_id=',
        '/rdo/next_rdo?os_id=',
        '/rdo/next?os_id='
      ];
      for (var i=0;i<candidates.length;i++){
        try {
          var url = candidates[i] + encodeURIComponent(osId);
          var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
          if (!resp.ok) continue;
          var data = await resp.json();
          if (!data || !data.success) continue;
          // Accept multiple possible keys returned by different implementations
          var next = null;
          if (typeof data.next_rdo !== 'undefined') next = data.next_rdo;
          else if (typeof data.next !== 'undefined') next = data.next;
          else if (typeof data.rdo !== 'undefined') next = data.rdo;
          else if (typeof data.next_r !== 'undefined') next = data.next_r;
          if (next == null) continue;
          try { supRdoEl.value = String(next); } catch(_){ }
          // sucesso, encerrar tentativas
          return;
        } catch(e){ /* tentar próximo */ }
      }
      // nenhuma tentativa teve sucesso — restaurar valor anterior se existir
      try { if (typeof supRdoEl.dataset !== 'undefined' && typeof supRdoEl.dataset.prev !== 'undefined') supRdoEl.value = supRdoEl.dataset.prev || ''; } catch(_){}
    } catch(e){ console.warn('populateNextRdoIfNeeded failed', e); }
  }

  function buildSupervisorFormData(form){
    if (!form) form = qs('#form-supervisor');
    var fd = null;
      if (window.buildSupervisorFormDataExternal && typeof window.buildSupervisorFormDataExternal === 'function') {
        try { fd = window.buildSupervisorFormDataExternal(form); } catch(e){ console.warn('External builder failed, fallback used', e); fd = null; }
      }
      if (!fd) fd = new FormData();
      // Normalizador local para `sentido_limpeza` — garante tokens canônicos no envio
      function _normalizeSentido(raw){
        try{
          if (raw == null) return '';
          var s = String(raw).trim(); if (!s) return '';
          var low = s.toLowerCase();
          // Already canonical?
          var canon = ['vante > ré','ré > vante','bombordo > boreste','boreste < bombordo'];
          for (var i=0;i<canon.length;i++){ if (low === canon[i].toLowerCase()) return canon[i]; }
          // boolean/short aliases
          if (low === 'true' || low === 'sim' || low === 'vante' || low === 'vante->ré' || low === 'vante-para-ré' || low === 'vante para ré') return 'vante > ré';
          if (low === 'false' || low === 'nao' || low === 'não' || low === 'ré' || low === 'ré->vante' || low === 'ré-para-vante' || low === 'ré para vante') return 'ré > vante';
          // phrase matching for PT labels
          if (low.indexOf('vante') !== -1 && low.indexOf('ré') !== -1){ if (low.indexOf('vante') < low.indexOf('ré')) return 'vante > ré'; else return 'ré > vante'; }
          if (low.indexOf('bombordo') !== -1 && low.indexOf('boreste') !== -1){ if (low.indexOf('bombordo') < low.indexOf('boreste')) return 'bombordo > boreste'; else return 'boreste < bombordo'; }
          // fallback: return raw string (backend will canonicalize server-side as well)
          return s;
        } catch(_){ return String(raw||''); }
      }

      Array.prototype.forEach.call(form.elements, function(el){
      if (!el || !el.name) return;
      // Skip file inputs here (handled later)
      if (el.type === 'file') return;
      // Skip unchecked checkboxes/radios
      if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return;
      // IMPORTANT: avoid including inputs that live inside the activities/team wrappers
      // because we'll serialize those sections explicitly to keep ordering and avoid
      // duplicated hidden/template inputs that may have been cloned.
      try {
        if (el.closest && (el.closest('#atividades-wrapper') || el.closest('#equipe-wrapper'))) return;
      } catch(_){ }
        // Skip inputs that belong to dynamic activities/team rows. These are serialized
        // explicitly later to avoid duplicate array entries when template/clone
        // nodes exist inside the form.
        try {
          if (el.closest && (el.closest('.activities-row') || el.closest('.team-row'))) return;
        } catch(_){ }
        // Ensure sentido_limpeza is normalized to canonical token strings
        try {
          if (el.name === 'sentido_limpeza') {
            try { fd.append(el.name, _normalizeSentido(el.value || '')); }
            catch(e){ fd.append(el.name, el.value); }
          } else {
            fd.append(el.name, el.value);
          }
        } catch(_){ try { fd.append(el.name, el.value); } catch(__){} }
    });
  // anexar fotos (name="fotos" multiple)
    var fInputs = qsa('input[type=file][name="fotos"]', form);
    // coletar arquivos brutos
    var rawFiles = [];
    fInputs.forEach(function(inp){ if (inp.files) Array.prototype.forEach.call(inp.files, function(f){ rawFiles.push(f); }); });
    // Enviar arquivos como 'fotos' e 'fotos[]' para máxima compatibilidade
    try {
      rawFiles.forEach(function(f){
        fd.append('fotos', f);    // padrão Django: request.FILES.getlist('fotos')
        fd.append('fotos[]', f);  // legado: caso backend espere fotos[]
      });
    } catch(e){ /* ignore file appends on failure */ }
    // Normalize percentual supervisor fields so backend receives plain numeric strings
    try {
      function _normPercent(s){
        if (s == null) return '';
        var t = String(s).trim();
        if (!t) return '';
        if (t.slice(-1) === '%') t = t.slice(0, -1).trim();
        t = t.replace(',', '.');
        if (/^-?\d+(?:\.\d+)?$/.test(t)) return t;
        // fallback: try parseInt
        var i = parseInt(t, 10);
        return isNaN(i) ? '' : String(i);
      }
      var superKeys = ['sup-limp','sup-limp-acu','sup-limp-fina','sup-limp-fina-acu'];
      // Alternative selectors map: if the supervisor UI uses different input ids/names
      // (legacy or translated), check these alternatives so we don't miss values.
      var altMap = {
        'sup-limp': ['#limpeza_mecanizada_diaria', 'input[name="limpeza_mecanizada_diaria"]', '#percentual_limpeza', 'input[name="percentual_limpeza"]'],
        'sup-limp-fina': ['#limpeza_fina_diaria', 'input[name="limpeza_fina_diaria"]', '#percentual_limpeza_fina', 'input[name="percentual_limpeza_fina"]'],
        'sup-limp-acu': ['#limpeza_mecanizada_cumulativa', 'input[name="limpeza_mecanizada_cumulativa"]', '#percentual_limpeza_cumulativo', 'input[name="percentual_limpeza_cumulativo"]'],
        'sup-limp-fina-acu': ['#limpeza_fina_cumulativa', 'input[name="limpeza_fina_cumulativa"]', '#percentual_limpeza_fina_cumulativo', 'input[name="percentual_limpeza_fina_cumulativo"]']
      };
      // NOTE: suportes a inputs canônicos por-tanque foram removidos intencionalmente.
      // Não adicionamos selectors alternativos para 'limpeza_manual_*_tanque' porque
      // o front-end não deve mais enviar esses nomes ao servidor (os campos
      // permanecem apenas declarados no modelo para compatibilidade histórica).

      function _findElForKey(form, k){
        var el = form.querySelector('#' + k) || form.querySelector('input[name="' + k + '"]') || null;
        if (el) return el;
        var alts = altMap[k] || [];
        for (var i=0;i<alts.length;i++){
          try { var sel = alts[i]; var e = form.querySelector(sel); if (e) return e; } catch(_){ }
        }
        return null;
      }

      superKeys.forEach(function(k){
        try {
          var el = _findElForKey(form, k);
          if (!el) return;
          var val = _normPercent(el.value || el.textContent || '');
          // decide canonical names to set / delete
          var canonicalSet = [];
          var canonicalDelete = [];
          if (k === 'sup-limp') { canonicalSet.push(['avanco_limpeza','limpeza_mecanizada_diaria']); canonicalDelete.push('avanco_limpeza'); canonicalDelete.push('limpeza_mecanizada_diaria'); }
          else if (k === 'sup-limp-fina') { canonicalSet.push(['avanco_limpeza_fina','limpeza_fina_diaria']); canonicalDelete.push('avanco_limpeza_fina'); canonicalDelete.push('limpeza_fina_diaria'); }
          else if (k === 'sup-limp-acu') { canonicalSet.push(['limpeza_acu','limpeza_mecanizada_cumulativa','percentual_limpeza_cumulativo']); canonicalDelete.push('limpeza_acu'); canonicalDelete.push('limpeza_mecanizada_cumulativa'); canonicalDelete.push('percentual_limpeza_cumulativo'); }
          else if (k === 'sup-limp-fina-acu') { canonicalSet.push(['limpeza_fina_acu','limpeza_fina_cumulativa','percentual_limpeza_fina_cumulativo']); canonicalDelete.push('limpeza_fina_acu'); canonicalDelete.push('limpeza_fina_cumulativa'); canonicalDelete.push('percentual_limpeza_fina_cumulativo'); }

            if (val !== '') {
            // set/update the form key (legacy id/name)
            try { if (typeof fd.set === 'function') fd.set(k, val); else fd.append(k, val); } catch(_){ }
            // set also canonical backend names (multiple aliases)
            canonicalSet.forEach(function(arr){
              for (var ii=0; ii<arr.length; ii++){
                try { if (typeof fd.set === 'function') fd.set(arr[ii], val); else fd.append(arr[ii], val); } catch(_){ }
              }
            });
            // NOTE: não definimos mais os campos canônicos por-tanque
            // ('limpeza_manual_diaria_tanque', 'limpeza_manual_cumulativa_tanque',
            // 'limpeza_fina_cumulativa_tanque') aqui — isso foi removido
            // intencionalmente para evitar envio/alteração desses nomes.
          } else {
            try { if (typeof fd.delete === 'function') fd.delete(k); } catch(_){ }
            // delete canonical names when empty
            canonicalDelete.forEach(function(nm){ try { if (typeof fd.delete === 'function') fd.delete(nm); } catch(_){ } });
          }
        } catch(_){ }
      });
    } catch(_){ }
    // --- Serializar explicitamente atividades e equipe a partir das linhas visíveis ---
    try {
      // Atividades: considerar wrappers do supervisor e do editor
      var atividadesWrappers = [];
      try {
        var w1 = form.querySelector('#atividades-wrapper'); if (w1) atividadesWrappers.push(w1);
      } catch(_){ }
      try {
        var w2 = form.querySelector('#edit-atividades-wrapper'); if (w2) atividadesWrappers.push(w2);
      } catch(_){ }
      var seenAt = new Set();
      atividadesWrappers.forEach(function(atividadesWrapper){
        var atRows = atividadesWrapper.querySelectorAll('.activities-row');
        Array.prototype.forEach.call(atRows, function(row){
          try {
            var nome = '';
            var sel = row.querySelector('.atividade-nome-select, select[name="atividade_nome[]"]');
            if (sel) nome = (sel.value || '').trim();
            var inicio = '';
            var inpInicio = row.querySelector('input.atividade-inicio, input[name="atividade_inicio[]"]');
            if (inpInicio) inicio = (inpInicio.value || '').trim();
            var fim = '';
            var inpFim = row.querySelector('input.atividade-fim, input[name="atividade_fim[]"]');
            if (inpFim) fim = (inpFim.value || '').trim();
            var cpt = '';
            var cptEl = row.querySelector('.atividade-comentario-pt, input[name="atividade_comentario_pt[]"], textarea[name="atividade_comentario_pt[]"]');
            if (cptEl) cpt = (cptEl.value || '').trim();
            var cen = '';
            var cenEl = row.querySelector('.atividade-comentario-en, input[name="atividade_comentario_en[]"], textarea[name="atividade_comentario_en[]"]');
            if (cenEl) cen = (cenEl.value || '').trim();
            // Only append rows that have at least a name or a comment or times (avoid empty template rows)
            if ((nome !== '') || (cpt !== '') || (inicio !== '') || (fim !== '')) {
              // Dedupe exact duplicates to avoid automatic double entries
              var key = [nome, inicio, fim, cpt, cen].join('|');
              if (seenAt.has(key)) return;
              seenAt.add(key);
              fd.append('atividade_nome[]', nome);
              fd.append('atividade_inicio[]', inicio);
              fd.append('atividade_fim[]', fim);
              fd.append('atividade_comentario_pt[]', cpt);
              fd.append('atividade_comentario_en[]', cen);
            }
          } catch(_){ }
        });
      });

      // Equipe: considerar wrappers do supervisor e do editor
      var equipeWrappers = [];
      try { var ew1 = form.querySelector('#equipe-wrapper'); if (ew1) equipeWrappers.push(ew1); } catch(_){ }
      try { var ew2 = form.querySelector('#edit-equipe-wrapper'); if (ew2) equipeWrappers.push(ew2); } catch(_){ }
      var seenEq = new Set();
      equipeWrappers.forEach(function(equipeWrapper){
        var memRows = equipeWrapper.querySelectorAll('.team-row');
        Array.prototype.forEach.call(memRows, function(row){
          try {
            var nome = '';
            var nomeEl = row.querySelector('.equipe-nome, input[name="equipe_nome[]"]');
            if (nomeEl) nome = (nomeEl.value || '').trim();
            var func = '';
            var funcEl = row.querySelector('.equipe-funcao, input[name="equipe_funcao[]"]');
            if (funcEl) func = (funcEl.value || '').trim();
            var ems = '';
            var emsEl = row.querySelector('input[name="equipe_em_servico[]"]');
            if (emsEl) {
              if (emsEl.type === 'checkbox' || emsEl.type === 'radio') ems = emsEl.checked ? '1' : '0'; else ems = (emsEl.value || '').trim();
            }
            var pid = '';
            var pidEl = row.querySelector('input[name="equipe_pessoa_id[]"]');
            if (pidEl) pid = (pidEl.value || '').trim();
            if ((nome !== '') || (func !== '') || (pid !== '')) {
              var k2 = [pid, nome, func, ems].join('|');
              if (seenEq.has(k2)) return;
              seenEq.add(k2);
              fd.append('equipe_nome[]', nome);
              fd.append('equipe_funcao[]', func);
              fd.append('equipe_em_servico[]', ems);
              fd.append('equipe_pessoa_id[]', pid);
            }
          } catch(_){ }
        });
      });
    } catch(_){ }

    // Fallback: se nenhum arquivo foi coletado dos inputs (alguns navegadores podem
    // limpar input.files após manipulações), tente anexar arquivos a partir do
    // DataTransfer exposto em window._supvPhotoDT (inicializado em _initSupervisorPhotoPreviews).
    try {
      // verificar se já existe alguma entrada 'fotos' no FormData
      var hasFotos = false;
      try {
        if (typeof fd.entries === 'function') {
          var it = fd.entries(); var ne = it.next();
          while (!ne.done) { if (ne.value && ne.value[0] && String(ne.value[0]).indexOf('fotos') === 0) { hasFotos = true; break; } ne = it.next(); }
        }
      } catch(_){ /* ignore */ }

      if (!hasFotos && window && window._supvPhotoDT && window._supvPhotoDT.files && window._supvPhotoDT.files.length) {
        try {
          Array.prototype.forEach.call(window._supvPhotoDT.files, function(f){
            try { fd.append('fotos', f); } catch(_){ }
            try { fd.append('fotos[]', f); } catch(_){ }
          });
        } catch(_){ }
      }
    } catch(_){ }

    return fd;
  }

  // Sincronizar campo "Ensacamento (Previsão)" -> "Içamento (Previsão)"
  // Usuário preenche ensacamento_prev e o valor é automaticamente copiado para icamento_prev
  onReady(function(){
    try{
      var ensac = qs('#sup-prev-ensac');
      var ica = qs('#sup-prev-ica');
      if (ensac && ica) {
        // copiar no input e também no evento change para compatibilidade
        ensac.addEventListener('input', function(){
          try{ ica.value = ensac.value; }catch(e){}
        }, false);
        // garantir cópia ao perder o foco
        ensac.addEventListener('change', function(){
          try{ ica.value = ensac.value; }catch(e){}
        }, false);
      }
    }catch(e){ console.warn('sync ensac->ica failed', e); }
  });

  // Escutar cliques de remoção nas fotos exibidas para marcar remoção por slot
  function initPhotoRemoveHandlers(context){
    var container = context || document;
    // delegado: escuta no container principal
    container.addEventListener('click', function(ev){
      try {
        var btn = ev.target.closest && ev.target.closest('.photo-remove');
        if (!btn) return;
        ev.preventDefault();
        var item = btn.closest && btn.closest('.photo-slot');
        var slotName = item && item.getAttribute ? item.getAttribute('data-slot-name') : null;
        var form = document.getElementById('form-supervisor') || document.getElementById('form-editor') || document.querySelector('form');
        if (slotName && form) {
          // inserir um hidden para indicar remoção do slot
          var inp = document.createElement('input'); inp.type = 'hidden'; inp.name = 'fotos_remove[]'; inp.value = slotName; form.appendChild(inp);
        } else if (item) {
          // sem slot definido: enviar identificador genérico (url)
          var url = item.getAttribute('data-url') || null;
          if (form && url) {
            var inp2 = document.createElement('input'); inp2.type = 'hidden'; inp2.name = 'fotos_remove[]'; inp2.value = url; form.appendChild(inp2);
          }
        }
        // Remover visualmente o item
        try { item && item.remove(); } catch(_){ btn.remove(); }
      } catch(e){ console.warn('photo-remove handler failed', e); }
    }, false);
  }

  // Inicializar handlers ao carregar o script
  onReady(function(){ initPhotoRemoveHandlers(document); });

  // Remover cartões mobile finalizados apenas para supervisor (client-side/mobile)
  function isMobileViewport(){
    try { return window.matchMedia && window.matchMedia('(max-width: 767px)').matches; } catch(e){ return (window.innerWidth || document.documentElement.clientWidth) < 768; }
  }

  function removeFinalizedCardsForSupervisor(){
    try {
      var site = document.getElementById('site-wrapper');
      if (!site) return;
      var isSupervisor = (site.getAttribute('data-is-supervisor') || '').toString().toLowerCase() === 'true';
      if (!isSupervisor) return; // only for supervisor
      if (!isMobileViewport()) return; // only on narrow/mobile view
      var cards = qsa('.rdo-mobile-card.rdo-mobile-item');
      if (!cards || !cards.length) return;
      var finalRe = /finaliz|encerrad|fechad|conclu|retorn/i;
      cards.forEach(function(card){
        try {
          var st = (card.getAttribute('data-status-geral') || '').toString();
          if (finalRe.test(st)) {
            card.remove();
          }
        } catch(_){}
      });
    } catch(e){ console.warn('removeFinalizedCardsForSupervisor failed', e); }
  }

  // Run on load and when the viewport changes (simple resize listener)
  onReady(function(){
    try { removeFinalizedCardsForSupervisor(); } catch(_){}
    var resizeDebounce = null;
    window.addEventListener('resize', function(){
      try {
        if (resizeDebounce) clearTimeout(resizeDebounce);
        resizeDebounce = setTimeout(function(){ removeFinalizedCardsForSupervisor(); }, 220);
      } catch(_){}
    }, { passive: true });
  });

  // Inicializar pré-visualização de fotos e gerenciamento via DataTransfer
  // (migrado do inline script em templates/rdo.html)
  function _initSupervisorPhotoPreviews(){
    try{
      var MAX_PHOTOS = 5;
      var input = document.getElementById('sup-fotos');
      var btn = document.getElementById('btn-add-foto');
      var previews = document.getElementById('supv-photo-previews');
      if (!input || !btn || !previews) return;

      // Use DataTransfer to manage files programmatically
      var dt = new DataTransfer();

      function renderPreviews(){
        // limpar previews
        previews.innerHTML = '';
        Array.prototype.forEach.call(dt.files, function(file, idx){
          try{
            var url = URL.createObjectURL(file);
            var slot = document.createElement('div');
            slot.className = 'photo-slot';
            slot.style.width = '92px';
            slot.style.height = '92px';
            slot.style.position = 'relative';
            slot.style.borderRadius = '8px';
            slot.style.overflow = 'hidden';
            slot.style.background = '#f6f6f6';
            slot.style.boxShadow = '0 6px 18px rgba(0,0,0,0.06)';

            var img = document.createElement('img');
            img.src = url;
            img.style.width = '100%';
            img.style.height = '100%';
            img.style.objectFit = 'cover';
            img.alt = file.name;
            // store objectURL to revoke later
            img.dataset.objectUrl = url;
            slot.appendChild(img);

            var remove = document.createElement('button');
            remove.type = 'button';
            remove.setAttribute('aria-label', 'Remover foto');
            remove.className = 'photo-remove';
            remove.style.position = 'absolute';
            remove.style.right = '6px';
            remove.style.top = '6px';
            remove.style.background = 'rgba(0,0,0,0.6)';
            remove.style.color = '#fff';
            remove.style.border = 'none';
            remove.style.borderRadius = '8px';
            remove.style.padding = '6px';
            remove.textContent = '✕';
            remove.addEventListener('click', function(){
              try{
                var files = Array.prototype.slice.call(dt.files);
                files.splice(idx, 1);
                // rebuild DataTransfer
                var newDt = new DataTransfer();
                files.forEach(function(f){ newDt.items.add(f); });
                // replace items in dt
                while(dt.items.length) dt.items.remove(0);
                Array.prototype.forEach.call(newDt.files, function(f){ dt.items.add(f); });
                input.files = dt.files;
                // revoke object URL used by this slot (if present)
                try{ if (img && img.dataset && img.dataset.objectUrl) URL.revokeObjectURL(img.dataset.objectUrl); }catch(_){ }
                renderPreviews();
              }catch(_){ renderPreviews(); }
            });
            slot.appendChild(remove);

            previews.appendChild(slot);
          }catch(e){ console.warn('render preview item failed', e); }
        });
        // disable add button if max reached
        try{ btn.disabled = dt.files.length >= MAX_PHOTOS; }catch(_){ }
      }

      btn.addEventListener('click', function(){ input.click(); });

      input.addEventListener('change', function(e){
        try{
          var files = Array.prototype.slice.call(e.target.files || []);
          for (var i=0;i<files.length;i++){
            if (dt.files.length >= MAX_PHOTOS) break;
            dt.items.add(files[i]);
          }
          input.files = dt.files; // sync
          renderPreviews();
        }catch(e){ console.warn('supv photo change failed', e); }
  // Note: do NOT reset the native input.value here — clearing it may also
  // clear input.files in some browsers after we assigned dt.files above.
  // We keep input.files = dt.files so buildSupervisorFormData can read them.
      });

      // expose for debugging if needed
      try{ window._supvPhotoDT = dt; }catch(_){ }
    }catch(e){ console.warn('initSupervisorPhotoPreviews failed', e); }
  }

  // Register to run once DOM is ready
  onReady(_initSupervisorPhotoPreviews);

  // Small dev helper: wire debug button to open supervisor modal (moved from template inline)
  function _initSupvOpenDebug(){
    try{
      var btn = document.getElementById('supv-open-debug');
      if (!btn) return;
      btn.addEventListener('click', function(){
        try {
          var overlay = document.getElementById('supv-modal-overlay');
          if (!overlay) return alert('Overlay do Supervisor não encontrado');
          overlay.classList.add('open'); overlay.setAttribute('aria-hidden','false');
          try { var f = overlay.querySelector('input,select,textarea,button'); if (f) f.focus(); } catch(_){ }
        } catch(e){ console.warn('open debug failed', e); }
      });
    }catch(e){}
  }
  onReady(_initSupvOpenDebug);

  // Bind para bloquear/desbloquear campos de Permissão de Trabalho (PT)
  function _bindPTFieldsToggle(){
    try {
      // injetar estilos mínimos apenas uma vez para melhorar UX do bloqueio PT
      try {
        if (!document.getElementById('rdo-pt-lock-styles')) {
          var st = document.createElement('style'); st.id = 'rdo-pt-lock-styles';
          st.type = 'text/css';
          st.appendChild(document.createTextNode('\n.rdo-pt-locked { opacity: 0.6; transition: opacity .18s ease; }\n.rdo-pt-locked .form-field { pointer-events: auto; }\n.rdo-pt-locked input[disabled], .rdo-pt-locked select[disabled], .rdo-pt-locked textarea[disabled] { background: #f5f5f5; color: #888; }\n.supv-pt-lock-icon { margin-left: 8px; font-size: 14px; opacity: 0.9; }\n'));
          document.head.appendChild(st);
        }
      } catch(_){ }
      var sel = document.getElementById('sup-pt-abertura');
      if (!sel) return;
      if (sel.__ptToggleBound) return; // idempotente

      function setLocked(isLocked){
        try {
          var wrapper = document.querySelector('#sec-pt');
          if (!wrapper) return;
          // campos que dependem de PT
          var inputs = wrapper.querySelectorAll('input[name^="pt_num_"], input[name="pt_num_manha"], input[name="pt_num_tarde"], input[name="pt_num_noite"], input[type="checkbox"][name="pt_turnos[]"]');
          // adicionar/remover classe visual
          if (isLocked) wrapper.classList.add('rdo-pt-locked'); else wrapper.classList.remove('rdo-pt-locked');
          Array.prototype.forEach.call(inputs, function(i){ try { i.disabled = !!isLocked; if (isLocked) { if (i.type === 'checkbox') i.checked = false; else i.value = ''; } }catch(_){}});

          // inserir/remover indicador de cadeado no header da seção
          var hdr = wrapper.querySelector('.rdo-section__head');
          if (hdr) {
            var key = hdr.querySelector('.supv-pt-lock-icon');
            if (isLocked && !key) {
              var span = document.createElement('span');
              span.className = 'supv-pt-lock-icon';
              span.title = 'Campos de PT bloqueados';
              span.setAttribute('aria-hidden','false');
              span.style.marginLeft = '10px';
              span.style.fontSize = '14px';
              span.textContent = '🔒';
              hdr.appendChild(span);
            } else if (!isLocked && key) {
              try { key.parentNode && key.parentNode.removeChild(key); } catch(_){ }
            }
          }
        } catch(e){ console.warn('setLocked PT failed', e); }
      }

      function handler(ev){
        try { var v = (sel.value || '').toString().toLowerCase().trim(); setLocked(v === 'nao' || v === 'não' || v === 'naõ'); } catch(e){}
      }

      sel.addEventListener('change', handler);
      // initial state
      setLocked(((sel.value||'').toString().toLowerCase().trim() === 'nao' || (sel.value||'').toString().toLowerCase().trim() === 'não'));
      sel.__ptToggleBound = true;
    } catch(e){ console.warn('_bindPTFieldsToggle failed', e); }
  }
  onReady(_bindPTFieldsToggle);

  // Inject minimal CSS to style automatic (locked) fields — idempotent
  function _injectAutoLockedStyles(){
    try {
      if (document.getElementById('rdo-auto-locked-styles')) return;
      var st = document.createElement('style'); st.id = 'rdo-auto-locked-styles';
      st.type = 'text/css';
      st.appendChild(document.createTextNode('\n.rdo-auto-locked { position: relative; }\n.rdo-auto-locked label { display: inline-flex; align-items: center; gap: 8px; }\n.rdo-auto-locked .auto-lock-icon { font-size: 14px; opacity: 0.9; margin-left: 6px; color: #555; }\n.rdo-auto-locked input[readonly], .rdo-auto-locked input[disabled] { background: #f5f5f5; color: #666; }\n'));
      document.head.appendChild(st);
    } catch(e){ /* noop */ }
  }
  onReady(_injectAutoLockedStyles);

  // On page load, mark previous RDOs as locked per OS: for each OS group, find the
  // maximum rdo_count and mark any row/card with rdo_count < max as locked. This
  // prevents users from opening older RDOs once a newer one exists.
  function _lockPreviousRdosOnLoad(){
    try {
      // gather rows and cards that contain os identifier and rdo_count
      var rows = document.querySelectorAll('tr[data-os-id][data-rdo-count], tr[data-numero-os][data-rdo-count]');
      var cards = document.querySelectorAll('.rdo-mobile-card[data-os-id][data-rdo-count], .rdo-mobile-card[data-os][data-rdo-count], .rdo-mobile-item[data-os-id][data-rdo-count]');
      var map = Object.create(null);
      function normKey(osId, numeroOs){ return String(osId || numeroOs || '').trim(); }
      Array.prototype.forEach.call(rows, function(tr){
        try {
          var osId = tr.getAttribute('data-os-id') || tr.getAttribute('data-numero-os') || '';
          var key = normKey(osId, tr.getAttribute('data-numero-os'));
          if (!key) return;
          var rc = parseInt(String(tr.getAttribute('data-rdo-count') || tr.dataset && tr.dataset.rdoCount || '0').replace(/[^0-9]/g,''),10) || 0;
          if (!map[key] || map[key] < rc) map[key] = rc;
        } catch(_){ }
      });
      Array.prototype.forEach.call(cards, function(c){
        try {
          var osId = c.getAttribute('data-os-id') || c.getAttribute('data-os') || '';
          var key = normKey(osId, c.getAttribute('data-os'));
          if (!key) return;
          var rc = parseInt(String(c.getAttribute('data-rdo-count') || c.dataset && c.dataset.rdoCount || '0').replace(/[^0-9]/g,''),10) || 0;
          if (!map[key] || map[key] < rc) map[key] = rc;
        } catch(_){ }
      });

      // now lock any element with rdo_count < max for that os
      function lockElement(el){
        try {
          if (!el) return;
          if (el.classList && el.classList.contains('rdo-locked')) return;
          el.classList.add('rdo-locked');
          if (!el.querySelector('.rdo-lock-icon')){
            var ico = document.createElement('span'); ico.className = 'rdo-lock-icon material-icons'; ico.setAttribute('aria-hidden','true'); ico.textContent = 'lock';
            // prefer appending to the element so it floats in the right place
            el.appendChild(ico);
          }
        } catch(_){ }
      }

      Array.prototype.forEach.call(rows, function(tr){
        try {
          var osId = tr.getAttribute('data-os-id') || tr.getAttribute('data-numero-os') || '';
          var key = normKey(osId, tr.getAttribute('data-numero-os'));
          if (!key) return;
          var rc = parseInt(String(tr.getAttribute('data-rdo-count') || tr.dataset && tr.dataset.rdoCount || '0').replace(/[^0-9]/g,''),10) || 0;
          var max = map[key] || 0;
          // localizar o botão de abrir dentro da linha (apenas para linhas de tabela)
          var openBtn = null;
          try { openBtn = tr.querySelector('.open-supervisor, .btn-rdo.open-supervisor, .action-btn.open-supervisor'); } catch(_){ openBtn = null; }
          if (rc && max && rc < max) {
            lockElement(tr);
            // Desabilitar apenas o botão de abrir (manter outros botões funcionais)
            if (openBtn) {
              try {
                openBtn.classList.add('disabled');
                openBtn.disabled = true;
                openBtn.setAttribute('aria-disabled','true');
                // store message in data-tooltip so we can show a styled tooltip (avoid native title)
                openBtn.setAttribute('data-tooltip','Abrir disponível apenas a partir do último RDO (RDO ' + String(max) + ')');
              } catch(_){ }
            }
          } else {
            // garantir que o botão de abrir esteja habilitado quando esta for a linha mais recente
            if (openBtn) {
              try {
                openBtn.classList.remove('disabled');
                openBtn.disabled = false;
                openBtn.removeAttribute('aria-disabled');
                // remover title informativo caso seja o que colocamos automaticamente
                try {
                  var d = openBtn.getAttribute('data-tooltip');
                  if (d && d.indexOf('Abrir disponível apenas') === 0) openBtn.removeAttribute('data-tooltip');
                } catch(_){ }
              } catch(_){ }
            }
          }
        } catch(_){ }
      });

      Array.prototype.forEach.call(cards, function(c){
        try {
          var osId = c.getAttribute('data-os-id') || c.getAttribute('data-os') || '';
          var key = normKey(osId, c.getAttribute('data-os'));
          if (!key) return;
          var rc = parseInt(String(c.getAttribute('data-rdo-count') || c.dataset && c.dataset.rdoCount || '0').replace(/[^0-9]/g,''),10) || 0;
          var max = map[key] || 0;
          if (rc && max && rc < max) lockElement(c);
        } catch(_){ }
      });
    } catch(e){ console.warn('_lockPreviousRdosOnLoad failed', e); }
  }
  onReady(_lockPreviousRdosOnLoad);

  // Remove mobile supervisor cards when the corresponding OS is finalized in the table
  function _removeFinalizedMobileCardsOnLoad(){
    try {
      var rows = document.querySelectorAll('table tbody tr');
      // Se existirem linhas de tabela, use-as para mapear e remover cards correspondentes
      if (rows && rows.length) {
        Array.prototype.forEach.call(rows, function(tr){
          try {
            // read several possible status attributes
            var status = (tr.getAttribute('data-status-geral') || tr.getAttribute('data-status') || tr.getAttribute('data-status-frente') || tr.getAttribute('data-status_frente') || '');
            status = (status || '').toString().toLowerCase().trim();
            // if no attribute, inspect td text content for typical finalization keywords
            if (!status) {
              var tds = tr.querySelectorAll('td');
              for (var i=0;i<tds.length;i++){
                try {
                  var t = (tds[i].textContent || '').toString().toLowerCase();
                  if (/finaliz|encerrad|fechad|conclu|retorn/.test(t)) { status = t; break; }
                } catch(_){ }
              }
            }
            if (!status) return;
            // consider finalized if keywords match
            if (!(/finaliz|encerrad|fechad|conclu|retorn/.test(status))) return;

            // determine matching keys for the card: prefer data-os-id, then data-numero-os, then first td (id)
            var osId = tr.getAttribute('data-os-id') || (tr.dataset && tr.dataset.osId) || '';
            var numeroOs = tr.getAttribute('data-numero-os') || (tr.dataset && tr.dataset.numeroOs) || '';
            var firstTd = tr.querySelector('td');
            var idFromCell = firstTd ? (firstTd.textContent || '').toString().trim() : '';
            var keys = [];
            if (osId) keys.push(String(osId));
            if (numeroOs && keys.indexOf(String(numeroOs))===-1) keys.push(String(numeroOs));
            if (idFromCell && keys.indexOf(String(idFromCell))===-1) keys.push(String(idFromCell));

            keys.forEach(function(k){ if (!k) return; try {
              var sels = ['.rdo-mobile-card[data-os-id="'+k+'"]', '.rdo-mobile-item[data-os-id="'+k+'"]', '.rdo-mobile-card[data-os="'+k+'"]', '.rdo-mobile-item[data-os="'+k+'"]'];
              sels.forEach(function(sel){
                try {
                  var nodes = document.querySelectorAll(sel);
                  Array.prototype.forEach.call(nodes, function(n){ try { n.remove(); } catch(_) { try { n.style.display = 'none'; } catch(_){} } });
                } catch(_){ }
              });
            } catch(_){ } });
          } catch(_){ }
        });
        return;
      }

      // Sem tabela (mobile supervisor): remova cards que já vieram com status finalizado no próprio data-atributo
      var cards = document.querySelectorAll('.rdo-mobile-card, .rdo-mobile-item');
      Array.prototype.forEach.call(cards, function(card){
        try {
          var st = (card.getAttribute('data-status-geral') || '').toString().toLowerCase().trim();
          if (st && /finaliz|encerrad|fechad|conclu|retorn/.test(st)) {
            try { card.remove(); } catch(_){ try { card.style.display = 'none'; } catch(_){} }
          }
        } catch(_){ }
      });
      Array.prototype.forEach.call(rows, function(tr){
        try {
          // read several possible status attributes
          var status = (tr.getAttribute('data-status-geral') || tr.getAttribute('data-status') || tr.getAttribute('data-status-frente') || tr.getAttribute('data-status_frente') || '');
          status = (status || '').toString().toLowerCase().trim();
          // if no attribute, inspect td text content for typical finalization keywords
          if (!status) {
            var tds = tr.querySelectorAll('td');
            for (var i=0;i<tds.length;i++){
              try {
                var t = (tds[i].textContent || '').toString().toLowerCase();
                if (/finaliz|encerrad|fechad|conclu|retorn/.test(t)) { status = t; break; }
              } catch(_){ }
            }
          }
          if (!status) return;
          // consider finalized if keywords match
          if (!(/finaliz|encerrad|fechad|conclu|retorn/.test(status))) return;

          // determine matching keys for the card: prefer data-os-id, then data-numero-os, then first td (id)
          var osId = tr.getAttribute('data-os-id') || (tr.dataset && tr.dataset.osId) || '';
          var numeroOs = tr.getAttribute('data-numero-os') || (tr.dataset && tr.dataset.numeroOs) || '';
          var firstTd = tr.querySelector('td');
          var idFromCell = firstTd ? (firstTd.textContent || '').toString().trim() : '';
          var keys = [];
          if (osId) keys.push(String(osId));
          if (numeroOs && keys.indexOf(String(numeroOs))===-1) keys.push(String(numeroOs));
          if (idFromCell && keys.indexOf(String(idFromCell))===-1) keys.push(String(idFromCell));

          keys.forEach(function(k){ if (!k) return; try {
            var sels = ['.rdo-mobile-card[data-os-id="'+k+'"]', '.rdo-mobile-item[data-os-id="'+k+'"]', '.rdo-mobile-card[data-os="'+k+'"]', '.rdo-mobile-item[data-os="'+k+'"]'];
            sels.forEach(function(sel){
              try {
                var nodes = document.querySelectorAll(sel);
                Array.prototype.forEach.call(nodes, function(n){ try { n.remove(); } catch(_) { try { n.style.display = 'none'; } catch(_){} } });
              } catch(_){ }
            });
          } catch(_){ } });
        } catch(_){ }
      });
    } catch(e){ console.warn('_removeFinalizedMobileCardsOnLoad failed', e); }
  }
  onReady(_removeFinalizedMobileCardsOnLoad);

  // Bind para bloquear Nº Compart. quando Tipo do tanque for 'Salão'
  function _bindTankTypeLock(){
    try {
      // Support locking fields for both Supervisor and Editor selects
      var selects = [document.getElementById('sup-tipo-tanque'), document.getElementById('edit-tipo-tanque')].filter(function(x){ return !!x; });
      if (!selects || !selects.length) return;

      // injetar estilos mínimos apenas uma vez (aplica aos campos bloqueados)
      try {
        if (!document.getElementById('rdo-ncomp-lock-styles')) {
          var st = document.createElement('style'); st.id = 'rdo-ncomp-lock-styles';
          st.type = 'text/css';
          st.appendChild(document.createTextNode('\n.rdo-ncomp-locked { opacity: 1; }\n.rdo-ncomp-locked input[disabled] { background:#f5f5f5; color:#888; }\n.rdo-ncomp-lock-icon { margin-left:8px; font-size:14px; opacity:0.95; vertical-align: middle; }\n'));
          document.head.appendChild(st);
        }
      } catch(_){ }

      // Helper to lock/unlock a specific input by id (adds class on wrapper, stores prev value, adds icon)
      function _lockFieldById(inputId, labelFor, title){
        try {
          var inp = document.getElementById(inputId);
          if (!inp) return;
          var field = inp.closest && inp.closest('.form-field');
          try { inp.dataset._prevVal = (typeof inp.value !== 'undefined' ? String(inp.value) : ''); } catch(_){ }
          // set sensible default for numero compartimentos
          if (inputId.indexOf('n-comp') !== -1) try { inp.value = '1'; } catch(_){ }
          inp.disabled = true;
          if (field) field.classList.add('rdo-ncomp-locked');
          if (field) {
            var lbl = field.querySelector('label[for="' + (labelFor || inputId) + '"]');
            if (lbl && !field.querySelector('.rdo-ncomp-lock-icon')) {
              var span = document.createElement('span'); span.className = 'rdo-ncomp-lock-icon'; span.title = (title || 'Campo bloqueado'); span.setAttribute('aria-hidden','true'); span.textContent = '🔒';
              lbl.appendChild(span);
            }
          }
        } catch(e){ console.warn('_lockFieldById failed', e); }
      }

      function _unlockFieldById(inputId){
        try {
          var inp = document.getElementById(inputId);
          if (!inp) return;
          var field = inp.closest && inp.closest('.form-field');
          inp.disabled = false;
          try { if (typeof inp.dataset._prevVal !== 'undefined') { inp.value = inp.dataset._prevVal || ''; delete inp.dataset._prevVal; } } catch(_){ }
          if (field) field.classList.remove('rdo-ncomp-locked');
          if (field) {
            var key = field.querySelector('.rdo-ncomp-lock-icon'); if (key) try { key.parentNode && key.parentNode.removeChild(key); } catch(_){ }
          }
        } catch(e){ console.warn('_unlockFieldById failed', e); }
      }

      // For each select, bind handler idempotently
      selects.forEach(function(sel){
        try {
          if (sel.__tankLockBound) return;
          var prefix = (sel.id === 'edit-tipo-tanque') ? 'edit' : 'sup';
          // We keep gavetas and patamar locked for tipo 'Salão', but allow
          // número de compartimentos to remain editable so the user can
          // still mark avance do compartimento (even que seja 1).
          var toLock = [prefix + '-gavetas', prefix + '-patamar'];

          function handler(){
            try {
              var v = (sel.value || '').toString().toLowerCase().trim();
              var ncompId = prefix + '-n-comp';
              var ncompEl = document.getElementById(ncompId);
              if (v === 'salão' || v === 'salao') {
                // For Salão: numero de compartimentos é 1 e deve ficar travado (não editável),
                // porém o seletor de compartimentos precisa aparecer e o compartimento 1
                // deve vir marcado como tendo avanço. Mantemos gavetas/patamar bloqueados.
                try { _lockFieldById(ncompId, ncompId, 'Número de compartimentos fixo para Salão'); } catch(_){ }
                try { toLock.forEach(function(id){ _lockFieldById(id, id, 'Campo bloqueado para tipo Salão'); }); } catch(_){ }

                // Trigger rebuild of the compartimentos selector (rdo.compartment.js listens to input/change and mutation)
                try {
                  if (ncompEl) {
                    // ensure value attribute is set and dispatch input event so the component rebuilds
                    try { ncompEl.value = '1'; } catch(_){ }
                    try { ncompEl.setAttribute('value', '1'); } catch(_){ }
                    try { var ev = new Event('input', { bubbles: true }); ncompEl.dispatchEvent(ev); } catch(_){ }
                  }
                } catch(_){ }

                // After the selector rebuilds, programmatically press the first pill (select compartimento 1)
                try {
                  setTimeout(function(){
                    try {
                      var container = document.getElementById('' + prefix + '-comp-selector') || document.getElementById('sup-comp-selector') || document.querySelector('#sup-comp-selector');
                      var pill = container && container.querySelector('.sup-comp-pill');
                      if (pill && pill.getAttribute('aria-pressed') !== 'true') {
                        try { pill.click(); } catch(_){ /* fallback to set attribute */ pill.setAttribute('aria-pressed','true'); }
                      }

                      // Ensure hidden inputs for compartimento 1 exist and have sensible defaults
                      try {
                        var formEl = document.getElementById(prefix === 'sup' ? 'form-supervisor' : 'form-editor') || document.querySelector('form');
                        if (formEl) {
                          function ensureHidden(name, val){
                            var existing = formEl.querySelector('input[name="' + name + '"]');
                            if (existing) { existing.value = String(val); }
                            else { var i = document.createElement('input'); i.type = 'hidden'; i.name = name; i.value = String(val); formEl.appendChild(i); }
                          }
                          // mark mecanizada as 100% (fully progressed) and fina as 0 by default
                          ensureHidden('compartimento_avanco_mecanizada_1', 100);
                          ensureHidden('compartimento_avanco_fina_1', 0);
                          // also migrate legacy single-key if needed
                          ensureHidden('compartimento_avanco_1', 100);
                          // Recompute top-level summaries if available
                          try { if (typeof computeAndSetTopLevelSummaries === 'function') computeAndSetTopLevelSummaries(formEl); } catch(_){ }
                        }
                      } catch(_){ }
                    } catch(_){ }
                  }, 40);
                } catch(_){ }
              } else {
                // unlock gavetas/patamar and restore numero compartimentos behavior
                toLock.forEach(function(id){ _unlockFieldById(id); });
                _unlockFieldById(ncompId);
              }
            } catch(e){ console.warn('tank handler failed', e); }
          }

          sel.addEventListener('change', handler);
          // initial state
          handler();
          sel.__tankLockBound = true;
        } catch(_){ }
      });
    } catch(e){ console.warn('_bindTankTypeLock failed', e); }
  }
  onReady(_bindTankTypeLock);

  // Bind para bloquear campos relacionados a Espaço Confinado quando 'Não' selecionado
  function _bindEcFieldsToggle(){
    try {
      var sel = document.getElementById('sup-espaco-conf');
      if (!sel) return;
      if (sel.__ecToggleBound) return;

      // injetar estilos mínimos apenas uma vez
      try {
        if (!document.getElementById('rdo-ec-lock-styles')) {
          var st = document.createElement('style'); st.id = 'rdo-ec-lock-styles';
          st.type = 'text/css';
          st.appendChild(document.createTextNode('\n.rdo-ec-locked { opacity: 1; }\n.rdo-ec-locked input[disabled], .rdo-ec-locked button[disabled] { background:#f5f5f5; color:#888; }\n.rdo-ec-lock-icon { margin-left:8px; font-size:14px; opacity:0.95; vertical-align: middle; }\n.supv-ec-card.dimmed { opacity: 0.6; pointer-events: none; }\n'));
          document.head.appendChild(st);
        }
      } catch(_){ }

      // Elements to disable when EC = 'nao'
      var ecGrid = document.getElementById('ec-times-grid');
      var sec = document.getElementById('supv-sec-espaco-confinado');
      var sectionWrapper = document.getElementById('sec-tanque'); // header location for icon
      var operationalIds = ['sup-operadores','sup-h2s','sup-lel','sup-co','sup-o2'];

      function setLocked(isLocked){
        try {
          // disable inputs in EC grid (entrada_confinado[] / saida_confinado[]), and buttons .supv-ec-clear-card
          if (ecGrid) {
            var inps = ecGrid.querySelectorAll('input[name="entrada_confinado[]"], input[name="saida_confinado[]"]');
            Array.prototype.forEach.call(inps, function(i){ try { i.disabled = !!isLocked; if (isLocked) i.value = ''; } catch(_){} });
            var clears = ecGrid.querySelectorAll('.supv-ec-clear-card');
            Array.prototype.forEach.call(clears, function(b){ try { b.disabled = !!isLocked; if (isLocked) b.classList.add('disabled'); else b.classList.remove('disabled'); } catch(_){} });
            // optionally dim individual EC cards for visual hint
            Array.prototype.forEach.call(ecGrid.querySelectorAll('.supv-ec-card'), function(c){ try { if (isLocked) c.classList.add('dimmed'); else c.classList.remove('dimmed'); } catch(_){} });
          }

          // operational fields
          operationalIds.forEach(function(id){ try { var el = document.getElementById(id); if (!el) return; el.disabled = !!isLocked; if (isLocked) { try { if (el.type === 'number' || el.tagName.toLowerCase() === 'input') el.value = ''; } catch(_){} } } catch(_){} });

          // controlar o campo editável de total não-efetivo confinado:
          // - se EC bloqueado via seleção 'Não' => desabilitar e limpar
          // - se EC habilitado => habilitar apenas se existir ao menos uma linha preenchida na grade de EC
          try {
            var confEl = document.getElementById('sup-total-n-efetivo-confinado');
            if (confEl) {
              if (isLocked) {
                // Quando Espaço Confinado = 'Não' -> trancar e limpar o valor
                try { confEl.value = ''; } catch(_){}
                confEl.disabled = true;
              } else {
                // Caso contrário, garantir que esteja habilitado para edição.
                // Não limpar o valor aqui para preservar entrada do usuário.
                confEl.disabled = false;
              }
            }
          } catch(_){ }

          // add/remove lock icon in EC section head
          if (sec) {
            var hdr = sec.querySelector('.supv-ec-section-head');
            if (hdr) {
              var key = hdr.querySelector('.rdo-ec-lock-icon');
              if (isLocked && !key) {
                var span = document.createElement('span'); span.className = 'rdo-ec-lock-icon'; span.title = 'Campos de Espaço Confinado bloqueados'; span.setAttribute('aria-hidden','true'); span.textContent = '🔒';
                hdr.appendChild(span);
              } else if (!isLocked && key) {
                try { key.parentNode && key.parentNode.removeChild(key); } catch(_){ }
              }
            }
          }
        } catch(e){ console.warn('setLocked EC failed', e); }
      }

      function handler(){
        try {
          var v = (sel.value || '').toString().toLowerCase().trim();
          setLocked(v === 'nao' || v === 'não' || v === 'naõ');
        } catch(e){ }
      }

      sel.addEventListener('change', handler);
      // initial state
      handler();
      sel.__ecToggleBound = true;
    } catch(e){ console.warn('_bindEcFieldsToggle failed', e); }
  }
  onReady(_bindEcFieldsToggle);

  // Safety: ensure tambores compute runs on ready so UI shows tambores immediate
  onReady(function(){ try { computeEditorTambores(); } catch(_){ } try { computeSupervisorTambores(); } catch(_){ } });

  // --- Dynamic EC grid controls for Supervisor modal (Add up to 6 teams on mobile)
  function _initDynamicEcGrid(){
    try {
      var grid = document.getElementById('ec-times-grid');
      if (!grid) return;
      var addBtn = document.getElementById('btn-supv-add-ec');
      var countEl = document.getElementById('supv-ec-count');
      var max = 6;

      // Ensure each card has data-ec-index already (template provides 0..5)
      var cards = Array.prototype.slice.call(grid.querySelectorAll('.supv-ec-card'));
      if (!cards.length) return;

      // Inject minimal CSS for animations and remove button (idempotent)
      try {
        if (!document.getElementById('rdo-ec-dynamic-styles')){
          var st = document.createElement('style'); st.id = 'rdo-ec-dynamic-styles'; st.type='text/css';
          var css = '\n.supv-ec-card { transition: opacity .22s ease, transform .22s ease; }\n.supv-ec-card.animate-in { opacity: 0; transform: translateY(-6px); }\n.supv-ec-card.animate-in.show { opacity: 1; transform: none; }\n.supv-ec-card.animate-out { opacity: 0; transform: translateY(-8px); }\n.supv-ec-actions .supv-ec-remove-card { margin-left:8px; background:transparent; border:1px solid rgba(0,0,0,0.06); }\n#btn-supv-add-ec { min-width: 120px; }\n';
          st.appendChild(document.createTextNode(css));
          document.head.appendChild(st);
        }
      } catch(_){ }

      // Helper: robust visibility check (considers computed style and offsetParent)
      function isHidden(el){
        try {
          if (!el) return true;
          var cs = window.getComputedStyle(el);
          if (!cs) return (el.style && (el.style.display === 'none' || el.style.visibility === 'hidden'));
          if (cs.display === 'none' || cs.visibility === 'hidden' || el.offsetParent === null) return true;
          return false;
        } catch(_){
          try { return (el.style && (el.style.display === 'none' || el.style.visibility === 'hidden')); } catch(_){ return false; }
        }
      }

      // Helper: update visible count text
      function updateCount(){
        try {
          var vis = cards.filter(function(c){ return !isHidden(c); }).length || 0;
          if (countEl) countEl.textContent = String(Math.max(1, vis)) + '/' + String(max);
        } catch(_){ }
      }

      // Hide cards beyond the first by default on narrow viewports
      function collapseInitial(){
        try {
          var startVisible = 1;
          cards.forEach(function(c, idx){
            try {
              if (idx < startVisible) { c.style.display = ''; } else { c.style.display = 'none'; }
            } catch(_){ }
          });
          updateCount();
        } catch(_){ }
      }

      // Add next hidden card
      function showNextCard(){
        try {
          for (var i=0;i<cards.length;i++){
            var c = cards[i];
            if (isHidden(c)){
              // reveal with class-based animation
              c.classList.remove('animate-out');
              c.classList.add('animate-in');
              c.style.display = '';
              // focus first input inside the card
              try { var first = c.querySelector('input[type=time]'); if (first) { setTimeout(function(){ try { first.focus(); } catch(_){} }, 100); } } catch(_){ }
              updateCount();
              // bind clear and remove buttons in this card
              _bindEcCardClear(c);
              _bindEcCardRemove(c);
              // remove animate-in class after animation ends
              setTimeout(function(el){ try { el.classList.remove('animate-in'); } catch(_){} }, 400, c);
              return true;
            }
          }
          return false;
        } catch(e){ return false; }
      }

      function hideLastCard(){
        try {
          // hide the last visible card beyond the first
          var visible = cards.filter(function(c){ return !isHidden(c); });
          if (visible.length <= 1) return false;
          var last = visible[visible.length-1];
          // clear inputs before hiding
          try { var inps = last.querySelectorAll('input[type=time]'); Array.prototype.forEach.call(inps, function(i){ i.value = ''; }); } catch(_){ }
          // animate out then hide
          try { last.classList.add('animate-out'); } catch(_){ last.style.opacity = 0; }
          setTimeout(function(el){ try { el.style.display = 'none'; el.classList.remove('animate-out'); } catch(_){} }, 260, last);
          updateCount();
          return true;
        } catch(e){ return false; }
      }

      // bind remove button handler for a card (removes that specific card)
      function _bindEcCardRemove(card){
        try {
          if (!card) return;
          var btn = card.querySelector('.supv-ec-remove-card');
          if (!btn) return;
          if (btn.__ecRemoveBound) return;
          btn.addEventListener('click', function(ev){ ev.preventDefault(); try {
            // animate out and then hide
            card.classList.add('animate-out');
            // clear inputs
            try { Array.prototype.forEach.call(card.querySelectorAll('input[type=time]'), function(i){ i.value = ''; }); } catch(_){ }
            setTimeout(function(el){ try { el.style.display = 'none'; el.classList.remove('animate-out'); updateCount(); computeModalAggregates(); } catch(_){} }, 260, card);
          } catch(e){ console.warn('remove ec card failed', e); } });
          btn.__ecRemoveBound = true;
        } catch(e){ }
      }

      // bind clear button for a card
      function _bindEcCardClear(card){
        try {
          if (!card) return;
          var btn = card.querySelector('.supv-ec-clear-card');
          if (!btn) return;
          if (btn.__ecClearBound) return;
          btn.addEventListener('click', function(ev){ ev.preventDefault(); try { Array.prototype.forEach.call(card.querySelectorAll('input[type=time]'), function(inp){ inp.value=''; inp.dispatchEvent(new Event('input',{ bubbles:true })); }); computeModalAggregates(); showToast('Horários limpos', 'info'); } catch(e){ console.warn('clear ec card failed', e); } });
          btn.__ecClearBound = true;
        } catch(e){ }
      }

  // ensure all initial visible cards have clear and remove bound
  cards.forEach(function(c){ try { _bindEcCardClear(c); _bindEcCardRemove(c); } catch(_){} });

      // bind time inputs per card to update per-card duration immediately
      function _bindEcCardTimes(card){
        try {
          if (!card) return;
          if (card.__ecTimeBound) return;
          var ent = card.querySelector('input[name="entrada_confinado[]"]');
          var sai = card.querySelector('input[name="saida_confinado[]"]');
          var handler = function(){
            try {
              var valE = ent ? ent.value : '';
              var valS = sai ? sai.value : '';
              // reuse time parsing from computeModalAggregates (simple local impl)
              function timeToMinLocal(v){ if (!v) return null; var p = String(v).split(':'); if (p.length<2) return null; var hh=parseInt(p[0],10)||0; var mm=parseInt(p[1],10)||0; if (!isFinite(hh) || !isFinite(mm)) return null; return hh*60+mm; }
              function minutesToHHMMLocal(m){ if (m==null || !isFinite(m)) return '--:--'; var mm = Math.floor(m); var hh = Math.floor(mm/60); var rem = mm%60; return (hh<10?('0'+hh):String(hh))+':'+(rem<10?('0'+rem):String(rem)); }
              var eM = timeToMinLocal(valE); var sM = timeToMinLocal(valS); var d = null; if (eM!=null && sM!=null){ d = sM - eM; if (d<0) d += 24*60; }
              var durationEl = card.querySelector('[data-ec-duration]');
              if (durationEl) {
                durationEl.textContent = 'Tempo total: ' + (d!=null ? minutesToHHMMLocal(d) : '--:--');
              }
              // recompute overall aggregates (updates sup-total-confinado etc.)
              try { computeModalAggregates(); } catch(_){ }
            } catch(_){ }
          };
          if (ent && !ent.__ecTimeListener) { ent.addEventListener('input', handler); ent.addEventListener('change', handler); ent.__ecTimeListener = true; }
          if (sai && !sai.__ecTimeListener) { sai.addEventListener('input', handler); sai.addEventListener('change', handler); sai.__ecTimeListener = true; }
          // run once to initialize display
          try { handler(); } catch(_){ }
          card.__ecTimeBound = true;
        } catch(_){ }
      }

      // ensure time bindings for all cards
      cards.forEach(function(c){ try { _bindEcCardTimes(c); } catch(_){} });

      // Add button handler
      if (addBtn && !addBtn.__supvEcBound) {
        addBtn.addEventListener('click', function(ev){ ev.preventDefault(); try {
          // count visible
          var vis = cards.filter(function(c){ return c.style.display !== 'none' && c.style.display !== 'hidden'; }).length || 0;
          if (vis >= max) { showToast('Máximo de ' + max + ' equipes atingido', 'info'); return; }
          if (!showNextCard()) showToast('Nenhum cartão adicional disponível', 'error');
        } catch(e){ console.warn('supv add ec failed', e); } });
        addBtn.__supvEcBound = true;
      }

      // Optional: long-press on count to remove last visible (mobile-friendly)
      if (countEl && !countEl.__supvCountBound){
        countEl.addEventListener('click', function(ev){ try { ev.preventDefault(); hideLastCard(); } catch(_){ } });
        countEl.__supvCountBound = true;
      }

      // Recompute aggregates when any time input changes
      grid.addEventListener('input', function(ev){ try { if (ev.target && (ev.target.name === 'entrada_confinado[]' || ev.target.name === 'saida_confinado[]')) computeModalAggregates(); } catch(_){} }, { passive: true });

      // On load: collapse extras on mobile widths
      try { if (isMobileViewport()) collapseInitial(); else { cards.forEach(function(c){ c.style.display=''; }); updateCount(); } } catch(_){ collapseInitial(); }
    } catch(e){ console.warn('_initDynamicEcGrid failed', e); }
  }

  // run onReady
  onReady(_initDynamicEcGrid);

  function computeModalAggregates(){
    try {
      // localizar wrapper de atividades (suporta Supervisor e Editor)
      var wrap = document.getElementById('atividades-wrapper') || document.getElementById('edit-atividades-wrapper') || document.querySelector('.activities-wrapper');
      // Não retornar cedo: podemos calcular agregados de espaço confinado mesmo sem a seção de atividades
      var rows = wrap ? (qsa('.activities-row', wrap) || []) : [];

      function timeToMin(val){
        if (val == null || val === '') return null;
        if (typeof val === 'number') return Math.floor(val);
        if (typeof val === 'string'){
          var parts = val.split(':'); if (parts.length < 2) return null;
          var hh = parseInt(parts[0],10) || 0; var mm = parseInt(parts[1],10) || 0;
          if (!isFinite(hh) || !isFinite(mm)) return null; return hh*60 + mm;
        }
        return null;
      }

      var total_atividade = 0, total_abertura_pt = 0, total_efetivas = 0;
      var efetivas = {
        'avaliação inicial da área de trabalho':1,'bombeio':1,'instalação/preparação/montagem':1,
        'desmobilização do material - dentro do tanque':1,'desmobilização do material - fora do tanque':1,
        'mobilização de material - dentro do tanque':1,'mobilização de material - fora do tanque':1,
        'limpeza e higienização de coifa':1,'limpeza de dutos':1,'coleta e análise de ar':1,
        'cambagem':1,'içamento':1,'limpeza fina':1,'manutenção de equipamentos - dentro do tanque':1,
        'manutenção de equipamentos - fora do tanque':1,'jateamento':1
      };

      rows.forEach(function(row){
        try{
          var sel = qs('.atividade-nome-select', row);
          var ini = qs('.atividade-inicio', row);
          var fim = qs('.atividade-fim', row);
          var iniM = ini ? timeToMin(ini.value) : null;
          var fimM = fim ? timeToMin(fim.value) : null;
          if (iniM == null || fimM == null) return;
          var dur = fimM - iniM; if (dur < 0) dur += 24*60;
          total_atividade += dur;
          var at = (sel && sel.value) ? String(sel.value).toLowerCase().trim() : '';
          if (at === 'abertura pt') total_abertura_pt += dur;
          if (efetivas[at]) total_efetivas += dur;
        } catch(_){ }
      });

      // calcular total_confinado a partir de grid EC (editor ou supervisor)
      var total_confinado = 0;
      var ecGrid = document.getElementById('edit-ec-times-grid') || document.getElementById('ec-times-grid') || document.querySelector('.confined-times-grid');
      if (ecGrid) {
        var ent = qsa('input[name="entrada_confinado[]"]', ecGrid) || [];
        var sai = qsa('input[name="saida_confinado[]"]', ecGrid) || [];
        var n = Math.max(ent.length, sai.length);
        // helper to format minutes into HH:MM
        function minutesToHHMM(m){ if (m == null || !isFinite(m)) return '--:--'; var mm = Math.floor(m); var hh = Math.floor(mm/60); var rem = mm % 60; return (hh<10?('0'+hh):String(hh))+':'+(rem<10?('0'+rem):String(rem)); }
        for (var i=0;i<n;i++){
          var e = ent[i] ? timeToMin(ent[i].value) : null;
          var s = sai[i] ? timeToMin(sai[i].value) : null;
          var d = null;
          if (e != null && s != null){ d = s - e; if (d < 0) d += 24*60; total_confinado += d; }
          try {
            // update per-card duration if element exists
            var card = ecGrid.querySelector('.supv-ec-card[data-ec-index="' + i + '"]');
            if (card) {
              var durationEl = card.querySelector('[data-ec-duration]');
              if (durationEl) {
                if (d != null) durationEl.textContent = 'Tempo total: ' + minutesToHHMM(d);
                else durationEl.textContent = 'Tempo total: --:--';
              }
            }
          } catch(_){ }
        }
      }

      // nEfetivo: preferir campo editor, senão supervisor
      var nEf = 0;
      var nEfEl = document.getElementById('edit-total-n-efetivo-confinado') || document.getElementById('sup-total-n-efetivo-confinado') || document.getElementById('total-n-efetivo-confinado');
      if (nEfEl && nEfEl.value) { var tn = parseInt(nEfEl.value,10); if (isFinite(tn)) nEf = tn; }

      var total_nao_efetivas_fora = total_atividade - total_efetivas - nEf;

      // setar resultados em ambos os prefixes quando existirem
      function setResultFor(idSuffix, value, allowOverwriteIfEdited){ ['sup','edit'].forEach(function(pref){ try { var el = document.getElementById(pref + '-' + idSuffix); if (el && (allowOverwriteIfEdited !== false || !el.dataset.userEdited)) el.value = (value==null ? '' : String(Math.round(value))); } catch(_){ } }); }

      setResultFor('total-atividades', total_atividade);
      setResultFor('total-confinado', total_confinado);
      setResultFor('total-abertura-pt', total_abertura_pt);
      setResultFor('total-atividades-efetivas', total_efetivas);
      setResultFor('total-n-efetivo-confinado', nEf, false);
      setResultFor('total-nao-efetivas-fora', total_nao_efetivas_fora);

      return { total_atividade: total_atividade, total_confinado: total_confinado, total_abertura_pt: total_abertura_pt, total_atividades_efetivas: total_efetivas, total_nao_efetivas_fora: total_nao_efetivas_fora, n_efetivo_confinado: nEf };
    } catch(e){ console.warn('computeModalAggregates failed', e); return {}; }
  }

  // Calcula Bombeio (m3) e Resíduo Líquido no Editor a partir de tempo_bomba (h) e vazao_bombeio (m3/h)
  function computeEditorBombeio(){
    try {
      // Idempotent bind: se já ligado, só executa compute
      if (!computeEditorBombeio.__bound) computeEditorBombeio.__bound = true;
      var tempoInput = document.getElementById('edit-tempo-bomba');
      var bombeioInput = document.getElementById('edit-bombeio');
      var resLiqInput = document.getElementById('edit-res-liq');
      if (!tempoInput || !bombeioInput || !resLiqInput) return;

      function computeAndFill(){
        try {
          var val = parseFloat(tempoInput.value);
          if (!isFinite(val)) return;
          var vazEl = document.getElementById('edit-vazao-bombeio');
          var vazao = vazEl ? parseFloat(vazEl.value) : NaN;
          var vazaoLocal = isFinite(vazao) ? vazao : 36;
          var computed = Math.round((val * vazaoLocal) * 100) / 100; // duas casas
          bombeioInput.value = computed;
          resLiqInput.value = computed;
          try { resLiqInput.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
        } catch(e){ console.warn('computeEditorBombeio compute failed', e); }
      }

      // bind idempotentemente
      if (!tempoInput.__computeEditorBound) { tempoInput.addEventListener('input', computeAndFill); tempoInput.__computeEditorBound = true; }
      var vazEl = document.getElementById('edit-vazao-bombeio');
      if (vazEl && !vazEl.__computeEditorBound) { vazEl.addEventListener('input', computeAndFill); vazEl.__computeEditorBound = true; }
  // Note: optional 'edit-btn-recalcular-bombeio' button was removed from
  // templates; recompute is triggered by input events. No click binding here.

      // run once to initialize
      try { setTimeout(computeAndFill, 30); } catch(e){}
    } catch(e){ console.warn('computeEditorBombeio failed', e); }
  }

  // Calcula Resíduo Total = Resíduo Líquido + Resíduos Sólidos
  function computeEditorResTotal(){
    try {
      // idempotent flag
      if (computeEditorResTotal.__bound) {
        // apenas calcula
        var rl = parseFloat((document.getElementById('edit-res-liq')||{}).value);
        var rs = parseFloat((document.getElementById('edit-res-sol')||{}).value);
        rl = isFinite(rl) ? rl : 0;
        rs = isFinite(rs) ? rs : 0;
        var total = Math.round((rl + rs) * 100) / 100;
        var out = document.getElementById('edit-res-total'); if (out) out.value = total;
        return total;
      }

      var resLiqEl = document.getElementById('edit-res-liq');
      var resSolEl = document.getElementById('edit-res-sol');
      var resTotalEl = document.getElementById('edit-res-total');
      if (!resLiqEl || !resSolEl || !resTotalEl) return null;

      function computeAndFill(){
        try {
          var rl = parseFloat(resLiqEl.value);
          var rs = parseFloat(resSolEl.value);
          rl = isFinite(rl) ? rl : 0;
          rs = isFinite(rs) ? rs : 0;
          var total = Math.round((rl + rs) * 100) / 100;
          resTotalEl.value = total;
        } catch(e){}
      }

      // bind idempotente
      try { if (!resLiqEl.__computeEditorResBound) { resLiqEl.addEventListener('input', computeAndFill); resLiqEl.__computeEditorResBound = true; } } catch(e){}
      try { if (!resSolEl.__computeEditorResBound) { resSolEl.addEventListener('input', computeAndFill); resSolEl.__computeEditorResBound = true; } } catch(e){}
  // Removed click binding for optional 'edit-btn-recalcular-res-total'.

      // inicializar
      try { computeAndFill(); } catch(e){}
      computeEditorResTotal.__bound = true;
      return computeAndFill();
    } catch(e){ console.warn('computeEditorResTotal failed', e); return null; }
  }

  // Calcula Resíduos Sólidos a partir de Ensacamento (ensacamento_dia * 0.008)
  function computeEditorResSolidos(){
    try {
      if (computeEditorResSolidos.__bound) {
        var ens = parseFloat((document.getElementById('edit-ensac')||{}).value);
        ens = isFinite(ens) ? ens : 0;
        var rs = Math.round((ens * 0.008) * 100) / 100;
        var out = document.getElementById('edit-res-sol'); if (out) { out.value = rs; try { out.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){} }
        return rs;
      }

      var ensEl = document.getElementById('edit-ensac');
      var resSolEl = document.getElementById('edit-res-sol');
      if (!ensEl || !resSolEl) return null;

      function computeAndFill(){
        try {
          var ens = parseFloat(ensEl.value);
          ens = isFinite(ens) ? ens : 0;
          var rs = Math.round((ens * 0.008) * 100) / 100;
          resSolEl.value = rs;
          try { resSolEl.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
        } catch(e){}
      }

      try { if (!ensEl.__computeEditorResSolBound) { ensEl.addEventListener('input', computeAndFill); ensEl.__computeEditorResSolBound = true; } } catch(e){}
  // Removed click binding for optional 'edit-btn-recalcular-res-total'.

      try { computeAndFill(); } catch(e){}
      computeEditorResSolidos.__bound = true;
      return computeAndFill();
    } catch(e){ console.warn('computeEditorResSolidos failed', e); return null; }
  }

  // Calcula percentuais do Editor: ensacamento/icamento/cambagem e percentual_avanco
  // Mantém os mesmos pesos definidos no backend: limpeza 70, ensacamento 7, icamento 7, cambagem 5, limpeza_fina 6
  function computeEditorPercentuais(){
    try{
      function toNumber(val){
        if (val == null || val === '') return 0;
        if (typeof val === 'number') return val;
        // aceitar vírgula como decimal
        val = String(val).replace(',', '.');
        var f = parseFloat(val);
        return isNaN(f) ? 0 : f;
      }

      var get = function(id){ var el = document.getElementById(id); return el ? el.value : null; };

      // Ensacamento
      var ensac_cum = toNumber(get('ensacamento_cumulativo') || get('edit-ensacamento_cumulativo'));
      var ensac_prev = toNumber(get('ensacamento_previsao') || get('edit-ensacamento_previsao'));
      var perc_ensac = 0;
      if (ensac_prev > 0) perc_ensac = (ensac_cum / ensac_prev) * 100;

      // Içamento
      var ic_cum = toNumber(get('icamento_cumulativo') || get('edit-icamento_cumulativo'));
      var ic_prev = toNumber(get('icamento_previsao') || get('edit-icamento_previsao'));
      var perc_ic = 0;
      if (ic_prev > 0) perc_ic = (ic_cum / ic_prev) * 100;

      // Cambagem
      var camb_cum = toNumber(get('cambagem_cumulativo') || get('edit-cambagem_cumulativo'));
      var camb_prev = toNumber(get('cambagem_previsao') || get('edit-cambagem_previsao'));
      var perc_camb = 0;
      if (camb_prev > 0) perc_camb = (camb_cum / camb_prev) * 100;

      // Limpeza e limpeza fina (podem ser decimais)
      var perc_limpeza = toNumber(get('percentual_limpeza') || get('edit-percentual_limpeza'));
      var perc_limpeza_fina = toNumber(get('percentual_limpeza_fina') || get('edit-percentual_limpeza_fina'));

      // Normalizar e limitar
      function clamp(v){ if (!isFinite(v) || isNaN(v)) return 0; return Math.max(0, Math.min(100, v)); }
      perc_ensac = clamp(perc_ensac);
      perc_ic = clamp(perc_ic);
      perc_camb = clamp(perc_camb);
      perc_limpeza = clamp(perc_limpeza);
      perc_limpeza_fina = clamp(perc_limpeza_fina);

      // Atualizar campos de percentual (formatar com 2 casas decimais onde aplicável)
      // setVal: atualiza campo salvo no DOM, mas NÃO sobrescreve campos marcados como vindos do RdoTanque
      var setVal = function(id, v, decimals){
        var el = document.getElementById(id); if (!el) return;
        try{
          if (el.dataset && el.dataset.source === 'rdotanque') return; // respeitar valor persistido por RdoTanque
        }catch(_){ }
        if (decimals != null) el.value = Number(v).toFixed(decimals); else el.value = String(Math.round(v));
      };
      // tentar múltiplos IDs/names para compatibilidade com fragmentos
      setVal('percentual_ensacamento', perc_ensac, 2);
      setVal('edit-percentual_ensacamento', perc_ensac, 2);
      setVal('percentual_icamento', perc_ic, 2);
      setVal('edit-percentual_icamento', perc_ic, 2);
      setVal('percentual_cambagem', perc_camb, 2);
      setVal('edit-percentual_cambagem', perc_camb, 2);

      // Calcular percentual_avanco com pesos (usar somente campos disponíveis)
      var pesos = {
        'percentual_limpeza': 70.0,
        'percentual_ensacamento': 7.0,
        'percentual_icamento': 7.0,
        'percentual_cambagem': 5.0,
        'percentual_limpeza_fina': 6.0
      };
      var weightedSum = 0, weightTotal = 0;
      Object.keys(pesos).forEach(function(k){
        var w = pesos[k];
        var val = toNumber(get(k) || get('edit-' + k));
        if (k === 'percentual_ensacamento') val = perc_ensac;
        if (k === 'percentual_icamento') val = perc_ic;
        if (k === 'percentual_cambagem') val = perc_camb;
        if (!isFinite(val) || isNaN(val)) val = 0;
        weightedSum += val * w;
        weightTotal += w;
      });

      var percentual_avanco = 0;
      if (weightTotal > 0) percentual_avanco = weightedSum / weightTotal;
      percentual_avanco = clamp(percentual_avanco);
      // gravar como inteiro (compatível com campo IntegerField)
      setVal('percentual_avanco', percentual_avanco, null);
      setVal('edit-percentual_avanco', percentual_avanco, null);

      // Também espelhar valores para os campos do Supervisor (ui do modal)
      try {
        // exibição: usar inteiro e acrescentar '%' para ficar claro ao usuário
        var supAv = document.getElementById('sup-limp');
        if (supAv) supAv.value = String(Math.round(percentual_avanco)) + '%';

        // limpeza fina (diário)
        var supFina = document.getElementById('sup-limp-fina');
        if (supFina) supFina.value = (isFinite(perc_limpeza_fina) ? String(Math.round(perc_limpeza_fina)) + '%' : '');

        // tentar também preencher os acumulados (se existirem nos inputs de origem)
        var perc_limpeza_acu = toNumber(get('percentual_limpeza_cumulativo') || get('edit-percentual_limpeza_cumulativo'));
        var perc_limpeza_fina_acu = toNumber(get('percentual_limpeza_fina_cumulativo') || get('edit-percentual_limpeza_fina_cumulativo'));
        var supAcu = document.getElementById('sup-limp-acu'); if (supAcu) supAcu.value = (isFinite(perc_limpeza_acu) ? String(Math.round(perc_limpeza_acu)) + '%' : '');
        var supFinaAcu = document.getElementById('sup-limp-fina-acu'); if (supFinaAcu) supFinaAcu.value = (isFinite(perc_limpeza_fina_acu) ? String(Math.round(perc_limpeza_fina_acu)) + '%' : '');
      } catch(_){ }
    }catch(e){ try{ console.warn('computeEditorPercentuais error', e); }catch(_){ } }
  }

  async function submitSupervisorForm(ev){
    if (ev && ev.preventDefault) ev.preventDefault();
    var form = qs('#form-supervisor');
    if (!form) return;
    // Prevent re-entrant / duplicate submissions: if the form is already
    // being submitted, skip this invocation. This avoids the UI sending
    // the same payload twice when handlers are accidentally bound twice
    // or the user clicks the button fast.
    if (form.__rdoCoreSubmitting) { try { console.warn('submitSupervisorForm already running — skipping duplicate call'); } catch(_){}; return; }
  form.__rdoCoreSubmitting = true;
  var hid = document.getElementById('sup-rdo-id');
    var isEdit = !!(hid && hid.value);
    var url = isEdit ? '/rdo/update_ajax/' : '/rdo/create_ajax/';
  // ensure top-level summaries (daily + acumulados) are up-to-date before building payload
  try{ if (typeof computeAndSetTopLevelSummaries === 'function') computeAndSetTopLevelSummaries(form); } catch(_){ }
  var payload = buildSupervisorFormData(form);

  // Defensive normalization: garantir que atividades/equipe idênticas não sejam enviadas duas vezes
  try {
    if (payload && typeof payload.entries === 'function' && typeof payload.delete === 'function') {
      // coletar todas as entradas atuais
      var _entries = [];
      try {
        var it = payload.entries();
        var _n = it.next();
        while (!_n.done) { _entries.push(_n.value); _n = it.next(); }
      } catch(e) {
        try { payload.forEach(function(v,k){ _entries.push([k,v]); }); } catch(_) { _entries = []; }
      }

      // extrair arrays por campo (mantendo ordem)
      function _valsByName(name) { return _entries.filter(function(x){ return x[0] === name; }).map(function(x){ return x[1]; }); }
      var a_names = _valsByName('atividade_nome[]');
      var a_inis  = _valsByName('atividade_inicio[]');
      var a_fims  = _valsByName('atividade_fim[]');
      var a_cpts  = _valsByName('atividade_comentario_pt[]');
      var a_cens  = _valsByName('atividade_comentario_en[]');
      var maxA = Math.max(a_names.length, a_inis.length, a_fims.length, a_cpts.length, a_cens.length);
      var seenA = new Set();
      var dedupA = [];
      for (var iA = 0; iA < maxA; iA++) {
        var an = a_names[iA] || '';
        var ai = a_inis[iA] || '';
        var af = a_fims[iA] || '';
        var ac = a_cpts[iA] || '';
        var ae = a_cens[iA] || '';
        if (!an && !ai && !af && !ac && !ae) continue;
        var kA = [an, ai, af, ac, ae].join('||');
        if (seenA.has(kA)) continue; seenA.add(kA);
        dedupA.push([an, ai, af, ac, ae]);
      }

      // Equipe
      var e_pids = _valsByName('equipe_pessoa_id[]');
      var e_noms = _valsByName('equipe_nome[]');
      var e_funs = _valsByName('equipe_funcao[]');
      var e_srvs = _valsByName('equipe_em_servico[]');
      var maxE = Math.max(e_pids.length, e_noms.length, e_funs.length, e_srvs.length);
      var seenE = new Set();
      var dedupE = [];
      for (var iE = 0; iE < maxE; iE++) {
        var ep = e_pids[iE] || '';
        var en = e_noms[iE] || '';
        var ef = e_funs[iE] || '';
        var es = e_srvs[iE] || '';
        if (!ep && !en && !ef && !es) continue;
        var kE = [ep, en, ef, es].join('||');
        if (seenE.has(kE)) continue; seenE.add(kE);
        dedupE.push([ep, en, ef, es]);
      }

      // Reconstruir FormData: copiar tudo exceto os campos atividade_/equipe_ e então anexar as listas deduplicadas
      var newFd = new FormData();
      _entries.forEach(function(p){
        var k = p[0], v = p[1];
        if (k === 'atividade_nome[]' || k === 'atividade_inicio[]' || k === 'atividade_fim[]' || k === 'atividade_comentario_pt[]' || k === 'atividade_comentario_en[]') return;
        if (k === 'equipe_pessoa_id[]' || k === 'equipe_nome[]' || k === 'equipe_funcao[]' || k === 'equipe_em_servico[]') return;
        newFd.append(k, v);
      });
      dedupA.forEach(function(r){ newFd.append('atividade_nome[]', r[0]); newFd.append('atividade_inicio[]', r[1]); newFd.append('atividade_fim[]', r[2]); newFd.append('atividade_comentario_pt[]', r[3]); newFd.append('atividade_comentario_en[]', r[4]); });
      dedupE.forEach(function(r){ newFd.append('equipe_pessoa_id[]', r[0]); newFd.append('equipe_nome[]', r[1]); newFd.append('equipe_funcao[]', r[2]); newFd.append('equipe_em_servico[]', r[3]); });

      // opcional: marcar origin do normalizador
      try { newFd.append('__rdo_client_normalized', '1'); } catch(_){ }
      payload = newFd;
    }
  } catch(e) { console.warn('RDO: normalization failed', e); }
    if (isEdit) payload.append('rdo_id', hid.value);

    // Helpers: coletar dados do tanque atual e, se necessário, adicionar via endpoint dedicado
    function _collectTankValues(scope){
      try {
        var names = [
          // identificação
          'tanque_codigo','tanque_nome','nome_tanque','tipo_tanque','numero_compartimento','numero_compartimentos',
          // configurações/geom
          'gavetas','patamar','patamares','volume_tanque_exec',
          // operação
          'servico_exec','metodo_exec','espaco_confinado','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado',
          // diários / previsões
            'tempo_bomba','ensacamento_dia','icamento_dia','cambagem_dia','ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo','ensacamento_prev','icamento_prev','cambagem_prev','tambores_dia',
          // resíduos / bombeio
          'residuos_solidos','residuos_totais','bombeio','total_liquido',
          // avancos
          'avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json',
          // campos legados mecanizada/fina (mantemos para leitura/escrita quando presentes)
          'limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa',
          // percentuais por-tanque / cumulativos
          'percentual_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_fina_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo',
          'percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco',
          // aliases/compat
          'limpeza_acu','limpeza_fina_acu'
        ];
        var out = Object.create(null);
        names.forEach(function(n){ try { var el = scope.querySelector('[name="'+n+'"]'); out[n] = el ? (el.value || '') : ''; } catch(_){ out[n] = ''; } });
        return out;
      } catch(_) { return {}; }
    }
    function _hasTankContent(tv){
      try {
        if (!tv) return false;
        // Considerar campos de identificação e também campos operacionais
        // como sinais de que o usuário deseja adicionar um tanque. Em particular,
        // aceitar os cumulativos (ensacamento/icamento/cambagem) como conteúdo
        // válido — antes disso, apenas identificar por código/nome fazia com que
        // preenchimentos apenas de cumulativos fossem ignorados.
        var keys = ['tanque_codigo','tanque_nome','tipo_tanque','numero_compartimentos','numero_compartimento','volume_tanque_exec','servico_exec','metodo_exec',
                    'ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo'];
        for (var i=0;i<keys.length;i++){ var v = tv[keys[i]]; if (v && String(v).trim() !== '') return true; }
        return false;
      } catch(_){ return false; }
    }
    async function _addTankForRdo(rdoId, tv){
      try {
        if (!rdoId) return { success:false, error:'RDO inválido' };
        try { console.debug('DEBUG _addTankForRdo tv object:', tv); } catch(_){ }
        var fd = new FormData();
        // incluir apenas campos conhecidos e não vazios (tolerante a vazios também)
        Object.keys(tv||{}).forEach(function(k){ try { if (typeof tv[k] !== 'undefined') fd.append(k, tv[k]); } catch(_){ } });
        // opcional: enviar rdo_id no body (id também está na URL)
        fd.append('rdo_id', String(rdoId));
        // Debug: listar FormData antes do fetch
        try {
          var dbgA = [];
          if (typeof fd.entries === 'function') {
            for (var pair of fd.entries()) dbgA.push(pair[0] + '=' + String(pair[1]));
          }
          console.debug('DEBUG _addTankForRdo FormData entries:', dbgA);
        } catch(_){ }
        var csrf = getCSRF(form) || _getCookie('csrftoken') || '';
        var urlAdd = '/api/rdo/' + encodeURIComponent(rdoId) + '/add_tank/';
        var resp = await fetch(urlAdd, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf } });
        var data = null; try { data = await resp.json(); } catch(_){ data = null; }
        try { console.debug('DEBUG _addTankForRdo response:', { ok: resp.ok, status: resp.status, data: data }); } catch(_){ }
        if (resp.ok && data && data.success) {
          // marcar flag local de tanques adicionados
          try {
            var flag = form.querySelector('input[name="rdo_has_tanks"]');
            if (!flag) { flag = document.createElement('input'); flag.type = 'hidden'; flag.name = 'rdo_has_tanks'; form.appendChild(flag); }
            flag.value = '1';
            if (form.classList) form.classList.add('has-tank-additions');
          } catch(_){ }
          return { success:true, data:data };
        }
        return { success:false, error: (data && (data.error||data.message)) || 'Falha ao adicionar tanque' };
      } catch(err){ return { success:false, error:String(err) }; }
    }
    var tankValues = _collectTankValues(form);
    var shouldAddFinalTank = _hasTankContent(tankValues);

    // Defensive: garantir que entradas/saidas de espaço confinado estejam presentes no payload
    try {
      // aceitar ambos os nomes com e sem colchetes
      // Normalize: remove any existing keys and re-append all inputs in order (including empty strings)
      try { if (typeof payload.delete === 'function') { payload.delete('entrada_confinado[]'); payload.delete('entrada_confinado'); payload.delete('saida_confinado[]'); payload.delete('saida_confinado'); } } catch(_){ }
      var entInputs = form.querySelectorAll('input[name="entrada_confinado[]"], input[name="entrada_confinado"]') || [];
      Array.prototype.forEach.call(entInputs, function(e){ try { payload.append('entrada_confinado[]', (e && e.value) ? e.value : ''); } catch(_){} });
      var saiInputs = form.querySelectorAll('input[name="saida_confinado[]"], input[name="saida_confinado"]') || [];
      Array.prototype.forEach.call(saiInputs, function(s){ try { payload.append('saida_confinado[]', (s && s.value) ? s.value : ''); } catch(_){} });
      // Também enviar campos explícitos 1..6 para compatibilidade com backend novo
      try {
        for (var idx = 0; idx < 6; idx++) {
          var entVal = (entInputs[idx] && entInputs[idx].value) ? entInputs[idx].value : '';
          var saiVal = (saiInputs[idx] && saiInputs[idx].value) ? saiInputs[idx].value : '';
          payload.append('entrada_confinado_' + (idx+1), entVal);
          payload.append('saida_confinado_' + (idx+1), saiVal);
        }
      } catch(_){ }
    } catch(e){ try { console.warn('ensure EC fields append failed', e); } catch(_){} }

    // Se tanques foram adicionados via fluxo "Salvar e adicionar outro tanque",
    // não reenviar campos de TANQUE no submit final para evitar sobrescrever
    // dados do RDO com o último tanque preenchido.
    try {
      var hasTankAdds = false;
      try { var flagEl = document.getElementById('sup-has-tank-additions'); hasTankAdds = !!(flagEl && String(flagEl.value||'') === '1'); } catch(_){ }
      // também considerar o hidden usado pelos handlers: rdo_has_tanks
      if (!hasTankAdds) { try { var flag2 = (form && form.querySelector) ? form.querySelector('input[name="rdo_has_tanks"]') : null; hasTankAdds = !!(flag2 && String(flag2.value||'') === '1'); } catch(_){ } }
      if (!hasTankAdds) { try { hasTankAdds = !!(form && form.classList && form.classList.contains('has-tank-additions')); } catch(_){ hasTankAdds = false; } }
      if (isEdit && hasTankAdds && payload && typeof payload.delete === 'function') {
        var tankNamesToDrop = [
          'tanque_codigo','tanque_nome','nome_tanque','tipo_tanque',
          // aceitar ambas as variantes de nomes
          'numero_compartimento','numero_compartimentos',
          // configurações
          'gavetas','patamar','patamares','volume_tanque_exec',
          // operação
          'servico_exec','metodo_exec','espaco_confinado','operadores_simultaneos',
          'h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','tempo_bomba',
          // diários / previsões
          'ensacamento_dia','icamento_dia','cambagem_dia','ensacamento_prev','icamento_prev','cambagem_prev','ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo','tambores_dia','residuos_solidos','residuos_totais',
          // bombeio/total
          'bombeio','total_liquido',
          // avanços
          'avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json',
          // mecanizada/fina legados
          'limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa',
          // novos campos de limpeza manual/fina
          'limpeza_manual_diaria_tanque','limpeza_manual_cumulativa_tanque','limpeza_fina_cumulativa_tanque',
          // percentuais/cumulativos adicionais solicitados
          'percentual_limpeza_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo','percentual_limpeza_fina','limpeza_acu','limpeza_fina_acu','percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco'
        ];
        try { tankNamesToDrop.forEach(function(k){ try { payload.delete(k); } catch(_){ } }); } catch(_){ }
      }
    } catch(_){ }
    // DEBUG: imprimir conteúdo do FormData (entries e arquivos) antes de enviar
    try {
      if (payload && typeof payload.entries === 'function'){
        var dbgEntries = [];
        for (var pair of payload.entries()){
          // Para objetos File, mostrar só nome e size para evitar poluir output
          if (pair[1] && typeof pair[1] === 'object' && pair[1].name) dbgEntries.push(pair[0] + '=' + pair[1].name + '(' + pair[1].size + 'B)');
          else dbgEntries.push(pair[0] + '=' + String(pair[1]));
        }
        try { console.debug('DEBUG submitSupervisorForm FormData entries:', dbgEntries); } catch(_){ }
      } else {
        try { console.debug('DEBUG submitSupervisorForm payload (non-FormData):', payload); } catch(_){ }
      }
      // Also list files from file inputs for clarity
      try {
        var fileInputs = qsa('input[type=file]', form);
        var filesDbg = [];
        fileInputs.forEach(function(fi){
          try {
            var list = [];
            for (var i=0;i<(fi.files||[]).length;i++) list.push((fi.files[i] && fi.files[i].name) ? fi.files[i].name + '(' + fi.files[i].size + 'B)' : String(fi.files[i]));
            filesDbg.push(fi.name + ':' + list.join(',') );
          } catch(e){}
        });
        try { console.debug('DEBUG submitSupervisorForm file inputs:', filesDbg); } catch(_){ }
      } catch(e){}
    } catch(e){ try { console.warn('DEBUG submitSupervisorForm failed to enumerate payload', e); } catch(_){ } }

    var btn = qs('button[type="submit"]', form);
    var orig = btn ? btn.textContent : null;
    // prevent duplicate submits and provide immediate feedback
    if (btn) { btn.disabled = true; btn.textContent = 'Salvando...'; }
    // flag to detect a successful save so we don't re-enable the button and
    // we can trigger a reload after showing the success notification
    var didSucceed = false;
    var controller = new AbortController();
    var t = setTimeout(function(){ try{ controller.abort(); }catch(_){} }, 30000);
    try {
      // Fluxo ajustado: se for edição e houver conteúdo de tanque atual, adicionar tanque ANTES do update
      if (isEdit) {
        var rdoIdEdit = hid && hid.value ? String(hid.value) : '';
        if (rdoIdEdit && shouldAddFinalTank) {
          var addRes = await _addTankForRdo(rdoIdEdit, tankValues);
          if (!addRes.success) { throw new Error(addRes.error || 'Falha ao adicionar tanque'); }
        }
        // prosseguir com update do RDO (campos de tanque já foram removidos quando apropriado)
        var respUp = await fetch(url, {
          method: 'POST',
          body: payload,
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': (getCSRF(form) || _getCookie('csrftoken') || '') },
          signal: controller.signal
        });
        var dataUp = null; try { dataUp = await respUp.json(); } catch(_){ dataUp = null; }
        if (respUp.ok && dataUp && dataUp.success) {
          didSucceed = true;
          showToast(dataUp.message || 'RDO atualizado', 'success');
          try { document.dispatchEvent(new CustomEvent('rdo:saved', { detail: { mode: 'update', response: dataUp } })); } catch(_){ }
          try { closeModal(); } catch(_){ }
          try { setTimeout(function(){ try { window.location.reload(); } catch(_){} }, 400); } catch(_){ try { window.location.reload(); } catch(_){} }
        } else {
          var msgUp = (dataUp && (dataUp.error || dataUp.message)) || 'Falha ao salvar RDO';
          throw new Error(msgUp);
        }
      } else {
        // Criação: primeiro cria o RDO; se houver dados de tanque, adiciona o tanque em seguida
        var respCr = await fetch(url, {
          method: 'POST',
          body: payload,
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': (getCSRF(form) || _getCookie('csrftoken') || '') },
          signal: controller.signal
        });
        var dataCr = null; try { dataCr = await respCr.json(); } catch(_){ dataCr = null; }
        if (!(respCr.ok && dataCr && dataCr.success)) {
          var msgCr = (dataCr && (dataCr.error || dataCr.message)) || 'Falha ao salvar RDO';
          throw new Error(msgCr);
        }
        // se houver tanque a adicionar, faça agora usando o id retornado
        var newId = dataCr.id || (dataCr.rdo && (dataCr.rdo.id || dataCr.rdo.pk)) || '';
        if (shouldAddFinalTank && newId) {
          var addRes2 = await _addTankForRdo(String(newId), tankValues);
          if (!addRes2.success) {
            // não marcar como sucesso; exibir erro e permitir retry sem recarregar
            throw new Error(addRes2.error || 'Falha ao adicionar tanque');
          }
        }
        didSucceed = true;
        showToast(dataCr.message || 'RDO criado', 'success');
        try { document.dispatchEvent(new CustomEvent('rdo:saved', { detail: { mode: 'create', response: dataCr } })); } catch(_){ }
        try { closeModal(); } catch(_){ }
        try { setTimeout(function(){ try { window.location.reload(); } catch(_){} }, 400); } catch(_){ try { window.location.reload(); } catch(_){} }
      }
    } catch(err){
      showToast(err && err.name === 'AbortError' ? 'Tempo de requisição expirou' : (err && err.message ? err.message : 'Erro ao salvar'), 'error');
      try { document.dispatchEvent(new CustomEvent('rdo:save:error', { detail: { mode: isEdit ? 'update' : 'create', error: String(err && err.message ? err.message : err) } })); } catch(_){ }
    } finally {
      clearTimeout(t);
      // Only re-enable the submit button if the save did NOT succeed. When
      // successful we keep it disabled because the page will reload shortly —
      // this prevents the modal showing a spinner forever or duplicate saves.
      if (btn) {
        if (!didSucceed) {
          btn.disabled = false;
          if (orig != null) try { btn.textContent = orig; } catch(_){ }
        } else {
          // leave the button visually disabled while reload occurs
          try { btn.textContent = 'Salvo'; } catch(_){ }
        }
      }
      try { form.__rdoCoreSubmitting = false; } catch(_) {}
    }
  }

  // Submit handler para o Editor (form id="form-editor")
  // --- Helper: cria RDO e retorna id/payload sem recarregar ---
  async function saveSupervisorCreateReturnId(form){
    if (!form) form = qs('#form-supervisor');
    var payload = buildSupervisorFormData(form);
    // Ensure EC fields appended as in submitSupervisorForm
    try { if (typeof payload.delete === 'function') { payload.delete('entrada_confinado[]'); payload.delete('entrada_confinado'); payload.delete('saida_confinado[]'); payload.delete('saida_confinado'); } } catch(_){ }
    try { var entInputs = form.querySelectorAll('input[name="entrada_confinado[]"], input[name="entrada_confinado"]') || []; Array.prototype.forEach.call(entInputs, function(e){ try { payload.append('entrada_confinado[]', (e && e.value) ? e.value : ''); } catch(_){} }); } catch(_){ }
    try { var saiInputs = form.querySelectorAll('input[name="saida_confinado[]"], input[name="saida_confinado"]') || []; Array.prototype.forEach.call(saiInputs, function(s){ try { payload.append('saida_confinado[]', (s && s.value) ? s.value : ''); } catch(_){} }); } catch(_){ }

    var btn = qs('button[type="submit"]', form);
    var orig = btn ? btn.textContent : null;
    if (btn) { btn.disabled = true; try { btn.textContent = 'Salvando...'; } catch(_){} }
    var controller = new AbortController();
    var t = setTimeout(function(){ try{ controller.abort(); }catch(_){} }, 30000);
    try {
      var resp = await fetch('/rdo/create_ajax/', { method: 'POST', body: payload, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': (getCSRF(form) || _getCookie('csrftoken') || '') }, signal: controller.signal });
      var data = null; try { data = await resp.json(); } catch(_){ data = null; }
      if (resp.ok && data && data.success) {
        // return created id and rdo payload
        return { success: true, id: data.id || (data.rdo && data.rdo.id), rdo: data.rdo || data.rdo };
      }
      return { success: false, error: (data && (data.error || data.message)) || 'Falha ao criar RDO' };
    } catch(err){ return { success: false, error: String(err) }; }
    finally { clearTimeout(t); if (btn) { if (orig != null) try { btn.textContent = orig; } catch(_){} btn.disabled = false; } }
  }

  // Bloquear visualmente/desabilitar campos não relacionados a tanque dentro do modal Supervisor
  function lockNonTankFields(){
    try {
  var form = qs('#form-supervisor'); if (!form) return;
  // Preserve certain non-tank fields so the user doesn't have to re-type
  // previsões and sentido da limpeza when adding multiple tanks.
  var _preserveNames = ['ensacamento_prev','icamento_prev','cambagem_prev','sentido_limpeza'];
  var _preserved = {};
  try { _preserveNames.forEach(function(n){ var el = form.querySelector('[name="'+n+'"]'); _preserved[n] = el ? (el.value || '') : ''; }); } catch(_){ }
      // Lista branca de nomes permitidos (campos de tanque) - manter sincronizado com add_tank_ajax
  var tankFields = new Set([
  'tanque_codigo','tanque_nome','nome_tanque','tipo_tanque','numero_compartimento','numero_compartimentos',
  'gavetas','patamar','patamares','volume_tanque_exec','servico_exec','metodo_exec','espaco_confinado','operadores_simultaneos',
  'h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','tempo_bomba','ensacamento_dia','icamento_dia','cambagem_dia',
  'ensacamento_prev','icamento_prev','cambagem_prev','tambores_dia','residuos_solidos','residuos_totais','bombeio','total_liquido',
  // cumulativos operacionais — manter como campos de tanque editáveis e submetidos
  'ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo',
  'avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json',
        'limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa',
        'limpeza_manual_diaria_tanque','limpeza_manual_cumulativa_tanque','limpeza_fina_cumulativa_tanque',
        'percentual_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_fina_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo',
        'percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco','limpeza_acu','limpeza_fina_acu', 'ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo'
      ]);
      Array.prototype.forEach.call(form.elements, function(el){
        try {
          if (!el || !el.name) return;
          if (tankFields.has(el.name)) {
            // keep enabled
            if (el.closest && el.closest('.form-field')) el.closest('.form-field').classList.remove('rdo-auto-locked');
            return;
          }
          // keep CSRF hidden and rdo id hidden enabled (we still need to send it)
          if (el.name === 'csrfmiddlewaretoken' || el.id === 'sup-rdo-id') return;
          // disable other inputs/selects/textarea/buttons (but not cancel buttons)
          if (el.tagName && (el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'select' || el.tagName.toLowerCase() === 'textarea' || el.tagName.toLowerCase() === 'button')) {
            try { el.disabled = true; el.classList.add('rdo-locked-after-save'); } catch(_){ }
          }
        } catch(_){ }
      });
      // additionally disable photo file inputs to avoid re-upload
      try { var fInputs = form.querySelectorAll('input[type=file]'); Array.prototype.forEach.call(fInputs, function(fi){ try { fi.disabled = true; fi.classList.add('rdo-locked-after-save'); } catch(_){} }); } catch(_){ }
      // visually mark modal as saved
      try { var overlay = document.getElementById('supv-modal-overlay'); if (overlay) overlay.classList.add('rdo-saved-first'); } catch(_){ }
    } catch(e){ console.warn('lockNonTankFields failed', e); }
  }

  // Delegated handler: 'Salvar e adicionar outro tanque' (botão existente #btn-rdo-add-another)
  document.addEventListener('click', async function(ev){
    try {
      var btn = ev.target && ev.target.closest && ev.target.closest('#btn-rdo-add-another, #btn-add-tanque');
      if (!btn) return;
      ev.preventDefault();
      var form = qs('#form-supervisor'); if (!form) return;
      var hid = document.getElementById('sup-rdo-id');
      var rdoId = hid && hid.value ? hid.value : '';
      // If no RDO yet, create one first (without reloading)
      if (!rdoId) {
        var res = await saveSupervisorCreateReturnId(form);
        if (!res || !res.success || !res.id) {
          showToast((res && res.error) || 'Falha ao criar RDO antes de adicionar tanque', 'error');
          return;
        }
  rdoId = String(res.id);
        // store id in hidden input and visible rdo field
        try { if (hid) hid.value = rdoId; var supRdo = document.getElementById('sup-rdo'); if (supRdo && res.rdo && res.rdo.rdo) supRdo.value = String(res.rdo.rdo); } catch(_){ }
        // lock non-tank fields so further add-another only touches tanks
  try { lockNonTankFields(); } catch(_){ }
  // restore preserved non-tank values (they may have been disabled by lockNonTankFields)
  try { _preserveNames.forEach(function(n){ var el = form.querySelector('[name="'+n+'"]'); if (el) try { el.value = _preserved[n] || ''; } catch(_){ } }); } catch(_){ }
        showToast('RDO criado — agora você pode adicionar tanques', 'success');
      }
      // Build FormData with only tank-related fields
  var tankNames = ['tanque_codigo','tanque_nome','nome_tanque','tipo_tanque','numero_compartimento','numero_compartimentos','gavetas','patamar','patamares','volume_tanque_exec','servico_exec','metodo_exec','espaco_confinado','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','tempo_bomba','ensacamento_dia','icamento_dia','cambagem_dia','ensacamento_prev','icamento_prev','cambagem_prev','ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo','tambores_dia','residuos_solidos','residuos_totais','bombeio','total_liquido','avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json','limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa','limpeza_manual_diaria_tanque','limpeza_manual_cumulativa_tanque','limpeza_fina_cumulativa_tanque','percentual_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_fina_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo','percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco','limpeza_acu','limpeza_fina_acu'];
      var fd = new FormData();
      // append rdo id in the body (endpoint expects rdo in URL but having it in body is harmless)
      fd.append('rdo_id', rdoId);
      tankNames.forEach(function(n){ try { var el = form.querySelector('[name="' + n + '"]'); if (!el) return; if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return; fd.append(n, el.value); } catch(_){ } });

      // Append supervisor percent fields and other per-tank extras so the
      // add_tank endpoint receives the same per-tank percentuais the UI shows.
      try {
  // top-level daily percentuais (UI ids: #sup-limp, #sup-limp-fina)
        var supL = form.querySelector('#sup-limp') || form.querySelector('input[name="percentual_limpeza_diario"]');
        if (supL && (supL.value || supL.value === '0')) fd.append('percentual_limpeza_diario', supL.value);
        var supLF = form.querySelector('#sup-limp-fina') || form.querySelector('input[name="avanco_limpeza_fina"], input[name="percentual_limpeza_fina_diario"]');
        if (supLF && (supLF.value || supLF.value === '0')) fd.append('avanco_limpeza_fina', supLF.value);

        // acumulados (cumulativos)
        var supLA = form.querySelector('#sup-limp-acu') || form.querySelector('input[name="percentual_limpeza_cumulativo"], input[name="limpeza_acu"]');
        if (supLA && (supLA.value || supLA.value === '0')) { fd.append('percentual_limpeza_cumulativo', supLA.value); fd.append('limpeza_acu', supLA.value); }
        var supLFA = form.querySelector('#sup-limp-fina-acu') || form.querySelector('input[name="percentual_limpeza_fina_cumulativo"], input[name="limpeza_fina_acu"]');
        if (supLFA && (supLFA.value || supLFA.value === '0')) { fd.append('percentual_limpeza_fina_cumulativo', supLFA.value); fd.append('limpeza_fina_acu', supLFA.value); }

  // Os campos simples de limpeza manual/fina agora são enviados diretamente
  // via tankNames acima; não há regras de negócio adicionais.
        // preserve/send sentido da limpeza (se presente in the modal)
        var sentido = form.querySelector('[name="sentido_limpeza"]');
        if (sentido && (typeof sentido.value !== 'undefined')) fd.append('sentido_limpeza', sentido.value || '');

        // include per-compartment hidden inputs created by rdo.compartment.js
        var compSelectors = form.querySelectorAll('input[name^="compartimento_avanco"], input[name^="compartimentos_avanco"]');
        Array.prototype.forEach.call(compSelectors, function(ci){ try { if (ci && ci.name) fd.append(ci.name, ci.value); } catch(_){ } });
      } catch(_){ /* non-fatal: still send tank payload */ }

      // send to add_tank endpoint using internal PK
      var url = '/api/rdo/' + encodeURIComponent(rdoId) + '/add_tank/';
      var csrf = getCSRF(form) || _getCookie('csrftoken') || '';
      try { btn.disabled = true; btn.textContent = 'Adicionando...'; } catch(_){ }
      // Debug: listar FormData antes do fetch
      try {
        var dbgB = [];
        if (typeof fd.entries === 'function') {
          for (var pr of fd.entries()) dbgB.push(pr[0] + '=' + String(pr[1]));
        }
        console.debug('DEBUG add-another FormData entries:', dbgB);
      } catch(_){ }
      var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf } });
      var data = null; try { data = await resp.json(); } catch(_){ data = null; }
      try { console.debug('DEBUG add-another response:', { ok: resp.ok, status: resp.status, data: data }); } catch(_){ }
      if (resp.ok && data && data.success) {
        showToast(data.message || 'Tanque adicionado', 'success');
        try { document.dispatchEvent(new CustomEvent('rdo:tank:added', { detail: { rdo_id: rdoId, tank: data.tank } })); } catch(_){ }
        // marcar no formulário que já existem tanques adicionados (para o submit final não regravar campos de tanque no RDO)
        try {
          var flag = form.querySelector('input[name="rdo_has_tanks"]');
          if (!flag) { flag = document.createElement('input'); flag.type = 'hidden'; flag.name = 'rdo_has_tanks'; form.appendChild(flag); }
          flag.value = '1';
        } catch(_){ }
        // clear tank input fields and return focus/scroll to the first tank field
        try {
          var firstField = null;
          tankNames.forEach(function(n){
            try {
              var el = form.querySelector('[name="' + n + '"]');
              if (!el) return;
              var tag = (el.tagName || '').toLowerCase();
              if (tag === 'select') {
                try { el.selectedIndex = 0; } catch(_){ }
              } else if (el.type === 'checkbox' || el.type === 'radio') {
                try { el.checked = false; } catch(_){ }
              } else {
                try { el.value = ''; } catch(_){ }
              }
              if (!firstField) firstField = el;
            } catch(_){}
          });
          // scroll/focus so the user can immediately start filling the next tank
          try {
            if (firstField) {
              // attempt to bring the field into view inside the modal
              if (typeof firstField.scrollIntoView === 'function') {
                try { firstField.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch(_){ try { firstField.scrollIntoView(); } catch(_){} }
              }
              // focus after a short delay to allow rendering/reflow
              setTimeout(function(){ try { firstField.focus(); if (typeof firstField.select === 'function') try { firstField.select(); } catch(_){} } catch(_){} }, 120);
            }
          } catch(_){ }
        } catch(_){ }
        // optional UI append handler (if defined elsewhere)
        try { if (typeof _appendSavedTankSummary === 'function') _appendSavedTankSummary(data.tank); } catch(_){ }
      } else {
        showToast((data && (data.error || data.message)) || 'Falha ao adicionar tanque', 'error');
      }
      try { btn.disabled = false; btn.textContent = 'Salvar e adicionar outro tanque'; } catch(_){ }
    } catch(e){ console.warn('add-another handler failed', e); showToast('Erro ao adicionar tanque', 'error'); }
  }, false);

  async function submitEditorForm(ev){
    if (ev && ev.preventDefault) ev.preventDefault();
    var form = qs('#form-editor');
    if (!form) return;
    // decidir create vs update pelo hidden edit-rdo-id
    var hid = document.getElementById('edit-rdo-id');
    var isEdit = !!(hid && hid.value);
    var url = isEdit ? '/rdo/update_ajax/' : '/rdo/create_ajax/';
    // construir FormData (tenta usar builder externo se existir)
    var payload = null;
    try {
      if (window.buildSupervisorFormDataExternal && typeof window.buildSupervisorFormDataExternal === 'function') payload = window.buildSupervisorFormDataExternal(form);
    } catch(e){ payload = null; }
    if (!payload) {
      try { payload = buildSupervisorFormData(form); } catch(e){ payload = new FormData(form); }
    }
    if (isEdit) payload.append('rdo_id', hid.value);

    // Defensive: garantir que entradas/saídas de espaço confinado sejam anexadas ao payload
    try {
      // Normalize FormData: delete any previous EC keys then append all inputs (preserve order and empties)
      try { if (typeof payload.delete === 'function') { payload.delete('entrada_confinado[]'); payload.delete('entrada_confinado'); payload.delete('saida_confinado[]'); payload.delete('saida_confinado'); } } catch(_){ }
      var entInputsEd = form.querySelectorAll('input[name="entrada_confinado[]"], input[name="entrada_confinado"]') || [];
      Array.prototype.forEach.call(entInputsEd, function(e){ try { payload.append('entrada_confinado[]', (e && e.value) ? e.value : ''); } catch(_){} });
      var saiInputsEd = form.querySelectorAll('input[name="saida_confinado[]"], input[name="saida_confinado"]') || [];
      Array.prototype.forEach.call(saiInputsEd, function(s){ try { payload.append('saida_confinado[]', (s && s.value) ? s.value : ''); } catch(_){} });
      // Também enviar campos explícitos 1..6 para compat com backend novo
      try {
        for (var j = 0; j < 6; j++) {
          var eV = (entInputsEd[j] && entInputsEd[j].value) ? entInputsEd[j].value : '';
          var sV = (saiInputsEd[j] && saiInputsEd[j].value) ? saiInputsEd[j].value : '';
          payload.append('entrada_confinado_' + (j+1), eV);
          payload.append('saida_confinado_' + (j+1), sV);
        }
      } catch(_){ }
    } catch(e){ try { console.warn('ensure EC fields (editor) append failed', e); } catch(_){} }

    var btn = form.querySelector('button[type="submit"], button.save-editor');
    var orig = btn ? btn.textContent : null;
    if (btn) { btn.disabled = true; try { btn.textContent = 'Salvando...'; } catch(_){} }
    var controller = new AbortController();
    var t = setTimeout(function(){ try{ controller.abort(); }catch(_){} }, 30000);
    // DEBUG: imprimir conteúdo do FormData no console para diagnóstico
    try {
      try { console.debug('DEBUG submitEditorForm - preparing to send payload'); } catch(_){}
      if (payload && typeof payload.entries === 'function'){
        try {
          var entries = [];
          for (var pair of payload.entries()){
            entries.push(pair[0] + '=' + String(pair[1]));
          }
          try { console.debug('DEBUG submitEditorForm FormData entries:', entries); } catch(_){}
        } catch(e){ try { console.warn('DEBUG submitEditorForm could not iterate payload.entries', e); } catch(_){} }
      } else {
        try { console.debug('DEBUG submitEditorForm payload (non-FormData):', payload); } catch(_){}
      }
    } catch(_){}
    try {
      var resp = await fetch(url, {
        method: 'POST',
        body: payload,
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCSRF(form) || _getCookie('csrftoken') || '' },
        signal: controller.signal
      });
      var data = null; try { data = await resp.json(); } catch(_){ data = null; }
      if (resp.ok && data && data.success) {
        showToast(data.message || (isEdit ? 'RDO atualizado' : 'RDO criado'), 'success');
        try { document.dispatchEvent(new CustomEvent('rdo:saved', { detail: { mode: isEdit ? 'update' : 'create', response: data } })); } catch(_){ }
        // If server returned the saved RDO payload with ec_times, populate the editor
        // inputs so the user sees the entered EC horários immediately without a full reload.
        try {
          if (data && data.rdo) {
            var r = data.rdo;
            try {
              if (r.ec_times) {
                var entradas = [], saidas = [];
                for (var i = 1; i <= 6; i++) {
                  entradas.push(r.ec_times['entrada_' + i] || '');
                  saidas.push(r.ec_times['saida_' + i] || '');
                }
                try { _setECGrid(entradas, saidas); } catch(_){ }
              }
            } catch(_){ }
            try {
              if (typeof r.espaco_confinado !== 'undefined') {
                var v = '';
                try {
                  if (r.espaco_confinado === true || String(r.espaco_confinado).toLowerCase() === 'sim' || String(r.espaco_confinado).toLowerCase() === 'true') v = 'sim';
                  else if (r.espaco_confinado === false || String(r.espaco_confinado).toLowerCase() === 'nao' || String(r.espaco_confinado).toLowerCase() === 'false' || String(r.espaco_confinado).toLowerCase() === 'não') v = 'nao';
                } catch(_){ }
                try { _setSelectById('edit-espaco-conf', v); } catch(_){ }
              }
            } catch(_){ }
            // If we applied ec_times from response, close modal and reload so the UI reflects persisted state.
            if (r.ec_times) {
              try { showToast('RDO atualizado — horários aplicados. Recarregando...', 'success'); } catch(_){ }
              try { if (typeof closeEditorModal === 'function') closeEditorModal(); } catch(_){ }
              // dar um pequeno delay para o toast aparecer e o modal fechar visualmente
              try { setTimeout(function(){ try { window.location.reload(); } catch(_){} }, 400); } catch(_){ try { window.location.reload(); } catch(_){} }
              return;
            }
          }
        } catch(_){ }
        // fallback: reload conforme solicitado pelo usuário
        try { window.location.reload(); } catch(e){ /* fallback */ }
      } else {
        var msg = (data && (data.error || data.message)) || 'Falha ao salvar RDO';
        showToast(msg, 'error');
        try { document.dispatchEvent(new CustomEvent('rdo:save:error', { detail: { mode: isEdit ? 'update' : 'create', response: data } })); } catch(_){ }
      }
    } catch(err){
      showToast(err && err.name === 'AbortError' ? 'Tempo de requisição expirou' : 'Erro de rede ao salvar', 'error');
      try { document.dispatchEvent(new CustomEvent('rdo:save:error', { detail: { mode: isEdit ? 'update' : 'create', error: String(err) } })); } catch(_){ }
    } finally {
      clearTimeout(t);
      if (btn) { btn.disabled = false; if (orig != null) try { btn.textContent = orig; } catch(_){} }
    }
  }

  function ensureEditorSubmitBound(){
    var form = qs('#form-editor');
    if (!form) return;
    if (form.__rdoEditorSubmitBound) return;
    form.addEventListener('submit', submitEditorForm);
    form.__rdoEditorSubmitBound = true;
  }

  function ensureSubmitBound(){
    var form = qs('#form-supervisor');
    if (!form) return;
    if (form.__rdoCoreSubmitBound) return;
    // Bind native submit
    form.addEventListener('submit', submitSupervisorForm);
    // Bind the modal "Enviar" button (template uses type="button" id="btn-rdo")
    try {
      var send = document.getElementById('btn-rdo');
      if (send && !send.__rdoCoreBound) {
        send.addEventListener('click', function(ev){ ev.preventDefault(); try { submitSupervisorForm(); } catch(e){ console.warn('btn-rdo click failed', e); } });
        send.__rdoCoreBound = true;
      }
    } catch(_){ }

    form.__rdoCoreSubmitBound = true;
    // Bind supervisor-specific controls (activities, team, close)
    try { bindSupervisorActivityControls(); } catch(_){}
    try { bindSupervisorTeamControls(); } catch(_){}
    try { bindSupervisorModalClose(); } catch(_){}
    try { bindAggregateInputListeners(); } catch(_){}
    try { ensureSupervisorComputesBound(); } catch(_){ }
    try { ensureSupervisorTranslationsBound(); } catch(_){ }
  }

  // Bind add/remove activity buttons inside Supervisor modal
  function bindSupervisorActivityControls(){
    try {
      var wrapper = document.getElementById('atividades-wrapper');
      if (!wrapper) return;
      var addBtn = document.getElementById('btn-add-atividade');
      var removeLast = document.getElementById('btn-remove-last-atividade');
      function addRow(){
        try {
          var base = wrapper.querySelector('.activities-row');
          if (!base) return;
          var clone = base.cloneNode(true);
          // clear inputs
          Array.prototype.forEach.call(clone.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; });
          base.parentNode.insertBefore(clone, wrapper.querySelector('.activities-footer'));
          computeModalAggregates();
          try { _bindTranslationHandlers(clone); } catch(_){}
        } catch(e){ console.warn('addRow supervisor failed', e); }
      }
      function removeLastRow(){
        try {
          var rows = wrapper.querySelectorAll('.activities-row');
          if (rows.length <= 1) return;
          var last = rows[rows.length-1]; if (last && last.parentNode) last.parentNode.removeChild(last);
          computeModalAggregates();
        } catch(e){ console.warn('removeLastRow supervisor failed', e); }
      }
      if (addBtn && !addBtn.__supBound) { addBtn.addEventListener('click', function(ev){ ev.preventDefault(); addRow(); }); addBtn.__supBound = true; }
      if (removeLast && !removeLast.__supBound) { removeLast.addEventListener('click', function(ev){ ev.preventDefault(); removeLastRow(); }); removeLast.__supBound = true; }
    } catch(e){ console.warn('bindSupervisorActivityControls failed', e); }
  }

  // Bind add/remove team members in Supervisor modal
  function bindSupervisorTeamControls(){
    try {
      var wrap = document.getElementById('equipe-wrapper'); if (!wrap) return;
      var add = document.getElementById('btn-add-membro');
      var rem = document.getElementById('btn-remove-membro');
      function addMember(){
        try {
          var base = wrap.querySelector('.team-row'); if (!base) return;
          var clone = base.cloneNode(true);
          Array.prototype.forEach.call(clone.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; });
          base.parentNode.insertBefore(clone, wrap.querySelector('.team-footer'));
        } catch(e){ console.warn('addMember failed', e); }
      }
      function removeMember(){
        try {
          var rows = wrap.querySelectorAll('.team-row'); if (rows.length <= 1) return; var last = rows[rows.length-1]; if (last && last.parentNode) last.parentNode.removeChild(last);
        } catch(e){ console.warn('removeMember failed', e); }
      }
      if (add && !add.__supBound) { add.addEventListener('click', function(ev){ ev.preventDefault(); addMember(); }); add.__supBound = true; }
      if (rem && !rem.__supBound) { rem.addEventListener('click', function(ev){ ev.preventDefault(); removeMember(); }); rem.__supBound = true; }
    } catch(e){ console.warn('bindSupervisorTeamControls failed', e); }
  }

  // Bind modal close controls
  function bindSupervisorModalClose(){
    try {
      var closeBtn = document.querySelectorAll('.supv-modal__close, .supv-modal__cancel');
      Array.prototype.forEach.call(closeBtn, function(b){ if (!b.__supvCloseBound) { b.addEventListener('click', function(ev){ ev.preventDefault(); closeModal(); }); b.__supvCloseBound = true; } });
    } catch(e){ console.warn('bindSupervisorModalClose failed', e); }
  }

  // Bind inputs that should trigger recompute of aggregates
  function bindAggregateInputListeners(){
    try {
      var scope = document.getElementById('supv-modal-overlay') || document;
      var selectors = [
        '.atividade-inicio', '.atividade-fim',
        'input[name="entrada_confinado[]"]', 'input[name="saida_confinado[]"]',
        // Editor-specific fields (ids and names attempted for compatibility)
        'input#ensacamento_cumulativo', 'input#edit-ensacamento_cumulativo', 'input[name="ensacamento_cumulativo"]',
        'input#ensacamento_previsao', 'input#edit-ensacamento_previsao', 'input[name="ensacamento_previsao"]',
        'input#icamento_cumulativo', 'input#edit-icamento_cumulativo', 'input[name="icamento_cumulativo"]',
        'input#icamento_previsao', 'input#edit-icamento_previsao', 'input[name="icamento_previsao"]',
        'input#cambagem_cumulativo', 'input#edit-cambagem_cumulativo', 'input[name="cambagem_cumulativo"]',
        'input#cambagem_previsao', 'input#edit-cambagem_previsao', 'input[name="cambagem_previsao"]',
        'input#percentual_limpeza', 'input#edit-percentual_limpeza', 'input[name="percentual_limpeza"]',
        'input#percentual_limpeza_fina', 'input#edit-percentual_limpeza_fina', 'input[name="percentual_limpeza_fina"]'
      ];
      selectors.forEach(function(sel){
        Array.prototype.forEach.call(scope.querySelectorAll(sel), function(el){
          try {
            if (!el.__aggBound) { el.addEventListener('input', computeModalAggregates); el.__aggBound = true; }
            if (!el.__percBound) { el.addEventListener('input', function(){ try { if (typeof computeEditorPercentuais === 'function') computeEditorPercentuais(); } catch(_){} }); el.__percBound = true; }
          } catch(e){ }
        });
      });
    } catch(e){ console.warn('bindAggregateInputListeners failed', e); }
  }

  // Supervisor-side automatic computes (mirror do Editor)
  function computeSupervisorBombeio(){
    try {
      var tempo = document.getElementById('sup-tempo-bomba');
      var bombeio = document.getElementById('sup-bombeio');
      if (!tempo || !bombeio) return null;
      var val = parseFloat(tempo.value);
      if (!isFinite(val)) return null;
      var vazEl = document.getElementById('sup-vazao-bombeio') || document.getElementById('edit-vazao-bombeio');
      var vaz = vazEl ? parseFloat(vazEl.value) : NaN;
      var vazaoLocal = isFinite(vaz) ? vaz : 36; // default 36 m3/h
      var computed = Math.round((val * vazaoLocal) * 100) / 100;
      bombeio.value = computed;
      try { bombeio.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}

      // preencher Resíduo Líquido e a explicação da conta (tempo * vazão)
      try {
        var resLiqEl = document.getElementById('sup-res-liq');
        var calcHint = document.getElementById('sup-res-liq-calc');
        if (resLiqEl) {
          // resíduo líquido assume mesmo valor do bombeio (m³)
          resLiqEl.value = computed;
          try { resLiqEl.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
        }
        if (calcHint) {
          var vazText = isFinite(vazaoLocal) ? vazaoLocal : '36';
          calcHint.textContent = 'Conta: ' + String(val) + ' h × ' + String(vazText) + ' m³/h = ' + String(computed) + ' m³';
        }
      } catch(_){ }
      return computed;
    } catch(e){ console.warn('computeSupervisorBombeio failed', e); return null; }
  }

  function computeSupervisorResSolidos(){
    try {
      var ens = document.getElementById('sup-ensac');
      var resSol = document.getElementById('sup-res-sol');
      if (!ens || !resSol) return null;
      var v = parseFloat(ens.value);
      v = isFinite(v) ? v : 0;
      var rs = Math.round((v * 0.008) * 100) / 100;
      resSol.value = rs;
      try { resSol.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
      return rs;
    } catch(e){ console.warn('computeSupervisorResSolidos failed', e); return null; }
  }

  function computeSupervisorResTotal(){
    try {
      var rl = parseFloat((document.getElementById('sup-res-liq')||{}).value);
      var rs = parseFloat((document.getElementById('sup-res-sol')||{}).value);
      rl = isFinite(rl) ? rl : 0;
      rs = isFinite(rs) ? rs : 0;
      var total = Math.round((rl + rs) * 100) / 100;
      var out = document.getElementById('sup-res-total'); if (out) out.value = total;
      try { out.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
      return total;
    } catch(e){ console.warn('computeSupervisorResTotal failed', e); return null; }
  }

  function ensureSupervisorComputesBound(){
    try {
      if (ensureSupervisorComputesBound.__bound) return;
      // bind inputs
  var tempo = document.getElementById('sup-tempo-bomba');
  var ens = document.getElementById('sup-ensac');
  var vazEl = document.getElementById('sup-vazao-bombeio') || document.getElementById('edit-vazao-bombeio');
  // legacy supervisor recalc buttons removed from templates; do not bind
  // click handlers. Inputs drive recompute via their 'input' listeners.
  if (tempo && !tempo.__supComputeBound) { tempo.addEventListener('input', computeSupervisorBombeio); tempo.__supComputeBound = true; }
  if (vazEl && !vazEl.__supComputeBound) { vazEl.addEventListener('input', computeSupervisorBombeio); vazEl.__supComputeBound = true; }
      if (ens && !ens.__supComputeBound) { ens.addEventListener('input', function(){ computeSupervisorResSolidos(); computeSupervisorResTotal(); }); ens.__supComputeBound = true; }
      // When res_liq updates (maybe via fetch/populate), recompute total
      var resLiq = document.getElementById('sup-res-liq'); if (resLiq && !resLiq.__supComputeBound) { resLiq.addEventListener('input', computeSupervisorResTotal); resLiq.__supComputeBound = true; }
      var resSol = document.getElementById('sup-res-sol'); if (resSol && !resSol.__supComputeBound) { resSol.addEventListener('input', computeSupervisorResTotal); resSol.__supComputeBound = true; }
  // removed supervisor-level click bindings for obsolete recalc buttons
      // initial run to populate values if possible
  try { computeSupervisorBombeio(); computeSupervisorResSolidos(); computeSupervisorResTotal(); } catch(_){ }
  // compute tambores for both editor and supervisor (idempotent)
  try { computeEditorTambores(); } catch(_){ }
  try { computeSupervisorTambores(); } catch(_){ }
      // Allow user to edit sup-total-n-efetivo-confinado
      var nEfEl = document.getElementById('sup-total-n-efetivo-confinado'); if (nEfEl && !nEfEl.__userEditedBound) { nEfEl.addEventListener('input', function(){ this.dataset.userEdited = 'true'; }); nEfEl.__userEditedBound = true; }
      ensureSupervisorComputesBound.__bound = true;
    } catch(e){ console.warn('ensureSupervisorComputesBound failed', e); }
  }

  // Expose public API and bind table/mobile open handlers
  try { window.rdoOpenSupervisorModal = openSupervisorModal; } catch(_){ }

  // Delegate document clicks to open supervisor modal from table edit buttons and mobile cards
  onReady(function(){
    document.addEventListener('click', function(ev){
      try {
        // Only trigger Supervisor modal on explicit Supervisor controls.
        var supTrigger = ev.target && ev.target.closest && ev.target.closest('[data-open="supervisor"], .open-supervisor, .btn-rdo.open-supervisor');
  // If the clicked control (or any ancestor) is in a locked RDO, ignore.
  // Allow bypass when the clicked control (or an ancestor) carries `.allow-edit`.
  if (supTrigger && supTrigger.closest && supTrigger.closest('.rdo-locked') && !supTrigger.closest('.allow-edit')) return;
        if (supTrigger) {
          var tr = supTrigger.closest('tr');
          // If the trigger is inside a table row, handle it here. If not, fall
          // through so the mobile/card handler below can process the .open-supervisor
          // button (mobile cards are not <tr> elements).
          if (tr) {
            // respect locked rows: do not open supervisor modal from a locked row
            // but allow if the trigger or the row contains an explicit `.allow-edit` bypass
            if (tr.classList && tr.classList.contains('rdo-locked')) {
              var bypass = (supTrigger && supTrigger.closest && supTrigger.closest('.allow-edit')) || tr.classList.contains('allow-edit') || !!tr.querySelector('.allow-edit');
              if (!bypass) return;
            }
            var ctx = {
              os_id: tr.getAttribute('data-os-id') || tr.dataset && tr.dataset.osId || '',
              numero_os: tr.getAttribute('data-numero-os') || tr.dataset && tr.dataset.numeroOs || '',
              empresa: tr.getAttribute('data-empresa') || tr.dataset && tr.dataset.empresa || '',
              unidade: tr.getAttribute('data-unidade') || tr.dataset && tr.dataset.unidade || '',
              contrato_po: tr.getAttribute('data-po') || tr.dataset && tr.dataset.po || '',
              supervisor: tr.getAttribute('data-supervisor') || tr.dataset && tr.dataset.supervisor || '',
              supervisor_login: tr.getAttribute('data-supervisor-login') || tr.dataset && tr.dataset.supervisorLogin || '',
              supervisor_fullname: tr.getAttribute('data-supervisor-fullname') || tr.dataset && tr.dataset.supervisorFullname || '',
              rdo_id: tr.getAttribute('data-rdo-id') || tr.dataset && tr.dataset.rdoId || '',
              rdo_count: tr.getAttribute('data-rdo-count') || tr.dataset && tr.dataset.rdoCount || ''
            };
            try {
              // Verificar se a linha corresponde ao último RDO da mesma OS.
              // Se existir um RDO maior (mais recente) para a mesma OS, bloquear a abertura
              // para evitar criação/edição de RDOs antigos.
              try {
                var curRaw = String(ctx.rdo_count || '').replace(/[^0-9]/g, '');
                var curNum = curRaw === '' ? 0 : parseInt(curRaw, 10) || 0;
                var osKey = ctx.os_id || ctx.numero_os || '';
                if (osKey) {
                  var selector = 'tr[data-os-id="' + String(osKey).replace(/"/g,'') + '"][data-rdo-count]';
                  var peers = document.querySelectorAll(selector);
                  var max = 0;
                  Array.prototype.forEach.call(peers, function(p){ try { var v = String(p.getAttribute('data-rdo-count') || (p.dataset && p.dataset.rdoCount) || '').replace(/[^0-9]/g,''); var n = v === '' ? 0 : parseInt(v,10) || 0; if (n > max) max = n; } catch(_){ } });
                  if (max > 0 && curNum > 0 && curNum < max) {
                    showToast('Atenção: só é possível abrir a partir do último RDO (RDO ' + String(max) + ').', 'info');
                    return;
                  }
                }
              } catch(_){ }
              console.log && console.log('rdo: supTrigger (table) opening modal, ctx', ctx);
            } catch(_){ }
            try { window.rdoOpenSupervisorModal(ctx); } catch(e){ openSupervisorModal(ctx); }
            return;
          }
          // else: no <tr> ancestor — let the mobile handler below pick it up
        }
        // mobile/open-supervisor buttons
        var oc = ev.target && ev.target.closest && ev.target.closest('.open-supervisor, .btn-rdo.open-supervisor');
        if (oc) {
          var card = oc.closest('.rdo-mobile-item') || oc.closest('.rdo-mobile-card');
          if (!card) return;
          // respect locked mobile cards but allow bypass when `.allow-edit` present
          if (card.classList && card.classList.contains('rdo-locked')) {
            var cardBypass = (oc && oc.closest && oc.closest('.allow-edit')) || card.classList.contains('allow-edit') || !!card.querySelector('.allow-edit');
            if (!cardBypass) return;
          }
          var ctx2 = {
            os_id: card.getAttribute('data-os-id') || card.dataset && card.dataset.osId || '',
            numero_os: card.getAttribute('data-os') || card.dataset && card.dataset.os || '',
            empresa: card.getAttribute('data-empresa') || card.dataset && card.dataset.empresa || '',
            unidade: card.getAttribute('data-unidade') || card.dataset && card.dataset.unidade || '',
            contrato_po: card.getAttribute('data-po') || card.dataset && card.dataset.po || '',
            supervisor: card.getAttribute('data-supervisor') || card.dataset && card.dataset.supervisor || '',
            rdo_id: card.getAttribute('data-rdo-id') || card.dataset && card.dataset.rdoId || '',
            rdo_count: card.getAttribute('data-rdo-count') || card.dataset && card.dataset.rdoCount || ''
          };
          try { console.log && console.log('rdo: open-supervisor (card) clicked, card ctx', ctx2); } catch(_){}
          try { window.rdoOpenSupervisorModal(ctx2); } catch(e){ openSupervisorModal(ctx2); }
          return;
        }
      } catch(_){ }
    }, false);
  });

  async function openSupervisorModal(context){
    applyContext(context || {});
    // Se temos um RDO existente, buscar seus detalhes e popular o modal antes de abrir
    try {
      if (context && context.rdo_id) {
        try { await fetchAndPopulateRdo(context.rdo_id); } catch(_){ }
      }
    } catch(_){}
    // preencher campo RDO (rdo_count + 1) e contrato/PO antes de abrir
    try { await populateNextRdoIfNeeded(context || {}); } catch(_){ }
    ensureSubmitBound();
    openModal();
    try {
      var supOverlay = document.getElementById('supv-modal-overlay');
      // run shortly after opening to ensure DOM ready and scrolling stable
      setTimeout(function(){
        try {
          var focusTarget = document.getElementById('sup-observacoes-pt') || document.getElementById('sup-planejamento-pt') || (supOverlay && supOverlay.querySelector('input:not([type="hidden"]):not([readonly]), select, textarea'));
          if (focusTarget) {
            // Prefer focus({preventScroll:true}) para evitar pular a viewport.
            // Se não suportado, salvamos e restauramos a posição de scroll.
            try {
              focusTarget.focus({ preventScroll: true });
            } catch (e) {
              try {
                var scEl = document.scrollingElement || document.documentElement || document.body;
                var prevTop = scEl.scrollTop;
                var prevLeft = scEl.scrollLeft;
                focusTarget.focus();
                try { scEl.scrollTop = prevTop; scEl.scrollLeft = prevLeft; } catch(_){}
              } catch (_){
                try { focusTarget.focus(); } catch(__){}
              }
            }
          }
          var hint = document.getElementById('sup-translate-hint');
          if (hint) {
            // ensure polite live region and force announcement by toggling a trailing space
            try { hint.setAttribute('aria-live','polite'); hint.setAttribute('aria-atomic','true'); } catch(_){ }
            try {
              var t = hint.textContent || '';
              hint.textContent = t + ' ';
              setTimeout(function(){ try { hint.textContent = t; } catch(_){} }, 200);
            } catch(_){ }
          }
        } catch(_){ }
      }, 120);
    } catch(_){ }
    // Buscar detalhes apenas quando houver rdo_id
    try {
      var rid = (context && (context.rdo_id || context.id)) || (document.getElementById('sup-rdo-id')||{}).value;
      if (rid) await fetchAndPopulateRdo(rid);
    } catch(_){}
  }

  // ---------- Editor Modal (edição rápida) ----------
  function openEditorModal(context){
    try {
      var overlay = document.getElementById('modal-editor-overlay');
      if (!overlay) return false;
      // Aplicar contexto mínimo (rdo_id)
      var rid = (context && (context.rdo_id || context.id)) || '';
      var hid = document.getElementById('edit-rdo-id');
      if (hid) hid.value = rid;
      // se o contexto inclui tanque_id, preencher o hidden correspondente
      try {
        var tid = (context && (context.tanque_id || context.tank_id)) || '';
        var hidTid = document.getElementById('edit-tanque-id');
        if (hidTid) hidTid.value = tid || '';
        try { if (tid && window) window.__last_rdo_tanque_id = String(tid || ''); } catch(_){ }
      } catch(_){ }
      // Chips de contexto
      try {
        var ctxRdo = document.getElementById('edit-context-rdo');
        var ctxOs = document.getElementById('edit-context-os');
  if (ctxRdo) ctxRdo.textContent = '';
  // Tentar recuperar OS a partir da linha clicada (se vier no context) — não mostrar nada
  if (ctxOs) ctxOs.textContent = '';
      } catch(_){ }
      // Abrir modal
      overlay.classList.add('open');
      overlay.classList.remove('is-hidden');
      overlay.setAttribute('aria-hidden','false');
      // Foco no primeiro campo editável
      setTimeout(function(){
        try {
          var first = overlay.querySelector('input:not([type="hidden"]):not([readonly]), select, textarea');
          if (first) {
            try { first.focus({ preventScroll: true }); } catch(e) { first.focus(); }
            try { first.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch(_) {}
          }
        } catch(_){ }
      }, 100);
  // garantir binding do submit do editor (quando modal aberto sem fragmento)
  try { if (typeof ensureEditorSubmitBound === 'function') ensureEditorSubmitBound(); } catch(_){ }
      // aplicar lock visual e lógico no campo Data Início do editor
      try{ if (typeof _applyStartDateLock === 'function') _applyStartDateLock(); } catch(_){ }
    // Recalcular percentuais ao abrir o editor (depois de qualquer injeção de fragmento)
    try { setTimeout(function(){ if (typeof computeEditorPercentuais === 'function') computeEditorPercentuais(); }, 250); } catch(_){ }
      // Tentar carregar automaticamente o fragmento detalhado (se possível)
      try { setTimeout(function(){ if (typeof loadEditorDetails === 'function') { try { loadEditorDetails(); } catch(_){} } }, 120); } catch(_){ }
      return true;
    } catch(e){ console.warn('openEditorModal failed', e); return false; }
  }

  function closeEditorModal(){
    try {
      var overlay = document.getElementById('modal-editor-overlay');
      if (!overlay) return false;
      overlay.classList.remove('open');
      overlay.classList.add('is-hidden');
      overlay.setAttribute('aria-hidden','true');
      return true;
    } catch(e){ console.warn('closeEditorModal failed', e); return false; }
  }

  // -------- Helpers para preencher Editor --------
  // Aplica lock no campo "Data Início" (preenche com a data atual caso vazio e adiciona ícone)
  function _applyStartDateLock(){
    try{
      var ids = ['sup-data-inicio','edit-data-inicio'];
      var today = new Date();
      function ymd(d){
        var yyyy = d.getFullYear();
        var mm = String(d.getMonth()+1).padStart(2,'0');
        var dd = String(d.getDate()).padStart(2,'0');
        return yyyy + '-' + mm + '-' + dd;
      }
      ids.forEach(function(id){
        var el = document.getElementById(id);
        if (!el) return;
        if (!el.value) el.value = ymd(today);
        el.disabled = true;
        el.setAttribute('aria-readonly','true');
        el.dataset.rdoLocked = 'start-date';
        var wrapper = el.closest('.form-field');
        if (wrapper) wrapper.classList.add('rdo-auto-locked');
        var lbl = document.querySelector('label[for="'+id+'"]');
        if (lbl && !lbl.querySelector('.auto-lock-icon')){
          var span = document.createElement('span');
          span.className = 'auto-lock-icon';
          span.setAttribute('title','Campo automático (fixo)');
          span.setAttribute('aria-hidden','true');
          span.textContent = '🔒';
          lbl.appendChild(document.createTextNode(' '));
          lbl.appendChild(span);
        }
      });
    }catch(e){ console.warn('_applyStartDateLock failed', e); }
  }
  function _setValById(id, v){ var el = document.getElementById(id); if (!el) return; if (v == null) { el.value = ''; return; } el.value = String(v); }
  function _setSelectById(id, v){ var el = document.getElementById(id); if (!el) return; var val = (v == null ? '' : String(v)); el.value = val; if (el.value !== val) { /* valor inexistente */ } }
  function _setBoolSelectSimNaoById(id, v){ var el = document.getElementById(id); if (!el) return; var val = v; if (typeof v === 'boolean') val = v ? 'sim' : 'nao'; if (v === 1) val = 'sim'; if (v === 0) val = 'nao'; _setSelectById(id, val); }
  function _setBoolSelectTrueFalseById(id, v){ var el = document.getElementById(id); if (!el) return; var val = v; if (typeof v === 'boolean') val = v ? 'true' : 'false'; if (v === 1) val = 'true'; if (v === 0) val = 'false'; _setSelectById(id, val); }
  function _setChecksByName(name, values, scope){
    try {
      var container = scope || document.getElementById('modal-editor-overlay') || document;
      var els = container.querySelectorAll('input[type="checkbox"][name="'+name+'"][value]');
      var arr = Array.isArray(values) ? values.map(function(x){return String(x);}): [];
      Array.prototype.forEach.call(els, function(el){ el.checked = (arr.indexOf(String(el.value)) !== -1); });
    } catch(_){ }
  }
  function _setECGrid(entradaArr, saidaArr){
    try {
      var grid = document.getElementById('edit-ec-times-grid'); if (!grid) return;
      var ent = grid.querySelectorAll('input[name="entrada_confinado[]"]');
      var sai = grid.querySelectorAll('input[name="saida_confinado[]"]');
      var toStrTime = function(t){ if (!t) return ''; if (typeof t === 'string') return t.slice(0,5); if (typeof t === 'number') { var h=Math.floor(t/60), m=t%60; return (String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')); } return ''; };
      var n = Math.max(ent.length, sai.length, (entradaArr||[]).length, (saidaArr||[]).length);
      for (var i=0;i<n;i++){
        if (ent[i]) ent[i].value = toStrTime((entradaArr||[])[i]);
        if (sai[i]) sai[i].value = toStrTime((saidaArr||[])[i]);
      }
    } catch(_){ }
  }
  // Formata valores de tempo (minutos, 'HH:MM' ou ISO) para string 'HH:MM' para inputs <input type="time">
  function _formatTimeForInput(val){
    try{
      if (val == null || val === '') return '';
      // número em minutos
      if (typeof val === 'number' && isFinite(val)){
        var m = Math.floor(val);
        var hh = Math.floor(m/60) % 24;
        var mm = m % 60;
        return (hh<10?('0'+hh):String(hh))+':'+(mm<10?('0'+mm):String(mm));
      }
      if (typeof val === 'string'){
        var s = String(val).trim();
        if (!s) return '';
        // se for só dígitos => minutos
        if (/^\d+$/.test(s)){
          var m2 = parseInt(s,10);
          var hh2 = Math.floor(m2/60) % 24;
          var mm2 = m2 % 60;
          return (hh2<10?('0'+hh2):String(hh2))+':'+(mm2<10?('0'+mm2):String(mm2));
        }
        // já no formato HH:MM
        if (/^\d{1,2}:\d{2}$/.test(s)) return s;
        // aceitar formatos 12h com AM/PM como '10 a.m.', '10am', '10:30 PM', etc.
        var m12 = s.match(/^\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|am|p\.?m\.?|pm)\s*$/i);
        if (m12) {
          var hh = parseInt(m12[1],10) || 0;
          var mm = parseInt(m12[2] || '0',10) || 0;
          var ap = (m12[3] || '').toString().toLowerCase();
          if (/p/.test(ap) && hh < 12) hh = hh + 12;
          if (/^a/i.test(ap) && hh === 12) hh = 0;
          hh = hh % 24;
          mm = Math.max(0, Math.min(59, mm));
          return (hh<10?('0'+hh):String(hh))+':'+(mm<10?('0'+mm):String(mm));
        }
        // tentar parse de data/ISO
        var d = new Date(s);
        if (!isNaN(d.getTime())){
          var hh3 = d.getHours(); var mm3 = d.getMinutes();
          return (hh3<10?('0'+hh3):String(hh3))+':'+(mm3<10?('0'+mm3):String(mm3));
        }
      }
    }catch(e){/* ignore */}
    return '';
  }
  // Debounce utility
  function _debounce(fn, wait){
    var t = null;
    return function(){
      var ctx = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(function(){ try{ fn.apply(ctx, args); } catch(_){} }, wait || 300);
    };
  }
  // Feature flag: translation availability (avoid repeated failing requests)
  var __rdo_translate_available = true;
  var __rdo_translate_warned = false;
  // Read cookie helper to fallback CSRF
  function _getCookie(name){
    try{
      var v = document.cookie.match('(?:^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
      return v ? decodeURIComponent(v[1]) : null;
    }catch(e){ return null; }
  }
  // Translate preview: POST to backend translate_preview endpoint. Returns translated string or null.
  async function _translatePreview(text){
    try {
      if (!text || !text.toString().trim()) return '';
      if (!__rdo_translate_available) {
        // translation endpoint previously failed (404 or unreachable) — avoid retry spam
        if (!__rdo_translate_warned) { __rdo_translate_warned = true; showToast('Tradução automática indisponível', 'info'); }
        return '';
      }
  // endpoint defined in Django: path('api/rdo/translate/preview/', views_rdo.translate_preview)
  var url = '/api/rdo/translate/preview/';
      var payload = JSON.stringify({ text: String(text) });
      // CSRF: prefer token from form, fallback to cookie 'csrftoken'
      var csrf = getCSRF(document) || _getCookie('csrftoken') || '';
      console.debug('translate_preview: sending', { url: url, text: text, csrf_present: !!csrf });
      var resp = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': csrf
        },
        body: payload
      });
      if (!resp.ok) {
        console.warn('translate_preview: HTTP error', resp.status);
        // If endpoint missing (404) or server error, disable further attempts to avoid spam
        if (resp.status === 404) {
          __rdo_translate_available = false;
          if (!__rdo_translate_warned) { __rdo_translate_warned = true; showToast('Tradução automática indisponível (endpoint não encontrado)', 'error'); }
        }
        return '';
      }
      var data = null; try { data = await resp.json(); } catch(e){ console.warn('translate_preview: invalid json', e); }
      console.debug('translate_preview: response', data);
      if (!data) return '';
      if (data && (data.en || data.en === '')) {
        // if success is false but en present, return it (fallback)
        if (!data.success) console.warn('translate_preview: returned success=false', data.error || 'no error');
        return data.en || '';
      }
      return '';
    } catch(e){ return ''; }
  }

  // Spinner next to input while translating
  function _showTranslatingIndicator(target){
    try{
      if (!target) return;
      // ensure a container for indicator
      var existing = target.parentNode && target.parentNode.querySelector('.rdo-translate-spinner[data-for="'+(target.id||'')+'"]');
      if (existing) return existing;
      var span = document.createElement('span');
      span.className = 'rdo-translate-spinner';
      span.setAttribute('data-for', target.id || '');
      span.title = 'Translating...';
      span.style.marginLeft = '6px';
      span.style.fontSize = '14px';
      span.style.opacity = '0.7';
      span.textContent = '…';
      // insert after target
      if (target.nextSibling) target.parentNode.insertBefore(span, target.nextSibling); else target.parentNode.appendChild(span);
      return span;
    }catch(e){}
    return null;
  }
  function _hideTranslatingIndicator(target){
    try{
      if (!target) return;
      var sel = '.rdo-translate-spinner[data-for="'+(target.id||'')+'"]';
      var existing = target.parentNode && target.parentNode.querySelector(sel);
      if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
    }catch(e){}
  }

  // Ensure spinner styles exist (idempotent)
  try {
    if (!document.getElementById('rdo-translate-spinner-styles')) {
      var st = document.createElement('style'); st.id = 'rdo-translate-spinner-styles';
      st.type = 'text/css';
      st.appendChild(document.createTextNode('\n.rdo-translate-spinner { display: inline-block; margin-left: 6px; font-size: 16px; color: #666; vertical-align: middle; }\n.rdo-translate-spinner.loading { font-style: italic; opacity: 0.9; }\n.rdo-translate-spinner[data-for] { margin-left: 8px; }\n'));
      document.head.appendChild(st);
    }
  } catch(_){ }

  // Vincula handlers de tradução PT->EN dentro de um escopo (container). idempotente por elemento.
  function _bindTranslationHandlers(scope){
    try {
      var ctx = scope || document;
      try { console.debug && console.debug('rdo.core: _bindTranslationHandlers scope=', ctx && (ctx.id || ctx.nodeName)); } catch(_){}
      // Activities: each row has .atividade-comentario-pt and .atividade-comentario-en
      var ptComments = Array.prototype.slice.call(ctx.querySelectorAll('.atividade-comentario-pt')) || [];
      ptComments.forEach(function(el){
        try {
          if (el.__translateBound) return;
          var row = el.closest('.activities-row');
          var target = row ? row.querySelector('.atividade-comentario-en') : null;
          if (!target) { el.__translateBound = true; return; }
          var handler = _debounce(async function(ev){
            try {
              var txt = el.value || '';
              var spinner = _showTranslatingIndicator(target);
              var trans = await _translatePreview(txt);
              _hideTranslatingIndicator(target);
              if (trans != null) { target.value = trans; }
            } catch(_){ try{ _hideTranslatingIndicator(target); }catch(_){} }
          }, 450);
          el.addEventListener('input', handler);
          el.__translateBound = true;
        } catch(_){}
      });

      // Observações
      try {
        // Support both Editor and Supervisor IDs for Observações
        var obsPt = ctx.querySelector('#edit-observacoes-pt, #sup-observacoes-pt');
        var obsEn = ctx.querySelector('#edit-observacoes-en, #sup-observacoes-en');
        if (obsPt && obsEn && !obsPt.__translateBound){
          try { console.debug && console.debug('rdo.core: binding observacoes'); } catch(_){ }
          var h = _debounce(async function(){
              try{
                var t = obsPt.value||'';
                var spinner = _showTranslatingIndicator(obsEn);
                var tr = await _translatePreview(t);
                _hideTranslatingIndicator(obsEn);
                if (tr != null) obsEn.value = tr;
              }catch(_){ try{ _hideTranslatingIndicator(obsEn); }catch(_){} }
            }, 700);
            obsPt.addEventListener('input', h);
          obsPt.__translateBound = true;
        }
      } catch(_){ }

      // Planejamento
      try {
        // Support both Editor and Supervisor IDs for Planejamento
        var planPt = ctx.querySelector('#edit-planejamento-pt, #sup-planejamento-pt');
        var planEn = ctx.querySelector('#edit-planejamento-en, #sup-planejamento-en');
        if (planPt && planEn && !planPt.__translateBound){
          try { console.debug && console.debug('rdo.core: binding planejamento'); } catch(_){ }
          var h2 = _debounce(async function(){
              try{
                var t = planPt.value||'';
                var spinner = _showTranslatingIndicator(planEn);
                var tr = await _translatePreview(t);
                _hideTranslatingIndicator(planEn);
                if (tr != null) planEn.value = tr;
              }catch(_){ try{ _hideTranslatingIndicator(planEn); }catch(_){} }
            }, 700);
            planPt.addEventListener('input', h2);
          planPt.__translateBound = true;
        }
      } catch(_){ }
    } catch(_){}
  }

  // Bind translation handlers specifically for Supervisor modal scope
  function ensureSupervisorTranslationsBound(){
    try {
      if (ensureSupervisorTranslationsBound.__bound) return;
      var scope = document.getElementById('supv-content') || document.getElementById('supv-modal-overlay') || document;
      if (!scope) return;
      try { _bindTranslationHandlers(scope); } catch(_){ }

      // Trigger initial translations for Observações and Planejamento if present (debounced inside handlers)
      try {
        var obsPt = scope.querySelector('#sup-observacoes-pt');
        var planPt = scope.querySelector('#sup-planejamento-pt');
        if (obsPt) { try { obsPt.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ } }
        if (planPt) { try { planPt.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ } }
      } catch(_){ }

      // Also bind activity rows translation (PT->EN) when activities are changed/added
      try {
        var actWrap = document.getElementById('atividades-wrapper');
        if (actWrap && !actWrap.__supTransBound) {
          actWrap.addEventListener('input', function(ev){ try { _bindTranslationHandlers(actWrap); } catch(_){} }, { passive: true });
          actWrap.__supTransBound = true;
        }
      } catch(_){ }

      ensureSupervisorTranslationsBound.__bound = true;
    } catch(e){ console.warn('ensureSupervisorTranslationsBound failed', e); }
  }
  function _renderExistingPhotos(list){
    try {
      var wrap = document.getElementById('edit-fotos-existing'); if (!wrap) return;
      wrap.innerHTML = '';
      var items = Array.isArray(list) ? list : [];
      if (!items.length) { var txt = wrap.getAttribute('data-empty-text') || 'Sem fotos'; wrap.textContent = txt; return; }
      var grid = document.createElement('div'); grid.className = 'photo-grid-inner'; grid.style.display='grid'; grid.style.gridTemplateColumns='repeat(auto-fill,minmax(96px,120px))'; grid.style.gap='8px';
      items.forEach(function(it){
        try {
          var url = (typeof it === 'string') ? it : (it.url || it.href || ''); if (!url) return;
          var item = document.createElement('div'); item.className = 'photo-slot photo-item'; item.dataset.url = url; item.style.position='relative'; item.style.display='inline-block'; item.style.borderRadius='8px'; item.style.overflow='hidden'; item.style.border='1px solid rgba(0,0,0,0.06)';
          var a = document.createElement('a'); a.href=url; a.target='_blank'; a.rel='noopener'; a.style.display='block';
          var img = document.createElement('img'); img.src=url; img.alt=(it.name||'Foto'); img.style.display='block'; img.style.width='160px'; img.style.height='80px'; img.style.objectFit='cover';
          a.appendChild(img);
          var btn = document.createElement('button'); btn.type='button'; btn.className='photo-remove'; btn.title='Remover foto'; btn.setAttribute('aria-label','Remover foto');
          btn.textContent = '×';
          Object.assign(btn.style,{position:'absolute',top:'6px',right:'6px',background:'rgba(220,0,0,0.95)',color:'#fff',border:'none',borderRadius:'12px',width:'24px',height:'24px',display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer',boxShadow:'0 1px 2px rgba(0,0,0,0.25)'});
          item.appendChild(a);
          item.appendChild(btn);
          grid.appendChild(item);
        } catch(_){ }
      });
      wrap.appendChild(grid);
    } catch(_){ }
  }

  // Delegated handler: quando clicar em remover foto, substituir visualmente e adicionar hidden input fotos_remove[] ao form-editor
  document.addEventListener('click', function(ev){
    try {
      var btn = ev.target && ev.target.closest && ev.target.closest('.photo-remove');
      if (!btn) return;
      ev.preventDefault();
      var item = btn.closest && btn.closest('.photo-slot, .photo-item') ? btn.closest('.photo-slot, .photo-item') : (btn.closest('.photo-item') || null);
      if (!item) return;
      var url = item.dataset && item.dataset.url ? item.dataset.url : null;
      var form = document.getElementById('form-editor') || document.getElementById('form-supervisor');

      // If we have an rdo_id, perform immediate AJAX deletion (photos-first style)
      var rdoIdEl = null;
      try {
        if (form) rdoIdEl = form.querySelector('#edit-rdo-id') || form.querySelector('#sup-rdo-id') || form.querySelector('input[name="rdo_id"]');
      } catch(_){ rdoIdEl = null; }

      if (rdoIdEl && rdoIdEl.value) {
        // show overlay on the photo
        var overlay = document.createElement('div');
        overlay.className = 'photo-action-overlay';
        overlay.style.position='absolute'; overlay.style.left=0; overlay.style.top=0; overlay.style.right=0; overlay.style.bottom=0; overlay.style.display='flex'; overlay.style.alignItems='center'; overlay.style.justifyContent='center'; overlay.style.background='rgba(0,0,0,0.5)'; overlay.style.color='#fff'; overlay.style.fontSize='13px';
        overlay.innerHTML = '<div>Removendo...</div>';
        try { item.appendChild(overlay); } catch(_){ }

        (async function(){
          try {
            // Use new lightweight endpoint that deletes by basename to avoid complex payloads
            var fd = new FormData();
            fd.append('rdo_id', rdoIdEl.value);
            // enviar apenas o basename do arquivo para remoção
            var basename = (url || '').split('/').slice(-1)[0].split('?')[0];
            fd.append('foto_basename', basename || url || '');
            var controller = new AbortController();
            var to = setTimeout(function(){ try{ controller.abort(); }catch(_){} }, 30000);
            var resp = await fetch('/api/rdo/delete_photo_basename/', { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCSRF(form) || _getCookie('csrftoken') || '' }, signal: controller.signal });
            clearTimeout(to);
            var data = null; try { data = await resp.json(); } catch(_) { data = null; }
            if (resp.ok && data && data.success) {
              try {
                // Append hidden input to form so subsequent saves are aware of removal
                if (form) {
                  var hid = document.createElement('input'); hid.type='hidden'; hid.name='fotos_remove[]'; hid.value = url || basename || '';
                  hid.className = 'fotos-remove-input'; form.appendChild(hid);
                  // Clear any file inputs that may contain the same basename to avoid re-upload
                  try {
                    var finputs = Array.prototype.slice.call((form.querySelectorAll('input[type=file][name="fotos"]')) || []);
                    finputs.forEach(function(fi){
                      try {
                        if (!fi.files || !fi.files.length) return;
                        var match=false;
                        for (var ii=0; ii<fi.files.length; ii++){
                          try { if (fi.files[ii].name === basename || fi.files[ii].name.endsWith(basename)) { match=true; break; } } catch(_){}
                        }
                        if (match) {
                          try { fi.value = ''; } catch(e) { try { var clone = fi.cloneNode(true); fi.parentNode.replaceChild(clone, fi); } catch(_){} }
                        }
                      } catch(_){ }
                    });
                  } catch(_){ }
                }
                try { item.parentNode && item.parentNode.removeChild(item); } catch(_){ }
                try { _updateFotosCount(); } catch(_){ }
                showToast(data.message || 'Foto removida', 'success');
              } catch(e){ showToast('Foto removida (parcial)', 'success'); }
            } else {
              // restore overlay with error
              try { if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); } catch(_){ }
              var msg = (data && (data.error || data.message)) || 'Falha ao remover foto';
              showToast(msg, 'error');
            }
          } catch(err){
            try { if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); } catch(_){ }
            showToast(err && err.name === 'AbortError' ? 'Tempo de requisição expirou' : 'Erro de rede ao remover foto', 'error');
          }
        })();
      } else {
        // No rdo_id: fallback to marking for removal on save (existing behavior)
        try {
          item.parentNode && item.parentNode.removeChild(item);
        } catch(_){ }
        try {
          if (!form) return;
          var inp = document.createElement('input'); inp.type = 'hidden'; inp.name = 'fotos_remove[]'; inp.value = url || ''; inp.className='fotos-remove-input'; form.appendChild(inp);
          _updateFotosCount();
          showToast('Foto marcada para remoção (será excluída ao salvar)', 'info');
        } catch(_){ }
      }
    } catch(_){ }
  }, false);
  function _fillTeam(equipe){
    try {
      var wrap = document.getElementById('edit-equipe-wrapper'); if (!wrap) return;
      var rows = wrap.querySelectorAll('.team-row');
      // remove extras, keep just one template row
      Array.prototype.forEach.call(rows, function(row, idx){ if (idx>0 && row.parentNode) row.parentNode.removeChild(row); });
      var base = wrap.querySelector('.team-row'); if (!base) return;
      var list = Array.isArray(equipe) ? equipe : [];
      if (!list.length) return;

      function _setField(el, value){
        if (!el) return;
        var v = (value === null || typeof value === 'undefined') ? '' : String(value);
        try {
          if (el.tagName && el.tagName.toLowerCase() === 'select'){
            try { el.value = v; } catch(e){}
            // se select não possui a option, criar temporária para exibir o valor
            if (v && String(el.value || '') === ''){
              try { var op = document.createElement('option'); op.value = v; op.textContent = v; el.appendChild(op); el.value = v; } catch(e){}
            }
          } else {
            try { el.value = v; } catch(e){}
          }
        } catch(e){}
      }

      // preencher primeira linha
      var first = base;
      var f0 = list[0] || {};
      var selN = first.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
      var selF = first.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
      _setField(selN, f0.nome || f0.name || '');
      _setField(selF, f0.funcao || f0.role || '');

      // clonar para demais membros
      for (var i=1;i<list.length;i++){
        var clone = first.cloneNode(true);
        var it = list[i] || {};
        var cN = clone.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
        var cF = clone.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
        _setField(cN, it.nome || it.name || '');
        _setField(cF, it.funcao || it.role || '');
        first.parentNode.insertBefore(clone, wrap.querySelector('.team-footer'));
      }
    } catch(_){ }
  }

  async function loadEditorDetails(){
    try {
      var btn = document.getElementById('edit-btn-load-details');
      var rid = (document.getElementById('edit-rdo-id')||{}).value;
      // If hidden id is empty, prefer the last clicked row id (set when opening the editor)
      if (!rid) {
        try { if (window && window.__last_rdo_row_id) { rid = String(window.__last_rdo_row_id || ''); } } catch(_){ }
      }
      // Se hidden id ainda estiver vazio, tentar resolver pelo número mostrado em #edit-rdo
      if (!rid) {
        try {
          var displayed = (document.getElementById('edit-rdo')||{}).value || '';
          if (displayed) {
            var rresp = await fetch('/rdo/find_by_number/?rdo=' + encodeURIComponent(displayed), { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (rresp && rresp.ok) {
              var jd = await rresp.json();
              if (jd && jd.success && jd.id) {
                rid = String(jd.id);
                // atualizar hidden para próximos usos
                try { var hidEl = document.getElementById('edit-rdo-id'); if (hidEl) hidEl.value = rid; } catch(_){ }
                // atualizar chips de contexto
                try { var ctxRdo = document.getElementById('edit-context-rdo'); if (ctxRdo) ctxRdo.textContent = ''; } catch(_){ }
                try { var ctxOs = document.getElementById('edit-context-os'); if (ctxOs) ctxOs.textContent = ''; } catch(_){ }
              }
            }
          }
        } catch(e){ /* ignore */ }
      }
      if (!rid) { showToast('RDO não definido para carregar', 'error'); return; }
      if (btn) { btn.classList.add('loading'); btn.setAttribute('aria-disabled','true'); btn.disabled = true; }
  // Request the server-rendered editor fragment when available
  var url = '/rdo/' + encodeURIComponent(rid) + '/detail/?render=editor';
      try {
        // Determine the desired tank id in a robust way. Prefer explicit global set when
        // opening the modal, then the hidden input, then the visible select inside the
        // editor fragment (if present). This avoids stale/empty tank_id being used.
        var lastTank = '';
        try { if (window && window.__last_rdo_tanque_id) lastTank = String(window.__last_rdo_tanque_id || ''); } catch(_){ lastTank = ''; }
        // hidden input used by openEditorModal
        try { var hidTid = (document.getElementById('edit-tanque-id')||{}).value; if (!lastTank && hidTid) lastTank = String(hidTid||''); } catch(_){ }
        // visible select inside the fragment (user may have changed it directly)
        try { var sel = document.getElementById('edit-select-tanque'); if (!lastTank && sel && sel.value) lastTank = String(sel.value || ''); } catch(_){ }
        // Persist back to global so subsequent calls are consistent
        try { if (lastTank && window) window.__last_rdo_tanque_id = String(lastTank); } catch(_){ }
        if (lastTank) {
          url += '&tank_id=' + encodeURIComponent(lastTank);
        }
        try { console.debug && console.debug('loadEditorDetails - requesting editor fragment', { url: url, lastTank: lastTank }); } catch(_){ }
      } catch(_){ }
      var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();
      // Se o backend retornou um fragmento HTML, injetar no container
      if (data && data.html) {
        try {
          var container = document.getElementById('rdo-edit-content');
          if (container) {
            // substituir apenas o conteúdo interno, preservando o <form> pai e CSRF
            container.innerHTML = data.html;
            // após injetar, rebind handlers necessários para tornar o formulário interativo
            // 1) bind add/remove atividades
            (function bindActivities(){
              try {
                var wrapper = document.getElementById('edit-atividades-wrapper') || document.getElementById('edit-atividades-wrapper');
                if (!wrapper) return;
                var addBtn = document.getElementById('edit-btn-add-atividade');
                var removeLast = document.getElementById('edit-btn-remove-last-atividade');
                function addRow(){
                  try {
                    var base = wrapper.querySelector('.activities-row');
                    if (!base) return;
                    var clone = base.cloneNode(true);
                    // clear inputs
                    Array.prototype.forEach.call(clone.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; });
                    base.parentNode.insertBefore(clone, wrapper.querySelector('.activities-footer'));
                    computeModalAggregates();
                  } catch(_){}
                }
                function removeLastRow(){
                  try {
                    var rows = wrapper.querySelectorAll('.activities-row');
                    if (rows.length <= 1) return;
                    var last = rows[rows.length-1]; if (last && last.parentNode) last.parentNode.removeChild(last);
                    computeModalAggregates();
                  } catch(_){}
                }
                if (addBtn) { addBtn.addEventListener('click', function(ev){ ev.preventDefault(); addRow(); }); }
                if (removeLast) { removeLast.addEventListener('click', function(ev){ ev.preventDefault(); removeLastRow(); }); }
                // bind remove buttons on existing rows
                Array.prototype.forEach.call(wrapper.querySelectorAll('.btn-remove-atividade'), function(b){ b.addEventListener('click', function(ev){ ev.preventDefault(); var row = b.closest('.activities-row'); if (row && row.parentNode) row.parentNode.removeChild(row); computeModalAggregates(); }); });
              } catch(_){}
            })();

            // 2) bind equipe add/remove
            (function bindTeam(){
              try {
                var wrap = document.getElementById('edit-equipe-wrapper'); if (!wrap) return;
                var add = document.getElementById('edit-btn-add-membro'); var rem = document.getElementById('edit-btn-remove-membro');
                function addMember(){ try { var base = wrap.querySelector('.team-row'); if (!base) return; var clone = base.cloneNode(true); Array.prototype.forEach.call(clone.querySelectorAll('select,input,textarea'), function(el){ if(el.tagName.toLowerCase()==='select') el.selectedIndex=0; else el.value=''; }); base.parentNode.insertBefore(clone, wrap.querySelector('.team-footer')); } catch(_){} }
                function removeMember(){ try { var rows = wrap.querySelectorAll('.team-row'); if (rows.length<=1) return; var last = rows[rows.length-1]; if(last && last.parentNode) last.parentNode.removeChild(last); } catch(_){} }
                if (add) add.addEventListener('click', function(ev){ ev.preventDefault(); addMember(); });
                if (rem) rem.addEventListener('click', function(ev){ ev.preventDefault(); removeMember(); });
              } catch(_){}
            })();

            // 3) bind fotos add button (proxy to input)
            (function bindFotos(){
              try {
                var photoBtn = document.getElementById('edit-btn-add-foto'); var input = document.getElementById('edit-fotos');
                if (photoBtn && input) photoBtn.addEventListener('click', function(ev){ ev.preventDefault(); input.click(); });
              } catch(_){}
            })();

            // Garantir que a linha de cabeçalho das atividades exista (Atividade / Início / Fim / Comentários / Ações)
            try {
              var _wrapper = document.getElementById('edit-atividades-wrapper');
              if (_wrapper && !_wrapper.querySelector('.activities-head-row')){
                var head = document.createElement('div'); head.className = 'activities-head-row';
                head.innerHTML = '<div class="col atividade">Atividade</div>' +
                                 '<div class="col horario">Início</div>' +
                                 '<div class="col horario">Fim</div>' +
                                 '<div class="col comentario-pt">Comentário (PT)</div>' +
                                 '<div class="col comentario-en">Comentário (EN)</div>' +
                                 '<div class="col actions" aria-label="Remover atividade">×</div>';
                _wrapper.insertBefore(head, _wrapper.firstChild);
              }
            } catch(_){ }

            // 4) bind recalcular button to compute aggregates
            try { var recalc = document.getElementById('edit-btn-recalcular-calculos'); if (recalc) recalc.addEventListener('click', function(ev){ ev.preventDefault(); computeModalAggregates(); showToast('Cálculos atualizados', 'success'); }); } catch(_){}

            // Bind translation handlers for PT->EN and then ensure calculation routines run so readonly inputs
            try { if (typeof _bindTranslationHandlers === 'function') _bindTranslationHandlers(container); } catch(_){ }
            // Garantir que o handler de submit do editor esteja ligado
            try { if (typeof ensureEditorSubmitBound === 'function') ensureEditorSubmitBound(); } catch(_){ }
            // After injection and binding, ensure calculation routines run so readonly inputs
            // produced by JS (bombeio, resíduo líquido/total, res. sólidos) are populated.
            try { if (typeof computeEditorBombeio === 'function') computeEditorBombeio(); } catch(e){}
            try { if (typeof computeEditorResSolidos === 'function') computeEditorResSolidos(); } catch(e){}
            try { if (typeof computeEditorResTotal === 'function') computeEditorResTotal(); } catch(e){}

            showToast('Detalhes carregados (render)', 'success');
            return;
          }
        } catch(e){ console.warn('failed to inject html fragment', e); }
      }

      var r = data && (data.rdo || data.data || data.item) || null;
      if (!r) { showToast('Resposta sem dados do RDO', 'error'); return; }

      // Identificação - normalizar nomes de campo (há variações entre endpoints)
      try {
        var displayedRdo = '';
        if (typeof r.rdo !== 'undefined' && r.rdo !== null && r.rdo !== '') displayedRdo = String(r.rdo);
        else if (typeof r.rdo_contagem !== 'undefined' && r.rdo_contagem !== null && r.rdo_contagem !== '') displayedRdo = String(r.rdo_contagem);
        else if (typeof r.id !== 'undefined' && r.id !== null) displayedRdo = String(r.id);
        _setValById('edit-rdo', displayedRdo);
      } catch(_){ _setValById('edit-rdo', ''); }
  try { var ctxRdo = document.getElementById('edit-context-rdo'); if (ctxRdo) ctxRdo.textContent = (typeof displayedRdo !== 'undefined' && displayedRdo) ? displayedRdo : ''; } catch(_){ }
      try { var hidEl = document.getElementById('edit-rdo-id'); if (hidEl && r.id) hidEl.value = String(r.id); } catch(_){ }
      _setSelectById('edit-turno', r.turno);
      _setValById('edit-data-inicio', (r.rdo_data_inicio||'').slice(0,10));
      _setValById('edit-previsao-termino', (r.rdo_previsao_termino||'').slice(0,10));
      _setValById('edit-contrato-po', r.contrato_po);
  try {
    var displayedOs = '';
    if (typeof r.numero_os !== 'undefined' && r.numero_os !== null && r.numero_os !== '') displayedOs = String(r.numero_os);
    else if (typeof r.os !== 'undefined' && r.os !== null && r.os !== '') displayedOs = String(r.os);
    var ctxOs = document.getElementById('edit-context-os'); if (ctxOs) ctxOs.textContent = displayedOs || '';
  } catch(_){ }

      // PT
      _setBoolSelectSimNaoById('edit-pt-abertura', r.pt_abertura);
      _setChecksByName('pt_turnos[]', r.pt_turnos);
      _setValById('edit-pt-manha', r.pt_num_manha);
      _setValById('edit-pt-tarde', r.pt_num_tarde);
      _setValById('edit-pt-noite', r.pt_num_noite);

      // Tanque & Ambiente
      _setValById('edit-tanque-cod', r.tanque_codigo);
      _setValById('edit-tanque-nome', r.tanque_nome);
      _setSelectById('edit-tipo-tanque', r.tipo_tanque);
      _setValById('edit-n-comp', r.numero_compartimento);
      _setValById('edit-gavetas', r.gavetas);
      _setValById('edit-patamar', r.patamar);
      _setValById('edit-volume', r.volume_tanque_exec);
      _setSelectById('edit-servico', r.servico_exec);
      _setSelectById('edit-metodo', r.metodo_exec);
      _setBoolSelectSimNaoById('edit-espaco-conf', r.espaco_confinado);
      // Populate EC grid robustly: support multiple shapes returned by the backend
      try {
        var entradasArr = [], saidasArr = [];
        // 1) Prefer structured ec_times { entrada_1..6, saida_1..6 }
        if (r.ec_times && typeof r.ec_times === 'object') {
          for (var ii = 1; ii <= 6; ii++) {
            entradasArr.push(r.ec_times['entrada_' + ii] || '');
            saidasArr.push(r.ec_times['saida_' + ii] || '');
          }
        } else if (r.ec_times_json && typeof r.ec_times_json === 'string') {
          // 2) ec_times_json persisted as JSON-text in the model
          try {
            var parsed_ec = JSON.parse(r.ec_times_json || '{}');
            if (parsed_ec) {
              entradasArr = Array.isArray(parsed_ec.entrada) ? parsed_ec.entrada.slice(0,6) : (Array.isArray(parsed_ec.entradas) ? parsed_ec.entradas.slice(0,6) : []);
              saidasArr = Array.isArray(parsed_ec.saida) ? parsed_ec.saida.slice(0,6) : (Array.isArray(parsed_ec.saidas) ? parsed_ec.saidas.slice(0,6) : []);
            }
          } catch(e) { /* ignore parse errors */ }
        } else if (Array.isArray(r.entrada_confinado) || Array.isArray(r.saida_confinado)) {
          // 3) Legacy arrays provided directly
          entradasArr = Array.isArray(r.entrada_confinado) ? r.entrada_confinado.slice(0,6) : [];
          saidasArr = Array.isArray(r.saida_confinado) ? r.saida_confinado.slice(0,6) : [];
        } else {
          // 4) Single legacy time fields (string) -> put into first slot
          if (r.entrada_confinado) entradasArr.push(r.entrada_confinado);
          if (r.saida_confinado) saidasArr.push(r.saida_confinado);
          // 5) Debug/raw shape: ec_raw may contain entrada/saida arrays
          if ((entradasArr.length === 0 || saidasArr.length === 0) && r.ec_raw && typeof r.ec_raw === 'object') {
            var eRaw = r.ec_raw.entrada || r.ec_raw.entrada_list || r.ec_raw.entradas || r.ec_raw.entrada_confinado || [];
            var sRaw = r.ec_raw.saida || r.ec_raw.saida_list || r.ec_raw.saidas || r.ec_raw.saida_confinado || [];
            if (Array.isArray(eRaw) && eRaw.length) entradasArr = eRaw.slice(0,6);
            if (Array.isArray(sRaw) && sRaw.length) saidasArr = sRaw.slice(0,6);
          }
        }
        // Ensure arrays have same length for grid (pad with empty strings)
        var maxn = Math.max(entradasArr.length, saidasArr.length, 6);
        for (var k = 0; k < maxn; k++) { if (typeof entradasArr[k] === 'undefined') entradasArr[k] = ''; if (typeof saidasArr[k] === 'undefined') saidasArr[k] = ''; }
        _setECGrid(entradasArr, saidasArr);
      } catch(_){ try { _setECGrid(r.entrada_confinado, r.saida_confinado); } catch(_){} }
      _setValById('edit-operadores', r.operadores_simultaneos);
      _setValById('edit-h2s', r.h2s_ppm);
      _setValById('edit-lel', r.lel);
      _setValById('edit-co', r.co_ppm);
      _setValById('edit-o2', r.o2_percent);

      // Operacionais
      // Preencher o select de sentido: preferir o booleano (compat com modelo),
      // senão usar o texto legado. O helper _setBoolSelectTrueFalseById aceita
      // true/false/1/0 e converte para 'true'/'false' conforme os option values.
      if (typeof r.sentido_limpeza_bool !== 'undefined' && r.sentido_limpeza_bool !== null) {
        _setBoolSelectTrueFalseById('edit-sentido', r.sentido_limpeza_bool);
      } else {
        // fallback: aceitar r.sentido_limpeza textual (ex.: 'Vante para Ré' ou 'Ré para Vante')
        // Normalizar para os valores esperados pelo select ('true' / 'false') quando possível.
        try {
          var s = r.sentido_limpeza;
          if (typeof s === 'string') {
            var sl = s.toLowerCase();
            if (sl.indexOf('vante') !== -1 && sl.indexOf('ré') !== -1) {
              // presumir vante -> ré quando o texto contém 'vante' antes de 'ré'
              _setBoolSelectTrueFalseById('edit-sentido', true);
            } else if (sl.indexOf('ré') !== -1 && sl.indexOf('vante') !== -1) {
              // presumir ré -> vante quando 'ré' aparece antes de 'vante'
              _setBoolSelectTrueFalseById('edit-sentido', false);
            } else {
              // valor textual desconhecido: setar diretamente (deixa em branco se não existir)
              _setSelectById('edit-sentido', s);
            }
          } else {
            // não é string nem booleano: limpar
            _setSelectById('edit-sentido', '');
          }
        } catch(e){ _setSelectById('edit-sentido', ''); }
      }
      _setValById('edit-tempo-bomba', r.tempo_bomba);
      _setValById('edit-vazao-bombeio', r.vazao_bombeio);
      _setValById('edit-bombeio', r.bombeio);
      _setValById('edit-res-liq', r.residuo_liquido);
      _setValById('edit-ensac', r.ensacamento_dia);
      _setValById('edit-tambores', r.tambores_dia);
      _setValById('edit-res-sol', r.residuos_solidos);
      _setValById('edit-res-total', r.residuos_totais);

      // Limpeza: preencher percentuais (diário / cumulativo) com suporte a aliases retornados pelo backend
      try {
        var _pick = function(obj, keys){ for (var i=0;i<keys.length;i++){ var k = keys[i]; if (typeof obj[k] !== 'undefined' && obj[k] !== null) return obj[k]; } return null; };
        var pl = _pick(r, ['percentual_limpeza', 'avanco_limpeza', 'limpeza', 'percentual_limpeza_diario']);
        var plc = _pick(r, ['percentual_limpeza_cumulativo', 'limpeza_acu', 'limpeza_acumulado', 'percentual_limpeza_acu']);
        var plf = _pick(r, ['percentual_limpeza_fina', 'avanco_limpeza_fina', 'limpeza_fina']);
        var plfc = _pick(r, ['percentual_limpeza_fina_cumulativo', 'limpeza_fina_acu', 'limpeza_fina_acumulado']);
        _setValById('percentual_limpeza', pl);
        _setValById('percentual_limpeza_cumulativo', plc);
        _setValById('percentual_limpeza_fina', plf);
        _setValById('percentual_limpeza_fina_cumulativo', plfc);
      } catch(_){ }

      // Recalcular percentuais derivados (garantir que campos readonly sejam atualizados)
      try { if (typeof computeEditorPercentuais === 'function') computeEditorPercentuais(); } catch(_){ }

  // Garantir que cálculos de bombeio/resíduo sejam (re)ligados e executados
  try { if (typeof computeEditorBombeio === 'function') computeEditorBombeio(); } catch(e){}

  // Garantir que cálculo de Res. Total esteja disponível e ligado
  try { if (typeof computeEditorResTotal === 'function') computeEditorResTotal(); } catch(e){}
  // Garantir que cálculo de Res. Sólidos esteja ligado
  try { if (typeof computeEditorResSolidos === 'function') computeEditorResSolidos(); } catch(e){}

      // Cálculos/Resumos (se vierem)
      _setValById('edit-total-atividades', r.total_atividade_min);
      _setValById('edit-total-confinado', r.total_confinado_min);
      _setValById('edit-total-abertura-pt', r.total_abertura_pt_min);
      _setValById('edit-total-atividades-efetivas', r.total_atividades_efetivas_min);
      _setValById('edit-total-n-efetivo-confinado', r.total_n_efetivo_confinado_min);
      _setValById('edit-total-nao-efetivas-fora', r.total_nao_efetivas_fora_min);

      // Observações / Planejamento
      _setValById('edit-observacoes-pt', r.observacoes);
      if (r.observacoes_en) _setValById('edit-observacoes-en', r.observacoes_en);
      _setValById('edit-planejamento-pt', r.planejamento);
      if (r.planejamento_en) _setValById('edit-planejamento-en', r.planejamento_en);

      // Equipe (se disponível)
      if (Array.isArray(r.equipe)) { _fillTeam(r.equipe); }
      else if (Array.isArray(r.equipe_nomes) && Array.isArray(r.equipe_funcoes)) {
        var eq = []; var n = Math.max(r.equipe_nomes.length, r.equipe_funcoes.length);
        for (var i=0;i<n;i++){ eq.push({ nome: r.equipe_nomes[i], funcao: r.equipe_funcoes[i] }); }
        _fillTeam(eq);
      }

      // Fotos existentes (se disponível)
      if (Array.isArray(r.fotos)) _renderExistingPhotos(r.fotos);

      // Preencher horários das atividades (início/fim) a partir de r.atividades se disponíveis
      try {
        if (Array.isArray(r.atividades) && r.atividades.length) {
          var wrapperRows = document.querySelectorAll('#edit-atividades-wrapper .activities-row');
          var rowsArr = Array.prototype.slice.call(wrapperRows || []);
          var need = r.atividades.length - rowsArr.length;
          var wrapper = document.getElementById('edit-atividades-wrapper');
          // clone last row if need more
          if (need > 0 && wrapper && rowsArr.length) {
            var base = rowsArr[rowsArr.length-1];
            for (var c=0;c<need;c++){
              try {
                var clone = base.cloneNode(true);
                // clear values in clone
                Array.prototype.forEach.call(clone.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; });
                base.parentNode.insertBefore(clone, wrapper.querySelector('.activities-footer'));
                rowsArr.push(clone);
              } catch(_){ }
            }
          }
          for (var i=0;i<Math.min(rowsArr.length, r.atividades.length); i++){
            try{
              var at = r.atividades[i] || {};
              var row = rowsArr[i];
              var sel = row.querySelector('.atividade-nome-select, select[name="atividade_nome[]"]');
              if (sel && (at.atividade || at.name || at.nome)) {
                try { sel.value = String(at.atividade || at.name || at.nome); } catch(_){}
              }
              var inpInicio = row.querySelector('input.atividade-inicio, input[name="atividade_inicio[]"]');
              var inpFim = row.querySelector('input.atividade-fim, input[name="atividade_fim[]"]');
              if (inpInicio) inpInicio.value = _formatTimeForInput(at.inicio || at.start || at.atividade_inicio || at.inicio_hora || '');
              if (inpFim) inpFim.value = _formatTimeForInput(at.fim || at.end || at.atividade_fim || at.fim_hora || '');
              var cpt = row.querySelector('.atividade-comentario-pt, input[name="atividade_comentario_pt[]"], textarea[name="atividade_comentario_pt[]"]');
              var cen = row.querySelector('.atividade-comentario-en, input[name="atividade_comentario_en[]"], textarea[name="atividade_comentario_en[]"]');
              if (cpt) cpt.value = (at.comentario_pt || at.comment_pt || at.comentario || at.comment || '');
              if (cen) cen.value = (at.comentario_en || at.comment_en || at.comment_en || '');
            }catch(_){ }
          }
          // re-run aggregates
          try { computeModalAggregates(); } catch(_){ }
        }
      } catch(_){ }

      // Garantir que a linha de cabeçalho das atividades exista (Atividade / Início / Fim / Comentários / Ações)
      try {
        var _wrapper2 = document.getElementById('edit-atividades-wrapper');
        if (_wrapper2 && !_wrapper2.querySelector('.activities-head-row')){
          var head2 = document.createElement('div'); head2.className = 'activities-head-row';
          head2.innerHTML = '<div class="col atividade">Atividade</div>' +
                            '<div class="col horario">Início</div>' +
                            '<div class="col horario">Fim</div>' +
                            '<div class="col comentario-pt">Comentário (PT)</div>' +
                            '<div class="col comentario-en">Comentário (EN)</div>' +
                            '<div class="col actions" aria-label="Remover atividade">×</div>';
          _wrapper2.insertBefore(head2, _wrapper2.firstChild);
        }
      } catch(_){ }

  try { if (typeof _bindTranslationHandlers === 'function') _bindTranslationHandlers(document.getElementById('rdo-edit-content') || document); } catch(_){ }
  showToast('Detalhes carregados', 'success');
    } catch(err){
      showToast('Falha ao carregar detalhes', 'error');
    } finally {
      var btn = document.getElementById('edit-btn-load-details');
      if (btn) { btn.classList.remove('loading'); btn.removeAttribute('aria-disabled'); btn.disabled = false; }
    }
  }

  // Delegated handler: garantir que mudanças no select de tanques provoquem reload
  // centralizado do fragmento do editor. Alguns templates também adicionam um
  // handler inline; este listener serve como fallback/centralizador para quando
  // o comportamento estiver inconsistênte (por exemplo voltar para um tanque
  // previamente carregado não reaplica os campos).
  try {
    document.addEventListener('change', function(ev){
      try {
        var el = ev && ev.target ? ev.target : null;
        if (!el) return;
        if (el.id === 'edit-select-tanque' || el.matches && el.matches('#edit-select-tanque')) {
          // atualizar hidden e global
          var val = el.value || '';
          try { var hid = document.getElementById('edit-tanque-id'); if (hid) hid.value = val; } catch(_){ }
          try { if (window) window.__last_rdo_tanque_id = String(val || ''); } catch(_){ }
          try { console.debug && console.debug('edit-select-tanque changed, reloading fragment with tank_id=', val); } catch(_){ }
          // carregar novamente os detalhes (centraliza a lógica de fetch e binding)
          try { if (typeof loadEditorDetails === 'function') { loadEditorDetails(); } } catch(_){ }
        }
      } catch(_){ }
    }, false);
  } catch(_){ }

  // ---------- Public API ----------
  onReady(function(){
    // Namespace seguro
    try { window.RDO = window.RDO || {}; } catch(_){ }
    try { window.RDO.openSupervisorModal = openSupervisorModal; } catch(_){ }
    try { window.RDO.computeModalAggregates = computeModalAggregates; } catch(_){ }
    try { window.RDO.openEditorModal = openEditorModal; } catch(_){ }
    // Evitar conflito com rdo.js legado: só definir se não existir
    try { if (!window.rdoOpenSupervisorModal) window.rdoOpenSupervisorModal = openSupervisorModal; } catch(_){ }
    try { if (!window.computeModalAggregates) window.computeModalAggregates = computeModalAggregates; } catch(_){ }
  try { if (!window.openEditorModal) window.openEditorModal = openEditorModal; } catch(_){ }
  try { if (!window.computeEditorResTotal) window.computeEditorResTotal = computeEditorResTotal; } catch(_){ }
  try { if (!window.computeEditorResSolidos) window.computeEditorResSolidos = computeEditorResSolidos; } catch(_){ }
    // Stub de AI para evitar erros caso template chame algo
    try { window.ai = window.ai || {}; } catch(_){}

    // Botões do modal: fechar/cancelar e Enviar (btn-rdo) -> submit form
    try {
      var overlay = qs('#modal-supervisor-overlay');
      if (overlay) {
        qsa('.modal-close, .modal-cancel', overlay).forEach(function(btn){
          btn.addEventListener('click', function(ev){ ev.preventDefault(); closeModal(); });
        });
      }
      var submitProxy = document.getElementById('btn-rdo');
      if (submitProxy) {
        submitProxy.addEventListener('click', function(ev){ ev.preventDefault(); var f=qs('#form-supervisor'); if (f) f.requestSubmit ? f.requestSubmit() : f.submit(); });
      }
    } catch(_){}

    // ---------- Editor modal: fechar/cancelar e delegação de clique no botão editar da tabela ----------
    try {
      var editorOverlay = document.getElementById('modal-editor-overlay');
      if (editorOverlay) {
        qsa('.editor-close, .editor-cancel', editorOverlay).forEach(function(btn){
          btn.addEventListener('click', function(ev){ ev.preventDefault(); closeEditorModal(); });
        });
        var loadBtn = document.getElementById('edit-btn-load-details');
        if (loadBtn) {
          loadBtn.addEventListener('click', function(ev){ ev.preventDefault(); loadEditorDetails(); });
        }
        // Se o fragmento do editor já estiver presente, vincular handlers de tradução
        try { if (typeof _bindTranslationHandlers === 'function') _bindTranslationHandlers(document); } catch(_){ }
      }
      // Garantir que os botões de recalcular no Editor acionem computeModalAggregates (idempotente)
      // The editor "Recalcular" buttons were removed from the templates. We do
      // not perform mass-binding of non-existent elements. computeModalAggregates
      // continues to run on input events and when fragments are injected.
      // delegação global: abrir ao clicar em botões que deveriam abrir o Editor
      // Nota: ignorar explicitamente cliques em '.action-btn.edit' — esses botões
      // agora abrem o modal Supervisor (handled elsewhere). Isso evita que ambos
      // os modais abram ao mesmo tempo.
      document.addEventListener('click', function(ev){
        try {
          // If the click was explicitly intended to open the Supervisor (marked with
          // data-open="supervisor" or a .open-supervisor class), let that handler run
          // and don't open the Editor here.
          if (ev.target && ev.target.closest && ev.target.closest('[data-open="supervisor"], .open-supervisor, .btn-rdo.open-supervisor')) return;
        } catch(_){ }
        var btn = ev.target && ev.target.closest ? ev.target.closest('.action-btn.edit, .action-btn.open-editor, .action-btn.edit-editor, [data-open="editor"]') : null;
        if (!btn) return;
        ev.preventDefault();
        try {
          var tr = btn.closest('tr');
          var rid = tr && (tr.getAttribute('data-rdo-id') || (tr.dataset && (tr.dataset.rdoId || tr.dataset.rdo_id)));
          // Try to capture a per-tank id if the table row contains one
          var tid = tr && (tr.getAttribute('data-tanque-id') || (tr.dataset && (tr.dataset.tanqueId || tr.dataset.tanque_id)));
          // store last clicked row id and tanque id globally so loadEditorDetails can resolve
          // ambiguous cases where the hidden input is not yet populated.
          try { window.__last_rdo_row_id = rid || ''; } catch(_){ }
          try { window.__last_rdo_tanque_id = tid || ''; } catch(_){ }
          openEditorModal({ rdo_id: rid || '', tanque_id: tid || '' });
        } catch(e){ openEditorModal({}); }
      }, true);
    } catch(_){ }

    // ---------- Filtros: toggle painel, limpar, aplicar e badge ----------
    try {
      var filtersBtn = document.getElementById('btn_rdo_filtros');
      var filtersPanel = document.getElementById('rdo-filters-panel');
      var filterBadge = document.querySelector('#btn_rdo_filtros .filter-badge');
      var filtersForm = document.querySelector('.filters-form');
      var FILTERS_STORAGE_KEY = 'rdo_filters_state_v1';

      function getFilterValues(){
        var vals = {};
        if (!filtersForm) return vals;
        var els = filtersForm.querySelectorAll('input, select, textarea');
        Array.prototype.forEach.call(els, function(el){
          if (!el.name) return;
          var tag = (el.tagName||'').toLowerCase();
          var type = (el.type||'').toLowerCase();
          if ((type === 'checkbox' || type === 'radio') && !el.checked) return;
          var v = (tag === 'select') ? (el.value || '') : (el.value || '');
          if (v !== '' && v != null) vals[el.name] = v;
        });
        return vals;
      }

      function prefillFiltersFromQuery(){
        if (!filtersForm) return;
        try {
          var params = new URLSearchParams(window.location.search || '');
          var els = filtersForm.querySelectorAll('input, select, textarea');
          Array.prototype.forEach.call(els, function(el){
            if (!el.name) return;
            var values = params.getAll(el.name);
            if (!values || values.length === 0) return;
            var tag = (el.tagName||'').toLowerCase();
            var type = (el.type||'').toLowerCase();
            if (type === 'checkbox' || type === 'radio') {
              // marcar se o valor do input aparece nos params
              if (values.indexOf(el.value) !== -1) el.checked = true; else if (type === 'radio') el.checked = false;
              return;
            }
            if (tag === 'select') {
              if (el.multiple) {
                Array.prototype.forEach.call(el.options, function(opt){ opt.selected = (values.indexOf(opt.value) !== -1); });
              } else {
                el.value = values[0];
              }
              return;
            }
            // input/text/textarea
            el.value = values[0];
          });
        } catch(_){}
      }

      // Persistência de filtros no localStorage (quando não há querystring)
      function _collectFormValues(){
        var vals = {};
        if (!filtersForm) return vals;
        var els = filtersForm.querySelectorAll('input, select, textarea');
        Array.prototype.forEach.call(els, function(el){
          if (!el.name) return;
          var tag = (el.tagName||'').toLowerCase();
          var type = (el.type||'').toLowerCase();
          if (type === 'radio') { if (!el.checked) return; }
          if (type === 'checkbox') { if (!el.checked) return; }
          if (tag === 'select' && el.multiple) {
            var arr = Array.prototype.map.call(el.selectedOptions || [], function(o){ return o.value; });
            if (arr.length) vals[el.name] = arr;
          } else {
            if (el.value != null && el.value !== '') {
              if (vals[el.name]) {
                if (!Array.isArray(vals[el.name])) vals[el.name] = [vals[el.name]];
                vals[el.name].push(el.value);
              } else {
                vals[el.name] = el.value;
              }
            }
          }
        });
        return vals;
      }

      function _saveFilters(){
        try { localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(_collectFormValues())); } catch(_){ }
      }

      function _loadFilters(){
        try {
          var raw = localStorage.getItem(FILTERS_STORAGE_KEY);
          if (!raw) return null;
          var obj = JSON.parse(raw);
          return (obj && typeof obj === 'object') ? obj : null;
        } catch(_){ return null; }
      }

      function _applyToForm(map){
        if (!filtersForm || !map) return;
        try {
          var els = filtersForm.querySelectorAll('input, select, textarea');
          Array.prototype.forEach.call(els, function(el){
            if (!el.name || !(el.name in map)) return;
            var v = map[el.name];
            var tag = (el.tagName||'').toLowerCase();
            var type = (el.type||'').toLowerCase();
            var arr = Array.isArray(v) ? v : [v];
            if (type === 'checkbox' || type === 'radio') { el.checked = (arr.indexOf(el.value) !== -1); return; }
            if (tag === 'select') {
              if (el.multiple) Array.prototype.forEach.call(el.options, function(opt){ opt.selected = (arr.indexOf(opt.value) !== -1); });
              else el.value = arr.length ? arr[0] : '';
              return;
            }
            el.value = arr.length ? arr[0] : '';
          });
        } catch(_){ }
      }

      function buildParamsFromForm(){
        var params = new URLSearchParams(window.location.search || '');
        if (!filtersForm) return params;
        // Agrupar valores por nome (suporte a múltiplos)
        var grouped = Object.create(null);
        var els = filtersForm.querySelectorAll('input, select, textarea');
        Array.prototype.forEach.call(els, function(el){
          if (!el.name) return;
          var tag = (el.tagName||'').toLowerCase();
          var type = (el.type||'').toLowerCase();
          if (type === 'radio') { if (!el.checked) return; }
          if (type === 'checkbox') { if (!el.checked) return; }
          var values = [];
          if (tag === 'select' && el.multiple) {
            values = Array.prototype.map.call(el.selectedOptions || [], function(o){ return o.value; });
          } else {
            values = [el.value];
          }
          values.forEach(function(v){
            if (v == null || v === '') return;
            if (!grouped[el.name]) grouped[el.name] = [];
            grouped[el.name].push(v);
          });
        });
        // Limpar chaves existentes do form e re-aplicar valores não vazios
        Object.keys(grouped).forEach(function(name){ params.delete(name); });
        Object.keys(grouped).forEach(function(name){ grouped[name].forEach(function(v){ params.append(name, v); }); });
        // Resetar paginação para a primeira página
        params.set('page', '1');
        return params;
      }

      function clearFormParams(){
        var params = new URLSearchParams(window.location.search || '');
        if (filtersForm) {
          var els = filtersForm.querySelectorAll('input, select, textarea');
          Array.prototype.forEach.call(els, function(el){ if (el.name) params.delete(el.name); });
        }
        params.set('page', '1');
        return params;
      }

      function updateFilterBadge(){
        try {
          var vals = getFilterValues();
          var count = Object.keys(vals).length;
          if (filterBadge) {
            filterBadge.textContent = count ? String(count) : '';
            filterBadge.style.display = count ? 'inline-flex' : 'none';
          }
        } catch(_){}
      }

      function toggleFilters(){
        if (!filtersBtn || !filtersPanel) return;
        var isHidden = (filtersPanel.getAttribute('aria-hidden') !== 'false');
        // se estava oculto, vamos abrir
        if (isHidden) {
          filtersPanel.setAttribute('aria-hidden','false');
          filtersBtn.setAttribute('aria-expanded','true');
          try { filtersPanel.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch(_){}
        } else {
          filtersPanel.setAttribute('aria-hidden','true');
          filtersBtn.setAttribute('aria-expanded','false');
        }
      }

      if (filtersBtn && filtersPanel) {
        filtersBtn.addEventListener('click', function(ev){ ev.preventDefault(); toggleFilters(); });
      }

      // Botões limpar/aplicar
      var clearBtn = document.getElementById('btn_clear_filters');
      if (clearBtn && filtersForm) {
        clearBtn.addEventListener('click', function(){
          try {
            filtersForm.reset();
            updateFilterBadge();
            document.dispatchEvent(new CustomEvent('rdo:filters:clear'));
            showToast('Filtros limpos', 'success');
            // Navegar removendo filtros da URL (preserva outros parâmetros)
            var params = clearFormParams();
            var q = params.toString();
            window.location.search = q ? ('?' + q) : window.location.pathname;
          } catch(e){}
        });
      }

      var applyBtn = document.getElementById('btn_apply_filters');
      if (applyBtn && filtersForm) {
        applyBtn.addEventListener('click', function(){
          var vals = getFilterValues();
          updateFilterBadge();
          try { document.dispatchEvent(new CustomEvent('rdo:filters:apply', { detail: { values: vals } })); } catch(_){}
          showToast('Filtros aplicados', 'success');
          // Navegar incluindo filtros na querystring e resetando para page=1
          var params = buildParamsFromForm();
          var q = params.toString();
          window.location.search = q ? ('?' + q) : window.location.pathname;
        });
      }

      // Atualiza badge ao digitar/mudar e persiste filtros
      if (filtersForm) {
        // Prefill inicial a partir da querystring; se não houver, usar storage
        prefillFiltersFromQuery();
        try {
          var hasQuery = (window.location.search || '').replace(/^\?/, '').length > 0;
          if (!hasQuery) { var stored = _loadFilters(); if (stored) _applyToForm(stored); }
        } catch(_){ }
        filtersForm.addEventListener('input', function(){ updateFilterBadge(); }, { passive: true });
        filtersForm.addEventListener('change', function(){ updateFilterBadge(); _saveFilters(); }, { passive: true });
        // Submit do formulário aplica os filtros
        filtersForm.addEventListener('submit', function(ev){ ev.preventDefault(); if (applyBtn) applyBtn.click(); else {
          var params = buildParamsFromForm(); var q = params.toString(); window.location.search = q ? ('?' + q) : window.location.pathname; }
        });
        setTimeout(updateFilterBadge, 50);
      }

      // Botão opcional: copiar link com filtros (#btn_copy_filter_link)
      try {
        var copyBtn = document.getElementById('btn_copy_filter_link');
        if (copyBtn) {
          copyBtn.addEventListener('click', function(){
            try {
              var params = buildParamsFromForm();
              var url = window.location.origin + window.location.pathname + (params.toString() ? ('?' + params.toString()) : '');
              navigator.clipboard.writeText(url)
                .then(function(){ showToast('Link copiado para a área de transferência', 'success'); })
                .catch(function(){ showToast('Não foi possível copiar o link', 'error'); });
            } catch(e){ showToast('Não foi possível gerar o link', 'error'); }
          });
        }
      } catch(_){ }

      // Limpar storage ao usar o botão limpar
      if (clearBtn) {
        clearBtn.addEventListener('click', function(){ try { localStorage.removeItem(FILTERS_STORAGE_KEY); } catch(_){ } });
      }
    } catch(e){ console.warn('filters init failed', e); }

    // ---------- Notificações/CTA: carregar pendências e abrir popover ----------
    try {
      var notifBtn = document.getElementById('rdo-notification-btn');
      var notifCountEl = notifBtn ? notifBtn.querySelector('.count') : null;
      var cta = document.getElementById('rdo-mobile-cta');
      var ctaPopover = cta ? cta.querySelector('.rdo-cta-popover') : null;
      var ctaClose = document.getElementById('rdo-cta-close');
      var ctaClear = document.getElementById('rdo-cta-clear-cards');

      function updateNotificationCount(n){
        try {
          // Determine authoritative count in this order:
          // 1) explicit numeric argument 'n'
          // 2) window.__rdo_pending_count (set by fetchPending)
          // 3) localStorage 'rdo_pending_count' fallback
          var count = 0;
          try {
            if (typeof n === 'number' && Number.isFinite(n)) {
              count = Number(n);
            } else if (typeof window.__rdo_pending_count === 'number' && Number.isFinite(window.__rdo_pending_count)) {
              count = Number(window.__rdo_pending_count);
            } else {
              try { count = parseInt(localStorage.getItem('rdo_pending_count') || '0', 10) || 0; } catch(_){ count = 0; }
            }
          } catch(_){ count = 0; }

          // sanitize value
          if (!Number.isFinite(count) || count < 0) count = 0;

          // persist authoritative value so other tabs / future fallbacks don't show stale values
          try { localStorage.setItem('rdo_pending_count', String(count)); } catch(_){ }

          if (notifCountEl) {
            notifCountEl.textContent = String(count);
          }
        } catch(_){ }
      }

      async function fetchPending(){
        try {
          var meta = document.querySelector('meta[name="rdo-pending-url"]');
          var url = meta ? meta.getAttribute('content') : null;
          if (!url) {
            console.debug && console.debug('rdo: fetchPending - no meta url found');
            return [];
          }
          console.debug && console.debug('rdo: fetchPending - fetching', url);
          var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With':'XMLHttpRequest' } });
          console.debug && console.debug('rdo: fetchPending - response status', resp.status, resp.statusText);
          if (!resp.ok) {
            console.warn && console.warn('rdo: fetchPending - non-ok response', resp.status);
            return [];
          }
          var data = null;
          try { data = await resp.json(); } catch(e) { console.warn && console.warn('rdo: fetchPending - failed to parse JSON', e); data = null; }
          // Esperado: { success: true, data: [...] } ou { items: [...] }
          var list = (data && (data.data || data.items || data.list)) || [];
          var arr = Array.isArray(list) ? list : [];
          console.debug && console.debug('rdo: fetchPending - parsed list length', arr.length, 'raw:', list);
          // manter cópia global para compatibilidade com lógica legada
          try {
            window.__rdo_pending_list = arr;
            window.__rdo_pending_count = arr.length || 0;
            try { localStorage.setItem('rdo_pending_count', String(window.__rdo_pending_count)); } catch(_){ }
            // store raw payload for debugging if needed
            try { localStorage.setItem('rdo_pending_list', JSON.stringify(arr)); } catch(_){ }
            try { window.__rdo_pending_last_status = resp.status; } catch(_){ }
          } catch(_){ }
          // Tentar popular o select mobile quando houver dados
          try { if (typeof populateOsSelect === 'function') populateOsSelect(); } catch(_){ }
          return arr;
        } catch(e){
          try { window.__rdo_pending_last_error = String(e && e.message ? e.message : e); } catch(_){ }
          return [];
        }
      }

      // Popula o select mobile #rdo-cta-os-select com as OS abertas.
      // Usa window.__rdo_pending_list (preenchido por fetchPending) ou lista vazia.
      function populateOsSelect(){
        try {
          var sel = document.getElementById('rdo-cta-os-select');
          if (!sel) return;
          if (sel.dataset && sel.dataset.populated === '1') return;
          var list = window.__rdo_pending_list || [];
          var knownCount = (window.__rdo_pending_count != null) ? window.__rdo_pending_count : (list.length || 0);
          // limpar opções existentes
          sel.innerHTML = '';
          if (list && list.length) {
            var seen = Object.create(null);
            for (var i=0;i<list.length;i++){ try {
              var item = list[i] || {};
              var key = item.numero_os ? String(item.numero_os) : (item.id ? String(item.id) : null);
              if (!key) continue; if (seen[key]) continue; seen[key]=true;
              var opt = document.createElement('option');
              opt.value = item.id || '';
              opt.dataset.rdoId = item.rdo_id || item.id || '';
              opt.dataset.osNum = item.numero_os || item.os || '';
              opt.dataset.empresa = item.empresa || item.cliente || '';
              opt.dataset.unidade = item.unidade || '';
              opt.dataset.supervisor = item.supervisor || '';
              var txt = [opt.dataset.osNum, opt.dataset.empresa, opt.dataset.unidade].filter(function(x){ return !!x; }).join(' • ');
              opt.textContent = txt || (opt.dataset.osNum || opt.value || '—');
              sel.appendChild(opt);
            } catch(_){}};
          } else if (knownCount > 0) {
            // fallback: extrair da tabela caso existam linhas com data-*
            var rows = document.querySelectorAll('table tbody tr[data-os-id], table tbody tr[data-numero-os], table tbody tr[data-numero]');
            if (rows && rows.length) {
              var seen2 = Object.create(null);
              Array.prototype.forEach.call(rows, function(tr){ try {
                var rdoId = tr.getAttribute('data-rdo-id') || tr.getAttribute('data-rdoid') || tr.dataset && (tr.dataset.rdoId || tr.dataset.rdo_id) || '';
                var numero = tr.getAttribute('data-numero-os') || tr.getAttribute('data-numero') || tr.dataset && (tr.dataset.numeroOs || tr.dataset.numero) || '';
                var empresa = tr.getAttribute('data-empresa') || (tr.dataset && tr.dataset.empresa) || '';
                var unidade = tr.getAttribute('data-unidade') || (tr.dataset && tr.dataset.unidade) || '';
                var key = numero || rdoId; if (!key || seen2[key]) return; seen2[key]=true;
                var opt = document.createElement('option'); opt.value = rdoId || numero || ''; opt.dataset.rdoId = rdoId || ''; opt.dataset.osNum = numero || ''; opt.dataset.empresa = empresa; opt.dataset.unidade = unidade; opt.textContent = [opt.dataset.osNum, opt.dataset.empresa, opt.dataset.unidade].filter(Boolean).join(' • ');
                sel.appendChild(opt);
              } catch(_){ }});
            }
          }
          if (sel.options.length === 0) {
            sel.disabled = true;
            var p = document.createElement('option'); p.value=''; p.textContent = 'Nenhuma OS nova'; sel.appendChild(p);
          } else {
            sel.disabled = false;
          }
          if (sel.dataset) sel.dataset.populated = '1';
          // change handler abre o modal
          if (!sel.__rdoPopBound) {
            sel.addEventListener('change', function(ev){ try {
              var opt = ev.target && ev.target.selectedOptions && ev.target.selectedOptions[0]; if (!opt) return;
              var rdoId = opt.dataset.rdoId || opt.value || '';
              var numeroOs = opt.dataset.osNum || opt.textContent || '';
              var empresa = opt.dataset.empresa || '';
              var unidade = opt.dataset.unidade || '';
              var ctx = { rdo_id: rdoId, os_id: opt.value || '', numero_os: numeroOs, os: numeroOs, empresa: empresa, unidade: unidade, supervisor: opt.dataset.supervisor || '' };
              try { if (typeof window.rdoOpenSupervisorModal === 'function') window.rdoOpenSupervisorModal(ctx); else if (typeof openSupervisorModal === 'function') openSupervisorModal(ctx); } catch(_){ }
              // reset selection to placeholder
              try { ev.target.selectedIndex = -1; } catch(_){}
            } catch(_){ } }, false);
            sel.__rdoPopBound = true;
          }
        } catch(e){ console.warn('populateOsSelect failed', e); }
      }

      function openCTA(){
        if (!cta) return;
        // Novo comportamento: CTA só aparece em mobile; em desktop usamos o popover.
        if (window.innerWidth >= 900) {
          cta.setAttribute('aria-hidden','true');
          return;
        }
        cta.setAttribute('aria-hidden','false');
      }
      function closeCTA(){ if (!cta) return; cta.setAttribute('aria-hidden','true'); }

      async function openNotifications(){
        // Se for desktop, deixamos o novo popover de rdo.core.js cuidar da interface.
        if (window.innerWidth >= 900) return;
        if (!cta || !ctaPopover) { showToast('Interface de notificações indisponível', 'error'); return; }
        ctaPopover.innerHTML = '<div class="loading" style="padding:10px;">Carregando pendências...</div>';
        openCTA();
        console.debug && console.debug('rdo: openNotifications - fetching pending items');
        var items = await fetchPending();
        console.debug && console.debug('rdo: openNotifications - items length after fetch', (items && items.length) || 0);
        // fallback to table extraction if fetch returned empty
        if (!items || !items.length) {
          console.debug && console.debug('rdo: openNotifications - using extractOpenOsFromTable fallback');
          items = extractOpenOsFromTable();
          console.debug && console.debug('rdo: openNotifications - fallback items length', (items && items.length) || 0);
        }
        updateNotificationCount(items.length || 0);
        if (!items.length) {
          ctaPopover.innerHTML = '<div style="padding:10px;color:#555;">Sem pendências de RDO</div>';
          return;
        }
        // Render simples de lista
        var ul = document.createElement('ul');
        ul.style.listStyle = 'none'; ul.style.padding = '8px'; ul.style.margin = '0'; ul.style.maxHeight='220px'; ul.style.overflow='auto';
        items.forEach(function(it){
          try {
            var li = document.createElement('li'); li.style.margin='6px 0';
            var btn = document.createElement('button'); btn.type='button'; btn.className='btn-rdo small';
            try { btn.classList.add('rdo-os-item'); } catch(_){ }
            var os = it.numero_os || it.os || it.os_id || it.id || '-';
            var empresa = it.empresa || it.cliente || '';
            var unidade = it.unidade || '';
            btn.textContent = [os, empresa, unidade].filter(Boolean).join(' • ');
            btn.addEventListener('click', function(){
              try {
                var ctx = {
                  os: String(os), numero_os: String(os), empresa: empresa, unidade: unidade,
                  os_id: String(it.os_id || it.id || ''), supervisor: it.supervisor || '', rdo_id: it.rdo_id || ''
                };
                openSupervisorModal(ctx);
              } catch(_){}
            });
            li.appendChild(btn); ul.appendChild(li);
          } catch(_){}
        });
        ctaPopover.innerHTML = ''; ctaPopover.appendChild(ul);
      }

      if (notifBtn) notifBtn.addEventListener('click', function(ev){ ev.preventDefault(); openNotifications(); });
      if (ctaClose) ctaClose.addEventListener('click', function(){ closeCTA(); });
      if (ctaClear) ctaClear.addEventListener('click', function(){
        try {
          if (window.clearMobileCards && typeof window.clearMobileCards === 'function') window.clearMobileCards({ remove: true });
          else {
            // Fallback: remover cartões summary duplicados, manter só o primeiro por OS
            var lists = document.querySelectorAll('.rdo-mobile-rdo-list .rdo-summary');
            Array.prototype.forEach.call(lists, function(card, idx){ if (idx>0 && card.parentNode) card.parentNode.removeChild(card); });
          }
          showToast('Cartões limpos', 'success');
        } catch(e){}
      });
            // Build a map of finalized (osId, rdoCount) from table rows when available.
            var finalRe = /finaliz|encerrad|fechad|conclu|retorn/i;
            var finalizedMap = Object.create(null);
            try {
              var rows = document.querySelectorAll('table tbody tr[data-os-id][data-rdo-count], table tbody tr[data-numero-os][data-rdo-count]');
              Array.prototype.forEach.call(rows, function(tr){
                try{
                  var st = (tr.getAttribute('data-status-geral') || '').toString();
                  if (st && finalRe.test(st)){
                    var osId = tr.getAttribute('data-os-id') || '';
                    var numOs = tr.getAttribute('data-numero-os') || '';
                    var rdoCount = tr.getAttribute('data-rdo-count') || '';
                    var key = (osId || numOs) + '::' + (rdoCount || '');
                    finalizedMap[key] = true;
                  }
                }catch(_){ }
              });
            } catch(_){ }

            // New behavior: when a OS is finalized, remove ALL cards related to that OS id
            // (or numero_os when id missing). This ensures cards for other OS IDs with the
            // same visible OS number remain shown.
            var finalizedOsKeys = Object.create(null);
            try {
              // Build set of os ids / numero_os that are finalized from table rows
              var rows = document.querySelectorAll('table tbody tr');
              Array.prototype.forEach.call(rows, function(tr){
                try{
                  var st = (tr.getAttribute('data-status-geral') || tr.getAttribute('data-status') || '').toString().toLowerCase();
                  if (!st) return;
                  if (!finalRe.test(st)) return;
                  var osId = (tr.getAttribute('data-os-id') || '').toString();
                  var numOs = (tr.getAttribute('data-numero-os') || '').toString();
                  if (osId) finalizedOsKeys[osId] = true;
                  else if (numOs) finalizedOsKeys[numOs] = true;
                }catch(_){ }
              });
            } catch(_){ }

            // ensure 'cards' is defined in this scope before iterating
            var cards = document.querySelectorAll('.rdo-mobile-card, .rdo-mobile-item');
            Array.prototype.forEach.call(cards, function(card){
              try{
                var cardOsId = (card.getAttribute('data-os-id') || '').toString();
                var cardNumOs = (card.getAttribute('data-os') || card.getAttribute('data-numero-os') || '').toString();

                // Always remove if the card itself reports a finalizada status
                var cardSt = (card.getAttribute('data-status-geral') || '').toString();
                if (cardSt && finalRe.test(cardSt)){
                  if (card.parentNode) card.parentNode.removeChild(card);
                  return;
                }

                // If the OS id/numero_os is in finalized set, remove the card
                if ((cardOsId && finalizedOsKeys[cardOsId]) || (!cardOsId && cardNumOs && finalizedOsKeys[cardNumOs])){
                  if (card.parentNode) card.parentNode.removeChild(card);
                  return;
                }

                // Previous fallback (kept for safety): if no table rows exist and we didn't
                // have a card-level status, nothing more to do here.
              }catch(e){ }
            });
      try { window.updateNotificationCount = updateNotificationCount; } catch(_){}
      // Carregar contador inicial em background (não abre CTA).
      // Executar com pequeno atraso e repetir em eventos (focus/visibilitychange)
      // para contornar casos onde a primeira chamada ocorre cedo demais.
      (function(){
        function doFetchAndUpdate(){
          (async function(){
            try {
              console.debug && console.debug('rdo: delayed pending load - calling fetchPending');
              var items = await fetchPending();
              console.debug && console.debug('rdo: delayed pending load - fetch returned', (items && items.length) || 0);
              if (!items || !items.length) {
                console.debug && console.debug('rdo: delayed pending load - using extractOpenOsFromTable fallback');
                items = extractOpenOsFromTable();
                console.debug && console.debug('rdo: delayed pending load - fallback found', (items && items.length) || 0);
              }
              updateNotificationCount(items.length||0);
            } catch(e) {
              console.warn && console.warn('rdo: delayed pending load - unexpected error', e);
              try { var items2 = extractOpenOsFromTable(); updateNotificationCount(items2.length||0); } catch(_){}
            }
          })();
        }

        // initial delayed attempt (allow other scripts to run)
        try { setTimeout(doFetchAndUpdate, 350); } catch(e){ doFetchAndUpdate(); }

        // also attempt shortly again in case of race (low-cost)
        try { setTimeout(doFetchAndUpdate, 1200); } catch(_){ }

        // when the tab/window gains focus, refresh
        try {
          window.addEventListener('focus', function(){ try { console.debug && console.debug('rdo: window focus - refreshing pending'); doFetchAndUpdate(); } catch(_){} });
        } catch(_){ }

        // when document becomes visible, refresh (useful on mobile when coming from background)
        try {
          document.addEventListener('visibilitychange', function(){ try { if (document.visibilityState === 'visible') { console.debug && console.debug('rdo: visibilitychange visible - refreshing pending'); doFetchAndUpdate(); } } catch(_){} });
        } catch(_){ }
      })();

      // Atualização periódica do contador (ex.: a cada 60s) com mesmo fallback.
      try {
        setInterval(async function(){
          try {
            var items = await fetchPending();
            if (!items || !items.length) items = extractOpenOsFromTable();
            updateNotificationCount(items.length||0);
          } catch(_) {
            try { var fb = extractOpenOsFromTable(); updateNotificationCount(fb.length||0); } catch(_){}
          }
        }, 60000);
      } catch(_){ }
    } catch(e){ console.warn('notifications init failed', e); }
  });

  // Handler Add Tanque (reimplementado do rdo.js): cria RDO parcial para o tanque atual,
  // preserva campos importantes para repetir o fluxo (RDO, Contrato/PO, Turno, Planejamento e Atividades)
  (function(){
    try {
      var btn = document.getElementById('btn-add-tanque');
      if (!btn) return;
      btn.addEventListener('click', async function(ev){
        ev.preventDefault();
        var form = document.getElementById('form-supervisor');
        if (!form) return;

        // validações mínimas
        var rdoVal = (document.getElementById('sup-rdo')||{}).value || '';
        var contratoVal = (document.getElementById('sup-contrato-po')||{}).value || '';
        if (!rdoVal || !contratoVal) {
          if (!rdoVal && document.getElementById('sup-rdo')) document.getElementById('sup-rdo').focus();
          else if (!contratoVal && document.getElementById('sup-contrato-po')) document.getElementById('sup-contrato-po').focus();
          return;
        }

        // prevenir duplo clique
        btn.disabled = true;
        var origText = btn.textContent;
        btn.textContent = 'Salvando...';

        try {
          var payload = buildSupervisorFormData(form);
          // Garantir que o RDO atual seja enviado explicitamente como rdo_contagem
          try {
            var currentRdo = (document.getElementById('sup-rdo')||{}).value || '';
            if (currentRdo) payload.append('rdo_contagem', String(currentRdo));
            // also mirror common aliases for robustness
            if (currentRdo) { payload.append('rdo', String(currentRdo)); payload.append('rdo_override', String(currentRdo)); }
            console.debug && console.debug('rdo.core: sending rdo_contagem', currentRdo);
          } catch(e) { console.warn('failed to append rdo_contagem to payload', e); }
          var url = '/rdo/create_ajax/';
          // usar getCSRF helper para obter token
          var headers = { 'X-Requested-With': 'XMLHttpRequest' };
          var csrf = '';
          try { csrf = getCSRF(form) || ''; } catch(e) { csrf = ''; }
          if (csrf) headers['X-CSRFToken'] = csrf;

          var resp = await fetch(url, { method: 'POST', body: payload, credentials: 'same-origin', headers: headers });
          var data = null;
          if (resp && resp.ok) {
            try { data = await resp.json(); } catch(e) { data = null; }
          }

          // inserir linha visual na tabela (se existir)
          var table = document.querySelector('table');
          var tbody = table ? table.querySelector('tbody') : null;
          if (tbody) {
            var newTr = document.createElement('tr');
            try { newTr.dataset.rdoId = (data && data.id) ? data.id : ''; } catch(e){}
            try { newTr.dataset.numeroOs = (document.getElementById('sup-rdo')||{}).value || ''; } catch(e){}
            try { newTr.dataset.empresa = (document.getElementById('sup-context-empresa')||{}).textContent || ''; } catch(e){}
            try { newTr.dataset.unidade = (document.getElementById('sup-context-unidade')||{}).textContent || ''; } catch(e){}
            try { newTr.dataset.supervisor = (document.getElementById('sup-context-supervisor')||{}).textContent || ''; } catch(e){}

            newTr.innerHTML = `
              <td>-</td>
              <td>${(document.getElementById('sup-rdo')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-contrato-po')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-context-empresa')||{}).textContent || '-'}</td>
              <td>${(document.getElementById('sup-context-unidade')||{}).textContent || '-'}</td>
              <td>${(document.getElementById('sup-context-supervisor')||{}).textContent || '-'}</td>
              <td>-</td>
              <td>${new Date().toLocaleDateString()}</td>
              <td>${(document.getElementById('sup-rdo')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-turno')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-tanque-cod')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-tanque-nome')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-tipo-tanque')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-n-comp')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-gavetas')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-patamar')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-volume')||{}).value || '-'}</td>
              <td>${(document.getElementById('sup-servico') && document.getElementById('sup-servico').options[document.getElementById('sup-servico').selectedIndex]) ? document.getElementById('sup-servico').options[document.getElementById('sup-servico').selectedIndex].text : '-'}</td>
              <td>${(document.getElementById('sup-metodo') && document.getElementById('sup-metodo').options[document.getElementById('sup-metodo').selectedIndex]) ? document.getElementById('sup-metodo').options[document.getElementById('sup-metodo').selectedIndex].text : '-'}</td>
              <td>-</td>
              <td>-</td>
              <td>-</td>
              <td class="action-cell"><button class="action-btn edit" type="button"><span class="material-icons" aria-hidden="true">edit</span></button></td>
              <td class="action-cell"><button class="action-btn view" type="button"><span class="material-icons" aria-hidden="true">visibility</span></button></td>
            `;
            var first = tbody.querySelector('tr');
            tbody.insertBefore(newTr, first || null);
          }

          // decrementar contador local
          try {
            var cnt = parseInt(localStorage.getItem('rdo_pending_count')||'0',10);
            cnt = Math.max(0, cnt-1);
            localStorage.setItem('rdo_pending_count', String(cnt));
            if (window.updateNotificationCount) window.updateNotificationCount();
          } catch(e){}

          // limpar o formulário: preservar RDO, Contrato/PO, Ordem e Turno, Planejamento e Atividades
          try {
            var preserveIds = { 'sup-rdo': true, 'sup-contrato-po': true, 'sup-ordem-id': true, 'sup-turno': true, 'sup-planejamento-pt': true, 'sup-planejamento-en': true };
            function shouldPreserve(el){
              try {
                if (!el) return false;
                if (preserveIds[el.id]) return true;
                var sec = el.closest && el.closest('.rdo-section');
                if (!sec) return false;
                var secId = sec.id || '';
                if (secId === 'sec-atividades' || secId === 'sec-pt') return true;
                return false;
              } catch(e){ return false; }
            }
            Array.from(form.elements).forEach(function(el){
              if (!el.name) return;
              if (el.name === 'csrfmiddlewaretoken') return;
              if (shouldPreserve(el)) return;
              var tag = (el.tagName || '').toLowerCase();
              var type = (el.type || '').toLowerCase();
              if (type === 'file') { try { el.value = ''; } catch(e) {} return; }
              if (type === 'checkbox' || type === 'radio') { el.checked = false; return; }
              if (tag === 'select') { el.selectedIndex = 0; return; }
              // hidden inputs como sup-rdo-id devem ser limpos
              el.value = '';
            });

            // garantir que o hidden `sup-rdo-id` contenha o id do RDO recém-criado
            // (isso permite que o fluxo "Salvar e adicionar outro tanque" use o mesmo RDO)
            try {
              var hid = document.getElementById('sup-rdo-id');
              if (hid) {
                hid.value = (data && data.id) ? String(data.id) : (hid.value || '');
              }
            } catch(e) { console.warn('failed to set sup-rdo-id', e); }

            // Bloquear edição manual do RDO no próximo tanque (readOnly)
            try {
              var rdoInput = document.getElementById('sup-rdo');
              if (rdoInput) {
                rdoInput.readOnly = true;
                rdoInput.setAttribute('aria-readonly','true');
                rdoInput.classList.add('readonly');
                if (!document.getElementById('sup-rdo-lock')) {
                  var lock = document.createElement('span');
                  lock.id = 'sup-rdo-lock';
                  lock.className = 'sup-rdo-lock material-icons';
                  lock.style.marginLeft = '8px';
                  lock.style.fontSize = '18px';
                  lock.title = 'RDO bloqueado para edição neste ciclo';
                  lock.textContent = 'lock';
                  if (rdoInput.parentNode) rdoInput.parentNode.insertBefore(lock, rdoInput.nextSibling);
                }
              }
            } catch(e){}
          } catch(e) { console.warn('clear form partial failed', e); }

        } catch(e){ console.error('add tanque failed', e); }
        finally { btn.disabled = false; btn.textContent = origText; }
      });
    } catch(e){ console.error('rdo.core.js add tanque init error', e); }
  })();

  // Inject CSS for locked RDO visual state (padlock and dimming)
  try {
    var lockStyleId = 'rdo-locked-style';
    if (!document.getElementById(lockStyleId)) {
  var css = '\n.rdo-locked { opacity: 0.6; position: relative; }\n.rdo-locked .rdo-lock-icon { position: absolute; right: 8px; top: 8px; font-family: "Material Icons"; font-size: 18px; color: #444; }\n.rdo-locked .open-supervisor, .rdo-locked .action-btn.edit { opacity: 0.5; }\n/* allow explicit edits when element has allow-edit class inside locked rows */\n.rdo-locked .allow-edit, .rdo-locked .allow-edit * { pointer-events: auto !important; opacity: 1 !important; }\n';
      var s = document.createElement('style'); s.id = lockStyleId; s.type = 'text/css'; s.appendChild(document.createTextNode(css)); document.head.appendChild(s);
    }
  } catch(_){ }

  // When an RDO is saved, lock all previous RDOs for the same OS if a later RDO was created
  try {
    document.addEventListener('rdo:saved', function(ev){
      try {
        var detail = (ev && ev.detail) || {};
        var mode = detail.mode || '';
        var resp = detail.response || {};
        // Only act on creation (not update)
        if (mode !== 'create') return;
        // Response should include created rdo payload: expect os_id and rdo (count)
        var payload = resp.rdo || resp || {};
        var osId = payload.ordem_servico_id || payload.os_id || payload.ordem_servico || '';
        var rdoCount = payload.rdo || payload.rdo_contagem || payload.rdo_count || '';
        var n = parseInt(String(rdoCount).replace(/[^0-9]/g,''), 10);
        if (!isFinite(n) || n <= 1) return;

        // Build selectors to find any element (rows/cards) for the same OS
        var trSelectorBase = '';
        if (osId) trSelectorBase = '[data-os-id="' + String(osId) + '"]';
        var numOs = payload.numero_os || payload.numero || payload.num_os || '';

        // Helper to lock an element (add class only — não inserir ícone visual na linha/tabela)
        function lockEl(el){ try { if (!el) return; if (el.classList && el.classList.contains('rdo-locked')) return; el.classList.add('rdo-locked'); } catch(_){ } }

        // Lock table rows with same OS where rdo_count < n
        try {
          var rowSel = 'tr[data-rdo-count]';
          if (trSelectorBase) rowSel = 'tr' + trSelectorBase + '[data-rdo-count]';
          var rows = document.querySelectorAll(rowSel);
          Array.prototype.forEach.call(rows, function(r){ try {
            var rc = parseInt(String(r.getAttribute('data-rdo-count') || (r.dataset && r.dataset.rdoCount) || '').replace(/[^0-9]/g,''),10) || 0;
            if (rc && rc < n) lockEl(r);
          } catch(_){} });
        } catch(_){ }

        // Lock mobile cards similarly
        try {
          var cardSel = '.rdo-mobile-card[data-rdo-count], .rdo-mobile-item[data-rdo-count]';
          if (trSelectorBase) cardSel = '.rdo-mobile-card' + trSelectorBase + '[data-rdo-count], .rdo-mobile-item' + trSelectorBase + '[data-rdo-count]';
          var cards = document.querySelectorAll(cardSel);
          Array.prototype.forEach.call(cards, function(c){ try {
            var rc = parseInt(String(c.getAttribute('data-rdo-count') || (c.dataset && c.dataset.rdoCount) || '').replace(/[^0-9]/g,''),10) || 0;
            if (rc && rc < n) lockEl(c);
          } catch(_){} });
          // If we didn't find by data-os-id but have numero_os, also attempt by numero
          if ((!cards || !cards.length) && numOs) {
            var cardSel2 = '.rdo-mobile-card[data-os="' + String(numOs) + '"][data-rdo-count], .rdo-mobile-item[data-os="' + String(numOs) + '"][data-rdo-count]';
            var cards2 = document.querySelectorAll(cardSel2);
            Array.prototype.forEach.call(cards2, function(c){ try { var rc = parseInt(String(c.getAttribute('data-rdo-count') || (c.dataset && c.dataset.rdoCount) || '').replace(/[^0-9]/g,''),10) || 0; if (rc && rc < n) lockEl(c); } catch(_){} });
          }
        } catch(_){ }
      } catch(_){ }
    }, false);
  } catch(_){ }
  // Delegated handler: Botão alternativo "Adicionar Tanque" no modal Supervisor
  // IMPORTANTE: o fluxo principal de "Salvar e adicionar outro tanque" (#btn-rdo-add-another)
  // já é tratado mais acima neste arquivo (handler que também cria o RDO se necessário).
  // Para evitar eventos duplicados e tanques em dobro, este handler AQUI passa a escutar
  // SOMENTE um botão alternativo opcional com id="#btn-add-tanque" (quando existir em algum template).
  // Ele coleta apenas os campos relacionados ao tanque do `#form-supervisor` e faz POST para
  // /api/rdo/<pk>/add_tank/.
  // Em caso de sucesso emite evento 'rdo:tank:added' com payload do tank e limpa os campos de tanque.
  document.addEventListener('click', async function(ev){
    try{
      var target = ev.target || ev.srcElement;
      if (!target) return;
      // Escuta apenas o botão alternativo explicitamente identificado por #btn-add-tanque
      // (não inclui #btn-rdo-add-another para evitar duplicar o envio do tanque).
      var btn = (target.closest && target.closest('#btn-add-tanque')) || null;
      if (!btn) return;
      ev.preventDefault();

      var form = document.getElementById('form-supervisor');
      if (!form) {
        console.warn('add-tank: form-supervisor não encontrado');
        return;
      }

      // obter rdo internal id (inserido no hidden sup-rdo-id pelo fluxo de criação)
      var hid = document.getElementById('sup-rdo-id') || document.getElementById('edit-rdo-id');
      var rdoId = hid && hid.value ? String(hid.value).trim() : null;
      if (!rdoId) {
        showToast('RDO ainda não criado. Use "Salvar" primeiro.', 'error');
        return;
      }

      // nomes de campo de tanque suportados (coletar se existirem no form)
  var tankNames = ['tanque_codigo','tanque_nome','tipo_tanque','numero_compartimento','gavetas','patamar','volume_tanque_exec','servico_exec','metodo_exec','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','tempo_bomba','ensacamento_dia','ensacamento_cumulativo','icamento_dia','icamento_cumulativo','cambagem_dia','cambagem_cumulativo','tambores_dia','residuos_solidos','residuos_totais','avanco_limpeza','avanco_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo','percentual_avanco','percentual_avanco_cumulativo'];
      var fd = new FormData();
      tankNames.forEach(function(n){
        try{
          var el = form.querySelector('[name="'+n+'"]');
          if (el && typeof el.value !== 'undefined') fd.append(n, el.value);
        }catch(e){}
      });

      // anexar CSRF token como campo hidden/ cabeçalho
      var csrf = getCSRF(form) || '';

      var url = '/api/rdo/' + encodeURIComponent(rdoId) + '/add_tank/';
      try{
        var headers = { 'X-Requested-With': 'XMLHttpRequest' };
        if (csrf) headers['X-CSRFToken'] = csrf;
        var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin', headers: headers });
        var data = null;
        try{ data = await resp.json(); }catch(e){ data = null; }
        if (!resp.ok) {
          console.error('add_tank failed', resp.status, data);
          showToast((data && data.error) ? data.error : 'Falha ao adicionar tanque', 'error');
          return;
        }
        if (data && data.success) {
          var tank = data.tank || data.tanque || null;
          // emitir evento custom para permitir pontos de extensão do app
          try{ document.dispatchEvent(new CustomEvent('rdo:tank:added', { detail: { tank: tank, raw: data } })); } catch(e){}

          // Se existir helper interno para atualizar a lista de tanques, chamar
          try{ if (typeof _appendSavedTankSummary === 'function' && tank) _appendSavedTankSummary(tank); }catch(e){}

          showToast((data && data.message) ? data.message : 'Tanque adicionado', 'success');

          // marcar no formulário que já existem tanques adicionados (para o submit final não regravar campos de tanque no RDO)
          try {
            var flag = form.querySelector('input[name="rdo_has_tanks"]');
            if (!flag) { flag = document.createElement('input'); flag.type = 'hidden'; flag.name = 'rdo_has_tanks'; form.appendChild(flag); }
            flag.value = '1';
            try { if (form && form.classList) form.classList.add('has-tank-additions'); } catch(_){}
          } catch(_){ }

          // limpar campos de tanque no form (apenas os conhecidos)
          tankNames.forEach(function(n){
            try{ var el = form.querySelector('[name="'+n+'"]'); if (el) el.value = ''; }catch(e){}
          });
        } else {
          console.warn('add_tank no-success payload', data);
          showToast((data && data.error) ? data.error : 'Falha ao adicionar tanque', 'error');
        }
      }catch(err){
        console.error('add_tank network/error', err);
        showToast('Erro conectando ao servidor (add_tank)', 'error');
      }
    }catch(e){ console.warn('btn-add-tanque handler failed', e); }
  }, false);

})();
