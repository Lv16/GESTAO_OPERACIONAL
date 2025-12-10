(function(){
  'use strict';
  var MAX_RESULTS = 20;

  function getDataFromContext(source){
    try {
      // Fonte: renderizadas no template via variáveis do Django
      if(source === 'pessoas'){
        var arr = window.__RDO_PESSOAS || [];
        return Array.isArray(arr) ? arr : [];
      }
      if(source === 'funcoes'){
        var arrf = window.__RDO_FUNCOES || [];
        return Array.isArray(arrf) ? arrf : [];
      }
      if(source === 'atividades'){
        var arra = window.__RDO_ATIVIDADES || [];
        return Array.isArray(arra) ? arra : [];
      }
        if(source === 'servicos'){
          var arrs = window.__RDO_SERVICOS || [];
          return Array.isArray(arrs) ? arrs : [];
        }
    } catch(_){}
    return [];
  }

  function buildItemsFromTemplate(container){
    // Extrai opções de um <select> oculto dentro do próprio componente
    var source = container.getAttribute('data-source');
    var items = [];
    // generic: read any <select class="dropdown-data"> inside the component
    var options = container.querySelectorAll('select.dropdown-data option');
    // fallback: se não houver opções dentro do componente, tente buscar no documento
    if((!options || options.length === 0) && document){
      options = document.querySelectorAll('select.dropdown-data option');
    }
    options.forEach(function(op){
      var v = op && op.value ? String(op.value).trim() : '';
      var label = (op.textContent || op.innerText || '').trim();
      if(!v) return;
      // store as object with value/label for richer rendering
      items.push({ value: v, label: label || v });
    });
    return items;
  }

  function getItems(container){
    var source = container.getAttribute('data-source');
    var data = getDataFromContext(source);
    if(Array.isArray(data) && data.length){
      // normalize simple arrays of strings into {value,label}
      if(typeof data[0] === 'string'){
        return data.map(function(s){ return {value: s, label: s}; });
      }
      return data;
    }
    return buildItemsFromTemplate(container);
  }

  function renderMenu(container, items){
    var menu = container.querySelector('.dropdown-menu');
    menu.innerHTML = '';
    if(!items || !items.length){
      var empty = document.createElement('div');
      empty.className = 'dropdown-empty';
      empty.textContent = 'Nenhum resultado';
      menu.appendChild(empty);
      return;
    }
    items.slice(0, MAX_RESULTS).forEach(function(item){
      var value = (item && item.value) ? item.value : String(item);
      var label = (item && item.label) ? item.label : String(item);
      var opt = document.createElement('div');
      opt.className = 'dropdown-option';
      opt.setAttribute('role','option');
      opt.setAttribute('data-value', value);
      opt.setAttribute('data-label', label);
      opt.textContent = label;
      opt.addEventListener('mousedown', function(e){
        e.preventDefault();
        selectValue(container, value, label);
      });
      menu.appendChild(opt);
    });
  }

  function selectValue(container, value, label){
    var hidden = container.querySelector('.dropdown-value');
    var input = container.querySelector('.dropdown-input');
    hidden.value = value || '';
    // show user-friendly label in the visible input
    input.value = (label !== undefined && label !== null) ? label : (value || '');
    closeMenu(container);
  }

  function openMenu(container){
    container.classList.add('open');
  }
  function closeMenu(container){
    container.classList.remove('open');
  }

  function filterItems(items, q){
    if(!q) return items;
    var low = q.toLowerCase();
    var prefix = [], substr = [];
    for(var i=0;i<items.length;i++){
      var it = items[i];
      var val = (it && it.value) ? String(it.value) : String(it);
      var lab = (it && it.label) ? String(it.label) : val;
      var vl = val.toLowerCase();
      var ll = lab.toLowerCase();
      if(ll.indexOf(low) === 0 || vl.indexOf(low) === 0) prefix.push(it);
      else if(ll.indexOf(low) !== -1 || vl.indexOf(low) !== -1) substr.push(it);
    }
    return prefix.concat(substr);
  }

  function attach(container){
    if(!container || container.__dropdown_attached) return;
    var input = container.querySelector('.dropdown-input');
    var toggle = container.querySelector('.dropdown-toggle');
    var menu = container.querySelector('.dropdown-menu');
    var items = getItems(container);
    // Se não houver itens, não mostra o menu
    if(!items || !items.length){
      renderMenu(container, []);
    }

    function update(q){
      var matches = filterItems(items, q || input.value || '');
      renderMenu(container, matches);
    }

    input.addEventListener('focus', function(){ update(''); openMenu(container); });
    input.addEventListener('input', function(){ update(input.value); openMenu(container); });
    toggle.addEventListener('click', function(){ if(container.classList.contains('open')) closeMenu(container); else { update(''); openMenu(container); } });

    document.addEventListener('click', function(ev){
      if(!container.contains(ev.target)) closeMenu(container);
    });

    // teclado
    input.addEventListener('keydown', function(ev){
      // If user presses ArrowDown while menu is closed, open full list (show all options)
      if(ev.key === 'ArrowDown' && !container.classList.contains('open')){
        ev.preventDefault();
        update('');
        openMenu(container);
        // allow the rest of the handler to run so first option can be focused below
      }
      var opts = menu.querySelectorAll('.dropdown-option');
      var focused = Array.prototype.findIndex.call(opts, function(o){return o.classList.contains('is-focused')});
      if(ev.key === 'ArrowDown'){
        ev.preventDefault();
        if(opts.length){ var ni = Math.min(focused+1, opts.length-1); setFocus(opts, ni); }
      } else if(ev.key === 'ArrowUp'){
        ev.preventDefault();
        if(opts.length){ var ni = Math.max(focused-1, 0); setFocus(opts, ni); }
      } else if(ev.key === 'Enter'){
        if(focused>=0 && opts[focused]){ ev.preventDefault(); selectValue(container, opts[focused].getAttribute('data-value'), opts[focused].getAttribute('data-label')); }
      } else if(ev.key === 'Escape'){
        closeMenu(container);
      }
    });

    function setFocus(opts, idx){
      Array.prototype.forEach.call(opts, function(o){ o.classList.remove('is-focused'); });
      if(opts[idx]){ opts[idx].classList.add('is-focused'); opts[idx].scrollIntoView({block:'nearest'}); }
    }

    // inicial
    update('');
    container.__dropdown_attached = true;
  }

  function init(){
    var nodes = document.querySelectorAll('.dropdown-select');
    nodes.forEach(attach);
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  // Try to read activities JSON provided by Django's json_script (id="rdo_atividades").
  try{
    var el = document.getElementById('rdo_atividades');
    if(el && el.textContent){
      try{
        var parsed = JSON.parse(el.textContent);
        // atividades_choices may be list of [val,label] pairs — normalize to {value,label}
        if(Array.isArray(parsed) && parsed.length){
          window.__RDO_ATIVIDADES = parsed.map(function(it){
            if(Array.isArray(it) && it.length>=2) return {value: String(it[0]), label: String(it[1])};
            if(typeof it === 'object' && it !== null && ('value' in it || 'label' in it)) return {value: String(it.value||''), label: String(it.label||it.value||'')};
            return {value: String(it), label: String(it)};
          });
        }
      }catch(_e){ /* ignore parse errors */ }
    }
  }catch(_){ }

  // Try to read services JSON provided by Django's json_script (id="rdo_servicos").
  try{
    var elS = document.getElementById('rdo_servicos');
    if(elS && elS.textContent){
      try{
        var parsedS = JSON.parse(elS.textContent);
        if(Array.isArray(parsedS) && parsedS.length){
          window.__RDO_SERVICOS = parsedS.map(function(it){
            if(Array.isArray(it) && it.length>=2) return {value: String(it[0]), label: String(it[1])};
            if(typeof it === 'object' && it !== null && ('value' in it || 'label' in it)) return {value: String(it.value||''), label: String(it.label||it.value||'')};
            return {value: String(it), label: String(it)};
          });
        }
      }catch(_e){ /* ignore parse errors */ }
    }
  }catch(_){ }

  // Observer para linhas dinâmicas
  var wrapper = document.getElementById('equipe-wrapper');
  if(wrapper && window.MutationObserver){
    var mo = new MutationObserver(function(){
      var nodes = wrapper.querySelectorAll('.dropdown-select');
      nodes.forEach(attach);
    });
    mo.observe(wrapper, {childList:true, subtree:true});
  }
  // Observer para atividades dinâmicas (adicionar/remover linhas de atividade)
  var atividadesWrapper = document.getElementById('atividades-wrapper');
  if(atividadesWrapper && window.MutationObserver){
    var mo2 = new MutationObserver(function(mutations){
      mutations.forEach(function(m){
        if(m.addedNodes && m.addedNodes.length){
          Array.prototype.forEach.call(m.addedNodes, function(n){
            if(n.nodeType !== 1) return;
            var selects = n.querySelectorAll && n.querySelectorAll('.dropdown-select');
            if(selects && selects.length){ selects.forEach(attach); }
            // also if the added node itself is a dropdown-select
            if(n.classList && n.classList.contains && n.classList.contains('dropdown-select')) attach(n);
          });
        }
      });
      // ensure any dropdowns inside the wrapper are attached (in case of complex replacements)
      var all = atividadesWrapper.querySelectorAll('.dropdown-select');
      all.forEach(attach);
    });
    mo2.observe(atividadesWrapper, {childList:true, subtree:true});
  }
})();
