(function(){
    'use strict';

    function qs(id){ return document.getElementById(id); }
    function qsa(sel, root){ try{ return Array.prototype.slice.call((root||document).querySelectorAll(sel)); }catch(e){ return []; } }
    function q1(sel, root){ try{ return (root||document).querySelector(sel); }catch(e){ return null; } }
    function setValue(id, v){ var el = qs(id); if(!el) return; try{ el.value = (v===null||typeof v==='undefined')? '': v; }catch(e){} }
    function setSelect(id, v){ var el = qs(id); if(!el) return; try{ el.value = (v===null||typeof v==='undefined')? '': v; }catch(e){} }
    function triggerInputEvent(id){ var el = qs(id); if(!el) return; try{ var ev = new Event('input', { bubbles: true }); el.dispatchEvent(ev); }catch(e){} }

    // build hidden input helper (selector fix: use querySelector)
    function ensureHidden(name, form){ var el = q1('input[name="'+name+'"][data-hidden]', form); if(!el){ el = document.createElement('input'); el.type='hidden'; el.name = name; el.setAttribute('data-hidden','1'); form.appendChild(el); } return el; }
    function removeHidden(name, form){ var el = q1('input[name="'+name+'"][data-hidden]', form); if(el && el.parentNode){ try{ el.parentNode.removeChild(el); }catch(e){} } }
    function byIdOrName(name){ return qs(name) || q1('[name="'+name+'"]'); }

    document.addEventListener('DOMContentLoaded', function(){
        var input = qs('sup-tanque-cod');
        var datalist = qs('sup-tank-datalist');
        // Botões antigos (Listar/Carregar) podem não existir mais no template
        var listBtn = qs('sup-list-tanks-btn');
        var loadBtn = qs('sup-load-tank-btn');
        var quickList = qs('sup-tank-quick-list');
        var quickWrap = qs('sup-tank-quick-wrap');
        var form = qs('form-supervisor');
        if(!input || !form) return;

        // Limpa campos diários/operacionais para evitar “vazamento” de valores do tanque/RDO anterior.
        function clearOperationalFields(){
            try{
                // Inputs do bloco "Dados Diários" (inclui campos auto-calculados/locked)
                [
                    'sup-espaco-conf',
                    'sup-operadores',
                    'sup-h2s',
                    'sup-lel',
                    'sup-co',
                    'sup-o2',
                    'sup-total-n-efetivo-confinado',
                    'sup-sentido',
                    'sup-tempo-bomba',
                    'sup-bombeio',
                    'sup-res-liq',
                    'sup-ensac',
                    'sup-ica',
                    'sup-camba',
                    'sup-tambores',
                    'sup-res-sol',
                    'sup-res-total',
                    'sup-limp',
                    'sup-limp-fina'
                ].forEach(function(id){
                    var el = qs(id);
                    if(!el) return;
                    try{ el.value = ''; }catch(e){}
                    // dispara input para recomputes/limpeza de UI dependente
                    try{ el.dispatchEvent(new Event('input', { bubbles: true })); }catch(e){}
                    try{ el.dispatchEvent(new Event('change', { bubbles: true })); }catch(e){}
                });

                // Preservar horários de Entrada/Saída (EC) para não forçar o usuário a preencher novamente.
                // Antes eles eram limpos aqui, mas isso causava confusão e bloqueio indevido.
                // Portanto: não tocar em inputs 'ec-entrada-X' / 'ec-saida-X'.

                // Hidden canônicos que podem ter sobrado de seleções anteriores
                [
                    'espaco_confinado','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','total_n_efetivo_confinado',
                    'tempo_bomba','ensacamento_dia','icamento_dia','cambagem_dia','tambores_dia',
                    'bombeio','total_liquido','residuos_solidos','residuos_totais',
                    'sentido_limpeza','percentual_limpeza_diario','avanco_limpeza_fina'
                ].forEach(function(name){
                    var hid = q1('input[name="'+name+'"][data-hidden]', form);
                    if(hid){ try{ hid.value = ''; }catch(e){} }
                });

                // Remover eventuais hidden duplicados (sem data-hidden) que possam sobrescrever o dia
                try{
                    ['icamento_dia','cambagem_dia'].forEach(function(n){
                        var hs = form.querySelectorAll('input[type="hidden"][name="'+n+'"]');
                        Array.prototype.forEach.call(hs, function(el){ try{ el.parentNode && el.parentNode.removeChild(el); }catch(e){} });
                    });
                }catch(e){}
            }catch(e){}
        }

        // Marca campos diários como "editados pelo usuário" para não zerar indevidamente.
        function markUserEdited(id){
            try{
                var el = qs(id);
                if(!el || el.__userEditBound) return;
                el.addEventListener('input', function(){
                    try{ el.setAttribute('data-user-edited','1'); }catch(e){}
                });
                el.__userEditBound = true;
            }catch(e){}
        }

        // Se um campo diário estiver igual à previsão e o usuário não tiver editado, assumir que foi cópia automática e limpar.
        function clearIfAutoCopiedDaily(dailyId, prevId){
            try{
                var daily = qs(dailyId);
                var prev = qs(prevId);
                if(!daily || !prev) return;
                if(String(daily.getAttribute('data-user-edited')||'') === '1') return;
                var dv = (daily.value||'').toString().trim();
                var pv = (prev.value||'').toString().trim();
                if(dv && pv && dv === pv){
                    daily.value = '';
                    try{ daily.dispatchEvent(new Event('input', { bubbles: true })); }catch(e){}
                    try{ daily.dispatchEvent(new Event('change', { bubbles: true })); }catch(e){}
                }
            }catch(e){}
        }

        // Define clearFields local (evita ReferenceError e mantém a intenção original do script).
        function clearFields(){
            try{ clearOperationalFields(); }catch(e){}
            try{
                // reset user-edited flags
                ['sup-ica','sup-camba'].forEach(function(id){ var el = qs(id); if(el){ try{ el.removeAttribute('data-user-edited'); }catch(e){} } });
            }catch(e){}
            try{ hidTank.value = ''; }catch(e){}
            try{ hidTankCode.value = ''; }catch(e){}

            // Limpa e destrava metadados do tanque
            try{
                ['sup-tanque-nome','sup-n-comp','sup-gavetas','sup-patamar','sup-volume','sup-prev-ensac','sup-prev-ica','sup-prev-camba'].forEach(function(id){
                    var el = qs(id);
                    if(!el) return;
                    try{ el.value = ''; }catch(e){}
                    try{ el.readOnly = false; }catch(e){}
                    try{ el.removeAttribute('data-locked'); }catch(e){}
                });
            }catch(e){}

            try{
                var tipoSel = qs('sup-tipo-tanque');
                if(tipoSel){
                    try{ tipoSel.disabled = false; }catch(e){}
                    try{ tipoSel.value = ''; }catch(e){}
                    try{ tipoSel.removeAttribute('data-locked'); }catch(e){}
                }
                removeHidden('tipo_tanque', form);
            }catch(e){}

            try{
                var servSelect = qs('sup-servico');
                if(servSelect){
                    try{ servSelect.disabled = false; }catch(e){}
                    try{ servSelect.removeAttribute('data-locked'); }catch(e){}
                }
                removeHidden('servico_exec', form);
                try{ var servVisible2 = qs('sup-servico-input'); if(servVisible2){ servVisible2.readOnly = false; servVisible2.removeAttribute('data-locked'); } }catch(e){}
            }catch(e){}

            try{
                var metodoSel = qs('sup-metodo');
                if(metodoSel){
                    try{ metodoSel.disabled = false; }catch(e){}
                    try{ metodoSel.removeAttribute('data-locked'); }catch(e){}
                }
                removeHidden('metodo_exec', form);
            }catch(e){}

            try{ input.removeAttribute('data-loaded-code'); }catch(e){}
            try{ syncPrevHidden(); }catch(e){}
            try{ syncDisabledToHidden(); }catch(e){}
        }

        // helper seguro para appendChild (evita TypeError quando variáveis não são Nodes)
        function safeAppend(parent, child, label){ try{ if(!parent || typeof parent.appendChild !== 'function'){ console.warn('safeAppend: parent invalid', label, parent); return; } if(!child || !(child.nodeType===1 || child.nodeType===11)){ console.warn('safeAppend: child invalid', label, child); return; } parent.appendChild(child); }catch(e){ console.warn('safeAppend error', label, e); } }

        // controla se já estamos exibindo/consulta a lista (toggle)
        var listed = false;

    // Ensure hidden tanque_id exists
        var hidTank = qs('input[name="tanque_id"][data-hidden]');
    if(!hidTank){ hidTank = ensureHidden('tanque_id', form); }

    // Ensure hidden tanque_codigo (texto) exists and is kept in sync
    var hidTankCode = ensureHidden('tanque_codigo', form);

    // Ensure hidden JSON payload for compartimentos exists and can be populated
    function ensureHiddenJsonField(form){ var el = q1('input[name="compartimentos_avanco_json"][data-hidden]', form); if(!el){ el = document.createElement('input'); el.type='hidden'; el.name = 'compartimentos_avanco_json'; el.setAttribute('data-hidden','1'); form.appendChild(el); } return el; }

    function buildCompartimentosJSONFromNComp(form){
        try{
            var totalEl = qs('sup-n-comp') || q1('input[name="numero_compartimentos"]', form);
            var hid = ensureHiddenJsonField(form);
            var total = totalEl ? parseInt(totalEl.value,10) : 0;
            if(!total || isNaN(total) || total < 1){ hid.value = '{}'; return; }
            var payload = Object.create(null);
            for(var i=1;i<=total;i++){ payload[String(i)] = { mecanizada: 0, fina: 0 }; }
            hid.value = JSON.stringify(payload);
            return;
        }catch(e){ /* noop */ }
    }
        function populateFromTankData(t, codigo){
            if(!t) return;

            // Muito importante: ao trocar o tanque, limpar campos do dia para não reaproveitar valores do tanque/RDO anterior.
            clearOperationalFields();
            try{
                ['sup-ica','sup-camba'].forEach(function(id){ var el = qs(id); if(el){ try{ el.removeAttribute('data-user-edited'); }catch(e){} } });
            }catch(e){}

            hidTank.value = t.id || '';
            var codeVal = (codigo || t.tanque_codigo || t.codigo || t.code || t.cod || '').toString();
            try{ hidTankCode.value = codeVal || ''; }catch(e){}
            try{ setValue('sup-tanque-cod', codeVal || ''); }catch(e){}
            try{ if (input) { input.setAttribute('data-loaded-code', codeVal || ''); input.dispatchEvent(new Event('input',{ bubbles: true })); } }catch(e){}

            setValue('sup-tanque-nome', t.nome_tanque || t.tanque_codigo || t.nome || '');
            setSelect('sup-tipo-tanque', t.tipo_tanque || t.tipo || '');
            setValue('sup-n-comp', t.numero_compartimentos || t.n_compartimentos || t.numero_compartimento || '');
            try{ triggerInputEvent('sup-n-comp'); }catch(e){}
            setValue('sup-gavetas', t.gavetas || t.gavetas_count || '');
            setValue('sup-patamar', t.patamares || t.patamar || '');
            setValue('sup-volume', t.volume_tanque_exec || t.volume || '');
            setValue('sup-prev-ensac', t.ensacamento_prev || t.ensacamento_previsao || '');
            setValue('sup-prev-ica', t.icamento_prev || t.icamento_previsao || '');
            setValue('sup-prev-camba', t.cambagem_prev || t.cambagem_previsao || '');
            try{ syncPrevHidden(); }catch(e){}

            // lock basic fields (same behaviour as load button)
            try{
                ['sup-tanque-nome','sup-n-comp','sup-gavetas','sup-patamar','sup-volume','sup-prev-ensac','sup-prev-ica','sup-prev-camba'].forEach(function(id){
                    var el = qs(id); if(!el) return; try{ el.readOnly = true; }catch(e){}; el.setAttribute && el.setAttribute('data-locked','1');
                });
            }catch(e){}

            try{
                var tipoSel = qs('sup-tipo-tanque');
                if(tipoSel){
                    if(t.tipo_tanque || t.tipo){
                        try{ tipoSel.value = t.tipo_tanque || t.tipo; }catch(e){}
                        var hidTipo = ensureHidden('tipo_tanque', form);
                        hidTipo.value = t.tipo_tanque || t.tipo || '';
                        tipoSel.disabled = true; tipoSel.setAttribute('data-locked','1');
                    } else {
                        tipoSel.disabled = false;
                        var hidTipo2 = q1('input[name="tipo_tanque"][data-hidden]', form); if(hidTipo2) hidTipo2.remove();
                    }
                }
            }catch(e){}

            try{
                var servSelect = qs('sup-servico');
                if(servSelect){
                    if(t.servico_exec || t.servico){
                        try{ servSelect.value = t.servico_exec || t.servico; }catch(e){}
                        var hid = ensureHidden('servico_exec', form);
                        hid.value = t.servico_exec || t.servico || '';
                        servSelect.disabled = true; servSelect.setAttribute('data-locked','1');
                        try{
                            var servVisible = qs('sup-servico-input');
                            if(servVisible){
                                var wrap = servSelect.closest ? servSelect.closest('.dropdown-select') : null;
                                var dd = wrap ? wrap.querySelector('select.dropdown-data') : document.querySelector('select.dropdown-data');
                                var val = t.servico_exec || t.servico || '';
                                var opt = dd ? dd.querySelector('option[value="'+val+'"]') : null;
                                servVisible.value = opt ? opt.textContent : val;
                                servVisible.readOnly = true; servVisible.setAttribute('data-locked','1');
                            }
                        }catch(e){}
                    } else {
                        servSelect.disabled = false; var hid2 = q1('input[name="servico_exec"][data-hidden]', form); if(hid2) hid2.remove();
                        try{ var servVisible2 = qs('sup-servico-input'); if(servVisible2){ servVisible2.readOnly = false; servVisible2.removeAttribute('data-locked'); } }catch(e){}
                    }
                }
            }catch(e){ console.warn('preenchimento servico failed', e); }

            // Método: preencher e bloquear select `sup-metodo` quando disponível no detalhe do tanque
            try{
                var metodoSel = qs('sup-metodo');
                if(metodoSel){
                    if(t.metodo_exec || t.metodo){
                        try{ metodoSel.value = t.metodo_exec || t.metodo; }catch(e){}
                        var hidm = ensureHidden('metodo_exec', form);
                        hidm.value = t.metodo_exec || t.metodo || '';
                        metodoSel.disabled = true; metodoSel.setAttribute('data-locked','1');
                    } else {
                        metodoSel.disabled = false; var hidm2 = q1('input[name="metodo_exec"][data-hidden]', form); if(hidm2) hidm2.remove();
                    }
                }
            }catch(e){ console.warn('preenchimento metodo failed', e); }

            try{ input.setAttribute('data-loaded-code', codigo || (t.tanque_codigo||t.codigo||'')); }catch(e){}
            try{ syncDisabledToHidden(); }catch(e){}
            try{ buildCompartimentosJSONFromNComp(form); }catch(e){}

            // Blindagem final: se algum script copiar previsão -> dia, limpamos aqui.
            clearIfAutoCopiedDaily('sup-ica','sup-prev-ica');
            clearIfAutoCopiedDaily('sup-camba','sup-prev-camba');
        }

            // Helpers: detectar RDO atual, checar existência e controlar botões de submissão
            function getRdoId(){
                try{
                    var el = qs('sup-context-rdo') || q1('[data-rdo-id]') || q1('input[name="rdo_id"]');
                    if(!el) return '';
                    var v = el.getAttribute && (el.getAttribute('data-rdo-id') || el.getAttribute('data-rdo') || el.value);
                    if(v) return String(v).trim();
                    if(el.textContent) return String(el.textContent).trim();
                }catch(e){}
                return '';
            }

            function checkTypedCodeExistsInRdo(code){
                return new Promise(function(resolve, reject){
                    try{
                        var rdoId = getRdoId();
                        var osId = getOsId();
                        if(rdoId){
                            var url = '/api/rdo/tank/' + encodeURIComponent(code) + '/?rdo_id=' + encodeURIComponent(rdoId);
                            fetch(url, { credentials: 'same-origin' }).then(function(resp){
                                if(!resp.ok) return resolve(false);
                                return resp.json();
                            }).then(function(data){
                                if(!data) return resolve(false);
                                // endpoint may return {tank: null} or {tank: {...}}
                                var found = !!(data && (data.tank || data.exists || data.id || data.id === 0));
                                resolve(found);
                            }).catch(function(err){ resolve(false); });
                            return;
                        }
                        // fallback: check OS tanks list conservatively
                        if(osId){
                            var url2 = '/api/os/' + encodeURIComponent(osId) + '/tanks/?limit=200';
                            fetch(url2, { credentials: 'same-origin' }).then(function(resp){
                                if(!resp.ok) return resolve(false);
                                return resp.json();
                            }).then(function(data){
                                var arr = [];
                                if(!data) return resolve(false);
                                if(Array.isArray(data.tanks)) arr = data.tanks;
                                else if(Array.isArray(data.results)) arr = data.results;
                                else if(Array.isArray(data)) arr = data;
                                var codeNorm = (code||'').toString().trim().toLowerCase();
                                var exists = arr.some(function(t){
                                    try{ var c = (t.tanque_codigo || t.codigo || t.code || t.cod || '').toString().trim().toLowerCase(); return c === codeNorm; }catch(e){ return false; }
                                });
                                resolve(!!exists);
                            }).catch(function(){ resolve(false); });
                            return;
                        }
                        resolve(false);
                    }catch(e){ resolve(false); }
                });
            }

            function isCancelButton(el){
                if(!el) return false;
                try{
                    var name = (el.name||'').toString().toLowerCase();
                    if(name.indexOf('cancel') !== -1) return true;
                    var cls = (el.className||'').toString().toLowerCase(); if(cls.indexOf('cancel') !== -1 || cls.indexOf('btn-cancel') !== -1) return true;
                    var da = (el.getAttribute && (el.getAttribute('data-action')||'') ).toString().toLowerCase(); if(da.indexOf('cancel')!==-1) return true;
                    var aria = (el.getAttribute && (el.getAttribute('aria-label')||'') ).toString().toLowerCase(); if(aria.indexOf('cancel')!==-1 || aria.indexOf('cancelar')!==-1) return true;
                    var txt = (el.textContent||'').toString().trim().toLowerCase(); if(txt === 'cancel' || txt === 'cancelar' || txt.indexOf('cancel')!==-1) return true;
                }catch(e){}
                return false;
            }

            function disableSubmissionButtons(){
                try{
                    var els = Array.prototype.slice.call(form.querySelectorAll('button, input[type="submit"], input[type="button"]'));
                    els.forEach(function(el){
                        try{
                            // Não desabilitar botões relacionados à seleção/carregamento de tanques
                            if(isCancelButton(el)) return;
                            if(typeof listBtn !== 'undefined' && listBtn && (el === listBtn)) return;
                            if(typeof loadBtn !== 'undefined' && loadBtn && (el === loadBtn)) return;
                            if(quickList && quickList.contains && quickList.contains(el)) return;
                            if(quickWrap && quickWrap.contains && quickWrap.contains(el)) return;
                            if(el.classList && el.classList.contains('sup-tank-quick-item')) return;
                            if(el.getAttribute && el.getAttribute('data-tanque-id')) return;
                            // skip links
                            if(el.tagName && el.tagName.toLowerCase() === 'a') return;
                            el.setAttribute('data-disabled-by-dup','1');
                            try{ el.disabled = true; }catch(e){}
                            try{ el.classList && el.classList.add('disabled'); }catch(e){}
                            try{
                                // preserve inline styles to restore later
                                var prev = {
                                    bg: el.style.backgroundColor || '',
                                    color: el.style.color || '',
                                    cursor: el.style.cursor || '',
                                    opacity: el.style.opacity || '',
                                    pointerEvents: el.style.pointerEvents || ''
                                };
                                try{ el.setAttribute('data-original-style', JSON.stringify(prev)); }catch(e){}
                                // apply blocked visual state
                                el.style.backgroundColor = '#d0d0d0';
                                el.style.color = '#6a6a6a';
                                el.style.cursor = 'not-allowed';
                                el.style.opacity = '0.7';
                                el.style.pointerEvents = 'none';
                            }catch(e){}
                        }catch(e){}
                    });
                }catch(e){}
            }

            function enableSubmissionButtons(){
                try{
                    var els = Array.prototype.slice.call(form.querySelectorAll('[data-disabled-by-dup]'));
                    els.forEach(function(el){
                        try{ el.removeAttribute('data-disabled-by-dup'); }catch(e){}
                        try{ el.disabled = false; }catch(e){}
                        try{ el.classList && el.classList.remove('disabled'); }catch(e){}
                        try{
                            var prevRaw = el.getAttribute && el.getAttribute('data-original-style');
                            if(prevRaw){
                                try{
                                    var prev = JSON.parse(prevRaw);
                                    el.style.backgroundColor = prev.bg || '';
                                    el.style.color = prev.color || '';
                                    el.style.cursor = prev.cursor || '';
                                    el.style.opacity = prev.opacity || '';
                                    el.style.pointerEvents = prev.pointerEvents || '';
                                }catch(e){}
                                try{ el.removeAttribute('data-original-style'); }catch(e){}
                            } else {
                                // remove blocking visuals if nothing to restore
                                el.style.backgroundColor = '';
                                el.style.color = '';
                                el.style.cursor = '';
                                el.style.opacity = '';
                                el.style.pointerEvents = '';
                            }
                        }catch(e){}
                    });
                }catch(e){}
            }

            function getOsId(){
                var el = qs('sup-context-os');
                if(!el) return '';
                var direct = el.getAttribute('data-os-id') || el.getAttribute('data-os-code');
                if(direct){
                    var d = String(direct).trim();
                    if(d === '-' || d === '—') return '';
                    return d;
                }
                var txt = (el.textContent || '').toString().trim();
                if(!txt || txt === '-' || txt === '—') return '';
                try{
                    var mapEl = document.querySelector('[data-numero-os="' + (window.CSS && CSS.escape ? CSS.escape(txt) : txt) + '"]') || document.querySelector('[data-os="' + (window.CSS && CSS.escape ? CSS.escape(txt) : txt) + '"]');
                    if(mapEl){ var mapped = mapEl.getAttribute('data-os-id') || mapEl.getAttribute('data-os'); if(mapped){ var m = String(mapped).trim(); if(m === '-' || m === '—') return ''; return m; } }
                }catch(e){}
                return txt;
            }

            // -------------------------
            // Lista rápida de tanques
            // -------------------------
            function _normText(s){ try{ return String(s||'').trim(); }catch(e){ return ''; } }

            function _renderQuickList(items){
                if(!quickList) return;
                try{ while(quickList.firstChild) quickList.removeChild(quickList.firstChild); }catch(e){}

                if(!items || !items.length){
                    try{
                        var empty = document.createElement('div');
                        empty.className = 'form-hint sup-tank-quick-empty';
                        empty.textContent = 'Nenhum tanque cadastrado nesta OS.';
                        quickList.appendChild(empty);
                    }catch(e){}
                    return;
                }

                items.forEach(function(t){
                    try{
                        var codigo = _normText(t.tanque_codigo || t.codigo || t.code || t.cod || '');
                        if(!codigo) return;
                        var nome = _normText(t.nome || t.nome_tanque || '');
                        var btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'btn-rdo small sup-tank-quick-item';
                        btn.setAttribute('role','option');
                        btn.setAttribute('data-tanque-id', _normText(t.id || ''));
                        btn.setAttribute('data-tanque-codigo', codigo);
                        btn.setAttribute('title','Clique para carregar este tanque');
                        btn.setAttribute('aria-label','Carregar tanque ' + (nome ? (codigo + ' ' + nome) : codigo));
                        btn.textContent = nome ? (codigo + ' — ' + nome) : codigo;
                        btn.addEventListener('click', function(){
                            try{ _selectFromQuickList(t); }catch(e){}
                        });
                        quickList.appendChild(btn);
                    }catch(e){}
                });
            }

            function _fetchAllTanksForOs(osId){
                // Endpoint pagina com page_size máx=5; buscar todas as páginas.
                var all = [];
                var page = 1;
                var pageSize = 5;
                var base = '/api/os/' + encodeURIComponent(osId) + '/tanks/?page_size=' + pageSize;

                function step(){
                    var url = base + '&page=' + page;
                    return fetch(url, { credentials: 'same-origin' }).then(function(resp){
                        if(!resp.ok) throw new Error('http ' + resp.status);
                        return resp.json();
                    }).then(function(data){
                        var results = (data && (data.results || data.tanks)) || [];
                        if(Array.isArray(results)) all = all.concat(results);
                        var totalPages = (data && data.total_pages) ? parseInt(data.total_pages,10) : 1;
                        if(!totalPages || isNaN(totalPages)) totalPages = 1;
                        if(page < totalPages){ page += 1; return step(); }
                        return all;
                    });
                }
                return step();
            }

            var _quickListLastOs = null;
            var _quickListLoading = false;
            function refreshQuickList(force){
                if(!quickList) return;
                if(_quickListLoading) return;
                var osId = getOsId();
                if(!osId){
                    _quickListLastOs = null;
                    _renderQuickList([]);
                    return;
                }
                if(!force && _quickListLastOs === String(osId)) return;
                _quickListLastOs = String(osId);
                _quickListLoading = true;
                try{ quickList.setAttribute('aria-busy','true'); }catch(e){}

                _fetchAllTanksForOs(osId).then(function(items){
                    try{ _renderQuickList(items || []); }catch(e){}
                }).catch(function(){
                    try{ _renderQuickList([]); }catch(e){}
                }).finally(function(){
                    _quickListLoading = false;
                    try{ quickList.removeAttribute('aria-busy'); }catch(e){}
                });
            }

            function focusTankQuickSelection(){
                if(!quickList) { try{ input && input.focus(); }catch(e){}; return; }

                // garante que a lista esteja atualizada ao entrar na seção
                try{ refreshQuickList(false); }catch(e){}

                window.setTimeout(function(){
                    try{
                        var first = quickList.querySelector('.sup-tank-quick-item');
                        if(first){
                            try{ first.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }catch(e){}
                            try{ first.focus({ preventScroll: true }); }catch(e){ try{ first.focus(); }catch(e2){} }
                            return;
                        }
                    }catch(e){}
                    try{ input && input.focus(); }catch(e){}
                }, 0);
            }

            // Ao clicar na aba "Tanque & Ambiente", colocar a seleção de tanques como primeira ação
            try{
                var tankNavLink = q1('.supv-nav a[href="#sec-tanque"]');
                if(tankNavLink){
                    tankNavLink.addEventListener('click', function(){
                        window.setTimeout(function(){
                            try{ quickWrap && quickWrap.scrollIntoView({ block: 'start', inline: 'nearest' }); }catch(e){}
                            focusTankQuickSelection();
                        }, 0);
                    });
                }
            }catch(e){}

            // Também cobre navegação por hash (ex.: teclado / histórico)
            try{
                window.addEventListener('hashchange', function(){
                    try{
                        if((window.location && window.location.hash) === '#sec-tanque'){
                            window.setTimeout(function(){
                                try{ quickWrap && quickWrap.scrollIntoView({ block: 'start', inline: 'nearest' }); }catch(e){}
                                focusTankQuickSelection();
                            }, 0);
                        }
                    }catch(e){}
                });
            }catch(e){}

            function _selectFromQuickList(t){
                if(!t) return;
                var codigo = _normText(t.tanque_codigo || t.codigo || t.code || t.cod || '');
                if(!codigo) return;

                // Preservar o id do RdoTanque selecionado (importante para não disparar criação duplicada)
                try{ hidTank.value = _normText(t.id || ''); }catch(e){}
                try{ hidTankCode.value = codigo; }catch(e){}
                try{ setValue('sup-tanque-cod', codigo); }catch(e){}

                var url = '/api/rdo/tank/' + encodeURIComponent(codigo) + '/';
                try{
                    var osIdCtx = getOsId();
                    if(osIdCtx){
                        url += '?os_id=' + encodeURIComponent(osIdCtx);
                    }
                }catch(e){}
                fetch(url, { credentials: 'same-origin' }).then(function(resp){
                    if(!resp.ok) throw new Error('http ' + resp.status);
                    return resp.json();
                }).then(function(data){
                    var detail = (data && (data.tank || data)) || {};
                    // Garantir que o tanque_id enviado seja o RdoTanque da OS (e não o Tanque canônico)
                    try{ detail.id = t.id; }catch(e){}
                    if(!detail.tanque_codigo) detail.tanque_codigo = codigo;
                    if(!detail.nome_tanque && (t.nome || t.nome_tanque)) detail.nome_tanque = t.nome || t.nome_tanque;
                    populateFromTankData(detail, codigo);
                }).catch(function(){
                    // fallback: preencher pelo menos código/nome e n_compartimentos
                    var fallback = {
                        id: t.id,
                        tanque_codigo: codigo,
                        nome_tanque: t.nome || t.nome_tanque || '',
                        numero_compartimentos: t.numero_compartimentos
                    };
                    try{ populateFromTankData(fallback, codigo); }catch(e){}
                });
            }

            // Atualizar automaticamente quando a OS do modal mudar
            try{
                var osEl = qs('sup-context-os');
                if(osEl && window.MutationObserver){
                    var mo = new MutationObserver(function(){ refreshQuickList(false); });
                    mo.observe(osEl, { childList: true, characterData: true, subtree: true, attributes: true });
                }
            }catch(e){}
            // Primeira carga quando o usuário entra na seção (ou quando o modal abre)
            try{ refreshQuickList(true); }catch(e){}


        // Listar tanques da OS: popula datalist com opções (value = tanque_codigo)
        function doListTanks(){
            if(!listBtn) return;
            if(listed) return;
            listed = true; // avoid duplicate concurrent requests; will be reset on error so user can retry
            var osId = getOsId();
            var url = osId ? ('/api/os/' + encodeURIComponent(osId) + '/tanks/?limit=200') : '/api/rdo/tanks/?limit=200';
            listBtn.disabled = true;
            var prevText = listBtn.textContent;
            listBtn.textContent = 'Carregando...';
            fetch(url, { credentials: 'same-origin' }).then(function(resp){
                listBtn.disabled = false; listBtn.textContent = prevText || 'Listar';
                if(!resp.ok) { console.warn('failed to list tanks for os', resp.status); listed = false; return; }
                return resp.json();
            }).then(function(data){
                if(!data) return;
                var arr = [];
                if (Array.isArray(data.tanks)) arr = data.tanks;
                else if (Array.isArray(data.results)) arr = data.results;
                else if (Array.isArray(data)) arr = data;

                // clear datalist
                while(datalist.firstChild) datalist.removeChild(datalist.firstChild);

                if(!arr.length){
                    // Avisar que não há tanques cadastrados
                    try{ alert('Nenhum tanque cadastrado para esta OS.'); }catch(e){ console.warn('no tanks'); }
                    listed = false;
                    return;
                }
                // Deduplicate tanks by code, preferring the last occurrence (mais recente RDO)
                var mapByCode = Object.create(null);
                arr.forEach(function(t){
                    var codeKey = (t.tanque_codigo || t.codigo || t.code || t.cod || t.id || '').toString();
                    if(!codeKey) return; // skip empty
                    // overwrite previous entries so the last item in `arr` wins
                    mapByCode[codeKey] = t;
                });
                var uniqueArr = Object.keys(mapByCode).map(function(k){ return mapByCode[k]; });

                // popular datalist e abrir modal com opções selecionáveis (usar uniqueArr)
                uniqueArr.forEach(function(t){
                    var opt = document.createElement('option');
                    opt.value = t.tanque_codigo || t.codigo || t.id || t.code || t.cod || '';
                    datalist.appendChild(opt);
                });

                // Detectar se o que o usuário escreveu corresponde a um tanque já existente
                function _normName(s){ try{ if(!s && s!==0) return ''; var str=String(s).trim(); str = str.normalize ? str.normalize('NFD').replace(/[\u0300-\u036f]/g,'') : str.replace(/[\u0300-\u036f]/g,''); str = str.replace(/\s+/g,' '); return str.toLowerCase(); }catch(e){ return (String(s||'').trim()).toLowerCase(); } }
                function _normCode(s){ try{ if(!s && s!==0) return ''; var str=String(s).trim(); str = str.normalize ? str.normalize('NFD').replace(/[\u0300-\u036f]/g,'') : str.replace(/[\u0300-\u036f]/g,''); str = str.replace(/\s+/g,''); return str.toLowerCase(); }catch(e){ return (String(s||'').replace(/\s+/g,'')).toLowerCase(); } }

                var typedCodeRaw = (input && input.value) ? (input.value||'').toString() : '';
                var typedNameEl = q1('[name="sup-tanque-nome"]', form) || q1('[name="sup-tanque-nome"]');
                var typedNameRaw = typedNameEl ? (typedNameEl.value||'').toString() : '';
                var typedCode = _normCode(typedCodeRaw);
                var typedName = _normName(typedNameRaw);
                var matchesTyped = false;
                var matchingCodes = Object.create(null);
                try{
                    uniqueArr.forEach(function(t){
                        try{
                            var codeRaw = (t.tanque_codigo||t.codigo||t.code||t.cod||'').toString();
                            var nameRaw = (t.nome_tanque||t.nome||'').toString();
                            var code = _normCode(codeRaw);
                            var name = _normName(nameRaw);
                            if (typedCode && code && code === typedCode) { matchesTyped = true; matchingCodes[code] = true; }
                            if (typedName && name && name === typedName) { matchesTyped = true; matchingCodes[code] = true; }
                        }catch(e){}
                    });
                }catch(e){}

                // Construir modal de seleção (design moderno: cards, verde/branco/preto)
                try{
                    var modal = document.getElementById('sup-tank-list-modal');
                    var isMobile = (window.innerWidth <= 640) || (/Mobi|Android|iPhone|iPad|Phone/i.test(navigator.userAgent || ''));

                    // If mobile, create a dedicated bottom-sheet modal (unique ID/class). Desktop keeps existing modal.
                    if(isMobile){
                        var existingMobile = document.getElementById('sup-tank-list-modal-mobile');
                        if(existingMobile && existingMobile.parentNode) existingMobile.parentNode.removeChild(existingMobile);
                        var modalMobile = document.createElement('div'); modalMobile.id = 'sup-tank-list-modal-mobile'; modalMobile.className = 'sup-tank-list-modal-mobile';
                        modalMobile.style.position = 'fixed'; modalMobile.style.inset = '0'; modalMobile.style.zIndex = 100000; modalMobile.style.display = 'block';

                        // backdrop
                        var backdropMobile = document.createElement('div'); backdropMobile.className = 'sup-tank-backdrop-mobile'; backdropMobile.style.position = 'fixed'; backdropMobile.style.inset = '0'; backdropMobile.style.background = 'rgba(0,0,0,0.0)'; backdropMobile.style.transition = 'background 180ms ease'; backdropMobile.style.zIndex = 99999;
                        safeAppend(modalMobile, backdropMobile, 'backdropMobile');

                        // panel (bottom sheet)
                        var panel = document.createElement('div');
                        panel.id = 'sup-tank-panel-mobile'; panel.className = 'sup-tank-panel-mobile';
                        panel.style.position = 'fixed'; panel.style.left = '0'; panel.style.right = '0'; panel.style.bottom = '0'; panel.style.maxHeight = '92vh'; panel.style.height = 'auto'; panel.style.background = '#fff'; panel.style.borderRadius = '12px 12px 0 0'; panel.style.boxShadow = '0 -8px 30px rgba(0,0,0,0.12)'; panel.style.overflow = 'hidden'; panel.style.transition = 'transform 300ms cubic-bezier(.2,.9,.2,1), opacity 200ms ease'; panel.style.transform = 'translateY(100%)'; panel.style.opacity = '0'; panel.style.fontFamily = 'Inter, system-ui, -apple-system, Roboto, "Helvetica Neue", Arial';

                        // Mobile header with drag handle and close
                        var headerMobile = document.createElement('div'); headerMobile.style.display = 'flex'; headerMobile.style.flexDirection = 'column'; headerMobile.style.alignItems = 'center'; headerMobile.style.padding = '10px'; headerMobile.style.borderBottom = '1px solid #eee'; headerMobile.style.background = '#eaf6ee';
                        var drag = document.createElement('div'); drag.style.width = '36px'; drag.style.height = '4px'; drag.style.borderRadius = '4px'; drag.style.background = '#d6eeda'; drag.style.marginBottom = '8px'; headerMobile.appendChild(drag);
                        var headerRow = document.createElement('div'); headerRow.style.display = 'flex'; headerRow.style.width = '100%'; headerRow.style.alignItems = 'center'; headerRow.style.justifyContent = 'space-between';
                        var titleM = document.createElement('div'); titleM.style.fontWeight = '700'; titleM.style.color = '#1b5e20'; titleM.textContent = 'Tanques da OS'; headerRow.appendChild(titleM);
                        var closeM = document.createElement('button'); closeM.type = 'button'; closeM.className = 'btn-rdo ghost small'; closeM.textContent = '×'; closeM.style.border = 'none'; closeM.style.background = 'transparent'; closeM.style.fontSize = '18px'; closeM.style.cursor = 'pointer'; closeM.setAttribute('aria-label','Fechar'); headerRow.appendChild(closeM);
                        headerMobile.appendChild(headerRow);
                        safeAppend(panel, headerMobile, 'headerMobile');
                        // attach search/content/footer to mobile panel later (after they are created)
                        safeAppend(modalMobile, panel, 'panel -> modalMobile');
                        try{ var supOverlay = document.getElementById('supv-modal-overlay') || document.getElementById('modal-supervisor-overlay'); if(supOverlay && supOverlay.parentNode){ safeAppend(supOverlay, modalMobile, 'supOverlay append modalMobile'); } else { safeAppend(document.body, modalMobile, 'body append modalMobile'); } }catch(e){ safeAppend(document.body, modalMobile, 'body append modalMobile fallback'); }

                        // wire handlers to close mobile
                        closeM.addEventListener('click', function(e){ try{ e.stopPropagation(); }catch(_){} try{ if(modalMobile && modalMobile.parentNode){ modalMobile.parentNode.removeChild(modalMobile); } listed = false; }catch(e){} });
                        backdropMobile.addEventListener('click', function(e){ try{ if(modalMobile && modalMobile.parentNode){ modalMobile.parentNode.removeChild(modalMobile); } listed = false; }catch(e){} });

                        // make modal variable point to mobile for shared close logic below
                        modal = modalMobile;

                        // animate open
                        window.requestAnimationFrame(function(){ try{ backdropMobile.style.background = 'rgba(0,0,0,0.45)'; }catch(e){} try{ panel.style.transform = 'translateY(0)'; }catch(e){} try{ panel.style.opacity = '1'; }catch(e){} });

                    } else {
                        // desktop modal (existing behavior)
                        if(modal && modal.parentNode) modal.parentNode.removeChild(modal);
                        modal = document.createElement('div'); modal.id = 'sup-tank-list-modal'; modal.className = 'sup-tank-list-modal';
                        modal.style.position = 'fixed'; modal.style.inset = '0'; modal.style.background = 'rgba(0,0,0,0.45)'; modal.style.zIndex = 99999; modal.style.display = 'flex'; modal.style.alignItems = 'center'; modal.style.justifyContent = 'center';

                        var panel = document.createElement('div');
                        panel.style.width = '760px'; panel.style.maxWidth = '95%'; panel.style.maxHeight = '78vh'; panel.style.display = 'flex'; panel.style.flexDirection = 'column'; panel.style.borderRadius = '12px'; panel.style.overflow = 'hidden'; panel.style.boxShadow = '0 12px 40px rgba(0,0,0,0.35)'; panel.style.background = '#fff'; panel.style.fontFamily = 'Inter, system-ui, -apple-system, Roboto, "Helvetica Neue", Arial';
                        // transitions for nicer open/close
                        modal.style.transition = 'background 180ms ease';
                        panel.style.transition = 'transform 220ms cubic-bezier(.2,.9,.2,1), opacity 200ms ease';
                        panel.style.transformOrigin = 'center center';
                        panel.style.opacity = '0';
                        // Header
                        var header = document.createElement('div'); header.style.display = 'flex'; header.style.alignItems = 'center'; header.style.justifyContent = 'space-between'; header.style.padding = '14px 18px'; header.style.background = '#eaf6ee'; header.style.borderBottom = '1px solid #e6efe6';
                        var title = document.createElement('div'); title.style.display = 'flex'; title.style.flexDirection = 'column';
                        var titleMain = document.createElement('div'); titleMain.textContent = 'Tanques da OS'; titleMain.style.fontSize = '16px'; titleMain.style.fontWeight = '700'; titleMain.style.color = '#1b5e20';
                        var titleSub = document.createElement('div'); titleSub.textContent = 'Selecione um tanque para preencher o formulário'; titleSub.style.fontSize = '12px'; titleSub.style.color = '#2e7d32';
                        title.appendChild(titleMain); title.appendChild(titleSub);
                        var closeX = document.createElement('button'); closeX.type = 'button'; closeX.className = 'btn-rdo ghost small'; closeX.textContent = '×'; closeX.setAttribute('aria-label','Fechar'); closeX.style.border = 'none'; closeX.style.background = 'transparent'; closeX.style.fontSize = '18px'; closeX.style.cursor = 'pointer';
                        header.appendChild(title); header.appendChild(closeX);
                        // append header to panel using safeAppend (search/content/footer will be appended later)
                        safeAppend(panel, header, 'header (desktop)');

                        safeAppend(modal, panel, 'modal <- panel (desktop)');
                        try{ var supOverlay2 = document.getElementById('supv-modal-overlay') || document.getElementById('modal-supervisor-overlay'); if(supOverlay2 && supOverlay2.parentNode){ safeAppend(supOverlay2, modal, 'supOverlay2 append modal'); } else { safeAppend(document.body, modal, 'body append modal'); } }catch(e){ safeAppend(document.body, modal, 'body append modal fallback'); }
                        // attach close handlers (desktop)
                        closeX.addEventListener('click', function(e){ try{ e.stopPropagation(); }catch(_){} try{ if(modal && modal.parentNode){ modal.parentNode.removeChild(modal); } listed = false; }catch(e){} });
                        modal.addEventListener('click', function(e){ try{ if(e.target === modal){ if(modal && modal.parentNode){ modal.parentNode.removeChild(modal); } listed = false; } }catch(err){} });

                        // animate open (next frame)
                        window.requestAnimationFrame(function(){ try{ modal.style.background = 'rgba(0,0,0,0.45)'; }catch(e){} try{ panel.style.transform = 'scale(1) translateY(0)'; }catch(e){} try{ panel.style.opacity = '1'; }catch(e){} });
                    }

                    // Search
                    var searchWrap = document.createElement('div'); searchWrap.style.padding = '12px 18px'; searchWrap.style.borderBottom = '1px solid #f3f3f3';
                    var searchInput = document.createElement('input'); searchInput.type = 'search'; searchInput.placeholder = 'Filtrar por código ou nome do tanque'; searchInput.style.width = '100%'; searchInput.style.padding = '10px 12px'; searchInput.style.border = '1px solid #e0e0e0'; searchInput.style.borderRadius = '8px'; searchInput.style.fontSize = '14px';
                    searchWrap.appendChild(searchInput); panel.appendChild(searchWrap);

                    // Content
                    var content = document.createElement('div'); content.style.overflow = 'auto'; content.style.padding = '12px 16px'; content.style.display = 'grid'; content.style.gridTemplateColumns = 'repeat(2, 1fr)'; content.style.gap = '12px'; content.style.alignContent = 'start';
                    try{ if(typeof isMobile !== 'undefined' && isMobile){ content.style.gridTemplateColumns = '1fr'; content.style.padding = '12px 12px 20px'; content.style.gap = '10px'; } }catch(e){}

                    uniqueArr.forEach(function(t){
                        var code = (t.tanque_codigo || t.codigo || t.code || t.cod || '').toString();
                        var name = (t.nome_tanque || t.nome || '(sem nome)').toString();
                        var card = document.createElement('div');
                        card.className = 'tank-card';
                        card.setAttribute('data-code', code.toLowerCase());
                        card.setAttribute('data-name', name.toLowerCase());
                        // destacar se for correspondência ao que o usuário digitou
                        try{
                            if (matchingCodes && matchingCodes[_normCode(code)]){
                                card.style.border = '2px solid #c62828';
                                var badge = document.createElement('div'); badge.textContent = 'Já cadastrado'; badge.style.background = '#ffebee'; badge.style.color = '#c62828'; badge.style.padding = '4px 8px'; badge.style.borderRadius = '6px'; badge.style.fontSize = '12px'; badge.style.marginBottom = '8px'; badge.style.display = 'inline-block';
                                try{ card.appendChild(badge); }catch(_){}
                            }
                        }catch(e){}
                        card.style.background = '#ffffff'; card.style.border = '1px solid #eef6ee'; card.style.borderRadius = '10px'; card.style.padding = '12px'; card.style.display = 'flex'; card.style.flexDirection = 'column'; card.style.justifyContent = 'space-between';
                        card.style.transition = 'transform 150ms ease, box-shadow 150ms ease';
                        try{ if(typeof isMobile !== 'undefined' && isMobile){ card.style.width = '100%'; card.style.boxSizing = 'border-box'; } }catch(e){}
                        card.addEventListener('mouseenter', function(){ try{ card.style.transform = 'scale(1.02)'; card.style.boxShadow = '0 8px 24px rgba(6,90,30,0.08)'; }catch(e){} });
                        card.addEventListener('mouseleave', function(){ try{ card.style.transform = 'scale(1)'; card.style.boxShadow = 'none'; }catch(e){} });

                        var meta = document.createElement('div'); meta.style.marginBottom = '10px';
                        var codeEl = document.createElement('div'); codeEl.textContent = code; codeEl.style.fontWeight = '700'; codeEl.style.fontSize = '15px'; codeEl.style.color = '#0b6623';
                        var nameEl = document.createElement('div'); nameEl.textContent = name; nameEl.style.fontSize = '13px'; nameEl.style.color = '#333'; nameEl.style.marginTop = '4px';
                        meta.appendChild(codeEl); meta.appendChild(nameEl);

                        var actions = document.createElement('div'); actions.style.display = 'flex'; actions.style.gap = '8px'; actions.style.justifyContent = 'flex-end';
                        var loadBtnItem = document.createElement('button'); loadBtnItem.type = 'button'; loadBtnItem.className = 'btn-rdo primary small'; loadBtnItem.textContent = 'Carregar'; loadBtnItem.style.background = '#1b5e20'; loadBtnItem.style.color = '#fff'; loadBtnItem.style.border = 'none'; loadBtnItem.style.padding = '8px 12px'; loadBtnItem.style.borderRadius = '6px'; loadBtnItem.style.cursor = 'pointer';
                        loadBtnItem.addEventListener('click', function(){
                            loadBtnItem.disabled = true; loadBtnItem.textContent = 'Carregando...';
                                var urlDetail = '/api/rdo/tank/' + encodeURIComponent(code) + '/';
                                try{
                                    var osIdCtx2 = getOsId();
                                    if(osIdCtx2){
                                        urlDetail += '?os_id=' + encodeURIComponent(osIdCtx2);
                                    }
                                }catch(e){}
                            fetch(urlDetail, { credentials: 'same-origin' }).then(function(resp){
                                loadBtnItem.disabled = false; loadBtnItem.textContent = 'Carregar';
                                if(resp.status === 404){ alert('Detalhe do tanque não encontrado.'); return null; }
                                if(!resp.ok){ if(resp.status !== 404){ console.warn('failed to fetch tank detail', resp.status); } return null; }
                                return resp.json();
                            }).then(function(data){
                                if(!data) return;
                                var payload = data.tank || data;
                                populateFromTankData(payload, code);
                                try{ closeModal(); }catch(err){}
                            }).catch(function(err){ loadBtnItem.disabled = false; loadBtnItem.textContent = 'Carregar'; try{ if(!(err && err.status === 404)){ console.warn('error fetching tank detail', err); alert('Erro ao carregar detalhes do tanque.'); } }catch(e){} });
                        });

                        var selBtn = document.createElement('button'); selBtn.type='button'; selBtn.className='btn-rdo ghost small'; selBtn.textContent='Selecionar'; selBtn.style.background='transparent'; selBtn.style.border='1px solid #d0d0d0'; selBtn.style.padding='8px 10px'; selBtn.style.borderRadius='6px'; selBtn.style.cursor='pointer';
                        selBtn.addEventListener('click', function(){
                            try{
                                // populate fields immediately using the data we already have (no extra fetch)
                                setValue('sup-tanque-cod', code);
                                if (input) input.dispatchEvent(new Event('input',{ bubbles: true }));
                                try{ populateFromTankData(t, code); }catch(e){}
                            }catch(e){ console.warn('select tank failed', e); }
                            try{ closeModal(); }catch(err){}
                        });

                        // subtle button lift on hover
                        try{ loadBtnItem.style.transition = 'transform 120ms ease'; loadBtnItem.addEventListener('mouseenter', function(){ loadBtnItem.style.transform='translateY(-2px)'; }); loadBtnItem.addEventListener('mouseleave', function(){ loadBtnItem.style.transform=''; }); }catch(e){}
                        try{ selBtn.style.transition = 'transform 120ms ease'; selBtn.addEventListener('mouseenter', function(){ selBtn.style.transform='translateY(-2px)'; }); selBtn.addEventListener('mouseleave', function(){ selBtn.style.transform=''; }); }catch(e){}
                        actions.appendChild(selBtn); actions.appendChild(loadBtnItem);
                        card.appendChild(meta); card.appendChild(actions);
                        content.appendChild(card);
                    });

                    // If the user typed a code/name that matches existing tank(s), show alert banner
                    try{
                        if (matchesTyped) {
                            var alertDiv = document.createElement('div');
                            alertDiv.textContent = 'Atenção: já existe um tanque com o mesmo código ou nome nesta OS.';
                            alertDiv.style.background = '#fff3f3';
                            alertDiv.style.color = '#c62828';
                            alertDiv.style.padding = '10px 14px';
                            alertDiv.style.margin = '8px 12px';
                            alertDiv.style.borderRadius = '8px';
                            alertDiv.style.fontWeight = '600';
                            try{ panel.appendChild(alertDiv); }catch(_){ }
                        }
                    }catch(e){}

                    panel.appendChild(content);

                    // If mobile panel was created earlier, append the real search/content/footer into it now
                    try{
                        var mobilePanel = document.getElementById('sup-tank-panel-mobile');
                        if(mobilePanel){
                            try{ if(searchWrap && (searchWrap.nodeType === 1 || searchWrap.nodeType === 11)) mobilePanel.appendChild(searchWrap); }catch(e){}
                            try{ if(content && (content.nodeType === 1 || content.nodeType === 11)) mobilePanel.appendChild(content); }catch(e){}
                            try{ if(footer && (footer.nodeType === 1 || footer.nodeType === 11)) mobilePanel.appendChild(footer); }catch(e){}
                        }
                    }catch(e){}

                    // centralized close function and Esc handler (animated)
                    var _modalClosing = false;
                    function closeModal(){
                        if(_modalClosing) return; _modalClosing = true;
                        try{ document.removeEventListener('keydown', onModalKeydown); }catch(e){}
                        try{
                            // animate backdrop fade and panel scale/opacity
                            try{ modal.style.background = 'rgba(0,0,0,0)'; }catch(e){}
                            try{ panel.style.opacity = '0'; }catch(e){}
                            try{ if(typeof usingOverlay !== 'undefined' && usingOverlay){ panel.style.transform = 'scale(0.98)'; } else { panel.style.transform = 'scale(0.98) translateY(8px)'; } }catch(e){}
                        }catch(e){}
                        // remove after transition
                        setTimeout(function(){ try{ if(modal && modal.parentNode){ modal.parentNode.removeChild(modal); } }catch(e){} listed = false; _modalClosing = false; }, 260);
                    }
                    function onModalKeydown(ev){ try{ if(!ev) return; if(ev.key === 'Escape' || ev.key === 'Esc'){ closeModal(); } }catch(e){} }
                    try{ document.addEventListener('keydown', onModalKeydown); }catch(e){}

                    // Footer
                    var footer = document.createElement('div'); footer.style.padding = '10px 16px'; footer.style.textAlign = 'right'; footer.style.borderTop = '1px solid #f3f3f3';
                    var closeBtn = document.createElement('button'); closeBtn.type='button'; closeBtn.className='btn-rdo ghost small'; closeBtn.textContent='Fechar'; closeBtn.style.padding='8px 12px'; closeBtn.style.borderRadius='6px'; closeBtn.style.cursor='pointer';
                    closeBtn.addEventListener('click', function(){ try{ closeModal(); }catch(err){} });
                    footer.appendChild(closeBtn); panel.appendChild(footer);

                    modal.appendChild(panel);

                    // close on backdrop
                    modal.addEventListener('click', function(e){ try{ if(e.target === modal){ closeModal(); } }catch(err){} });

                    // search/filter behavior
                    try{
                        searchInput.addEventListener('input', function(){ var q = (this.value||'').toLowerCase().trim(); var cards = content.querySelectorAll('.tank-card'); for(var i=0;i<cards.length;i++){ var c = cards[i]; var code = c.getAttribute('data-code')||''; var name = c.getAttribute('data-name')||''; if(!q || code.indexOf(q) !== -1 || name.indexOf(q) !== -1){ c.style.display='flex'; } else { c.style.display='none'; } } });
                    }catch(e){}

                    // append respecting supervisor overlay and prepare open animation
                    var supOverlay = document.getElementById('supv-modal-overlay') || document.getElementById('modal-supervisor-overlay');
                    try{
                        var usingOverlay = !!(supOverlay && supOverlay.parentNode);
                        var isMobile = (window.innerWidth <= 640) || (/Mobi|Android|iPhone|iPad|Phone/i.test(navigator.userAgent || ''));
                        if(usingOverlay){
                            // keep modal as a flex container but positioned relative to the overlay
                            modal.style.position = 'absolute';
                            modal.style.display = 'flex';
                            modal.style.justifyContent = 'center';
                            modal.style.background = 'transparent';
                            // panel will be centered by modal's flex layout
                            panel.style.position = 'relative';
                            panel.style.zIndex = '999999';
                            if(isMobile){
                                // bottom-sheet style for mobile when overlay present
                                modal.style.alignItems = 'flex-end';
                                panel.style.width = '100%';
                                panel.style.maxWidth = '100%';
                                panel.style.maxHeight = '92vh';
                                panel.style.borderRadius = '12px 12px 0 0';
                                panel.style.margin = '0';
                                panel.style.transform = 'translateY(12px)';
                                panel.style.opacity = '0';
                            } else {
                                panel.style.transform = 'scale(0.98)';
                                panel.style.opacity = '0';
                            }
                            supOverlay.appendChild(modal);
                        } else {
                            // center in flexbox; use translateY for subtle motion
                            modal.style.position = 'fixed';
                            modal.style.display = 'flex';
                            modal.style.justifyContent = 'center';
                            modal.style.background = 'rgba(0,0,0,0)';
                            if(isMobile){
                                // full-width bottom sheet for mobile
                                modal.style.alignItems = 'flex-end';
                                panel.style.width = '100%';
                                panel.style.maxWidth = '100%';
                                panel.style.maxHeight = '92vh';
                                panel.style.borderRadius = '12px 12px 0 0';
                                panel.style.margin = '0';
                                panel.style.transform = 'translateY(12px)';
                                panel.style.opacity = '0';
                            } else {
                                modal.style.alignItems = 'center';
                                modal.style.justifyContent = 'center';
                                panel.style.transform = 'scale(0.98) translateY(8px)';
                                panel.style.opacity = '0';
                            }
                            document.body.appendChild(modal);
                        }
                    }catch(e){ document.body.appendChild(modal); }

                    try{ searchInput.focus(); }catch(e){}

                    // animate open (next frame) to final state
                    try{
                        window.requestAnimationFrame(function(){
                            try{ modal.style.background = 'rgba(0,0,0,0.45)'; }catch(e){}
                            try{
                                if(typeof isMobile !== 'undefined' && isMobile){
                                    panel.style.transform = 'translateY(0)';
                                } else if(typeof usingOverlay !== 'undefined' && usingOverlay){
                                    panel.style.transform = 'scale(1)';
                                } else {
                                    panel.style.transform = 'scale(1) translateY(0)';
                                }
                            }catch(e){}
                            try{ panel.style.opacity = '1'; }catch(e){}
                        });
                    }catch(e){}
                }catch(e){ console.warn('error building tank list modal', e); }

            }).catch(function(err){
                try{ if(listBtn){ listBtn.disabled = false; listBtn.textContent = prevText || 'Listar'; } }catch(e){}
                listed = false;
                console.warn('error loading tanks for os', err);
            });
        }

        if(listBtn){
            listBtn.addEventListener('click', function(){ doListTanks(); });
        }

        // Auto-list disabled: listing is now explicit and requires the user to click "Listar".

        // enable load button when input has value
        // When the user edits the tank code after a load, clear previously-loaded metadata
        input.addEventListener('input', function(){
            var val = input.value && input.value.trim();
            if(loadBtn){ loadBtn.disabled = !val; }
            // keep hidden tanque_codigo synced to current typed code
            try{ hidTankCode.value = (val||''); }catch(e){}
            try{
                var loaded = input.getAttribute('data-loaded-code');
                if(loaded && loaded !== (val||'')){
                    // user changed the code after a load — clear locked metadata so they can load another
                    clearFields();
                }
            }catch(e){}
            // --- Novo: detectar se o código digitado já existe no mesmo RDO ---
            try{
                var typed = (val||'').toString();
                // if user already selected a tanque (hidTank filled) we should not block
                var alreadySelected = (hidTank && hidTank.value && String(hidTank.value).trim());
                if(!typed){ enableSubmissionButtons(); return; }
                if(alreadySelected){ enableSubmissionButtons(); return; }
                // perform existence check and disable/enable buttons accordingly
                // Guard against race: only apply result if the input value didn't change meanwhile
                (function(current){
                    checkTypedCodeExistsInRdo(current).then(function(exists){
                        try{
                            var now = input.value && input.value.trim();
                            if(String(now) !== String(current)){
                                // input changed since we started the request; ignore this result
                                return;
                            }
                            if(exists){ disableSubmissionButtons(); }
                            else { enableSubmissionButtons(); }
                        }catch(e){}
                    }).catch(function(){
                        try{ var now2 = input.value && input.value.trim(); if(String(now2) !== String(current)){ return; } }catch(e){}
                        enableSubmissionButtons();
                    });
                })(typed);
            }catch(e){}
        });

        // Sync previsões por-tanque para inputs hidden canônicos
        var prevEnsEl = byIdOrName('sup-prev-ensac');
        var prevIcaEl = byIdOrName('sup-prev-ica');
        var prevCamEl = byIdOrName('sup-prev-camba');
        var hidPrevEns = ensureHidden('ensacamento_prev', form);
        var hidPrevIca = ensureHidden('icamento_prev', form);
        var hidPrevCam = ensureHidden('cambagem_prev', form);
        function syncPrevHidden(){
            try{ hidPrevEns.value = prevEnsEl && prevEnsEl.value ? prevEnsEl.value : ''; }catch(e){}
            try{ hidPrevIca.value = prevIcaEl && prevIcaEl.value ? prevIcaEl.value : ''; }catch(e){}
            try{ hidPrevCam.value = prevCamEl && prevCamEl.value ? prevCamEl.value : ''; }catch(e){}
        }
        try{
            if(prevEnsEl){ prevEnsEl.addEventListener('input', syncPrevHidden); prevEnsEl.addEventListener('change', syncPrevHidden); }
            if(prevIcaEl){ prevIcaEl.addEventListener('input', syncPrevHidden); prevIcaEl.addEventListener('change', syncPrevHidden); }
            if(prevCamEl){ prevCamEl.addEventListener('input', syncPrevHidden); prevCamEl.addEventListener('change', syncPrevHidden); }
        }catch(e){}
        // initial sync
        syncPrevHidden();

        // Ensure disabled cleaning fields are mirrored to hidden inputs for submission
    var CLEANING_NAMES = ['sup-limp','sup-limp-acu','sup-limp-fina','sup-limp-fina-acu', 'compartimentos_avanco_json', 'compartimentos_avanco'];
        function syncDisabledToHidden(){
            CLEANING_NAMES.forEach(function(name){
                var el = byIdOrName(name);
                if(!el){ removeHidden(name, form); return; }
                // If the element already is a hidden input, keep it as-is.
                if(el.tagName && el.tagName.toLowerCase() === 'input' && el.type === 'hidden'){
                    return;
                }
                if(el.disabled || el.getAttribute('data-locked')){
                    var hid = ensureHidden(name, form);
                    try{ hid.value = el.value || ''; }catch(e){}
                } else {
                    // if enabled, we can remove the helper hidden to avoid duplicates
                    removeHidden(name, form);
                }
            });
        }
        // run once and before submit
        syncDisabledToHidden();
        try{ form.addEventListener('change', syncDisabledToHidden, true); }catch(e){}

        // Load button: fetch tank details and populate fields (explicit action)
        if(loadBtn) loadBtn.addEventListener('click', function(){
            var codigo = (input.value||'').trim();
            if(!codigo){ return; }
            loadBtn.disabled = true; loadBtn.textContent = 'Carregando...';
            var url = '/api/rdo/tank/' + encodeURIComponent(codigo) + '/';
            try{
                var osIdCtx3 = getOsId();
                if(osIdCtx3){
                    url += '?os_id=' + encodeURIComponent(osIdCtx3);
                }
            }catch(e){}
            fetch(url, { credentials: 'same-origin' }).then(function(resp){
                loadBtn.disabled = false; loadBtn.textContent = 'Carregar';
                if(resp.status === 404){ clearFields(); return null; }
                return resp.json();
            }).then(function(data){
                if(!data) return;
                if(!data.success){ clearFields(); return; }
                var t = data.tank || {};

                // Evita que valores do tanque/RDO anterior permaneçam no formulário
                clearOperationalFields();
                try{
                    ['sup-ica','sup-camba'].forEach(function(id){ var el = qs(id); if(el){ try{ el.removeAttribute('data-user-edited'); }catch(e){} } });
                }catch(e){}

                hidTank.value = t.id || '';
                // keep textual code in hidden for backend to preserve
                try{ hidTankCode.value = t.tanque_codigo || codigo || ''; }catch(e){}
                // populate visible fields
                setValue('sup-tanque-nome', t.nome_tanque || t.tanque_codigo || '');
                setSelect('sup-tipo-tanque', t.tipo_tanque || '');
                setValue('sup-n-comp', t.numero_compartimentos || '');
                // notify compartment script to rebuild pills when value is set programmatically
                try{ triggerInputEvent('sup-n-comp'); }catch(e){}
                setValue('sup-gavetas', t.gavetas || '');
                setValue('sup-patamar', t.patamares || '');
                setValue('sup-volume', t.volume_tanque_exec || '');
                // previsões por tanque (quando disponíveis do detalhe)
                setValue('sup-prev-ensac', t.ensacamento_prev || t.ensacamento_previsao || '');
                setValue('sup-prev-ica', t.icamento_prev || t.icamento_previsao || '');
                setValue('sup-prev-camba', t.cambagem_prev || t.cambagem_previsao || '');
                // and mirror previsões to hidden canonical names
                syncPrevHidden();

                // Mark these fields as immutable: make inputs readonly and selects disabled,
                // but ensure their values are still submitted by creating hidden inputs when we disable selects.
                try{
                    // readonly text/number inputs (these remain in form submission)
                    ['sup-tanque-nome','sup-n-comp','sup-gavetas','sup-patamar','sup-volume','sup-prev-ensac','sup-prev-ica','sup-prev-camba'].forEach(function(id){
                        var el = qs(id);
                        if(!el) return;
                        try{ el.readOnly = true; }catch(e){}
                        el.setAttribute && el.setAttribute('data-locked','1');
                    });
                }catch(e){}

                // Tipo de tanque (select) - disable and create hidden field to preserve value
                try{
                    var tipoSel = qs('sup-tipo-tanque');
                    if(tipoSel){
                        if(t.tipo_tanque){
                            try{ tipoSel.value = t.tipo_tanque; }catch(e){}
                            var hidTipo = ensureHidden('tipo_tanque', form);
                            hidTipo.value = t.tipo_tanque || '';
                            tipoSel.disabled = true;
                            tipoSel.setAttribute('data-locked','1');
                        } else {
                            tipoSel.disabled = false;
                            var hidTipo2 = q1('input[name="tipo_tanque"][data-hidden]', form); if(hidTipo2) hidTipo2.remove();
                        }
                    }
                }catch(e){}

                // Serviço é IMUTÁVEL por tanque: preserve and lock visually (hidden input already used)
                try{
                    var servSelect = qs('sup-servico');
                    if(servSelect){
                        if(t.servico_exec){
                            try{ servSelect.value = t.servico_exec; }catch(e){}
                            var hid = ensureHidden('servico_exec', form);
                            hid.value = t.servico_exec || '';
                            servSelect.disabled = true;
                            servSelect.setAttribute('data-locked','1');
                            try{
                                var servVisible = qs('sup-servico-input');
                                if(servVisible){
                                    var wrap = servSelect.closest ? servSelect.closest('.dropdown-select') : null;
                                    var dd = wrap ? wrap.querySelector('select.dropdown-data') : document.querySelector('select.dropdown-data');
                                    var val = t.servico_exec || '';
                                    var opt = dd ? dd.querySelector('option[value="'+val+'"]') : null;
                                    servVisible.value = opt ? opt.textContent : val;
                                    servVisible.readOnly = true; servVisible.setAttribute('data-locked','1');
                                }
                            }catch(e){}
                        } else {
                            servSelect.disabled = false;
                            var hid2 = q1('input[name="servico_exec"][data-hidden]', form); if(hid2) hid2.remove();
                            try{ var servVisible2 = qs('sup-servico-input'); if(servVisible2){ servVisible2.readOnly = false; servVisible2.removeAttribute('data-locked'); } }catch(e){}
                        }
                    }
                }catch(e){ console.warn('preenchimento servico failed', e); }

                // Método: preencher e bloquear select `sup-metodo` quando disponível no detalhe do tanque
                try{
                    var metodoSel = qs('sup-metodo');
                    if(metodoSel){
                        if(t.metodo_exec){
                            try{ metodoSel.value = t.metodo_exec; }catch(e){}
                            var hidm = ensureHidden('metodo_exec', form);
                            hidm.value = t.metodo_exec || '';
                            metodoSel.disabled = true;
                            metodoSel.setAttribute('data-locked','1');
                        } else {
                            metodoSel.disabled = false;
                            var hidm2 = q1('input[name="metodo_exec"][data-hidden]', form); if(hidm2) hidm2.remove();
                        }
                    }
                }catch(e){ console.warn('preenchimento metodo failed', e); }

                // remember loaded code so if user edits it we clear the locked metadata
                try{ input.setAttribute('data-loaded-code', codigo); }catch(e){}
                // Re-sync disabled cleaning -> hidden, in case some are disabled by UI state
                try{ syncDisabledToHidden(); }catch(e){}

                // Ensure we have a JSON placeholder for compartimentos so backend can persist
                try{ buildCompartimentosJSONFromNComp(form); }catch(e){}

                // Blindagem final: se algum script copiar previsão -> dia, limpamos aqui.
                clearIfAutoCopiedDaily('sup-ica','sup-prev-ica');
                clearIfAutoCopiedDaily('sup-camba','sup-prev-camba');

            }).catch(function(err){ loadBtn.disabled = false; loadBtn.textContent = 'Carregar'; try{ if(!(err && err.status === 404)){ console.warn('tank lookup error', err); } }catch(e){} clearFields(); });
        });

        // Final safety: on submit, mirror any disabled fields to hidden before sending
        try{
            form.addEventListener('submit', function(){
                // Antes de enviar: se icamento/cambagem do dia estiverem iguais à previsão sem edição do usuário, zera.
                try{ clearIfAutoCopiedDaily('sup-ica','sup-prev-ica'); }catch(e){}
                try{ clearIfAutoCopiedDaily('sup-camba','sup-prev-camba'); }catch(e){}
                try{ syncPrevHidden(); }catch(e){}
                try{ syncDisabledToHidden(); }catch(e){}
                try{ var v = (input.value||'').trim(); hidTankCode.value = v; }catch(e){}
            });
        }catch(e){}

        // Bind user-edit markers
        markUserEdited('sup-ica');
        markUserEdited('sup-camba');
    });
})();
