/* rdo.js
*/

;(function(){
	'use strict';

	// Mapeamento entre IDs dos inputs e atributos data-* das linhas
	var FIELD_MAP = {
		'f-contrato': ['po','contrato','dataPo'], // tentar várias chaves possíveis
		'f-os': ['numeroOs','os'],
		'f-empresa': ['empresa','cliente'],
		'f-unidade': ['unidade'],
		'f-turno': ['turno'],
		'f-servico': ['servico'],
		'f-metodo': ['metodo'],
		'f-date-start': ['data'],
		'f-tanque': ['tanque','tanqueNome','tanqueCodigo','tanque-nome'],
		'f-supervisor': ['supervisor'],
		'f-status_geral': ['statusGeral','status-geral']
	};

	function qs(sel, ctx){ return (ctx || document).querySelector(sel); }
	function qsa(sel, ctx){ return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

	function getInputValue(id){
		var el = document.getElementById(id);
		if(!el) return '';
		return String(el.value || '').trim();
	}

	function normalize(v){ return String(v || '').toLowerCase(); }

	;(function(){
		try {
			var overlay = document.getElementById('supv-modal-overlay');
			if (!overlay) return;

				// Helpers e delegação
					function openModal(){
					try {
						overlay.classList.remove('is-hidden');
						overlay.classList.add('open');
						overlay.setAttribute('aria-hidden','false');
						var focusable = overlay.querySelector('input,select,textarea,button'); if (focusable) focusable.focus();
					} catch(e){}
				}

				// Auto aceitação de .force-lower para .btn-remove-atividade quando o modal do supervisor abre
						// Marca/desmarca a classe `force-lower` em botões de remoção
						function applyForceLower(enable){
							try {
								var buttons = document.querySelectorAll('.btn-remove-atividade');
								Array.prototype.forEach.call(buttons, function(b){
									try {
										if (enable) b.classList.add('force-lower');
										else b.classList.remove('force-lower');
									} catch(e){}
								});
							} catch(e){ console.warn('applyForceLower failed', e); }
						}

					// Toast helper: show brief messages in the corner
					function showToast(message, type){
					    try {
					        var id = 'rdo-toast';
					        var existing = document.getElementById(id);
					        if (existing) existing.remove();
					        var div = document.createElement('div');
					        div.id = id;
					        div.className = 'rdo-toast ' + (type || 'info');
					        div.textContent = message;
					        div.style.position = 'fixed';
					        div.style.right = '20px';
					        div.style.bottom = '20px';
					        div.style.padding = '10px 14px';
					        div.style.borderRadius = '6px';
					        div.style.boxShadow = '0 2px 6px rgba(0,0,0,0.2)';
					        div.style.zIndex = 99999;
					        if (type === 'success') { div.style.background = '#2e7d32'; div.style.color = '#fff'; }
					        else if (type === 'error') { div.style.background = '#c62828'; div.style.color = '#fff'; }
					        else { div.style.background = '#333'; div.style.color = '#fff'; }
					        document.body.appendChild(div);
					        setTimeout(function(){ try{ div.style.opacity = '0'; setTimeout(function(){ try{ div.remove(); }catch(e){} }, 300); }catch(e){} }, 3000);
					    } catch (e) { try{ console.warn('toast failed', e); }catch(_){} }
					}

					try { if (typeof window !== 'undefined') window.showToast = showToast; } catch(e) { /* noop */ }

					// Efeito visual para nova linha: destaca e remove o destaque depois
					function addNewRowEffect(tr) {
					    try {
					        if (!tr || !tr.style) return;
					        tr.classList.add('rdo-new-row');
					        tr.style.transition = 'background-color 0.8s ease';
					        tr.style.backgroundColor = '#fff7e6';
					        setTimeout(function(){ try { tr.style.backgroundColor = ''; tr.classList.remove('rdo-new-row'); } catch(e){} }, 1800);
					    } catch(e){}
					}
					// Delegated openers: garantir que estamos dentro de um event handler com `ev`
					document.addEventListener('click', function(ev){
					if (typeof ev === 'undefined' || !ev || !ev.target) return;
					var edit = ev.target.closest('.action-btn.edit');
					if (edit) {
						// Se o novo modal-editor estiver presente, não interceptamos o clique aqui
						// (o handler do modal-editor no template cuidará da abertura).
						if (document.getElementById('modal-editor-overlay')) {
							return;
						}
						var tr = edit.closest('tr');
								var ctxOs = document.getElementById('sup-context-os');
						var ctxEmpresa = document.getElementById('sup-context-empresa');
						var ctxUnid = document.getElementById('sup-context-unidade');
						var ctxSup = document.getElementById('sup-context-supervisor');
							if (tr) {
								if (ctxOs) ctxOs.textContent = tr.dataset.numeroOs || tr.dataset.os || (tr.querySelector('td:nth-child(2)')||{}).textContent || '-';
								// remova referências inválidas que podem ter sobrado de edições anteriores
								// (antes havia acessos a `el`/`k` aqui, que provocavam ReferenceError)
								// localizar elemento mobile de forma segura: preferir variável `mobile` se existir,
								// senão tentar elementos conhecidos no DOM (fallback)
								var mobileEl = (typeof mobile !== 'undefined' && mobile) ? mobile : (document.getElementById('rdo-mobile-root') || document.getElementById('rdo-mobile-cta') || null);
								if (mobileEl) {
							// Construir contexto e delegar para rdoOpenSupervisorModal — ele já calcula o próximo RDO
							try {

								var ctx = {
									os: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-os') : null) || (mobileEl.dataset && mobileEl.dataset.os) || '',
									numero_os: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-os') : null) || (mobileEl.dataset && mobileEl.dataset.os) || '',
									empresa: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-empresa') : null) || (mobileEl.dataset && mobileEl.dataset.empresa) || '',
									unidade: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-unidade') : null) || (mobileEl.dataset && mobileEl.dataset.unidade) || '',
									// servidor agora expõe data-supervisor-login e data-supervisor-fullname no DOM
									supervisor: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-supervisor') : null) || (mobileEl.dataset && mobileEl.dataset.supervisor) || '',
									supervisor_login: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-supervisor-login') : null) || (mobileEl.dataset && mobileEl.dataset.supervisorLogin) || '',
									supervisor_fullname: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-supervisor-fullname') : null) || (mobileEl.dataset && mobileEl.dataset.supervisorFullname) || '',
									rdo_id: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-rdo-id') : null) || (mobileEl.dataset && (mobileEl.dataset.rdoId || mobileEl.dataset.rdoid)) || '',
									os_id: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-os-id') : null) || (mobileEl.dataset && (mobileEl.dataset.osId || mobileEl.dataset.os_id)) || '' ,
									rdo_count: (typeof mobileEl.getAttribute === 'function' ? mobileEl.getAttribute('data-rdo-count') : null) || (mobileEl.dataset && mobileEl.dataset.rdoCount) || ''
								};
								if (window.rdoOpenSupervisorModal && typeof window.rdoOpenSupervisorModal === 'function') {
									window.rdoOpenSupervisorModal(ctx);
									return;
								} else {
									// fallback: replicar o comportamento anterior (preencher context labels e abrir modal)
									var ctxOs = document.getElementById('sup-context-os');
									var ctxEmpresa = document.getElementById('sup-context-empresa');
									var ctxUnid = document.getElementById('sup-context-unidade');
									var ctxSup = document.getElementById('sup-context-supervisor');
									var ctxRdo = document.getElementById('sup-context-rdo');

									// Helper: normalizar nomes para exibição (ex: carolina.machado -> Carolina Machado)
									function normalizePersonDisplay(raw){
										if (!raw) return '';
										try {
											var s = String(raw || '');
											// substituir separadores comuns por espaço
											s = s.replace(/[._\-\u005F\+]+/g, ' ');
											// split por qualquer sequência não-letra (aceita acentuação básica)
											var parts = s.split(/[^A-Za-zÀ-ÖØ-öø-ÿ]+/).filter(function(p){ return !!p; });
											if (!parts.length) return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
											return parts.map(function(p){ return p.charAt(0).toUpperCase() + p.slice(1).toLowerCase(); }).join(' ');
										} catch(e){
											try { var s2 = String(raw).replace(/[._\-\u005F]+/g,' '); return s2.charAt(0).toUpperCase() + s2.slice(1).toLowerCase(); } catch(e){ return String(raw); }
										}
									}

									if (ctxOs) ctxOs.textContent = ctx.numero_os || ctx.os || '-';
									if (ctxEmpresa) ctxEmpresa.textContent = ctx.empresa || '-';
									if (ctxUnid) ctxUnid.textContent = ctx.unidade || '-';
									if (ctxSup) ctxSup.textContent = ctx.supervisor ? normalizePersonDisplay(ctx.supervisor) : '-';
									try {
										var form2 = document.getElementById('form-supervisor');
										var osHidden2 = document.getElementById('sup-ordem-id');
										if (!osHidden2 && form2) {
											osHidden2 = document.createElement('input');
											osHidden2.type = 'hidden';
											osHidden2.name = 'ordem_servico_id';
											osHidden2.id = 'sup-ordem-id';
											form2.appendChild(osHidden2);
										}
										if (osHidden2) osHidden2.value = ctx.os_id || '';
									} catch(e){}
									openModal();
									return;
								}
							} catch(e) { console.warn('open mobile modal fallback failed', e); }
						}
						}
					}
				});

				// Expor função para abrir modal do supervisor com contexto (usada por select)
				window.rdoOpenSupervisorModal = function(context){
					try {
						var ctxOs = document.getElementById('sup-context-os');
						var ctxEmpresa = document.getElementById('sup-context-empresa');
						var ctxUnid = document.getElementById('sup-context-unidade');
						var ctxSup = document.getElementById('sup-context-supervisor');
						var ctxRdo = document.getElementById('sup-context-rdo');
						var hid = document.getElementById('sup-rdo-id');
						if (ctxOs) ctxOs.textContent = context.numero_os || context.os || '-';
						if (ctxEmpresa) ctxEmpresa.textContent = context.empresa || '-';
						if (ctxUnid) ctxUnid.textContent = context.unidade || '-';
						if (ctxSup) ctxSup.textContent = context.supervisor || '-';
						// Preencher hidden APENAS com RDO ID (se conhecido). Evita usar OS ID por engano
						if (hid) hid.value = context.rdo_id || '';
						// hidden com OS id
						try {
							var form = document.getElementById('form-supervisor');
							var osHidden = document.getElementById('sup-ordem-id');
							if (!osHidden && form) {
								osHidden = document.createElement('input');
								osHidden.type = 'hidden';
								osHidden.name = 'ordem_servico_id';
								osHidden.id = 'sup-ordem-id';
								form.appendChild(osHidden);
							}
							if (osHidden) osHidden.value = context.os_id || '';
						} catch(e){}

						// Auto-clear: se a OS atual for diferente da última aberta, limpar os cartões móveis
						try {
							var tryOsId = context.os_id || context.os || '';
							if (tryOsId) {
								var prevOs = '';
								try { prevOs = localStorage.getItem('rdo_last_opened_os') || ''; } catch(e) { prevOs = ''; }
								// considerar apenas ambiente mobile (ex.: presença de #rdo-mobile-list)
								if (prevOs && String(prevOs) !== String(tryOsId) && document.getElementById('rdo-mobile-list')) {
									try { if (window.clearMobileCards && typeof window.clearMobileCards === 'function') window.clearMobileCards({ remove: true, os_id: tryOsId }); } catch(e){}
								}
								try { localStorage.setItem('rdo_last_opened_os', String(tryOsId)); } catch(e){}
							}
						} catch(e){}

						// preencher Contrato / PO automaticamente quando disponível e bloquear edição
						try {
							var contratoEl = document.getElementById('sup-contrato-po');
							var contratoVal = context && context.contrato_po ? String(context.contrato_po) : '';
							if (!contratoVal) {
								// procurar em elementos DOM que contenham data-os-id igual
								var osIdSearch = context && context.os_id ? String(context.os_id) : '';
								if (osIdSearch) {
									try {
										var rows = Array.from(document.querySelectorAll('[data-os-id]'));
										rows.forEach(function(r){
											try {
												if (String(r.getAttribute('data-os-id')) === osIdSearch) {
													var v = r.getAttribute('data-po') || r.getAttribute('data-contrato-po') || r.dataset && (r.dataset.po || r.dataset.contratoPo);
													if (v) contratoVal = String(v);
												}
											} catch(e){}
										});
									} catch(e){}
								}
							}
							if (contratoEl && contratoVal) {
								contratoEl.value = contratoVal;
								// tornar somente leitura (bloqueado) para evitar edição neste fluxo
								contratoEl.readOnly = true; contratoEl.setAttribute('aria-readonly','true'); contratoEl.classList.add('readonly');
							} else if (contratoEl) {
								// garantir que possa ser editado quando não há valor conhecido
								contratoEl.readOnly = false; contratoEl.removeAttribute('aria-readonly'); contratoEl.classList.remove('readonly');
							}
						} catch(e) { console.warn('prefill contrato po failed', e); }

						// preencher automaticamente Contrato / PO quando possível (contexto ou DOM)
						try {
							var contratoEl = document.getElementById('sup-contrato-po');
							if (contratoEl) {
								var contratoVal = context.contrato_po || context.po || '';
								if (!contratoVal) {
									// procurar por um elemento no DOM com data-os-id correspondente e extrair data-po
									var osId = (context && context.os_id) ? String(context.os_id) : ((context && context.os) ? String(context.os) : '');
									if (osId) {
										try {
											var candidates = Array.from(document.querySelectorAll('[data-os-id], [data-numero-os]'));
											for (var i=0;i<candidates.length;i++){
												var el = candidates[i];
												var val = el.getAttribute('data-os-id') || el.getAttribute('data-numero-os') || '';
												if (val === osId) {
													contratoVal = el.getAttribute('data-po') || el.getAttribute('data-contrato') || (el.dataset && (el.dataset.po || el.dataset.contrato_po)) || '';
													if (contratoVal) break;
												}
											}
										} catch(e){}
									}
								}
								if (contratoVal) contratoEl.value = contratoVal;
							}
						} catch(e){}
						// calcular e preencher o próximo número de RDO consultando o servidor
						try {
							(function(){
								var rdoInput = document.getElementById('sup-rdo');
								if (!rdoInput) return;

								// Função utilitária para aplicar o valor retornado (ou fallback)
								function applyValue(val){
									try {
										rdoInput.value = String(val);
										rdoInput.readOnly = true; rdoInput.setAttribute('aria-readonly','true'); rdoInput.classList.add('readonly');
										if (ctxRdo) ctxRdo.textContent = String(val);
									} catch(e){ console.warn('applyValue failed', e); }
								}

								// Desabilitar controles "abrir/editar" de RDOs anteriores para a mesma OS
								function disablePreviousOpenControls(osId, currentRdo){
									try {
										// Apenas atuar sobre os cartões mobile para não afetar os botões da tabela
										if (!osId) return;
										var cur = parseInt(String(currentRdo||'').replace(/[^0-9\-]/g,''), 10);
										if (!isFinite(cur)) return;
										// selecionar apenas os cartões mobile que representam resumo RDO/OS
										var selector = '.rdo-mobile-item[data-os-id="' + osId + '"], .rdo-mobile-card[data-os-id="' + osId + '"]';
										var nodes = Array.from(document.querySelectorAll(selector));
										nodes.forEach(function(node){
											try {
												var attr = node.getAttribute('data-rdo-count') || (node.dataset && node.dataset.rdoCount);
												if (!attr) return;
												var n = parseInt(String(attr||'').replace(/[^0-9\-]/g,''), 10);
												if (!isFinite(n)) return;
												if (n < cur) {
													// Preferir desabilitar o botão de abrir do cartão (classe .open-supervisor)
													var btns = Array.from(node.querySelectorAll('.open-supervisor, .btn-rdo.open-supervisor'));
													if (btns.length) {
														btns.forEach(function(b){
															try { b.classList.add('disabled-by-next-rdo'); b.disabled = true; b.setAttribute('aria-disabled','true'); b.style.pointerEvents = 'none'; b.style.opacity = '0.5'; } catch(e){}
														});
													} else {
														// fallback: desabilitar o próprio cartão
														try { node.classList.add('disabled-by-next-rdo'); node.setAttribute('aria-disabled','true'); node.style.pointerEvents = 'none'; node.style.opacity = '0.5'; } catch(e){}
													}
												}
											} catch(e){}
										});
									} catch(e){}
								}

								// 1) se contexto já sugerir valor confiável, mostrar provisório imediatamente
								var fromCtxRaw = (context && typeof context.rdo_count !== 'undefined') ? context.rdo_count : '';
								var fromCtx = parseInt(String(fromCtxRaw || '').replace(/[^0-9\-]/g,''), 10);
								if (isFinite(fromCtx) && fromCtx >= 0) {
									var provisional = Math.max(1, fromCtx + 1);
									applyValue(provisional);
									try { disablePreviousOpenControls(context && context.os_id ? String(context.os_id) : '', provisional); } catch(e){}
								} else {
									// aplicar 1 provisoriamente até consulta
									applyValue(1);
									try { disablePreviousOpenControls(context && context.os_id ? String(context.os_id) : '', 1); } catch(e){}
								}

								// 2) consultar endpoint server-side para obter próximo número definitivo
								try {
									var osId = (context && context.os_id) ? String(context.os_id) : '';
									if (!osId) return; // nothing to query
									// construir URL relativa para o endpoint; assumimos rota '/api/rdo/next/' implementada no backend
									var url = '/api/rdo/next/?os_id=' + encodeURIComponent(osId);
									fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With':'XMLHttpRequest' } })
										.then(function(resp){ if (!resp.ok) throw new Error('status-' + resp.status); return resp.json(); })
										.then(function(data){
											if (data && data.success && typeof data.next_rdo !== 'undefined') {
												try { applyValue(data.next_rdo); } catch(e){}
											} else {
												// manter o valor provisório (do contexto ou 1)
												console.warn('next_rdo: resposta inesperada', data);
											}
											// após aplicar o valor definitivo (ou manter provisório), garantir desabilitação de controles anteriores
											try { disablePreviousOpenControls(osId, (data && typeof data.next_rdo !== 'undefined') ? data.next_rdo : (isFinite(fromCtx) ? Math.max(1, fromCtx + 1) : 1)); } catch(e){}
										}).catch(function(err){
											// fallback: manter valor provisório e logar
											console.warn('Erro ao consultar /api/rdo/next/:', err);
										});
								} catch(e){ console.warn('prefill RDO fetch failed', e); }
							})();
						} catch(e) { console.warn('prefill RDO failed', e); }

						if (overlay) {
							overlay.classList.remove('is-hidden');
							overlay.classList.add('open');
							overlay.setAttribute('aria-hidden','false');
							var focusable = overlay.querySelector('input,select,textarea,button'); if (focusable) focusable.focus();
						}

						// Auto-popular primeira linha da equipe: selecionar supervisor como pessoa e a função "Supervisor"
						try {
							// procurar primeiro dentro do overlay para evitar confusão com outros wrappers
								var overlayEl = document.getElementById('supv-modal-overlay');
							var equipeWrapper = (overlayEl && overlayEl.querySelector) ? (overlayEl.querySelector('#equipe-wrapper') || document.getElementById('equipe-wrapper')) : document.getElementById('equipe-wrapper');
							if (equipeWrapper) {
								var firstRow = equipeWrapper.querySelector('.team-row') || (overlayEl && overlayEl.querySelector && overlayEl.querySelector('.team-row'));
								if (firstRow) {
									var nameSel = firstRow.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
									var funcSel = firstRow.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
									// fallback: procurar por name dentro do overlay se não encontramos na primeira linha
									if ((!nameSel || !funcSel) && overlayEl) {
										try {
											nameSel = nameSel || overlayEl.querySelector('[name="equipe_nome[]"]');
											funcSel = funcSel || overlayEl.querySelector('[name="equipe_funcao[]"]');
										} catch(e){}
									}
									function setSelectValueOrAdd(sel, val){
										if (!sel || !val) return;
										var originalVal = String(val);
										// remover domínio se fornecido (carolina.machado@dominio -> carolina.machado)
										try { val = String(val).split('@')[0]; } catch(e) { val = String(val); }
										val = String(val).trim();
										if (!val) return;
										try {
											// procurar opção existente (comparar value e texto)
											var found = null;
											var isSelect = (sel.tagName && sel.tagName.toLowerCase() === 'select');
											if (isSelect) {
												for (var i=0;i<sel.options.length;i++){
													var o = sel.options[i];
													var oVal = (o.value||'').trim();
													var oText = (o.text||'').trim();
													if (oVal === val || oText === val || (originalVal && (oVal === originalVal || oText === originalVal))) { found = o; break; }
													// tentar correlacionar login canônico: canonicalLoginFromName(oText) === val (ex: 'carolina.machado')
													try {
														var canon = canonicalLoginFromName(oText || oVal || '');
														if (canon && canon === String(val).toLowerCase()) { found = o; break; }
													} catch(e){}
												}
											}
											if (!found) {
												// adicionar opção ao final (não persiste no servidor) apenas para selects
												if (isSelect) {
													try {
														// tentar resolver nome completo via mapa exposto pelo servidor antes de criar label
														var displayLabel = (window.RDO_PESSOAS_MAP && window.RDO_PESSOAS_MAP[String(val).toLowerCase()]) || normalizePersonDisplay(val) || val;
														var opt = document.createElement('option'); opt.value = val; opt.text = displayLabel;
														sel.appendChild(opt);
														found = opt;
													} catch(e) { /* ignore */ }
												} else {
													// se for input/text, simplesmente atribuir o valor normalizado
													try { sel.value = normalizePersonDisplay(val) || val; } catch(e){}
												}
											}
											if (found) try {
												// garantir label amigável ao exibir (formatar caso necessário)
												try { if (found.text === found.value || !found.text) found.text = normalizePersonDisplay(found.value) || found.value; } catch(e){}
												sel.value = found.value;
											} catch(e){}
										} catch(e){}
									}
									// obter candidato ao nome do supervisor: priorizar fullname exposto pelo servidor
									var supCandidate = '';
									try {
										if (context && context.supervisor_fullname) {
											supCandidate = String(context.supervisor_fullname || '');
										} else if (context && context.supervisor_login) {
											// tentar resolver login -> nome via mapa gerado no servidor
											var loginKey = String(context.supervisor_login || '').toLowerCase().split('@')[0];
											if (window.RDO_PESSOAS_MAP && window.RDO_PESSOAS_MAP[loginKey]) supCandidate = window.RDO_PESSOAS_MAP[loginKey];
											else supCandidate = String(context.supervisor_login || '');
										} else if (overlayEl) {
											var supLabel = overlayEl.querySelector('#sup-context-supervisor');
											if (supLabel && supLabel.textContent) supCandidate = supLabel.textContent;
										}
									} catch(e){}

									// aplicar valores (tentativa imediata e novas tentativas após atrasos curtos)
									if (supCandidate) setSelectValueOrAdd(nameSel, supCandidate);
									setSelectValueOrAdd(funcSel, 'Supervisor');
									try {
										var delays = [120, 300, 600];
										delays.forEach(function(ms){
											setTimeout(function(){
												if (supCandidate) setSelectValueOrAdd(nameSel, supCandidate);
												setSelectValueOrAdd(funcSel, 'Supervisor');
											}, ms);
										});
									} catch(e){}

									// observar mudanças na wrapper e reaplicar uma vez se as opções forem substituídas
									try {
										if (equipeWrapper && window.MutationObserver) {
											var mo = new MutationObserver(function(muts){
												muts.forEach(function(m){
													if (m.type === 'childList' || m.type === 'attributes') {
														try { if (context && context.supervisor) setSelectValueOrAdd(nameSel, context.supervisor); } catch(e){}
													}
												});
												// desconectar após primeira execução para evitar overhead
												setTimeout(function(){ try { mo.disconnect(); } catch(e){} }, 1000);
											});
											mo.observe(equipeWrapper, { childList: true, subtree: true, attributes: true });
										}
									} catch(e){}
								}
							}
						} catch(e){ /* não bloquear abertura do modal se algo falhar */ }
						// carregar dados do RDO via fetch e preencher campos agregados
						(function(){
							try {
								// Só buscar detalhes quando tivermos um RDO ID real
								var id = context.rdo_id || (hid && hid.value);
								if (!id) return;
								var url = '/rdo/' + encodeURIComponent(id) + '/detail/';
								fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
									.then(function(resp){ if (!resp.ok) throw new Error('fetch'); return resp.json(); })
									.then(function(data){
										if (!data || !data.success || !data.rdo) return;
										var r = data.rdo;
										try {
											var map = [
												['sup-total-atividades','total_atividade_min'],
												['sup-total-confinado','total_confinado_min'],
												['sup-total-abertura-pt','total_abertura_pt_min'],
												['sup-total-atividades-efetivas','total_atividades_efetivas_min'],
												['sup-total-nao-efetivas-fora','total_atividades_nao_efetivas_fora_min'],
												['sup-total-n-efetivo-confinado','total_n_efetivo_confinado_min'],
											];
											map.forEach(function(pair){
												var el = document.getElementById(pair[0]);
												if (!el) return;
												var v = r[pair[1]];
												if (v === null || v === undefined) el.value = '';
												else el.value = String(v);
											});

											// preencher datas de periodo, se existirem
											try {
												var di = document.getElementById('sup-data-inicio');
												var pt = document.getElementById('sup-previsao-termino');
												if (di) di.value = r.data_inicio || '';
												if (pt) pt.value = r.previsao_termino || '';
											} catch(e){}
										} catch(e){}
									}).catch(function(e){ });
							} catch(e){}
						})();
					} catch (e) { console.error('rdoOpenSupervisorModal error', e); }
				};

			} catch(e){ console.error('rdo.js modal init error', e); }
		})();



					// Função: recalcular os agregados no modal com base nas linhas de atividade
					function computeModalAggregates(){
						try {
							var wrapper = document.getElementById('atividades-wrapper');
							if (!wrapper) return {};
							var rows = Array.from(wrapper.querySelectorAll('.activities-row'));
							// helper para converter time 'HH:MM' para minutos
							function timeToMinutes(t){
								if (!t) return null;
								if (typeof t === 'string' && t.indexOf(':') > -1) {
									var p = t.split(':');
									var hh = parseInt(p[0],10);
									var mm = parseInt(p[1],10)||0;
									if (!isFinite(hh) || !isFinite(mm)) return null;
									return hh*60 + mm;
								}
								return null;
							}

							var total_atividade = 0;
							var total_abertura_pt = 0;
							var total_atividades_efetivas = 0;
							// usar a mesma lista curta presente no servidor para marcar efetivas
							var ATIVIDADES_EFETIVAS = [
								'avaliação inicial da área de trabalho',
								'bombeio',
								'instalação/preparação/montagem',
								'desmobilização do material - dentro do tanque',
								'desmobilização do material - fora do tanque',
								'mobilização de material - dentro do tanque',
								'mobilização de material - fora do tanque',
								'limpeza e higienização de coifa',
								'limpeza de dutos',
								'coleta e análise de ar',
								'cambagem',
								'içamento',
								'limpeza fina',
								'manutenção de equipamentos - dentro do tanque',
								'manutenção de equipamentos - fora do tanque',
								'jateamento'
							];

							rows.forEach(function(row){
								try {
									var sel = row.querySelector('.atividade-nome-select');
									var inicio = row.querySelector('.atividade-inicio');
									var fim = row.querySelector('.atividade-fim');
									var atVal = sel ? (sel.value || '').toString().trim().toLowerCase() : '';
									var inicioMin = inicio ? timeToMinutes(inicio.value) : null;
									var fimMin = fim ? timeToMinutes(fim.value) : null;
									if (inicioMin !== null && fimMin !== null) {
										var dur = fimMin - inicioMin;
										// normalizar travessia de meia-noite
										if (dur < 0) dur += 24*60;
										total_atividade += dur;
										// abertura PT
										if (atVal === 'abertura pt') total_abertura_pt += dur;
										// efetivas
										if (ATIVIDADES_EFETIVAS.indexOf(atVal) !== -1) total_atividades_efetivas += dur;
									}
								} catch(e){}
							});

							// calcular total confinado a partir dos inputs de ec-times-grid (soma de pares entrada/saida)
							var ecGrid = document.getElementById('ec-times-grid');
							var total_confinado = 0;
							if (ecGrid) {
								var entradas = Array.from(ecGrid.querySelectorAll('input[name="entrada_confinado[]"]'));
								var saidas = Array.from(ecGrid.querySelectorAll('input[name="saida_confinado[]"]'));
								for (var i=0;i<Math.max(entradas.length, saidas.length); i++){
									var e = entradas[i] ? timeToMinutes(entradas[i].value) : null;
									var s = saidas[i] ? timeToMinutes(saidas[i].value) : null;
									if (e !== null && s !== null) {
										var d = s - e; if (d < 0) d += 24*60; total_confinado += d;
									}
								}
							}

							// total_n_efetivo_confinado: ler do input do modal se preenchido, senão 0
							var nEfetivoEl = document.getElementById('sup-total-n-efetivo-confinado');
							var nEfetivo = 0;
							if (nEfetivoEl && nEfetivoEl.value) {
								var tmp = parseInt(nEfetivoEl.value,10);
								if (isFinite(tmp)) nEfetivo = tmp;
							}

							var total_nao_efetivas_fora = total_atividade - total_atividades_efetivas - nEfetivo;

							// popular campos
							function setIf(id, value){ var el = document.getElementById(id); if (!el) return; el.value = (value === null || value === undefined) ? '' : String(Math.round(value)); }
							setIf('sup-total-atividades', total_atividade);
							setIf('sup-total-confinado', total_confinado);
							setIf('sup-total-abertura-pt', total_abertura_pt);
							setIf('sup-total-atividades-efetivas', total_atividades_efetivas);
							setIf('sup-total-n-efetivo-confinado', nEfetivo);
							setIf('sup-total-nao-efetivas-fora', total_nao_efetivas_fora);

							return {
								total_atividade: total_atividade,
								total_confinado: total_confinado,
								total_abertura_pt: total_abertura_pt,
								total_atividades_efetivas: total_atividades_efetivas,
								total_nao_efetivas_fora: total_nao_efetivas_fora,
								n_efetivo_confinado: nEfetivo
							};
						} catch(e){ console.warn('computeModalAggregates failed', e); return {}; }
					}

					// ligar ao botão criado no template
					try {
						var recBtn = document.getElementById('btn-recalcular-calculos');
						if (recBtn) recBtn.addEventListener('click', function(ev){ ev.preventDefault(); var res = computeModalAggregates(); showToast('Cálculos atualizados (pré-visualização)', 'success'); });
						// expor para uso externo
						window.computeModalAggregates = computeModalAggregates;
					} catch(e){}


		//Atividades dinâmicas: adicionar/remover linhas
		(function(){
			try {
				var wrapper = document.getElementById('atividades-wrapper');
				if (!wrapper) return;

				wrapper.addEventListener('click', function(ev){
					var rem = ev.target.closest('.btn-remove-atividade');
					if (!rem) return;
					var rows = wrapper.querySelectorAll('.activities-row');
					if (rows.length <= 1) return;
					var row = rem.closest('.activities-row'); if (row) row.remove();
					updateRemoveState();
				});

				var addBtn = document.getElementById('btn-add-atividade');
				if (addBtn) addBtn.addEventListener('click', function(){
					var max = parseInt(addBtn.getAttribute('data-max')||'20',10);
					var rows = wrapper.querySelectorAll('.activities-row');
					if (rows.length >= max) return;
					var last = rows[rows.length-1]; if (!last) return;
					var newIndex = rows.length; // next index (0-based)
					var clone = last.cloneNode(true);

					Array.from(clone.querySelectorAll('input,select,textarea,label')).forEach(function(el){
						try {
							if (el.tagName.toLowerCase() === 'label') {
								var f = el.getAttribute('for');
								if (f) el.setAttribute('for', f.replace(/-\d+$/, '-') + newIndex);
								return;
							}
							var tag = el.tagName.toLowerCase();
							var type = (el.type || '').toLowerCase();
							if (tag === 'select') { el.selectedIndex = 0; }
							else if (type === 'checkbox' || type === 'radio') { el.checked = false; }
							else { el.value = ''; }

							if (el.id) {
								if (/-(\d+)$/.test(el.id)) el.id = el.id.replace(/-(\d+)$/, '-' + newIndex);
								else el.id = el.id + '-' + newIndex;
							}

							if (el.name) {
							}

							if (el.dataset) {
								delete el.dataset.rdoTranslatorInit;
								delete el.dataset.userEdited;
								delete el.dataset.autoFilled;
							}

							try { el.removeAttribute && el.removeAttribute('readonly'); } catch(e){}
						} catch(e){}
					});

					var footer = wrapper.querySelector('.activities-footer');
					wrapper.insertBefore(clone, footer || null);

					try { initActivityTranslators(); } catch(e){}

					updateRemoveState();
				});

				function updateRemoveState(){
					var rows = wrapper.querySelectorAll('.activities-row');
					rows.forEach(function(r){ var b = r.querySelector('.btn-remove-atividade'); if (b) b.disabled = (rows.length <= 1); });
				}

				updateRemoveState();

				try {
					var removeLastBtn = document.getElementById('btn-remove-last-atividade');
					if (removeLastBtn) {
						removeLastBtn.addEventListener('click', function(ev){
							ev.preventDefault();
							try {
								var rows = wrapper.querySelectorAll('.activities-row');
								if (!rows || rows.length <= 1) return;
								var last = rows[rows.length - 1];
								if (last) last.remove();
								try { initActivityTranslators(); } catch(e){}
								updateRemoveState();
							} catch(e) { console.warn('remove last atividade failed', e); }
						});
					}
				} catch(e){}
			} catch(e){ console.error('rdo.js activities init error', e); }
		})();

			// Gerenciador de fotos: contador, preview, adicionar mais e remover selecionadas
			(function(){
				try {
					var fileInput = document.querySelector('input[type="file"][name="fotos"]');
					if (!fileInput) return;

					var MAX_FILES = 5;
					var selectedFiles = [];

					function ensurePreviewRoot(){
						var existing = document.getElementById('sup-fotos-preview');
						if (existing) return existing;
						var label = document.querySelector('label[for="sup-fotos"]');
						var container = document.createElement('div');
						container.id = 'sup-fotos-preview';
						container.style.display = 'flex';
						container.style.flexWrap = 'wrap';
						container.style.gap = '8px';
						container.style.alignItems = 'center';
						container.style.marginTop = '6px';
						if (label && label.parentNode) label.parentNode.appendChild(container);
						else {
							var form = document.getElementById('form-supervisor');
							if (form) form.appendChild(container);
						}
						return container;
					}

					function syncInputFiles(){
						try {
							var dt = new DataTransfer();
							selectedFiles.forEach(function(f){ try { dt.items.add(f); } catch(e){} });
							fileInput.files = dt.files;
						} catch(e){ console.warn('syncInputFiles failed', e); }
					}

					function renderPreviews(){
						var root = ensurePreviewRoot();
						root.innerHTML = '';
						var info = document.createElement('div');
						info.style.display = 'flex';
						info.style.alignItems = 'center';
						info.style.gap = '8px';
						var count = selectedFiles.length;
						var txt = document.createElement('span');
						txt.textContent = count + ' arquivo' + (count>1 ? 's' : '');
						txt.style.fontSize = '0.9rem';
						txt.style.color = '#333';
						info.appendChild(txt);
						var addBtn = document.createElement('button');
						addBtn.type = 'button';
						addBtn.id = 'sup-fotos-add-btn';
						addBtn.className = 'btn-rdo small';
						addBtn.style.marginLeft = '6px';
						addBtn.textContent = 'Adicionar fotos';
						addBtn.addEventListener('click', function(){ fileInput.click(); });
						info.appendChild(addBtn);
						root.appendChild(info);

						selectedFiles.slice(0, MAX_FILES).forEach(function(f, idx){
							var box = document.createElement('div');
							box.style.position = 'relative';
							box.style.width = '64px';
							box.style.height = '64px';
							box.style.borderRadius = '6px';
							box.style.overflow = 'hidden';
							box.style.border = '1px solid #ddd';
							var img = document.createElement('img');
							img.style.width = '100%';
							img.style.height = '100%';
							img.style.objectFit = 'cover';
							var reader = new FileReader();
							reader.onload = function(ev){ img.src = ev.target.result; };
							reader.readAsDataURL(f);
							box.appendChild(img);
							var btn = document.createElement('button');
							btn.type = 'button';
							btn.title = 'Remover foto';
							btn.textContent = '×';
							btn.style.position = 'absolute';
							btn.style.top = '2px';
							btn.style.right = '2px';
							btn.style.background = 'rgba(0,0,0,0.6)';
							btn.style.color = '#fff';
							btn.style.border = 'none';
							btn.style.borderRadius = '50%';
							btn.style.width = '20px';
							btn.style.height = '20px';
							btn.style.cursor = 'pointer';
							btn.addEventListener('click', function(){
								selectedFiles.splice(idx, 1);
								syncInputFiles();
								renderPreviews();
							});
							box.appendChild(btn);
							root.appendChild(box);
						});
						if (selectedFiles.length > MAX_FILES) {
							var hint = document.createElement('div');
							hint.textContent = 'Máx. ' + MAX_FILES + ' imagens serão enviadas; selecione menos.';
							hint.style.fontSize = '0.8rem';
							hint.style.color = '#b26a00';
							hint.style.marginLeft = '8px';
							root.appendChild(hint);
						}
					}

					fileInput.addEventListener('change', function(ev){
						try {
							var fl = ev.target.files ? Array.from(ev.target.files) : [];
							fl.forEach(function(f){
								if (!f) return;
								var exists = selectedFiles.some(function(sf){ return sf.name === f.name && sf.size === f.size && sf.type === f.type; });
								if (!exists) selectedFiles.push(f);
							});
							if (selectedFiles.length > MAX_FILES) selectedFiles = selectedFiles.slice(0, MAX_FILES);
							syncInputFiles();
							renderPreviews();
						} catch(e) { console.warn('sup-fotos change handler', e); }
					});

					if (fileInput.files && fileInput.files.length) {
						selectedFiles = Array.from(fileInput.files).slice(0, MAX_FILES);
						renderPreviews();
					}
				} catch(e){ console.warn('sup-fotos manager init failed', e); }
			})();

			// Ligar botão Recalcular Res. total (se existir)
			(function(){
				try {
					var btn = document.getElementById('btn-recalcular-res-total');
					if (!btn) return;
					btn.addEventListener('click', function(ev){
						ev.preventDefault();
						// forçar recomputo e sobrescrever
						try { if (window.computeResTotal) window.computeResTotal(); } catch(e){}
						showToast('Recalculado: resíduo total atualizado', 'success');
					});
				} catch(e){}
			})();

			// Calcular Res. total = Resíduo líquido + Resíduos sólidos
				// Also compute Resíduos sólidos automatically from Ensacamento: res_sol = ensacamento * 0.008
			(function(){
				try {
					var resLiq = document.getElementById('sup-res-liq');
					var resSol = document.getElementById('sup-res-sol');
					var resTotal = document.getElementById('sup-res-total');
					if (!resLiq || !resSol || !resTotal) return;
					// marcar edição manual
					function markUserEdited(el){ try { if (el && el.dataset) el.dataset.userEdited = '1'; } catch(e){} }
					resTotal.addEventListener('input', function(){ markUserEdited(resTotal); });
					resSol.addEventListener('input', function(){ try { if (resTotal.dataset && resTotal.dataset.userEdited === '1') return; compute(); } catch(e){} });
					resLiq.addEventListener('input', function(){ try { if (resTotal.dataset && resTotal.dataset.userEdited === '1') return; compute(); } catch(e){} });
					function compute(){
						try {
							var a = parseFloat(resLiq.value);
							var b = parseFloat(resSol.value);
							a = isFinite(a) ? a : 0;
							b = isFinite(b) ? b : 0;
							var total = Math.round((a + b) * 100) / 100;
							if (!resTotal.dataset || resTotal.dataset.userEdited !== '1') {
								resTotal.value = total;
							}
						} catch(e){}
					}
					// expor helper para chamadas externas
					try { window.computeResTotal = compute; } catch(e){}
					setTimeout(compute, 30);
				} catch(e) { }
			})();

			// Auto-calcular Res. sólidos a partir de Ensacamento (supervisor)
			(function(){
				try {
					var ensac = document.getElementById('sup-ensac');
					var resSol = document.getElementById('sup-res-sol');
					if (!ensac || !resSol) return;

					function computeSupResSol(){
						try {
							var e = parseFloat(ensac.value);
							e = isFinite(e) ? e : 0;
							var sol = Math.round((e * 0.008) * 100) / 100;
							resSol.value = sol;
							// dispatch input so total recomputes
							try { resSol.dispatchEvent(new Event('input', { bubbles: true })); } catch(e) { if (window.computeResTotal) try { window.computeResTotal(); } catch(e){} }
						} catch(e){}
					}

					ensac.addEventListener('input', computeSupResSol);
					// compute initial
					setTimeout(computeSupResSol, 40);
				} catch(e){}
			})();

			// Gerenciador de equipe: adicionar/remover membros, limitar número máximo, atualizar dica
			(function(){
				try {
					var wrapper = document.getElementById('equipe-wrapper');
					if (!wrapper) return;
					var footer = wrapper.querySelector('.team-footer');
					var hint = wrapper.querySelector('.team-limit-hint');
					var addBtn = document.getElementById('btn-add-membro');
					var max = 18;

					wrapper.addEventListener('click', function(ev){
						try {
							var rem = ev.target.closest && ev.target.closest('.btn-remove-membro');
							if (!rem) return;
							console.debug('team remove click (wrapper handler)', rem);
							var rows = wrapper.querySelectorAll('.team-row');
							if (rows.length <= 1) return; // keep at least one
							var row = rem.closest && rem.closest('.team-row');
							if (row) {
								row.remove();
								updateHint();
							}
						} catch(e){}
					});

					function updateHint(){
						try {
							var rows = wrapper.querySelectorAll('.team-row');
							if (!hint) return;
							var remaining = Math.max(0, max - rows.length);
							hint.textContent = rows.length >= max ? ('Máx. ' + max + ' membros') : ('Pode adicionar até ' + remaining + ' membro(s)');
							try {
								var addBtnLocal = document.getElementById('btn-add-membro');
								var remBtnLocal = document.getElementById('btn-remove-membro');
								if (addBtnLocal) addBtnLocal.disabled = (rows.length >= max);
								if (remBtnLocal) remBtnLocal.disabled = (rows.length <= 1);
							} catch(e){}
						} catch(e){}
					}

					function makeRemovable(row){

						if (!row) return;
						var btn = row.querySelector('.btn-remove-membro');
						if (!btn) return; 
						try {
							btn.type = 'button';
							btn.classList.add('btn-rdo');
							btn.classList.add('small');
							btn.classList.add('btn-remove-membro');
							btn.setAttribute('title', btn.getAttribute('title') || 'Remover membro');
							btn.style.cursor = btn.style.cursor || 'pointer';
						} catch(e){}
					};

					Array.from(wrapper.querySelectorAll('.team-row')).forEach(function(r){
						try {
							// Garantir que existam os campos esperados (selects ou inputs)
							var selNome = r.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
							var selFunc = r.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
							// Fallback legacy: se não houver, tentar marcar os dois primeiros campos como tais
							if (!selNome) {
								var firstField = r.querySelector('select, input[type="text"]');
								if (firstField) firstField.name = 'equipe_nome[]';
							}
							if (!selFunc) {
								// segundo campo do tipo select/input
								var fields = r.querySelectorAll('select, input[type="text"]');
								if (fields && fields.length > 1) fields[1].name = 'equipe_funcao[]';
							}
						} catch(e){}
						makeRemovable(r);
					});

					if (addBtn) addBtn.addEventListener('click', function(){
						var rows = wrapper.querySelectorAll('.team-row');
						if (rows.length >= max) return;
						var first = rows[0];
						if (!first) return;
						var clone = first.cloneNode(true);
						Array.from(clone.querySelectorAll('input,select')).forEach(function(el, idx){
							try {
								var tag = (el.tagName || '').toLowerCase();
								if (tag === 'select') { el.selectedIndex = 0; }
								else { el.value = ''; }
								if (!el.name) {
									if (idx === 0) el.name = 'equipe_nome[]'; else el.name = 'equipe_funcao[]';
								}
							} catch(e){}
						});
						wrapper.insertBefore(clone, footer || null);
						updateHint();
					});
					var globalRemove = document.getElementById('btn-remove-membro');
					if (globalRemove) globalRemove.addEventListener('click', function(ev){
						try {
							var rows = wrapper.querySelectorAll('.team-row');
							if (!rows || rows.length <= 1) return;
							var last = rows[rows.length - 1];
							if (last) last.remove();
							updateHint();
						} catch(e){}
					});

					updateHint();
				} catch(e){ console.error('team manager init failed', e); }
			})();

			// Conectar botão visível 'Adicionar foto' ao input de fotos
			(function(){
				try {
					var addFotoBtn = document.getElementById('btn-add-foto');
					var fotoInput = document.getElementById('sup-fotos');
					if (addFotoBtn && fotoInput) {
						addFotoBtn.addEventListener('click', function(){ fotoInput.click(); });
					}
				} catch(e){ console.warn('btn-add-foto init failed', e); }
			})();

		// input[name='fotos'] - exibir contagem e miniaturas no modal supervisor
		(function(){
			try {
				var inputFotos = document.querySelector('input[name="fotos"]');
				var overlay = document.getElementById('modal-supervisor-overlay');
				if (!inputFotos || !overlay) return;
				// flag global para desativar previews de fotos se suspeitarmos de travamento (pode ser setada via console)
				try { if (typeof window !== 'undefined' && typeof window.RDO_DISABLE_PHOTO_PREVIEW === 'undefined') window.RDO_DISABLE_PHOTO_PREVIEW = false; } catch(e){}

				// Exibir contagem e miniaturas (até 5) de arquivos selecionados
				inputFotos.addEventListener('change', function(){
					try {
						if (typeof window !== 'undefined' && window.RDO_DISABLE_PHOTO_PREVIEW) return;
						var files = Array.from(inputFotos.files);
						var countEl = overlay.querySelector('.foto-count');
						var previewEl = overlay.querySelector('.foto-preview');
						if (countEl) countEl.textContent = files.length > 0 ? files.length + ' arquivo(s) selecionado(s)' : '';
						if (previewEl) {
							// Limpar miniaturas existentes
							while (previewEl.firstChild) { previewEl.removeChild(previewEl.firstChild); }
							// Adicionar novas miniaturas
							files.slice(0, 5).forEach(function(file){
								var reader = new FileReader();
								reader.onload = function(e) {
									var img = document.createElement('img');
									img.src = e.target.result;
									img.className = 'miniatura';
									previewEl.appendChild(img);
								};
								reader.readAsDataURL(file);
							});
						}
					} catch(e) {}
				});

				// Limpar contagem e miniaturas ao fechar o modal
				var closeModalBtns = overlay.querySelectorAll('.modal-close, .modal-cancel');
				closeModalBtns.forEach(function(btn){
					btn.addEventListener('click', function(){
						setTimeout(function(){
							if (typeof window !== 'undefined' && window.RDO_DISABLE_PHOTO_PREVIEW) return;
							var countEl = overlay.querySelector('.foto-count');
							var previewEl = overlay.querySelector('.foto-preview');
							if (countEl) countEl.textContent = '';
							if (previewEl) {
								while (previewEl.firstChild) { previewEl.removeChild(previewEl.firstChild); }
							}
						}, 300);
					});
				});
			} catch(e) { console.error('rdo.js fotos input init error', e); }
		})();

		// Tanque tipo behavior: quando 'Salão' limpar/desabilitar campos relacionados
		(function(){
			try {
				var tipo = document.getElementById('sup-tipo-tanque');
				var ncomp = document.getElementById('sup-n-comp');
				var gav = document.getElementById('sup-gavetas');
				var pat = document.getElementById('sup-patamar');
				function applyTipoState(){
					try {
						var v = (tipo && tipo.value) ? String(tipo.value).trim() : '';
						if (!v) return;
						if (v === 'Salão' || v.toLowerCase() === 'salão') {
							var closed = [];
							if (ncomp) { ncomp.value = ''; ncomp.disabled = true; ncomp.setAttribute('aria-disabled','true'); var p = ncomp.closest('.form-field'); if (p) p.classList.add('field-closed'); closed.push('Nº compartimentos'); }
							if (gav) { gav.value = ''; gav.disabled = true; gav.setAttribute('aria-disabled','true'); var p2 = gav.closest('.form-field'); if (p2) p2.classList.add('field-closed'); closed.push('Gavetas'); }
							if (pat) { pat.value = ''; pat.disabled = true; pat.setAttribute('aria-disabled','true'); var p3 = pat.closest('.form-field'); if (p3) p3.classList.add('field-closed'); closed.push('Patamar'); }
							if (closed.length && typeof showToast === 'function') {
								showToast('Campos fechados: ' + closed.join(', '), 'info');
							}
						} else {
							var opened = [];
							if (ncomp) { ncomp.disabled = false; ncomp.removeAttribute('aria-disabled'); var p = ncomp.closest('.form-field'); if (p) p.classList.remove('field-closed'); opened.push('Nº compartimentos'); }
							if (gav) { gav.disabled = false; gav.removeAttribute('aria-disabled'); var p2 = gav.closest('.form-field'); if (p2) p2.classList.remove('field-closed'); opened.push('Gavetas'); }
							if (pat) { pat.disabled = false; pat.removeAttribute('aria-disabled'); var p3 = pat.closest('.form-field'); if (p3) p3.classList.remove('field-closed'); opened.push('Patamar'); }
							if (opened.length && typeof showToast === 'function') {
								showToast('Campos reabertos: ' + opened.join(', '), 'success');
							}
						}
					} catch(e){}
				}
				if (tipo) {
					tipo.addEventListener('change', applyTipoState);
					setTimeout(applyTipoState, 40);
				}

				// Espaço confinado: se selecionado 'nao' fechar TODOS os campos de Tanque & Ambiente
				try {
					var espaco = document.getElementById('sup-espaco-conf');
					var tanqueSection = document.getElementById('sec-tanque');
					function applyEspacoState(){
						try {
							if (!tanqueSection || !espaco) return;
							var v = (espaco.value || '').toString().trim().toLowerCase();

							// targets: entrada/saida inputs inside #ec-times-grid and the fields from
							// #sup-1entrada up to #sup-o2 (inclusive)
							var timeInputs = Array.from(tanqueSection.querySelectorAll('#ec-times-grid input[name="entrada_confinado[]"], #ec-times-grid input[name="saida_confinado[]"]'));

							var otherIds = ['sup-1entrada','sup-7entrada','sup-operadores','sup-h2s','sup-lel','sup-co','sup-o2'];
							var otherElems = otherIds.map(function(id){ return document.getElementById(id); }).filter(Boolean);

							if (v === 'nao') {
								// clear + disable the targeted inputs, mark visually closed
								var closed = [];

								timeInputs.forEach(function(el){
									try {
										el.value = '';
										el.disabled = true; el.setAttribute('aria-disabled','true');
										var p = el.closest('.time-field') || el.closest('.form-field');
										if (p) p.classList.add('field-closed');
									} catch(e){}
								});
								if (timeInputs.length) closed.push('Horários de Entrada/Saída (EC)');

								otherElems.forEach(function(el){
									try {
										var tag = (el.tagName||'').toLowerCase();
										if (tag === 'select') el.selectedIndex = 0;
										else el.value = '';
										el.disabled = true; el.setAttribute('aria-disabled','true');
										var p = el.closest('.form-field') || el.closest('.time-field'); if (p) p.classList.add('field-closed');
									} catch(e){}
								});
								if (otherElems.length) closed.push('Medições / Contagem (1E/7E, operadores, H2S, LEL, CO, O2)');

								if (closed.length && typeof showToast === 'function') showToast('Campos fechados: ' + closed.join('; '), 'info');
							} else {
								timeInputs.forEach(function(el){
									try { el.disabled = false; el.removeAttribute('aria-disabled'); var p = el.closest('.time-field') || el.closest('.form-field'); if (p) p.classList.remove('field-closed'); } catch(e){}
								});
								otherElems.forEach(function(el){
									try { el.disabled = false; el.removeAttribute('aria-disabled'); var p = el.closest('.form-field') || el.closest('.time-field'); if (p) p.classList.remove('field-closed'); } catch(e){}
								});
								if (typeof showToast === 'function') showToast('Campos de Entrada/Saída e Medições reabertos', 'success');
							}
						} catch(e){ console.warn('applyEspacoState failed', e); }
					}
					if (espaco) { espaco.addEventListener('change', applyEspacoState); setTimeout(applyEspacoState, 40); }
				} catch(e) {}

				// Calcular automaticamente Bombeio e Resíduo líquido a partir do Tempo de bomba
				(function(){
					try {
						var tempoInput = document.getElementById('sup-tempo-bomba');
						var bombeioInput = document.getElementById('sup-bombeio');
						var resLiqInput = document.getElementById('sup-res-liq');
						if (!tempoInput || !bombeioInput || !resLiqInput) return;

						// campos automáticos: não permitir edição manual (template define readonly)

						function computeAndFill(){
							try {
								var val = parseFloat(tempoInput.value);
								if (!isFinite(val)) return;
								var vazaoInput = document.getElementById('sup-vazao-bombeio');
								var vazao = vazaoInput ? parseFloat(vazaoInput.value) : NaN;
								// se vazão não informada ou inválida, usar fallback de 36 m3/h
								if (!isFinite(vazao)) {
									vazao = 36;
								}
								var computed = Math.round((val * vazao) * 100) / 100; // 2 casas decimais
								// preencher sempre (campos são readonly para usuários)
								bombeioInput.value = computed;
								resLiqInput.value = computed;
								// dispatch input so any listeners (res total) recompute
								try { resLiqInput.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) { if (window.computeResTotal) try { window.computeResTotal(); } catch(e){} }
							} catch(e){}
						}

						tempoInput.addEventListener('input', function(){
							// se tempo inválido ou vazão ausente, não sobrescrever
							computeAndFill();
						});
						try { if (document.getElementById('sup-vazao-bombeio')) document.getElementById('sup-vazao-bombeio').addEventListener('input', computeAndFill); } catch(e){}

						// conectar handler ao botão de recalcular existente (inserido no template)
						try {
							var templateBtn = document.getElementById('btn-recalcular-bombeio');
							if (templateBtn) {
								templateBtn.addEventListener('click', function(ev){
									ev.preventDefault();
									// forçar sobrescrita
									try { if (bombeioInput && bombeioInput.dataset) delete bombeioInput.dataset.userEdited; if (resLiqInput && resLiqInput.dataset) delete resLiqInput.dataset.userEdited; } catch(e){}
									computeAndFill();
									showToast('Recalculado: bombeio e resíduo líquido atualizados', 'success');
								});
							}
						} catch(e) { /* ignore */ }

						// aplicar inicialmente caso já exista valor (prefill)
						setTimeout(computeAndFill, 30);
					} catch(e) { console.warn('auto bombeio init failed', e); }
				})();

				// Permissão de Trabalho: fechar campos quando 'Houve abertura de PT?' == 'nao'
				(function(){
					try {
						var ptSelect = document.getElementById('sup-pt-abertura');
						if (!ptSelect) return;

						var turnoGroup = document.querySelector('.inline-options[role="group"][aria-label="Turnos com abertura"]');
						var ptManha = document.getElementById('sup-pt-manha');
						var ptTarde = document.getElementById('sup-pt-tarde');
						var ptNoite = document.getElementById('sup-pt-noite');

						function applyPtState(){
							try {
								var v = (ptSelect.value || '').toString().trim().toLowerCase();
								if (v === 'nao') {
									if (turnoGroup) {
										Array.from(turnoGroup.querySelectorAll('input[type=checkbox]')).forEach(function(cb){
											cb.checked = false;
											cb.disabled = true; cb.setAttribute('aria-disabled','true');
											var p = cb.closest('.form-field') || turnoGroup; if (p) p.classList.add('field-closed');
										});
									}

									[ptManha, ptTarde, ptNoite].forEach(function(inp){ if (!inp) return; inp.value = ''; inp.disabled = true; inp.setAttribute('aria-disabled','true'); var p = inp.closest('.form-field'); if (p) p.classList.add('field-closed'); });
									if (typeof showToast === 'function') showToast('Campos de PT fechados: sem abertura registrada', 'info');
								} else {

									if (turnoGroup) {
										Array.from(turnoGroup.querySelectorAll('input[type=checkbox]')).forEach(function(cb){ cb.disabled = false; cb.removeAttribute('aria-disabled'); var p = cb.closest('.form-field') || turnoGroup; if (p) p.classList.remove('field-closed'); });
									}
									[ptManha, ptTarde, ptNoite].forEach(function(inp){ if (!inp) return; inp.disabled = false; inp.removeAttribute('aria-disabled'); var p = inp.closest('.form-field'); if (p) p.classList.remove('field-closed'); });
									if (typeof showToast === 'function') showToast('Campos de PT reabertos', 'success');
								}
							} catch(e) { console.warn('applyPtState failed', e); }
						}

						ptSelect.addEventListener('change', applyPtState);
						// aplicar ao carregar caso já exista valor
						setTimeout(applyPtState, 30);
					} catch(e) { console.warn('pt close init failed', e); }
				})();
			} catch(e){ console.warn('sup tipo-tanque init failed', e); }
		})();

	// Botão de notificação sempre visível com contador de OS pendentes
	(function(){
		try {
			const safeLocal = {
				get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
				set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
				remove(k) { try { localStorage.removeItem(k); } catch (e) {} }
			};

			(function(){
				try {
					var sections = Array.from(document.querySelectorAll('.rdo-section'));
					sections.forEach(function(sec){
						try {
							var head = sec.querySelector('.rdo-section__head');
							if (!head) return;
							head.style.cursor = 'pointer';
							head.setAttribute('role','button');
							head.setAttribute('aria-expanded', sec.classList.contains('open') ? 'true' : 'false');
							head.addEventListener('click', function(ev){
								sec.classList.toggle('open');
								head.setAttribute('aria-expanded', sec.classList.contains('open') ? 'true' : 'false');
								try { sec.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch(e){}
							});
						} catch(e){}
					});
					
					window.rdoOpenSection = function(name){
						try {
							var el = document.querySelector('[data-section="' + name + '"]');
							if (!el) return false;
							if (!el.classList.contains('open')) el.classList.add('open');
							el.scrollIntoView({ behavior: 'smooth', block: 'start' });
							return true;
						} catch(e){ return false; }
					};

					var recBtn = document.getElementById('btn-recalcular-calculos');
					if (recBtn) recBtn.addEventListener('click', function(ev){
						try { window.rdoOpenSection('calculos'); } catch(e){}
					});
				} catch(e){ console.warn('collapsible sections init failed', e); }
			})();

			// Handler de submit do formulário Supervisor -> cria/edita linha na tabela e tenta persistir via AJAX
			(function(){
				try {
					var form = document.getElementById('form-supervisor');
					if (!form) return;

					function getCSRF() {
						var el = form.querySelector('input[name=csrfmiddlewaretoken]');
						return el ? el.value : (document.querySelector('input[name=csrfmiddlewaretoken]')||{}).value || '';
					}

					form.addEventListener('submit', async function(ev){
						ev.preventDefault();
						var hid = document.getElementById('sup-rdo-id');
						var isEdit = hid && hid.value;
						var table = document.querySelector('table');
						var tbody = table ? table.querySelector('tbody') : null;

						// Mesmo que não haja tabela/tbody (ex.: view alternativa ou mobile), devemos prosseguir com o salvamento
						// Pular apenas a parte visual de inserção/atualização na tabela.
						var hasTable = !!tbody;

						var submitBtn = form.querySelector('button[type="submit"]');
						var originalBtnText = submitBtn ? submitBtn.textContent : null;
						if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Salvando...'; }

						var payload = buildSupervisorFormData(form);
						// timeout/abort
						var controller = new AbortController();
						var timeout = setTimeout(function(){ try{ controller.abort(); }catch(e){} }, 30000);

						try {
							// debug keys (no-op on failure)
							try {
								var entries = [];
								try { payload.forEach(function(v,k){ entries.push(k); }); } catch(e) { try { for (var p of payload.entries()) entries.push(p[0]); } catch(e){} }
								var counts = {}; entries.forEach(function(k){ counts[k] = (counts[k]||0) + 1; });
								console.log('DEBUG: buildSupervisorFormData keys count', counts);
							} catch(e){}

							if (isEdit) {
								payload.append('rdo_id', hid.value);
								var url = '/rdo/update_ajax/';
								var resp = null;
								try {
									resp = await fetch(url, { method: 'POST', body: payload, credentials: 'same-origin', headers: { 'X-Requested-With':'XMLHttpRequest', 'X-CSRFToken': getCSRF() }, signal: controller.signal });
								} catch(err) {
									if (err.name === 'AbortError') { showToast('Tempo de requisição expirou. Tente novamente.', 'error'); return; }
									throw err;
								}
								var data = null;
								try { data = await resp.json(); } catch(e) { data = null; }
								if (resp && resp.ok && data && data.success) {
									showToast(data.message || 'RDO atualizado com sucesso', 'success');
									// atualizar linha na tabela se existir
									try {
										if (hasTable) {
											var row = tbody.querySelector('tr[data-rdo-id="' + hid.value + '"]');
											if (row && data.rdo) {
												row.dataset.numeroOs = data.rdo.numero_os || row.dataset.numeroOs || '';
												row.dataset.empresa = data.rdo.empresa || row.dataset.empresa || '';
												row.dataset.unidade = data.rdo.unidade || row.dataset.unidade || '';
												row.dataset.supervisor = data.rdo.supervisor || row.dataset.supervisor || '';
												// atualizar exibição mínima: data e turno
												var cells = row.querySelectorAll('td');
												if (cells && cells.length > 7) {
													try { cells[7].textContent = (data.rdo && data.rdo.data) ? new Date(data.rdo.data).toLocaleDateString() : cells[7].textContent; } catch(e){}
													try { cells[9].textContent = (data.rdo && data.rdo.turno) ? data.rdo.turno : cells[9].textContent; } catch(e){}
												}
											}
										}
									} catch(e){}
								} else {
									var msg = (data && data.error) ? data.error : 'Falha ao atualizar RDO';
									showToast(msg, 'error');
								}
							} else {
								// criar linha visual antes de persistir (mesma UX anterior) — somente se houver tabela
								if (hasTable) {
									var numeroOs = document.getElementById('sup-rdo') ? document.getElementById('sup-rdo').value : '';
									var turno = document.getElementById('sup-turno') ? document.getElementById('sup-turno').value : '';
									var contrato = document.getElementById('sup-contrato-po') ? document.getElementById('sup-contrato-po').value : '';
									var empresa = document.getElementById('sup-context-empresa') ? document.getElementById('sup-context-empresa').textContent : '';
									var unidade = document.getElementById('sup-context-unidade') ? document.getElementById('sup-context-unidade').textContent : '';
									var supervisor = document.getElementById('sup-context-supervisor') ? document.getElementById('sup-context-supervisor').textContent : '';
									var newTr = document.createElement('tr');
									newTr.dataset.rdoId = '';
									newTr.dataset.numeroOs = numeroOs || '';
									newTr.dataset.empresa = empresa || '';
									newTr.dataset.unidade = unidade || '';
									newTr.dataset.supervisor = supervisor || '';
									newTr.innerHTML = `
										<td>-</td>
										<td>${numeroOs || '-'}</td>
										<td>${contrato || '-'}</td>
										<td>${empresa || '-'}</td>
										<td>${unidade || '-'}</td>
										<td>${supervisor || '-'}</td>
										<td>-</td>
										<td>${new Date().toLocaleDateString()}</td>
										<td>${document.getElementById('sup-rdo') ? document.getElementById('sup-rdo').value || '-' : '-'}</td>
										<td>${turno || '-'}</td>
										<td>${document.getElementById('sup-tanque-cod') ? document.getElementById('sup-tanque-cod').value || '-' : '-'}</td>
										<td>${document.getElementById('sup-tanque-nome') ? document.getElementById('sup-tanque-nome').value || '-' : '-'}</td>
										<td>${document.getElementById('sup-tipo-tanque') ? document.getElementById('sup-tipo-tanque').value || '-' : '-'}</td>
										<td>${document.getElementById('sup-n-comp') ? document.getElementById('sup-n-comp').value || '-' : '-'}</td>
										<td>${document.getElementById('sup-gavetas') ? document.getElementById('sup-gavetas').value || '-' : '-'}</td>
										<td>${document.getElementById('sup-patamar') ? document.getElementById('sup-patamar').value || '-' : '-'}</td>
										<td>${document.getElementById('sup-volume') ? document.getElementById('sup-volume').value || '-' : '-'}</td>
										<td>${(document.getElementById('sup-servico') && document.getElementById('sup-servico').options[document.getElementById('sup-servico').selectedIndex]) ? document.getElementById('sup-servico').options[document.getElementById('sup-servico').selectedIndex].text : '-'}</td>
										<td>${(document.getElementById('sup-metodo') && document.getElementById('sup-metodo').options[document.getElementById('sup-metodo').selectedIndex]) ? document.getElementById('sup-metodo').options[document.getElementById('sup-metodo').selectedIndex].text : '-'}</td>
										<td>-</td>
										<td>-</td>
										<td>-</td>
										<td class="action-cell"><button class="action-btn edit" type="button"><span class="material-icons" aria-hidden="true">edit</span></button></td>
										<td class="action-cell"><button class="action-btn view" type="button"><span class="material-icons" aria-hidden="true">visibility</span></button></td>
									`;
									var first = tbody.querySelector('tr');
									tbody.insertBefore(newTr, first || null);
								}

								var url = '/rdo/create_ajax/';
								var resp = null;
								try {
									resp = await fetch(url, { method: 'POST', body: payload, credentials: 'same-origin', headers: { 'X-Requested-With':'XMLHttpRequest', 'X-CSRFToken': getCSRF() }, signal: controller.signal });
								} catch(err) {
									if (err.name === 'AbortError') { showToast('Tempo de requisição expirou. Tente novamente.', 'error'); return; }
									throw err;
								}
								var data = null;
								try { data = await resp.json(); } catch(e) { data = null; }
								if (resp && resp.ok && data && data.success) {
									try { if (data.id) newTr.dataset.rdoId = data.id; } catch(e){}
									showToast(data.message || 'Tanque salvo', 'success');
									// Atualizar contagem local de RDO para esta OS e ajustar cartões mobile (manter somente o mais recente)
									try {
										var osIdVal = (document.getElementById('sup-ordem-id')||{}).value || '';
										var nextRdoVal = (document.getElementById('sup-rdo')||{}).value || '';
										if (osIdVal && nextRdoVal) {
											// Atualizar atributo data-rdo-count em todos os elementos relacionados (sem usar CSS.escape)
											var allWithOs = Array.from(document.querySelectorAll('[data-os-id]'));
											allWithOs.forEach(function(el){
												try {
													if (String(el.getAttribute('data-os-id')) === String(osIdVal)) el.setAttribute('data-rdo-count', String(nextRdoVal));
												} catch(e){}
											});
											try { if (newTr) newTr.setAttribute('data-rdo-count', String(nextRdoVal)); } catch(e){}
											// Ajustar cartões mobile RDO-summary: manter apenas um cartão por OS e atualizá-lo para o novo número
											try {
												var summarySelector = '.rdo-mobile-rdo-list .rdo-summary';
												var summaries = Array.from(document.querySelectorAll(summarySelector)).filter(function(c){ try { return String(c.getAttribute('data-os-id')) === String(osIdVal); } catch(e){ return false; } });
												if (summaries && summaries.length) {
													// atualizar o primeiro (mais recente) e remover os demais
													summaries.forEach(function(card, idx){
														try {
															if (idx === 0) {
																card.setAttribute('data-rdo-count', String(nextRdoVal));
																// atualizar labels visuais
																var headTurno = card.querySelector('.head-right .turno') || card.querySelector('.turno');
																if (headTurno) headTurno.textContent = 'RDO ' + String(nextRdoVal);
																var pill = card.querySelector('.rdo-pill');
																if (pill) pill.textContent = 'RDO ' + String(nextRdoVal);
														} else {
															card.parentNode && card.parentNode.removeChild(card);
														}
													} catch(e){}
													});
												} else {
													// se não existia cartão summary, nada a fazer (opcional: poderíamos criar um novo card)
												}
											} catch(e){ console.warn('update mobile summaries failed', e); }
										}
									} catch(e){ console.warn('update data-rdo-count failed', e); }
									try {
										var cnt = parseInt(localStorage.getItem('rdo_pending_count')||'0',10);
										cnt = Math.max(0, cnt-1);
										localStorage.setItem('rdo_pending_count', String(cnt));
										if (window.updateNotificationCount) window.updateNotificationCount();
									} catch(e){}
								} else {
									var msg = (data && data.error) ? data.error : 'Falha ao salvar tanque';
									showToast(msg, 'error');
								}
							}
						} catch(e) {
							console.warn('rdo submit AJAX failed', e);
							showToast('Erro ao salvar RDO', 'error');
						} finally {
							clearTimeout(timeout);
							if (submitBtn) { submitBtn.disabled = false; if (originalBtnText !== null) submitBtn.textContent = originalBtnText; }
							// fechar modal
							var overlay = document.getElementById('modal-supervisor-overlay');
							if (overlay) { overlay.classList.remove('open'); overlay.classList.add('is-hidden'); overlay.setAttribute('aria-hidden','true'); }
						}
					});
				} catch(e){ console.error('rdo.js form submit init error', e); }
			})();

			// Helper: construir FormData a partir do form supervisor (reutilizável)
			// Preferir o helper externo `window.buildSupervisorFormDataExternal` se disponível.
			function buildSupervisorFormData(form) {
				if (window.buildSupervisorFormDataExternal && typeof window.buildSupervisorFormDataExternal === 'function') {
					try { return window.buildSupervisorFormDataExternal(form); } catch (e) { console.warn('external buildSupervisorFormData failed, falling back', e); }
				}

				// Fallback local (mantido para compatibilidade)
				var payload = new FormData();
				Array.from(form.elements).forEach(function(el){
					if (!el.name) return;
					if (el.type === 'file') return; // arquivos anexados depois
					if (el.type === 'checkbox' || el.type === 'radio') {
						if (!el.checked) return;
					}
					payload.append(el.name, el.value);
				});

				// anexar arquivos (fotos) - suporta input multiple name="fotos" ou fallback foto1..foto5
				var files = [];
				var inputFotos = form.querySelectorAll('input[type=file][name="fotos"]');
				if (inputFotos && inputFotos.length) {
					inputFotos.forEach(function(inp){ if (inp.files && inp.files.length) Array.from(inp.files).forEach(function(f){ files.push(f); }); });
				}
				if (!files.length) {
					for (var i=1;i<=5;i++) {
						var fIn = form.querySelector('input[type=file][name="foto' + i + '"]');
						if (fIn && fIn.files && fIn.files.length) files.push(fIn.files[0]);
					}
				}
				files.forEach(function(f){ payload.append('fotos', f); payload.append('fotos[]', f); });

				// anexar entradas/saidas de confinamento
				var entradas = form.querySelectorAll('input[name="entrada_confinado[]"], input[name="entrada_confinado"]');
				entradas.forEach(function(e){ if (e.value) payload.append('entrada_confinado[]', e.value); });
				var saidas = form.querySelectorAll('input[name="saida_confinado[]"], input[name="saida_confinado"]');
				saidas.forEach(function(s){ if (s.value) payload.append('saida_confinado[]', s.value); });

				return payload;
			}

			// Gerar uma chave canônica de login a partir do nome exibido
			function canonicalLoginFromName(name){
				if (!name) return '';
				try {
					var s = String(name || '');
					// remover acentos utilizando normalização Unicode
					try { s = s.normalize('NFD').replace(/\p{Diacritic}/gu, ''); } catch(e) { /* fallback simples */ s = s.replace(/[\u0300-\u036f]/g,''); }
					// transformar em minúsculas
					s = s.toLowerCase();
					// substituir qualquer sequência de não letras/dígitos por ponto
					s = s.replace(/[^a-z0-9]+/g, '.');
					// colapsar vários pontos e remover nas bordas
					s = s.replace(/\.{2,}/g, '.').replace(/^\.|\.$/g, '');
					return s;
				} catch(e){ try { return String(name).toLowerCase().replace(/[^a-z0-9]+/g,'.'); } catch(e){ return String(name); } }
			}

				// Editor: popular campos do form a partir do objeto retornado pela API
				function populateEditorFromData(r){
					if (!r) return;
					try {
						// simple mapping: [elementId, rProperty]
						var map = [
							['edit-rdo','rdo'],
							['edit-data-inicio','data_inicio'],
							['edit-previsao-termino','previsao_termino'],
							['edit-contrato-po','po'],
							['edit-tanque-cod','tanque_codigo'],
							['edit-tanque-nome','nome_tanque'],
							['edit-tipo-tanque','tipo_tanque'],
							['edit-n-comp','numero_compartimentos'],
							['edit-gavetas','gavetas'],
							['edit-patamar','patamares'],
							['edit-volume','volume_tanque_exec'],
							['edit-servico','servico_exec'],
							['edit-metodo','metodo_exec'],
							['edit-operadores','operadores_simultaneos'],
							['edit-h2s','H2S_ppm'],
							['edit-lel','LEL'],
							['edit-co','CO_ppm'],
							['edit-o2','O2_percent'],
							['edit-observacoes-pt','observacoes_pt'],
							['edit-observacoes-en','observacoes_en'],
							['edit-planejamento-pt','planejamento_pt'],
							['edit-planejamento-en','planejamento_en'],
							// Operacionais
							['edit-tempo-bomba','tempo_bomba'],
							['edit-bombeio','bombeio'],
							['edit-res-liq','total_liquido'],
							['edit-ensac','ensacamento'],
							['edit-tambores','tambores'],
							['edit-res-sol','total_solidos'],
							['edit-res-total','total_residuos']
						];
						map.forEach(function(pair){
							var el = document.getElementById(pair[0]);
							if (!el) return;
							var v = r[pair[1]];
							if (v === null || v === undefined) return;
							try {
								if (el.tagName && el.tagName.toLowerCase() === 'select') {
									el.value = String(v);
								} else if (el.tagName && el.tagName.toLowerCase() === 'textarea') {
									el.value = String(v);
								} else {
									el.value = String(v);
								}
							} catch(e){}
						});

						// Turno (mapear para valores do select: 'diurno' | 'noturno')
						try {
							var turn = document.getElementById('edit-turno');
							if (turn && r.turno) {
								var val = String(r.turno).toLowerCase();
								if (val.indexOf('diurno') > -1) turn.value = 'diurno';
								else if (val.indexOf('noturno') > -1) turn.value = 'noturno';
							}
						} catch(e){}

						// Sentido limpeza: preferir valor booleano exposto pelo backend
						// (sentido_limpeza_bool). Para compatibilidade, aceitar também
						// o rótulo textual em sentido_limpeza.
						try {
							var sel = document.getElementById('edit-sentido');
							if (sel) {
								// Priorizar booleano
								if (typeof r.sentido_limpeza_bool !== 'undefined' && r.sentido_limpeza_bool !== null) {
									sel.value = (r.sentido_limpeza_bool === true) ? 'vante-re' : (r.sentido_limpeza_bool === false ? 're-vante' : '');
								} else if (r.sentido_limpeza) {
									var s = String(r.sentido_limpeza).toLowerCase();
									sel.value = (s.indexOf('vante') > -1) ? 'vante-re' : (s.indexOf('ré')>-1 || s.indexOf('re')>-1 ? 're-vante' : '');
								}
							}
						} catch(e){}
 
						// Espaço confinado (booleano -> 'sim'/'nao')
						try {
							var ecSel = document.getElementById('edit-espaco-conf');
							if (ecSel && typeof r.confinado !== 'undefined') {
								ecSel.value = (r.confinado === true || String(r.confinado).toLowerCase() === 'sim') ? 'sim' : (r.confinado === false ? 'nao' : '');
							}
						} catch(e){}

						// Contexto (preencher elementos span/div apenas para exibição
						try { if (r.numero_os && document.getElementById('edit-context-os')) document.getElementById('edit-context-os').textContent = r.numero_os; } catch(e){}
						try { if (r.empresa && document.getElementById('edit-context-empresa')) document.getElementById('edit-context-empresa').textContent = r.empresa; } catch(e){}
						try { if (r.unidade && document.getElementById('edit-context-unidade')) document.getElementById('edit-context-unidade').textContent = r.unidade; } catch(e){}

						// If some fields are still empty, try to fallback to the last clicked table row's data-* attributes
						try {
							var lastRow = (typeof window !== 'undefined') ? window.__rdo_last_edit_row : null;
							if (lastRow && lastRow.dataset) {
								var ds = lastRow.dataset;
								// list of mappings: [elementId, datasetKey]
								var fallbacks = [
									['edit-tanque-nome','tanqueNome'], ['edit-tanque-cod','tanqueCodigo'], ['edit-tipo-tanque','tipoTanque'], ['edit-volume','volume'],
									['edit-operadores','operadores'], ['edit-servico','servico'], ['edit-metodo','metodo'],
									['edit-h2s','h2s'], ['edit-lel','lel'], ['edit-co','co'], ['edit-o2','o2'], ['edit-contrato-po','po']
								];
								fallbacks.forEach(function(pair){
									try {
										var el = document.getElementById(pair[0]);
										if (!el) return;
										if (el.value && String(el.value).trim()) return; // already filled
										var key = pair[1];
										var v = ds[key] || ds[key.replace(/[A-Z]/g,function(m){return '-' + m.toLowerCase();})] || ds[pair[1].toLowerCase()] || ds[pair[1].replace(/_/g,'-')];
										if (v) el.value = v;
									} catch(e){}
								});
							}
						} catch(e){}

						// preencher horários de espaço confinado (entradas/saidas)
						try {
							var entradas = document.querySelectorAll('#edit-ec-times-grid input[name="entrada_confinado[]"]');
							var saidas = document.querySelectorAll('#edit-ec-times-grid input[name="saida_confinado[]"]');
							var enArr = [];
							var saArr = [];
							if (r.ec_times && typeof r.ec_times === 'object') {
								for (var idx=1; idx<=entradas.length; idx++) { enArr.push(r.ec_times['entrada_'+idx] || ''); saArr.push(r.ec_times['saida_'+idx] || ''); }
							} else if (Array.isArray(r.entrada_confinado) || Array.isArray(r.saida_confinado)) {
								enArr = Array.isArray(r.entrada_confinado) ? r.entrada_confinado : [];
								saArr = Array.isArray(r.saida_confinado) ? r.saida_confinado : [];
							}
							for (var i=0;i<entradas.length;i++) { try { entradas[i].value = enArr[i] || ''; } catch(e){} }
							for (var j=0;j<saidas.length;j++) { try { saidas[j].value = saArr[j] || ''; } catch(e){} }
						} catch(e){}

						// Preencher atividades: reconstruir linhas no editor com os dados retornados
						try {
							var acts = r.atividades || r.activities || r.atividades_list || [];
							var wrapper = document.getElementById('edit-atividades-wrapper');
							// If backend provides atividades_choices, ensure selects have options
							try {
								if (Array.isArray(r.atividades_choices) && r.atividades_choices.length && wrapper) {
									var protoSel = wrapper.querySelector('.atividade-nome-select');
									if (protoSel) {
										// clear existing options except first placeholder
										var placeholder = protoSel.querySelector('option');
										var optsHtml = '';
										if (placeholder) optsHtml = placeholder.outerHTML;
										r.atividades_choices.forEach(function(item){
											try {
												var val = Array.isArray(item) ? item[0] : (item.value || item.key || '');
												var lab = Array.isArray(item) ? item[1] : (item.label || String(val));
												optsHtml += '<option value="'+String(val)+'">'+String(lab)+'</option>';
											} catch(e){}
										});
										// apply to all existing selects in wrapper
										Array.from(wrapper.querySelectorAll('.atividade-nome-select')).forEach(function(s){ try { s.innerHTML = optsHtml; } catch(e){} });
									}
								}
							} catch(e){}
							if (wrapper && Array.isArray(acts) && acts.length) {
								// remove todas as activities-row existentes
								var existing = Array.from(wrapper.querySelectorAll('.activities-row'));
								existing.forEach(function(ex){ ex.parentNode && ex.parentNode.removeChild(ex); });
								// prototype row to clone (if exists use a template row inside the wrapper or build one)
								var proto = wrapper.querySelector('.activities-row');
								for (var k=0;k<acts.length;k++) {
									var a = acts[k] || {};
									var row;
									if (proto) row = proto.cloneNode(true);
									else {
										row = document.createElement('div'); row.className = 'activities-row';
										row.innerHTML = '\n\t\t\t\t\t\t<div class="col atividade form-field">\n\t\t\t\t\t\t\t<select name="atividade_nome[]" class="atividade-nome-select" required>\n\t\t\t\t\t\t\t\t<option value="" selected disabled>Selecione...</option>\n\t\t\t\t\t\t\t</select>\n\t\t\t\t\t\t</div>\n\t\t\t\t\t\t<div class="col horario form-field">\n\t\t\t\t\t\t\t<label class="activity-label visible-on-compact">Início</label>\n\t\t\t\t\t\t\t<input type="time" name="atividade_inicio[]" class="atividade-inicio" />\n\t\t\t\t\t\t</div>\n\t\t\t\t\t\t<div class="col horario form-field">\n\t\t\t\t\t\t\t<label class="activity-label visible-on-compact">Fim</label>\n\t\t\t\t\t\t\t<input type="time" name="atividade_fim[]" class="atividade-fim" />\n\t\t\t\t\t\t</div>\n\t\t\t\t\t\t<div class="col comentario-pt form-field">\n\t\t\t\t\t\t\t<input type="text" name="atividade_comentario_pt[]" class="atividade-comentario-pt" />\n\t\t\t\t\t\t</div>\n\t\t\t\t\t\t<div class="col comentario-en form-field">\n\t\t\t\t\t\t\t<input type="text" name="atividade_comentario_en[]" class="atividade-comentario-en" readonly />\n\t\t\t\t\t\t</div>\n\t\t\t\t\t\t<div class="col actions">\n\t\t\t\t\t\t\t<button type="button" class="btn-remove-atividade">&times;</button>\n\t\t\t\t\t\t</div>';
									}
									// update ids/names for inputs inside cloned row
									Array.from(row.querySelectorAll('input,select,textarea,label')).forEach(function(el){
										try {
											if (el.tagName.toLowerCase() === 'label') return;
											// clear values
											if (el.tagName.toLowerCase() === 'select') el.selectedIndex = 0;
											else el.value = '';
										} catch(e){}
									});
									// set values from a
									try {
										var sel = row.querySelector('.atividade-nome-select');
										if (sel) {
											var val = a.atividade || a.nome || '';
											// tentar selecionar pelo value recebido
											sel.value = val;
											// se valor não existir nas opções, tentar casar pelo texto do label
											if (!sel.value && a.atividade_label) {
												Array.from(sel.options).some(function(op){ if (String(op.text).trim().toLowerCase() === String(a.atividade_label).trim().toLowerCase()) { sel.value = op.value; return true; } return false; });
											}
											// Se ainda não encontrou uma option correspondente, criar uma temporária para mostrar ao usuário
											if (!sel.value && (val || a.atividade_label)) {
												try {
													var tmpVal = String(val || a.atividade_label || '');
													var tmpLabel = String(a.atividade_label || val || tmpVal);
													var opt = document.createElement('option');
													opt.value = tmpVal;
													opt.textContent = tmpLabel;
													sel.appendChild(opt);
													sel.value = tmpVal;
												} catch(e){}
											}
										}
									} catch(e){}
									try { var ini = row.querySelector('input.atividade-inicio'); if (ini) ini.value = a.inicio || a.entrada || ''; } catch(e){}
									try { var fim = row.querySelector('input.atividade-fim'); if (fim) fim.value = a.fim || a.saida || ''; } catch(e){}
									try { var cpt = row.querySelector('input.atividade-comentario-pt'); if (cpt) cpt.value = a.comentario_pt || a.comentario || a.descricao || ''; } catch(e){}
									try { var cen = row.querySelector('input.atividade-comentario-en'); if (cen) cen.value = a.comentario_en || ''; } catch(e){}
									// insert before footer
									var footer = wrapper.querySelector('.activities-footer');
									wrapper.insertBefore(row, footer || null);
								}
							// re-init translators for new rows
							try { initEditorActivityTranslators(); } catch(e){}
						}
						} catch(e){}

						// Totais/cálculos exibidos no editor (se existirem)
						try {
							var pairs = [
								['edit-total-atividades','total_atividade_min'],
								['edit-total-confinado','total_confinado_min'],
								['edit-total-abertura-pt','total_abertura_pt_min'],
								['edit-total-atividades-efetivas','total_atividades_efetivas_min'],
								['edit-total-nao-efetivas-fora','total_atividades_nao_efetivas_fora_min']
							];
							pairs.forEach(function(p){ var el = document.getElementById(p[0]); if (el && (r[p[1]] !== undefined && r[p[1]] !== null)) el.value = String(r[p[1]]); });
						} catch(e){}

						// Hidden ID
						try { var hid = document.getElementById('edit-rdo-id'); if (hid && r.id) hid.value = r.id; } catch(e){}

						// --- Preencher equipe (membros/funções) para o editor (mover aqui para ter acesso a `r` corretamente)
						try {
							var teamWrapper = document.getElementById('edit-equipe-wrapper');
							if (teamWrapper) {
								var proto = teamWrapper.querySelector('.team-row');
								var teamData = r.equipe || r.team || r.equipe_list || null;
								if (typeof teamData === 'string') {
									try { teamData = JSON.parse(teamData); } catch(e){
										var lines = teamData.split(/\r?\n|;/).map(function(s){ return s.trim(); }).filter(Boolean);
										teamData = lines.map(function(name){ return { nome: name, funcao: '' }; });
									}
								}
								if (!Array.isArray(teamData)) teamData = [];
								// remove existing team rows (keep footer)
								Array.from(teamWrapper.querySelectorAll('.team-row')).forEach(function(tr){ tr.parentNode && tr.parentNode.removeChild(tr); });
								if (!teamData.length) {
									if (proto) {
										var clone = proto.cloneNode(true);
										Array.from(clone.querySelectorAll('input,textarea')).forEach(function(i){ try{i.value='';}catch(e){} });
										teamWrapper.insertBefore(clone, teamWrapper.querySelector('.team-footer') || null);
									} else {
										var row = document.createElement('div'); row.className='team-row';
										row.innerHTML = '<div class="form-field"><label>Nome</label><input name="equipe_nome[]" type="text" /></div><div class="form-field"><label>Função</label><input name="equipe_funcao[]" type="text" /></div>';
										teamWrapper.insertBefore(row, teamWrapper.querySelector('.team-footer') || null);
									}
								} else {
									teamData.forEach(function(m){
										var row;
										if (proto) row = proto.cloneNode(true); else {
											row = document.createElement('div'); row.className='team-row';
											row.innerHTML = '<div class="form-field"><label>Nome</label><input name="equipe_nome[]" type="text" /></div><div class="form-field"><label>Função</label><input name="equipe_funcao[]" type="text" /></div>';
										}
										try { var inpN = row.querySelector('input[name="equipe_nome[]"]'); if (inpN) inpN.value = m.nome || m.name || (Array.isArray(m) ? m[0] : '') || ''; } catch(e){}
										try { var inpF = row.querySelector('input[name="equipe_funcao[]"]'); if (inpF) inpF.value = m.funcao || m.funcao_pt || m.role || (Array.isArray(m) ? m[1] : '') || ''; } catch(e){}
										teamWrapper.insertBefore(row, teamWrapper.querySelector('.team-footer') || null);
									});
								}
							}
						} catch(e){ console.warn('populate equipe failed', e); }

						// Exibir fotos já anexadas ao RDO (se houver URLs)
						try {
							var existingPhotosRoot = document.getElementById('edit-fotos-existing');
							if (existingPhotosRoot) {
								var photos = [];
								if (Array.isArray(r.fotos)) {
									photos = r.fotos.filter(function(item){ return item && String(item).trim(); });
								} else if (typeof r.fotos === 'string') {
									photos = r.fotos.split(/\r?\n|;/).map(function(s){ return s.trim(); }).filter(Boolean);
								}
								existingPhotosRoot.innerHTML = '';
								if (!photos.length) {
									existingPhotosRoot.textContent = existingPhotosRoot.getAttribute('data-empty-text') || 'Nenhuma foto anexada.';
								} else {
									existingPhotosRoot.textContent = '';
									function normalizePhotoUrl(raw) {
										try {
											if (!raw) return '';
											var txt = String(raw).trim();
											if (!txt) return '';
											var protocol = window.location ? window.location.protocol : 'https:';
											var origin = window.location ? window.location.origin : '';
											if (txt.indexOf('://') === -1) {
												if (txt.charAt(0) === '/') return origin ? origin + txt : txt;
												return origin ? origin.replace(/\/$/, '') + '/' + txt.replace(/^\//, '') : txt;
											}
											if (txt.slice(0, 2) === '//') return protocol + txt;
											if (protocol === 'https:' && txt.toLowerCase().indexOf('http://') === 0) {
												try {
													var parsed = new URL(txt);
													return 'https://' + parsed.host + parsed.pathname + parsed.search + parsed.hash;
												} catch (e) {
													return txt.replace(/^http:\/\//i, 'https://');
												}
											}
											return txt;
										} catch (e) { return raw; }
									}
									photos.slice(0, 12).forEach(function(url, idx){
										try {
											var normalizedUrl = normalizePhotoUrl(url);
											var card = document.createElement('a');
											card.href = normalizedUrl || url || '#';
											card.target = '_blank';
											card.rel = 'noopener noreferrer';
											card.className = 'photo-preview-card';
											card.title = 'Abrir foto ' + (idx + 1);
											card.style.display = 'inline-flex';
											card.style.width = '72px';
											card.style.height = '72px';
											card.style.borderRadius = '6px';
											card.style.overflow = 'hidden';
											card.style.border = '1px solid #d0d0d0';
											card.style.margin = '4px';
											card.style.alignItems = 'center';
											card.style.justifyContent = 'center';
											var thumb = document.createElement('img');
											thumb.src = normalizedUrl || url;
											thumb.alt = 'Foto anexada ' + (idx + 1);
											thumb.style.maxWidth = '100%';
											thumb.style.maxHeight = '100%';
											thumb.style.objectFit = 'cover';
											thumb.loading = 'lazy';
											thumb.onerror = function(){
												card.classList.add('photo-preview-error');
												card.textContent = thumb.alt;
											};
											card.appendChild(thumb);
											existingPhotosRoot.appendChild(card);
										} catch(e){}
									});
									if (photos.length > 12) {
										var more = document.createElement('div');
										more.className = 'photo-preview-more';
										more.textContent = '+' + (photos.length - 12) + ' foto(s)';
										more.style.margin = '6px 4px';
										more.style.fontSize = '0.85rem';
										more.style.color = '#555';
										existingPhotosRoot.appendChild(more);
									}
								}
							}
						} catch(e){ console.warn('populate existing photos failed', e); }

						// Permissão de Trabalho: abertura, turnos e numeração
						try {
							var ptSel = document.getElementById('edit-pt-abertura');
							if (ptSel && typeof r.exist_pt !== 'undefined') ptSel.value = (r.exist_pt === true) ? 'sim' : (r.exist_pt === false ? 'nao' : '');
							// turnos com abertura
							var group = document.querySelector('#edit-sec-pt .inline-options[role="group"]');
							if (group && Array.isArray(r.select_turnos)) {
								var lower = r.select_turnos.map(function(t){ return String(t||'').trim().toLowerCase(); });
								Array.from(group.querySelectorAll('input[type=checkbox]')).forEach(function(cb){
									var v = (cb.value||'').toLowerCase();
									cb.checked = (lower.indexOf(v === 'manha' ? 'manhã' : v) !== -1) || (lower.indexOf(v) !== -1);
								});
							}
							var m = document.getElementById('edit-pt-manha'); if (m && r.pt_manha != null) m.value = r.pt_manha;
							var t = document.getElementById('edit-pt-tarde'); if (t && r.pt_tarde != null) t.value = r.pt_tarde;
							var n = document.getElementById('edit-pt-noite'); if (n && r.pt_noite != null) n.value = r.pt_noite;
						} catch(e){}

					} catch(e) { console.warn('populateEditorFromData failed', e); }
				}

					// Handler: botão 'Carregar detalhes' dentro do modal de edição
					try {
						var loadDetailsBtn = document.getElementById('edit-btn-load-details');
						if (loadDetailsBtn) loadDetailsBtn.addEventListener('click', function(ev){
							ev && ev.preventDefault && ev.preventDefault();
							var origTxt = loadDetailsBtn.textContent;
							try { loadDetailsBtn.disabled = true; loadDetailsBtn.textContent = 'Carregando...'; } catch(e){}

							// obter id do RDO (preferir hidden edit-rdo-id, fallback para campo edit-rdo)
							var hid = document.getElementById('edit-rdo-id');
							var rdoId = (hid && hid.value) ? hid.value : ((document.getElementById('edit-rdo')||{}).value || '');
							if (!rdoId) {
								try { showToast('ID do RDO não encontrado para carregamento', 'error'); } catch(e){}
								try { loadDetailsBtn.disabled = false; loadDetailsBtn.textContent = origTxt; } catch(e){}
								return;
							}

							var url = '/rdo/' + encodeURIComponent(rdoId) + '/detail/';
							fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
								.then(function(resp){ if (!resp.ok) throw new Error('fetch-status-' + resp.status); return resp.text(); })
								.then(function(text){
									if (!text) return null;
									try { return JSON.parse(text); } catch (err) { try { console.warn('rdo.js: /rdo/<id>/detail returned non-JSON (preview):', text.slice(0,800)); } catch(e){} return null; }
								})
								.then(function(data){
									if (data && data.success && data.rdo) {
										try { populateEditorFromData(data.rdo); } catch(e){ console.warn('populateEditorFromData error', e); }
										try { showToast('Detalhes carregados', 'success'); } catch(e){}
									} else {
										try { showToast('Não foi possível carregar os detalhes do RDO', 'error'); } catch(e){}
									}
								})
								.catch(function(err){ try { console.warn('rdo.js: load details failed', err); } catch(e){} try { showToast('Erro ao carregar detalhes', 'error'); } catch(e){} })
								.finally(function(){ try { loadDetailsBtn.disabled = false; loadDetailsBtn.textContent = origTxt; } catch(e){} });
						});
					} catch(e){ console.warn('edit load-details init failed', e); }

					// --- Editor: atividades dinâmicas (adicionar / remover) ---
					(function(){
						try {
							var wrapper = document.getElementById('edit-atividades-wrapper');
							if (!wrapper) return;

							wrapper.addEventListener('click', function(ev){
								var rem = ev.target.closest && ev.target.closest('.btn-remove-atividade');
								if (!rem) return;
								var rows = wrapper.querySelectorAll('.activities-row');
								if (rows.length <= 1) return;
								var row = rem.closest && rem.closest('.activities-row'); if (row) row.remove();
								updateRemoveState();
							});

							var addBtn = document.getElementById('edit-btn-add-atividade');
							if (addBtn) addBtn.addEventListener('click', function(){
								var max = parseInt(addBtn.getAttribute('data-max')||'20',10);
								var rows = wrapper.querySelectorAll('.activities-row');
								if (rows.length >= max) return;
								var last = rows[rows.length-1]; if (!last) return;
								var newIndex = rows.length;
								var clone = last.cloneNode(true);
								Array.from(clone.querySelectorAll('input,select,textarea,label')).forEach(function(el){
									try {
										if (el.tagName.toLowerCase() === 'label') {
											var f = el.getAttribute('for'); if (f) el.setAttribute('for', f.replace(/-\d+$/, '-') + newIndex);
											return;
										}
										var tag = el.tagName.toLowerCase();
										var type = (el.type || '').toLowerCase();
										if (tag === 'select') { el.selectedIndex = 0; }
										else if (type === 'checkbox' || type === 'radio') { el.checked = false; }
										else { el.value = ''; }
										if (el.id) {
											if (/-\d+$/.test(el.id)) el.id = el.id.replace(/-(\d+)$/, '-' + newIndex);
											else el.id = el.id + '-' + newIndex;
										}
										if (el.dataset) {
											delete el.dataset.rdoTranslatorInit; delete el.dataset.userEdited; delete el.dataset.autoFilled;
										}
										try { el.removeAttribute && el.removeAttribute('readonly'); } catch(e){}
									} catch(e){}
								});
								var footer = wrapper.querySelector('.activities-footer');
								wrapper.insertBefore(clone, footer || null);
								try { initEditorActivityTranslators(); } catch(e){}
								updateRemoveState();
							});

							function updateRemoveState(){
								var rows = wrapper.querySelectorAll('.activities-row');
								rows.forEach(function(r){ var b = r.querySelector('.btn-remove-atividade'); if (b) b.disabled = (rows.length <= 1); });
							}

							updateRemoveState();

							var removeLastBtn = document.getElementById('edit-btn-remove-last-atividade');
							if (removeLastBtn) {
								removeLastBtn.addEventListener('click', function(ev){
									ev.preventDefault();
									try {
										var rows = wrapper.querySelectorAll('.activities-row');
										if (!rows || rows.length <= 1) return;
										var last = rows[rows.length - 1]; if (last) last.remove();
										try { initEditorActivityTranslators(); } catch(e){}
										updateRemoveState();
									} catch(e) { console.warn('remove last edit atividade failed', e); }
								});
							}
						} catch(e){ console.error('edit activities init error', e); }
					})();

					// --- Editor: gerenciador de equipe (adicionar / remover membros) ---
					(function(){
						try {
							var wrapper = document.getElementById('edit-equipe-wrapper');
							if (!wrapper) return;
							var footer = wrapper.querySelector('.team-footer');
							var hint = wrapper.querySelector('.team-limit-hint');
							var addBtn = document.getElementById('edit-btn-add-membro');
							var max = 18;

							wrapper.addEventListener('click', function(ev){
								try {
									var rem = ev.target.closest && ev.target.closest('.btn-remove-membro');
									if (!rem) return;
									var rows = wrapper.querySelectorAll('.team-row');
									if (rows.length <= 1) return;
									var row = rem.closest && rem.closest('.team-row');
									if (row) { row.remove(); updateHint(); }
								} catch(e){}
							});

							function updateHint(){
								try {
									var rows = wrapper.querySelectorAll('.team-row'); if (!hint) return;
									var remaining = Math.max(0, max - rows.length);
									hint.textContent = rows.length >= max ? ('Máx. ' + max + ' membros') : ('Pode adicionar até ' + remaining + ' membro(s)');
									try {
										var addBtnLocal = document.getElementById('edit-btn-add-membro');
										var remBtnLocal = document.getElementById('edit-btn-remove-membro');
										if (addBtnLocal) addBtnLocal.disabled = (rows.length >= max);
										if (remBtnLocal) remBtnLocal.disabled = (rows.length <= 1);
									} catch(e){}
								} catch(e){}
							}

							function makeRemovable(row){
								if (!row) return; var btn = row.querySelector('.btn-remove-membro'); if (!btn) return;
								try { btn.type = 'button'; btn.classList.add('btn-rdo','small','btn-remove-membro'); btn.setAttribute('title', btn.getAttribute('title') || 'Remover membro'); btn.style.cursor = btn.style.cursor || 'pointer'; } catch(e){}
							}

							Array.from(wrapper.querySelectorAll('.team-row')).forEach(function(r){
								try {
									var inpNome = r.querySelector('input[name="equipe_nome[]"]');
									var inpFunc = r.querySelector('input[name="equipe_funcao[]"]');
									if (!inpNome) { var anyNome = r.querySelector('input[type="text"]'); if (anyNome) anyNome.name = 'equipe_nome[]'; }
									if (!inpFunc) { var allText = r.querySelectorAll('input[type="text"]'); if (allText && allText.length > 1) allText[1].name = 'equipe_funcao[]'; }
								} catch(e){}
								makeRemovable(r);
							});

							if (addBtn) addBtn.addEventListener('click', function(){
								var rows = wrapper.querySelectorAll('.team-row'); if (rows.length >= max) return; var first = rows[0]; if (!first) return;
								var clone = first.cloneNode(true);
								Array.from(clone.querySelectorAll('input')).forEach(function(el, idx){ try { el.value = ''; if (!el.name) { if (idx === 0) el.name = 'equipe_nome[]'; else el.name = 'equipe_funcao[]'; } } catch(e){} });
								wrapper.insertBefore(clone, footer || null);
								updateHint();
							});

							var globalRemove = document.getElementById('edit-btn-remove-membro');
							if (globalRemove) globalRemove.addEventListener('click', function(ev){
								try { var rows = wrapper.querySelectorAll('.team-row'); if (!rows || rows.length <= 1) return; var last = rows[rows.length - 1]; if (last) last.remove(); updateHint(); } catch(e){}
							});

							updateHint();
						} catch(e){ console.error('edit team manager init failed', e); }
					})();

					// --- Editor: gerenciador de fotos (preview e adicionar) ---
					(function(){
						try {
							var fileInput = document.getElementById('edit-fotos');
							if (!fileInput) return;
							var MAX_FILES = 5;
							var selectedFiles = [];

							function ensurePreviewRoot(){
								var existing = document.getElementById('edit-fotos-preview'); if (existing) return existing;
								var label = document.querySelector('label[for="edit-fotos"]');
								var container = document.createElement('div'); container.id = 'edit-fotos-preview'; container.style.display = 'flex'; container.style.flexWrap = 'wrap'; container.style.gap = '8px'; container.style.alignItems = 'center'; container.style.marginTop = '6px';
								if (label && label.parentNode) label.parentNode.appendChild(container); else { var form = document.getElementById('form-editor'); if (form) form.appendChild(container); }
								return container;
							}

							function syncInputFiles(){ try { var dt = new DataTransfer(); selectedFiles.forEach(function(f){ try{ dt.items.add(f); }catch(e){} }); fileInput.files = dt.files; } catch(e){ console.warn('syncInputFiles edit failed', e); } }

							function renderPreviews(){ var root = ensurePreviewRoot(); root.innerHTML = ''; var info = document.createElement('div'); info.style.display='flex'; info.style.alignItems='center'; info.style.gap='8px'; var count = selectedFiles.length; var txt = document.createElement('span'); txt.textContent = count + ' arquivo' + (count>1 ? 's' : ''); txt.style.fontSize='0.9rem'; txt.style.color='#333'; info.appendChild(txt); var addBtn = document.createElement('button'); addBtn.type='button'; addBtn.id='edit-fotos-add-btn'; addBtn.className='btn-rdo small'; addBtn.style.marginLeft='6px'; addBtn.textContent='Adicionar fotos'; addBtn.addEventListener('click', function(){ fileInput.click(); }); info.appendChild(addBtn); root.appendChild(info);
								selectedFiles.slice(0, MAX_FILES).forEach(function(f, idx){ var box = document.createElement('div'); box.style.position='relative'; box.style.width='64px'; box.style.height='64px'; box.style.borderRadius='6px'; box.style.overflow='hidden'; box.style.border='1px solid #ddd'; var img = document.createElement('img'); img.style.width='100%'; img.style.height='100%'; img.style.objectFit='cover'; var reader = new FileReader(); reader.onload = function(ev){ img.src = ev.target.result; }; reader.readAsDataURL(f); box.appendChild(img); var btn = document.createElement('button'); btn.type='button'; btn.title='Remover foto'; btn.textContent='×'; btn.style.position='absolute'; btn.style.top='2px'; btn.style.right='2px'; btn.style.background='rgba(0,0,0,0.6)'; btn.style.color='#fff'; btn.style.border='none'; btn.style.borderRadius='50%'; btn.style.width='20px'; btn.style.height='20px'; btn.style.cursor='pointer'; btn.addEventListener('click', function(){ selectedFiles.splice(idx,1); syncInputFiles(); renderPreviews(); }); box.appendChild(btn); root.appendChild(box); }); if (selectedFiles.length > MAX_FILES) { var hint = document.createElement('div'); hint.textContent = 'Máx. ' + MAX_FILES + ' imagens serão enviadas; selecione menos.'; hint.style.fontSize='0.8rem'; hint.style.color='#b26a00'; hint.style.marginLeft='8px'; root.appendChild(hint); } }

							fileInput.addEventListener('change', function(ev){ try { var fl = ev.target.files ? Array.from(ev.target.files) : []; fl.forEach(function(f){ if (!f) return; var exists = selectedFiles.some(function(sf){ return sf.name === f.name && sf.size === f.size && sf.type === f.type; }); if (!exists) selectedFiles.push(f); }); if (selectedFiles.length > MAX_FILES) selectedFiles = selectedFiles.slice(0, MAX_FILES); syncInputFiles(); renderPreviews(); } catch(e){ console.warn('edit-fotos change handler', e); } });

							if (fileInput.files && fileInput.files.length) { selectedFiles = Array.from(fileInput.files).slice(0, MAX_FILES); renderPreviews(); }
							// connect visible button
							var addFotoBtn = document.getElementById('edit-btn-add-foto'); if (addFotoBtn && fileInput) addFotoBtn.addEventListener('click', function(){ fileInput.click(); });
						} catch(e){ console.warn('edit-fotos manager init failed', e); }
					})();

					// --- Editor: cálculos (bombeio / res total / agregados) ---
					(function(){
						try {
							function timeToMinutes(t){ if (!t) return null; if (typeof t === 'string' && t.indexOf(':') > -1) { var p = t.split(':'); var hh = parseInt(p[0],10); var mm = parseInt(p[1],10)||0; if (!isFinite(hh) || !isFinite(mm)) return null; return hh*60 + mm; } return null; }

							function computeEditorAggregates(){
								try {
									var wrapper = document.getElementById('edit-atividades-wrapper'); if (!wrapper) return {};
									var rows = Array.from(wrapper.querySelectorAll('.activities-row'));
									var total_atividade = 0; var total_abertura_pt = 0; var total_atividades_efetivas = 0;
									var ATIVIDADES_EFETIVAS = [ 'avaliação inicial da área de trabalho','bombeio','instalação/preparação/montagem','desmobilização do material - dentro do tanque','desmobilização do material - fora do tanque','mobilização de material - dentro do tanque','mobilização de material - fora do tanque','limpeza e higienização de coifa','limpeza de dutos','coleta e análise de ar','cambagem','içamento','limpeza fina','manutenção de equipamentos - dentro do tanque','manutenção de equipamentos - fora do tanque','jateamento' ];
									rows.forEach(function(row){ try { var sel = row.querySelector('.atividade-nome-select'); var inicio = row.querySelector('.atividade-inicio'); var fim = row.querySelector('.atividade-fim'); var atVal = sel ? (sel.value || '').toString().trim().toLowerCase() : ''; var inicioMin = inicio ? timeToMinutes(inicio.value) : null; var fimMin = fim ? timeToMinutes(fim.value) : null; if (inicioMin !== null && fimMin !== null) { var dur = fimMin - inicioMin; if (dur < 0) dur += 24*60; total_atividade += dur; if (atVal === 'abertura pt') total_abertura_pt += dur; if (ATIVIDADES_EFETIVAS.indexOf(atVal) !== -1) total_atividades_efetivas += dur; } } catch(e){} });

									var ecGrid = document.getElementById('edit-ec-times-grid'); var total_confinado = 0; if (ecGrid) { var entradas = Array.from(ecGrid.querySelectorAll('input[name="entrada_confinado[]"]')); var saidas = Array.from(ecGrid.querySelectorAll('input[name="saida_confinado[]"]')); for (var i=0;i<Math.max(entradas.length, saidas.length); i++){ var e = entradas[i] ? timeToMinutes(entradas[i].value) : null; var s = saidas[i] ? timeToMinutes(saidas[i].value) : null; if (e !== null && s !== null) { var d = s - e; if (d < 0) d += 24*60; total_confinado += d; } } }

									var nEfetivoEl = document.getElementById('edit-total-n-efetivo-confinado'); var nEfetivo = 0; if (nEfetivoEl && nEfetivoEl.value) { var tmp = parseInt(nEfetivoEl.value,10); if (isFinite(tmp)) nEfetivo = tmp; }
									var total_nao_efetivas_fora = total_atividade - total_atividades_efetivas - nEfetivo;
									function setIf(id, value){ var el = document.getElementById(id); if (!el) return; el.value = (value === null || value === undefined) ? '' : String(Math.round(value)); }
									setIf('edit-total-atividades', total_atividade); setIf('edit-total-confinado', total_confinado); setIf('edit-total-abertura-pt', total_abertura_pt); setIf('edit-total-atividades-efetivas', total_atividades_efetivas); setIf('edit-total-nao-efetivas-fora', total_nao_efetivas_fora);
									return { total_atividade: total_atividade, total_confinado: total_confinado, total_abertura_pt: total_abertura_pt, total_atividades_efetivas: total_atividades_efetivas, total_nao_efetivas_fora: total_nao_efetivas_fora, n_efetivo_confinado: nEfetivo };
								} catch(e){ console.warn('computeEditorAggregates failed', e); return {}; }
							}

							// recalcular res.total no editor
							(function(){ try { var resLiq = document.getElementById('edit-res-liq'); var resSol = document.getElementById('edit-res-sol'); var resTotal = document.getElementById('edit-res-total'); if (!resLiq || !resSol || !resTotal) return; function markUserEdited(el){ try { if (el && el.dataset) el.dataset.userEdited = '1'; } catch(e){} } resTotal.addEventListener('input', function(){ markUserEdited(resTotal); }); resSol.addEventListener('input', function(){ try { if (resTotal.dataset && resTotal.dataset.userEdited === '1') return; compute(); } catch(e){} }); resLiq.addEventListener('input', function(){ try { if (resTotal.dataset && resTotal.dataset.userEdited === '1') return; compute(); } catch(e){} }); function compute(){ try { var a = parseFloat(resLiq.value); var b = parseFloat(resSol.value); a = isFinite(a) ? a : 0; b = isFinite(b) ? b : 0; var total = Math.round((a + b) * 100) / 100; if (!resTotal.dataset || resTotal.dataset.userEdited !== '1') { resTotal.value = total; } } catch(e){} } window.computeEditorResTotal = compute; setTimeout(compute, 30); } catch(e){} })();

							// recalcular bombeio no editor (usar vazão informada pelo usuário)
							(function(){ try { var tempoInput = document.getElementById('edit-tempo-bomba'); var bombeioInput = document.getElementById('edit-bombeio'); var resLiqInput = document.getElementById('edit-res-liq'); if (!tempoInput || !bombeioInput || !resLiqInput) return; function computeAndFill(){ try { var val = parseFloat(tempoInput.value); if (!isFinite(val)) return; var vazaoEl = document.getElementById('edit-vazao-bombeio'); var vazao = vazaoEl ? parseFloat(vazaoEl.value) : NaN; // fallback 36 quando vazão não informada/inválida
var vazaoLocal = isFinite(vazao) ? vazao : 36; var computed = Math.round((val * vazaoLocal) * 100) / 100; bombeioInput.value = computed; resLiqInput.value = computed; try { resLiqInput.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) { if (window.computeEditorResTotal) try { window.computeEditorResTotal(); } catch(e){} } } catch(e){} } tempoInput.addEventListener('input', computeAndFill); try { var vazEl = document.getElementById('edit-vazao-bombeio'); if (vazEl) vazEl.addEventListener('input', computeAndFill); } catch(e){} var templateBtn = document.getElementById('edit-btn-recalcular-bombeio'); if (templateBtn) { templateBtn.addEventListener('click', function(ev){ ev.preventDefault(); try { if (bombeioInput && bombeioInput.dataset) delete bombeioInput.dataset.userEdited; if (resLiqInput && resLiqInput.dataset) delete resLiqInput.dataset.userEdited; } catch(e){} computeAndFill(); showToast('Recalculado: bombeio e resíduo líquido atualizados', 'success'); }); } setTimeout(computeAndFill, 30); } catch(e){} })();

						// Auto-calcular Res. sólidos a partir de Ensacamento (editor)
						(function(){
							try {
								var ensac = document.getElementById('edit-ensac');
								var resSol = document.getElementById('edit-res-sol');
								if (!ensac || !resSol) return;

								function computeEditResSol(){
									try {
										var e = parseFloat(ensac.value);
										e = isFinite(e) ? e : 0;
										var sol = Math.round((e * 0.008) * 100) / 100;
										resSol.value = sol;
										try { resSol.dispatchEvent(new Event('input', { bubbles: true })); } catch(e) { if (window.computeEditorResTotal) try { window.computeEditorResTotal(); } catch(e){} }
									} catch(e){}
								}

								ensac.addEventListener('input', computeEditResSol);
								setTimeout(computeEditResSol, 40);
							} catch(e){}
						})();

							// ligar botão de recalcular agregados do editor
							try { var recBtn = document.getElementById('edit-btn-recalcular-calculos'); if (recBtn) recBtn.addEventListener('click', function(ev){ ev.preventDefault(); var res = computeEditorAggregates(); showToast('Cálculos atualizados (pré-visualização)', 'success'); }); window.computeEditorAggregates = computeEditorAggregates; } catch(e){}
						} catch(e){ console.warn('editor aggregates init failed', e); }
					})();

			// Removido: exposição global do builder (não há mais botão Enviar dedicado)

			// Handler Add Tanque: persiste o tanque atual e limpa apenas campos de tanque/fotos mantendo RDO/PO
			(function(){
				try {
					var btn = document.getElementById('btn-add-tanque');
					if (!btn) return;
					btn.addEventListener('click', async function(ev){
						ev.preventDefault();
						var form = document.getElementById('form-supervisor');
						if (!form) return;

						// validações mínimas
						var rdoVal = (document.getElementById('sup-rdo')||{}).value || '';
						var contratoVal = (document.getElementById('sup-contrato-po')||{}).value || '';
						if (!rdoVal || !contratoVal) {
							// focar no campo faltante
							if (!rdoVal && document.getElementById('sup-rdo')) document.getElementById('sup-rdo').focus();
							else if (!contratoVal && document.getElementById('sup-contrato-po')) document.getElementById('sup-contrato-po').focus();
							return;
						}

						// desabilitar botão para prevenir duplo clique
						btn.disabled = true;
						var origText = btn.textContent;
						btn.textContent = 'Salvando...';

						try {
							var payload = buildSupervisorFormData(form);
							// endpoint de criação
							var url = '/rdo/create_ajax/';
							var resp = await fetch(url, { method: 'POST', body: payload, credentials: 'same-origin', headers: { 'X-Requested-With':'XMLHttpRequest', 'X-CSRFToken': (form.querySelector('input[name=csrfmiddlewaretoken]')||{}).value || '' } });
							var data = null;
							if (resp && resp.ok) {
								try { data = await resp.json(); } catch(e) { data = null; }
							}

							// inserir linha visual na tabela como já acontece no submit flow
							var table = document.querySelector('table');
							var tbody = table ? table.querySelector('tbody') : null;
							if (tbody) {
								var newTr = document.createElement('tr');
								newTr.dataset.rdoId = (data && data.id) ? data.id : '';
								newTr.dataset.numeroOs = (document.getElementById('sup-rdo')||{}).value || '';
								newTr.dataset.empresa = (document.getElementById('sup-context-empresa')||{}).textContent || '';
								newTr.dataset.unidade = (document.getElementById('sup-context-unidade')||{}).textContent || '';
								newTr.dataset.supervisor = (document.getElementById('sup-context-supervisor')||{}).textContent || '';
								newTr.innerHTML = `
									<td>-</td>
									<td>${(document.getElementById('sup-rdo')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-contrato-po')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-context-empresa')||{}).textContent || '-'}</td>
									<td>${(document.getElementById('sup-context-unidade')||{}).textContent || '-'}</td>
									<td>${(document.getElementById('sup-context-supervisor')||{}).textContent || '-'}</td>
									<td>-</td>
									<td>${new Date().toLocaleDateString()}</td>
									<td>${(document.getElementById('sup-rdo')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-turno')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-tanque-cod')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-tanque-nome')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-tipo-tanque')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-n-comp')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-gavetas')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-patamar')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-volume')||{}).value || '-'}</td>
									<td>${(document.getElementById('sup-servico') && document.getElementById('sup-servico').options[document.getElementById('sup-servico').selectedIndex]) ? document.getElementById('sup-servico').options[document.getElementById('sup-servico').selectedIndex].text : '-'}</td>
									<td>${(document.getElementById('sup-metodo') && document.getElementById('sup-metodo').options[document.getElementById('sup-metodo').selectedIndex]) ? document.getElementById('sup-metodo').options[document.getElementById('sup-metodo').selectedIndex].text : '-'}</td>
									<td>-</td>
									<td>-</td>
									<td>-</td>
									<td class="action-cell"><button class="action-btn edit" type="button"><span class="material-icons" aria-hidden="true">edit</span></button></td>
									<td class="action-cell"><button class="action-btn view" type="button"><span class="material-icons" aria-hidden="true">visibility</span></button></td>
								`;
								var first = tbody.querySelector('tr');
								tbody.insertBefore(newTr, first || null);
							}

							// decrementar contador local
							try {
								var cnt = parseInt(localStorage.getItem('rdo_pending_count')||'0',10);
								cnt = Math.max(0, cnt-1);
								localStorage.setItem('rdo_pending_count', String(cnt));
								if (window.updateNotificationCount) window.updateNotificationCount();
							} catch(e){}

							// limpar o formulário: preservar apenas RDO e Contrato/PO
							try {
								var preserveIds = { 'sup-rdo': true, 'sup-contrato-po': true, 'sup-ordem-id': true, 'sup-turno': true };
								function shouldPreserve(el){
									try {
										if (!el) return false;
										if (preserveIds[el.id]) return true;
										var sec = el.closest && el.closest('.rdo-section');
										if (!sec) return false;
										var secId = sec.id || '';
										// Preservar completamente as seções de Atividades e PT
										if (secId === 'sec-atividades' || secId === 'sec-pt') return true;
										// Na seção de identificação, preservar RDO/Turno/PO pelos IDs (já coberto acima)
										return false;
									} catch(e){ return false; }
								}
								// limpar todos os inputs/selects/textarea, exceto os preservados e csrf
								Array.from(form.elements).forEach(function(el){
									if (!el.name) return;
									if (el.name === 'csrfmiddlewaretoken') return;
									if (shouldPreserve(el)) return;
									var tag = (el.tagName || '').toLowerCase();
									var type = (el.type || '').toLowerCase();
									if (type === 'file') { try { el.value = ''; } catch(e) {} return; }
									if (type === 'checkbox' || type === 'radio') { el.checked = false; return; }
									if (tag === 'select') { el.selectedIndex = 0; return; }
									// hidden inputs como sup-rdo-id devem ser limpos
									el.value = '';
								});

								// limpar sup-rdo-id (se existir) para garantir modo create no próximo add
								var hid = document.getElementById('sup-rdo-id'); if (hid) hid.value = '';

								// Não resetar a seção de Atividades: os dados devem se repetir no próximo tanque

								// Bloquear edição manual do RDO no próximo tanque (readOnly)
								try {
									var rdoInput = document.getElementById('sup-rdo');
									if (rdoInput) {
										rdoInput.readOnly = true;
										rdoInput.setAttribute('aria-readonly','true');
										rdoInput.classList.add('readonly');
										// adicionar ícone de cadeado se não existir
										try {
											if (!document.getElementById('sup-rdo-lock')) {
												var lock = document.createElement('span');
												lock.id = 'sup-rdo-lock';
												lock.className = 'sup-rdo-lock material-icons';
												lock.style.marginLeft = '8px';
												lock.style.fontSize = '18px';
												lock.title = 'RDO bloqueado para edição neste ciclo';
												lock.textContent = 'lock';
												// inserir após input
												if (rdoInput.parentNode) rdoInput.parentNode.insertBefore(lock, rdoInput.nextSibling);
											}
										} catch(e){}
									}
								} catch(e){}
							} catch(e) { console.warn('clear form partial failed', e); }

						} catch(e){ console.error('add tanque failed', e); }
						finally { btn.disabled = false; btn.textContent = origText; }
					});
				} catch(e){ console.error('rdo.js add tanque init error', e); }
			})();

			// Reusar botão existente no template (evita duplicata)
			let notificationBtn = document.getElementById('rdo-notification-btn');
			if (notificationBtn) {
				// garantir estrutura interna (.count)
				if (!notificationBtn.querySelector('.count')) {
					const span = document.createElement('span');
					span.className = 'count';
					span.textContent = '0';
					notificationBtn.appendChild(span);
				}
				notificationBtn.addEventListener('click', showCTA);
			}

			async function updateNotificationCount() {
				if (!notificationBtn) return;
				// preferir contagem única de OS calculada no cliente/servidor
				var uniqueCount = null;
				if (typeof window.__rdo_pending_unique_count === 'number') {
					uniqueCount = window.__rdo_pending_unique_count;
				} else if (Array.isArray(window.__rdo_pending_list) && window.__rdo_pending_list.length) {
					// deduplicar por numero_os preferencialmente, senão por id
					try {
						var seen = new Set();
						window.__rdo_pending_list.forEach(function(it){
							var key = (it.numero_os && String(it.numero_os)) || (it.id && String(it.id)) || '';
							if (key) seen.add(key);
						});
						uniqueCount = seen.size;
					} catch(e){ uniqueCount = null; }
				} else {
					// fallback para valor em localStorage
					uniqueCount = parseInt(safeLocal.get('rdo_pending_count') || '0') || 0;
				}
				var count = (typeof uniqueCount === 'number') ? uniqueCount : 0;
				const countEl = notificationBtn.querySelector('.count');
				if (countEl) {
					countEl.textContent = String(count);
				}
				// O botão deve ficar fixo na tela o tempo inteiro; estilizamos o badge para refletir 0 também
				notificationBtn.style.display = 'inline-flex';
				// dar classe de destaque quando >0
				if (count > 0) notificationBtn.classList.add('has-pending'); else notificationBtn.classList.remove('has-pending');
			}

			async function getPendingUrl() {
				try {
					if (notificationBtn && notificationBtn.dataset && notificationBtn.dataset.pendingUrl) return notificationBtn.dataset.pendingUrl;
					var meta = document.querySelector('meta[name="rdo-pending-url"]');
					if (meta && meta.content) return meta.content;
				} catch(e){}
				return '/rdo/pending_os_json/';
			}

			async function fetchPendingOs() {
				var url = await getPendingUrl();
				if (!url) return null;
				try {
					var resp = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
					if (!resp.ok) return null;
					var data = await resp.json();
					// Espera { count: number, os_list: [ { id, numero_os, empresa, unidade, supervisor } ] }
					if (data && typeof data.count === 'number') {
						window.__rdo_pending_count = data.count;
						window.__rdo_pending_list = Array.isArray(data.os_list) ? data.os_list : [];
						// calcular contagem única (dedupe por numero_os preferencial)
						try {
							var seen = new Set();
							window.__rdo_pending_list.forEach(function(it){
								var key = (it.numero_os && String(it.numero_os)) || (it.id && String(it.id)) || '';
								if (key) seen.add(key);
							});
							window.__rdo_pending_unique_count = seen.size;
							// persistir contagem única em localStorage para outras abas
							safeLocal.set('rdo_pending_count', String(window.__rdo_pending_unique_count));
						} catch(e){
							window.__rdo_pending_unique_count = (Array.isArray(window.__rdo_pending_list) ? window.__rdo_pending_list.length : 0);
							try { safeLocal.set('rdo_pending_count', String(window.__rdo_pending_unique_count)); } catch(e){}
						}
						return data;
					}
				} catch (e) { console.error('fetchPendingOs error', e); }
				return null;
			}

			// Popular select de OS: primeiro usa dados do servidor (window.__rdo_pending_list), senão fallback para tabela
			function populateOsSelect() {
				const sel = document.getElementById('rdo-cta-os-select');
				if (!sel) return;
				if (sel.dataset.populated === '1') return; // evitar repopular
				sel.innerHTML = '<option value="">Selecione a OS...</option>';

				// calcular contador conhecido (prefere valor vindo do servidor)
				var knownCount = (typeof window.__rdo_pending_count === 'number') ? window.__rdo_pending_count : parseInt(safeLocal.get('rdo_pending_count') || '0') || 0;

				// Se não há pendentes conhecidos, não fazer fallback para tabela: indicar "Nenhuma OS nova"
				if (!Array.isArray(window.__rdo_pending_list) || !window.__rdo_pending_list.length) {
					if (knownCount === 0) {
						sel.innerHTML = '<option value="">Nenhuma OS nova</option>';
						sel.disabled = true;
						sel.dataset.populated = '1';
						return;
					}
				}

				// Se o servidor já forneceu uma lista, usar essa lista (com deduplicação)
				if (Array.isArray(window.__rdo_pending_list) && window.__rdo_pending_list.length) {
					sel.disabled = false;
					var seen = new Set();
					window.__rdo_pending_list.forEach(function(it){
						// chave de deduplicação: preferir numero_os, cair para id/rdo_id
						var key = String(it.numero_os || it.id || it.rdo_id || '').trim();
						if (!key) return; // pular itens sem identificação
						if (seen.has(key)) return; // já adicionada
						seen.add(key);
						const opt = document.createElement('option');
						opt.value = it.id || it.rdo_id || it.numero_os || '';
						opt.dataset.rdoId = it.id || it.rdo_id || '';
						// 'codigo_os' removido do modelo — usar apenas numero_os quando disponível
						opt.dataset.osNum = it.numero_os || '';
						opt.dataset.empresa = it.empresa || it.cliente || '';
						opt.dataset.unidade = it.unidade || '';
						opt.dataset.supervisor = it.supervisor || '';
						opt.textContent = (opt.dataset.osNum ? opt.dataset.osNum + ' — ' : '') + (opt.dataset.empresa ? opt.dataset.empresa + ' — ' : '') + (opt.dataset.unidade || '');
						sel.appendChild(opt);
					});
					sel.dataset.populated = '1';
					return;
				}

			// fallback: ler linhas da tabela (somente se não tivermos um contador zerado e não houver lista do servidor)
			let rows = [];
			if (knownCount > 0 && (!Array.isArray(window.__rdo_pending_list) || !window.__rdo_pending_list.length)) {
				rows = Array.from(document.querySelectorAll('table tbody tr[data-numero-os]'));
				if (!rows.length) rows = Array.from(document.querySelectorAll('table tbody tr'));
			} else {
				// se chegamos aqui, significa que não há itens do servidor e contador é 0 — já retornamos acima.
				rows = [];
			}
				// fallback: ler linhas da tabela (somente se não tivermos um contador zerado e não houver lista do servidor)
				var seenRows = new Set();
				rows.forEach(function(tr){
					const tds = tr.querySelectorAll('td');
					// Mapear colunas conforme template: 0:ID, 1:Nº OS, 2:PO, 3:EMPRESA, 4:UNIDADE, 5:SUPERVISOR
					const rdoId = tr.dataset.osId || tr.dataset.os_id || tr.dataset['os-id'] || tr.dataset.rdoId || (tds[0] ? tds[0].textContent.trim() : '');
					const osNum = tr.dataset.numeroOs || tr.dataset.numero_os || tr.dataset['numero-os'] || (tds[1] ? tds[1].textContent.trim() : '');
					var key = String(osNum || rdoId || '').trim();
					if (!key) return;
					if (seenRows.has(key)) return;
					seenRows.add(key);
					const empresa = tr.dataset.empresa || (tds[3] ? tds[3].textContent.trim() : '');
					const unidade = tr.dataset.unidade || (tds[4] ? tds[4].textContent.trim() : '');
					const supervisor = tr.dataset.supervisor || (tds[5] ? tds[5].textContent.trim() : '');
					const opt = document.createElement('option');
					opt.value = rdoId || osNum || '';
					opt.dataset.rdoId = rdoId || '';
					opt.dataset.osNum = osNum || '';
					opt.dataset.empresa = empresa || '';
					opt.dataset.unidade = unidade || '';
					opt.dataset.supervisor = supervisor || '';
					let labelParts = [];
					if (osNum) labelParts.push(osNum);
					if (empresa) labelParts.push(empresa);
					if (unidade) labelParts.push(unidade);
					opt.textContent = labelParts.join(' — ') || (rdoId ? String(rdoId) : '(sem identificação)');
					sel.appendChild(opt);
				});
				sel.dataset.populated = '1';
			}

			async function showCTA() {
				const ctaRoot = document.getElementById('rdo-mobile-cta');
				if (!ctaRoot) return;
				// Atualizar dados do servidor antes de mostrar
				try {
					await fetchPendingOs();
					// forçar repopular o select com dados do servidor, se existirem
					var sel = document.getElementById('rdo-cta-os-select'); if (sel) sel.dataset.populated = '0';
					populateOsSelect();
				} catch(e){}
				ctaRoot.style.display = '';
				ctaRoot.setAttribute('aria-hidden', 'false');
				const first = ctaRoot.querySelector('input, button, select');
				if (first) first.focus();
			}

			function hideCTA() {
				const ctaRoot = document.getElementById('rdo-mobile-cta');
				if (!ctaRoot) return;
				ctaRoot.style.display = 'none';
				ctaRoot.setAttribute('aria-hidden', 'true');
			}

			function applyCreateActivityFromInputs() {
				const os = (document.getElementById('f-os') || {}).value || '-';
				const empresa = (document.getElementById('f-empresa') || {}).value || '-';
				const unidade = (document.getElementById('f-unidade') || {}).value || '-';
				const turno = (document.getElementById('f-turno') || {}).value || '-';
				const servico = (document.getElementById('f-servico') || {}).value || '-';

				// Inserir linha na tabela de atividades
				const tbody = document.querySelector('#atividades-wrapper tbody');
				if (tbody) {
					const row = document.createElement('tr');
					row.className = 'activities-row';
					row.innerHTML = `
						<td><input type="text" value="RDO gerado - ${servico}" readonly></td>
						<td><input type="text" value="${os}" readonly></td>
						<td><input type="text" value="${empresa}" readonly></td>
						<td><input type="text" value="${unidade}" readonly></td>
						<td><input type="text" value="${turno}" readonly></td>
						<td><button type="button" class="btn-remove-atividade" title="Remover atividade">×</button></td>
					`;
					const footer = tbody.querySelector('.activities-footer');
					tbody.insertBefore(row, footer || null);
				}

				// Decrementar contador
				const count = Math.max(0, parseInt(safeLocal.get('rdo_pending_count') || '0') - 1);
				safeLocal.set('rdo_pending_count', count.toString());
				updateNotificationCount();
				hideCTA();

				// Notificação
				if (window.NotificationManager && typeof window.NotificationManager.show === 'function') {
					window.NotificationManager.show('Atividade criada', 'A atividade foi adicionada localmente ao RDO.');
				}
			}

			function initCTA() {
				// Ligar handlers aos botões do CTA
				const createBtn = document.getElementById('rdo-cta-create-btn');
				const cancelBtn = document.getElementById('rdo-cta-cancel-btn');
				const osSelect = document.getElementById('rdo-cta-os-select');

				if (createBtn) createBtn.addEventListener('click', function(){
					// Delegar para a função que abre o modal do supervisor com o contexto do select
					if (!osSelect || !osSelect.value) {
						try { showToast('Por favor, selecione uma OS primeiro.', 'error'); } catch(e){}
						return;
					}
					var selectedOption = osSelect.options[osSelect.selectedIndex];
					if (!selectedOption) return;

					// Construir contexto a partir dos data-* da option selecionada
					var context = {
						os_id: selectedOption.value || '',
						numero_os: selectedOption.dataset.osNum || '',
						empresa: selectedOption.dataset.empresa || '',
						unidade: selectedOption.dataset.unidade || '',
						supervisor: selectedOption.dataset.supervisor || ''
						// Adicionar outros data-* se necessário (ex: rdo_count, po)
					};

					// Chamar a função global que abre o modal do supervisor
					if (window.rdoOpenSupervisorModal) {
						window.rdoOpenSupervisorModal(context);
						hideCTA(); // Fechar o CTA após abrir o modal
					}
				});
				if (cancelBtn) cancelBtn.addEventListener('click', hideCTA);

				// Popular o select ao iniciar
				populateOsSelect();
			}

			// Iniciar tudo
			(async function(){
				try {
					await fetchPendingOs();
					await updateNotificationCount();
					initCTA();
				} catch(e) {
					console.error('RDO startup failed', e);
				}
			})();

		} catch(e){ console.error('rdo.js notification button init error', e); }
	})();
})();
				const ctaRoot = document.getElementById('rdo-mobile-cta');
				if (!ctaRoot) return;

				// inserir botão Limpar cartões se não existir (apenas UI mobile)
				try {
					if (!ctaRoot.querySelector('.btn-clear-cards')) {
						var clearCardsBtn = document.createElement('button');
						clearCardsBtn.type = 'button';
						clearCardsBtn.className = 'btn-rdo small btn-clear-cards';
						clearCardsBtn.textContent = 'Limpar cartões';
						clearCardsBtn.style.marginRight = '8px';
						// inserir no topo do CTA, antes do conteúdo principal
						var header = ctaRoot.querySelector('.cta-header') || ctaRoot;
						header.insertBefore(clearCardsBtn, header.firstChild || null);
						clearCardsBtn.addEventListener('click', function(ev){ ev.preventDefault(); if (window.clearMobileCards) window.clearMobileCards({ remove: false }); });
					}
				} catch(e){}

				// Buttons inside CTA: Criar / Fechar
				const createBtn = document.getElementById('rdo-cta-create');
				const closeBtn = document.getElementById('rdo-cta-close');
				const applyBtn = ctaRoot.querySelector('.filter-actions button:last-child');
				const clearBtn = ctaRoot.querySelector('.filter-actions button:first-child');

				if (createBtn) {
					createBtn.addEventListener('click', function(ev){
						ev.preventDefault();
						var sel = document.getElementById('rdo-cta-os-select');
						if (sel && sel.selectedIndex > 0) {
							var opt = sel.options[sel.selectedIndex];
							var context = {
								rdo_id: opt.dataset.rdoId || '',
								os_id: opt.value || '',
								numero_os: opt.dataset.osNum || opt.value,
								empresa: opt.dataset.empresa || '',
								unidade: opt.dataset.unidade || '',
								supervisor: opt.dataset.supervisor || ''
							};
							if (window.rdoOpenSupervisorModal) {
								window.rdoOpenSupervisorModal(context);
							}
						} else {
							applyCreateActivityFromInputs();
						}
					});
				}
				if (closeBtn) {
					closeBtn.addEventListener('click', function(ev){ ev.preventDefault(); hideCTA(); });
				}
				if (applyBtn) applyBtn.addEventListener('click', applyCreateActivityFromInputs);
				if (clearBtn) clearBtn.addEventListener('click', () => { Array.from(ctaRoot.querySelectorAll('input')).forEach(i => i.value = ''); });

				// Popular select de OS: primeiro usa dados do servidor (window.__rdo_pending_list), senão fallback para tabela
				function populateOsSelect() {
					const sel = document.getElementById('rdo-cta-os-select');
					if (!sel) return;
					if (sel.dataset.populated === '1') return; // evitar repopular
					// start with placeholder
					sel.innerHTML = '<option value="">Selecione a OS...</option>';

					// calcular contador conhecido (prefere valor vindo do servidor)
					var knownCount = (typeof window.__rdo_pending_count === 'number') ? window.__rdo_pending_count : parseInt(safeLocal.get('rdo_pending_count') || '0') || 0;

					// Se não há pendentes conhecidos, não fazer fallback para tabela: indicar "Nenhuma OS nova"
					if (!Array.isArray(window.__rdo_pending_list) || !window.__rdo_pending_list.length) {
						if (knownCount === 0) {
							sel.innerHTML = '<option value="">Nenhuma OS nova</option>';
							sel.disabled = true;
							sel.dataset.populated = '1';
							return;
						}
					}

					// Se o servidor já forneceu uma lista, usar essa lista
					if (Array.isArray(window.__rdo_pending_list) && window.__rdo_pending_list.length) {
						sel.disabled = false;
						window.__rdo_pending_list.forEach(function(it){
							const opt = document.createElement('option');
							opt.value = it.id || it.rdo_id || it.numero_os || '';
							opt.dataset.rdoId = it.id || it.rdo_id || '';
							// 'codigo_os' removido do modelo — usar apenas numero_os quando disponível
							opt.dataset.osNum = it.numero_os || '';
							opt.dataset.empresa = it.empresa || it.cliente || '';
							opt.dataset.unidade = it.unidade || '';
							opt.dataset.supervisor = it.supervisor || '';
							opt.textContent = (opt.dataset.osNum ? opt.dataset.osNum + ' — ' : '') + (opt.dataset.empresa ? opt.dataset.empresa + ' — ' : '') + (opt.dataset.unidade || '');
							sel.appendChild(opt);
						});
						sel.dataset.populated = '1';
						return;
					}

					// fallback: ler linhas da tabela (somente se não tivermos um contador zerado e não houver lista do servidor)
					let rows = [];
					if (knownCount > 0 && (!Array.isArray(window.__rdo_pending_list) || !window.__rdo_pending_list.length)) {
						rows = Array.from(document.querySelectorAll('table tbody tr[data-numero-os]'));
						if (!rows.length) rows = Array.from(document.querySelectorAll('table tbody tr'));
					} else {
						rows = [];
					}
					rows.forEach(function(tr){
						const tds = tr.querySelectorAll('td');
						const rdoId = tr.dataset.rdoId || tr.dataset.rdo_id || tr.dataset.rdoid || (tds[0] ? tds[0].textContent.trim() : '');
						const osNum = tr.dataset.numeroOs || tr.dataset.numero_os || tr.dataset['numero-os'] || (tds[1] ? tds[1].textContent.trim() : '');
						const empresa = tr.dataset.empresa || (tds[4] ? tds[4].textContent.trim() : '');
						const unidade = tr.dataset.unidade || (tds[5] ? tds[5].textContent.trim() : '');
						const supervisor = tr.dataset.supervisor || (tds[16] ? tds[16].textContent.trim() : '');
						const opt = document.createElement('option');
						opt.value = rdoId || osNum || '';
						opt.dataset.rdoId = rdoId || '';
						opt.dataset.osNum = osNum || '';
						opt.dataset.empresa = empresa || '';
						opt.dataset.unidade = unidade || '';
						opt.dataset.supervisor = supervisor || '';
						let labelParts = [];
						if (osNum) labelParts.push(osNum);
						if (empresa) labelParts.push(empresa);
						if (unidade) labelParts.push(unidade);
						opt.textContent = labelParts.join(' — ') || (rdoId ? String(rdoId) : '(sem identificação)');
						sel.appendChild(opt);
					});
					sel.dataset.populated = '1';
				}

				populateOsSelect();

				// Ao mudar o select, abrir modal de edição com contexto preenchido
				const osSelect = document.getElementById('rdo-cta-os-select');
				if (osSelect) {
					osSelect.addEventListener('change', function(){
						const idx = osSelect.selectedIndex;
						if (idx <= 0) return; // primeira opção é placeholder
						const opt = osSelect.options[idx];
						const context = {
							rdo_id: opt.dataset.rdoId || '',
							os_id: opt.value || '',
							numero_os: opt.dataset.osNum || opt.value,
							empresa: opt.dataset.empresa || '',
							unidade: opt.dataset.unidade || '',
							supervisor: opt.dataset.supervisor || ''
						};
						// abrir modal supervisor usando função exposta
						if (window.rdoOpenSupervisorModal) window.rdoOpenSupervisorModal(context);
					});
				}

				// Função pública para limpar ou ajustar cartões mobile relacionados à OS
				window.clearMobileCards = function(opts) {
					opts = opts || {};
					var remove = !!opts.remove; // se true, remover cartões antigos; se false, apenas dimming/limpar infos
					var osId = opts.os_id || null;
					try {
						var list = document.querySelectorAll('.rdo-mobile-card, .rdo-mobile-item');
						Array.prototype.forEach.call(list, function(card){
							try {
								var cardOs = card.getAttribute('data-os-id') || (card.dataset && card.dataset.osId) || '';
								if (osId && String(cardOs) !== String(osId)) return; // filtrar se fornecido
								// remover conteúdo sensível: rdo-count e labels
								try { card.setAttribute('data-rdo-count', ''); } catch(e){}
								var head = card.querySelector('.head-right, .rdo-summary, .rdo-card-head');
								if (head) {
									var turno = head.querySelector('.turno'); if (turno) turno.textContent = '';
									var pill = head.querySelector('.rdo-pill'); if (pill) pill.textContent = '';
								}
								// remover botão abrir se remover for true
								if (remove) {
									var btn = card.querySelector('.open-supervisor, .btn-rdo.open-supervisor');
									if (btn) { try { btn.remove(); } catch(e){} }
									else try { card.parentNode && card.parentNode.removeChild(card); } catch(e){}
								} else {
									// aplicar estilo de 'limpo' (dim) para indicar que está vazio
									card.classList.add('cleared-by-supervisor');
									card.style.opacity = '0.45';
									card.style.pointerEvents = 'none';
								}
							} catch(e){}
						});
					} catch(e){}
				};

				// Fecha o CTA quando o usuário clica fora dele ou no botão de notificação
				document.addEventListener('click', function(ev){
					try {
						var cta = document.getElementById('rdo-mobile-cta');
						var btn = document.getElementById('rdo-notification-btn');
						if (!cta) return;
						// se o CTA está visível e o clique não foi dentro do CTA nem no botão de notificação, fechar
						var targetInsideCTA = !!ev.target.closest && !!ev.target.closest('#rdo-mobile-cta');
						var targetIsBtn = !!ev.target.closest && !!ev.target.closest('#rdo-notification-btn');
						if (cta.style.display !== 'none' && !targetInsideCTA && !targetIsBtn) {
							hideCTA();
						}
					} catch(e){}

					// Preencher equipe (membros/funções)
					try {
						var teamWrapper = document.getElementById('edit-equipe-wrapper');
						if (teamWrapper) {
							// find prototype row (first .team-row)
							var proto = teamWrapper.querySelector('.team-row');
							// normalize payload: ensure `r` is defined (may be undefined on first open)
							var r = (typeof window.__rdo_last_fetched !== 'undefined' && window.__rdo_last_fetched) ? window.__rdo_last_fetched : {};
							// try to derive from selected option in CTA as fallback
							try {
								var selOpt = document.querySelector('#rdo-cta-os-select option:checked');
								if (selOpt && selOpt.dataset && selOpt.dataset.rdoId && (!r || !r.id)) {
									r.id = selOpt.dataset.rdoId || selOpt.value || r.id;
								}
							} catch(e){}
							// normalize payload: could be array or JSON string or comma-separated
							var teamData = (r && (r.equipe || r.team || r.equipe_list)) ? (r.equipe || r.team || r.equipe_list) : null;
							if (typeof teamData === 'string') {
								// try parse JSON first
								try { teamData = JSON.parse(teamData); } catch(e){
									// fallback: split by semicolon or newline into names only
									var lines = teamData.split(/\r?\n|;/).map(function(s){ return s.trim(); }).filter(Boolean);
									teamData = lines.map(function(name){ return { nome: name, funcao: '' }; });
								}
							}
							if (!Array.isArray(teamData)) teamData = [];
							// remove existing team rows (keep footer)
							Array.from(teamWrapper.querySelectorAll('.team-row')).forEach(function(tr){ tr.parentNode && tr.parentNode.removeChild(tr); });
							// if no data, re-insert a single proto row (or create minimal)
							if (!teamData.length) {
								if (proto) {
									var clone = proto.cloneNode(true);
									// clear inputs
									Array.from(clone.querySelectorAll('input,textarea')).forEach(function(i){ try{i.value='';}catch(e){} });
									teamWrapper.insertBefore(clone, teamWrapper.querySelector('.team-footer') || null);
								} else {
									var row = document.createElement('div'); row.className='team-row';
									row.innerHTML = '<div class="form-field"><label>Nome</label><input name="equipe_nome[]" type="text" /></div><div class="form-field"><label>Função</label><input name="equipe_funcao[]" type="text" /></div>';
									teamWrapper.insertBefore(row, teamWrapper.querySelector('.team-footer') || null);
								}
							} else {
								// build rows for each member
								teamData.forEach(function(m){
									var row;
									if (proto) row = proto.cloneNode(true); else {
										row = document.createElement('div'); row.className='team-row';
										row.innerHTML = '<div class="form-field"><label>Nome</label><input name="equipe_nome[]" type="text" /></div><div class="form-field"><label>Função</label><input name="equipe_funcao[]" type="text" /></div>';
									}
									// fill values
									try { var inpN = row.querySelector('input[name="equipe_nome[]"]'); if (inpN) inpN.value = m.nome || m.name || m[0] || ''; } catch(e){}
									try { var inpF = row.querySelector('input[name="equipe_funcao[]"]'); if (inpF) inpF.value = m.funcao || m.funcao_pt || m.role || m[1] || ''; } catch(e){}
									teamWrapper.insertBefore(row, teamWrapper.querySelector('.team-footer') || null);
								});
							}
						}
					} catch(e){ console.warn('populate equipe failed', e); }
				}, true);

				// Esc fecha o CTA quando aberto
				document.addEventListener('keydown', function(ev){
					if (ev.key === 'Escape') {
						var cta = document.getElementById('rdo-mobile-cta');
						if (cta && cta.style.display !== 'none') hideCTA();
					}
				});
			

			// se não existe no DOM, criar (fallback)
			if (!notificationBtn) {
				// fallback menor: criar um botão mínimo
				notificationBtn = document.createElement('button');
				notificationBtn.id = 'rdo-notification-btn';
				notificationBtn.className = 'rdo-notification';
				notificationBtn.innerHTML = '<span class="material-icons">notifications</span><span class="count">0</span>';
				document.body.appendChild(notificationBtn);
				notificationBtn.addEventListener('click', showCTA);
			}

			initCTA();
			// Tentar obter contador atualizado do servidor na inicialização para garantir badge correto
			(async function(){
				try {
					await fetchPendingOs();
				} catch(e) {}
				try { updateNotificationCount(); } catch(e){}
			})();
			window.updateNotificationCount = updateNotificationCount; // Expor para uso externo se necessário

			// Função utilitária pública `ai` — assistente rápido para abrir CTA, popular select e abrir modal na primeira OS
			// Uso comum: window.ai() -> abre CTA, atualiza lista, seleciona a primeira OS e abre o modal do supervisor
			window.ai = async function(options) {
				options = options || {};
				try {
					// atualizar dados do servidor
					await fetchPendingOs();
					// repopular select
					var sel = document.getElementById('rdo-cta-os-select');
					if (sel) sel.dataset.populated = '0';
					populateOsSelect();

					// obter lista efetiva
					var list = Array.isArray(window.__rdo_pending_list) && window.__rdo_pending_list.length ? window.__rdo_pending_list.slice() : null;
					if (!list) {
						// construir a partir do select (ignorando placeholder)
						list = [];
						var sel2 = document.getElementById('rdo-cta-os-select');
						if (sel2) {
							for (var i=1;i<sel2.options.length;i++){
								var o = sel2.options[i];
								list.push({
									id: o.dataset.rdoId || o.value,
									numero_os: o.dataset.osNum || o.value,
									empresa: o.dataset.empresa || '',
									unidade: o.dataset.unidade || '',
									supervisor: o.dataset.supervisor || ''
								});
							}
						}
					}

					// mostrar CTA se solicitado
					if (options.showCTA !== false) showCTA();

					if (!list || !list.length) {
						return { success: false, message: 'Nenhuma OS pendente encontrada', count: 0, list: [] };
					}

					// ação padrão: abrir modal para primeiro item
					var idx = (typeof options.index === 'number') ? options.index : 0;
					idx = Math.max(0, Math.min(list.length-1, idx));
					var item = list[idx];

					// selecionar no select (se presente)
					if (sel) {
						// encontrar option correspondente
						for (var j=0;j<sel.options.length;j++){
							var opt = sel.options[j];
							if ((opt.dataset.rdoId && String(opt.dataset.rdoId) === String(item.id)) || (opt.dataset.osNum && String(opt.dataset.osNum) === String(item.numero_os)) || String(opt.value) === String(item.id) ) {
								sel.selectedIndex = j;
								// disparar change handler para abrir modal via código existente
								var ev = new Event('change', { bubbles: true });
								sel.dispatchEvent(ev);
								break;
							}
						}
					}

					// se rdoOpenSupervisorModal disponível, chamar diretamente (garante foco)
					if (window.rdoOpenSupervisorModal) {
						window.rdoOpenSupervisorModal({
							rdo_id: item.id || '',
							os_id: item.numero_os || '',
							numero_os: item.numero_os,
							empresa: item.empresa,
							unidade: item.unidade,
							supervisor: item.supervisor
						});
					}

					return { success: true, count: list.length, list: list, selected: item };
				} catch (e) {
					console.error('ai helper error', e);
					return { success: false, error: String(e) };
				}
			};

				// Ouvir mudanças de localStorage vindas de outras abas e atualizar badge
				window.addEventListener('storage', function(ev){
					if (ev.key === 'rdo_pending_count') {
						try { updateNotificationCount(); } catch(e){}
					}
				});

				// Observar alterações na tabela para repopular o select se o DOM mudar (ex: reload parcial)
				var table = document.querySelector('table tbody');
				if (table) {
					var mo = new MutationObserver(function(){
						try {
							var sel = document.getElementById('rdo-cta-os-select'); if (sel) sel.dataset.populated = '0';
							populateOsSelect();
						} catch(e){}
					});
					mo.observe(table, { childList: true, subtree: true });
				}

				// Global click handler para garantir fechamento de overlays ao clicar fora (caso handlers locais falhem)
				document.addEventListener('click', function(ev){
					try {
						var overlays = document.querySelectorAll('.modal-overlay.open');
						overlays.forEach(function(ov){
							if (ev.target === ov) {
								ov.classList.remove('open');
								ov.classList.add('is-hidden');
								ov.setAttribute('aria-hidden','true');
							}
						});
					} catch(e){}
				});


		// Handler do botão Enviar (modal Supervisor) - constrói FormData, envia ao servidor e atualiza tabela
		(function(){
			function getCSRF() {
				var m = document.cookie.match(/csrftoken=([^;]+)/);
				return m ? decodeURIComponent(m[1]) : '';
			}

			function formToPayload(form){
				// retorna FormData pronto para envio (inclui arquivos)
				try { return new FormData(form); } catch(e){ return null; }
			}

			function buildRowHtmlFrom(obj, fallbackForm){
				// Columns in template order (simplified): many fields may be missing; use fallbackForm when needed
				function v(k, fb){ if (obj && (obj[k] !== undefined && obj[k] !== null && obj[k] !== '')) return String(obj[k]); if (fb && fb[k] !== undefined) return String(fb[k]); return '-'; }
				var html = '' +
					'<td>' + v('ordem_servico_id', fallbackForm) + '</td>' +
					'<td>' + v('numero_os', fallbackForm) + '</td>' +
					'<td>' + v('contrato_po', fallbackForm) + '</td>' +
					'<td>' + v('empresa', fallbackForm) + '</td>' +
					'<td>' + v('unidade', fallbackForm) + '</td>' +
					'<td>' + v('supervisor', fallbackForm) + '</td>' +
					'<td>' + v('status_geral', fallbackForm) + '</td>' +
					'<td>' + v('data_inicio', fallbackForm) + '</td>' +
					'<td>' + v('rdo', fallbackForm) + '</td>' +
					'<td>' + v('turno', fallbackForm) + '</td>' +
					'<td>' + v('tanque_codigo', fallbackForm) + '</td>' +
					'<td>' + v('tanque_nome', fallbackForm) + '</td>' +
					'<td>' + v('tipo_tanque', fallbackForm) + '</td>' +
					'<td>' + v('numero_compartimentos', fallbackForm) + '</td>' +
					'<td>' + v('gavetas', fallbackForm) + '</td>' +
					'<td>' + v('patamares', fallbackForm) + '</td>' +
					'<td>' + v('volume_tanque_exec', fallbackForm) + '</td>' +
					'<td>' + v('servico_exec', fallbackForm) + '</td>' +
					'<td>' + v('metodo_exec', fallbackForm) + '</td>' +
					'<td>' + v('operadores_simultaneos', fallbackForm) + '</td>' +
					'<td>' + v('H2S_ppm', fallbackForm) + '</td>' +
					'<td>' + v('LEL', fallbackForm) + '</td>' +
					'<td>' + v('CO_ppm', fallbackForm) + '</td>' +
					'<td>' + v('O2_percent', fallbackForm) + '</td>' +
					'<td class="action-cell"><button class="action-btn edit" type="button"><span class="material-icons" aria-hidden="true">edit</span></button></td>' +
					'<td class="action-cell"><button class="action-btn view" type="button"><span class="material-icons" aria-hidden="true">visibility</span></button></td>';
				return html;
			}

			function extractFormFallback(form){
				var out = {};
				if (!form) return out;
				try {
					var fields = ['rdo','rdo_contagem','turno','rdo_data_inicio','contrato_po','tanque_codigo','tanque_nome','tipo_tanque','numero_compartimento','gavetas','patamar','volume_tanque_exec','servico_exec','metodo_exec','operadores_simultaneos','h2s_ppm','lel','co_ppm','o2_percent','observacoes'];
					fields.forEach(function(k){
						var el = form.querySelector('[name="'+k+'"]') || document.getElementById(k) || form.elements[k];
						if (el) out[k] = el.value || el.textContent || '';
					});
					// também coletar contexto visível
					out.empresa = (document.getElementById('sup-context-empresa')||{}).textContent || out.empresa || '';
					out.unidade = (document.getElementById('sup-context-unidade')||{}).textContent || out.unidade || '';
					out.supervisor = (document.getElementById('sup-context-supervisor')||{}).textContent || out.supervisor || '';
				} catch(e){}
				return out;
			}

			var btn = document.getElementById('btn-rdo');
			if (!btn) return; // nada a fazer

			btn.addEventListener('click', function(ev){
				ev.preventDefault && ev.preventDefault();
				var form = document.getElementById('form-supervisor');
				if (!form) { showToast('Formulário não encontrado', 'error'); return; }

				// Construir payload a partir do form (inclui arquivos)
				var fd = formToPayload(form);
				if (!fd) { showToast('Erro ao montar dados do formulário', 'error'); return; }

				// Adicionar campos de contexto que não fazem parte do form
				try { fd.append('empresa', (document.getElementById('sup-context-empresa')||{}).textContent || ''); } catch(e){}
				try { fd.append('unidade', (document.getElementById('sup-context-unidade')||{}).textContent || ''); } catch(e){}
				try { fd.append('supervisor', (document.getElementById('sup-context-supervisor')||{}).textContent || ''); } catch(e){}

				// UI feedback: mostrar loading persistente
				var origText = btn.textContent;
				btn.disabled = true;
				btn.classList.add('loading');
				btn.textContent = 'Enviando...';

				var url = '/api/rdo/create_ajax/';
				// Envio: tratar casos onde o servidor responde com sucesso mas não retorna JSON
				fetch(url, {
					method: 'POST',
					body: fd,
					credentials: 'same-origin',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'X-CSRFToken': getCSRF()
					}
				}).then(function(resp){
					// Sempre ler o corpo como texto; tentaremos parsear JSON, mas aceitaremos respostas vazias
					return resp.text().then(function(text){
						var data = null;
						if (text) {
							try { data = JSON.parse(text); } catch(e){ data = null; }
						}
						return { resp: resp, data: data };
					});
				}).then(function(result){
					var resp = result && result.resp; var data = result && result.data;
					var fallback = extractFormFallback(form);

					if (resp && resp.ok) {
						// sucesso: usar dados retornados se existirem, senão usar fallback
						var rowData = (data && typeof data === 'object') ? (data.rdo || data || {}) : {};
						if (rowData && rowData.data_inicio && rowData.data_inicio.indexOf && rowData.data_inicio.indexOf('T') !== -1) {
							try { rowData.data_inicio = new Date(rowData.data_inicio).toLocaleDateString('pt-BR'); } catch(e){}
						}

						// atualizar tabela (se existente)
						var tbody = document.querySelector('.tabela_conteiner table tbody');
						if (tbody) {
							var tr = document.createElement('tr');
							try {
								if (rowData.id) tr.dataset.rdoId = rowData.id;
								if (rowData.ordem_servico_id) tr.dataset.osId = rowData.ordem_servico_id;
								if (rowData.numero_os) tr.dataset.numeroOs = rowData.numero_os;
								if (rowData.contrato_po) tr.dataset.po = rowData.contrato_po;
								tr.dataset.empresa = rowData.empresa || fallback.empresa || '';
								tr.dataset.unidade = rowData.unidade || fallback.unidade || '';
								tr.dataset.supervisor = rowData.supervisor || fallback.supervisor || '';
								tr.dataset.turno = rowData.turno || fallback.turno || '';
								tr.dataset.servico = rowData.servico_exec || rowData.servico || fallback.servico_exec || '';
								tr.dataset.metodo = rowData.metodo_exec || rowData.metodo || fallback.metodo_exec || '';
								tr.dataset.data = rowData.data_inicio || fallback.rdo_data_inicio || '';
								tr.dataset.tanque = rowData.tanque_nome || fallback.tanque_nome || '';
							} catch(e){}
							tr.innerHTML = buildRowHtmlFrom(rowData, fallback);
							tbody.insertBefore(tr, tbody.firstChild);
							try { addNewRowEffect(tr); } catch(e){}
						}

						showToast((data && data.message) ? data.message : 'RDO criado com sucesso', 'success', { once: false });

						try { var overlay = document.getElementById('modal-supervisor-overlay'); if (overlay) { overlay.classList.remove('open'); overlay.classList.add('is-hidden'); overlay.setAttribute('aria-hidden','true'); } } catch(e){}

						// atualizar contadores locais / notificações se o endpoint retornou id/rdo_count
						try {
							var cnt = parseInt(localStorage.getItem('rdo_pending_count')||'0',10);
							if (!isNaN(cnt) && cnt > 0) { localStorage.setItem('rdo_pending_count', String(Math.max(0, cnt-1))); if (window.updateNotificationCount) window.updateNotificationCount(); }
						} catch(e){}

						// reload curto para sincronizar o estado da página (mantendo UX atual)
						setTimeout(function(){ try { window.location.reload(); } catch(e) { console.info('reload failed', e); } }, 800);
					} else {
						// falha: tentar extrair mensagem do payload JSON, se presente
						var msg = 'Falha ao salvar RDO';
						if (data && (data.error || data.message)) msg = data.error || data.message;
						else if (resp && resp.status) msg = 'Erro servidor: ' + resp.status;
						showToast(msg, 'error', { once: false, force: true });
					}
				}).catch(function(err){
					console.warn('rdo create (btn-rdo) failed', err);
					if (err && typeof err === 'object' && typeof err.message === 'string') showToast(err.message, 'error', { force: true });
					else showToast('Erro ao enviar RDO', 'error', { force: true });
				}).finally(function(){
					// limpar estado visual do botão
					try { btn.disabled = false; btn.textContent = origText; btn.classList.remove('loading'); } catch(e){}
				});
			});
		})();

;

// --- Equipe: shim de compatibilidade para selects/inputs ---
(function(){
	'use strict';

	function onReady(fn){
		if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
		else fn();
	}

	onReady(function(){
		try {
			function clearTeamRow(row){
				try {
					var nome = row && row.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
					var func = row && row.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
					if (nome){ if (nome.tagName === 'SELECT') nome.selectedIndex = 0; else nome.value = ''; }
					if (func){ if (func.tagName === 'SELECT') func.selectedIndex = 0; else func.value = ''; }
				} catch(e){ /* no-op */ }
			}

			function getLastRow(wrapper){
				try {
					var rows = wrapper ? Array.from(wrapper.querySelectorAll('.team-row')) : [];
					return rows.length ? rows[rows.length - 1] : null;
				} catch(e){ return null; }
			}

			// Após adicionar membro no Supervisor, limpar selects/inputs da última linha
			var addSup = document.getElementById('btn-add-membro');
			if (addSup){
				addSup.addEventListener('click', function(){
					// esperar o handler existente clonar a linha
					setTimeout(function(){
						var wrap = document.getElementById('equipe-wrapper');
						var row = getLastRow(wrap);
						if (row) clearTeamRow(row);
					}, 0);
				});
			}

			// Após adicionar no Editor, limpar selects/inputs da última linha
			var addEdit = document.getElementById('edit-btn-add-membro');
			if (addEdit){
				addEdit.addEventListener('click', function(){
					setTimeout(function(){
						var wrap = document.getElementById('edit-equipe-wrapper');
						var row = getLastRow(wrap);
						if (row) clearTeamRow(row);
					}, 0);
				});
			}

			// Expor helpers globais para popular e coletar equipe de forma resiliente
			try { window.RDO = window.RDO || {}; } catch(e) { /* no-op */ }
			if (typeof window !== 'undefined'){
				window.RDO.setTeamValues = function(wrapperId, team){
					try {
						var wrap = document.getElementById(wrapperId);
						if (!wrap) return;
						var rows = Array.from(wrap.querySelectorAll('.team-row'));
						var need = Array.isArray(team) ? team.length : 0;
						var addBtn = (wrapperId === 'edit-equipe-wrapper')
							? document.getElementById('edit-btn-add-membro')
							: document.getElementById('btn-add-membro');
						while (rows.length < need && addBtn){
							addBtn.click();
							rows = Array.from(wrap.querySelectorAll('.team-row'));
						}
						(team || []).forEach(function(m, i){
							var r = rows[i];
							if (!r) return;
							var nome = r.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
							var func = r.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
							var nomeVal = (m && (m.nome || m.name || m.pessoa || (Array.isArray(m) ? m[0] : ''))) || '';
							var funcVal = (m && (m.funcao || m.role || (Array.isArray(m) ? m[1] : ''))) || '';
							if (nome){ nome.value = nomeVal; if (nome.tagName === 'SELECT') nome.dispatchEvent(new Event('change')); }
							if (func){ func.value = funcVal; if (func.tagName === 'SELECT') func.dispatchEvent(new Event('change')); }
						});
					} catch(e){ /* no-op */ }
				};

				window.RDO.collectTeam = function(wrapperId){
					try {
						var wrap = document.getElementById(wrapperId);
						if (!wrap) return [];
						var out = [];
						Array.from(wrap.querySelectorAll('.team-row')).forEach(function(r){
							var nome = r.querySelector('select[name="equipe_nome[]"], input[name="equipe_nome[]"]');
							var func = r.querySelector('select[name="equipe_funcao[]"], input[name="equipe_funcao[]"]');
							var n = nome ? String(nome.value || '').trim() : '';
							var f = func ? String(func.value || '').trim() : '';
							if (n || f) out.push({ nome: n, funcao: f });
						});
						return out;
					} catch(e){ return []; }
				};
			}

		} catch(e){ /* no-op */ }
	});
})();

// --- Auto-popular equipe ao carregar detalhes do RDO (intercepta fetch) ---
(function(){
	'use strict';
	if (typeof window === 'undefined') return;
	if (window.__rdo_fetch_patched) return; // evitar dupla aplicação
	window.__rdo_fetch_patched = true;

	var origFetch = window.fetch;
	function isOpen(el){
		if (!el) return false;
		try {
			var hidden = el.getAttribute('aria-hidden');
			if (hidden === 'true') return false;
			var style = window.getComputedStyle(el);
			return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
		} catch(e){ return true; }
	}

	window.fetch = function(input, init){
		try {
			// Only intercept RDO detail endpoint responses to avoid cloning/parsing unrelated responses
			var url = '';
			try {
				if (typeof input === 'string') url = input;
				else if (input && input.url) url = input.url;
			} catch(e){ url = '' }

			// quick heuristic: only intercept requests that look like '/rdo/<id>/detail/'
			var shouldIntercept = false;
			try {
				if (url && /\/rdo\/[0-9a-zA-Z\-_%]+\/detail\/?(\?.*)?$/.test(url)) shouldIntercept = true;
			} catch(e){ shouldIntercept = false; }

			var p = origFetch(input, init);
			if (!shouldIntercept) return p;

			return p.then(function(resp){
				try {
					var clone = resp.clone();
					clone.json().then(function(data){
						try {
							if (!data || !data.rdo || !Array.isArray(data.rdo.equipe)) return;
							var equipe = data.rdo.equipe;
							// Decidir qual modal está aberto
							var editor = document.getElementById('modal-editor-overlay');
							var supervisor = document.getElementById('modal-supervisor-overlay');
							// Pequeno atraso para garantir que o DOM do modal esteja pronto
							setTimeout(function(){
								try {
									if (isOpen(editor) && document.getElementById('edit-equipe-wrapper')){
										if (window.RDO && typeof window.RDO.setTeamValues === 'function'){
											window.RDO.setTeamValues('edit-equipe-wrapper', equipe);
										}
									} else if (isOpen(supervisor) && document.getElementById('equipe-wrapper')){
										if (window.RDO && typeof window.RDO.setTeamValues === 'function'){
											window.RDO.setTeamValues('equipe-wrapper', equipe);
										}
									}
								} catch(e){ /* no-op */ }
							}, 50);
						} catch(e){ /* no-op */ }
					}).catch(function(){ /* not json */ });
				} catch(e){ /* no-op */ }
				return resp;
			});
		} catch(e){
			return origFetch(input, init);
		}
	};
})();



