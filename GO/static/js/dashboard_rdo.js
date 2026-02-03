// Variáveis globais para os gráficos
let charts = {};

// Global small overlay usado no modo TV / auto-refresh para indicar atualização sutil
function ensureGlobalOverlay(){
    if(document.getElementById('global-update-overlay')) return document.getElementById('global-update-overlay');
    const el = document.createElement('div');
    el.id = 'global-update-overlay';
    el.style.position = 'fixed';
    el.style.right = '18px';
    el.style.top = '12px';
    el.style.zIndex = 2147483646;
    el.style.padding = '8px 12px';
    el.style.borderRadius = '8px';
    el.style.display = 'none';
    el.style.alignItems = 'center';
    el.style.gap = '8px';
    el.style.fontFamily = 'Inter, system-ui, -apple-system, "Segoe UI", Roboto';
    el.style.fontWeight = '700';
    el.style.fontSize = '14px';
    // adaptive color based on theme
    const isDark = document.body && document.body.classList && document.body.classList.contains('dark-mode');
    if(isDark){
        el.style.background = 'rgba(0,0,0,0.6)';
        el.style.color = '#fff';
    } else {
        el.style.background = 'rgba(255,255,255,0.92)';
        el.style.color = '#0b0b0b';
        el.style.boxShadow = '0 6px 18px rgba(2,6,23,0.12)';
    }

    // spinner
    const spinner = document.createElement('span');
    spinner.style.width = '12px';
    spinner.style.height = '12px';
    spinner.style.border = '2px solid rgba(0,0,0,0.15)';
    spinner.style.borderTop = isDark ? '2px solid #fff' : '2px solid #1B7A4B';
    spinner.style.borderRadius = '50%';
    spinner.style.display = 'inline-block';
    spinner.style.animation = 'global-spin 900ms linear infinite';
    // text
    const txt = document.createElement('span');
    txt.id = 'global-update-overlay-text';
    txt.textContent = 'Atualizando...';

    // last-updated small text (invisible until set)
    const last = document.createElement('div');
    last.id = 'global-update-last';
    last.style.fontSize = '12px';
    last.style.fontWeight = '600';
    last.style.opacity = '0.85';
    last.style.marginLeft = '8px';
    last.style.display = 'none';
    last.textContent = '';

    el.appendChild(spinner);
    el.appendChild(txt);
    el.appendChild(last);
    document.body.appendChild(el);

    // keyframes (inject once)
    if(!document.getElementById('global-update-overlay-style')){
        const style = document.createElement('style');
        style.id = 'global-update-overlay-style';
        style.textContent = `@keyframes global-spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`; 
        document.head.appendChild(style);
    }
    return el;
}

function showGlobalUpdating(show, message){
    try{
        const el = ensureGlobalOverlay();
        if(!el) return;
        const txt = document.getElementById('global-update-overlay-text');
        const spinner = el.querySelector('span');
        const last = document.getElementById('global-update-last');
        if(message && txt) txt.textContent = message;
        if(show){
            // mostrar estado de loading: spinner + mensagem
            if(spinner) spinner.style.display = 'inline-block';
            if(txt) txt.style.display = 'inline-block';
            if(last) last.style.display = 'none';
            el.style.display = 'flex';
        } else {
            // ao terminar, mostrar timestamp breve (ou permanentemente em TV-mode)
            if(spinner) spinner.style.display = 'none';
            if(txt) txt.style.display = 'none';
            // atualizar last-updated (se message for Date string, usá-la)
            const d = (message instanceof Date) ? message : (message ? new Date(message) : new Date());
            if(last){
                try{
                    const fmt = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    last.textContent = 'Última: ' + fmt;
                    last.style.display = 'block';
                }catch(e){ last.textContent = ''; last.style.display = 'none'; }
            }
            // se estiver em modo TV, manter o badge visível; caso contrário, ocultar após 4s
            const keep = document.body && document.body.classList && document.body.classList.contains('tv-mode');
            if(keep){ el.style.display = 'flex'; }
            else { setTimeout(()=>{ try{ el.style.display = 'none'; }catch(e){} }, 4000); }
        }
    }catch(e){ console.debug('showGlobalUpdating error', e); }
}

// Escapa texto para uso em atributos/title (evita injeção acidental de HTML)
function escapeHtml(str){
    if(str === null || str === undefined) return '';
    return String(str).replace(/[&"'<>]/g, function(s){
        return ({'&':'&amp;','"':'&quot;',"'":'&#39;','<':'&lt;','>':'&gt;'}[s]);
    });
}

/**
 * Coleta os valores dos filtros
 */
function getFilters() {
    // normalize multi-value inputs: accept separators ',' or ';' and return as single comma-separated string
    function norm(val){
        if(val === null || val === undefined) return '';
        val = String(val).trim();
        if(!val) return '';
        // split on commas or semicolons, trim tokens and rejoin with comma
        const parts = val.split(/[;,]+/).map(s => s.trim()).filter(s => s);
        return parts.join(',');
    }

    return {
        start: norm(document.getElementById('filter_data_inicio').value),
        end: norm(document.getElementById('filter_data_fim').value),
        supervisor: norm(document.getElementById('filter_supervisor') ? document.getElementById('filter_supervisor').value : ''),
        cliente: norm(document.getElementById('filter_cliente') ? document.getElementById('filter_cliente').value : ''),
        unidade: norm(document.getElementById('filter_unidade') ? document.getElementById('filter_unidade').value : ''),
        coordenador: norm(document.getElementById('filter_coordenador') ? document.getElementById('filter_coordenador').value : ''),
        group: (document.getElementById('filter_group_by') ? document.getElementById('filter_group_by').value : 'day'),
        tanque: norm(document.getElementById('filter_tanque') ? document.getElementById('filter_tanque').value : ''),
        status: norm(document.getElementById('filter_status') ? document.getElementById('filter_status').value : ''),
        os_existente: norm(document.getElementById('os_existente_input') ? document.getElementById('os_existente_input').value : '')
    };
}

function exportSummaryToExcel() {
    if (!window.XLSX || !window.XLSX.utils) {
        showNotification('Exportacao para Excel indisponivel no momento.', 'error');
        return;
    }

    const items = Array.isArray(window.__summary_ops_items) ? window.__summary_ops_items : [];
    if (!items.length) {
        showNotification('Nenhum dado encontrado para exportar.', 'warning');
        return;
    }

    const headers = [
        'OS',
        'Supervisor',
        'Cliente',
        'Unidade',
        'POB',
        'Operadores',
        'HH Nao Efetivo',
        'HH Efetivo',
        'Sacos',
        'Tambores'
    ];

    const dataRows = items.map((it) => ([
        String(it.numero_os || ''),
        String(it.supervisor || ''),
        String(it.cliente || ''),
        String(it.unidade || ''),
        Number(it.avg_pob || 0),
        Number(it.sum_operadores_simultaneos || 0),
        Number(it.sum_hh_nao_efetivo || 0),
        Number(it.sum_hh_efetivo || 0),
        Number(it.total_ensacamento || 0),
        Number(it.total_tambores || 0)
    ]));

    const sheet = window.XLSX.utils.aoa_to_sheet([headers, ...dataRows]);
    sheet['!cols'] = [
        { wch: 12 }, { wch: 24 }, { wch: 24 }, { wch: 20 }, { wch: 10 },
        { wch: 12 }, { wch: 16 }, { wch: 12 }, { wch: 12 }, { wch: 12 }
    ];

    const filters = getFilters();
    const filterRows = [
        ['Filtro', 'Valor'],
        ['Data Inicio', filters.start || ''],
        ['Data Fim', filters.end || ''],
        ['Supervisor', filters.supervisor || ''],
        ['Cliente', filters.cliente || ''],
        ['Unidade', filters.unidade || ''],
        ['Coordenador', filters.coordenador || ''],
        ['Tanque', filters.tanque || ''],
        ['Status', filters.status || ''],
        ['OS', filters.os_existente || '']
    ];
    const filterSheet = window.XLSX.utils.aoa_to_sheet(filterRows);
    filterSheet['!cols'] = [{ wch: 16 }, { wch: 40 }];

    const workbook = window.XLSX.utils.book_new();
    window.XLSX.utils.book_append_sheet(workbook, sheet, 'Resumo Operacoes');
    window.XLSX.utils.book_append_sheet(workbook, filterSheet, 'Filtros');

    const now = new Date();
    const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
    window.XLSX.writeFile(workbook, `dashboard_rdo_resumo_${stamp}.xlsx`);
}

/**
 * Recarrega todos os gráficos
 */
async function loadDashboard() {
    const filters = getFilters();
    
    // Mostrar loading em todos os cards
    document.querySelectorAll('.chart-card').forEach(card => {
        card.classList.add('loading');
    });
        // Mostrar overlay sutil em modo TV ou quando auto-refresh estiver ativo
    try{
        const shouldShowGlobal = (document.body && document.body.classList && document.body.classList.contains('tv-mode')) || (typeof getAutoRefreshSeconds === 'function' && getAutoRefreshSeconds() > 0);
        if(shouldShowGlobal) showGlobalUpdating(true, 'Atualizando...');
    }catch(e){ /* ignore */ }
    
    try {
        // Carregar todos os gráficos em paralelo e coletar os retornos para atualizar KPIs
        const results = await Promise.all([
            loadChartHHConfinado(filters),
            loadChartHHForaConfinado(filters),
            loadChartEnsacamento(filters),
            loadChartTambores(filters),
            loadChartResidLiquido(filters),
            loadChartResidSolido(filters),
            loadChartLiquidoSupervisor(filters),
            loadChartSolidoSupervisor(filters),
            loadChartVolumeTanque(filters),
            loadChartPobComparativo(filters),
                loadChartTopSupervisores(filters),
                    loadChartTempoBomba(filters),
                    loadOsStatusSummary(filters),
                        loadOsMovimentacoes(filters),
                        loadSummaryOperations(filters)
        ]);
        // Atualiza KPIs com os dados coletados
        try {
            updateKPIs(results);
        } catch(e) {
            console.warn('Falha ao atualizar KPIs:', e);
        }
    } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
        showNotification('Erro ao carregar dados do dashboard', 'error');
    } finally {
        // Remover loading de todos os cards
        document.querySelectorAll('.chart-card').forEach(card => {
            card.classList.remove('loading');
        });
        // esconder overlay global se estiver visível
        try{ showGlobalUpdating(false); }catch(e){}
    }
}

/**
 * Busca resumo de status de OS e atualiza os KPIs no template.
 */
async function loadOsStatusSummary(filters){
    try{
        try{ console.debug('loadOsStatusSummary: sending filters', filters); }catch(e){}
        const resp = await fetchChartData('/rdo/os_status_summary', filters);
        try{ console.debug('loadOsStatusSummary: received resp', resp); }catch(e){}
        if(!resp || !resp.success){
            console.warn('loadOsStatusSummary: resposta sem sucesso', resp);
            return { key: 'os_status_summary', data: resp || { success: false } };
        }
        const total = Number(resp.total || 0);
        const programada = Number(resp.programada || 0);
        const em_andamento = Number(resp.em_andamento || 0);
        const paralizada = Number(resp.paralizada || 0);
        const finalizada = Number(resp.finalizada || 0);
        const cancelada = Number(resp.cancelada || 0);

        const elTotal = document.getElementById('os_total_value');
        const elProg = document.getElementById('os_programada_value');
        const elAnd = document.getElementById('os_em_andamento_value');
        const elPar = document.getElementById('os_paralizada_value');
        const elFin = document.getElementById('os_finalizada_value');
        const elCan = document.getElementById('os_cancelada_value');

        // Prevenir sobrescrever valores renderizados pelo servidor com zeros
        // quando não há filtros de data aplicados (comportamento observado em atualizações rápidas).
        // Se a UI já mostra um total > 0 e o servidor retornou 0 sem filtros, mantemos o valor atual.
        try {
            const hasDateFilter = (filters && (filters.start || filters.end));
            const hasClientOrUnit = (filters && (filters.cliente || filters.unidade));
            const currentTotalText = elTotal ? elTotal.textContent.trim() : '';
            const currentTotalNum = currentTotalText ? Number(currentTotalText.replace(/\./g,'').replace(/,/g,'.')) : 0;
            // Only skip replacing server-rendered KPIs when there is no date filter
            // AND no client/unidade filter. If the user filtered by cliente or
            // unidade, we should update the KPI cards to reflect that scope.
            const shouldSkipReplace = (!hasDateFilter && !hasClientOrUnit && currentTotalNum > 0 && total === 0);
            if(!shouldSkipReplace){
                if(elTotal) elTotal.textContent = Intl.NumberFormat('pt-BR').format(total);
                if(elProg) elProg.textContent = Intl.NumberFormat('pt-BR').format(programada);
                if(elAnd) elAnd.textContent = Intl.NumberFormat('pt-BR').format(em_andamento);
                if(elPar) elPar.textContent = Intl.NumberFormat('pt-BR').format(paralizada);
                if(elFin) elFin.textContent = Intl.NumberFormat('pt-BR').format(finalizada);
                if(elCan) elCan.textContent = Intl.NumberFormat('pt-BR').format(cancelada);
            } else {
                // Logar em console para facilitar diagnóstico em caso de discrepância
                console.debug('loadOsStatusSummary: pulando substituição por resposta vazia (sem filtros)', { currentTotalNum, resp });
            }
        } catch(e){
            // fallback seguro: escrever valores mesmo se ocorrer erro na checagem
            if(elTotal) elTotal.textContent = Intl.NumberFormat('pt-BR').format(total);
            if(elProg) elProg.textContent = Intl.NumberFormat('pt-BR').format(programada);
            if(elAnd) elAnd.textContent = Intl.NumberFormat('pt-BR').format(em_andamento);
            if(elPar) elPar.textContent = Intl.NumberFormat('pt-BR').format(paralizada);
            if(elFin) elFin.textContent = Intl.NumberFormat('pt-BR').format(finalizada);
            if(elCan) elCan.textContent = Intl.NumberFormat('pt-BR').format(cancelada);
        }

        // pequena animação de destaque (fade-in)
        [elTotal, elProg, elAnd, elPar, elFin, elCan].forEach(el => {
            if(!el) return;
            el.style.transition = 'transform 220ms ease, opacity 220ms ease';
            el.style.transform = 'translateY(-6px)';
            el.style.opacity = '0.85';
            setTimeout(()=>{ try{ el.style.transform = ''; el.style.opacity = '1'; }catch(e){} }, 240);
        });

            // Debug: logar filtros e resposta para diagnóstico
            try{ console.debug('loadOsStatusSummary: filters=', filters, 'resp=', resp); }catch(e){}

            // Render lists per status if present
            try{
                const showLists = !!(filters && (filters.cliente || filters.unidade || filters.status));
                function renderStatusList(listId, items){
                    const el = document.getElementById(listId);
                    if(!el) return;
                    if(!showLists){ el.innerHTML = ''; el.style.display = 'none'; return; }
                    if(!items || !items.length){ el.innerHTML = ''; el.style.display = 'none'; return; }
                    // Mapear listId para rótulo de status a ser exibido
                    const statusLabels = {
                        'os_programada_list': 'Programada',
                        'os_em_andamento_list': 'Em Andamento',
                        'os_paralizada_list': 'Paralizada',
                        'os_finalizada_list': 'Finalizada',
                        'os_cancelada_list': 'Cancelada'
                    };
                    const label = statusLabels[listId] || '';
                    // Mostrar até 6 itens no formato: 10029 - Em Andamento
                    const top = items.slice(0,6);
                    el.innerHTML = top.map(it => `<div>${escapeHtml(String(it.numero_os))} - ${escapeHtml(label)}</div>`).join('');
                    el.style.display = 'block';
                }
                renderStatusList('os_programada_list', resp.programada_items || []);
                renderStatusList('os_em_andamento_list', resp.em_andamento_items || []);
                renderStatusList('os_paralizada_list', resp.paralizada_items || []);
                renderStatusList('os_finalizada_list', resp.finalizada_items || []);
                renderStatusList('os_cancelada_list', resp.cancelada_items || []);
            }catch(e){ console.debug('Erro ao renderizar listas por status', e); }

            return { key: 'os_status_summary', data: resp };

    }catch(e){
        console.debug('Erro ao buscar resumo OS:', e);
    }
}

/**
 * Carrega contagem de movimentações por OS quando filtrado por cliente e/ou unidade.
 * Retorna um objeto { key: 'os_movimentacoes', data: items }
 */
async function loadOsMovimentacoes(filters){
    try{
        // Mostrar apenas se cliente ou unidade estiverem preenchidos
        if(!(filters && (filters.cliente || filters.unidade))){
            // esconder card caso esteja visível
            const card = document.getElementById('kpi_movimentacoes_card');
            if(card) card.style.display = 'none';
            return { key: 'os_movimentacoes', data: [] };
        }

        const resp = await fetchChartData('/rdo/api/get_os_movimentacoes_count/', filters);
        if(!resp || !resp.success) {
            console.warn('Falha ao carregar movimentações por OS', resp);
            return { key: 'os_movimentacoes', data: [] };
        }

        const items = resp.items || [];

        // Atualizar card na UI
        const card = document.getElementById('kpi_movimentacoes_card');
        const valEl = document.getElementById('kpi_movimentacoes_value');
        const listEl = document.getElementById('kpi_movimentacoes_list');
        const subEl = document.getElementById('kpi_movimentacoes_sub');
        if(card) card.style.display = 'block';
        if(valEl) valEl.textContent = items.length ? items.length + ' OS' : '0 OS';
        if(subEl) subEl.textContent = items.length ? '' : 'Nenhuma movimentação encontrada';

        if(listEl){
            if(!items.length){
                listEl.innerHTML = '';
            } else {
                // Mostrar até 6 primeiras OS com formato: 6019 - 2 movimentações
                const top = items.slice(0,6);
                listEl.innerHTML = top.map(it => `<div>${escapeHtml(String(it.numero_os))} - ${Number(it.count)} movimenta\u00e7\u00f5es</div>`).join('');
                if(items.length > 6) listEl.innerHTML += `<div style="margin-top:6px;color:var(--muted)">+ ${items.length-6} mais...</div>`;
            }
        }

        return { key: 'os_movimentacoes', data: items };
    }catch(e){
        console.error('Erro em loadOsMovimentacoes', e);
        return { key: 'os_movimentacoes', data: [] };
    }
}

/**
 * Carrega e renderiza a tabela "Resumo das Operações" usando o endpoint
 * `/api/rdo-dashboard/summary_operations/`. Realiza paginação simples no
 * cliente (10 linhas por página) para evitar sobrecarregar o DOM.
 */
async function loadSummaryOperations(filters){
    try{
        // Se o usuário estiver filtrando por status, não aplicar o filtro de
        // datas na requisição de resumo das operações para garantir que OS
        // com o `status_operacao` solicitado apareçam mesmo sem RDOs na
        // janela de datas selecionada.
        const reqFilters = Object.assign({}, filters || {});
        if(reqFilters.status){ reqFilters.start = ''; reqFilters.end = ''; }
        const resp = await fetchChartData('/api/rdo-dashboard/summary_operations/', reqFilters);
        if(!resp || !resp.success){
            console.warn('Falha ao obter resumo das operações', resp);
            renderSummaryTable([]);
            return { key: 'summary_operations', data: [] };
        }

        const items = Array.isArray(resp.items) ? resp.items : [];
        // armazenar itens em closure para paginação
        try{ window.__summary_ops_items = items; }catch(e){}
        // renderizar de acordo com preferência do usuário (table ou cards)
        try{
            if(getSummaryViewMode && getSummaryViewMode() === 'cards') renderSummaryCardsPage(1);
            else renderSummaryTablePage(1);
        }catch(e){ renderSummaryTablePage(1); }
        return { key: 'summary_operations', data: items };
    }catch(e){
        console.error('Erro em loadSummaryOperations', e);
        renderSummaryTable([]);
        return { key: 'summary_operations', data: [] };
    }
}

function renderSummaryTable(items){
    const tbody = document.getElementById('summary-table-body');
    const info = document.getElementById('summary_paging_info');
    const controls = document.getElementById('summary_paging_controls');
    if(!tbody) return;
    tbody.innerHTML = '';
    if(!items || !items.length){
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:18px;color:#aaa;font-size:15px;">Nenhuma operação encontrada</td></tr>';
        if(info) info.textContent = '';
        if(controls) controls.innerHTML = '';
        return;
    }

    // renderizar todas as linhas (usado quando paginação externa não aplicada)
    const rows = items.map(it => {
        const numero = escapeHtml(String(it.numero_os || ''));
        const sup = escapeHtml(String(it.supervisor || ''));
        const cli = escapeHtml(String(it.cliente || ''));
        const uni = escapeHtml(String(it.unidade || ''));
        const pob = Intl.NumberFormat('pt-BR').format(Number(it.avg_pob || 0));
        const ops = Intl.NumberFormat('pt-BR').format(Number(it.sum_operadores_simultaneos || 0));
        const hhNao = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_nao_efetivo || 0));
        const hh = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_efetivo || 0));
        const sacos = Intl.NumberFormat('pt-BR').format(Number(it.total_ensacamento || 0));
        const tambores = Intl.NumberFormat('pt-BR').format(Number(it.total_tambores || 0));
        return `<tr>
            <td class="col-os" style="padding:8px">${numero}</td>
            <td class="col-supervisor" style="padding:8px">${sup}</td>
            <td class="col-cliente" style="padding:8px">${cli}</td>
            <td class="col-unidade" style="padding:8px">${uni}</td>
            <td class="col-pob" style="padding:8px;text-align:right">${pob}</td>
            <td class="col-op" style="padding:8px;text-align:right">${ops}</td>
            <td class="col-hh-nao" style="padding:8px;text-align:right">${hhNao}</td>
            <td class="col-hh" style="padding:8px;text-align:right">${hh}</td>
            <td class="col-sacos" style="padding:8px;text-align:right">${sacos}</td>
            <td class="col-tambores" style="padding:8px;text-align:right">${tambores}</td>
        </tr>`;
    }).join('');
    tbody.innerHTML = rows;
    if(info) info.textContent = `Mostrando ${items.length} registro(s)`;
    if(controls) controls.innerHTML = '';
}

function renderSummaryTablePage(page){
    const pageSize = 10;
    const items = (window.__summary_ops_items && Array.isArray(window.__summary_ops_items)) ? window.__summary_ops_items : [];
    const tbody = document.getElementById('summary-table-body');
    const info = document.getElementById('summary_paging_info');
    const controls = document.getElementById('summary_paging_controls');
    if(!tbody) return;
    if(!items.length){ renderSummaryTable([]); return; }

    const total = items.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const current = Math.min(Math.max(1, page || 1), totalPages);
    const start = (current - 1) * pageSize;
    const slice = items.slice(start, start + pageSize);

    // preencher body com slice
    const rows = slice.map(it => {
        const numero = escapeHtml(String(it.numero_os || ''));
        const sup = escapeHtml(String(it.supervisor || ''));
        const cli = escapeHtml(String(it.cliente || ''));
        const uni = escapeHtml(String(it.unidade || ''));
        const pob = Intl.NumberFormat('pt-BR').format(Number(it.avg_pob || 0));
        const ops = Intl.NumberFormat('pt-BR').format(Number(it.sum_operadores_simultaneos || 0));
        const hhNao = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_nao_efetivo || 0));
        const hh = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_efetivo || 0));
        const sacos = Intl.NumberFormat('pt-BR').format(Number(it.total_ensacamento || 0));
        const tambores = Intl.NumberFormat('pt-BR').format(Number(it.total_tambores || 0));
        return `<tr>
            <td class="col-os" style="padding:8px">${numero}</td>
            <td class="col-supervisor" style="padding:8px">${sup}</td>
            <td class="col-cliente" style="padding:8px">${cli}</td>
            <td class="col-unidade" style="padding:8px">${uni}</td>
            <td class="col-pob" style="padding:8px;text-align:right">${pob}</td>
            <td class="col-op" style="padding:8px;text-align:right">${ops}</td>
            <td class="col-hh-nao" style="padding:8px;text-align:right">${hhNao}</td>
            <td class="col-hh" style="padding:8px;text-align:right">${hh}</td>
            <td class="col-sacos" style="padding:8px;text-align:right">${sacos}</td>
            <td class="col-tambores" style="padding:8px;text-align:right">${tambores}</td>
        </tr>`;
    }).join('');
    tbody.innerHTML = rows;

    if(info) info.textContent = `Mostrando ${start+1}–${Math.min(start+slice.length, total)} de ${total}`;

    // garantir que o container de cards esteja oculto quando no modo tabela
    try{
        const container = document.getElementById('summary-cards-container');
        const tableEl = tbody ? tbody.closest('table') : null;
        if(container) container.style.display = getSummaryViewMode() === 'cards' ? '' : 'none';
        if(tableEl) tableEl.style.display = getSummaryViewMode() === 'cards' ? 'none' : '';
    }catch(e){/* ignore */}

    // montar controles simples: Prev / Next
    if(controls){
        controls.innerHTML = '';
        const prev = document.createElement('button');
        prev.className = 'btn-secondary';
        prev.textContent = '◀';
        prev.disabled = current <= 1;
        prev.addEventListener('click', () => renderSummaryTablePage(current - 1));

        const next = document.createElement('button');
        next.className = 'btn-secondary';
        next.textContent = '▶';
        next.disabled = current >= totalPages;
        next.addEventListener('click', () => renderSummaryTablePage(current + 1));

        const pageIndicator = document.createElement('span');
        pageIndicator.style.margin = '0 8px';
        pageIndicator.style.fontSize = '12px';
        pageIndicator.style.color = 'var(--muted)';
        pageIndicator.textContent = `${current}/${totalPages}`;

        controls.appendChild(prev);
        controls.appendChild(pageIndicator);
        controls.appendChild(next);

        // ensure a single toggle button exists and place it next to pagination
        let toggleBtn = document.getElementById('summary-view-toggle-btn');
        if(!toggleBtn){
            toggleBtn = document.createElement('button');
            toggleBtn.type = 'button';
            toggleBtn.id = 'summary-view-toggle-btn';
            toggleBtn.className = 'btn-secondary';
            toggleBtn.style.marginLeft = '10px';
            toggleBtn.onclick = toggleSummaryView;
        } else {
            // remove from previous parent to re-append here
            try{ toggleBtn.remove(); }catch(e){}
        }
        // atualizar rótulo de acordo com o modo atual
        if(typeof getSummaryViewMode === 'function'){
            toggleBtn.textContent = getSummaryViewMode() === 'cards' ? 'Tabela' : 'Cards';
        }
        controls.appendChild(toggleBtn);
    }
}

// --- Nova visualização em Cards para o resumo das operações ---
function ensureSummaryCardsContainer(){
    let container = document.getElementById('summary-cards-container');
    const table = document.getElementById('summary-table-body');
    if(!container){
        container = document.createElement('div');
        container.id = 'summary-cards-container';
        container.style.display = 'none';
        container.style.marginTop = '14px';
        // inserir logo após a tabela (se existir) ou no final do pai
        if(table && table.parentElement){
            const parent = table.parentElement.parentElement || table.parentElement;
            parent.insertBefore(container, table.parentElement.nextSibling);
        } else if(document.getElementById('summary-table')){
            document.getElementById('summary-table').parentElement.appendChild(container);
        } else {
            document.body.appendChild(container);
        }
    }
    return container;
}

function getSummaryViewMode(){
    try{ return localStorage.getItem('summary_view_mode') || 'table'; }catch(e){ return 'table'; }
}

function setSummaryViewMode(mode){
    try{ localStorage.setItem('summary_view_mode', mode); }catch(e){}
}

function applySummaryCardStyles(){
    if(document.getElementById('summary-cards-styles')) return;
    const css = `
    #summary-cards-container{padding:8px 6px}
    #summary-cards-container .summary-cards-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
    .summary-card{background:linear-gradient(180deg,#141614,#0b0b0b);border-radius:12px;padding:18px;color:rgba(255,255,255,0.92);box-shadow:0 8px 28px rgba(0,0,0,0.6);border:1px solid rgba(204,255,0,0.08);font-family:Inter, system-ui, -apple-system, "Segoe UI", Roboto, 'Helvetica Neue', Arial;box-sizing:border-box;min-height:260px}
    .summary-card .card-os{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:10px}
    .summary-card .card-os .os-num{display:none}
    .summary-card .card-os .os-badge{background:#1B7A4B;color:#fff;padding:6px 14px;border-radius:999px;font-weight:700;font-size:12px;min-width:140px;text-align:center}
    .summary-card .divider{height:1px;background:rgba(204,255,0,0.08);margin:12px 0;border-radius:2px}
    .summary-card .divider-top{height:1px;background:rgba(204,255,0,0.06);margin:8px 0 14px;border-radius:2px;opacity:0.9}
    .card-top-grid{display:flex;gap:18px;align-items:flex-start}
    .card-top-grid .col{flex:1;display:flex;flex-direction:column;gap:8px}
    .card-top-grid .item{display:flex;flex-direction:column}
    .card-top-grid .item strong{display:block;font-size:13px;color:rgba(255,255,255,0.72);letter-spacing:0.04em;text-transform:uppercase;font-weight:700}
    .card-top-grid .item .value{font-weight:800;color:#CCFF00;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .summary-card .kpi-row{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;align-items:center;margin-top:14px;border-top:1px solid rgba(255,255,255,0.04);padding-top:12px}
    .summary-card .kpi-row.kpi-row--two{display:flex;justify-content:center;gap:48px;max-width:380px;margin:14px auto 0}
    .summary-card .kpi-row.kpi-row--two .kpi-item{flex:0 0 140px}
    .summary-card .kpi-item{display:flex;flex-direction:column;align-items:center;justify-content:center}
    .summary-card .kpi-item .kpi-value{font-weight:900;font-size:16px;color:#CCFF00;display:block;text-align:center;min-width:44px}
    .summary-card .kpi-item .kpi-label{font-size:11px;color:rgba(255,255,255,0.6);margin-top:6px;text-align:center}
    .summary-card .small-muted{font-size:12px;color:rgba(255,255,255,0.65)}
    @media (max-width:1100px){ #summary-cards-container .summary-cards-grid{grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px} }
    @media (max-width:900px){ #summary-cards-container .summary-cards-grid{grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px} }
    @media (max-width:600px){ #summary-cards-container .summary-cards-grid{grid-template-columns:1fr} }
    `;
    const s = document.createElement('style');
    s.id = 'summary-cards-styles';
    s.appendChild(document.createTextNode(css));
    document.head.appendChild(s);
}

function renderSummaryCardsPage(page){
    const pageSize = 10;
    const items = (window.__summary_ops_items && Array.isArray(window.__summary_ops_items)) ? window.__summary_ops_items : [];
    const tableBody = document.getElementById('summary-table-body');
    const tableEl = tableBody ? tableBody.closest('table') : null;
    const container = ensureSummaryCardsContainer();
    applySummaryCardStyles();

    if(!items.length){
        // mostrar mensagem vazia
        container.innerHTML = '<div style="color:#888;padding:18px">Nenhuma operação encontrada</div>';
        if(tableEl) tableEl.style.display = '';
        container.style.display = getSummaryViewMode() === 'cards' ? '' : 'none';
        return;
    }

    const total = items.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const current = Math.min(Math.max(1, page || 1), totalPages);
    const start = (current - 1) * pageSize;
    const slice = items.slice(start, start + pageSize);

    const cardsHtml = slice.map(it => {
        const numero = escapeHtml(String(it.numero_os || ''));
        const sup = escapeHtml(String(it.supervisor || ''));
        const cli = escapeHtml(String(it.cliente || ''));
        const uni = escapeHtml(String(it.unidade || ''));
        const pob = Intl.NumberFormat('pt-BR').format(Number(it.avg_pob || 0));
        const ops = Intl.NumberFormat('pt-BR').format(Number(it.sum_operadores_simultaneos || 0));
        const hhNao = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_nao_efetivo || 0));
        const hh = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_efetivo || 0));
        const sacos = Intl.NumberFormat('pt-BR').format(Number(it.total_ensacamento || 0));
        const tambores = Intl.NumberFormat('pt-BR').format(Number(it.total_tambores || 0));

        return `
        <div class="summary-card">
            <div class="card-os">
                <div class="os-badge">OS ${numero} • ${uni}</div>
            </div>
            <div class="divider-top" aria-hidden="true"></div>
            <div class="card-top-grid">
                <div class="col">
                    <div class="item"><strong>Supervisor</strong><div class="value">${sup}</div></div>
                    <div class="item"><strong>Operadores</strong><div class="value">${ops}</div></div>
                    <div class="item"><strong>Sacos</strong><div class="value">${sacos}</div></div>
                </div>
                <div class="col">
                    <div class="item"><strong>Cliente</strong><div class="value">${cli}</div></div>
                    <div class="item"><strong>Média POB</strong><div class="value">${pob}</div></div>
                    <div class="item"><strong>Tambores</strong><div class="value">${tambores}</div></div>
                </div>
            </div>
            <div class="divider"></div>
            <div class="kpi-row kpi-row--two">
                <div class="kpi-item"><div class="kpi-value">${hh}</div><div class="kpi-label">HH Efetivo</div></div>
                <div class="kpi-item"><div class="kpi-value">${hhNao}</div><div class="kpi-label">HH Não Efetivo</div></div>
            </div>
        </div>`;
    }).join('');

    container.innerHTML = `<div class="summary-cards-grid">${cardsHtml}</div>`;

    // ocultar a tabela quando em modo cards
    if(tableEl) tableEl.style.display = getSummaryViewMode() === 'cards' ? 'none' : '';
    container.style.display = getSummaryViewMode() === 'cards' ? '' : 'none';

    // controls de paginação simples (aproveitar summary_paging_controls)
    const controls = document.getElementById('summary_paging_controls');
    if(controls){
        controls.innerHTML = '';
        const prev = document.createElement('button'); prev.className='btn-secondary'; prev.textContent='◀'; prev.disabled = current<=1; prev.addEventListener('click', ()=>renderSummaryCardsPage(current-1));
        const next = document.createElement('button'); next.className='btn-secondary'; next.textContent='▶'; next.disabled = current>=totalPages; next.addEventListener('click', ()=>renderSummaryCardsPage(current+1));
        const info = document.createElement('span'); info.style.margin='0 8px'; info.style.fontSize='12px'; info.style.color='var(--muted)'; info.textContent = `${current}/${totalPages}`;
        controls.appendChild(prev); controls.appendChild(info); controls.appendChild(next);

        // ensure a single toggle button exists and place it next to pagination
        let toggleBtn = document.getElementById('summary-view-toggle-btn');
        if(!toggleBtn){
            toggleBtn = document.createElement('button');
            toggleBtn.type = 'button';
            toggleBtn.id = 'summary-view-toggle-btn';
            toggleBtn.className = 'btn-secondary';
            toggleBtn.style.marginLeft = '10px';
            toggleBtn.onclick = toggleSummaryView;
        } else {
            try{ toggleBtn.remove(); }catch(e){}
        }
        if(typeof getSummaryViewMode === 'function'){
            toggleBtn.textContent = getSummaryViewMode() === 'cards' ? 'Tabela' : 'Cards';
        }
        controls.appendChild(toggleBtn);
    }
}

function toggleSummaryView(){
    const mode = getSummaryViewMode() === 'cards' ? 'table' : 'cards';
    setSummaryViewMode(mode);
    // re-render current page according to mode
    if(mode === 'cards') renderSummaryCardsPage(1); else renderSummaryTablePage(1);
    // update button label if present
    const btn = document.getElementById('summary-view-toggle-btn'); if(btn) btn.textContent = mode === 'cards' ? 'Tabela' : 'Cards';
}

// (removed delegated handler in favor of a single onclick handler on the button elements)

/**
 * Reseta os filtros e recarrega o dashboard
 */
function resetFilters() {
    const today = new Date();
    const thirtyDaysAgo = new Date(today.getTime() - (30 * 24 * 60 * 60 * 1000));
    
    document.getElementById('filter_data_inicio').valueAsDate = thirtyDaysAgo;
    document.getElementById('filter_data_fim').valueAsDate = today;
    document.getElementById('filter_supervisor').value = '';
    document.getElementById('filter_cliente').value = '';
    document.getElementById('filter_unidade').value = '';
    if(document.getElementById('filter_coordenador')) document.getElementById('filter_coordenador').value = '';
    document.getElementById('filter_tanque').value = '';
    if(document.getElementById('filter_status')) document.getElementById('filter_status').value = '';
    if(document.getElementById('os_existente_input')) document.getElementById('os_existente_input').value = '';
    
    loadDashboard();
}

/**
 * Faz requisição AJAX para um endpoint e retorna os dados
 */
async function fetchChartData(endpoint, filters) {
    const queryParams = new URLSearchParams({
        start: filters.start,
        end: filters.end,
        supervisor: filters.supervisor,
        cliente: filters.cliente,
        unidade: filters.unidade,
        tanque: filters.tanque,
        os_existente: filters.os_existente,
        coordenador: (filters.coordenador || ''),
        status: (filters.status || '')
    });
    
    const response = await fetch(`${endpoint}?${queryParams}`, {
        method: 'GET',
        credentials: 'same-origin',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    });
    
    // Se a resposta não estiver OK, tentar extrair corpo para diagnóstico e lançar erro mais informativo
    if (!response.ok) {
        try{
            const loc = response.url || '';
            if(loc.indexOf('/login') !== -1){
                window.location.href = loc;
                return Promise.reject(new Error('Sessão inválida — redirecionando para login'));
            }
        }catch(e){}

        // Ler corpo como texto para ajudar no debug (pode ser JSON ou HTML de erro)
        let bodyText = '';
        try {
            bodyText = await response.text();
        } catch (e) {
            bodyText = '<não foi possível ler o corpo da resposta>';
        }

        // Tentar parsear JSON para mostrar estrutura legível
        let parsed = null;
        try { parsed = JSON.parse(bodyText); } catch(e) { parsed = null; }

        console.error('fetchChartData: resposta não OK', { status: response.status, url: response.url, body: parsed || bodyText });

        // Incluir trecho do corpo na mensagem de erro (limitado) para não poluir o console
        const snippet = (typeof bodyText === 'string' ? bodyText.substr(0, 800) : String(bodyText));
        throw new Error(`Erro HTTP: ${response.status} - ${snippet}`);
    }

    // Verificar tipo de conteúdo — se não for JSON (p.ex. HTML de login), redirecionar para login
    const ct = response.headers.get('content-type') || '';
    if(ct.indexOf('application/json') === -1){
        // Possível HTML (login). Se a URL final contém '/login', redirecionar.
        try{
            const loc = response.url || '';
            if(loc.indexOf('/login') !== -1){
                window.location.href = loc;
                return Promise.reject(new Error('Redirecionando para login'));
            }
        }catch(e){}
        // Se não sabemos, tentar parse seguro: ler texto e buscar hint de login
        const txt = await response.text();
        if(typeof txt === 'string' && txt.indexOf('<form') !== -1 && txt.toLowerCase().indexOf('login') !== -1){
            window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname + window.location.search);
            return Promise.reject(new Error('Sessão expirada — redirecionando para login'));
        }
        // caso contrário, rejeitar
        throw new Error('Resposta inesperada (não JSON) do servidor');
    }

    return await response.json();
}

/**
 * Cria ou atualiza um gráfico Chart.js
 */
function updateChart(chartId, type, data, options = {}) {
    const ctx = document.getElementById(chartId);

    // Destruir gráfico anterior se existir
    if (charts[chartId]) {
        charts[chartId].destroy();
    }

    // Normaliza dados: força valores numéricos e labels vazios
    function normalizePayload(payload){
        if(!payload) return payload;
        // labels
        if(Array.isArray(payload.labels)){
            payload.labels = payload.labels.map(l => {
                if(l === null || l === undefined || String(l).trim() === '') return 'Desconhecido';
                return String(l);
            });
        }
        // datasets
        if(Array.isArray(payload.datasets)){
            payload.datasets.forEach(ds => {
                if(!Array.isArray(ds.data)) ds.data = [];
                ds.data = ds.data.map(v => {
                    // Nulls, empty strings or localized numbers: try parse
                    if (v === null || v === undefined || v === '') return 0;
                    // Remove thousands separators and replace comma decimal
                    if(typeof v === 'string'){
                        const cleaned = v.replace(/\./g,'').replace(/,/g,'.');
                        const n = Number(cleaned);
                        return isNaN(n) ? 0 : n;
                    }
                    const n = Number(v);
                    return isNaN(n) ? 0 : n;
                });
            });
        }
        return payload;
    }

    // Paleta verde para linhas e barras (usar #1B7A4B como cor principal conforme solicitado)
        const themePalette = ['#1B7A4B','#149245','#9FE66F','#6fbf4f','#2ecc71'];
        const lineFill = 'rgba(27,122,75,0.08)';
    const payload = normalizePayload(JSON.parse(JSON.stringify(data)));

    // Atribui cores padrão globalmente (paleta verde), exceto quando o chamador solicitar
    // explicitamente que as cores de dataset sejam preservadas.
    const preserveDatasetColors = !!(options && options.__preserveDatasetColors);
    if(!preserveDatasetColors && Array.isArray(payload.datasets)){
        payload.datasets.forEach((ds, idx) => {
            const chosen = themePalette[idx % themePalette.length];
            ds.backgroundColor = chosen;
            ds.borderColor = chosen;
            if(ds.type === 'line' || type === 'line'){
                ds.fill = ds.fill !== undefined ? ds.fill : false;
                ds.borderWidth = ds.borderWidth || 2;
                ds.pointRadius = ds.pointRadius !== undefined ? ds.pointRadius : 3;
                // lines devem ter preenchimento suave
                ds.backgroundColor = lineFill;
                ds.borderColor = chosen;
            }
        });
    }

    // Detectar se labels parecem datas (YYYY-MM-DD) — usado mais abaixo
    const labelsAreDates = Array.isArray(payload.labels) && payload.labels.length && /^\d{4}-\d{2}-\d{2}/.test(String(payload.labels[0]));

    // Verifica se há dados (todos zeros)
    const totalSum = (function(){
        if(!payload.datasets) return 0;
        return payload.datasets.reduce((acc, ds) => acc + ds.data.reduce((s,v) => s + (Number(v)||0), 0), 0);
    })();

    

    // Opções padrão aprimoradas
    const defaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: true, position: 'top' },
            tooltip: { mode: 'index', intersect: false, callbacks: { label: ctx => {
                // label de tooltip personalizado (formatação)
                if(ctx.dataset && ctx.parsed !== undefined){
                    const val = ctx.parsed.y !== undefined ? ctx.parsed.y : ctx.parsed;
                    return `${ctx.dataset.label || ''}: ${Intl.NumberFormat('pt-BR').format(Number(val) || 0)}`;
                }
                return '';
            }}}
        }
    };

    // Detectar tema escuro (aplicado pela classe `dark-mode` no body) e ajustar cores para legibilidade
    const isDark = (typeof document !== 'undefined' && document.body && document.body.classList.contains('dark-mode')) ? true : false;
    if (isDark) {
        defaultOptions.color = '#ffffff';
        defaultOptions.font = defaultOptions.font || {};
        defaultOptions.font.family = defaultOptions.font.family || 'Inter, system-ui, -apple-system, "Segoe UI", Roboto';

        // Legenda e tooltip em claro
        defaultOptions.plugins.legend = defaultOptions.plugins.legend || {};
        defaultOptions.plugins.legend.labels = Object.assign({}, defaultOptions.plugins.legend.labels, { color: '#ffffff' });
        defaultOptions.plugins.tooltip = defaultOptions.plugins.tooltip || {};
        defaultOptions.plugins.tooltip.titleColor = '#ffffff';
        defaultOptions.plugins.tooltip.bodyColor = '#ffffff';

        // Escalas padrão com ticks e grid mais claros
        defaultOptions.scales = defaultOptions.scales || {};
        defaultOptions.scales.x = defaultOptions.scales.x || {};
        defaultOptions.scales.y = defaultOptions.scales.y || {};
        defaultOptions.scales.x.ticks = Object.assign({}, defaultOptions.scales.x.ticks, { color: '#ffffff' });
        defaultOptions.scales.y.ticks = Object.assign({}, defaultOptions.scales.y.ticks, { color: '#ffffff' });
        defaultOptions.scales.x.grid = Object.assign({}, defaultOptions.scales.x.grid, { color: 'rgba(255,255,255,0.04)' });
        defaultOptions.scales.y.grid = Object.assign({}, defaultOptions.scales.y.grid, { color: 'rgba(255,255,255,0.04)' });
    }

    const finalOptions = { ...defaultOptions, ...options };

    // Calcular padding superior dinamicamente para gráficos de barra com rótulos acima.
    if(type === 'bar'){
        finalOptions.layout = finalOptions.layout || {};
        finalOptions.layout.padding = finalOptions.layout.padding || {};
        try{
            const measureCanvas = document.createElement('canvas');
            const measureCtx = measureCanvas.getContext('2d');
            const font = '600 12px Inter, system-ui';
            measureCtx.font = font;
            const formatter = new Intl.NumberFormat('pt-BR');
            let maxTextHeight = 0;
            // limitar custo de medição para conjuntos muito grandes
            const maxComputeLabels = 200;
            if(Array.isArray(data.datasets) && Array.isArray(data.labels) && data.labels.length <= maxComputeLabels){
                data.datasets.forEach(ds => {
                    if(!Array.isArray(ds.data)) return;
                    ds.data.forEach(v => {
                        const num = Number(v);
                        if(isNaN(num) || num === 0) return;
                        const txt = formatter.format(num);
                        const m = measureCtx.measureText(txt);
                        const ascent = (m.actualBoundingBoxAscent !== undefined) ? m.actualBoundingBoxAscent : 10;
                        const descent = (m.actualBoundingBoxDescent !== undefined) ? m.actualBoundingBoxDescent : 2;
                        const h = ascent + descent;
                        if(h > maxTextHeight) maxTextHeight = h;
                    });
                });
            }
            const safety = 12; // margem
            const minTop = 28; // valor base
            const needed = Math.ceil(Math.max(minTop, (maxTextHeight ? (maxTextHeight + safety) : minTop)));
            finalOptions.layout.padding.top = Math.max(finalOptions.layout.padding.top || 0, needed);
        }catch(e){
            finalOptions.layout.padding.top = Math.max(finalOptions.layout.padding.top || 0, 28);
        }
    }

    // Detectar largura da janela para ajustes responsivos nos charts
    const screenWidth = (typeof window !== 'undefined' && window.innerWidth) ? window.innerWidth : (ctx && ctx.width) ? ctx.width : 1024;
    const isSmallScreen = screenWidth <= 480;
    const isMediumScreen = screenWidth > 480 && screenWidth <= 768;

    // Ajustar limite de ticks (quantidade de rótulos no eixo X) quando não informado
    if(!finalOptions.scales) finalOptions.scales = finalOptions.scales || {};
    finalOptions.scales.x = finalOptions.scales.x || {};
    finalOptions.scales.x.ticks = finalOptions.scales.x.ticks || finalOptions.scales.x.ticks || {};
    if(finalOptions.scales.x.ticks.maxTicksLimit === undefined){
        if(labelsAreDates){
            finalOptions.scales.x.ticks.maxTicksLimit = isSmallScreen ? 4 : (isMediumScreen ? 6 : 12);
        } else {
            finalOptions.scales.x.ticks.maxTicksLimit = isSmallScreen ? 4 : (isMediumScreen ? 8 : 20);
        }
    }

    // Garantir espaço inferior suficiente para rótulos de data (evita corte dos labels)
    finalOptions.layout = finalOptions.layout || {};
    finalOptions.layout.padding = finalOptions.layout.padding || {};
    try{
        // Valor base para padding bottom, ajustado por tamanho de tela
        const baseBottom = isSmallScreen ? 48 : (isMediumScreen ? 64 : 84);
        // Se labels são datas, aumentar margem ainda mais para suportar rotação
        const dateExtra = labelsAreDates ? 12 : 0;
        finalOptions.layout.padding.bottom = Math.max(finalOptions.layout.padding.bottom || 0, baseBottom + dateExtra);
    }catch(e){
        finalOptions.layout.padding.bottom = Math.max(finalOptions.layout.padding.bottom || 0, 64);
    }

    // Desabilitar desenho de labels/valores nas barras em telas pequenas (evita poluição visual)
    finalOptions.plugins = finalOptions.plugins || {};
    finalOptions.plugins.barValuePlugin = finalOptions.plugins.barValuePlugin || {};
    if(isSmallScreen){
        finalOptions.plugins.barValuePlugin.display = false;
    }

    // Ajustes leves nos datasets para telas pequenas (menos pontos e linhas mais finas)
    if(isSmallScreen && Array.isArray(payload.datasets)){
        payload.datasets.forEach(ds => {
            if(ds.type === 'line' || type === 'line'){
                ds.pointRadius = 0;
                ds.borderWidth = ds.borderWidth ? Math.max(1, ds.borderWidth - 1) : 1;
            }
            // em barras, evitar backgroundColor muito opaco quando a largura for pequena
            if(ds.type === 'bar' || type === 'bar'){
                ds.borderWidth = ds.borderWidth || 0;
            }
        });
    }

    // Forçar eixo X como categórico quando labels não são datas,
    // para evitar que Chart.js trate labels numéricos como eixo linear e mostre índices (0,1...)
    if(!labelsAreDates && Array.isArray(payload && payload.labels)){
        finalOptions.scales = finalOptions.scales || {};
        finalOptions.scales.x = finalOptions.scales.x || {};
        finalOptions.scales.x.type = finalOptions.scales.x.type || 'category';
    }

    // Ajustar dinamicamente os eixos quando todos os valores forem positivos
    try{
        const allValues = [];
        if(Array.isArray(payload.datasets)){
            payload.datasets.forEach(ds => {
                if(Array.isArray(ds.data)) ds.data.forEach(v => {
                    const n = Number((typeof v === 'string') ? v.replace(/\./g,'').replace(/,/g,'.') : v);
                    if(!isNaN(n)) allValues.push(n);
                });
            });
        }
        const positiveVals = allValues.filter(v => isFinite(v) && v > 0);
        if(positiveVals.length){
            const minVal = Math.min.apply(null, positiveVals);
            // Queremos que o eixo numérico não mostre 0 — ideal começar em 1.
            // Usar 90% do menor valor quando for maior que 1, caso contrário forçar 1.
            const suggested = Math.max(1, Math.floor(minVal * 0.9));
            if(!finalOptions.scales) finalOptions.scales = {};

            // Determinar qual eixo é numérico: por padrão é Y (vertical bars),
            // mas se o gráfico estiver em indexAxis === 'y' (barras horizontais), o numérico é X.
            const numericAxis = (finalOptions.indexAxis === 'y') ? 'x' : 'y';

            // Aplicar ajuste no eixo numérico detectado
            finalOptions.scales[numericAxis] = finalOptions.scales[numericAxis] || {};
            finalOptions.scales[numericAxis].beginAtZero = false;
            finalOptions.scales[numericAxis].suggestedMin = suggested;
        }
    } catch(err){
        console.debug('axis adjust error', err);
    }

    // Plugin para mostrar mensagem quando não há dados
    const noDataPlugin = {
        id: 'noDataPlugin',
        beforeDraw: (chart) => {
            if(totalSum === 0){
                const ctx = chart.ctx;
                const width = chart.width;
                const height = chart.height;
                ctx.save();
                ctx.fillStyle = isDark ? 'rgba(255,255,255,0.85)' : 'rgba(15,23,42,0.6)';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.font = '600 14px Inter, system-ui, -apple-system, "Segoe UI", Roboto';
                ctx.fillText('Sem dados para este período', width / 2, height / 2);
                ctx.restore();
            }
        }
    };

    // Plugin para desenhar texto central (usado por doughnut)
    const centerTextPlugin = {
        id: 'centerTextPlugin',
        beforeDraw: (chart) => {
            const cfg = finalOptions && finalOptions.plugins && finalOptions.plugins.centerText;
            if(!cfg) return;
            const ctx = chart.ctx;
            const width = chart.width;
            const height = chart.height;
            ctx.save();
            ctx.fillStyle = cfg.color || 'rgba(15,23,42,0.9)';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = cfg.font || '700 14px Inter, system-ui, -apple-system, "Segoe UI", Roboto';
            ctx.fillText(typeof cfg.text === 'function' ? cfg.text(chart) : (cfg.text || ''), width / 2, height / 2);
            ctx.restore();
        }
    };

    // Plugin para desenhar valores ao final das barras (funciona para barras horizontais/verticais)
    const barValuePlugin = {
        id: 'barValuePlugin',
        afterDatasetsDraw: (chart) => {
            const cfg = chart.options.plugins?.barValuePlugin;
            //desativa o desenho de valores
            if (cfg?.display === false) return;
            //se não houver dados agregados, não desenha valores
            if (totalSum === 0) return;
            const ctx = chart.ctx;
            const canvasHeight = chart.height;
            const canvasWidth = chart.width;
            const outsideColor = isDark ? '#ffffff' : '#0f172a';
            chart.data.datasets.forEach((dataset, datasetIndex) => {
                const meta = chart.getDatasetMeta(datasetIndex);
                if(!meta || !meta.data) return;
                // evitar desenhar rótulos quando houver muitos pontos (evita poluição visual)
                const maxLabels = (cfg && cfg.maxLabels) ? cfg.maxLabels : 40;
                if(Array.isArray(chart.data.labels) && chart.data.labels.length > maxLabels) return;
                meta.data.forEach((element, index) => {
                    const value = dataset.data[index];
                    if(value === undefined || value === null) return;
                    // não desenhar valores zero (evita '0' desnecessário abaixo das barras)
                    if(Number(value) === 0) return;

                    ctx.save();
                    ctx.font = '600 12px Inter, system-ui';
                    const formatted = Intl.NumberFormat('pt-BR').format(Number(value) || 0);

                    // coordenadas e dimensões da barra (fazer cálculos de forma robusta)
                    let top = 0, bottom = 0, left = 0, right = 0;
                    try{
                        // Para barras verticais (indexAxis !== 'y'):
                        if(chart.options.indexAxis === 'y'){
                            // horizontal bars: x varia, y é centro
                            left = Math.min(typeof element.x === 'number' ? element.x : 0, typeof element.base === 'number' ? element.base : element.x || 0);
                            right = Math.max(typeof element.x === 'number' ? element.x : 0, typeof element.base === 'number' ? element.base : element.x || 0);
                            const barWidth = Math.abs(right - left);
                            const pos = element.tooltipPosition ? element.tooltipPosition() : {x: element.x, y: element.y};

                            // Se couber dentro da barra, desenha dentro com texto claro, caso contrário desenha à direita
                            if(barWidth > 36){
                                ctx.fillStyle = '#fff';
                                ctx.textAlign = 'right';
                                ctx.textBaseline = 'middle';
                                ctx.fillText(formatted, right - 6, pos.y);
                            } else {
                                ctx.fillStyle = '#0f172a';
                                ctx.textAlign = 'left';
                                ctx.textBaseline = 'middle';
                                // garantir que o texto não fique fora do canvas
                                const x = Math.min(right + 6, canvasWidth - 6);
                                ctx.fillText(formatted, x, pos.y);
                            }
                        } else {
                            // vertical bars
                                top = Math.min(typeof element.y === 'number' ? element.y : 0, typeof element.base === 'number' ? element.base : element.y || 0);
                                bottom = Math.max(typeof element.y === 'number' ? element.y : 0, typeof element.base === 'number' ? element.base : element.y || 0);
                                const barHeight = Math.abs(bottom - top);
                                const pos = element.tooltipPosition ? element.tooltipPosition() : {x: element.x, y: element.y};

                                // Forçar rótulos acima (fora) para os gráficos diários onde os valores no meio ficam feios
                                const forceAboveIds = ['chartEnsacamento','chartTambores','chartResidLiquido','chartResidSolido'];
                                const forceAbove = forceAboveIds.includes(chart.canvas && chart.canvas.id ? chart.canvas.id : '');

                                // Se couber dentro da barra e não for um gráfico com força de posicionamento, desenha dentro (cor clara).
                                // Caso contrário, desenha acima da barra (cor escura) para melhorar legibilidade.
                                if(!forceAbove && barHeight > 22){
                                    ctx.fillStyle = '#fff';
                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'middle';
                                    const yInside = (top + bottom) / 2;
                                    ctx.fillText(formatted, pos.x, yInside);
                                } else {
                                    ctx.fillStyle = outsideColor;
                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'bottom';
                                    // desenha acima, com margem mínima de 6px
                                    // garantir que não desenhe acima do padding superior reservado
                                    const topPadding = (finalOptions && finalOptions.layout && finalOptions.layout.padding && finalOptions.layout.padding.top) ? finalOptions.layout.padding.top : 12;
                                    const y = Math.max(top - 6, topPadding);
                                    // evitar desenhar fora do canvas
                                    const clampedY = Math.min(Math.max(y, topPadding), canvasHeight - 6);
                                    ctx.fillText(formatted, pos.x, clampedY);
                                }
                        }
                    }catch(e){
                        // fallback simples: desenhar acima do ponto central
                        try{
                            const pos = element.tooltipPosition ? element.tooltipPosition() : {x: element.x, y: element.y};
                            ctx.fillStyle = outsideColor;
                            ctx.textAlign = 'center';
                            ctx.textBaseline = 'bottom';
                            const y = Math.max((typeof element.y === 'number' ? element.y : pos.y) - 8, 12);
                            ctx.fillText(formatted, pos.x, y);
                        }catch(err){}
                    }
                    ctx.restore();
                });
            });
        }
    };

    // Ajustes por tipo comuns
    if(!finalOptions.scales) finalOptions.scales = {};
    // Formatação de ticks para eixos
    // Se não houver dados, esconder ticks numéricos (para não mostrar apenas '0')
    if(totalSum === 0){
        if(finalOptions.scales.x) finalOptions.scales.x.ticks = finalOptions.scales.x.ticks || {}, finalOptions.scales.x.ticks.display = false;
        if(finalOptions.scales.y) finalOptions.scales.y.ticks = finalOptions.scales.y.ticks || {}, finalOptions.scales.y.ticks.display = false;
    }
    if(finalOptions.scales.x){
        finalOptions.scales.x.ticks = finalOptions.scales.x.ticks || {};
        // Detecta se os rótulos são datas no formato YYYY-MM-DD (ou similar)
        const labelsAreDates = Array.isArray(payload.labels) && payload.labels.length && /^\d{4}-\d{2}-\d{2}/.test(String(payload.labels[0]));
        if(labelsAreDates){
            // Usar auto-skip e limitar número de ticks para evitar sobreposição
            finalOptions.scales.x.ticks.autoSkip = finalOptions.scales.x.ticks.autoSkip !== undefined ? finalOptions.scales.x.ticks.autoSkip : true;
            finalOptions.scales.x.ticks.maxTicksLimit = finalOptions.scales.x.ticks.maxTicksLimit || 8;
            // Callback para formatar as datas de forma curta (dd/mm/aaaa)
            finalOptions.scales.x.ticks.callback = function(tickValue, index){
                // Tentar recuperar label original no payload quando possível
                const raw = (Array.isArray(payload.labels) && payload.labels[index] !== undefined) ? String(payload.labels[index]) : String(tickValue);
                // Tenta parsear para Date; se falhar, retorna substring curta
                let d = new Date(raw);
                if(isNaN(d)){
                    const parts = raw.match(/(\d{4})[^\d]?(\d{2})[^\d]?(\d{2})/);
                    if(parts && parts.length >= 4){
                        d = new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]));
                    }
                }
                if(isNaN(d)){
                    return raw.length > 10 ? raw.slice(0,10) : raw;
                }
                // Se o rótulo representar o primeiro dia do mês (YYYY-MM-01), mostrar apenas MM/YYYY
                try{
                    const isoMatch = String(raw).match(/^(\d{4})-(\d{2})-01$/);
                    if(isoMatch){
                        const year = Number(isoMatch[1]);
                        const month = Number(isoMatch[2]) - 1;
                        const monthLabel = new Date(year, month, 1).toLocaleDateString('pt-BR', {month: '2-digit', year: 'numeric'});
                        return monthLabel;
                    }
                }catch(e){}
                return d.toLocaleDateString('pt-BR');
            };
            // Ajustar rotações e padding para evitar sobreposição e cortes
            finalOptions.scales.x.ticks.maxRotation = finalOptions.scales.x.ticks.maxRotation || 30;
            finalOptions.scales.x.ticks.minRotation = finalOptions.scales.x.ticks.minRotation || 0;
            finalOptions.scales.x.ticks.padding = finalOptions.scales.x.ticks.padding || 6;
            // Espaçamento extra utilizado pelo algoritmo de auto-skip
            finalOptions.scales.x.ticks.autoSkip = finalOptions.scales.x.ticks.autoSkip !== undefined ? finalOptions.scales.x.ticks.autoSkip : true;
            finalOptions.scales.x.ticks.autoSkipPadding = finalOptions.scales.x.ticks.autoSkipPadding || 12;
            // Ajustar tamanho da fonte dos ticks para caber melhor em telas pequenas
            finalOptions.scales.x.ticks.font = finalOptions.scales.x.ticks.font || {};
            finalOptions.scales.x.ticks.font.size = finalOptions.scales.x.ticks.font.size || (isSmallScreen ? 10 : 12);
        } else {
            finalOptions.scales.x.ticks.callback = function(value, index){
                // Se houver labels fornecidas, mostre a label correspondente (caso categórico)
                if(Array.isArray(payload.labels) && payload.labels[index] !== undefined){
                    return String(payload.labels[index]);
                }
                return Intl.NumberFormat('pt-BR').format(value);
            };
        }
    }
    if(finalOptions.scales.y){
        finalOptions.scales.y.ticks = finalOptions.scales.y.ticks || {};
        finalOptions.scales.y.ticks.callback = function(value){
            return Intl.NumberFormat('pt-BR').format(value);
        };
    }

    // Criar novo gráfico com plugins apropriados
    const pluginsList = [noDataPlugin];
    if(finalOptions && finalOptions.plugins && finalOptions.plugins.centerText){
        pluginsList.push(centerTextPlugin);
    }

    // Adiciona plugin de valores em barras automaticamente para gráficos do tipo 'bar'
    // mas respeita a configuração responsiva `finalOptions.plugins.barValuePlugin.display`.
    const allowBarValues = !(finalOptions.plugins && finalOptions.plugins.barValuePlugin && finalOptions.plugins.barValuePlugin.display === false);
    if(type === 'bar' && allowBarValues){
        pluginsList.push(barValuePlugin);
    }

    charts[chartId] = new Chart(ctx, {
        type: type,
        data: payload,
        options: finalOptions,
        plugins: pluginsList
    });
}

/**
 * Gráfico 1: HH em Espaço Confinado por Dia
 */
async function loadChartHHConfinado(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/hh_confinado_por_dia/', filters);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };
        
        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Horas' }
                }
            }
        };
        
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };
        
        updateChart('chartHHConfinado', 'line', chartData, mergedOptions);
        return { key: 'hh_confinado', data: data };
    } catch (error) {
        console.error('Erro ao carregar HH Confinado:', error);
    }
}

/**
 * Gráfico 2: HH Fora de Espaço Confinado por Dia
 */
async function loadChartHHForaConfinado(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/hh_fora_confinado_por_dia/', filters);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };
        
        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Horas' }
                }
            }
        };
        
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };
        
        updateChart('chartHHForaConfinado', 'line', chartData, mergedOptions);
        return { key: 'hh_fora', data: data };
    } catch (error) {
        console.error('Erro ao carregar HH Fora Confinado:', error);
    }
}

/**
 * Gráfico: Tempo de uso da bomba por dia
 */
async function loadChartTempoBomba(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/rdo_tempo_bomba_por_dia/', filters);
        if (!data || !data.success) {
            throw new Error(data ? data.error || 'Erro desconhecido' : 'Resposta inválida');
        }

        const rawLabels = Array.isArray(data.labels) ? data.labels : [];
        const rawDatasets = Array.isArray(data.datasets) ? data.datasets : [];
        const tankSeries = rawDatasets.map(ds => {
            const label = (ds && ds.label !== undefined && ds.label !== null) ? String(ds.label) : 'Tanque';
            const arr = (ds && Array.isArray(ds.data)) ? ds.data : [];
            const series = arr.map(v => {
                const n = Number(v);
                return isFinite(n) ? n : 0;
            });
            return { label, series };
        }).filter(t => t && t.series && t.series.length);

        // Total por ponto (soma de todos os tanques) — usado para tendência/acumulado
        const values = rawLabels.map((_, idx) => {
            let s = 0;
            tankSeries.forEach(t => { s += Number(t.series[idx]) || 0; });
            return s;
        });

        // Helpers de datas (labels do backend são YYYY-MM-DD)
        function parseYMD(s){
            try{
                const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})/);
                if(!m) return null;
                const y = Number(m[1]);
                const mo = Number(m[2]) - 1;
                const d = Number(m[3]);
                const dt = new Date(Date.UTC(y, mo, d));
                return isNaN(dt.getTime()) ? null : dt;
            }catch(e){
                return null;
            }
        }
        function fmtDateBR(dt){
            try{
                // dd/mm
                const d = String(dt.getUTCDate()).padStart(2,'0');
                const m = String(dt.getUTCMonth()+1).padStart(2,'0');
                return `${d}/${m}`;
            }catch(e){
                return '';
            }
        }

        // Agregação semanal (seg-dom). Deixa muito mais legível quando o período é grande.
        function aggregateToWeeks(labels, series){
            const buckets = new Map();
            for(let i=0;i<labels.length;i++){
                const dt = parseYMD(labels[i]);
                if(!dt) continue;
                // getUTCDay: 0=dom ... 6=sab; queremos seg=0 ... dom=6
                const day = dt.getUTCDay();
                const deltaToMonday = (day === 0) ? 6 : (day - 1);
                const monday = new Date(dt.getTime() - deltaToMonday*24*60*60*1000);
                const key = monday.toISOString().slice(0,10);
                const v = Number(series[i]) || 0;
                const prev = buckets.get(key) || { monday, sum: 0, days: 0 };
                prev.sum += v;
                prev.days += 1;
                buckets.set(key, prev);
            }
            const ordered = Array.from(buckets.values()).sort((a,b) => a.monday - b.monday);
            const weekLabels = [];
            const weekSums = [];
            const weekDays = [];
            ordered.forEach(w => {
                const start = w.monday;
                const end = new Date(start.getTime() + 6*24*60*60*1000);
                weekLabels.push(`${fmtDateBR(start)}–${fmtDateBR(end)}`);
                weekSums.push(w.sum);
                weekDays.push(w.days);
            });
            return { weekLabels, weekSums, weekDays };
        }

        // Média móvel simples (7 dias) para visual mais moderno e leitura de tendência
        function movingAverage(series, windowSize){
            const out = [];
            const w = Math.max(2, Number(windowSize) || 7);
            for(let i = 0; i < series.length; i++){
                const start = Math.max(0, i - (w - 1));
                let sum = 0;
                let count = 0;
                for(let j = start; j <= i; j++){
                    sum += Number(series[j]) || 0;
                    count += 1;
                }
                out.push(count ? (sum / count) : 0);
            }
            return out;
        }

        const ma7 = movingAverage(values, 7);

        const useWeekly = values.length > 21; // acima de 3 semanas, diário fica difícil de entender
        let labels = rawLabels;
        let barsTotal = values;
        let trend = ma7;
        let modeLabel = 'Diário';
        let tankBars = tankSeries.map(t => ({ label: t.label, data: t.series }));

        if(useWeekly){
            // agrega cada tanque para semana e recalcula total
            const aggTotal = aggregateToWeeks(rawLabels, values);
            labels = aggTotal.weekLabels;

            tankBars = tankBars.map(t => {
                const agg = aggregateToWeeks(rawLabels, t.data);
                return { label: t.label, data: agg.weekSums };
            });

            barsTotal = labels.map((_, idx) => {
                let s = 0;
                tankBars.forEach(t => { s += Number(t.data[idx]) || 0; });
                return s;
            });

            // tendência semanal: média móvel em cima das semanas
            trend = movingAverage(barsTotal, 4);
            modeLabel = 'Semanal';
        }

        // Linha acumulada (muito mais fácil de entender volume/tempo total ao longo do período)
        const cumulative = [];
        let run = 0;
        for(let i=0;i<barsTotal.length;i++){
            run += Number(barsTotal[i]) || 0;
            cumulative.push(run);
        }

        const maxY = barsTotal.reduce((m, v) => Math.max(m, Number(v) || 0), 0);
        const avgBar = barsTotal.length ? (barsTotal.reduce((a,b)=>a+(Number(b)||0),0) / barsTotal.length) : 0;
        const totalBars = barsTotal.reduce((acc, v) => acc + (Number(v) || 0), 0);
        const lastBar = barsTotal.length ? (Number(barsTotal[barsTotal.length - 1]) || 0) : 0;

        // Evitar valores de tendência em dias/semanas sem lançamento (ex: 0,854 em dia vazio)
        const trendMasked = trend.map((v, i) => (Number(barsTotal[i] || 0) > 0 ? v : null));

        // Tanque líder no período
        let leaderLabel = '--';
        let leaderTotal = 0;
        try{
            tankBars.forEach(t => {
                const tTotal = (t.data || []).reduce((acc, v) => acc + (Number(v) || 0), 0);
                if(tTotal > leaderTotal){
                    leaderTotal = tTotal;
                    leaderLabel = t.label;
                }
            });
        }catch(e){ /* ignore */ }

        // Cores bem distintas por tanque (determinístico pela label), evitando “tudo verde”.
        // Paleta baseada em cores categóricas amplamente usadas (alta distinção).
        const distinctPalette = [
            '#4E79A7', // blue
            '#F28E2B', // orange
            '#E15759', // red
            '#76B7B2', // teal
            '#59A14F', // green (aparece, mas não domina)
            '#EDC948', // yellow
            '#B07AA1', // purple
            '#FF9DA7', // pink
            '#9C755F', // brown
            '#BAB0AC', // gray
            '#1F77B4', // plotly blue
            '#FF7F0E', // plotly orange
            '#D62728', // plotly red
            '#9467BD', // plotly purple
            '#8C564B', // plotly brown
            '#E377C2', // plotly pink
            '#7F7F7F', // plotly gray
            '#BCBD22', // olive
            '#17BECF'  // cyan
        ];

        function colorForLabel(label){
            // manter 'Outros' sempre neutro
            try{
                const s0 = String(label || '').trim().toLowerCase();
                if(s0 === 'outros'){
                    return { bg: '#BAB0AC44', border: '#BAB0AC' };
                }
            }catch(e){ /* ignore */ }
            const s = String(label || '');
            let hash = 0;
            for(let i=0;i<s.length;i++) hash = ((hash << 5) - hash) + s.charCodeAt(i);
            const idx = Math.abs(hash) % distinctPalette.length;
            const hex = distinctPalette[idx];
            // fundo translúcido + borda sólida
            const bg = hex + '44';
            const border = hex;
            return { bg, border };
        }

        const tankDatasets = tankBars.map((t) => {
            const c = colorForLabel(t.label);
            return {
                type: 'bar',
                label: t.label,
                data: t.data,
                stack: 'tanques',
                borderRadius: 6,
                borderSkipped: false,
                backgroundColor: c.bg,
                borderColor: c.border,
                borderWidth: 1,
                maxBarThickness: 24
            };
        });

        const chartData = {
            labels: labels,
            datasets: [
                ...tankDatasets,
                {
                    type: 'line',
                    label: useWeekly ? 'Tendência (4 semanas)' : 'Média móvel (7 dias)',
                    data: trendMasked,
                    borderColor: '#CCFF00',
                    backgroundColor: 'rgba(204,255,0,0.08)',
                    pointRadius: 0,
                    tension: 0.35,
                    borderWidth: 2,
                    fill: true,
                    order: 90
                },
                {
                    type: 'line',
                    label: 'Acumulado (total)',
                    data: cumulative,
                    yAxisID: 'y2',
                    borderColor: 'rgba(255,255,255,0.65)',
                    borderDash: [6, 6],
                    pointRadius: 0,
                    tension: 0.15,
                    borderWidth: 2,
                    order: 91
                }
            ]
        };

        const backendOptions = data.options || {};
        const localOptions = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                // Vamos usar uma legenda HTML (mais legível) em vez da legenda padrão
                legend: { display: false },
                // Desliga valores em cima das barras neste gráfico (fica impossível ler com empilhamento)
                barValuePlugin: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx){
                            const v = Number(ctx.parsed && ctx.parsed.y);
                            const h = (isFinite(v) ? v : 0);
                            // y2 é acumulado (mesma unidade), manter padrão
                            return `${ctx.dataset.label}: ${h.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} h (${formatHoursToHHMM(h)})`;
                        },
                        footer: function(items){
                            try{
                                // Somar apenas as barras (tanques) para mostrar o total do dia/semana
                                let sum = 0;
                                items.forEach(it => {
                                    if(it && it.dataset && it.dataset.type === 'bar'){
                                        sum += Number(it.parsed && it.parsed.y) || 0;
                                    }
                                });
                                if(sum > 0){
                                    return `Total: ${sum.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} h (${formatHoursToHHMM(sum)})`;
                                }
                            }catch(e){ /* ignore */ }
                            return '';
                        }
                    }
                },
                subtitle: {
                    display: true,
                    text: `Modo: ${modeLabel}  •  Total: ${totalBars.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} h (${formatHoursToHHMM(totalBars)})  •  ${useWeekly ? 'Média/semana' : 'Média/dia'}: ${avgBar.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} h`,
                    color: (document.body && document.body.classList && document.body.classList.contains('dark-mode')) ? 'rgba(255,255,255,0.75)' : 'rgba(0,0,0,0.65)',
                    font: { size: 12, weight: '600' },
                    padding: { top: 0, bottom: 8 }
                }
            },
            scales: {
                x: { grid: { display: false }, stacked: true },
                y: {
                    beginAtZero: true,
                    suggestedMax: maxY ? (maxY * 1.15) : undefined,
                    title: { display: true, text: useWeekly ? 'Horas por semana (por tanque)' : 'Horas por dia (por tanque)' },
                    stacked: true,
                    ticks: {
                        callback: function(value){
                            const n = Number(value);
                            if(!isFinite(n)) return String(value);
                            return formatHoursToHHMM(n);
                        }
                    }
                },
                y2: {
                    position: 'right',
                    beginAtZero: true,
                    grid: { display: false },
                    ticks: {
                        callback: function(value){
                            const n = Number(value);
                            if(!isFinite(n)) return String(value);
                            return formatHoursToHHMM(n);
                        }
                    },
                    title: { display: true, text: 'Acumulado (h)' }
                }
            }
        };

        // Renderiza legenda HTML clicável (com total por tanque) para facilitar leitura e isolamento
        function ensureTempoBombaLegendUI(){
            const canvas = document.getElementById('chartTempoBomba');
            if(!canvas) return null;
            // Inserir dentro do mesmo wrapper do canvas (evita erro de insertBefore quando o canvas não é filho direto do card)
            const container = canvas.parentElement;
            if(!container) return null;

            let wrap = document.getElementById('tempo_bomba_legend_wrap');
            if(!wrap){
                wrap = document.createElement('div');
                wrap.id = 'tempo_bomba_legend_wrap';
                wrap.style.display = 'flex';
                wrap.style.flexDirection = 'column';
                wrap.style.gap = '8px';
                wrap.style.margin = '6px 0 10px';
                // inserir antes do canvas
                container.insertBefore(wrap, canvas);
            }

            let legend = document.getElementById('tempo_bomba_legend');
            if(!legend){
                legend = document.createElement('div');
                legend.id = 'tempo_bomba_legend';
                legend.style.display = 'flex';
                legend.style.flexWrap = 'wrap';
                legend.style.gap = '8px';
                legend.style.maxHeight = '110px';
                legend.style.overflow = 'auto';
                legend.style.padding = '6px 2px';
                wrap.appendChild(legend);
            }

            return { wrap, legend };
        }

        function renderTempoBombaLegend(chart, tankCount, tankTotalsSorted){
            const ui = ensureTempoBombaLegendUI();
            if(!ui || !chart) return;
            const { legend } = ui;

            function build(){
                legend.innerHTML = '';

                // util: cria pill
                function makePill(label, color, isHidden, rightText){
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'tempo-bomba-pill';
                    btn.style.display = 'inline-flex';
                    btn.style.alignItems = 'center';
                    btn.style.gap = '8px';
                    btn.style.padding = '6px 10px';
                    btn.style.borderRadius = '999px';
                    btn.style.border = '1px solid rgba(148,163,184,0.28)';
                    btn.style.background = isHidden ? 'rgba(148,163,184,0.08)' : 'rgba(255,255,255,0.06)';
                    btn.style.color = 'inherit';
                    btn.style.cursor = 'pointer';
                    btn.style.fontSize = '12px';
                    btn.style.fontWeight = '700';
                    btn.title = 'Clique para mostrar/ocultar. Shift+clique para isolar.';

                    const dot = document.createElement('span');
                    dot.style.width = '10px';
                    dot.style.height = '10px';
                    dot.style.borderRadius = '50%';
                    dot.style.background = color;
                    dot.style.display = 'inline-block';

                    const txt = document.createElement('span');
                    txt.textContent = label;
                    txt.style.opacity = isHidden ? '0.5' : '0.95';

                    const right = document.createElement('span');
                    right.textContent = rightText || '';
                    right.style.marginLeft = '4px';
                    right.style.padding = '2px 8px';
                    right.style.borderRadius = '999px';
                    right.style.fontWeight = '800';
                    right.style.fontSize = '12px';
                    right.style.background = 'rgba(15,23,42,0.22)';
                    right.style.border = '1px solid rgba(148,163,184,0.18)';
                    right.style.opacity = isHidden ? '0.55' : '1';

                    btn.appendChild(dot);
                    btn.appendChild(txt);
                    if(rightText) btn.appendChild(right);
                    return btn;
                }

                // Botão "Todos" (reset)
                const reset = makePill('Mostrar tudo', 'rgba(255,255,255,0.6)', false, '');
                reset.title = 'Restaura a visualização de todos os tanques';
                reset.addEventListener('click', () => {
                    for(let j=0;j<tankCount;j++){
                        const m = chart.getDatasetMeta(j);
                        if(m) m.hidden = false;
                    }
                    chart.update();
                    build();
                });
                legend.appendChild(reset);

                const order = Array.isArray(tankTotalsSorted) && tankTotalsSorted.length
                    ? tankTotalsSorted
                    : Array.from({length: tankCount}, (_, i) => ({ index: i, total: 0 }));

                // Tanques (barras): primeiros `tankCount` datasets, ordenados por total
                for(const item of order){
                    const i = item.index;
                    const ds = chart.data.datasets[i];
                    if(!ds) continue;
                    const label = String(ds.label || 'Tanque');
                    const meta = chart.getDatasetMeta(i);
                    const hidden = meta && meta.hidden === true;
                    const color = (ds.borderColor || ds.backgroundColor || 'rgba(255,255,255,0.7)');
                    const totalTxt = (item && isFinite(item.total)) ? formatHoursToHHMM(item.total) : '';
                    const pill = makePill(label, color, hidden, totalTxt);
                    pill.addEventListener('click', (ev) => {
                        const isolate = ev.shiftKey;
                        if(isolate){
                            // isolar: esconder todos os tanques exceto este; manter linhas visíveis
                            for(let j=0;j<tankCount;j++){
                                const m = chart.getDatasetMeta(j);
                                if(!m) continue;
                                m.hidden = (j !== i);
                            }
                        } else {
                            const m = chart.getDatasetMeta(i);
                            if(m) m.hidden = !m.hidden;
                        }
                        chart.update();
                        build();
                    });
                    legend.appendChild(pill);
                }
            }
            build();
        }

        // Mini-card (chips) explicando o gráfico
        setTextById('tempo_bomba_mode', `${modeLabel} (por tanque)`);
        setTextById('tempo_bomba_total', formatHoursToHHMM(totalBars));
        setTextById('tempo_bomba_avg', formatHoursToHHMM(avgBar));
        if(leaderLabel && leaderLabel !== '--'){
            setTextById('tempo_bomba_peak', `${leaderLabel}: ${formatHoursToHHMM(leaderTotal)}`);
        } else {
            setTextById('tempo_bomba_peak', '--');
        }
        if(labels.length){
            setTextById('tempo_bomba_last', `${formatHoursToHHMM(lastBar)} (${labels[labels.length - 1]})`);
        } else {
            setTextById('tempo_bomba_last', '--');
        }

        // Ajustar texto de ajuda (mantém curto e coerente com modo)
        try{
            const help = document.getElementById('tempo_bomba_help');
            if(help){
                const base = 'Barras = horas no período · Linha verde = tendência (total) · Tracejado = acumulado (total)';
                help.textContent = (useWeekly ? (base + ' · Agrupado por semana') : (base + ' · Agrupado por dia')) + ' · Empilhado por tanque';
            }
        }catch(e){ /* ignore */ }

        const mergedOptions = {
            ...backendOptions,
            ...localOptions,
            plugins: {
                ...(backendOptions.plugins || {}),
                ...(localOptions.plugins || {})
            },
            scales: {
                ...(backendOptions.scales || {}),
                ...(localOptions.scales || {}),
                x: {
                    ...((backendOptions.scales || {}).x || {}),
                    ...((localOptions.scales || {}).x || {})
                },
                y: {
                    ...((backendOptions.scales || {}).y || {}),
                    ...((localOptions.scales || {}).y || {})
                }
            }
        };

        // Este gráfico define cores por tanque (categóricas). Não deixar o updateChart sobrescrever.
        mergedOptions.__preserveDatasetColors = true;

        updateChart('chartTempoBomba', 'bar', chartData, mergedOptions);

        // Depois de criar/atualizar o chart, montar legenda HTML
        try{
            const chart = charts && charts['chartTempoBomba'];
            if(chart){
                const tankTotalsSorted = tankBars.map((t, idx) => ({
                    index: idx,
                    label: t.label,
                    total: (t.data || []).reduce((acc, v) => acc + (Number(v) || 0), 0)
                })).sort((a,b) => (b.total || 0) - (a.total || 0));
                renderTempoBombaLegend(chart, tankDatasets.length, tankTotalsSorted);
            }
        }catch(e){ /* ignore */ }
        return { key: 'tempo_bomba', data: data };
    } catch (error) {
        console.error('Erro ao carregar Tempo de Bomba:', error);
    }
}

/**
 * Gráfico 3: Ensacamento por Dia
 */
async function loadChartEnsacamento(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/ensacamento_por_dia/', filters);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };
        
        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        };
        
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };
        
        updateChart('chartEnsacamento', 'bar', chartData, mergedOptions);
        return { key: 'ensacamento', data: data };
    } catch (error) {
        console.error('Erro ao carregar Ensacamento:', error);
    }
}

/**
 * Gráfico 4: Tambores por Dia
 */
async function loadChartTambores(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/tambores_por_dia/', filters);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };
        
        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        };
        
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };
        
        updateChart('chartTambores', 'bar', chartData, mergedOptions);
        return { key: 'tambores', data: data };
    } catch (error) {
        console.error('Erro ao carregar Tambores:', error);
    }
}

/**
 * Gráfico 5: Resíduo Líquido por Dia
 */
async function loadChartResidLiquido(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/residuos_liquido_por_dia/', filters);
        
        // debug logs removed
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };
        
        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'M³' }
                }
            }
        };
        
        // Mesclar opções mantendo configurações do backend
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };
        
        updateChart('chartResidLiquido', 'bar', chartData, mergedOptions);
        return { key: 'total_liquido', data: data };
    } catch (error) {
        console.error('Erro ao carregar Resíduo Líquido:', error);
    }
}

/**
 * Gráfico 6: Resíduo Sólido por Dia
 */
async function loadChartResidSolido(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/residuos_solido_por_dia/', filters);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };
        
        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'M³' }
                }
            }
        };
        
        // Mesclar opções mantendo configurações do backend
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };
        
        updateChart('chartResidSolido', 'bar', chartData, mergedOptions);
        return { key: 'residuo_solido', data: data };
    } catch (error) {
        console.error('Erro ao carregar Resíduo Sólido:', error);
    }
}

/**
 * Gráfico 7: Líquido por Supervisor
 */
async function loadChartLiquidoSupervisor(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/liquido_por_supervisor/', filters);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };

        // Transformar em barra horizontal, ordenar por valor decrescente
        // Agregação espera que exista apenas um dataset principal
        const ds = (chartData.datasets && chartData.datasets[0]) || {data:[]};
        const pairs = (chartData.labels || []).map((lab, i) => ({label: lab, value: Number(ds.data[i] || 0)}));
        pairs.sort((a,b) => b.value - a.value);
        const sortedLabels = pairs.map(p => p.label);
        const sortedValues = pairs.map(p => p.value);

        const prepared = { labels: sortedLabels, datasets: [{ label: ds.label || 'M³ líquido removido', data: sortedValues, backgroundColor: '#1b7a4b' }] };

        // Ajustar dataset (espessura e borda) para ficar igual ao chartVolumeTanque
        prepared.datasets = prepared.datasets.map(ds2 => ({ ...ds2, maxBarThickness: 64, borderRadius: 8 }));

        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'M³' }, ticks: { callback: v => Intl.NumberFormat('pt-BR').format(v) } },
                x: { ticks: { autoSkip: false, maxRotation: 45, minRotation: 30 } }
            }
        };
        
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };

        updateChart('chartLiquidoSupervisor', 'bar', prepared, mergedOptions);

        return { key: 'liquido_supervisor', data: data };
    } catch (error) {
        console.error('Erro ao carregar Líquido por Supervisor:', error);
    }
}

/**
 * Gráfico 8: Sólido por Supervisor
 */
async function loadChartSolidoSupervisor(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/solido_por_supervisor/', filters);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };

        // Usar barra horizontal ordenada também para sólido (mais legível que polarArea)
        const ds = (chartData.datasets && chartData.datasets[0]) || {data:[]};
        const pairs = (chartData.labels || []).map((lab, i) => ({label: lab, value: Number(ds.data[i] || 0)}));
        pairs.sort((a,b) => b.value - a.value);
        const sortedLabels = pairs.map(p => p.label);
        const sortedValues = pairs.map(p => p.value);

        const prepared = { labels: sortedLabels, datasets: [{ label: ds.label || 'M³ sólido removido', data: sortedValues, backgroundColor: '#6fbf4f' }] };
        // Ajustar dataset para combinar com volume por tanque
        prepared.datasets = prepared.datasets.map(ds2 => ({ ...ds2, maxBarThickness: 64, borderRadius: 8 }));

        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'M³' }, ticks: { callback: v => Intl.NumberFormat('pt-BR').format(v) } },
                x: { ticks: { autoSkip: false, maxRotation: 45, minRotation: 30 } }
            }
        };
        
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };

        updateChart('chartSolidoSupervisor', 'bar', prepared, mergedOptions);
        return { key: 'solido_supervisor', data: data };
    } catch (error) {
        console.error('Erro ao carregar Sólido por Supervisor:', error);
    }
}

/**
 * Gráfico 9: Volume por Tanque
 */
async function loadChartVolumeTanque(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/volume_por_tanque/', filters);
        
        if (!data.success) {
            throw new Error(data.error || 'Erro desconhecido');
        }
        
        const chartData = {
            labels: data.labels,
            datasets: data.datasets
        };

        // Ajustar espessura das barras para melhor leitura
        chartData.datasets = chartData.datasets.map(ds => ({...ds, maxBarThickness: 64, borderRadius: 8}));

        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    beginAtZero: true,
                    title: { display: true, text: 'M³' },
                    ticks: { callback: v => Intl.NumberFormat('pt-BR').format(v) }
                },
                y: {
                    ticks: { autoSkip: false },
                    title: { display: true, text: 'Tanque' }
                }
            }
        };
        
        const mergedOptions = {
            ...localOptions,
            ...backendOptions,
            scales: {
                ...localOptions.scales,
                ...backendOptions.scales,
                x: {
                    ...localOptions.scales?.x,
                    ...backendOptions.scales?.x
                },
                y: {
                    ...localOptions.scales?.y,
                    ...backendOptions.scales?.y
                }
            }
        };

        // Se houver muitas categorias, usar barra vertical com rótulos inclinados
        updateChart('chartVolumeTanque', 'bar', chartData, mergedOptions);
        return { key: 'volume_tanque', data: data };
    } catch (error) {
        console.error('Erro ao carregar Volume por Tanque:', error);
    }
}

    /**
     * Gráfico extra: Média de POB alocado x POB em espaço confinado por Dia
     */
    async function loadChartPobComparativo(filters) {
        try {
            const data = await fetchChartData('/api/rdo-dashboard/pob_comparativo/', filters);

            if (!data.success) {
                throw new Error(data.error || 'Erro desconhecido');
            }


            console.debug('pob_comparativo payload:', data);

            const chartPayload = data.chart || { labels: [], datasets: [] };
            const meta = data.meta || {};

            // Garantir que existam duas séries (posição consistente)
            // Se backend retornou somente uma, preencher a outra com zeros
            const ds = chartPayload.datasets || [];
            if (ds.length === 1) {
                ds.push({ label: 'POB em Espaço Confinado (média/dia)', data: new Array((chartPayload.labels||[]).length).fill(0) });
            }

            // Cores: azul para alocado, laranja para confinado
            const prepared = {
                labels: chartPayload.labels || [],
                datasets: [
                    Object.assign({}, ds[0] || {}, { label: ds[0]?.label || 'POB Alocado (média)', backgroundColor: '#1B7A4B', borderColor: '#1B7A4B', borderRadius: 6, maxBarThickness: 36, barPercentage: 0.6, categoryPercentage: 0.6, order: 1 }),
                    Object.assign({}, ds[1] || {}, { label: ds[1]?.label || 'POB em Espaço Confinado (média)', backgroundColor: '#149245', borderColor: '#149245', borderRadius: 6, maxBarThickness: 36, barPercentage: 0.6, categoryPercentage: 0.6, order: 1 })
                ]
            };

            // Atualizar subtítulo com unidade e totais quando disponível
            try {
                const subEl = document.getElementById('chartPobComparativo_sub');
                if (subEl) {
                    const unidade = meta.filtered_unidade;
                    const counts = meta.counts || {};
                    const totalRDOs = Array.isArray(counts.rdos_per_day) ? counts.rdos_per_day.reduce((s,v)=>s+(Number(v)||0),0) : 0;
                    const totalOS = Array.isArray(counts.distinct_os_per_day) ? counts.distinct_os_per_day.reduce((s,v)=>s+(Number(v)||0),0) : 0;
                    if (unidade) {
                        subEl.textContent = `Unidade: ${unidade} — RDOs no período: ${totalRDOs} • OS distintos no período: ${totalOS}`;
                    } else {
                        subEl.textContent = `RDOs no período: ${totalRDOs} • OS distintos no período: ${totalOS}`;
                    }
                }
            } catch(e){ console.debug('subtitle update error', e); }
            // construir série percentual (POB confinado / POB alocado) como linha
            const alocados = prepared.datasets[0].data || [];
            const confinados = prepared.datasets[1].data || [];
            const ratio = alocados.map((a,i) => {
                const aa = Number(a) || 0;
                const cc = Number(confinados[i]) || 0;
                return aa > 0 ? (cc / aa) * 100.0 : 0.0;
            });

            const percentDs = {
                label: '% POB confinado / alocado',
                data: ratio,
                type: 'line',
                yAxisID: 'yPercent',
                borderColor: '#00E5FF',
                backgroundColor: 'rgba(0,229,255,0.06)',
                tension: 0.3,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointStyle: 'rectRot',
                fill: false,
                borderWidth: 2,
                order: 2
            };

            // anexar série percentual (terceira série)
            prepared.datasets.push(percentDs);

            // Mesclar opções do backend com opções locais
            const backendOptions = (data.chart && data.chart.options) || {};
            const localOptions = {
                plugins: {
                    legend: { display: true, position: 'top', labels: { usePointStyle: true, boxWidth: 12 } },
                    title: { display: true, text: meta.group_by === 'month' ? 'Média de POB (mês)' : 'Média de POB (por dia)' },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            footer: (ctx) => {
                                try {
                                    const chart = ctx && ctx[0] && ctx[0].chart;
                                    const m = (chart && chart.options && chart.options.plugins && chart.options.plugins.meta) || meta;
                                    const idx = (ctx && ctx[0] && ctx[0].dataIndex) || 0;
                                    const rdos = (m.counts && m.counts.rdos_per_day && m.counts.rdos_per_day[idx]) || 0;
                                    const os = (m.counts && m.counts.distinct_os_per_day && m.counts.distinct_os_per_day[idx]) || 0;
                                    return [`RDOs: ${rdos}`, `OS distintos: ${os}`];
                                } catch (e) { return ''; }
                            }
                        }
                    },
                    meta: meta
                },
                scales: {
                    x: { stacked: false },
                    y: { beginAtZero: true, title: { display: true, text: 'POB (pessoas)' } },
                    yPercent: { 
                        position: 'right',
                        beginAtZero: true,
                        suggestedMax: 100,
                        ticks: { callback: v => `${Intl.NumberFormat('pt-BR').format(v)}%` },
                        grid: { display: false },
                        title: { display: true, text: '% POB confinado / alocado' }
                    }
                },
                // espacamento das barras para separar visualmente os grupos
                datasets: {
                    bar: {
                        categoryPercentage: 0.6,
                        barPercentage: 0.7
                    }
                }
            };
            
            const mergedOptions = {
                ...localOptions,
                ...backendOptions,
                scales: {
                    ...localOptions.scales,
                    ...backendOptions.scales,
                    x: {
                        ...localOptions.scales?.x,
                        ...backendOptions.scales?.x
                    },
                    y: {
                        ...localOptions.scales?.y,
                        ...backendOptions.scales?.y
                    },
                    yPercent: {
                        ...localOptions.scales?.yPercent,
                        ...backendOptions.scales?.yPercent
                    }
                },
                plugins: {
                    ...localOptions.plugins,
                    ...backendOptions.plugins
                }
            };

            updateChart('chartPobComparativo', 'bar', prepared, mergedOptions);

            return { key: 'pob_comparativo', data: data };
        } catch (error) {
            console.error('Erro ao carregar POB comparativo:', error);
            // mostra mensagem no card quando houver erro
            try {
                const canvas = document.getElementById('chartPobComparativo');
                const wrap = canvas && canvas.closest('.chart-wrapper');
                if (wrap) {
                    let no = wrap.querySelector('.no-data');
                    if (!no) {
                        no = document.createElement('div');
                        no.className = 'no-data';
                        no.textContent = 'Sem dados disponíveis';
                        wrap.appendChild(no);
                    } else {
                        no.textContent = 'Sem dados disponíveis';
                        no.style.display = 'block';
                    }
                }
            } catch(e) { /* ignore UI fallback errors */ }
        }
    }

    /**
     * Gráfico extra: Top Supervisores (ranking)
     */
    async function loadChartTopSupervisores(filters) {
        try {
            const data = await fetchChartData('/api/rdo-dashboard/top_supervisores/', filters);

            if (!data.success) {
                throw new Error(data.error || 'Erro desconhecido');
            }

            // Esperado: items com { name, value (percentual), value_raw, capacity_total, rd_count }
            const chartPayload = (data.chart && data.chart.labels) ? data.chart : {
                labels: (data.items || []).map(i => (i.name || i.username)),
                datasets: [{ label: 'Índice normalizado (%)', data: (data.items || []).map(i => Number(i.value) || 0) }]
            };

            // Preparar ordenação decrescente e manter items ordenados para tooltip/listas
            const originalItems = Array.isArray(data.items) ? data.items.slice() : [];
            const sortedItems = originalItems.slice().sort((a, b) => (Number(b.value || 0) - Number(a.value || 0)));
            const sortedLabels = sortedItems.map(i => (i.name || i.username || 'Desconhecido'));
            const sortedValues = sortedItems.map(i => Number(i.value || 0));

            // Voltar para barras verticais com cantos arredondados (design de ranking simples)
            // Sem alterar cores do tema: usar gradiente verde já aplicado no restante do dashboard
            let grad = '#149245';
            try {
                const ctxCanvas = document.getElementById('chartTopSupervisores')?.getContext('2d');
                if (ctxCanvas) {
                    const g = ctxCanvas.createLinearGradient(0, 0, 0, 240);
                    g.addColorStop(0, '#1B7A4B');
                    g.addColorStop(1, '#6fbf4f');
                    grad = g;
                }
            } catch(e) { /* fallback mantém cor sólida */ }

            const mainLabel = (chartPayload.datasets && chartPayload.datasets[0] && chartPayload.datasets[0].label) || 'Índice normalizado (%)';
            const prepared = {
                labels: sortedLabels,
                datasets: [{
                    label: mainLabel,
                    data: sortedValues,
                    backgroundColor: grad,
                    maxBarThickness: 64,
                    borderRadius: 8
                }]
            };

            // Renderizar como barras verticais de ranking com nomes no eixo X
            const backendOptions = (chartPayload.options) || {};
            const localOptions = {
                plugins: {
                    legend: { display: false },
                    title: { display: true, text: [
                        'Top Supervisores — Índice Normalizado (%)',
                        `${filters.start || ''} → ${filters.end || ''}`
                    ] },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const idx = ctx.dataIndex;
                                const it = (sortedItems || [])[idx] || {};
                                // em barras verticais, o valor está em ctx.parsed.y
                                const pct = Number(ctx.parsed.y || ctx.parsed) || 0;
                                const bruto = Number(it.value_raw || 0);
                                const cap = Number(it.capacity_total || 0);
                                const rd = Number(it.rd_count || 0);
                                return `Índice: ${pct.toFixed(2)}% | Bruto: ${Intl.NumberFormat('pt-BR').format(bruto)} m³ | Capacidade: ${Intl.NumberFormat('pt-BR').format(cap)} m³ | RDOs: ${rd}`;
                            }
                        }
                    }
                },
                layout: { padding: { left: 6, right: 14, top: 8, bottom: 4 } },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Índice (%)' },
                        ticks: { callback: v => `${Intl.NumberFormat('pt-BR').format(v)}%` }
                    },
                    x: {
                        type: 'category',
                        // mostrar os nomes dos supervisores ao invés de índices 0,1,2...
                        ticks: {
                            autoSkip: false,
                            maxRotation: 45,
                            minRotation: 0,
                            callback: (value, index) => (sortedLabels && sortedLabels[index] !== undefined) ? String(sortedLabels[index]) : String(value)
                        }
                    }
                }
            };
            
            const mergedOptions = {
                ...localOptions,
                ...backendOptions,
                scales: {
                    ...localOptions.scales,
                    ...backendOptions.scales,
                    x: {
                        ...localOptions.scales?.x,
                        ...backendOptions.scales?.x
                    },
                    y: {
                        ...localOptions.scales?.y,
                        ...backendOptions.scales?.y
                    }
                },
                plugins: {
                    ...localOptions.plugins,
                    ...backendOptions.plugins
                }
            };
            
            updateChart('chartTopSupervisores', 'bar', prepared, mergedOptions);

            // Preencher lista lateral (mostrar apenas TOP_N no card) e preparar modal com ranking completo
            const TOP_N = 4;
            const listEl = document.getElementById('top_supervisores_list');
            const viewAllBtn = document.getElementById('top_supervisores_view_all');
            const modalBackdrop = document.getElementById('rankingModalBackdrop');
            const modalList = document.getElementById('ranking_modal_list');
            const modalClose = document.getElementById('rankingModalClose');

            if (listEl) {
                listEl.innerHTML = '';
                const buildItem = (rank, name, pct, bruto, cap, rd) => {
                    const item = document.createElement('div');
                    item.className = `ranking-item ${rank <= 3 ? 'top-' + rank : ''}`;
                    const pctFmt = `${Number(pct || 0).toFixed(2)}%`;
                    const brutoFmt = `${Intl.NumberFormat('pt-BR').format(Number(bruto || 0))} m³`;
                    const safePct = Math.max(0, Math.min(100, Number(pct || 0)));
                    const capFmt = cap ? `${Intl.NumberFormat('pt-BR').format(Number(cap || 0))} m³` : 'Não disponível';
                    const rdFmt = Number(rd || 0);
                    // cálculo textual
                    let calcText = '';
                    if (cap && Number(cap) > 0) {
                        const calc = (Number(bruto || 0) / Number(cap || 1)) * 100;
                        calcText = `Cálculo: (${Intl.NumberFormat('pt-BR').format(Number(bruto || 0))} / ${Intl.NumberFormat('pt-BR').format(Number(cap || 0))}) × 100 = ${calc.toFixed(2)}%`;
                    } else {
                        calcText = 'Capacidade não disponível — índice baseado no volume bruto.';
                    }

                    item.innerHTML = `
                        <div class="ranking-row">
                            <span class="rank-badge">${rank}</span>
                            <span class="rank-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span class="rank-value">${pctFmt}</span>
                                <button class="detail-toggle" type="button">Detalhes</button>
                            </div>
                        </div>
                        <div class="rank-sub">${brutoFmt}</div>
                        <div class="rank-progress"><span style="width:${safePct}%"></span></div>
                        <div class="detail-box" style="display:none">
                            <div><strong>Bruto:</strong> ${brutoFmt}</div>
                            <div><strong>Capacidade:</strong> ${capFmt}</div>
                            <div><strong>RDOs:</strong> ${rdFmt}</div>
                            <div style="margin-top:6px">${calcText}</div>
                        </div>
                    `;
                    return item;
                };

                if (Array.isArray(sortedItems) && sortedItems.length) {
                    sortedItems.slice(0, TOP_N).forEach((it, idx) => {
                        const name = it.name || it.username || 'Desconhecido';
                        const pct = Number(it.value || 0);
                        const bruto = Number(it.value_raw || 0);
                        const cap = Number(it.capacity_total || 0);
                        const rd = Number(it.rd_count || 0);
                        listEl.appendChild(buildItem(idx + 1, name, pct, bruto, cap, rd));
                    });
                } else if (prepared.labels && prepared.labels.length) {
                    prepared.labels.slice(0, TOP_N).forEach((lab, idx) => {
                        const pct = Number(prepared.datasets[0].data[idx] || 0);
                        listEl.appendChild(buildItem(idx + 1, lab, pct, 0, 0, 0));
                    });
                } else {
                    listEl.innerHTML = '<div class="no-data">Sem dados</div>';
                }
                // Attach toggle handlers for detail buttons
                listEl.querySelectorAll('.detail-toggle').forEach(btn => {
                    btn.addEventListener('click', function(e){
                        const item = e.target.closest('.ranking-item');
                        if(!item) return;
                        const box = item.querySelector('.detail-box');
                        if(!box) return;
                        box.style.display = box.style.display === 'block' ? 'none' : 'block';
                    });
                });
                // global info toggle
                const infoBtn = document.getElementById('top_supervisores_info_btn');
                if(infoBtn){
                    infoBtn.addEventListener('click', function(){
                        const ex = document.getElementById('top_supervisores_explain');
                        if(!ex) return;
                        const visible = ex.style.display === 'block';
                        ex.style.display = visible ? 'none' : 'block';
                        infoBtn.setAttribute('aria-expanded', visible ? 'false' : 'true');
                    });
                }
            }

            // Modal: popular lista completa e abrir/fechar
            if(viewAllBtn && modalBackdrop && modalList){
                const renderFullModal = () => {
                    modalList.innerHTML = '';
                    if (!Array.isArray(sortedItems) || !sortedItems.length) {
                        modalList.innerHTML = '<div class="no-data">Sem dados</div>';
                        return;
                    }
                    sortedItems.forEach((it, idx) => {
                        const rank = idx + 1;
                        const pct = Number(it.value || 0);
                        const name = it.name || it.username || 'Desconhecido';
                        const brutoFmt = `${Intl.NumberFormat('pt-BR').format(Number(it.value_raw || 0))} m³`;
                        const capFmt = it.capacity_total ? `${Intl.NumberFormat('pt-BR').format(Number(it.capacity_total || 0))} m³` : 'Não disponível';
                        const rd = Number(it.rd_count || 0);
                        const row = document.createElement('div');
                        row.className = 'modal-ranking-row';
                        row.innerHTML = `
                            <div class="modal-rank">${rank}</div>
                            <div class="modal-content">
                                <div class="modal-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
                                <div class="modal-meta">${rd} RDO(s) • Capacidade: ${capFmt} • Bruto: ${brutoFmt}</div>
                            </div>
                            <div class="modal-value">${pct.toFixed(2)}%</div>
                        `;
                        modalList.appendChild(row);
                    });
                };

                viewAllBtn.removeEventListener && viewAllBtn.removeEventListener('click', renderFullModal);
                viewAllBtn.addEventListener('click', function(e){
                    e.preventDefault();
                    renderFullModal();
                    modalBackdrop.classList.add('open');
                    modalBackdrop.setAttribute('aria-hidden', 'false');
                    modalClose && modalClose.focus();
                });

                modalClose && modalClose.addEventListener('click', function(){
                    modalBackdrop.classList.remove('open');
                    modalBackdrop.setAttribute('aria-hidden', 'true');
                });

                modalBackdrop && modalBackdrop.addEventListener('click', function(ev){
                    if(ev.target === modalBackdrop){
                        modalBackdrop.classList.remove('open');
                        modalBackdrop.setAttribute('aria-hidden', 'true');
                    }
                });
            }

            return { key: 'top_supervisores', data: data };
        } catch (error) {
            console.error('Erro ao carregar Top Supervisores:', error);
        }
    }

/**
 * Helpers para KPIs e sparklines
 */
function sumDatasets(data){
    // espera estrutura: { labels: [], datasets: [{data: [...]}, ...] }
    if(!data || !data.datasets) return 0;
    let total = 0;
    data.datasets.forEach(ds => {
        if(Array.isArray(ds.data)){
            ds.data.forEach(v => { total += Number(v) || 0; });
        }
    });
    return total;
}

function animateValue(elId, start, end, duration = 800, decimals = 0){
    const el = document.getElementById(elId);
    if(!el) return;
    const range = end - start;
    let startTime = null;
    function step(timestamp){
        if(!startTime) startTime = timestamp;
        const progress = Math.min((timestamp - startTime) / duration, 1);
        const value = start + range * progress;
        // Formata com N casas decimais conforme pedido (pt-BR)
        const formatted = value.toLocaleString('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
        el.textContent = formatted;
        if(progress < 1) window.requestAnimationFrame(step);
    }
    window.requestAnimationFrame(step);
}

// Formata um número de horas (float) em "HH:MM" (ex: 1.5 -> "1:30")
function formatHoursToHHMM(hoursFloat){
    if(!isFinite(hoursFloat) || hoursFloat === null) return '--';
    const totalMinutes = Math.round(Number(hoursFloat) * 60);
    const hh = Math.floor(totalMinutes / 60);
    const mm = totalMinutes % 60;
    return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
}

function setTextById(id, text){
    try{
        const el = document.getElementById(id);
        if(el) el.textContent = text;
    }catch(e){ /* ignore */ }
}
function renderSparkline(canvasId, data){
    try{
        const ctx = document.getElementById(canvasId);
        if(!ctx) return;
        // travar dimensoes do sparkline para evitar overflow do canvas no card
        // sem deixar o grafico baixo demais (usa altura definida no CSS quando existir)
        const cssHeight = Number.parseFloat(window.getComputedStyle(ctx).height || '0');
        const SPARK_HEIGHT = Math.max(52, Math.round(isFinite(cssHeight) ? cssHeight : 0));
        ctx.style.width = '100%';
        ctx.style.maxWidth = '100%';
        ctx.style.height = SPARK_HEIGHT + 'px';
        ctx.style.maxHeight = SPARK_HEIGHT + 'px';
        const parentWidth = ctx.parentElement ? Number(ctx.parentElement.clientWidth || 0) : 0;
        if(parentWidth > 0){
            ctx.width = Math.max(80, Math.floor(parentWidth));
        }
        ctx.height = SPARK_HEIGHT;
        // small, non-responsive sparkline
        if(charts[canvasId]) charts[canvasId].destroy();
        charts[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels || [],
                datasets: [{
                    data: (data.datasets && data.datasets[0] && data.datasets[0].data) || [],
                    borderColor: '#1b7a4b',
                    backgroundColor: 'rgba(27,122,75,0.08)',
                    pointRadius: 0,
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {responsive:false, maintainAspectRatio:false, scales:{x:{display:false}, y:{display:false}}, plugins:{legend:{display:false}}}
        });
    }catch(e){console.debug('sparkline error', e)}
}

function updateKPIs(results){
    // results é um array com objetos {key, data}
    const map = {};
    results.forEach(r => { if(r && r.key) map[r.key] = r.data; });

    // HH Confinado (mostrar em HH:MM, sem arredondamento para inteiro)
    const hhConfinadoTotal = sumDatasets(map['hh_confinado']);
    const hhConfinadoFmt = formatHoursToHHMM(hhConfinadoTotal);
    const hhConfEl = document.getElementById('kpi_hh_confinado_value');
    if(hhConfEl){
        const intVal = Math.round(hhConfinadoTotal || 0);
        hhConfEl.innerHTML = `<div class="value-main"><span id="kpi_hh_confinado_int">${intVal}</span><span class="value-unit">h</span></div><span class="value-sep">-</span><div class="value-badge">${hhConfinadoFmt}</div>`;
        // animate integer part
        animateValue('kpi_hh_confinado_int', 0, intVal, 700, 0);
    }
    renderSparkline('kpi_hh_confinado_spark', map['hh_confinado'] || {});

    // HH Fora (mostrar em HH:MM)
    const hhForaTotal = sumDatasets(map['hh_fora']);
    const hhForaFmt = formatHoursToHHMM(hhForaTotal);
    const hhForaEl = document.getElementById('kpi_hh_fora_value');
    if(hhForaEl){
        const intVal = Math.round(hhForaTotal || 0);
        hhForaEl.innerHTML = `<div class="value-main"><span id="kpi_hh_fora_int">${intVal}</span><span class="value-unit">h</span></div><span class="value-sep">-</span><div class="value-badge">${hhForaFmt}</div>`;
        animateValue('kpi_hh_fora_int', 0, intVal, 700, 0);
    }
    renderSparkline('kpi_hh_fora_spark', map['hh_fora'] || {});

    // Ensacamento
    const ensacTotal = sumDatasets(map['ensacamento']);
    animateValue('kpi_ensacamento_value', 0, Math.round(ensacTotal), 800, 0);
    renderSparkline('kpi_ensacamento_spark', map['ensacamento'] || {});

    // Tambores
    const tambTotal = sumDatasets(map['tambores']);
    animateValue('kpi_tambores_value', 0, Math.round(tambTotal), 800, 0);
    renderSparkline('kpi_tambores_spark', map['tambores'] || {});

    // Líquido
    const liquidoTotal = sumDatasets(map['total_liquido']);
    // Mostrar líquido com 3 casas decimais
    animateValue('kpi_liquido_value', 0, liquidoTotal, 800, 3);
    renderSparkline('kpi_liquido_spark', map['total_liquido'] || {});

    // Tempo de uso da bomba (horas)
    try{
        const bombaTotal = sumDatasets(map['tempo_bomba']);
        const bombaFmt = formatHoursToHHMM(bombaTotal);
        const bombaEl = document.getElementById('kpi_tempo_bomba_value');
        if(bombaEl){
            const intVal = Math.round(bombaTotal || 0);
            bombaEl.innerHTML = `<div class="value-main"><span id="kpi_tempo_bomba_int">${intVal}</span><span class="value-unit">h</span></div><span class="value-sep">-</span><div class="value-badge">${bombaFmt}</div>`;
            try{ animateValue('kpi_tempo_bomba_int', 0, intVal, 800, 0); }catch(e){}
        }
        renderSparkline('kpi_tempo_bomba_spark', map['tempo_bomba'] || {});
    }catch(e){ console.debug('Falha ao atualizar KPI tempo_bomba', e); }
}

/**
 * Carrega as opções de Ordens de Serviço abertas
 */
async function loadOrdensSevico() {
    try {
        const response = await fetch('/rdo/api/get_ordens_servico/');
        const data = await response.json();
        if (!data || !data.success) return true;
        const list = document.getElementById('os_existente_datalist');
        if (!list) return true;
        list.innerHTML = '';
        data.items.forEach(os => {
            const option = document.createElement('option');
            // mostrar numero_os para o usuário; backend aceitará número ou id
            option.value = os.numero_os !== undefined && os.numero_os !== null ? String(os.numero_os) : String(os.id);
            list.appendChild(option);
        });
        // Compatibilidade: popular um select antigo `os_existente_select` caso outros scripts o usem
        try{
            let sel = document.getElementById('os_existente_select');
            if(!sel){
                sel = document.createElement('select');
                sel.id = 'os_existente_select';
                sel.name = 'os_existente';
                sel.style.display = 'none';
                document.body.appendChild(sel);
            }
            // limpar e adicionar opções
            sel.innerHTML = '';
            const defOpt = document.createElement('option'); defOpt.value = ''; defOpt.text = 'Todas'; sel.appendChild(defOpt);
            data.items.forEach(os => {
                const o = document.createElement('option');
                o.value = String(os.id || os.numero_os || '');
                o.text = os.numero_os ? (`OS ${os.numero_os}`) : (`OS ${os.id}`);
                sel.appendChild(o);
            });
        }catch(e){/* ignore compat errors */}
        return true;
    } catch (error) {
        console.error('Erro ao carregar Ordens de Serviço:', error);
        return true;
    }
}

/**
 * Função auxiliar para mostrar notificações (se disponível)
 */
function showNotification(message, type = 'info') {
    // Se houver um sistema de notificações disponível, usar
    if (typeof displayNotification === 'function') {
        displayNotification(message, type);
    } else {
        // Fallback: alert simples
        alert(message);
    }
}

/**
 * Event listeners para filtros
 */
document.addEventListener('DOMContentLoaded', function() {
    // Carregar opções de OS e depois carregar dashboard
    loadOrdensSevico().then(() => {
        loadDashboard();
    });
    
    // Permitir Enter para aplicar filtros
    const filterInputs = document.querySelectorAll('.filter-group input, .filter-group select');
    filterInputs.forEach(input => {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                loadDashboard();
            }
        });
    });

    // Criar botão de alternância Tabela <-> Cards (sem modificar HTML diretamente)
    try{
        const toolbar = document.querySelector('.toolbar-actions') || document.querySelector('.filters-panel') || document.body;
        if(toolbar && !document.getElementById('summary-view-toggle-btn')){
            const btn = document.createElement('button');
            btn.id = 'summary-view-toggle-btn';
            btn.type = 'button';
            btn.className = 'Btn';
            const current = (typeof getSummaryViewMode === 'function' && getSummaryViewMode() === 'cards') ? 'Tabela' : 'Cards';
            btn.textContent = current;
            btn.style.marginLeft = '8px';
            btn.onclick = toggleSummaryView;
            toolbar.appendChild(btn);
        }
    }catch(e){console.debug('Não foi possível criar toggle de visualização', e)}
});

// --- TV Mode helpers: ativar via ?tv=1 ---
function isTVMode(){
    try { return new URLSearchParams(window.location.search).get('tv') === '1'; } catch(e){ return false; }
}

// requestFullscreen com verificação e fallback para overlay de instrução
let __tv_wake_lock = null;
async function requestFullscreenSafe(){
    try{
        if(document.fullscreenElement) return true;
        if(document.documentElement.requestFullscreen){
            await document.documentElement.requestFullscreen();
            return true;
        }
    }catch(e){
        console.debug('requestFullscreen failed:', e);
    }
    return false;
}

function createFullscreenPrompt(){
    // já existe? evita duplicar
    if(document.getElementById('tv-fullscreen-prompt')) return;
    const overlay = document.createElement('div');
    overlay.id = 'tv-fullscreen-prompt';
    overlay.style.position = 'fixed';
    overlay.style.inset = '12px';
    overlay.style.zIndex = 2147483646;
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';
    overlay.style.pointerEvents = 'auto';
    overlay.style.background = 'rgba(0,0,0,0.35)';
    overlay.innerHTML = `
        <div style="background:#fff;padding:22px 28px;border-radius:12px;max-width:820px;box-shadow:0 8px 30px rgba(0,0,0,0.4);text-align:center;font-family:Inter, system-ui;">
            <div style="font-size:20px;font-weight:800;color:#0b0b0b;margin-bottom:8px">Ativar Tela Cheia</div>
            <div style="font-size:14px;color:#334155;margin-bottom:14px">O navegador bloqueou o modo de tela cheia automático. Clique no botão abaixo para entrar em tela cheia.</div>
            <div style="display:flex;gap:12px;justify-content:center">
                <button id="tv-enter-full-btn" style="background:var(--accent-1);color:#fff;border:0;padding:10px 16px;border-radius:8px;font-weight:700;">Entrar em Tela Cheia</button>
                <button id="tv-dismiss-full-btn" style="background:transparent;border:1px solid rgba(0,0,0,0.08);padding:10px 14px;border-radius:8px;">Fechar</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    document.getElementById('tv-enter-full-btn').addEventListener('click', async function(){
        await requestFullscreenSafe();
        const el = document.getElementById('tv-fullscreen-prompt'); if(el) el.remove();
    });
    document.getElementById('tv-dismiss-full-btn').addEventListener('click', function(){
        const el = document.getElementById('tv-fullscreen-prompt'); if(el) el.remove();
    });
}

async function requestWakeLock(){
    try{
        if('wakeLock' in navigator){
            __tv_wake_lock = await navigator.wakeLock.request('screen');
            __tv_wake_lock.addEventListener('release', () => { __tv_wake_lock = null; });
            console.debug('WakeLock acquired');
        }
    }catch(e){ console.debug('WakeLock error', e); }
}

function setupVisibilityHandlerForWakeLock(){
    document.addEventListener('visibilitychange', async () => {
        if(document.visibilityState === 'visible' && document.body.classList.contains('tv-mode')){
            if(!__tv_wake_lock) await requestWakeLock();
        }
    });
}

async function enableTVMode(){
    try {
        document.body.classList.add('tv-mode');
        const hide = document.querySelectorAll('.filters-panel, .toolbar-actions, .mobile-bottom-nav, #drawer-nav, footer, .logout-overlay');
        hide.forEach(e => { if(e) e.style.display = 'none'; });

        // Tentar fullscreen automático
        const ok = await requestFullscreenSafe();
        if(!ok){
            // mostrar sugestão visual para o usuário disparar fullscreen manualmente
            createFullscreenPrompt();
        }

        // tentar adquirir Wake Lock para evitar dim/tela desligando
        await requestWakeLock();
        setupVisibilityHandlerForWakeLock();

        // recarregar dashboard para garantir layout dos charts
        loadDashboard();
        // recarregamento periódico (3 minutos)
        setInterval(loadDashboard, 3 * 60 * 1000);
    } catch(e){ console.debug('enableTVMode error', e); }
}

// Se ?tv=1 na URL, ativar automaticamente
if (isTVMode()){
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', enableTVMode);
    } else {
        enableTVMode();
    }
}

// --- Auto-refresh global (polling) ---
let __auto_refresh_timer = null;
function clearAutoRefresh(){
    if(__auto_refresh_timer){
        clearInterval(__auto_refresh_timer);
        __auto_refresh_timer = null;
    }
}

function getAutoRefreshSeconds(){
    try{
        const qp = new URLSearchParams(window.location.search);
        const q = qp.get('autorefresh');
        if(q !== null){
            const n = Number(q);
            if(!isNaN(n) && n > 0) return Math.max(5, Math.floor(n)); // mínimo 5s
        }
    }catch(e){}
    // fallback para preferências do usuário salvas
    try{
        const saved = localStorage.getItem('dashboard_autorefresh_seconds');
        const n = Number(saved);
        if(!isNaN(n) && n > 0) return Math.max(5, Math.floor(n));
    }catch(e){}
    // Valor padrão quando não há parâmetro na URL nem preferência salva.
    // Ajuste aqui para alterar o comportamento global (segundos).
    return 60; // 60s = ativado por padrão
}

function setAutoRefreshSeconds(sec){
    try{ localStorage.setItem('dashboard_autorefresh_seconds', String(sec)); }catch(e){}
    initAutoRefresh();
}

function initAutoRefresh(){
    clearAutoRefresh();
    const secs = getAutoRefreshSeconds();
    if(secs > 0){
        // desfazer timer do modo TV (evita duplicata)
        __auto_refresh_timer = setInterval(() => {
            try{ loadDashboard(); }catch(e){ console.debug('auto-refresh error', e); }
        }, secs * 1000);
        console.info('Auto-refresh habilitado: ' + secs + 's');
    } else {
        console.info('Auto-refresh desabilitado');
    }
}

// Inicializar auto-refresh após DOM pronto
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAutoRefresh);
} else {
    initAutoRefresh();
}
