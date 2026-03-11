// Variáveis globais para os gráficos
let charts = {};
let __tempo_bomba_carousel_timer = null;
const __tempo_bomba_view_state = {
    mode: 'auto', // auto
    paused: false,
    hoverPause: false,
    intervalSec: 20,
    currentTankLabel: ''
};

function clearTempoBombaCarouselTimer(){
    if(__tempo_bomba_carousel_timer){
        clearInterval(__tempo_bomba_carousel_timer);
        __tempo_bomba_carousel_timer = null;
    }
}

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

function toRoundedInt(value){
    const numeric = Number(value || 0);
    if(!Number.isFinite(numeric)) return 0;
    return Math.round(numeric);
}

function formatNumberPt(value, digits = 2){
    const numeric = Number(value || 0);
    const safe = Number.isFinite(numeric) ? numeric : 0;
    return Intl.NumberFormat('pt-BR', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits
    }).format(safe);
}

function formatPercentPt(value, digits = 1){
    return formatNumberPt(value, digits);
}

function isMetodoValido(label){
    const raw = String(label === null || label === undefined ? '' : label).trim();
    if(!raw) return false;
    const normalized = raw
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]/g, '');
    if(!normalized) return false;
    const invalid = new Set([
        'na', 'nd', 'null', 'none', 'desconhecido',
        'semmetodo', 'naoinformado', 'naoseaplica'
    ]);
    return !invalid.has(normalized);
}

function renderMetodoEficaciaLegend(items, colors, totalIndice, mediaConclusao){
    const legendEl = document.getElementById('chartMetodoEficaciaLegend');
    const helpEl = document.getElementById('chartMetodoEficaciaHelp');
    if(!legendEl){
        if(helpEl){
            helpEl.textContent = 'Gráfico circular: participação do índice de eficácia por método.';
        }
        return;
    }

    if(!Array.isArray(items) || !items.length){
        legendEl.innerHTML = '<div class="metodo-eficacia-empty">Sem dados para o período filtrado.</div>';
        if(helpEl){
            helpEl.textContent = 'Sem dados suficientes para montar o gráfico de eficácia (N/A e vazios não entram no cálculo).';
        }
        return;
    }

    const totalSafe = Number(totalIndice) > 0 ? Number(totalIndice) : 0;
    const mediaSafe = Number.isFinite(Number(mediaConclusao)) ? Number(mediaConclusao) : 0;

    const rows = items.map((item, idx) => {
        const cor = colors[idx] || '#22c55e';
        const participacao = totalSafe > 0 ? (item.indice / totalSafe) * 100 : 0;
        const metodo = escapeHtml(String(item.label || 'N/A'));
        const meta = `Índice ${formatNumberPt(item.indice, 2)} · Conclusão ${formatPercentPt(item.taxaConclusao, 1)}% · F:${item.finalizadas} A:${item.andamento}`;
        return `
            <div class="metodo-eficacia-row" title="${escapeHtml(meta)}">
                <div class="metodo-eficacia-main">
                    <div class="metodo-eficacia-method">
                        <span class="metodo-eficacia-dot" style="background:${cor}"></span>
                        <span class="metodo-eficacia-label">${metodo}</span>
                    </div>
                    <div class="metodo-eficacia-meta">${escapeHtml(meta)}</div>
                </div>
                <div class="metodo-eficacia-share">${formatPercentPt(participacao, 1)}%</div>
            </div>
        `;
    }).join('');

    legendEl.innerHTML = `
        <div class="metodo-eficacia-legend-head">
            <span>Métodos</span>
            <span>Participação</span>
        </div>
        ${rows}
    `;

    if(helpEl){
        helpEl.textContent = `Centro do gráfico: média ponderada da taxa de conclusão (${formatPercentPt(mediaSafe, 1)}%). N/A e vazios não são contabilizados.`;
    }
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
        toRoundedInt(it.sum_operadores_simultaneos || 0),
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
                loadChartMetodoEficacia(filters),
                loadHeatmapMetodoSupervisor(filters),
                loadChartBacklogCoordenador(filters),
                loadChartTaxaConclusaoCoordenador(filters),
                    loadChartTempoBomba(filters),
                    loadOsStatusSummary(filters),
                        loadOsMovimentacoes(filters),
                        loadKpiTotals(filters),
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
 * Gráfico novo: Eficácia por Método (Finalizada x Em Andamento)
 */
async function loadChartMetodoEficacia(filters) {
    try {
        const data = await fetchChartData('/api/rdo-dashboard/metodos_eficacia_por_dias/', filters);
        if (!data || !data.success) {
            throw new Error(data && data.error ? data.error : 'Erro desconhecido');
        }

        const labels = Array.isArray(data.labels) ? data.labels : [];
        const values = Array.isArray(data.efficacy_index) ? data.efficacy_index : [];
        const finalizadas = Array.isArray(data.finalizadas_counts) ? data.finalizadas_counts : [];
        const andamento = Array.isArray(data.andamento_counts) ? data.andamento_counts : [];

        const items = labels.map((label, idx) => {
            const indice = Math.max(0, Number(values[idx] || 0));
            const fin = Math.max(0, Number(finalizadas[idx] || 0));
            const andm = Math.max(0, Number(andamento[idx] || 0));
            const total = fin + andm;
            const taxa = total > 0 ? (fin / total) * 100 : 0;
            return {
                label: String(label || 'N/A'),
                indice: Number.isFinite(indice) ? indice : 0,
                finalizadas: Number.isFinite(fin) ? fin : 0,
                andamento: Number.isFinite(andm) ? andm : 0,
                totalOps: total,
                taxaConclusao: Number.isFinite(taxa) ? taxa : 0
            };
        }).filter(item => isMetodoValido(item.label))
          .sort((a, b) => (b.indice - a.indice) || (b.taxaConclusao - a.taxaConclusao));

        const palette = [
            '#22c55e', '#38bdf8', '#f59e0b', '#ef4444', '#a78bfa',
            '#14b8a6', '#f97316', '#eab308', '#3b82f6', '#84cc16'
        ];
        const colors = items.map((_, idx) => palette[idx % palette.length]);
        const totalIndice = items.reduce((acc, item) => acc + (Number(item.indice) || 0), 0);
        const totalOps = items.reduce((acc, item) => acc + (Number(item.totalOps) || 0), 0);
        const mediaConclusaoPonderada = totalOps > 0
            ? items.reduce((acc, item) => acc + ((Number(item.taxaConclusao) || 0) * (Number(item.totalOps) || 0)), 0) / totalOps
            : 0;

        const prepared = {
            labels: items.map(item => item.label),
            datasets: [{
                label: 'Participação do índice de eficácia',
                data: items.map(item => Number(item.indice || 0)),
                backgroundColor: colors,
                borderColor: colors.map(() => 'rgba(255,255,255,0.22)'),
                borderWidth: 1,
                hoverOffset: 8,
                spacing: 2
            }]
        };

        const isDark = !!(document.body && document.body.classList && document.body.classList.contains('dark-mode'));
        const options = {
            animation: {
                duration: 900,
                easing: 'easeOutQuart'
            },
            cutout: '58%',
            layout: {
                padding: { top: 6, right: 6, bottom: 6, left: 6 }
            },
            plugins: {
                legend: { display: false },
                centerText: {
                    text: totalOps > 0 ? `${formatPercentPt(mediaConclusaoPonderada, 1)}%` : '--',
                    color: isDark ? 'rgba(255,255,255,0.92)' : 'rgba(15,23,42,0.92)',
                    font: '800 20px Inter, system-ui, -apple-system, "Segoe UI", Roboto'
                },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            const idx = context && context[0] ? context[0].dataIndex : 0;
                            return items[idx] ? items[idx].label : 'Método';
                        },
                        label: function(ctx) {
                            const idx = Number(ctx.dataIndex || 0);
                            const item = items[idx];
                            if(!item) return '';
                            const participacao = totalIndice > 0 ? (item.indice / totalIndice) * 100 : 0;
                            return `Índice: ${formatNumberPt(item.indice, 2)} · Participação: ${formatPercentPt(participacao, 1)}%`;
                        },
                        afterLabel: function(ctx) {
                            const idx = Number(ctx.dataIndex || 0);
                            const item = items[idx];
                            if(!item) return '';
                            return `Conclusão: ${formatPercentPt(item.taxaConclusao, 1)}% · Finalizadas: ${item.finalizadas} · Em andamento: ${item.andamento}`;
                        }
                    }
                }
            },
            scales: {}
        };
        options.__preserveDatasetColors = true;

        updateChart('chartMetodoEficacia', 'doughnut', prepared, options);
        renderMetodoEficaciaLegend(items, colors, totalIndice, mediaConclusaoPonderada);

        return { key: 'metodos_eficacia', data: data };
    } catch (error) {
        renderMetodoEficaciaLegend([], [], 0, 0);
        console.error('Erro ao carregar Eficácia por Método:', error);
    }
}

function renderFunilStatusFromSummary(summary){
    const canvas = document.getElementById('chartFunilOSStatus');
    if(!canvas) return;

    const prog = Number(summary && summary.programada || 0);
    const andm = Number(summary && summary.em_andamento || 0);
    const fin = Number(summary && summary.finalizada || 0);
    const par = Number(summary && summary.paralizada || 0);
    const can = Number(summary && summary.cancelada || 0);

    const chartData = {
        labels: ['Programada', 'Em Andamento', 'Finalizada'],
        datasets: [{
            label: 'Quantidade de OS',
            data: [prog, andm, fin],
            backgroundColor: ['#f59e0b', '#38bdf8', '#22c55e'],
            borderColor: ['#d97706', '#0284c7', '#16a34a'],
            borderWidth: 1,
            borderRadius: 12,
            borderSkipped: false,
            maxBarThickness: 42
        }]
    };

    const convProgAnd = prog > 0 ? (andm / prog) * 100 : 0;
    const convAndFin = andm > 0 ? (fin / andm) * 100 : 0;
    const convProgFin = prog > 0 ? (fin / prog) * 100 : 0;

    const options = {
        indexAxis: 'y',
        plugins: {
            legend: { display: false },
            tooltip: {
                callbacks: {
                    label: function(ctx){
                        const value = Number(ctx.parsed && (ctx.parsed.x !== undefined ? ctx.parsed.x : ctx.parsed.y) || 0);
                        return `OS: ${Intl.NumberFormat('pt-BR').format(value)}`;
                    }
                }
            },
            barValuePlugin: { maxLabels: 10 }
        },
        scales: {
            x: {
                beginAtZero: true,
                title: { display: true, text: 'Quantidade de OS' },
                grid: { color: 'rgba(148, 163, 184, 0.16)' }
            },
            y: {
                grid: { display: false }
            }
        }
    };
    options.__preserveDatasetColors = true;
    updateChart('chartFunilOSStatus', 'bar', chartData, options);

    const info = document.getElementById('funil_status_insights');
    if(info){
        info.innerHTML = `
            <span class="funil-chip">Prog -> And: <b>${formatPercentPt(convProgAnd, 1)}%</b></span>
            <span class="funil-chip">And -> Fin: <b>${formatPercentPt(convAndFin, 1)}%</b></span>
            <span class="funil-chip">Prog -> Fin: <b>${formatPercentPt(convProgFin, 1)}%</b></span>
            <span class="funil-chip">Paralizada: <b>${Intl.NumberFormat('pt-BR').format(par)}</b></span>
            <span class="funil-chip">Cancelada: <b>${Intl.NumberFormat('pt-BR').format(can)}</b></span>
        `;
    }
}

function renderAgingEmAndamentoFromSummary(summary){
    const canvas = document.getElementById('chartAgingEmAndamento');
    const oldestListEl = document.getElementById('aging_status_oldest');
    if(!canvas) return;

    const defaultLabels = ['0-2 d/serv', '3-5 d/serv', '6-10 d/serv', '11+ d/serv', 'Sem inicio'];
    const aging = summary && summary.aging_em_andamento ? summary.aging_em_andamento : {};
    const labels = Array.isArray(aging.labels) && aging.labels.length ? aging.labels : defaultLabels;
    const rawValues = Array.isArray(aging.values) ? aging.values : [0, 0, 0, 0, 0];
    const topOldest = Array.isArray(aging.top_oldest_os) ? aging.top_oldest_os : [];
    const values = labels.map((_, idx) => {
        const val = Number(rawValues[idx] || 0);
        return Number.isFinite(val) && val > 0 ? val : 0;
    });

    const total = values.reduce((acc, n) => acc + n, 0);
    const avgDaysPerService = Number(aging.avg_days_per_service || 0);
    const worstDaysPerService = Number(aging.worst_days_per_service || 0);
    const oldestDays = Number(aging.oldest_days || 0);
    const semInicio = Number(aging.sem_inicio || 0);
    const leaderBucket = String(aging.leader_bucket || '-');

    const chartData = {
        labels,
        datasets: [{
            label: 'OS em andamento',
            data: values,
            backgroundColor: ['#16a34a', '#22c55e', '#f59e0b', '#ef4444', '#94a3b8'],
            borderColor: ['#15803d', '#16a34a', '#d97706', '#dc2626', '#64748b'],
            borderWidth: 1,
            borderRadius: 12,
            borderSkipped: false,
            maxBarThickness: 36
        }]
    };

    const options = {
        indexAxis: 'y',
        plugins: {
            legend: { display: false },
            tooltip: {
                callbacks: {
                    label: function(ctx){
                        const value = Number(ctx.parsed && (ctx.parsed.x !== undefined ? ctx.parsed.x : ctx.parsed.y) || 0);
                        const pct = total > 0 ? (value / total) * 100 : 0;
                        return `OS: ${Intl.NumberFormat('pt-BR').format(value)} (${formatPercentPt(pct, 1)}%)`;
                    }
                }
            },
            barValuePlugin: { maxLabels: 10 }
        },
        scales: {
            x: {
                beginAtZero: true,
                title: { display: true, text: 'Quantidade de OS' },
                grid: { color: 'rgba(148, 163, 184, 0.16)' }
            },
            y: { grid: { display: false } }
        }
    };
    options.__preserveDatasetColors = true;
    updateChart('chartAgingEmAndamento', 'bar', chartData, options);

    const info = document.getElementById('aging_status_insights');
    if(info){
        info.innerHTML = `
            <span class="funil-chip">Em andamento: <b>${Intl.NumberFormat('pt-BR').format(total)}</b></span>
            <span class="funil-chip">Média (d/serv): <b>${formatNumberPt(avgDaysPerService, 2)}</b></span>
            <span class="funil-chip">Pior (d/serv): <b>${formatNumberPt(worstDaysPerService, 2)}</b></span>
            <span class="funil-chip">Mais antiga: <b>${Intl.NumberFormat('pt-BR').format(oldestDays)}d</b></span>
            <span class="funil-chip">Faixa líder: <b>${escapeHtml(leaderBucket)}</b></span>
            <span class="funil-chip">Sem início: <b>${Intl.NumberFormat('pt-BR').format(semInicio)}</b></span>
        `;
    }

    if(oldestListEl){
        if(!topOldest.length){
            oldestListEl.innerHTML = '<div class="aging-oldest-empty">Sem OS em andamento para o período.</div>';
        }else{
            oldestListEl.innerHTML = topOldest.map((item) => {
                const numeroOs = escapeHtml(String(item && item.numero_os ? item.numero_os : '-'));
                const dias = Number(item && item.dias || 0);
                const qtdServicos = Number(item && item.qtd_servicos || 0);
                const qtdExecucoesServico = Number(item && item.qtd_execucoes_servico || 0);
                const diasPorServico = Number(item && item.dias_por_servico || 0);
                const servicosResumo = escapeHtml(String(item && item.servicos_resumo ? item.servicos_resumo : 'Servico nao informado'));
                return `
                    <div class="aging-oldest-row">
                        <div class="aging-oldest-main">
                            <span class="aging-oldest-os">OS ${numeroOs}</span>
                            <span class="aging-oldest-service" title="${servicosResumo}">${servicosResumo}</span>
                        </div>
                        <div class="aging-oldest-side">
                            <span class="aging-oldest-meta">${Intl.NumberFormat('pt-BR').format(dias)}d · ${Intl.NumberFormat('pt-BR').format(qtdServicos)} tipos · ${Intl.NumberFormat('pt-BR').format(qtdExecucoesServico)} regs</span>
                            <span class="aging-oldest-days">${formatNumberPt(diasPorServico, 2)} d/serv</span>
                        </div>
                    </div>
                `;
            }).join('');
        }
    }
}

function colorForHeatmapScore(score, maxScore){
    const value = Number(score || 0);
    const max = Number(maxScore || 0);
    if(!Number.isFinite(value) || value <= 0 || max <= 0){
        return 'rgba(148, 163, 184, 0.16)';
    }
    const ratio = Math.max(0, Math.min(1, value / max));
    const hue = 8 + Math.round(ratio * 120); // vermelho -> verde
    const sat = 76;
    const light = 20 + (ratio * 28);
    return `hsla(${hue}, ${sat}%, ${light}%, 0.9)`;
}

function renderHeatmapMetodoSupervisor(payload){
    const wrap = document.getElementById('heatmapMetodoSupervisorWrap');
    const meta = document.getElementById('heatmapMetodoSupervisorMeta');
    if(!wrap) return;

    const methods = payload && Array.isArray(payload.methods) ? payload.methods : [];
    const supervisors = payload && Array.isArray(payload.supervisors) ? payload.supervisors : [];
    const scores = payload && Array.isArray(payload.scores) ? payload.scores : [];
    const details = payload && Array.isArray(payload.details) ? payload.details : [];
    const maxScore = Number(payload && payload.max_score || 0);
    const periodFallback = Boolean(payload && payload.period_fallback);

    if(!methods.length || !supervisors.length){
        wrap.innerHTML = '<div class="heatmap-empty">Sem dados para este período.</div>';
        if(meta){
            meta.textContent = 'Cor representa o índice de eficácia da célula (N/A não contabilizado).';
        }
        return;
    }

    const headerCells = methods.map((m) => `<th>${escapeHtml(String(m || '-'))}</th>`).join('');
    const rowHtml = supervisors.map((sup, rIdx) => {
        const cells = methods.map((_, cIdx) => {
            const score = Number((scores[rIdx] && scores[rIdx][cIdx]) || 0);
            const d = (details[rIdx] && details[rIdx][cIdx]) || {};
            const valueLabel = d.has_data ? `${formatPercentPt(score, 1)}%` : '--';
            const title = d.has_data
                ? `Indice ${formatPercentPt(score, 1)}% | Conclusao ${formatPercentPt(d.completion_rate || 0, 1)}% | Finalizadas ${d.finalizadas || 0} | Em andamento ${d.andamento || 0}`
                : 'Sem dados';
            return `<td class="heatmap-cell" style="background:${colorForHeatmapScore(score, maxScore)}" title="${escapeHtml(title)}">${valueLabel}</td>`;
        }).join('');
        return `<tr><th class="sticky-col">${escapeHtml(String(sup || 'Sem supervisor'))}</th>${cells}</tr>`;
    }).join('');

    wrap.innerHTML = `
        <table class="heatmap-table">
            <thead>
                <tr><th class="sticky-col">Supervisor</th>${headerCells}</tr>
            </thead>
            <tbody>${rowHtml}</tbody>
        </table>
    `;

    if(meta){
        meta.textContent = periodFallback
            ? `Sem dados no período informado; exibindo dados sem corte de data para os filtros atuais. Supervisores exibidos: ${supervisors.length}.`
            : `Cor mais intensa = maior índice de eficácia. Supervisores exibidos: ${supervisors.length}.`;
    }
}

async function loadHeatmapMetodoSupervisor(filters){
    try{
        const resp = await fetchChartData('/api/rdo-dashboard/heatmap_metodo_supervisor/', filters);
        if(!resp || !resp.success){
            console.warn('Falha ao obter heatmap método x supervisor', resp);
            renderHeatmapMetodoSupervisor(null);
            return { key: 'heatmap_metodo_supervisor', data: {} };
        }
        renderHeatmapMetodoSupervisor(resp);
        return { key: 'heatmap_metodo_supervisor', data: resp };
    }catch(e){
        console.error('Erro em loadHeatmapMetodoSupervisor', e);
        renderHeatmapMetodoSupervisor(null);
        return { key: 'heatmap_metodo_supervisor', data: {} };
    }
}

/**
 * Busca totais confiáveis para os cards KPI.
 */
async function loadKpiTotals(filters){
    try{
        const resp = await fetchChartData('/api/rdo-dashboard/kpis_totais/', filters);
        if(!resp || !resp.success){
            console.warn('Falha ao obter totais KPI', resp);
            return { key: 'kpi_totais', data: {} };
        }
        return { key: 'kpi_totais', data: resp };
    }catch(e){
        console.error('Erro em loadKpiTotals', e);
        return { key: 'kpi_totais', data: {} };
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
            try{ renderFunilStatusFromSummary(null); }catch(e){}
            try{ renderAgingEmAndamentoFromSummary(null); }catch(e){}
            return { key: 'os_status_summary', data: resp || { success: false } };
        }
        const total = Number(resp.total || 0);
        const programada = Number(resp.programada || 0);
        const em_andamento = Number(resp.em_andamento || 0);
        const paralizada = Number(resp.paralizada || 0);
        const finalizada = Number(resp.finalizada || 0);
        const cancelada = Number(resp.cancelada || 0);
        try{ renderFunilStatusFromSummary(resp); }catch(e){ console.debug('Erro ao renderizar funil de status', e); }
        try{ renderAgingEmAndamentoFromSummary(resp); }catch(e){ console.debug('Erro ao renderizar aging de OS em andamento', e); }

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
        try{ renderFunilStatusFromSummary(null); }catch(err){}
        try{ renderAgingEmAndamentoFromSummary(null); }catch(err){}
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
function getSummaryCurrentPage(){
    try{
        const page = Number(window.__summary_ops_current_page || 1);
        if(Number.isFinite(page) && page > 0) return Math.floor(page);
    }catch(e){}
    return 1;
}

function setSummaryCurrentPage(page){
    const normalized = Math.max(1, Math.floor(Number(page) || 1));
    try{ window.__summary_ops_current_page = normalized; }catch(e){}
    return normalized;
}

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
        const currentPage = getSummaryCurrentPage();
        try{
            if(getSummaryViewMode && getSummaryViewMode() === 'cards') renderSummaryCardsPage(currentPage);
            else renderSummaryTablePage(currentPage);
        }catch(e){ renderSummaryTablePage(currentPage); }
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
        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:18px;color:#aaa;font-size:15px;">Nenhuma operação encontrada</td></tr>';
        if(info) info.textContent = '';
        if(controls) controls.innerHTML = '';
        setSummaryLayoutModeClass('table');
        return;
    }

    // renderizar todas as linhas (usado quando paginação externa não aplicada)
    const rows = items.map(it => {
        const numero = escapeHtml(String(it.numero_os || ''));
        const sup = escapeHtml(String(it.supervisor || ''));
        const cli = escapeHtml(String(it.cliente || ''));
        const uni = escapeHtml(String(it.unidade || ''));
        const pob = Intl.NumberFormat('pt-BR').format(Number(it.avg_pob || 0));
        const ops = Intl.NumberFormat('pt-BR').format(toRoundedInt(it.sum_operadores_simultaneos || 0));
        const hhNao = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_nao_efetivo || 0));
        const hh = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_efetivo || 0));
        const sacos = Intl.NumberFormat('pt-BR').format(Number(it.total_ensacamento || 0));
        const tambores = Intl.NumberFormat('pt-BR').format(Number(it.total_tambores || 0));
        const dias = Intl.NumberFormat('pt-BR').format(Number(it.dias_movimentacao || 0));
        return `<tr>
            <td class="col-os" style="padding:8px;text-align:center">${numero}</td>
            <td class="col-supervisor" style="padding:8px;text-align:center">${sup}</td>
            <td class="col-cliente" style="padding:8px;text-align:center">${cli}</td>
            <td class="col-unidade" style="padding:8px;text-align:center">${uni}</td>
            <td class="col-dias" style="padding:8px;text-align:center">${dias}</td>
            <td class="col-pob" style="padding:8px;text-align:center">${pob}</td>
            <td class="col-op" style="padding:8px;text-align:center">${ops}</td>
            <td class="col-hh-nao" style="padding:8px;text-align:center">${hhNao}</td>
            <td class="col-hh" style="padding:8px;text-align:center">${hh}</td>
            <td class="col-sacos" style="padding:8px;text-align:center">${sacos}</td>
            <td class="col-tambores" style="padding:8px;text-align:center">${tambores}</td>
        </tr>`;
    }).join('');
    tbody.innerHTML = rows;
    if(info) info.textContent = `Mostrando ${items.length} registro(s)`;
    if(controls) controls.innerHTML = '';
    setSummaryLayoutModeClass('table');
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
    setSummaryCurrentPage(current);
    const start = (current - 1) * pageSize;
    const slice = items.slice(start, start + pageSize);

    // preencher body com slice
    const rows = slice.map(it => {
        const numero = escapeHtml(String(it.numero_os || ''));
        const sup = escapeHtml(String(it.supervisor || ''));
        const cli = escapeHtml(String(it.cliente || ''));
        const uni = escapeHtml(String(it.unidade || ''));
        const pob = Intl.NumberFormat('pt-BR').format(Number(it.avg_pob || 0));
        const ops = Intl.NumberFormat('pt-BR').format(toRoundedInt(it.sum_operadores_simultaneos || 0));
        const hhNao = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_nao_efetivo || 0));
        const hh = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_efetivo || 0));
        const sacos = Intl.NumberFormat('pt-BR').format(Number(it.total_ensacamento || 0));
        const tambores = Intl.NumberFormat('pt-BR').format(Number(it.total_tambores || 0));
        const dias = Intl.NumberFormat('pt-BR').format(Number(it.dias_movimentacao || 0));
        return `<tr>
            <td class="col-os" style="padding:8px;text-align:center">${numero}</td>
            <td class="col-supervisor" style="padding:8px;text-align:center">${sup}</td>
            <td class="col-cliente" style="padding:8px;text-align:center">${cli}</td>
            <td class="col-unidade" style="padding:8px;text-align:center">${uni}</td>
            <td class="col-dias" style="padding:8px;text-align:center">${dias}</td>
            <td class="col-pob" style="padding:8px;text-align:center">${pob}</td>
            <td class="col-op" style="padding:8px;text-align:center">${ops}</td>
            <td class="col-hh-nao" style="padding:8px;text-align:center">${hhNao}</td>
            <td class="col-hh" style="padding:8px;text-align:center">${hh}</td>
            <td class="col-sacos" style="padding:8px;text-align:center">${sacos}</td>
            <td class="col-tambores" style="padding:8px;text-align:center">${tambores}</td>
        </tr>`;
    }).join('');
    tbody.innerHTML = rows;
    setSummaryLayoutModeClass('table');

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
        toggleBtn.className = 'btn-secondary';
        toggleBtn.style.marginLeft = '10px';
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

function isSummaryMobileViewport(){
    try{
        if(typeof window !== 'undefined' && window.matchMedia){
            return window.matchMedia('(max-width: 900px)').matches;
        }
        return (typeof window !== 'undefined' && Number(window.innerWidth || 0) <= 900);
    }catch(e){
        return false;
    }
}

function getSummaryViewMode(){
    const isMobile = isSummaryMobileViewport();
    try{
        if(isMobile){
            const mobileMode = localStorage.getItem('summary_view_mode_mobile');
            if(mobileMode === 'cards' || mobileMode === 'table') return mobileMode;
            // Mobile default: cards (evita tabela comprimida em telas pequenas)
            return 'cards';
        }
        const mode = localStorage.getItem('summary_view_mode');
        if(mode === 'cards' || mode === 'table') return mode;
    }catch(e){}
    return isMobile ? 'cards' : 'table';
}

function setSummaryViewMode(mode){
    const normalized = (mode === 'cards') ? 'cards' : 'table';
    try{
        if(isSummaryMobileViewport()) localStorage.setItem('summary_view_mode_mobile', normalized);
        else localStorage.setItem('summary_view_mode', normalized);
    }catch(e){}
}

function setSummaryLayoutModeClass(mode){
    try{
        const wrap = document.querySelector('.summary-operations');
        if(!wrap) return;
        wrap.classList.remove('summary-table-active', 'summary-cards-active');
        wrap.classList.add(mode === 'cards' ? 'summary-cards-active' : 'summary-table-active');
    }catch(e){}
}

function applySummaryCardStyles(){
    if(document.getElementById('summary-cards-styles')) return;
    const css = `
    #summary-cards-container{padding:8px 6px; overflow-x:hidden; max-width:100%}
    #summary-cards-container .summary-cards-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
    #summary-cards-container .summary-card{background:linear-gradient(180deg,#141614,#0b0b0b);border-radius:12px;padding:16px;color:rgba(255,255,255,0.92);box-shadow:0 8px 28px rgba(0,0,0,0.6);border:1px solid rgba(204,255,0,0.08);font-family:Inter, system-ui, -apple-system, "Segoe UI", Roboto, 'Helvetica Neue', Arial;box-sizing:border-box;min-height:244px;max-width:100%;overflow:hidden}
    #summary-cards-container .summary-card .card-os{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:10px}
    #summary-cards-container .summary-card .card-os .os-num{display:none}
    #summary-cards-container .summary-card .card-os .os-badge{background:#1B7A4B;color:#fff;padding:6px 14px;border-radius:999px;font-weight:700;font-size:12px;min-width:140px;text-align:center}
    #summary-cards-container .summary-card .divider{height:1px;background:rgba(204,255,0,0.08);margin:12px 0;border-radius:2px}
    #summary-cards-container .summary-card .divider-top{height:1px;background:rgba(204,255,0,0.06);margin:8px 0 14px;border-radius:2px;opacity:0.9}
    #summary-cards-container .card-top-grid{display:flex;gap:14px;align-items:flex-start}
    #summary-cards-container .card-top-grid .col{flex:1;display:flex;flex-direction:column;gap:8px}
    #summary-cards-container .card-top-grid .item{display:flex;flex-direction:column}
    #summary-cards-container .card-top-grid .item strong{display:block;font-size:12px;color:rgba(255,255,255,0.72);letter-spacing:0.04em;text-transform:uppercase;font-weight:700}
    #summary-cards-container .card-top-grid .item .value{font-weight:800;color:#CCFF00;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #summary-cards-container .summary-card .kpi-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;align-items:stretch;margin-top:12px;border-top:1px solid rgba(255,255,255,0.04);padding-top:10px}
    #summary-cards-container .summary-card .kpi-row.kpi-row--compact{gap:10px}
    #summary-cards-container .summary-card .kpi-item{display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:0;padding:2px 0}
    #summary-cards-container .summary-card .kpi-item .kpi-value{font-weight:900;font-size:15px;color:#CCFF00;display:block;text-align:center;min-width:0}
    #summary-cards-container .summary-card .kpi-item .kpi-label{font-size:10.5px;color:rgba(255,255,255,0.62);margin-top:4px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #summary-cards-container .summary-card .small-muted{font-size:12px;color:rgba(255,255,255,0.65)}
    @media (max-width:1100px){ #summary-cards-container .summary-cards-grid{grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px} }
    @media (max-width:900px){ #summary-cards-container .summary-cards-grid{grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px} }
    @media (max-width:600px){
        #summary-cards-container .summary-cards-grid{grid-template-columns:1fr}
        #summary-cards-container{padding:6px 0}
        #summary-cards-container .summary-card{padding:14px}
        #summary-cards-container .summary-card .kpi-row.kpi-row--compact{gap:8px;padding-top:8px}
    }
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
        setSummaryLayoutModeClass('cards');
        return;
    }

    const total = items.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const current = Math.min(Math.max(1, page || 1), totalPages);
    setSummaryCurrentPage(current);
    const start = (current - 1) * pageSize;
    const slice = items.slice(start, start + pageSize);

    const cardsHtml = slice.map(it => {
        const numero = escapeHtml(String(it.numero_os || ''));
        const sup = escapeHtml(String(it.supervisor || ''));
        const cli = escapeHtml(String(it.cliente || ''));
        const uni = escapeHtml(String(it.unidade || ''));
        const pob = Intl.NumberFormat('pt-BR').format(Number(it.avg_pob || 0));
        const ops = Intl.NumberFormat('pt-BR').format(toRoundedInt(it.sum_operadores_simultaneos || 0));
        const hhNao = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_nao_efetivo || 0));
        const hh = Intl.NumberFormat('pt-BR').format(Number(it.sum_hh_efetivo || 0));
        const sacos = Intl.NumberFormat('pt-BR').format(Number(it.total_ensacamento || 0));
        const tambores = Intl.NumberFormat('pt-BR').format(Number(it.total_tambores || 0));
        const dias = Intl.NumberFormat('pt-BR').format(Number(it.dias_movimentacao || 0));

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
            <div class="kpi-row kpi-row--compact">
                <div class="kpi-item"><div class="kpi-value">${hh}</div><div class="kpi-label">HH Efetivo</div></div>
                <div class="kpi-item"><div class="kpi-value">${hhNao}</div><div class="kpi-label">HH Não Efetivo</div></div>
                <div class="kpi-item"><div class="kpi-value">${dias}</div><div class="kpi-label">Dias</div></div>
            </div>
        </div>`;
    }).join('');

    container.innerHTML = `<div class="summary-cards-grid">${cardsHtml}</div>`;

    // ocultar a tabela quando em modo cards
    if(tableEl) tableEl.style.display = getSummaryViewMode() === 'cards' ? 'none' : '';
    container.style.display = getSummaryViewMode() === 'cards' ? '' : 'none';
    setSummaryLayoutModeClass('cards');

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
        toggleBtn.className = 'btn-secondary';
        toggleBtn.style.marginLeft = '10px';
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
    const currentPage = getSummaryCurrentPage();
    if(mode === 'cards') renderSummaryCardsPage(currentPage); else renderSummaryTablePage(currentPage);
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
    const isRadialChart = (type === 'doughnut' || type === 'pie' || type === 'polarArea');

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

    // Paleta variada para linhas e barras (evita aparência monocromática)
    const themePalette = ['#2563eb','#ef4444','#16a34a','#f59e0b','#8b5cf6','#06b6d4','#ec4899','#14b8a6'];
    const chartBaseColorById = {
        chartHHConfinado: '#2563eb',
        chartHHForaConfinado: '#ef4444',
        chartTempoBomba: '#16a34a',
        chartEnsacamento: '#f59e0b',
        chartTambores: '#8b5cf6',
        chartResidLiquido: '#06b6d4',
        chartResidSolido: '#ec4899',
        chartLiquidoSupervisor: '#14b8a6',
        chartSolidoSupervisor: '#dc2626',
        chartVolumeTanque: '#0ea5e9',
        chartPobComparativo: '#f97316',
        chartTopSupervisores: '#7c3aed'
    };

    function toRgba(hex, alpha){
        const v = String(hex || '').replace('#','').trim();
        if (!/^[0-9a-fA-F]{6}$/.test(v)) return `rgba(37,99,235,${alpha})`;
        const r = parseInt(v.slice(0,2), 16);
        const g = parseInt(v.slice(2,4), 16);
        const b = parseInt(v.slice(4,6), 16);
        return `rgba(${r},${g},${b},${alpha})`;
    }

    const baseColor = chartBaseColorById[chartId] || '#2563eb';
    const baseOffset = Math.max(0, themePalette.indexOf(baseColor));
    const lineFill = toRgba(baseColor, 0.10);
    const payload = normalizePayload(JSON.parse(JSON.stringify(data)));

    // Atribui cores padrão globalmente (paleta verde), exceto quando o chamador solicitar
    // explicitamente que as cores de dataset sejam preservadas.
    const preserveDatasetColors = !!(options && options.__preserveDatasetColors);
    if(!preserveDatasetColors && Array.isArray(payload.datasets)){
        payload.datasets.forEach((ds, idx) => {
            const chosen = themePalette[(baseOffset + idx) % themePalette.length];
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

        // Escalas padrão com ticks/grid só para gráficos cartesianos
        if(!isRadialChart){
            defaultOptions.scales = defaultOptions.scales || {};
            defaultOptions.scales.x = defaultOptions.scales.x || {};
            defaultOptions.scales.y = defaultOptions.scales.y || {};
            defaultOptions.scales.x.ticks = Object.assign({}, defaultOptions.scales.x.ticks, { color: '#ffffff' });
            defaultOptions.scales.y.ticks = Object.assign({}, defaultOptions.scales.y.ticks, { color: '#ffffff' });
            defaultOptions.scales.x.grid = Object.assign({}, defaultOptions.scales.x.grid, { color: 'rgba(255,255,255,0.04)' });
            defaultOptions.scales.y.grid = Object.assign({}, defaultOptions.scales.y.grid, { color: 'rgba(255,255,255,0.04)' });
        }
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

    if(!isRadialChart){
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
    } else if(finalOptions.scales) {
        // Para doughnut/pie, remover escalas para evitar labels/eixos e deslocamento vertical.
        delete finalOptions.scales;
    }

    // Ajuste dinâmico de eixo mínimo: aplicar apenas em barras.
    // Em linhas isso "achata" séries com valores baixos no mobile.
    if(type === 'bar'){
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
                const suggested = Math.max(1, Math.floor(minVal * 0.9));
                if(!finalOptions.scales) finalOptions.scales = {};

                // Por padrão, barras verticais usam Y como eixo numérico.
                const numericAxis = (finalOptions.indexAxis === 'y') ? 'x' : 'y';
                const axisCfg = finalOptions.scales[numericAxis] = finalOptions.scales[numericAxis] || {};

                // Respeitar configurações explícitas do chamador.
                if(axisCfg.beginAtZero !== true){
                    axisCfg.beginAtZero = false;
                    if(axisCfg.suggestedMin === undefined) axisCfg.suggestedMin = suggested;
                }
            }
        } catch(err){
            console.debug('axis adjust error', err);
        }
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
            const area = chart.chartArea;
            const centerX = area ? (area.left + area.right) / 2 : chart.width / 2;
            const centerY = area ? (area.top + area.bottom) / 2 : chart.height / 2;
            ctx.save();
            ctx.fillStyle = cfg.color || 'rgba(15,23,42,0.9)';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = cfg.font || '700 14px Inter, system-ui, -apple-system, "Segoe UI", Roboto';
            ctx.fillText(typeof cfg.text === 'function' ? cfg.text(chart) : (cfg.text || ''), centerX, centerY);
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
    if(!isRadialChart){
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
        const tempoMeta = (data && data.meta && typeof data.meta === 'object') ? data.meta : {};
        const backendOptions = data.options || {};

        function sanitizeTankLabel(label){
            const s = String(label || '').trim();
            if(!s) return 'Sem identificacao';
            const low = s.toLowerCase();
            if(low === 'outros') return null;
            if(['desconhecido', 'unknown', 'none', 'null', 'n/a', 'na', '-', '—'].includes(low)){
                return 'Sem identificacao';
            }
            return s;
        }

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
                const d = String(dt.getUTCDate()).padStart(2,'0');
                const m = String(dt.getUTCMonth()+1).padStart(2,'0');
                return `${d}/${m}`;
            }catch(e){
                return '';
            }
        }

        function aggregateToWeeks(labels, series){
            const buckets = new Map();
            for(let i=0;i<labels.length;i++){
                const dt = parseYMD(labels[i]);
                if(!dt) continue;
                const day = dt.getUTCDay();
                const deltaToMonday = (day === 0) ? 6 : (day - 1);
                const monday = new Date(dt.getTime() - deltaToMonday*24*60*60*1000);
                const key = monday.toISOString().slice(0,10);
                const v = Number(series[i]) || 0;
                const prev = buckets.get(key) || { monday, sum: 0 };
                prev.sum += v;
                buckets.set(key, prev);
            }
            const ordered = Array.from(buckets.values()).sort((a,b) => a.monday - b.monday);
            const weekLabels = [];
            const weekSums = [];
            ordered.forEach(w => {
                const start = w.monday;
                const end = new Date(start.getTime() + 6*24*60*60*1000);
                weekLabels.push(`${fmtDateBR(start)}–${fmtDateBR(end)}`);
                weekSums.push(w.sum);
            });
            return { weekLabels, weekSums };
        }

        function sumSeries(series){
            return (series || []).reduce((acc, v) => acc + (Number(v) || 0), 0);
        }

        function avgSeries(series){
            if(!Array.isArray(series) || !series.length) return 0;
            return sumSeries(series) / series.length;
        }

        function buildCumulative(series){
            const out = [];
            let run = 0;
            for(let i=0;i<(series || []).length;i++){
                run += Number(series[i]) || 0;
                out.push(run);
            }
            return out;
        }

        // Projeção simples por tanque baseada na média dos últimos períodos com produção
        function forecastNextPeriod(series, isWeekly){
            const clean = (series || []).map(v => Number(v) || 0).filter(v => v > 0);
            if(!clean.length) return 0;
            const windowSize = isWeekly ? 3 : 5;
            const recent = clean.slice(-windowSize);
            if(!recent.length) return 0;
            const avg = recent.reduce((acc, v) => acc + v, 0) / recent.length;
            return Math.max(0, avg);
        }

        function buildForecastCumulative(series, isWeekly){
            const clean = (series || []).map(v => Number(v) || 0);
            const forecastPerPeriod = forecastNextPeriod(clean, isWeekly);
            const out = [];
            let run = 0;
            for(let i=0;i<clean.length;i++){
                const actual = clean[i] > 0 ? clean[i] : forecastPerPeriod;
                run += Number(actual) || 0;
                out.push(run);
            }
            return out;
        }

        // Cores categóricas, determinísticas por nome de tanque
        const distinctPalette = [
            '#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F',
            '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC',
            '#1F77B4', '#FF7F0E', '#D62728', '#9467BD', '#8C564B',
            '#E377C2', '#7F7F7F', '#BCBD22', '#17BECF'
        ];
        function colorForLabel(label){
            const s = String(label || '');
            let hash = 0;
            for(let i=0;i<s.length;i++) hash = ((hash << 5) - hash) + s.charCodeAt(i);
            const idx = Math.abs(hash) % distinctPalette.length;
            return distinctPalette[idx];
        }

        const tankSeriesRaw = rawDatasets.map(ds => {
            const labelRaw = (ds && ds.label !== undefined && ds.label !== null) ? String(ds.label) : 'Tanque';
            const label = sanitizeTankLabel(labelRaw);
            const arr = (ds && Array.isArray(ds.data)) ? ds.data : [];
            const series = arr.map(v => {
                const n = Number(v);
                return isFinite(n) ? n : 0;
            });
            return { label, series };
        }).filter(t => t && t.label && t.series && t.series.length);

        const visibleValuesDaily = rawLabels.map((_, idx) => {
            let s = 0;
            tankSeriesRaw.forEach(t => { s += Number(t.series[idx]) || 0; });
            return s;
        });

        const totalSeriesRaw = Array.isArray(tempoMeta.total_series_all) ? tempoMeta.total_series_all : null;
        const totalValuesDaily = rawLabels.map((_, idx) => {
            const fromMeta = totalSeriesRaw && totalSeriesRaw.length === rawLabels.length
                ? Number(totalSeriesRaw[idx])
                : NaN;
            if(isFinite(fromMeta) && fromMeta >= 0){
                return fromMeta;
            }
            return Number(visibleValuesDaily[idx]) || 0;
        });

        const useWeekly = totalValuesDaily.length > 21;
        let labels = rawLabels.slice();
        let barsTotal = totalValuesDaily.slice();
        let modeLabel = 'Diário';
        let tanks = tankSeriesRaw.map(t => ({ label: t.label, data: t.series.slice() }));

        if(useWeekly){
            const aggTotal = aggregateToWeeks(rawLabels, totalValuesDaily);
            labels = aggTotal.weekLabels;
            barsTotal = aggTotal.weekSums;
            modeLabel = 'Semanal';

            tanks = tanks.map(t => {
                const agg = aggregateToWeeks(rawLabels, t.data);
                return { label: t.label, data: agg.weekSums };
            });
        }

        tanks = tanks.map(t => {
            const cleanData = (t.data || []).map(v => Number(v) || 0);
            return {
                label: t.label,
                data: cleanData,
                cumulative: buildCumulative(cleanData),
                total: sumSeries(cleanData),
                color: colorForLabel(t.label)
            };
        }).sort((a,b) => (b.total || 0) - (a.total || 0));

        const totalBars = sumSeries(barsTotal);
        const avgBarTotal = avgSeries(barsTotal);
        const totalCumulative = buildCumulative(barsTotal);
        const hiddenTankCount = Math.max(0, Number(tempoMeta.hidden_tanks_count) || 0);
        const hiddenTankTotal = Math.max(0, Number(tempoMeta.hidden_tanks_total) || 0);

        if(tanks.length){
            const hasCurrent = tanks.some(t => t.label === __tempo_bomba_view_state.currentTankLabel);
            if(!hasCurrent){
                __tempo_bomba_view_state.currentTankLabel = tanks[0].label;
            }
        } else {
            __tempo_bomba_view_state.currentTankLabel = '';
            __tempo_bomba_view_state.mode = 'auto';
        }

        if(__tempo_bomba_view_state.mode !== 'auto'){
            __tempo_bomba_view_state.mode = 'auto';
        }

        const leader = tanks.length ? tanks[0] : null;
        const leaderLabel = leader ? leader.label : '--';
        const leaderTotal = leader ? leader.total : 0;

        function getSelectedTank(){
            if(!tanks.length) return null;
            const found = tanks.find(t => t.label === __tempo_bomba_view_state.currentTankLabel);
            return found || tanks[0];
        }

        function getCurrentTankIndex(){
            if(!tanks.length) return -1;
            const idx = tanks.findIndex(t => t.label === __tempo_bomba_view_state.currentTankLabel);
            return idx >= 0 ? idx : 0;
        }

        function ensureTempoBombaUI(){
            const canvas = document.getElementById('chartTempoBomba');
            if(!canvas) return null;
            const container = canvas.parentElement;
            if(!container) return null;

            let wrap = document.getElementById('tempo_bomba_legend_wrap');
            if(!wrap){
                wrap = document.createElement('div');
                wrap.id = 'tempo_bomba_legend_wrap';
                container.insertBefore(wrap, canvas);
            }
            wrap.style.display = 'flex';
            wrap.style.flexDirection = 'column';
            wrap.style.gap = '8px';
            wrap.style.margin = '6px 0 10px';

            let toolbar = document.getElementById('tempo_bomba_toolbar');
            if(!toolbar){
                toolbar = document.createElement('div');
                toolbar.id = 'tempo_bomba_toolbar';
                wrap.appendChild(toolbar);
            }
            toolbar.style.display = 'flex';
            toolbar.style.flexWrap = 'wrap';
            toolbar.style.gap = '8px';
            toolbar.style.alignItems = 'center';

            let legend = document.getElementById('tempo_bomba_legend');
            if(!legend){
                legend = document.createElement('div');
                legend.id = 'tempo_bomba_legend';
                wrap.appendChild(legend);
            }
            legend.style.display = 'flex';
            legend.style.flexWrap = 'nowrap';
            legend.style.gap = '8px';
            legend.style.maxHeight = 'none';
            legend.style.overflow = 'visible';
            legend.style.padding = '2px';

            wrap.onmouseenter = function(){ __tempo_bomba_view_state.hoverPause = true; };
            wrap.onmouseleave = function(){ __tempo_bomba_view_state.hoverPause = false; };

            return { wrap, toolbar, legend };
        }

        function makeControlBtn(label, active){
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = label;
            btn.style.display = 'inline-flex';
            btn.style.alignItems = 'center';
            btn.style.gap = '6px';
            btn.style.padding = '6px 10px';
            btn.style.borderRadius = '999px';
            btn.style.border = active ? '1px solid rgba(27,122,75,0.45)' : '1px solid rgba(148,163,184,0.28)';
            btn.style.background = active ? 'rgba(27,122,75,0.16)' : 'rgba(255,255,255,0.06)';
            btn.style.color = 'inherit';
            btn.style.cursor = 'pointer';
            btn.style.fontSize = '12px';
            btn.style.fontWeight = '800';
            return btn;
        }

        function makeTankPill(tank, active){
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'tempo-bomba-pill';
            btn.style.display = 'inline-flex';
            btn.style.alignItems = 'center';
            btn.style.gap = '8px';
            btn.style.padding = '6px 10px';
            btn.style.borderRadius = '999px';
            btn.style.border = active ? `1px solid ${tank.color}` : '1px solid rgba(148,163,184,0.28)';
            btn.style.background = active ? 'rgba(27,122,75,0.14)' : 'rgba(255,255,255,0.06)';
            btn.style.color = 'inherit';
            btn.style.cursor = 'pointer';
            btn.style.fontSize = '12px';
            btn.style.fontWeight = '700';
            btn.title = `Fixar tanque ${tank.label}`;

            const dot = document.createElement('span');
            dot.style.width = '10px';
            dot.style.height = '10px';
            dot.style.borderRadius = '50%';
            dot.style.background = tank.color;
            dot.style.display = 'inline-block';

            const txt = document.createElement('span');
            txt.textContent = tank.label;

            const right = document.createElement('span');
            right.textContent = formatHoursToHHMM(tank.total);
            right.style.marginLeft = '4px';
            right.style.padding = '2px 8px';
            right.style.borderRadius = '999px';
            right.style.fontWeight = '800';
            right.style.fontSize = '12px';
            right.style.background = 'rgba(15,23,42,0.22)';
            right.style.border = '1px solid rgba(148,163,184,0.18)';

            btn.appendChild(dot);
            btn.appendChild(txt);
            btn.appendChild(right);
            return btn;
        }

        function mergeChartOptions(localOptions){
            const backendScales = (backendOptions && backendOptions.scales) ? backendOptions.scales : {};
            const localScales = (localOptions && localOptions.scales) ? localOptions.scales : {};
            const mergedScales = {
                ...backendScales,
                ...localScales,
                x: {
                    ...((backendScales || {}).x || {}),
                    ...((localScales || {}).x || {})
                },
                y: {
                    ...((backendScales || {}).y || {}),
                    ...((localScales || {}).y || {})
                }
            };
            if((backendScales && backendScales.y2) || (localScales && localScales.y2)){
                mergedScales.y2 = {
                    ...((backendScales || {}).y2 || {}),
                    ...((localScales || {}).y2 || {})
                };
            }

            const merged = {
                ...backendOptions,
                ...localOptions,
                plugins: {
                    ...(backendOptions.plugins || {}),
                    ...(localOptions.plugins || {})
                },
                scales: mergedScales
            };
            merged.__preserveDatasetColors = true;
            return merged;
        }

        function buildAllTankChart(){
            const datasets = tanks.map(t => ({
                type: 'line',
                label: `Curva S • ${t.label}`,
                data: t.cumulative,
                borderColor: t.color,
                backgroundColor: `${t.color}22`,
                pointRadius: 0,
                tension: 0.25,
                borderWidth: 2,
                fill: false
            }));

            datasets.push({
                type: 'line',
                label: 'Curva S • Total',
                data: totalCumulative,
                borderColor: 'rgba(255,255,255,0.82)',
                backgroundColor: 'rgba(255,255,255,0.08)',
                borderDash: [6, 6],
                pointRadius: 0,
                tension: 0.2,
                borderWidth: 2,
                fill: false
            });

            const maxCum = Math.max(0, ...totalCumulative);
            const chartData = { labels, datasets };
            const options = mergeChartOptions({
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    barValuePlugin: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx){
                                const v = Number(ctx.parsed && ctx.parsed.y);
                                const h = isFinite(v) ? v : 0;
                                return `${ctx.dataset.label}: ${h.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} h (${formatHoursToHHMM(h)})`;
                            }
                        }
                    },
                    subtitle: {
                        display: true,
                        text: `Curvas S por tanque (${tanks.length}) • ${modeLabel} • Total: ${formatHoursToHHMM(totalBars)}`,
                        color: (document.body && document.body.classList && document.body.classList.contains('dark-mode')) ? 'rgba(255,255,255,0.75)' : 'rgba(0,0,0,0.65)',
                        font: { size: 12, weight: '600' },
                        padding: { top: 0, bottom: 8 }
                    }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: {
                        beginAtZero: true,
                        suggestedMax: maxCum ? (maxCum * 1.08) : undefined,
                        title: { display: true, text: 'Acumulado (h)' },
                        ticks: {
                            callback: function(value){
                                const n = Number(value);
                                return isFinite(n) ? formatHoursToHHMM(n) : String(value);
                            }
                        }
                    }
                }
            });
            return { type: 'line', chartData, options };
        }

        function buildSingleTankChart(tank){
            const tankData = tank ? tank.data : labels.map(() => 0);
            const tankCumulative = tank ? tank.cumulative : labels.map(() => 0);
            const tankForecastCumulative = buildForecastCumulative(tankData, useWeekly);
            const tankColor = tank ? tank.color : '#16a34a';
            const maxTankBar = Math.max(0, ...tankData);
            const maxCum = Math.max(0, ...tankCumulative, ...tankForecastCumulative, ...totalCumulative);

            const chartData = {
                labels,
                datasets: [
                    {
                        type: 'bar',
                        label: tank ? `${tank.label} (h no período)` : 'Sem tanque',
                        data: tankData,
                        backgroundColor: `${tankColor}33`,
                        borderColor: tankColor,
                        borderWidth: 1,
                        borderRadius: 6,
                        borderSkipped: false,
                        maxBarThickness: 24
                    },
                    {
                        type: 'line',
                        label: tank ? `Curva S • ${tank.label}` : 'Curva S',
                        data: tankCumulative,
                        yAxisID: 'y2',
                        borderColor: tankColor,
                        backgroundColor: `${tankColor}14`,
                        pointRadius: 0,
                        tension: 0.25,
                        borderWidth: 3,
                        fill: false
                    },
                    {
                        type: 'line',
                        label: tank ? `Previsão • ${tank.label}` : 'Previsão',
                        data: tankForecastCumulative,
                        yAxisID: 'y2',
                        borderColor: `${tankColor}CC`,
                        borderDash: [6, 6],
                        pointRadius: 0,
                        tension: 0.2,
                        borderWidth: 2,
                        fill: false
                    }
                ]
            };

            const options = mergeChartOptions({
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    barValuePlugin: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx){
                                const v = Number(ctx.parsed && ctx.parsed.y);
                                const h = isFinite(v) ? v : 0;
                                return `${ctx.dataset.label}: ${h.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} h (${formatHoursToHHMM(h)})`;
                            },
                            footer: function(items){
                                const idx = (items && items.length) ? Number(items[0].dataIndex) : -1;
                                if(idx < 0) return '';
                                const tankPoint = Number(tankData[idx]) || 0;
                                const forecastCumPoint = Number(tankForecastCumulative[idx]) || 0;
                                return [
                                    `Tanque no período: ${formatHoursToHHMM(tankPoint)}`,
                                    `Previsão acumulada: ${formatHoursToHHMM(forecastCumPoint)}`
                                ];
                            }
                        }
                    },
                    subtitle: {
                        display: true,
                        text: `${tank ? tank.label : 'Sem tanque'} • Curva S por tanque • ${modeLabel}`,
                        color: (document.body && document.body.classList && document.body.classList.contains('dark-mode')) ? 'rgba(255,255,255,0.75)' : 'rgba(0,0,0,0.65)',
                        font: { size: 12, weight: '600' },
                        padding: { top: 0, bottom: 8 }
                    }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: {
                        beginAtZero: true,
                        suggestedMax: maxTankBar ? (maxTankBar * 1.15) : undefined,
                        title: { display: true, text: useWeekly ? 'Horas por semana' : 'Horas por dia' },
                        ticks: {
                            callback: function(value){
                                const n = Number(value);
                                return isFinite(n) ? formatHoursToHHMM(n) : String(value);
                            }
                        }
                    },
                    y2: {
                        position: 'right',
                        beginAtZero: true,
                        suggestedMax: maxCum ? (maxCum * 1.08) : undefined,
                        grid: { display: false },
                        title: { display: true, text: 'Acumulado (h)' },
                        ticks: {
                            callback: function(value){
                                const n = Number(value);
                                return isFinite(n) ? formatHoursToHHMM(n) : String(value);
                            }
                        }
                    }
                }
            });

            return { type: 'bar', chartData, options };
        }

        function updateInsightsAndHelp(selectedTank){
            const modeText = `${modeLabel} · Carrossel ${__tempo_bomba_view_state.intervalSec}s`;
            setTextById('tempo_bomba_mode', modeText);
            setTextById('tempo_bomba_total', formatHoursToHHMM(totalBars));

            const avgRef = selectedTank ? avgSeries(selectedTank.data) : avgBarTotal;
            setTextById('tempo_bomba_avg', formatHoursToHHMM(avgRef));

            if(leaderLabel && leaderLabel !== '--'){
                setTextById('tempo_bomba_peak', `${leaderLabel}: ${formatHoursToHHMM(leaderTotal)}`);
            } else {
                setTextById('tempo_bomba_peak', '--');
            }

            if(labels.length){
                const idx = labels.length - 1;
                const ref = selectedTank ? (Number(selectedTank.data[idx]) || 0) : (Number(barsTotal[idx]) || 0);
                setTextById('tempo_bomba_last', `${formatHoursToHHMM(ref)} (${labels[idx]})`);
            } else {
                setTextById('tempo_bomba_last', '--');
            }

            const forecast = selectedTank ? forecastNextPeriod(selectedTank.data, useWeekly) : 0;
            setTextById('tempo_bomba_forecast', `${formatHoursToHHMM(forecast)} (${useWeekly ? 'próx. semana' : 'próx. dia'})`);

            try{
                const help = document.getElementById('tempo_bomba_help');
                if(!help) return;
                const hiddenTxt = hiddenTankCount > 0
                    ? ` · +${hiddenTankCount} tanque(s) oculto(s) no backend (${formatHoursToHHMM(hiddenTankTotal)})`
                    : '';
                help.textContent = `Carrossel automático por tanque (${__tempo_bomba_view_state.intervalSec}s) · Barras = período do tanque · Linha sólida = curva S do tanque · Tracejado = previsão por tanque${hiddenTxt}`;
            }catch(e){ /* ignore */ }
        }

        function renderControls(ui){
            if(!ui) return;
            const { toolbar, legend } = ui;
            toolbar.innerHTML = '';
            legend.innerHTML = '';

            const btnAuto = makeControlBtn('Carrossel', __tempo_bomba_view_state.mode === 'auto');
            btnAuto.title = 'Rotação automática entre tanques';
            btnAuto.onclick = function(){
                if(!tanks.length) return;
                __tempo_bomba_view_state.mode = 'auto';
                __tempo_bomba_view_state.paused = false;
                if(!__tempo_bomba_view_state.currentTankLabel){
                    __tempo_bomba_view_state.currentTankLabel = tanks[0].label;
                }
                renderFrame();
                restartCarousel();
            };
            toolbar.appendChild(btnAuto);

            const btnPause = makeControlBtn(__tempo_bomba_view_state.paused ? 'Continuar' : 'Pausar', __tempo_bomba_view_state.paused);
            btnPause.title = 'Pausar/retomar carrossel';
            btnPause.disabled = (__tempo_bomba_view_state.mode !== 'auto');
            btnPause.style.opacity = btnPause.disabled ? '0.55' : '1';
            btnPause.style.cursor = btnPause.disabled ? 'not-allowed' : 'pointer';
            btnPause.onclick = function(){
                if(__tempo_bomba_view_state.mode !== 'auto') return;
                __tempo_bomba_view_state.paused = !__tempo_bomba_view_state.paused;
                renderControls(ui);
            };
            toolbar.appendChild(btnPause);

            if(!tanks.length){
                const empty = document.createElement('div');
                empty.textContent = 'Sem dados por tanque para o período selecionado.';
                empty.style.fontSize = '12px';
                empty.style.opacity = '0.75';
                legend.appendChild(empty);
                return;
            }

            // Navegação compacta para muitos tanques
            const idx = getCurrentTankIndex();
            const total = tanks.length;
            const current = tanks[idx];

            const btnPrev = makeControlBtn('Anterior', false);
            btnPrev.title = 'Voltar para o tanque anterior';
            btnPrev.onclick = function(){
                const prevIdx = (idx - 1 + total) % total;
                __tempo_bomba_view_state.currentTankLabel = tanks[prevIdx].label;
                __tempo_bomba_view_state.paused = false;
                renderFrame();
                restartCarousel();
            };
            toolbar.appendChild(btnPrev);

            const btnNext = makeControlBtn('Próximo', false);
            btnNext.title = 'Ir para o próximo tanque';
            btnNext.onclick = function(){
                const nextIdx = (idx + 1) % total;
                __tempo_bomba_view_state.currentTankLabel = tanks[nextIdx].label;
                __tempo_bomba_view_state.paused = false;
                renderFrame();
                restartCarousel();
            };
            toolbar.appendChild(btnNext);

            // Ajuste rápido de velocidade do carrossel
            const speed = document.createElement('select');
            speed.setAttribute('aria-label', 'Velocidade do carrossel');
            speed.style.padding = '6px 10px';
            speed.style.borderRadius = '999px';
            speed.style.border = '1px solid rgba(148,163,184,0.28)';
            speed.style.background = 'rgba(255,255,255,0.06)';
            speed.style.color = 'inherit';
            speed.style.fontSize = '12px';
            speed.style.fontWeight = '700';
            [10, 15, 20, 30, 45, 60].forEach(sec => {
                const opt = document.createElement('option');
                opt.value = String(sec);
                opt.textContent = `Troca: ${sec}s`;
                if(Number(__tempo_bomba_view_state.intervalSec) === sec){
                    opt.selected = true;
                }
                speed.appendChild(opt);
            });
            speed.onchange = function(){
                const sec = Number(speed.value) || 20;
                __tempo_bomba_view_state.intervalSec = sec;
                restartCarousel();
                updateInsightsAndHelp(getSelectedTank());
            };
            toolbar.appendChild(speed);

            // Seletor único (evita poluição visual com dezenas de tanques)
            const picker = document.createElement('select');
            picker.setAttribute('aria-label', 'Selecionar tanque');
            picker.style.padding = '6px 10px';
            picker.style.borderRadius = '999px';
            picker.style.border = `1px solid ${current ? current.color : 'rgba(148,163,184,0.28)'}`;
            picker.style.background = 'rgba(255,255,255,0.06)';
            picker.style.color = 'inherit';
            picker.style.fontSize = '12px';
            picker.style.fontWeight = '800';
            picker.style.minWidth = '250px';
            tanks.forEach((tank, i) => {
                const opt = document.createElement('option');
                opt.value = tank.label;
                opt.textContent = `${i + 1}/${total} · ${tank.label} · ${formatHoursToHHMM(tank.total)}`;
                if(tank.label === __tempo_bomba_view_state.currentTankLabel){
                    opt.selected = true;
                }
                picker.appendChild(opt);
            });
            picker.onchange = function(){
                __tempo_bomba_view_state.currentTankLabel = picker.value;
                __tempo_bomba_view_state.paused = false;
                renderFrame();
                restartCarousel();
            };
            toolbar.appendChild(picker);

            // Resumo da fila de carrossel (compacto)
            legend.style.display = 'grid';
            legend.style.gridTemplateColumns = 'repeat(auto-fit, minmax(220px, 1fr))';
            legend.style.width = '100%';

            function makeInfoCard(title, value, accent){
                const card = document.createElement('div');
                card.style.display = 'flex';
                card.style.flexDirection = 'column';
                card.style.gap = '4px';
                card.style.padding = '8px 10px';
                card.style.borderRadius = '10px';
                card.style.border = `1px solid ${accent || 'rgba(148,163,184,0.25)'}`;
                card.style.background = 'rgba(255,255,255,0.04)';

                const t = document.createElement('span');
                t.textContent = title;
                t.style.fontSize = '11px';
                t.style.fontWeight = '700';
                t.style.opacity = '0.78';

                const v = document.createElement('span');
                v.textContent = value;
                v.style.fontSize = '13px';
                v.style.fontWeight = '800';

                card.appendChild(t);
                card.appendChild(v);
                return card;
            }

            const nextA = tanks[(idx + 1) % total];
            const nextB = tanks[(idx + 2) % total];
            const queueTxt = [nextA, nextB].filter(Boolean).map(t => t.label).join(' → ');
            const rest = Math.max(0, total - 3);
            const queueSuffix = rest > 0 ? ` → +${rest}` : '';

            legend.appendChild(makeInfoCard('Tanque Atual', current ? `${current.label} · ${formatHoursToHHMM(current.total)}` : '--', current ? `${current.color}88` : undefined));
            legend.appendChild(makeInfoCard('Posição', `${idx + 1} de ${total}`));
            legend.appendChild(makeInfoCard('Próximos', queueTxt ? `${queueTxt}${queueSuffix}` : '--'));
        }

        function restartCarousel(){
            clearTempoBombaCarouselTimer();
            if(tanks.length <= 1) return;
            const everyMs = Math.max(10, Number(__tempo_bomba_view_state.intervalSec) || 20) * 1000;
            __tempo_bomba_carousel_timer = setInterval(() => {
                if(__tempo_bomba_view_state.paused || __tempo_bomba_view_state.hoverPause) return;
                const idx = tanks.findIndex(t => t.label === __tempo_bomba_view_state.currentTankLabel);
                const nextIdx = (idx >= 0 ? idx + 1 : 0) % tanks.length;
                __tempo_bomba_view_state.currentTankLabel = tanks[nextIdx].label;
                renderFrame();
            }, everyMs);
        }

        function renderFrame(){
            const ui = ensureTempoBombaUI();
            renderControls(ui);

            const selectedTank = getSelectedTank();
            updateInsightsAndHelp(selectedTank);

            const built = buildSingleTankChart(selectedTank);

            updateChart('chartTempoBomba', built.type, built.chartData, built.options);
        }

        clearTempoBombaCarouselTimer();
        renderFrame();
        restartCarousel();
        return { key: 'tempo_bomba', data: data };
    } catch (error) {
        clearTempoBombaCarouselTimer();
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
        // Dividir valores por 100 e arredondar ao inteiro mais próximo
        const withRounded = pairs.map(p => ({...p, rounded: Math.round(p.value / 100)}));
        // Filtrar apenas supervisores com valor exibido > 0 (após divisão/arredondamento)
        const filtered = withRounded.filter(p => p.rounded > 0);
        filtered.sort((a,b) => b.rounded - a.rounded);
        const sortedLabels = filtered.map(p => p.label);
        const sortedValues = filtered.map(p => p.rounded);

        const prepared = { labels: sortedLabels, datasets: [{ label: ds.label || 'M³ líquido removido (x100)', data: sortedValues, backgroundColor: '#2563eb' }] };

        // Ajustar dataset (espessura e borda) para ficar igual ao chartVolumeTanque
        prepared.datasets = prepared.datasets.map(ds2 => ({ ...ds2, maxBarThickness: 64, borderRadius: 8 }));

        // Mesclar opções do backend com opções locais
        const backendOptions = data.options || {};
        const localOptions = {
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'M³ (÷100)' }, ticks: { stepSize: 1, callback: v => Intl.NumberFormat('pt-BR').format(v) } },
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
        // Filtrar apenas supervisores com valor > 0
        const filtered = pairs.filter(p => p.value > 0);
        filtered.sort((a,b) => b.value - a.value);
        const sortedLabels = filtered.map(p => p.label);
        // Manter valores originais em M³ (sem divisão)
        const sortedValues = filtered.map(p => p.value);

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

        // Filtrar apenas entradas com valor > 0
        if (chartData.labels && chartData.datasets && chartData.datasets[0] && chartData.datasets[0].data) {
            const dsData = chartData.datasets[0].data;
            const keepIdx = dsData.map((v, i) => Number(v) > 0 ? i : -1).filter(i => i >= 0);
            chartData.labels = keepIdx.map(i => chartData.labels[i]);
            chartData.datasets = chartData.datasets.map(ds => ({
                ...ds,
                data: keepIdx.map(i => ds.data[i])
            }));
        }

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
     * Média de POB alocado x POB em espaço confinado por Dia
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

            // Cores distintas para facilitar leitura
            const prepared = {
                labels: chartPayload.labels || [],
                datasets: [
                    Object.assign({}, ds[0] || {}, { label: ds[0]?.label || 'POB Alocado (média)', backgroundColor: '#2563eb', borderColor: '#2563eb', borderRadius: 6, maxBarThickness: 36, barPercentage: 0.6, categoryPercentage: 0.6, order: 1 }),
                    Object.assign({}, ds[1] || {}, { label: ds[1]?.label || 'POB em Espaço Confinado (média)', backgroundColor: '#f59e0b', borderColor: '#f59e0b', borderRadius: 6, maxBarThickness: 36, barPercentage: 0.6, categoryPercentage: 0.6, order: 1 })
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
            // Filtrar para mostrar apenas dados a partir de dezembro
            const filteredIndices = [];
            const filteredLabels = [];
            (prepared.labels || []).forEach((label, i) => {
                const parts = String(label).split('/');
                let month = null;
                if (parts.length === 3) {
                    month = parseInt(parts[1], 10);
                } else if (parts.length === 2) {
                    month = parseInt(parts[0], 10);
                }
                const year = parts.length === 3 ? parseInt(parts[2], 10) : (parts.length === 2 ? parseInt(parts[1], 10) : null);
                if (month !== null && (month >= 12 || (year !== null && year >= 2026))) {
                    filteredIndices.push(i);
                    filteredLabels.push(label);
                }
            });

            if (filteredIndices.length > 0) {
                prepared.labels = filteredLabels;
                prepared.datasets.forEach(ds => {
                    ds.data = filteredIndices.map(i => ds.data[i]);
                });
                if (meta.counts) {
                    if (Array.isArray(meta.counts.rdos_per_day)) {
                        meta.counts.rdos_per_day = filteredIndices.map(i => meta.counts.rdos_per_day[i]);
                    }
                    if (Array.isArray(meta.counts.distinct_os_per_day)) {
                        meta.counts.distinct_os_per_day = filteredIndices.map(i => meta.counts.distinct_os_per_day[i]);
                    }
                }
            }

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
                    y: { beginAtZero: true, title: { display: true, text: 'POB (pessoas)' } }
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
            const sortedItems = originalItems.slice().sort((a, b) => (Number(b.value || 0) - Number(a.value || 0))).filter(i => Number(i.value || 0) > 0);
            const sortedLabels = sortedItems.map(i => (i.name || i.username || 'Desconhecido'));
            const sortedValues = sortedItems.map(i => Number(i.value || 0));

            // Voltar para barras verticais com cantos arredondados (design de ranking simples)
            // Gradiente em tons frios para diferenciar dos demais gráficos
            let grad = '#2563eb';
            try {
                const ctxCanvas = document.getElementById('chartTopSupervisores')?.getContext('2d');
                if (ctxCanvas) {
                    const g = ctxCanvas.createLinearGradient(0, 0, 0, 240);
                    g.addColorStop(0, '#2563eb');
                    g.addColorStop(1, '#8b5cf6');
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
            
            // Em mobile, mostrar apenas o ranking (sem canvas) para melhor legibilidade.
            const rankingOnlyMobile = (typeof window !== 'undefined' && window.matchMedia)
                ? window.matchMedia('(max-width: 900px)').matches
                : false;
            if (!rankingOnlyMobile) {
                updateChart('chartTopSupervisores', 'bar', prepared, mergedOptions);
            } else if (charts && charts['chartTopSupervisores']) {
                try { charts['chartTopSupervisores'].destroy(); } catch(e) {}
                try { delete charts['chartTopSupervisores']; } catch(e) {}
            }

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

async function loadChartBacklogCoordenador(filters){
    const metaEl = document.getElementById('chartBacklogCoordenadorMeta');
    try{
        const data = await fetchChartData('/api/rdo-dashboard/backlog_por_coordenador/', filters);
        if(!data || !data.success){
            throw new Error((data && data.error) || 'Erro ao obter backlog por coordenador');
        }

        const labels = Array.isArray(data.labels) ? data.labels : [];
        const prepared = {
            labels,
            datasets: [
                { label: 'Programada', data: Array.isArray(data.programada) ? data.programada : [], backgroundColor: '#f59e0b', borderColor: '#d97706', borderWidth: 1, stack: 'status', maxBarThickness: 30, borderRadius: 8, borderSkipped: false },
                { label: 'Em Andamento', data: Array.isArray(data.em_andamento) ? data.em_andamento : [], backgroundColor: '#38bdf8', borderColor: '#0284c7', borderWidth: 1, stack: 'status', maxBarThickness: 30, borderRadius: 8, borderSkipped: false },
                { label: 'Paralizada', data: Array.isArray(data.paralizada) ? data.paralizada : [], backgroundColor: '#f97316', borderColor: '#ea580c', borderWidth: 1, stack: 'status', maxBarThickness: 30, borderRadius: 8, borderSkipped: false },
                { label: 'Finalizada', data: Array.isArray(data.finalizada) ? data.finalizada : [], backgroundColor: '#22c55e', borderColor: '#16a34a', borderWidth: 1, stack: 'status', maxBarThickness: 30, borderRadius: 8, borderSkipped: false },
                { label: 'Cancelada', data: Array.isArray(data.cancelada) ? data.cancelada : [], backgroundColor: '#ef4444', borderColor: '#dc2626', borderWidth: 1, stack: 'status', maxBarThickness: 30, borderRadius: 8, borderSkipped: false }
            ]
        };

        const options = {
            indexAxis: 'y',
            plugins: {
                legend: { display: true, position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: function(ctx){
                            const value = Number(ctx.parsed && (ctx.parsed.x !== undefined ? ctx.parsed.x : ctx.parsed.y) || 0);
                            return `${ctx.dataset.label}: ${Intl.NumberFormat('pt-BR').format(value)} OS`;
                        }
                    }
                },
                barValuePlugin: { display: false }
            },
            scales: {
                x: {
                    stacked: true,
                    beginAtZero: true,
                    title: { display: true, text: 'Quantidade de OS' },
                    grid: { color: 'rgba(148, 163, 184, 0.16)' }
                },
                y: {
                    stacked: true,
                    grid: { display: false }
                }
            }
        };
        options.__preserveDatasetColors = true;
        updateChart('chartBacklogCoordenador', 'bar', prepared, options);

        if(metaEl){
            metaEl.textContent = `Top ${Number(data.top_n || labels.length || 0)} coordenadores no período selecionado.`;
        }
        return { key: 'backlog_coordenador', data };
    }catch(error){
        console.error('Erro ao carregar Backlog por Coordenador:', error);
        if(metaEl){
            metaEl.textContent = 'Sem dados disponíveis para os filtros aplicados.';
        }
        updateChart('chartBacklogCoordenador', 'bar', { labels: [], datasets: [{ label: 'Backlog', data: [] }] }, {
            plugins: { legend: { display: false }, barValuePlugin: { display: false } },
            scales: { x: { beginAtZero: true }, y: {} }
        });
        return { key: 'backlog_coordenador', data: {} };
    }
}

async function loadChartTaxaConclusaoCoordenador(filters){
    const metaEl = document.getElementById('chartTaxaConclusaoCoordenadorMeta');
    const helpEl = document.getElementById('chartTaxaConclusaoCoordenadorHelp');
    const insightsEl = document.getElementById('chartTaxaConclusaoCoordenadorInsights');
    try{
        const data = await fetchChartData('/api/rdo-dashboard/taxa_conclusao_coordenador/', filters);
        if(!data || !data.success){
            throw new Error((data && data.error) || 'Erro ao obter taxa de conclusao por coordenador');
        }

        const labels = Array.isArray(data.labels) ? data.labels : [];
        const taxas = Array.isArray(data.taxa_conclusao) ? data.taxa_conclusao : [];
        const finalizadas = Array.isArray(data.finalizada) ? data.finalizada : [];
        const emAndamento = Array.isArray(data.em_andamento) ? data.em_andamento : [];
        const bases = Array.isArray(data.base_metric) ? data.base_metric : [];
        const taxaPonderada = Number(data.taxa_ponderada || 0);
        const bestTaxa = taxas.length ? Math.max.apply(null, taxas.map((n) => Number(n) || 0)) : 0;
        const worstTaxa = taxas.length ? Math.min.apply(null, taxas.map((n) => Number(n) || 0)) : 0;
        const totalBase = bases.reduce((acc, v) => acc + (Number(v) || 0), 0);

        const prepared = {
            labels,
            datasets: [
                {
                    label: 'Taxa de conclusao (%)',
                    data: taxas,
                    backgroundColor: '#22c55e',
                    borderColor: '#16a34a',
                    borderWidth: 1,
                    maxBarThickness: 34,
                    borderRadius: 8,
                    borderSkipped: false
                }
            ]
        };

        const options = {
            indexAxis: 'y',
            plugins: {
                legend: { display: true, position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: function(ctx){
                            const idx = Number(ctx.dataIndex || 0);
                            const taxa = Number((ctx.parsed && (ctx.parsed.x !== undefined ? ctx.parsed.x : ctx.parsed.y)) || 0);
                            const fin = Number(finalizadas[idx] || 0);
                            const andm = Number(emAndamento[idx] || 0);
                            const base = Number(bases[idx] || 0);
                            return `Taxa: ${formatPercentPt(taxa, 1)}% · Finalizadas: ${Intl.NumberFormat('pt-BR').format(fin)} · Em andamento: ${Intl.NumberFormat('pt-BR').format(andm)} · Base: ${Intl.NumberFormat('pt-BR').format(base)}`;
                        }
                    }
                },
                barValuePlugin: { display: false }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    max: 100,
                    title: { display: true, text: 'Taxa de conclusao (%)' },
                    ticks: {
                        callback: function(v){ return `${Intl.NumberFormat('pt-BR').format(v)}%`; }
                    },
                    grid: { color: 'rgba(148, 163, 184, 0.16)' }
                },
                y: {
                    ticks: {
                        autoSkip: false,
                        maxRotation: 0,
                        minRotation: 0
                    },
                    grid: { display: false }
                }
            }
        };
        options.__preserveDatasetColors = true;
        updateChart('chartTaxaConclusaoCoordenador', 'bar', prepared, options);

        if(metaEl){
            metaEl.textContent = `Top ${Number(data.top_n || labels.length || 0)} coordenadores por taxa de conclusao no periodo selecionado.`;
        }
        if(helpEl){
            helpEl.textContent = 'Formula: Taxa de conclusao = Finalizadas / (Finalizadas + Em andamento) x 100. Programada, Paralizada e Cancelada nao entram na base da taxa.';
        }
        if(insightsEl){
            insightsEl.innerHTML = `
                <span class="mini-chip">Taxa ponderada: <b>${formatPercentPt(taxaPonderada, 1)}%</b></span>
                <span class="mini-chip">Melhor taxa: <b>${formatPercentPt(bestTaxa, 1)}%</b></span>
                <span class="mini-chip">Menor taxa: <b>${formatPercentPt(worstTaxa, 1)}%</b></span>
                <span class="mini-chip">Base total: <b>${Intl.NumberFormat('pt-BR').format(totalBase)}</b></span>
            `;
        }
        return { key: 'taxa_conclusao_coordenador', data };
    }catch(error){
        console.error('Erro ao carregar Taxa de Conclusao por Coordenador:', error);
        if(metaEl){
            metaEl.textContent = 'Sem dados disponíveis para os filtros aplicados.';
        }
        if(helpEl){
            helpEl.textContent = 'Sem dados suficientes para calcular a taxa de conclusao no periodo filtrado.';
        }
        if(insightsEl){
            insightsEl.innerHTML = `
                <span class="mini-chip">Taxa ponderada: <b>0,0%</b></span>
                <span class="mini-chip">Melhor taxa: <b>0,0%</b></span>
                <span class="mini-chip">Menor taxa: <b>0,0%</b></span>
                <span class="mini-chip">Base total: <b>0</b></span>
            `;
        }
        updateChart('chartTaxaConclusaoCoordenador', 'bar', { labels: [], datasets: [{ label: 'Taxa de conclusao (%)', data: [] }] }, {
            plugins: { legend: { display: false }, barValuePlugin: { display: false } },
            scales: { x: { beginAtZero: true, max: 100 }, y: {} }
        });
        return { key: 'taxa_conclusao_coordenador', data: {} };
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
                    borderColor: '#2563eb',
                    backgroundColor: 'rgba(37,99,235,0.10)',
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
    const totals = (map['kpi_totais'] && typeof map['kpi_totais'] === 'object') ? map['kpi_totais'] : {};

    // HH Confinado (mostrar em HH:MM, sem arredondamento para inteiro)
    const hhConfinadoTotal = (totals.hh_confinado_total !== undefined && totals.hh_confinado_total !== null)
        ? Number(totals.hh_confinado_total || 0)
        : sumDatasets(map['hh_confinado']);
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
    const hhForaTotal = (totals.hh_fora_total !== undefined && totals.hh_fora_total !== null)
        ? Number(totals.hh_fora_total || 0)
        : sumDatasets(map['hh_fora']);
    const hhForaFmt = formatHoursToHHMM(hhForaTotal);
    const hhForaEl = document.getElementById('kpi_hh_fora_value');
    if(hhForaEl){
        const intVal = Math.round(hhForaTotal || 0);
        hhForaEl.innerHTML = `<div class="value-main"><span id="kpi_hh_fora_int">${intVal}</span><span class="value-unit">h</span></div><span class="value-sep">-</span><div class="value-badge">${hhForaFmt}</div>`;
        animateValue('kpi_hh_fora_int', 0, intVal, 700, 0);
    }
    renderSparkline('kpi_hh_fora_spark', map['hh_fora'] || {});

    // Ensacamento
    const ensacTotal = (totals.ensacamento_total !== undefined && totals.ensacamento_total !== null)
        ? Number(totals.ensacamento_total || 0)
        : sumDatasets(map['ensacamento']);
    animateValue('kpi_ensacamento_value', 0, Math.round(ensacTotal), 800, 0);
    renderSparkline('kpi_ensacamento_spark', map['ensacamento'] || {});

    // Tambores
    const tambTotal = (totals.tambores_total !== undefined && totals.tambores_total !== null)
        ? Number(totals.tambores_total || 0)
        : sumDatasets(map['tambores']);
    animateValue('kpi_tambores_value', 0, Math.round(tambTotal), 800, 0);
    renderSparkline('kpi_tambores_spark', map['tambores'] || {});

    // Líquido
    const liquidoTotal = (totals.liquido_total !== undefined && totals.liquido_total !== null)
        ? Number(totals.liquido_total || 0)
        : sumDatasets(map['total_liquido']);
    // Mostrar líquido com 3 casas decimais
    animateValue('kpi_liquido_value', 0, liquidoTotal, 800, 3);
    renderSparkline('kpi_liquido_spark', map['total_liquido'] || {});

    // Tempo de uso da bomba (horas)
    try{
        const bombaTotal = (totals.tempo_bomba_total !== undefined && totals.tempo_bomba_total !== null)
            ? Number(totals.tempo_bomba_total || 0)
            : sumDatasets(map['tempo_bomba']);
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
            btn.className = 'btn-secondary';
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
