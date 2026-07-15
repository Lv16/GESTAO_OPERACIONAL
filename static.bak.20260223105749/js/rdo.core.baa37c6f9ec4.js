// NÃO MEXER EM "VAR TANK NAMES" PELO AMOR DE DEUS!!! SUJEITO A QUEBRAR TODO O CÓDIGO

;(function(){
  'use strict';
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

  function estimateFormDataBytes(fd){
    var total = 0;
    try {
      if (!fd || typeof fd.entries !== 'function') return 0;
      var it = fd.entries();
      var next = it.next();
      while (!next.done) {
        var val = next.value && next.value[1];
        if (val && typeof val === 'object' && typeof val.size === 'number') total += (val.size || 0);
        next = it.next();
      }
    } catch(_){}
    return total;
  }

  function getRequestTimeoutMs(payload){
    // Ajuste de timeout para uploads com fotos maiores em rede móvel.
    var baseMs = 60000;
    var maxMs = 240000;
    try {
      var bytes = estimateFormDataBytes(payload);
      if (!bytes || !isFinite(bytes) || bytes <= 0) return baseMs;
      var mb = bytes / (1024 * 1024);
      var extraSteps = Math.ceil(mb / 5); // +15s a cada ~5MB
      var timeout = baseMs + (extraSteps * 15000);
      if (!isFinite(timeout) || timeout < baseMs) timeout = baseMs;
      if (timeout > maxMs) timeout = maxMs;
      return timeout;
    } catch(_){
      return baseMs;
    }
  }

  function countFormDataFiles(fd){
    var total = 0;
    try {
      if (!fd || typeof fd.entries !== 'function') return 0;
      var it = fd.entries();
      var next = it.next();
      while (!next.done) {
        var val = next.value && next.value[1];
        if (val && typeof val === 'object' && typeof val.size === 'number') total += 1;
        next = it.next();
      }
    } catch(_){}
    return total;
  }

  function formatBytes(bytes){
    try {
      var b = Number(bytes || 0);
      if (!isFinite(b) || b <= 0) return '0 B';
      if (b < 1024) return Math.round(b) + ' B';
      var kb = b / 1024;
      if (kb < 1024) return kb.toFixed(0) + ' KB';
      var mb = kb / 1024;
      if (mb < 1024) return mb.toFixed(1) + ' MB';
      var gb = mb / 1024;
      return gb.toFixed(2) + ' GB';
    } catch(_){
      return '0 B';
    }
  }

  function showUploadProgress(label, percent){
    try {
      var id = 'rdo-upload-progress';
      var box = document.getElementById(id);
      if (!box) {
        box = document.createElement('div');
        box.id = id;
        box.setAttribute('role', 'status');
        box.setAttribute('aria-live', 'polite');
        box.innerHTML = '<div class="rdo-upload-progress__label"></div><div class="rdo-upload-progress__track"><div class="rdo-upload-progress__bar"></div></div>';
        Object.assign(box.style, {
          position: 'fixed',
          right: '16px',
          bottom: '16px',
          width: 'min(320px, calc(100vw - 32px))',
          background: '#0b3d2e',
          color: '#fff',
          borderRadius: '10px',
          padding: '10px 12px',
          zIndex: 100000,
          boxShadow: '0 8px 24px rgba(0,0,0,0.25)'
        });
        document.body.appendChild(box);
      }
      var lbl = box.querySelector('.rdo-upload-progress__label');
      var track = box.querySelector('.rdo-upload-progress__track');
      var bar = box.querySelector('.rdo-upload-progress__bar');
      if (lbl) lbl.textContent = label || 'Enviando...';
      if (track) {
        Object.assign(track.style, {
          marginTop: '8px',
          width: '100%',
          height: '8px',
          background: 'rgba(255,255,255,0.25)',
          borderRadius: '999px',
          overflow: 'hidden'
        });
      }
      if (bar) {
        var p = (typeof percent === 'number' && isFinite(percent)) ? Math.max(0, Math.min(100, Math.round(percent))) : 10;
        Object.assign(bar.style, {
          height: '100%',
          width: p + '%',
          background: '#73e29a',
          transition: 'width .18s ease'
        });
      }
      box.style.display = 'block';
    } catch(_){}
  }

  function hideUploadProgress(delayMs){
    try {
      var run = function(){
        try {
          var box = document.getElementById('rdo-upload-progress');
          if (box && box.parentNode) box.parentNode.removeChild(box);
        } catch(_){}
      };
      if (delayMs && delayMs > 0) setTimeout(run, delayMs);
      else run();
    } catch(_){}
  }

  function requestJsonWithProgress(opts){
    return new Promise(function(resolve, reject){
      var xhr = null;
      var finished = false;
      var signal = opts && opts.signal ? opts.signal : null;
      var onAbort = null;
      function cleanup(){
        try {
          if (signal && onAbort) signal.removeEventListener('abort', onAbort);
        } catch(_){}
      }
      function doneResolve(payload){
        if (finished) return;
        finished = true;
        cleanup();
        resolve(payload);
      }
      function doneReject(err){
        if (finished) return;
        finished = true;
        cleanup();
        reject(err);
      }
      try {
        xhr = new XMLHttpRequest();
        xhr.open((opts && opts.method) || 'POST', (opts && opts.url) || '', true);
        if (opts && opts.credentials && opts.credentials !== 'omit') {
          try { xhr.withCredentials = true; } catch(_){}
        }
        var headers = (opts && opts.headers) || {};
        Object.keys(headers).forEach(function(k){
          try { xhr.setRequestHeader(k, headers[k]); } catch(_){}
        });

        if (signal) {
          if (signal.aborted) {
            var e0 = new Error('Aborted');
            e0.name = 'AbortError';
            doneReject(e0);
            return;
          }
          onAbort = function(){
            try { xhr.abort(); } catch(_){}
          };
          signal.addEventListener('abort', onAbort);
        }

        if (xhr.upload && opts && typeof opts.onUploadProgress === 'function') {
          xhr.upload.onprogress = function(ev){
            try { opts.onUploadProgress(ev); } catch(_){}
          };
        }
        xhr.onerror = function(){
          var e = new Error('Network error');
          e.name = 'NetworkError';
          doneReject(e);
        };
        xhr.onabort = function(){
          var e = new Error('Aborted');
          e.name = 'AbortError';
          doneReject(e);
        };
        xhr.onload = function(){
          var text = '';
          try { text = xhr.responseText || ''; } catch(_){ text = ''; }
          var data = null;
          if (text) {
            try { data = JSON.parse(text); } catch(_){ data = null; }
          }
          doneResolve({
            ok: xhr.status >= 200 && xhr.status < 300,
            status: xhr.status,
            data: data,
            text: text
          });
        };
        xhr.send((opts && opts.body) || null);
      } catch(err){
        doneReject(err);
      }
    });
  }

  function canCompressPhoto(file){
    try {
      if (!file || !file.type || String(file.type).indexOf('image/') !== 0) return false;
      var t = String(file.type).toLowerCase();
      return (
        t.indexOf('jpeg') !== -1 ||
        t.indexOf('jpg') !== -1 ||
        t.indexOf('png') !== -1 ||
        t.indexOf('webp') !== -1
      );
    } catch(_){
      return false;
    }
  }

  function compressPhotoFile(file){
    return new Promise(function(resolve){
      try {
        if (!canCompressPhoto(file)) { resolve(file); return; }
        var minCompressBytes = 380 * 1024;
        if (!file.size || file.size < minCompressBytes) { resolve(file); return; }

        var reader = new FileReader();
        reader.onerror = function(){ resolve(file); };
        reader.onload = function(ev){
          try {
            var img = new Image();
            img.onerror = function(){ resolve(file); };
            img.onload = function(){
              try {
                var maxW = 1920;
                var maxH = 1920;
                var w = img.width || 0;
                var h = img.height || 0;
                if (!w || !h) { resolve(file); return; }
                var ratio = Math.min(1, maxW / w, maxH / h);
                var nw = Math.max(1, Math.round(w * ratio));
                var nh = Math.max(1, Math.round(h * ratio));
                var canvas = document.createElement('canvas');
                canvas.width = nw;
                canvas.height = nh;
                var ctx = canvas.getContext('2d');
                if (!ctx) { resolve(file); return; }
                ctx.drawImage(img, 0, 0, nw, nh);
                canvas.toBlob(function(blob){
                  try {
                    if (!blob || !blob.size || blob.size >= file.size) { resolve(file); return; }
                    var out = new File([blob], file.name, { type: 'image/jpeg', lastModified: Date.now() });
                    resolve(out);
                  } catch(_){
                    resolve(file);
                  }
                }, 'image/jpeg', 0.8);
              } catch(_){
                resolve(file);
              }
            };
            img.src = ev && ev.target ? ev.target.result : '';
          } catch(_){
            resolve(file);
          }
        };
        reader.readAsDataURL(file);
      } catch(_){
        resolve(file);
      }
    });
  }

  function optimizePhotoList(files, onProgress){
    return new Promise(function(resolve){
      try {
        var list = Array.isArray(files) ? files.slice() : [];
        if (!list.length) { resolve([]); return; }
        var out = [];
        var idx = 0;
        function step(){
          if (idx >= list.length) { resolve(out); return; }
          var f = list[idx];
          compressPhotoFile(f).then(function(cf){
            out.push(cf || f);
            idx += 1;
            try { if (typeof onProgress === 'function') onProgress(idx, list.length); } catch(_){}
            step();
          }).catch(function(){
            out.push(f);
            idx += 1;
            try { if (typeof onProgress === 'function') onProgress(idx, list.length); } catch(_){}
            step();
          });
        }
        step();
      } catch(_){
        resolve(Array.isArray(files) ? files : []);
      }
    });
  }

  function _isDesktop(){
    return window.innerWidth >= 900;
  }

  function _buildOsLabel(os){
    var parts = [];
    try {
      var osNum = os && (os.numero_os || os.os || os.os_id || os.id) ? String(os.numero_os || os.os || os.os_id || os.id) : '';
      var osId = os && (os.os_id || os.id) ? String(os.os_id || os.id) : '';
      if (osNum) {
        if (osId && osId !== osNum) parts.push(osNum + ' (ID ' + osId + ')');
        else parts.push(osNum);
      }
    } catch(_){}
    if (os && os.empresa) parts.push(os.empresa);
    if (os && os.unidade) parts.push(os.unidade);
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
    try {
      if (typeof fetchPending === 'function') {
        try {
          var items = await fetchPending();
          if (items && items.length) return items;
        } catch(_){ }
      }
      if (window.__rdo_pending_list && Array.isArray(window.__rdo_pending_list) && window.__rdo_pending_list.length) {
        return window.__rdo_pending_list;
      }
      try {
        var raw = localStorage.getItem('rdo_pending_list');
        if (raw) {
          var parsed = JSON.parse(raw);
          if (Array.isArray(parsed) && parsed.length) return parsed;
        }
      } catch(_){ }
    } catch(_){ }
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
    function _pendingSortKey(it){
      try {
        if (!it) return 0;
        var raw = (it.id != null ? it.id : (it.os_id != null ? it.os_id : (it.numero_os != null ? it.numero_os : (it.os != null ? it.os : 0))));
        var num = parseInt(String(raw).replace(/[^0-9]/g,''), 10);
        return Number.isFinite(num) ? num : 0;
      } catch(_){ return 0; }
    }
    try { items = items.slice().sort(function(a,b){ return _pendingSortKey(b) - _pendingSortKey(a); }); } catch(_){ }
    try { if (!pop.__allItemsOriginal || !Array.isArray(pop.__allItemsOriginal) || pop.__allItemsOriginal.length === 0) pop.__allItemsOriginal = items.slice(); } catch(_){ }
    var allItems = (pop.__allItemsOriginal && Array.isArray(pop.__allItemsOriginal)) ? pop.__allItemsOriginal : items.slice();
    var total = items.length;
    if (countEl) countEl.textContent = total + ' OS';

    if (!total){
      var empty = document.createElement('div');
      empty.className = 'rdo-empty-state';
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
    var ul = document.createElement('ul');
    ul.style.listStyle = 'none'; ul.style.padding = '8px'; ul.style.margin = '0'; ul.style.maxHeight='320px'; ul.style.overflow='auto';

    var visualLimit = 5; // show top 5
    var visible = items.slice(0, visualLimit);
    var remaining = items.slice(visualLimit);

    visible.forEach(function(it){
      try {
        var li = document.createElement('li'); li.style.margin='6px 0';
        var btn = document.createElement('button'); btn.type='button'; btn.className='btn-rdo small';
        var osNum = it.numero_os || it.os || '';
        var osId = it.os_id || it.id || '';
        var empresa = it.empresa || it.cliente || '';
        var unidade = it.unidade || '';
        var label = '';
        if (osNum) {
          label = osNum;
          if (osId && String(osId) !== String(osNum)) label += ' (ID ' + osId + ')';
        } else if (osId) {
          label = 'ID ' + osId;
        } else {
          label = '-';
        }
        btn.textContent = [label, empresa, unidade].filter(Boolean).join(' • ');
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
    try {
      var verBtn = pop.querySelector('#rdo-popover-ver-todas');
      if (verBtn) {
        var remainingCount = (allItems && allItems.length) ? Math.max(0, allItems.length - visualLimit) : 0;
        if (remainingCount) verBtn.textContent = 'Ver todas (' + remainingCount + ')';
        else verBtn.textContent = 'Ver todas';
        if (!verBtn.__boundFull) {
          verBtn.addEventListener('click', function(){ try { _openFullListModal(allItems); } catch(_){ } });
          verBtn.__boundFull = true;
        }
      }
    } catch(_){ }
    try { console.debug && console.debug('rdo: renderDesktopPopover - items length', total, items && items[0]); } catch(_){ }
  }

    function _openFullListModal(items){
      try {
        var list = Array.isArray(items) ? items : (window.__rdo_pending_list || []);
        if (!list || !list.length) {
          try { var table = document.querySelector('.tabela_conteiner'); if (table) table.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch(_){ }
          return;
        }

        var existing = document.getElementById('rdo-full-list-overlay');
        if (existing) {
          try { existing.parentNode.removeChild(existing); } catch(_){ }
        }

        try {
          if (!document.getElementById('rdo-full-list-style')){
            var css = '\n#rdo-full-list-overlay{position:fixed;z-index:12000;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;padding:20px;}\n#rdo-full-list-overlay .rdo-full-list-modal{background:#fff;max-width:820px;width:100%;max-height:80vh;overflow:auto;border-radius:8px;padding:16px;box-shadow:0 8px 24px rgba(0,0,0,0.2);}\n#rdo-full-list-overlay .rdo-full-list-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}\n#rdo-full-list-overlay .rdo-full-list-body{max-height:64vh;overflow:auto;}\n#rdo-full-list-overlay .rdo-full-list-item{display:block;width:100%;text-align:left;padding:10px;border-radius:6px;border:1px solid #eee;margin-bottom:8px;background:#fafafa;}\n#rdo-full-list-overlay .rdo-full-list-item:hover{background:#f3f3f3;}\n#rdo-full-list-overlay .rdo-full-list-close{background:transparent;border:0;font-size:18px;cursor:pointer;}\n';
            var s = document.createElement('style'); s.id = 'rdo-full-list-style'; s.type = 'text/css'; s.appendChild(document.createTextNode(css)); document.head.appendChild(s);
          }
        } catch(_){ }

        var overlay = document.createElement('div'); overlay.id = 'rdo-full-list-overlay'; overlay.setAttribute('role','dialog'); overlay.setAttribute('aria-modal','true'); overlay.setAttribute('aria-label','Lista de OS abertas');
        overlay.setAttribute('aria-hidden', 'false');
        console.debug && console.debug('rdo: _openFullListModal - overlay created, items=', (list && list.length) || 0);
        var modal = document.createElement('div'); modal.className = 'rdo-full-list-modal';
        var header = document.createElement('div'); header.className = 'rdo-full-list-header';
        var title = document.createElement('div'); title.textContent = (list.length || 0) + ' OS abertas'; title.style.fontWeight = '600';
        var closeBtn = document.createElement('button'); closeBtn.type = 'button'; closeBtn.className = 'rdo-full-list-close'; closeBtn.setAttribute('aria-label','Fechar'); closeBtn.textContent = '×';
        header.appendChild(title); header.appendChild(closeBtn);
        var body = document.createElement('div'); body.className = 'rdo-full-list-body';

        list.forEach(function(it){ try {
          var btn = document.createElement('button'); btn.type='button'; btn.className='rdo-full-list-item';
          var osNum = it.numero_os || it.os || '';
          var osId = it.os_id || it.id || '';
          var empresa = it.empresa || it.cliente || '';
          var unidade = it.unidade || '';
          var label = '';
          if (osNum) {
            label = osNum;
            if (osId && String(osId) !== String(osNum)) label += ' (ID ' + osId + ')';
          } else if (osId) {
            label = 'ID ' + osId;
          } else {
            label = '-';
          }
          btn.textContent = [label, empresa, unidade].filter(Boolean).join(' • ');
          btn.addEventListener('click', function(ev){ try {
            ev.preventDefault();
            var ctx = { rdo_id: it.rdo_id || it.id || '', os_id: it.os_id || it.id || '', numero_os: osNum, os: osNum, empresa: empresa, unidade: unidade, supervisor: it.supervisor || '' };
            try { if (typeof window.rdoOpenSupervisorModal === 'function') window.rdoOpenSupervisorModal(ctx); else if (typeof openSupervisorModal === 'function') openSupervisorModal(ctx); } catch(_){ }
            try { document.body.removeChild(overlay); } catch(_){ }
          } catch(_){ } });
          body.appendChild(btn);
        } catch(_){ } });

        modal.appendChild(header); modal.appendChild(body); overlay.appendChild(modal); document.body.appendChild(overlay);
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
        if (!_isDesktop()) return;

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

      var search = qs('#rdo-popover-search-input', pop);
      if (search){
        search.addEventListener('input', function(){
          try {
            var term = (search.value || '').toLowerCase().trim();
            var canonical = (pop.__allItemsOriginal && Array.isArray(pop.__allItemsOriginal)) ? pop.__allItemsOriginal : [];
            if (!term) {
              _renderDesktopPopover((canonical && canonical.slice) ? canonical.slice(0,5) : canonical);
              return;
            }

            var matched = canonical.filter(function(it){
              try {
                var osNum = String(it.numero_os || it.os || it.os_id || it.id || '').toLowerCase();
                var empresa = String(it.empresa || it.cliente || '').toLowerCase();
                var unidade = String(it.unidade || it.unidade || '').toLowerCase();
                var hay = [osNum, empresa, unidade].join(' ');
                return hay.indexOf(term) !== -1;
              } catch(_){ return false; }
            });

            _renderDesktopPopover(matched);
          } catch(_){ }
        });
      }

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

  // Modal de criação/associação de tanque dentro do modal Editor.
  // Objetivo: permitir preencher os mesmos campos do Tanque do modal Supervisor (RdoTanque).
  // Retorna uma Promise que resolve com um objeto (chaves iguais ao POST do add_tank_ajax) ou null se cancelado.
  function showTankCreateModal(defaults){
    return new Promise(function(resolve){
      try{
        defaults = defaults || {};

        function _cloneOptionsFrom(selector){
          try{
            var src = document.querySelector(selector);
            if (!src) return null;
            var opts = [];
            Array.prototype.forEach.call(src.querySelectorAll('option'), function(o){
              try{ opts.push({ value: o.value, label: o.textContent }); }catch(_){ }
            });
            return opts;
          }catch(_){ return null; }
        }

        function _makeField(labelText, el){
          var row = document.createElement('div');
          row.className = 'rdo-tank-create-modal__field';

          var lbl = document.createElement('div');
          lbl.className = 'rdo-tank-create-modal__label';
          lbl.textContent = labelText;
          row.appendChild(lbl);

          try{
            if (!el.className) el.className = 'rdo-tank-create-modal__control';
            else if (String(el.className).indexOf('rdo-tank-create-modal__control') === -1) el.className += ' rdo-tank-create-modal__control';
          }catch(_){ }

          row.appendChild(el);
          return row;
        }

        function _makeInput(type, name, value, placeholder, extra){
          var inp = document.createElement('input');
          inp.type = type || 'text';
          inp.name = name;
          inp.value = (value == null ? '' : String(value));
          inp.placeholder = placeholder || '';
          try{ inp.className = 'rdo-tank-create-modal__control'; }catch(_){ }
          if (extra) {
            try { Object.keys(extra).forEach(function(k){ inp.setAttribute(k, String(extra[k])); }); } catch(_){ }
          }
          return inp;
        }

        function _makeSelect(name, value, options){
          var sel = document.createElement('select');
          sel.name = name;
          try{ sel.className = 'rdo-tank-create-modal__control'; }catch(_){ }
          var opts = options || [];
          if (!opts.length) {
            opts = [{ value: '', label: 'Selecionar...' }];
          }
          opts.forEach(function(o){
            try{
              var opt = document.createElement('option');
              opt.value = o.value;
              opt.textContent = o.label;
              sel.appendChild(opt);
            }catch(_){ }
          });
          try { sel.value = (value == null ? '' : String(value)); } catch(_){ }
          return sel;
        }

        var container = document.createElement('div');
        container.className = 'rdo-tank-create-modal';

        var card = document.createElement('div');
        card.className = 'rdo-tank-create-modal__card';

        var header = document.createElement('div');
        header.className = 'rdo-tank-create-modal__header';

        var title = document.createElement('div');
        title.className = 'rdo-tank-create-modal__title';
        title.textContent = 'Novo Tanque (mesmo RDO)';
        header.appendChild(title);

        var subtitle = document.createElement('div');
        subtitle.className = 'rdo-tank-create-modal__subtitle';
        subtitle.textContent = 'Preencha os dados do tanque e do ambiente (igual ao Supervisor).';
        header.appendChild(subtitle);

        card.appendChild(header);

        var body = document.createElement('div');
        body.className = 'rdo-tank-create-modal__body';

        // Options sourced from Supervisor modal, when available
        var tipoOpts = _cloneOptionsFrom('#sup-tipo-tanque') || [{ value: '', label: 'Selecionar...' }, { value: 'Salão', label: 'Salão' }, { value: 'Compartimento', label: 'Compartimento' }];
        var metodoOpts = _cloneOptionsFrom('#sup-metodo') || [{ value: '', label: 'Selecionar...' }];
        var sentidoOpts = _cloneOptionsFrom('#sup-sentido') || [{ value: '', label: 'Selecionar...' }];
        var ecOpts = _cloneOptionsFrom('#sup-espaco-conf') || [{ value: '', label: 'Selecionar...' }, { value: 'sim', label: 'Sim' }, { value: 'nao', label: 'Não' }];
        var servicoOpts = _cloneOptionsFrom('#sup-servico').filter ? _cloneOptionsFrom('#sup-servico') : null;
        if (!servicoOpts) {
          // tenta pegar o select escondido do dropdown do Supervisor
          servicoOpts = _cloneOptionsFrom('#sup-servico-input') || _cloneOptionsFrom('#sec-tanque select.dropdown-data') || [{ value: '', label: 'Selecionar...' }];
        }
        // Garantir que temos pelo menos um "Selecionar..."
        if (servicoOpts && servicoOpts.length && servicoOpts[0].value !== '') servicoOpts.unshift({ value: '', label: 'Selecionar...' });

        // Layout em duas colunas
        var grid = document.createElement('div');
        grid.className = 'rdo-tank-create-modal__grid';

        // Coluna esquerda
        var colL = document.createElement('div');
        var colR = document.createElement('div');

        // Campos de tanque
        var codInp = _makeInput('text', 'tanque_codigo', defaults.tanque_codigo, 'Ex.: 5M');
        var nomeInp = _makeInput('text', 'tanque_nome', defaults.nome_tanque, 'Ex.: Tanque 5M');
        var tipoSel = _makeSelect('tipo_tanque', defaults.tipo_tanque, tipoOpts);
        var compInp = _makeInput('number', 'numero_compartimentos', defaults.numero_compartimentos, 'Ex.: 1', { min: '1', inputmode: 'numeric' });
        var gavInp = _makeInput('number', 'gavetas', defaults.gavetas, '', { inputmode: 'numeric' });
        var patInp = _makeInput('number', 'patamar', defaults.patamar, '', { inputmode: 'numeric' });
        var volInp = _makeInput('number', 'volume_tanque_exec', defaults.volume_tanque_exec, '', { step: '0.01', inputmode: 'decimal' });
        var servSel = _makeSelect('servico_exec', defaults.servico_exec, servicoOpts);
        var metSel = _makeSelect('metodo_exec', defaults.metodo_exec, metodoOpts);

        colL.appendChild(_makeField('Tanque (código)', codInp));
        colL.appendChild(_makeField('Nome do Tanque', nomeInp));
        colL.appendChild(_makeField('Tipo', tipoSel));
        colL.appendChild(_makeField('Nº Compartimentos', compInp));
        colL.appendChild(_makeField('Gavetas', gavInp));
        colL.appendChild(_makeField('Patamar', patInp));
        colL.appendChild(_makeField('Volume (m³)', volInp));
        colL.appendChild(_makeField('Serviço', servSel));
        colL.appendChild(_makeField('Método', metSel));

        // Ambiente e operacionais
        var ecSel = _makeSelect('espaco_confinado', defaults.espaco_confinado, ecOpts);
        var opsInp = _makeInput('number', 'operadores_simultaneos', defaults.operadores_simultaneos, '', { inputmode: 'numeric' });
        var h2sInp = _makeInput('number', 'h2s_ppm', defaults.h2s_ppm, '', { step: '0.01', inputmode: 'decimal' });
        var lelInp = _makeInput('number', 'lel', defaults.lel, '', { step: '0.01', inputmode: 'decimal' });
        var coInp = _makeInput('number', 'co_ppm', defaults.co_ppm, '', { step: '0.01', inputmode: 'decimal' });
        var o2Inp = _makeInput('number', 'o2_percent', defaults.o2_percent, '', { step: '0.01', inputmode: 'decimal' });
        var nEfInp = _makeInput('number', 'total_n_efetivo_confinado', defaults.total_n_efetivo_confinado, '--', { step: '1', inputmode: 'numeric' });

        var sentidoSel = _makeSelect('sentido_limpeza', defaults.sentido_limpeza, sentidoOpts);
        var tempoBombaInp = _makeInput('number', 'tempo_bomba', defaults.tempo_bomba, '', { step: '0.5', inputmode: 'decimal' });
        var ensacInp = _makeInput('number', 'ensacamento_dia', defaults.ensacamento_dia, '', { step: '1', inputmode: 'numeric' });
        var icaInp = _makeInput('number', 'icamento_dia', defaults.icamento_dia, '', { step: '1', inputmode: 'numeric' });
        var cambaInp = _makeInput('number', 'cambagem_dia', defaults.cambagem_dia, '', { step: '1', inputmode: 'numeric' });
        var tambInp = _makeInput('number', 'tambores_dia', defaults.tambores_dia, '', { step: '1', inputmode: 'numeric' });
        var resSolInp = _makeInput('number', 'residuos_solidos', defaults.residuos_solidos, '', { step: '0.01', inputmode: 'decimal' });
        var resTotInp = _makeInput('number', 'residuos_totais', defaults.residuos_totais, '', { step: '0.01', inputmode: 'decimal' });

        colR.appendChild(_makeField('Houve acesso no espaço confinado?', ecSel));
        colR.appendChild(_makeField('Operadores simultâneos', opsInp));
        colR.appendChild(_makeField('H2S (ppm)', h2sInp));
        colR.appendChild(_makeField('LEL (%)', lelInp));
        colR.appendChild(_makeField('CO (ppm)', coInp));
        colR.appendChild(_makeField('O2 (%)', o2Inp));
        colR.appendChild(_makeField('Total não-efetivo confinado (min)', nEfInp));
        colR.appendChild(_makeField('Sentido limpeza', sentidoSel));
        colR.appendChild(_makeField('Tempo bomba (h)', tempoBombaInp));

        // 6 campos diários: manter o mesmo padrão do grid (1 por coluna)
        // 3 linhas x 2 colunas
        colL.appendChild(_makeField('Ensacamento (diário)', ensacInp));
        colR.appendChild(_makeField('Içamento (diário)', icaInp));
        colL.appendChild(_makeField('Cambagem (diário)', cambaInp));
        colR.appendChild(_makeField('Tambores (diário)', tambInp));
        colL.appendChild(_makeField('Res. sólidos (m³)', resSolInp));
        colR.appendChild(_makeField('Res. total (m³)', resTotInp));

        grid.appendChild(colL);
        grid.appendChild(colR);
        body.appendChild(grid);
        card.appendChild(body);

        var actions = document.createElement('div');
        actions.className = 'rdo-tank-create-modal__footer';

        var btnCancel = document.createElement('button');
        btnCancel.type='button';
        btnCancel.className = 'btn-rdo outline';
        btnCancel.textContent='Cancelar';

        var btnCreate = document.createElement('button');
        btnCreate.type='button';
        btnCreate.className = 'btn-rdo primary';
        btnCreate.textContent='Criar / Associar';

        actions.appendChild(btnCancel);
        actions.appendChild(btnCreate);
        card.appendChild(actions);

        container.appendChild(card);
        document.body.appendChild(container);

        function cleanup(){ try{ document.body.removeChild(container); }catch(_){ } }

        btnCancel.addEventListener('click', function(){ cleanup(); resolve(null); });
        btnCreate.addEventListener('click', function(){
          function v(el){ try{ return (el && el.value != null) ? String(el.value).trim() : ''; }catch(_){ return ''; } }
          var payload = {
            tanque_codigo: v(codInp),
            tanque_nome: v(nomeInp),
            tipo_tanque: v(tipoSel),
            numero_compartimentos: v(compInp),
            gavetas: v(gavInp),
            patamar: v(patInp),
            volume_tanque_exec: v(volInp),
            servico_exec: v(servSel),
            metodo_exec: v(metSel),
            espaco_confinado: v(ecSel),
            operadores_simultaneos: v(opsInp),
            h2s_ppm: v(h2sInp),
            lel: v(lelInp),
            co_ppm: v(coInp),
            o2_percent: v(o2Inp),
            total_n_efetivo_confinado: v(nEfInp),
            sentido_limpeza: v(sentidoSel),
            tempo_bomba: v(tempoBombaInp),
            ensacamento_dia: v(ensacInp),
            icamento_dia: v(icaInp),
            cambagem_dia: v(cambaInp),
            tambores_dia: v(tambInp),
            residuos_solidos: v(resSolInp),
            residuos_totais: v(resTotInp)
          };

          // limpeza de chaves vazias
          try{ Object.keys(payload).forEach(function(k){ if (!payload[k]) delete payload[k]; }); }catch(_){ }

          cleanup(); resolve(payload);
        });

        setTimeout(function(){ try{ codInp.focus(); }catch(_){ } }, 10);
      }catch(e){ console.error('showTankCreateModal failed', e); resolve(null); }
    });
  }

  // Expor globalmente para que handlers delegados possam chamar sem ReferenceError
  try{ if (typeof window !== 'undefined' && !window.showTankCreateModal) window.showTankCreateModal = showTankCreateModal; }catch(_){ }

  // Coleta todos os campos relevantes do modal Editor (IDs começando com 'edit-')
  function collectEditorTankFormData(rdoId){
    var fd = new FormData();
    try{
      var mapping = [
        ['edit-tanque-cod','tanque_codigo'],['edit-tanque-nome','tanque_nome'],['edit-tipo-tanque','tipo_tanque'],['edit-n-comp','numero_compartimentos'],
        ['edit-gavetas','gavetas'],['edit-patamar','patamar'],['edit-volume','volume_tanque_exec'],['edit-servico','servico_exec'],
        ['edit-metodo','metodo_exec'],['edit-espaco-conf','espaco_confinado'],['edit-operadores','operadores_simultaneos'],
        ['edit-h2s','h2s_ppm'],['edit-lel','lel'],['edit-co','co_ppm'],['edit-o2','o2_percent'],
        ['edit-tempo-bomba','tempo_bomba'],['edit-ensac','ensacamento_dia'],['edit-ica','icamento_dia'],['edit-camba','cambagem_dia'],
        ['edit-tambores','tambores_dia'],['edit-res-sol','residuos_solidos'],['edit-res-total','residuos_totais']
      ];
      mapping.forEach(function(pair){
        try{
          var el = document.getElementById(pair[0]);
          if (!el) return;
          var val = (el.type === 'checkbox' || el.type === 'radio') ? (el.checked ? el.value : '') : (el.value!=null?String(el.value).trim():'');
          if (val !== null && val !== undefined && val !== '') fd.append(pair[1], val);
        }catch(e){}
      });
      if (rdoId) fd.append('rdo_id', String(rdoId));
    }catch(e){ console.error('collectEditorTankFormData failed', e); }
    return fd;
  }

  // Expor globalmente como fallback para handlers delegados externos
  try{ if (typeof window !== 'undefined' && !window.collectEditorTankFormData) window.collectEditorTankFormData = collectEditorTankFormData; }catch(_){ }

  function applyContext(ctx){
    try {
      try { console.log && console.log('rdo: applyContext start', ctx); } catch(_){}
  if (!ctx) return;

  // Normalize common data-attribute mistakes: sometimes templates place OS id
  // into `data-rdo-id` by accident. If we have a numeric `rdo_id` but no
  // `os_id` or `rdo_count`, assume the value is actually an OS id and move
  // it to `os_id`. This makes card-open behavior match the notification flow.
  try {
    if (ctx && ctx.rdo_id && (!ctx.os_id || String(ctx.os_id).trim() === '') && (!ctx.rdo_count || String(ctx.rdo_count).trim() === '')) {
      var candidate = String(ctx.rdo_id).replace(/[^0-9]/g,'');
      if (candidate !== '') {
        // move to os_id and clear rdo_id to avoid accidental RDO fetch
        try { ctx.os_id = candidate; } catch(_){ }
        try { ctx.rdo_id = ''; } catch(_){ }
      }
    }
  } catch(_){ }

  try { window.rdo_previous_compartimentos = ctx.previous_compartimentos || window.rdo_previous_compartimentos || []; } catch(_){ }
      var setText = function(id, v){ var el = document.getElementById(id); if (el) el.textContent = (v == null ? '-' : String(v)); };
      setText('sup-context-os', ctx.numero_os || ctx.os || '');
      try{
        var supCtx = document.getElementById('sup-context-os');
        if (supCtx) {
          if (typeof ctx.os_id !== 'undefined' && ctx.os_id !== null && String(ctx.os_id) !== '') {
            try{ supCtx.setAttribute('data-os-id', String(ctx.os_id)); }catch(e){}
          } else {
            try{ supCtx.removeAttribute('data-os-id'); }catch(e){}
          }
        }
      }catch(_){ }
      setText('sup-context-empresa', ctx.empresa || '');
      setText('sup-context-unidade', ctx.unidade || '');
      setText('sup-context-supervisor', ctx.supervisor || ctx.supervisor_fullname || ctx.supervisor_login || '');
  setText('sup-context-rdo', (typeof ctx.rdo_count !== 'undefined' && ctx.rdo_count !== '') ? ctx.rdo_count : (ctx.rdo || ''));

  var form = qs('#form-supervisor');
      if (form) {
        var hidRdo = document.getElementById('sup-rdo-id');

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
        try {
          var contratoEl = document.getElementById('sup-contrato-po');
          if (contratoEl) {
            if (typeof ctx.contrato_po !== 'undefined' && String(ctx.contrato_po || '').trim() !== '') {
              contratoEl.value = ctx.contrato_po || '';
            } else if (ctx.rdo_count != null && String(ctx.rdo_count).trim() !== '') {
              try {
                var selector = 'tr[data-rdo-count="' + String(ctx.rdo_count) + '"]';
                var tr = document.querySelector(selector);
                if (tr) {
                  var po = tr.getAttribute('data-po') || (tr.dataset && (tr.dataset.po || tr.dataset.po)) || '';
                  if (po) contratoEl.value = po;
                }
              } catch(_){ }
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
        try {
          var _cEl = document.getElementById('sup-contrato-po');
          var _final = _cEl ? (_cEl.value || '') : '';
          console.debug && console.debug('rdo: applyContext contrato resolution final', { ctx: ctx, finalPo: _final });
        } catch(_){ }
        try {
          var contratoEl2 = document.getElementById('sup-contrato-po');
          if (contratoEl2) {
            var rawCount = (ctx && (ctx.rdo_count || ctx.rdo)) || '';
            var n = parseInt(String(rawCount).replace(/[^0-9]/g,''), 10);
            if (isFinite(n) && n > 1) {
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
                contratoEl2.readOnly = true;
                contratoEl2.setAttribute('aria-readonly','true');
                contratoEl2.classList.add('readonly');
              }
            } else {
              contratoEl2.readOnly = false;
              contratoEl2.removeAttribute('aria-readonly');
              contratoEl2.classList.remove('readonly');
            }
          }
        } catch(_){ }
      }
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
        var ensacEl = qs('#sup-prev-ensac');
        var icaEl = qs('#sup-prev-ica');
        var cambaEl = qs('#sup-prev-camba');
        var ensacVal = (ctx.ensacamento_prev !== undefined ? ctx.ensacamento_prev : (ctx.ensacamento_previsao !== undefined ? ctx.ensacamento_previsao : (ctx.ensacamento_prevision || ctx.ensacamento || null)));
        var icaVal = (ctx.icamento_prev !== undefined ? ctx.icamento_prev : (ctx.icamento_previsao !== undefined ? ctx.icamento_previsao : (ctx.icamento_prevision || null)));
        var cambaVal = (ctx.cambagem_prev !== undefined ? ctx.cambagem_prev : (ctx.cambagem_previsao !== undefined ? ctx.cambagem_previsao : (ctx.cambagem || null)));

        lockField(ensacEl, ensacVal);
        if ((icaVal === null || typeof icaVal === 'undefined' || String(icaVal).trim() === '') && (ensacVal !== null && typeof ensacVal !== 'undefined' && String(ensacVal).trim() !== '')) {
          lockField(icaEl, ensacVal);
        } else {
          lockField(icaEl, icaVal);
        }
        lockField(cambaEl, cambaVal);
      } catch(e){ console.warn('applyContext: lock previsoes failed', e); }

      try {
        var ncompEl = qs('#sup-n-comp');
        var compSelector = qs('#sup-comp-selector');
        var ncompVal = (ctx.numero_compartimentos !== undefined ? ctx.numero_compartimentos : (ctx.numero_compartimento !== undefined ? ctx.numero_compartimento : null));
        if (ncompEl) {
          if (typeof ncompVal !== 'undefined' && ncompVal !== null && String(ncompVal).toString().trim() !== '') {
            try { ncompEl.value = String(ncompVal); } catch(_){ }
            try { ncompEl.readOnly = true; ncompEl.setAttribute('aria-readonly','true'); ncompEl.classList.add('readonly'); } catch(_){ }
            try { var w = ncompEl.closest('.form-field'); if (w) w.classList.add('rdo-auto-locked'); } catch(_){ }
          } else {
            try { ncompEl.readOnly = false; ncompEl.removeAttribute('aria-readonly'); ncompEl.classList.remove('readonly'); } catch(_){ }
            try { var w2 = ncompEl.closest('.form-field'); if (w2) w2.classList.remove('rdo-auto-locked'); } catch(_){ }
          }
        }
      } catch(e) { console.warn('applyContext: lock numero_compartimentos failed', e); }

      try {
        var prevEnsac = (typeof ctx.ensacamento_acu !== 'undefined' ? ctx.ensacamento_acu : (typeof ctx.ensacamento_cumulativo !== 'undefined' ? ctx.ensacamento_cumulativo : (typeof ctx.ensacamento_total !== 'undefined' ? ctx.ensacamento_total : null)));
        var prevIca = (typeof ctx.icamento_acu !== 'undefined' ? ctx.icamento_acu : (typeof ctx.icamento_cumulativo !== 'undefined' ? ctx.icamento_cumulativo : null));
        var prevCamba = (typeof ctx.cambagem_acu !== 'undefined' ? ctx.cambagem_acu : (typeof ctx.cambagem_cumulativo !== 'undefined' ? ctx.cambagem_cumulativo : null));
        var prevResLiq = (typeof ctx.total_liquido_acu !== 'undefined' ? ctx.total_liquido_acu : (typeof ctx.total_liquido_cumulativo !== 'undefined' ? ctx.total_liquido_cumulativo : (typeof ctx.residuo_liquido_cumulativo !== 'undefined' ? ctx.residuo_liquido_cumulativo : null)));
        var prevResSol = (typeof ctx.residuos_solidos_acu !== 'undefined' ? ctx.residuos_solidos_acu : (typeof ctx.residuos_solidos_cumulativo !== 'undefined' ? ctx.residuos_solidos_cumulativo : null));

        var ensacDiaEl = qs('#sup-ensac');
        var icaDiaEl = qs('#sup-ica');
        var cambaDiaEl = qs('#sup-camba');
        var resLiqDiaEl = qs('#sup-res-liq');
        var resSolDiaEl = qs('#sup-res-sol');

        var ensacAcuEl = qs('#sup-ensac-acu');
        var icaAcuEl = qs('#sup-ica-acu');
        var cambaAcuEl = qs('#sup-camba-acu');
        var resLiqAcuEl = qs('#sup-res-liq-acu');
        var resSolAcuEl = qs('#sup-res-sol-acu');

        function toIntSafe(v){ try { if (v === null || typeof v === 'undefined' || String(v).trim() === '') return 0; return parseInt(String(v).replace(/[^0-9\-]/g,''),10) || 0; } catch(e){ return 0; } }
        function toNumSafe(v){
          try {
            if (v === null || typeof v === 'undefined') return 0;
            var s = String(v).trim();
            if (!s) return 0;
            s = s.replace(',', '.');
            var n = parseFloat(s);
            return isFinite(n) ? n : 0;
          } catch(e){ return 0; }
        }
        function round2(n){ try { return Math.round(n * 100) / 100; } catch(e){ return n; } }

        function setAccumulatesBase(nextCtx){
          if (!nextCtx) return;
          if (typeof nextCtx.ensacamento_acu !== 'undefined') prevEnsac = nextCtx.ensacamento_acu;
          else if (typeof nextCtx.ensacamento_cumulativo !== 'undefined') prevEnsac = nextCtx.ensacamento_cumulativo;
          else if (typeof nextCtx.ensacamento_total !== 'undefined') prevEnsac = nextCtx.ensacamento_total;

          if (typeof nextCtx.icamento_acu !== 'undefined') prevIca = nextCtx.icamento_acu;
          else if (typeof nextCtx.icamento_cumulativo !== 'undefined') prevIca = nextCtx.icamento_cumulativo;

          if (typeof nextCtx.cambagem_acu !== 'undefined') prevCamba = nextCtx.cambagem_acu;
          else if (typeof nextCtx.cambagem_cumulativo !== 'undefined') prevCamba = nextCtx.cambagem_cumulativo;

          if (typeof nextCtx.total_liquido_acu !== 'undefined') prevResLiq = nextCtx.total_liquido_acu;
          else if (typeof nextCtx.total_liquido_cumulativo !== 'undefined') prevResLiq = nextCtx.total_liquido_cumulativo;
          else if (typeof nextCtx.residuo_liquido_cumulativo !== 'undefined') prevResLiq = nextCtx.residuo_liquido_cumulativo;

          if (typeof nextCtx.residuos_solidos_acu !== 'undefined') prevResSol = nextCtx.residuos_solidos_acu;
          else if (typeof nextCtx.residuos_solidos_cumulativo !== 'undefined') prevResSol = nextCtx.residuos_solidos_cumulativo;
        }

        function recomputeAccumulates(){
          try{
            var baseEns = toIntSafe(prevEnsac);
            var baseIca = toIntSafe(prevIca);
            var baseCamba = toIntSafe(prevCamba);
            var baseResLiq = toNumSafe(prevResLiq);
            var baseResSol = toNumSafe(prevResSol);
            var curEns = ensacDiaEl ? toIntSafe(ensacDiaEl.value) : 0;
            var curIca = icaDiaEl ? toIntSafe(icaDiaEl.value) : 0;
            var curCamba = cambaDiaEl ? toIntSafe(cambaDiaEl.value) : 0;
            var curResLiq = resLiqDiaEl ? toNumSafe(resLiqDiaEl.value) : 0;
            var curResSol = resSolDiaEl ? toNumSafe(resSolDiaEl.value) : 0;
            if (ensacAcuEl) ensacAcuEl.value = String(baseEns + curEns);
            if (icaAcuEl) icaAcuEl.value = String(baseIca + curIca);
            if (cambaAcuEl) cambaAcuEl.value = String(baseCamba + curCamba);
            if (resLiqAcuEl) resLiqAcuEl.value = String(round2(baseResLiq + curResLiq));
            if (resSolAcuEl) resSolAcuEl.value = String(round2(baseResSol + curResSol));
          }catch(e){}
        }

        try{
          function bindAccListener(el){
            if (!el) return;
            try { if (el.__accHandler) el.removeEventListener('input', el.__accHandler); } catch(_){}
            try { el.addEventListener('input', recomputeAccumulates); } catch(_){}
            el.__accHandler = recomputeAccumulates;
            el.__accBound = true;
          }
          bindAccListener(ensacDiaEl);
          bindAccListener(icaDiaEl);
          bindAccListener(cambaDiaEl);
          bindAccListener(resLiqDiaEl);
          bindAccListener(resSolDiaEl);
        }catch(e){}

        try {
          var supFormAcc = document.getElementById('form-supervisor');
          if (supFormAcc) {
            supFormAcc.__applyAccBase = function(nextCtx){
              try {
                setAccumulatesBase(nextCtx || {});
                recomputeAccumulates();
              } catch(_){}
            };
          }
        } catch(_){}

        recomputeAccumulates();
      } catch(e){ console.warn('applyContext: realtime accumulates failed', e); }

    function extractOpenOsFromTable(){
          try {
            var rows = document.querySelectorAll('table tbody tr[data-os-id]');
            if (!rows || !rows.length) return [];
            var map = Object.create(null);
            Array.prototype.forEach.call(rows, function(tr){
              try {
                var osId = tr.getAttribute('data-os-id') || '';
                if (!osId) return;
                var status = (tr.getAttribute('data-status-geral') || (tr.dataset && (tr.dataset.statusGeral || tr.dataset.statusGeral)) || '').toString().toLowerCase();
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
    try {
      try { populateNextRdoIfNeeded(ctx); } catch(_) {}
    } catch(_) {}
    } catch(e){ console.warn('applyContext failed', e); }
  }

  async function fetchAndPopulateRdo(rdoId){
    if (!rdoId) return null;
    try {
      var url = '/rdo/' + encodeURIComponent(rdoId) + '/detail/';
      var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) {
        if (resp.status === 404) return null;
        try {
          var txt = null;
          try { var j = await resp.json(); if (j && (j.error || j.message)) txt = j.error || j.message; } catch(_){ }
          if (!txt) {
            try { txt = (await resp.text()) || (resp.status + ' ' + resp.statusText); } catch(_){ txt = (resp.status + ' ' + resp.statusText); }
          }
          if (txt) showToast(txt, 'error');
        } catch(_){ }
        return null;
      }
      var data = await resp.json();
      if (!data || !data.success || !data.rdo) return null;
      var r = data.rdo || {};
      try{ window.rdo_previous_compartimentos = r.previous_compartimentos || window.rdo_previous_compartimentos || []; }catch(_){ }
      var pairs = [
        ['sup-total-atividades','total_atividade_min'],
        ['sup-total-confinado','total_confinado_min'],
        ['sup-total-abertura-pt','total_abertura_pt_min'],
        ['sup-total-atividades-efetivas','total_atividades_efetivas_min']
      ];
      pairs.forEach(function(p){ var el = document.getElementById(p[0]); if (el && (r[p[1]] != null)) el.value = String(r[p[1]]); });

      try {
        var ensAcu = (r.ensacamento_cumulativo != null ? r.ensacamento_cumulativo : (r.ensacamento_acu != null ? r.ensacamento_acu : (r.ensacamento_total != null ? r.ensacamento_total : null)));
        var icaAcu = (r.icamento_cumulativo != null ? r.icamento_cumulativo : (r.icamento_acu != null ? r.icamento_acu : null));
        var cambAcu = (r.cambagem_cumulativo != null ? r.cambagem_cumulativo : (r.cambagem_acu != null ? r.cambagem_acu : null));
        var liqAcu = (r.total_liquido_cumulativo != null ? r.total_liquido_cumulativo : (r.total_liquido_acu != null ? r.total_liquido_acu : (r.residuo_liquido_cumulativo != null ? r.residuo_liquido_cumulativo : null)));
        var solAcu = (r.residuos_solidos_cumulativo != null ? r.residuos_solidos_cumulativo : (r.residuos_solidos_acu != null ? r.residuos_solidos_acu : null));
        var ensAcuEl = document.getElementById('sup-ensac-acu');
        var icaAcuEl = document.getElementById('sup-ica-acu');
        var cambAcuEl = document.getElementById('sup-camba-acu');
        var liqAcuEl = document.getElementById('sup-res-liq-acu');
        var solAcuEl = document.getElementById('sup-res-sol-acu');
        if (ensAcuEl && ensAcu != null) ensAcuEl.value = String(ensAcu);
        if (icaAcuEl && icaAcu != null) icaAcuEl.value = String(icaAcu);
        if (cambAcuEl && cambAcu != null) cambAcuEl.value = String(cambAcu);
        if (liqAcuEl && liqAcu != null) liqAcuEl.value = String(liqAcu);
        if (solAcuEl && solAcu != null) solAcuEl.value = String(solAcu);
        try {
          var supFormAcc = document.getElementById('form-supervisor');
          if (supFormAcc && typeof supFormAcc.__applyAccBase === 'function') {
            supFormAcc.__applyAccBase({
              ensacamento_cumulativo: ensAcu,
              icamento_cumulativo: icaAcu,
              cambagem_cumulativo: cambAcu,
              total_liquido_cumulativo: liqAcu,
              residuos_solidos_cumulativo: solAcu
            });
          }
        } catch(_){}
      } catch(e) {}
      try {
        var _pick = function(obj, keys){ for (var i=0;i<keys.length;i++){ var k = keys[i]; if (typeof obj[k] !== 'undefined' && obj[k] !== null) return obj[k]; } return null; };
        var plc = _pick(r, ['percentual_limpeza_cumulativo', 'limpeza_acu', 'limpeza_acumulado', 'percentual_limpeza_acu']);
        var plfc = _pick(r, ['percentual_limpeza_fina_cumulativo', 'limpeza_fina_acu', 'limpeza_fina_acumulado']);
        try { var supL = document.getElementById('sup-limp'); if (supL) supL.value = ''; } catch(_){ }
        try { var supLF = document.getElementById('sup-limp-fina'); if (supLF) supLF.value = ''; } catch(_){ }
        try { var supLA = document.getElementById('sup-limp-acu'); if (supLA && plc != null) supLA.value = String(plc); } catch(_){ }
        try { var supLFA = document.getElementById('sup-limp-fina-acu'); if (supLFA && plfc != null) supLFA.value = String(plfc); } catch(_){ }
      } catch(_) {}

      try {
        var confEl = document.getElementById('sup-total-n-efetivo-confinado');
        if (confEl) {
          var v = (r.total_n_efetivo_confinado_min != null) ? r.total_n_efetivo_confinado_min : (r.total_n_efetivo_confinado != null ? r.total_n_efetivo_confinado : null);
          if (v != null) confEl.value = String(v);
        }
      } catch(e) {}
      return r;
    } catch(e){ console.warn('fetchAndPopulateRdo failed', e); }
    return null;
  }

  function resetSupervisorAccumulates(){
    try {
      var ids = [
        'sup-ensac', 'sup-ica', 'sup-camba',
        'sup-res-liq', 'sup-res-sol',
        'sup-ensac-acu', 'sup-ica-acu', 'sup-camba-acu',
        'sup-res-liq-acu', 'sup-res-sol-acu'
      ];
      ids.forEach(function(id){
        try {
          var el = document.getElementById(id);
          if (!el) return;
          el.value = '';
          try { delete el.__accumLast; } catch(_){}
          try { delete el.__accumCur; } catch(_){}
        } catch(_){}
      });
      try {
        var supFormAcc = document.getElementById('form-supervisor');
        if (supFormAcc && typeof supFormAcc.__applyAccBase === 'function') {
          supFormAcc.__applyAccBase({
            ensacamento_cumulativo: null,
            icamento_cumulativo: null,
            cambagem_cumulativo: null,
            total_liquido_cumulativo: null,
            residuos_solidos_cumulativo: null
          });
        }
      } catch(_){}
    } catch(_){}
  }

  async function populateNextRdoIfNeeded(ctx){
    try {
      if (!ctx) ctx = {};
      // Em modo edição (RDO existente), não calcular o próximo RDO.
      // Isso evita que o modal sugira o próximo número e o usuário acabe criando
      // um RDO novo (nova "linha") sem querer.
      try {
        if (ctx && (ctx.edit === true || ctx.action === 'edit' || ctx.forceEdit === true)) return;
      } catch(_){ }
      var supRdoEl = document.getElementById('sup-rdo');
      var contratoEl = document.getElementById('sup-contrato-po');
      if (contratoEl && typeof ctx.contrato_po !== 'undefined') { try { contratoEl.value = ctx.contrato_po || ''; } catch(_){} }
      if (!supRdoEl) return;
      var rc = ctx.rdo_count || '';
      var osId = ctx.os_id || '';
      if ((!osId || String(osId).trim() === '') && rc != null && String(rc).trim() !== '' && /^\d+$/.test(String(rc).trim())) {
        try { supRdoEl.value = String(parseInt(String(rc).trim(),10) + 1); return; } catch(_){ }
      }
  if (!osId) return;
  try { supRdoEl.dataset.prev = supRdoEl.value || ''; supRdoEl.value = 'Carregando...'; } catch(_){}
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
          var next = null;
          if (typeof data.next_rdo !== 'undefined') next = data.next_rdo;
          else if (typeof data.next !== 'undefined') next = data.next;
          else if (typeof data.rdo !== 'undefined') next = data.rdo;
          else if (typeof data.next_r !== 'undefined') next = data.next_r;
          if (next == null) continue;
          try { supRdoEl.value = String(next); } catch(_){ }
          return;
        } catch(e){}
      }
      try { if (typeof supRdoEl.dataset !== 'undefined' && typeof supRdoEl.dataset.prev !== 'undefined') supRdoEl.value = supRdoEl.dataset.prev || ''; } catch(_){}
    } catch(e){ console.warn('populateNextRdoIfNeeded failed', e); }
  }

  function _getTeamFieldValue(row, selectors){
    try {
      for (var i = 0; i < selectors.length; i++) {
        var el = row.querySelector(selectors[i]);
        if (!el) continue;
        var raw = (typeof el.value !== 'undefined') ? el.value : el.textContent;
        var val = (raw == null) ? '' : String(raw).trim();
        if (val !== '') return val;
      }
    } catch(_){ }
    return '';
  }

  function countTeamMembers(wrapper){
    try {
      if (!wrapper) return 0;
      var rows = wrapper.querySelectorAll('.team-row');
      var total = 0;
      Array.prototype.forEach.call(rows, function(row){
        try {
          var nome = _getTeamFieldValue(row, [
            '.equipe-nome',
            'input[name="equipe_nome[]"]',
            'select[name="equipe_nome[]"]',
            'input[name="equipe_nome"]',
            'select[name="equipe_nome"]'
          ]);
          var func = _getTeamFieldValue(row, [
            '.equipe-funcao',
            'input[name="equipe_funcao[]"]',
            'select[name="equipe_funcao[]"]',
            'input[name="equipe_funcao"]',
            'select[name="equipe_funcao"]'
          ]);
          var pid = _getTeamFieldValue(row, [
            'input[name="equipe_pessoa_id[]"]',
            'input[name="equipe_pessoa_id"]'
          ]);
          if (nome || func || pid) total += 1;
        } catch(_){ }
      });
      return total;
    } catch(_){
      return 0;
    }
  }

  function _ensurePobField(form, createHidden){
    try {
      if (!form) return null;
      var visible = form.querySelector('input[name="pob"]:not([type="hidden"])');
      if (visible) {
        try {
          var oldHidden = form.querySelector('input[type="hidden"][name="pob"][data-auto-pob="1"]');
          if (oldHidden && oldHidden.parentNode) oldHidden.parentNode.removeChild(oldHidden);
        } catch(_){ }
        return visible;
      }
      var hidden = form.querySelector('input[type="hidden"][name="pob"][data-auto-pob="1"]');
      if (hidden) return hidden;
      if (!createHidden) return null;
      hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'pob';
      hidden.setAttribute('data-auto-pob', '1');
      form.appendChild(hidden);
      return hidden;
    } catch(_){
      return null;
    }
  }

  function syncPobWithEquipe(form){
    try {
      if (!form) return 0;
      var wrap = null;
      try { wrap = form.querySelector('#edit-equipe-wrapper, #equipe-wrapper'); } catch(_){ wrap = null; }
      var total = countTeamMembers(wrap);
      var pobField = _ensurePobField(form, true);
      if (pobField) {
        try { pobField.value = String(total); } catch(_){ }
        try {
          if (pobField.type !== 'hidden') {
            pobField.readOnly = true;
            pobField.setAttribute('aria-readonly', 'true');
          }
        } catch(_){ }
      }
      return total;
    } catch(_){
      return 0;
    }
  }

  function syncPobAllForms(){
    try {
      var supForm = document.getElementById('form-supervisor');
      if (supForm) syncPobWithEquipe(supForm);
    } catch(_){ }
    try {
      var editForm = document.getElementById('form-editor');
      if (editForm) syncPobWithEquipe(editForm);
    } catch(_){ }
  }

  function schedulePobSync(){
    try {
      if (window.requestAnimationFrame) {
        window.requestAnimationFrame(function(){ syncPobAllForms(); });
      } else {
        setTimeout(function(){ syncPobAllForms(); }, 0);
      }
    } catch(_){
      try { syncPobAllForms(); } catch(__){ }
    }
  }

  function buildSupervisorFormData(form){
    if (!form) form = qs('#form-supervisor');
    var fd = null;
    var usedExternalBuilder = false;
    if (window.buildSupervisorFormDataExternal && typeof window.buildSupervisorFormDataExternal === 'function') {
      try {
        fd = window.buildSupervisorFormDataExternal(form);
        usedExternalBuilder = !!fd;
      } catch(e){
        console.warn('External builder failed, fallback used', e);
        fd = null;
      }
    }
    if (!fd) fd = new FormData();
    function _normalizeSentido(raw){
      try{
        if (raw == null) return '';
        var s = String(raw).trim(); if (!s) return '';
        var low = s.toLowerCase();
        var canon = ['vante > ré','ré > vante','bombordo > boreste','boreste < bombordo'];
        for (var i=0;i<canon.length;i++){ if (low === canon[i].toLowerCase()) return canon[i]; }
        if (low === 'true' || low === 'sim' || low === 'vante' || low === 'vante->ré' || low === 'vante-para-ré' || low === 'vante para ré') return 'vante > ré';
        if (low === 'false' || low === 'nao' || low === 'não' || low === 'ré' || low === 'ré->vante' || low === 'ré-para-vante' || low === 'ré para vante') return 'ré > vante';
        if (low.indexOf('vante') !== -1 && low.indexOf('ré') !== -1){ if (low.indexOf('vante') < low.indexOf('ré')) return 'vante > ré'; else return 'ré > vante'; }
        if (low.indexOf('bombordo') !== -1 && low.indexOf('boreste') !== -1){ if (low.indexOf('bombordo') < low.indexOf('boreste')) return 'bombordo > boreste'; else return 'boreste < bombordo'; }
        return s;
      } catch(_){ return String(raw||''); }
    }
    function _formDataHasPhotos(formData){
      try {
        if (!formData || typeof formData.entries !== 'function') return false;
        var it = formData.entries(); var ne = it.next();
        while (!ne.done) {
          if (ne.value && ne.value[0] && String(ne.value[0]).indexOf('fotos') === 0) return true;
          ne = it.next();
        }
      } catch(_){}
      return false;
    }

    if (!usedExternalBuilder) {
      Array.prototype.forEach.call(form.elements, function(el){
        if (!el || !el.name) return;
        if (el.type === 'file') return;
        if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return;
        try {
          if (el.closest && (el.closest('#atividades-wrapper') || el.closest('#equipe-wrapper'))) return;
        } catch(_){ }
        try {
          if (el.closest && (el.closest('.activities-row') || el.closest('.team-row'))) return;
        } catch(_){ }
        try {
          if (el.name === 'sentido_limpeza') {
            try { fd.append(el.name, _normalizeSentido(el.value || '')); }
            catch(e){ fd.append(el.name, el.value); }
          } else {
            fd.append(el.name, el.value);
          }
        } catch(_){ try { fd.append(el.name, el.value); } catch(__){} }
      });
    }
    if (!usedExternalBuilder && !_formDataHasPhotos(fd)) {
      var fInputs = qsa('input[type=file][name="fotos"]', form);
      var rawFiles = [];
      fInputs.forEach(function(inp){ if (inp.files) Array.prototype.forEach.call(inp.files, function(f){ rawFiles.push(f); }); });
      try {
        rawFiles.forEach(function(f){ fd.append('fotos', f); });
      } catch(e){}
    }
    try {
      function _normPercent(s){
        if (s == null) return '';
        var t = String(s).trim();
        if (!t) return '';
        if (t.slice(-1) === '%') t = t.slice(0, -1).trim();
        t = t.replace(',', '.');
        if (/^-?\d+(?:\.\d+)?$/.test(t)) return t;
        var i = parseInt(t, 10);
        return isNaN(i) ? '' : String(i);
      }
      var superKeys = ['sup-limp','sup-limp-acu','sup-limp-fina','sup-limp-fina-acu'];
      var altMap = {
        'sup-limp': ['#limpeza_mecanizada_diaria', 'input[name="limpeza_mecanizada_diaria"]', '#percentual_limpeza', 'input[name="percentual_limpeza"]'],
        'sup-limp-fina': ['#limpeza_fina_diaria', 'input[name="limpeza_fina_diaria"]', '#percentual_limpeza_fina', 'input[name="percentual_limpeza_fina"]'],
        'sup-limp-acu': ['#limpeza_mecanizada_cumulativa', 'input[name="limpeza_mecanizada_cumulativa"]', '#percentual_limpeza_cumulativo', 'input[name="percentual_limpeza_cumulativo"]'],
        'sup-limp-fina-acu': ['#limpeza_fina_cumulativa', 'input[name="limpeza_fina_cumulativa"]', '#percentual_limpeza_fina_cumulativo', 'input[name="percentual_limpeza_fina_cumulativo"]']
      };
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
          var canonicalSet = [];
          var canonicalDelete = [];
          if (k === 'sup-limp') { canonicalSet.push(['avanco_limpeza','limpeza_mecanizada_diaria']); canonicalDelete.push('avanco_limpeza'); canonicalDelete.push('limpeza_mecanizada_diaria'); }
          else if (k === 'sup-limp-fina') { canonicalSet.push(['avanco_limpeza_fina','limpeza_fina_diaria']); canonicalDelete.push('avanco_limpeza_fina'); canonicalDelete.push('limpeza_fina_diaria'); }
          else if (k === 'sup-limp-acu') { canonicalSet.push(['limpeza_acu','limpeza_mecanizada_cumulativa','percentual_limpeza_cumulativo']); canonicalDelete.push('limpeza_acu'); canonicalDelete.push('limpeza_mecanizada_cumulativa'); canonicalDelete.push('percentual_limpeza_cumulativo'); }
          else if (k === 'sup-limp-fina-acu') { canonicalSet.push(['limpeza_fina_acu','limpeza_fina_cumulativa','percentual_limpeza_fina_cumulativo']); canonicalDelete.push('limpeza_fina_acu'); canonicalDelete.push('limpeza_fina_cumulativa'); canonicalDelete.push('percentual_limpeza_fina_cumulativo'); }

            if (val !== '') {
            try { if (typeof fd.set === 'function') fd.set(k, val); else fd.append(k, val); } catch(_){ }
            canonicalSet.forEach(function(arr){
              for (var ii=0; ii<arr.length; ii++){
                try { if (typeof fd.set === 'function') fd.set(arr[ii], val); else fd.append(arr[ii], val); } catch(_){ }
              }
            });
          } else {
            try { if (typeof fd.delete === 'function') fd.delete(k); } catch(_){ }
            canonicalDelete.forEach(function(nm){ try { if (typeof fd.delete === 'function') fd.delete(nm); } catch(_){ } });
          }
        } catch(_){ }
      });
    } catch(_){ }
    if (!usedExternalBuilder) {
      try {
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
              if ((nome !== '') || (cpt !== '') || (inicio !== '') || (fim !== '')) {
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

        var equipeWrappers = [];
        try { var ew1 = form.querySelector('#equipe-wrapper'); if (ew1) equipeWrappers.push(ew1); } catch(_){ }
        try { var ew2 = form.querySelector('#edit-equipe-wrapper'); if (ew2) equipeWrappers.push(ew2); } catch(_){ }
        var seenEq = new Set();
        equipeWrappers.forEach(function(equipeWrapper){
          var memRows = equipeWrapper.querySelectorAll('.team-row');
          Array.prototype.forEach.call(memRows, function(row){
            try {
              var nome = '';
              var nomeEl = row.querySelector('.equipe-nome, input[name="equipe_nome[]"], select[name="equipe_nome[]"]');
              if (nomeEl) nome = (nomeEl.value || '').trim();
              var func = '';
              var funcEl = row.querySelector('.equipe-funcao, input[name="equipe_funcao[]"], select[name="equipe_funcao[]"]');
              if (funcEl) func = (funcEl.value || '').trim();
              var ems = '';
              var emsEl = row.querySelector('input[name="equipe_em_servico[]"]');
              if (emsEl) {
                if (emsEl.type === 'checkbox' || emsEl.type === 'radio') ems = emsEl.checked ? '1' : '0'; else ems = (emsEl.value || '').trim();
              }
              var pid = '';
              var pidEl = row.querySelector('input[name="equipe_pessoa_id[]"]');
              if (pidEl) pid = (pidEl.value || '').trim();
              if (nomeEl && nomeEl.tagName && nomeEl.tagName.toLowerCase() === 'select') {
                try {
                  var opt = (nomeEl.options && nomeEl.selectedIndex >= 0) ? nomeEl.options[nomeEl.selectedIndex] : null;
                  var optPid = opt && (opt.getAttribute('data-id') || (opt.dataset && opt.dataset.id));
                  if (optPid != null && String(optPid).trim() !== '') {
                    pid = String(optPid).trim();
                  } else {
                    pid = '';
                  }
                  if (pidEl) pidEl.value = pid;
                } catch(_){ }
              }
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
    }

    try {
      var hasFotos = _formDataHasPhotos(fd);
      if (!hasFotos && window && window._supvPhotoDT && window._supvPhotoDT.files && window._supvPhotoDT.files.length) {
        try {
          Array.prototype.forEach.call(window._supvPhotoDT.files, function(f){
            try { fd.append('fotos', f); } catch(_){ }
          });
        } catch(_){ }
      }
    } catch(_){ }

    try {
      var pobCount = syncPobWithEquipe(form);
      if (typeof fd.set === 'function') fd.set('pob', String(pobCount));
      else fd.append('pob', String(pobCount));
    } catch(_){ }

    return fd;
  }
  onReady(function(){
    try{
      var ensac = qs('#sup-prev-ensac');
      var ica = qs('#sup-prev-ica');
      if (ensac && ica) {
        ensac.addEventListener('input', function(){
          try{ ica.value = ensac.value; }catch(e){}
        }, false);
        ensac.addEventListener('change', function(){
          try{ ica.value = ensac.value; }catch(e){}
        }, false);
      }
    }catch(e){ console.warn('sync ensac->ica failed', e); }
  });

  onReady(function(){
    try {
      schedulePobSync();
      if (!document.__rdoPobSyncBound) {
        document.__rdoPobSyncBound = true;
        function _isTeamEventTarget(t){
          try {
            if (!t || !t.closest) return false;
            return !!t.closest('#equipe-wrapper, #edit-equipe-wrapper');
          } catch(_){
            return false;
          }
        }
        document.addEventListener('input', function(ev){
          var t = ev && ev.target ? ev.target : null;
          if (!_isTeamEventTarget(t)) return;
          schedulePobSync();
        }, true);
        document.addEventListener('change', function(ev){
          var t = ev && ev.target ? ev.target : null;
          if (!_isTeamEventTarget(t)) return;
          schedulePobSync();
        }, true);
        document.addEventListener('mousedown', function(ev){
          var t = ev && ev.target ? ev.target : null;
          if (!_isTeamEventTarget(t)) return;
          try {
            if (t.closest('.dropdown-option') || t.closest('#btn-add-membro') || t.closest('#edit-btn-add-membro') || t.closest('#btn-remove-membro') || t.closest('#edit-btn-remove-membro')) {
              schedulePobSync();
            }
          } catch(_){ }
        }, true);
      }
    } catch(_){ }
  });

  function initPhotoRemoveHandlers(context){
    var container = context || document;
    container.addEventListener('click', function(ev){
      try {
        var btn = ev.target.closest && ev.target.closest('.photo-remove');
        if (!btn) return;
        ev.preventDefault();
        var item = btn.closest && btn.closest('.photo-slot');
        var slotName = item && item.getAttribute ? item.getAttribute('data-slot-name') : null;
        var form = document.getElementById('form-supervisor') || document.getElementById('form-editor') || document.querySelector('form');
        if (slotName && form) {
          var inp = document.createElement('input'); inp.type = 'hidden'; inp.name = 'fotos_remove[]'; inp.value = slotName; form.appendChild(inp);
        } else if (item) {
          var url = item.getAttribute('data-url') || null;
          if (form && url) {
            var inp2 = document.createElement('input'); inp2.type = 'hidden'; inp2.name = 'fotos_remove[]'; inp2.value = url; form.appendChild(inp2);
          }
        }
        try { item && item.remove(); } catch(_){ btn.remove(); }
      } catch(e){ console.warn('photo-remove handler failed', e); }
    }, false);
  }

  onReady(function(){ initPhotoRemoveHandlers(document); });

  function isMobileViewport(){
    try { return window.matchMedia && window.matchMedia('(max-width: 767px)').matches; } catch(e){ return (window.innerWidth || document.documentElement.clientWidth) < 768; }
  }

  function removeFinalizedCardsForSupervisor(){
    try {
      var site = document.getElementById('site-wrapper');
      if (!site) return;
      var isSupervisor = (site.getAttribute('data-is-supervisor') || '').toString().toLowerCase() === 'true';
      if (!isSupervisor) return;
      if (!isMobileViewport()) return; 
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

  function _initSupervisorPhotoPreviews(){
    try{
      var MAX_PHOTOS = 5;
      var input = document.getElementById('sup-fotos');
      var btn = document.getElementById('btn-add-foto');
      var previews = document.getElementById('supv-photo-previews');
      if (!input || !btn || !previews) return;
      if (input.__supvPhotoBound) return;
      input.__supvPhotoBound = true;

      var dt = null;
      try { dt = new DataTransfer(); } catch(_){ dt = null; }
      if (!dt || !dt.items) {
        btn.addEventListener('click', function(){ input.click(); });
        input.addEventListener('change', function(){
          try {
            var count = input.files ? input.files.length : 0;
            if (count > 0) showToast(count + ' foto(s) selecionada(s).', 'info');
          } catch(_){}
        });
        return;
      }

      function fileFingerprint(file){
        try { return [file && file.name || '', file && file.size || 0, file && file.lastModified || 0].join('|'); }
        catch(_){ return String(file && file.name || ''); }
      }
      function totalBytesFromDt(){
        var total = 0;
        try {
          Array.prototype.forEach.call(dt.files || [], function(f){ total += Number((f && f.size) || 0); });
        } catch(_){}
        return total;
      }
      function syncInput(){
        try { input.files = dt.files; } catch(_){}
        try { window._supvPhotoDT = dt; } catch(_){}
      }

      function renderPreviews(){
        previews.innerHTML = '';
        if (!dt.files || !dt.files.length) {
          var empty = document.createElement('div');
          empty.style.fontSize = '12px';
          empty.style.color = '#5f6b66';
          empty.textContent = 'Nenhuma foto selecionada.';
          previews.appendChild(empty);
        }
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
            remove.textContent = '×';
            remove.addEventListener('click', function(){
              try{
                var files = Array.prototype.slice.call(dt.files);
                files.splice(idx, 1);
                var newDt = new DataTransfer();
                files.forEach(function(f){ newDt.items.add(f); });
                while(dt.items.length) dt.items.remove(0);
                Array.prototype.forEach.call(newDt.files, function(f){ dt.items.add(f); });
                syncInput();
                try{ if (img && img.dataset && img.dataset.objectUrl) URL.revokeObjectURL(img.dataset.objectUrl); }catch(_){ }
                renderPreviews();
              }catch(_){ renderPreviews(); }
            });
            slot.appendChild(remove);

            previews.appendChild(slot);
          }catch(e){ console.warn('render preview item failed', e); }
        });
        try {
          var info = document.createElement('div');
          info.style.flexBasis = '100%';
          info.style.fontSize = '12px';
          info.style.color = '#385247';
          info.textContent = dt.files.length + ' foto(s) pronta(s) para envio (' + formatBytes(totalBytesFromDt()) + ').';
          previews.appendChild(info);
        } catch(_){}
        try{ btn.disabled = dt.files.length >= MAX_PHOTOS; }catch(_){ }
      }

      btn.addEventListener('click', function(){ input.click(); });

      input.addEventListener('change', function(e){
        try{
          var incoming = Array.prototype.slice.call((e && e.target && e.target.files) || []);
          try { input.value = ''; } catch(_){}
          if (!incoming.length) return;

          var existingKeys = {};
          Array.prototype.forEach.call(dt.files || [], function(f){ existingKeys[fileFingerprint(f)] = true; });
          incoming = incoming.filter(function(f){
            var key = fileFingerprint(f);
            if (existingKeys[key]) return false;
            existingKeys[key] = true;
            return true;
          });
          if (!incoming.length) {
            showToast('Essas fotos já foram adicionadas.', 'info');
            return;
          }

          var remaining = MAX_PHOTOS - (dt.files ? dt.files.length : 0);
          if (remaining <= 0) {
            showToast('Limite de ' + MAX_PHOTOS + ' fotos atingido.', 'warning');
            return;
          }
          if (incoming.length > remaining) {
            incoming = incoming.slice(0, remaining);
            showToast('Máximo de ' + MAX_PHOTOS + ' fotos por envio.', 'warning');
          }

          showUploadProgress('Otimizando fotos para envio...', 0);
          optimizePhotoList(incoming, function(done, total){
            var pct = Math.round((done / Math.max(1, total)) * 100);
            showUploadProgress('Otimizando fotos para envio...', pct);
          }).then(function(optimized){
            try {
              Array.prototype.forEach.call(optimized || [], function(f){
                if (!f || dt.files.length >= MAX_PHOTOS) return;
                try { dt.items.add(f); } catch(_){}
              });
              syncInput();
              renderPreviews();
              showUploadProgress('Fotos 100% preparadas para envio.', 100);
              hideUploadProgress(500);
              showToast('Fotos prontas: ' + dt.files.length + ' arquivo(s) (' + formatBytes(totalBytesFromDt()) + ').', 'success');
            } catch(_){
              hideUploadProgress(0);
            }
          }).catch(function(){
            hideUploadProgress(0);
            showToast('Falha ao otimizar fotos. Tentando enviar originais.', 'warning');
          });
        }catch(e){ console.warn('supv photo change failed', e); }
      });
      syncInput();
      renderPreviews();
    }catch(e){ console.warn('initSupervisorPhotoPreviews failed', e); }
  }
  onReady(_initSupervisorPhotoPreviews);

  function _initEditorPhotoCompression(){
    try {
      var input = document.getElementById('edit-fotos');
      if (!input || input.__rdoEditPhotoCompressBound) return;
      input.__rdoEditPhotoCompressBound = true;

      input.addEventListener('change', function(ev){
        try {
          var files = Array.prototype.slice.call((ev && ev.target && ev.target.files) || []);
          if (!files.length) return;
          showUploadProgress('Otimizando fotos para envio...', 0);
          optimizePhotoList(files, function(done, total){
            var pct = Math.round((done / Math.max(1, total)) * 100);
            showUploadProgress('Otimizando fotos para envio...', pct);
          }).then(function(optimized){
            try {
              var totalBytes = 0;
              Array.prototype.forEach.call(optimized || [], function(f){ totalBytes += Number((f && f.size) || 0); });
              var dt = null;
              try { dt = new DataTransfer(); } catch(_){ dt = null; }
              if (dt && dt.items) {
                Array.prototype.forEach.call(optimized || [], function(f){ try { dt.items.add(f); } catch(_){} });
                try { input.files = dt.files; } catch(_){}
              }
              showUploadProgress('Fotos 100% preparadas para envio.', 100);
              hideUploadProgress(500);
              showToast('Fotos prontas para envio (' + (optimized ? optimized.length : files.length) + ' arquivo(s), ' + formatBytes(totalBytes) + ').', 'success');
            } catch(_){
              hideUploadProgress(0);
            }
          }).catch(function(){
            hideUploadProgress(0);
            showToast('Falha ao otimizar fotos. Mantendo arquivos originais.', 'warning');
          });
        } catch(_){}
      });
    } catch(e){ console.warn('initEditorPhotoCompression failed', e); }
  }
  onReady(_initEditorPhotoCompression);
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
  function _bindPTFieldsToggle(){
    try {
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
      if (sel.__ptToggleBound) return;

      function setLocked(isLocked){
        try {
          var wrapper = document.querySelector('#sec-pt');
          if (!wrapper) return;
          var inputs = wrapper.querySelectorAll('input[name^="pt_num_"], input[name="pt_num_manha"], input[name="pt_num_tarde"], input[name="pt_num_noite"], input[type="checkbox"][name="pt_turnos[]"]');
          if (isLocked) wrapper.classList.add('rdo-pt-locked'); else wrapper.classList.remove('rdo-pt-locked');
          Array.prototype.forEach.call(inputs, function(i){ try { i.disabled = !!isLocked; if (isLocked) { if (i.type === 'checkbox') i.checked = false; else i.value = ''; } }catch(_){}});
          var hdr = wrapper.querySelector('.rdo-section__head');
          if (hdr) {
            var key = hdr.querySelector('.supv-pt-lock-icon');
            if (isLocked && !key) {
              var span = document.createElement('span');
              span.className = 'supv-pt-lock-icon material-icons';
              span.title = 'Campos de PT bloqueados';
              span.setAttribute('aria-hidden','false');
              span.style.marginLeft = '10px';
              span.style.fontSize = '14px';
              span.textContent = 'lock';
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
      setLocked(((sel.value||'').toString().toLowerCase().trim() === 'nao' || (sel.value||'').toString().toLowerCase().trim() === 'não'));
      sel.__ptToggleBound = true;
    } catch(e){ console.warn('_bindPTFieldsToggle failed', e); }
  }
  onReady(_bindPTFieldsToggle);
  function _injectAutoLockedStyles(){
    try {
      if (document.getElementById('rdo-auto-locked-styles')) return;
      var st = document.createElement('style'); st.id = 'rdo-auto-locked-styles';
      st.type = 'text/css';
      st.appendChild(document.createTextNode('\n.rdo-auto-locked { position: relative; }\n.rdo-auto-locked label { display: inline-flex; align-items: center; gap: 8px; }\n.rdo-auto-locked .auto-lock-icon { font-size: 14px; opacity: 0.9; margin-left: 6px; color: #555; }\n.rdo-auto-locked input[readonly], .rdo-auto-locked input[disabled] { background: #f5f5f5; color: #666; }\n'));
      document.head.appendChild(st);
    } catch(e){}
  }
  onReady(_injectAutoLockedStyles);

  function _lockPreviousRdosOnLoad(){
    try {
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

      function lockElement(el){
        try {
          if (!el) return;
          if (el.classList && el.classList.contains('rdo-locked')) return;
          el.classList.add('rdo-locked');
        } catch(_){ }
      }

      Array.prototype.forEach.call(rows, function(tr){
        try {
          var osId = tr.getAttribute('data-os-id') || tr.getAttribute('data-numero-os') || '';
          var key = normKey(osId, tr.getAttribute('data-numero-os'));
          if (!key) return;
          var rc = parseInt(String(tr.getAttribute('data-rdo-count') || tr.dataset && tr.dataset.rdoCount || '0').replace(/[^0-9]/g,''),10) || 0;
          var max = map[key] || 0;
          var openBtn = null;
          try { openBtn = tr.querySelector('.open-supervisor, .btn-rdo.open-supervisor, .action-btn.open-supervisor'); } catch(_){ openBtn = null; }
          if (rc && max && rc < max) {
            lockElement(tr);
            if (openBtn) {
              try {
                openBtn.classList.add('disabled');
                openBtn.disabled = true;
                openBtn.setAttribute('aria-disabled','true');
                openBtn.setAttribute('data-tooltip','Abrir disponível apenas a partir do último RDO (RDO ' + String(max) + ')');
              } catch(_){ }
            }
          } else {
            if (openBtn) {
              try {
                openBtn.classList.remove('disabled');
                openBtn.disabled = false;
                openBtn.removeAttribute('aria-disabled');
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

  function _removeFinalizedMobileCardsOnLoad(){
    try {
      var rows = document.querySelectorAll('table tbody tr');
      if (rows && rows.length) {
        Array.prototype.forEach.call(rows, function(tr){
          try {
            var status = (tr.getAttribute('data-status-geral') || tr.getAttribute('data-status') || tr.getAttribute('data-status-frente') || tr.getAttribute('data-status_frente') || '');
            status = (status || '').toString().toLowerCase().trim();
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
            if (!(/finaliz|encerrad|fechad|conclu|retorn/.test(status))) return;

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
          var status = (tr.getAttribute('data-status-geral') || tr.getAttribute('data-status') || tr.getAttribute('data-status-frente') || tr.getAttribute('data-status_frente') || '');
          status = (status || '').toString().toLowerCase().trim();
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
          if (!(/finaliz|encerrad|fechad|conclu|retorn/.test(status))) return;

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

  function _bindTankTypeLock(){
    try {
      var selects = [document.getElementById('sup-tipo-tanque'), document.getElementById('edit-tipo-tanque')].filter(function(x){ return !!x; });
      if (!selects || !selects.length) return;

      try {
        if (!document.getElementById('rdo-ncomp-lock-styles')) {
          var st = document.createElement('style'); st.id = 'rdo-ncomp-lock-styles';
          st.type = 'text/css';
          st.appendChild(document.createTextNode('\n.rdo-ncomp-locked { opacity: 1; }\n.rdo-ncomp-locked input[disabled] { background:#f5f5f5; color:#888; }\n.rdo-ncomp-lock-icon { margin-left:8px; font-size:14px; opacity:0.95; vertical-align: middle; }\n'));
          document.head.appendChild(st);
        }
      } catch(_){ }

      function _lockFieldById(inputId, labelFor, title){
        try {
          var inp = document.getElementById(inputId);
          if (!inp) return;
          var field = inp.closest && inp.closest('.form-field');
          try { inp.dataset._prevVal = (typeof inp.value !== 'undefined' ? String(inp.value) : ''); } catch(_){ }
          if (inputId.indexOf('n-comp') !== -1) try { inp.value = '1'; } catch(_){ }
          inp.disabled = true;
          if (field) field.classList.add('rdo-ncomp-locked');
          if (field) {
            var lbl = field.querySelector('label[for="' + (labelFor || inputId) + '"]');
            if (lbl && !field.querySelector('.rdo-ncomp-lock-icon')) {
              var span = document.createElement('span'); span.className = 'rdo-ncomp-lock-icon material-icons'; span.title = (title || 'Campo bloqueado'); span.setAttribute('aria-hidden','true'); span.textContent = 'lock';
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
      selects.forEach(function(sel){
        try {
          if (sel.__tankLockBound) return;
          var prefix = (sel.id === 'edit-tipo-tanque') ? 'edit' : 'sup';
          var toLock = [prefix + '-gavetas', prefix + '-patamar'];

          function handler(){
            try {
              var v = (sel.value || '').toString().toLowerCase().trim();
              var ncompId = prefix + '-n-comp';
              var ncompEl = document.getElementById(ncompId);
              if (v === 'salão' || v === 'salao') {
                try { _lockFieldById(ncompId, ncompId, 'Número de compartimentos fixo para Salão'); } catch(_){ }
                try { toLock.forEach(function(id){ _lockFieldById(id, id, 'Campo bloqueado para tipo Salão'); }); } catch(_){ }
                try {
                  if (ncompEl) {
                    try { ncompEl.value = '1'; } catch(_){ }
                    try { ncompEl.setAttribute('value', '1'); } catch(_){ }
                    try { var ev = new Event('input', { bubbles: true }); ncompEl.dispatchEvent(ev); } catch(_){ }
                  }
                } catch(_){ }
                try {
                  setTimeout(function(){
                    try {
                      var container = document.getElementById('' + prefix + '-comp-selector') || document.getElementById('sup-comp-selector') || document.querySelector('#sup-comp-selector');
                      var pill = container && container.querySelector('.sup-comp-pill');
                      if (pill && pill.getAttribute('aria-pressed') !== 'true') {
                        try { pill.click(); } catch(_){pill.setAttribute('aria-pressed','true'); }
                      }
                      try {
                        var formEl = document.getElementById(prefix === 'sup' ? 'form-supervisor' : 'form-editor') || document.querySelector('form');
                        if (formEl) {
                          function ensureHidden(name, val){
                            var existing = formEl.querySelector('input[name="' + name + '"]');
                            if (existing) { existing.value = String(val); }
                            else { var i = document.createElement('input'); i.type = 'hidden'; i.name = name; i.value = String(val); formEl.appendChild(i); }
                          }
                          ensureHidden('compartimento_avanco_mecanizada_1', 100);
                          ensureHidden('compartimento_avanco_fina_1', 0);
                          ensureHidden('compartimento_avanco_1', 100);
                          try { if (typeof computeAndSetTopLevelSummaries === 'function') computeAndSetTopLevelSummaries(formEl); } catch(_){ }
                        }
                      } catch(_){ }
                    } catch(_){ }
                  }, 40);
                } catch(_){ }
              } else {
                toLock.forEach(function(id){ _unlockFieldById(id); });
                _unlockFieldById(ncompId);
              }
            } catch(e){ console.warn('tank handler failed', e); }
          }

          sel.addEventListener('change', handler);
          handler();
          sel.__tankLockBound = true;
        } catch(_){ }
      });
    } catch(e){ console.warn('_bindTankTypeLock failed', e); }
  }
  onReady(_bindTankTypeLock);

  function _bindEcFieldsToggle(){
    try {
      var sel = document.getElementById('sup-espaco-conf');
      if (!sel) return;
      if (sel.__ecToggleBound) return;
      try {
        if (!document.getElementById('rdo-ec-lock-styles')) {
          var st = document.createElement('style'); st.id = 'rdo-ec-lock-styles';
          st.type = 'text/css';
          st.appendChild(document.createTextNode('\n.rdo-ec-locked { opacity: 1; }\n.rdo-ec-locked input[disabled], .rdo-ec-locked button[disabled], .rdo-ec-locked select[disabled], .rdo-ec-locked textarea[disabled] { background:#f5f5f5; color:#888; }\n.rdo-ec-locked .sup-tank-quick-list, .rdo-ec-locked .sup-tank-quick-list * { pointer-events: none; }\n.rdo-ec-locked .sup-comp-selector, .rdo-ec-locked .sup-comp-selector * { pointer-events: none; }\n.rdo-ec-lock-icon { margin-left:8px; font-size:14px; opacity:0.95; vertical-align: middle; }\n.supv-ec-card.dimmed { opacity: 0.6; pointer-events: none; }\n'));
          document.head.appendChild(st);
        }
      } catch(_){ }
      var ecGrid = document.getElementById('ec-times-grid');
      var sec = document.getElementById('supv-sec-espaco-confinado');
      var sectionWrapper = document.getElementById('sec-tanque');
      var sectionOper = document.getElementById('sec-operacionais');
      var accumulatedIds = ['sup-ensac-acu','sup-ica-acu','sup-camba-acu','sup-res-liq-acu','sup-res-sol-acu','sup-limp-acu','sup-limp-fina-acu'];

      function _keepEnabled(el){
        try {
          if (!el) return false;
          if (el.id === 'sup-espaco-conf') return true;
          if (el.id === 'sup-metodo') return true;
          if (el.id === 'sup-servico' || el.id === 'sup-servico-input') return true;
          if (el.closest && el.closest('.dropdown-select[data-source="servicos"]')) return true;
        } catch(_){}
        return false;
      }

      function _rememberState(el){
        try {
          if (!el || !el.dataset || el.dataset.rdoEcRemembered === '1') return;
          el.dataset.rdoEcRemembered = '1';
          el.dataset.rdoEcPrevDisabled = el.disabled ? '1' : '0';
          if (typeof el.readOnly !== 'undefined') el.dataset.rdoEcPrevReadonly = el.readOnly ? '1' : '0';
          if (el.type === 'checkbox' || el.type === 'radio') {
            el.dataset.rdoEcPrevChecked = el.checked ? '1' : '0';
          } else if (typeof el.value !== 'undefined') {
            el.dataset.rdoEcPrevValue = String(el.value || '');
          }
          if (el.getAttribute && el.getAttribute('type')) el.dataset.rdoEcPrevType = el.getAttribute('type');
        } catch(_){}
      }

      function _restoreState(el){
        try {
          if (!el || !el.dataset || el.dataset.rdoEcRemembered !== '1') return;
          if (el.dataset.rdoEcPrevType && el.getAttribute && el.getAttribute('type') !== el.dataset.rdoEcPrevType) {
            try { el.type = el.dataset.rdoEcPrevType; } catch(_){ }
          }
          el.disabled = (el.dataset.rdoEcPrevDisabled === '1');
          if (typeof el.readOnly !== 'undefined') el.readOnly = (el.dataset.rdoEcPrevReadonly === '1');
          if (el.type === 'checkbox' || el.type === 'radio') {
            el.checked = (el.dataset.rdoEcPrevChecked === '1');
          } else if (typeof el.value !== 'undefined' && typeof el.dataset.rdoEcPrevValue !== 'undefined') {
            el.value = el.dataset.rdoEcPrevValue;
          }
          try {
            delete el.dataset.rdoEcRemembered;
            delete el.dataset.rdoEcPrevDisabled;
            delete el.dataset.rdoEcPrevReadonly;
            delete el.dataset.rdoEcPrevChecked;
            delete el.dataset.rdoEcPrevValue;
            delete el.dataset.rdoEcPrevType;
          } catch(_){}
        } catch(_){}
      }

      function _lockContainer(container, isLocked){
        try {
          if (!container) return;
          var controls = container.querySelectorAll('input, select, textarea, button');
          Array.prototype.forEach.call(controls, function(el){
            try {
              if (!el) return;
              if (el.type === 'hidden') return;
              if (_keepEnabled(el)) return;
              if (isLocked) {
                _rememberState(el);
                el.disabled = true;
                try {
                  var ff = el.closest && el.closest('.form-field');
                  if (ff) {
                    var lbl = ff.querySelector('label');
                    if (lbl && !lbl.querySelector('[data-rdo-ec-lock-icon="1"]')) {
                      var icon = document.createElement('span');
                      icon.className = 'auto-lock-icon material-icons';
                      icon.setAttribute('data-rdo-ec-lock-icon', '1');
                      icon.setAttribute('title', 'Campo bloqueado');
                      icon.setAttribute('aria-hidden', 'true');
                      icon.textContent = 'lock';
                      lbl.appendChild(icon);
                    }
                  }
                } catch(_){}
              } else {
                _restoreState(el);
                try {
                  var ff2 = el.closest && el.closest('.form-field');
                  if (ff2) {
                    var toRemove = ff2.querySelectorAll('[data-rdo-ec-lock-icon="1"]');
                    Array.prototype.forEach.call(toRemove, function(n){ try { n.parentNode && n.parentNode.removeChild(n); } catch(_){} });
                  }
                } catch(_){}
              }
            } catch(_){}
          });
          if (isLocked) container.classList.add('rdo-ec-locked');
          else container.classList.remove('rdo-ec-locked');
        } catch(_){}
      }

      function setLocked(isLocked){
        try {
          _lockContainer(sectionWrapper, isLocked);
          _lockContainer(sectionOper, isLocked);
          if (ecGrid) {
            Array.prototype.forEach.call(ecGrid.querySelectorAll('.supv-ec-card'), function(c){ try { if (isLocked) c.classList.add('dimmed'); else c.classList.remove('dimmed'); } catch(_){} });
          }
          try {
            accumulatedIds.forEach(function(id){
              var el = document.getElementById(id);
              if (!el) return;
              if (isLocked) {
                _rememberState(el);
                try { if (el.getAttribute && el.getAttribute('type') && el.getAttribute('type') !== 'text') el.type = 'text'; } catch(_){}
                try { el.value = '-'; } catch(_){}
                try { el.disabled = true; } catch(_){}
              } else {
                _restoreState(el);
              }
            });
          } catch(_){}

          if (sec) {
            var hdr = sec.querySelector('.supv-ec-section-head');
            if (hdr) {
              var key = hdr.querySelector('.rdo-ec-lock-icon');
              if (isLocked && !key) {
                var span = document.createElement('span'); span.className = 'rdo-ec-lock-icon material-icons'; span.title = 'Campos de Espaço Confinado bloqueados'; span.setAttribute('aria-hidden','true'); span.textContent = 'lock';
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
      handler();
      sel.__ecToggleBound = true;
    } catch(e){ console.warn('_bindEcFieldsToggle failed', e); }
  }
  onReady(_bindEcFieldsToggle);
  onReady(function(){ try { computeEditorTambores(); } catch(_){ } try { computeSupervisorTambores(); } catch(_){ } try { computeEditorAccumulates(); } catch(_){ } });

  function _initDynamicEcGrid(){
    try {
      var grid = document.getElementById('ec-times-grid');
      if (!grid) return;
      var addBtn = document.getElementById('btn-supv-add-ec');
      var countEl = document.getElementById('supv-ec-count');
      var max = 6;
      var cards = Array.prototype.slice.call(grid.querySelectorAll('.supv-ec-card'));
      if (!cards.length) return;
      try {
        if (!document.getElementById('rdo-ec-dynamic-styles')){
          var st = document.createElement('style'); st.id = 'rdo-ec-dynamic-styles'; st.type='text/css';
          var css = '\n.supv-ec-card { transition: opacity .22s ease, transform .22s ease; }\n.supv-ec-card.animate-in { opacity: 0; transform: translateY(-6px); }\n.supv-ec-card.animate-in.show { opacity: 1; transform: none; }\n.supv-ec-card.animate-out { opacity: 0; transform: translateY(-8px); }\n.supv-ec-actions .supv-ec-remove-card { margin-left:8px; background:transparent; border:1px solid rgba(0,0,0,0.06); }\n#btn-supv-add-ec { min-width: 120px; }\n';
          st.appendChild(document.createTextNode(css));
          document.head.appendChild(st);
        }
      } catch(_){ }
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

      function updateCount(){
        try {
          var vis = cards.filter(function(c){ return !isHidden(c); }).length || 0;
          if (countEl) countEl.textContent = String(Math.max(1, vis)) + '/' + String(max);
        } catch(_){ }
      }

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

      function showNextCard(){
        try {
          for (var i=0;i<cards.length;i++){
            var c = cards[i];
            if (isHidden(c)){
              c.classList.remove('animate-out');
              c.classList.add('animate-in');
              c.style.display = '';
              try { var first = c.querySelector('input[type=time]'); if (first) { setTimeout(function(){ try { first.focus(); } catch(_){} }, 100); } } catch(_){ }
              updateCount();
              _bindEcCardClear(c);
              _bindEcCardRemove(c);
              setTimeout(function(el){ try { el.classList.remove('animate-in'); } catch(_){} }, 400, c);
              return true;
            }
          }
          return false;
        } catch(e){ return false; }
      }

      function hideLastCard(){
        try {
          var visible = cards.filter(function(c){ return !isHidden(c); });
          if (visible.length <= 1) return false;
          var last = visible[visible.length-1];
          try { var inps = last.querySelectorAll('input[type=time]'); Array.prototype.forEach.call(inps, function(i){ i.value = ''; }); } catch(_){ }
          try { last.classList.add('animate-out'); } catch(_){ last.style.opacity = 0; }
          setTimeout(function(el){ try { el.style.display = 'none'; el.classList.remove('animate-out'); } catch(_){} }, 260, last);
          updateCount();
          return true;
        } catch(e){ return false; }
      }

      function _bindEcCardRemove(card){
        try {
          if (!card) return;
          var btn = card.querySelector('.supv-ec-remove-card');
          if (!btn) return;
          if (btn.__ecRemoveBound) return;
          btn.addEventListener('click', function(ev){ ev.preventDefault(); try {
            card.classList.add('animate-out');
            try { Array.prototype.forEach.call(card.querySelectorAll('input[type=time]'), function(i){ i.value = ''; }); } catch(_){ }
            setTimeout(function(el){ try { el.style.display = 'none'; el.classList.remove('animate-out'); updateCount(); computeModalAggregates(); } catch(_){} }, 260, card);
          } catch(e){ console.warn('remove ec card failed', e); } });
          btn.__ecRemoveBound = true;
        } catch(e){ }
      }

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

  cards.forEach(function(c){ try { _bindEcCardClear(c); _bindEcCardRemove(c); } catch(_){} });

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
              function timeToMinLocal(v){ if (!v) return null; var p = String(v).split(':'); if (p.length<2) return null; var hh=parseInt(p[0],10)||0; var mm=parseInt(p[1],10)||0; if (!isFinite(hh) || !isFinite(mm)) return null; return hh*60+mm; }
              function minutesToHHMMLocal(m){ if (m==null || !isFinite(m)) return '--:--'; var mm = Math.floor(m); var hh = Math.floor(mm/60); var rem = mm%60; return (hh<10?('0'+hh):String(hh))+':'+(rem<10?('0'+rem):String(rem)); }
              var eM = timeToMinLocal(valE); var sM = timeToMinLocal(valS); var d = null; if (eM!=null && sM!=null){ d = sM - eM; if (d<0) d += 24*60; }
              var durationEl = card.querySelector('[data-ec-duration]');
              if (durationEl) {
                durationEl.textContent = 'Tempo total: ' + (d!=null ? minutesToHHMMLocal(d) : '--:--');
              }
              try { computeModalAggregates(); } catch(_){ }
            } catch(_){ }
          };
          if (ent && !ent.__ecTimeListener) { ent.addEventListener('input', handler); ent.addEventListener('change', handler); ent.__ecTimeListener = true; }
          if (sai && !sai.__ecTimeListener) { sai.addEventListener('input', handler); sai.addEventListener('change', handler); sai.__ecTimeListener = true; }
          try { handler(); } catch(_){ }
          card.__ecTimeBound = true;
        } catch(_){ }
      }

      cards.forEach(function(c){ try { _bindEcCardTimes(c); } catch(_){} });

      if (addBtn && !addBtn.__supvEcBound) {
        addBtn.addEventListener('click', function(ev){ ev.preventDefault(); try {
          var vis = cards.filter(function(c){ return c.style.display !== 'none' && c.style.display !== 'hidden'; }).length || 0;
          if (vis >= max) { showToast('Máximo de ' + max + ' equipes atingido', 'info'); return; }
          if (!showNextCard()) showToast('Nenhum cartão adicional disponível', 'error');
        } catch(e){ console.warn('supv add ec failed', e); } });
        addBtn.__supvEcBound = true;
      }

      if (countEl && !countEl.__supvCountBound){
        countEl.addEventListener('click', function(ev){ try { ev.preventDefault(); hideLastCard(); } catch(_){ } });
        countEl.__supvCountBound = true;
      }

      grid.addEventListener('input', function(ev){ try { if (ev.target && (ev.target.name === 'entrada_confinado[]' || ev.target.name === 'saida_confinado[]')) computeModalAggregates(); } catch(_){} }, { passive: true });

      try { if (isMobileViewport()) collapseInitial(); else { cards.forEach(function(c){ c.style.display=''; }); updateCount(); } } catch(_){ collapseInitial(); }
    } catch(e){ console.warn('_initDynamicEcGrid failed', e); }
  }

  onReady(_initDynamicEcGrid);

  function computeModalAggregates(){
    try {
      var wrap = document.getElementById('atividades-wrapper') || document.getElementById('edit-atividades-wrapper') || document.querySelector('.activities-wrapper');
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
        'conferencia do material e equipamento no conteiner':1,'conferência do material e equipamento no contêiner':1,
        'desobstrução de linhas':1,'desobstrucao de linhas':1,
        'drenagem do tanque':1,
        'acesso ao tanque':1,
        'instalação / preparação / montagem':1,'instalacao / preparacao / montagem':1,'instalação/preparação/montagem':1,'instalacao/preparacao/montagem':1,'instalação':1,'preparação':1,'montagem':1,'setup':1,
        'mobilização dentro do tanque':1,'mobilizacao dentro do tanque':1,
        'mobilização fora do tanque':1,'mobilizacao fora do tanque':1,
        'desmobilização dentro do tanque':1,'desmobilizacao dentro do tanque':1,
        'desmobilização fora do tanque':1,'desmobilizacao fora do tanque':1,
        'avaliação inicial da área de trabalho':1,'avaliacao inicial da area de trabalho':1,
        'teste tubo a tubo':1,'teste tubo-a-tubo':1,
        'teste hidrostatico':1,'teste hidrostático':1,
        'limpeza mecânica':1,'limpeza mecanica':1,
        'limpeza bebedouro':1,'limpeza caixa d\'água':1,'limpeza caixa dagua':1,'limpeza caixa d\'agua':1,
        'operação com robô':1,'operacao com robo':1,'operacao com robô':1,'operação com robo':1,
        'coleta e análise de ar':1,'coleta e analise de ar':1,'coleta de ar':1,
        'limpeza de dutos':1,
        'coleta de água':1,'coleta de agua':1
      };

      function _normalizeLabel(s){ try { return (s||'').toString().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim(); } catch(e){ try { return (s||'').toString().toLowerCase().trim(); } catch(_) { return ''; } } }

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
          var rawAt = (sel && sel.value) ? String(sel.value) : '';
          var atRawLower = rawAt ? rawAt.toLowerCase().trim() : '';
          var at = _normalizeLabel(rawAt);
          // contar tanto 'abertura pt' quanto variações de renovação (ex: 'renovação de pt', 'renovacao pt/pet')
          if (at === 'abertura pt' || (at.indexOf('renov') !== -1 && at.indexOf('pt') !== -1)) total_abertura_pt += dur;
          if (efetivas[at] || efetivas[atRawLower]) total_efetivas += dur;
        } catch(_){ }
      });
      var total_confinado = 0;
      var ecGrid = document.getElementById('edit-ec-times-grid') || document.getElementById('ec-times-grid') || document.querySelector('.confined-times-grid');
      if (ecGrid) {
        var ent = qsa('input[name="entrada_confinado[]"]', ecGrid) || [];
        var sai = qsa('input[name="saida_confinado[]"]', ecGrid) || [];
        var n = Math.max(ent.length, sai.length);
        function minutesToHHMM(m){ if (m == null || !isFinite(m)) return '--:--'; var mm = Math.floor(m); var hh = Math.floor(mm/60); var rem = mm % 60; return (hh<10?('0'+hh):String(hh))+':'+(rem<10?('0'+rem):String(rem)); }
        for (var i=0;i<n;i++){
          var e = ent[i] ? timeToMin(ent[i].value) : null;
          var s = sai[i] ? timeToMin(sai[i].value) : null;
          var d = null;
          if (e != null && s != null){ d = s - e; if (d < 0) d += 24*60; total_confinado += d; }
          try {
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
      var nEf = 0;
      var nEfEl = document.getElementById('edit-total-n-efetivo-confinado') || document.getElementById('sup-total-n-efetivo-confinado') || document.getElementById('total-n-efetivo-confinado');
      if (nEfEl && nEfEl.value) { var tn = parseInt(nEfEl.value,10); if (isFinite(tn)) nEf = tn; }

      var total_nao_efetivas_fora = total_atividade - total_efetivas - nEf;
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

  function computeEditorBombeio(){
    try {
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
          var computed = Math.round((val * vazaoLocal) * 100) / 100;
          bombeioInput.value = computed;
          resLiqInput.value = computed;
          try { resLiqInput.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
        } catch(e){ console.warn('computeEditorBombeio compute failed', e); }
      }
      if (!tempoInput.__computeEditorBound) { tempoInput.addEventListener('input', computeAndFill); tempoInput.__computeEditorBound = true; }
      var vazEl = document.getElementById('edit-vazao-bombeio');
      if (vazEl && !vazEl.__computeEditorBound) { vazEl.addEventListener('input', computeAndFill); vazEl.__computeEditorBound = true; }
      try { setTimeout(computeAndFill, 30); } catch(e){}
    } catch(e){ console.warn('computeEditorBombeio failed', e); }
  }

  function computeEditorResTotal(){
    try {
      if (computeEditorResTotal.__bound) {
        var rlEl2 = document.getElementById('edit-res-liq');
        var rsEl2 = document.getElementById('edit-res-sol');
        var out2 = document.getElementById('edit-res-total');
        if (!out2) return null;
        var rlRaw2 = (rlEl2 && rlEl2.value != null) ? String(rlEl2.value).trim() : '';
        var rsRaw2 = (rsEl2 && rsEl2.value != null) ? String(rsEl2.value).trim() : '';
        if (!rlRaw2 && !rsRaw2) { out2.value = ''; return null; }
        var rl = parseFloat(String(rlRaw2).replace(',', '.'));
        var rs = parseFloat(String(rsRaw2).replace(',', '.'));
        rl = isFinite(rl) ? rl : 0;
        rs = isFinite(rs) ? rs : 0;
        var total = Math.round((rl + rs) * 100) / 100;
        out2.value = total;
        return total;
      }

      var resLiqEl = document.getElementById('edit-res-liq');
      var resSolEl = document.getElementById('edit-res-sol');
      var resTotalEl = document.getElementById('edit-res-total');
      if (!resLiqEl || !resSolEl || !resTotalEl) return null;

      function computeAndFill(){
        try {
          var rlRaw = resLiqEl.value != null ? String(resLiqEl.value).trim() : '';
          var rsRaw = resSolEl.value != null ? String(resSolEl.value).trim() : '';
          if (!rlRaw && !rsRaw) { resTotalEl.value = ''; return null; }
          var rl = parseFloat(String(rlRaw).replace(',', '.'));
          var rs = parseFloat(String(rsRaw).replace(',', '.'));
          rl = isFinite(rl) ? rl : 0;
          rs = isFinite(rs) ? rs : 0;
          var total = Math.round((rl + rs) * 100) / 100;
          resTotalEl.value = total;
          return total;
        } catch(e){}
      }
      try { if (!resLiqEl.__computeEditorResBound) { resLiqEl.addEventListener('input', computeAndFill); resLiqEl.__computeEditorResBound = true; } } catch(e){}
      try { if (!resSolEl.__computeEditorResBound) { resSolEl.addEventListener('input', computeAndFill); resSolEl.__computeEditorResBound = true; } } catch(e){}
      try { computeAndFill(); } catch(e){}
      computeEditorResTotal.__bound = true;
      return computeAndFill();
    } catch(e){ console.warn('computeEditorResTotal failed', e); return null; }
  }

  function computeEditorResSolidos(){
    try {
      if (computeEditorResSolidos.__bound) {
        var ensEl2 = document.getElementById('edit-ensac');
        var out2 = document.getElementById('edit-res-sol');
        if (!ensEl2 || !out2) return null;
        var raw2 = (ensEl2.value == null ? '' : String(ensEl2.value)).trim();
        if (!raw2) {
          out2.value = '';
          try { out2.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
          return null;
        }
        var ens = parseFloat(String(raw2).replace(',', '.'));
        if (!isFinite(ens)) {
          out2.value = '';
          try { out2.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
          return null;
        }
        var rs = Math.round((ens * 0.008) * 100) / 100;
        out2.value = rs;
        try { out2.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
        return rs;
      }

      var ensEl = document.getElementById('edit-ensac');
      var resSolEl = document.getElementById('edit-res-sol');
      if (!ensEl || !resSolEl) return null;

      function computeAndFill(){
        try {
          var raw = (ensEl.value == null ? '' : String(ensEl.value)).trim();
          if (!raw) {
            resSolEl.value = '';
            try { resSolEl.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
            return null;
          }
          var ens = parseFloat(String(raw).replace(',', '.'));
          if (!isFinite(ens)) {
            resSolEl.value = '';
            try { resSolEl.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
            return null;
          }
          var rs = Math.round((ens * 0.008) * 100) / 100;
          resSolEl.value = rs;
          try { resSolEl.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
          return rs;
        } catch(e){}
      }

      try { if (!ensEl.__computeEditorResSolBound) { ensEl.addEventListener('input', computeAndFill); ensEl.__computeEditorResSolBound = true; } } catch(e){}
      try { computeAndFill(); } catch(e){}
      computeEditorResSolidos.__bound = true;
      return computeAndFill();
    } catch(e){ console.warn('computeEditorResSolidos failed', e); return null; }
  }

  function computeEditorAccumulates(){
    try {
      var root = document.getElementById('form-editor') || document.getElementById('rdo-edit-content') || document;
      if (!root) return;

      function isBlank(v){ return v == null || String(v).trim() === ''; }
      function toInt(v){
        if (isBlank(v)) return null;
        var s = String(v).replace(/[^0-9\-]/g, '');
        if (!s) return null;
        var n = parseInt(s, 10);
        return isFinite(n) ? n : null;
      }
      function toFloat(v){
        if (isBlank(v)) return null;
        var s = String(v).trim();
        s = s.replace(/\./g, '').replace(/,/g, '.');
        s = s.replace(/[^0-9.\-]/g, '');
        if (!s) return null;
        var n = parseFloat(s);
        return isFinite(n) ? n : null;
      }
      function round2(n){ return Math.round(n * 100) / 100; }
      function findFirst(selectors){
        for (var i = 0; i < selectors.length; i++) {
          var el = root.querySelector(selectors[i]);
          if (el) return el;
        }
        return null;
      }

      var pairs = [
        {
          day: ['#edit-ensac', 'input[name="ensacamento_dia"]'],
          cum: ['#ensacamento_cumulativo', '#edit-ensacamento_cumulativo', 'input[name="ensacamento_cumulativo"]'],
          type: 'int'
        },
        {
          day: ['#icamento', '#edit-ica', 'input[name="icamento_dia"]'],
          cum: ['#icamento_cumulativo', '#edit-icamento_cumulativo', 'input[name="icamento_cumulativo"]'],
          type: 'int'
        },
        {
          day: ['#cambagem', '#edit-camba', 'input[name="cambagem_dia"]'],
          cum: ['#cambagem_cumulativo', '#edit-cambagem_cumulativo', 'input[name="cambagem_cumulativo"]'],
          type: 'int'
        },
        {
          day: ['#edit-res-liq', 'input[name="total_liquido"]', 'input[name="residuo_liquido"]'],
          cum: ['#total_liquido_acu', 'input[name="total_liquido_acu"]', 'input[name="total_liquido_cumulativo"]'],
          type: 'float'
        },
        {
          day: ['#edit-res-sol', 'input[name="residuos_solidos"]'],
          cum: ['#residuos_solidos_acu', 'input[name="residuos_solidos_acu"]', 'input[name="residuos_solidos_cumulativo"]'],
          type: 'float'
        }
      ];

      function bindPair(dayEl, cumEl, type){
        if (!dayEl || !cumEl) return;
        var parseVal = (type === 'float') ? toFloat : toInt;
        function getDay(){ return parseVal(dayEl.value); }
        function getCum(){ return parseVal(cumEl.value); }
        function formatVal(n){
          if (n == null || !isFinite(n)) return '';
          if (type === 'float') return String(round2(n));
          return String(Math.round(n));
        }
        function initState(){
          var c = getCum();
          var d = getDay();
          cumEl.__accumCur = (c == null ? 0 : c);
          dayEl.__accumLast = (d == null ? 0 : d);
        }
        function recompute(){
          var newDay = getDay();
          if (newDay == null) newDay = 0;
          if (dayEl.__accumLast == null || !isFinite(dayEl.__accumLast)) dayEl.__accumLast = 0;
          if (cumEl.__accumCur == null || !isFinite(cumEl.__accumCur)) {
            var cNow = getCum();
            cumEl.__accumCur = (cNow == null ? 0 : cNow);
          }
          var delta = newDay - dayEl.__accumLast;
          var next = cumEl.__accumCur + delta;
          cumEl.__accumCur = next;
          dayEl.__accumLast = newDay;
          cumEl.value = formatVal(next);
          try { if (typeof computeEditorPercentuais === 'function') computeEditorPercentuais(); } catch(_){ }
        }
        if (!dayEl.__editorAccBound) { initState(); dayEl.addEventListener('input', recompute); dayEl.__editorAccBound = true; }
        if (!cumEl.__editorAccBaseBound) {
          cumEl.addEventListener('input', function(){
            var c = getCum();
            var d = getDay();
            if (c == null) { cumEl.__accumCur = null; return; }
            cumEl.__accumCur = c;
            if (d == null) d = 0;
            dayEl.__accumLast = d;
          });
          cumEl.__editorAccBaseBound = true;
        }
        recompute();
      }

      pairs.forEach(function(p){
        var dayEl = findFirst(p.day);
        var cumEl = findFirst(p.cum);
        bindPair(dayEl, cumEl, p.type);
      });
    } catch(e){ console.warn('computeEditorAccumulates failed', e); }
  }

  function computeEditorPercentuais(){
    try{
      function isBlank(val){ return (val == null) || (String(val).trim() === ''); }
      function toNumberOrNull(val){
        if (isBlank(val)) return null;
        if (typeof val === 'number') return (isFinite(val) && !isNaN(val)) ? val : null;
        var s = String(val).trim().replace(',', '.');
        var f = parseFloat(s);
        return (isFinite(f) && !isNaN(f)) ? f : null;
      }

      var get = function(id){ var el = document.getElementById(id); return el ? el.value : null; };
      var ensac_cum = toNumberOrNull(get('ensacamento_cumulativo') || get('edit-ensacamento_cumulativo'));
      var ensac_prev = toNumberOrNull(get('ensacamento_previsao') || get('edit-ensacamento_previsao'));
      var perc_ensac = null;
      if (ensac_prev != null && ensac_prev > 0 && ensac_cum != null) perc_ensac = (ensac_cum / ensac_prev) * 100;

      var ic_cum = toNumberOrNull(get('icamento_cumulativo') || get('edit-icamento_cumulativo'));
      var ic_prev = toNumberOrNull(get('icamento_previsao') || get('edit-icamento_previsao'));
      var perc_ic = null;
      if (ic_prev != null && ic_prev > 0 && ic_cum != null) perc_ic = (ic_cum / ic_prev) * 100;

      var camb_cum = toNumberOrNull(get('cambagem_cumulativo') || get('edit-cambagem_cumulativo'));
      var camb_prev = toNumberOrNull(get('cambagem_previsao') || get('edit-cambagem_previsao'));
      var perc_camb = null;
      if (camb_prev != null && camb_prev > 0 && camb_cum != null) perc_camb = (camb_cum / camb_prev) * 100;

      var perc_limpeza = toNumberOrNull(get('percentual_limpeza') || get('edit-percentual_limpeza'));
      var perc_limpeza_fina = toNumberOrNull(get('percentual_limpeza_fina') || get('edit-percentual_limpeza_fina'));

      function clampOpt(v){ if (v == null) return null; if (!isFinite(v) || isNaN(v)) return null; return Math.max(0, Math.min(100, v)); }
      perc_ensac = clampOpt(perc_ensac);
      perc_ic = clampOpt(perc_ic);
      perc_camb = clampOpt(perc_camb);
      perc_limpeza = clampOpt(perc_limpeza);
      perc_limpeza_fina = clampOpt(perc_limpeza_fina);

      var setVal = function(id, v, decimals){
        var el = document.getElementById(id); if (!el) return;
        try{
          if (el.dataset && el.dataset.source === 'rdotanque') return;
        }catch(_){ }
        if (v == null) { el.value = ''; return; }
        if (decimals != null) el.value = Number(v).toFixed(decimals); else el.value = String(Math.round(v));
      };
      setVal('percentual_ensacamento', perc_ensac, 2);
      setVal('edit-percentual_ensacamento', perc_ensac, 2);
      setVal('percentual_icamento', perc_ic, 2);
      setVal('edit-percentual_icamento', perc_ic, 2);
      setVal('percentual_cambagem', perc_camb, 2);
      setVal('edit-percentual_cambagem', perc_camb, 2);

      var pesos = {
        'percentual_limpeza': 70.0,
        'percentual_ensacamento': 7.0,
        'percentual_icamento': 7.0,
        'percentual_cambagem': 5.0,
        'percentual_limpeza_fina': 6.0
      };
      var weightedSum = 0, weightTotal = 0;
      var hasAnyComponent = false;
      Object.keys(pesos).forEach(function(k){
        var w = pesos[k];
        var val = toNumberOrNull(get(k) || get('edit-' + k));
        if (k === 'percentual_ensacamento') val = perc_ensac;
        if (k === 'percentual_icamento') val = perc_ic;
        if (k === 'percentual_cambagem') val = perc_camb;
        if (val != null) hasAnyComponent = true;
        if (!isFinite(val) || isNaN(val) || val == null) val = 0;
        weightedSum += val * w;
        weightTotal += w;
      });

      var percentual_avanco = null;
      if (hasAnyComponent && weightTotal > 0) percentual_avanco = weightedSum / weightTotal;
      percentual_avanco = clampOpt(percentual_avanco);
      setVal('percentual_avanco', percentual_avanco, null);
      setVal('edit-percentual_avanco', percentual_avanco, null);
      try {
        var supAv = document.getElementById('sup-limp');
        if (supAv) supAv.value = (percentual_avanco == null ? '' : String(Math.round(percentual_avanco)) + '%');
        var supFina = document.getElementById('sup-limp-fina');
        if (supFina) supFina.value = (perc_limpeza_fina == null ? '' : String(Math.round(perc_limpeza_fina)) + '%');
        var perc_limpeza_acu = toNumberOrNull(get('percentual_limpeza_cumulativo') || get('edit-percentual_limpeza_cumulativo'));
        var perc_limpeza_fina_acu = toNumberOrNull(get('percentual_limpeza_fina_cumulativo') || get('edit-percentual_limpeza_fina_cumulativo'));
        var supAcu = document.getElementById('sup-limp-acu'); if (supAcu) supAcu.value = (perc_limpeza_acu == null ? '' : String(Math.round(perc_limpeza_acu)) + '%');
        var supFinaAcu = document.getElementById('sup-limp-fina-acu'); if (supFinaAcu) supFinaAcu.value = (perc_limpeza_fina_acu == null ? '' : String(Math.round(perc_limpeza_fina_acu)) + '%');
      } catch(_){ }
    }catch(e){ try{ console.warn('computeEditorPercentuais error', e); }catch(_){ } }
  }

  async function submitSupervisorForm(ev){
    if (ev && ev.preventDefault) ev.preventDefault();
    var form = qs('#form-supervisor');
    if (!form) return;
    if (form.__rdoCoreSubmitting) { try { console.warn('submitSupervisorForm already running — skipping duplicate call'); } catch(_){}; return; }

  form.__rdoCoreSubmitting = true;
  var hid = document.getElementById('sup-rdo-id');
    var isEdit = !!(hid && hid.value);
    var url = isEdit ? '/rdo/update_ajax/' : '/rdo/create_ajax/';
  try{ if (typeof computeAndSetTopLevelSummaries === 'function') computeAndSetTopLevelSummaries(form); } catch(_){ }
  var payload = buildSupervisorFormData(form);
  try {
    if (payload && typeof payload.entries === 'function' && typeof payload.delete === 'function') {
      var _entries = [];
      try {
        var it = payload.entries();
        var _n = it.next();
        while (!_n.done) { _entries.push(_n.value); _n = it.next(); }
      } catch(e) {
        try { payload.forEach(function(v,k){ _entries.push([k,v]); }); } catch(_) { _entries = []; }
      }

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

      var newFd = new FormData();
      _entries.forEach(function(p){
        var k = p[0], v = p[1];
        if (k === 'atividade_nome[]' || k === 'atividade_inicio[]' || k === 'atividade_fim[]' || k === 'atividade_comentario_pt[]' || k === 'atividade_comentario_en[]') return;
        if (k === 'equipe_pessoa_id[]' || k === 'equipe_nome[]' || k === 'equipe_funcao[]' || k === 'equipe_em_servico[]') return;
        newFd.append(k, v);
      });
      dedupA.forEach(function(r){ newFd.append('atividade_nome[]', r[0]); newFd.append('atividade_inicio[]', r[1]); newFd.append('atividade_fim[]', r[2]); newFd.append('atividade_comentario_pt[]', r[3]); newFd.append('atividade_comentario_en[]', r[4]); });
      dedupE.forEach(function(r){ newFd.append('equipe_pessoa_id[]', r[0]); newFd.append('equipe_nome[]', r[1]); newFd.append('equipe_funcao[]', r[2]); newFd.append('equipe_em_servico[]', r[3]); });
      try { newFd.set('pob', String(dedupE.length)); } catch(_){ try { newFd.append('pob', String(dedupE.length)); } catch(__){ } }
      try { newFd.append('__rdo_client_normalized', '1'); } catch(_){ }
      payload = newFd;
    }
  } catch(e) { console.warn('RDO: normalization failed', e); }
    if (isEdit) payload.append('rdo_id', hid.value);
    var tankFieldNames = [
      'tanque_id','tank_id','tanqueId','tanque_id_text',
      'tanque_codigo','tanque_nome','nome_tanque','tipo_tanque',
      'numero_compartimento','numero_compartimentos','gavetas','patamar','patamares','volume_tanque_exec',
      'servico_exec','metodo_exec','espaco_confinado','operadores_simultaneos',
      'h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','sentido_limpeza','tempo_bomba',
      'ensacamento_prev','icamento_prev','cambagem_prev',
      'ensacamento_dia','icamento_dia','cambagem_dia','tambores_dia',
      'residuos_solidos','residuos_totais','bombeio','total_liquido',
      'ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo',
      'ensacamento_acu','icamento_acu','cambagem_acu',
      'total_liquido_cumulativo','residuos_solidos_cumulativo','total_liquido_acu','residuos_solidos_acu',
      'avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json',
      'limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa',
      'limpeza_acu','limpeza_fina_acu',
      'percentual_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_fina_diario',
      'percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo',
      'percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco'
    ];
    function _collectTankValues(scope, payloadLike){
      try {
        var out = Object.create(null);
        tankFieldNames.forEach(function(n){
          try {
            var el = scope.querySelector('[name="'+n+'"]');
            out[n] = el ? (el.value || '') : '';
          } catch(_){ out[n] = ''; }
        });
        if (payloadLike && typeof payloadLike.get === 'function') {
          tankFieldNames.forEach(function(n){
            try {
              var pv = payloadLike.get(n);
              if (pv == null) return;
              if (typeof Blob !== 'undefined' && pv instanceof Blob) return;
              var ps = String(pv);
              if (ps.trim() !== '') out[n] = ps;
            } catch(_){ }
          });
        }
        try {
          if ((!out.numero_compartimentos || String(out.numero_compartimentos).trim() === '') && out.numero_compartimento) out.numero_compartimentos = out.numero_compartimento;
          if ((!out.ensacamento_cumulativo || String(out.ensacamento_cumulativo).trim() === '') && out.ensacamento_acu) out.ensacamento_cumulativo = out.ensacamento_acu;
          if ((!out.icamento_cumulativo || String(out.icamento_cumulativo).trim() === '') && out.icamento_acu) out.icamento_cumulativo = out.icamento_acu;
          if ((!out.cambagem_cumulativo || String(out.cambagem_cumulativo).trim() === '') && out.cambagem_acu) out.cambagem_cumulativo = out.cambagem_acu;
          if ((!out.total_liquido_cumulativo || String(out.total_liquido_cumulativo).trim() === '') && out.total_liquido_acu) out.total_liquido_cumulativo = out.total_liquido_acu;
          if ((!out.residuos_solidos_cumulativo || String(out.residuos_solidos_cumulativo).trim() === '') && out.residuos_solidos_acu) out.residuos_solidos_cumulativo = out.residuos_solidos_acu;
        } catch(_){ }
        return out;
      } catch(_) { return {}; }
    }
    function _hasTankContent(tv){
      try {
        if (!tv) return false;
        function _hasAny(keys){
          for (var i=0;i<keys.length;i++){
            var k = keys[i];
            var v = tv[k];
            if (v != null && String(v).trim() !== '') return true;
          }
          return false;
        }
        var anchorKeys = [
          'tanque_id','tank_id','tanqueId','tanque_id_text',
          'tanque_codigo','tanque_nome','nome_tanque','tipo_tanque',
          'numero_compartimento','numero_compartimentos','volume_tanque_exec',
          'servico_exec','metodo_exec'
        ];
        if (_hasAny(anchorKeys)) return true;
        var metricKeys = [
          'gavetas','patamar','patamares','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado',
          'sentido_limpeza','tempo_bomba',
          'ensacamento_prev','icamento_prev','cambagem_prev',
          'ensacamento_dia','icamento_dia','cambagem_dia','tambores_dia',
          'residuos_solidos','residuos_totais','bombeio','total_liquido',
          'ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo',
          'ensacamento_acu','icamento_acu','cambagem_acu',
          'total_liquido_cumulativo','residuos_solidos_cumulativo','total_liquido_acu','residuos_solidos_acu',
          'avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json',
          'limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa',
          'limpeza_acu','limpeza_fina_acu',
          'percentual_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_fina_diario',
          'percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo',
          'percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco'
        ];
        return _hasAny(metricKeys);
      } catch(_){ return false; }
    }
    async function _addTankForRdo(rdoId, tv){
      try {
        if (!rdoId) return { success:false, error:'RDO inválido' };
        try { console.debug('DEBUG _addTankForRdo tv object:', tv); } catch(_){ }
        var fd = new FormData();
        Object.keys(tv||{}).forEach(function(k){ try { if (typeof tv[k] !== 'undefined') fd.append(k, tv[k]); } catch(_){ } });
        fd.append('rdo_id', String(rdoId));
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
        try { console.debug('DEBUG _addTankForRdo response:', { ok: resp.ok, status: resp.status, data: data, url: urlAdd }); } catch(_){ }
        // Fallback: some deployments expose non-/api/ endpoint or CSRF rules differ.
        if (resp && resp.status === 403) {
          try { console.warn('DEBUG _addTankForRdo received 403, retrying fallback /rdo/<id>/add_tank/'); } catch(_){ }
          try {
            var altUrl = '/rdo/' + encodeURIComponent(rdoId) + '/add_tank/';
            var resp2 = await fetch(altUrl, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf } });
            var data2 = null; try { data2 = await resp2.json(); } catch(_){ data2 = null; }
            try { console.debug('DEBUG _addTankForRdo fallback response:', { ok: resp2.ok, status: resp2.status, data: data2, url: altUrl }); } catch(_){ }
            // if fallback succeeded, use its result
            if (resp2 && resp2.ok && data2 && data2.success) {
              var flag = form.querySelector('input[name="rdo_has_tanks"]');
              if (!flag) { flag = document.createElement('input'); flag.type = 'hidden'; flag.name = 'rdo_has_tanks'; form.appendChild(flag); }
              flag.value = '1';
              if (form.classList) form.classList.add('has-tank-additions');
              return { success:true, data:data2 };
            }
            // otherwise, fall through to return error below
            resp = resp2; data = data2;
          } catch(e) { try { console.warn('DEBUG _addTankForRdo fallback failed', e); } catch(_){ } }
        }
        if (resp.ok && data && data.success) {
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
    var tankValues = _collectTankValues(form, payload);
    var shouldAddFinalTank = _hasTankContent(tankValues);
    try {
      try { if (typeof payload.delete === 'function') { payload.delete('entrada_confinado[]'); payload.delete('entrada_confinado'); payload.delete('saida_confinado[]'); payload.delete('saida_confinado'); } } catch(_){ }
      var entInputs = form.querySelectorAll('input[name="entrada_confinado[]"], input[name="entrada_confinado"]') || [];
      Array.prototype.forEach.call(entInputs, function(e){ try { payload.append('entrada_confinado[]', (e && e.value) ? e.value : ''); } catch(_){} });
      var saiInputs = form.querySelectorAll('input[name="saida_confinado[]"], input[name="saida_confinado"]') || [];
      Array.prototype.forEach.call(saiInputs, function(s){ try { payload.append('saida_confinado[]', (s && s.value) ? s.value : ''); } catch(_){} });
      try {
        for (var idx = 0; idx < 6; idx++) {
          var entVal = (entInputs[idx] && entInputs[idx].value) ? entInputs[idx].value : '';
          var saiVal = (saiInputs[idx] && saiInputs[idx].value) ? saiInputs[idx].value : '';
          payload.append('entrada_confinado_' + (idx+1), entVal);
          payload.append('saida_confinado_' + (idx+1), saiVal);
        }
      } catch(_){ }
    } catch(e){ try { console.warn('ensure EC fields append failed', e); } catch(_){} }
    try {
      var hasTankAdds = false;
      try { var flagEl = document.getElementById('sup-has-tank-additions'); hasTankAdds = !!(flagEl && String(flagEl.value||'') === '1'); } catch(_){ }
      if (!hasTankAdds) { try { var flag2 = (form && form.querySelector) ? form.querySelector('input[name="rdo_has_tanks"]') : null; hasTankAdds = !!(flag2 && String(flag2.value||'') === '1'); } catch(_){ } }
      if (!hasTankAdds) { try { hasTankAdds = !!(form && form.classList && form.classList.contains('has-tank-additions')); } catch(_){ hasTankAdds = false; } }
      if (isEdit && hasTankAdds && payload && typeof payload.delete === 'function') {
        var tankNamesToDrop = [
          'tanque_codigo','tanque_nome','nome_tanque','tipo_tanque',
          'numero_compartimento','numero_compartimentos',
          'gavetas','patamar','patamares','volume_tanque_exec',
          'servico_exec','metodo_exec','operadores_simultaneos',
          'h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','tempo_bomba',
          'ensacamento_dia','icamento_dia','cambagem_dia','ensacamento_prev','icamento_prev','cambagem_prev','ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo','tambores_dia','residuos_solidos','residuos_totais',
          'bombeio','total_liquido',
          'avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json',
          'limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa',
          'limpeza_manual_diaria_tanque','limpeza_manual_cumulativa_tanque','limpeza_fina_cumulativa_tanque',
          'percentual_limpeza_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo','percentual_limpeza_fina','limpeza_acu','limpeza_fina_acu','percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco'
        ];
        try { tankNamesToDrop.forEach(function(k){ try { payload.delete(k); } catch(_){ } }); } catch(_){ }
      }
    } catch(_){ }
    try {
      if (payload && typeof payload.entries === 'function'){
        var dbgEntries = [];
        for (var pair of payload.entries()){
          if (pair[1] && typeof pair[1] === 'object' && pair[1].name) dbgEntries.push(pair[0] + '=' + pair[1].name + '(' + pair[1].size + 'B)');
          else dbgEntries.push(pair[0] + '=' + String(pair[1]));
        }
        try { console.debug('DEBUG submitSupervisorForm FormData entries:', dbgEntries); } catch(_){ }
      } else {
        try { console.debug('DEBUG submitSupervisorForm payload (non-FormData):', payload); } catch(_){ }
      }
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
    if (btn) { btn.disabled = true; btn.textContent = 'Salvando...'; }
    var didSucceed = false;
    var controller = new AbortController();
    var requestTimeout = getRequestTimeoutMs(payload);
    var t = setTimeout(function(){ try{ controller.abort(); }catch(_){} }, requestTimeout);
    var hasPhotoUpload = countFormDataFiles(payload) > 0;
    var lastUploadPct = -1;
    var tankSaveWarning = '';
    function onPhotoUploadProgress(ev){
      try {
        if (!hasPhotoUpload) return;
        if (ev && ev.lengthComputable && ev.total > 0) {
          var pct = Math.max(0, Math.min(99, Math.round((ev.loaded / ev.total) * 100)));
          if (pct !== lastUploadPct) {
            lastUploadPct = pct;
            showUploadProgress('Enviando fotos...', pct);
          }
        } else {
          showUploadProgress('Enviando fotos...', null);
        }
      } catch(_){}
    }
    try {
      if (hasPhotoUpload) showUploadProgress('Enviando fotos...', 0);
      if (isEdit) {
        var rdoIdEdit = hid && hid.value ? String(hid.value) : '';
        if (rdoIdEdit && shouldAddFinalTank) {
          var addRes = await _addTankForRdo(rdoIdEdit, tankValues);
          if (!addRes.success) { throw new Error(addRes.error || 'Falha ao adicionar tanque'); }
        }
        var respUpObj = await requestJsonWithProgress({
          url: url,
          method: 'POST',
          body: payload,
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': (getCSRF(form) || _getCookie('csrftoken') || '') },
          signal: controller.signal,
          onUploadProgress: hasPhotoUpload ? onPhotoUploadProgress : null
        });
        var dataUp = respUpObj ? respUpObj.data : null;
        if (hasPhotoUpload) showUploadProgress('Upload 100% concluído. Finalizando...', 100);
        if (respUpObj && respUpObj.ok && dataUp && dataUp.success) {
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
        var respCrObj = await requestJsonWithProgress({
          url: url,
          method: 'POST',
          body: payload,
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': (getCSRF(form) || _getCookie('csrftoken') || '') },
          signal: controller.signal,
          onUploadProgress: hasPhotoUpload ? onPhotoUploadProgress : null
        });
        var dataCr = respCrObj ? respCrObj.data : null;
        if (hasPhotoUpload) showUploadProgress('Upload 100% concluído. Finalizando...', 100);
        if (!(respCrObj && respCrObj.ok && dataCr && dataCr.success)) {
          var msgCr = (dataCr && (dataCr.error || dataCr.message)) || 'Falha ao salvar RDO';
          throw new Error(msgCr);
        }
        var newId = dataCr.id || (dataCr.rdo && (dataCr.rdo.id || dataCr.rdo.pk)) || '';
        if (shouldAddFinalTank && newId) {
          var addRes2 = await _addTankForRdo(String(newId), tankValues);
          if (!addRes2.success) {
            try { console.warn('add_tank failed after create (non-fatal):', addRes2); } catch(_){ }
            tankSaveWarning = 'RDO criado, mas falhou ao salvar os dados do tanque. Abra o RDO e toque em Salvar novamente.';
            // Non-fatal: continue RDO creation even if tank addition failed (permission/403 may occur).
          }
        }
        didSucceed = true;
        if (tankSaveWarning) showToast(tankSaveWarning, 'warning');
        else showToast(dataCr.message || 'RDO criado', 'success');
        try { document.dispatchEvent(new CustomEvent('rdo:saved', { detail: { mode: 'create', response: dataCr } })); } catch(_){ }
        try { closeModal(); } catch(_){ }
        try {
          setTimeout(function(){
            try {
              var q = new URLSearchParams(window.location.search || '');
              q.set('page', '1');
              window.location.href = window.location.pathname + (q.toString() ? '?' + q.toString() : '');
            } catch(_){ try { window.location.reload(); } catch(_){} }
          }, 400);
        } catch(_){ try { window.location.reload(); } catch(_){} }
      }
    } catch(err){
      showToast(err && err.name === 'AbortError' ? 'Tempo de requisição expirou' : (err && err.message ? err.message : 'Erro ao salvar'), 'error');
      try { document.dispatchEvent(new CustomEvent('rdo:save:error', { detail: { mode: isEdit ? 'update' : 'create', error: String(err && err.message ? err.message : err) } })); } catch(_){ }
    } finally {
      hideUploadProgress(0);
      clearTimeout(t);
      if (btn) {
        if (!didSucceed) {
          btn.disabled = false;
          if (orig != null) try { btn.textContent = orig; } catch(_){ }
        } else {
          try { btn.textContent = 'Salvo'; } catch(_){ }
        }
      }
      try { form.__rdoCoreSubmitting = false; } catch(_) {}
    }
  }
  async function saveSupervisorCreateReturnId(form){
    if (!form) form = qs('#form-supervisor');
    var payload = buildSupervisorFormData(form);

    try { if (typeof payload.delete === 'function') { payload.delete('entrada_confinado[]'); payload.delete('entrada_confinado'); payload.delete('saida_confinado[]'); payload.delete('saida_confinado'); } } catch(_){ }
    try { var entInputs = form.querySelectorAll('input[name="entrada_confinado[]"], input[name="entrada_confinado"]') || []; Array.prototype.forEach.call(entInputs, function(e){ try { payload.append('entrada_confinado[]', (e && e.value) ? e.value : ''); } catch(_){} }); } catch(_){ }
    try { var saiInputs = form.querySelectorAll('input[name="saida_confinado[]"], input[name="saida_confinado"]') || []; Array.prototype.forEach.call(saiInputs, function(s){ try { payload.append('saida_confinado[]', (s && s.value) ? s.value : ''); } catch(_){} }); } catch(_){ }

    var btn = qs('button[type="submit"]', form);
    var orig = btn ? btn.textContent : null;
    if (btn) { btn.disabled = true; try { btn.textContent = 'Salvando...'; } catch(_){} }
    var controller = new AbortController();
    var requestTimeout = getRequestTimeoutMs(payload);
    var t = setTimeout(function(){ try{ controller.abort(); }catch(_){} }, requestTimeout);
    var hasPhotoUpload = countFormDataFiles(payload) > 0;
    var lastUploadPct = -1;
    try {
      if (hasPhotoUpload) showUploadProgress('Enviando fotos...', 0);
      var respObj = await requestJsonWithProgress({
        url: '/rdo/create_ajax/',
        method: 'POST',
        body: payload,
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': (getCSRF(form) || _getCookie('csrftoken') || '') },
        signal: controller.signal,
        onUploadProgress: hasPhotoUpload ? function(ev){
          try {
            if (ev && ev.lengthComputable && ev.total > 0) {
              var pct = Math.max(0, Math.min(99, Math.round((ev.loaded / ev.total) * 100)));
              if (pct !== lastUploadPct) {
                lastUploadPct = pct;
                showUploadProgress('Enviando fotos...', pct);
              }
            } else {
              showUploadProgress('Enviando fotos...', null);
            }
          } catch(_){}
        } : null
      });
      var data = respObj ? respObj.data : null;
      if (hasPhotoUpload) showUploadProgress('Upload 100% concluído. Finalizando...', 100);
      if (respObj && respObj.ok && data && data.success) {
        return { success: true, id: data.id || (data.rdo && data.rdo.id), rdo: data.rdo || data.rdo };
      }
      return { success: false, error: (data && (data.error || data.message)) || 'Falha ao criar RDO' };
    } catch(err){ return { success: false, error: String(err) }; }
    finally {
      hideUploadProgress(0);
      clearTimeout(t);
      if (btn) { if (orig != null) try { btn.textContent = orig; } catch(_){} btn.disabled = false; }
    }
  }
  function lockNonTankFields(){
    try {
  var form = qs('#form-supervisor'); if (!form) return;
    var _preserveNames = ['ensacamento_prev','icamento_prev','cambagem_prev'];
  var _preserved = {};
  try { _preserveNames.forEach(function(n){ var el = form.querySelector('[name="'+n+'"]'); _preserved[n] = el ? (el.value || '') : ''; }); } catch(_){ }
  var tankFields = new Set([
  'tanque_codigo','tanque_nome','nome_tanque','tanque_nome','tipo_tanque','numero_compartimento','numero_compartimentos',
  'gavetas','patamar','patamares','volume_tanque_exec','servico_exec','metodo_exec','espaco_confinado','operadores_simultaneos',
  'h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','tempo_bomba','ensacamento_dia','icamento_dia','cambagem_dia',
  'ensacamento_prev','icamento_prev','cambagem_prev','tambores_dia','residuos_solidos','residuos_totais','bombeio','total_liquido','sentido_limpeza',
  'total_liquido_acu','residuos_solidos_acu',
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
            if (el.closest && el.closest('.form-field')) el.closest('.form-field').classList.remove('rdo-auto-locked');
            return;
          }
          if (el.name === 'csrfmiddlewaretoken' || el.id === 'sup-rdo-id') return;
          if (el.tagName && (el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'select' || el.tagName.toLowerCase() === 'textarea' || el.tagName.toLowerCase() === 'button')) {
            try { el.disabled = true; el.classList.add('rdo-locked-after-save'); } catch(_){ }
          }
        } catch(_){ }
      });
      try { var fInputs = form.querySelectorAll('input[type=file]'); Array.prototype.forEach.call(fInputs, function(fi){ try { fi.disabled = true; fi.classList.add('rdo-locked-after-save'); } catch(_){} }); } catch(_){ }
      try { var overlay = document.getElementById('supv-modal-overlay'); if (overlay) overlay.classList.add('rdo-saved-first'); } catch(_){ }
    } catch(e){ console.warn('lockNonTankFields failed', e); }
  }
  document.addEventListener('click', async function(ev){
    try {
      var btn = ev.target && ev.target.closest && ev.target.closest('#btn-rdo-add-another, #btn-add-tanque');
      if (!btn) return;
      ev.preventDefault();
      var form = qs('#form-supervisor'); if (!form) return;
      var hid = document.getElementById('sup-rdo-id');
      var rdoId = hid && hid.value ? hid.value : '';
      if (!rdoId) {
        var res = await saveSupervisorCreateReturnId(form);
        if (!res || !res.success || !res.id) {
          showToast((res && res.error) || 'Falha ao criar RDO antes de adicionar tanque', 'error');
          return;
        }
  rdoId = String(res.id);
        try { if (hid) hid.value = rdoId; var supRdo = document.getElementById('sup-rdo'); if (supRdo && res.rdo && res.rdo.rdo) supRdo.value = String(res.rdo.rdo); } catch(_){ }
  try { lockNonTankFields(); } catch(_){ }

        showToast('RDO criado — agora você pode adicionar tanques', 'success');
      }
  var tankNames = ['tanque_codigo','tanque_nome','nome_tanque','tipo_tanque','numero_compartimento','numero_compartimentos','gavetas','patamar','patamares','volume_tanque_exec','servico_exec','metodo_exec','espaco_confinado','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','tempo_bomba','ensacamento_dia','icamento_dia','cambagem_dia','sentido_limpeza','ensacamento_prev','icamento_prev','cambagem_prev','ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo','tambores_dia','residuos_solidos','residuos_totais','bombeio','total_liquido','total_liquido_acu','residuos_solidos_acu','avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json','limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa','limpeza_manual_diaria_tanque','limpeza_manual_cumulativa_tanque','limpeza_fina_cumulativa_tanque','percentual_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_fina_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo','percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco','limpeza_acu','limpeza_fina_acu'];
      var fd = new FormData();
      fd.append('rdo_id', rdoId);
      tankNames.forEach(function(n){ try { var el = form.querySelector('[name="' + n + '"]'); if (!el) return; if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return; fd.append(n, el.value); } catch(_){ } });
      try {
        var supL = form.querySelector('#sup-limp') || form.querySelector('input[name="percentual_limpeza_diario"]');
        if (supL && (supL.value || supL.value === '0')) fd.append('percentual_limpeza_diario', supL.value);
        var supLF = form.querySelector('#sup-limp-fina') || form.querySelector('input[name="avanco_limpeza_fina"], input[name="percentual_limpeza_fina_diario"]');
        if (supLF && (supLF.value || supLF.value === '0')) fd.append('avanco_limpeza_fina', supLF.value);
        var supLA = form.querySelector('#sup-limp-acu') || form.querySelector('input[name="percentual_limpeza_cumulativo"], input[name="limpeza_acu"]');
        if (supLA && (supLA.value || supLA.value === '0')) { fd.append('percentual_limpeza_cumulativo', supLA.value); fd.append('limpeza_acu', supLA.value); }
        var supLFA = form.querySelector('#sup-limp-fina-acu') || form.querySelector('input[name="percentual_limpeza_fina_cumulativo"], input[name="limpeza_fina_acu"]');
        if (supLFA && (supLFA.value || supLFA.value === '0')) { fd.append('percentual_limpeza_fina_cumulativo', supLFA.value); fd.append('limpeza_fina_acu', supLFA.value); }
        var sentido = form.querySelector('[name="sentido_limpeza"]');
        if (sentido && (typeof sentido.value !== 'undefined')) fd.append('sentido_limpeza', sentido.value || '');
        var compSelectors = form.querySelectorAll('input[name^="compartimento_avanco"], input[name^="compartimentos_avanco"]');
        Array.prototype.forEach.call(compSelectors, function(ci){ try { if (ci && ci.name) fd.append(ci.name, ci.value); } catch(_){ } });
      } catch(_){}
      var url = '/api/rdo/' + encodeURIComponent(rdoId) + '/add_tank/';
      var csrf = getCSRF(form) || _getCookie('csrftoken') || '';
      try { btn.disabled = true; btn.textContent = 'Adicionando...'; } catch(_){ }
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
        try {
          var flag = form.querySelector('input[name="rdo_has_tanks"]');
          if (!flag) { flag = document.createElement('input'); flag.type = 'hidden'; flag.name = 'rdo_has_tanks'; form.appendChild(flag); }
          flag.value = '1';
        } catch(_){ }
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
          try {
            if (firstField) {
              if (typeof firstField.scrollIntoView === 'function') {
                try { firstField.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch(_){ try { firstField.scrollIntoView(); } catch(_){} }
              }
              setTimeout(function(){ try { firstField.focus(); if (typeof firstField.select === 'function') try { firstField.select(); } catch(_){} } catch(_){} }, 120);
            }
          } catch(_){ }
            try {
              tankNames.forEach(function(n){
                try {
                  var el2 = form.querySelector('[name="' + n + '"]');
                  if (!el2) return;
                  try { el2.disabled = false; el2.classList.remove && el2.classList.remove('rdo-locked-after-save'); } catch(_){}
                  try { var p = el2.closest && el2.closest('.form-field'); if (p && p.classList) { p.classList.remove('rdo-locked-after-save'); p.classList.remove('rdo-auto-locked'); } } catch(_){}
                } catch(_){}
              });
            } catch(_){}
        } catch(_){ }
        try { if (typeof _appendSavedTankSummary === 'function') _appendSavedTankSummary(data.tank); } catch(_){ }
      } else {
        showToast((data && (data.error || data.message)) || 'Falha ao adicionar tanque', 'error');
      }
      try { btn.disabled = false; btn.textContent = 'Salvar e adicionar outro tanque'; } catch(_){ }
    } catch(e){ console.warn('add-another handler failed', e); showToast('Erro ao adicionar tanque', 'error'); }
  }, false);

  // Atualiza linha/ cartão do RDO quando um tanque é associado (se API retornar dados mínimos do RDO)
  try {
    document.addEventListener('rdo:tank:associated', function(ev){
      try{
        var detail = (ev && ev.detail) || {};
        var payload = detail.rdo || detail.rdo_payload || detail.rdo_obj || (detail.raw && detail.raw.rdo) || null;

        // alguns endpoints retornam também `tank`; usar como fallback
        var tankObj = detail.tank || detail.tanque || detail.tanque_obj || (detail.raw && (detail.raw.tank || detail.raw.tanque)) || null;

        // permitir seguir mesmo que `payload` (rdo) venha nulo
        if (!payload || typeof payload !== 'object') payload = {};
        var rdoId = '';
        try { rdoId = String(payload.id || payload.rdo_id || detail.rdo_id || detail.rdoId || ''); } catch(_){ rdoId = ''; }
        if (!rdoId) return;

        function _pick(obj, keys){
          try{
            if (!obj) return undefined;
            for (var i=0;i<keys.length;i++){
              var k = keys[i];
              if (typeof obj[k] !== 'undefined' && obj[k] !== null) {
                var s = String(obj[k]);
                if (s.trim() !== '') return obj[k];
              }
            }
          }catch(_){ }
          return undefined;
        }

        // valores efetivos (prioriza rdo; cai para tank quando rdo vier vazio)
        var effTankCodigo = _pick(payload, ['tanque_codigo']) || _pick(tankObj, ['tanque_codigo', 'codigo', 'identificacao']);
        var effTankNome = _pick(payload, ['nome_tanque']) || _pick(tankObj, ['nome_tanque', 'tanque_nome', 'nome', 'tanque']);
        var effTipoTanque = _pick(payload, ['tipo_tanque']) || _pick(tankObj, ['tipo_tanque', 'tipo']);
        var effNComp = (typeof payload.numero_compartimentos !== 'undefined' ? payload.numero_compartimentos : _pick(tankObj, ['numero_compartimentos', 'numero_compartimento']));
        var effGavetas = (typeof payload.gavetas !== 'undefined' ? payload.gavetas : _pick(tankObj, ['gavetas']));
        var effPatamares = (typeof payload.patamares !== 'undefined' ? payload.patamares : _pick(tankObj, ['patamares', 'patamar']));
        var effVolume = (typeof payload.volume_tanque_exec !== 'undefined' ? payload.volume_tanque_exec : _pick(tankObj, ['volume_tanque_exec', 'volume_tanque', 'volume']));

        function _txt(v){
          try{
            if (v == null) return '-';
            var s = String(v);
            if (!s || !s.trim()) return '-';
            return s;
          }catch(_){ return '-'; }
        }

        function _normHeader(s){
          try{ return String(s||'').replace(/\s+/g,' ').trim().toUpperCase(); }catch(_){ return ''; }
        }

        function _updateRowCellsByHeader(trEl){
          try{
            if (!trEl) return;
            var table = trEl.closest && trEl.closest('table');
            if (!table) return;
            var ths = table.querySelectorAll('thead th');
            if (!ths || !ths.length) return;
            var idx = {};
            for (var i=0;i<ths.length;i++){
              var key = _normHeader(ths[i] && ths[i].textContent);
              if (!key) continue;
              idx[key] = i;
            }
            var tds = trEl.querySelectorAll('td');
            if (!tds || !tds.length) return;
            function setCol(headerName, value){
              try{
                var k = _normHeader(headerName);
                var pos = (typeof idx[k] !== 'undefined') ? idx[k] : -1;
                if (pos < 0 || !tds[pos]) return;
                tds[pos].textContent = _txt(value);
              }catch(_){ }
            }
            setCol('TANQUE', effTankCodigo);
            setCol('NOME DO TANQUE', effTankNome);
            setCol('TIPO DE TANQUE', effTipoTanque);
            // opcional: manter coerência do restante caso o backend devolva
            if (typeof effNComp !== 'undefined') setCol('Nº COMPARTIMENTOS', effNComp);
            if (typeof effGavetas !== 'undefined') setCol('GAVETAS', effGavetas);
            if (typeof effPatamares !== 'undefined') setCol('PATAMARES', effPatamares);
            if (typeof effVolume !== 'undefined') setCol('VOLUME DO TANQUE', effVolume);
            if (typeof payload.servico_exec !== 'undefined') setCol('SERVIÇO', payload.servico_exec);
            if (typeof payload.metodo_exec !== 'undefined') setCol('MÉTODO', payload.metodo_exec);
          }catch(_){ }
        }

        // atualizar atributos/data-attrs da linha da tabela
        try{
          var tr = document.querySelector('tr[data-rdo-id="' + rdoId + '"]');
          if (tr){
            try{ tr.setAttribute('data-tanque-codigo', (effTankCodigo || payload.tanque_codigo || '') ); }catch(_){ }
            // o template usa data-tanque-nome (não data-nome-tanque)
            try{ tr.setAttribute('data-tanque-nome', (effTankNome || payload.nome_tanque || '') ); }catch(_){ }
            try{ tr.setAttribute('data-tipo-tanque', (effTipoTanque || payload.tipo_tanque || '') ); }catch(_){ }
            try{ if (typeof effVolume !== 'undefined') tr.setAttribute('data-volume', effVolume || ''); }catch(_){ }
            try{ tr.setAttribute('data-tanque', (effTankNome || effTankCodigo || payload.nome_tanque || payload.tanque_codigo || '') || ''); }catch(_){ }

            // Atualiza as células corretas (a tabela não tem classes nas colunas)
            _updateRowCellsByHeader(tr);
          }
        }catch(_){ }

        // atualizar cartões mobile se existirem
        try{
          var card = document.querySelector('.rdo-mobile-card[data-rdo-id="' + rdoId + '"]') || document.querySelector('.rdo-mobile-item[data-rdo-id="' + rdoId + '"]');
          if (card){
            try{ var lbl = card.querySelector('.rdo-tanque-label'); if (lbl) lbl.textContent = (effTankCodigo ? (String(effTankCodigo) + ' — ') : '') + (effTankNome || ''); }catch(_){ }
          }
        }catch(_){ }

        // Atualiza também o modal editor (campos do formulário) imediatamente
        try{
          var editRdoIdEl = document.getElementById('edit-rdo-id');
          var isSameEditor = !!(editRdoIdEl && String(editRdoIdEl.value || '').trim() === String(rdoId));
          if (isSameEditor){
            function _pick(obj, keys){
              try{
                if (!obj) return undefined;
                for (var i=0;i<keys.length;i++){
                  var k = keys[i];
                  if (typeof obj[k] !== 'undefined' && obj[k] !== null && String(obj[k]).trim() !== '') return obj[k];
                }
              }catch(_){ }
              return undefined;
            }
            function _setVal(id, v){
              try{
                var el = document.getElementById(id);
                if (!el) return;
                if (typeof v === 'undefined' || v === null) return;
                el.value = String(v);
                try{ el.dispatchEvent(new Event('change', { bubbles: true })); }catch(_){ }
                try{ el.dispatchEvent(new Event('input', { bubbles: true })); }catch(_){ }
              }catch(_){ }
            }
            function _setSelect(id, v){
              try{
                var el = document.getElementById(id);
                if (!el) return;
                if (typeof v === 'undefined' || v === null) return;
                var s = String(v);
                var has = false;
                try{ Array.prototype.forEach.call(el.options || [], function(o){ if (String(o.value) === s) has = true; }); }catch(_){ }
                if (has) el.value = s;
                else if (s) el.value = s; // deixa tentar setar mesmo sem option (não quebra)
                try{ el.dispatchEvent(new Event('change', { bubbles: true })); }catch(_){ }
              }catch(_){ }
            }

            var tanqueId = _pick(tankObj, ['id','tanque_id','tank_id']);
            var tanqueCodigo = _pick(payload, ['tanque_codigo']) || _pick(tankObj, ['tanque_codigo','codigo','identificacao']);
            var tanqueNome = _pick(payload, ['nome_tanque']) || _pick(tankObj, ['nome_tanque','tanque_nome','nome','tanque']);
            var tipoTanque = _pick(payload, ['tipo_tanque']) || _pick(tankObj, ['tipo_tanque','tipo']);
            var nComp = _pick(payload, ['numero_compartimentos']) || _pick(tankObj, ['numero_compartimentos','numero_compartimento']);
            var gav = _pick(payload, ['gavetas']) || _pick(tankObj, ['gavetas']);
            var pat = _pick(payload, ['patamares']) || _pick(tankObj, ['patamares','patamar']);
            var vol = _pick(payload, ['volume_tanque_exec']) || _pick(tankObj, ['volume_tanque_exec','volume_tanque','volume']);

            if (typeof tanqueId !== 'undefined') _setVal('edit-tanque-id', tanqueId);
            if (typeof tanqueCodigo !== 'undefined') _setVal('edit-tanque-cod', tanqueCodigo);
            if (typeof tanqueNome !== 'undefined') _setVal('edit-tanque-nome', tanqueNome);
            if (typeof tipoTanque !== 'undefined') _setSelect('edit-tipo-tanque', tipoTanque);
            if (typeof nComp !== 'undefined') _setVal('edit-n-comp', nComp);
            if (typeof gav !== 'undefined') _setVal('edit-gavetas', gav);
            if (typeof pat !== 'undefined') _setVal('edit-patamar', pat);
            if (typeof vol !== 'undefined') _setVal('edit-volume', vol);
          }
        }catch(_){ }

        // Se a API informou a OS (ordem_servico_id), remover linhas duplicadas sem tanque
        try{
          var osId = payload.ordem_servico_id || payload.os_id || detail.os_id || detail.ordem_servico_id || null;
          // Remover RDOs explicitamente deletados pelo servidor
          try{
            var deleted = detail.deleted_rdos || detail.deleted_rdo_ids || detail.deleted || null;
            if (Array.isArray(deleted) && deleted.length){
              deleted.forEach(function(did){
                try{ var rtr = document.querySelector('tr[data-rdo-id="' + String(did) + '"]'); if (rtr && rtr.parentNode) rtr.parentNode.removeChild(rtr); }catch(_){ }
                try{ var cardr = document.querySelector('.rdo-mobile-card[data-rdo-id="' + String(did) + '"]') || document.querySelector('.rdo-mobile-item[data-rdo-id="' + String(did) + '"]'); if (cardr && cardr.parentNode) cardr.parentNode.removeChild(cardr); }catch(_){ }
              });
            }
          }catch(_){ }
          if (osId) {
            var rows = Array.prototype.slice.call(document.querySelectorAll('tr[data-os-id="' + String(osId) + '"]')) || [];
            if (rows.length > 1) {
              var rowsWithTank = rows.filter(function(r){
                try{
                  var codeAttr = (r.getAttribute('data-tanque-codigo') || '').toString().trim();
                  if (codeAttr) return true;
                  // fallback: tentar ler a coluna "TANQUE" pelo header (se existir)
                  try{
                    var table = r.closest && r.closest('table');
                    if (table){
                      var ths = table.querySelectorAll('thead th');
                      var tds = r.querySelectorAll('td');
                      if (ths && tds && ths.length && tds.length){
                        var pos = -1;
                        for (var i=0;i<ths.length;i++){ if (_normHeader(ths[i] && ths[i].textContent) === 'TANQUE'){ pos = i; break; } }
                        if (pos >= 0 && tds[pos] && (tds[pos].textContent||'').toString().trim() && (tds[pos].textContent||'').toString().trim() !== '-') return true;
                      }
                    }
                  }catch(_){ }
                }catch(_){ }
                return false;
              });
              var rowsWithoutTank = rows.filter(function(r){ return rowsWithTank.indexOf(r) === -1; });
              if (rowsWithTank.length >= 1 && rowsWithoutTank.length >= 1) {
                rowsWithoutTank.forEach(function(r){ try{ if (r && r.parentNode) r.parentNode.removeChild(r); }catch(_){ } });
              }
            }
          }
        }catch(_){ }
      }catch(e){ console.warn('rdo:tank:associated handler failed', e); }
    }, false);
  }catch(_){ }

  async function submitEditorForm(ev){
    if (ev && ev.preventDefault) ev.preventDefault();
    var form = qs('#form-editor');
    if (!form) return;

    var hid = document.getElementById('edit-rdo-id');
    var isEdit = !!(hid && hid.value);
    var url = isEdit ? '/rdo/update_ajax/' : '/rdo/create_ajax/';

    var payload = null;
    try {
      if (window.buildSupervisorFormDataExternal && typeof window.buildSupervisorFormDataExternal === 'function') payload = window.buildSupervisorFormDataExternal(form);
    } catch(e){ payload = null; }
    if (!payload) {
      try { payload = buildSupervisorFormData(form); } catch(e){ payload = new FormData(form); }
    }
    if (isEdit) payload.append('rdo_id', hid.value);

    // garantir que os campos EC (entrada/saida) também sejam enviados no editor
    try {
      try { if (typeof payload.delete === 'function') { payload.delete('entrada_confinado[]'); payload.delete('entrada_confinado'); payload.delete('saida_confinado[]'); payload.delete('saida_confinado'); } } catch(_){ }
      var entInputsEd = form.querySelectorAll('input[name="entrada_confinado[]"], input[name="entrada_confinado"]') || [];
      Array.prototype.forEach.call(entInputsEd, function(e){ try { payload.append('entrada_confinado[]', (e && e.value) ? e.value : ''); } catch(_){} });
      var saiInputsEd = form.querySelectorAll('input[name="saida_confinado[]"], input[name="saida_confinado"]') || [];
      Array.prototype.forEach.call(saiInputsEd, function(s){ try { payload.append('saida_confinado[]', (s && s.value) ? s.value : ''); } catch(_){} });
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
    var requestTimeout = getRequestTimeoutMs(payload);
    var t = setTimeout(function(){ try{ controller.abort(); }catch(_){} }, requestTimeout);
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
      var editTankEl = document.getElementById('edit-tanque-id');
      var tankId = editTankEl && editTankEl.value ? String(editTankEl.value) : '';
      var didTankUpdate = false;
      if (tankId) {
        var tankNames = ['tanque_codigo','tanque_nome','nome_tanque','tipo_tanque','numero_compartimento','numero_compartimentos','gavetas','patamar','patamares','volume_tanque_exec','servico_exec','metodo_exec','espaco_confinado','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','tempo_bomba','ensacamento_dia','icamento_dia','cambagem_dia','sentido_limpeza','ensacamento_prev','icamento_prev','cambagem_prev','ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo','tambores_dia','residuos_solidos','residuos_totais','bombeio','total_liquido','total_liquido_acu','residuos_solidos_acu','avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json','limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa','limpeza_manual_diaria_tanque','limpeza_manual_cumulativa_tanque','limpeza_fina_cumulativa_tanque','percentual_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_fina_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo','percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco','limpeza_acu','limpeza_fina_acu'];
        var fdTank = new FormData();
        tankNames.forEach(function(n){ try { var el = form.querySelector('[name="' + n + '"]'); if (!el) return; if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return; fdTank.append(n, el.value); } catch(_){ } });
        try { var compInputs = form.querySelectorAll('input[name^="compartimento_avanco"], input[name^="compartimentos_avanco"]'); Array.prototype.forEach.call(compInputs, function(ci){ try { if (ci && ci.name) fdTank.append(ci.name, ci.value); } catch(_){} }); } catch(_){ }
        try { if (hid && hid.value) fdTank.append('rdo_id', hid.value); } catch(_){ }
        var csrf = getCSRF(form) || _getCookie('csrftoken') || '';
        var tankUrl = '/api/rdo/tank/' + encodeURIComponent(tankId) + '/update/';
        try { console.debug && console.debug('DEBUG submitEditorForm: updating tank', tankId); } catch(_){ }
        var respTank = await fetch(tankUrl, { method: 'POST', body: fdTank, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf }, signal: controller.signal });
        var dataTank = null; try { dataTank = await respTank.json(); } catch(_){ dataTank = null; }
        if (respTank.ok && dataTank && dataTank.success) {
          didTankUpdate = true;
          showToast(dataTank.message || 'Tanque atualizado', 'success');
          try { document.dispatchEvent(new CustomEvent('rdo:tank:updated', { detail: { tank: dataTank.tank || dataTank } })); } catch(_){ }
        } else {
          var errMsg = (dataTank && (dataTank.error || dataTank.message)) || 'Falha ao atualizar tanque';
          throw new Error(errMsg);
        }
      }
      var shouldSendRdo = true;
      if (didTankUpdate) {
        var tankSet = new Set(['tanque_codigo','tanque_nome','nome_tanque','tipo_tanque','numero_compartimento','numero_compartimentos','gavetas','patamar','patamares','volume_tanque_exec','servico_exec','metodo_exec','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado','tempo_bomba','ensacamento_dia','icamento_dia','cambagem_dia','ensacamento_prev','icamento_prev','cambagem_prev','ensacamento_cumulativo','icamento_cumulativo','cambagem_cumulativo','tambores_dia','residuos_solidos','residuos_totais','bombeio','total_liquido','total_liquido_acu','residuos_solidos_acu','avanco_limpeza','avanco_limpeza_fina','compartimentos_avanco_json','limpeza_mecanizada_diaria','limpeza_mecanizada_cumulativa','limpeza_fina_diaria','limpeza_fina_cumulativa','limpeza_manual_diaria_tanque','limpeza_manual_cumulativa_tanque','limpeza_fina_cumulativa_tanque','percentual_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_fina_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo','percentual_ensacamento','percentual_icamento','percentual_cambagem','percentual_avanco','limpeza_acu','limpeza_fina_acu']);
        var rdoPayload = new FormData();
        if (payload && typeof payload.entries === 'function'){
          try {
            for (var pair of payload.entries()){
              try {
                var k = pair[0]; var v = pair[1];
                if (tankSet.has(k)) continue;
                rdoPayload.append(k, v);
              } catch(_){ }
            }
          } catch(e){
            rdoPayload = null;
          }
        }
        if (!rdoPayload) shouldSendRdo = false;
        else {
          var meaningful = false;
          try {
            if (typeof rdoPayload.entries === 'function'){
              for (var p of rdoPayload.entries()){
                if (p && p[0] && String(p[0]) !== 'csrfmiddlewaretoken') { meaningful = true; break; }
              }
            }
          } catch(_){ meaningful = true; }
          shouldSendRdo = meaningful;
          payload = rdoPayload;
        }
      }

      if (shouldSendRdo) {
        var hasPhotoUpload = countFormDataFiles(payload) > 0;
        var lastUploadPct = -1;
        if (hasPhotoUpload) showUploadProgress('Enviando fotos...', 0);
        var respObj = await requestJsonWithProgress({
          url: url,
          method: 'POST',
          body: payload,
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCSRF(form) || _getCookie('csrftoken') || '' },
          signal: controller.signal,
          onUploadProgress: hasPhotoUpload ? function(ev){
            try {
              if (ev && ev.lengthComputable && ev.total > 0) {
                var pct = Math.max(0, Math.min(99, Math.round((ev.loaded / ev.total) * 100)));
                if (pct !== lastUploadPct) {
                  lastUploadPct = pct;
                  showUploadProgress('Enviando fotos...', pct);
                }
              } else {
                showUploadProgress('Enviando fotos...', null);
              }
            } catch(_){}
          } : null
        });
        var data = respObj ? respObj.data : null;
        if (hasPhotoUpload) showUploadProgress('Upload 100% concluído. Finalizando...', 100);
        if (respObj && respObj.ok && data && data.success) {
          showToast(data.message || (isEdit ? 'RDO atualizado' : 'RDO criado'), 'success');
          try { document.dispatchEvent(new CustomEvent('rdo:saved', { detail: { mode: isEdit ? 'update' : 'create', response: data } })); } catch(_){ }
          try {
            if (isEdit) {
              window.location.reload();
            } else {
              var q = new URLSearchParams(window.location.search || '');
              q.set('page', '1');
              window.location.href = window.location.pathname + (q.toString() ? '?' + q.toString() : '');
            }
          } catch(_){ try { window.location.reload(); } catch(_){} }
        } else {
          var msg = (data && (data.error || data.message)) || 'Falha ao salvar RDO';
          throw new Error(msg);
        }
      } else {
        try {
          if (isEdit) {
            window.location.reload();
          } else {
            var q2 = new URLSearchParams(window.location.search || '');
            q2.set('page', '1');
            window.location.href = window.location.pathname + (q2.toString() ? '?' + q2.toString() : '');
          }
        } catch(_){ try { window.location.reload(); } catch(_){} }
      }
    } catch(err){
      showToast(err && err.name === 'AbortError' ? 'Tempo de requisição expirou' : (err && err.message ? err.message : 'Erro ao salvar'), 'error');
      try { document.dispatchEvent(new CustomEvent('rdo:save:error', { detail: { mode: isEdit ? 'update' : 'create', error: String(err && err.message ? err.message : err) } })); } catch(_){ }
    } finally {
      hideUploadProgress(0);
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
    try { syncPobWithEquipe(form); } catch(_){ }
  }

  function ensureSubmitBound(){
    var form = qs('#form-supervisor');
    if (!form) return;
    if (form.__rdoCoreSubmitBound) return;
    form.addEventListener('submit', submitSupervisorForm);
    try {
      var send = document.getElementById('btn-rdo');
      if (send && !send.__rdoCoreBound) {
        send.addEventListener('click', function(ev){ ev.preventDefault(); try { submitSupervisorForm(); } catch(e){ console.warn('btn-rdo click failed', e); } });
        send.__rdoCoreBound = true;
      }
    } catch(_){ }

    form.__rdoCoreSubmitBound = true;
    try { bindSupervisorActivityControls(); } catch(_){}
    try { bindSupervisorTeamControls(); } catch(_){}
    try { bindSupervisorModalClose(); } catch(_){}
    try { bindAggregateInputListeners(); } catch(_){}
    try { ensureSupervisorComputesBound(); } catch(_){ }
    try { ensureSupervisorTranslationsBound(); } catch(_){ }
    try { syncPobWithEquipe(form); } catch(_){ }
  }
  function bindSupervisorActivityControls(){
    try {
      var wrapper = document.getElementById('atividades-wrapper');
      if (!wrapper) return;
      try { wrapper.setAttribute('data-rdo-local-bindings', '1'); } catch(_){ }
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
          if (rows.length <= 1) {
            // Se houver apenas uma linha, limpar seus campos em vez de bloquear a ação.
            try { var only = rows[0]; if (only) Array.prototype.forEach.call(only.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; }); } catch(_){ }
            computeModalAggregates();
            return;
          }
          var last = rows[rows.length-1]; if (last && last.parentNode) last.parentNode.removeChild(last);
          computeModalAggregates();
        } catch(e){ console.warn('removeLastRow supervisor failed', e); }
      }
      if (addBtn && !addBtn.__supBound) { addBtn.addEventListener('click', function(ev){ ev.preventDefault(); addRow(); }); addBtn.__supBound = true; }
      if (removeLast && !removeLast.__supBound) { removeLast.addEventListener('click', function(ev){ ev.preventDefault(); removeLastRow(); }); removeLast.__supBound = true; }
      if (!wrapper.__supRowBound) {
        wrapper.addEventListener('click', function(ev){
          try {
            var btn = ev.target && ev.target.closest ? ev.target.closest('.btn-remove-atividade') : null;
            if (!btn || !wrapper.contains(btn)) return;
            ev.preventDefault();
            var rows = wrapper.querySelectorAll('.activities-row');
            if (rows.length <= 1) {
              try { var only = rows[0]; if (only) Array.prototype.forEach.call(only.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; }); } catch(_){ }
              computeModalAggregates();
              return;
            }
            var row = btn.closest('.activities-row');
            if (row && row.parentNode) row.parentNode.removeChild(row);
            computeModalAggregates();
          } catch(_){ }
        });
        wrapper.__supRowBound = true;
      }
    } catch(e){ console.warn('bindSupervisorActivityControls failed', e); }
  }
  function bindSupervisorTeamControls(){
    try {
      var wrap = document.getElementById('equipe-wrapper'); if (!wrap) return;
      try { wrap.setAttribute('data-rdo-local-bindings', '1'); } catch(_){ }
      function syncNow(){ try { syncPobAllForms(); } catch(_){ } }
      var add = document.getElementById('btn-add-membro');
      var rem = document.getElementById('btn-remove-membro');
      function addMember(){
        try {
          var base = wrap.querySelector('.team-row'); if (!base) return;
          var clone = base.cloneNode(true);
          Array.prototype.forEach.call(clone.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; });
          base.parentNode.insertBefore(clone, wrap.querySelector('.team-footer'));
          syncNow();
        } catch(e){ console.warn('addMember failed', e); }
      }
      function removeMember(){
        try {
          var rows = wrap.querySelectorAll('.team-row'); if (rows.length <= 1) return; var last = rows[rows.length-1]; if (last && last.parentNode) last.parentNode.removeChild(last);
          syncNow();
        } catch(e){ console.warn('removeMember failed', e); }
      }
      if (add && !add.__supBound) { add.addEventListener('click', function(ev){ ev.preventDefault(); addMember(); }); add.__supBound = true; }
      if (rem && !rem.__supBound) { rem.addEventListener('click', function(ev){ ev.preventDefault(); removeMember(); }); rem.__supBound = true; }
      if (!wrap.__pobSyncBound) {
        wrap.addEventListener('input', schedulePobSync, true);
        wrap.addEventListener('change', schedulePobSync, true);
        wrap.__pobSyncBound = true;
      }
      syncNow();
    } catch(e){ console.warn('bindSupervisorTeamControls failed', e); }
  }

  function bindSupervisorModalClose(){
    try {
      var closeBtn = document.querySelectorAll('.supv-modal__close, .supv-modal__cancel');
      Array.prototype.forEach.call(closeBtn, function(b){ if (!b.__supvCloseBound) { b.addEventListener('click', function(ev){ ev.preventDefault(); closeModal(); }); b.__supvCloseBound = true; } });
    } catch(e){ console.warn('bindSupervisorModalClose failed', e); }
  }
  function bindAggregateInputListeners(){
    try {
      var scope = document.getElementById('supv-modal-overlay') || document;
      var selectors = [
        '.atividade-inicio', '.atividade-fim',
        'input[name="entrada_confinado[]"]', 'input[name="saida_confinado[]"]',
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

  function computeSupervisorBombeio(){
    try {
      var tempo = document.getElementById('sup-tempo-bomba');
      var bombeio = document.getElementById('sup-bombeio');
      if (!tempo || !bombeio) return null;
      var val = parseFloat(tempo.value);
      if (!isFinite(val)) return null;
      var vazEl = document.getElementById('sup-vazao-bombeio') || document.getElementById('edit-vazao-bombeio');
      var vaz = vazEl ? parseFloat(vazEl.value) : NaN;
      var vazaoLocal = isFinite(vaz) ? vaz : 36;
      var computed = Math.round((val * vazaoLocal) * 100) / 100;
      bombeio.value = computed;
      try { bombeio.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
      try {
        var resLiqEl = document.getElementById('sup-res-liq');
        var calcHint = document.getElementById('sup-res-liq-calc');
        if (resLiqEl) {
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
      var raw = (ens.value == null ? '' : String(ens.value)).trim();
      if (!raw) {
        resSol.value = '';
        try { resSol.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
        return null;
      }
      var v = parseFloat(raw.replace(',', '.'));
      if (!isFinite(v)) {
        resSol.value = '';
        try { resSol.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
        return null;
      }
      var rs = Math.round((v * 0.008) * 100) / 100;
      resSol.value = rs;
      try { resSol.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
      return rs;
    } catch(e){ console.warn('computeSupervisorResSolidos failed', e); return null; }
  }

  function computeSupervisorResTotal(){
    try {
      var rlEl = document.getElementById('sup-res-liq');
      var rsEl = document.getElementById('sup-res-sol');
      var out = document.getElementById('sup-res-total');
      if (!out) return null;
      var rlRaw = (rlEl && rlEl.value != null) ? String(rlEl.value).trim() : '';
      var rsRaw = (rsEl && rsEl.value != null) ? String(rsEl.value).trim() : '';
      if (!rlRaw && !rsRaw) {
        out.value = '';
        try { out.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
        return null;
      }
      var rl = parseFloat(String(rlRaw).replace(',', '.'));
      var rs = parseFloat(String(rsRaw).replace(',', '.'));
      rl = isFinite(rl) ? rl : 0;
      rs = isFinite(rs) ? rs : 0;
      var total = Math.round((rl + rs) * 100) / 100;
      out.value = total;
      try { out.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
      return total;
    } catch(e){ console.warn('computeSupervisorResTotal failed', e); return null; }
  }

  function ensureSupervisorComputesBound(){
    try {
      if (ensureSupervisorComputesBound.__bound) return;
  var tempo = document.getElementById('sup-tempo-bomba');
  var ens = document.getElementById('sup-ensac');
  var vazEl = document.getElementById('sup-vazao-bombeio') || document.getElementById('edit-vazao-bombeio');
  if (tempo && !tempo.__supComputeBound) { tempo.addEventListener('input', computeSupervisorBombeio); tempo.__supComputeBound = true; }
  if (vazEl && !vazEl.__supComputeBound) { vazEl.addEventListener('input', computeSupervisorBombeio); vazEl.__supComputeBound = true; }
      if (ens && !ens.__supComputeBound) { ens.addEventListener('input', function(){ computeSupervisorResSolidos(); computeSupervisorResTotal(); }); ens.__supComputeBound = true; }
      var resLiq = document.getElementById('sup-res-liq'); if (resLiq && !resLiq.__supComputeBound) { resLiq.addEventListener('input', computeSupervisorResTotal); resLiq.__supComputeBound = true; }
      var resSol = document.getElementById('sup-res-sol'); if (resSol && !resSol.__supComputeBound) { resSol.addEventListener('input', computeSupervisorResTotal); resSol.__supComputeBound = true; }
  try { computeSupervisorBombeio(); computeSupervisorResSolidos(); computeSupervisorResTotal(); } catch(_){ }
  try { computeEditorTambores(); } catch(_){ }
  try { computeSupervisorTambores(); } catch(_){ }
      var nEfEl = document.getElementById('sup-total-n-efetivo-confinado'); if (nEfEl && !nEfEl.__userEditedBound) { nEfEl.addEventListener('input', function(){ this.dataset.userEdited = 'true'; }); nEfEl.__userEditedBound = true; }
      ensureSupervisorComputesBound.__bound = true;
    } catch(e){ console.warn('ensureSupervisorComputesBound failed', e); }
  }
  try { window.rdoOpenSupervisorModal = openSupervisorModal; } catch(_){ }
  onReady(function(){
    document.addEventListener('click', function(ev){
      try {
        var supTrigger = ev.target && ev.target.closest && ev.target.closest('[data-open="supervisor"], .open-supervisor, .btn-rdo.open-supervisor');
  if (supTrigger && supTrigger.closest && supTrigger.closest('.rdo-locked') && !supTrigger.closest('.allow-edit')) return;
        if (supTrigger) {
          var tr = supTrigger.closest('tr');
          if (tr) {
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
        }
        var oc = ev.target && ev.target.closest && ev.target.closest('.open-supervisor, .btn-rdo.open-supervisor');
        if (oc) {
          var card = oc.closest('.rdo-mobile-item') || oc.closest('.rdo-mobile-card');
          if (!card) return;
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
    try { resetSupervisorAccumulates(); } catch(_){}
    applyContext(context || {});
    try {
      // Only fetch an existing RDO when we have a reliable indicator
      // that the card/context refers to an existing RDO (e.g. rdo_count)
      // or when explicitly editing. This prevents attempting to fetch
      // RDO detail endpoints for contexts that only describe an OS
      // (which may return 404) and block normal creation flow.
      if (context && context.rdo_id) {
        var shouldFetch = false;
        try {
          if (context.edit === true || context.action === 'edit' || context.forceEdit === true) shouldFetch = true;
        } catch(_){ }
        try {
          if (!shouldFetch) {
            var rc = context.rdo_count || context.rdo || '';
            // only consider numeric rdo_count (avoid '-' or other placeholders)
            try { var rcDigits = String(rc).replace(/[^0-9]/g,''); var rcN = rcDigits === '' ? NaN : parseInt(rcDigits,10); if (isFinite(rcN) && rcN > 0) shouldFetch = true; } catch(_){ }
          }
        } catch(_){ }
        if (shouldFetch) {
          try { await fetchAndPopulateRdo(context.rdo_id); } catch(_){ }
        }
      }
    } catch(_){}
    try { await populateNextRdoIfNeeded(context || {}); } catch(_){ }
    ensureSubmitBound();
    try {
      var _rdoLabel = (context && (context.rdo_count || context.rdo)) || ((context && context.rdo_id) ? ('ID ' + String(context.rdo_id)) : '');
      var _osLabel = (context && (context.numero_os || context.os)) || (context && context.os_id) || '';
      var _isEdit = false;
      var _supRdoValue = '';
      try { if (context && (context.edit === true || context.action === 'edit' || context.forceEdit === true)) _isEdit = true; } catch(_){ }
      try { _supRdoValue = String(((document.getElementById('sup-rdo') || {}).value || '')).trim(); } catch(_){ _supRdoValue = ''; }
      try {
        if (_isEdit) {
          if ((!_rdoLabel || String(_rdoLabel).indexOf('ID ') === 0) && _supRdoValue) {
            _rdoLabel = _supRdoValue;
          }
        } else {
          if (_supRdoValue && /^\d+$/.test(_supRdoValue)) {
            _rdoLabel = _supRdoValue;
          } else {
            var _rawCurrent = String((context && (context.rdo_count || context.rdo)) || '').replace(/[^0-9]/g, '');
            var _current = _rawCurrent === '' ? NaN : parseInt(_rawCurrent, 10);
            _rdoLabel = (isFinite(_current) && _current > 0) ? String(_current + 1) : '1';
          }
        }
      } catch(_){ }
      if (typeof showToast === 'function') {
        if (_isEdit) {
          showToast('Editando RDO ' + (_rdoLabel || '') + (_rdoLabel && _osLabel ? ' da OS ' : _osLabel ? ' da OS ' : '') + (_osLabel || ''), 'info');
        } else {
          showToast('Gerando o RDO ' + (_rdoLabel || '') + (_rdoLabel && _osLabel ? ' da OS ' : _osLabel ? ' da OS ' : '') + (_osLabel || ''), 'info');
        }
      }
    } catch(_){ }
    openModal();
    try {
      var supOverlay = document.getElementById('supv-modal-overlay');
      setTimeout(function(){
        try {
          try {
            if (typeof _isDesktop === 'function' && _isDesktop()) {
              var focusTarget = document.getElementById('sup-observacoes-pt') || document.getElementById('sup-planejamento-pt') || (supOverlay && supOverlay.querySelector('input:not([type="hidden"]):not([readonly]), select, textarea'));
              if (focusTarget) {
                try {
                  focusTarget.focus({ preventScroll: true });
                } catch (e) {
                  try {
                    var scEl = document.scrollingElement || document.documentElement || document.body;
                    var prevTop = scEl.scrollTop;
                    var prevLeft = scEl.scrollLeft;
                    focusTarget.focus();
                    try { scEl.scrollTop = prevTop; scEl.scrollLeft = prevLeft; } catch(_){ }
                  } catch (_){
                    try { focusTarget.focus(); } catch(__){}
                  }
                }
              }
            }
          } catch(_){ }
          var hint = document.getElementById('sup-translate-hint');
          if (hint) {
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
    try {
      setTimeout(function(){
        try {
          var me = (window.RDO_ME || {});
          var pessoas = (window.RDO_PESSOAS_MAP || {});
          var desired = '';
          if (me && me.login && pessoas && typeof pessoas === 'object' && pessoas[me.login]) desired = String(pessoas[me.login] || '').trim();
          if (!desired && me && me.fullname) desired = String(me.fullname || '').trim();
          if (desired) {
            var nameSel = document.querySelector('#equipe-wrapper select[name="equipe_nome[]"]');
            if (nameSel) {
              var opt = Array.prototype.slice.call(nameSel.options).find(function(o){ try { return String((o.value||'')).trim() === desired; } catch(_){ return false; } });
              if (!opt) opt = Array.prototype.slice.call(nameSel.options).find(function(o){ try { return String((o.text||'')).trim() === desired; } catch(_){ return false; } });
              if (opt) {
                nameSel.value = opt.value;
                try { nameSel.dispatchEvent(new Event('change', { bubbles: true })); } catch(_){ }
              }
            }
            var funcSel = document.querySelector('#equipe-wrapper select[name="equipe_funcao[]"]');
            if (funcSel) {
              var preferred = 'Supervisor';
              var optf = Array.prototype.slice.call(funcSel.options).find(function(o){
                try {
                  var v = String((o.value||'')).trim().toLowerCase();
                  var t = String((o.text||'')).trim().toLowerCase();
                  return v === preferred.toLowerCase() || t === preferred.toLowerCase();
                } catch(_){ return false; }
              });
              if (!optf && me && me.funcao) {
                var desiredFunc = String(me.funcao || '').trim();
                optf = Array.prototype.slice.call(funcSel.options).find(function(o){ try { return String((o.value||'')).trim() === desiredFunc; } catch(_){ return false; } });
                if (!optf) optf = Array.prototype.slice.call(funcSel.options).find(function(o){ try { return String((o.text||'')).trim() === desiredFunc; } catch(_){ return false; } });
              }
              if (optf) {
                funcSel.value = optf.value;
                try { funcSel.dispatchEvent(new Event('change', { bubbles: true })); } catch(_){ }
              }
            }
          }
        } catch(_){ }
      }, 180);
    } catch(_){ }
    try {
      var rid = (context && (context.rdo_id || context.id)) || (document.getElementById('sup-rdo-id')||{}).value;
      var doFetchRid = false;
      try {
        if (context && (context.edit === true || context.action === 'edit' || context.forceEdit === true)) doFetchRid = true;
      } catch(_){ }
      try {
        if (!doFetchRid) {
          var rc = context && (context.rdo_count || context.rdo) || '';
          var rcDigits = String(rc).replace(/[^0-9]/g,'');
          var rcN = rcDigits === '' ? NaN : parseInt(rcDigits,10);
          if (isFinite(rcN) && rcN > 0) doFetchRid = true;
        }
      } catch(_){ }
      if (rid && doFetchRid) await fetchAndPopulateRdo(rid);
    } catch(_){}
  }

  function openEditorModal(context){
    try {
      var overlay = document.getElementById('modal-editor-overlay');
      if (!overlay) return false;
      var rid = (context && (context.rdo_id || context.id)) || '';
      var hid = document.getElementById('edit-rdo-id');
      if (hid) hid.value = rid;
      try {
        var osId = (context && (context.os_id || context.osId)) || '';
        var osNum = (context && (context.numero_os || context.os_num || context.os)) || '';
        if (osId) {
          try { overlay.dataset.osId = String(osId); } catch(_){ }
          try { if (window) window.__last_editor_os_id = String(osId); } catch(_){ }
        }
        if (osNum) {
          try { overlay.dataset.osNum = String(osNum); } catch(_){ }
          try { if (window) window.__last_editor_os_num = String(osNum); } catch(_){ }
        }
      } catch(_){ }
      try {
        var tid = (context && (context.tanque_id || context.tank_id)) || '';
        var hidTid = document.getElementById('edit-tanque-id');
        if (hidTid) hidTid.value = tid || '';
        try { if (tid && window) window.__last_rdo_tanque_id = String(tid || ''); } catch(_){ }
      } catch(_){ }
      try {
        var ctxRdo = document.getElementById('edit-context-rdo');
        var ctxOs = document.getElementById('edit-context-os');
  if (ctxRdo) ctxRdo.textContent = '';
  if (ctxOs) ctxOs.textContent = '';
      } catch(_){ }
      try {
        var _editRdoLabel = (context && (context.rdo_count || context.rdo)) || (rid ? ('ID ' + String(rid)) : '');
        var _editOsLabel = osNum || (context && (context.numero_os || context.os)) || (context && context.os_id) || '';
          try {
            if ((!_editRdoLabel || String(_editRdoLabel).indexOf('ID ') === 0)) {
              _editRdoLabel = '1';
            }
          } catch(_){ }
        if (typeof showToast === 'function') {
          showToast('Editando RDO ' + (_editRdoLabel || '') + (_editRdoLabel && _editOsLabel ? ' da OS ' : _editOsLabel ? ' da OS ' : '') + (_editOsLabel || ''), 'info');
        }
      } catch(_){ }
      overlay.classList.add('open');
      overlay.classList.remove('is-hidden');
      overlay.setAttribute('aria-hidden','false');
      try { document.documentElement.classList.add('modal-open'); } catch(_){}
      try { document.body.classList.add('modal-open'); } catch(_){}
      setTimeout(function(){
        try {
          var first = overlay.querySelector('input:not([type="hidden"]):not([readonly]), select, textarea');
          if (first) {
            try { first.focus({ preventScroll: true }); } catch(e) { first.focus(); }
            try { first.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch(_) {}
          }
        } catch(_){ }
      }, 100);
  try { if (typeof ensureEditorSubmitBound === 'function') ensureEditorSubmitBound(); } catch(_){ }
      try{ if (typeof _applyStartDateLock === 'function') _applyStartDateLock(); } catch(_){ }
    try { setTimeout(function(){ if (typeof computeEditorPercentuais === 'function') computeEditorPercentuais(); }, 250); } catch(_){ }
      try { setTimeout(function(){ if (typeof loadEditorDetails === 'function') { try { loadEditorDetails(); } catch(_){} } }, 120); } catch(_){ }
      return true;
    } catch(e){ console.warn('openEditorModal failed', e); return false; }
  }

  function _getEditorOsContext(){
    try {
      var overlay = document.getElementById('modal-editor-overlay');
      var rid = (document.getElementById('edit-rdo-id')||{}).value || '';
      var osId = '';
      var osNum = '';
      try {
        if (overlay && overlay.dataset) {
          osId = overlay.dataset.osId || '';
          osNum = overlay.dataset.osNum || '';
        }
      } catch(_){ }
      if (!osId) {
        try { if (window && window.__last_editor_os_id) osId = String(window.__last_editor_os_id||''); } catch(_){ }
      }
      if (!osNum) {
        try { if (window && window.__last_editor_os_num) osNum = String(window.__last_editor_os_num||''); } catch(_){ }
      }
      // fallback: localizar a linha da tabela pelo rdo_id e ler data-os-id
      if ((!osId || !osNum) && rid) {
        try {
          var tr = document.querySelector('tr[data-rdo-id="' + String(rid).replace(/"/g,'') + '"]');
          if (tr) {
            if (!osId) osId = tr.getAttribute('data-os-id') || (tr.dataset && tr.dataset.osId) || '';
            if (!osNum) osNum = tr.getAttribute('data-numero-os') || (tr.dataset && tr.dataset.numeroOs) || '';
          }
        } catch(_){ }
      }
      return { os_id: String(osId||'').trim(), numero_os: String(osNum||'').trim(), rdo_id: String(rid||'').trim() };
    } catch(e){ return { os_id:'', numero_os:'', rdo_id:'' }; }
  }

  async function _fetchTanksForMerge(osId, rdoId){
    var url = '/api/os/' + encodeURIComponent(String(osId||'')) + '/tanks/?all=1&page_size=200';
    if (rdoId) url += '&rdo_id=' + encodeURIComponent(String(rdoId));
    var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    var data = null;
    try { data = await resp.json(); } catch(_){ data = null; }
    if (!resp.ok || !data || data.success !== true) {
      var msg = (data && data.error) ? data.error : 'Falha ao listar tanques da OS';
      throw new Error(msg);
    }
    return (data.results || []).slice(0);
  }

  // Modal: selecionar origem/destino para juntar
  async function showTankMergeModal(opts){
    opts = opts || {};
    var ctx = _getEditorOsContext();
    var osId = String(opts.os_id || opts.osId || ctx.os_id || '').trim();
    var osNum = String(opts.numero_os || opts.os_num || ctx.numero_os || '').trim();
    var rdoId = String(opts.rdo_id || ctx.rdo_id || '').trim();
    var preSourceId = String(opts.source_id || opts.sourceId || '').trim();

    if (!osId) { showToast('OS não identificada para listar tanques.', 'error'); return null; }

    var tanks = [];
    try { tanks = await _fetchTanksForMerge(osId, null); } catch(e){ console.warn('fetch tanks failed', e); showToast(e && e.message ? e.message : 'Falha ao listar tanques', 'error'); return null; }
    if (!tanks || !tanks.length) { showToast('Nenhum tanque encontrado nesta OS.', 'error'); return null; }

    function labelFor(t){
      try {
        var code = (t && t.tanque_codigo) ? String(t.tanque_codigo).trim() : '';
        var name = (t && (t.nome || t.nome_tanque)) ? String(t.nome || t.nome_tanque).trim() : '';
        if (code && name) return code + ' — ' + name;
        if (code) return code;
        if (name) return name;
        return 'Tanque ' + String(t && t.id ? t.id : '');
      } catch(_){ return 'Tanque'; }
    }

    return await new Promise(function(resolve){
      var overlay = document.createElement('div');
      overlay.className = 'rdo-tank-create-modal';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.setAttribute('aria-label', 'Juntar tanques');

      var card = document.createElement('div');
      card.className = 'rdo-tank-create-modal__card';

      var header = document.createElement('div');
      header.className = 'rdo-tank-create-modal__header';
      header.innerHTML = '<div class="rdo-tank-create-modal__title">Juntar Tanques</div>' +
        '<div class="rdo-tank-create-modal__subtitle">Selecione origem (será removido) e destino (ficará). ' +
        (osNum ? ('OS #' + String(osNum)) : ('OS ID ' + String(osId))) + '</div>';

      var body = document.createElement('div');
      body.className = 'rdo-tank-create-modal__body';

      var grid = document.createElement('div');
      grid.className = 'rdo-tank-create-modal__grid';

      function mkField(label, control){
        var wrap = document.createElement('div');
        wrap.className = 'rdo-tank-create-modal__field';
        var lab = document.createElement('label');
        lab.className = 'rdo-tank-create-modal__label';
        lab.textContent = label;
        var ctrlWrap = document.createElement('div');
        ctrlWrap.className = 'rdo-tank-create-modal__control';
        ctrlWrap.appendChild(control);
        wrap.appendChild(lab);
        wrap.appendChild(ctrlWrap);
        return wrap;
      }

      var filter = document.createElement('input');
      filter.type = 'text';
      filter.placeholder = 'Filtrar por código/nome…';

      var selSource = document.createElement('select');
      var selTarget = document.createElement('select');
      selSource.className = 'small-select';
      selTarget.className = 'small-select';

      var selNameMode = document.createElement('select');
      selNameMode.className = 'small-select';
      try {
        selNameMode.appendChild(new Option('Manter nome do destino', 'keep_target', true, true));
        selNameMode.appendChild(new Option('Manter nome da origem', 'keep_source'));
        selNameMode.appendChild(new Option('Definir manualmente', 'manual'));
      } catch(_){ }

      var inpNameManual = document.createElement('input');
      inpNameManual.type = 'text';
      inpNameManual.placeholder = 'Nome final (opcional)';
      inpNameManual.style.display = 'none';

      var selCodeMode = document.createElement('select');
      selCodeMode.className = 'small-select';
      try {
        selCodeMode.appendChild(new Option('Manter código do destino', 'keep_target', true, true));
        selCodeMode.appendChild(new Option('Manter código da origem', 'keep_source'));
        selCodeMode.appendChild(new Option('Definir manualmente', 'manual'));
      } catch(_){ }

      var inpCodeManual = document.createElement('input');
      inpCodeManual.type = 'text';
      inpCodeManual.placeholder = 'Código final (ex.: 3C / 4P)';
      inpCodeManual.style.display = 'none';

      function fillSelect(selectEl, keepValue){
        var prev = keepValue ? (selectEl.value || '') : '';
        selectEl.innerHTML = '';
        var opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = 'Selecionar…';
        selectEl.appendChild(opt0);
        var q = String(filter.value || '').trim().toLowerCase();
        tanks.forEach(function(t){
          try {
            var text = labelFor(t);
            if (q) {
              var hay = (String(text||'') + ' ' + String(t && t.id ? t.id : '')).toLowerCase();
              if (hay.indexOf(q) === -1) return;
            }
            var opt = document.createElement('option');
            opt.value = String(t.id);
            opt.textContent = text;
            selectEl.appendChild(opt);
          } catch(_){ }
        });
        if (prev) {
          try { selectEl.value = prev; } catch(_){ }
        }
      }

      filter.addEventListener('input', function(){
        fillSelect(selSource, true);
        fillSelect(selTarget, true);
      });

      selNameMode.addEventListener('change', function(){
        try { inpNameManual.style.display = (selNameMode.value === 'manual') ? '' : 'none'; } catch(_){ }
      });
      selCodeMode.addEventListener('change', function(){
        try { inpCodeManual.style.display = (selCodeMode.value === 'manual') ? '' : 'none'; } catch(_){ }
      });

      fillSelect(selSource, false);
      fillSelect(selTarget, false);

      // tenta preselecionar origem
      if (preSourceId) {
        try { selSource.value = preSourceId; } catch(_){ }
      }

      var hint = document.createElement('div');
      hint.style.fontSize = '12px';
      hint.style.opacity = '0.9';
      hint.textContent = 'Dica: o tanque de origem será apagado após a união.';

      grid.appendChild(mkField('Buscar', filter));
      grid.appendChild(mkField('Tanque de origem', selSource));
      grid.appendChild(mkField('Tanque de destino', selTarget));
      try {
        var nameWrap = document.createElement('div');
        nameWrap.style.display = 'grid';
        nameWrap.style.gridTemplateColumns = '1fr';
        nameWrap.style.gap = '8px';
        nameWrap.appendChild(selNameMode);
        nameWrap.appendChild(inpNameManual);
        grid.appendChild(mkField('Nome final', nameWrap));
      } catch(_){ }
      try {
        var codeWrap = document.createElement('div');
        codeWrap.style.display = 'grid';
        codeWrap.style.gridTemplateColumns = '1fr';
        codeWrap.style.gap = '8px';
        codeWrap.appendChild(selCodeMode);
        codeWrap.appendChild(inpCodeManual);
        grid.appendChild(mkField('Código final', codeWrap));
      } catch(_){ }
      body.appendChild(grid);
      body.appendChild(hint);

      var footer = document.createElement('div');
      footer.className = 'rdo-tank-create-modal__footer';

      var btnCancel = document.createElement('button');
      btnCancel.type = 'button';
      btnCancel.className = 'btn-rdo small outline';
      btnCancel.textContent = 'Cancelar';

      var btnOk = document.createElement('button');
      btnOk.type = 'button';
      btnOk.className = 'btn-rdo small primary';
      btnOk.textContent = 'Juntar';

      footer.appendChild(btnCancel);
      footer.appendChild(btnOk);

      card.appendChild(header);
      card.appendChild(body);
      card.appendChild(footer);
      overlay.appendChild(card);

      function cleanup(result){
        try { overlay.removeEventListener('click', onOverlayClick); } catch(_){ }
        try { document.removeEventListener('keydown', onKeyDown, true); } catch(_){ }
        try { if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); } catch(_){ }
        resolve(result || null);
      }
      function onOverlayClick(ev){
        try { if (ev.target === overlay) cleanup(null); } catch(_){ }
      }
      function onKeyDown(ev){
        try {
          if (!ev) return;
          if (ev.key === 'Escape') { ev.preventDefault(); cleanup(null); }
        } catch(_){ }
      }

      btnCancel.addEventListener('click', function(){ cleanup(null); });
      btnOk.addEventListener('click', function(){
        var s = String(selSource.value || '').trim();
        var t = String(selTarget.value || '').trim();
        if (!s || !t) { showToast('Selecione origem e destino.', 'error'); return; }
        if (s === t) { showToast('Origem e destino devem ser diferentes.', 'error'); return; }
        // calcular nome/código final
        var srcObj = null;
        var dstObj = null;
        try {
          tanks.forEach(function(x){
            if (x && String(x.id) === String(s)) srcObj = x;
            if (x && String(x.id) === String(t)) dstObj = x;
          });
        } catch(_){ }
        var finalNome = '';
        try {
          if (selNameMode.value === 'manual') finalNome = String(inpNameManual.value || '').trim();
          else if (selNameMode.value === 'keep_source') finalNome = String((srcObj && (srcObj.nome || srcObj.nome_tanque)) || '').trim();
          else finalNome = String((dstObj && (dstObj.nome || dstObj.nome_tanque)) || '').trim();
        } catch(_){ finalNome = ''; }

        var finalCodigo = '';
        try {
          if (selCodeMode.value === 'manual') finalCodigo = String(inpCodeManual.value || '').trim();
          else if (selCodeMode.value === 'keep_source') finalCodigo = String((srcObj && (srcObj.tanque_codigo || srcObj.codigo)) || '').trim();
          else finalCodigo = String((dstObj && (dstObj.tanque_codigo || dstObj.codigo)) || '').trim();
        } catch(_){ finalCodigo = ''; }

        cleanup({ sourceId: s, targetId: t, final_tanque_nome: finalNome, final_tanque_codigo: finalCodigo });
      });
      overlay.addEventListener('click', onOverlayClick);
      document.addEventListener('keydown', onKeyDown, true);

      document.body.appendChild(overlay);
      try { setTimeout(function(){ try { filter.focus({ preventScroll: true }); } catch(_){ try { filter.focus(); } catch(__){} } }, 50); } catch(_){ }
    });
  }

  // Modal: selecionar um tanque existente para associar ao RDO (Editor)
  async function showTankAssociateModal(opts){
    opts = opts || {};
    var ctx = _getEditorOsContext();
    var osId = String(opts.os_id || opts.osId || ctx.os_id || '').trim();
    var osNum = String(opts.numero_os || opts.os_num || ctx.numero_os || '').trim();
    var rdoId = String(opts.rdo_id || ctx.rdo_id || '').trim();

    if (!osId) { showToast('OS não identificada para listar tanques.', 'error'); return null; }

    var tanks = [];
    try { tanks = await _fetchTanksForMerge(osId, null); } catch(e){ console.warn('fetch tanks failed', e); showToast(e && e.message ? e.message : 'Falha ao listar tanques', 'error'); return null; }
    if (!tanks || !tanks.length) { showToast('Nenhum tanque encontrado nesta OS.', 'error'); return null; }

    function labelFor(t){
      try {
        var code = (t && t.tanque_codigo) ? String(t.tanque_codigo).trim() : '';
        var name = (t && (t.nome || t.nome_tanque)) ? String(t.nome || t.nome_tanque).trim() : '';
        if (code && name) return code + ' — ' + name;
        if (code) return code;
        if (name) return name;
        return 'Tanque ' + String(t && t.id ? t.id : '');
      } catch(_){ return 'Tanque'; }
    }

    return await new Promise(function(resolve){
      var overlay = document.createElement('div');
      overlay.className = 'rdo-tank-create-modal';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.setAttribute('aria-label', 'Associar tanque');

      var card = document.createElement('div');
      card.className = 'rdo-tank-create-modal__card';

      var header = document.createElement('div');
      header.className = 'rdo-tank-create-modal__header';
      header.innerHTML = '<div class="rdo-tank-create-modal__title">Associar Tanque</div>' +
        '<div class="rdo-tank-create-modal__subtitle">Selecione o tanque desta OS para associar ao RDO. ' +
        (osNum ? ('OS #' + String(osNum)) : ('OS ID ' + String(osId))) + '</div>';

      var body = document.createElement('div');
      body.className = 'rdo-tank-create-modal__body';

      var sel = document.createElement('select');
      sel.className = 'small-select';
      sel.style.width = '100%';
      sel.style.padding = '8px';
      tanks.forEach(function(t){ try{ var opt = document.createElement('option'); opt.value = String(t.id || ''); opt.textContent = labelFor(t); sel.appendChild(opt); }catch(_){ } });

      var filter = document.createElement('input'); filter.type='text'; filter.placeholder='Filtrar por código/nome…'; filter.style.width='100%'; filter.style.margin='8px 0'; filter.addEventListener('input', function(){
        var term = (filter.value||'').toLowerCase().trim();
        Array.prototype.forEach.call(sel.options, function(o){ try{ var txt = (o.textContent||'').toLowerCase(); o.style.display = (term && txt.indexOf(term)===-1) ? 'none' : ''; }catch(_){ } });
      });

      var footer = document.createElement('div'); footer.className = 'rdo-tank-create-modal__footer';
      footer.style.marginTop = '12px'; footer.style.textAlign = 'right';
      var btnCancel = document.createElement('button'); btnCancel.type='button'; btnCancel.className='btn-rdo small'; btnCancel.textContent='Cancelar';
      var btnOk = document.createElement('button'); btnOk.type='button'; btnOk.className='btn-rdo small primary'; btnOk.textContent='Associar';

      footer.appendChild(btnCancel); footer.appendChild(btnOk);

      body.appendChild(filter); body.appendChild(sel);
      card.appendChild(header); card.appendChild(body); card.appendChild(footer); overlay.appendChild(card); document.body.appendChild(overlay);

      function close(){ try{ if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); }catch(_){ } }
      btnCancel.addEventListener('click', function(ev){ ev.preventDefault(); close(); resolve(null); });
      btnOk.addEventListener('click', function(ev){ ev.preventDefault(); try{ var v = sel.value; if(!v) return; close(); resolve({ tankId: String(v) }); }catch(e){ close(); resolve(null); } });
      overlay.addEventListener('click', function(ev){ try{ if (ev.target === overlay) { close(); resolve(null); } }catch(_){ } });
      document.addEventListener('keydown', function onEsc(ev){ try{ if (ev.key === 'Escape'){ document.removeEventListener('keydown', onEsc); close(); resolve(null); } }catch(_){ } });
    });
  }
  try { window.showTankMergeModal = showTankMergeModal; } catch(_){ }

  // Modal: selecionar um tanque para excluir
  async function showTankDeleteModal(opts){
    opts = opts || {};
    var ctx = _getEditorOsContext();
    var osId = String(opts.os_id || opts.osId || ctx.os_id || '').trim();
    var osNum = String(opts.numero_os || opts.os_num || ctx.numero_os || '').trim();
    var rdoId = String(opts.rdo_id || ctx.rdo_id || '').trim();
    var preTankId = String(opts.tank_id || opts.tankId || opts.selected_id || '').trim();

    if (!osId) { showToast('OS não identificada para listar tanques.', 'error'); return null; }

    var tanks = [];
    // para exclusão, listar tanques da OS (não filtrar por RDO)
    try { tanks = await _fetchTanksForMerge(osId, null); } catch(e){ console.warn('fetch tanks failed', e); showToast(e && e.message ? e.message : 'Falha ao listar tanques', 'error'); return null; }
    if (!tanks || !tanks.length) { showToast('Nenhum tanque encontrado nesta OS.', 'error'); return null; }

    function labelFor(t){
      try {
        var code = (t && t.tanque_codigo) ? String(t.tanque_codigo).trim() : '';
        var name = (t && (t.nome || t.nome_tanque)) ? String(t.nome || t.nome_tanque).trim() : '';
        if (code && name) return code + ' — ' + name;
        if (code) return code;
        if (name) return name;
        return 'Tanque ' + String(t && t.id ? t.id : '');
      } catch(_){ return 'Tanque'; }
    }

    return await new Promise(function(resolve){
      var overlay = document.createElement('div');
      overlay.className = 'rdo-tank-create-modal';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.setAttribute('aria-label', 'Excluir tanque');

      var card = document.createElement('div');
      card.className = 'rdo-tank-create-modal__card';

      var header = document.createElement('div');
      header.className = 'rdo-tank-create-modal__header';
      header.innerHTML = '<div class="rdo-tank-create-modal__title">Excluir Tanque</div>' +
        '<div class="rdo-tank-create-modal__subtitle">Escolha o tanque a ser excluído. ' +
        (osNum ? ('OS #' + String(osNum)) : ('OS ID ' + String(osId))) + '</div>';

      var body = document.createElement('div');
      body.className = 'rdo-tank-create-modal__body';

      var grid = document.createElement('div');
      grid.className = 'rdo-tank-create-modal__grid';

      function mkField(label, control){
        var wrap = document.createElement('div');
        wrap.className = 'rdo-tank-create-modal__field';
        var lab = document.createElement('label');
        lab.className = 'rdo-tank-create-modal__label';
        lab.textContent = label;
        var ctrlWrap = document.createElement('div');
        ctrlWrap.className = 'rdo-tank-create-modal__control';
        ctrlWrap.appendChild(control);
        wrap.appendChild(lab);
        wrap.appendChild(ctrlWrap);
        return wrap;
      }

      var filter = document.createElement('input');
      filter.type = 'text';
      filter.placeholder = 'Filtrar por código/nome…';

      var sel = document.createElement('select');
      sel.className = 'small-select';

      function fillSelect(keepValue){
        var prev = keepValue ? (sel.value || '') : '';
        sel.innerHTML = '';
        var opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = 'Selecionar…';
        sel.appendChild(opt0);
        var q = String(filter.value || '').trim().toLowerCase();
        tanks.forEach(function(t){
          try {
            var text = labelFor(t);
            if (q) {
              var hay = (String(text||'') + ' ' + String(t && t.id ? t.id : '')).toLowerCase();
              if (hay.indexOf(q) === -1) return;
            }
            var opt = document.createElement('option');
            opt.value = String(t.id);
            opt.textContent = text;
            sel.appendChild(opt);
          } catch(_){ }
        });
        if (prev) { try { sel.value = prev; } catch(_){ } }
      }

      filter.addEventListener('input', function(){ fillSelect(true); });
      fillSelect(false);
      if (preTankId) { try { sel.value = preTankId; } catch(_){ } }

      var confirmWrap = document.createElement('div');
      confirmWrap.style.display = 'flex';
      confirmWrap.style.gap = '8px';
      confirmWrap.style.alignItems = 'center';
      var chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.id = 'rdo-tank-delete-confirm';
      var chkLbl = document.createElement('label');
      chkLbl.setAttribute('for', chk.id);
      chkLbl.textContent = 'Entendi que essa ação não pode ser desfeita.';
      confirmWrap.appendChild(chk);
      confirmWrap.appendChild(chkLbl);

      var hint = document.createElement('div');
      hint.style.fontSize = '12px';
      hint.style.opacity = '0.95';
      hint.textContent = 'Atenção: em “Toda a OS”, o tanque será removido de todos os RDOs dessa OS.';

      var scopeWrap = document.createElement('div');
      scopeWrap.style.display = 'grid';
      scopeWrap.style.gap = '6px';
      scopeWrap.style.marginTop = '6px';
      scopeWrap.style.padding = '10px';
      scopeWrap.style.border = '1px solid rgba(0,0,0,0.08)';
      scopeWrap.style.borderRadius = '10px';
      scopeWrap.style.background = 'rgba(255,255,255,0.85)';

      var r1 = document.createElement('label');
      r1.style.display = 'flex';
      r1.style.gap = '8px';
      r1.style.alignItems = 'flex-start';
      var rb1 = document.createElement('input');
      rb1.type = 'radio';
      rb1.name = 'rdo-tank-delete-scope';
      rb1.value = 'rdo';
      rb1.checked = true;
      var rb1Txt = document.createElement('div');
      rb1Txt.innerHTML = '<strong>Somente este RDO</strong><div style="opacity:.85;font-size:12px">Exclui apenas o registro deste tanque no RDO atual.</div>';
      r1.appendChild(rb1);
      r1.appendChild(rb1Txt);

      var r2 = document.createElement('label');
      r2.style.display = 'flex';
      r2.style.gap = '8px';
      r2.style.alignItems = 'flex-start';
      var rb2 = document.createElement('input');
      rb2.type = 'radio';
      rb2.name = 'rdo-tank-delete-scope';
      rb2.value = 'os';
      var rb2Txt = document.createElement('div');
      rb2Txt.innerHTML = '<strong>Toda a OS</strong><div style="opacity:.85;font-size:12px">Remove este tanque em todos os RDOs dessa OS (mesmo código).</div>';
      r2.appendChild(rb2);
      r2.appendChild(rb2Txt);

      scopeWrap.appendChild(r1);
      scopeWrap.appendChild(r2);

      grid.appendChild(mkField('Buscar', filter));
      grid.appendChild(mkField('Tanque', sel));
      body.appendChild(grid);
      body.appendChild(scopeWrap);
      body.appendChild(confirmWrap);
      body.appendChild(hint);

      var footer = document.createElement('div');
      footer.className = 'rdo-tank-create-modal__footer';

      var btnCancel = document.createElement('button');
      btnCancel.type = 'button';
      btnCancel.className = 'btn-rdo small outline';
      btnCancel.textContent = 'Cancelar';

      var btnOk = document.createElement('button');
      btnOk.type = 'button';
      btnOk.className = 'btn-rdo small danger';
      btnOk.textContent = 'Excluir';

      footer.appendChild(btnCancel);
      footer.appendChild(btnOk);

      card.appendChild(header);
      card.appendChild(body);
      card.appendChild(footer);
      overlay.appendChild(card);

      function cleanup(result){
        try { overlay.removeEventListener('click', onOverlayClick); } catch(_){ }
        try { document.removeEventListener('keydown', onKeyDown, true); } catch(_){ }
        try { if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); } catch(_){ }
        resolve(result || null);
      }
      function onOverlayClick(ev){ try { if (ev.target === overlay) cleanup(null); } catch(_){ } }
      function onKeyDown(ev){ try { if (ev && ev.key === 'Escape') { ev.preventDefault(); cleanup(null); } } catch(_){ } }

      btnCancel.addEventListener('click', function(){ cleanup(null); });
      btnOk.addEventListener('click', function(){
        var id = String(sel.value || '').trim();
        if (!id) { showToast('Selecione o tanque para excluir.', 'error'); return; }
        if (!chk.checked) { showToast('Confirme a exclusão para continuar.', 'error'); return; }
        var scope = 'rdo';
        try {
          var checked = scopeWrap.querySelector('input[name="rdo-tank-delete-scope"]:checked');
          if (checked && checked.value) scope = String(checked.value);
        } catch(_){ scope = 'rdo'; }
        cleanup({ tankId: id, scope: scope });
      });

      overlay.addEventListener('click', onOverlayClick);
      document.addEventListener('keydown', onKeyDown, true);
      document.body.appendChild(overlay);
      try { setTimeout(function(){ try { filter.focus({ preventScroll: true }); } catch(_){ try { filter.focus(); } catch(__){} } }, 50); } catch(_){ }
    });
  }
  try { window.showTankDeleteModal = showTankDeleteModal; } catch(_){ }

  function closeEditorModal(){
    try {
      var overlay = document.getElementById('modal-editor-overlay');
      if (!overlay) return false;
      overlay.classList.remove('open');
      overlay.classList.add('is-hidden');
      overlay.setAttribute('aria-hidden','true');
      try { document.documentElement.classList.remove('modal-open'); } catch(_){}
      try { document.body.classList.remove('modal-open'); } catch(_){}
      return true;
    } catch(e){ console.warn('closeEditorModal failed', e); return false; }
  }

  function _applyStartDateLock(){
    try{
      // Apenas bloquear a data no modal Supervisor (`sup-data-inicio`).
      // Não incluir `edit-data-inicio` aqui para permitir edição no editor.
      var ids = ['sup-data-inicio'];
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
          span.className = 'auto-lock-icon material-icons';
          span.setAttribute('title','Campo automático (fixo)');
          span.setAttribute('aria-hidden','true');
          span.textContent = 'lock';
          lbl.appendChild(document.createTextNode(' '));
          lbl.appendChild(span);
        }
      });
    }catch(e){ console.warn('_applyStartDateLock failed', e); }
  }
  function _setValById(id, v){ var el = document.getElementById(id); if (!el) return; if (v == null) { el.value = ''; return; } el.value = String(v); }
  function _setSelectById(id, v){ var el = document.getElementById(id); if (!el) return; var val = (v == null ? '' : String(v)); el.value = val; if (el.value !== val) { /* valor inexistente */ } }
  function _setBoolSelectSimNaoById(id, v){
    var el = document.getElementById(id); if (!el) return;
    var val = v;
    if (typeof v === 'boolean') val = v ? 'sim' : 'nao';
    else if (v === 1 || v === '1') val = 'sim';
    else if (v === 0 || v === '0') val = 'nao';
    else if (typeof v === 'string') {
      var low = v.trim().toLowerCase();
      if (low === 'sim' || low === 's' || low === 'true' || low === 'yes' || low === 'y') val = 'sim';
      else if (low === 'nao' || low === 'não' || low === 'n' || low === 'false' || low === 'no') val = 'nao';
    }
    _setSelectById(id, val);
  }
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

  function _formatTimeForInput(val){
    try{
      if (val == null || val === '') return '';
      if (typeof val === 'number' && isFinite(val)){
        var m = Math.floor(val);
        var hh = Math.floor(m/60) % 24;
        var mm = m % 60;
        return (hh<10?('0'+hh):String(hh))+':'+(mm<10?('0'+mm):String(mm));
      }
      if (typeof val === 'string'){
        var s = String(val).trim();
        if (!s) return '';
        if (/^\d+$/.test(s)){
          var m2 = parseInt(s,10);
          var hh2 = Math.floor(m2/60) % 24;
          var mm2 = m2 % 60;
          return (hh2<10?('0'+hh2):String(hh2))+':'+(mm2<10?('0'+mm2):String(mm2));
        }
        if (/^\d{1,2}:\d{2}$/.test(s)) return s;
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
        var d = new Date(s);
        if (!isNaN(d.getTime())){
          var hh3 = d.getHours(); var mm3 = d.getMinutes();
          return (hh3<10?('0'+hh3):String(hh3))+':'+(mm3<10?('0'+mm3):String(mm3));
        }
      }
    }catch(e){}
    return '';
  }
  function _debounce(fn, wait){
    var t = null;
    return function(){
      var ctx = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(function(){ try{ fn.apply(ctx, args); } catch(_){} }, wait || 300);
    };
  }
  function _bindActivityTimeLinking(){
    try {
      var wrapper = qs('#atividades-wrapper');
      if (!wrapper) return;
      wrapper.addEventListener('input', function(ev){
        try {
          var t = ev.target || ev.srcElement;
          if (!t || !t.classList) return;
          if (t.dataset && t.dataset._syncLock) return;
          if (t.classList.contains('atividade-fim')) {
            var row = t.closest('.activities-row'); if (!row) return;
            var next = row.nextElementSibling;
            while(next && !next.classList.contains('activities-row')) next = next.nextElementSibling;
            if (!next) return;
            var nextStart = next.querySelector('.atividade-inicio'); if (!nextStart) return;
            try { nextStart.dataset._syncLock = '1'; } catch(_){}
            nextStart.value = t.value || '';
            try { nextStart.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ }
            setTimeout(function(){ try{ delete nextStart.dataset._syncLock; } catch(_){} }, 20);
            return;
          }

          if (t.classList.contains('atividade-inicio')) {
            var row2 = t.closest('.activities-row'); if (!row2) return;
            var prev = row2.previousElementSibling;
            while(prev && !prev.classList.contains('activities-row')) prev = prev.previousElementSibling;
            if (!prev) return;
            var prevEnd = prev.querySelector('.atividade-fim'); if (!prevEnd) return;
            try { prevEnd.dataset._syncLock = '1'; } catch(_){}
            prevEnd.value = t.value || '';
            try { prevEnd.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ }
            setTimeout(function(){ try{ delete prevEnd.dataset._syncLock; } catch(_){} }, 20);
            return;
          }
        } catch(_){ }
      }, false);
      var addBtn = qs('#btn-add-atividade');
      if (addBtn) {
        addBtn.addEventListener('click', function(){
          setTimeout(function(){
            try {
              var rows = qsa('.activities-row');
              if (!rows || rows.length < 2) return;
              var prev = rows[rows.length-2];
              var newly = rows[rows.length-1];
              if (!prev || !newly) return;
              var prevEnd = (prev.querySelector('.atividade-fim')||{}).value || '';
              var newStart = newly.querySelector('.atividade-inicio');
              if (prevEnd && newStart && !newStart.value) {
                try { newStart.dataset._syncLock = '1'; } catch(_){}
                newStart.value = prevEnd;
                try { newStart.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ }
                setTimeout(function(){ try{ delete newStart.dataset._syncLock; } catch(_){} }, 20);
              }
            } catch(_){ }
          }, 60);
        });
      }
      try {
        var mo = new MutationObserver(function(muts){
          try {
            muts.forEach(function(m){
              Array.prototype.forEach.call(m.addedNodes || [], function(node){
                try {
                  if (!node || !node.classList) return;
                  if (node.classList.contains('activities-row')) {
                    var prev = node.previousElementSibling;
                    while(prev && !prev.classList.contains('activities-row')) prev = prev.previousElementSibling;
                    if (!prev) return;
                    var prevEnd = (prev.querySelector('.atividade-fim')||{}).value || '';
                    var newStart = node.querySelector('.atividade-inicio');
                    if (prevEnd && newStart && !newStart.value) {
                      try { newStart.dataset._syncLock = '1'; } catch(_){ }
                      newStart.value = prevEnd;
                      try { newStart.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ }
                      setTimeout(function(){ try{ delete newStart.dataset._syncLock; } catch(_){} }, 20);
                    }
                  }
                } catch(_){ }
              });
            });
          } catch(_){ }
        });
        mo.observe(wrapper, { childList: true, subtree: false });
      } catch(_){ }
    } catch(e){ console.warn('_bindActivityTimeLinking failed', e); }
  }
  try { onReady(_bindActivityTimeLinking); } catch(_){ }
  var __rdo_translate_available = true;
  var __rdo_translate_warned = false;
  function _getCookie(name){
    try{
      var v = document.cookie.match('(?:^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
      return v ? decodeURIComponent(v[1]) : null;
    }catch(e){ return null; }
  }
  async function _translatePreview(text){
    try {
      if (!text || !text.toString().trim()) return '';
      if (!__rdo_translate_available) {
        if (!__rdo_translate_warned) { __rdo_translate_warned = true; showToast('Tradução automática indisponível', 'info'); }
        return '';
      }
  var url = '/api/rdo/translate/preview/';
      var payload = JSON.stringify({ text: String(text) });
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
        if (!data.success) console.warn('translate_preview: returned success=false', data.error || 'no error');
        return data.en || '';
      }
      return '';
    } catch(e){ return ''; }
  }

  function _showTranslatingIndicator(target){
    try{
      if (!target) return;
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

  try {
    if (!document.getElementById('rdo-translate-spinner-styles')) {
      var st = document.createElement('style'); st.id = 'rdo-translate-spinner-styles';
      st.type = 'text/css';
      st.appendChild(document.createTextNode('\n.rdo-translate-spinner { display: inline-block; margin-left: 6px; font-size: 16px; color: #666; vertical-align: middle; }\n.rdo-translate-spinner.loading { font-style: italic; opacity: 0.9; }\n.rdo-translate-spinner[data-for] { margin-left: 8px; }\n'));
      document.head.appendChild(st);
    }
  } catch(_){ }

  function _bindTranslationHandlers(scope){
    try {
      var ctx = scope || document;
      try { console.debug && console.debug('rdo.core: _bindTranslationHandlers scope=', ctx && (ctx.id || ctx.nodeName)); } catch(_){}
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
      try {
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
      try {
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
      try {
        var cientePt = ctx.querySelector('#edit-ciente-observacoes-pt, #sup-ciente-observacoes-pt');
        var cienteEn = ctx.querySelector('#edit-ciente-observacoes-en, #sup-ciente-observacoes-en');
        if (cientePt && cienteEn && !cientePt.__translateBound){
          try { console.debug && console.debug('rdo.core: binding ciente_observacoes'); } catch(_){ }
          var h3 = _debounce(async function(){
            try{
              var t = cientePt.value||'';
              var spinner = _showTranslatingIndicator(cienteEn);
              var tr = await _translatePreview(t);
              _hideTranslatingIndicator(cienteEn);
              if (tr != null) cienteEn.value = tr;
            }catch(_){ try{ _hideTranslatingIndicator(cienteEn); }catch(_){} }
          }, 700);
          cientePt.addEventListener('input', h3);
          cientePt.__translateBound = true;
        }
      } catch(_){ }
    } catch(_){}
  }

  function ensureSupervisorTranslationsBound(){
    try {
      if (ensureSupervisorTranslationsBound.__bound) return;
      var scope = document.getElementById('supv-content') || document.getElementById('supv-modal-overlay') || document;
      if (!scope) return;
      try { _bindTranslationHandlers(scope); } catch(_){ }
      try {
        var obsPt = scope.querySelector('#sup-observacoes-pt');
        var planPt = scope.querySelector('#sup-planejamento-pt');
        var cientePtSup = scope.querySelector('#sup-ciente-observacoes-pt');
        var cienteEnSup = scope.querySelector('#sup-ciente-observacoes-en');
        if (obsPt) { try { obsPt.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ } }
        if (planPt) { try { planPt.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ } }
        try {
          if (cientePtSup && cienteEnSup && (String(cientePtSup.value||'').trim() !== '') && String(cienteEnSup.value||'').trim() === '') {
            try { cientePtSup.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ }
          }
        } catch(_){ }
      } catch(_){ }
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
  document.addEventListener('click', function(ev){
    try {
      var btn = ev.target && ev.target.closest && ev.target.closest('.photo-remove');
      if (!btn) return;
      ev.preventDefault();
      var item = btn.closest && btn.closest('.photo-slot, .photo-item') ? btn.closest('.photo-slot, .photo-item') : (btn.closest('.photo-item') || null);
      if (!item) return;
      var url = item.dataset && item.dataset.url ? item.dataset.url : null;
      var form = document.getElementById('form-editor') || document.getElementById('form-supervisor');
      var rdoIdEl = null;
      try {
        if (form) rdoIdEl = form.querySelector('#edit-rdo-id') || form.querySelector('#sup-rdo-id') || form.querySelector('input[name="rdo_id"]');
      } catch(_){ rdoIdEl = null; }
      if (rdoIdEl && rdoIdEl.value) {
        var overlay = document.createElement('div');
        overlay.className = 'photo-action-overlay';
        overlay.style.position='absolute'; overlay.style.left=0; overlay.style.top=0; overlay.style.right=0; overlay.style.bottom=0; overlay.style.display='flex'; overlay.style.alignItems='center'; overlay.style.justifyContent='center'; overlay.style.background='rgba(0,0,0,0.5)'; overlay.style.color='#fff'; overlay.style.fontSize='13px';
        overlay.innerHTML = '<div>Removendo...</div>';
        try { item.appendChild(overlay); } catch(_){ }

        (async function(){
          try {
            var fd = new FormData();
            fd.append('rdo_id', rdoIdEl.value);
            var basename = (url || '').split('/').slice(-1)[0].split('?')[0];
            fd.append('foto_basename', basename || url || '');
            var controller = new AbortController();
            var to = setTimeout(function(){ try{ controller.abort(); }catch(_){} }, 30000);
            var resp = await fetch('/api/rdo/delete_photo_basename/', { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCSRF(form) || _getCookie('csrftoken') || '' }, signal: controller.signal });
            clearTimeout(to);
            var data = null; try { data = await resp.json(); } catch(_) { data = null; }
            if (resp.ok && data && data.success) {
              try {
                if (form) {
                  var hid = document.createElement('input'); hid.type='hidden'; hid.name='fotos_remove[]'; hid.value = url || basename || '';
                  hid.className = 'fotos-remove-input'; form.appendChild(hid);
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
      Array.prototype.forEach.call(rows, function(row, idx){ if (idx>0 && row.parentNode) row.parentNode.removeChild(row); });
      var base = wrap.querySelector('.team-row'); if (!base) return;
      var list = Array.isArray(equipe) ? equipe : [];
      if (!list.length) { try { syncPobAllForms(); } catch(_){ } return; }

      function _setField(el, value){
        if (!el) return;
        var v = (value === null || typeof value === 'undefined') ? '' : String(value);
        try {
          if (el.tagName && el.tagName.toLowerCase() === 'select'){
            try { el.value = v; } catch(e){}
            if (v && String(el.value || '') === ''){
              try { var op = document.createElement('option'); op.value = v; op.textContent = v; el.appendChild(op); el.value = v; } catch(e){}
            }
          } else {
            try { el.value = v; } catch(e){}
          }
        } catch(e){}
      }
      var first = base;
      var f0 = list[0] || {};
      var selN = first.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
      var selF = first.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
      _setField(selN, f0.nome || f0.name || '');
      _setField(selF, f0.funcao || f0.role || '');
      for (var i=1;i<list.length;i++){
        var clone = first.cloneNode(true);
        var it = list[i] || {};
        var cN = clone.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
        var cF = clone.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
        _setField(cN, it.nome || it.name || '');
        _setField(cF, it.funcao || it.role || '');
        first.parentNode.insertBefore(clone, wrap.querySelector('.team-footer'));
      }
      try { syncPobAllForms(); } catch(_){ }
    } catch(_){ }
  }

  async function loadEditorDetails(){
    try {
      var btn = document.getElementById('edit-btn-load-details');
      var rid = (document.getElementById('edit-rdo-id')||{}).value;
      if (!rid) {
        try { if (window && window.__last_rdo_row_id) { rid = String(window.__last_rdo_row_id || ''); } } catch(_){ }
      }
      if (!rid) {
        try {
          var displayed = (document.getElementById('edit-rdo')||{}).value || '';
          if (displayed) {
            var rresp = await fetch('/rdo/find_by_number/?rdo=' + encodeURIComponent(displayed), { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (rresp && rresp.ok) {
              var jd = await rresp.json();
              if (jd && jd.success && jd.id) {
                rid = String(jd.id);
                try { var hidEl = document.getElementById('edit-rdo-id'); if (hidEl) hidEl.value = rid; } catch(_){ }
                try { var ctxRdo = document.getElementById('edit-context-rdo'); if (ctxRdo) ctxRdo.textContent = ''; } catch(_){ }
                try { var ctxOs = document.getElementById('edit-context-os'); if (ctxOs) ctxOs.textContent = ''; } catch(_){ }
              }
            }
          }
        } catch(e){}
      }
      if (!rid) { showToast('RDO não definido para carregar', 'error'); return; }
      if (btn) { btn.classList.add('loading'); btn.setAttribute('aria-disabled','true'); btn.disabled = true; }
  var url = '/rdo/' + encodeURIComponent(rid) + '/detail/?render=editor';
      try {
        var lastTank = '';
        try { if (window && window.__last_rdo_tanque_id) lastTank = String(window.__last_rdo_tanque_id || ''); } catch(_){ lastTank = ''; }
        try { var hidTid = (document.getElementById('edit-tanque-id')||{}).value; if (!lastTank && hidTid) lastTank = String(hidTid||''); } catch(_){ }
        try { var sel = document.getElementById('edit-select-tanque'); if (!lastTank && sel && sel.value) lastTank = String(sel.value || ''); } catch(_){ }
        try { if (lastTank && window) window.__last_rdo_tanque_id = String(lastTank); } catch(_){ }
        if (lastTank) {
          url += '&tank_id=' + encodeURIComponent(lastTank);
        }
        try { console.debug && console.debug('loadEditorDetails - requesting editor fragment', { url: url, lastTank: lastTank }); } catch(_){ }
      } catch(_){ }
      var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();
      if (data && data.html) {
        try {
          var container = document.getElementById('rdo-edit-content');
          if (container) {
            container.innerHTML = data.html;
            try {
              var fragHidden = container.querySelector('#edit-tanque-id');
              if (fragHidden) {
                var globalHidden = document.querySelector('input#edit-tanque-id');
                if (globalHidden && globalHidden !== fragHidden) {
                  try { globalHidden.value = fragHidden.value || ''; } catch(_){ }
                } else if (!globalHidden) {
                  try {
                    var form = document.getElementById('form-editor') || document.getElementById('form-supervisor') || document.querySelector('form');
                    if (form) {
                      var clone = document.createElement('input');
                      clone.type = 'hidden';
                      clone.id = 'edit-tanque-id';
                      clone.name = fragHidden.name || 'tanque_id';
                      clone.value = fragHidden.value || '';
                      form.appendChild(clone);
                    }
                  } catch(_){ }
                }
                try { if (window) window.__last_rdo_tanque_id = String(fragHidden.value || ''); } catch(_){ }
              }
            } catch(_){ }
            (function bindActivities(){
              try {
                var wrapper = document.getElementById('edit-atividades-wrapper') || document.getElementById('edit-atividades-wrapper');
                if (!wrapper) return;
                try { wrapper.setAttribute('data-rdo-local-bindings', '1'); } catch(_){ }
                var addBtn = document.getElementById('edit-btn-add-atividade');
                var removeLast = document.getElementById('edit-btn-remove-last-atividade');
                function addRow(){
                  try {
                    var base = wrapper.querySelector('.activities-row');
                    if (!base) return;
                    var clone = base.cloneNode(true);
                    Array.prototype.forEach.call(clone.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; });
                    base.parentNode.insertBefore(clone, wrapper.querySelector('.activities-footer'));
                    computeModalAggregates();
                  } catch(_){}
                }
                function removeLastRow(){
                  try {
                    var rows = wrapper.querySelectorAll('.activities-row');
                    if (rows.length <= 1) {
                      // Se só existir uma linha, limpá-la em vez de bloquear a remoção
                      try { var only = rows[0]; if (only) Array.prototype.forEach.call(only.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; }); } catch(_){ }
                      computeModalAggregates();
                      return;
                    }
                    var last = rows[rows.length-1]; if (last && last.parentNode) last.parentNode.removeChild(last);
                    computeModalAggregates();
                  } catch(_){}
                }
                if (addBtn) { addBtn.addEventListener('click', function(ev){ ev.preventDefault(); addRow(); }); }
                if (removeLast) { removeLast.addEventListener('click', function(ev){ ev.preventDefault(); removeLastRow(); }); }
                wrapper.addEventListener('click', function(ev){
                  try {
                    var btn = ev.target && ev.target.closest ? ev.target.closest('.btn-remove-atividade') : null;
                    if (!btn || !wrapper.contains(btn)) return;
                    ev.preventDefault();
                    var rows = wrapper.querySelectorAll('.activities-row');
                    if (rows.length <= 1) {
                      try { var only = rows[0]; if (only) Array.prototype.forEach.call(only.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; }); } catch(_){ }
                      computeModalAggregates();
                      return;
                    }
                    var row = btn.closest('.activities-row');
                    if (row && row.parentNode) row.parentNode.removeChild(row);
                    computeModalAggregates();
                  } catch(_){}
                });
              } catch(_){}
            })();

            (function bindTeam(){
              try {
                var wrap = document.getElementById('edit-equipe-wrapper'); if (!wrap) return;
                try { wrap.setAttribute('data-rdo-local-bindings', '1'); } catch(_){ }
                function syncNow(){ try { syncPobAllForms(); } catch(_){ } }
                var add = document.getElementById('edit-btn-add-membro'); var rem = document.getElementById('edit-btn-remove-membro');
                function addMember(){ try { var base = wrap.querySelector('.team-row'); if (!base) return; var clone = base.cloneNode(true); Array.prototype.forEach.call(clone.querySelectorAll('select,input,textarea'), function(el){ if(el.tagName.toLowerCase()==='select') el.selectedIndex=0; else el.value=''; }); base.parentNode.insertBefore(clone, wrap.querySelector('.team-footer')); syncNow(); } catch(_){} }
                function removeMember(){ try { var rows = wrap.querySelectorAll('.team-row'); if (rows.length<=1) return; var last = rows[rows.length-1]; if(last && last.parentNode) last.parentNode.removeChild(last); syncNow(); } catch(_){} }
                if (add) add.addEventListener('click', function(ev){ ev.preventDefault(); addMember(); });
                if (rem) rem.addEventListener('click', function(ev){ ev.preventDefault(); removeMember(); });
                if (!wrap.__pobSyncBound) {
                  wrap.addEventListener('input', schedulePobSync, true);
                  wrap.addEventListener('change', schedulePobSync, true);
                  wrap.__pobSyncBound = true;
                }
                syncNow();
              } catch(_){}
            })();

            (function bindFotos(){
              try {
                var photoBtn = document.getElementById('edit-btn-add-foto'); var input = document.getElementById('edit-fotos');
                if (photoBtn && input) photoBtn.addEventListener('click', function(ev){ ev.preventDefault(); input.click(); });
                try { _initEditorPhotoCompression(); } catch(_){}
              } catch(_){}
            })();

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
            try { var recalc = document.getElementById('edit-btn-recalcular-calculos'); if (recalc) recalc.addEventListener('click', function(ev){ ev.preventDefault(); computeModalAggregates(); showToast('Cálculos atualizados', 'success'); }); } catch(_){}
            try { if (typeof _bindTranslationHandlers === 'function') _bindTranslationHandlers(container); } catch(_){ }
            try { if (typeof ensureEditorSubmitBound === 'function') ensureEditorSubmitBound(); } catch(_){ }
            try { if (typeof computeEditorBombeio === 'function') computeEditorBombeio(); } catch(e){}
            try { if (typeof computeEditorResSolidos === 'function') computeEditorResSolidos(); } catch(e){}
            try { if (typeof computeEditorResTotal === 'function') computeEditorResTotal(); } catch(e){}
            try { if (typeof computeEditorAccumulates === 'function') computeEditorAccumulates(); } catch(e){}

            showToast('Detalhes carregados (render)', 'success');
            return;
          }
        } catch(e){ console.warn('failed to inject html fragment', e); }
      }

      var r = data && (data.rdo || data.data || data.item) || null;
      if (!r) { showToast('Resposta sem dados do RDO', 'error'); return; }
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
      _setBoolSelectSimNaoById('edit-pt-abertura', r.pt_abertura);
      _setChecksByName('pt_turnos[]', r.pt_turnos);
      _setValById('edit-pt-manha', r.pt_num_manha);
      _setValById('edit-pt-tarde', r.pt_num_tarde);
      _setValById('edit-pt-noite', r.pt_num_noite);
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
      try {
        var entradasArr = [], saidasArr = [];
        if (r.ec_times && typeof r.ec_times === 'object') {
          for (var ii = 1; ii <= 6; ii++) {
            entradasArr.push(r.ec_times['entrada_' + ii] || '');
            saidasArr.push(r.ec_times['saida_' + ii] || '');
          }
        } else if (r.ec_times_json && typeof r.ec_times_json === 'string') {
          try {
            var parsed_ec = JSON.parse(r.ec_times_json || '{}');
            if (parsed_ec) {
              entradasArr = Array.isArray(parsed_ec.entrada) ? parsed_ec.entrada.slice(0,6) : (Array.isArray(parsed_ec.entradas) ? parsed_ec.entradas.slice(0,6) : []);
              saidasArr = Array.isArray(parsed_ec.saida) ? parsed_ec.saida.slice(0,6) : (Array.isArray(parsed_ec.saidas) ? parsed_ec.saidas.slice(0,6) : []);
            }
          } catch(e) {}
        } else if (Array.isArray(r.entrada_confinado) || Array.isArray(r.saida_confinado)) {
          entradasArr = Array.isArray(r.entrada_confinado) ? r.entrada_confinado.slice(0,6) : [];
          saidasArr = Array.isArray(r.saida_confinado) ? r.saida_confinado.slice(0,6) : [];
        } else {
          if (r.entrada_confinado) entradasArr.push(r.entrada_confinado);
          if (r.saida_confinado) saidasArr.push(r.saida_confinado);
          if ((entradasArr.length === 0 || saidasArr.length === 0) && r.ec_raw && typeof r.ec_raw === 'object') {
            var eRaw = r.ec_raw.entrada || r.ec_raw.entrada_list || r.ec_raw.entradas || r.ec_raw.entrada_confinado || [];
            var sRaw = r.ec_raw.saida || r.ec_raw.saida_list || r.ec_raw.saidas || r.ec_raw.saida_confinado || [];
            if (Array.isArray(eRaw) && eRaw.length) entradasArr = eRaw.slice(0,6);
            if (Array.isArray(sRaw) && sRaw.length) saidasArr = sRaw.slice(0,6);
          }
        }
        var maxn = Math.max(entradasArr.length, saidasArr.length, 6);
        for (var k = 0; k < maxn; k++) { if (typeof entradasArr[k] === 'undefined') entradasArr[k] = ''; if (typeof saidasArr[k] === 'undefined') saidasArr[k] = ''; }
        _setECGrid(entradasArr, saidasArr);
      } catch(_){ try { _setECGrid(r.entrada_confinado, r.saida_confinado); } catch(_){} }
      _setValById('edit-operadores', r.operadores_simultaneos);
      _setValById('edit-h2s', r.h2s_ppm);
      _setValById('edit-lel', r.lel);
      _setValById('edit-co', r.co_ppm);
      _setValById('edit-o2', r.o2_percent);
      if (typeof r.sentido_limpeza_bool !== 'undefined' && r.sentido_limpeza_bool !== null) {
        _setBoolSelectTrueFalseById('edit-sentido', r.sentido_limpeza_bool);
      } else {
        try {
          var s = r.sentido_limpeza;
          if (typeof s === 'string') {
            var sl = s.toLowerCase();
            if (sl.indexOf('vante') !== -1 && sl.indexOf('ré') !== -1) {
              _setBoolSelectTrueFalseById('edit-sentido', true);
            } else if (sl.indexOf('ré') !== -1 && sl.indexOf('vante') !== -1) {
              _setBoolSelectTrueFalseById('edit-sentido', false);
            } else {
              _setSelectById('edit-sentido', s);
            }
          } else {
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
      try { if (typeof computeEditorPercentuais === 'function') computeEditorPercentuais(); } catch(_){ }
  try { if (typeof computeEditorBombeio === 'function') computeEditorBombeio(); } catch(e){}
  try { if (typeof computeEditorResTotal === 'function') computeEditorResTotal(); } catch(e){}
  try { if (typeof computeEditorResSolidos === 'function') computeEditorResSolidos(); } catch(e){}
  try { if (typeof computeEditorAccumulates === 'function') computeEditorAccumulates(); } catch(e){}
      _setValById('edit-total-atividades', r.total_atividade_min);
      _setValById('edit-total-confinado', r.total_confinado_min);
      _setValById('edit-total-abertura-pt', r.total_abertura_pt_min);
      _setValById('edit-total-atividades-efetivas', r.total_atividades_efetivas_min);
      _setValById('edit-total-n-efetivo-confinado', r.total_n_efetivo_confinado_min);
      _setValById('edit-total-nao-efetivas-fora', r.total_nao_efetivas_fora_min);
      _setValById('edit-observacoes-pt', r.observacoes);
      if (r.observacoes_en) _setValById('edit-observacoes-en', r.observacoes_en);
      _setValById('edit-planejamento-pt', r.planejamento);
      if (r.planejamento_en) _setValById('edit-planejamento-en', r.planejamento_en);
      if (Array.isArray(r.equipe)) { _fillTeam(r.equipe); }
      else if (Array.isArray(r.equipe_nomes) && Array.isArray(r.equipe_funcoes)) {
        var eq = []; var n = Math.max(r.equipe_nomes.length, r.equipe_funcoes.length);
        for (var i=0;i<n;i++){ eq.push({ nome: r.equipe_nomes[i], funcao: r.equipe_funcoes[i] }); }
        _fillTeam(eq);
      }
      if (Array.isArray(r.fotos)) _renderExistingPhotos(r.fotos);
      try {
        if (Array.isArray(r.atividades) && r.atividades.length) {
          var wrapperRows = document.querySelectorAll('#edit-atividades-wrapper .activities-row');
          var rowsArr = Array.prototype.slice.call(wrapperRows || []);
          var need = r.atividades.length - rowsArr.length;
          var wrapper = document.getElementById('edit-atividades-wrapper');
          if (need > 0 && wrapper && rowsArr.length) {
            var base = rowsArr[rowsArr.length-1];
            for (var c=0;c<need;c++){
              try {
                var clone = base.cloneNode(true);
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
          try { computeModalAggregates(); } catch(_){ }
        }
      } catch(_){ }
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
            try {
              var _cPt = (document.getElementById('edit-ciente-observacoes-pt') || null);
              var _cEn = (document.getElementById('edit-ciente-observacoes-en') || null);
              if (_cPt && _cEn && (String(_cPt.value||'').trim() !== '') && String(_cEn.value||'').trim() === '') {
                try { _cPt.dispatchEvent(new Event('input', { bubbles: true })); } catch(_){ }
              }
            } catch(_){ }
  showToast('Detalhes carregados', 'success');
    } catch(err){
      showToast('Falha ao carregar detalhes', 'error');
    } finally {
      var btn = document.getElementById('edit-btn-load-details');
      if (btn) { btn.classList.remove('loading'); btn.removeAttribute('aria-disabled'); btn.disabled = false; }
    }
  }
  try {
    document.addEventListener('change', function(ev){
      try {
        var el = ev && ev.target ? ev.target : null;
        if (!el) return;
        if (el.id === 'edit-select-tanque' || el.matches && el.matches('#edit-select-tanque')) {
          var val = el.value || '';
          try { var hid = document.getElementById('edit-tanque-id'); if (hid) hid.value = val; } catch(_){ }
          try { if (window) window.__last_rdo_tanque_id = String(val || ''); } catch(_){ }
          try { console.debug && console.debug('edit-select-tanque changed, reloading fragment with tank_id=', val); } catch(_){ }
          try { if (typeof loadEditorDetails === 'function') { loadEditorDetails(); } } catch(_){ }
        }
      } catch(_){ }
    }, false);
  } catch(_){ }
  onReady(function(){
    try { window.RDO = window.RDO || {}; } catch(_){ }
    try { window.RDO.openSupervisorModal = openSupervisorModal; } catch(_){ }
    try { window.RDO.computeModalAggregates = computeModalAggregates; } catch(_){ }
    try { window.RDO.openEditorModal = openEditorModal; } catch(_){ }
    try { if (!window.rdoOpenSupervisorModal) window.rdoOpenSupervisorModal = openSupervisorModal; } catch(_){ }
    try { if (!window.computeModalAggregates) window.computeModalAggregates = computeModalAggregates; } catch(_){ }
  try { if (!window.openEditorModal) window.openEditorModal = openEditorModal; } catch(_){ }
  try { if (!window.computeEditorResTotal) window.computeEditorResTotal = computeEditorResTotal; } catch(_){ }
  try { if (!window.computeEditorResSolidos) window.computeEditorResSolidos = computeEditorResSolidos; } catch(_){ }
  try { if (!window.computeEditorAccumulates) window.computeEditorAccumulates = computeEditorAccumulates; } catch(_){ }
    try { window.ai = window.ai || {}; } catch(_){}
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
        try { if (typeof _bindTranslationHandlers === 'function') _bindTranslationHandlers(document); } catch(_){ }
      }
      document.addEventListener('click', function(ev){
        try {
          if (ev.target && ev.target.closest && ev.target.closest('[data-open="supervisor"], .open-supervisor, .btn-rdo.open-supervisor')) return;
        } catch(_){ }
        var btn = ev.target && ev.target.closest ? ev.target.closest('.action-btn.edit, .action-btn.open-editor, .action-btn.edit-editor, [data-open="editor"]') : null;
        if (!btn) return;
        ev.preventDefault();
        try {
          var tr = btn.closest('tr');
          var rid = tr && (tr.getAttribute('data-rdo-id') || (tr.dataset && (tr.dataset.rdoId || tr.dataset.rdo_id)));
          var tid = tr && (tr.getAttribute('data-tanque-id') || (tr.dataset && (tr.dataset.tanqueId || tr.dataset.tanque_id)));
          var osid = tr && (tr.getAttribute('data-os-id') || (tr.dataset && tr.dataset.osId)) || '';
          var osnum = tr && (tr.getAttribute('data-numero-os') || (tr.dataset && tr.dataset.numeroOs)) || '';
          try { window.__last_rdo_row_id = rid || ''; } catch(_){ }
          try { window.__last_rdo_tanque_id = tid || ''; } catch(_){ }
          openEditorModal({ rdo_id: rid || '', tanque_id: tid || '', os_id: osid || '', numero_os: osnum || '' });
        } catch(e){ openEditorModal({}); }
      }, true);
    } catch(_){ }
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
            el.value = values[0];
          });
        } catch(_){}
      }
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
        Object.keys(grouped).forEach(function(name){ params.delete(name); });
        Object.keys(grouped).forEach(function(name){ grouped[name].forEach(function(v){ params.append(name, v); }); });
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
      var clearBtn = document.getElementById('btn_clear_filters');
      if (clearBtn && filtersForm) {
        clearBtn.addEventListener('click', function(){
          try {
            filtersForm.reset();
            updateFilterBadge();
            document.dispatchEvent(new CustomEvent('rdo:filters:clear'));
            showToast('Filtros limpos', 'success');
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
          var params = buildParamsFromForm();
          var q = params.toString();
          window.location.search = q ? ('?' + q) : window.location.pathname;
        });
      }
      if (filtersForm) {
        prefillFiltersFromQuery();
        try {
          var hasQuery = (window.location.search || '').replace(/^\?/, '').length > 0;
          if (!hasQuery) { var stored = _loadFilters(); if (stored) _applyToForm(stored); }
        } catch(_){ }
        filtersForm.addEventListener('input', function(){ updateFilterBadge(); }, { passive: true });
        filtersForm.addEventListener('change', function(){ updateFilterBadge(); _saveFilters(); }, { passive: true });
        filtersForm.addEventListener('submit', function(ev){ ev.preventDefault(); if (applyBtn) applyBtn.click(); else {
          var params = buildParamsFromForm(); var q = params.toString(); window.location.search = q ? ('?' + q) : window.location.pathname; }
        });
        setTimeout(updateFilterBadge, 50);
      }
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
      if (clearBtn) {
        clearBtn.addEventListener('click', function(){ try { localStorage.removeItem(FILTERS_STORAGE_KEY); } catch(_){ } });
      }
    } catch(e){ console.warn('filters init failed', e); }
    try {
      var notifBtn = document.getElementById('rdo-notification-btn');
      var notifCountEl = notifBtn ? notifBtn.querySelector('.count') : null;
      var cta = document.getElementById('rdo-mobile-cta');
      var ctaPopover = cta ? cta.querySelector('.rdo-cta-popover') : null;
      var ctaClose = document.getElementById('rdo-cta-close');
      var ctaClear = document.getElementById('rdo-cta-clear-cards');

      function updateNotificationCount(n){
        try {
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
          if (!Number.isFinite(count) || count < 0) count = 0;
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
          var fallbackUrl = '/rdo/pending_os_json/';
          try { if (typeof url === 'string') url = url.trim(); } catch(_){ }
          if (!url || url === '/api/rdo/pending_os/') {
            if (!url) { console.debug && console.debug('rdo: fetchPending - no meta url found, using fallback'); }
            url = fallbackUrl;
          }
          console.debug && console.debug('rdo: fetchPending - fetching', url);
          var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With':'XMLHttpRequest' } });
          console.debug && console.debug('rdo: fetchPending - response status', resp.status, resp.statusText);
          if (!resp.ok) {
            console.warn && console.warn('rdo: fetchPending - non-ok response', resp.status);
            if (url !== fallbackUrl) {
              try { console.debug && console.debug('rdo: fetchPending - retrying fallback', fallbackUrl); } catch(_){ }
              try {
                resp = await fetch(fallbackUrl, { credentials: 'same-origin', headers: { 'X-Requested-With':'XMLHttpRequest' } });
                url = fallbackUrl;
                console.debug && console.debug('rdo: fetchPending - fallback response status', resp.status, resp.statusText);
              } catch(_){ }
            }
            if (!resp.ok) return [];
          }
          var data = null;
          try { data = await resp.json(); } catch(e) { console.warn && console.warn('rdo: fetchPending - failed to parse JSON', e); data = null; }
          var list = (data && (data.data || data.items || data.list)) || [];
          var arr = Array.isArray(list) ? list : [];
          console.debug && console.debug('rdo: fetchPending - parsed list length', arr.length, 'raw:', list);
          try {
            window.__rdo_pending_list = arr;
            window.__rdo_pending_count = arr.length || 0;
            try { localStorage.setItem('rdo_pending_count', String(window.__rdo_pending_count)); } catch(_){ }
            try { localStorage.setItem('rdo_pending_list', JSON.stringify(arr)); } catch(_){ }
            try { window.__rdo_pending_last_status = resp.status; } catch(_){ }
          } catch(_){ }
          try { if (typeof populateOsSelect === 'function') populateOsSelect(); } catch(_){ }
          return arr;
        } catch(e){
          try { window.__rdo_pending_last_error = String(e && e.message ? e.message : e); } catch(_){ }
          return [];
        }
      }

      function populateOsSelect(){
        try {
          var sel = document.getElementById('rdo-cta-os-select');
          if (!sel) return;
          if (sel.dataset && sel.dataset.populated === '1') return;
          var list = window.__rdo_pending_list || [];
          var knownCount = (window.__rdo_pending_count != null) ? window.__rdo_pending_count : (list.length || 0);
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
              var osId = item.id || item.os_id || '';
              var parts = [opt.dataset.osNum, opt.dataset.empresa, opt.dataset.unidade].filter(function(x){ return !!x; });
              if (osId) {
                if (opt.dataset.osNum && String(opt.dataset.osNum) !== String(osId)) {
                  parts[0] = (opt.dataset.osNum || '') + ' (ID ' + osId + ')';
                } else if (!opt.dataset.osNum) {
                  parts.unshift('ID ' + osId);
                }
              }
              var txt = parts.join(' • ');
              opt.textContent = txt || (opt.dataset.osNum || (osId ? 'ID ' + osId : opt.value) || '—');
              sel.appendChild(opt);
            } catch(_){}};
          } else if (knownCount > 0) {
            var rows = document.querySelectorAll('table tbody tr[data-os-id], table tbody tr[data-numero-os], table tbody tr[data-numero]');
            if (rows && rows.length) {
              var seen2 = Object.create(null);
              Array.prototype.forEach.call(rows, function(tr){ try {
                var rdoId = tr.getAttribute('data-rdo-id') || tr.getAttribute('data-rdoid') || tr.dataset && (tr.dataset.rdoId || tr.dataset.rdo_id) || '';
                var numero = tr.getAttribute('data-numero-os') || tr.getAttribute('data-numero') || tr.dataset && (tr.dataset.numeroOs || tr.dataset.numero) || '';
                var empresa = tr.getAttribute('data-empresa') || (tr.dataset && tr.dataset.empresa) || '';
                var unidade = tr.getAttribute('data-unidade') || (tr.dataset && tr.dataset.unidade) || '';
                var key = numero || rdoId; if (!key || seen2[key]) return; seen2[key]=true;
                var opt = document.createElement('option'); opt.value = rdoId || numero || ''; opt.dataset.rdoId = rdoId || ''; opt.dataset.osNum = numero || ''; opt.dataset.empresa = empresa; opt.dataset.unidade = unidade;
                var osId2 = rdoId || '';
                var parts2 = [opt.dataset.osNum, opt.dataset.empresa, opt.dataset.unidade].filter(Boolean);
                if (osId2) {
                  if (opt.dataset.osNum && String(opt.dataset.osNum) !== String(osId2)) parts2[0] = (opt.dataset.osNum || '') + ' (ID ' + osId2 + ')';
                  else if (!opt.dataset.osNum) parts2.unshift('ID ' + osId2);
                }
                opt.textContent = parts2.join(' • ');
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
          if (!sel.__rdoPopBound) {
            sel.addEventListener('change', function(ev){ try {
              var opt = ev.target && ev.target.selectedOptions && ev.target.selectedOptions[0]; if (!opt) return;
              var rdoId = opt.dataset.rdoId || opt.value || '';
              var numeroOs = opt.dataset.osNum || opt.textContent || '';
              var empresa = opt.dataset.empresa || '';
              var unidade = opt.dataset.unidade || '';
              var ctx = { rdo_id: rdoId, os_id: opt.value || '', numero_os: numeroOs, os: numeroOs, empresa: empresa, unidade: unidade, supervisor: opt.dataset.supervisor || '' };
              try { if (typeof window.rdoOpenSupervisorModal === 'function') window.rdoOpenSupervisorModal(ctx); else if (typeof openSupervisorModal === 'function') openSupervisorModal(ctx); } catch(_){ }
              try { ev.target.selectedIndex = -1; } catch(_){}
            } catch(_){ } }, false);
            sel.__rdoPopBound = true;
          }
        } catch(e){ console.warn('populateOsSelect failed', e); }
      }

      function openCTA(){
        if (!cta) return;
        if (window.innerWidth >= 900) {
          cta.setAttribute('aria-hidden','true');
          return;
        }
        cta.setAttribute('aria-hidden','false');
      }
      function closeCTA(){ if (!cta) return; cta.setAttribute('aria-hidden','true'); }

      async function openNotifications(){
        if (window.innerWidth >= 900) return;
        if (!cta || !ctaPopover) { showToast('Interface de notificações indisponível', 'error'); return; }
        ctaPopover.innerHTML = '<div class="loading" style="padding:10px;">Carregando pendências...</div>';
        openCTA();
        console.debug && console.debug('rdo: openNotifications - fetching pending items');
        var items = await fetchPending();
        console.debug && console.debug('rdo: openNotifications - items length after fetch', (items && items.length) || 0);
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
        var ul = document.createElement('ul');
        ul.style.listStyle = 'none'; ul.style.padding = '8px'; ul.style.margin = '0'; ul.style.maxHeight='220px'; ul.style.overflow='auto';
        items.forEach(function(it){
          try {
            var li = document.createElement('li'); li.style.margin='6px 0';
            var btn = document.createElement('button'); btn.type='button'; btn.className='btn-rdo small';
            try { btn.classList.add('rdo-os-item'); } catch(_){ }
            var os = it.numero_os || it.os || '';
            var osId = it.os_id || it.id || '';
            var empresa = it.empresa || it.cliente || '';
            var unidade = it.unidade || '';
            var label = '';
            if (os) {
              label = os;
              if (osId && String(osId) !== String(os)) label += ' (ID ' + osId + ')';
            } else if (osId) {
              label = 'ID ' + osId;
            } else {
              label = '-';
            }
            btn.textContent = [label, empresa, unidade].filter(Boolean).join(' • ');
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
            var lists = document.querySelectorAll('.rdo-mobile-rdo-list .rdo-summary');
            Array.prototype.forEach.call(lists, function(card, idx){ if (idx>0 && card.parentNode) card.parentNode.removeChild(card); });
          }
          showToast('Cartões limpos', 'success');
        } catch(e){}
      });
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
            var finalizedOsKeys = Object.create(null);
            try {
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
            var cards = document.querySelectorAll('.rdo-mobile-card, .rdo-mobile-item');
            Array.prototype.forEach.call(cards, function(card){
              try{
                var cardOsId = (card.getAttribute('data-os-id') || '').toString();
                var cardNumOs = (card.getAttribute('data-os') || card.getAttribute('data-numero-os') || '').toString();
                var cardSt = (card.getAttribute('data-status-geral') || '').toString();
                if (cardSt && finalRe.test(cardSt)){
                  if (card.parentNode) card.parentNode.removeChild(card);
                  return;
                }
                if ((cardOsId && finalizedOsKeys[cardOsId]) || (!cardOsId && cardNumOs && finalizedOsKeys[cardNumOs])){
                  if (card.parentNode) card.parentNode.removeChild(card);
                  return;
                }
              }catch(e){ }
            });
      try { window.updateNotificationCount = updateNotificationCount; } catch(_){}
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
        try { setTimeout(doFetchAndUpdate, 350); } catch(e){ doFetchAndUpdate(); }
        try { setTimeout(doFetchAndUpdate, 1200); } catch(_){ }
        try {
          window.addEventListener('focus', function(){ try { console.debug && console.debug('rdo: window focus - refreshing pending'); doFetchAndUpdate(); } catch(_){} });
        } catch(_){ }
        try {
          document.addEventListener('visibilitychange', function(){ try { if (document.visibilityState === 'visible') { console.debug && console.debug('rdo: visibilitychange visible - refreshing pending'); doFetchAndUpdate(); } } catch(_){} });
        } catch(_){ }
      })();
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

  (function(){
    try {
      var btn = document.getElementById('btn-add-tanque');
      if (!btn) return;
      btn.addEventListener('click', async function(ev){
        ev.preventDefault();
        var form = document.getElementById('form-supervisor');
        if (!form) return;
        var rdoVal = (document.getElementById('sup-rdo')||{}).value || '';
        var contratoVal = (document.getElementById('sup-contrato-po')||{}).value || '';
        if (!rdoVal || !contratoVal) {
          if (!rdoVal && document.getElementById('sup-rdo')) document.getElementById('sup-rdo').focus();
          else if (!contratoVal && document.getElementById('sup-contrato-po')) document.getElementById('sup-contrato-po').focus();
          return;
        }
        btn.disabled = true;
        var origText = btn.textContent;
        btn.textContent = 'Salvando...';

        try {
          var payload = buildSupervisorFormData(form);
          try {
            var currentRdo = (document.getElementById('sup-rdo')||{}).value || '';
            if (currentRdo) payload.append('rdo_contagem', String(currentRdo));
            if (currentRdo) { payload.append('rdo', String(currentRdo)); payload.append('rdo_override', String(currentRdo)); }
            console.debug && console.debug('rdo.core: sending rdo_contagem', currentRdo);
          } catch(e) { console.warn('failed to append rdo_contagem to payload', e); }
          var url = '/rdo/create_ajax/';
          var headers = { 'X-Requested-With': 'XMLHttpRequest' };
          var csrf = '';
          try { csrf = getCSRF(form) || ''; } catch(e) { csrf = ''; }
          if (csrf) headers['X-CSRFToken'] = csrf;

          var resp = await fetch(url, { method: 'POST', body: payload, credentials: 'same-origin', headers: headers });
          var data = null;
          if (resp && resp.ok) {
            try { data = await resp.json(); } catch(e) { data = null; }
          }
          var table = document.querySelector('.tabela_conteiner table');
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
              <td class="action-cell"><button class="action-btn pdf-all" type="button" disabled aria-disabled="true" title="OS não identificada"><span class="material-icons" aria-hidden="true">picture_as_pdf</span></button></td>
            `;
            var first = tbody.querySelector('tr');
            tbody.insertBefore(newTr, first || null);
          }
          try {
            var cnt = parseInt(localStorage.getItem('rdo_pending_count')||'0',10);
            cnt = Math.max(0, cnt-1);
            localStorage.setItem('rdo_pending_count', String(cnt));
            if (window.updateNotificationCount) window.updateNotificationCount();
          } catch(e){}
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
              el.value = '';
            });
            try {
              var hid = document.getElementById('sup-rdo-id');
              if (hid) {
                hid.value = (data && data.id) ? String(data.id) : (hid.value || '');
              }
            } catch(e) { console.warn('failed to set sup-rdo-id', e); }
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
  try {
    var lockStyleId = 'rdo-locked-style';
    if (!document.getElementById(lockStyleId)) {
  var css = '\n.rdo-locked { opacity: 0.6; position: relative; }\n.rdo-locked .rdo-lock-icon { position: absolute; right: 8px; top: 8px; font-family: "Material Icons"; font-size: 18px; color: #444; }\n.rdo-locked .open-supervisor, .rdo-locked .action-btn.edit { opacity: 0.5; }\n/* allow explicit edits when element has allow-edit class inside locked rows */\n.rdo-locked .allow-edit, .rdo-locked .allow-edit * { pointer-events: auto !important; opacity: 1 !important; }\n';
      var s = document.createElement('style'); s.id = lockStyleId; s.type = 'text/css'; s.appendChild(document.createTextNode(css)); document.head.appendChild(s);
    }
  } catch(_){ }
  try {
    document.addEventListener('rdo:saved', function(ev){
      try {
        var detail = (ev && ev.detail) || {};
        var mode = detail.mode || '';
        var resp = detail.response || {};
        if (mode !== 'create') return;
        var payload = resp.rdo || resp || {};
        var osId = payload.ordem_servico_id || payload.os_id || payload.ordem_servico || '';
        var rdoCount = payload.rdo || payload.rdo_contagem || payload.rdo_count || '';
        var n = parseInt(String(rdoCount).replace(/[^0-9]/g,''), 10);
        if (!isFinite(n) || n <= 1) return;
        var trSelectorBase = '';
        if (osId) trSelectorBase = '[data-os-id="' + String(osId) + '"]';
        var numOs = payload.numero_os || payload.numero || payload.num_os || '';

        function lockEl(el){ try { if (!el) return; if (el.classList && el.classList.contains('rdo-locked')) return; el.classList.add('rdo-locked');} catch(_){ } }
        try {
          var rowSel = 'tr[data-rdo-count]';
          if (trSelectorBase) rowSel = 'tr' + trSelectorBase + '[data-rdo-count]';
          var rows = document.querySelectorAll(rowSel);
          Array.prototype.forEach.call(rows, function(r){ try {
            var rc = parseInt(String(r.getAttribute('data-rdo-count') || (r.dataset && r.dataset.rdoCount) || '').replace(/[^0-9]/g,''),10) || 0;
            if (rc && rc < n) lockEl(r);
          } catch(_){} });
        } catch(_){ }
        try {
          var cardSel = '.rdo-mobile-card[data-rdo-count], .rdo-mobile-item[data-rdo-count]';
          if (trSelectorBase) cardSel = '.rdo-mobile-card' + trSelectorBase + '[data-rdo-count], .rdo-mobile-item' + trSelectorBase + '[data-rdo-count]';
          var cards = document.querySelectorAll(cardSel);
          Array.prototype.forEach.call(cards, function(c){ try {
            var rc = parseInt(String(c.getAttribute('data-rdo-count') || (c.dataset && c.dataset.rdoCount) || '').replace(/[^0-9]/g,''),10) || 0;
            if (rc && rc < n) lockEl(c);
          } catch(_){} });
          if ((!cards || !cards.length) && numOs) {
            var cardSel2 = '.rdo-mobile-card[data-os="' + String(numOs) + '"][data-rdo-count], .rdo-mobile-item[data-os="' + String(numOs) + '"][data-rdo-count]';
            var cards2 = document.querySelectorAll(cardSel2);
            Array.prototype.forEach.call(cards2, function(c){ try { var rc = parseInt(String(c.getAttribute('data-rdo-count') || (c.dataset && c.dataset.rdoCount) || '').replace(/[^0-9]/g,''),10) || 0; if (rc && rc < n) lockEl(c); } catch(_){} });
          }
        } catch(_){ }
      } catch(_){ }
    }, false);
  } catch(_){ }
  document.addEventListener('click', async function(ev){
    try{
      var target = ev.target || ev.srcElement;
      if (!target) return;
      var btn = (target.closest && target.closest('#btn-add-tanque')) || null;
      if (!btn) return;
      ev.preventDefault();

      var form = document.getElementById('form-supervisor');
      if (!form) {
        console.warn('add-tank: form-supervisor não encontrado');
        return;
      }
      var hid = document.getElementById('sup-rdo-id') || document.getElementById('edit-rdo-id');
      var rdoId = hid && hid.value ? String(hid.value).trim() : null;
      if (!rdoId) {
        showToast('RDO ainda não criado. Use "Salvar" primeiro.', 'error');
        return;
      }
  var tankNames = ['tanque_codigo','tanque_nome','tipo_tanque','numero_compartimento','gavetas','patamar','volume_tanque_exec','servico_exec','metodo_exec','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','tempo_bomba','ensacamento_dia','ensacamento_cumulativo','icamento_dia','icamento_cumulativo','cambagem_dia','sentido_limpeza','cambagem_cumulativo','tambores_dia','residuos_solidos','residuos_totais','total_liquido','total_liquido_acu','residuos_solidos_acu','avanco_limpeza','avanco_limpeza_fina','percentual_limpeza_diario','percentual_limpeza_cumulativo','percentual_limpeza_fina_cumulativo','percentual_avanco','percentual_avanco_cumulativo'];
      var fd = new FormData();
      tankNames.forEach(function(n){
        try{
          var el = form.querySelector('[name="'+n+'"]');
          if (el && typeof el.value !== 'undefined') fd.append(n, el.value);
        }catch(e){}
      });
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
          try{ document.dispatchEvent(new CustomEvent('rdo:tank:added', { detail: { tank: tank, raw: data } })); } catch(e){}
          try{ if (typeof _appendSavedTankSummary === 'function' && tank) _appendSavedTankSummary(tank); }catch(e){}
          showToast((data && data.message) ? data.message : 'Tanque adicionado', 'success');
          try {
            var flag = form.querySelector('input[name="rdo_has_tanks"]');
            if (!flag) { flag = document.createElement('input'); flag.type = 'hidden'; flag.name = 'rdo_has_tanks'; form.appendChild(flag); }
            flag.value = '1';
            try { if (form && form.classList) form.classList.add('has-tank-additions'); } catch(_){}
          } catch(_){ }
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

  // Delegated handler: abrir RDO em nova aba quando clicar no botão de visualização
  try {
    document.addEventListener('click', function(ev){
      try {
        var target = ev.target || ev.srcElement;
        if (!target || !target.closest) return;
        var btn = target.closest('.action-btn.view');
        if (!btn) return;
        ev.preventDefault();
        var tr = btn.closest('tr');
        var rdoId = '';
        try { if (tr) rdoId = tr.getAttribute('data-rdo-id') || (tr.dataset && (tr.dataset.rdoId || tr.dataset.rdo_id)) || ''; } catch(_){ rdoId = ''; }
        if (rdoId) {
          try { window.open('/rdo/' + encodeURIComponent(rdoId) + '/page/', '_blank'); } catch(_){ window.location = '/rdo/' + encodeURIComponent(rdoId) + '/page/'; }
          return;
        }
        // fallback: check mobile card structure
        var card = btn.closest('.rdo-mobile-card, .rdo-mobile-item');
        if (card) {
          try { rdoId = card.getAttribute('data-rdo-id') || (card.dataset && (card.dataset.rdoId || card.dataset.rdo_id)) || ''; } catch(_){ rdoId = ''; }
          if (rdoId) {
            try { window.open('/rdo/' + encodeURIComponent(rdoId) + '/page/', '_blank'); } catch(_){ window.location = '/rdo/' + encodeURIComponent(rdoId) + '/page/'; }
            return;
          }
        }
        // If no rdoId found, try to open by RDO number in cell
        try {
          if (tr) {
            var rdoNum = tr.getAttribute('data-rdo-count') || (tr.dataset && (tr.dataset.rdoCount || tr.dataset.rdo)) || '';
            if (rdoNum) {
              try { window.open('/rdo/find/?rdo=' + encodeURIComponent(rdoNum), '_blank'); } catch(_){ window.location = '/rdo/find/?rdo=' + encodeURIComponent(rdoNum); }
            }
          }
        } catch(_){ }
      } catch(_){ }
    }, false);
  } catch(_){ }

  // Delegated handler: baixar PDF com todos os RDOs da OS (client-side)
  function _loadScriptOnce(src){
    return new Promise(function(resolve, reject){
      try{
        var existing = document.querySelector('script[data-rdo-pdf-src="' + src + '"]');
        if (existing) return resolve();
        var s = document.createElement('script');
        s.src = src;
        s.async = true;
        s.setAttribute('data-rdo-pdf-src', src);
        s.onload = function(){ resolve(); };
        s.onerror = function(){ reject(new Error('load_failed')); };
        document.head.appendChild(s);
      }catch(e){ reject(e); }
    });
  }

  function _ensurePdfLibs(){
    var tasks = [];
    if (!window.html2canvas){
      tasks.push(_loadScriptOnce('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js'));
    }
    if (!((window.jspdf && window.jspdf.jsPDF) || window.jsPDF)){
      tasks.push(_loadScriptOnce('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js'));
    }
    return Promise.all(tasks);
  }

  function _getJsPdfCtor(){
    return (window.jspdf && window.jspdf.jsPDF) ? window.jspdf.jsPDF : (window.jsPDF || null);
  }

  function _ensureRdoCss(){
    return new Promise(function(resolve){
      try{
        var href = '/static/css/page_rdo.css';
        var existing = document.querySelector('link[data-rdo-pdf-css=\"1\"]');
        if (existing){
          if (existing.getAttribute('data-loaded') === '1') return resolve({ link: existing, inserted: false });
          existing.addEventListener('load', function(){ existing.setAttribute('data-loaded','1'); resolve({ link: existing, inserted: false }); }, { once: true });
          existing.addEventListener('error', function(){ existing.setAttribute('data-loaded','1'); resolve({ link: existing, inserted: false }); }, { once: true });
          return;
        }
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        link.setAttribute('data-rdo-pdf-css', '1');
        link.onload = function(){ link.setAttribute('data-loaded','1'); resolve({ link: link, inserted: true }); };
        link.onerror = function(){ link.setAttribute('data-loaded','1'); resolve({ link: link, inserted: true }); };
        document.head.appendChild(link);
      }catch(e){ resolve({ link: null, inserted: false }); }
    });
  }

  // UI overlay de progresso para exportação de PDF
  (function(){
    var __pdfProgressEl = null;
    window._showPdfProgress = function(text, pct){
      try{
        if (!__pdfProgressEl){
          __pdfProgressEl = document.createElement('div');
          __pdfProgressEl.id = 'rdo-pdf-progress-overlay';
          __pdfProgressEl.style.position = 'fixed';
          __pdfProgressEl.style.right = '20px';
          __pdfProgressEl.style.top = '20px';
          __pdfProgressEl.style.zIndex = '99999';
          __pdfProgressEl.style.minWidth = '260px';
          __pdfProgressEl.style.padding = '10px 12px';
          __pdfProgressEl.style.background = 'rgba(0,0,0,0.75)';
          __pdfProgressEl.style.color = '#fff';
          __pdfProgressEl.style.borderRadius = '6px';
          __pdfProgressEl.style.fontSize = '13px';
          __pdfProgressEl.style.boxShadow = '0 2px 10px rgba(0,0,0,0.5)';
          __pdfProgressEl.innerHTML = '<div class="title"></div><div style="height:8px;margin-top:8px;background:#333;border-radius:4px;overflow:hidden"><div class="bar" style="height:100%;width:0;background:#4caf50"></div></div>';
          document.body.appendChild(__pdfProgressEl);
        }
        try{ __pdfProgressEl.querySelector('.title').textContent = text || ''; }catch(_){ }
        try{ var b = __pdfProgressEl.querySelector('.bar'); if (b && typeof pct === 'number') b.style.width = Math.max(0,Math.min(100,pct)) + '%'; }catch(_){ }
      }catch(_){ }
    };
    window._hidePdfProgress = function(){ try{ if (__pdfProgressEl && __pdfProgressEl.parentNode) __pdfProgressEl.parentNode.removeChild(__pdfProgressEl); __pdfProgressEl = null; }catch(_){ } };
  })();

  // Util: fetch em pool concorrente (limita número de requests simultâneos)
  async function _parallelFetchPages(list, concurrency, onProgress){
    var results = new Array(list.length);
    var idx = 0;
    concurrency = Math.max(1, Math.floor(concurrency || 3));
    var workers = [];
    for (var w = 0; w < concurrency; w++){
      workers.push((async function(workerId){
        while(true){
          var i = idx++;
          if (i >= list.length) break;
          var rid = list[i] && list[i].id ? list[i].id : null;
          try{
            if (onProgress) onProgress('Baixando RDOs: ' + (i+1) + '/' + list.length, (i/list.length)*100);
            var pageUrl = '/rdo/' + encodeURIComponent(rid) + '/page/';
            var resp = await fetch(pageUrl, { credentials: 'same-origin' });
            if (!resp.ok) { results[i] = null; continue; }
            var html = await resp.text();
            results[i] = { id: rid, html: html };
          }catch(e){ results[i] = null; }
        }
      })(w));
    }
    await Promise.all(workers);
    return results;
  }

  function _waitImages(root){
    try{
      var imgs = Array.prototype.slice.call(root.querySelectorAll('img'));
      if (!imgs.length) return Promise.resolve();
      return Promise.all(imgs.map(function(img){
        if (img.complete) return Promise.resolve();
        return new Promise(function(res){ img.onload = img.onerror = function(){ res(); }; });
      }));
    }catch(_){ return Promise.resolve(); }
  }

  async function _fetchOsRdos(osId){
    var url = '/api/rdo/os/' + encodeURIComponent(osId) + '/rdos/';
    var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    var data = null;
    try { data = await resp.json(); } catch(_){ data = null; }
    if (!resp.ok || !data || !data.success){
      var msg = (data && data.error) ? data.error : 'Falha ao obter RDOs da OS';
      throw new Error(msg);
    }
    return data;
  }

  async function _exportOsRdosPdf(osId, osNumero){
    try{
      showToast('Gerando PDF da OS... aguarde.', 'info');
      // Ajustes de compactação do PDF (equilíbrio entre legibilidade e tamanho)
      // captureScale menor => menos pixels => PDF menor
      // jpegQuality menor => mais compressão => PDF menor
      var captureScale = 0.95;
      var jpegQuality = 0.68;
      var pdfImageCompression = 'FAST';
      var prevBodyClass = '';
      try { prevBodyClass = document.body.className || ''; } catch(_){ prevBodyClass = ''; }
      try { document.body.classList.add('exporting-pdf'); } catch(_){ }
      var data = await _fetchOsRdos(osId);
      var list = (data && data.rdos) ? data.rdos : [];
      if (!list.length){
        showToast('Nenhum RDO encontrado para esta OS.', 'error');
        return;
      }
      var cssRef = await _ensureRdoCss();
      await _ensurePdfLibs();
      var jsPDFCtor = _getJsPdfCtor();
      if (!jsPDFCtor || !window.html2canvas){
        showToast('Bibliotecas de PDF não carregadas. Tente novamente.', 'error');
        return;
      }
      // Forçar A4 em modo retrato (portrait) para este fluxo de exportação
      var doc = new jsPDFCtor({ unit: 'mm', format: 'a4', orientation: 'portrait' });
      var container = document.createElement('div');
      container.style.position = 'fixed';
      container.style.left = '-10000px';
      container.style.top = '0';
      // Mantém o layout fiel ao A4 portrait (210mm) para evitar reflow e escala incorreta
      container.style.width = '210mm';
      container.style.background = '#fff';
      container.style.zIndex = '-1';
      document.body.appendChild(container);

      // Baixa as páginas em paralelo (limitado) para acelerar rede
      window._showPdfProgress('Iniciando download das páginas...', 2);
      var fetched = await _parallelFetchPages(list, 4, function(text, pct){ window._showPdfProgress(text, pct); });
      // Converte para elementos DOM e filtra inválidos
      var pages = [];
      for (var i = 0; i < (fetched || []).length; i++){
        try{
          var item = fetched[i];
          if (!item || !item.html) continue;
          var docDom = new DOMParser().parseFromString(item.html, 'text/html');
          var pageEl = docDom.querySelector('.page');
          if (!pageEl) continue;
          pages.push({ id: item.id, pageEl: pageEl });
        }catch(e){ }
      }

      // Estimativa de páginas totais (cada RDO tem no máximo 2 páginas)
      var estimatedTotalPages = Math.max(1, pages.length * 2);
      var totalAdded = 0;
      // Renderiza (html2canvas) sequencialmente para evitar estouro de CPU/memoria
      for (var idx = 0; idx < pages.length; idx++){
        var info = pages[idx];
        try{
          var imported = document.importNode(info.pageEl, true);
          // Forçar classe portrait na cópia para que o CSS de impressão use dimensões retrato
          try{ imported.classList.add && imported.classList.add('portrait'); }catch(_){ }
          container.appendChild(imported);
          await _waitImages(imported);
          window._showPdfProgress('Renderizando RDO ' + (idx+1) + '/' + pages.length, Math.min(95, Math.round((totalAdded/estimatedTotalPages)*100)) );
          var canvas = await window.html2canvas(imported, {
            scale: captureScale,
            useCORS: true,
            allowTaint: false,
            logging: false,
            backgroundColor: '#ffffff'
          });

          var pageW = doc.internal.pageSize.getWidth();
          var pageH = doc.internal.pageSize.getHeight();
          var imgW = canvas.width;
          var imgH = canvas.height;
          var maxPagesPerRdo = 2;
          var mmPerPxW = pageW / imgW;
          var mmPerPxH = (maxPagesPerRdo * pageH) / imgH;
          var mmPerPx = Math.min(mmPerPxW, mmPerPxH);
          if (!isFinite(mmPerPx) || mmPerPx <= 0) mmPerPx = mmPerPxW;
          var pageHeightPx = pageH / mmPerPx;
          var pagesNeeded = Math.ceil((imgH / pageHeightPx) - 1e-9);
          if (pagesNeeded > maxPagesPerRdo) {
            mmPerPx = (maxPagesPerRdo * pageH) / imgH;
            pageHeightPx = pageH / mmPerPx;
            pagesNeeded = maxPagesPerRdo;
          }
          pagesNeeded = Math.max(1, Math.min(maxPagesPerRdo, pagesNeeded));

          for (var p = 0; p < pagesNeeded; p++){
            var yPx = Math.floor(p * pageHeightPx);
            if (yPx >= imgH) break;
            var sliceHpx = Math.min(pageHeightPx, imgH - yPx);
            var sliceCanvas = document.createElement('canvas');
            sliceCanvas.width = imgW;
            sliceCanvas.height = Math.max(1, Math.floor(sliceHpx));
            var sctx = sliceCanvas.getContext('2d');
            try { sctx.fillStyle = '#ffffff'; sctx.fillRect(0, 0, sliceCanvas.width, sliceCanvas.height); } catch(_){ }
            sctx.drawImage(canvas, 0, yPx, imgW, sliceCanvas.height, 0, 0, imgW, sliceCanvas.height);
            var imgData = sliceCanvas.toDataURL('image/jpeg', jpegQuality);
            var renderWmm = (sliceCanvas.width * mmPerPx);
            var renderHmm = (sliceCanvas.height * mmPerPx);
            var xMm = Math.max(0, (pageW - renderWmm) / 2);
            if (totalAdded > 0) doc.addPage();
            doc.addImage(imgData, 'JPEG', xMm, 0, renderWmm, renderHmm, undefined, pdfImageCompression);
            totalAdded += 1;
            window._showPdfProgress('Preparando PDF: ' + totalAdded + '/' + estimatedTotalPages, Math.min(98, Math.round((totalAdded/estimatedTotalPages)*100)) );
          }
        }catch(e){ console.warn('render error', e); }
        try{ container.removeChild(imported); }catch(_){ }
      }

      try{ document.body.removeChild(container); }catch(_){ }
      try{
        if (cssRef && cssRef.inserted && cssRef.link && cssRef.link.parentNode){
          cssRef.link.parentNode.removeChild(cssRef.link);
        }
      }catch(_){ }
      if (!totalAdded){
        showToast('Falha ao gerar PDF. Nenhum RDO válido.', 'error');
        return;
      }
      var osLabel = (data && data.os && data.os.numero_os) ? data.os.numero_os : (osNumero || osId);
      var filename = 'RDO_OS_' + osLabel + '.pdf';
      try{
        window._showPdfProgress('Gerando arquivo final...', 99);
        // tenta gerar Blob e forçar download (pode ser mais responsivo que doc.save direta)
        var blob = doc.output && typeof doc.output === 'function' ? doc.output('blob') : null;
        if (blob) {
          var url = URL.createObjectURL(blob);
          var a = document.createElement('a');
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          try{ a.parentNode.removeChild(a); }catch(_){ }
          URL.revokeObjectURL(url);
        } else {
          doc.save(filename);
        }
        showToast('PDF gerado com sucesso.', 'success');
      } finally {
        window._hidePdfProgress();
      }
    }catch(err){
      showToast(err && err.message ? err.message : 'Erro ao gerar PDF da OS', 'error');
    } finally {
      // restaura classe do body para não afetar a UI
      try {
        document.body.classList.remove('exporting-pdf');
        if (prevBodyClass) document.body.className = prevBodyClass;
      } catch(_){ }
      try{ if (window && typeof window._hidePdfProgress === 'function') window._hidePdfProgress(); }catch(_){ }
    }
  }

  try {
    document.addEventListener('click', function(ev){
      try {
        var target = ev.target || ev.srcElement;
        if (!target || !target.closest) return;
        var btn = target.closest('.action-btn.pdf-all');
        if (!btn) return;
        ev.preventDefault();
        if (btn.disabled) return;
        var tr = btn.closest('tr');
        var osId = '';
        var osNumero = '';
        try {
          if (tr) {
            osId = tr.getAttribute('data-os-id') || (tr.dataset && (tr.dataset.osId || tr.dataset.os_id)) || '';
            osNumero = tr.getAttribute('data-numero-os') || (tr.dataset && (tr.dataset.numeroOs || tr.dataset.numero_os)) || '';
          }
        } catch(_){ osId = ''; }
        if (!osId) {
          showToast('OS não identificada para este RDO.', 'error');
          return;
        }
        _exportOsRdosPdf(osId, osNumero);
      } catch(_){ }
    }, false);
  } catch(_){ }


  // Bind editor modal tank actions (create/associate, edit name, merge)
  function initEditorTankActions(){
    try{
      onReady(function(){
        var createBtn = document.getElementById('edit-btn-create-tanque');
        var editBtn = document.getElementById('edit-btn-edit-tanque');
        var mergeBtn = document.getElementById('edit-btn-merge-tanque');
        var deleteBtn = document.getElementById('edit-btn-delete-tanque');
        var codEl = document.getElementById('edit-tanque-cod');
        var nomeEl = document.getElementById('edit-tanque-nome');
        var tankIdEl = document.getElementById('edit-tanque-id');
        var rdoIdEl = document.getElementById('edit-rdo-id');
        if (createBtn) {
          createBtn.addEventListener('click', async function(ev){
            ev && ev.preventDefault();
            var payload = null;
            // Tanque novo: não reutilizar valores do Editor (modal deve abrir zerado)
            try{ payload = await window.showTankCreateModal({}); }catch(e){ console.warn('showTankCreateModal failed', e); payload = null; }
            if (!payload) return; // usuário cancelou
            var rdoId = rdoIdEl && rdoIdEl.value && String(rdoIdEl.value).trim();
            var fd = new FormData();
            try{ Object.keys(payload || {}).forEach(function(k){ try{ var v = payload[k]; if (v == null) return; var s = String(v).trim(); if (!s) return; fd.append(k, s); }catch(_){ } }); }catch(_){ }
            if (rdoId) fd.append('rdo_id', rdoId);
            try{
              var headers = {};
              var csrf = getCSRF(document) || '';
              if (csrf) headers['X-CSRFToken'] = csrf;
              var url = '/api/rdo/' + (rdoId ? encodeURIComponent(rdoId) + '/' : '') + 'add_tank/';
              var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin', headers: headers });
              var data = null; try{ data = await resp.json(); } catch(e){ data = null; }
              if (!resp.ok) { showToast((data && data.error) ? data.error : 'Falha ao criar/associar tanque', 'error'); return; }
              if (data && (data.tanque_id || (data.tank && data.tank.id) || data.id)){
                var id = data.tanque_id || (data.tank && data.tank.id) || data.id;
                try{ if (tankIdEl) tankIdEl.value = id; }catch(_){ }
                showToast('Tanque criado/associado com sucesso', 'success');
                try{ document.dispatchEvent(new CustomEvent('rdo:tank:created', { detail: data })); }catch(_){ }
              } else if (data && data.error){ showToast(data.error, 'error'); } else { showToast('Resposta inesperada do servidor', 'error'); }
            }catch(err){ console.error('create-tank error', err); showToast('Erro ao comunicar com o servidor', 'error'); }
          }, false);
        }

        if (editBtn){
          editBtn.addEventListener('click', async function(ev){
            ev && ev.preventDefault();
            var id = tankIdEl && tankIdEl.value && String(tankIdEl.value).trim();
            var nome = nomeEl && nomeEl.value && nomeEl.value.trim();
            var codigo = codEl && codEl.value && codEl.value.trim();
            if (!id) { showToast('Nenhum tanque associado para editar. Use Criar/Associar primeiro.', 'error'); return; }
            if (!nome && !codigo) { showToast('Informe o nome e/ou o código do tanque.', 'error'); return; }
            var fd = new FormData();
            if (nome) fd.append('tanque_nome', nome);
            if (codigo) fd.append('tanque_codigo', codigo);
            try{
              var headers = {};
              var csrf = getCSRF(document) || '';
              if (csrf) headers['X-CSRFToken'] = csrf;
              var url = '/api/rdo/tank/' + encodeURIComponent(id) + '/update/';
              var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin', headers: headers });
              if (resp.ok){ showToast('Tanque atualizado.', 'success'); try{ document.dispatchEvent(new CustomEvent('rdo:tank:updated', { detail: { tank_id: id } })); }catch(_){ } }
              else { var data=null; try{ data = await resp.json(); }catch(_){ } showToast((data && data.error) ? data.error : 'Falha ao atualizar o tanque', 'error'); }
            }catch(err){ console.error('edit-tank error', err); showToast('Erro ao comunicar com o servidor', 'error'); }
          }, false);
        }

        if (mergeBtn){
          mergeBtn.addEventListener('click', async function(ev){
            ev && ev.preventDefault();
            var sourceId = tankIdEl && tankIdEl.value && String(tankIdEl.value).trim();
            if (!sourceId){ showToast('Nenhum tanque associado neste RDO para juntar.', 'error'); return; }
            var ctx = _getEditorOsContext();
            var pick = null;
            try { pick = await showTankMergeModal({ os_id: ctx.os_id, numero_os: ctx.numero_os, rdo_id: ctx.rdo_id, source_id: sourceId }); } catch(e){ console.warn('showTankMergeModal failed', e); pick = null; }
            if (!pick) return;
            var fd = new FormData();
            fd.append('source_tank_id', pick.sourceId);
            fd.append('target_tank_id', pick.targetId);
            try {
              if (pick.final_tanque_nome) fd.append('final_tanque_nome', String(pick.final_tanque_nome));
              if (pick.final_tanque_codigo) fd.append('final_tanque_codigo', String(pick.final_tanque_codigo));
            } catch(_){ }
            try{
              var headers = {};
              var csrf = getCSRF(document) || '';
              if (csrf) headers['X-CSRFToken'] = csrf;
              var url = '/api/rdo/tank/merge/';
              var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin', headers: headers });
              var data = null; try{ data = await resp.json(); } catch(e){ data = null; }
              if (resp.ok && data && (data.ok || data.success)) {
                showToast('Tanques unidos com sucesso.', 'success');
                try{ if (tankIdEl) tankIdEl.value = String(pick.targetId); }catch(_){ }
                try{ if (window) window.__last_rdo_tanque_id = String(pick.targetId); }catch(_){ }
                try{ if (typeof loadEditorDetails === 'function') { loadEditorDetails(); } }catch(_){ }
                try{ document.dispatchEvent(new CustomEvent('rdo:tank:merged', { detail: data })); }catch(_){ }
              }
              else { showToast((data && data.error) ? data.error : 'Falha ao juntar tanques', 'error'); }
            }catch(err){ console.error('merge-tank error', err); showToast('Erro ao comunicar com o servidor', 'error'); }
          }, false);
        }

        if (deleteBtn){
          deleteBtn.addEventListener('click', async function(ev){
            ev && ev.preventDefault();
            var ctx = _getEditorOsContext();
            var currentId = tankIdEl && tankIdEl.value && String(tankIdEl.value).trim();
            var pick = null;
            try { pick = await showTankDeleteModal({ os_id: ctx.os_id, numero_os: ctx.numero_os, rdo_id: ctx.rdo_id, tank_id: currentId }); } catch(e){ console.warn('showTankDeleteModal failed', e); pick = null; }
            if (!pick || !pick.tankId) return;
            var fd = new FormData();
            fd.append('tank_id', String(pick.tankId));
            try { fd.append('scope', String(pick.scope || 'rdo')); } catch(_){ }
            try {
              if (ctx.os_id) fd.append('os_id', String(ctx.os_id));
              if (ctx.rdo_id) fd.append('rdo_id', String(ctx.rdo_id));
            } catch(_){ }
            try{
              var headers = {};
              var csrf = getCSRF(document) || '';
              if (csrf) headers['X-CSRFToken'] = csrf;
              var url = '/api/rdo/tank/delete/';
              var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin', headers: headers });
              var data = null; try{ data = await resp.json(); } catch(e){ data = null; }
              if (resp.ok && data && (data.ok || data.success)) {
                showToast('Tanque excluído.', 'success');
                try{
                  if (currentId && String(currentId) === String(pick.tankId)) {
                    if (tankIdEl) tankIdEl.value = '';
                    try { if (window) window.__last_rdo_tanque_id = ''; } catch(_){ }
                  }
                }catch(_){ }
                try{ if (typeof loadEditorDetails === 'function') loadEditorDetails(); }catch(_){ }
                try{ document.dispatchEvent(new CustomEvent('rdo:tank:deleted', { detail: data })); }catch(_){ }
              } else {
                showToast((data && data.error) ? data.error : 'Falha ao excluir tanque', 'error');
              }
            }catch(err){ console.error('delete-tank error', err); showToast('Erro ao comunicar com o servidor', 'error'); }
          }, false);
        }

        // Associate existing tank to this RDO
        var assocBtn = document.getElementById('edit-btn-associate-tanque');
        if (assocBtn){
          assocBtn.addEventListener('click', async function(ev){
            ev && ev.preventDefault();
            var ctx = _getEditorOsContext();
            if (!ctx || !ctx.rdo_id){ showToast('RDO não identificada.', 'error'); return; }
            var pick = null;
            try { pick = await showTankAssociateModal({ os_id: ctx.os_id, numero_os: ctx.numero_os, rdo_id: ctx.rdo_id }); } catch(e){ console.warn('showTankAssociateModal failed', e); pick = null; }
            if (!pick || !pick.tankId) return;
            var fd = new FormData();
            try{ fd.append('tanque_id', String(pick.tankId)); fd.append('tank_id', String(pick.tankId)); }catch(_){ }
            try{ if (ctx.rdo_id) fd.append('rdo_id', String(ctx.rdo_id)); if (ctx.os_id) fd.append('os_id', String(ctx.os_id)); }catch(_){ }
            try{
              var headers = {}; var csrf = getCSRF(document) || ''; if (csrf) headers['X-CSRFToken'] = csrf;
              var url = '/api/rdo/' + encodeURIComponent(String(ctx.rdo_id || '')) + '/add_tank/';
              var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin', headers: headers });
              var data = null; try{ data = await resp.json(); }catch(e){ data = null; }
              if (resp.ok && data && (data.ok || data.success)){
                showToast('Tanque associado ao RDO.', 'success');
                try{
                  // garante que o reload do fragment use o tanque recém associado
                  var newTankId = (data && (data.tanque_id || data.tank_id || (data.tank && data.tank.id) || (data.tanque && data.tanque.id))) || '';
                  if (newTankId) {
                    try { if (tankIdEl) tankIdEl.value = String(newTankId); } catch(_){ }
                    try { var hid = document.getElementById('edit-tanque-id'); if (hid) hid.value = String(newTankId); } catch(_){ }
                    try { if (window) window.__last_rdo_tanque_id = String(newTankId); } catch(_){ }
                  }
                }catch(_){ }
                try{ if (typeof loadEditorDetails === 'function') { try { await loadEditorDetails(); } catch(_){} } }catch(_){ }
                try{
                  var det = {};
                  try{
                    if (data && typeof data === 'object') {
                      Object.keys(data).forEach(function(k){ try{ det[k] = data[k]; }catch(_){ } });
                    }
                  }catch(_){ }
                  try{ det.rdo_id = ctx.rdo_id || det.rdo_id; }catch(_){ }
                  try{ det.os_id = ctx.os_id || det.os_id; }catch(_){ }
                  document.dispatchEvent(new CustomEvent('rdo:tank:associated', { detail: det }));
                }catch(_){ }
              } else {
                showToast((data && data.error) ? data.error : 'Falha ao associar tanque', 'error');
              }
            }catch(err){ console.error('associate-tank error', err); showToast('Erro ao comunicar com o servidor', 'error'); }
          }, false);
        }
      });
    }catch(e){ console.warn('initEditorTankActions failed', e); }
  }
  try{ initEditorTankActions(); }catch(_){ }

  // Delegated clicks for editor tank actions (works even when fragment is loaded later)
  try{
    document.addEventListener('click', function(ev){
      try{
        var target = ev.target || ev.srcElement;
        if (!target || !target.closest) return;
        var createBtn = target.closest('#edit-btn-create-tanque');
        var editBtn = target.closest('#edit-btn-edit-tanque');
        var mergeBtn = target.closest('#edit-btn-merge-tanque');
        var deleteBtn = target.closest('#edit-btn-delete-tanque');
        var assocBtn = target.closest('#edit-btn-associate-tanque');
        if (!createBtn && !editBtn && !mergeBtn && !deleteBtn && !assocBtn) return;
        // delegate to the bound functions by triggering click on element (or run logic inline)
        // prefer to run inline to avoid relying on binding order
        var codEl = document.getElementById('edit-tanque-cod');
        var nomeEl = document.getElementById('edit-tanque-nome');
        var tankIdEl = document.getElementById('edit-tanque-id');
        var rdoIdEl = document.getElementById('edit-rdo-id');
        if (createBtn){
          ev.preventDefault();
          (async function(){
            var payload = null;
            // Tanque novo: não reutilizar valores do Editor (modal deve abrir zerado)
            try{ payload = await window.showTankCreateModal({}); }catch(e){ console.warn('showTankCreateModal failed', e); payload = null; }
            if (!payload) return;
            var rdoId = rdoIdEl && rdoIdEl.value && String(rdoIdEl.value).trim();
            var fd = new FormData();
            try{ Object.keys(payload || {}).forEach(function(k){ try{ var v = payload[k]; if (v == null) return; var s = String(v).trim(); if (!s) return; fd.append(k, s); }catch(_){ } }); }catch(_){ }
            if (rdoId) fd.append('rdo_id', rdoId);
            try{ var headers={}; var csrf=getCSRF(document)||''; if(csrf) headers['X-CSRFToken']=csrf; var url='/api/rdo/'+(rdoId?encodeURIComponent(rdoId)+'/':'')+'add_tank/'; var resp=await fetch(url,{method:'POST',body:fd,credentials:'same-origin',headers:headers}); var data=null; try{data=await resp.json();}catch(e){data=null;} if(!resp.ok){ showToast((data&&data.error)?data.error:'Falha ao criar/associar tanque','error'); return;} var id = data&& (data.tanque_id||(data.tank&&data.tank.id)||data.id); if(id){ try{ if(tankIdEl) tankIdEl.value = id; }catch(_){ } showToast('Tanque criado/associado com sucesso','success'); try{ document.dispatchEvent(new CustomEvent('rdo:tank:created',{detail:data})); }catch(_){ } } else if(data&&data.error){ showToast(data.error,'error'); } else { showToast('Resposta inesperada do servidor','error'); } }catch(err){ console.error('create-tank error',err); showToast('Erro ao comunicar com o servidor','error'); }
          })();
          return;
        }
        if (editBtn){
          ev.preventDefault();
          (async function(){
            var id = tankIdEl && tankIdEl.value && String(tankIdEl.value).trim();
            var nome = nomeEl && nomeEl.value && nomeEl.value.trim();
            var codigo = codEl && codEl.value && codEl.value.trim();
            if (!id){ showToast('Nenhum tanque associado para editar. Use Criar/Associar primeiro.','error'); return; }
            if (!nome && !codigo){ showToast('Informe o nome e/ou o código do tanque.','error'); return; }
            var fd = new FormData();
            if (nome) fd.append('tanque_nome', nome);
            if (codigo) fd.append('tanque_codigo', codigo);
            try{ var headers={}; var csrf=getCSRF(document)||''; if(csrf) headers['X-CSRFToken']=csrf; var url='/api/rdo/tank/'+encodeURIComponent(id)+'/update/'; var resp=await fetch(url,{method:'POST',body:fd,credentials:'same-origin',headers:headers}); if(resp.ok){ showToast('Tanque atualizado.','success'); try{ document.dispatchEvent(new CustomEvent('rdo:tank:updated',{detail:{tank_id:id}})); }catch(_){ } } else { var data=null; try{data=await resp.json();}catch(_){ } showToast((data&&data.error)?data.error:'Falha ao atualizar o tanque','error'); } }catch(err){ console.error('edit-tank error',err); showToast('Erro ao comunicar com o servidor','error'); }
          })();
          return;
        }
        if (mergeBtn){
          ev.preventDefault();
          (async function(){
            var sourceId = tankIdEl && tankIdEl.value && String(tankIdEl.value).trim();
            if (!sourceId){ showToast('Nenhum tanque associado neste RDO para juntar.','error'); return; }
            var ctx = _getEditorOsContext();
            var pick = null;
            try { pick = await showTankMergeModal({ os_id: ctx.os_id, numero_os: ctx.numero_os, rdo_id: ctx.rdo_id, source_id: sourceId }); } catch(e){ console.warn('showTankMergeModal failed', e); pick = null; }
            if (!pick) return;
            var fd = new FormData();
            fd.append('source_tank_id', pick.sourceId);
            fd.append('target_tank_id', pick.targetId);
            try {
              if (pick.final_tanque_nome) fd.append('final_tanque_nome', String(pick.final_tanque_nome));
              if (pick.final_tanque_codigo) fd.append('final_tanque_codigo', String(pick.final_tanque_codigo));
            } catch(_){ }
            try{ var headers={}; var csrf=getCSRF(document)||''; if(csrf) headers['X-CSRFToken']=csrf; var url='/api/rdo/tank/merge/'; var resp=await fetch(url,{method:'POST',body:fd,credentials:'same-origin',headers:headers}); var data=null; try{data=await resp.json();}catch(e){data=null;} if(resp.ok && data && (data.ok||data.success)){ showToast('Tanques unidos com sucesso.','success'); try{ document.dispatchEvent(new CustomEvent('rdo:tank:merged',{detail:data})); }catch(_){ } } else { showToast((data&&data.error)?data.error:'Falha ao juntar tanques','error'); } }catch(err){ console.error('merge-tank error',err); showToast('Erro ao comunicar com o servidor','error'); }
            try{ if(resp && resp.ok && data && (data.ok||data.success)){ try{ if(tankIdEl) tankIdEl.value = String(pick.targetId); }catch(_){ } try{ if(window) window.__last_rdo_tanque_id = String(pick.targetId); }catch(_){ } try{ if(typeof loadEditorDetails === 'function') loadEditorDetails(); }catch(_){ } } }catch(_){ }
          })();
          return;
        }

        if (assocBtn){
          ev.preventDefault();
          (async function(){
            var ctx = _getEditorOsContext();
            if (!ctx || !ctx.rdo_id){ showToast('RDO não identificada.', 'error'); return; }
            var pick = null;
            try { pick = await showTankAssociateModal({ os_id: ctx.os_id, numero_os: ctx.numero_os, rdo_id: ctx.rdo_id }); } catch(e){ console.warn('showTankAssociateModal failed', e); pick = null; }
            if (!pick || !pick.tankId) return;
            var fd = new FormData();
            try{ fd.append('tanque_id', String(pick.tankId)); fd.append('tank_id', String(pick.tankId)); }catch(_){ }
            try{ if (ctx.rdo_id) fd.append('rdo_id', String(ctx.rdo_id)); if (ctx.os_id) fd.append('os_id', String(ctx.os_id)); }catch(_){ }
            try{
              var headers = {}; var csrf = getCSRF(document) || ''; if (csrf) headers['X-CSRFToken'] = csrf;
              var url = '/api/rdo/' + encodeURIComponent(String(ctx.rdo_id || '')) + '/add_tank/';
              var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin', headers: headers });
              var data = null; try{ data = await resp.json(); }catch(e){ data = null; }
              if (resp.ok && data && (data.ok || data.success)){
                showToast('Tanque associado ao RDO.', 'success');
                try{
                  var newTankId = (data && (data.tanque_id || data.tank_id || (data.tank && data.tank.id) || (data.tanque && data.tanque.id))) || '';
                  if (newTankId) {
                    try { if (tankIdEl) tankIdEl.value = String(newTankId); } catch(_){ }
                    try { var hid = document.getElementById('edit-tanque-id'); if (hid) hid.value = String(newTankId); } catch(_){ }
                    try { if (window) window.__last_rdo_tanque_id = String(newTankId); } catch(_){ }
                  }
                }catch(_){ }
                try{ if (typeof loadEditorDetails === 'function') { try { await loadEditorDetails(); } catch(_){} } }catch(_){ }
                try{
                  var det2 = {};
                  try{
                    if (data && typeof data === 'object') {
                      Object.keys(data).forEach(function(k){ try{ det2[k] = data[k]; }catch(_){ } });
                    }
                  }catch(_){ }
                  try{ det2.rdo_id = ctx.rdo_id || det2.rdo_id; }catch(_){ }
                  try{ det2.os_id = ctx.os_id || det2.os_id; }catch(_){ }
                  document.dispatchEvent(new CustomEvent('rdo:tank:associated', { detail: det2 }));
                }catch(_){ }
              } else {
                showToast((data && data.error) ? data.error : 'Falha ao associar tanque', 'error');
              }
            }catch(err){ console.error('associate-tank error', err); showToast('Erro ao comunicar com o servidor', 'error'); }
          })();
          return;
        }

        if (deleteBtn){
          ev.preventDefault();
          (async function(){
            var ctx = _getEditorOsContext();
            var currentId = tankIdEl && tankIdEl.value && String(tankIdEl.value).trim();
            var pick = null;
            try { pick = await showTankDeleteModal({ os_id: ctx.os_id, numero_os: ctx.numero_os, rdo_id: ctx.rdo_id, tank_id: currentId }); } catch(e){ console.warn('showTankDeleteModal failed', e); pick = null; }
            if (!pick || !pick.tankId) return;
            var fd = new FormData();
            fd.append('tank_id', String(pick.tankId));
            try { fd.append('scope', String(pick.scope || 'rdo')); } catch(_){ }
            try { if (ctx.os_id) fd.append('os_id', String(ctx.os_id)); if (ctx.rdo_id) fd.append('rdo_id', String(ctx.rdo_id)); } catch(_){ }
            try{ var headers={}; var csrf=getCSRF(document)||''; if(csrf) headers['X-CSRFToken']=csrf; var url='/api/rdo/tank/delete/'; var resp=await fetch(url,{method:'POST',body:fd,credentials:'same-origin',headers:headers}); var data=null; try{data=await resp.json();}catch(e){data=null;} if(resp.ok && data && (data.ok||data.success)){ showToast('Tanque excluído.','success'); try{ if(currentId && String(currentId)===String(pick.tankId)){ if(tankIdEl) tankIdEl.value=''; try{ if(window) window.__last_rdo_tanque_id=''; }catch(_){ } } }catch(_){ } try{ if(typeof loadEditorDetails==='function') loadEditorDetails(); }catch(_){ } try{ document.dispatchEvent(new CustomEvent('rdo:tank:deleted',{detail:data})); }catch(_){ } } else { showToast((data&&data.error)?data.error:'Falha ao excluir tanque','error'); } }catch(err){ console.error('delete-tank error',err); showToast('Erro ao comunicar com o servidor','error'); }
          })();
          return;
        }
      }catch(e){/* swallow */}
    }, false);
  }catch(e){/* ignore */}

  // Delegated handlers para garantir adicionar/remover atividades mesmo quando fragmentos
  // não foram ligados corretamente (ex.: ausência de bindings por variação do template).
  try {
    document.addEventListener('click', function(ev){
      try {
        var t = ev.target;
        var addBtn = t.closest && (t.closest('#edit-btn-add-atividade') || t.closest('#btn-add-atividade'));
        var removeLastBtn = t.closest && (t.closest('#edit-btn-remove-last-atividade') || t.closest('#btn-remove-last-atividade'));
        var perRowRemove = t.closest && t.closest('.btn-remove-atividade');
        var memberAddBtn = t.closest && (t.closest('#edit-btn-add-membro') || t.closest('#btn-add-membro'));
        var memberRemoveBtn = t.closest && (t.closest('#edit-btn-remove-membro') || t.closest('#btn-remove-membro'));

        if (addBtn) {
          try {
            var wrapper = (addBtn.closest && (addBtn.closest('#edit-atividades-wrapper') || addBtn.closest('#atividades-wrapper') || addBtn.closest('.activities-wrapper'))) || document.getElementById('edit-atividades-wrapper') || document.getElementById('atividades-wrapper');
            if (!wrapper) return;
            if (wrapper.getAttribute && wrapper.getAttribute('data-rdo-local-bindings') === '1') return;
            ev.preventDefault && ev.preventDefault();
            var max = parseInt((addBtn.getAttribute && addBtn.getAttribute('data-max')) || addBtn.getAttribute && addBtn.getAttribute('data-max') || '20', 10) || 20;
            var rows = wrapper.querySelectorAll('.activities-row') || [];
            if (rows.length >= max) return;
            var base = wrapper.querySelector('.activities-row'); if (!base) return;
            var clone = base.cloneNode(true);
            Array.prototype.forEach.call(clone.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; });
            var footer = wrapper.querySelector('.activities-footer');
            if (footer && footer.parentNode) footer.parentNode.insertBefore(clone, footer); else wrapper.appendChild(clone);
            try { if (typeof computeModalAggregates === 'function') computeModalAggregates(); } catch(_){ }
          } catch(_){}
          return;
        }

          if (memberAddBtn) {
            try {
              var wrap = (memberAddBtn.closest && (memberAddBtn.closest('#edit-equipe-wrapper') || memberAddBtn.closest('#equipe-wrapper') || memberAddBtn.closest('.team-wrapper'))) || document.getElementById('edit-equipe-wrapper') || document.getElementById('equipe-wrapper');
              if (!wrap) return;
              if (wrap.getAttribute && wrap.getAttribute('data-rdo-local-bindings') === '1') return;
              ev.preventDefault && ev.preventDefault();
              var base = wrap.querySelector('.team-row'); if (!base) return;
              var clone = base.cloneNode(true);
              Array.prototype.forEach.call(clone.querySelectorAll('input,select,textarea'), function(el){ if(el.tagName && el.tagName.toLowerCase()==='select') el.selectedIndex=0; else el.value=''; });
              var footer = wrap.querySelector('.team-footer'); if (footer && footer.parentNode) footer.parentNode.insertBefore(clone, footer); else wrap.appendChild(clone);
              try { syncPobAllForms(); } catch(_){ }
            } catch(_){ }
            return;
          }

          if (memberRemoveBtn) {
            try {
              var wrap = (memberRemoveBtn.closest && (memberRemoveBtn.closest('#edit-equipe-wrapper') || memberRemoveBtn.closest('#equipe-wrapper') || memberRemoveBtn.closest('.team-wrapper'))) || document.getElementById('edit-equipe-wrapper') || document.getElementById('equipe-wrapper');
              if (!wrap) return;
              if (wrap.getAttribute && wrap.getAttribute('data-rdo-local-bindings') === '1') return;
              ev.preventDefault && ev.preventDefault();
              var rows = wrap.querySelectorAll('.team-row') || [];
              if (rows.length <= 1) return;
              var last = rows[rows.length-1]; if (last && last.parentNode) last.parentNode.removeChild(last);
              try { syncPobAllForms(); } catch(_){ }
            } catch(_){ }
            return;
          }

        if (removeLastBtn) {
          try {
            var wrapper = (removeLastBtn.closest && (removeLastBtn.closest('#edit-atividades-wrapper') || removeLastBtn.closest('#atividades-wrapper') || removeLastBtn.closest('.activities-wrapper'))) || document.getElementById('edit-atividades-wrapper') || document.getElementById('atividades-wrapper');
            if (!wrapper) return;
            if (wrapper.getAttribute && wrapper.getAttribute('data-rdo-local-bindings') === '1') return;
            ev.preventDefault && ev.preventDefault();
            var rows = wrapper.querySelectorAll('.activities-row') || [];
            if (rows.length <= 1) {
              try { var only = rows[0]; if (only) Array.prototype.forEach.call(only.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; }); } catch(_){ }
              try { if (typeof computeModalAggregates === 'function') computeModalAggregates(); } catch(_){ }
              return;
            }
            var last = rows[rows.length-1]; if (last && last.parentNode) last.parentNode.removeChild(last);
            try { if (typeof computeModalAggregates === 'function') computeModalAggregates(); } catch(_){ }
          } catch(_){}
          return;
        }

        if (perRowRemove) {
          try {
            var wrapper = perRowRemove.closest && (perRowRemove.closest('#edit-atividades-wrapper') || perRowRemove.closest('#atividades-wrapper'));
            if (!wrapper) wrapper = document.getElementById('edit-atividades-wrapper') || document.getElementById('atividades-wrapper');
            if (!wrapper) return;
            if (wrapper.getAttribute && wrapper.getAttribute('data-rdo-local-bindings') === '1') return;
            ev.preventDefault && ev.preventDefault();
            var rows = wrapper.querySelectorAll('.activities-row') || [];
            if (rows.length <= 1) {
              try { var only = rows[0]; if (only) Array.prototype.forEach.call(only.querySelectorAll('input,select,textarea'), function(el){ if (el.type==='checkbox' || el.type==='radio') el.checked=false; else el.value=''; }); } catch(_){ }
              try { if (typeof computeModalAggregates === 'function') computeModalAggregates(); } catch(_){ }
              return;
            }
            var row = perRowRemove.closest && perRowRemove.closest('.activities-row'); if (row && row.parentNode) row.parentNode.removeChild(row);
            try { if (typeof computeModalAggregates === 'function') computeModalAggregates(); } catch(_){ }
          } catch(_){}
          return;
        }
      } catch(_){ }
    }, false);
  } catch(e){ /* ignore */ }

})();

// Garantir que botões de adicionar/remover atividade não fiquem permanentemente
// desabilitados pelo template — habilita-os no carregamento para que os
// handlers delegados (acima) possam capturar cliques mesmo quando variantes
// de template removem bindings locais.
(function(fn){
  try {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  } catch(_){
    try { fn(); } catch(__){}
  }
})(function(){
  function enableActivityButtons(){
    try {
      var removes = document.querySelectorAll('.btn-remove-atividade[disabled]');
      Array.prototype.forEach.call(removes, function(b){ try { b.removeAttribute('disabled'); } catch(_){ } });
      var adds = document.querySelectorAll('#edit-btn-add-atividade[disabled], #btn-add-atividade[disabled]');
      Array.prototype.forEach.call(adds, function(b){ try { b.removeAttribute('disabled'); } catch(_){ } });

      // Re-habilitar botões de adicionar/remover membro (editor e página)
      var memberAdds = document.querySelectorAll('#edit-btn-add-membro[disabled], #btn-add-membro[disabled]');
      Array.prototype.forEach.call(memberAdds, function(b){ try { b.removeAttribute('disabled'); } catch(_){ } });
      var memberRemoves = document.querySelectorAll('#edit-btn-remove-membro[disabled], #btn-remove-membro[disabled]');
      Array.prototype.forEach.call(memberRemoves, function(b){ try { b.removeAttribute('disabled'); } catch(_){ } });
    } catch(_){ }
  }

  try { enableActivityButtons(); } catch(_){ }

  try {
    var observerTarget = document.getElementById('rdo-edit-content') || document.body;
    if (observerTarget && typeof MutationObserver !== 'undefined') {
      var mo = new MutationObserver(function(mutations){ try { enableActivityButtons(); } catch(_){ } });
      mo.observe(observerTarget, { childList: true, subtree: true });
    }
  } catch(_){ }
});
