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
        var listBtn = qs('sup-list-tanks-btn');
        var loadBtn = qs('sup-load-tank-btn');
        var form = qs('form-supervisor');
        if(!input || !datalist || !listBtn || !loadBtn || !form) return;

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
                    } else {
                        servSelect.disabled = false; var hid2 = q1('input[name="servico_exec"][data-hidden]', form); if(hid2) hid2.remove();
                    }
                }
            }catch(e){ console.warn('preenchimento servico failed', e); }

            try{ input.setAttribute('data-loaded-code', codigo || (t.tanque_codigo||t.codigo||'')); }catch(e){}
            try{ syncDisabledToHidden(); }catch(e){}
            try{ buildCompartimentosJSONFromNComp(form); }catch(e){}
        }

            function getOsId(){
                var el = qs('sup-context-os');
                if(!el) return '';
                var direct = el.getAttribute('data-os-id') || el.getAttribute('data-os-code');
                if(direct) return String(direct).trim();
                var txt = (el.textContent || '').toString().trim();
                if(!txt) return '';
                try{
                    var mapEl = document.querySelector('[data-numero-os="' + (window.CSS && CSS.escape ? CSS.escape(txt) : txt) + '"]') || document.querySelector('[data-os="' + (window.CSS && CSS.escape ? CSS.escape(txt) : txt) + '"]');
                    if(mapEl){ var mapped = mapEl.getAttribute('data-os-id') || mapEl.getAttribute('data-os'); if(mapped) return String(mapped).trim(); }
                }catch(e){}
                return txt;
            }

        // Listar tanques da OS: popula datalist com opções (value = tanque_codigo)
        function doListTanks(){
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

                // popular datalist e abrir modal com opções selecionáveis
                arr.forEach(function(t){
                    var opt = document.createElement('option');
                    opt.value = t.tanque_codigo || t.codigo || t.id || t.code || t.cod || '';
                    datalist.appendChild(opt);
                });

                // Construir modal de seleção (design moderno: cards, verde/branco/preto)
                try{
                    var modal = document.getElementById('sup-tank-list-modal');
                    if(modal && modal.parentNode) modal.parentNode.removeChild(modal);
                    modal = document.createElement('div'); modal.id = 'sup-tank-list-modal'; modal.className = 'sup-tank-list-modal';
                    modal.style.position = 'fixed'; modal.style.inset = '0'; modal.style.background = 'rgba(0,0,0,0.45)'; modal.style.zIndex = 99999; modal.style.display = 'flex'; modal.style.alignItems = 'center'; modal.style.justifyContent = 'center';

                    var panel = document.createElement('div');
                    panel.style.width = '760px'; panel.style.maxWidth = '95%'; panel.style.maxHeight = '78vh'; panel.style.display = 'flex'; panel.style.flexDirection = 'column'; panel.style.borderRadius = '12px'; panel.style.overflow = 'hidden'; panel.style.boxShadow = '0 12px 40px rgba(0,0,0,0.35)'; panel.style.background = '#fff'; panel.style.fontFamily = 'Inter, system-ui, -apple-system, Roboto, "Helvetica Neue", Arial';

                    // Header
                    var header = document.createElement('div'); header.style.display = 'flex'; header.style.alignItems = 'center'; header.style.justifyContent = 'space-between'; header.style.padding = '14px 18px'; header.style.background = '#eaf6ee'; header.style.borderBottom = '1px solid #e6efe6';
                    var title = document.createElement('div'); title.style.display = 'flex'; title.style.flexDirection = 'column';
                    var titleMain = document.createElement('div'); titleMain.textContent = 'Tanques da OS'; titleMain.style.fontSize = '16px'; titleMain.style.fontWeight = '700'; titleMain.style.color = '#1b5e20';
                    var titleSub = document.createElement('div'); titleSub.textContent = 'Selecione um tanque para preencher o formulário'; titleSub.style.fontSize = '12px'; titleSub.style.color = '#2e7d32';
                    title.appendChild(titleMain); title.appendChild(titleSub);
                    var closeX = document.createElement('button'); closeX.type = 'button'; closeX.className = 'btn-rdo ghost small'; closeX.textContent = '✕'; closeX.setAttribute('aria-label','Fechar'); closeX.style.border = 'none'; closeX.style.background = 'transparent'; closeX.style.fontSize = '18px'; closeX.style.cursor = 'pointer';
                    header.appendChild(title); header.appendChild(closeX);
                    panel.appendChild(header);

                    // Search
                    var searchWrap = document.createElement('div'); searchWrap.style.padding = '12px 18px'; searchWrap.style.borderBottom = '1px solid #f3f3f3';
                    var searchInput = document.createElement('input'); searchInput.type = 'search'; searchInput.placeholder = 'Filtrar por código ou nome do tanque'; searchInput.style.width = '100%'; searchInput.style.padding = '10px 12px'; searchInput.style.border = '1px solid #e0e0e0'; searchInput.style.borderRadius = '8px'; searchInput.style.fontSize = '14px';
                    searchWrap.appendChild(searchInput); panel.appendChild(searchWrap);

                    // Content
                    var content = document.createElement('div'); content.style.overflow = 'auto'; content.style.padding = '12px 16px'; content.style.display = 'grid'; content.style.gridTemplateColumns = 'repeat(2, 1fr)'; content.style.gap = '12px'; content.style.alignContent = 'start';

                    arr.forEach(function(t){
                        var code = (t.tanque_codigo || t.codigo || t.code || t.cod || '').toString();
                        var name = (t.nome_tanque || t.nome || '(sem nome)').toString();
                        var card = document.createElement('div');
                        card.className = 'tank-card';
                        card.setAttribute('data-code', code.toLowerCase());
                        card.setAttribute('data-name', name.toLowerCase());
                        card.style.background = '#ffffff'; card.style.border = '1px solid #eef6ee'; card.style.borderRadius = '10px'; card.style.padding = '12px'; card.style.display = 'flex'; card.style.flexDirection = 'column'; card.style.justifyContent = 'space-between';

                        var meta = document.createElement('div'); meta.style.marginBottom = '10px';
                        var codeEl = document.createElement('div'); codeEl.textContent = code; codeEl.style.fontWeight = '700'; codeEl.style.fontSize = '15px'; codeEl.style.color = '#0b6623';
                        var nameEl = document.createElement('div'); nameEl.textContent = name; nameEl.style.fontSize = '13px'; nameEl.style.color = '#333'; nameEl.style.marginTop = '4px';
                        meta.appendChild(codeEl); meta.appendChild(nameEl);

                        var actions = document.createElement('div'); actions.style.display = 'flex'; actions.style.gap = '8px'; actions.style.justifyContent = 'flex-end';
                        var loadBtnItem = document.createElement('button'); loadBtnItem.type = 'button'; loadBtnItem.className = 'btn-rdo primary small'; loadBtnItem.textContent = 'Carregar'; loadBtnItem.style.background = '#1b5e20'; loadBtnItem.style.color = '#fff'; loadBtnItem.style.border = 'none'; loadBtnItem.style.padding = '8px 12px'; loadBtnItem.style.borderRadius = '6px'; loadBtnItem.style.cursor = 'pointer';
                        loadBtnItem.addEventListener('click', function(){
                            loadBtnItem.disabled = true; loadBtnItem.textContent = 'Carregando...';
                            var urlDetail = '/api/rdo/tank/' + encodeURIComponent(code) + '/';
                            fetch(urlDetail, { credentials: 'same-origin' }).then(function(resp){
                                loadBtnItem.disabled = false; loadBtnItem.textContent = 'Carregar';
                                if(resp.status === 404){ alert('Detalhe do tanque não encontrado.'); return null; }
                                if(!resp.ok){ console.warn('failed to fetch tank detail', resp.status); return null; }
                                return resp.json();
                            }).then(function(data){
                                if(!data) return;
                                var payload = data.tank || data;
                                populateFromTankData(payload, code);
                                if(modal && modal.parentNode){ listed = false; modal.parentNode.removeChild(modal); }
                            }).catch(function(err){ loadBtnItem.disabled = false; loadBtnItem.textContent = 'Carregar'; console.warn('error fetching tank detail', err); alert('Erro ao carregar detalhes do tanque.'); });
                        });

                        var selBtn = document.createElement('button'); selBtn.type='button'; selBtn.className='btn-rdo ghost small'; selBtn.textContent='Selecionar'; selBtn.style.background='transparent'; selBtn.style.border='1px solid #d0d0d0'; selBtn.style.padding='8px 10px'; selBtn.style.borderRadius='6px'; selBtn.style.cursor='pointer';
                        selBtn.addEventListener('click', function(){ try{ setValue('sup-tanque-cod', code); if (input) input.dispatchEvent(new Event('input',{ bubbles: true })); }catch(e){} if(modal && modal.parentNode){ listed = false; modal.parentNode.removeChild(modal); } });

                        actions.appendChild(selBtn); actions.appendChild(loadBtnItem);
                        card.appendChild(meta); card.appendChild(actions);
                        content.appendChild(card);
                    });

                    panel.appendChild(content);

                    // Footer
                    var footer = document.createElement('div'); footer.style.padding = '10px 16px'; footer.style.textAlign = 'right'; footer.style.borderTop = '1px solid #f3f3f3';
                    var closeBtn = document.createElement('button'); closeBtn.type='button'; closeBtn.className='btn-rdo ghost small'; closeBtn.textContent='Fechar'; closeBtn.style.padding='8px 12px'; closeBtn.style.borderRadius='6px'; closeBtn.style.cursor='pointer';
                    closeBtn.addEventListener('click', function(){ if(modal && modal.parentNode){ listed = false; modal.parentNode.removeChild(modal); } });
                    footer.appendChild(closeBtn); panel.appendChild(footer);

                    modal.appendChild(panel);

                    // close on backdrop
                    modal.addEventListener('click', function(e){ if(e.target === modal){ if(modal && modal.parentNode){ listed = false; modal.parentNode.removeChild(modal); } } });

                    // search/filter behavior
                    try{
                        searchInput.addEventListener('input', function(){ var q = (this.value||'').toLowerCase().trim(); var cards = content.querySelectorAll('.tank-card'); for(var i=0;i<cards.length;i++){ var c = cards[i]; var code = c.getAttribute('data-code')||''; var name = c.getAttribute('data-name')||''; if(!q || code.indexOf(q) !== -1 || name.indexOf(q) !== -1){ c.style.display='flex'; } else { c.style.display='none'; } } });
                    }catch(e){}

                    // append respecting supervisor overlay
                    var supOverlay = document.getElementById('supv-modal-overlay') || document.getElementById('modal-supervisor-overlay');
                    try{ if(supOverlay && supOverlay.parentNode){ modal.style.position='absolute'; modal.style.background='transparent'; panel.style.position='absolute'; panel.style.left='50%'; panel.style.top='50%'; panel.style.transform='translate(-50%,-50%)'; panel.style.zIndex='999999'; supOverlay.appendChild(modal); } else { document.body.appendChild(modal); } }catch(e){ document.body.appendChild(modal); }

                    try{ searchInput.focus(); }catch(e){}
                }catch(e){ console.warn('error building tank list modal', e); }

            }).catch(function(err){ listBtn.disabled = false; listBtn.textContent = prevText || 'Listar'; listed = false; console.warn('error loading tanks for os', err); });
        }

        listBtn.addEventListener('click', function(){ doListTanks(); });

        // Auto-list disabled: listing is now explicit and requires the user to click "Listar".

        // enable load button when input has value
        // When the user edits the tank code after a load, clear previously-loaded metadata
        input.addEventListener('input', function(){
            var val = input.value && input.value.trim();
            loadBtn.disabled = !val;
            // keep hidden tanque_codigo synced to current typed code
            try{ hidTankCode.value = (val||''); }catch(e){}
            try{
                var loaded = input.getAttribute('data-loaded-code');
                if(loaded && loaded !== (val||'')){
                    // user changed the code after a load — clear locked metadata so they can load another
                    clearFields();
                }
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
        loadBtn.addEventListener('click', function(){
            var codigo = (input.value||'').trim();
            if(!codigo){ return; }
            loadBtn.disabled = true; loadBtn.textContent = 'Carregando...';
            var url = '/api/rdo/tank/' + encodeURIComponent(codigo) + '/';
            fetch(url, { credentials: 'same-origin' }).then(function(resp){
                loadBtn.disabled = false; loadBtn.textContent = 'Carregar';
                if(resp.status === 404){ clearFields(); return null; }
                return resp.json();
            }).then(function(data){
                if(!data) return;
                if(!data.success){ clearFields(); return; }
                var t = data.tank || {};
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
                        } else {
                            servSelect.disabled = false;
                            var hid2 = q1('input[name="servico_exec"][data-hidden]', form); if(hid2) hid2.remove();
                        }
                    }
                }catch(e){ console.warn('preenchimento servico failed', e); }

                // remember loaded code so if user edits it we clear the locked metadata
                try{ input.setAttribute('data-loaded-code', codigo); }catch(e){}
                // Re-sync disabled cleaning -> hidden, in case some are disabled by UI state
                try{ syncDisabledToHidden(); }catch(e){}

                // Ensure we have a JSON placeholder for compartimentos so backend can persist
                try{ buildCompartimentosJSONFromNComp(form); }catch(e){}

            }).catch(function(err){ loadBtn.disabled = false; loadBtn.textContent = 'Carregar'; console.warn('tank lookup error', err); clearFields(); });
        });

        // Final safety: on submit, mirror any disabled fields to hidden before sending
        try{
            form.addEventListener('submit', function(){
                try{ syncPrevHidden(); }catch(e){}
                try{ syncDisabledToHidden(); }catch(e){}
                try{ var v = (input.value||'').trim(); hidTankCode.value = v; }catch(e){}
            });
        }catch(e){}
    });
})();
