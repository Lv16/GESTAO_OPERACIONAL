// Utilitário fetchJson: padroniza timeout, erros e parsing JSON
async function fetchJson(url, options = {}) {
    const timeout = options.timeout || 10000;
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    try {
        if (window.NotificationManager && typeof window.NotificationManager.showLoading === 'function') {
            window.NotificationManager.showLoading();
        }
    } catch (e) {}

    try {
        const resp = await fetch(url, Object.assign({}, options, { signal: controller.signal }));
        clearTimeout(id);
        const ct = resp.headers.get('content-type') || '';
        if (!resp.ok) {
            let body = '';
            try { body = await resp.text(); } catch (e) {}
            throw { status: resp.status, message: body || resp.statusText };
        }
        if (ct.indexOf('application/json') !== -1) {
            return await resp.json();
        }
        return { success: false, error: 'Resposta inválida do servidor' };
    } catch (err) {
        if (err.name === 'AbortError') throw { status: 0, message: 'timeout' };
        throw err;
    } finally {
        try {
            if (window.NotificationManager && typeof window.NotificationManager.hideLoading === 'function') {
                window.NotificationManager.hideLoading();
            }
        } catch (e) {}
    }
}

// Helper: escapa texto para uso em atributos HTML
function escapeHtml(unsafe) {
    if (unsafe === null || unsafe === undefined) return '';
    return String(unsafe)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Retorna o serviço primário (antes da vírgula) e a string completa
function getPrimaryService(full) {
    if (!full && full !== '') return { primary: '', full: '' };
    const s = String(full || '');
    if (s.indexOf(',') !== -1) {
        const parts = s.split(',').map(p => p.trim()).filter(p => p);
        return { primary: parts.length ? parts[0] : s, full: s };
    }
    return { primary: s, full: s };
}

// Gera HTML para a célula de serviço: mostra o primário e adiciona title com a lista completa (se houver)
function buildServiceCell(os) {
    // aceitar tanto payload com 'servicos' (lista completa) quanto apenas 'servico' (primário)
    const full = (os && (os.servicos || os.servico)) ? (os.servicos || os.servico) : '';
    const info = getPrimaryService(full);
    const titleAttr = (info.full && info.full !== info.primary) ? ` title="${escapeHtml(info.full)}"` : '';
    const display = (info.full && info.full !== info.primary) ? `${escapeHtml(info.primary)} (…)` : escapeHtml(info.primary);
    // incluir atributos e classe iguais ao template para que o popover por delegação funcione
    const dataServicos = ` data-servicos="${escapeHtml(info.full)}"`;
    const dataPrimary = ` data-primary="${escapeHtml(info.primary)}"`;
    return `<td class="td-servicos"${dataServicos}${dataPrimary}${titleAttr}><span class="servico-primary">${display}</span></td>`;
}

// Gera HTML para a célula de Tanques: exibe apenas o primeiro tanque e guarda a lista completa em data-tanques
function buildTankCell(os) {
    const full = (os && (os.tanques || os.tanque)) ? (os.tanques || os.tanque) : '';
    const parts = String(full || '').split(',').map(s => s.trim()).filter(Boolean);
    const primary = parts.length ? parts[0] : '';
    const titleAttr = full && full !== primary ? ` title="${escapeHtml(full)}"` : '';
    const dataAttr = ` data-tanques="${escapeHtml(full)}"`;
    const more = parts.length > 1 ? ' <span class="tanques-more"> (…) </span>' : '';
    return `<td class="td-tanques"${dataAttr}${titleAttr}><span class="tanque-primary">${escapeHtml(primary)}</span>${more}</td>`;
}

// Se NotificationManager ainda não estiver carregado, cria um shim leve que enfileira chamadas
if (!window.NotificationManager) {
    window.NotificationManager = {
        queued: [],
        show(...args) { this.queued.push(['show', args]); },
        showLoading() { this.queued.push(['showLoading', []]); },
        hideLoading() { this.queued.push(['hideLoading', []]); },
        applyReal(real) {
            // aplica chamadas enfileiradas para o real NotificationManager
            this.queued.forEach(([m, a]) => { if (typeof real[m] === 'function') real[m](...a); });
            this.queued = [];
        }
    };
    // Quando o real NotificationManager inicializar, ele deve chamar NotificationManager.applyReal
}

    // Nova função: abrir o link de logística (agora usa link fixo)
// Esta função foi desativada pois o link logistica agora é fixo
// Mantemos a referência para compatibilidade com template/código legado

// Recarrega a página ao submeter o formulário de edição do modal-edicao
document.addEventListener('DOMContentLoaded', function() {
    // Mobile full menu sheet toggle
    try {
        const openBtn = document.getElementById('mobile-open-menu');
        const sheet = document.getElementById('mobile-full-menu');
        const closeBtn = document.getElementById('mobile-full-menu-close');
        function openSheet() {
            if (!sheet) return;
            sheet.setAttribute('aria-hidden', 'false');
            sheet.classList.add('open');
            // prevent body scroll
            document.body.style.overflow = 'hidden';
            // focus first link
            const first = sheet.querySelector('a.menu-btn'); if (first) first.focus();
        }
        function closeSheet() {
            if (!sheet) return;
            sheet.setAttribute('aria-hidden', 'true');
            sheet.classList.remove('open');
            document.body.style.overflow = '';
            if (openBtn) openBtn.focus();
        }
        if (openBtn && sheet) openBtn.addEventListener('click', function(e){ e.preventDefault(); openSheet(); });
        if (closeBtn && sheet) closeBtn.addEventListener('click', function(e){ e.preventDefault(); closeSheet(); });
        // close on Escape
        document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && sheet && sheet.classList.contains('open')) { closeSheet(); } });
    } catch (e) {}
    // Força autocomplete off em inputs problemáticos (ajuda a evitar dropdowns de autofill do navegador)
    try {
        ['id_cliente','id_unidade','servico_input','edit_servico_input','edit_cliente','edit_unidade'].forEach(function(id) {
            try {
                const el = document.getElementById(id);
                if (el) el.setAttribute('autocomplete', 'off');
            } catch(e) {}
        });
    } catch(e) {}
    
    // Técnica adicional: ao focar, renomear temporariamente o atributo `name` para evitar que o navegador associe e mostre autofill.
    // Restauramos o nome no blur ou antes do submit. Funciona bem quando há um campo hidden real que será enviado (ex.: servico_hidden),
    // e para campos de cliente/unidade restauramos o name no blur (campo é necessário para envio).
    try {
        const inputsToProtect = ['id_cliente','id_unidade','servico_input','edit_servico_input','edit_cliente','edit_unidade'];
        inputsToProtect.forEach(function(id) {
            try {
                const el = document.getElementById(id);
                if (!el) return;
                // guardar nome original
                const origName = el.getAttribute('name');
                if (!origName) {
                    // alguns campos (servico_input) podem não ter name; ainda assim protegemos
                    el.dataset._origName = '';
                } else {
                    el.dataset._origName = origName;
                }

                el.addEventListener('focus', function() {
                    try {
                        // atribuir um nome 'no_autofill_<rand>' temporário
                        const rnd = 'no_autofill_' + Math.random().toString(36).slice(2,8);
                        // store current name in data- attribute
                        try { el.dataset._beforeAutofillName = el.getAttribute('name') || ''; } catch(e) {}
                        try { el.setAttribute('name', rnd); } catch(e) {}
                        try { el.setAttribute('autocomplete', 'off'); } catch(e) {}
                        // Alguns navegadores já preenchem antes do focus handler, por isso aplicar readonly hack por curto período
                        try {
                            el.setAttribute('readonly', 'readonly');
                            // remover readonly logo em seguida para permitir digitação
                            setTimeout(function() { try { el.removeAttribute('readonly'); } catch(e) {} }, 50);
                        } catch(e) {}
                    } catch(e) {}
                }, { passive: true });

                el.addEventListener('blur', function() {
                    try {
                        // restaurar o name original
                        const before = el.dataset._beforeAutofillName;
                        if (typeof before !== 'undefined') {
                            try {
                                if (before === '') {
                                    el.removeAttribute('name');
                                } else {
                                    el.setAttribute('name', before);
                                }
                            } catch(e) {}
                            try { delete el.dataset._beforeAutofillName; } catch(e) {}
                        }
                    } catch(e) {}
                }, { passive: true });
            } catch(e) {}
        });

        // Antes de enviar o formulário, garantir que todos os nomes originais estejam restaurados
        try {
            const form = document.getElementById('form-os');
            if (form) {
                form.addEventListener('submit', function() {
                    inputsToProtect.forEach(function(id) {
                        try {
                            const el = document.getElementById(id);
                            if (!el) return;
                            const before = el.dataset._beforeAutofillName;
                            if (typeof before !== 'undefined') {
                                if (before === '') el.removeAttribute('name'); else el.setAttribute('name', before);
                            }
                        } catch(e) {}
                    });
                });
            }
        } catch(e) {}
    } catch(e) {}
    // Normaliza células de tanques geradas no servidor: exibe apenas o primeiro tanque e adiciona indicador quando houver mais
    (function normalizeTankCells() {
        try {
            const tds = document.querySelectorAll('td.td-tanques');
            tds.forEach(td => {
                try {
                    const full = td.getAttribute('data-tanques') || '';
                    const parts = String(full || '').split(',').map(s => s.trim()).filter(Boolean);
                    const primary = parts.length ? parts[0] : '';
                    const primaryEl = td.querySelector('.tanque-primary');
                    if (primaryEl) {
                        primaryEl.textContent = primary;
                    } else {
                        // criar elemento caso não exista
                        const span = document.createElement('span');
                        span.className = 'tanque-primary';
                        span.textContent = primary;
                        td.innerHTML = '';
                        td.appendChild(span);
                    }
                    const moreEl = td.querySelector('.tanques-more');
                    if (parts.length > 1) {
                        if (!moreEl) {
                            const m = document.createElement('span');
                            m.className = 'tanques-more';
                            m.setAttribute('aria-label', 'Mostrar todos os tanques');
                            m.textContent = ' (…)';
                            td.appendChild(m);
                        }
                    } else {
                        if (moreEl) moreEl.remove();
                    }
                } catch (e) {}
            });
        } catch (e) {}
    })();
    var formEdicao = document.getElementById('form-edicao');
    if (formEdicao) {
        formEdicao.addEventListener('submit', function() {
            setTimeout(function() {
                window.location.reload();
            }, 700); 
        });
    }
});

// Mobile (home): tabela em cards com "Ver mais/Ver menos" por linha
document.addEventListener('DOMContentLoaded', function() {
    try {
        // Only enable mobile row toggles on the Home page (dashboard present)
        if (!document.getElementById('dashboard-panel')) return;
        const mq = window.matchMedia('(max-width: 700px)');

        function applyRowToggles() {
            const table = document.querySelector('.tabela_conteiner table');
            if (!table) return;

            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                try {
                    if (!row.querySelector('td')) return;
                    if (row.querySelector('td.mobile-toggle-cell')) return;

                    const td = document.createElement('td');
                    td.className = 'mobile-toggle-cell';

                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'mobile-row-toggle';
                    btn.setAttribute('aria-expanded', 'false');
                    btn.textContent = 'Ver mais';

                    btn.addEventListener('click', function(ev) {
                        try { ev.preventDefault(); } catch (e) {}
                        const expanded = row.classList.toggle('is-expanded');
                        btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
                        btn.textContent = expanded ? 'Ver menos' : 'Ver mais';
                    });

                    td.appendChild(btn);
                    row.appendChild(td);
                } catch (e) {}
            });
        }

        function removeRowToggles() {
            const table = document.querySelector('.tabela_conteiner table');
            if (!table) return;

            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                try {
                    row.classList.remove('is-expanded');
                    const td = row.querySelector('td.mobile-toggle-cell');
                    if (td) td.remove();
                } catch (e) {}
            });
        }

        function sync() {
            if (mq && mq.matches) {
                applyRowToggles();
            } else {
                removeRowToggles();
            }
        }

        sync();
        try {
            mq.addEventListener('change', sync);
        } catch (e) {
            // Safari legado
            try { mq.addListener(sync); } catch (e2) {}
        }
    } catch (e) {}
});

// Popover de serviços: ao clicar na célula de Serviços, mostrar lista completa
document.addEventListener('DOMContentLoaded', function() {
    let currentPopover = null;

    function closePopover() {
        if (currentPopover && currentPopover.parentNode) {
            currentPopover.parentNode.removeChild(currentPopover);
        }
        currentPopover = null;
    }

    function buildPopoverContent(fullList, numeroOS) {
        const wrap = document.createElement('div');
        wrap.className = 'servicos-popover';
        const title = document.createElement('h4');
        title.textContent = numeroOS ? `Serviços da OS ${numeroOS}` : 'Serviços desta OS';
        wrap.appendChild(title);
        const ul = document.createElement('ul');
        const items = String(fullList || '')
            .split(',')
            .map(s => s.trim())
            .filter(Boolean);
        if (items.length === 0) {
            const li = document.createElement('li');
            li.textContent = 'Nenhum serviço definido.';
            ul.appendChild(li);
        } else {
            items.forEach(s => {
                const li = document.createElement('li');
                li.textContent = s;
                ul.appendChild(li);
            });
        }
        wrap.appendChild(ul);
        return wrap;
    }

    function positionPopover(pop, anchor) {
        const rect = anchor.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
        pop.style.top = (rect.bottom + scrollTop + 6) + 'px';
        // Alinhar à esquerda, mas caber na viewport
        let left = rect.left + scrollLeft;
        document.body.appendChild(pop);
        const popRect = pop.getBoundingClientRect();
        if (left + popRect.width > (window.innerWidth - 12)) {
            left = Math.max(12, window.innerWidth - popRect.width - 12) + scrollLeft;
        }
        pop.style.left = left + 'px';
    }

    function onCellClick(e) {
        const cell = e.currentTarget;
        const full = cell.getAttribute('data-servicos') || cell.getAttribute('data-primary') || '';
        const row = cell.closest('tr');
        const numeroOS = row ? (row.getAttribute('data-numero-os') || '') : '';
        closePopover();
        const pop = buildPopoverContent(full, numeroOS);
        currentPopover = pop;
        positionPopover(pop, cell);
    }

    // Usar delegação de eventos para que células adicionadas dinamicamente também funcionem
    document.addEventListener('click', function(ev) {
        const td = ev.target && ev.target.closest ? ev.target.closest('td.td-servicos') : null;
        if (td) {
            // se clicou em uma célula de serviços, abrir popover
            ev.stopPropagation();
            onCellClick({ currentTarget: td });
            return;
        }
        // click em célula de tanques: popover mostrando lista de tanques
        const tdTan = ev.target && ev.target.closest ? ev.target.closest('td.td-tanques') : null;
        if (tdTan) {
            ev.stopPropagation();
            // reaproveitar a lógica de popover: construir conteúdo a partir de data-tanques
            closePopover();
            const full = tdTan.getAttribute('data-tanques') || '';
            const numeroOS = tdTan.closest('tr') ? (tdTan.closest('tr').getAttribute('data-numero-os') || '') : '';
            const wrap = document.createElement('div');
            wrap.className = 'servicos-popover';
            const title = document.createElement('h4');
            title.textContent = numeroOS ? `Tanques da OS ${numeroOS}` : 'Tanques desta OS';
            wrap.appendChild(title);
            const ul = document.createElement('ul');
            const items = String(full || '').split(',').map(s => s.trim()).filter(Boolean);
            if (items.length === 0) {
                const li = document.createElement('li');
                li.textContent = 'Nenhum tanque definido.';
                ul.appendChild(li);
            } else {
                items.forEach(s => {
                    const li = document.createElement('li');
                    li.textContent = s;
                    ul.appendChild(li);
                });
            }
            wrap.appendChild(ul);
            currentPopover = wrap;
            positionPopover(wrap, tdTan);
            return;
        }
        // se clicou fora do popover e não em td.td-servicos, fecha
        const t = ev.target;
        if (currentPopover && t instanceof Node) {
            if (!currentPopover.contains(t) && !(t.closest && t.closest('td.td-servicos'))) {
                closePopover();
            }
        }
    });
    // Fecha popover com ESC
    document.addEventListener('keydown', function(ev) {
        if (ev.key === 'Escape') closePopover();
    });
    document.addEventListener('keydown', function(ev) {
        if (ev.key === 'Escape') closePopover();
    });
});

// Conecta campos Cliente/Unidade aos datalists e valida contra opções cadastradas
document.addEventListener('DOMContentLoaded', function() {
    try {
        const dlClientes = document.getElementById('clientes_datalist');
        const dlUnidades = document.getElementById('unidades_datalist');
        // Campos na criação de OS (form principal inside modal)
        const inpCliente = document.getElementById('id_cliente') || document.querySelector("input[name='cliente']");
        const inpUnidade = document.getElementById('id_unidade') || document.querySelector("input[name='unidade']");
        // Campos no modal de edição de OS
        const editCliente = document.getElementById('edit_cliente');
        const editUnidade = document.getElementById('edit_unidade');
        // Campos de filtro
        const filtroCliente = document.querySelector("#campos-filtro input[name='cliente']");
        const filtroUnidade = document.querySelector("#campos-filtro input[name='unidade']");

        function attachDatalist(inputEl, datalistEl) {
            if (!inputEl || !datalistEl) return;
            inputEl.setAttribute('list', datalistEl.id);
            // Validação: exige que o valor esteja entre as opções do datalist
            inputEl.addEventListener('blur', function() {
                const val = (inputEl.value || '').trim();
                if (!val) return; // vazio permitido dependendo do contexto
                const has = Array.from(datalistEl.options).some(opt => (opt.value || '').trim().toLowerCase() === val.toLowerCase());
                if (!has) {
                    // feedback sutil: borda vermelha por alguns segundos
                    const prev = inputEl.style.borderColor;
                    inputEl.style.borderColor = '#e74c3c';
                    inputEl.title = 'Selecione um valor cadastrado';
                    setTimeout(() => { inputEl.style.borderColor = prev || ''; }, 1500);
                } else {
                    inputEl.title = '';
                }
            });
        }

        // Dica visual abaixo do campo sobre a validação por cadastros
        function ensureHint(inputEl, datalistEl, tipoLabel) {
            if (!inputEl) return;
            // don't show datalist validation hints inside the RDO filters panel (compact mode)
            if (inputEl.closest && inputEl.closest('#rdo-filters-panel')) return;
            const parent = inputEl.parentNode;
            if (!parent) return;
            // remove dica anterior
            const prev = parent.querySelector('.hint-datalist');
            if (prev) prev.remove();
            const hint = document.createElement('div');
            hint.className = 'hint-datalist';
            hint.style.fontSize = '12px';
            hint.style.color = '#6b7280';
            hint.style.marginTop = '6px';
            const hasList = !!datalistEl;
            const count = hasList ? (datalistEl.options ? datalistEl.options.length : 0) : 0;
            if (!hasList) {
                hint.textContent = `Validação: selecione um ${tipoLabel} cadastrado.`;
            } else if (count > 0) {
                hint.textContent = `Validação: selecione um ${tipoLabel} cadastrado (sugestões ao digitar).`;
            } else {
                hint.textContent = `Validação: selecione um ${tipoLabel} cadastrado. Nenhum ${tipoLabel} encontrado — cadastre para habilitar sugestões.`;
            }
            parent.appendChild(hint);
        }

        attachDatalist(inpCliente, dlClientes);
        attachDatalist(inpUnidade, dlUnidades);
        // Repor placeholders visualmente na criação de OS
        if (inpCliente && !inpCliente.placeholder) {
            inpCliente.placeholder = 'Selecione um cliente cadastrado';
        }
        if (inpUnidade && !inpUnidade.placeholder) {
            inpUnidade.placeholder = 'Selecione uma unidade cadastrada';
        }
        // Dicas visuais na criação de OS
        ensureHint(inpCliente, dlClientes, 'cliente');
        ensureHint(inpUnidade, dlUnidades, 'unidade');
        attachDatalist(editCliente, dlClientes);
        attachDatalist(editUnidade, dlUnidades);
        attachDatalist(filtroCliente, dlClientes);
        attachDatalist(filtroUnidade, dlUnidades);
        // Placeholders descritivos nos filtros
        if (filtroCliente) {
            filtroCliente.placeholder = 'Filtrar por cliente cadastrado';
        }
        if (filtroUnidade) {
            filtroUnidade.placeholder = 'Filtrar por unidade cadastrada';
        }
    } catch (e) {
        // silencioso
    }
});

// Drawer lateral expansível
document.addEventListener('DOMContentLoaded', function() {
    const hamburger = document.getElementById('hamburger-menu');
    const drawer = document.getElementById('drawer-nav');
    const siteWrapper = document.getElementById('site-wrapper');
    const body = document.body;
    function openDrawer() {
        drawer.classList.add('open');
        body.classList.add('drawer-open');
    }
    function closeDrawer() {
        drawer.classList.remove('open');
        body.classList.remove('drawer-open');
    }
    if (hamburger && drawer) {
        hamburger.addEventListener('click', function(e) {
            e.stopPropagation();
            if (drawer.classList.contains('open')) {
                closeDrawer();
            } else {
                openDrawer();
            }
        });
    }
    // Fecha ao clicar fora do drawer
    document.addEventListener('click', function(e) {
        if (drawer.classList.contains('open') && !drawer.contains(e.target) && !hamburger.contains(e.target)) {
            closeDrawer();
        }
    });
    // Fecha com ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && drawer.classList.contains('open')) {
            closeDrawer();
        }
    });
});

// Menu Hamburguer
document.addEventListener('DOMContentLoaded', function() {
    const hamburger = document.getElementById('hamburger-menu');
    const nav = document.getElementById('main-nav');
    if (hamburger && nav) {
        hamburger.addEventListener('click', function() {
            nav.classList.toggle('open');
        });
        hamburger.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' || e.key === ' ') nav.classList.toggle('open');
        });
    }
});
// Limpa a flag do sessionStorage ao fazer logout ANTES do submit
document.addEventListener('DOMContentLoaded', function() {
    var logoutForm = document.getElementById('logoutForm');
    var logoutOverlay = document.getElementById('logoutOverlay');
    if (logoutForm) {
        logoutForm.addEventListener('submit', function(e) {
            e.preventDefault();
            // Exibe overlay de logout
            if (logoutOverlay) {
                logoutOverlay.classList.add('show');
                logoutOverlay.style.display = 'flex';
            }
            setTimeout(function() {
                sessionStorage.removeItem('welcome_shown');
                logoutForm.submit();
            }, 1000); // 1 segundo de tela de logout
        });
    }
});

// Preencher e travar cliente/unidade ao selecionar OS existente no modal de nova OS
document.addEventListener('DOMContentLoaded', function() {
    const radioButtons = document.querySelectorAll('#box-opcao-container input[type="radio"]');
    const osExistenteField = document.getElementById('os-existente-Field');
    const clienteField = document.getElementById('id_cliente');
    const unidadeField = document.getElementById('id_unidade');
    const osExistenteSelect = document.getElementById('os_existente_select');

    function setFieldsDisabled(disabled) {
        if (clienteField) clienteField.disabled = disabled;
        if (unidadeField) unidadeField.disabled = disabled;
    }

    function preencherClienteUnidadeDaOS(osId) {
        if (!osId) return;
        (async () => {
            try {
                const data = await fetchJson(`/buscar_os/${osId}/`);
                if (data && data.success && data.os) {
                    if (clienteField && data.os.cliente) clienteField.value = data.os.cliente;
                    if (unidadeField && data.os.unidade) unidadeField.value = data.os.unidade;
                    // Preencher também solicitante, PO, regime de operação e data de início
                    try {
                        const solicitanteEl = document.getElementById('id_solicitante') || document.querySelector('[name="solicitante"]');
                        const poEl = document.getElementById('id_po') || document.querySelector('[name="po"]');
                        const tipoOpEl = document.getElementById('id_tipo_operacao') || document.querySelector('[name="tipo_operacao"]');
                        const dataInicioEl = document.getElementById('id_data_inicio') || document.querySelector('[name="data_inicio"]');

                        const solicitanteVal = (data.os.solicitante && data.os.solicitante.trim()) ? data.os.solicitante : (data.os.solicitante_from_first || '');
                        const poVal = (data.os.po && data.os.po.toString().trim()) ? data.os.po : (data.os.po_from_first || '');
                        const tipoOpVal = (data.os.tipo_operacao && data.os.tipo_operacao.trim()) ? data.os.tipo_operacao : (data.os.tipo_operacao_from_first || '');
                        const dataInicioVal = (data.os.data_inicio && data.os.data_inicio.toString().trim()) ? data.os.data_inicio : (data.os.data_inicio_from_first || '');

                        if (solicitanteEl) {
                            try { solicitanteEl.value = solicitanteVal || ''; } catch(e) { /* noop */ }
                        }
                        if (poEl) {
                            try { poEl.value = poVal || ''; } catch(e) { /* noop */ }
                        }
                        if (tipoOpEl) {
                            try {
                                // if select, try to set by value or by option text
                                if (tipoOpEl.tagName === 'SELECT') {
                                    let foundOpt = Array.from(tipoOpEl.options).find(o => o.value === tipoOpVal || o.text === tipoOpVal);
                                    if (foundOpt) tipoOpEl.value = foundOpt.value;
                                } else {
                                    tipoOpEl.value = tipoOpVal || '';
                                }
                            } catch(e) {}
                        }
                        if (dataInicioEl) {
                            try { dataInicioEl.value = dataInicioVal || ''; } catch(e) {}
                        }
                    } catch(e) {
                        console.debug('preencherClienteUnidadeDaOS - fill extra fields failed', e);
                    }
                    // Se o backend retornou a lista completa de serviços, popular o widget de tags
                    try {
                        const createServContainer = document.getElementById('servico_tags_container');
                        const createServHidden = document.getElementById('servico_hidden');
                        if (createServContainer && typeof createServContainer.loadFromString === 'function') {
                            createServContainer.loadFromString(data.os.servicos || data.os.servico || '');
                            try { if (typeof createServContainer.loadIntoTanques === 'function') createServContainer.loadIntoTanques(); } catch(e){}
                        }
                        if (createServHidden) {
                            createServHidden.value = data.os.servicos || data.os.servico || '';
                        }
                    } catch (e) { /* silencioso */ }
                } else if (data && data.error) {
                    NotificationManager.show(data.error || 'Erro ao buscar OS', 'error');
                } else {
                    NotificationManager.show('Resposta inesperada ao buscar OS', 'error');
                }
            } catch (err) {
                NotificationManager.show('Erro ao buscar dados da OS existente: ' + (err.message || JSON.stringify(err)), 'error');
            }
        })();
    }


    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.value === 'existente') {
                setFieldsDisabled(true);
                if (osExistenteSelect && osExistenteSelect.value) {
                    preencherClienteUnidadeDaOS(osExistenteSelect.value);
                }
            } else {
                setFieldsDisabled(false);
                if (clienteField) clienteField.value = '';
                if (unidadeField) unidadeField.value = '';
            }
        });
    });

    if (osExistenteSelect) {
        osExistenteSelect.addEventListener('change', function() {
            const radioExistente = Array.from(radioButtons).find(r => r.value === 'existente' && r.checked);
            if (radioExistente) {
                preencherClienteUnidadeDaOS(this.value);
            }
        });
    }

    const radioExistente = Array.from(radioButtons).find(r => r.value === 'existente' && r.checked);
    if (radioExistente && osExistenteSelect && osExistenteSelect.value) {
        setFieldsDisabled(true);
        preencherClienteUnidadeDaOS(osExistenteSelect.value);
    } else {
        setFieldsDisabled(false);
    }
});


const servicosEspeciais = [
    "VISITA TÉCNICA", "DELINEAMENTO DE ATIVIDADES", "carreta de armazenamento temporário", "certificação gas fire", "certificação gas free", "coleta e análise da água", "coleta e análise do ar", "descarte de resíduos", "descomissionamento", "descontaminação profunda na embarcação", "desmobilização de equipamentos", "desmobilização de pessoas", "desmobilização de pessoas e equipamentos", "desobstrução", "desobstrução da linha de drenagem aberta", "diária da equipe de limpeza de tanques", "diária de ajudante operacional", "diária de consumíveis para limpeza", "diária de consumíveis para pintura", "diária de resgatista", "diária de supervisor", "diária do técnico de segurança do trabalho", "elaboração do pmoc", "emissão de free for fire", "ensacamento e remoção", "equipamentos em stand by", "equipe em stand by", "esgotamento de resíduo", "fornecimento de almoxarife", "fornecimento de auxiliar offshore", "fornecimento de caminhão vácuo", "fornecimento de carreta tanque", "fornecimento de eletricista", "fornecimento de engenheiro químico", "fornecimento de equipamentos e consumíveis", "fornecimento de equipe de alpinista industrial", "fornecimento de equipe de resgate", "fornecimento de irata n1 ou n2", "fornecimento de irata n3", "fornecimento de mão de obra operacional", "fornecimento de materiais", "fornecimento de mecânico", "fornecimento de químicos", "fornecimento de técnico offshore", "hotel, alimentação e transfer por paxinspeção por boroscópio", "inventário", "lista de verificação e planejamento dos materiais a bordo", "limpeza (dutos + coifa + coleta e análise de ar + lavanderia)", "limpeza (dutos + coifa + coleta e análise de ar)", "limpeza (dutos + coifa)", "limpeza da casa de bombas", "limpeza de área do piso de praça", "limpeza de coifa", "limpeza de coifa de cozinha", "limpeza de compartimentos void e cofferdans", "limpeza de dutos", "limpeza de dutos da lavanderia", "limpeza de dutos de ar condicionado", "limpeza de exaustor de cozinha", "limpeza de lavanderia", "limpeza de silos", "limpeza de vaso", "limpeza e descontaminação de carreta", "limpeza geral na embarcação", "limpeza, tratamento e pintura", "locação de equipamentos", "medição de espessura", "mobilização de equipamentos", "mobilização de pessoas", "mobilização de pessoas e equipamentos", "mobilização/desmobilização de carreta tanque", "pintura", "radioproteção norm", "renovação do pmoc", "segregação", "sinalização e isolamento de rejeitos", "serviço de irata", "shut down", "survey para avaliação de atividade", "taxa diária de auxiliar à disposição", "taxa diária de supervisor/operador à disposição", "taxa mensal de equipe onshore", "vigia"
];

// Verifica se o serviço selecionado é especial

function verificaServicoEspecial(valor) {
    if (!valor) return false;
    valor = valor.toLowerCase().trim();
    return servicosEspeciais.some(s => valor === s.toLowerCase());
}
// Atualiza os campos "tanque" e "volume do tanque" com base no serviço selecionado
function atualizarCamposTanque(servicoId, tanqueId, volumeId) {
   
    let servico = document.getElementById(servicoId) || document.querySelector(`[name='servico']`);
    let tanque = document.getElementById(tanqueId) || document.querySelector(`[name='tanque']`);
    let volume = document.getElementById(volumeId) || document.querySelector(`[name='volume_tanque']`);
    if (!servico || !tanque || !volume) return;
    function handler() {
        const selecionado = servico.options ? servico.options[servico.selectedIndex].text : servico.value;
        if (verificaServicoEspecial(selecionado)) {
            tanque.value = "-";
            tanque.readOnly = true;
            tanque.setAttribute('tabindex', '-1');
            tanque.style.backgroundColor = '#e0e0e0';
            tanque.placeholder = 'Bloqueado automaticamente';
            volume.value = 0;
            volume.readOnly = true;
            volume.setAttribute('tabindex', '-1');
            volume.style.backgroundColor = '#e0e0e0';
            volume.placeholder = 'Bloqueado automaticamente';
        } else {
            tanque.readOnly = false;
            tanque.removeAttribute('tabindex');
            tanque.style.backgroundColor = '';
            tanque.placeholder = '';
            volume.readOnly = false;
            volume.removeAttribute('tabindex');
            volume.style.backgroundColor = '';
            volume.placeholder = '';
        }
    }
    servico.addEventListener('change', handler);

    handler();
}

// Gerenciamento de notificações

document.addEventListener('DOMContentLoaded', function() {
    // Botão Limpar Filtros
        // Corrige o botão Limpar Filtros para limpar todos os campos do painel de filtros e filtros ativos
        var btnLimpar = document.getElementById('btn-limpar-filtros');
        if (btnLimpar) {
            btnLimpar.addEventListener('click', function(e) {
                e.preventDefault();
                var filterPanel = document.getElementById('campos-filtro');
                if (filterPanel) {
                    var inputs = filterPanel.querySelectorAll('input, select');
                    inputs.forEach(function(input) {
                        if (input.type === 'checkbox' || input.type === 'radio') {
                            input.checked = false;
                        } else if (input.type === 'date' || input.type === 'text' || input.type === 'number' || input.tagName === 'SELECT') {
                            input.value = '';
                        }
                    });
                }
                // Limpa os chips de filtros ativos (se existirem)
                var filtrosAtivosBar = document.getElementById('filtros-ativos-bar');
                if (filtrosAtivosBar) {
                    // Redireciona para a página sem parâmetros de filtro
                    window.location.href = window.location.pathname;
                }
            });
    }

        // Corrige o botão Limpar Filtros da barra de filtros ativos
        var btnLimparBar = document.querySelector('.btn-limpar-filtros-bar');
        if (btnLimparBar) {
            btnLimparBar.addEventListener('click', function(e) {
                e.preventDefault();
                window.location.href = window.location.pathname;
            });
        }
    
    const btnLimparDatas = document.getElementById('btn-limpar-datas');
    if (btnLimparDatas) {
        btnLimparDatas.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = '?';
        });
    }
    
    // Gerenciamento do toggle de datas
    var btnToggleDatas = document.getElementById('btn-toggle-datas');
    var filtroDataInicial = document.getElementById('filtro-data-inicial');
    var filtroDataFinal = document.getElementById('filtro-data-final');
    if (filtroDataInicial) filtroDataInicial.classList.remove('ativo');
    if (filtroDataFinal) filtroDataFinal.classList.remove('ativo');
    if (btnToggleDatas && filtroDataInicial && filtroDataFinal) {
        btnToggleDatas.addEventListener('click', function() {
            filtroDataInicial.classList.toggle('ativo');
            filtroDataFinal.classList.toggle('ativo');
        });
    }
   
    atualizarCamposTanque('id_servico', 'id_tanque', 'id_volume_tanque');
    
    atualizarCamposTanque('edit_servico', 'edit_tanque', 'edit_volume_tanque');

    // Inicializar widgets de tags para seleção múltipla de serviços
    function initTagInput(inputId, hiddenId, containerId) {
        const input = document.getElementById(inputId);
        const hidden = document.getElementById(hiddenId);
        const container = document.getElementById(containerId);
        if (!input || !hidden || !container) return;
        // normaliza string: remove acentos e espaços extras e converte para lowercase
        function normalizeStr(s) {
            if (s === null || s === undefined) return '';
            try {
                return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();
            } catch (e) {
                return String(s).toLowerCase().trim();
            }
        }

        // verifica se um valor (texto) corresponde exatamente a uma opção do datalist (após normalização)
        function findMatchingOption(val) {
            const listId = input.getAttribute('list');
            if (!listId) return null;
            const dl = document.getElementById(listId);
            if (!dl) return null;
            const target = normalizeStr(val || '');
            for (const opt of Array.from(dl.options || [])) {
                const v = (opt.value || opt.textContent || '').trim();
                if (!v) continue;
                if (normalizeStr(v) === target) return v; // retorna a option canonical text
            }
            return null;
        }

        function addTagRaw(value) {
            value = (value || '').trim();
            if (!value) return;
            // evitar duplicatas (case-insensitive)
            const existingRaw = Array.from(container.querySelectorAll('.tag-item')).some(t => t.textContent.trim().toLowerCase() === value.toLowerCase());
            if (existingRaw) return;
            const tagRaw = document.createElement('span');
            tagRaw.className = 'tag-item';
            tagRaw.textContent = value;
            const btnRaw = document.createElement('button');
            btnRaw.type = 'button';
            btnRaw.className = 'tag-remove';
            btnRaw.textContent = '✕';
            btnRaw.addEventListener('click', function() { tagRaw.remove(); updateHidden(); });
            tagRaw.appendChild(btnRaw);
            container.appendChild(tagRaw);
            updateHidden();
        }

        function addTag(value) {
            value = (value || '').trim();
            if (!value) return;
            // aceitar somente valores que existam no datalist (comparação insensível a acento/caixa)
            const matched = findMatchingOption(value);
            if (!matched) {
                // feedback visual breve
                const prev = input.style.borderColor;
                input.style.borderColor = '#e74c3c';
                input.title = 'Selecione um serviço a partir das opções.';
                setTimeout(() => { input.style.borderColor = prev || ''; input.title = ''; }, 1600);
                return; // não adiciona tags que não sejam opções válidas
            }
            // garantir canonical text (corrige diferenças de caixa/acentos)
            value = matched;
            // evitar duplicatas (case-insensitive)
            const existing = Array.from(container.querySelectorAll('.tag-item')).some(t => t.textContent.trim().toLowerCase() === value.toLowerCase());
            if (existing) return;
            const tag = document.createElement('span');
            tag.className = 'tag-item';
            tag.textContent = value;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'tag-remove';
            btn.textContent = '✕';
            btn.addEventListener('click', function() { tag.remove(); updateHidden(); });
            tag.appendChild(btn);
            container.appendChild(tag);
            updateHidden();
        }

        // expor métodos para adicionar tag programaticamente
        // addTag: valida contra datalist
        container.addTag = function(value) { addTag(value); };
        // addTagRaw: adiciona sem validação (usado ao carregar dados do servidor)
        container.addTagRaw = function(value) { addTagRaw(value); };

        function updateHidden() {
            const vals = Array.from(container.querySelectorAll('.tag-item')).map(t => {
                // remover o botão '✕' do texto
                return t.childNodes && t.childNodes.length ? t.childNodes[0].nodeValue.trim() : t.textContent.trim();
            }).filter(v => v);
            hidden.value = vals.join(', ');
            // se existir um sincronizador de tanques, chamar
            try {
                if (typeof container.onTagsChanged === 'function') container.onTagsChanged(vals);
            } catch (e) {}
        }

        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === '+') {
                e.preventDefault();
                const val = input.value.trim();
                if (val) addTag(val);
                input.value = '';
            }
        });

        // Quando o valor do input muda (ex: seleção via datalist por clique),
        // se bater exatamente com uma opção válida, adicionar como tag automaticamente.
        input.addEventListener('input', function() {
            try {
                // Se a seleção veio do dropdown custom, ignorar este evento para evitar duplicação.
                if (input.getAttribute && input.getAttribute('data-selected-from-dropdown')) {
                    // limpar flag e não processar aqui (a adição já foi feita pelo handler do dropdown)
                    try { input.removeAttribute('data-selected-from-dropdown'); } catch(e){}
                    return;
                }
                const val = input.value.trim();
                if (!val) return;
                const matched = findMatchingOption(val);
                if (matched) {
                    // adiciona e limpa o input
                    addTag(matched);
                    input.value = '';
                }
            } catch (e) {
                // silencioso - não queremos quebrar o fluxo de digitação
            }
        });

        // Ao perder foco, só aceitar se for opção válida do datalist
        input.addEventListener('blur', function() {
            try {
                // Se a seleção foi originada no dropdown custom, evitar re-adicionar (duplica)
                if (input.getAttribute && input.getAttribute('data-selected-from-dropdown')) {
                    try { input.removeAttribute('data-selected-from-dropdown'); } catch(e){}
                    // limpar o input residual, pois a tag já foi adicionada pelo dropdown
                    input.value = '';
                    return;
                }
            } catch(e) {}
            const val = input.value.trim();
            if (!val) return;
            const matched = findMatchingOption(val);
            if (matched) {
                addTag(matched);
            } else {
                // breve feedback: não aceita valor livre
                const prev = input.style.borderColor;
                input.style.borderColor = '#e74c3c';
                input.title = 'Selecione um serviço válido a partir da lista.';
                setTimeout(() => { input.style.borderColor = prev || ''; input.title = ''; }, 1600);
            }
            input.value = '';
        });

        // Clear container helper
        container.clear = function() {
            container.innerHTML = '';
            updateHidden();
        };

        // function to populate tags from comma-separated string
        container.loadFromString = function(str) {
            container.clear();
            if (!str) return;
            const parts = String(str).split(',').map(p => p.trim()).filter(p => p);
            parts.forEach(p => {
                // usar adição raw para garantir que valores vindos do servidor sejam carregados
                addTagRaw(p);
            });
        };
    }

    // inicializa para criação e edição
    initTagInput('servico_input', 'servico_hidden', 'servico_tags_container');
    initTagInput('edit_servico_input', 'edit_servico_hidden', 'edit_servico_tags_container');

    // --- Sincronização Tanques <-> Serviços ---
    function buildTankRow(service, index) {
        const row = document.createElement('div');
        row.className = 'tank-row';
        row.style.display = 'flex';
        row.style.gap = '8px';
        row.style.marginTop = '6px';
        // label
        const lbl = document.createElement('div');
        lbl.textContent = (index + 1) + '. ' + service;
        lbl.style.flex = '1 0 35%';
        lbl.style.alignSelf = 'center';
        // tanque input
        const inpTanque = document.createElement('input');
        inpTanque.type = 'text';
        inpTanque.name = `tanque_${index}`;
        inpTanque.className = 'form-control tanque-input';
        inpTanque.style.flex = '1 0 30%';
        // sincroniza hidden ao digitar
        inpTanque.addEventListener('input', function() {
            try { updateTankHiddenFields(); } catch (e) {}
        });
        // Se o serviço for especial (não precisa de tanque), bloquear o campo
        try {
            if (verificaServicoEspecial(service)) {
                inpTanque.value = '';
                inpTanque.placeholder = 'Não aplicável';
                inpTanque.readOnly = true;
                inpTanque.style.backgroundColor = '#f3f4f6';
                inpTanque.setAttribute('data-na', '1');
            } else {
                inpTanque.placeholder = 'Tanque para este serviço';
            }
        } catch (e) {
            inpTanque.placeholder = 'Tanque para este serviço';
        }
        // remove button
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn small tag-remove';
        btn.textContent = 'Remover';
        btn.style.flex = '1 0 10%';
        btn.addEventListener('click', function() {
            // ao remover, também remover a tag correspondente via busca pelo texto
            try {
                const container = document.getElementById('servico_tags_container');
                if (container) {
                    const tags = Array.from(container.querySelectorAll('.tag-item'));
                    for (const t of tags) {
                        const text = t.childNodes && t.childNodes.length ? t.childNodes[0].nodeValue.trim() : t.textContent.trim();
                        if (text === service) { t.remove(); break; }
                    }
                    // forçar atualização dos hidden via evento existente
                    if (typeof container.onTagsChanged === 'function') container.onTagsChanged(Array.from(container.querySelectorAll('.tag-item')).map(tn => tn.childNodes[0].nodeValue.trim()));
                }
            } catch (e) {}
            row.remove();
            updateTankHiddenFields();
        });

        row.appendChild(lbl);
        row.appendChild(inpTanque);
        row.appendChild(btn);
        return row;
    }

    function updateTankHiddenFields() {
        // atualizar criação
        try {
            const container = document.getElementById('tanques_container');
            const tanquesHidden = document.getElementById('tanques_hidden');
            if (container && tanquesHidden) {
                const inputs = Array.from(container.querySelectorAll('.tanque-input'));
                const tanques = inputs.map(i => {
                    // se marcado como Não Aplicável, manter string vazia para preservar posição
                    if (i.getAttribute && i.getAttribute('data-na')) return '';
                    return (i.value || '').trim();
                });
                let joined = tanques.join(', ').trim();
                // Fallback: se não houver linhas de tanques ou se todos vazios, usar campo legado 'tanque'
                const allEmpty = !tanques.length || tanques.every(v => !v);
                if (allEmpty) {
                    const singleTankEl = document.getElementById('id_tanque') || document.querySelector('input[name="tanque"], textarea[name="tanque"]');
                    if (singleTankEl && singleTankEl.value && singleTankEl.value.trim()) {
                        joined = singleTankEl.value.trim();
                    }
                }
                tanquesHidden.value = joined;
            }
        } catch(e) {}
        // atualizar editar
        try {
            const containerE = document.getElementById('edit_tanques_container');
            const tanquesHiddenE = document.getElementById('edit_tanques_hidden');
            if (containerE && tanquesHiddenE) {
                const tanquesE = Array.from(containerE.querySelectorAll('.tanque-input')).map(i => {
                    if (i.getAttribute && i.getAttribute('data-na')) return '';
                    return (i.value || '').trim();
                });
                tanquesHiddenE.value = tanquesE.join(', ');
            }
        } catch(e) {}
        // também atualizar compatibilidade: primeiro tanque para campo tanque e soma volumes para volume_tanque
        try {
            // Não manter compatibilidade com volume/tanque antigo — removed
        } catch (e) {}
    }

    // ligar sincronização quando as tags mudarem
    (function attachSync() {
        function bindContainer(servId, tanquesId, tanquesHiddenId, volumesHiddenId) {
            const servContainer = document.getElementById(servId);
            if (!servContainer) return;
            servContainer.onTagsChanged = function(tags) {
                const tanquesContainer = document.getElementById(tanquesId);
                if (!tanquesContainer) return;
                // reconstruir campos
                tanquesContainer.innerHTML = '';
                tags.forEach((s, idx) => {
                    const row = buildTankRow(s, idx);
                    tanquesContainer.appendChild(row);
                });
                // tentar pré-preencher valores de tanques a partir do hidden correspondente
                try {
                    const hiddenEl = tanquesHiddenId ? document.getElementById(tanquesHiddenId) : null;
                    if (hiddenEl && hiddenEl.value) {
                        const vals = String(hiddenEl.value).split(',').map(v => v.trim());
                        const inputs = Array.from(tanquesContainer.querySelectorAll('.tanque-input'));
                        inputs.forEach((inp, i) => {
                            if (inp && !inp.getAttribute('data-na')) {
                                const v = vals[i] || '';
                                // somente atribuir se ainda vazio para não sobrescrever edição do usuário
                                if (!inp.value && v) inp.value = v;
                            }
                        });
                    }
                } catch (e) { /* noop */ }
                // atualizar hidden específicos (updateTankHiddenFields updates global ones)
                updateTankHiddenFields();
            };
            servContainer.loadIntoTanques = function() {
                const vals = Array.from(servContainer.querySelectorAll('.tag-item')).map(t => t.childNodes[0].nodeValue.trim());
                servContainer.onTagsChanged(vals);
            };
        }
        bindContainer('servico_tags_container', 'tanques_container', 'tanques_hidden');
        bindContainer('edit_servico_tags_container', 'edit_tanques_container', 'edit_tanques_hidden');
    })();

    // Dropdown customizado para listar todos os serviços do datalist (mostra lista completa ao focar)
    function initServiceDropdown(inputId) {
        const input = document.getElementById(inputId);
        if (!input) return;
        const listId = input.getAttribute('list') || 'servicos_datalist';
        const datalist = document.getElementById(listId);
        if (!datalist) return;

    let dropdown = null;
    // guardar o id original do list para restaurar ao fechar
    const originalList = input.getAttribute('list');

        function buildDropdownItems(filter) {
            function normalizeLocal(s) {
                try { return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim(); } catch(e) { return String(s).toLowerCase().trim(); }
            }
            const opts = Array.from(datalist.options || []).map(o => (o.value || o.textContent || '').trim()).filter(v => v);
            const f = normalizeLocal(filter || '');
            return opts.filter(v => !f || normalizeLocal(v).indexOf(f) !== -1);
        }

        function showDropdown() {
            hideDropdown();
            const items = buildDropdownItems(input.value || '');
            if (!items.length) return;
            dropdown = document.createElement('div');
            dropdown.className = 'servicos-dropdown';
            dropdown.style.position = 'absolute';
            dropdown.style.zIndex = 9999;
            dropdown.style.minWidth = (input.offsetWidth) + 'px';
            dropdown.style.maxHeight = '220px';
            dropdown.style.overflow = 'auto';
            dropdown.style.background = '#fff';
            dropdown.style.border = '1px solid #ccc';
            dropdown.style.boxShadow = '0 4px 10px rgba(0,0,0,0.08)';
            dropdown.style.borderRadius = '4px';
            dropdown.style.padding = '6px 0';

            items.forEach(text => {
                const item = document.createElement('div');
                item.className = 'servicos-dropdown-item';
                item.textContent = text;
                item.style.padding = '6px 12px';
                item.style.cursor = 'pointer';
                item.style.whiteSpace = 'nowrap';
                item.style.overflow = 'hidden';
                item.style.textOverflow = 'ellipsis';
                item.addEventListener('mouseenter', () => item.style.background = '#f3f4f6');
                item.addEventListener('mouseleave', () => item.style.background = '');
                // Garantir que o valor seja definido ANTES do blur do input (pointerdown ocorre antes do blur)
                item.addEventListener('pointerdown', function(e) {
                    try {
                        e.preventDefault();
                        // Define valor no input sem disparar eventos (evita duplicação no fluxo de click)
                        input.value = text;
                        input.setAttribute('data-selected-from-dropdown', '1');
                    } catch (err) {
                        // silencioso
                    }
                });

                item.addEventListener('click', function(e) {
                    e.preventDefault();
                    console.debug('servicos-dropdown: item clicked ->', text, 'inputId=', inputId);
                    try {
                        const containerId = inputId.replace('_input', '_tags_container');
                        const cont = document.getElementById(containerId);
                        if (cont) {
                            if (typeof cont.addTagRaw === 'function') {
                                cont.addTagRaw(text);
                            } else if (typeof cont.addTag === 'function') {
                                cont.addTag(text);
                            }
                        } else {
                            // preencher input, disparar eventos para que outros listeners reajam
                            input.value = text;
                            input.setAttribute('data-selected-from-dropdown', '1');
                            try { input.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
                            try { input.dispatchEvent(new Event('change', { bubbles: true })); } catch(e){}
                            // forçar foco seguido de blur para acionar validações que usam blur
                            try { input.focus(); setTimeout(() => { try { input.blur(); } catch(_){} }, 60); } catch(e){}
                        }
                    } catch (ex) {
                        console.debug('servicos-dropdown: exception while handling click', ex);
                        input.value = text;
                        input.setAttribute('data-selected-from-dropdown', '1');
                        try { input.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
                        try { input.dispatchEvent(new Event('change', { bubbles: true })); } catch(e){}
                        try { input.focus(); setTimeout(() => { try { input.blur(); } catch(_){} }, 60); } catch(e){}
                    }
                    hideDropdown();
                });
                dropdown.appendChild(item);
            });

            document.body.appendChild(dropdown);
            positionDropdown();

            // Não remover o atributo 'list' — manter o datalist nativo disponível.

            // close on outside click
            setTimeout(() => {
                document.addEventListener('click', onDocClick);
            }, 10);
        }

        function positionDropdown() {
            if (!dropdown) return;
            const rect = input.getBoundingClientRect();
            const top = rect.bottom + window.scrollY + 4;
            const left = rect.left + window.scrollX;
            dropdown.style.left = left + 'px';
            dropdown.style.top = top + 'px';
            // ensure dropdown width at least input width
            dropdown.style.minWidth = (rect.width) + 'px';
        }

        function hideDropdown() {
            if (dropdown && dropdown.parentNode) {
                dropdown.parentNode.removeChild(dropdown);
            }
            dropdown = null;
            document.removeEventListener('click', onDocClick);
            // não é necessário restaurar o atributo 'list'
        }

        function onDocClick(e) {
            if (!dropdown) return;
            if (e.target === input || input.contains(e.target) || dropdown.contains(e.target)) return;
            hideDropdown();
        }

        input.addEventListener('focus', function() {
            showDropdown();
        });

        input.addEventListener('input', function() {
            // rebuild dropdown with filter
            if (dropdown) {
                hideDropdown();
            }
            showDropdown();
        });

        window.addEventListener('resize', positionDropdown);
        window.addEventListener('scroll', positionDropdown, true);
        // hide when input is blurred (delay to allow click)
        input.addEventListener('blur', function() {
            setTimeout(hideDropdown, 150);
        });
    }

    // inicializar dropdowns para criar e editar
    initServiceDropdown('servico_input');
    initServiceDropdown('edit_servico_input');
    // Inicializar dropdown customizado também para Cliente/Unidade.
    // O dropdown custom agora preserva o atributo `list` e dispara eventos
    // `input`/`change` ao selecionar, então clicar em uma opção preenche o campo.
    initServiceDropdown('id_cliente');
    initServiceDropdown('id_unidade');
    // também inicializar campos de edição caso existam
    initServiceDropdown('edit_cliente');
    initServiceDropdown('edit_unidade');

});
function showLoading() {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.classList.remove('fade-out');
    }
}



function hideLoading() {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.classList.add('fade-out');
    }
}

// Overlay simples de feedback antes do reload
function showReloadOverlay(message) {
    try {
        // remover se já existir
        const prev = document.getElementById('reloadOverlay');
        if (prev) {
            try { if (prev._interval) clearInterval(prev._interval); } catch(e){}
            prev.remove();
        }
        const ov = document.createElement('div');
        ov.id = 'reloadOverlay';
        Object.assign(ov.style, {
            position: 'fixed', top: '0', left: '0', width: '100%', height: '100%',
            background: 'rgba(0,0,0,0.55)', color: '#fff', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 12000, flexDirection: 'column',
            fontFamily: 'Arial, sans-serif'
        });

        const card = document.createElement('div');
        Object.assign(card.style, { padding: '18px 24px', borderRadius: '8px', background: 'rgba(0,0,0,0.35)', textAlign: 'center' });

        const msg = document.createElement('div');
        msg.textContent = message || 'Recarregando página...';
        Object.assign(msg.style, { fontSize: '18px', marginBottom: '10px' });

        const dot = document.createElement('div');
        dot.textContent = '';
        Object.assign(dot.style, { fontSize: '22px', letterSpacing: '4px' });

        card.appendChild(msg);
        card.appendChild(dot);
        ov.appendChild(card);
        document.body.appendChild(ov);

        let d = 0;
        const interval = setInterval(() => { d = (d + 1) % 4; dot.textContent = '.'.repeat(d); }, 420);
        // armazenar referência para limpar depois
        ov._interval = interval;
    } catch (e) {
        // silencioso
    }
}

function hideReloadOverlay() {
    try {
        const ov = document.getElementById('reloadOverlay');
        if (ov) {
            if (ov._interval) clearInterval(ov._interval);
            ov.remove();
        }
    } catch (e) {}
}

// Atualiza dinamicamente a tabela (tbody), paginação e barra de filtros ativos sem recarregar a página inteira
async function refreshTableAndBindings() {
    try {
        const url = window.location.href;
        const resp = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const html = await resp.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        // Atualiza tabela
        const newTableWrap = doc.querySelector('.tabela_conteiner');
        const curTableWrap = document.querySelector('.tabela_conteiner');
        if (newTableWrap && curTableWrap) {
            curTableWrap.innerHTML = newTableWrap.innerHTML;
        }
        // Atualiza paginação
        const newPagina = doc.querySelector('.pagina');
        const curPagina = document.querySelector('.pagina');
        if (newPagina && curPagina) {
            curPagina.innerHTML = newPagina.innerHTML;
        }
        // Atualiza barra de filtros ativos
        const newFiltros = doc.querySelector('#filtros-ativos-bar');
        const curFiltros = document.querySelector('#filtros-ativos-bar');
        if (newFiltros && curFiltros) {
            curFiltros.innerHTML = newFiltros.innerHTML;
        }
        // Reanexa eventos necessários na tabela (detalhes)
        try {
            document.querySelectorAll('.btn_tabela[id^="btn_detalhes_"]').forEach(botao => {
                botao.onclick = function () {
                    const osId = this.getAttribute('data-id');
                    abrirDetalhesModal(osId);
                };
            });
        } catch (e) { /* noop */ }
        // Normaliza células de tanques em novas linhas
        try {
            const tds = document.querySelectorAll('td.td-tanques');
            tds.forEach(td => {
                try {
                    const full = td.getAttribute('data-tanques') || '';
                    const parts = String(full || '').split(',').map(s => s.trim()).filter(Boolean);
                    const primary = parts.length ? parts[0] : '';
                    const primaryEl = td.querySelector('.tanque-primary');
                    if (primaryEl) {
                        primaryEl.textContent = primary;
                    } else {
                        const span = document.createElement('span');
                        span.className = 'tanque-primary';
                        span.textContent = primary;
                        td.innerHTML = '';
                        td.appendChild(span);
                    }
                    const moreEl = td.querySelector('.tanques-more');
                    if (parts.length > 1) {
                        if (!moreEl) {
                            const m = document.createElement('span');
                            m.className = 'tanques-more';
                            m.setAttribute('aria-label', 'Mostrar todos os tanques');
                            m.textContent = ' (…)';
                            td.appendChild(m);
                        }
                    } else {
                        if (moreEl) moreEl.remove();
                    }
                } catch (e) {}
            });
        } catch (e) { /* noop */ }
    } catch (e) {
        // Se falhar, mostra aviso mas não quebra a página
        try { NotificationManager.show('Não foi possível atualizar a tabela.', 'warning'); } catch(_){}
    }
}

// Animação do barco

document.addEventListener('DOMContentLoaded', function() {
    const barco = document.querySelector('.barco');
    const fumaca = document.querySelector('.fumaca');
    if (barco && fumaca) {
        const barcoContainer = barco.parentElement;
        const barcoWidth = barco.offsetWidth;
        const caminho = barcoContainer.offsetWidth - barcoWidth;
        let start = null;
        function animarBarco(ts) {
            // Função de animação principal (não-blocking).
            // Qualquer lógica assíncrona necessária para atualizar dados usa Promises internas
            // para evitar uso de `await` direto aqui (função não-async), mantendo compatibilidade com requestAnimationFrame.
            (async () => {
                try {
                    // Tentar obter detalhes de OS apenas se 'osId' estiver definido
                    if (typeof osId !== 'undefined' && osId) {
                        try {
                            const os = await fetchJson(`/os/${osId}/detalhes/`);
                            // se o fetchJson retornar objeto com sucesso
                            if (os && os.numero_os !== undefined) {
                                // popula campos básicos existentes
                                try { document.getElementById('num_os').textContent = os.numero_os || ''; } catch(e){}
                                try { document.getElementById('cod_os').textContent = os.codigo_os || ''; } catch(e){}
                                try { document.getElementById('id_os').textContent = os.id || ''; } catch(e){}
                                try { document.getElementById('status_os').textContent = os.status_operacao || ''; } catch(e){}
                                try { document.getElementById('status_geral').textContent = os.status_geral || ''; } catch(e){}
                                try { document.getElementById('status_comercial').textContent = os.status_comercial || ''; } catch(e){}

                                try { document.getElementById('data_inicio').textContent = os.data_inicio || ''; } catch(e){}
                                try { document.getElementById('data_fim').textContent = os.data_fim || ''; } catch(e){}
                                try { document.getElementById('dias_op').textContent = os.dias_de_operacao || ''; } catch(e){}

                                // campos de frente
                                try { if (document.getElementById('data_inicio_frente')) document.getElementById('data_inicio_frente').textContent = os.data_inicio_frente || ''; } catch(e){}
                                try { if (document.getElementById('data_fim_frente')) document.getElementById('data_fim_frente').textContent = os.data_fim_frente || ''; } catch(e){}
                                try { if (document.getElementById('dias_op_frente')) document.getElementById('dias_op_frente').textContent = os.dias_de_operacao_frente || ''; } catch(e){}

                                try { document.getElementById('cliente').textContent = os.cliente || ''; } catch(e){}
                                try { document.getElementById('unidade').textContent = os.unidade || ''; } catch(e){}
                                try { document.getElementById('solicitante').textContent = os.solicitante || ''; } catch(e){}

                                // população de serviços: converter CSV em <ul><li>...</li></ul>
                                try {
                                    if (document.getElementById('servicos_full')) {
                                        var servicosCsv = os.servicos || os.servico || '';
                                        var container = document.getElementById('servicos_full');
                                        // limpa conteúdo anterior
                                        container.innerHTML = '';
                                        if (!servicosCsv) {
                                            container.textContent = '';
                                        } else {
                                            // dividir por vírgula, remover espaços vazios e entradas duplicadas
                                            var items = servicosCsv.split(',').map(function(s){ return s.trim(); }).filter(function(s){ return s.length > 0; });
                                            // se não houver vírgula mas houver separador diferente (ponto e vírgula) tente também
                                            if (items.length <= 1 && servicosCsv.indexOf(';') !== -1) {
                                                items = servicosCsv.split(';').map(function(s){ return s.trim(); }).filter(function(s){ return s.length > 0; });
                                            }
                                            // remover duplicatas mantendo ordem
                                            var seen = {};
                                            var unique = [];
                                            items.forEach(function(it){ if (!seen[it]) { seen[it]=true; unique.push(it); } });

                                            if (unique.length === 1) {
                                                // se só houver um item, mostrar como texto normal para manter aparência
                                                container.textContent = unique[0];
                                            } else {
                                                var ul = document.createElement('ul');
                                                ul.className = 'detalhes-servicos-list';
                                                unique.forEach(function(it){
                                                    var li = document.createElement('li');
                                                    li.textContent = it;
                                                    ul.appendChild(li);
                                                });
                                                container.appendChild(ul);
                                            }
                                        }
                                    } else if (document.getElementById('servico')) {
                                        document.getElementById('servico').textContent = os.servico || '';
                                    }
                                } catch(e) { /* silencioso */ }

                                try { document.getElementById('regime').textContent = os.tipo_operacao || ''; } catch(e){}
                                try { document.getElementById('metodo').textContent = os.metodo || ''; } catch(e){}
                                try { document.getElementById('metodo_secundario').textContent = os.metodo_secundario || ''; } catch(e){}
                                try { document.getElementById('po').textContent = os.po || ''; } catch(e){}
                                try { document.getElementById('material').textContent = os.material || ''; } catch(e){}
                                try { document.getElementById('tanque').textContent = os.tanque || ''; } catch(e){}
                                try { document.getElementById('volume_tq').textContent = os.volume_tanque || ''; } catch(e){}
                                try { document.getElementById('especificacao').textContent = os.especificacao || ''; } catch(e){}
                                try { document.getElementById('pob').textContent = os.pob || ''; } catch(e){}
                                try { document.getElementById('coordenador').textContent = os.coordenador || ''; } catch(e){}
                                try { document.getElementById('supervisor').textContent = os.supervisor || ''; } catch(e){}
                                try { document.getElementById('observacao').textContent = os.observacao || ''; } catch(e){}
                                // abre modal
                                try { document.getElementById('detalhes_os').style.display = 'block'; } catch(e){}
                            }
                        } catch(errFetch) {
                            console.error('Erro ao buscar detalhes da OS', errFetch);
                        }
                    }

                    // pequenas esperas controladas para animação/fluxo
                    await new Promise(resolve => setTimeout(resolve, 1500));
                    if (typeof fetchTableData === 'function') {
                        try { await fetchTableData(); } catch(e) { /* silencioso */ }
                    }
                    await new Promise(resolve => setTimeout(resolve, 2500));
                    hideLoading();
                } catch (error) {
                    if (error && error.message !== "fetchTableData is not defined") {
                        NotificationManager.show("Erro ao carregar dados do sistema", "error");
                    }
                    hideLoading();
                }
            })();
        } // fim function animarBarco

            // iniciar animação do barco
            try {
                requestAnimationFrame(animarBarco);
            } catch (e) {
                // se algo falhar ao iniciar a animação, não quebra o restante do script
                console.warn('Falha ao iniciar animarBarco:', e);
            }
        } // fim if (barco && fumaca)
    }); // fim DOMContentLoaded

document.addEventListener('DOMContentLoaded', function() {
    // Gerenciamento da tela de loading: só mostra após login
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        if (!sessionStorage.getItem('welcome_shown')) {
            setTimeout(() => {
                hideLoading();
                setTimeout(() => {
                    if (loadingScreen && loadingScreen.parentNode) {
                        loadingScreen.parentNode.removeChild(loadingScreen);
                    }
                }, 800); // tempo do fade-out em ms
            }, 2500);
            sessionStorage.setItem('welcome_shown', '1');
        } else {
            loadingScreen.parentNode.removeChild(loadingScreen);
        }
    }

    // Animação do barco
    const barco = document.querySelector('.barco');
    const fumaca = document.querySelector('.fumaca');
    if (barco && fumaca) {
        const barcoContainer = barco.parentElement;
        const barcoWidth = barco.offsetWidth;
        const caminho = barcoContainer.offsetWidth - barcoWidth;
        let start = null;
        function animarBarco(ts) {
            if (!start) start = ts;
            const dur = 6000;
            let elapsed = (ts - start) % dur;
            let pct = elapsed / dur;
            let left = caminho * pct;
            let amplitude = 4;
            let yBase = 10;
            let freq = 2;
            let y = Math.sin(pct * Math.PI * 2 * freq) * amplitude + yBase;
            barco.style.left = left + 'px';
            barco.style.bottom = y + 'px';
            fumaca.style.left = (left + 18) + 'px';
            fumaca.style.top = (y) + 'px';
            requestAnimationFrame(animarBarco);
        }
        requestAnimationFrame(animarBarco);
        barco.style.filter = 'brightness(0) saturate(100%)';
    }
});

// Gerenciamento do modal de nova OS
const btnNovaOS = document.querySelector("#btn_nova_os");
const modal = document.getElementById("modal-os");

function abrirModal() {
    if (!modal) {
        NotificationManager.show("Erro ao abrir o modal", "error");
        return;
    } 
    modal.style.display = "flex";
    // Incrementar contador de OS pendentes para RDO
    try {
        const count = parseInt(localStorage.getItem('rdo_pending_count') || '0');
        localStorage.setItem('rdo_pending_count', (count + 1).toString());
    } catch(e) {}
    NotificationManager.show("Criando nova Ordem de Serviço", "info");
    
    setTimeout(() => {
        const radioButtons = document.querySelectorAll('#box-opcao-container input[type="radio"]');
        const osExistenteField = document.getElementById('os-existente-Field');

        if (osExistenteField) {
            osExistenteField.style.display = 'none';
        }

        radioButtons.forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.value === 'existente') {
                    osExistenteField.style.display = 'block';
                } else {
                    osExistenteField.style.display = 'none';
                }
            });
           
            if (radio.checked && radio.value === 'existente') {
                osExistenteField.style.display = 'block';
            }
        });
    }, 100);
}

function fecharModal() {
    modal.style.display = "none";
}

// Função para exibir erros de formulário
function handleFormErrors(errors) {
    clearFormErrors();
    for (const [field, messages] of Object.entries(errors)) {
        const fieldElement = document.querySelector(`[name="${field}"]`);
        if (fieldElement) {
            fieldElement.classList.add('error-field');
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.style.color = 'red';
            errorDiv.style.fontSize = '12px';
            errorDiv.style.marginTop = '5px';
            errorDiv.textContent = messages.join(', ');
            fieldElement.parentNode.appendChild(errorDiv);
        } else {
            NotificationManager.show(`${field}: ${messages.join(', ')}`, 'error');
        }
    }
}

// Função para limpar erros de formulário
async function submitFormAjax(form) {
    try {
        NotificationManager.showLoading();
        const formData = new FormData(form);
        
        try {
            const data = await fetchJson(form.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                },
                timeout: 15000
            });

            if (data && data.success) {
                NotificationManager.show(data.message || 'Operação realizada com sucesso!', 'success');
                if (data.redirect) {
                    setTimeout(() => window.location.href = data.redirect, 1500);
                }
                return true;
            } else {
                if (data && data.errors) {
                    handleFormErrors(data.errors);
                } else {
                    NotificationManager.show((data && data.error) || 'Erro ao processar sua solicitação', 'error');
                }
                return false;
            }
        } catch (err) {
            NotificationManager.show('Erro ao conectar com o servidor', 'error');
            return false;
        }
    } catch (error) {
        NotificationManager.show('Erro ao conectar com o servidor', 'error');
        return false;
    } finally {
        NotificationManager.hideLoading();
    }
}


// Eventos para abrir e fechar o modal (guardados caso elementos não existam no DOM)
if (typeof btnNovaOS !== 'undefined' && btnNovaOS) {
    btnNovaOS.addEventListener("click", () => {
        abrirModal();
    });
}

var modalOsCloseBtn = document.querySelector("#modal-os .close-btn");
if (modalOsCloseBtn) {
    modalOsCloseBtn.addEventListener("click", fecharModal);
}

window.addEventListener("click", (e) => {
    
    if (e.target === modal) {
        fecharModal();
    }
    const detalhesModal = document.getElementById('detalhes_os');
    if (detalhesModal && detalhesModal.style.display === 'flex' && e.target === detalhesModal) {
        fecharDetalhesModal();
    }
    const modalEdicao = document.getElementById('modal-edicao');
    if (modalEdicao && modalEdicao.style.display === 'flex' && e.target === modalEdicao) {
        fecharModalEdicao();
    }

    
    const filterPanel = document.getElementById('campos-filtro');
    const filterToggle = document.getElementById('filter-toggle');
    const isPanelVisible = filterPanel && (getComputedStyle(filterPanel).display !== 'none' && getComputedStyle(filterPanel).visibility !== 'hidden');
    if (filterPanel && isPanelVisible && !filterPanel.contains(e.target) && e.target !== filterToggle) {
        if (typeof toggleFiltros === 'function') {
            toggleFiltros();
        }
    }
    const datasRangeBar = document.querySelector('.datas-range-bar');
    const btnDatasToggle = document.getElementById('btn-datas-toggle');
    const isDatasVisible = datasRangeBar && (datasRangeBar.classList.contains('active') || (getComputedStyle(datasRangeBar).display !== 'none' && getComputedStyle(datasRangeBar).visibility !== 'hidden'));

    const isBtnDatasClick = btnDatasToggle && (e.target === btnDatasToggle || btnDatasToggle.contains(e.target));
    if (datasRangeBar && isDatasVisible && !datasRangeBar.contains(e.target) && !isBtnDatasClick) {
        if (btnDatasToggle) btnDatasToggle.click();
    }
});

// Submissão do formulário via AJAX
(function(){
    const formOsEl = document.getElementById("form-os");
    if (!formOsEl) return; // evita erro em páginas sem o formulário
    formOsEl.addEventListener("submit", async function(e) {
    e.preventDefault();
    
    
    const submitBtn = this.querySelector('.btn-confirmar');
    if (submitBtn && submitBtn.disabled) {
        return;
    }

    try {
        // garantir que os campos de tanques e serviços ocultos estejam atualizados
        try {
            const servContainer = document.getElementById('servico_tags_container');
            const servHidden = document.getElementById('servico_hidden');
            if (servContainer && servHidden) {
                const vals = Array.from(servContainer.querySelectorAll('.tag-item')).map(t => t.childNodes && t.childNodes.length ? t.childNodes[0].nodeValue.trim() : t.textContent.trim()).filter(v => v);
                servHidden.value = vals.join(', ');
            }
        } catch (e) {}
        try { updateTankHiddenFields(); } catch(e) {}

        const formData = new FormData(this);
        NotificationManager.showLoading();

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Enviando...';
        }

        try {
            const resp = await fetch(this.action, {
                method: "POST",
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            });
            const ct = resp.headers.get('content-type') || '';
            let payload = null;
            if (ct.includes('application/json')) {
                payload = await resp.json();
            } else {
                try { payload = JSON.parse(await resp.text()); } catch (_) { payload = null; }
            }
            if (resp.ok) {
                if (payload && payload.success) {
                    NotificationManager.show(payload.message || "OS criada com sucesso!", "success");
                    fecharModal();
                    // Se o backend retornou os dados da OS criada, injetar na tabela (melhoria UX),
                    // mas garantir que a página seja recarregada para manter consistência de estado.
                    try {
                        if (payload.os) {
                            const os = payload.os;
                            console.debug('OS criada (payload) — dispatching event only, skipping DOM insertion:', payload);
                            try {
                                const ev = new CustomEvent('os:created', { detail: os });
                                window.dispatchEvent(ev);
                            } catch(e) { console.debug('dispatch os:created falhou', e); }
                        }
                    } catch(e) {
                        console.warn('Erro ao processar payload.os:', e);
                    }
                    // Atualização dinâmica da tabela sem recarregar a página inteira
                    try { await refreshTableAndBindings(); } catch(e) {}
                // Caso o servidor responda com HTML/redirect (sem JSON), recarregar a página para refletir a nova OS
                } else if (!payload && (ct.includes('text/html') || resp.redirected)) {
                    // Se veio HTML/redirect, ainda assim tentar rehidratar a tabela dinamicamente
                    try { await refreshTableAndBindings(); } catch(e) {}
                } else if (payload && payload.errors) {
                    handleFormErrors(payload.errors);
                } else {
                    NotificationManager.show((payload && payload.error) || "Erro ao processar sua solicitação", "error");
                }
            } else if (resp.status === 400 && payload && payload.errors) {
                handleFormErrors(payload.errors);
            } else {
                NotificationManager.show((payload && (payload.error || payload.message)) || `Erro ${resp.status}`, 'error');
            }
        } catch (err) {
            NotificationManager.show('Erro ao conectar com o servidor: ' + (err.message || JSON.stringify(err)), 'error');
        }
    } catch (error) {

        NotificationManager.show("Erro ao conectar com o servidor", "error");
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Confirmar';
        }
        NotificationManager.hideLoading();
    }
});
})();


function clearFormErrors() {
    const errorMessages = document.querySelectorAll('.error-message');
    errorMessages.forEach(msg => msg.remove());
    const errorFields = document.querySelectorAll('.error-field');
    errorFields.forEach(field => field.classList.remove('error-field'));
}

const inputPesquisa = document.querySelector(".pesquisar_os");
if (inputPesquisa) {
    inputPesquisa.addEventListener("keyup", (event) => {
        if (event.key === 'Enter') {
            const valor = inputPesquisa.value.trim();
            if (valor) {
                window.location.href = `?search=${encodeURIComponent(valor)}`;
            } else {
                window.location.href = '?page=1';
            }
        }
    });
} else {
    console.debug('inputPesquisa not found; skipping keyup listener');
}
// Submeter filtro por OS ao pressionar Enter no campo 'numero_os'
(function(){
    try {
        var inputNumeroOS = document.querySelector('input[name="numero_os"]');
        if (!inputNumeroOS) return;
        inputNumeroOS.addEventListener('keydown', function(event){
            if (event.key === 'Enter') {
                event.preventDefault();
                var val = (inputNumeroOS.value || '').trim();
                var form = document.getElementById('pesquisa');
                try {
                    if (form) {
                        // Construir querystring a partir dos campos do formulário (mais robusto que form.submit())
                        var params = new URLSearchParams(window.location.search || '');
                        // remover chaves do form para re-aplicar
                        var els = form.querySelectorAll('input[name], select[name], textarea[name]');
                        Array.prototype.forEach.call(els, function(el){ if (el.name) params.delete(el.name); });
                        Array.prototype.forEach.call(els, function(el){
                            if (!el.name) return;
                            var type = (el.type||'').toLowerCase();
                            if ((type === 'checkbox' || type === 'radio') && !el.checked) return;
                            var v = el.value || '';
                            if (v !== '' && v != null) params.append(el.name, v);
                        });
                        params.set('page','1');
                        var q = params.toString();
                        window.location.search = q ? ('?' + q) : window.location.pathname;
                    } else {
                        if (val) {
                            window.location.href = window.location.pathname + '?numero_os=' + encodeURIComponent(val);
                        } else {
                            window.location.href = window.location.pathname;
                        }
                    }
                } catch (e) {
                    try { form.submit(); } catch(_) { if (val) window.location.href = window.location.pathname + '?numero_os=' + encodeURIComponent(val); }
                }
            }
        });
    } catch (e) { console.debug('numero_os key handler init failed', e); }
})();
    
const detalhesModal = document.getElementById("detalhes_os");

// Atualiza tabela dinamicamente quando uma OS é criada (evento disparado no submit com sucesso)
window.addEventListener('os:created', async function(ev) {
    try {
        await refreshTableAndBindings();
        // feedback sutil
        try { NotificationManager.show('Tabela atualizada.', 'success'); } catch(_){}
    } catch(e) { /* noop */ }
});

// Função para abrir o modal de detalhes da OS
function abrirDetalhesModal(osId) {

    var detalhesModal = document.getElementById("detalhes_os");
    // helpers seguros para preencher texto/HTML sem quebrar quando o elemento não existe
    const safeSetText = function(id, value) {
        var el = document.getElementById(id);
        if (!el) return;
        try {
            el.innerText = (value ?? '').toString();
        } catch(e) {
            try { el.textContent = (value ?? '').toString(); } catch(_) {}
        }
    };
    const safeSetHTML = function(id, html) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = html ?? '';
    };
    // buscar via fetchJson (tratamento de timeout/erros padronizado)
    fetchJson(`/os/${osId}/detalhes/`)
        .then(data => {
            if (!data || !data.success || !data.os) {
                NotificationManager.show(data && data.error ? data.error : 'Erro ao carregar detalhes da OS', 'error');
                detalhesModal.style.display = "flex";
                exibirNotificacaoExportarPDF();
                return;
            }
            const os = data.os || {};
            // Preencher os campos do modal com os dados recebidos
            safeSetText("id_os", os.id);
            safeSetText("num_os", os.numero_os);
            // 'tag' field removed from models; clear UI field if present
            var tagEl = document.getElementById("tag");
            if (tagEl) tagEl.innerText = "";
            safeSetText("data_inicio", os.data_inicio);
            safeSetText("data_fim", os.data_fim);
            safeSetText("dias_op", os.dias_de_operacao);
            safeSetText("cliente", os.cliente);
            safeSetText("unidade", os.unidade);
            safeSetText("solicitante", os.solicitante);
            safeSetText("regime", os.tipo_operacao);
            // Turno (Diurno / Noturno)
            safeSetText("turno", os.turno || '');
            // preencher lista completa de serviços (usar único campo 'servicos_full')
            (function preencherServicos() {
                var container = document.getElementById('servicos_full');
                var valor = os.servicos || os.servico || '';
                if (container) {
                    // Limpa conteúdo anterior
                    container.innerHTML = '';
                    if (!valor) {
                        container.textContent = '';
                    } else {
                        // Tenta dividir por vírgula; se só vier um item, tenta por ponto e vírgula
                        var items = valor.split(',').map(function(s){ return s.trim(); }).filter(function(s){ return s.length > 0; });
                        if (items.length <= 1 && valor.indexOf(';') !== -1) {
                            items = valor.split(';').map(function(s){ return s.trim(); }).filter(function(s){ return s.length > 0; });
                        }
                        // Remove duplicatas mantendo ordem
                        var seen = {};
                        var unique = [];
                        items.forEach(function(it){ if (!seen[it]) { seen[it] = true; unique.push(it); } });

                        if (unique.length <= 1) {
                            container.textContent = unique[0] || valor; // mostra texto simples se apenas 1
                        } else {
                            var ul = document.createElement('ul');
                            ul.className = 'detalhes-servicos-list';
                            unique.forEach(function(it){
                                var li = document.createElement('li');
                                li.textContent = it;
                                ul.appendChild(li);
                            });
                            container.appendChild(ul);
                        }
                    }
                } else {
                    // fallback: se não existir 'servicos_full', preencher 'servico' (compatibilidade)
                    var servEl = document.getElementById('servico');
                    if (servEl) servEl.textContent = valor;
                }
            })();
        safeSetText("metodo", os.metodo);
        if (document.getElementById("metodo_secundario")) {
            safeSetText("metodo_secundario", os.metodo_secundario);
        }
        // Tanques: exibir TODOS os tanques (CSV) se disponível
        var tanquesCsv = (os.tanques || os.tanque || '').toString();
        safeSetText("tanque", tanquesCsv);
        // opcional: se existir um contêiner 'tanques_full', renderiza como lista
        var tanquesFull = document.getElementById('tanques_full');
        if (tanquesFull) {
            tanquesFull.innerHTML = '';
            var ulT = document.createElement('ul');
            ulT.className = 'detalhes-tanques-list';
            var itensT = tanquesCsv.split(',').map(function(s){ return s.trim(); }).filter(function(s){ return s.length>0; });
            if (itensT.length === 0) {
                var li0 = document.createElement('li');
                li0.textContent = 'Nenhum tanque definido.';
                ulT.appendChild(li0);
            } else {
                itensT.forEach(function(t){ var li=document.createElement('li'); li.textContent=t; ulT.appendChild(li); });
            }
            tanquesFull.appendChild(ulT);
        }
        safeSetText("volume_tq", os.volume_tanque);
        safeSetText("especificacao", os.especificacao);
        // preencher campos de 'frente' no modal de detalhes
        var diFrente = document.getElementById('data_inicio_frente');
        var dfFrente = document.getElementById('data_fim_frente');
        var diasFrente = document.getElementById('dias_op_frente');
        if (diFrente) diFrente.innerText = os.data_inicio_frente || '';
        if (dfFrente) dfFrente.innerText = os.data_fim_frente || '';
        if (diasFrente) diasFrente.innerText = os.dias_de_operacao_frente || '';
        // PO e Material
        var poSpan = document.getElementById('po');
        if (poSpan) poSpan.innerText = os.po || '';
        var matSpan = document.getElementById('material');
        if (matSpan) matSpan.innerText = os.material || '';
        safeSetText("pob", os.pob);
        safeSetText("coordenador", os.coordenador);
        safeSetText("supervisor", os.supervisor);
        safeSetText("status_os", os.status_operacao);
        safeSetText("status_geral", os.status_geral);
        safeSetText("status_comercial", os.status_comercial);
        safeSetText("observacao", os.observacao || 'Nenhuma observação registrada.');
        // campos de links de controle e materiais foram removidos do projeto

        detalhesModal.style.display = "flex";

        try {
            const count = parseInt(localStorage.getItem('rdo_pending_count') || '0');
            localStorage.setItem('rdo_pending_count', (count + 1).toString());
        } catch(e) {}
        exibirNotificacaoExportarPDF();

        const btnExportar = document.getElementById('confirmar-exportar-pdf');
        const btnRecusar = document.getElementById('recusar-exportar-pdf');
        if (btnExportar) {
            btnExportar.onclick = function() {
                window.location.href = `/os/${osId}/exportar_pdf/`;
            };
        }
        if (btnRecusar) btnRecusar.onclick = minimizarNotificacaoPDF;
    })
    .catch(error => {
        NotificationManager.show('Erro ao carregar dados da OS: ' + (error.message || JSON.stringify(error)), 'error');
        detalhesModal.style.display = "flex";
        exibirNotificacaoExportarPDF();
    });
}

// Gerenciamento da notificação de exportação PDF
function exibirNotificacaoExportarPDF() {
    var notificacao = document.getElementById('notificacao-exportar-pdf');
    var minimizada = document.getElementById('notificacao-pdf-minimizada');
    if (notificacao) {
        notificacao.style.display = 'block';
        notificacao.setAttribute('aria-hidden', 'false');
    }
    if (minimizada) {
        minimizada.style.display = 'none';
        minimizada.setAttribute('aria-hidden', 'true');
    }
}

// Eventos para abrir e fechar o modal de detalhes
document.querySelectorAll(".btn_tabela[id^='btn_detalhes_']").forEach(botao => {
    botao.addEventListener("click", function () {
        const osId = this.getAttribute("data-id");
    // Em produção, não exibe debug
        abrirDetalhesModal(osId);
    });
});

document.querySelector("#detalhes_os .close-btn").addEventListener("click", fecharDetalhesModal);

window.addEventListener("click", (e) => {
    if (e.target === detalhesModal) {
        fecharDetalhesModal();
    }
});


function fecharDetalhesModal() {
    var detalhesModal = document.getElementById("detalhes_os");
    if (detalhesModal) {
        detalhesModal.style.display = "none";
    }
}

document.querySelector("#detalhes_os .close-btn").addEventListener("click", fecharDetalhesModal);

window.addEventListener("click", (e) => {
    if (e.target === detalhesModal) {
        fecharDetalhesModal();
    }
});

// Filtro por status
const filtroIcon = document.querySelector(".fa-filter");
const dropdown = document.getElementById("dropdown-filtro");

if (filtroIcon) {
    filtroIcon.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation(); 
        if (dropdown) dropdown.style.display = dropdown.style.display === "flex" ? "none" : "flex";
    });
}

if (dropdown) {
    document.addEventListener("click", (e) => {
        if (!dropdown.contains(e.target) && e.target !== filtroIcon) {
            dropdown.style.display = "none";
        }
    });
}

// --- Renderiza serviços como chips (substitui o comportamento da reticência) ---
document.addEventListener('DOMContentLoaded', function(){
    function renderServiceChipsCell(td){
        try {
            const container = td.querySelector('.servicos-chips') || td;
            const rawAttr = td.getAttribute('data-servicos') || td.getAttribute('data-primary') || '';
            const raw = (rawAttr || '').toString();
            const items = raw.split(',').map(s=>s.trim()).filter(Boolean);
            // fallback: if no comma-separated tokens, try semicolon
            if(items.length <= 1 && raw.indexOf(';') !== -1) {
                const tmp = raw.split(';').map(s=>s.trim()).filter(Boolean);
                if(tmp.length) items.length = 0, tmp.forEach(i=>items.push(i));
            }
            if(container.dataset.rendered === raw) return;
            container.innerHTML = '';
            const maxVisible = 6;
            const makeChip = (text, extraClass) => {
                const span = document.createElement('span');
                span.className = 'servico-chip' + (extraClass? ' ' + extraClass : '');
                span.textContent = text;
                return span;
            };
            if(items.length === 0) {
                const primary = td.getAttribute('data-primary') || td.textContent || '';
                if(primary && primary.trim()) container.appendChild(makeChip(primary.trim()));
                else container.appendChild(makeChip('-'));
            } else {
                // Criar chips para TODOS os itens (para acessibilidade e copiar/tooltip),
                // mas aplicar colapso visual por CSS quando muitos itens existirem.
                items.forEach(it => container.appendChild(makeChip(it)));
                if(items.length > maxVisible){
                    const remaining = items.length - maxVisible;
                    container.classList.add('collapsed');
                    const plus = makeChip('+' + remaining, 'servico-chip-plus');
                    plus.setAttribute('role','button');
                    plus.tabIndex = 0;
                    plus.addEventListener('click', () => {
                        if(container.classList.contains('expanded')){
                            container.classList.remove('expanded');
                            container.classList.add('collapsed');
                            plus.textContent = '+' + remaining;
                        } else {
                            container.classList.remove('collapsed');
                            container.classList.add('expanded');
                            plus.textContent = '—';
                        }
                    });
                    plus.addEventListener('keypress', (e) => { if(e.key === 'Enter' || e.key === ' ') plus.click(); });
                    container.appendChild(plus);
                }
            }
            container.dataset.rendered = raw;
        } catch(err) {
            try {
                td.textContent = td.getAttribute('data-servicos') || td.getAttribute('data-primary') || td.textContent || '';
            } catch(_){}
        }
    }

    document.querySelectorAll('.td-servicos').forEach(td => {
        if(!td.querySelector('.servicos-chips')){
            // limpar texto residual (evita duplicação entre texto e chips)
            td.innerHTML = '';
            const div = document.createElement('div');
            div.className = 'servicos-chips';
            td.appendChild(div);
        } else {
            // remover text nodes que possam estar fora do container
            Array.from(td.childNodes).forEach(n => { if(n.nodeType === Node.TEXT_NODE && n.textContent.trim()) n.textContent=''; });
        }
        renderServiceChipsCell(td);
    });

    const tbody = document.querySelector('.tabela_conteiner tbody');
    if(tbody){
        const obs = new MutationObserver(()=> document.querySelectorAll('.td-servicos').forEach(renderServiceChipsCell));
        obs.observe(tbody, {childList:true, subtree:true});
    }
});

// --- Renderiza tanques como chips (comportamento espelhado aos serviços) ---
(function(){
    function renderTanquesChipsCell(td){
        try{
            const container = td.querySelector('.tanques-chips') || td;
            const rawAttr = td.getAttribute('data-tanques') || '';
            let items = (rawAttr||'').toString().split(',').map(s=>s.trim()).filter(Boolean);
            if(items.length <= 1 && rawAttr && rawAttr.indexOf(';') !== -1){
                items = rawAttr.split(';').map(s=>s.trim()).filter(Boolean);
            }
            if(container.dataset.rendered === rawAttr) return;
            container.innerHTML = '';
            const maxVisible = 6;
            const makeChip = (text, extraClass) => {
                const span = document.createElement('span');
                span.className = 'tanque-chip' + (extraClass? ' ' + extraClass : '');
                span.textContent = text;
                return span;
            };
            if(items.length === 0){
                const primary = td.getAttribute('data-tanques') || td.textContent || '';
                container.appendChild(makeChip(primary.trim() || '-'));
            } else {
                items.forEach(it => container.appendChild(makeChip(it)));
                if(items.length > maxVisible){
                    const remaining = items.length - maxVisible;
                    container.classList.add('collapsed');
                    const plus = makeChip('+' + remaining, 'tanque-chip-plus');
                    plus.setAttribute('role','button');
                    plus.tabIndex = 0;
                    plus.addEventListener('click', () => {
                        if(container.classList.contains('expanded')){
                            container.classList.remove('expanded');
                            container.classList.add('collapsed');
                            plus.textContent = '+' + remaining;
                        } else {
                            container.classList.remove('collapsed');
                            container.classList.add('expanded');
                            plus.textContent = '—';
                        }
                    });
                    plus.addEventListener('keypress', (e) => { if(e.key === 'Enter' || e.key === ' ') plus.click(); });
                    container.appendChild(plus);
                }
            }
            container.dataset.rendered = rawAttr;
        } catch(err){
            try{ td.textContent = td.getAttribute('data-tanques') || td.textContent || ''; } catch(_){}
        }
    }

    function initTanques(){
        document.querySelectorAll('.td-tanques').forEach(td => {
            if(!td.querySelector('.tanques-chips')){
                // limpar texto residual para evitar duplicação
                td.innerHTML = '';
                const div = document.createElement('div');
                div.className = 'tanques-chips';
                td.appendChild(div);
            } else {
                Array.from(td.childNodes).forEach(n => { if(n.nodeType === Node.TEXT_NODE && n.textContent.trim()) n.textContent=''; });
            }
            renderTanquesChipsCell(td);
        });
        const tbody = document.querySelector('.tabela_conteiner tbody');
        if(tbody){
            const obs = new MutationObserver(()=> document.querySelectorAll('.td-tanques').forEach(renderTanquesChipsCell));
            obs.observe(tbody, {childList:true, subtree:true});
        }
    }

    if(document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', initTanques);
    } else {
        // DOM already ready
        setTimeout(initTanques, 0);
    }
})();

document.querySelectorAll(".opcao-filtro").forEach(opcao => {
    opcao.addEventListener("click", function () {
        const statusSelecionado = this.getAttribute("data-status").toLowerCase();
        filtrarPorStatus(statusSelecionado);
        if (dropdown) dropdown.style.display = "none";
    });
});

// Função para filtrar linhas da tabela por status
function filtrarPorStatus(statusFiltro) {
    const linhas = document.querySelectorAll("tbody tr");
    linhas.forEach(linha => {
        const dataStatus = linha.getAttribute('data-status');
        if (dataStatus !== null) {
            linha.style.display = (dataStatus === statusFiltro) ? "" : "none";
            return;
        }
        const celulas = linha.querySelectorAll("td");
        const statusCell = celulas[19];
        if (statusCell) {
            const statusTexto = statusCell.textContent.toLowerCase().trim();
            linha.style.display = statusTexto === statusFiltro ? "" : "none";
        }
    });
}

// Gerenciamento do painel de filtros
function toggleFiltros() {
    const filterPanel = document.getElementById("campos-filtro");
    if (!filterPanel) return;
    filterPanel.classList.toggle("visible");

    // botão pode ser identificado por classe ou por id 'filter-toggle'
    const toggleButton = document.querySelector(".filter-toggle") || document.getElementById('filter-toggle') || document.querySelector('#filter-toggle');
    if (!toggleButton) return;
    if (filterPanel.classList.contains("visible")) {
        try { toggleButton.textContent = "Ocultar Filtros"; } catch(e){}
    } else {
        try { toggleButton.textContent = "Mostrar Filtros"; } catch(e){}
    }
}

// Evento para o botão de alternar filtros (fecha ao clicar fora)
document.addEventListener('click', function(event) {
    const filterPanel = document.getElementById("campos-filtro");
    const toggleButton = document.querySelector(".filter-toggle") || document.getElementById('filter-toggle') || document.querySelector('#filter-toggle');
    if (!filterPanel) return;

    try {
        if (filterPanel.classList && filterPanel.classList.contains("visible") &&
            !filterPanel.contains(event.target) &&
            event.target !== toggleButton) {
            filterPanel.classList.remove("visible");
            if (toggleButton) try { toggleButton.textContent = "Mostrar Filtros"; } catch(e){}
        }
    } catch (e) {
        // proteção adicional: se algo falhar, apenas não interromper o fluxo
    }
});

// Se existir um elemento com classe '.filter-panel', evitar que cliques internos fechem o painel
const _filterPanelEl = document.querySelector('.filter-panel');
if (_filterPanelEl && _filterPanelEl.addEventListener) {
    _filterPanelEl.addEventListener('click', function(event) {
        try { event.stopPropagation(); } catch(e) {}
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const radioButtons = document.querySelectorAll('#box-opcao-container input[type="radio"]');
    const osExistenteField = document.getElementById('os-existente-Field');



    if (osExistenteField) {
        osExistenteField.style.display = 'none';
    }

    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {

            if (this.value === 'existente') {
                osExistenteField.style.display = 'block';
            } else {
                osExistenteField.style.display = 'none';
            }
        });
    });
});

document.addEventListener('DOMContentLoaded', function() {
    var btnLimpar = document.getElementById('btn-limpar-filtros');
    if (btnLimpar) {
        btnLimpar.addEventListener('click', function() {
            window.location.href = window.location.pathname;
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    // Mostrar/ocultar campos de data no painel de filtros
    var btnToggleDatas = document.getElementById('btn-toggle-datas');
    var filtroDataInicial = document.getElementById('filtro-data-inicial');
    var filtroDataFinal = document.getElementById('filtro-data-final');
    if (btnToggleDatas && filtroDataInicial && filtroDataFinal) {
        btnToggleDatas.addEventListener('click', function() {
            filtroDataInicial.classList.toggle('ativo');
            filtroDataFinal.classList.toggle('ativo');
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    var btnLimparDatasChip = document.getElementById('btn-limpar-datas-chip');
    if (btnLimparDatasChip) {
        btnLimparDatasChip.addEventListener('click', function() {
            const url = new URL(window.location.href);
            url.searchParams.delete('data_inicial');
            url.searchParams.delete('data_final');
            window.location.href = url.pathname + (url.searchParams.toString() ? '?' + url.searchParams.toString() : '');
        });
    }

   
    var btnLimparFiltros = document.getElementById('btn-limpar-filtros');
    if (btnLimparFiltros) {
        btnLimparFiltros.addEventListener('click', function() {
           
            window.location.href = window.location.pathname;
        });
    }

});
// Gerenciamento do modal de edição de OS
function abrirModalEdicao(osId) {

    
    
    (async () => {
        try {
            const data = await fetchJson(`/buscar_os/${osId}/`);
                if (data && data.success && data.os) {
                preencherFormularioEdicao(data.os);
                // popular o container de tags de edição com a lista completa de serviços, se fornecida
                try {
                    const editContainer = document.getElementById('edit_servico_tags_container');
                    const editHidden = document.getElementById('edit_servico_hidden');
                    if (editContainer && typeof editContainer.loadFromString === 'function') {
                        editContainer.loadFromString(data.os.servicos || data.os.servico || '');
                    }
                    if (editHidden) editHidden.value = data.os.servicos || data.os.servico || '';
                    // Garantir que o hidden de tanques da edição esteja preenchido
                    try {
                        const editTanHidden = document.getElementById('edit_tanques_hidden');
                        if (editTanHidden) editTanHidden.value = data.os.tanques || data.os.tanque || '';
                        // se a função de carregar tanques estiver disponível, invocar para construir os inputs
                        if (editContainer && typeof editContainer.loadIntoTanques === 'function') {
                            try { editContainer.loadIntoTanques(); } catch(e) { /* noop */ }
                        }
                    } catch(e) { /* noop */ }
                } catch (e) { /* noop */ }
                try {
                    const count = parseInt(localStorage.getItem('rdo_pending_count') || '0');
                    localStorage.setItem('rdo_pending_count', (count + 1).toString());
                } catch(e) {}
                document.getElementById('modal-edicao').style.display = 'flex';
                const novaObs = document.getElementById('nova_observacao');
                if (novaObs) novaObs.value = '';
            } else {
                NotificationManager.show('Erro ao carregar dados da OS: ' + (data && data.error), 'error');
            }
        } catch (err) {
            NotificationManager.show('Erro ao carregar dados da OS: ' + (err.message || JSON.stringify(err)), 'error');
        }
    })();
}

function fecharModalEdicao() {
    document.getElementById('modal-edicao').style.display = 'none';
    limparFormularioEdicao();
    // limpar container de tags para não manter estado entre edições
    try {
        const editContainer = document.getElementById('edit_servico_tags_container');
        const editHidden = document.getElementById('edit_servico_hidden');
        if (editContainer && typeof editContainer.clear === 'function') editContainer.clear();
        if (editHidden) editHidden.value = '';
    } catch (e) { /* noop */ }
}

// Eventos para abrir e fechar o modal de edição
function preencherFormularioEdicao(os) {

    try { console.debug('preencherFormularioEdicao called (original) id:', os && os.id, 'keys:', os ? Object.keys(os) : null); } catch(e) {}

    const setValue = (id, value, prop = 'value') => {
        const el = document.getElementById(id);
        if (el) {
            if (prop === 'value') {
                el.value = value || '';
            } else {
                el.textContent = value || 'N/A';
            }
        }
    };
    // Preencher os campos do formulário
    setValue('edit_num_os', os.numero_os, 'textContent');
    setValue('edit_id_os', os.id, 'textContent');
    setValue('edit_os_id', os.id);
    setValue('edit_cliente', os.cliente);
    setValue('edit_unidade', os.unidade);
    
    // Preencher solicitante: usar valor da OS atual, ou da primeira OS se vazio
    const solicitanteValue = os.solicitante || os.solicitante_from_first || '';
    setValue('edit_solicitante', solicitanteValue);
    
    setValue('edit_servico', os.servico);
    setValue('edit_metodo', os.metodo);
    setValue('edit_metodo_secundario', os.metodo_secundario);
    setValue('edit_tanque', os.tanque);
    setValue('edit_volume_tanque', os.volume_tanque);
    
    // Preencher PO: usar valor da OS atual, ou da primeira OS se vazio
    const poValue = os.po || os.po_from_first || '';
    setValue('edit_po', poValue);
    
    setValue('edit_material', os.material);
    setValue('edit_especificacao', os.especificacao);
    
    // Preencher tipo de operação: usar valor da OS atual, ou da primeira OS se vazio
    const tipoOperacaoValue = os.tipo_operacao || os.tipo_operacao_from_first || '';
    setValue('edit_tipo_operacao', tipoOperacaoValue);
    setValue('edit_turno', os.turno);
    
    setValue('edit_status_operacao', os.status_operacao);
    setValue('edit_status_geral', os.status_geral);
    // Tentar atribuir diretamente; se não selecionar, procurar opção por texto ou valor normalizado
    setValue('edit_status_planejamento', os.status_planejamento);
    try {
        const elPlan = document.getElementById('edit_status_planejamento');
        const desired = (os && typeof os.status_planejamento !== 'undefined' && os.status_planejamento !== null) ? String(os.status_planejamento).trim() : '';
        if (elPlan && desired) {
            // Se a atribuição direta não encontrou opção, elPlan.value ficará diferente de desired
            if (elPlan.value !== desired) {
                // Normalizar helper (minusculas, sem acentos, trim)
                const normalize = s => s ? s.toString().normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim() : '';
                const wantNorm = normalize(desired);
                let matched = null;
                for (const opt of Array.from(elPlan.options)) {
                    if (normalize(opt.value) === wantNorm || normalize(opt.textContent) === wantNorm) {
                        matched = opt;
                        break;
                    }
                }
                if (matched) {
                    elPlan.value = matched.value;
                    // disparar evento change caso haja listeners
                    try { elPlan.dispatchEvent(new Event('change', { bubbles: true })); } catch(e) {}
                }
            }
        }
    } catch(e) { console.debug('fallback set status_planejamento failed', e); }
    setValue('edit_status_comercial', os.status_comercial);
    
    // Preencher data de início: usar valor da OS atual, ou da primeira OS se vazio
    const dataInicioValue = os.data_inicio || os.data_inicio_from_first || '';
    setValue('edit_data_inicio', dataInicioValue);
    
    setValue('edit_data_fim', os.data_fim);
    setValue('edit_pob', os.pob);
    setValue('edit_coordenador', os.coordenador);
    // Campos 'frente' adicionados recentemente: datas e dias de operação
    setValue('edit_data_inicio_frente', os.data_inicio_frente);
    setValue('edit_data_fim_frente', os.data_fim_frente);
    setValue('edit_dias_de_operacao_frente', os.dias_de_operacao_frente, 'textContent');
    // Handle supervisor as either select (ModelChoice) or plain input
    try {
        var supEl = document.getElementById('edit_supervisor');
        if (supEl) {
            if (supEl.tagName === 'SELECT') {
                // Prefer numeric id if provided
                if (os.supervisor_id) {
                    // Try to set by value (pk)
                    var opt = supEl.querySelector('option[value="' + os.supervisor_id + '"]');
                    if (opt) {
                        supEl.value = String(os.supervisor_id);
                    } else {
                        // fallback: try match by text
                        var found = Array.from(supEl.options).find(o => o.textContent.trim() === (os.supervisor || '').trim());
                        if (found) supEl.value = found.value;
                    }
                } else {
                    var found = Array.from(supEl.options).find(o => o.textContent.trim() === (os.supervisor || '').trim());
                    if (found) supEl.value = found.value;
                }
            } else {
                supEl.value = os.supervisor || '';
            }
        }
    } catch(e) { console.warn('setting supervisor failed', e); }

    const observacoesField = document.getElementById('edit_observacoes');
    if (observacoesField) {
        observacoesField.value = os.observacao || '';
    }
        // campos de links de controle e materiais foram removidos do projeto

    const historicoDiv = document.getElementById('historico_observacoes');
    if (historicoDiv) {
        historicoDiv.textContent = os.observacao || "Nenhuma observação registrada.";
        // Se o histórico for muito grande, ativar rolagem no contêiner (cartão) para não vazar conteúdo
        try {
            setTimeout(() => {
                const limit = Math.max(window.innerHeight * 0.40, 360); // 40% da viewport ou 360px
                const card = historicoDiv.closest('.historico-card');
                if (card) {
                    if (historicoDiv.scrollHeight > limit) {
                        card.classList.add('long');
                    } else {
                        card.classList.remove('long');
                    }
                }
            }, 0);
        } catch (e) { /* noop */ }
    }
    const novaObs = document.getElementById('nova_observacao');
    if (novaObs) novaObs.value = '';
    // Garantir que o container de tags da edição seja populado e sincronize os tanques
    try {
        const editContainer = document.getElementById('edit_servico_tags_container');
        const editHidden = document.getElementById('edit_servico_hidden');
        // primeiro, garanta que o hidden de tanques esteja preenchido para uso na reconstrução
        try {
            const hiddenTanques = document.getElementById('edit_tanques_hidden');
            if (hiddenTanques) hiddenTanques.value = os.tanques || os.tanque || '';
        } catch (e) { /* noop */ }
        if (editContainer && typeof editContainer.loadFromString === 'function') {
            editContainer.loadFromString(os.servicos || os.servico || '');
            try { if (typeof editContainer.loadIntoTanques === 'function') editContainer.loadIntoTanques(); } catch(e){}
        }
        if (editHidden) editHidden.value = os.servicos || os.servico || '';
    } catch(e) {}
    // --- Nova: garantir supervisor e popular container de tanques (inserido inline para evitar problemas de ordem de load) ---
    try {
        // Ensure supervisor select/input is populated
        try {
            const select = document.querySelector('#modal-edicao select#id_supervisor');
            if (select) {
                if (os && os.supervisor_id) {
                    const opt = select.querySelector('option[value="' + os.supervisor_id + '"]');
                    if (opt) {
                        select.value = String(os.supervisor_id);
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    } else {
                        const found = Array.from(select.options).find(o => o.textContent.trim() === (os.supervisor || '').trim());
                        if (found) select.value = found.value;
                    }
                } else if (os && os.supervisor) {
                    const found = Array.from(select.options).find(o => o.textContent.trim() === (os.supervisor || '').trim());
                    if (found) select.value = found.value;
                }
            } else {
                // fallback to input
                const inputSup = document.getElementById('edit_supervisor') || document.querySelector('#modal-edicao [name="supervisor"]');
                if (inputSup) {
                    inputSup.value = os && (os.supervisor || os.supervisor_id) ? (os.supervisor || String(os.supervisor_id)) : '';
                    inputSup.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        } catch(e) { console.debug('inline supervisor set failed', e); }

        // Build tanque inputs UI from os.tanques (CSV) into #edit_tanques_container and sync hidden
        try {
            const cont = document.getElementById('edit_tanques_container');
            const hidden = document.getElementById('edit_tanques_hidden');
            try { console.debug('About to build tanques UI (improved):', 'os.tanques=', os && os.tanques, 'os.tanque=', os && os.tanque, 'containerExists=', !!cont, 'hiddenExists=', !!hidden); } catch(e) {}
            if (cont) {
                const csv = (os && (os.tanques || os.tanque)) ? String(os.tanques || os.tanque) : '';
                if (hidden) hidden.value = csv; // manter sincronizado
                // obter lista de serviços (para rotular as linhas) a partir do container de serviços de edição
                let services = [];
                try {
                    const svcCont = document.getElementById('edit_servico_tags_container');
                    if (svcCont) {
                        services = Array.from(svcCont.querySelectorAll('.tag-item')).map(t => t.childNodes && t.childNodes.length ? t.childNodes[0].nodeValue.trim() : t.textContent.trim()).filter(Boolean);
                    }
                } catch(e) { services = []; }

                // fallback: derive serviços a partir do payload (CSV)
                if (!services.length) {
                    const svcCsv = (os && (os.servicos || os.servico)) ? String(os.servicos || os.servico) : '';
                    services = svcCsv ? svcCsv.split(',').map(s=>s.trim()).filter(Boolean) : [];
                }

                const tankVals = csv ? csv.split(',').map(s => s.trim()) : [];
                cont.innerHTML = '';

                // se tivermos serviços, associar uma linha de tanque por serviço
                if (services.length) {
                    services.forEach((svc, idx) => {
                        // usar buildTankRow para manter consistência com a UI de criação
                        let row = null;
                        try {
                            row = buildTankRow(svc, idx);
                        } catch(e) {
                            // fallback simples
                            row = document.createElement('div'); row.className = 'tank-row';
                            const inp = document.createElement('input'); inp.type='text'; inp.className='form-control tanque-input'; row.appendChild(inp);
                        }
                        // preencher valor do tanque correspondente, se houver
                        try {
                            const inp = row.querySelector('.tanque-input');
                            if (inp) inp.value = (tankVals[idx] || '').trim();
                        } catch(e){}
                        cont.appendChild(row);
                    });
                } else {
                    // sem serviços: criar uma linha por tanque existente
                    if (tankVals.length) {
                        tankVals.forEach((t, idx) => {
                            let row = document.createElement('div'); row.className='tank-row';
                            let inp = document.createElement('input'); inp.type='text'; inp.className='form-control tanque-input'; inp.value = t || '';
                            inp.addEventListener('input', function(){ try { updateTankHiddenFields(); } catch(e){} });
                            row.appendChild(inp);
                            cont.appendChild(row);
                        });
                    }
                }

                // garantir que os hidden/valores estejam sincronizados com os inputs criados
                try { updateTankHiddenFields(); } catch(e) {}
            }
        } catch(e) { console.debug('improved tanques UI build failed', e); }
    } catch(e) {}

    try { updateTankHiddenFields(); } catch(e) {}
}

function limparFormularioEdicao() {
    
    const campos = [
    'edit_cliente', 'edit_unidade', 'edit_solicitante', 'edit_servico',
    'edit_metodo', 'edit_metodo_secundario', 'edit_tanque', 'edit_volume_tanque', 'edit_especificacao',
        'edit_tipo_operacao', 'edit_status_operacao', 'edit_status_comercial',
        'edit_data_inicio', 'edit_data_fim', 'edit_pob', 'edit_coordenador',
    'edit_supervisor', 'edit_observacoes'
    ];
    // incluir turno na limpeza do formulário de edição
    campos.push('edit_turno');
    // incluir campos de frente para limpeza
    campos.push('edit_data_inicio_frente', 'edit_data_fim_frente', 'edit_dias_de_operacao_frente');
    // incluir PO e material
    campos.push('edit_po', 'edit_material');
    
    campos.forEach(campo => {
        const element = document.getElementById(campo);
        if (element) {
            if (element.tagName === 'SELECT') {
                element.selectedIndex = 0;
            } else {
                element.value = '';
            }
        }
    });
    // limpar campo de status_planejamento se existir
    const elStatusPlan = document.getElementById('edit_status_planejamento');
    if (elStatusPlan) try { elStatusPlan.selectedIndex = 0; } catch(e) {}
    // 'edit_dias_de_operacao_frente' é um span/texto em alguns templates — limpar explicitamente
    var diasFrenteEl = document.getElementById('edit_dias_de_operacao_frente');
    if (diasFrenteEl) try { diasFrenteEl.textContent = ''; } catch(e) {}
    
    
    document.getElementById('edit_num_os').textContent = '';
    // 'codigo_os' removed from models; clear UI element if present
    var elCodOs = document.getElementById('edit_cod_os');
    if (elCodOs) elCodOs.textContent = '';
    document.getElementById('edit_id_os').textContent = '';
    document.getElementById('edit_os_id').value = '';
}

// Função para lidar com a submissão do formulário de edição via onclick

// Eventos para abrir e fechar o modal de edição
document.addEventListener('DOMContentLoaded', function() {
    
    window.addEventListener('click', (e) => {
        const modalEdicao = document.getElementById('modal-edicao');
        if (e.target === modalEdicao) {
            fecharModalEdicao();
        }
    });
    
   
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            fecharModalEdicao();
        }
    });
    
    // Envio do formulário de edição via AJAX
    const formEdicao = document.getElementById('form-edicao');
    if (formEdicao) {
 
        formEdicao.addEventListener('submit', function(e) {

            e.preventDefault();

            
            const submitBtn = this.querySelector('.btn-confirmar');
            const originalText = submitBtn.textContent;
            submitBtn.textContent = 'Salvando...';
            submitBtn.disabled = true;
            
            // garantir que os campos de tanques e serviços ocultos da edição estejam atualizados
            try {
                const editServContainer = document.getElementById('edit_servico_tags_container');
                const editServHidden = document.getElementById('edit_servico_hidden');
                if (editServContainer && editServHidden) {
                    const vals = Array.from(editServContainer.querySelectorAll('.tag-item')).map(t => t.childNodes && t.childNodes.length ? t.childNodes[0].nodeValue.trim() : t.textContent.trim()).filter(v => v);
                    editServHidden.value = vals.join(', ');
                    // reconstruir tanques caso a função loadIntoTanques esteja disponível
                    try { if (typeof editServContainer.loadIntoTanques === 'function') editServContainer.loadIntoTanques(); } catch(e) {}
                }
            } catch(e) {}
            try { updateTankHiddenFields(); } catch(e) {}

            const formData = new FormData(this);

            
            (async () => {
                try {
                    const data = await fetchJson(this.action, {
                        method: 'POST',
                        body: formData,
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                        },
                        timeout: 20000
                    });

                    if (data && data.success) {
                        NotificationManager.show("OS atualizada com sucesso!", "success");
                        fecharModalEdicao();
                        const novaObs = document.getElementById('nova_observacao');
                        if (novaObs) novaObs.value = '';
                        NotificationManager.hideLoading();
                        if (NotificationManager.loadingOverlay && NotificationManager.loadingOverlay.parentNode) {
                            NotificationManager.loadingOverlay.parentNode.removeChild(NotificationManager.loadingOverlay);
                        }
                        // Se o backend retornou o objeto 'os', atualizar a linha existente sem reload
                        try {
                            if (data.os) {
                                const os = data.os;
                                // localizar botão editar correspondente e a linha pai
                                const btnEdit = document.querySelector(`.btn-editar[data-id="${os.id}"]`);
                                let tr = null;
                                if (btnEdit) tr = btnEdit.closest('tr');
                                // fallback: tentar localizar pela célula com o id
                                if (!tr) {
                                    const possible = Array.from(document.querySelectorAll('tbody tr'))
                                        .find(r => r.querySelector(`.btn-editar[data-id=\"${os.id}\"]`));
                                    tr = possible || null;
                                }
                                if (tr) {
                                    tr.setAttribute('data-cliente', os.cliente || '');
                                    tr.setAttribute('data-unidade', os.unidade || '');
                                    tr.setAttribute('data-status', (os.status_operacao || '').toString().toLowerCase());
                                    tr.setAttribute('data-status-planejamento', (os.status_planejamento || '').toString().toLowerCase());
                                    tr.innerHTML = `
                                        <td>${os.id || ''}</td>
                                        <td>${os.numero_os || ''}</td>
                                        <td>${os.data_inicio || ''}</td>
                                        <td>${os.data_fim || ''}</td>
                                        <td>${os.data_inicio_frente || ''}</td>
                                        <td>${os.data_fim_frente || ''}</td>
                                        <td>${os.dias_de_operacao_frente || ''}</td>
                                        <td>${os.turno || ''}</td>
                                        <td>${os.cliente || ''}</td>
                                        <td>${os.unidade || ''}</td>
                                        <td>${os.solicitante || ''}</td>
                                        <td>${os.tipo_operacao || ''}</td>
                                        ${buildServiceCell(os)}
                                        <td>${os.tanques || os.tanque || ''}</td>
                                            <td>${os.volume_tanque || ''}</td>
                                            <td>${os.especificacao || ''}</td>
                                            <td>${os.metodo || ''}</td>
                                            <td>${os.po || ''}</td>
                                            <td>${os.material || ''}</td>
                                            <td>${os.pob || ''}</td>
                                        <td>${os.dias_de_operacao || ''}</td>
                                        <td>${os.coordenador || ''}</td>
                                        <td>${os.supervisor || ''}</td>
                                        <td>${os.status_geral || ''}</td>
                                        <td>${os.status_planejamento || ''}</td>
                                        <td>${os.status_operacao || ''}</td>
                                        <td>${os.material || ''}</td>
                                        <td>${os.status_comercial || ''}</td>
                                        <td>
                                            <button class="btn_tabela" id="btn_detalhes_${os.id}" data-id="${os.id}" onclick="abrirDetalhesModal('${os.id}')">
                                                <svg class="plusIcon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30">
                                                    <g mask="url(#mask0_21_345)"><path d="M13.75 23.75V16.25H6.25V13.75H13.75V6.25H16.25V13.75H23.75V16.25H16.25V23.75H13.75Z"></path></g>
                                                </svg>
                                            </button>
                                        </td>
                                        <td>
                                            <button class="btn_tabela btn-editar" data-id="${os.id}" onclick="abrirModalEdicao('${os.id}')">
                                                <svg viewBox="0 0 512 512"><path d="M410.3 231l11.3-11.3-33.9-33.9-62.1-62.1L291.7 89.8l-11.3 11.3-22.6 22.6L58.6 322.9c-10.4 10.4-18 23.3-22.2 37.4L1 480.7c-2.5 8.4-.2 17.5 6.1 23.7s15.3 8.5 23.7 6.1l120.3-35.4c14.1-4.2 27-11.8 37.4-22.2L387.7 253.7 410.3 231zM160 399.4l-9.1 22.7c-4 3.1-8.5 5.4-13.3 6.9L59.4 452l23-78.1c1.4-4.9 3.8-9.4 6.9-13.3l22.7-9.1v32c0 8.8 7.2 16 16 16h32zM362.7 18.7L348.3 33.2 325.7 55.8 314.3 67.1l33.9 33.9 62.1 62.1 33.9 33.9 11.3-11.3 22.6-22.6 14.5-14.5c25-25 25-65.5 0-90.5L453.3 18.7c-25-25-65.5-25-90.5 0zm-47.4 168l-144 144c-6.2 6.2-16.4 6.2-22.6 0s-6.2-16.4 0-22.6l144-144c6.2-6.2 16.4-6.2 22.6 0s6.2 16.4 0 22.6z" /></svg>
                                            </button>
                                        </td>
                                    `;
                                    // re-anexar listeners
                                    try {
                                        var btnDet = tr.querySelector('#btn_detalhes_' + (os.id || ''));
                                        if (btnDet) {
                                            btnDet.addEventListener('click', function(ev){ ev.preventDefault && ev.preventDefault(); abrirDetalhesModal(String(os.id)); });
                                        }
                                        var btnEditNew = tr.querySelector('.btn-editar');
                                        if (btnEditNew) {
                                            btnEditNew.addEventListener('click', function(ev){ ev.preventDefault && ev.preventDefault(); abrirModalEdicao(String(os.id)); });
                                        }
                                    } catch(e) { console.debug('anexar listeners falhou (edit update)', e); }
                                    try { if (typeof addNewRowEffect === 'function') addNewRowEffect(tr); } catch(e){}
                                } else {
                                    // não encontrou a linha, recarregar como fallback
                                    setTimeout(() => { location.href = location.href; }, 150);
                                }
                                return;
                            }
                        } catch (e) {
                            console.warn('Atualização in-place falhou, recarregando', e);
                            setTimeout(() => { location.href = location.href; }, 150);
                        }
                        // Se não houver data.os, recarregar para garantir consistência
                        setTimeout(() => { location.href = location.href; }, 100);
                    } else {
                        NotificationManager.show('Erro ao atualizar OS: ' + (data && data.error), "error");
                    }
                } catch (err) {
                    NotificationManager.show("Erro ao atualizar OS: " + (err.message || JSON.stringify(err)), "error");
                } finally {
                    submitBtn.textContent = originalText;
                    submitBtn.disabled = false;
                }
            })();
            return false;
        });
    }
});

// Atualiza a exibição da observação em tempo real enquanto o usuário digita
document.addEventListener('DOMContentLoaded', function() {
    const observacoesField = document.getElementById('edit_observacoes');
    const observacaoSpan = document.getElementById('observacao');
    if (observacoesField && observacaoSpan) {
        observacoesField.addEventListener('input', function() {
            observacaoSpan.innerText = observacoesField.value || "Nenhuma observação registrada.";
        });
    }
});
    

// Exportar tabela para Excel
document.addEventListener('DOMContentLoaded', function() {
    var btnExportar = document.getElementById('exportar_excel');
    if (btnExportar) {
        btnExportar.addEventListener('click', function(e) {
            e.preventDefault();
            if (window.NotificationManager && typeof NotificationManager.show === 'function') {
                NotificationManager.show('Tabela exportada com sucesso!', 'success', 4000);
            } else {
                alert('Tabela exportada com sucesso!');
            }
            setTimeout(function() {
                window.location.href = '/exportar_excel/';
            }, 700);
        });
    }
});


// Validação client-side: exigir Supervisor ao abrir OS (movido do template)
(function(){
    function onReady(fn){ if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn); else fn(); }
    onReady(function(){
        try{
            var form = document.getElementById('form-os');
            if (!form) return;
            var supervisorSelect = form.querySelector('select[name="supervisor"]') || form.querySelector('[name="supervisor"]');
            if (!supervisorSelect) return;

            // marcar como required (para navegadores que suportam)
            supervisorSelect.setAttribute('required','required');

            // helper visual mínimo
            function showInlineError(el, msg){
                var id = el.getAttribute('data-err-id');
                var existing = id ? document.getElementById(id) : null;
                if (existing) existing.remove();
                var err = document.createElement('div');
                err.className = 'field-error small';
                err.style.color = '#b00020';
                err.style.marginTop = '6px';
                err.style.fontSize = '0.9rem';
                err.textContent = msg || 'Selecione um Supervisor';
                var uid = 'err-supervisor-'+Date.now();
                err.id = uid;
                el.setAttribute('data-err-id', uid);
                el.parentNode && el.parentNode.appendChild(err);
                setTimeout(function(){ try{ err.style.opacity = '1'; }catch(e){} }, 20);
            }

            function clearInlineError(el){
                var id = el.getAttribute('data-err-id');
                if (!id) return;
                var ex = document.getElementById(id);
                if (ex) try{ ex.remove(); }catch(e){}
                el.removeAttribute('data-err-id');
            }

            form.addEventListener('submit', function(ev){
                try{
                    var val = supervisorSelect.value;
                    if (!val || String(val).trim() === ''){
                        ev.preventDefault();
                        ev.stopPropagation();
                        clearInlineError(supervisorSelect);
                        showInlineError(supervisorSelect, 'Por favor selecione um Supervisor antes de abrir a OS.');
                        try{ supervisorSelect.focus(); }catch(e){}
                        return false;
                    }
                    clearInlineError(supervisorSelect);
                }catch(e){/* noop */}
            }, false);

            // remover erro ao mudar
            supervisorSelect.addEventListener('change', function(){ clearInlineError(supervisorSelect); });

        }catch(e){ console.error('validation init error', e); }
    });
})();
// (Wrapper removed) lógica de pré-população de Supervisor e Tanques foi integrada diretamente em preencherFormularioEdicao

// Validação client-side para o modal de edição (form-edicao) (movido do template)
(function(){
    function qs(sel, ctx){ return (ctx||document).querySelector(sel); }
    function qsa(sel, ctx){ return Array.from((ctx||document).querySelectorAll(sel)); }

    document.addEventListener('DOMContentLoaded', function(){
        var form = qs('#form-edicao');
        if (!form) return;

        function clearError(el){
            if (!el) return;
            var id = el.getAttribute('data-err-id');
            if (id){
                var ex = document.getElementById(id);
                if (ex) try{ ex.remove(); }catch(e){}
                el.removeAttribute('data-err-id');
            }
        }

        function showError(el, msg){
            if (!el) return;
            clearError(el);
            var div = document.createElement('div');
            div.className = 'field-error small';
            div.style.color = '#b00020';
            div.style.marginTop = '6px';
            div.style.fontSize = '0.92rem';
            div.textContent = msg || 'Campo obrigatório';
            var uid = 'err-edit-supervisor-' + Date.now();
            div.id = uid;
            el.setAttribute('data-err-id', uid);
            // prefer appending after the input element
            try { el.parentNode && el.parentNode.appendChild(div); } catch(e){ form.appendChild(div); }
            try { el.focus(); } catch(e){}
        }

        var sup = qs('#edit_supervisor') || qs('#form-edicao [name="supervisor"]');
        if (!sup) return;

        // ensure browsers that support required will know, but we still enforce
        try { sup.setAttribute('required','required'); } catch(e){}

        sup.addEventListener('input', function(){ clearError(sup); });
        sup.addEventListener('change', function(){ clearError(sup); });

        form.addEventListener('submit', function(ev){
            try{
                clearError(sup);
                var val = (sup.value || '').toString().trim();
                if (!val){
                    ev.preventDefault();
                    ev.stopPropagation();
                    showError(sup, 'Por favor selecione ou informe um Supervisor antes de salvar.');
                    return false;
                }
                // Optionally: further format checks can be added here
            }catch(err){
                // se ocorrer erro na validação, não impedir envio — mas logar
                console.warn('Erro na validação do supervisor (form-edicao):', err);
            }
        }, false);
    });
})();

// Campo `link_logistica` foi removido (agora é fixo).
// O bloco legado de validação foi removido aqui porque estava com erro de sintaxe e quebrava o carregamento do arquivo.

// (Wrapper removed) lógica de pré-população de link de logística foi integrada diretamente em abrirModalEdicao

// Quando uma OS é criada, inserir imediatamente uma linha na tabela (inclui campo `turno`) e reidratar como fallback
window.addEventListener('os:created', async function(ev) {
    try {
        const os = ev && ev.detail ? ev.detail : null;
        if (os && typeof insertOsRowIntoTable === 'function') {
            try {
                insertOsRowIntoTable(os);
                try { NotificationManager.show('OS adicionada à tabela.', 'success'); } catch(_){}
            } catch (err) {
                console.debug('Falha ao inserir linha imediatamente:', err);
            }
        }
    } catch (e) {}
    // fallback: reidratar tabela (se função disponível)
    try { if (typeof refreshTableAndBindings === 'function') await refreshTableAndBindings(); } catch(e) {}
});

// Função que constrói e insere uma linha na tabela a partir do objeto `os` recebido do servidor
function insertOsRowIntoTable(os) {
    if (!os) return;
    const tbody = document.querySelector('.tabela_conteiner table tbody');
    if (!tbody) return;

    const tr = document.createElement('tr');
    tr.setAttribute('data-cliente', escapeHtml(os.cliente || ''));
    tr.setAttribute('data-unidade', escapeHtml(os.unidade || ''));
    tr.setAttribute('data-status', ((os.status_operacao||'')+'').toLowerCase());
    tr.setAttribute('data-numero-os', escapeHtml(os.numero_os || ''));

    function makeTd(text, cls) {
        const d = document.createElement('td');
        if (cls) d.className = cls;
        d.textContent = text != null ? text : '';
        return d;
    }

    // adicionar células em ordem conforme template
    tr.appendChild(makeTd(os.id)); // ID
    tr.appendChild(makeTd(os.numero_os));
    tr.appendChild(makeTd(os.cliente));
    tr.appendChild(makeTd(os.unidade));

    // serviço(s)
    const tdServ = document.createElement('td');
    tdServ.className = 'td-servicos';
    const servFull = os.servicos || os.servico || '';
    tdServ.setAttribute('data-servicos', servFull);
    tdServ.setAttribute('data-primary', os.servico || '');
    tdServ.title = 'Clique para ver todos os serviços';
    const spanServ = document.createElement('span');
    spanServ.className = 'servico-primary';
    spanServ.textContent = os.servico || (Array.isArray(servFull) ? servFull.join(', ') : servFull);
    tdServ.appendChild(spanServ);
    if (servFull && String(servFull).indexOf(',') !== -1) {
        const more = document.createElement('span'); more.className = 'servicos-more'; more.textContent = ' (…)'; tdServ.appendChild(more);
    }
    tr.appendChild(tdServ);

    tr.appendChild(makeTd(os.metodo));

    // tanques
    const tdTan = document.createElement('td');
    tdTan.className = 'td-tanques';
    const tanFull = os.tanques || os.tanque || '';
    tdTan.setAttribute('data-tanques', tanFull);
    tdTan.title = 'Clique para ver todos os tanques';
    const spanTan = document.createElement('span'); spanTan.className = 'tanque-primary';
    try { spanTan.textContent = String(tanFull || '').split(',').map(s=>s.trim()).filter(Boolean)[0] || (tanFull||''); } catch(e) { spanTan.textContent = tanFull || ''; }
    tdTan.appendChild(spanTan);
    if (tanFull && String(tanFull).indexOf(',') !== -1) { const moreT = document.createElement('span'); moreT.className='tanques-more'; moreT.textContent=' (…)'; tdTan.appendChild(moreT); }
    tr.appendChild(tdTan);

    tr.appendChild(makeTd(os.especificacao));
    tr.appendChild(makeTd(os.pob));
    tr.appendChild(makeTd(os.data_inicio));
    tr.appendChild(makeTd(os.data_fim));
    tr.appendChild(makeTd(os.dias_de_operacao));
    tr.appendChild(makeTd(os.frente));
    tr.appendChild(makeTd(os.data_inicio_frente));
    tr.appendChild(makeTd(os.data_fim_frente));
    tr.appendChild(makeTd(os.dias_de_operacao_frente));
    // turno — o campo solicitado
    tr.appendChild(makeTd(os.turno));
    tr.appendChild(makeTd(os.solicitante));
    tr.appendChild(makeTd(os.supervisor));
    tr.appendChild(makeTd(os.coordenador));
    tr.appendChild(makeTd(os.po));
    tr.appendChild(makeTd(os.status_geral));
    tr.appendChild(makeTd(os.status_operacao));
    tr.appendChild(makeTd(os.material));
    tr.appendChild(makeTd(os.status_comercial));

    // editar
    const tdEdit = document.createElement('td');
    const btnEdit = document.createElement('button'); btnEdit.type='button'; btnEdit.className='btn_tabela btn-editar'; btnEdit.setAttribute('data-id', os.id);
    btnEdit.addEventListener('click', function(){ abrirModalEdicao(String(os.id)); });
    btnEdit.innerHTML = '<svg viewBox="0 0 512 512" width="18" height="18"><path d="M410.3 231l11.3-11.3-33.9-33.9-62.1-62.1L291.7 89.8l-11.3 11.3-22.6 22.6L58.6 322.9c-10.4 10.4-18 23.3-22.2 37.4L1 480.7c-2.5 8.4-.2 17.5 6.1 23.7s15.3 8.5 23.7 6.1l120.3-35.4c14.1-4.2 27-11.8 37.4-22.2L387.7 253.7 410.3 231z"/></svg>';
    tdEdit.appendChild(btnEdit); tr.appendChild(tdEdit);

    // logistica
    const tdLog = document.createElement('td'); const btnLog = document.createElement('button'); btnLog.type='button'; btnLog.className='btn_tabela'; btnLog.addEventListener('click', function(){ abrirLogisticaModal(String(os.id)); }); btnLog.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16"><path fill-rule="evenodd" d="M15.528 2.973a.75.75 0 0 1 .472.696v8.662a.75.75 0 0 1-.472.696l-7.25 2.9a.75.75 0 0 1-.557 0l-7.25-2.9A.75.75 0 0 1 0 12.331V3.669a.75.75 0 0 1 .471-.696L7.443.184l.01-.003.268-.108a.75.75 0 0 1 .558 0l.269.108.01.003z"/></svg>'; tdLog.appendChild(btnLog); tr.appendChild(tdLog);

    // detalhes
    const tdDet = document.createElement('td'); const btnDet = document.createElement('button'); btnDet.type='button'; btnDet.className='btn_tabela'; btnDet.addEventListener('click', function(){ abrirDetalhesModal(String(os.id)); }); btnDet.innerHTML='<svg width="18" height="18" viewBox="0 0 30 30"><path d="M13.75 23.75V16.25H6.25V13.75H13.75V6.25H16.25V13.75H23.75V16.25H16.25V23.75H13.75Z"/></svg>'; tdDet.appendChild(btnDet); tr.appendChild(tdDet);

    // inserir no topo
    if (tbody.firstChild) tbody.insertBefore(tr, tbody.firstChild); else tbody.appendChild(tr);
}
// ===== Home (mobile): cards compactos + botão "Ver mais/menos" =====
document.addEventListener('DOMContentLoaded', function () {
    const tabelaContainer = document.querySelector('.tabela_conteiner');
    if (!tabelaContainer) return;

    const table = tabelaContainer.querySelector('table');
    if (!table) return;

    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const mq = window.matchMedia('(max-width: 700px)');

    function syncRowToggle(row, isMobile) {
        const existingToggleCell = row.querySelector('td.mobile-toggle-cell');

        if (!isMobile) {
            row.classList.remove('is-expanded');
            if (existingToggleCell) existingToggleCell.remove();
            return;
        }

        if (existingToggleCell) return;

        const toggleCell = document.createElement('td');
        toggleCell.className = 'mobile-toggle-cell';

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'mobile-row-toggle';
        btn.textContent = 'Ver mais';
        btn.setAttribute('aria-expanded', 'false');

        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            const expanded = row.classList.toggle('is-expanded');
            btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            btn.textContent = expanded ? 'Ver menos' : 'Ver mais';
        });

        toggleCell.appendChild(btn);
        row.appendChild(toggleCell);
    }

    function syncAll() {
        const isMobile = mq.matches;
        const rows = Array.from(tbody.querySelectorAll('tr'));
        for (const row of rows) {
            syncRowToggle(row, isMobile);
        }
    }

    syncAll();

    if (mq.addEventListener) {
        mq.addEventListener('change', syncAll);
    } else if (mq.addListener) {
        mq.addListener(syncAll);
    }

    if (window.MutationObserver) {
        const obs = new MutationObserver(function () {
            // se novas linhas forem inseridas (ex.: via JS), garantir o toggle
            if (mq.matches) syncAll();
        });
        obs.observe(tbody, { childList: true });
    }
});

