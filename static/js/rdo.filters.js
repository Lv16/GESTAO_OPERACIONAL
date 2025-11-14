(function(){
  'use strict';

  // LocalStorage key for persisted filters
  var STORAGE_KEY = 'rdo.filters.v1';

  // Map of inputs by logical name
  var inputs = {
    contrato: function(){ return document.getElementById('f-contrato'); },
    os: function(){ return document.getElementById('f-os'); },
    empresa: function(){ return document.getElementById('f-empresa'); },
    unidade: function(){ return document.getElementById('f-unidade'); },
    turno: function(){ return document.getElementById('f-turno'); },
    servico: function(){ return document.getElementById('f-servico'); },
    metodo: function(){ return document.getElementById('f-metodo'); },
    date_start: function(){ return document.getElementById('f-date-start'); },
    tanque: function(){ return document.getElementById('f-tanque'); },
    supervisor: function(){ return document.getElementById('f-supervisor'); },
    status_geral: function(){ return document.getElementById('f-status_geral'); }
  };

  function qs(sel, ctx){ return (ctx || document).querySelector(sel); }
  function qsa(sel, ctx){ return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  function norm(v){ return (v===null||v===undefined)?'':String(v).toLowerCase().trim(); }

  function saveFilters(obj){
    try{ localStorage.setItem(STORAGE_KEY, JSON.stringify(obj || {})); }catch(e){}
  }
  function loadFilters(){
    try{ var v = localStorage.getItem(STORAGE_KEY); if (!v) return {}; return JSON.parse(v||'{}'); }catch(e){ return {}; }
  }
  function clearStored(){ try{ localStorage.removeItem(STORAGE_KEY); }catch(e){} }

  function gatherValuesFromInputs(){
    var out = {};
    Object.keys(inputs).forEach(function(k){
      var el = inputs[k](); out[k] = el ? norm(el.value) : '';
    });
    return out;
  }

  function setInputsFromValues(vals){
    Object.keys(inputs).forEach(function(k){ var el = inputs[k](); if (!el) return; el.value = (vals && vals[k])? vals[k] : ''; });
  }

  function countActive(vals){
    var c = 0; Object.keys(vals||{}).forEach(function(k){ if (vals[k]) c++; }); return c;
  }

  function updateBadge(){
    var badge = qs('.filter-badge'); if (!badge) return;
    // Prefer server-provided active filters count when available
    try{
      if (typeof window !== 'undefined' && typeof window.RDO_ACTIVE_FILTERS !== 'undefined'){
        var serverCount = parseInt(window.RDO_ACTIVE_FILTERS, 10) || 0;
        badge.textContent = serverCount ? String(serverCount) : '';
        return;
      }
    }catch(e){}
    var vals = loadFilters(); var n = countActive(vals); badge.textContent = n? String(n): '';
  }

  function parseDateIso(s){
    if (!s) return null; try{ var d = new Date(s); if (isNaN(d.getTime())) return null; d.setHours(0,0,0,0); return d; }catch(e){ return null; }
  }

  function applyFiltersToDOM(vals){
    // Table rows
    var rows = qsa('table tbody tr');
    rows.forEach(function(tr){
      var ds = tr.dataset || {};
      var visible = true;

      // helper to match dataset keys (some keys in template use dashed names)
      function dget(name){ return norm(ds[name]) || norm(ds[name.replace(/_/g,'-')]) || norm(ds[name.replace(/-/g,'_')]) || '' }

      // Text fields: check contains
      if (vals.contrato && dget('po').indexOf(vals.contrato) === -1) visible = false;
      if (vals.os){
        var v = dget('numero-os') || dget('numero_os') || dget('os') || (tr.cells[1] && norm(tr.cells[1].textContent));
        if ((v||'').indexOf(vals.os) === -1) visible = false;
      }
      if (vals.empresa && dget('empresa').indexOf(vals.empresa) === -1) visible = false;
      if (vals.unidade && dget('unidade').indexOf(vals.unidade) === -1) visible = false;
      if (vals.turno && dget('turno').indexOf(vals.turno) === -1) visible = false;
      if (vals.servico && dget('servico').indexOf(vals.servico) === -1) visible = false;
      if (vals.metodo && dget('metodo').indexOf(vals.metodo) === -1) visible = false;
      if (vals.tanque && (dget('tanque')+dget('tanque-nome')+dget('tanque-nome')).indexOf(vals.tanque) === -1) visible = false;
      if (vals.supervisor && (dget('supervisor')+dget('supervisor-fullname')+dget('supervisorFullname')).indexOf(vals.supervisor) === -1) visible = false;
      if (vals.status_geral && (dget('status-geral')+dget('status_geral')+dget('statusGeral')).indexOf(vals.status_geral) === -1) visible = false;

      // Data filter (date >= date_start)
      if (vals.date_start){
        var rowDate = (dget('data') || '');
        if (!rowDate){
          var cell = tr.cells && tr.cells[7] ? tr.cells[7].textContent.trim() : '';
          if (cell && cell.indexOf('/')!==-1){ var p = cell.split('/'); if (p.length===3) rowDate = p[2]+'-'+p[1].padStart(2,'0')+'-'+p[0].padStart(2,'0'); }
        }
        var dRow = parseDateIso(rowDate);
        var dFilter = parseDateIso(vals.date_start);
        if (!dRow || !dFilter || dRow < dFilter) visible = false;
      }

      tr.style.display = visible ? '' : 'none';
    });

    // Cards (desktop + mobile)
    var cards = qsa('#rdo-desktop-cards .rdo-mobile-card, #rdo-mobile-list .rdo-mobile-card');
    cards.forEach(function(card){
      var ds = card.dataset || {};
      var visible = true;
      function dgetc(name){ return norm(ds[name]) || norm(ds[name.replace(/_/g,'-')]) || ''; }
      if (vals.contrato && (dgetc('po')||dgetc('os')||dgetc('numero-os')).indexOf(vals.contrato) === -1) visible = false;
      if (vals.os && (dgetc('os')||dgetc('numero-os')||dgetc('numero_os')).indexOf(vals.os) === -1) visible = false;
      if (vals.empresa && dgetc('empresa').indexOf(vals.empresa) === -1) visible = false;
      if (vals.unidade && dgetc('unidade').indexOf(vals.unidade) === -1) visible = false;
      if (vals.turno && dgetc('turno').indexOf(vals.turno) === -1) visible = false;
      if (vals.servico && dgetc('servico').indexOf(vals.servico) === -1) visible = false;
      if (vals.metodo && dgetc('metodo').indexOf(vals.metodo) === -1) visible = false;
      if (vals.tanque && (dgetc('tanque')||dgetc('tanque-nome')||dgetc('tanque-codigo')).indexOf(vals.tanque) === -1) visible = false;
      if (vals.supervisor && (dgetc('supervisor')||dgetc('supervisor-fullname')||dgetc('supervisorFullname')).indexOf(vals.supervisor) === -1) visible = false;
      if (vals.status_geral && (dgetc('status-geral')||dgetc('status_geral')||dgetc('statusGeral')).indexOf(vals.status_geral) === -1) visible = false;

      if (vals.date_start && visible){
        var rowDate = dgetc('data');
        var dRow = parseDateIso(rowDate);
        var dFilter = parseDateIso(vals.date_start);
        if (!dRow || !dFilter || dRow < dFilter) visible = false;
      }

      card.style.display = visible ? '' : 'none';
    });

    updateBadge();
    // after applying filters to DOM, check if anything is visible and notify
    try{ checkNoResultsAndNotify(); }catch(e){}
  }

  // Helper: determine if there are any visible rows or cards and show a toast if none
  function isElementVisible(el){
    if (!el) return false;
    // consider element visible if it occupies layout space and is not display:none
    var s = window.getComputedStyle(el);
    if (!s) return false;
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    // offsetParent is null for display:none and some positionings
    if (el.offsetParent === null && s.position !== 'fixed') return false;
    return true;
  }

  function checkNoResultsAndNotify(){
    // check table rows
    var rows = qsa('table tbody tr');
    var anyVisible = rows.some(function(r){ return isElementVisible(r); });
    // if no visible rows, check cards
    if (!anyVisible){
      var cards = qsa('#rdo-desktop-cards .rdo-mobile-card, #rdo-mobile-list .rdo-mobile-card, .rdo-mobile-list .rdo-mobile-card');
      anyVisible = cards.some(function(c){ return isElementVisible(c); });
    }
    if (!anyVisible){
      showToast('Nenhum resultado encontrado para os filtros aplicados.');
    }
    return !anyVisible;
  }

  function showToast(message, timeout){
    timeout = typeof timeout === 'number' ? timeout : 4000;
    try{
      var containerId = 'rdo-toast-container';
      var container = document.getElementById(containerId);
      if (!container){
        container = document.createElement('div');
        container.id = containerId;
        container.style.zIndex = 120000;
        // default placement (fixed bottom-right)
        container.style.position = 'fixed';
        container.style.right = '16px';
        container.style.bottom = '16px';
        document.body.appendChild(container);
      }

      // attempt to position the container near the Filters button when available
      var anchor = document.getElementById('btn_rdo_filtros');
      if (anchor){
        try{
          var rect = anchor.getBoundingClientRect();
          var left = rect.left + window.pageXOffset;
          var top = rect.bottom + window.pageYOffset + 8;
          container.style.position = 'absolute';
          container.style.left = Math.max(8, left) + 'px';
          container.style.top = top + 'px';
          container.style.right = 'auto';
          container.style.bottom = 'auto';
        }catch(e){}
      }

      var el = document.createElement('div');
      el.className = 'rdo-toast';
      el.textContent = message;
      // clicking removes immediately
      el.addEventListener('click', function(){ if (el && el.parentNode) el.parentNode.removeChild(el); });
      container.appendChild(el);
      // auto-remove after timeout
      setTimeout(function(){ try{ if (el && el.parentNode) el.parentNode.removeChild(el); }catch(e){} }, timeout);
    }catch(e){ console.warn('toast failed', e); }
  }

  function applyFromInputsAndPersist(){
    var vals = gatherValuesFromInputs();
    // persist locally so filters survive reloads until user clears explicitly
    saveFilters(vals);

    // Build querystring from non-empty values and navigate so server can filter
    var params = [];
    Object.keys(vals).forEach(function(k){
      if (vals[k]){
        params.push(encodeURIComponent(k) + '=' + encodeURIComponent(vals[k]));
      }
    });
    // reset to first page when applying filters
    // remove existing page param to let server default to page 1
    var qs = params.join('&');
    var base = window.location.pathname || '/';
    var url = qs ? (base + '?' + qs) : base;
    // navigate
    window.location.href = url;
  }

  function clearFilters(){
    clearStored();
    setInputsFromValues({});
    updateBadge();
    // navigate to base path (clears any server-side filters in querystring)
    var base = window.location.pathname || '/';
    window.location.href = base;
  }

  function bind(){
    var btnApply = document.getElementById('btn_apply_filters');
    var btnClear = document.getElementById('btn_clear_filters');
    if (btnApply) btnApply.addEventListener('click', function(ev){ ev.preventDefault(); applyFromInputsAndPersist(); });
    if (btnClear) btnClear.addEventListener('click', function(ev){ ev.preventDefault(); clearFilters(); });

    // Enter key applies
    Object.keys(inputs).forEach(function(k){ var el = inputs[k](); if (!el) return; el.addEventListener('keydown', function(ev){ if (ev.key === 'Enter'){ ev.preventDefault(); applyFromInputsAndPersist(); } }); });

    // When pagination links are clicked, we don't need special handling because filters are persisted in localStorage.
    // However, ensure when page loads we reapply persisted filters.

    // Also expose a global helper to clear filters from console if needed
    window.RDO_filters = {
      apply: applyFromInputsAndPersist,
      clear: clearFilters,
      get: function(){ return loadFilters(); }
    };

    // Handle clicks on removable filter chips
    try{
      var afl = document.getElementById('active-filters-list');
      if (afl){
        afl.addEventListener('click', function(ev){
          var target = ev.target || ev.srcElement;
          // if user clicked the remove '×' element, find parent .filter-chip
          if (target.classList && target.classList.contains('chip-remove')){
            var chip = target.closest('.filter-chip');
            if (chip) removeFilterByName(chip.getAttribute('data-name'));
          } else {
            // if user clicked the chip itself (not the ×), also allow removal
            var chip2 = target.closest && target.closest('.filter-chip');
            if (chip2 && target.classList && target.classList.contains('filter-chip')){
              removeFilterByName(chip2.getAttribute('data-name'));
            }
          }
        });
      }
    }catch(e){/* non-fatal */}
  }

  function removeFilterByName(name){
    if (!name) return;
    try{
      // Update stored filters (localStorage)
      var stored = loadFilters() || {};
      if (stored.hasOwnProperty(name)){
        delete stored[name];
        saveFilters(stored);
      }
    }catch(e){}
    // Build new URL without this param
    try{
      var params = new URLSearchParams(window.location.search || '');
      if (params.has(name)) params.delete(name);
      // remove page param to reset pagination
      if (params.has('page')) params.delete('page');
      var qs = params.toString();
      var base = window.location.pathname || '/';
      var url = qs ? (base + '?' + qs) : base;
      window.location.href = url;
    }catch(e){
      // fallback: just reload base page
      window.location.href = window.location.pathname || '/';
    }
  }

  // On load: apply persisted filters (if any) and fill inputs
  document.addEventListener('DOMContentLoaded', function(){
    try{
      var stored = loadFilters();
      var urlParams = new URLSearchParams(window.location.search || '');

      // If URL contains any filter params, prefer them (server-side render will have applied list)
      var hasUrlFilter = false;
      Object.keys(inputs).forEach(function(k){ if (urlParams.has(k)) hasUrlFilter = true; });

      if (hasUrlFilter){
        // ensure inputs reflect URL (template may already set values, but this is defensive)
        var vals = {};
        Object.keys(inputs).forEach(function(k){ vals[k] = urlParams.get(k) || ''; });
        setInputsFromValues(vals);
        applyFiltersToDOM(vals);
      } else if (stored && Object.keys(stored).length){
        // Prefill inputs from stored filters for user convenience (no automatic navigation)
        setInputsFromValues(stored);
        applyFiltersToDOM(stored);
      } else {
        updateBadge();
      }
      bind();
    }catch(e){ console.warn('rdo.filters init failed', e); }
  });

})();
