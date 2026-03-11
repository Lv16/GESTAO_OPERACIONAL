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
			if (!container || !container.parentNode) return;
			var legend = document.getElementById('sup-comp-legend');
			if (!legend){
				legend = document.createElement('div');
				legend.id = 'sup-comp-legend';
				legend.className = 'sup-comp-legend';
				container.parentNode.insertBefore(legend, container.nextSibling);
			}
			legend.innerHTML = '<strong>Legenda:</strong> F = somente limpeza fina disponível | M = somente mecanizada disponível | OK = compartimento concluído';
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

	// Ensure the hidden JSON payload exists and stays updated with the
	// current per-compartment values (mecanizada/fina 0..100 per comp).
	function ensureHiddenJsonField(form){
		var hid = form.querySelector('input[name="compartimentos_avanco_json"]');
		if (!hid){
			hid = createHiddenInput('compartimentos_avanco_json', '{}');
			form.appendChild(hid);
		}
		return hid;
	}

	// Build a compact JSON object keyed by compartment number (as string):
	// { "1": { mecanizada: 60, fina: 10 }, "2": { mecanizada: 0, fina: 0 }, ... }
	// Missing values default to 0. Total number of compartments is read from #sup-n-comp.
	function buildCompartimentosJSON(form){
		try{
			if (!form) return;
			var totalEl = form.querySelector('#sup-n-comp') || form.querySelector('input[name="numero_compartimentos"]');
			var total = totalEl ? parseInt(totalEl.value, 10) : 0;
			if (!total || isNaN(total) || total < 1){
				// if nothing selected/defined, still ensure we send an empty object
				ensureHiddenJsonField(form).value = '{}';
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
			ensureHiddenJsonField(form).value = JSON.stringify(payload);
		}catch(_){ /* noop */ }
	}

	// Read previous per-compartment acumulados provided by the server.
	// Tries multiple fallbacks (global var, hidden input, form dataset).
	function getPreviousCompartimentos(form){
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
			// 1) global variable injected by other scripts (preferred)
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
				return map1;
			}

			// 2) hidden input with JSON payload (name="previous_compartimentos_json")
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
						return map2;
					} catch(_){ }
				}
				// 3) form dataset (data-previous-compartimentos)
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
						return map3;
					} catch(_){ }
				}
			}

			// 4) fallback: try a hidden field that may contain the current RDO's compartimentos_avanco_json
			var cur = document.querySelector('input[name="compartimentos_avanco_json"]');
			if (cur && cur.value) {
				try {
					var parsed3 = JSON.parse(cur.value || '{}');
					// parsed3 may be an object keyed by index or an array
					var map4 = Object.create(null);
					if (Array.isArray(parsed3)) {
						parsed3.forEach(function(it){
							try {
								var parsedIt = parseEntry(it);
								if (!parsedIt) return;
								map4[parsedIt.index] = parsedIt;
							}catch(_){ }
						});
					} else {
						Object.keys(parsed3).forEach(function(k){
							try {
								var idx = parseInt(k,10);
								if (!isFinite(idx)) return;
								var v = parsed3[k] || {};
								map4[idx] = {
									index: idx,
									mecanizada: parseInt(v.mecanizada||v.m||0,10)||0,
									fina: parseInt(v.fina||v.f||0,10)||0,
									mecanizadaRestante: parseInt(v.mecanizada_restante != null ? v.mecanizada_restante : (100 - (parseInt(v.mecanizada||v.m||0,10)||0)), 10),
									finaRestante: parseInt(v.fina_restante != null ? v.fina_restante : (100 - (parseInt(v.fina||v.f||0,10)||0)), 10),
									mecanizadaBloqueado: !!v.mecanizada_bloqueado,
									finaBloqueado: !!v.fina_bloqueado
								};
							} catch(_){ }
						});
					}
					return map4;
				} catch(_){ }
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

	function renderPills(container, count, selectedSet, form){
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
					stateTag = 'OK';
					stateTitle = 'compartimento concluído';
				} else if (partialOnlyF){
					stateTag = 'F';
					stateTitle = 'mecanizada concluída; apenas limpeza fina disponível';
				} else if (partialOnlyM){
					stateTag = 'M';
					stateTitle = 'limpeza fina concluída; apenas mecanizada/manual/robotizada disponível';
				} else {
					stateTitle = 'disponível para avanço';
				}

				// Ensure pills behave as non-wrapping flex items so they scroll horizontally
				btn.style.display = 'inline-flex';
				btn.style.flex = '0 0 auto';
				btn.style.marginRight = '6px';
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
				btn.addEventListener('click', function(){ toggle(n, btn, form); });
				btn.addEventListener('keydown', function(ev){ if (ev.key === ' ' || ev.key === 'Enter'){ ev.preventDefault(); toggle(n, btn, form); } });
				container.appendChild(btn);
			})(i);
		}
	}

	function toggle(n, btn, form){
		if (btn.getAttribute('aria-disabled') === 'true') return;
		var pressed = btn.getAttribute('aria-pressed') === 'true';
		var newState = !pressed;
		btn.setAttribute('aria-pressed', newState ? 'true' : 'false');
		syncCompartmentAriaLabel(btn, n);
		syncHiddenInputs(form);
	}

	function syncHiddenInputs(form){
		// Remove existing hidden inputs for this component
		qsa('input[name="compartimentos_avanco"]', form).forEach(function(i){ i.remove(); });
		// Collect currently pressed pills
		var pressed = qsa('#sup-comp-selector .sup-comp-pill[aria-pressed="true"]');
		var selected = [];
		pressed.forEach(function(btn){
			var num = getCompartmentIndexFromButton(btn);
			if (num) selected.push(num);
			if (!num) return;
			form.appendChild(createHiddenInput('compartimentos_avanco', String(num)));
		});

		try{
			var totalEl = form.querySelector('#sup-n-comp') || form.querySelector('input[name="numero_compartimentos"]');
			var total = totalEl ? parseInt(totalEl.value, 10) : 0;
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
				}
			}
		}catch(_){ }

		// Ensure percent inputs / UI are in sync with selection
		syncPercentControls(form);

		// Also keep the JSON payload in sync for backend persistence on RdoTanque
		buildCompartimentosJSON(form);
	}

	// Create or remove hidden percent inputs and render sliders for selected compartments
	// Now manages two categories per compartment: mecanizada/manual and fina
	function syncPercentControls(form){
		var container = qs('#sup-comp-avanco-container');
		if (!container) return;

		var totalEl = form.querySelector('#sup-n-comp') || form.querySelector('input[name="numero_compartimentos"]');
		var total = totalEl ? parseInt(totalEl.value, 10) : 0;
		if (!total || total < 1){
			container.innerHTML = '';
			return;
		}

		// Gather selected compartment numbers
		var pressed = qsa('#sup-comp-selector .sup-comp-pill[aria-pressed="true"]');
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
		renderPercentControls(container, total, selected, form);
		// Also compute top-level summary values from current sliders
		if (typeof computeAndSetTopLevelSummaries === 'function') computeAndSetTopLevelSummaries(form);
	}

	// Compute tank-level daily and cumulative summaries from all existing compartments.
	function computeAndSetTopLevelSummaries(form){
		try{
			if (!form) form = qs('#form-supervisor');
			var totalEl = qs('#sup-n-comp') || qs('input[name="numero_compartimentos"]');
			var total = totalEl ? parseInt(totalEl.value,10) : NaN;
			if (!total || isNaN(total) || total <= 0){
				var supL0 = qs('#sup-limp'); if (supL0) supL0.value = '';
				var supF0 = qs('#sup-limp-fina'); if (supF0) supF0.value = '';
				var acM = qs('#sup-limp-acu'); if (acM) acM.value = '';
				var acF = qs('#sup-limp-fina-acu'); if (acF) acF.value = '';
				var supLNovo0 = qs('#sup-limp-manual-novo'); if (supLNovo0) supLNovo0.value = '';
				var acMNovo = qs('#sup-limp-manual-acu-novo'); if (acMNovo) acMNovo.value = '';
				var acFNovo = qs('#sup-limp-fina-acu-novo'); if (acFNovo) acFNovo.value = '';
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

			var supM = qs('#sup-limp'); if (supM) supM.value = String(avgDayM);
			var supF = qs('#sup-limp-fina'); if (supF) supF.value = String(avgDayF);
			var supLNovo = qs('#sup-limp-manual-novo'); if (supLNovo) supLNovo.value = String(avgDayM);
			var acMEl = qs('#sup-limp-acu'); if (acMEl) acMEl.value = (percAcM || percAcM === 0) ? String(percAcM) : '';
			var acFEl = qs('#sup-limp-fina-acu'); if (acFEl) acFEl.value = (percAcF || percAcF === 0) ? String(percAcF) : '';
			var acMElNovo = qs('#sup-limp-manual-acu-novo'); if (acMElNovo) acMElNovo.value = (percAcM || percAcM === 0) ? String(percAcM) : '';
			var acFElNovo = qs('#sup-limp-fina-acu-novo'); if (acFElNovo) acFElNovo.value = (percAcF || percAcF === 0) ? String(percAcF) : '';

		}catch(err){ console.warn('computeAndSetTopLevelSummaries error', err); }
	}

	function renderPercentControls(container, total, selectedArray, form){
		container.innerHTML = '';
		if (!total || total < 1) return;
		var selectedSet = new Set((selectedArray || []).map(function(v){ return parseInt(v, 10); }).filter(Boolean));

		// inject minimal CSS for baseline bars (idempotent)
		try{
			if (!document.getElementById('rdo-compartment-baseline-styles')){
				var st = document.createElement('style'); st.id = 'rdo-compartment-baseline-styles';
				st.type = 'text/css';
					st.appendChild(document.createTextNode('\n.sup-comp-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:12px;}\n.sup-comp-summary-card{min-width:0;border:1px solid #dbe4ea;border-radius:12px;padding:10px;background:linear-gradient(180deg,#ffffff 0%,#f8fbfc 100%);}\n.sup-comp-summary-card-label{display:block;font-size:10px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:#64748b;margin-bottom:4px;}\n.sup-comp-summary-card-value{display:block;font-size:18px;font-weight:800;color:#0f172a;line-height:1.1;}\n.sup-comp-summary-card-note{display:block;font-size:11px;color:#475569;margin-top:4px;}\n.sup-comp-empty{border:1px dashed #cbd5e1;border-radius:12px;padding:14px;background:#f8fafc;color:#475569;font-size:13px;line-height:1.45;}\n.sup-comp-avanco-row{border:1px solid #e5e7eb;border-radius:12px;padding:10px;margin-bottom:10px;background:#fff;}\n.sup-comp-avanco-head{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:10px;}\n.sup-comp-avanco-head-label{font-weight:700;}\n.sup-comp-avanco-grid{display:grid;grid-template-columns:1fr;gap:10px;}\n.sup-comp-avanco-col{min-width:0;border:1px solid #eef0f3;border-radius:10px;padding:10px;background:#fafafa;}\n.sup-comp-avanco-label-row{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:8px;}\n.sup-comp-avanco-label{font-size:12px;font-weight:700;max-width:70%;}\n.sup-comp-avanco-state{font-size:11px;font-weight:700;border-radius:999px;padding:3px 8px;background:#eef2f7;color:#475569;white-space:nowrap;}\n.sup-comp-avanco-state.is-complete{background:#dff7e8;color:#166534;}\n.sup-comp-avanco-state.is-open{background:#fff4d6;color:#8a6100;}\n.sup-comp-avanco-state.is-ready{background:#e2f0ff;color:#1d4ed8;}\n.sup-comp-avanco-sliderwrap{position:relative;padding:4px 0 14px;}\n.sup-comp-baseline{position:absolute;left:0;bottom:4px;height:6px;background:#d7dde5;border-radius:4px;z-index:1;opacity:0.95;}\n.sup-comp-slider{position:relative;z-index:2;width:100%;}\n.sup-comp-slider[disabled]{opacity:0.6;cursor:not-allowed;}\n.sup-comp-fill-text{position:absolute;z-index:3;left:50%;top:50%;transform:translate(-50%,-50%);font-size:12px;font-weight:700;}\n.sup-comp-fill-text--on-dark{color:#fff;}\n.sup-comp-meta{display:flex;flex-wrap:wrap;gap:8px;font-size:12px;color:#475569;margin-top:8px;}\n.sup-comp-meta span{background:#fff;border:1px solid #e5e7eb;border-radius:999px;padding:2px 8px;white-space:nowrap;}\n.sup-comp-status{font-size:12px;font-weight:700;border-radius:999px;padding:4px 8px;background:#eef2f7;color:#334155;}\n.sup-comp-status.is-complete{background:#dff7e8;color:#166534;}\n.sup-comp-status.is-pending{background:#eef2f7;color:#475569;}\n.sup-comp-status.is-ready{background:#e2f0ff;color:#1d4ed8;}\n.sup-comp-status.is-partial{background:#fff4d6;color:#8a6100;}\n.sup-comp-help{font-size:12px;color:#64748b;margin-top:8px;}\n@media (min-width:700px){.sup-comp-summary{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));}.sup-comp-avanco-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}\n'));
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
					var initialFinalValue = Math.max(previousValue, Math.min(100, previousValue + initial));

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
					range.type = 'range'; range.min = 0; range.max = 100; range.step = 1; range.value = initialFinalValue; range.className = 'sup-comp-slider';
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
					var prevMeta = document.createElement('span');
					var todayMeta = document.createElement('span');
					var finalMeta = document.createElement('span');
					var remMeta = document.createElement('span');
					meta.appendChild(prevMeta);
					meta.appendChild(todayMeta);
					meta.appendChild(finalMeta);
					meta.appendChild(remMeta);

				var help = document.createElement('div');
				help.className = 'sup-comp-help';

					// update handlers
					range.setAttribute('aria-valuemin', String(previousValue));
					range.setAttribute('aria-valuemax', '100');
					range.setAttribute('aria-valuenow', String(initialFinalValue));
					// set initial track background
					try{ range.style.background = 'linear-gradient(90deg, #37a05a ' + initialFinalValue + '%, #e9eceb ' + initialFinalValue + '%)'; }catch(e){}
					function refreshMeta(value){
						var requestedFinalValue = parseInt(value, 10) || 0;
						var finalValue = Math.max(previousValue, Math.min(100, requestedFinalValue));
						if (String(finalValue) !== String(value)) range.value = String(finalValue);
						var currentValue = Math.max(0, finalValue - previousValue);
						prevMeta.textContent = 'Anterior: ' + previousValue + '%';
						todayMeta.textContent = 'Hoje: ' + currentValue + '%';
						finalMeta.textContent = 'Depois: ' + finalValue + '%';
						remMeta.textContent = 'Saldo: ' + Math.max(0, 100 - finalValue) + '%';
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
							if (otherRemaining <= 0) {
								help.textContent = 'A outra frente já está concluída. Máximo disponível hoje: ' + remainingBefore + '%.';
							} else {
								help.textContent = 'Máximo disponível hoje: ' + remainingBefore + '%.';
							}
						}
						percentText.textContent = finalValue + '%';
						hid.value = String(currentValue);
						range.setAttribute('aria-valuenow', String(finalValue));
						range.setAttribute('aria-valuetext', finalValue + '% acumulado, ' + currentValue + '% hoje');
						try{ range.style.background = 'linear-gradient(90deg, #37a05a ' + finalValue + '%, #e9eceb ' + finalValue + '%)'; }catch(_){ }
						if (finalValue >= 40) percentText.classList.add('sup-comp-fill-text--on-dark');
						else percentText.classList.remove('sup-comp-fill-text--on-dark');
				}
				range.addEventListener('input', function(){
					refreshMeta(String(range.value));
					// update aggregate top-level summary fields
					computeAndSetTopLevelSummaries(form);
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

	function init(){
		var inputN = qs('#sup-n-comp');
		// prefer id, but accept existing class-based container
		var container = qs('#sup-comp-selector') || qs('.sup-comp-selector');
		var form = qs('#form-supervisor');
		if (!inputN || !form) return;

		// If no container found in the DOM, create one and insert it after the
		// number input so it appears next to the related control in the template.
		if (!container){
			container = document.createElement('div');
			container.id = 'sup-comp-selector';
			container.className = 'sup-comp-selector';
			if (inputN.parentNode){
				if (inputN.nextSibling) inputN.parentNode.insertBefore(container, inputN.nextSibling);
				else inputN.parentNode.appendChild(container);
			} else {
				document.body.appendChild(container);
			}
		}

		// Ensure the expected class is present so the CSS rules apply
		if (!container.classList.contains('sup-comp-selector')){
			container.classList.add('sup-comp-selector');
		}

		// Make the container a horizontally scrollable flex row so pills do not wrap and
		// instead allow horizontal scrolling on small screens. Also improve touch behavior.
		try {
			container.style.display = 'flex';
			container.style.flexWrap = 'nowrap';
			container.style.overflowX = 'auto';
			container.style.webkitOverflowScrolling = 'touch';
			container.style.alignItems = 'center';
			// accessibility: allow keyboard focus on container for arrow navigation
			container.setAttribute('aria-label', container.getAttribute('aria-label') || 'Selector de compartimentos');
			if (!container.hasAttribute('tabindex')) container.tabIndex = 0;

			// Keyboard navigation: left/right arrows move focus between pills and keep them visible
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
					// keep the focused pill visible in the horizontal viewport
					try { pills[nextIdx].scrollIntoView({behavior:'smooth', inline:'center'}); } catch(_){ pills[nextIdx].scrollIntoView(); }
					ev.preventDefault();
				}
			});
		} catch(_){ /* styling best-effort - noop if any error */ }

		function rebuild(){
			var v = parseInt(inputN.value, 10);
			if (!v || v < 1) { container.innerHTML = ''; syncHiddenInputs(form); return; }
			var max = Math.max(1, v); // permitir qualquer quantidade (ex.: 100)
			var currentMap = getCurrentCompartimentos(form, max);
			// manter seleção existente dentro do novo intervalo
				var existing = qsa('#sup-comp-selector .sup-comp-pill[aria-pressed="true"]').map(function(b){ return getCompartmentIndexFromButton(b); });
			var fromCurrent = [];
			for (var i = 1; i <= max; i++){
				var current = currentMap && currentMap[i] ? currentMap[i] : null;
				if (!current) continue;
				if ((parseInt(current.mecanizada || 0, 10) || 0) > 0 || (parseInt(current.fina || 0, 10) || 0) > 0){
					fromCurrent.push(i);
				}
			}
			var selectedSet = new Set(existing.concat(fromCurrent).filter(function(x){ return x && x <= max; }));
			renderPills(container, max, selectedSet, form);

			// Modo layout: até 30 => wrap total visível; acima de 30 => mini-scroll vertical com wrap controlado
			var isDesktop = window.matchMedia && window.matchMedia('(min-width: 900px)').matches;
			if (isDesktop){
				if (max <= 30){
					container.classList.add('mode-wrap');
					container.classList.remove('mode-scroll');
					container.style.flexWrap = 'wrap';
					container.style.maxHeight = 'none';
					container.style.overflow = 'visible';
					container.style.overflowY = 'visible';
					container.style.overflowX = 'visible';
				} else {
					container.classList.add('mode-scroll');
					container.classList.remove('mode-wrap');
					container.style.flexWrap = 'wrap'; // permitir múltiplas linhas
					container.style.maxHeight = '160px'; // altura compacta com scroll
					container.style.overflowY = 'auto';
					container.style.overflowX = 'hidden';
				}
			} else {
				// Mobile mantém comportamento horizontal rolável
				container.classList.remove('mode-wrap');
				container.classList.add('mode-scroll');
				container.style.flexWrap = 'nowrap';
				container.style.maxHeight = 'none';
				container.style.overflowX = 'auto';
				container.style.overflowY = 'hidden';
			}

			syncHiddenInputs(form);
		}

		// Rebuild when number changes (input event and change). Also when modal opened (some apps prefill).
		inputN.addEventListener('input', function(){ rebuild(); });
		inputN.addEventListener('change', function(){ rebuild(); });

		// If modal may be populated via JS, observe changes to the value attribute as fallback
		var mo = new MutationObserver(function(){ rebuild(); });
		mo.observe(inputN, {attributes:true, attributeFilter:['value']});

		// If form resets or is cleared, ensure sync
		form.addEventListener('reset', function(){ setTimeout(function(){ container.innerHTML=''; syncHiddenInputs(form); }, 10); });
		document.addEventListener('rdo:compartimentos:refresh', function(){ setTimeout(rebuild, 20); });

		// initial build
		setTimeout(rebuild, 40);

		// Ensure top-level fields are computed before any submit action
		form.addEventListener('submit', function(ev){
			computeAndSetTopLevelSummaries(form);
			buildCompartimentosJSON(form);
		});

		var submitBtn = qs('#btn-rdo');
		if (submitBtn){
			submitBtn.addEventListener('click', function(){
				computeAndSetTopLevelSummaries(form);
				buildCompartimentosJSON(form);
			});
		}
	}

	// run on DOM ready
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

})();
