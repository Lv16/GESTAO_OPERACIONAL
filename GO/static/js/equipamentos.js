(function () {
    const on = (el, ev, fn) => el && el.addEventListener(ev, fn);

    // simple in-memory store for photos keyed by OS number
    const photosByOs = {};
    const SITUACAO_LABELS = {
        'embarcardo': 'Embarcado',
        'embarcado': 'Embarcado',
        'trocou_unidade': 'Trocou de Unidade',
        'retornou_base': 'Retornou para Base'
    };

    function isContainerDescription(value){
        return String(value || '').trim().toLowerCase() === 'container';
    }

    function getEquipmentMode(value){
        return isContainerDescription(value) ? 'container' : 'default';
    }

    function getIdentifierTerms(value){
        if (isContainerDescription(value) || value === 'container') {
            return {
                tag: 'Número do Container',
                serie: 'Número da Eslinga',
                pair: 'Número do Container ou Número da Eslinga',
                actionTitle: 'Atualizar dados do container',
                actionAria: 'Atualizar dados do container',
                success: 'Dados do container atualizados com sucesso.',
            };
        }
        return {
            tag: 'TAG',
            serie: 'Número de Série',
            pair: 'TAG ou Número de Série',
            actionTitle: 'Trocar TAG/Série',
            actionAria: 'Trocar TAG e Série',
            success: 'TAG/Série atualizadas com sucesso.',
        };
    }

    function getModeDatasetValue(el, mode, kind){
        if(!el || !el.dataset) return '';
        if(kind === 'placeholder'){
            return mode === 'container'
                ? (el.dataset.containerPlaceholder || '')
                : (el.dataset.defaultPlaceholder || '');
        }
        return mode === 'container'
            ? (el.dataset.containerText || '')
            : (el.dataset.defaultText || '');
    }

    function applyModeText(target, mode){
        const el = typeof target === 'string' ? document.querySelector(target) : target;
        if(!el) return;
        const nextText = getModeDatasetValue(el, mode, 'text');
        if(nextText) el.textContent = nextText;
    }

    function applyModePlaceholder(target, mode){
        const el = typeof target === 'string' ? document.querySelector(target) : target;
        if(!el) return;
        const nextPlaceholder = getModeDatasetValue(el, mode, 'placeholder');
        if(typeof nextPlaceholder === 'string') el.placeholder = nextPlaceholder;
    }

    function getTableDisplayValue(value){
        const text = value == null ? '' : String(value).trim();
        return text && !/^(none|null|undefined)$/i.test(text) ? text : '-';
    }

    function setFieldLockedState(form, input, locked, forcedValue){
        if(!form || !input) return;
        const name = input.name || input.getAttribute('name');
        if(typeof forcedValue !== 'undefined'){
            try { input.value = forcedValue == null ? '' : String(forcedValue); } catch(e){}
        }

        const existingHidden = name
            ? form.querySelector(`input[type="hidden"][data-locked-for="${name}"]`)
            : null;

        if(locked){
            try { input.readOnly = true; } catch(e){}
            try { input.disabled = true; } catch(e){}
            if(name){
                const hidden = existingHidden || document.createElement('input');
                hidden.type = 'hidden';
                hidden.name = name;
                hidden.value = input.value || '';
                hidden.setAttribute('data-locked-for', name);
                if(!existingHidden) form.appendChild(hidden);
            }
        } else {
            try { input.readOnly = false; } catch(e){}
            try { input.disabled = false; } catch(e){}
            if(existingHidden && existingHidden.parentElement) existingHidden.parentElement.removeChild(existingHidden);
        }

        try {
            const label = input.closest && input.closest('label');
            const target = label || input;
            if(locked){
                target.classList.add('locked');
                target.setAttribute('aria-disabled', 'true');
                target.setAttribute('title', 'Campo bloqueado');
            } else {
                target.classList.remove('locked');
                target.removeAttribute('aria-disabled');
                if(target.getAttribute('title') === 'Campo bloqueado') target.removeAttribute('title');
            }
            if(!label){
                if(locked) input.classList.add('locked');
                else input.classList.remove('locked');
            }
        } catch (err) {}
    }

    function syncEquipamentoFormMode(value){
        const form = document.getElementById('equip-form');
        if(!form) return;

        const mode = getEquipmentMode(
            typeof value !== 'undefined'
                ? value
                : (form.querySelector('[name="descricao"]')?.value || '')
        );

        applyModeText('#equipment-info-summary', mode);
        applyModeText('#equipamento-choice-label', mode);
        applyModeText('#tag-field-label', mode);
        applyModeText('#serie-field-label', mode);
        applyModeText('#fabricante-field-label', mode);
        applyModeText('#identifier-history-subtitle', mode);

        const equipamentoChoice = document.getElementById('equipamento-choice');
        if(equipamentoChoice && equipamentoChoice.options && equipamentoChoice.options.length){
            const firstOption = equipamentoChoice.options[0];
            const placeholder = getModeDatasetValue(equipamentoChoice, mode, 'placeholder');
            if(firstOption && placeholder) firstOption.textContent = placeholder;
        }

        applyModePlaceholder(form.querySelector('[name="tag"]'), mode);
        applyModePlaceholder(form.querySelector('[name="serie"]'), mode);

        const fabricanteField = form.querySelector('[name="fabricante"]');
        if(fabricanteField){
            if(mode === 'container'){
                if(!Object.prototype.hasOwnProperty.call(fabricanteField.dataset, 'previousValue')){
                    fabricanteField.dataset.previousValue = fabricanteField.value || '';
                }
                setFieldLockedState(form, fabricanteField, true, '');
            } else {
                const previousValue = fabricanteField.dataset.previousValue || '';
                setFieldLockedState(form, fabricanteField, false);
                if(!fabricanteField.value && previousValue) fabricanteField.value = previousValue;
                try { delete fabricanteField.dataset.previousValue; } catch(err) {}
            }
        }
    }

    function syncIdentifierSwapMode(value){
        const mode = getEquipmentMode(value);
        const modal = document.getElementById('identifier-swap-modal');
        if(modal) modal.dataset.mode = mode;

        applyModeText('#identifier-swap-title', mode);
        applyModeText('#identifier-swap-subtitle', mode);
        applyModeText('#swap-tag-current-label', mode);
        applyModeText('#swap-serie-current-label', mode);
        applyModeText('#swap-tag-new-label', mode);
        applyModeText('#swap-serie-new-label', mode);
        applyModeText('#identifier-swap-submit', mode);

        const form = document.getElementById('identifier-swap-form');
        if(!form) return;
        applyModePlaceholder(form.querySelector('[name="tag"]'), mode);
        applyModePlaceholder(form.querySelector('[name="serie"]'), mode);
    }

    function updateIdentifierActionButton(button, value){
        if(!button) return;
        const terms = getIdentifierTerms(value);
        button.setAttribute('title', terms.actionTitle);
        button.setAttribute('aria-label', terms.actionAria);
    }

    function updateIdentifierActionButtonForRow(row){
        if(!row) return;
        updateIdentifierActionButton(
            row.querySelector('.identifier-swap-btn'),
            row.getAttribute('data-descricao') || row.dataset?.descricao || ''
        );
    }

// Fixed tooltips for action buttons: create a tooltip element in the body to avoid clipping
(function(){
    const MARGIN = 8;
    let active = null;
    function showTooltip(target){
        if(!target) return;
        const title = target.getAttribute('title');
        if(!title) return;
        // prevent native tooltip while our custom exists
        target.dataset._savedTitle = title;
        target.removeAttribute('title');

        const el = document.createElement('div');
        el.className = 'fixed-tooltip';
        el.textContent = title;
        document.body.appendChild(el);

        // position after inserted so we can measure
        const rect = target.getBoundingClientRect();
        const tw = el.offsetWidth;
        const th = el.offsetHeight;
        let left = Math.round(rect.left + rect.width/2 - tw/2);
        // clamp horizontally
        left = Math.max(6, Math.min(left, window.innerWidth - tw - 6));
        let top = Math.round(rect.top - th - MARGIN);
        if(top < 6) top = Math.round(rect.bottom + MARGIN);
        el.style.left = left + 'px';
        el.style.top = top + 'px';
        active = { el, target };
    }
    function hideTooltip(){
        if(!active) return;
        try{ if(active.el && active.el.parentNode) active.el.parentNode.removeChild(active.el); }catch(e){}
        try{ if(active.target && active.target.dataset && active.target.dataset._savedTitle) { active.target.setAttribute('title', active.target.dataset._savedTitle); delete active.target.dataset._savedTitle; } }catch(e){}
        active = null;
    }

    // Use pointer events and handle relatedTarget to reliably hide/show tooltips
    document.addEventListener('pointerover', function(ev){
        // support tooltips for both action buttons and the situacao badge (colored dot)
        const btn = ev.target && ev.target.closest && ev.target.closest('.action-btn, .situacao-badge');
        if(!btn) return;
        const title = btn.getAttribute('title') || btn.dataset._savedTitle;
        if(title) showTooltip(btn);
    });

    document.addEventListener('pointerout', function(ev){
        const btn = ev.target && ev.target.closest && ev.target.closest('.action-btn, .situacao-badge');
        const rel = ev.relatedTarget;
        if(btn){
            if(!rel || (rel && !btn.contains(rel))) {
                hideTooltip();
            }
        } else {
            if(active && (!rel || (rel && !active.target.contains && !active.el.contains(rel)))) {
                hideTooltip();
            }
        }
    });

    // also hide on interactions that likely move the layout
    ['scroll','resize','mousedown','touchstart'].forEach(evName => {
        window.addEventListener(evName, () => { hideTooltip(); }, { passive: true });
    });
})();

    // helper: normalize different date formats (dd/mm/yyyy, YYYY-MM-DD, timestamp) to YYYY-MM-DD
    function normalizeDateToISO(input){
        if(!input && input !== 0) return '';
        if(typeof input === 'number'){
            try { return (new Date(input)).toISOString().slice(0,10); } catch(e){ return String(input); }
        }
        const s = String(input).trim();
        const isoMatch = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if(isoMatch) return isoMatch[0];
        const brMatch = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if(brMatch) return `${brMatch[3]}-${brMatch[2]}-${brMatch[1]}`;
        const parsed = Date.parse(s);
        if(!isNaN(parsed)){
            try { return (new Date(parsed)).toISOString().slice(0,10); } catch(e) { return s; }
        }
        return s;
    }

    // helper: format ISO date (YYYY-MM-DD) to BR format dd/mm/YYYY
    function formatDateToBR(iso){
        if(!iso) return '';
        const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
        if(m) return `${m[3]}/${m[2]}/${m[1]}`;
        const parsed = Date.parse(String(iso));
        if(!isNaN(parsed)){
            const d = new Date(parsed);
            return `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}/${d.getFullYear()}`;
        }
        return String(iso);
    }

    function formatDateTimeToBR(iso){
        if(!iso) return '';
        const d = new Date(iso);
        if(!isNaN(d.getTime())){
            return d.toLocaleString('pt-BR', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit' });
        }
        return String(iso);
    }

    function getSituacaoLabel(value){
        if(!value) return 'Sem situação';
        const raw = String(value).trim();
        const key = raw.toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_');
        if (SITUACAO_LABELS[key]) return SITUACAO_LABELS[key];
        return raw
            .replace(/[_-]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim()
            .replace(/\b\w/g, (m) => m.toUpperCase());
    }

    function getIdentifierLabel(identifierType, equipmentDescription){
        const key = String(identifierType || '').toLowerCase();
        const terms = getIdentifierTerms(equipmentDescription);
        if (key === 'tag') return terms.tag;
        if (key === 'serie') return terms.serie;
        return 'Identificador';
    }

    function renderIdentifierHistory(history, equipmentDescription){
        try{
            const panel = document.getElementById('identifier-history-panel');
            const list = document.getElementById('identifier-history-list');
            if(!panel || !list) return;
            list.innerHTML = '';
            if(!history || !Array.isArray(history) || history.length === 0){
                const empty = document.createElement('p');
                empty.className = 'muted';
                empty.textContent = 'Nenhuma alteracao registrada.';
                list.appendChild(empty);
                panel.removeAttribute('hidden');
                return;
            }

            history.forEach(h => {
                const item = document.createElement('div');
                item.className = 'id-hist-item';

                const head = document.createElement('div');
                head.className = 'id-hist-head';

                const typeEl = document.createElement('span');
                typeEl.className = 'id-hist-type';
                typeEl.textContent = getIdentifierLabel(h.identifier_type, equipmentDescription);

                const when = h.created_at ? formatDateTimeToBR(h.created_at) : '';
                const who = h.changed_by || h.changed_by_name || h.user || '';
                const metaEl = document.createElement('span');
                metaEl.className = 'id-hist-meta';
                metaEl.textContent = `${when}${who ? (' - ' + who) : ''}`;

                head.appendChild(typeEl);
                head.appendChild(metaEl);

                const values = document.createElement('div');
                values.className = 'id-hist-values';

                const fromEl = document.createElement('span');
                fromEl.className = 'id-hist-pill from';
                fromEl.textContent = h.previous || 'vazio';

                const arrowEl = document.createElement('span');
                arrowEl.className = 'id-hist-arrow';
                arrowEl.textContent = '->';

                const toEl = document.createElement('span');
                toEl.className = 'id-hist-pill to';
                toEl.textContent = h.current || 'vazio';

                values.appendChild(fromEl);
                values.appendChild(arrowEl);
                values.appendChild(toEl);

                item.appendChild(head);
                item.appendChild(values);

                if (h.note) {
                    const note = document.createElement('div');
                    note.className = 'hist-item-note';
                    note.textContent = `Motivo: ${h.note}`;
                    item.appendChild(note);
                }
                list.appendChild(item);
            });
            panel.removeAttribute('hidden');
        }catch(err){ console.warn('renderIdentifierHistory error', err); }
    }

    // render situação history into the modal panel
    function renderSituacaoHistory(history){
        try{
            const panel = document.getElementById('situacao-history-panel');
            const list = document.getElementById('situacao-history-list');
            if(!panel || !list) return;
            list.innerHTML = '';
            if(!history || !Array.isArray(history) || history.length === 0){
                panel.setAttribute('hidden','');
                return;
            }
            history.forEach(h => {
                const item = document.createElement('div');
                item.className = 'hist-item';
                const when = h.created_at ? formatDateTimeToBR(h.created_at) : '';
                const who = h.changed_by || h.user || h.changed_by_name || '';
                const txt = document.createElement('div'); txt.className = 'hist-text';
                txt.textContent = `${when}${who ? (' — ' + who) : ''} — ${getSituacaoLabel(h.previous)} → ${getSituacaoLabel(h.current)}`;
                item.appendChild(txt);
                if (h.note) { const note = document.createElement('div'); note.className = 'hist-note'; note.textContent = `Motivo: ${h.note}`; item.appendChild(note); }
                list.appendChild(item);
            });
            panel.removeAttribute('hidden');
        }catch(err){ console.warn('renderSituacaoHistory error', err); }
    }

    // render situação history into the standalone history modal (full trace view)
    function renderSituacaoHistoryModal(history){
        try{
            const list = document.getElementById('situacao-history-list-modal');
            if(!list) return;
            list.innerHTML = '';
            if(!history || !Array.isArray(history) || history.length === 0){
                list.innerHTML = '<div class="hist-empty">Nenhum registro encontrado.</div>';
                return;
            }
            const container = document.createElement('div'); container.className = 'hist-list';
            history.forEach(h => {
                const item = document.createElement('div'); item.className = 'hist-item-modal';
                const when = h.created_at ? formatDateTimeToBR(h.created_at) : '';
                const who = h.changed_by || h.changed_by_name || h.user || '';
                const header = document.createElement('div'); header.className = 'hist-item-header';
                const whenEl = document.createElement('span'); whenEl.className = 'hist-item-when hist-meta';
                const whenIcon = document.createElement('span'); whenIcon.className = 'material-icons'; whenIcon.setAttribute('aria-hidden','true'); whenIcon.textContent = 'schedule';
                whenEl.appendChild(whenIcon);
                whenEl.appendChild(document.createTextNode(when || 'Data não informada'));
                header.appendChild(whenEl);
                if (who) {
                    const whoEl = document.createElement('span'); whoEl.className = 'hist-item-who hist-meta';
                    const whoIcon = document.createElement('span'); whoIcon.className = 'material-icons'; whoIcon.setAttribute('aria-hidden','true'); whoIcon.textContent = 'person';
                    whoEl.appendChild(whoIcon);
                    whoEl.appendChild(document.createTextNode(who));
                    header.appendChild(whoEl);
                }

                const body = document.createElement('div'); body.className = 'hist-item-body';
                const fromEl = document.createElement('span'); fromEl.className = 'hist-pill from';
                const fromIcon = document.createElement('span'); fromIcon.className = 'material-icons'; fromIcon.setAttribute('aria-hidden','true'); fromIcon.textContent = 'radio_button_unchecked';
                fromEl.appendChild(fromIcon);
                fromEl.appendChild(document.createTextNode(getSituacaoLabel(h.previous)));

                const arrowEl = document.createElement('span'); arrowEl.className = 'hist-arrow';
                const arrowIcon = document.createElement('span'); arrowIcon.className = 'material-icons'; arrowIcon.setAttribute('aria-hidden','true'); arrowIcon.textContent = 'trending_flat';
                arrowEl.appendChild(arrowIcon);

                const toEl = document.createElement('span'); toEl.className = 'hist-pill to';
                const toIcon = document.createElement('span'); toIcon.className = 'material-icons'; toIcon.setAttribute('aria-hidden','true'); toIcon.textContent = 'check_circle';
                toEl.appendChild(toIcon);
                toEl.appendChild(document.createTextNode(getSituacaoLabel(h.current)));
                body.appendChild(fromEl);
                body.appendChild(arrowEl);
                body.appendChild(toEl);

                item.appendChild(header);
                item.appendChild(body);
                if (h.note) {
                    const note = document.createElement('div');
                    note.className = 'hist-item-note';
                    note.textContent = `Motivo: ${h.note}`;
                    item.appendChild(note);
                }
                container.appendChild(item);
            });
            list.appendChild(container);
        }catch(err){ console.warn('renderSituacaoHistoryModal error', err); }
    }

    // Try to fetch equipamento data from server by id. Returns normalized payload or null if not available.
    async function fetchEquipamentoById(id){
        if(!id) return null;
        const tryUrls = [`/api/equipamentos/${id}/`, `/api/equipamentos/${id}/json/`, `/api/equipamentos/get/?id=${id}`];
        for(const url of tryUrls){
            try{
                const resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' } });
                if(!resp.ok) continue;
                const payload = await resp.json();
                // Normalize payload into the shape expected by openEditModalWithData
                // Support both {equipamento, formulario} and direct fields
                const eq = payload.equipamento || payload.equipment || payload;
                const fo = payload.formulario || payload.form || payload;
                const normalized = {
                    id: eq && (eq.id || eq.pk) ? (eq.id || eq.pk) : id,
                    modelo: (eq && (eq.modelo || eq.model)) || '',
                    fabricante: (eq && (eq.fabricante || eq.manufacturer)) || '',
                    descricao: (eq && (eq.descricao || eq.description)) || (payload.descricao || ''),
                    serie: (eq && (eq.numero_serie || eq.serial_number)) || (payload.numero_serie || ''),
                    tag: (eq && (eq.numero_tag || eq.tag)) || '',
                    cliente: (eq && eq.cliente) || (fo && fo.cliente) || payload.cliente || '',
                    embarcacao: (eq && eq.embarcacao) || (fo && fo.embarcacao) || payload.embarcacao || '',
                    responsavel: (fo && (fo.responsavel || fo.responsible)) || payload.responsavel || '',
                    numero_os: (eq && eq.numero_os) || (fo && fo.numero_os) || payload.numero_os || '',
                    data_inspecao: (fo && (fo.data_inspecao || fo.data_inspection)) || payload.data_inspecao || '',
                    local: (fo && fo.local_inspecao) || payload.local || '',
                    previsao_retorno: (fo && (fo.previsao_retorno || fo.prevision)) || payload.previsao_retorno || ''
                };
                // try to extract any photo URLs arrays from common locations in the payload
                const photoArrays = [];
                try {
                    if (payload && payload.formulario && Array.isArray(payload.formulario.photo_urls)) photoArrays.push(payload.formulario.photo_urls);
                    if (payload && Array.isArray(payload.photo_urls)) photoArrays.push(payload.photo_urls);
                    if (payload && Array.isArray(payload.photos)) photoArrays.push(payload.photos);
                    if (payload && Array.isArray(payload.fotos)) photoArrays.push(payload.fotos);
                    if (eq && Array.isArray(eq.photo_urls)) photoArrays.push(eq.photo_urls);
                    if (eq && Array.isArray(eq.photos)) photoArrays.push(eq.photos);
                    // flatten and dedupe
                    const merged = [].concat(...photoArrays).filter(Boolean).map(String);
                    const dedup = Array.from(new Set(merged));
                    if (dedup.length) {
                        normalized.formulario = normalized.formulario || {};
                        normalized.formulario.photo_urls = dedup;
                    }
                } catch (err) { /* ignore extraction errors */ }
                // preserve histories from server payload if present
                try{ if (payload && Array.isArray(payload.situacao_history)) normalized.situacao_history = payload.situacao_history; }catch(e){}
                try{ if (payload && Array.isArray(payload.identifier_history)) normalized.identifier_history = payload.identifier_history; }catch(e){}
                return normalized;
            }catch(err){ /* try next */ }
        }
        return null;
    }

    async function fetchEquipamentoByIdentifier(tag, serie){
        const t = (tag || '').trim();
        const s = (serie || '').trim();
        if(!t && !s) return null;
        const q = t ? `tag=${encodeURIComponent(t)}` : `serie=${encodeURIComponent(s)}`;
        const url = `/api/equipamentos/get/?${q}`;
        try{
            const resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' } });
            if(!resp.ok) return null;
            const payload = await resp.json();
            if(!payload || payload.success !== true) return null;
            const eq = payload.equipamento || {};
            const fo = payload.formulario || {};
            return {
                id: eq.id || '',
                modelo: eq.modelo || '',
                fabricante: eq.fabricante || '',
                descricao: eq.descricao || '',
                serie: eq.numero_serie || '',
                tag: eq.numero_tag || '',
                situacao: eq.situacao || '',
                numero_os: eq.numero_os || '',
                photo_urls: Array.isArray(fo.photo_urls) ? fo.photo_urls : [],
                situacao_history: Array.isArray(payload.situacao_history) ? payload.situacao_history : [],
                identifier_history: Array.isArray(payload.identifier_history) ? payload.identifier_history : [],
                responsavel: fo.responsavel || '',
                local: fo.local_inspecao || '',
                previsao_retorno: fo.previsao_retorno || ''
            };
        }catch(err){
            console.warn('fetchEquipamentoByIdentifier error', err);
            return null;
        }
    }

    // Open modal for a given table row. Try to fetch canonical data by ID, else fallback to dataset values.
    async function openModalForTr(tr){
        if(!tr) return;
        const d = tr.dataset || {};
        const fallback = {
            id: d.id || tr.getAttribute('data-id') || '',
            modelo: d.modelo || '',
            fabricante: d.fabricante || '',
            descricao: d.descricao || '',
            serie: d.serie || '',
            tag: d.tag || '',
            cliente: d.cliente || '',
            embarcacao: d.embarcacao || '',
            responsavel: d.responsavel || '',
            numero_os: d.os || d.numero_os || (tr.querySelector('td[data-label="Nº OS"]')?tr.querySelector('td[data-label="Nº OS"]').textContent.trim():'') ,
            data_inspecao: d.data_inspecao || '',
            local: d.local || '',
            previsao_retorno: d.previsao || d.previsao_retorno || ''
        };
        const id = fallback.id;
        let serverData = null;
        try { serverData = await fetchEquipamentoById(id); } catch(e) { serverData = null; }
    const finalData = serverData || fallback;
    openEditModalWithData(finalData, tr);
    }

    // store photo items as objects: { src, name, size, remote }
    function setPhotosForOs(os, items){
        if(!os) return;
        os = String(os).trim();
        photosByOs[os] = photosByOs[os] || [];
        const incoming = (items || []).map(it => {
            if (!it) return null;
            if (typeof it === 'string') return { src: it, name: '', size: 0, remote: true };
            // assume dataURL or File-like object
            if (it instanceof File) {
                return { src: null, name: it.name || 'photo', size: it.size || 0, file: it, remote: false };
            }
            // dataURL object already
            if (it && it.dataUrl) return { src: it.dataUrl, name: it.name || '', size: it.size || 0, file: it.file, remote: false };
            // raw dataUrl string (fallback)
            if (typeof it === 'string') return { src: it, name: '', size: 0, remote: false };
            return null;
        }).filter(Boolean);

        // merge, avoiding duplicate src values
        const seen = new Set(photosByOs[os].map(p => p && p.src));
        incoming.forEach(it => {
            if (!it) return;
            if (it.src && seen.has(it.src)) return;
            // if we have a File object, convert to dataUrl asynchronously when rendering/submitting
            photosByOs[os].push(it);
            if (it.src) seen.add(it.src);
        });
    }

    // replace all photos for a given OS (used when loading from server/row to avoid stale merges)
    function replacePhotosForOs(os, items){
        if(!os) return;
        os = String(os).trim();
        photosByOs[os] = [];
        setPhotosForOs(os, items || []);
    }

    function getPhotosForOs(os){
        return (os && photosByOs[os]) ? photosByOs[os] : [];
    }

    function renderPhotoPreview(previewEl, photos, os){
        if(!previewEl) return;
        previewEl.innerHTML = '';
        if(!photos || photos.length===0) return;
        photos.forEach((item, idx) => {
            const src = (typeof item === 'string') ? item : (item && (item.src || null));
            const wrapper = document.createElement('div');
            wrapper.className = 'photo-item';
            // identify this photo in DOM so progress updates can target it
            wrapper.setAttribute('data-photo-index', String(idx));
            wrapper.style.display = 'inline-block';
            wrapper.style.margin = '6px';
            wrapper.style.position = 'relative';

            const img = document.createElement('img');
            img.src = src || '';
            img.style.maxWidth = '160px';
            img.style.maxHeight = '120px';
            img.style.borderRadius = '8px';
            img.style.objectFit = 'cover';
            img.alt = item && item.name ? item.name : ('Foto ' + (idx+1));

            const caption = document.createElement('div');
            caption.style.textAlign = 'center';
            caption.style.fontSize = '10px';
            caption.style.color = '#666';
            caption.style.marginTop = '4px';
            caption.textContent = (item && item.name) ? item.name : ('Foto ' + (idx+1));

            // progress bar container (hidden until upload starts)
            const progWrap = document.createElement('div');
            progWrap.className = 'photo-progress';
            progWrap.style.width = '160px';
            progWrap.style.height = '8px';
            progWrap.style.background = '#eee';
            progWrap.style.borderRadius = '4px';
            progWrap.style.overflow = 'hidden';
            progWrap.style.margin = '6px auto 0';
            progWrap.style.display = 'none';
            const progBar = document.createElement('div');
            progBar.className = 'bar';
            progBar.style.width = '0%';
            progBar.style.height = '100%';
            progBar.style.background = '#3b82f6';
            progBar.style.transition = 'width 180ms linear';
            progWrap.appendChild(progBar);

            const progStatus = document.createElement('div');
            progStatus.className = 'photo-status';
            progStatus.style.fontSize = '11px';
            progStatus.style.color = '#444';
            progStatus.style.textAlign = 'center';
            progStatus.style.marginTop = '4px';
            progStatus.textContent = '';

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'photo-remove';
            btn.innerText = '×';
            btn.title = 'Remover foto';
            btn.style.position = 'absolute';
            btn.style.top = '6px';
            btn.style.right = '6px';
            btn.style.background = 'rgba(0,0,0,0.6)';
            btn.style.color = '#fff';
            btn.style.border = 'none';
            btn.style.borderRadius = '50%';
            btn.style.width = '24px';
            btn.style.height = '24px';
            btn.style.cursor = 'pointer';

            const repl = document.createElement('button');
            repl.type = 'button';
            repl.className = 'photo-replace';
            repl.innerText = '↻';
            repl.title = 'Substituir foto';
            repl.style.position = 'absolute';
            repl.style.top = '6px';
            repl.style.left = '6px';
            repl.style.background = 'rgba(0,0,0,0.6)';
            repl.style.color = '#fff';
            repl.style.border = 'none';
            repl.style.borderRadius = '50%';
            repl.style.width = '24px';
            repl.style.height = '24px';
            repl.style.cursor = 'pointer';

            // closure to bind the current index
            (function(index){
                btn.addEventListener('click', () => {
                    if(!os) return;
                    const arr = getPhotosForOs(os) || [];
                    if (index >= 0 && index < arr.length) {
                        arr.splice(index, 1);
                        setPhotosForOs(os, arr);
                        renderPhotoPreview(previewEl, getPhotosForOs(os), os);
                    }
                });

                repl.addEventListener('click', () => {
                    // open a hidden file input to pick a replacement image
                    const inp = document.createElement('input');
                    inp.type = 'file'; inp.accept = 'image/*'; inp.style.display = 'none';
                    inp.addEventListener('change', (ev) => {
                        const f = inp.files && inp.files[0];
                        if (!f) return;
                        const r = new FileReader();
                        r.onload = function(evt){
                            const newItem = { src: evt.target.result, name: f.name, size: f.size, file: f };
                            const arr2 = getPhotosForOs(os) || [];
                            if (index >= 0 && index < arr2.length) arr2[index] = newItem;
                            else arr2.push(newItem);
                            setPhotosForOs(os, arr2);
                            renderPhotoPreview(previewEl, getPhotosForOs(os), os);
                        };
                        r.readAsDataURL(f);
                    });
                    document.body.appendChild(inp);
                    inp.click();
                    setTimeout(()=>{ try{ document.body.removeChild(inp); }catch(e){} }, 1000);
                });
            })(idx);

            // use wrapper as the positioned container so absolute controls (remove/replace)
            // are positioned relative to each thumbnail
            wrapper.style.display = 'inline-block';
            wrapper.style.textAlign = 'center';
            wrapper.appendChild(img);
            wrapper.appendChild(caption);
            wrapper.appendChild(progWrap);
            wrapper.appendChild(progStatus);
            // replacement and remove controls
            wrapper.appendChild(repl);
            wrapper.appendChild(btn);
            previewEl.appendChild(wrapper);
        });
    }

    // update upload progress for a specific photo index belonging to an OS
    function updateUploadProgressForOs(os, index, percent){
        try{
            if(!os) return;
            const modal = document.getElementById('equip-modal');
            if(!modal) return;
            const preview = modal.querySelector('#photo-preview');
            if(!preview) return;
            const item = preview.querySelector('.photo-item[data-photo-index="' + index + '"]');
            if(!item) return;
            const progWrap = item.querySelector('.photo-progress');
            const progBar = item.querySelector('.photo-progress .bar');
            const status = item.querySelector('.photo-status');
            if(!progWrap || !progBar) return;
            progWrap.style.display = 'block';
            progBar.style.width = Math.max(0, Math.min(100, Math.round(percent))) + '%';
            if(status) status.textContent = percent >= 100 ? 'Enviado' : String(Math.round(percent)) + '%';
            if(percent >= 100){
                // brief delay then hide progress
                setTimeout(()=>{ try{ progWrap.style.display = 'none'; if(status) status.textContent = ''; }catch(e){} }, 800);
            }
        }catch(err){ console.warn('updateUploadProgressForOs error', err); }
    }

    // GLOBAL UI HELPERS: toasts and global upload progress
    function showToast(type, message, timeout){
        try{
            let container = document.getElementById('toast-container');
            if(!container){ container = document.createElement('div'); container.id = 'toast-container'; document.body.appendChild(container); }
            const toast = document.createElement('div');
            toast.className = 'toast ' + (type || 'info');
            toast.textContent = message || '';
            container.appendChild(toast);
            // trigger show
            requestAnimationFrame(()=>{ toast.classList.add('show'); });
            const t = (typeof timeout === 'number') ? timeout : 3500;
            setTimeout(()=>{ toast.classList.remove('show'); setTimeout(()=>{ try{ container.removeChild(toast); }catch(e){} }, 260); }, t);
        }catch(err){ console.warn('showToast error', err); }
    }

    function updateGlobalProgress(percent){
        try{
            const modal = document.getElementById('equip-modal');
            if(!modal) return;
            const pg = modal.querySelector('#global-upload-progress');
            if(!pg) return;
            const bar = pg.querySelector('.bar');
            if(!bar) return;
            const pct = Math.max(0, Math.min(100, Math.round(percent)));
            pg.style.display = pct > 0 && pct < 100 ? 'block' : (pct >= 100 ? 'block' : 'none');
            bar.style.width = pct + '%';
            pg.setAttribute('aria-valuenow', String(pct));
            if(pct >= 100){
                // hide after brief delay
                setTimeout(()=>{ try{ pg.style.display = 'none'; bar.style.width = '0%'; }catch(e){} }, 800);
            }
        }catch(err){ console.warn('updateGlobalProgress error', err); }
    }

    function initFilterPanel() {
        const toggle = document.getElementById('filter-toggle');
        const panel = document.getElementById('filter-panel');
        if (!toggle || !panel) return;

    const closePanel = () => {
        if (!panel) return;
        // remove visible/open state
        panel.classList.remove('open');
        panel.classList.remove('flip-up');
        panel.setAttribute('aria-hidden', 'true');
        toggle.setAttribute('aria-expanded', 'false');

        // remove all inline styles applied when opening so no visual artefacts remain
        try { panel.removeAttribute('style'); } catch (err) { /* defensive */ }

        // ensure the element is hidden so CSS rules for [hidden] take effect
        try { panel.setAttribute('hidden', ''); } catch (err) { /* defensive */ }

        // accessibility: return focus to the toggle button
        try { if (toggle && typeof toggle.focus === 'function') toggle.focus(); } catch (err) { /* noop */ }
    };

        const openPanel = () => {
                // defensive: ensure panel exists
                if (!panel) { console.warn('Filter panel element not found'); return; }
                // remove hidden attribute so browser can render it
                if (panel.hasAttribute('hidden')) panel.removeAttribute('hidden');
                const btnRect = toggle.getBoundingClientRect();
                const panelHeightEstimate = 480;
                const spaceBelow = window.innerHeight - btnRect.bottom;
                const spaceAbove = btnRect.top;
                const shouldFlip = spaceBelow < panelHeightEstimate && spaceAbove > spaceBelow;

            panel.style.position = 'fixed';
            panel.style.left = Math.max(8, btnRect.left) + 'px';
            panel.style.minWidth = Math.min(680, window.innerWidth - 32) + 'px';

            if (shouldFlip) {
                panel.classList.add('flip-up');
                panel.style.top = '';
                panel.style.bottom = (window.innerHeight - btnRect.top + 8) + 'px';
            } else {
                panel.classList.remove('flip-up');
                panel.style.bottom = '';
                panel.style.top = (btnRect.bottom + 8) + 'px';
            }

            panel.classList.add('open');
            panel.setAttribute('aria-hidden', 'false');
            toggle.setAttribute('aria-expanded', 'true');
        };

        toggle.addEventListener('click', () => {
            if (panel.classList.contains('open')) {
                closePanel();
            } else {
                const btnRect = toggle.getBoundingClientRect();
                const panelHeightEstimate = 480;
                const spaceBelow = window.innerHeight - btnRect.bottom;
                if (spaceBelow < panelHeightEstimate) panel.classList.add('flip-up');
                else panel.classList.remove('flip-up');
                openPanel();
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && panel.classList.contains('open')) closePanel();
        });

        // close panel when clicking outside of it or the toggle button
        document.addEventListener('click', (e) => {
            if (!panel) return;
            if (!panel.classList.contains('open')) return;
            if (!panel.contains(e.target) && !toggle.contains(e.target)) {
                closePanel();
            }
        });
    }

    // OS TOOLTIP + MODAL
    function initOsTooltipAndModal() {
        const osTooltipBtn = document.getElementById('open-os-tooltip-btn');
        const osTooltip = document.getElementById('os-tooltip');
        const modal = document.getElementById('equip-modal');
        if (!osTooltipBtn || !osTooltip || !modal) return;

        const overlay = modal.querySelector('.modal-overlay');
        const closeButtons = modal.querySelectorAll('[data-close], .modal-close, .modal-cancel');
        const form = document.getElementById('equip-form');

        // helper: fetch pending OS list from server (cached in window.__rdo_pending_list)
        async function fetchPendingOs(){
            if (Array.isArray(window.__rdo_pending_list) && window.__rdo_pending_list.length) return window.__rdo_pending_list;
            try {
                const resp = await fetch('/rdo/pending_os_json/', { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                if (!resp.ok) return [];
                const data = await resp.json();
                const list = Array.isArray(data.os_list) ? data.os_list : (Array.isArray(data.list) ? data.list : []);
                window.__rdo_pending_list = list;
                return list;
            } catch (e) { console.error('fetchPendingOs error', e); return []; }
        }

        function createHiddenForDisabled(input){
            if(!input) return null;
            // remove previous hidden if any
            const name = input.name || input.getAttribute('name');
            if(!name) return null;
            // existing hidden marker
            const existing = form.querySelector('input[type="hidden"][data-locked-for="'+name+'"]');
            if(existing) existing.parentElement.removeChild(existing);
            const h = document.createElement('input');
            h.type = 'hidden'; h.name = name; h.value = input.value || '';
            h.setAttribute('data-locked-for', name);
            form.appendChild(h);
            return h;
        }

        function lockField(input, value){
            setFieldLockedState(form, input, true, value || '');
        }

        function unlockLockedFields(){
            const lockedNames = Array.from(form.querySelectorAll('input[type="hidden"][data-locked-for]'))
                .map((h) => h.getAttribute('data-locked-for'))
                .filter(Boolean);
            lockedNames.forEach((name) => {
                const field = form.querySelector(`[name="${name}"]`);
                if(field) setFieldLockedState(form, field, false);
            });
            ['cliente','embarcacao','numero_os','previsao_retorno','fabricante'].forEach(name => {
                const field = form.querySelector(`[name="${name}"]`);
                if(field) setFieldLockedState(form, field, false);
            });
            // remove visual locked indicators
            try {
                const lockedLabels = form.querySelectorAll('label.locked');
                lockedLabels.forEach(lb => {
                    lb.classList.remove('locked');
                    lb.removeAttribute('aria-disabled');
                    // only remove title if it matches our marker
                    if (lb.getAttribute('title') === 'Campo bloqueado') lb.removeAttribute('title');
                });
                const lockedInputs = form.querySelectorAll('.locked');
                lockedInputs.forEach(inp => {
                    if (inp.tagName === 'INPUT' || inp.tagName === 'TEXTAREA' || inp.tagName === 'SELECT') {
                        inp.classList.remove('locked');
                        if (inp.getAttribute('title') === 'Campo bloqueado') inp.removeAttribute('title');
                        inp.removeAttribute('aria-disabled');
                    }
                });
            } catch (err) { /* defensive */ }
        }

        function openModalWithOsData(osObj){
            // osObj may contain keys with different names; be robust
            const numero = osObj.numero_os || osObj.numero || osObj.id || osObj.codigo_os || '';
            const cliente = osObj.cliente || osObj.empresa || osObj.company || '';
            const embarcacao = osObj.embarcacao || osObj.unidade || osObj.tanque || '';

            // prefer explicit data_fim from the OS (must be used as "previsão de retorno")
            const previsaoRaw = (osObj.hasOwnProperty('data_fim') && osObj.data_fim) ? osObj.data_fim : (osObj.previsao_retorno || osObj.previsao || osObj.data_fim_frente || '');

            // helper: normalize different date formats (dd/mm/yyyy, YYYY-MM-DD, timestamp) to YYYY-MM-DD
            function normalizeDateToISO(input){
                if(!input && input !== 0) return '';
                // numbers / timestamps
                if(typeof input === 'number'){
                    try { return (new Date(input)).toISOString().slice(0,10); } catch(e){ return String(input); }
                }
                const s = String(input).trim();
                // already ISO-like
                const isoMatch = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
                if(isoMatch) return isoMatch[0];
                // dd/mm/yyyy -> convert
                const brMatch = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
                if(brMatch) return `${brMatch[3]}-${brMatch[2]}-${brMatch[1]}`;
                // try Date parse fallback
                const parsed = Date.parse(s);
                if(!isNaN(parsed)){
                    try { return (new Date(parsed)).toISOString().slice(0,10); } catch(e) { return s; }
                }
                // unknown format, return raw
                return s;
            }

            // set & lock fields
            lockField(form.querySelector('[name="numero_os"]'), numero);
            lockField(form.querySelector('[name="cliente"]'), cliente);
            lockField(form.querySelector('[name="embarcacao"]'), embarcacao);
            const dateVal = normalizeDateToISO(previsaoRaw);
            lockField(form.querySelector('[name="previsao_retorno"]'), dateVal);

            // ensure create flow starts without editing id bound
            try {
                const idHidden = form.querySelector('input[type="hidden"][name="equipamento_id"]');
                if (idHidden) {
                    idHidden.value = '';
                    delete idHidden.dataset.source;
                }
                const sourceHidden = form.querySelector('input[type="hidden"][name="source_equipamento_id"]');
                if (sourceHidden) sourceHidden.value = '';
            } catch (err) {}

            try {
                const descricaoField = form.querySelector('[name="descricao"]');
                if(descricaoField && !descricaoField.value) syncEquipamentoFormMode('');
            } catch (err) {}

            modal.removeAttribute('hidden'); document.body.style.overflow='hidden';
            const previewEl = modal.querySelector('#photo-preview');
            // render existing photos for this OS (if any)
            const existing = getPhotosForOs(numero);
            renderPhotoPreview(previewEl, existing, numero);
            const first = form.querySelector('input:not([disabled]), textarea, select');
            if(first) first.focus();
        }

        function clearModalTransientState(){
            try {
                // clear lookup/edit binding
                const idHidden = form.querySelector('input[name="equipamento_id"]');
                if (idHidden) {
                    idHidden.value = '';
                    try { delete idHidden.dataset.source; } catch (err) {}
                }
                const sourceHidden = form.querySelector('input[name="source_equipamento_id"]');
                if (sourceHidden) sourceHidden.value = '';

                // clear histories shown in modal
                try { renderIdentifierHistory([]); } catch (err) {}
                try { renderSituacaoHistory([]); } catch (err) {}

                // clear photos preview and in-memory cache to avoid stale reopen state
                const previewEl = form.querySelector('#photo-preview');
                if (previewEl) previewEl.innerHTML = '';
                Object.keys(photosByOs).forEach((k) => { delete photosByOs[k]; });

                // clear identifier reason field
                const motivoEl = form.querySelector('[name="identificador_motivo"]');
                if (motivoEl) motivoEl.value = '';

                const fabricanteField = form.querySelector('[name="fabricante"]');
                if (fabricanteField) {
                    try { delete fabricanteField.dataset.previousValue; } catch (err) {}
                }
            } catch (err) {
                console.warn('clearModalTransientState error', err);
            }
        }

        function closeModal(){
            clearModalTransientState();
            modal.setAttribute('hidden','');
            document.body.style.overflow='';
            form.reset();
            syncEquipamentoFormMode('');
        }

        on(osTooltipBtn, 'click', async (e)=>{
            const expanded = osTooltipBtn.getAttribute('aria-expanded') === 'true';
            osTooltipBtn.setAttribute('aria-expanded', String(!expanded));
            // if we're opening, populate list from server
            if (!expanded) {
                // show tooltip while populating
                osTooltip.hidden = false;
                const list = await fetchPendingOs();
                const wrap = osTooltip.querySelector('.os-tooltip-list');
                if (!wrap) return;
                wrap.innerHTML = '';
                if (!list || list.length === 0) {
                    const p = document.createElement('div'); p.className='os-empty'; p.textContent = 'Nenhuma OS aberta encontrada.'; wrap.appendChild(p);
                } else {
                    // Build a mapping number -> [items] to deduplicate by OS number
                    const grouped = {};
                    list.forEach(it => {
                        const num = String(it.numero_os || it.numero || it.id || '').trim();
                        if (!num) return; // skip empty numbers
                        grouped[num] = grouped[num] || [];
                        grouped[num].push(it);
                    });

                    // collect numbers already present in the table to avoid repeating
                    const tableRows = document.querySelectorAll('.equipamentos-table tbody tr');
                    const tableNumbers = new Set();
                    tableRows.forEach(tr => {
                        const td = tr.querySelector('td[data-label="Nº OS"]');
                        const ds = td ? td.textContent.trim() : (tr.getAttribute('data-os') || tr.dataset.os || '');
                        if (ds) tableNumbers.add(String(ds).trim());
                    });

                    // create two sections: in-table and pending
                    const inTableKeys = [];
                    const pendingKeys = [];
                    Object.keys(grouped).forEach(num => {
                        if (tableNumbers.has(num)) inTableKeys.push(num);
                        else pendingKeys.push(num);
                    });

                    // open modal with full list and search/filter capability
                    function openOsListModal(fullList){
                        const modalEl = document.getElementById('os-list-modal');
                        const content = document.getElementById('os-list-content');
                        const search = document.getElementById('os-list-search');
                        if(!modalEl || !content) return;
                        content.innerHTML = '';
                        // render rows for full list (each entry separately)
                        const renderRows = (items) => {
                            content.innerHTML = '';
                            items.forEach(it => {
                                const div = document.createElement('div'); div.className = 'os-list-row';
                                const left = document.createElement('div'); left.className = 'meta';
                                const num = it.numero_os || it.numero || it.id || '';
                                left.textContent = (num ? String(num) : '') + (it.empresa || it.cliente ? ' — ' + (it.empresa || it.cliente) : '');
                                const btn = document.createElement('button'); btn.type = 'button'; btn.textContent = 'Abrir';
                                btn.addEventListener('click', ()=>{ try{ unlockLockedFields(); openModalWithOsData(it); }catch(e){} modalEl.setAttribute('hidden',''); document.body.style.overflow=''; });
                                div.appendChild(left); div.appendChild(btn); content.appendChild(div);
                            });
                        };
                        renderRows(fullList);
                        // show modal
                        modalEl.removeAttribute('hidden'); document.body.style.overflow='hidden';
                        const closeBtn = modalEl.querySelector('.os-list-close'); const overlay = modalEl.querySelector('.os-list-overlay');
                        const hide = () => { modalEl.setAttribute('hidden',''); document.body.style.overflow=''; };
                        if(closeBtn) closeBtn.onclick = hide; if(overlay) overlay.onclick = hide;
                        if(search){ search.value=''; search.oninput = ()=>{ const q = search.value.trim().toLowerCase(); const filtered = fullList.filter(it=>{ const s = ((it.numero_os||it.numero||'') + ' ' + (it.empresa||it.cliente||'') + ' ' + (it.embarcacao||'')).toLowerCase(); return s.indexOf(q) !== -1; }); renderRows(filtered); } }
                    }

                    const makeSection = (title, keys, cls) => {
                        if (!keys || keys.length === 0) return;
                        const h = document.createElement('div'); h.className = 'os-section-title'; h.textContent = title;
                        wrap.appendChild(h);
                        const MAX_VISIBLE = 6;
                        keys.forEach((num, idx) => {
                            const items = grouped[num] || [];
                            const representative = items[0] || {};
                            const btn = document.createElement('button');
                            btn.type = 'button'; btn.className = 'os-item ' + (cls||'');
                            const labelParts = [];
                            if (num) labelParts.push(String(num));
                            const c = representative.empresa || representative.cliente || representative.company || '';
                            if (c) labelParts.push('— ' + c);
                            if (items.length > 1) labelParts.push('(' + items.length + ')');
                            const label = labelParts.join(' ');
                            btn.setAttribute('data-numero-os', num);
                            try { btn.__os_payload = representative; } catch(e){}
                            btn.textContent = label || (representative.id || 'OS');
                            if (cls === 'in-table') { btn.setAttribute('aria-pressed', 'true'); btn.title = 'Já presente na tabela'; }
                            if (idx < MAX_VISIBLE) wrap.appendChild(btn);
                        });
                        if (keys.length > MAX_VISIBLE) {
                            const more = document.createElement('button'); more.type = 'button'; more.className = 'os-item os-more'; more.textContent = 'Ver mais...';
                            more.addEventListener('click', (ev) => { ev.preventDefault(); openOsListModal(list); });
                            wrap.appendChild(more);
                        }
                    };

                    // Render in-table first (if any), then pendentes
                    makeSection('OS já na tabela', inTableKeys, 'in-table');
                    makeSection('OS pendentes', pendingKeys, 'pending');

                    // If grouping produced no visible buttons (e.g. numbers missing), fall back to listing raw items
                    if (Object.keys(grouped).length === 0) {
                        const p = document.createElement('div'); p.className='os-empty'; p.textContent = 'Nenhuma OS aberta encontrada.'; wrap.appendChild(p);
                    }
                }
            } else {
                osTooltip.hidden = true;
            }
        });

        document.addEventListener('click', (e)=>{
            if(!osTooltip.contains(e.target) && !osTooltipBtn.contains(e.target)){
                osTooltipBtn.setAttribute('aria-expanded','false'); osTooltip.hidden = true;
            }
        });

        // delegate click inside tooltip list to handle dynamically populated items
        osTooltip.addEventListener('click', (e)=>{
            const btn = e.target.closest && e.target.closest('.os-item');
            if(!btn) return;
            // if this is the "Ver mais" button, let its own click handler run (it opens the full list modal)
            if (btn.classList && btn.classList.contains('os-more')) return;
            // prefer attached payload, else try to find by numero
            const payload = btn.__os_payload || null;
            osTooltipBtn.focus();
            osTooltipBtn.setAttribute('aria-expanded','false'); osTooltip.hidden = true;
            // unlock any previously locked fields before opening new selection
            unlockLockedFields();
            if(payload){ openModalWithOsData(payload); }
            else {
                // fallback: try fetchPendingOs and match by data-numero-os
                const num = btn.getAttribute('data-numero-os') || btn.textContent.trim();
                fetchPendingOs().then(list=>{
                    const found = (list||[]).find(x=>String(x.numero_os||x.numero||x.id) === String(num));
                    if(found) openModalWithOsData(found);
                    else openModalWithOsData({ numero_os: num });
                });
            }
        });

    if (overlay) on(overlay, 'click', () => { unlockLockedFields(); closeModal(); });
    closeButtons.forEach(b => on(b, 'click', () => { unlockLockedFields(); closeModal(); }));
    document.addEventListener('keydown', (e)=>{ if(e.key==='Escape' && !modal.hasAttribute('hidden')) { unlockLockedFields(); closeModal(); } });

        if (form) form.addEventListener('submit', async (e)=>{
            e.preventDefault();
            function clearFieldError(name){
                const input = form.querySelector(`[name="${name}"]`);
                if(!input) return;
                input.classList.remove('field-error');
                input.removeAttribute('aria-invalid');
                input.removeAttribute('title');
            }
            function setFieldError(name, message){
                const input = form.querySelector(`[name="${name}"]`);
                if(!input) return;
                input.classList.add('field-error');
                input.setAttribute('aria-invalid', 'true');
                if(message) input.setAttribute('title', message);
            }
            function handleSaveError(rawMessage){
                const msg = String(rawMessage || 'Erro ao salvar equipamento.');
                clearFieldError('tag');
                clearFieldError('serie');
                if (/\btag\b/i.test(msg)) setFieldError('tag', msg);
                if (/s(é|e)rie/i.test(msg)) setFieldError('serie', msg);
                if (/container/i.test(msg)) setFieldError('tag', msg);
                if (/eslinga/i.test(msg)) setFieldError('serie', msg);
                if (/tag\s+ou\s+n(ú|u)mero\s+de\s+s(é|e)rie/i.test(msg)) {
                    setFieldError('tag', msg);
                    setFieldError('serie', msg);
                }
                if (/n(ú|u)mero\s+do\s+container\s+ou\s+n(ú|u)mero\s+da\s+eslinga/i.test(msg)) {
                    setFieldError('tag', msg);
                    setFieldError('serie', msg);
                }
                showToast('error', msg);
            }

            // show spinner on save button to prevent double submits
            function startSaveSpinner(){
                const btn = form.querySelector('button[type="submit"]');
                if(!btn) return;
                // disable to prevent double submits
                try{ btn.disabled = true; }catch(e){}
                btn.classList.add('saving');
                // remember original text
                if(!btn.dataset.originalText) btn.dataset.originalText = btn.textContent.trim();
                btn.textContent = 'Enviando...';
                // prepend spinner element
                let s = btn.querySelector('.btn-spinner');
                if(!s){ s = document.createElement('span'); s.className = 'btn-spinner'; btn.insertBefore(s, btn.firstChild); }
                // show global progress bar at 0
                updateGlobalProgress(0);
            }

            function stopSaveSpinner(){
                const btn = form.querySelector('button[type="submit"]');
                if(!btn) return;
                try{ btn.disabled = false; }catch(e){}
                btn.classList.remove('saving');
                const s = btn.querySelector('.btn-spinner'); if(s) try{ btn.removeChild(s); }catch(e){}
                // restore original text
                try{ if(btn.dataset.originalText) btn.textContent = btn.dataset.originalText; }catch(e){}
                // ensure global progress hidden
                updateGlobalProgress(100);
            }
            // build FormData including disabled-hidden mirrored inputs
            const fd = new FormData(form);
            clearFieldError('tag');
            clearFieldError('serie');
            // if the user requested 'Salvar e +' mark the request so backend can respond accordingly
            try { if (form.dataset && form.dataset.keepOpen) fd.append('keep_open', '1'); else if (form.getAttribute && form.getAttribute('data-keep-open')) fd.append('keep_open', '1'); } catch(e) {}
            // include any photos currently stored in-memory for this OS
            const osVal = form.querySelector('[name="numero_os"]').value || '';
            const inMemoryPhotos = getPhotosForOs(osVal) || [];
            // Prefer sending the actual File objects from the input element when available.
            const fileInput = form.querySelector('[name="photos"]');
            if (fileInput && fileInput.files && fileInput.files.length > 0) {
                Array.from(fileInput.files).forEach(f => fd.append('photos', f));
            }
            // If there are photos stored in-memory, only upload local items (remote=true are already on server).
            if (inMemoryPhotos && inMemoryPhotos.length > 0) {
                const localItems = inMemoryPhotos.filter(p => !(p && p.remote));
                const conversions = localItems.map((item, idx) => (async () => {
                    try {
                        if (item.file) {
                            // original File object available
                            fd.append('photos', item.file, item.name || (`photo_${Date.now()}_${idx}`));
                            return;
                        }
                        const dataUrl = item.src;
                        if (!dataUrl) return;
                        const resp = await fetch(dataUrl);
                        const blob = await resp.blob();
                        const mime = blob.type || 'image/png';
                        const ext = (mime.split('/')[1] || 'png').split(';')[0];
                        const filename = item.name || `photo_${Date.now()}_${idx}.${ext}`;
                        fd.append('photos', blob, filename);
                    } catch (err) {
                        console.warn('failed to convert dataURL to blob', err);
                    }
                })());
                await Promise.all(conversions);
            }

            // Append list of existing remote photo URLs so backend can detect which photos were removed
            try {
                const existingRemote = (inMemoryPhotos || []).filter(p => p && p.remote).map(p => p.src).filter(Boolean);
                if (existingRemote.length > 0) {
                    fd.append('existing_photo_urls', JSON.stringify(existingRemote));
                } else {
                    // explicitly append empty list so backend knows none are kept for this equipamento
                    fd.append('existing_photo_urls', JSON.stringify([]));
                }
            } catch (err) { console.warn('could not append existing_photo_urls', err); }

            // CSRF token (Django default name)
            function getCookie(name) {
                const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
                return v ? v.pop() : '';
            }
            const csrftoken = getCookie('csrftoken');

            try {
                startSaveSpinner();

                // collect files appended under 'photos' in the FormData so we can map progress per-file
                const uploadFiles = [];
                try {
                    const photosEntries = fd.getAll ? fd.getAll('photos') : [];
                    // find preview indices for local (non-remote) photos so we can update the correct thumbnail
                    const previewAll = getPhotosForOs(osVal) || [];
                    const previewLocalIndexes = [];
                    previewAll.forEach((p, j) => { if (!(p && p.remote)) previewLocalIndexes.push(j); });

                    if (Array.isArray(photosEntries)) {
                        let totalBytes = 0;
                        photosEntries.forEach((val, k) => {
                            const size = (val && val.size) ? val.size : 0;
                            const previewIndex = (k < previewLocalIndexes.length) ? previewLocalIndexes[k] : k;
                            uploadFiles.push({ value: val, size: size, previewIndex: previewIndex });
                            totalBytes += size;
                        });
                        uploadFiles.totalBytes = totalBytes;
                    }
                } catch (err) { /* ignore FormData inspection errors */ }

                // If there are files to upload, use XHR to get upload progress events
                if (uploadFiles.length > 0) {
                    const xhr = new XMLHttpRequest();
                    xhr.open('POST', '/api/equipamentos/save/', true);
                    xhr.withCredentials = true;
                    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                    xhr.setRequestHeader('X-CSRFToken', csrftoken);

                    xhr.upload.onprogress = function(e){
                        try{
                            const loaded = e.loaded || 0;
                            const total = uploadFiles.totalBytes || e.total || 0;
                            // map cumulative loaded bytes to each file index
                            let cum = 0;
                            for(let i=0;i<uploadFiles.length;i++){
                                const fsize = uploadFiles[i].size || 0;
                                const start = cum;
                                const end = cum + fsize;
                                cum = end;
                                let pct = 0;
                                if (total > 0) {
                                    if (loaded >= end) pct = 100;
                                    else if (loaded <= start) pct = 0;
                                    else pct = ((loaded - start) / Math.max(1, (end - start))) * 100;
                                } else {
                                    pct = 0;
                                }
                                const previewIndex = (typeof uploadFiles[i].previewIndex !== 'undefined') ? uploadFiles[i].previewIndex : i;
                                // update preview progress for this photo
                                updateUploadProgressForOs(osVal, previewIndex, pct);
                            }
                            // overall progress
                            try{
                                const overallPct = total > 0 ? ((loaded/total) * 100) : 0;
                                updateGlobalProgress(overallPct);
                            }catch(e){}
                        }catch(err){ console.warn('xhr.onprogress error', err); }
                    };

                    xhr.onreadystatechange = function(){
                        if (xhr.readyState !== 4) return;
                        stopSaveSpinner();
                        // ensure progress at 100%
                        updateGlobalProgress(100);
                        if (xhr.status >= 200 && xhr.status < 300) {
                            let data = null;
                            try { data = JSON.parse(xhr.responseText); } catch (err) { data = null; }
                            if (data && data.success) {
                                // handle success (update in-memory photos and UI)
                                // If user requested 'Salvar e +' keep the modal open and only clear equipamento-specific fields
                                const keep = form && form.dataset && form.dataset.keepOpen;
                                if (!keep) { closeModal(); unlockLockedFields(); } else { /* keep modal open */ }
                                try {
                                    const returned = (data.formulario && Array.isArray(data.formulario.photo_urls)) ? data.formulario.photo_urls : [];
                                    const osValLocal = form.querySelector('[name="numero_os"]').value || '';
                                    if (returned.length > 0 && osValLocal) {
                                        photosByOs[osValLocal] = returned.map(u => ({ src: u, name: '', size: 0, remote: true }));
                                        try { const previewEl2 = form.querySelector('#photo-preview'); if(previewEl2) renderPhotoPreview(previewEl2, getPhotosForOs(osValLocal), osValLocal); } catch(e){}
                                    }
                                } catch (err) { console.warn('could not update photosByOs from response', err); }
                                try {
                                    const tb = document.querySelector('.equipamentos-table tbody');
                                    if (tb && data.equipamento && data.formulario) {
                                        const eq = data.equipamento; const fo = data.formulario; const tr = document.createElement('tr');
                                        tr.setAttribute('data-id', eq.id);
                                        tr.setAttribute('data-modelo', eq.modelo || '');
                                        tr.setAttribute('data-fabricante', eq.fabricante || '');
                                        tr.setAttribute('data-descricao', eq.descricao || '');
                                        tr.setAttribute('data-serie', eq.numero_serie || '');
                                        tr.setAttribute('data-tag', eq.numero_tag || '');
                                        tr.setAttribute('data-cliente', (form.querySelector('[name="cliente"]')||{value:''}).value);
                                        tr.setAttribute('data-embarcacao', (form.querySelector('[name="embarcacao"]')||{value:''}).value);
                                        tr.setAttribute('data-responsavel', fo.responsavel || '');
                                        tr.setAttribute('data-os', (form.querySelector('[name="numero_os"]')||{value:''}).value);
                                        tr.setAttribute('data-data_inspecao', fo.data_inspecao || '');
                                        tr.setAttribute('data-local', fo.local_inspecao || '');
                                        tr.setAttribute('data-previsao', fo.previsao_retorno || '');
                                        tr.setAttribute('data-situacao', (eq.situacao || (form.querySelector('[name="situacao"]')||{value:''}).value || ''));
                                        try { if (data.formulario && Array.isArray(data.formulario.photo_urls) && data.formulario.photo_urls.length>0) { tr.setAttribute('data-photo-urls', JSON.stringify(data.formulario.photo_urls)); } } catch(e){}
                                        const cell = (text, label, classes) => { const td = document.createElement('td'); if (label) td.setAttribute('data-label', label); if (classes) td.className = classes; td.innerHTML = text || ''; return td; };
                                        tr.appendChild(cell(eq.id || '', 'ID'));
                                        tr.appendChild(cell(eq.descricao || '', 'Tipo de Equipamento'));
                                        tr.appendChild(cell(eq.modelo || '', 'Modelo do Equipamento'));
                                        tr.appendChild(cell(eq.numero_serie || '', 'Número de Série do Equipamento'));
                                        tr.appendChild(cell(eq.numero_tag || '', 'Número de TAG Ambipar'));
                                        tr.appendChild(cell(getTableDisplayValue(eq.fabricante), 'Fabricante do Equipamento'));
                                        const clienteHtml = (form.querySelector('[name="cliente"]')||{value:''}).value ? `<div class="td-client" title="${(form.querySelector('[name="cliente"]')||{value:''}).value}"><span class="client-dot" aria-hidden="true"></span><span class="client-name">${(form.querySelector('[name="cliente"]')||{value:''}).value}</span></div>` : '';
                                        tr.appendChild(cell(clienteHtml, 'Cliente'));
                                        tr.appendChild(cell((form.querySelector('[name="embarcacao"]')||{value:''}).value, 'Embarcação'));
                                        tr.appendChild(cell(fo.responsavel || '', 'Responsável'));
                                        const numeroOsCell = cell((form.querySelector('[name="numero_os"]')||{value:''}).value, 'Nº OS'); try { numeroOsCell.setAttribute('data-os', (form.querySelector('[name="numero_os"]')||{value:''}).value); } catch(e){}
                                        tr.appendChild(numeroOsCell);
                                        tr.appendChild(cell(fo.data_inspecao ? formatDateToBR(fo.data_inspecao) : '', 'Data da inspeção'));
                                        tr.appendChild(cell(fo.local_inspecao || '', 'Local'));
                                        tr.appendChild(cell(fo.previsao_retorno ? formatDateToBR(fo.previsao_retorno) : '', 'Previsão de Retorno'));
                                        // situacao badge + action button (badge shows only color/icon; label available via aria-label/title)
                                        const situVal = (eq.situacao || (form.querySelector('[name="situacao"]')||{value:''}).value || '');
                                        const situLabel = (situVal === 'embarcardo') ? 'Embarcado' : (situVal === 'trocou_unidade' ? 'Trocou de Unidade' : (situVal === 'retornou_base' ? 'Retornou para Base' : ''));
                                        const situHtml = `<div class="situacao-cell"><span class="situacao-badge situacao-${situVal||'none'}" role="img" aria-label="${situLabel}"></span> <button type="button" class="action-btn situacao-btn" data-equip-id="${eq.id}" aria-label="Alterar situação" title="Alterar situação"><span class="material-icons" aria-hidden="true">swap_horiz</span></button> <button type="button" class="action-btn situacao-history-btn" data-equip-id="${eq.id}" aria-label="Ver histórico de situação" title="Ver histórico"><span class="material-icons" aria-hidden="true">history</span></button></div>`;
                                        tr.appendChild(cell(situHtml, 'Situação'));
                                        const actionsTd = document.createElement('td'); actionsTd.className='row-actions'; actionsTd.innerHTML = '<button type="button" class="action-btn identifier-swap-btn" data-equip-id="'+(eq.id || '')+'" aria-label="Trocar TAG e Série" title="Trocar TAG/Série"><span class="material-icons" aria-hidden="true">fingerprint</span></button> <button type="button" class="action-btn edit-btn" aria-label="Editar equipamento" title="Editar equipamento"><span class="material-icons" aria-hidden="true">edit</span></button> <button type="button" class="action-btn report-btn" aria-label="Relatório técnico" title="Abrir relatório técnico"><span class="material-icons" aria-hidden="true">description</span></button>';
                                        tr.appendChild(actionsTd);
                                        updateIdentifierActionButtonForRow(tr);
                                        // attach situacao handler for newly inserted row
                                        try { attachSituacaoHandlers(tr); } catch(e){}
                                        try { const existing = tb.querySelector('tr[data-id="' + (eq.id || '') + '"]'); if (existing) tb.replaceChild(tr, existing); else tb.insertBefore(tr, tb.firstChild); const editBtn = tr.querySelector('.edit-btn'); if(editBtn) editBtn.addEventListener('click', (e)=>{ openModalForTr(tr); }); const reportBtn = tr.querySelector('.report-btn'); if(reportBtn) reportBtn.addEventListener('click', (e)=>{ const payload = getRowPayloadFromTr(tr); const html = buildReportHtml(payload); const w = window.open('', '_blank'); if(w){ w.document.write(html); w.document.close(); } }); } catch (err) { try { tb.insertBefore(tr, tb.firstChild); } catch(e){} }
                                        try { 
                                            tr.classList.add('row-highlight');
                                            try { tr.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch(e) {}
                                            // show different feedback if keeping modal open
                                            showToast('success', keep ? 'Equipamento salvo. Adicione outro.' : 'Equipamento salvo com sucesso.');
                                            setTimeout(() => { tr.classList.remove('row-highlight'); }, 2200);
                                            if (keep) {
                                                // clear equipamento-specific fields but keep operation info
                                                try {
                                                    ['modelo','serie','tag','fabricante','descricao'].forEach(n=>{ const el=form.querySelector('[name="'+n+'"]'); if(el) el.value = ''; });
                                                    const idHidden = form.querySelector('input[name="equipamento_id"]'); if(idHidden) idHidden.value = '';
                                                    const sourceHidden = form.querySelector('input[name="source_equipamento_id"]'); if(sourceHidden) sourceHidden.value = '';
                                                    const fileInput = form.querySelector('[name="photos"]'); if(fileInput) try{ fileInput.value = ''; }catch(e){}
                                                    const previewEl3 = form.querySelector('#photo-preview'); if(previewEl3) renderPhotoPreview(previewEl3, [], form.querySelector('[name="numero_os"]').value || '');
                                                    try { renderIdentifierHistory([]); } catch(e){}
                                                    try { syncEquipamentoFormMode(''); } catch(e){}
                                                    delete form.dataset.keepOpen;
                                                    const firstEquip = form.querySelector('[name="modelo"]') || form.querySelector('input:not([readonly]), textarea, select'); if(firstEquip) firstEquip.focus();
                                                } catch(err){}
                                            } else {
                                                setTimeout(() => { try { window.location.reload(); } catch(e) {} }, 900);
                                            }
                                        } catch (err) { console.error('visual feedback error', err); }
                                    }
                                } catch (err) { console.error('erro ao inserir linha dinamicamente', err); }
                            } else {
                                console.error('save_equipamento response missing success', data);
                                showToast('error', 'Erro ao salvar: resposta inválida.');
                            }
                        } else {
                            let errMsg = 'Erro ao salvar equipamento. Verifique a conexão e tente novamente.';
                            try {
                                const parsed = JSON.parse(xhr.responseText || '{}');
                                if (parsed && parsed.error) errMsg = parsed.error;
                            } catch(err) {}
                            console.error('save_equipamento xhr failed', xhr.status, xhr.statusText, xhr.responseText);
                            handleSaveError(errMsg);
                        }
                    };
                    // send
                    try { xhr.send(fd); } catch (err) { stopSaveSpinner(); console.error('xhr send error', err); alert('Erro ao enviar dados. Verifique a conexão e tente novamente.'); }
                    return;
                }

                // fallback: no files to upload, use fetch as before
                const resp = await fetch('/api/equipamentos/save/', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrftoken
                    },
                    body: fd
                });
                if (!resp.ok) {
                    stopSaveSpinner();
                    const errTxt = await resp.text();
                    let errMsg = 'Erro ao salvar equipamento. Veja console para mais detalhes.';
                    try {
                        const parsed = JSON.parse(errTxt || '{}');
                        if (parsed && parsed.error) errMsg = parsed.error;
                    } catch(err) {}
                    console.error('save_equipamento failed', errTxt);
                    handleSaveError(errMsg);
                    return;
                }
                const data = await resp.json();
                if (data && data.success) {
                    // If user requested 'Salvar e +' keep the modal open and only clear equipamento-specific fields
                    const keep = form && form.dataset && form.dataset.keepOpen;
                    if (!keep) { closeModal(); unlockLockedFields(); }
                    showToast('success', keep ? 'Equipamento salvo. Adicione outro.' : 'Equipamento salvo com sucesso.');
                    if (keep) {
                        try {
                            ['modelo','serie','tag','fabricante','descricao'].forEach(n=>{ const el=form.querySelector('[name="'+n+'"]'); if(el) el.value = ''; });
                            const motivoEl = form.querySelector('[name="identificador_motivo"]'); if(motivoEl) motivoEl.value = '';
                            const idHidden = form.querySelector('input[name="equipamento_id"]'); if(idHidden) idHidden.value = '';
                            const sourceHidden = form.querySelector('input[name="source_equipamento_id"]'); if(sourceHidden) sourceHidden.value = '';
                            const fileInput = form.querySelector('[name="photos"]'); if(fileInput) try{ fileInput.value = ''; }catch(e){}
                            const previewEl3 = form.querySelector('#photo-preview'); if(previewEl3) renderPhotoPreview(previewEl3, [], form.querySelector('[name="numero_os"]').value || '');
                            try { renderIdentifierHistory([]); } catch(e){}
                            try { syncEquipamentoFormMode(''); } catch(e){}
                            delete form.dataset.keepOpen;
                            const firstEquip = form.querySelector('[name="modelo"]') || form.querySelector('input:not([readonly]), textarea, select'); if(firstEquip) firstEquip.focus();
                        } catch(err){}
                    } else {
                        try { window.location.reload(); } catch(e) { /* noop */ }
                    }
                } else {
                    stopSaveSpinner();
                    console.error('save_equipamento response error', data);
                    handleSaveError((data && data.error) ? data.error : 'Erro ao salvar: resposta inválida');
                }
            } catch (err) {
                stopSaveSpinner();
                console.error('save_equipamento exception', err);
                alert('Erro ao enviar dados. Verifique a conexão e tente novamente.');
            }
        });
    }

    function initTableActions(){
        function findRow(element){ while(element && element.tagName !== 'TR') element = element.parentElement; return element; }

        // Prefer reading canonical values from the tr's data-* attributes (set by server/template)
        function getRowPayloadFromTr(tr){
            if(!tr) return {};
            const d = tr.dataset || {};
            // map dataset keys to form-friendly names
            return {
                id: d.id || tr.getAttribute('data-id') || '',
                modelo: d.modelo || '',
                fabricante: d.fabricante || '',
                descricao: d.descricao || '',
                serie: d.serie || d.numeroSerie || '',
                tag: d.tag || '',
                cliente: d.cliente || '',
                embarcacao: d.embarcacao || '',
                responsavel: d.responsavel || '',
                numero_os: d.os || d.numero_os || tr.querySelector('td[data-label="Nº OS"]')?.textContent.trim() || '',
                data_inspecao: d.data_inspecao || d.dataInspecao || '',
                local: d.local || '',
                    previsao_retorno: d.previsao || d.previsao_retorno || '',
                    situacao: d.situacao || ''
            };
        }

        function openEditModalWithData(data, rowEl){
            // data is expected in the normalized payload shape from getRowPayloadFromTr
            const modal = document.getElementById('equip-modal');
            const form = document.getElementById('equip-form');
            if(!modal || !form) return;
            const set = (name, value) => { const el = form.querySelector('[name="' + name + '"]'); if(el) el.value = (value === null || value === undefined) ? '' : String(value); };
            set('cliente', data.cliente || '');
            set('embarcacao', data.embarcacao || '');
            set('responsavel', data.responsavel || '');
            set('numero_os', data.numero_os || '');
            // data_inspecao may be ISO (YYYY-MM-DD) already; input[type=date] accepts that format
            set('data_inspecao', data.data_inspecao || '');
            set('local', data.local || '');
            set('previsao_retorno', data.previsao_retorno || '');
            set('modelo', data.modelo || '');
            set('serie', data.serie || '');
            set('tag', data.tag || '');
            set('fabricante', data.fabricante || '');
            set('descricao', data.descricao || '');
            set('situacao', data.situacao || '');
            set('identificador_motivo', '');
            syncEquipamentoFormMode(data.descricao || '');

            // store the equipamento id in a hidden field so save endpoint can detect updates if desired
            let idHidden = form.querySelector('input[type="hidden"][name="equipamento_id"]');
            if(!idHidden){ idHidden = document.createElement('input'); idHidden.type = 'hidden'; idHidden.name = 'equipamento_id'; form.appendChild(idHidden); }
            idHidden.value = data.id || '';
            try { idHidden.dataset.source = 'edit'; } catch(err) {}

            const osField = form.querySelector('[name="numero_os"]'); if(osField) { osField.readOnly = true; osField.disabled = false; }

            // If editing an existing equipamento, lock cliente and embarcação so they cannot be changed
            if (data.id) {
                try {
                    const clienteField = form.querySelector('[name="cliente"]');
                    const embarField = form.querySelector('[name="embarcacao"]');
                    if (clienteField) setFieldLockedState(form, clienteField, true, clienteField.value || '');
                    if (embarField) setFieldLockedState(form, embarField, true, embarField.value || '');
                } catch (err) { /* defensive */ }
            }
            modal.removeAttribute('hidden'); document.body.style.overflow='hidden';
            const first = form.querySelector('input:not([readonly]), textarea, select'); if(first) first.focus();
            // attempt to fetch and render situacao history for this equipamento
            try {
                const histPanel = document.getElementById('situacao-history-panel');
                const histList = document.getElementById('situacao-history-list');
                if (data.id) {
                    (async () => {
                        try {
                            const srv = await fetchEquipamentoById(data.id);
                            const hist = (srv && srv.situacao_history) ? srv.situacao_history : (data.situacao_history || []);
                            renderSituacaoHistory(hist);
                            const idHist = (srv && srv.identifier_history) ? srv.identifier_history : (data.identifier_history || []);
                            renderIdentifierHistory(idHist, (srv && srv.descricao) || data.descricao || '');
                        } catch (err) { console.warn('erro ao obter historico de situacao', err); renderSituacaoHistory([]); renderIdentifierHistory([], data.descricao || ''); }
                    })();
                } else {
                    renderSituacaoHistory([]);
                    renderIdentifierHistory([], data.descricao || '');
                }
            } catch (err) { console.warn('render situacao history invoke error', err); }
            // render photos for this OS. Try in-memory, then row dataset, then server fetch as fallback.
            const osVal = (form.querySelector('[name="numero_os"]').value || '').trim();
            const previewEl = modal.querySelector('#photo-preview');
            const existing = getPhotosForOs(osVal) || [];
            if (existing.length > 0) {
                console.debug('[equipamentos] Found in-memory photos for OS', osVal, existing);
                renderPhotoPreview(previewEl, existing, osVal);
            } else {
                // If caller provided the table row element, prefer reading photo urls from it directly
                try {
                    if (rowEl) {
                        const attrProvided = rowEl.getAttribute('data-photo-urls') || rowEl.getAttribute('data-photo_urls') || rowEl.dataset.photoUrls;
                        if (attrProvided) {
                            let arrProv = null;
                            try { arrProv = JSON.parse(attrProvided); } catch(err) { arrProv = String(attrProvided).split(',').map(s=>s.trim()).filter(Boolean); }
                            if (Array.isArray(arrProv) && arrProv.length) {
                                replacePhotosForOs(osVal, arrProv);
                                renderPhotoPreview(previewEl, getPhotosForOs(osVal), osVal);
                                return;
                            }
                        }
                    }
                } catch(err) { console.warn('[equipamentos] error reading photo-urls from provided rowEl', err); }
                // try to read from table row data attribute if present
                try {
                    const eqId = data.id || '';
                    let row = null;
                    if (eqId) row = document.querySelector('tr[data-id="' + eqId + '"]');
                    if (!row) {
                        // try match by OS value
                        row = document.querySelector('tr[data-os="' + (osVal || '') + '"]');
                    }
                    if (row) {
                        const attr = row.getAttribute('data-photo-urls') || row.getAttribute('data-photo_urls') || row.dataset.photoUrls;
                        console.debug('[equipamentos] row found for edit', { eqId, osVal, row, attr });
                        if (attr) {
                            // Try JSON first, then fallback to comma-separated list of URLs
                            let arr = null;
                            try {
                                arr = JSON.parse(attr);
                            } catch (err) {
                                try {
                                    // fallback: split by comma (common if template printed URLs without JSON quoting)
                                    arr = String(attr).split(',').map(s => s.trim()).filter(Boolean);
                                } catch (err2) {
                                    arr = null;
                                }
                            }
                            console.debug('[equipamentos] parsed photo urls from row attr', arr);
                            if (Array.isArray(arr) && arr.length) {
                                replacePhotosForOs(osVal, arr);
                                renderPhotoPreview(previewEl, getPhotosForOs(osVal), osVal);
                                return;
                            }
                        }
                    } else {
                        console.debug('[equipamentos] no table row found for eqId/osVal', eqId, osVal);
                    }
                } catch (err) { /* ignore */ }
                // fallback: try fetching canonical equipamento payload which may include photo urls
                (async () => {
                    try {
                        if (data.id) {
                            console.debug('[equipamentos] fetching equipamento by id for photos', data.id);
                            const srv = await fetchEquipamentoById(data.id);
                            console.debug('[equipamentos] fetchEquipamentoById returned', srv);
                            const purls = (srv && srv.formulario && Array.isArray(srv.formulario.photo_urls)) ? srv.formulario.photo_urls : (srv && Array.isArray(srv.photo_urls) ? srv.photo_urls : []);
                            console.debug('[equipamentos] extracted photo urls from server payload', purls);
                            if (purls && purls.length) {
                                replacePhotosForOs(osVal, purls);
                                renderPhotoPreview(previewEl, getPhotosForOs(osVal), osVal);
                                return;
                            }
                        }
                    } catch (err) { console.warn('[equipamentos] error fetching equipamento photos', err); }
                    // nothing found, render empty preview
                    console.debug('[equipamentos] no photos found for', osVal);
                    renderPhotoPreview(previewEl, [], osVal);
                })();
            }
        }

        function buildReportHtml(data){
            const photos = getPhotosForOs(data['Nº OS']) || [];
            const photosSrc = photos.map(p => (p && p.src) ? p.src : p).filter(Boolean);
            const photosHtml = (photosSrc && photosSrc.length)? `<h2>Fotos</h2><div style="display:flex;flex-wrap:wrap;gap:8px">${photosSrc.map(s=>`<img src="${s}" style="max-width:260px;max-height:180px;border-radius:8px;object-fit:cover;"/>`).join('')}</div>` : '';
            return `<!doctype html><html><head><meta charset="utf-8"><title>Relatório Técnico - ${data['Nº OS']||''}</title><style>body{font-family:Arial,Helvetica,sans-serif;padding:24px}h1{font-size:20px}table{width:100%;border-collapse:collapse;margin-top:12px}td,th{padding:8px;border:1px solid #ddd}img{display:block}</style></head><body><h1>Relatório Técnico</h1><p><strong>OS:</strong> ${data['Nº OS']||''}</p><table><tbody>${Object.keys(data).map(k=>`<tr><th style="text-align:left">${k}</th><td>${data[k]}</td></tr>`).join('')}</tbody></table>${photosHtml}<p style="margin-top:20px">Gerado em ${new Date().toLocaleString()}</p></body></html>`;
        }

        document.querySelectorAll('.equipamentos-table tbody tr').forEach(updateIdentifierActionButtonForRow);

        document.querySelectorAll('.edit-btn').forEach(btn => btn.addEventListener('click', (e)=>{
            const tr = findRow(e.currentTarget);
            if(!tr) return;
            const data = getRowPayloadFromTr(tr);
            openEditModalWithData(data, tr);
        }));

        // Dedicated flow for identifier swap (outside create/edit modal)
        (function initIdentifierSwapFlow(){
            const modal = document.getElementById('identifier-swap-modal');
            const form = document.getElementById('identifier-swap-form');
            if(!modal || !form) return;

            function setField(name, value){
                const el = form.querySelector(`[name="${name}"]`);
                if(el) el.value = value == null ? '' : String(value);
            }

            function openForRow(tr){
                if(!tr) return;
                const data = getRowPayloadFromTr(tr);
                syncIdentifierSwapMode(data.descricao || '');
                setField('equipamento_id', data.id || '');
                setField('equipamento_label', `${data.descricao || 'Equipamento'}${data.modelo ? (' - ' + data.modelo) : ''}`);
                setField('tag_atual', data.tag || '');
                setField('serie_atual', data.serie || '');
                setField('tag', data.tag || '');
                setField('serie', data.serie || '');
                setField('motivo', '');
                modal.removeAttribute('hidden');
                document.body.style.overflow = 'hidden';
                const first = form.querySelector('[name="tag"]'); if(first) first.focus();
                try { modal.dataset.rowId = tr.getAttribute('data-id') || ''; } catch(err) {}
                try { modal.dataset.descricao = data.descricao || ''; } catch(err) {}
            }

            function closeModalSwap(){
                modal.setAttribute('hidden','');
                document.body.style.overflow = '';
                form.reset();
                try { delete modal.dataset.rowId; } catch(err) {}
                try { delete modal.dataset.descricao; } catch(err) {}
                syncIdentifierSwapMode('');
            }

            const closeEls = modal.querySelectorAll('[data-close], .modal-close');
            closeEls.forEach(el => el.addEventListener('click', closeModalSwap));
            const overlay = modal.querySelector('.modal-overlay');
            if(overlay) overlay.addEventListener('click', closeModalSwap);

            document.addEventListener('click', (e) => {
                const btn = e.target && e.target.closest ? e.target.closest('.identifier-swap-btn') : null;
                if(!btn) return;
                const tr = findRow(btn);
                openForRow(tr);
            });

            function getCookieLocal(name) {
                const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
                return v ? v.pop() : '';
            }

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const equipId = (form.querySelector('[name="equipamento_id"]')?.value || '').trim();
                const tag = (form.querySelector('[name="tag"]')?.value || '').trim();
                const serie = (form.querySelector('[name="serie"]')?.value || '').trim();
                const motivo = (form.querySelector('[name="motivo"]')?.value || '').trim();

                if(!equipId){
                    showToast('error', 'Equipamento não informado para troca de identificadores.');
                    return;
                }
                if(!tag && !serie){
                    const terms = getIdentifierTerms(modal.dataset.descricao || modal.dataset.mode || '');
                    showToast('error', `Informe ${terms.pair}.`);
                    return;
                }

                const fd = new FormData();
                fd.append('equipamento_id', equipId);
                fd.append('tag', tag);
                fd.append('serie', serie);
                fd.append('motivo', motivo);

                const submitBtn = form.querySelector('button[type="submit"]');
                if(submitBtn){ submitBtn.disabled = true; submitBtn.classList.add('is-loading'); }
                try {
                    const resp = await fetch('/api/equipamentos/identificadores/trocar/', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': getCookieLocal('csrftoken'),
                        },
                        body: fd,
                    });
                    let payload = null;
                    try { payload = await resp.json(); } catch(err) {}

                    if(!resp.ok || !payload || payload.success !== true){
                        const msg = (payload && payload.error) ? payload.error : 'Erro ao trocar identificadores.';
                        showToast('error', msg);
                        return;
                    }

                    const updatedIds = Array.isArray(payload.updated_equipamento_ids)
                        ? payload.updated_equipamento_ids.map((id) => String(id))
                        : [String(equipId)];

                    updatedIds.forEach((id) => {
                        const tr = document.querySelector(`tr[data-id="${id}"]`);
                        if(!tr) return;
                        tr.setAttribute('data-tag', payload.equipamento?.numero_tag || '');
                        tr.setAttribute('data-serie', payload.equipamento?.numero_serie || '');
                        const tdTag = tr.querySelector('td[data-label="Número de TAG Ambipar"]');
                        const tdSerie = tr.querySelector('td[data-label="Número de Série do Equipamento"]');
                        if(tdTag) tdTag.textContent = payload.equipamento?.numero_tag || '';
                        if(tdSerie) tdSerie.textContent = payload.equipamento?.numero_serie || '';
                        updateIdentifierActionButtonForRow(tr);
                    });

                    const terms = getIdentifierTerms(modal.dataset.descricao || modal.dataset.mode || '');
                    showToast('success', payload.message || terms.success);
                    closeModalSwap();
                } catch (err) {
                    console.error('identifier swap error', err);
                    showToast('error', 'Erro ao trocar identificadores.');
                } finally {
                    if(submitBtn){ submitBtn.disabled = false; submitBtn.classList.remove('is-loading'); }
                }
            });
        })();

        document.querySelectorAll('.report-btn').forEach(btn => btn.addEventListener('click', (e)=>{
            const tr = findRow(e.currentTarget);
            if(!tr) return;
            const data = getRowPayloadFromTr(tr);
            const html = buildReportHtml(data);
            const w = window.open('', '_blank');
            if(w){ w.document.write(html); w.document.close(); }
        }));

        // Exportar relatórios da mesma OS: intercepta clique, mostra overlay, faz fetch e baixa o PDF
        document.querySelectorAll('.export-os-btn').forEach(btn => btn.addEventListener('click', async (e) => {
            try {
                e.preventDefault(); e.stopPropagation();
                const el = e.currentTarget;
                const href = el.getAttribute('href');
                if(!href) return;
                // show global loading overlay if available
                try { const ov = document.querySelector('.loading-overlay'); if(ov) ov.classList.add('show'); } catch(err) {}
                // disable button to avoid duplicate clicks
                el.disabled = true; el.classList.add('disabled');

                const resp = await fetch(href, { method: 'GET', credentials: 'same-origin' });
                if(!resp.ok) {
                    try { const ov2 = document.querySelector('.loading-overlay'); if(ov2) ov2.classList.remove('show'); } catch(err){}
                    el.disabled = false; el.classList.remove('disabled');
                    showToast('error', 'Erro ao exportar PDF: ' + resp.statusText);
                    return;
                }
                const blob = await resp.blob();
                const url = window.URL.createObjectURL(blob);
                const filename = (resp.headers.get('Content-Disposition') || '').split('filename=')[1] || ('relatorios_export.pdf');
                const cleanName = filename.replace(/"/g,'').trim();
                const a = document.createElement('a');
                a.href = url; a.download = cleanName || ('relatorios_os.pdf');
                document.body.appendChild(a);
                a.click();
                setTimeout(()=>{ try{ window.URL.revokeObjectURL(url); a.remove(); }catch(e){} }, 1500);

                try { const ov3 = document.querySelector('.loading-overlay'); if(ov3) ov3.classList.remove('show'); } catch(err){}
                el.disabled = false; el.classList.remove('disabled');
                showToast('success', 'Exportação concluída. O download deve começar em breve.');
            } catch (err) {
                try { const ov4 = document.querySelector('.loading-overlay'); if(ov4) ov4.classList.remove('show'); } catch(e){}
                try { e.currentTarget.disabled = false; e.currentTarget.classList.remove('disabled'); } catch(e){}
                console.error('export-os error', err);
                showToast('error', 'Erro ao exportar relatórios. Veja console para detalhes.');
            }
        }));
    }

    document.addEventListener('DOMContentLoaded', () => {
        initFilterPanel();
        initOsTooltipAndModal();
        initTableActions();

        // Situacao popover editor: attach handlers to situacao buttons and provide a small popover UI
        function getCookie(name) { const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)'); return v ? v.pop() : ''; }
        function attachSituacaoHandlers(root=document){
            root.querySelectorAll('.situacao-btn').forEach(btn => {
                if (btn.__situacaoBound) return; btn.__situacaoBound = true;
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const button = e.currentTarget;
                    openSituacaoPopover(button);
                });
            });
            // history buttons
            root.querySelectorAll('.situacao-history-btn').forEach(hbtn => {
                if (hbtn.__histBound) return; hbtn.__histBound = true;
                hbtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const button = e.currentTarget;
                    openSituacaoHistoryModal(button);
                });
            });
        }

        function closeAllSituacaoPopovers(){
            document.querySelectorAll('.situacao-popover, .situacao-history-popover').forEach(p => p.parentElement && p.parentElement.removeChild(p));
            // also hide modal if open
            try{ const m = document.getElementById('situacao-history-modal'); if(m && !m.hasAttribute('hidden')) m.setAttribute('hidden',''); }catch(e){}
        }

        function openSituacaoPopover(button){
            closeAllSituacaoPopovers();
            const equipId = button.getAttribute('data-equip-id');
            const tr = button.closest && button.closest('tr');
            const current = (tr && tr.getAttribute('data-situacao')) || '';
            const pop = document.createElement('div'); pop.className = 'situacao-popover';
            pop.style.position = 'absolute'; pop.style.zIndex = 9999; pop.setAttribute('role','dialog');
            const opts = ['embarcardo','trocou_unidade','retornou_base'];
            opts.forEach(k => {
                const opt = document.createElement('button'); opt.type='button'; opt.className='situacao-option'; opt.textContent = SITUACAO_LABELS[k] || k; opt.dataset.value = k;
                if (k === current) opt.classList.add('active');
                opt.addEventListener('click', async (ev) => {
                    ev.preventDefault();
                    const val = opt.dataset.value || '';
                    const csrftoken = getCookie('csrftoken');
                    try{
                        const fd = new FormData(); fd.append('equipamento_id', equipId); fd.append('situacao', val);
                        const resp = await fetch('/api/equipamentos/save/', { method: 'POST', credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrftoken }, body: fd });
                        if (!resp.ok) {
                            let msg = 'Erro ao atualizar situação';
                            try {
                                const payload = await resp.json();
                                if (payload && payload.error) msg = payload.error;
                            } catch (err) {}
                            showToast('error', msg);
                            return;
                        }
                        const data = await resp.json();
                        if (data && data.success) {
                            // update badge class and ARIA attributes (no visible text)
                            const tr2 = button.closest && button.closest('tr');
                            if(tr2){
                                tr2.setAttribute('data-situacao', val);
                                const badge = tr2.querySelector('.situacao-badge');
                                if(badge){
                                    badge.className = 'situacao-badge situacao-'+(val||'none');
                                    try{ badge.textContent = ''; }catch(e){}
                                    try{ badge.setAttribute('aria-label', SITUACAO_LABELS[val] || ''); badge.setAttribute('title', SITUACAO_LABELS[val] || ''); }catch(e){}
                                }
                            }
                            // update history panel/modal if backend returned the array
                            if (data.situacao_history && Array.isArray(data.situacao_history)) {
                                try{ renderSituacaoHistory(data.situacao_history); }catch(e){ console.debug('situacao_history', data.situacao_history); }
                                try{ renderSituacaoHistoryModal(data.situacao_history); }catch(e){ /* ignore */ }
                            } else {
                                // if backend did not return history, try fetching latest payload and update modal if open
                                try {
                                    (async () => {
                                        try {
                                            const srv = await fetchEquipamentoById(equipId);
                                            if (srv && Array.isArray(srv.situacao_history)) {
                                                try{ renderSituacaoHistoryModal(srv.situacao_history); }catch(e){}
                                                try{ renderSituacaoHistory(srv.situacao_history); }catch(e){}
                                            }
                                        } catch (err) { /* ignore */ }
                                    })();
                                } catch (err) { /* ignore */ }
                            }
                            showToast('success','Situação atualizada.');
                            closeAllSituacaoPopovers();
                        } else {
                            showToast('error','Erro ao atualizar situação');
                        }
                    }catch(err){ console.error('situacao update error', err); showToast('error','Erro ao atualizar situação'); }
                });
                pop.appendChild(opt);
            });
            document.body.appendChild(pop);
            // position near button
            try{
                const r = button.getBoundingClientRect();
                pop.style.left = Math.round(r.left + window.pageXOffset) + 'px';
                pop.style.top = Math.round(r.bottom + window.pageYOffset + 6) + 'px';
            }catch(e){}
            // close on outside click
            setTimeout(()=>{
                const onDoc = (ev)=>{ if(!pop.contains(ev.target) && ev.target !== button){ closeAllSituacaoPopovers(); document.removeEventListener('click', onDoc); } };
                document.addEventListener('click', onDoc);
            }, 10);
        }

        // open a floating popover showing situacao history (does not collapse layout)
        // open a modal showing situacao history (full traceability with date/time)
        async function openSituacaoHistoryModal(button){
            try{
                closeAllSituacaoPopovers();
                const equipId = button.getAttribute('data-equip-id');
                const modal = document.getElementById('situacao-history-modal');
                const listContainer = document.getElementById('situacao-history-list-modal');
                if(!modal || !listContainer) return;
                // show loading
                listContainer.innerHTML = '<p class="muted">Carregando histórico...</p>';
                modal.removeAttribute('hidden'); document.body.style.overflow = 'hidden';
                // fetch history
                let hist = [];
                try{
                    if (equipId) {
                        const srv = await fetchEquipamentoById(equipId);
                        hist = (srv && Array.isArray(srv.situacao_history)) ? srv.situacao_history : [];
                    }
                }catch(err){ console.warn('fetch hist error', err); }
                renderSituacaoHistoryModal(hist);
                // wire close buttons
                const overlay = modal.querySelector('.modal-overlay'); const closeBtns = modal.querySelectorAll('[data-close], .modal-close');
                const hide = () => { try{ modal.setAttribute('hidden',''); document.body.style.overflow=''; }catch(e){} };
                if(overlay) overlay.onclick = hide; closeBtns.forEach(b=>{ b.onclick = hide; });
            }catch(err){ console.error('openSituacaoHistoryModal error', err); }
        }

        // attach initial handlers
        attachSituacaoHandlers(document);

        // wire photo input handler
        const form = document.getElementById('equip-form');
        if(form){
            const equipamentoChoice = form.querySelector('#equipamento-choice');
            const descricaoField = form.querySelector('[name="descricao"]');

            syncEquipamentoFormMode(descricaoField ? descricaoField.value : '');

            if(descricaoField){
                descricaoField.addEventListener('change', () => {
                    syncEquipamentoFormMode(descricaoField.value || '');
                });
            }

            function ensureHiddenInput(name){
                let hidden = form.querySelector(`input[name="${name}"]`);
                if(!hidden){
                    hidden = document.createElement('input');
                    hidden.type = 'hidden';
                    hidden.name = name;
                    form.appendChild(hidden);
                }
                return hidden;
            }

            function isEditMode(){
                const idHidden = form.querySelector('input[name="equipamento_id"]');
                return Boolean(idHidden && idHidden.value && idHidden.dataset && idHidden.dataset.source === 'edit');
            }

            function bindSourceEquipamento(foundId){
                if(isEditMode()) return;
                const idHidden = ensureHiddenInput('equipamento_id');
                idHidden.value = '';
                try { delete idHidden.dataset.source; } catch(err) {}
                const sourceHidden = ensureHiddenInput('source_equipamento_id');
                sourceHidden.value = String(foundId || '');
            }

            function clearLookupBindings(){
                const idHidden = form.querySelector('input[name="equipamento_id"]');
                if(idHidden && idHidden.dataset && idHidden.dataset.source === 'lookup'){
                    idHidden.value = '';
                    try { delete idHidden.dataset.source; } catch(err) {}
                }
                const sourceHidden = form.querySelector('input[name="source_equipamento_id"]');
                if(sourceHidden) sourceHidden.value = '';
            }

            async function loadEquipamentoChoices(){
                if(!equipamentoChoice) return;
                try {
                    const resp = await fetch('/api/equipamentos/choices/?limit=400', {
                        credentials: 'same-origin',
                        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }
                    });
                    if(!resp.ok) return;
                    const data = await resp.json();
                    if(!data || data.success !== true || !Array.isArray(data.items)) return;

                    const current = equipamentoChoice.value || '';
                    equipamentoChoice.innerHTML = '';

                    const first = document.createElement('option');
                    first.value = '';
                    first.textContent = getModeDatasetValue(
                        equipamentoChoice,
                        getEquipmentMode(descricaoField ? descricaoField.value : ''),
                        'placeholder'
                    ) || 'Selecione TAG - Série - Descrição...';
                    equipamentoChoice.appendChild(first);

                    data.items.forEach((item) => {
                        if(!item || !item.id) return;
                        const op = document.createElement('option');
                        op.value = String(item.id);
                        op.textContent = item.label || String(item.id);
                        equipamentoChoice.appendChild(op);
                    });

                    if(current) equipamentoChoice.value = current;
                } catch (err) {
                    console.warn('loadEquipamentoChoices error', err);
                }
            }

            function applyFoundEquipamentoToForm(found){
                if(!found || !found.id) return;
                const set = (name, val) => {
                    const el = form.querySelector(`[name="${name}"]`);
                    if(!el) return;
                    el.value = val || '';
                };

                // Equipment fields (explicit selection should override previous values).
                set('modelo', found.modelo);
                set('fabricante', found.fabricante);
                set('descricao', found.descricao);
                set('serie', found.serie);
                set('tag', found.tag);
                set('situacao', found.situacao);
                syncEquipamentoFormMode(found.descricao || '');

                // Keep operation data if already filled; only complement missing fields.
                const setIfEmpty = (name, val) => {
                    const el = form.querySelector(`[name="${name}"]`);
                    if(!el) return;
                    if((el.value || '').trim()) return;
                    el.value = val || '';
                };
                setIfEmpty('responsavel', found.responsavel || '');
                setIfEmpty('local', found.local || '');
                setIfEmpty('previsao_retorno', found.previsao_retorno || '');

                // In create flow, keep original record as source and create a new row on save.
                bindSourceEquipamento(found.id);

                // history and photos scoped to selected equipamento
                try { renderIdentifierHistory(found.identifier_history || [], found.descricao || ''); } catch (err) {}
                try { renderSituacaoHistory(found.situacao_history || []); } catch (err) {}
                try {
                    const osField = form.querySelector('[name="numero_os"]');
                    const osVal = ((osField && osField.value) || found.numero_os || '').trim();
                    const photos = Array.isArray(found.photo_urls)
                        ? found.photo_urls
                        : ((found.formulario && Array.isArray(found.formulario.photo_urls)) ? found.formulario.photo_urls : []);
                    if (osVal) {
                        replacePhotosForOs(osVal, photos);
                        const previewEl = form.querySelector('#photo-preview');
                        if (previewEl) renderPhotoPreview(previewEl, getPhotosForOs(osVal), osVal);
                    }
                } catch (err) { console.warn('erro ao renderizar fotos do seletor de equipamento', err); }
            }

            if (equipamentoChoice) {
                // Load choices lazily and also right away for convenience.
                equipamentoChoice.addEventListener('focus', () => { loadEquipamentoChoices(); });
                loadEquipamentoChoices();

                equipamentoChoice.addEventListener('change', async () => {
                    const selectedId = (equipamentoChoice.value || '').trim();
                    if(!selectedId) {
                        try {
                            clearLookupBindings();
                            renderIdentifierHistory([], descricaoField ? descricaoField.value : '');
                            renderSituacaoHistory([]);
                        } catch (err) {}
                        return;
                    }
                    try {
                        const found = await fetchEquipamentoById(selectedId);
                        if(found && found.id) {
                            applyFoundEquipamentoToForm(found);
                            showToast('info', 'Equipamento selecionado e dados preenchidos.');
                        }
                    } catch (err) {
                        console.warn('equipamento choice load error', err);
                    }
                });
            }

            // Auto preencher dados do equipamento ao informar TAG/Série já cadastrados.
            const tagInput = form.querySelector('[name="tag"]');
            const serieInput = form.querySelector('[name="serie"]');
            let autofillBusy = false;

            async function tryAutoFillByIdentifier(source){
                if(autofillBusy) return;
                // não sobrescrever quando estiver editando equipamento existente
                const idHidden = form.querySelector('input[name="equipamento_id"]');
                if(idHidden && idHidden.value && idHidden.dataset && idHidden.dataset.source === 'edit') return;

                const tagVal = (tagInput && tagInput.value) ? tagInput.value.trim() : '';
                const serieVal = (serieInput && serieInput.value) ? serieInput.value.trim() : '';
                if(!tagVal && !serieVal) return;

                autofillBusy = true;
                try{
                    const found = await fetchEquipamentoByIdentifier(tagVal, serieVal);
                    if(!found || !found.id) {
                        try {
                            clearLookupBindings();
                        } catch (err) {}
                        return;
                    }

                    const set = (name, val) => {
                        const el = form.querySelector(`[name="${name}"]`);
                        if(!el) return;
                        if((el.value || '').trim()) return; // respeita valor já digitado
                        el.value = val || '';
                    };

                    // Preenche principalmente dados do equipamento.
                    set('modelo', found.modelo);
                    set('fabricante', found.fabricante);
                    set('descricao', found.descricao);
                    set('serie', found.serie);
                    set('tag', found.tag);
                    set('situacao', found.situacao);
                    syncEquipamentoFormMode(found.descricao || descricaoField?.value || '');

                    // In create flow, use selected equipment as source for a new line.
                    bindSourceEquipamento(found.id);

                    // Keep history panels scoped to the currently selected equipment.
                    try { renderIdentifierHistory(found.identifier_history || [], found.descricao || ''); } catch (err) {}
                    try { renderSituacaoHistory(found.situacao_history || []); } catch (err) {}

                    // Load photos from matched equipamento so preview reflects the selected identifier.
                    try {
                        const osField = form.querySelector('[name="numero_os"]');
                        const osVal = ((osField && osField.value) || found.numero_os || '').trim();
                        if (osVal) {
                            replacePhotosForOs(osVal, found.photo_urls || []);
                            const previewEl = form.querySelector('#photo-preview');
                            if (previewEl) renderPhotoPreview(previewEl, getPhotosForOs(osVal), osVal);
                        }
                    } catch (err) { console.warn('erro ao renderizar fotos do lookup por identificador', err); }

                    showToast('info', 'Equipamento existente encontrado. Campos preenchidos automaticamente.');
                    if(source && source.classList) source.classList.remove('field-error');
                }catch(err){
                    console.warn('autofill by identifier failed', err);
                } finally {
                    autofillBusy = false;
                }
            }

            [tagInput, serieInput].forEach(inp => {
                if(!inp) return;
                inp.addEventListener('blur', () => { tryAutoFillByIdentifier(inp); });
                inp.addEventListener('change', () => { tryAutoFillByIdentifier(inp); });
                inp.addEventListener('input', () => {
                    inp.classList.remove('field-error');
                    inp.removeAttribute('aria-invalid');
                    inp.removeAttribute('title');
                    // changing identifier should unbind previous lookup match
                    try {
                        clearLookupBindings();
                        try { renderIdentifierHistory([], descricaoField ? descricaoField.value : ''); } catch (err) {}
                        try { renderSituacaoHistory([]); } catch (err) {}
                    } catch (err) {}
                });
            });

            const input = form.querySelector('[name="photos"]');
            const previewEl = form.querySelector('#photo-preview');
            if(input){
                // allow multiple selection
                try { input.multiple = true; } catch(e){}
                input.addEventListener('change', (e)=>{
                    const files = Array.from(e.target.files || []);
                    const osVal = (form.querySelector('[name="numero_os"]').value || '').trim();
                    if(files.length===0) return;
                    // convert File objects into dataUrls and keep name/size
                    const readers = files.map((f) => new Promise((res, rej) => {
                        const r = new FileReader();
                        r.onload = () => res({ dataUrl: r.result, name: f.name, size: f.size, file: f });
                        r.onerror = rej;
                        r.readAsDataURL(f);
                    }));
                    Promise.all(readers).then(items => {
                        setPhotosForOs(osVal, items);
                        renderPhotoPreview(previewEl, getPhotosForOs(osVal), osVal);
                        // clear input to allow re-uploading same file if needed
                        input.value = '';
                    }).catch(err => console.error('photo read error', err));
                });
                // Drag & drop support on preview element
                if(previewEl){
                    previewEl.addEventListener('dragover', ev => { ev.preventDefault(); ev.dataTransfer.dropEffect = 'copy'; previewEl.classList.add('drag-over'); });
                    previewEl.addEventListener('dragleave', ev => { previewEl.classList.remove('drag-over'); });
                    previewEl.addEventListener('drop', ev => {
                        ev.preventDefault(); previewEl.classList.remove('drag-over');
                        const dtFiles = Array.from(ev.dataTransfer.files || []);
                        if(dtFiles.length === 0) return;
                        const osVal = (form.querySelector('[name="numero_os"]').value || '').trim();
                        const readers = dtFiles.map(f => new Promise((res, rej) => {
                            const r = new FileReader();
                            r.onload = () => res({ dataUrl: r.result, name: f.name, size: f.size, file: f });
                            r.onerror = rej;
                            r.readAsDataURL(f);
                        }));
                        Promise.all(readers).then(items => { setPhotosForOs(osVal, items); renderPhotoPreview(previewEl, getPhotosForOs(osVal), osVal); }).catch(err => console.error('drop read error', err));
                    });
                }
            }
        }

        // 'Salvar e +' button: keep the modal open and clear equipamento fields for next entry
        const saveAndAddBtn = document.getElementById('save-and-add');
        if (saveAndAddBtn && form) {
            saveAndAddBtn.addEventListener('click', (e) => {
                e.preventDefault();
                try { form.dataset.keepOpen = '1'; } catch(err) { form.setAttribute('data-keep-open','1'); }
                // Prefer to activate the real submit button so browser constraint validation runs normally
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn && typeof submitBtn.click === 'function') {
                    submitBtn.click();
                } else if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            });
        }

        // ---------- Active filter badges handlers ----------
        function removeQueryParam(key){
            try{
                const url = new URL(window.location.href);
                url.searchParams.delete(key);
                url.searchParams.delete('page');
                window.location.href = url.toString();
            }catch(e){
                // fallback: rebuild querystring manually
                const params = new URLSearchParams(window.location.search);
                params.delete(key); params.delete('page');
                const base = window.location.pathname + (params.toString() ? ('?' + params.toString()) : '');
                window.location.href = base;
            }
        }

        document.querySelectorAll('.badge-clear').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault(); e.stopPropagation();
                const k = btn.getAttribute('data-key');
                const badge = btn.closest && btn.closest('.filter-badge');
                if(badge){
                    badge.classList.add('fade-out');
                    // delay slightly so animation is visible
                    setTimeout(()=>{ if(k) removeQueryParam(k); }, 240);
                } else {
                    if(k) removeQueryParam(k);
                }
            });
        });

        const clearAll = document.getElementById('clear-all-filters');
        if(clearAll){
            clearAll.addEventListener('click', (e)=>{
                e.preventDefault();
                // visual pulse
                clearAll.classList.add('btn-pulse'); clearAll.classList.add('pulse');
                // animate badges fade out
                const badges = document.querySelectorAll('.filter-badge');
                badges.forEach(b=>b.classList.add('fade-out'));
                setTimeout(()=>{
                    const url = new URL(window.location.href);
                    ['filter_cliente','filter_embarcacao','filter_numero_os','filter_data_inspecao','filter_local','filter_modelo','filter_fabricante','filter_descricao','filter_serie','filter_tag','filter_situacao'].forEach(k=>url.searchParams.delete(k));
                    url.searchParams.delete('page');
                    window.location.href = url.toString();
                }, 260);
            });
        }

        // panel 'Limpar' button behaviour: clear inputs and submit
        const panelClear = document.getElementById('filter-clear');
        if(panelClear){
            panelClear.addEventListener('click', (e)=>{
                const panelForm = document.querySelector('.filter-form');
                if(!panelForm) return;
                // pulse feedback
                panelClear.classList.add('btn-pulse'); panelClear.classList.add('pulse');
                ['filter_cliente','filter_embarcacao','filter_numero_os','filter_data_inspecao','filter_local','filter_modelo','filter_fabricante','filter_descricao','filter_serie','filter_tag','filter_situacao'].forEach(name=>{
                    const inp = panelForm.querySelector('[name="'+name+'"]'); if(inp) inp.value = '';
                });
                setTimeout(()=>{
                    try{ panelForm.submit(); }catch(err){ panelForm.dispatchEvent(new Event('submit')); }
                }, 120);
            });
        }
    });

})();
