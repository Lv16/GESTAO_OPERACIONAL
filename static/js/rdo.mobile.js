/* rdo.mobile.js — ajuda a garantir foco e scroll em mobile quando o modal abre */
(function(){
  'use strict';

  // Comportamento 'force_mobile' movido do template: somente aplica quando
  // o template adicionou <meta name="force-mobile" content="1"> no <head>.
  try {
    var metaForce = document.querySelector('meta[name="force-mobile"]');
    if (metaForce) {
      (function(){
        var MOBILE_BREAKPOINT = 820; // deve espelhar CSS/JS
        function isMobileUserAgent(){
          try{
            var ua = navigator.userAgent || '';
            return (/Mobi|Android|iPhone|iPad|iPod|Windows Phone/i).test(ua);
          }catch(e){ return false; }
        }
        function apply(){
          try{
            window.__force_mobile = true;
            document.documentElement.classList.add('force-mobile');
            try { document.body.classList.add('force-mobile'); } catch(e){}
          }catch(e){}
        }
        if (isMobileUserAgent()){
          try{ document.documentElement.classList.remove('desktop-prefer'); }catch(e){}
          apply();
        } else {
          try{ document.documentElement.classList.add('desktop-prefer'); }catch(e){}
        }
      })();
    }
  } catch(e) { /* noop */ }

  function isSmallMobile(){ return window.innerWidth <= 720; }

  /* Move editor footer actions to header toolbar on small screens
     to ensure Save/Cancel are reachable on mobile. We move the actual
     nodes (not clones) so event handlers and form submission keep working. */
  function setupEditorFooterRelocation(){
    var moved = false;
    var originalContainer = null;
    var footerButtons = null;

    function moveToHeader(){
      try{
        var overlay = document.getElementById('modal-editor-overlay');
        if (!overlay) return;
        var modal = overlay.querySelector('.modal.modal-editor');
        if (!modal) return;
        var toolbarActions = modal.querySelector('.editor-toolbar .toolbar-actions') || modal.querySelector('.modal-header');
        var footer = modal.querySelector('.modal-footer');
        if (!footer || !toolbarActions) return;
        if (moved) return;
        // Save original container for restoration
        originalContainer = footer;
        // Move all direct button children except hidden ones
        footerButtons = Array.prototype.slice.call(footer.querySelectorAll('button, input[type="submit"], a'));
        footerButtons.forEach(function(btn){
          try{ toolbarActions.appendChild(btn); }catch(e){}
        });
        moved = true;
        // Ensure visibility
        try{ toolbarActions.style.display = 'flex'; toolbarActions.style.gap = '8px'; }catch(e){}
      }catch(e){ }
    }

    function restoreFooter(){
      try{
        if (!moved) return;
        var overlay = document.getElementById('modal-editor-overlay');
        if (!overlay) return;
        var modal = overlay.querySelector('.modal.modal-editor');
        if (!modal) return;
        var footer = modal.querySelector('.modal-footer');
        var toolbarActions = modal.querySelector('.editor-toolbar .toolbar-actions') || modal.querySelector('.modal-header');
        if (!footer || !toolbarActions) return;
        if (!footerButtons || !footerButtons.length) return;
        footerButtons.forEach(function(btn){ try{ footer.appendChild(btn); }catch(e){} });
        moved = false;
        footerButtons = null;
      }catch(e){}
    }

    // Handle initial layout and on resize
    function onCheck(){ if (isSmallMobile()) moveToHeader(); else restoreFooter(); }
    window.addEventListener('resize', onCheck);
    document.addEventListener('DOMContentLoaded', onCheck);

    // Also observe the editor overlay to move when it's opened
    try{
      var editorOverlay = document.getElementById('modal-editor-overlay');
      if (editorOverlay){
        var mo = new MutationObserver(function(muts){ muts.forEach(function(m){ if (m.attributeName==='aria-hidden'){ var v = editorOverlay.getAttribute('aria-hidden'); if (v==='false' && isSmallMobile()) setTimeout(moveToHeader,120); if (v==='true') setTimeout(restoreFooter,120); } }); });
        mo.observe(editorOverlay, { attributes: true });
      }
    }catch(e){}
  }

  function ensureVisible(el){
    if (!el) return;
    try{
      var container = document.querySelector('.rdo-sup-content');
      if (container && container.contains(el)){
        el.scrollIntoView({behavior:'smooth',block:'center',inline:'nearest'});
        container.scrollTop = Math.max(0, container.scrollTop - 20);
      } else {
        el.scrollIntoView({behavior:'smooth',block:'center',inline:'nearest'});
      }
    }catch(e){
      var top = el.getBoundingClientRect().top + window.scrollY - (window.innerHeight/3);
      window.scrollTo({top: Math.max(0, top), behavior:'smooth'});
    }
  }

  function observeModalForFocus(){
    var modal = document.querySelector('.modal.modal-supervisor');
    if (!modal) return;

    var overlay = document.getElementById('modal-supervisor-overlay');
    var mo = new MutationObserver(function(mutations){
      mutations.forEach(function(m){
        if (m.attributeName === 'aria-hidden'){
          var hidden = overlay.getAttribute('aria-hidden');
          if (hidden === 'false' && isSmallMobile()){
            setTimeout(function(){
              var first = modal.querySelector('input:not([type="hidden"]):not([readonly]), select, textarea');
              if (first){
                try{ first.focus({preventScroll:true}); } catch(e){ first.focus(); }
                ensureVisible(first);
              }
            }, 220);
          }
        }
      });
    });
    mo.observe(overlay, {attributes:true});

    modal.addEventListener('focusin', function(ev){ if (!isSmallMobile()) return; var t = ev.target; setTimeout(function(){ ensureVisible(t); }, 120); });

    var fileInputs = modal.querySelectorAll('input[type="file"]');
    fileInputs.forEach(function(fi){
      if (fi.dataset.triggerAttached) return;
      var trigger = document.createElement('button');
      trigger.type = 'button';
      trigger.className = 'file-trigger-btn';
      trigger.textContent = 'Adicionar foto';
      trigger.addEventListener('click', function(){ fi.click(); });
      fi.parentNode && fi.parentNode.insertBefore(trigger, fi.nextSibling);
      fi.dataset.triggerAttached = '1';
    });
  }

  function onReady(fn){ if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn); else fn(); }
  onReady(function(){
    var list = document.getElementById('rdo-mobile-list');
    if (!list) return;

    // O click/touch para abrir o modal é tratado centralmente em rdo.core.js.
    // Aqui mantemos apenas o atalho de teclado para acessibilidade.
    list.addEventListener('keydown', function(ev){
      try{
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        var card = ev.target && ev.target.closest && ev.target.closest('.rdo-mobile-item[data-open="supervisor"], .rdo-mobile-card[data-open="supervisor"]');
        if (!card) return;
        var btn = card.querySelector('.open-supervisor');
        if (!btn) return;
        ev.preventDefault();
        try { btn.click(); } catch(_){}
      }catch(_){}
    });
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', observeModalForFocus); else observeModalForFocus();

  // initialize footer relocation for editor modal
  try{ setupEditorFooterRelocation(); }catch(e){}

})();

/* === rdo.mobile.extracted.js ===
   Auto-apply table view for non-supervisors on mobile and
   supervisor-only fallback to render mobile cards when needed.
   This block was extracted from the template to keep HTML clean.
*/
(function(){
  'use strict';

  function isMobile(){ return window.matchMedia && window.matchMedia('(max-width:820px)').matches; }
  function isSupervisor(){ try{ if (window.RDO_ME && window.RDO_ME.funcao) return String(window.RDO_ME.funcao).toLowerCase().indexOf('supervis')!==-1; var w = document.getElementById('site-wrapper'); return w && w.dataset && w.dataset.isSupervisor === 'true'; }catch(e){return false} }
  function canEditSystem(){ try{ var w = document.getElementById('site-wrapper'); return !(w && w.dataset && w.dataset.canEditSystem === 'false'); }catch(e){ return true; } }
  function safe(fn){ try{ fn(); }catch(e){} }

  // Auto-apply table view on mobile for NON-supervisors so they see the full table
  document.addEventListener('DOMContentLoaded', function(){
    safe(function(){
      if (!isMobile()) return;
      var wrapper = document.getElementById('site-wrapper');
      if (!wrapper) return;
      var sup = wrapper.dataset && wrapper.dataset.isSupervisor === 'true';
      if (!sup){
        document.body.classList.add('rdo-show-table');
      }
    });
  });

  // Supervisor-only: gentle fallback to fetch pending OS and render mobile cards if server didn't render them.
  document.addEventListener('DOMContentLoaded', function(){
    safe(function(){
      if (!isMobile() || !isSupervisor()) return;
      if (document.querySelectorAll('.rdo-mobile-card').length) return;
      var meta = document.querySelector('meta[name="rdo-pending-url"]');
      var fallbackUrl = '/rdo/pending_os_json/';
      var url = (meta && meta.content) ? String(meta.content).trim() : '';
      if (!url || url === '/api/rdo/pending_os/') url = fallbackUrl;
      function fetchJson(u){
        return fetch(u, { credentials: 'same-origin' }).then(function(resp){
          if (!resp || resp.status !== 200) return null;
          return resp.json();
        });
      }
      fetchJson(url).then(function(json){
        if (!json && url !== fallbackUrl) return fetchJson(fallbackUrl);
        return json;
      }).then(function(json){
        if (!json) return;
        var items = [];
        if (Array.isArray(json)) items = json;
        else if (json && Array.isArray(json.items)) items = json.items;
        else if (json && Array.isArray(json.data)) items = json.data;
        if (!items || !items.length) return;
        var container = document.getElementById('rdo-mobile-list');
        if (!container){
          container = document.createElement('div');
          container.id = 'rdo-mobile-list';
          container.className = 'rdo-mobile-list mobile-cards';
          var ref = document.querySelector('.tabela_conteiner') || document.querySelector('main') || document.body;
          if (ref && ref.parentNode) ref.parentNode.insertBefore(container, ref.nextSibling || ref);
        }
        container.innerHTML = '';
        items.forEach(function(it){
          var os = (it.numero_os || it.os || (it.ordem_servico && it.ordem_servico.numero_os) || '').toString();
          if (!os) os = '-';
          var empresa = (it.cliente || it.empresa || (it.ordem_servico && it.ordem_servico.cliente) || '').toString();
          if (!empresa) empresa = '-';
          var unidade = (it.unidade || (it.ordem_servico && it.ordem_servico.unidade) || '').toString();
          var os_id = (it.os_id || (it.ordem_servico && it.ordem_servico.id) || it.id || it.os || '').toString();
          // RDO: prefer explicit rdo/rdo_count, fall back to nested rdo or to empty when missing
          var rdo = (it.rdo || it.rdo_count || (it.ordem_servico && it.ordem_servico.rdo) || '');
          if (!rdo) rdo = '';
          var data = it.data_inicio || it.data || '';
          var isSupervisor = (document.getElementById('site-wrapper') && document.getElementById('site-wrapper').dataset && String(document.getElementById('site-wrapper').dataset.isSupervisor) === 'true');
          var canEdit = canEditSystem();
          var html = '<div class="rdo-mobile-card rdo-mobile-item rdo-summary" role="button" tabindex="0" data-open="supervisor" '
            + 'data-rdo-id="'+(it.id||'')+'" data-os-id="'+(os_id||'')+'" data-os="'+os+'" data-empresa="'+empresa+'" data-unidade="'+unidade+'" data-rdo-count="'+(rdo||'')+'" data-supervisor="'+(it.supervisor||'')+'">'
            + '<div class="card-head"><div class="head-left"><span class="os-badge">#'+os+'</span><span class="empresa">'+empresa+'</span></div>'
            + '<div class="head-right"><span class="turno">RDO '+(rdo||'-')+'</span></div></div>'
            + '<div class="card-body"><div class="row"><div class="row-col"><strong>Data</strong><div class="txt">'+(data?data.split('T')[0]:'-')+'</div><div class="txt">'+(unidade||'')+'</div></div></div></div>'
            + '<div class="card-foot"><div class="foot-left"><span class="rdo-pill">RDO '+(rdo||'-')+'</span></div>'
            + '<div class="foot-right">';
          if (canEdit) {
            html += '<button class="btn-rdo ghost small open-supervisor" type="button">Abrir</button>';
          }
          if (!isSupervisor && canEdit) {
            html += '<button class="btn-rdo secondary small open-editor" type="button">Editar</button>';
            html += '<a class="btn-rdo danger small" href="/rdo/'+(it.id||'')+'/page/" target="_blank" rel="noopener noreferrer">Gerar RDO</a>';
          } else if (!isSupervisor) {
            html += '<a class="btn-rdo danger small" href="/rdo/'+(it.id||'')+'/page/" target="_blank" rel="noopener noreferrer">Gerar RDO</a>';
          } else {
            html += '<button class="btn-rdo secondary small" type="button" disabled aria-disabled="true" title="Editar desabilitado para supervisores">Editar</button>';
            html += '<button class="btn-rdo danger small" type="button" disabled aria-disabled="true" title="Gerar RDO desabilitado para supervisores">Gerar RDO</button>';
          }
          html += '</div></div></div>';
          try{ container.insertAdjacentHTML('beforeend', html); }catch(e){ }
        });
        try{ /* handlers delegados ficam em rdo.core.js */ }catch(e){ }
      }).catch(function(){ });
    });
  });

  window.RDOMobile = window.RDOMobile || {
    forceShowTable: function(){ try{ document.body.classList.add('rdo-show-table'); }catch(e){} },
    forceShowCards: function(){ try{ document.body.classList.remove('rdo-show-table'); }catch(e){} }
  };

})();
