/* rdo.compartment.js
	 Mobile-first component to select which compartiments had avanço today.
	 - Watches #sup-n-comp (numero_compartimento) and renders pills 1..N in #sup-comp-selector
	 - Allows multi-select (toggle). Selected values are synced to hidden inputs named 'compartimentos_avanco' inside the form#form-supervisor
	 - Accessible: buttons with aria-pressed and keyboard toggling (Space/Enter)
*/

(function(){
	'use strict';

	function qs(sel, ctx){ return (ctx || document).querySelector(sel); }
	function qsa(sel, ctx){ return Array.from((ctx || document).querySelectorAll(sel)); }

	var FORM_CONFIGS = [
		{
			name: 'supervisor',
			formSelector: '#form-supervisor',
			totalSelector: '#sup-n-comp',
			selectorSelector: '#sup-comp-selector',
			outputSelector: '#sup-comp-avanco-container',
			submitButtonSelector: '#btn-rdo',
			ariaLabel: 'Selector de compartimentos',
			fields: {
				dayM: ['#sup-limp', '#sup-limp-manual-novo'],
				dayF: ['#sup-limp-fina'],
				cumM: ['#sup-limp-acu', '#sup-limp-manual-acu-novo'],
				cumF: ['#sup-limp-fina-acu', '#sup-limp-fina-acu-novo']
			}
		},
		{
			name: 'editor',
			formSelector: '#form-editor',
			totalSelector: '#edit-n-comp',
			selectorSelector: '#edit-comp-selector',
			outputSelector: '#edit-comp-avanco-container',
			submitButtonSelector: '#edit-save-btn',
			ariaLabel: 'Selector de compartimentos do editor',
			fields: {
				dayM: ['#limpeza_mecanizada_diaria'],
				dayMCanonical: ['input[name="percentual_limpeza_diario"]'],
				dayF: ['#avanco_limpeza_fina'],
				dayFCanonical: ['input[name="percentual_limpeza_fina_diario"]'],
				cumM: ['#percentual_limpeza_cumulativo'],
				cumF: ['#percentual_limpeza_fina_cumulativo'],
				totalAvanco: ['#percentual_avanco'],
				totalAvancoCum: ['#percentual_avanco_cumulativo']
			}
		}
	];

	function getConfigForForm(form){
		if (!form || !form.id) return FORM_CONFIGS[0];
		for (var i = 0; i < FORM_CONFIGS.length; i++){
			var cfg = FORM_CONFIGS[i];
			if (cfg && cfg.formSelector === ('#' + form.id)) return cfg;
		}
		return FORM_CONFIGS[0];
	}

	function getFormForConfig(config){
		return config ? qs(config.formSelector) : null;
	}

	function resolveTotalInput(form, config){
		var cfg = config || getConfigForForm(form);
		return (cfg && form && qs(cfg.totalSelector, form))
			|| (cfg && qs(cfg.totalSelector))
			|| (form && qs('input[name="numero_compartimentos"]', form))
			|| (form && qs('input[name="numero_compartimento"]', form))
			|| null;
	}

	function resolveSelectorContainer(form, config, createIfMissing){
		var cfg = config || getConfigForForm(form);
		var container = (cfg && form && qs(cfg.selectorSelector, form)) || (cfg && qs(cfg.selectorSelector)) || null;
		if (container || !createIfMissing || !cfg || !form) return container;
		container = document.createElement('div');
		container.id = String(cfg.selectorSelector || '').replace(/^#/, '') || 'sup-comp-selector';
		container.className = 'sup-comp-selector';
		container.setAttribute('aria-label', cfg.ariaLabel || 'Selector de compartimentos');
		container.setAttribute('role', 'group');
		var inputN = resolveTotalInput(form, cfg);
		if (inputN && inputN.parentNode){
			if (inputN.nextSibling) inputN.parentNode.insertBefore(container, inputN.nextSibling);
			else inputN.parentNode.appendChild(container);
		} else {
			form.appendChild(container);
		}
		return container;
	}

	function resolveOutputContainer(form, config){
		var cfg = config || getConfigForForm(form);
		return (cfg && form && qs(cfg.outputSelector, form)) || (cfg && qs(cfg.outputSelector)) || null;
	}

	function getPressedPills(form, config){
		var container = resolveSelectorContainer(form, config, false);
		return container ? qsa('.sup-comp-pill[aria-pressed="true"]', container) : [];
	}

	function formatCompartmentNumber(value){
		if (value == null || !isFinite(value) || isNaN(value)) return '';
		return String(Math.round(value * 100) / 100);
	}

	function parseNumericFieldValue(raw){
		try{
			if (raw == null) return null;
			if (typeof raw === 'number') return (isFinite(raw) && !isNaN(raw)) ? raw : null;
			var text = String(raw || '').trim();
			if (!text) return null;
			var hasDot = text.indexOf('.') !== -1;
			var hasComma = text.indexOf(',') !== -1;
			if (hasDot && hasComma){
				text = text.replace(/\./g, '').replace(/,/g, '.');
			} else if (hasComma){
				text = text.replace(/,/g, '.');
			}
			text = text.replace(/[^0-9.\-]/g, '');
			if (!text) return null;
			var firstDot = text.indexOf('.');
			if (firstDot !== -1) text = text.slice(0, firstDot + 1) + text.slice(firstDot + 1).replace(/\./g, '');
			var parsed = parseFloat(text);
			return (isFinite(parsed) && !isNaN(parsed)) ? parsed : null;
		}catch(_){
			return null;
		}
	}

	function readFirstNumericFieldValue(form, selectors){
		if (!form || !selectors || !selectors.length) return null;
		for (var i = 0; i < selectors.length; i++){
			try{
				var matches = qsa(selectors[i], form);
				for (var j = 0; j < matches.length; j++){
					var parsed = parseNumericFieldValue(matches[j] ? matches[j].value : null);
					if (parsed != null) return parsed;
				}
			}catch(_){ }
		}
		return null;
	}

	function hasPreviousCompartimentos(prevMap){
		try { return !!(prevMap && Object.keys(prevMap).length); } catch(_){ return false; }
	}

	function deriveEditorCumulativeFallback(form, fields, avgDayM, avgDayF){
		try{
			if (!form || !fields) return { mecanizada: null, fina: null };
			var existingDayM = readFirstNumericFieldValue(form, (fields.dayMCanonical || []).concat(fields.dayM || []));
			var existingDayF = readFirstNumericFieldValue(form, (fields.dayFCanonical || []).concat(fields.dayF || []));
			var existingCumM = readFirstNumericFieldValue(form, fields.cumM || []);
			var existingCumF = readFirstNumericFieldValue(form, fields.cumF || []);
			var nextCumM = null;
			var nextCumF = null;
			if (existingCumM != null && existingDayM != null && avgDayM != null){
				nextCumM = Math.max(0, Math.min(100, (existingCumM - existingDayM) + avgDayM));
				nextCumM = Math.round(nextCumM * 100) / 100;
			}
			if (existingCumF != null && existingDayF != null && avgDayF != null){
				nextCumF = Math.max(0, Math.min(100, (existingCumF - existingDayF) + avgDayF));
				nextCumF = Math.round(nextCumF * 100) / 100;
			}
			return { mecanizada: nextCumM, fina: nextCumF };
		}catch(_){
			return { mecanizada: null, fina: null };
		}
	}

	function setFieldValues(form, selectors, value){
		if (!form || !selectors || !selectors.length) return;
		selectors.forEach(function(sel){
			try {
				qsa(sel, form).forEach(function(el){
					try { el.value = value; } catch(_){ }
				});
			} catch(_){ }
		});
	}

	function getCompartmentIndexFromButton(btn){
		try{
			if (!btn) return null;
			var raw = '';
			try { raw = btn.getAttribute('data-compartment') || ''; } catch(_){ raw = ''; }
			if (!raw && btn.dataset) raw = btn.dataset.compartment || '';
			if (!raw && typeof btn.value !== 'undefined') raw = btn.value || '';
			var parsed = parseInt(raw, 10);
			if (isFinite(parsed)) return parsed;
			parsed = parseInt((btn.textContent || '').trim(), 10);
			return isFinite(parsed) ? parsed : null;
		}catch(_){
			return null;
		}
	}

	function syncCompartmentAriaLabel(btn, index){
		try{
			if (!btn) return;
			var n = parseInt(index, 10);
			if (!isFinite(n)) n = getCompartmentIndexFromButton(btn);
			if (!isFinite(n)) return;
			var parts = ['Compartimento ' + n];
			var state = btn.getAttribute('data-availability-label');
			if (state) parts.push(state);
			if (btn.getAttribute('aria-pressed') === 'true') parts.push('selecionado para avanço hoje');
			btn.setAttribute('aria-label', parts.join(', '));
		}catch(_){ }
	}

	function ensureLegend(container){
		try{
			var legend = document.getElementById('sup-comp-legend');
			if (legend && legend.parentNode) legend.parentNode.removeChild(legend);
		}catch(_){ }
	}

	function createHiddenInput(name, value){
		var inp = document.createElement('input');
		inp.type = 'hidden';
		// Django handles repeated keys without []
		inp.name = name;
		inp.value = value;
		return inp;
	}

	function resolveCompartimentosJsonField(form, createIfMissing){
		try{
			if (!form || !form.querySelectorAll) return null;
			var matches = qsa('input[name="compartimentos_avanco_json"]', form);
			var canonical = null;
			matches.forEach(function(el){
				if (!canonical && el && el.getAttribute && el.getAttribute('data-hidden') === '1') canonical = el;
			});
			if (!canonical){
				matches.forEach(function(el){
					if (!canonical && el && String(el.value || '').trim() !== '') canonical = el;
				});
			}
			if (!canonical && matches.length) canonical = matches[0];
			if (!canonical && createIfMissing){
				canonical = createHiddenInput('compartimentos_avanco_json', '{}');
				try { canonical.setAttribute('data-hidden', '1'); } catch(_){ }
				form.appendChild(canonical);
			}
			if (canonical){
				try { canonical.setAttribute('data-hidden', '1'); } catch(_){ }
				matches.forEach(function(el){
					if (!el || el === canonical) return;
					try { if (el.parentNode) el.parentNode.removeChild(el); } catch(_){ }
				});
			}
			return canonical;
		}catch(_){
			return null;
		}
	}

	// Ensure the hidden JSON payload exists and stays updated with the
	// current per-compartment values (mecanizada/fina 0..100 per comp).
	function ensureHiddenJsonField(form){
		return resolveCompartimentosJsonField(form, true);
	}

	// Build a compact JSON object keyed by compartment number (as string):
	// { "1": { mecanizada: 60, fina: 10 }, "2": { mecanizada: 0, fina: 0 }, ... }
	// Missing values default to 0. Total number of compartments is read from #sup-n-comp.
	function buildCompartimentosJSON(form){
		try{
			if (!form) return;
			var totalEl = resolveTotalInput(form, getConfigForForm(form));
			var total = totalEl ? parseInt(totalEl.value, 10) : 0;
			if (!total || isNaN(total) || total < 1){
				// if nothing selected/defined, still ensure we send an empty object
				var emptyField = ensureHiddenJsonField(form);
				if (emptyField) emptyField.value = '{}';
				return;
			}
			var payload = Object.create(null);
			for (var i=1;i<=total;i++){
				var mEl = form.querySelector('input[name="compartimento_avanco_mecanizada_' + i + '"]');
				var fEl = form.querySelector('input[name="compartimento_avanco_fina_' + i + '"]');
				var m = mEl ? parseInt(mEl.value, 10) : 0;
				var f = fEl ? parseInt(fEl.value, 10) : 0;
				m = isNaN(m) ? 0 : Math.max(0, Math.min(100, m));
				f = isNaN(f) ? 0 : Math.max(0, Math.min(100, f));
				payload[String(i)] = { mecanizada: m, fina: f };
			}
			var hid = ensureHiddenJsonField(form);
			if (hid) hid.value = JSON.stringify(payload);
		}catch(_){ /* noop */ }
	}

	function getCurrentCompartimentosFromJson(form, total){
		var payload = Object.create(null);
		for (var i = 1; i <= total; i++){
			payload[i] = { mecanizada: 0, fina: 0 };
		}
		try{
			var hid = resolveCompartimentosJsonField(form, false);
			if (!hid || !hid.value) return payload;
			var parsed = JSON.parse(hid.value || '{}');
			if (!parsed || typeof parsed !== 'object') return payload;
			Object.keys(parsed).forEach(function(key){
				var idx = parseInt(key, 10);
				if (!isFinite(idx) || !payload[idx]) return;
				var item = parsed[key] || {};
				payload[idx] = {
					mecanizada: parseInt(item.mecanizada || item.m || 0, 10) || 0,
					fina: parseInt(item.fina || item.f || 0, 10) || 0
				};
			});
		}catch(_){ }
		return payload;
	}

	// Read previous per-compartment acumulados provided by the server.
	// Tries multiple fallbacks (global var, hidden input, form dataset).
	function getPreviousCompartimentos(form){
		function hasEntries(map){
			try{ return !!(map && Object.keys(map).length); }catch(_){ return false; }
		}
		function parseEntry(it){
			try{
				if (!it) return null;
				var idx = (typeof it.index !== 'undefined') ? parseInt(it.index,10) : (typeof it.i !== 'undefined' ? parseInt(it.i,10) : NaN);
				if (!isFinite(idx)) return null;
				var mecPrev = 0;
				var finaPrev = 0;
				if (it.mecanizada && typeof it.mecanizada === 'object'){
					mecPrev = parseInt(it.mecanizada.anterior || 0, 10) || 0;
				} else {
					mecPrev = parseInt(it.mecanizada || 0, 10) || 0;
				}
				if (it.fina && typeof it.fina === 'object'){
					finaPrev = parseInt(it.fina.anterior || 0, 10) || 0;
				} else {
					finaPrev = parseInt(it.fina || 0, 10) || 0;
				}
				return {
					index: idx,
					mecanizada: mecPrev,
					fina: finaPrev,
					mecanizadaRestante: parseInt(it.mecanizada_restante != null ? it.mecanizada_restante : (it.mecanizada && it.mecanizada.restante), 10),
					finaRestante: parseInt(it.fina_restante != null ? it.fina_restante : (it.fina && it.fina.restante), 10),
					mecanizadaBloqueado: !!(it.mecanizada_bloqueado || (it.mecanizada && it.mecanizada.bloqueado)),
					finaBloqueado: !!(it.fina_bloqueado || (it.fina && it.fina.bloqueado))
				};
			}catch(_){
				return null;
			}
		}
		try {
			// 1) hidden input with JSON payload (name="previous_compartimentos_json")
			if (form) {
				var hid = form.querySelector('input[name="previous_compartimentos_json"]') || document.querySelector('input[name="previous_compartimentos_json"]');
				if (hid && hid.value) {
					try {
						var parsed = JSON.parse(hid.value || '[]');
						var map2 = Object.create(null);
						parsed.forEach(function(it){
							try {
								var parsedIt = parseEntry(it);
								if (!parsedIt) return;
								map2[parsedIt.index] = parsedIt;
							} catch(_){ }
						});
						if (hasEntries(map2)) return map2;
					} catch(_){ }
				}
				// 2) form dataset (data-previous-compartimentos)
				if (form.dataset && form.dataset.previousCompartimentos) {
					try {
						var parsed2 = JSON.parse(form.dataset.previousCompartimentos);
						var map3 = Object.create(null);
						parsed2.forEach(function(it){
							try {
								var parsedIt = parseEntry(it);
								if (!parsedIt) return;
								map3[parsedIt.index] = parsedIt;
							} catch(_){ }
						});
						if (hasEntries(map3)) return map3;
					} catch(_){ }
				}
			}

			// 3) global variable injected by other scripts
			if (window.rdo_previous_compartimentos && Array.isArray(window.rdo_previous_compartimentos)) {
				var arr = window.rdo_previous_compartimentos;
				var map1 = Object.create(null);
				arr.forEach(function(it){
					try {
						var parsedIt = parseEntry(it);
						if (!parsedIt) return;
						map1[parsedIt.index] = parsedIt;
					} catch(_){ }
				});
				if (hasEntries(map1)) return map1;
			}

		} catch(e){ /* noop */ }
		return Object.create(null);
	}

	function getCurrentCompartimentos(form, total){
		var payload = Object.create(null);
		for (var i = 1; i <= total; i++){
			payload[i] = { mecanizada: 0, fina: 0 };
		}
		try{
			var hid = form && form.querySelector ? form.querySelector('input[name="compartimentos_avanco_json"]') : null;
			if (hid && hid.value){
				var parsed = JSON.parse(hid.value || '{}');
				if (parsed && typeof parsed === 'object'){
					Object.keys(parsed).forEach(function(key){
						var idx = parseInt(key, 10);
						if (!isFinite(idx) || !payload[idx]) return;
						var item = parsed[key] || {};
						payload[idx] = {
							mecanizada: parseInt(item.mecanizada || item.m || 0, 10) || 0,
							fina: parseInt(item.fina || item.f || 0, 10) || 0
						};
					});
				}
			}
		}catch(_){ }
		for (var j = 1; j <= total; j++){
			try{
				var hidM = form.querySelector('input[name="compartimento_avanco_mecanizada_' + j + '"]');
				var hidF = form.querySelector('input[name="compartimento_avanco_fina_' + j + '"]');
				if (hidM) payload[j].mecanizada = parseInt(hidM.value || 0, 10) || 0;
				if (hidF) payload[j].fina = parseInt(hidF.value || 0, 10) || 0;
			}catch(_){ }
		}
		return payload;
	}

	function renderPills(container, count, selectedSet, form, config){
		var prevMap = getPreviousCompartimentos(form);
		container.innerHTML = '';
		ensureLegend(container);
		if (!count || count < 1) return;
		for (var i=1;i<=count;i++){
			(function(n){
				var btn = document.createElement('button');
				btn.type = 'button';
				btn.className = 'sup-comp-pill';
				var prev = prevMap && prevMap[n] ? prevMap[n] : null;
				var blockedM = !!(prev && prev.mecanizadaBloqueado);
				var blockedF = !!(prev && prev.finaBloqueado);
				var blockedAll = blockedM && blockedF;
				var partialOnlyM = !blockedM && blockedF;
				var partialOnlyF = blockedM && !blockedF;
				var stateTag = '';
				var stateTitle = '';
				if (blockedAll){
					stateTitle = 'compartimento concluído';
				} else if (partialOnlyF){
					stateTag = 'Fina';
					stateTitle = 'mecanizada concluída; apenas limpeza fina disponível';
				} else if (partialOnlyM){
					stateTag = 'Mec.';
					stateTitle = 'limpeza fina concluída; apenas mecanizada/manual/robotizada disponível';
				} else {
					stateTitle = 'disponível para avanço';
				}

				btn.setAttribute('data-compartment', String(n));
				btn.setAttribute('data-availability-label', stateTitle);

				btn.setAttribute('aria-pressed', (!blockedAll && selectedSet.has(n)) ? 'true' : 'false');
				btn.setAttribute('aria-disabled', blockedAll ? 'true' : 'false');
				btn.disabled = !!blockedAll;
				btn.setAttribute('role','button');
				btn.classList.toggle('is-complete', !!blockedAll);
				btn.classList.toggle('is-partial', !blockedAll && !!stateTag);
				btn.classList.toggle('is-mecanizada-only', partialOnlyM);
				btn.classList.toggle('is-fina-only', partialOnlyF);
				btn.classList.toggle('has-state-label', !!stateTag);
				btn.title = stateTitle.charAt(0).toUpperCase() + stateTitle.slice(1) + '.';
				var num = document.createElement('span');
				num.className = 'sup-comp-pill-num';
				num.textContent = String(n);
				btn.appendChild(num);
				if (stateTag){
					var tag = document.createElement('span');
					tag.className = 'sup-comp-pill-tag';
					tag.textContent = stateTag;
					btn.appendChild(tag);
				}
				syncCompartmentAriaLabel(btn, n);
				btn.addEventListener('click', function(){ toggle(n, btn, form, config); });
				btn.addEventListener('keydown', function(ev){ if (ev.key === ' ' || ev.key === 'Enter'){ ev.preventDefault(); toggle(n, btn, form, config); } });
				container.appendChild(btn);
			})(i);
		}
	}

	function toggle(n, btn, form, config){
		if (btn.getAttribute('aria-disabled') === 'true') return;
		var pressed = btn.getAttribute('aria-pressed') === 'true';
		var newState = !pressed;
		btn.setAttribute('aria-pressed', newState ? 'true' : 'false');
		syncCompartmentAriaLabel(btn, n);
		syncHiddenInputs(form, config);
	}

	function syncHiddenInputs(form, config){
		var cfg = config || getConfigForForm(form);
		// Remove existing hidden inputs for this component
		qsa('input[name="compartimentos_avanco"]', form).forEach(function(i){ i.remove(); });
		// Collect currently pressed pills
		var pressed = getPressedPills(form, cfg);
		var selected = [];
		pressed.forEach(function(btn){
			var num = getCompartmentIndexFromButton(btn);
			if (num) selected.push(num);
			if (!num) return;
			form.appendChild(createHiddenInput('compartimentos_avanco', String(num)));
		});

		try{
			var totalEl = resolveTotalInput(form, cfg);
			var total = totalEl ? parseInt(totalEl.value, 10) : 0;
			var currentJsonMap = getCurrentCompartimentosFromJson(form, total);
			var rawJsonField = resolveCompartimentosJsonField(form, false);
			var rawJsonText = rawJsonField ? String(rawJsonField.value || '').trim() : '';
			var hasStructuredPayload = !!(rawJsonText && rawJsonText !== '{}' && rawJsonText !== 'null');
			var hasExistingSerializedInputs = !!(
				qs('input[name^="compartimento_avanco_mecanizada_"]', form)
				|| qs('input[name^="compartimento_avanco_fina_"]', form)
			);
			var hydrateFromJson = !!(
				form &&
				(
					form.getAttribute('data-compartimentos-hydrate') === '1'
					|| (!hasExistingSerializedInputs && hasStructuredPayload)
				)
			);
			for (var i = 1; i <= total; i++){
				var hidM = qs('input[name="compartimento_avanco_mecanizada_' + i + '"]', form);
				var hidF = qs('input[name="compartimento_avanco_fina_' + i + '"]', form);
				if (!hidM){
					hidM = createHiddenInput('compartimento_avanco_mecanizada_' + i, '0');
					form.appendChild(hidM);
				}
				if (!hidF){
					hidF = createHiddenInput('compartimento_avanco_fina_' + i, '0');
					form.appendChild(hidF);
				}
				if (selected.indexOf(i) === -1){
					hidM.value = '0';
					hidF.value = '0';
				} else if (hydrateFromJson){
					var snapshot = currentJsonMap[i] || { mecanizada: 0, fina: 0 };
					hidM.value = String(parseInt(snapshot.mecanizada || 0, 10) || 0);
					hidF.value = String(parseInt(snapshot.fina || 0, 10) || 0);
				}
			}
			if (hydrateFromJson) form.removeAttribute('data-compartimentos-hydrate');
		}catch(_){ }

		// Ensure percent inputs / UI are in sync with selection
		syncPercentControls(form, cfg);

		// Also keep the JSON payload in sync for backend persistence on RdoTanque
		buildCompartimentosJSON(form);
	}

	// Create or remove hidden percent inputs and render sliders for selected compartments
	// Now manages two categories per compartment: mecanizada/manual and fina
	function syncPercentControls(form, config){
		var cfg = config || getConfigForForm(form);
		var container = resolveOutputContainer(form, cfg);
		if (!container) return;

		var totalEl = resolveTotalInput(form, cfg);
		var total = totalEl ? parseInt(totalEl.value, 10) : 0;
		if (!total || total < 1){
			container.innerHTML = '';
			return;
		}

		// Gather selected compartment numbers
		var pressed = getPressedPills(form, cfg);
		var selected = pressed.map(function(b){ return getCompartmentIndexFromButton(b); }).filter(Boolean);

		for (var n = 1; n <= total; n++){
			var compartmentIndex = n;
			var hidM = 'compartimento_avanco_mecanizada_' + n;
			var hidF = 'compartimento_avanco_fina_' + n;
			var existingM = qs('input[name="' + hidM + '"]', form);
			var existingF = qs('input[name="' + hidF + '"]', form);
			// Migrate old single-key value if present
			if (!existingM){
				var legacy = qs('input[name="compartimento_avanco_' + n + '"]', form);
				var v = legacy ? legacy.value : '0';
				form.appendChild(createHiddenInput(hidM, v));
			}
			if (!existingF){
				// default 0 for fina unless legacy value intended otherwise
				form.appendChild(createHiddenInput(hidF, '0'));
			}
		}

		// Render UI sliders reflecting current values
		renderPercentControls(container, total, selected, form, cfg);
		// Also compute top-level summary values from current sliders
		computeAndSetTopLevelSummaries(form, cfg);
	}

	// Compute tank-level daily and cumulative summaries from all existing compartments.
	function computeAndSetTopLevelSummaries(form, config){
		try{
			if (!form) form = qs('#form-supervisor') || qs('#form-editor');
			if (!form) return;
			var cfg = config || getConfigForForm(form);
			var totalEl = resolveTotalInput(form, cfg);
			var total = totalEl ? parseInt(totalEl.value,10) : NaN;
			if (!total || isNaN(total) || total <= 0){
				var emptyFields = cfg && cfg.fields ? cfg.fields : {};
				Object.keys(emptyFields).forEach(function(key){
					setFieldValues(form, emptyFields[key], '');
				});
				if (cfg && cfg.name === 'editor'){
					try { if (typeof window.computeEditorPercentuais === 'function') window.computeEditorPercentuais(); } catch(_){ }
				}
				return;
			}

			var prevMap = getPreviousCompartimentos(form);
			var sumDayM = 0, sumDayF = 0, sumCumM = 0, sumCumF = 0;
			for (var i=1;i<=total;i++){
				var hidM = qs('input[name="compartimento_avanco_mecanizada_' + i + '"]', form);
				var hidF = qs('input[name="compartimento_avanco_fina_' + i + '"]', form);
				var dayM = hidM ? Number(hidM.value) : 0;
				var dayF = hidF ? Number(hidF.value) : 0;
				var prev = prevMap && prevMap[i] ? prevMap[i] : null;
				var prevM = prev ? (parseInt(prev.mecanizada || 0, 10) || 0) : 0;
				var prevF = prev ? (parseInt(prev.fina || 0, 10) || 0) : 0;
				dayM = isNaN(dayM) ? 0 : Math.max(0, Math.min(100, dayM));
				dayF = isNaN(dayF) ? 0 : Math.max(0, Math.min(100, dayF));
				prevM = Math.max(0, Math.min(100, prevM));
				prevF = Math.max(0, Math.min(100, prevF));
				sumDayM += dayM;
				sumDayF += dayF;
				sumCumM += Math.min(100, prevM + dayM);
				sumCumF += Math.min(100, prevF + dayF);
			}

			var avgDayM = Math.round((sumDayM / total) * 100) / 100;
			var avgDayF = Math.round((sumDayF / total) * 100) / 100;
			var percAcM = Math.round((sumCumM / total) * 100) / 100;
			var percAcF = Math.round((sumCumF / total) * 100) / 100;

			var fields = cfg && cfg.fields ? cfg.fields : {};
			if (cfg && cfg.name === 'editor' && !hasPreviousCompartimentos(prevMap)){
				var editorFallback = deriveEditorCumulativeFallback(form, fields, avgDayM, avgDayF);
				if (editorFallback.mecanizada != null) percAcM = editorFallback.mecanizada;
				if (editorFallback.fina != null) percAcF = editorFallback.fina;
			}
			setFieldValues(form, fields.dayM || [], formatCompartmentNumber(avgDayM));
			setFieldValues(form, fields.dayMCanonical || [], formatCompartmentNumber(avgDayM));
			setFieldValues(form, fields.dayF || [], formatCompartmentNumber(avgDayF));
			setFieldValues(form, fields.dayFCanonical || [], formatCompartmentNumber(avgDayF));
			setFieldValues(form, fields.cumM || [], formatCompartmentNumber(percAcM));
			setFieldValues(form, fields.cumF || [], formatCompartmentNumber(percAcF));

			if (cfg && cfg.name === 'editor'){
				try { if (typeof window.computeEditorPercentuais === 'function') window.computeEditorPercentuais(); } catch(_){ }
			}
		}catch(err){ console.warn('computeAndSetTopLevelSummaries error', err); }
	}

	function renderPercentControls(container, total, selectedArray, form, config){
		container.innerHTML = '';
		if (!total || total < 1) return;
		var selectedSet = new Set((selectedArray || []).map(function(v){ return parseInt(v, 10); }).filter(Boolean));

		// inject minimal CSS for baseline bars (idempotent)
		try{
			if (!document.getElementById('rdo-compartment-baseline-styles')){
				var st = document.createElement('style'); st.id = 'rdo-compartment-baseline-styles';
				st.type = 'text/css';
					st.appendChild(document.createTextNode('\n.sup-comp-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:10px;}\n.sup-comp-summary-card{min-width:0;border:1px solid #dbe4ea;border-radius:12px;padding:9px;background:linear-gradient(180deg,#ffffff 0%,#f8fbfc 100%);}\n.sup-comp-summary-card-label{display:block;font-size:10px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:#64748b;margin-bottom:3px;}\n.sup-comp-summary-card-value{display:block;font-size:17px;font-weight:800;color:#0f172a;line-height:1.1;}\n.sup-comp-summary-card-note{display:block;font-size:11px;color:#475569;margin-top:3px;}\n.sup-comp-empty{border:1px dashed #cbd5e1;border-radius:12px;padding:12px;background:#f8fafc;color:#475569;font-size:13px;line-height:1.4;}\n.sup-comp-avanco-row{border:1px solid #e5e7eb;border-radius:12px;padding:8px;margin-bottom:8px;background:#fff;}\n.sup-comp-avanco-head{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:6px;margin-bottom:8px;}\n.sup-comp-avanco-head-label{font-weight:700;}\n.sup-comp-avanco-grid{display:grid;grid-template-columns:1fr;gap:8px;}\n.sup-comp-avanco-col{min-width:0;border:1px solid #eef0f3;border-radius:10px;padding:8px;background:#fafafa;}\n.sup-comp-avanco-label-row{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;}\n.sup-comp-avanco-label{font-size:12px;font-weight:700;max-width:70%;}\n.sup-comp-avanco-state{font-size:11px;font-weight:700;border-radius:999px;padding:3px 8px;background:#eef2f7;color:#475569;white-space:nowrap;}\n.sup-comp-avanco-state.is-complete{background:#dff7e8;color:#166534;}\n.sup-comp-avanco-state.is-open{background:#fff4d6;color:#8a6100;}\n.sup-comp-avanco-state.is-ready{background:#e2f0ff;color:#1d4ed8;}\n.sup-comp-avanco-sliderwrap{position:relative;padding:2px 0 6px;}\n.sup-comp-baseline{position:absolute;left:0;bottom:4px;height:6px;background:#d7dde5;border-radius:4px;z-index:1;opacity:0.95;}\n.sup-comp-slider{position:relative;z-index:2;width:100%;margin:0;}\n.sup-comp-slider[disabled]{opacity:0.6;cursor:not-allowed;}\n.sup-comp-fill-text{position:absolute;z-index:3;left:50%;top:50%;transform:translate(-50%,-50%);font-size:12px;font-weight:700;color:#0f172a;text-shadow:none;pointer-events:none;}\n.sup-comp-meta{display:flex;flex-wrap:wrap;gap:6px;font-size:12px;color:#475569;margin-top:6px;}\n.sup-comp-meta span{background:#fff;border:1px solid #e5e7eb;border-radius:999px;padding:2px 8px;white-space:nowrap;}\n.sup-comp-status{font-size:12px;font-weight:700;border-radius:999px;padding:4px 8px;background:#eef2f7;color:#334155;}\n.sup-comp-status.is-complete{background:#dff7e8;color:#166534;}\n.sup-comp-status.is-pending{background:#eef2f7;color:#475569;}\n.sup-comp-status.is-ready{background:#e2f0ff;color:#1d4ed8;}\n.sup-comp-status.is-partial{background:#fff4d6;color:#8a6100;}\n.sup-comp-help{display:none;font-size:12px;color:#64748b;margin-top:6px;line-height:1.35;}\n.sup-comp-help.has-message{display:block;}\n@media (min-width:700px){.sup-comp-summary{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));}.sup-comp-avanco-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}\n'));
					document.head.appendChild(st);
				}
			}catch(_){ }

			// Build map of previous compartimentos values (index -> {mecanizada,fina})
			var prevMap = getPreviousCompartimentos(form || document.getElementById('form-supervisor')) || Object.create(null);
			var currentMap = getCurrentCompartimentos(form || document.getElementById('form-supervisor'), total) || Object.create(null);
			var sumDayM = 0, sumDayF = 0, sumCumM = 0, sumCumF = 0, doneM = 0, doneF = 0, doneBoth = 0;
			for (var s = 1; s <= total; s++){
				var currentSummary = currentMap[s] || { mecanizada: 0, fina: 0 };
				var prevSummary = prevMap && prevMap[s] ? prevMap[s] : null;
				var prevSummaryM = prevSummary ? (parseInt(prevSummary.mecanizada || 0, 10) || 0) : 0;
				var prevSummaryF = prevSummary ? (parseInt(prevSummary.fina || 0, 10) || 0) : 0;
				var daySummaryM = parseInt(currentSummary.mecanizada || 0, 10) || 0;
				var daySummaryF = parseInt(currentSummary.fina || 0, 10) || 0;
				var finalSummaryM = Math.min(100, Math.max(0, prevSummaryM + daySummaryM));
				var finalSummaryF = Math.min(100, Math.max(0, prevSummaryF + daySummaryF));
				sumDayM += Math.max(0, Math.min(100, daySummaryM));
				sumDayF += Math.max(0, Math.min(100, daySummaryF));
				sumCumM += finalSummaryM;
				sumCumF += finalSummaryF;
				if (finalSummaryM >= 100) doneM += 1;
				if (finalSummaryF >= 100) doneF += 1;
				if (finalSummaryM >= 100 && finalSummaryF >= 100) doneBoth += 1;
			}

			var avgSummaryDayM = Math.round((sumDayM / total) * 100) / 100;
			var avgSummaryDayF = Math.round((sumDayF / total) * 100) / 100;
			var avgSummaryCumM = Math.round((sumCumM / total) * 100) / 100;
			var avgSummaryCumF = Math.round((sumCumF / total) * 100) / 100;
			if (config && config.name === 'editor' && !hasPreviousCompartimentos(prevMap)){
				var summaryFallback = deriveEditorCumulativeFallback(form, (config && config.fields) ? config.fields : {}, avgSummaryDayM, avgSummaryDayF);
				if (summaryFallback.mecanizada != null) avgSummaryCumM = summaryFallback.mecanizada;
				if (summaryFallback.fina != null) avgSummaryCumF = summaryFallback.fina;
			}
			var summary = document.createElement('div');
			summary.className = 'sup-comp-summary';
			function appendSummaryCard(label, value, note){
				var card = document.createElement('div');
				card.className = 'sup-comp-summary-card';
				var labelEl = document.createElement('span');
				labelEl.className = 'sup-comp-summary-card-label';
				labelEl.textContent = label;
				var valueEl = document.createElement('strong');
				valueEl.className = 'sup-comp-summary-card-value';
				valueEl.textContent = value;
				card.appendChild(labelEl);
				card.appendChild(valueEl);
				if (note){
					var noteEl = document.createElement('span');
					noteEl.className = 'sup-comp-summary-card-note';
					noteEl.textContent = note;
					card.appendChild(noteEl);
				}
				summary.appendChild(card);
			}
			appendSummaryCard('Diário Mec.', (Math.round((sumDayM / total) * 100) / 100).toFixed(2) + '%', 'Tanque inteiro no dia');
			appendSummaryCard('Cumulativo Mec.', (Math.round((sumCumM / total) * 100) / 100).toFixed(2) + '%', 'Histórico do tanque');
			appendSummaryCard('Diário Fina', (Math.round((sumDayF / total) * 100) / 100).toFixed(2) + '%', 'Tanque inteiro no dia');
			appendSummaryCard('Cumulativo Fina', (Math.round((sumCumF / total) * 100) / 100).toFixed(2) + '%', 'Histórico do tanque');
			appendSummaryCard('Compartimentos', doneBoth + '/' + total, 'Concluídos em ambas as frentes');
			appendSummaryCard('Conclusão Mec./Fina', doneM + '/' + total + ' | ' + doneF + '/' + total, 'Rastreio por categoria');
			try{
				var summaryValues = summary.querySelectorAll('.sup-comp-summary-card-value');
				if (summaryValues && summaryValues.length >= 4){
					summaryValues[0].textContent = avgSummaryDayM.toFixed(2) + '%';
					summaryValues[1].textContent = avgSummaryCumM.toFixed(2) + '%';
					summaryValues[2].textContent = avgSummaryDayF.toFixed(2) + '%';
					summaryValues[3].textContent = avgSummaryCumF.toFixed(2) + '%';
				}
			}catch(_){ }
			container.appendChild(summary);
			var selectedCompartments = Array.from(selectedSet)
				.filter(function(v){ return v && v >= 1 && v <= total; })
				.sort(function(a, b){ return a - b; });
			if (!selectedCompartments.length){
				var empty = document.createElement('div');
				empty.className = 'sup-comp-empty';
				empty.textContent = 'Selecione os compartimentos acima para lançar o avanço do dia. O resumo do tanque permanece visível aqui.';
				container.appendChild(empty);
				return;
			}

			selectedCompartments.forEach(function(n){
				var compartmentIndex = n;
				var hidM = 'compartimento_avanco_mecanizada_' + n;
				var hidF = 'compartimento_avanco_fina_' + n;
				var existingM = qs('input[name="' + hidM + '"]', form);
				var existingF = qs('input[name="' + hidF + '"]', form);
				var currentRow = currentMap[n] || { mecanizada: 0, fina: 0 };
				var valM = existingM ? parseInt(existingM.value,10) || 0 : (parseInt(currentRow.mecanizada || 0, 10) || 0);
				var valF = existingF ? parseInt(existingF.value,10) || 0 : (parseInt(currentRow.fina || 0, 10) || 0);
				var prev = prevMap && prevMap[n] ? prevMap[n] : null;
				var prevM = prev ? (parseInt(prev.mecanizada || 0, 10) || 0) : 0;
				var prevF = prev ? (parseInt(prev.fina || 0, 10) || 0) : 0;
				var restM = prev ? parseInt(prev.mecanizadaRestante, 10) : NaN;
				var restF = prev ? parseInt(prev.finaRestante, 10) : NaN;
				if (!isFinite(restM)) restM = Math.max(0, 100 - prevM);
				if (!isFinite(restF)) restF = Math.max(0, 100 - prevF);
				if (valM > restM) valM = restM;
				if (valF > restF) valF = restF;
				if (existingM) existingM.value = String(valM);
				if (existingF) existingF.value = String(valF);

				var row = document.createElement('div');
				row.className = 'sup-comp-avanco-row';

				var head = document.createElement('div');
				head.className = 'sup-comp-avanco-head';
				var lbl = document.createElement('label');
				lbl.textContent = 'Compart. ' + compartmentIndex;
				lbl.className = 'sup-comp-avanco-head-label';
				head.appendChild(lbl);
				var rowStatus = document.createElement('span');
				rowStatus.className = 'sup-comp-status is-pending';
				head.appendChild(rowStatus);
				row.appendChild(head);

				var grid = document.createElement('div');
				grid.className = 'sup-comp-avanco-grid';

			// Helper to create one slider block (category, value, hidden input name)
				function makeSliderBlock(catLabel, hidName, initialVal, category){
					var block = document.createElement('div');
					block.className = 'sup-comp-avanco-col';
					var previousValue = category === 'mecanizada' ? prevM : prevF;
					var remainingBefore = category === 'mecanizada' ? restM : restF;
					var otherRemaining = category === 'mecanizada' ? restF : restM;
					var blocked = remainingBefore <= 0;
					var enabled = selectedSet.has(compartmentIndex) && !blocked;
					var initial = Math.max(0, Math.min(remainingBefore, initialVal || 0));
					var maxFinalValue = Math.max(previousValue, Math.min(100, previousValue + remainingBefore));
					var initialFinalValue = Math.max(previousValue, Math.min(maxFinalValue, previousValue + initial));

					var catHead = document.createElement('div');
					catHead.className = 'sup-comp-avanco-label-row';
					var cat = document.createElement('div'); cat.className = 'sup-comp-avanco-label'; cat.textContent = catLabel;
					var catState = document.createElement('span');
					catState.className = 'sup-comp-avanco-state';
					if (blocked){
						catState.textContent = 'Concluída';
						catState.classList.add('is-complete');
					} else if (!selectedSet.has(compartmentIndex)){
						catState.textContent = 'Selecionar';
						catState.classList.add('is-open');
					} else {
						catState.textContent = 'Disponível';
						catState.classList.add('is-ready');
					}
					catHead.appendChild(cat);
					catHead.appendChild(catState);
					var range = document.createElement('input');
					range.type = 'range'; range.min = previousValue; range.max = maxFinalValue; range.step = 1; range.value = initialFinalValue; range.className = 'sup-comp-slider';
					range.disabled = !enabled;

				// numeric label removed from side; we'll show percent text centered on the fill bar itself
				// keep a referenceable element (percentText) created on the fillOuter below

				// Ensure hidden input exists (created earlier by syncPercentControls)
				var hid = qs('input[name="' + hidName + '"]', form);
				if (!hid){ hid = createHiddenInput(hidName, String(initial)); form.appendChild(hid); }
				hid.value = String(initial);

					// Use the slider's own track as the filled area by setting its
					// background to a linear-gradient. Create a percentText overlay
					// that will be positioned on top of the slider.
					var percentText = document.createElement('span');
					percentText.className = 'sup-comp-fill-text';
					percentText.textContent = initialFinalValue + '%';

					var meta = document.createElement('div');
					meta.className = 'sup-comp-meta';
					var accumMeta = document.createElement('span');
					var maxMeta = document.createElement('span');
					meta.appendChild(accumMeta);
					meta.appendChild(maxMeta);

				var help = document.createElement('div');
				help.className = 'sup-comp-help';

					// update handlers
					range.setAttribute('aria-valuemin', String(previousValue));
					range.setAttribute('aria-valuemax', String(maxFinalValue));
					range.setAttribute('aria-valuenow', String(initialFinalValue));
					// set initial track background
					try{ range.style.background = 'linear-gradient(90deg, #37a05a ' + initialFinalValue + '%, #e9eceb ' + initialFinalValue + '%)'; }catch(e){}
					function refreshMeta(value){
						var requestedFinalValue = parseInt(value, 10) || 0;
						var finalValue = Math.max(previousValue, Math.min(maxFinalValue, requestedFinalValue));
						if (String(finalValue) !== String(value)) range.value = String(finalValue);
						var currentValue = Math.max(0, finalValue - previousValue);
						accumMeta.textContent = 'Acumulado: ' + finalValue + '%';
						maxMeta.textContent = 'Máx. hoje: ' + remainingBefore + '%';
						if (blocked){
							if (otherRemaining <= 0) {
								help.textContent = 'Compartimento concluído.';
							} else if (category === 'mecanizada') {
								help.textContent = 'Mecanizada concluída. Apenas limpeza fina pode receber avanço.';
							} else {
								help.textContent = 'Limpeza fina concluída. Apenas mecanizada/manual/robotizada pode receber avanço.';
							}
						} else if (!selectedSet.has(compartmentIndex)){
							if (otherRemaining <= 0) {
								help.textContent = 'Selecione o compartimento para lançar avanço apenas nesta frente.';
							} else {
								help.textContent = 'Selecione o compartimento acima para lançar avanço hoje.';
							}
						} else {
							help.textContent = otherRemaining <= 0 ? 'A outra frente já está concluída.' : '';
						}
						help.classList.toggle('has-message', !!help.textContent);
						percentText.textContent = finalValue + '%';
						hid.value = String(currentValue);
						range.setAttribute('aria-valuenow', String(finalValue));
						range.setAttribute('aria-valuetext', finalValue + '% acumulado, ' + currentValue + '% hoje');
						try{ range.style.background = 'linear-gradient(90deg, #37a05a ' + finalValue + '%, #e9eceb ' + finalValue + '%)'; }catch(_){ }
				}
				range.addEventListener('input', function(){
					refreshMeta(String(range.value));
					// update aggregate top-level summary fields
					computeAndSetTopLevelSummaries(form, config);
				});

				var wrap = document.createElement('div'); wrap.className = 'sup-comp-avanco-sliderwrap';
				wrap.appendChild(range);
				// append percent overlay directly on top of the slider
				wrap.appendChild(percentText);

					block.appendChild(catHead);
					block.appendChild(wrap);
					block.appendChild(meta);
					block.appendChild(help);
				refreshMeta(initialFinalValue);
				return block;
			}

				grid.appendChild(makeSliderBlock('Mecanizada / Manual / Robotizada', hidM, valM, 'mecanizada'));
				grid.appendChild(makeSliderBlock('Limpeza Fina', hidF, valF, 'fina'));

				row.appendChild(grid);
				var rowComplete = ((prevM + valM) >= 100) && ((prevF + valF) >= 100);
				var rowMComplete = ((prevM + valM) >= 100);
				var rowFComplete = ((prevF + valF) >= 100);
				var rowSelected = selectedSet.has(compartmentIndex);
				if (rowComplete){
					rowStatus.textContent = 'Compartimento concluído';
					rowStatus.className = 'sup-comp-status is-complete';
				} else if (rowMComplete){
					rowStatus.textContent = rowSelected ? 'Mecanizada concluída; avance só fina' : 'Mecanizada concluída; falta fina';
					rowStatus.className = 'sup-comp-status is-partial';
				} else if (rowFComplete){
					rowStatus.textContent = rowSelected ? 'Fina concluída; avance só mecanizada' : 'Fina concluída; falta mecanizada';
					rowStatus.className = 'sup-comp-status is-partial';
				} else {
					rowStatus.textContent = rowSelected ? 'Lançamento ativo' : 'Sem lançamento hoje';
					rowStatus.className = 'sup-comp-status ' + (rowSelected ? 'is-ready' : 'is-pending');
				}
				container.appendChild(row);
			});
		}

	function applyContainerLayout(container, max){
		var isDesktop = window.matchMedia && window.matchMedia('(min-width: 900px)').matches;
		if (isDesktop){
			if (max <= 30){
				container.classList.add('mode-wrap');
				container.classList.remove('mode-scroll');
				container.classList.remove('mode-mobile-grid');
				container.style.display = 'flex';
				container.style.flexWrap = 'wrap';
				container.style.maxHeight = 'none';
				container.style.overflow = 'visible';
				container.style.overflowY = 'visible';
				container.style.overflowX = 'visible';
				container.style.gridTemplateColumns = '';
			} else {
				container.classList.add('mode-scroll');
				container.classList.remove('mode-wrap');
				container.classList.remove('mode-mobile-grid');
				container.style.display = 'flex';
				container.style.flexWrap = 'wrap';
				container.style.maxHeight = '160px';
				container.style.overflowY = 'auto';
				container.style.overflowX = 'hidden';
				container.style.gridTemplateColumns = '';
			}
		} else {
			container.classList.remove('mode-wrap');
			container.classList.remove('mode-scroll');
			container.classList.add('mode-mobile-grid');
			container.style.display = 'grid';
			container.style.gridTemplateColumns = 'repeat(auto-fit, minmax(56px, 1fr))';
			container.style.flexWrap = '';
			container.style.maxHeight = 'none';
			container.style.overflow = 'visible';
			container.style.overflowX = 'visible';
			container.style.overflowY = 'visible';
		}
	}

	function bindCompartimentosForm(config){
		var form = getFormForConfig(config);
		if (!form) return;
		var inputN = resolveTotalInput(form, config);
		if (!inputN) return;
		var container = resolveSelectorContainer(form, config, true);
		if (!container) return;

		var boundState = form.__rdoCompartimentosBound || null;
		if (boundState && boundState.input === inputN && boundState.container === container && boundState.configName === config.name){
			try { if (typeof boundState.rebuild === 'function') boundState.rebuild(); } catch(_){ }
			return;
		}
		if (boundState && boundState.observer){
			try { boundState.observer.disconnect(); } catch(_){ }
		}

		if (!container.classList.contains('sup-comp-selector')){
			container.classList.add('sup-comp-selector');
		}

		try {
			container.style.webkitOverflowScrolling = 'touch';
			container.setAttribute('aria-label', container.getAttribute('aria-label') || config.ariaLabel || 'Selector de compartimentos');
			if (!container.hasAttribute('tabindex')) container.tabIndex = 0;
			if (!container.__rdoCompartimentosKeyNavBound){
				container.addEventListener('keydown', function(ev){
					if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft'){
						var pills = Array.from(container.querySelectorAll('.sup-comp-pill'));
						if (!pills.length) return;
						var active = document.activeElement;
						var idx = pills.indexOf(active);
						if (idx === -1){
							var target = (ev.key === 'ArrowRight') ? pills[0] : pills[pills.length-1];
							if (target) target.focus();
							ev.preventDefault();
							return;
						}
						var nextIdx = idx + (ev.key === 'ArrowRight' ? 1 : -1);
						if (nextIdx < 0) nextIdx = 0;
						if (nextIdx >= pills.length) nextIdx = pills.length - 1;
						pills[nextIdx].focus();
						try { pills[nextIdx].scrollIntoView({behavior:'smooth', inline:'center'}); } catch(_){ pills[nextIdx].scrollIntoView(); }
						ev.preventDefault();
					}
				});
				container.__rdoCompartimentosKeyNavBound = true;
			}
		} catch(_){ }

		function rebuild(){
			var v = parseInt(inputN.value, 10);
			if (!v || v < 1) {
				container.innerHTML = '';
				syncHiddenInputs(form, config);
				return;
			}
			var max = Math.max(1, v);
			var currentMap = getCurrentCompartimentos(form, max);
			var existing = getPressedPills(form, config).map(function(btn){ return getCompartmentIndexFromButton(btn); });
			var fromCurrent = [];
			for (var i = 1; i <= max; i++){
				var current = currentMap && currentMap[i] ? currentMap[i] : null;
				if (!current) continue;
				if ((parseInt(current.mecanizada || 0, 10) || 0) > 0 || (parseInt(current.fina || 0, 10) || 0) > 0){
					fromCurrent.push(i);
				}
			}
			var selectedSet = new Set(existing.concat(fromCurrent).filter(function(x){ return x && x <= max; }));
			renderPills(container, max, selectedSet, form, config);
			applyContainerLayout(container, max);
			syncHiddenInputs(form, config);
		}

		inputN.addEventListener('input', function(){ rebuild(); });
		inputN.addEventListener('change', function(){ rebuild(); });

		var mo = new MutationObserver(function(){ rebuild(); });
		mo.observe(inputN, {attributes:true, attributeFilter:['value']});

		if (!form.__rdoCompartimentosResetBound){
			form.addEventListener('reset', function(){
				setTimeout(function(){
					var cfg = getConfigForForm(form);
					var currentContainer = resolveSelectorContainer(form, cfg, false);
					if (currentContainer) currentContainer.innerHTML = '';
					syncHiddenInputs(form, cfg);
				}, 10);
			});
			form.__rdoCompartimentosResetBound = true;
		}
		if (!form.__rdoCompartimentosSubmitBound){
			form.addEventListener('submit', function(){
				computeAndSetTopLevelSummaries(form, getConfigForForm(form));
				buildCompartimentosJSON(form);
			});
			form.__rdoCompartimentosSubmitBound = true;
		}
		var submitBtn = qs(config.submitButtonSelector);
		if (submitBtn && !submitBtn.__rdoCompartimentosBound){
			submitBtn.addEventListener('click', function(){
				computeAndSetTopLevelSummaries(form, getConfigForForm(form));
				buildCompartimentosJSON(form);
			});
			submitBtn.__rdoCompartimentosBound = true;
		}

		form.__rdoCompartimentosBound = {
			configName: config.name,
			input: inputN,
			container: container,
			rebuild: rebuild,
			observer: mo
		};

		setTimeout(rebuild, 40);
	}

	function init(){
		FORM_CONFIGS.forEach(function(config){
			try { bindCompartimentosForm(config); } catch(_){ }
		});
	}

	try {
		window.computeAndSetTopLevelSummaries = function(form){
			var targetForm = form || qs('#form-supervisor') || qs('#form-editor');
			if (!targetForm) return;
			computeAndSetTopLevelSummaries(targetForm, getConfigForForm(targetForm));
			buildCompartimentosJSON(targetForm);
		};
		window.buildCompartimentosJSON = buildCompartimentosJSON;
		window.initRdoCompartimentos = init;
	} catch(_){ }

	document.addEventListener('rdo:compartimentos:refresh', function(){ setTimeout(init, 20); });

	// run on DOM ready
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

})();
