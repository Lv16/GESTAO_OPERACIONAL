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

// Função para abrir o link de logística
function abrirLinkLogistica() {
    const inputLogistica = document.getElementById('edit_logistica');
    if (inputLogistica && inputLogistica.value) {
        window.open(inputLogistica.value, '_blank');
    } else {
        NotificationManager.showNotification('Nenhum link de logística definido', 'warning');
    }
}

// Função para abrir o link de logística da tabela
function abrirLogisticaModal(osId) {
    fetchJson(`/os/${osId}/detalhes/`)
        .then(response => {
            if (response.success && response.os && response.os.link_logistica) {
                window.open(response.os.link_logistica, '_blank');
            } else {
                NotificationManager.showNotification('Nenhum link de logística definido', 'warning');
            }
        })
        .catch(error => {
            console.error('Erro ao buscar link de logística:', error);
            NotificationManager.showNotification('Erro ao buscar link de logística', 'error');
        });
}

// Atualizar o link de logística quando o modal for aberto
function atualizarCampoLogistica(osData) {
    const inputLogistica = document.getElementById('edit_logistica');
    if (inputLogistica && osData.link_logistica) {
        inputLogistica.value = osData.link_logistica;
    }
}

// Recarrega a página ao submeter o formulário de edição do modal-edicao
document.addEventListener('DOMContentLoaded', function() {
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
    "acompanhamento de flushing ou transferência", "armazenamento temporário", "carreta de armazenamento temporário", "certificação gas fire", "certificação gas free", "coleta e análise da água", "coleta e análise do ar", "descarte de resíduos", "descomissionamento", "descontaminação profunda na embarcação", "desmobilização de equipamentos", "desmobilização de pessoas", "desmobilização de pessoas e equipamentos", "desobstrução", "desobstrução da linha de drenagem aberta", "diária da equipe de limpeza de tanques", "diária de ajudante operacional", "diária de consumíveis para limpeza", "diária de consumíveis para pintura", "diária de resgatista", "diária de supervisor", "diária do técnico de segurança do trabalho", "elaboração do pmoc", "emissão de free for fire", "ensacamento e remoção", "equipamentos em stand by", "equipe em stand by", "esgotamento de resíduo", "fornecimento de almoxarife", "fornecimento de auxiliar offshore", "fornecimento de caminhão vácuo", "fornecimento de carreta tanque", "fornecimento de eletricista", "fornecimento de engenheiro químico", "fornecimento de equipamentos e consumíveis", "fornecimento de equipe de alpinista industrial", "fornecimento de equipe de resgate", "fornecimento de irata n1 ou n2", "fornecimento de irata n3", "fornecimento de mão de obra operacional", "fornecimento de materiais", "fornecimento de mecânico", "fornecimento de químicos", "fornecimento de técnico offshore", "hotel, alimentação e transfer por paxinspeção por boroscópio", "inventário", "lista de verificação e planejamento dos materiais a bordo", "limpeza (dutos + coifa + coleta e análise de ar + lavanderia)", "limpeza (dutos + coifa + coleta e análise de ar)", "limpeza (dutos + coifa)", "limpeza da casa de bombas", "limpeza de área do piso de praça", "limpeza de coifa", "limpeza de coifa de cozinha", "limpeza de compartimentos void e cofferdans", "limpeza de dutos", "limpeza de dutos da lavanderia", "limpeza de dutos de ar condicionado", "limpeza de exaustor de cozinha", "limpeza de lavanderia", "limpeza de silos", "limpeza de vaso", "limpeza e descontaminação de carreta", "limpeza geral na embarcação", "limpeza, tratamento e pintura", "locação de equipamentos", "medição de espessura", "mobilização de equipamentos", "mobilização de pessoas", "mobilização de pessoas e equipamentos", "mobilização/desmobilização de carreta tanque", "pintura", "radioproteção norm", "renovação do pmoc", "segregação", "sinalização e isolamento de rejeitos", "serviço de irata", "shut down", "survey para avaliação de atividade", "taxa diária de auxiliar à disposição", "taxa diária de supervisor/operador à disposição", "taxa mensal de equipe onshore", "vigia"
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

        function addTag(value) {
            value = (value || '').trim();
            if (!value) return;
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

        // expor um método para adicionar tag programaticamente
        container.addTag = function(value) { addTag(value); };

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
            if (e.key === 'Enter' || e.key === '+' ) {
                e.preventDefault();
                const val = input.value.trim();
                if (val) addTag(val);
                input.value = '';
            }
        });

        // Allow selecting from datalist by blurring
        input.addEventListener('blur', function() {
            const val = input.value.trim();
            if (val) {
                addTag(val);
                input.value = '';
            }
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
            parts.forEach(p => addTag(p));
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
            const opts = Array.from(datalist.options || []).
                map(o => (o.value || o.textContent || '').trim()).
                filter(v => v);
            const f = (filter || '').toLowerCase().trim();
            return opts.filter(v => !f || v.toLowerCase().indexOf(f) !== -1);
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
                item.addEventListener('click', function(e) {
                    e.preventDefault();
                    // tentar adicionar a tag diretamente no container associado ao input
                    try {
                        const containerId = inputId.replace('_input', '_tags_container');
                        const cont = document.getElementById(containerId);
                        if (cont && typeof cont.addTag === 'function') {
                            cont.addTag(text);
                        } else {
                            // fallback: set input value and blur (antigo comportamento)
                            input.value = text;
                            setTimeout(() => { input.blur(); }, 10);
                        }
                    } catch (ex) {
                        try { input.value = text; setTimeout(() => { input.blur(); }, 10); } catch(e){}
                    }
                    hideDropdown();
                });
                dropdown.appendChild(item);
            });

            document.body.appendChild(dropdown);
            positionDropdown();

            // remover temporariamente o atributo 'list' para evitar o dropdown nativo do navegador
            try {
                if (input.hasAttribute('list')) input.removeAttribute('list');
            } catch (e) {}

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
            // restaurar o atributo 'list' original
            try {
                if (originalList) input.setAttribute('list', originalList);
            } catch (e) {}
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
document.getElementById("form-os").addEventListener("submit", async function(e) {
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
                    // Se o backend retornou os dados da OS criada, injetar na tabela
                    if (payload.os) {
                        try {
                            const os = payload.os;
                            console.debug('OS criado (payload):', payload);
                            // dispatch event para permitir hooks externos
                            try {
                                const ev = new CustomEvent('os:created', { detail: os });
                                window.dispatchEvent(ev);
                            } catch(e) { console.debug('dispatch os:created falhou', e); }
                            const tbody = document.querySelector('.tabela_conteiner table tbody');
                            if (tbody) {
                                const tr = document.createElement('tr');
                                    tr.setAttribute('data-cliente', os.cliente || '');
                                    tr.setAttribute('data-unidade', os.unidade || '');
                                    tr.setAttribute('data-status', (os.status_operacao || '').toString().toLowerCase());
                                tr.innerHTML = `
                                    <td>${os.id || ''}</td>
                                    <td>${os.numero_os || ''}</td>
                                    <td>${os.data_inicio || ''}</td>
                                    <td>${os.data_fim || ''}</td>
                                    <td>${os.data_inicio_frente || ''}</td>
                                    <td>${os.data_fim_frente || ''}</td>
                                    <td>${os.dias_de_operacao_frente || ''}</td>
                                    <td>${os.cliente || ''}</td>
                                    <td>${os.unidade || ''}</td>
                                    <td>${os.solicitante || ''}</td>
                                    <td>${os.tipo_operacao || ''}</td>
                                    ${buildServiceCell(os)}
                                    ${buildTankCell(os)}
                                    <td>${os.volume_tanque || ''}</td>
                                    <td>${os.especificacao || ''}</td>
                                    <td>${os.metodo || ''}</td>
                                    <td>${os.po || ''}</td>
                                    <td>${os.material || ''}</td>
                                    <td>${os.pob || ''}</td>
                                    <td>${os.dias_de_operacao || ''}</td>
                                    <td>${os.coordenador || ''}</td>
                                    <td>${os.supervisor || ''}</td>
                                    <td>${os.status_operacao || ''}</td>
                                    <td>${os.status_geral || ''}</td>
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
                                // inserir no topo
                                if (tbody.firstChild) tbody.insertBefore(tr, tbody.firstChild);
                                else tbody.appendChild(tr);
                                // anexar listeners aos botões recém-criados (fallback caso handlers iniciais não cubram novos elementos)
                                try {
                                    // botão detalhes
                                    var btnDet = tr.querySelector('#btn_detalhes_' + (os.id || ''));
                                    if (btnDet) {
                                        btnDet.addEventListener('click', function(ev){ ev.preventDefault && ev.preventDefault(); abrirDetalhesModal(String(os.id)); });
                                    }
                                    // botão editar
                                    var btnEdit = tr.querySelector('.btn-editar');
                                    if (btnEdit) {
                                        btnEdit.addEventListener('click', function(ev){ ev.preventDefault && ev.preventDefault(); abrirModalEdicao(String(os.id)); });
                                    }
                                } catch(e) { console.debug('anexar listeners falhou', e); }
                                // efeito visual
                                try { addNewRowEffect(tr); } catch(e){}
                                console.debug('Linha da OS injetada na tabela (id):', os.id);
                            }
                        } catch(e) {
                            console.warn('Falha ao injetar linha da OS criada:', e);
                            setTimeout(() => window.location.reload(), 1500);
                        }
                    } else {
                        setTimeout(() => window.location.reload(), 1500);
                    }
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
    

window.addEventListener("load", calcularDiasOperacao);

const detalhesModal = document.getElementById("detalhes_os");

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
            // preencher lista completa de serviços (usar único campo 'servicos_full')
            (function preencherServicos() {
                var container = document.getElementById('servicos_full');
                var valor = os.servicos || os.servico || '';
                if (container) {
                    // Limpa conteúdo anterior
                    container.innerHTML = '';
                    if (!valor) { container.textContent = ''; return; }
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

filtroIcon.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation(); 
    dropdown.style.display = dropdown.style.display === "flex" ? "none" : "flex";
});

document.addEventListener("click", (e) => {
    if (!dropdown.contains(e.target) && e.target !== filtroIcon) {
        dropdown.style.display = "none";
    }
});

document.querySelectorAll(".opcao-filtro").forEach(opcao => {
    opcao.addEventListener("click", function () {
        const statusSelecionado = this.getAttribute("data-status").toLowerCase();
        filtrarPorStatus(statusSelecionado);
        dropdown.style.display = "none";
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
    filterPanel.classList.toggle("visible");
    
    
    const toggleButton = document.querySelector(".filter-toggle");
    if (filterPanel.classList.contains("visible")) {
        toggleButton.textContent = "Ocultar Filtros";
    } else {
        toggleButton.textContent = "Mostrar Filtros";
    }
}

// Evento para o botão de alternar filtros
document.addEventListener('click', function(event) {
    const filterPanel = document.getElementById("campos-filtro");
    const toggleButton = document.querySelector(".filter-toggle");
    
    if (filterPanel.classList.contains("visible") && 
        !filterPanel.contains(event.target) && 
        event.target !== toggleButton) {
        filterPanel.classList.remove("visible");
        toggleButton.textContent = "Mostrar Filtros";
    }
});

document.querySelector('.filter-panel').addEventListener('click', function(event) {
    event.stopPropagation();
});

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
    setValue('edit_solicitante', os.solicitante);
    setValue('edit_servico', os.servico);
    setValue('edit_metodo', os.metodo);
    setValue('edit_metodo_secundario', os.metodo_secundario);
    setValue('edit_tanque', os.tanque);
    setValue('edit_volume_tanque', os.volume_tanque);
    // preencher PO e material no formulário de edição
    setValue('edit_po', os.po);
    setValue('edit_material', os.material);
    setValue('edit_especificacao', os.especificacao);
    setValue('edit_tipo_operacao', os.tipo_operacao);
    setValue('edit_status_operacao', os.status_operacao);
    setValue('edit_status_geral', os.status_geral);
    setValue('edit_status_comercial', os.status_comercial);
    setValue('edit_data_inicio', os.data_inicio);
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
            try { console.debug('About to build tanques UI:', 'os.tanques=', os && os.tanques, 'os.tanque=', os && os.tanque, 'containerExists=', !!cont, 'hiddenExists=', !!hidden); } catch(e) {}
            if (cont) {
                const csv = (os && (os.tanques || os.tanque)) ? String(os.tanques || os.tanque) : '';
                if (hidden) hidden.value = csv; // redundante, mas mantém sincronizado
                const items = csv ? csv.split(',').map(s => s.trim()).filter(Boolean) : [];
                cont.innerHTML = '';
                items.forEach(t => {
                    const row = document.createElement('div');
                    row.className = 'tanque-row';
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.className = 'form-control tanque-input';
                    input.setAttribute('data-role','edit-tanque');
                    input.value = t;
                    input.addEventListener('input', function(){
                        try {
                            const vals = Array.from(cont.querySelectorAll('input[data-role="edit-tanque"]')).map(i=> (i.value||'').trim()).filter(Boolean);
                            if (hidden) hidden.value = vals.join(', ');
                        } catch(e){}
                    });
                    row.appendChild(input);
                    cont.appendChild(row);
                });
            }
        } catch(e) { console.debug('inline tanques UI build failed', e); }
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
                                    tr.innerHTML = `
                                        <td>${os.id || ''}</td>
                                        <td>${os.numero_os || ''}</td>
                                        <td>${os.data_inicio || ''}</td>
                                        <td>${os.data_fim || ''}</td>
                                        <td>${os.data_inicio_frente || ''}</td>
                                        <td>${os.data_fim_frente || ''}</td>
                                        <td>${os.dias_de_operacao_frente || ''}</td>
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
                                        <td>${os.status_operacao || ''}</td>
                                        <td>${os.status_geral || ''}</td>
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

// Validação client-side para o link de logística (movido do template)
(function(){
    function qs(sel, ctx){ return (ctx||document).querySelector(sel); }
    function qsa(sel, ctx){ return Array.from((ctx||document).querySelectorAll(sel)); }

    document.addEventListener('DOMContentLoaded', function(){
        var form = qs('#form-edicao');
        if (!form) return;

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
            err.textContent = msg || 'URL inválida';
            var uid = 'err-logistica-'+Date.now();
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

        // Normaliza e valida URL ao sair do campo
        var inputLog = document.getElementById('edit_logistica');
        if (inputLog) {
            inputLog.value = os.link_logistica || '';
            updateEditLogisticaControls();
            // atualiza enquanto usuário digita
            inputLog.removeEventListener('input', updateEditLogisticaControls);
            inputLog.addEventListener('input', updateEditLogisticaControls);
        }

        form.addEventListener('submit', function(ev){
            try{
                var val = (inputLog.value || '').trim();
                clearInlineError(inputLog);
                if (!val){
                    ev.preventDefault();
                    ev.stopPropagation();
                    showInlineError(inputLog, 'Informe o link de logística ou desmarque a opção de logística.');
                    try{ inputLog.focus(); }catch(e){}
                    return false;
                }else{
                    // validação mínima: deve começar com http:// ou https://
                    if (!/^https?:\/\//i.test(val)){
                        ev.preventDefault();
                        ev.stopPropagation();
                        showInlineError(inputLog, 'O link de logística deve começar com "http://" ou "https://".');
                        try{ inputLog.focus(); }catch(e){}
                        return false;
                    }
                }
            }catch(e){}
        }, false);
    });
})();

// (Wrapper removed) lógica de pré-população de link de logística foi integrada diretamente em abrirModalEdicao

