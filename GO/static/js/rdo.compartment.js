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
		try {
			// 1) global variable injected by other scripts (preferred)
			if (window.rdo_previous_compartimentos && Array.isArray(window.rdo_previous_compartimentos)) {
				var arr = window.rdo_previous_compartimentos;
				var map1 = Object.create(null);
				arr.forEach(function(it){
					try {
						var idx = (typeof it.index !== 'undefined') ? parseInt(it.index,10) : (typeof it.i !== 'undefined' ? parseInt(it.i,10) : NaN);
						if (!isFinite(idx)) return;
						map1[idx] = { mecanizada: parseInt(it.mecanizada||0,10)||0, fina: parseInt(it.fina||0,10)||0 };
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
								var idx = (typeof it.index !== 'undefined') ? parseInt(it.index,10) : NaN;
								if (!isFinite(idx)) return;
								map2[idx] = { mecanizada: parseInt(it.mecanizada||0,10)||0, fina: parseInt(it.fina||0,10)||0 };
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
							try { var idx = parseInt(it.index,10); if (!isFinite(idx)) return; map3[idx] = { mecanizada: parseInt(it.mecanizada||0,10)||0, fina: parseInt(it.fina||0,10)||0 }; } catch(_){ }
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
						parsed3.forEach(function(it){ try { var idx = parseInt(it.index,10); if (!isFinite(idx)) return; map4[idx] = { mecanizada: parseInt(it.mecanizada||0,10)||0, fina: parseInt(it.fina||0,10)||0 }; }catch(_){ } });
					} else {
						Object.keys(parsed3).forEach(function(k){ try { var idx = parseInt(k,10); if (!isFinite(idx)) return; var v = parsed3[k] || {}; map4[idx] = { mecanizada: parseInt(v.mecanizada||v.m||0,10)||0, fina: parseInt(v.fina||v.f||0,10)||0 }; } catch(_){ } });
					}
					return map4;
				} catch(_){ }
			}

		} catch(e){ /* noop */ }
		return Object.create(null);
	}

	function renderPills(container, count, selectedSet, form){
		container.innerHTML = '';
		if (!count || count < 1) return;
		for (var i=1;i<=count;i++){
			(function(n){
				var btn = document.createElement('button');
				btn.type = 'button';
				btn.className = 'sup-comp-pill';

				// Ensure pills behave as non-wrapping flex items so they scroll horizontally
				btn.style.display = 'inline-flex';
				btn.style.flex = '0 0 auto';
				btn.style.marginRight = '6px';

				btn.setAttribute('aria-pressed', selectedSet.has(n) ? 'true' : 'false');
				btn.setAttribute('role','button');
				btn.setAttribute('aria-label','Compartimento ' + n + (selectedSet.has(n) ? ' selecionado' : ''));
				btn.textContent = n;
				btn.addEventListener('click', function(){ toggle(n, btn, form); });
				btn.addEventListener('keydown', function(ev){ if (ev.key === ' ' || ev.key === 'Enter'){ ev.preventDefault(); toggle(n, btn, form); } });
				container.appendChild(btn);
			})(i);
		}
	}

	function toggle(n, btn, form){
		var pressed = btn.getAttribute('aria-pressed') === 'true';
		var newState = !pressed;
		btn.setAttribute('aria-pressed', newState ? 'true' : 'false');
		btn.setAttribute('aria-label','Compartimento ' + n + (newState ? ' selecionado' : ''));
		syncHiddenInputs(form);
	}

	function syncHiddenInputs(form){
		// Remove existing hidden inputs for this component
		qsa('input[name="compartimentos_avanco"]', form).forEach(function(i){ i.remove(); });
		// Collect currently pressed pills
		var pressed = qsa('#sup-comp-selector .sup-comp-pill[aria-pressed="true"]');
		pressed.forEach(function(btn){
			var v = btn.textContent && btn.textContent.trim();
			if (!v) return;
			form.appendChild(createHiddenInput('compartimentos_avanco', v));
		});

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

		// Gather selected compartment numbers
		var pressed = qsa('#sup-comp-selector .sup-comp-pill[aria-pressed="true"]');
		var selected = pressed.map(function(b){ return parseInt(b.textContent,10); }).filter(Boolean);

		// Remove percent hidden inputs for compartments that are no longer selected
		qsa('input[name^="compartimento_avanco_"], input[name^="compartimento_avanco_fina_"]', form).forEach(function(inp){
			// names may be compartimento_avanco_<n> (old) or compartimento_avanco_mecanizada_<n> / compartimento_avanco_fina_<n>
			var m = inp.name.match(/(\d+)$/);
			var num = m ? parseInt(m[1],10) : NaN;
			if (isNaN(num) || selected.indexOf(num) === -1) inp.remove();
		});

		// For each selected compartment ensure there are hidden inputs for both categories
		selected.forEach(function(n){
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
		});

		// Render UI sliders reflecting current values
		renderPercentControls(container, selected, form);
		// Also compute top-level summary values from current sliders
		if (typeof computeAndSetTopLevelSummaries === 'function') computeAndSetTopLevelSummaries(form);
	}

	// Compute aggregate summaries:
	// - daily top-level fields (`#sup-limp`, `#sup-limp-fina`) keep using the
	//   simple average across SELECTED compartments (UX preserved)
	// - acumulados (`#sup-limp-acu`, `#sup-limp-fina-acu`) are computed using
	//   the TOTAL number of compartments as: (sum of per-compartment fractions / total) * 100
	//   The function tolerates per-compartment values expressed either as 0/1
	//   (binary cleaned flag) or 0..100 (percentage). It normalizes to fraction (0..1)
	//   before computing the percentual acumulado.
	function computeAndSetTopLevelSummaries(form){
		try{
			if (!form) form = qs('#form-supervisor');

			// --- Daily (average across selected) - preserve previous behavior ---
			var pressed = qsa('#sup-comp-selector .sup-comp-pill[aria-pressed="true"]');
			if (!pressed || !pressed.length){
				var supL = qs('#sup-limp'); if (supL) supL.value = '';
				var supF = qs('#sup-limp-fina'); if (supF) supF.value = '';
				// limpar também o novo campo diário de limpeza manual, se existir
				var supLNovo = qs('#sup-limp-manual-novo'); if (supLNovo) supLNovo.value = '';
			} else {
				var mecSum = 0, finaSum = 0, count = 0;
				pressed.forEach(function(btn){
					var n = parseInt(btn.textContent,10);
					if (!n) return;
					var hidM = qs('input[name="compartimento_avanco_mecanizada_' + n + '"]', form);
					var hidF = qs('input[name="compartimento_avanco_fina_' + n + '"]', form);
					var m = hidM ? Number(hidM.value) : NaN;
					var f = hidF ? Number(hidF.value) : NaN;
					if (!isNaN(m)) mecSum += m;
					if (!isNaN(f)) finaSum += f;
					count += 1;
				});
				var avgM = count ? Math.round(mecSum / count) : 0;
				var avgF = count ? Math.round(finaSum / count) : 0;
				// Store numeric values (no percent sign) so frontend and backend consume
				// a consistent numeric representation. Previously we appended '%' for UX,
				// but it's more robust to keep the input value numeric and, if desired,
				// apply visual decoration via CSS or adjacent labels.
				var supM = qs('#sup-limp'); if (supM) supM.value = (avgM || avgM === 0) ? String(avgM) : '';
				var supF = qs('#sup-limp-fina'); if (supF) supF.value = (avgF || avgF === 0) ? String(avgF) : '';
				// espelhar média diária de mecanizada/manual no novo campo
				var supLNovo2 = qs('#sup-limp-manual-novo'); if (supLNovo2) supLNovo2.value = (avgM || avgM === 0) ? String(avgM) : '';
			}

			// --- Acumulados (use TOTAL number of compartments) ---
			var totalEl = qs('#sup-n-comp') || qs('input[name="numero_compartimentos"]');
			var total = totalEl ? parseInt(totalEl.value,10) : NaN;
			if (!total || isNaN(total) || total <= 0){
				// cannot compute acumulado without total compartments
				var acM = qs('#sup-limp-acu'); if (acM) acM.value = '';
				var acF = qs('#sup-limp-fina-acu'); if (acF) acF.value = '';
				// limpar novos campos acumulados
				var acMNovo = qs('#sup-limp-manual-acu-novo'); if (acMNovo) acMNovo.value = '';
				var acFNovo = qs('#sup-limp-fina-acu-novo'); if (acFNovo) acFNovo.value = '';
				return;
			}

			// Sum fractions across ALL compartments (1..total). Normalize values:
			// - if value <= 1 treat as binary/fraction (0 or 1)
			// - if value > 1 treat as percentage 0..100 and convert to fraction (value/100)
			var sumFracM = 0, sumFracF = 0;
			for (var i=1;i<=total;i++){
				var hidM = qs('input[name="compartimento_avanco_mecanizada_' + i + '"]', form);
				var hidF = qs('input[name="compartimento_avanco_fina_' + i + '"]', form);
				var rawM = hidM ? Number(hidM.value) : 0;
				var rawF = hidF ? Number(hidF.value) : 0;
				var fracM = 0, fracF = 0;
				if (!isNaN(rawM)){
					if (rawM <= 1) fracM = rawM; else fracM = (rawM / 100);
				}
				if (!isNaN(rawF)){
					if (rawF <= 1) fracF = rawF; else fracF = (rawF / 100);
				}
				sumFracM += fracM;
				sumFracF += fracF;
			}

			// compute percentual acumulado (0..100)
			var percAcM = Math.round((sumFracM / total) * 100);
			var percAcF = Math.round((sumFracF / total) * 100);

			// Persist acumulados como números inteiros (0..100) sem '%' para facilitar
			// parsing no buildSupervisorFormData e no backend.
			var acMEl = qs('#sup-limp-acu'); if (acMEl) acMEl.value = (percAcM || percAcM === 0) ? String(percAcM) : '';
			var acFEl = qs('#sup-limp-fina-acu'); if (acFEl) acFEl.value = (percAcF || percAcF === 0) ? String(percAcF) : '';
			// popular os novos campos acumulados no modal Supervisor
			var acMElNovo = qs('#sup-limp-manual-acu-novo'); if (acMElNovo) acMElNovo.value = (percAcM || percAcM === 0) ? String(percAcM) : '';
			var acFElNovo = qs('#sup-limp-fina-acu-novo'); if (acFElNovo) acFElNovo.value = (percAcF || percAcF === 0) ? String(percAcF) : '';

		}catch(err){ console.warn('computeAndSetTopLevelSummaries error', err); }
	}

	function renderPercentControls(container, selectedArray, form){
		container.innerHTML = '';
		if (!selectedArray || !selectedArray.length) return;

		// inject minimal CSS for baseline bars (idempotent)
		try{
			if (!document.getElementById('rdo-compartment-baseline-styles')){
				var st = document.createElement('style'); st.id = 'rdo-compartment-baseline-styles';
				st.type = 'text/css';
				st.appendChild(document.createTextNode('\n.sup-comp-avanco-sliderwrap{position:relative;padding-bottom:14px;}\n.sup-comp-baseline{position:absolute;left:0;bottom:4px;height:6px;background:#e6e6e6;border-radius:4px;z-index:1;opacity:0.95;}\n.sup-comp-slider{position:relative;z-index:2;}\n.sup-comp-fill-text{position:absolute;z-index:3;right:8px;top:2px;}\n'));
				document.head.appendChild(st);
			}
		}catch(_){ }

		// Build map of previous compartimentos values (index -> {mecanizada,fina})
		var prevMap = getPreviousCompartimentos(form || document.getElementById('form-supervisor')) || Object.create(null);
		selectedArray.forEach(function(n){
			var hidM = 'compartimento_avanco_mecanizada_' + n;
			var hidF = 'compartimento_avanco_fina_' + n;
			var existingM = qs('input[name="' + hidM + '"]', form);
			var existingF = qs('input[name="' + hidF + '"]', form);
			var valM = existingM ? parseInt(existingM.value,10) || 0 : 0;
			var valF = existingF ? parseInt(existingF.value,10) || 0 : 0;

			var row = document.createElement('div');
			row.className = 'sup-comp-avanco-row';

			var head = document.createElement('div');
			head.className = 'sup-comp-avanco-head';
			var lbl = document.createElement('label');
			lbl.textContent = 'Compart. ' + n;
			lbl.className = 'sup-comp-avanco-head-label';
			head.appendChild(lbl);
			row.appendChild(head);

			var grid = document.createElement('div');
			grid.className = 'sup-comp-avanco-grid';

			// Helper to create one slider block (category, value, hidden input name)
				function makeSliderBlock(catLabel, hidName, initialVal, hiddenVolumeName){
				var block = document.createElement('div');
				block.className = 'sup-comp-avanco-col';

				var cat = document.createElement('div'); cat.className = 'sup-comp-avanco-label'; cat.textContent = catLabel;
				var range = document.createElement('input');
				range.type = 'range'; range.min = 0; range.max = 100; range.step = 1; range.value = initialVal; range.className = 'sup-comp-slider';

				// numeric label removed from side; we'll show percent text centered on the fill bar itself
				// keep a referenceable element (percentText) created on the fillOuter below

				// Ensure hidden input exists (created earlier by syncPercentControls)
				var hid = qs('input[name="' + hidName + '"]', form);
				if (!hid){ hid = createHiddenInput(hidName, String(initialVal)); form.appendChild(hid); }

				// If there is a volume hidden input available, render a visible volume input here instead of the redundant percent number
				var volHidden = null;
				if (hiddenVolumeName) volHidden = qs('input[name="' + hiddenVolumeName + '"]', form);
				if (!volHidden && hiddenVolumeName){ volHidden = createHiddenInput(hiddenVolumeName, '0'); form.appendChild(volHidden); }

				// We keep the hidden volume input for backend compatibility but
				// do not render a visible volume input; the UI uses only the fill bar.

				// Use the slider's own track as the filled area by setting its
				// background to a linear-gradient. Create a percentText overlay
				// that will be positioned on top of the slider.
					var percentText = document.createElement('span');
				percentText.className = 'sup-comp-fill-text';
				percentText.textContent = initialVal + '%';



				// update handlers
				range.setAttribute('aria-valuemin', '0');
				range.setAttribute('aria-valuemax', '100');
				range.setAttribute('aria-valuenow', String(initialVal));
				// set initial track background
				try{ range.style.background = 'linear-gradient(90deg, #37a05a ' + initialVal + '%, #e9eceb ' + initialVal + '%)'; }catch(e){}
				range.addEventListener('input', function(){
					var v = String(range.value);
					// update overlay text and hidden input
					percentText.textContent = v + '%';
					hid.value = v;
					range.setAttribute('aria-valuenow', v);
					// update the slider track fill using background gradient
					range.style.background = 'linear-gradient(90deg, #37a05a ' + v + '%, #e9eceb ' + v + '%)';
					// adjust text color for contrast when fill is dark enough
					var valNum = parseInt(v, 10) || 0;
					if (valNum >= 40) {
						percentText.classList.add('sup-comp-fill-text--on-dark');
					} else {
						percentText.classList.remove('sup-comp-fill-text--on-dark');
					}
					// update aggregate top-level summary fields
					computeAndSetTopLevelSummaries(form);
				});

				// If needed later, volume hidden input can be updated programmatically.

				var wrap = document.createElement('div'); wrap.className = 'sup-comp-avanco-sliderwrap';
				wrap.appendChild(range);
				// append percent overlay directly on top of the slider
				wrap.appendChild(percentText);

				// now that wrap exists, append baseline element (previous acumulado) if available
				try{
					var prev = prevMap && prevMap[n] ? prevMap[n] : null;
					var prevPercent = 0;
					if (prev){
						if (catLabel && /Mecaniz/i.test(catLabel)) prevPercent = parseInt(prev.mecanizada||0,10) || 0;
						else prevPercent = parseInt(prev.fina||0,10) || 0;
					}
					if (prevPercent < 0) prevPercent = 0; if (prevPercent > 100) prevPercent = 100;
					var baseline = document.createElement('div');
					baseline.className = 'sup-comp-baseline';
					baseline.style.width = String(prevPercent) + '%';
					// place baseline just under the slider track
					wrap.appendChild(baseline);
				} catch(_){ }

				block.appendChild(cat);
				block.appendChild(wrap);
				// no visible volume input: keep the DOM minimal
				return block;
				}

			var hidMVol = 'compartimento_avanco_mecanizada_volume_' + n;
			var hidFVol = 'compartimento_avanco_fina_volume_' + n;
			grid.appendChild(makeSliderBlock('Mecanizada / Manual', hidM, valM, hidMVol));
			grid.appendChild(makeSliderBlock('Limpeza Fina', hidF, valF, hidFVol));

			row.appendChild(grid);
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

		// initialize from current number and existing hidden inputs
		var existingInputs = qsa('input[name="compartimentos_avanco"]', form);
		var initialSelected = new Set(existingInputs.map(function(i){ return parseInt(i.value,10); }).filter(Boolean));

		function rebuild(){
			var v = parseInt(inputN.value, 10);
			if (!v || v < 1) { container.innerHTML = ''; syncHiddenInputs(form); return; }
			var max = Math.max(1, v); // permitir qualquer quantidade (ex.: 100)
			// manter seleção existente dentro do novo intervalo
			var existing = qsa('#sup-comp-selector .sup-comp-pill[aria-pressed="true"]').map(function(b){ return parseInt(b.textContent,10); });
			var selectedSet = new Set(existing.concat(Array.from(initialSelected)).filter(function(x){ return x && x <= max; }));
			renderPills(container, max, selectedSet, form);
			selectedSet.forEach(function(n){
				var el = container.querySelector('.sup-comp-pill:nth-child(' + n + ')');
				if (el) el.setAttribute('aria-pressed','true');
			});

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

