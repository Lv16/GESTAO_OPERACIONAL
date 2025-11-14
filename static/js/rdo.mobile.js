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

    // Tooltip helper: mostra uma dica rápida antes de abrir o modal
    function showPreModalTooltip(anchor, text, duration){
      try {
        var id = 'rdo-pre-tooltip';
        var old = document.getElementById(id); if (old) { try{ old.remove(); }catch(e){} }
        var tip = document.createElement('div');
        tip.id = id;
        tip.setAttribute('role','tooltip');
        tip.textContent = text || 'Gerar um novo RDO';
        // estilo mínimo inline para não depender de CSS
        tip.style.position = 'fixed';
        tip.style.zIndex = '100000';
        tip.style.background = '#111';
        tip.style.color = '#fff';
        tip.style.padding = '8px 10px';
        tip.style.borderRadius = '8px';
        tip.style.fontSize = '0.85rem';
        tip.style.boxShadow = '0 8px 22px rgba(0,0,0,0.25)';
        tip.style.opacity = '0';
        tip.style.transition = 'opacity .15s ease, transform .15s ease';
        document.body.appendChild(tip);
        var rect = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { top: window.innerHeight/2, left: window.innerWidth/2, width: 0, height: 0 };
        var top = Math.max(8, rect.top - 12);
        var left = Math.min(window.innerWidth - tip.offsetWidth - 8, Math.max(8, rect.left + rect.width/2 - tip.offsetWidth/2));
        tip.style.top = (top) + 'px';
        tip.style.left = (left) + 'px';
        requestAnimationFrame(function(){ tip.style.opacity = '1'; tip.style.transform = 'translateY(-4px)'; });
        var dur = Math.max(300, duration || 700);
        setTimeout(function(){ try { tip.style.opacity = '0'; tip.style.transform = 'translateY(-2px)'; setTimeout(function(){ try{ tip.remove(); }catch(e){} }, 160); } catch(e){} }, dur);
      } catch(e){}
    }
    function openFromEl(el){
      try {
        var ctx = {
          os: el.getAttribute('data-os') || '',
          numero_os: el.getAttribute('data-os') || '',
          empresa: el.getAttribute('data-empresa') || '',
          unidade: el.getAttribute('data-unidade') || '',
          supervisor: el.getAttribute('data-supervisor') || '',
          rdo_id: el.getAttribute('data-rdo-id') || '',
          os_id: el.getAttribute('data-os-id') || '',
          rdo_count: el.getAttribute('data-rdo-count') || ''
        };
        if (window.rdoOpenSupervisorModal) window.rdoOpenSupervisorModal(ctx);
      } catch(e){}
    }
    // Interceptar clique no card inteiro (fase de captura) para mostrar tooltip antes de abrir o modal
    document.addEventListener('click', function(ev){
      var card = ev.target.closest && ev.target.closest('.rdo-mobile-item');
      if (!card) return;
      ev.preventDefault();
      ev.stopImmediatePropagation();
      showPreModalTooltip(card, 'Gerar um novo RDO', 700);
      setTimeout(function(){ openFromEl(card); }, 700);
    }, true);

    // Interceptar apenas o botão "Abrir" (também na captura) — evita dupla abertura
    document.addEventListener('click', function(ev){
      var btn = ev.target.closest && ev.target.closest('.open-supervisor');
      if (!btn) return;
      var card = btn.closest && btn.closest('.rdo-mobile-item');
      if (!card) return;
      ev.preventDefault();
      ev.stopImmediatePropagation();
      showPreModalTooltip(btn, 'Gerar um novo RDO', 700);
      setTimeout(function(){ openFromEl(card); }, 700);
    }, true);
    list.addEventListener('keydown', function(ev){
      if (ev.key !== 'Enter') return;
      var card = ev.target.closest('.rdo-mobile-item');
      if (!card) return;
      ev.preventDefault();
      ev.stopPropagation();
      showPreModalTooltip(card, 'Gerar um novo RDO', 700);
      setTimeout(function(){ openFromEl(card); }, 700);
    });
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', observeModalForFocus); else observeModalForFocus();

})();
