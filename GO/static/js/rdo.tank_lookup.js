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
        }catch(e){ /* noop */ }
    }

        var listed = false;

        function getOsId(){ var el = qs('sup-context-os'); if(!el) return ''; var id = el.getAttribute('data-os-id') || el.getAttribute('data-os-code') || el.textContent || ''; return (id||'').toString().trim(); }

        function clearFields(){
            // remove loaded metadata marker
            hidTank.value = '';
            hidTankCode.value = '';
            // clear visible fields
            setValue('sup-tanque-nome','');
            setSelect('sup-tipo-tanque','');
            setValue('sup-n-comp','');
            setValue('sup-gavetas','');
            setValue('sup-patamar','');
            setValue('sup-volume','');
            // remove data-loaded-code marker from code input
            try{ var codeIn = qs('sup-tanque-cod'); if(codeIn) codeIn.removeAttribute('data-loaded-code'); }catch(e){}
            // re-enable and unlock controls that may have been locked
            try{
                var tipo = qs('sup-tipo-tanque');
                if(tipo){
                    // if we disabled the select and created a hidden field, remove the hidden
                    tipo.disabled = false;
                    tipo.removeAttribute('data-locked');
                    var hidTipo = q1('input[name="tipo_tanque"][data-hidden]', form); if(hidTipo) hidTipo.remove();
                }
            }catch(e){}
            try{
                var serv = qs('sup-servico');
                if(serv) {
                    serv.disabled = false;
                    serv.removeAttribute('data-locked');
                    var hid = q1('input[name="servico_exec"][data-hidden]', form); if(hid) hid.remove();
                }
            }catch(e){}
            // unlock text/number inputs by removing readonly/data-locked
            try{
                ['sup-tanque-nome','sup-n-comp','sup-gavetas','sup-patamar','sup-volume','sup-prev-ensac','sup-prev-ica','sup-prev-camba'].forEach(function(id){
                    var el = qs(id);
                    if(!el) return;
                    try{ el.readOnly = false; }catch(e){}
                    el.removeAttribute && el.removeAttribute('data-locked');
                });
                // inform compartment component that the number changed/was cleared
                try{ triggerInputEvent('sup-n-comp'); }catch(e){}
            }catch(e){}
        }

        // Listar tanques da OS: popula datalist com opções (value = tanque_codigo)
        function doListTanks(){
            if(listed) return;
            listed = true; // avoid duplicate concurrent requests; will be reset on error so user can retry
            var osId = getOsId();
            // Prefer the canonical backend route that exposes tanks for an OS.
            // Fallback to legacy frontend URL if no OS id is available.
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
                // Support multiple response shapes: { tanks: [...] } or { results: [...] } or plain array
                var arr = [];
                if (Array.isArray(data.tanks)) arr = data.tanks;
                else if (Array.isArray(data.results)) arr = data.results;
                else if (Array.isArray(data)) arr = data;
                if(!arr.length) return;
                // clear datalist
                while(datalist.firstChild) datalist.removeChild(datalist.firstChild);
                arr.forEach(function(t){
                    var opt = document.createElement('option');
                    opt.value = t.tanque_codigo || t.codigo || t.id || t.code || t.cod || '';
                    datalist.appendChild(opt);
                });
            }).catch(function(err){ listBtn.disabled = false; listBtn.textContent = prevText || 'Listar'; listed = false; console.warn('error loading tanks for os', err); });
        }

        listBtn.addEventListener('click', function(){ doListTanks(); });

        // Auto-list when Supervisor modal opens (or if already open on load). This avoids
        // requiring the user to press "Listar" when OS context is present.
        try {
            var modal = document.getElementById('supv-modal-overlay') || document.getElementById('modal-supervisor-overlay') || document.querySelector('.modal-overlay#supv-modal-overlay');
            if (modal) {
                // If it's already visible, run immediately
                var isVisible = modal.getAttribute('aria-hidden') === 'false' || modal.classList.contains('open');
                if (isVisible) {
                    // defer a tick to allow any other modal init to finish
                    setTimeout(doListTanks, 40);
                }
                // Observe attribute changes to detect when modal opens
                var mo = new MutationObserver(function(mutations){
                    mutations.forEach(function(m){
                        if (m.attributeName === 'aria-hidden' || m.attributeName === 'class'){
                            var v = modal.getAttribute('aria-hidden');
                            var opened = (v === 'false') || modal.classList.contains('open');
                            if (opened) setTimeout(doListTanks, 30);
                        }
                    });
                });
                mo.observe(modal, { attributes: true, attributeFilter: ['aria-hidden','class'] });
            } else {
                // If modal not present yet, attempt to list once anyway if OS context exists
                if (getOsId()) setTimeout(doListTanks, 100);
            }
        } catch(e){ /* noop */ }

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
