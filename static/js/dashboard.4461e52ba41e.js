// dashboard.js
// Depende de Chart.js (incluir CDN no template) e do utilitário fetchJson presente em scripts.js

document.addEventListener('DOMContentLoaded', function () {
    // Defaults visuais globais do Chart.js para harmonizar com o tema
    if (window.Chart && Chart.defaults) {
        Chart.defaults.font.family = getComputedStyle(document.body).fontFamily || 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
        Chart.defaults.font.size = 11;
        Chart.defaults.color = '#334155';
        Chart.defaults.plugins.legend.labels.usePointStyle = true;
    }

    // Aplica tema do dashboard (light/dark) — atualiza classe e cores do Chart.js
    function applyDashboardTheme(dark) {
        const panelEl = document.getElementById('dashboard-panel') || document.body;
        try {
            if (dark) panelEl.classList.add('dashboard-dark'); else panelEl.classList.remove('dashboard-dark');
        } catch(e) {}
        try {
            Chart.defaults.color = dark ? '#e2e8f0' : '#334155';
            Chart.defaults.plugins.tooltip.backgroundColor = dark ? '#0b1220' : '#0f172a';
        } catch(e) {}

        const gridX = dark ? 'rgba(226,232,240,0.06)' : 'rgba(15,23,42,0.06)';
        const gridY = dark ? 'rgba(226,232,240,0.04)' : 'rgba(15,23,42,0.08)';
        const tooltipBg = dark ? '#0b1220' : '#0f172a';

        [chartOrdens, chartStatus, chartTopClientes, chartMetodos, chartSupervisores].forEach(ch => {
            if (!ch) return;
            try {
                if (ch.options && ch.options.scales) {
                    if (ch.options.scales.x) ch.options.scales.x.grid = ch.options.scales.x.grid || {} , ch.options.scales.x.grid.color = gridX;
                    if (ch.options.scales.y) ch.options.scales.y.grid = ch.options.scales.y.grid || {} , ch.options.scales.y.grid.color = gridY;
                }
                if (ch.options && ch.options.plugins && ch.options.plugins.tooltip) ch.options.plugins.tooltip.backgroundColor = tooltipBg;
                // atualizar com wrapper que respeita preferência de reduzir animações quando painel não visível
                performChartUpdate(ch, 240);
            } catch(e) { /* ignore update errors */ }
        });
        try { localStorage.setItem('dash_dark_mode', dark ? '1' : '0'); } catch(e) {}
    }
    // UX: indicador "Atualizado em" (hora exata + relativo) e botão de atualizar agora
    let lastUpdatedAt = null;
    let lastUpdatedTimer = null;
    function formatTime(d){
        try {
            return new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(d);
        } catch(e) {
            const two=n=>String(n).padStart(2,'0');
            return `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
        }
    }
    function relativeFrom(date){
        if (!date) return '';
        const diff = Math.max(0, Math.floor((Date.now() - date.getTime())/1000));
        if (diff < 60) return 'há poucos segundos';
        const min = Math.floor(diff/60);
        if (min === 1) return 'há 1 minuto';
        if (min < 60) return `há ${min} minutos`;
        const h = Math.floor(min/60);
        return h === 1 ? 'há 1 hora' : `há ${h} horas`;
    }
    function renderLastUpdated(){
        const span = document.getElementById('dash_last_updated');
        if (!span) return;
        if (!lastUpdatedAt) { span.textContent = '—'; return; }
        const time = formatTime(lastUpdatedAt);
        const rel = relativeFrom(lastUpdatedAt);
        span.textContent = `Atualizado às ${time} (${rel})`;
    }
    function scheduleLastUpdatedTicker(){
        clearInterval(lastUpdatedTimer);
        lastUpdatedTimer = setInterval(renderLastUpdated, 30*1000);
    }
    const toggleBtn = document.getElementById('btn_dashboard_toggle');
    const panel = document.getElementById('dashboard-panel');

    if (toggleBtn && panel) {
        // Robust open/close: use .open class on panel and swap icon for FAB
        const openPanel = async () => {
            // show panel with transition
            panel.classList.add('open');
            // update button visual
            if (toggleBtn.classList.contains('dashboard-fab-btn')) {
                // swap icon to close
                const icon = toggleBtn.querySelector('.material-icons');
                if (icon) icon.textContent = 'close';
                toggleBtn.classList.add('open');
                toggleBtn.setAttribute('aria-pressed','true');
            } else {
                // legacy header button: set text
                toggleBtn.textContent = '✖ Fechar Dashboard';
            }
            await atualizarDashboard();
        };

        const closePanel = () => {
            // remove open class to start collapse transition
            panel.classList.remove('open');
            if (toggleBtn.classList.contains('dashboard-fab-btn')) {
                const icon = toggleBtn.querySelector('.material-icons');
                if (icon) icon.textContent = 'analytics';
                toggleBtn.classList.remove('open');
                toggleBtn.setAttribute('aria-pressed','false');
            } else {
                toggleBtn.textContent = '📊 Dashboard';
            }
            // after transition, we leave it collapsed (max-height handles visibility)
        };

        toggleBtn.addEventListener('click', () => {
            if (panel.classList.contains('open')) closePanel(); else openPanel();
        });
    }

    // Mostrar FAB apenas após a tela de loading desaparecer (mais robusto)
    (function showFabAfterLoading(){
        const fabWrap = document.getElementById('dashboard-fab');
        if (!fabWrap) return;

        // adicionar delay elegante antes de revelar o FAB para evitar "piscadas".
        let _fabTimer = null;
    const FAB_SHOW_DELAY_MS = 4000; // 4s - atraso intencional aumentado
        const makeVisible = (forceImmediate = false) => {
            try {
                if (fabWrap.classList.contains('ready')) return;
                if (forceImmediate) {
                    clearTimeout(_fabTimer);
                    _fabTimer = null;
                    fabWrap.classList.add('ready');
                    return;
                }
                // adicionar classe após pequeno delay (limpar timer anterior)
                clearTimeout(_fabTimer);
                _fabTimer = setTimeout(() => {
                    try { fabWrap.classList.add('ready'); } catch(e) { /* ignore */ }
                    _fabTimer = null;
                }, FAB_SHOW_DELAY_MS);
            } catch(e) { /* silent */ }
        };

        const loadingEl = document.getElementById('loadingScreen');
        if (!loadingEl) {
            // sem elemento de loading - usar evento load
            window.addEventListener('load', makeVisible);
            return;
        }

        // condição que considera a loading screen como 'oculta'
        function isLoadingHidden(el){
            try {
                if (!document.body.contains(el)) return true; // removido do DOM
                if (el.hasAttribute('hidden')) return true;
                if (el.classList.contains('hidden')) return true;
                const st = getComputedStyle(el);
                if (st.display === 'none' || st.visibility === 'hidden') return true;
                // considerar invisível quando totalmente transparente e sem pointer events
                if (('' + st.opacity) !== '' && parseFloat(st.opacity) === 0) return true;
            } catch(e){ /* ignore */ }
            return false;
        }

        // verificação periódica (robusta contra diferentes técnicas de hide/removal)
        const checkInterval = 150; // ms
        let checker = setInterval(() => {
            if (isLoadingHidden(loadingEl)) {
                makeVisible();
                clearInterval(checker);
                try { mo && mo.disconnect(); } catch(e){}
            }
        }, checkInterval);

        // observar remoção/atributos para resposta imediata
        const mo = new MutationObserver((mutations) => {
            if (isLoadingHidden(loadingEl)) {
                makeVisible();
                clearInterval(checker);
                mo.disconnect();
            }
        });
        try {
            mo.observe(document.body, { childList: true, subtree: true });
        } catch(e) { /* ignore */ }

        // garantia final: quando a janela terminar de carregar mostramos também
        window.addEventListener('load', () => { makeVisible(); try{ clearInterval(checker); mo.disconnect(); }catch(e){} });
    })();

    // inserir controles de filtro (data, cliente, unidade) se não existirem
    (function ensureFilterControls(){
        const filtersRowId = 'dashboard-filters-row';
        let row = document.getElementById(filtersRowId);
        if (!row) {
            row = document.createElement('div');
            row.id = filtersRowId;
            row.className = 'dashboard-filters';

            const start = document.createElement('input');
            start.type = 'date';
            start.id = 'dash_start';
            start.title = 'Data início';

            const end = document.createElement('input');
            end.type = 'date';
            end.id = 'dash_end';
            end.title = 'Data fim';

            const cliente = document.createElement('input');
            cliente.type = 'text';
            cliente.id = 'dash_cliente';
            cliente.placeholder = 'Cliente';
            cliente.setAttribute('list','clientes_datalist');

            const unidade = document.createElement('input');
            unidade.type = 'text';
            unidade.id = 'dash_unidade';
            unidade.placeholder = 'Unidade';
            unidade.setAttribute('list','unidades_datalist');

            const btnApply = document.createElement('button');
            btnApply.className = 'btn_os btn-dashboard-action';
            btnApply.textContent = 'Aplicar filtros';
            btnApply.type = 'button';
            btnApply.addEventListener('click', function(){ atualizarDashboard(); });

            // seletor de intervalo de polling (em segundos)
            const selectInterval = document.createElement('select');
            selectInterval.id = 'dash_interval';
            selectInterval.title = 'Intervalo de atualização';
            ['5','15','30','60'].forEach(v => {
                const o = document.createElement('option'); o.value = v; o.textContent = v + 's';
                selectInterval.appendChild(o);
            });
            // carregar preferencia do localStorage
            try { const saved = localStorage.getItem('dash_poll_interval'); if (saved) selectInterval.value = saved; } catch(e){}
            selectInterval.addEventListener('change', function(){
                try { localStorage.setItem('dash_poll_interval', this.value); } catch(e){}
                restartPolling();
            });

            // botão toggle modo escuro
            const darkToggle = document.createElement('button');
            darkToggle.id = 'dash_dark_toggle';
            darkToggle.type = 'button';
            darkToggle.className = 'btn_os btn-dashboard-secondary';
            darkToggle.title = 'Alternar modo escuro';
            darkToggle.style.marginLeft = '8px';
            darkToggle.textContent = '🌙';
            darkToggle.addEventListener('click', function(){
                try {
                    const panelEl = document.getElementById('dashboard-panel') || document.body;
                    const next = !panelEl.classList.contains('dashboard-dark');
                    applyDashboardTheme(next);
                } catch(e) {}
            });

            const btnClear = document.createElement('button');
            btnClear.className = 'btn_os btn-dashboard-secondary';
            btnClear.textContent = 'Limpar';
            btnClear.type = 'button';
            btnClear.addEventListener('click', function(){
                document.getElementById('dash_start').value = '';
                document.getElementById('dash_end').value = '';
                document.getElementById('dash_cliente').value = '';
                document.getElementById('dash_unidade').value = '';
                atualizarDashboard();
            });

            row.appendChild(start);
            row.appendChild(end);
            row.appendChild(cliente);
            row.appendChild(unidade);
            row.appendChild(btnApply);
            row.appendChild(selectInterval);
            row.appendChild(darkToggle);
            // trocar posição: primeiro o botão Limpar, depois Atualizar (swap solicitado)
            row.appendChild(btnClear);
            // botão atualizar agora
            const btnRefresh = document.createElement('button');
            btnRefresh.className = 'btn_os btn-dashboard-secondary';
            btnRefresh.id = 'dash_refresh_now';
            btnRefresh.title = 'Atualizar agora';
            btnRefresh.textContent = 'Atualizar';
            btnRefresh.type = 'button';
            btnRefresh.addEventListener('click', function(){ atualizarDashboard(); });
            row.appendChild(btnRefresh);
            // indicador de última atualização
            const last = document.createElement('span');
            last.id = 'dash_last_updated';
            last.className = 'dash-last-updated';
            last.setAttribute('aria-live','polite');
            last.textContent = '—';
            row.appendChild(last);

            const panelTop = document.querySelector('#dashboard-panel .kpis');
            if (panelTop && panelTop.parentNode) {
                panelTop.parentNode.insertBefore(row, panelTop);
            } else {
                document.getElementById('dashboard-panel').insertBefore(row, document.getElementById('dashboard-panel').firstChild);
            }
            // aplicar preferência salva de tema
            try {
                const saved = localStorage.getItem('dash_dark_mode');
                if (saved === '1') applyDashboardTheme(true);
                else if (saved === '0') applyDashboardTheme(false);
                else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                    // sem preferência salva: usar a preferência do sistema (sem pedir permissão)
                    applyDashboardTheme(true);
                }
            } catch(e) {}
            // iniciar ticker de tempo relativo
            scheduleLastUpdatedTicker();
        }
    })();

    // Chart instances
    let chartOrdens = null;
    let chartStatus = null;
    let chartSupervisores = null;
    let chartTopClientes = null;
    let chartMetodos = null;

    function criarChartsVazios() {
        const ctxOrdens = document.getElementById('chartOrdens').getContext('2d');
        chartOrdens = new Chart(ctxOrdens, {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, animation: { duration: 400, easing: 'easeOutQuad' } }
        });

        const ctxStatus = document.getElementById('chartStatus').getContext('2d');
        // Plugin para desenhar texto no centro do doughnut (total)
        const centerTextPlugin = {
            id: 'centerText',
            afterDraw(chart, args, opts){
                const cfg = chart.config.options?.plugins?.centerText;
                if (!cfg || cfg.display === false) return;
                const {ctx, chartArea} = chart;
                const dataset = chart.data.datasets?.[0];
                if (!dataset) return;
                const total = (dataset.data || []).reduce((a,b)=>a + (Number(b)||0), 0);
                const cx = (chartArea.left + chartArea.right) / 2;
                const cy = (chartArea.top + chartArea.bottom) / 2;
                ctx.save();
                ctx.fillStyle = cfg.color || '#0f172a';
                ctx.font = `600 ${cfg.fontSize || 14}px ${Chart.defaults.font.family}`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(total, cx, cy);
                ctx.restore();
            }
        };

        chartStatus = new Chart(ctxStatus, {
            type: 'doughnut',
            data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: '62%', animation: { duration: 400, easing: 'easeOutQuad' }, plugins: { legend: { position: 'top' }, centerText: { display: true, fontSize: 14, color: '#0f172a' } } },
            plugins: [centerTextPlugin]
        });

        // gráfico de supervisores: doughnut moderno com resumo Embarque vs Disponíveis
        const elSupervisores = document.getElementById('chartSupervisores');
        if (elSupervisores) {
            const ctxSuper = elSupervisores.getContext('2d');
            chartSupervisores = new Chart(ctxSuper, {
                type: 'doughnut',
                data: { labels: ['Embarque','Disponíveis'], datasets: [{ data: [0,0], backgroundColor: ['#e53935','#4caf50'] }] },
                options: { responsive: true, maintainAspectRatio: false, cutout: '62%', plugins: { legend: { position: 'bottom' } }, animation: { duration: 420, easing: 'easeOutQuad' } }
            });
        }

        // Plugin: desenhar valor na ponta direita de cada barra (ranking horizontal)
        const valueLabelRight = {
            id: 'valueLabelRight',
            afterDatasetsDraw(chart, args, opts){
                const { ctx } = chart;
                const dataset = chart.data.datasets?.[0];
                if (!dataset) return;
                ctx.save();
                ctx.fillStyle = '#0f172a';
                ctx.font = `600 11px ${Chart.defaults.font.family}`;
                const metas = chart.getDatasetMeta(0).data || [];
                metas.forEach((bar, i) => {
                    const v = dataset.data?.[i];
                    if (v == null) return;
                    const text = String(v);
                    const x = (chart.options.indexAxis === 'y') ? (bar.x + 8) : (bar.x + bar.width + 6);
                    const y = bar.y;
                    ctx.textBaseline = 'middle';
                    ctx.textAlign = 'left';
                    ctx.fillText(text, x, y);
                });
                ctx.restore();
            }
        };

        // Plugin: rótulo de valor no topo das barras (vertical)
        const valueLabelTop = {
            id: 'valueLabelTop',
            afterDatasetsDraw(chart){
                if (chart.options.indexAxis === 'y') return; // só para colunas
                const { ctx } = chart;
                const ds = chart.data.datasets?.[0];
                if (!ds) return;
                ctx.save();
                ctx.fillStyle = '#0f172a';
                ctx.font = `600 11px ${Chart.defaults.font.family}`;
                const metas = chart.getDatasetMeta(0).data || [];
                metas.forEach((bar, i) => {
                    const v = ds.data?.[i];
                    if (v == null) return;
                    const text = String(v);
                    const x = bar.x;
                    const y = bar.y - 8; // acima da barra
                    ctx.textBaseline = 'bottom';
                    ctx.textAlign = 'center';
                    ctx.fillText(text, x, y);
                });
                ctx.restore();
            }
        };

        // Plugin: sombra suave nas barras (efeito moderno)
        const softShadow = {
            id: 'softShadow',
            beforeDatasetsDraw(chart, args, pluginOptions){
                const {ctx} = chart;
                ctx.save();
                ctx.shadowColor = 'rgba(2,6,23,0.12)';
                ctx.shadowBlur = 12;
                ctx.shadowOffsetX = 0;
                ctx.shadowOffsetY = 6;
            },
            afterDatasetsDraw(chart){
                chart.ctx.restore();
            }
        };

        // Plugin: trilha (track) por trás das barras horizontais — visual de "progress bar"
        const barTrack = {
            id: 'barTrack',
            beforeDatasetsDraw(chart){
                if (!chart || chart.config.type !== 'bar') return;
                if (chart.options.indexAxis !== 'y') return; // apenas horizontais
                const { ctx, chartArea, scales } = chart;
                const meta = chart.getDatasetMeta(0);
                const bars = meta?.data || [];
                const x0 = scales.x.getPixelForValue(0);
                ctx.save();
                ctx.lineCap = 'round';
                ctx.strokeStyle = 'rgba(15,23,42,0.05)';
                bars.forEach(bar => {
                    const y = bar.y;
                    const thickness = Math.max(8, Math.min(18, bar?.height * 0.6 || 12));
                    ctx.lineWidth = thickness;
                    ctx.beginPath();
                    ctx.moveTo(x0, y);
                    ctx.lineTo(chartArea.right - 8, y);
                    ctx.stroke();
                });
                ctx.restore();
            }
        };

        // Helper para gradiente horizontal
        function gradientFor(chart, from, to){
            const {ctx, chartArea} = chart;
            if (!chartArea) return from;
            const g = ctx.createLinearGradient(chartArea.left, 0, chartArea.right, 0);
            g.addColorStop(0, from);
            g.addColorStop(1, to);
            return g;
        }

        // Opções modernas compartilhadas para rankings horizontais
        const modernRankingOptions = {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: {top: 6, right: 14, bottom: 6, left: 6} },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0f172a',
                    titleColor: '#e2e8f0',
                    bodyColor: '#e2e8f0',
                    padding: 10,
                    callbacks: {
                        label: (ctx) => `${ctx.label}: ${ctx.parsed.x}`
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: { color: 'rgba(15,23,42,0.08)' },
                    ticks: { precision: 0, color: '#64748b', font: { weight: 500 } }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#0f172a', font: { weight: 600 } }
                }
            },
            elements: {
                bar: { borderRadius: 12, borderSkipped: false, borderWidth: 0, barThickness: 26, maxBarThickness: 28 }
            },
            animation: { duration: 420, easing: 'easeOutQuad' }
        };

        // Opções específicas para Top Clientes (vertical, moderno): colunas finas + tooltip com percentual
        const topClientesOptions = {
            indexAxis: 'x',
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 8, right: 18, bottom: 18, left: 18 } },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0f172a',
                    titleColor: '#e2e8f0',
                    bodyColor: '#e2e8f0',
                    padding: 10,
                    callbacks: {
                        label: (ctx) => {
                            const val = ctx.parsed.y || 0;
                            const ds = ctx.dataset?.data || [];
                            const total = ds.reduce((a,b)=>a + (Number(b)||0), 0) || 1;
                            const pct = ((val/total)*100).toFixed(0);
                            return `${ctx.label}: ${val} (${pct}%)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#0f172a', font: { weight: 600 }, maxRotation: 25, minRotation: 0 }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(15,23,42,0.08)' },
                    ticks: { precision: 0, color: '#64748b', font: { weight: 500 } }
                }
            },
            elements: {
                // barras finas: igual ao estilo dos Métodos para consistência
                // barras ainda mais finas (afinação fina)
                bar: { borderRadius: { topLeft: 10, topRight: 10, bottomLeft: 0, bottomRight: 0 }, borderSkipped: false, barThickness: 6, maxBarThickness: 8 }
            },
            animation: { duration: 420, easing: 'easeOutQuad' }
        };

        const colorByRank = (chart, index, hover = false) => {
            // paleta mais suave/azulada, com variação leve por posição
            const palettes = [
                { from: hover ? '#93c5fd' : '#60a5fa', to: hover ? '#3b82f6' : '#2563eb' },
                { from: hover ? '#7dd3fc' : '#38bdf8', to: hover ? '#06b6d4' : '#0ea5b7' },
                { from: hover ? '#86efac' : '#34d399', to: hover ? '#059669' : '#047857' }
            ];
            const fallback = hover
                ? { from: '#a5b4fc', to: '#6366f1' }
                : { from: '#60a5fa', to: '#2563eb' };
            const palette = palettes[index] || fallback;
            return gradientFor(chart, palette.from, palette.to);
        };

        // Plugin: badge com posição do ranking à esquerda
        const rankBadge = {
            id: 'rankBadge',
            afterDatasetsDraw(chart){
                if (chart.options.indexAxis !== 'y') return;
                const { ctx, chartArea } = chart;
                const meta = chart.getDatasetMeta(0);
                const items = meta?.data || [];
                ctx.save();
                ctx.font = `700 11px ${Chart.defaults.font.family}`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                items.forEach((bar, index) => {
                    const rank = index + 1;
                    const cy = bar.y;
                    const cx = chartArea.left - 18;
                    let bg = '#dbeafe';
                    let color = '#1d4ed8';
                    if (rank === 1) { bg = '#fef3c7'; color = '#b45309'; }
                    else if (rank === 2) { bg = '#e5e7eb'; color = '#374151'; }
                    else if (rank === 3) { bg = '#ffedd5'; color = '#c2410c'; }
                    ctx.beginPath();
                    ctx.fillStyle = bg;
                    ctx.strokeStyle = 'rgba(15,23,42,0.08)';
                    ctx.lineWidth = 1;
                    ctx.arc(cx, cy, 11, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.stroke();
                    ctx.fillStyle = color;
                    ctx.fillText(rank, cx, cy + 0.5);
                });
                ctx.restore();
            }
        };

        // Top Clientes — vertical (colunas estilizadas com lollipop no topo)
        const ctxTopClientes = document.getElementById('chartTopClientes')?.getContext('2d');
        if (ctxTopClientes) {
            // plugin que desenha uma trilha vertical leve atrás de cada coluna
            const barTrackVertical = {
                id: 'barTrackVertical',
                beforeDatasetsDraw(chart){
                    if (!chart || chart.config.type !== 'bar') return;
                    if (chart.options.indexAxis !== 'x') return;
                    const { ctx, chartArea, scales } = chart;
                    const meta = chart.getDatasetMeta(0);
                    const bars = meta?.data || [];
                    ctx.save();
                    ctx.fillStyle = 'rgba(2,6,23,0.03)';
                    bars.forEach(bar => {
                        const x = bar.x - (bar.width/2);
                        const w = bar.width;
                        const y = chartArea.top + 6;
                        const h = chartArea.bottom - chartArea.top - 12;
                        const r = Math.min(10, Math.max(6, w*0.2));
                        // rounded rect
                        ctx.beginPath();
                        ctx.moveTo(x + r, y);
                        ctx.lineTo(x + w - r, y);
                        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
                        ctx.lineTo(x + w, y + h - r);
                        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
                        ctx.lineTo(x + r, y + h);
                        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
                        ctx.lineTo(x, y + r);
                        ctx.quadraticCurveTo(x, y, x + r, y);
                        ctx.closePath();
                        ctx.fill();
                    });
                    ctx.restore();
                }
            };

            chartTopClientes = new Chart(ctxTopClientes, {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Top Clientes',
                        data: [],
                        // largura relativa alinhada com o gráfico de Métodos (ainda mais fina)
                        categoryPercentage: 0.28,
                        barPercentage: 0.45,
                        backgroundColor: (ctx) => colorByRank(ctx.chart, ctx.dataIndex, false),
                        hoverBackgroundColor: (ctx) => colorByRank(ctx.chart, ctx.dataIndex, true)
                    }]
                },
                options: topClientesOptions,
                plugins: [barTrackVertical, softShadow, valueLabelTop]
            });
        }

        // Métodos mais utilizados (colunas verticais com rótulos no eixo X)
        const ctxMetodos = document.getElementById('chartMetodos')?.getContext('2d');
        if (ctxMetodos) {
            const metodosOptions = {
                indexAxis: 'x',
                responsive: true,
                maintainAspectRatio: false,
                layout: { padding: { top: 8, right: 8, bottom: 8, left: 8 } },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#0f172a',
                        titleColor: '#e2e8f0',
                        bodyColor: '#e2e8f0',
                        padding: 10,
                        callbacks: {
                            label: (ctx) => `${ctx.label}: ${ctx.parsed.y}`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(15,23,42,0.06)' },
                        ticks: { color: '#0f172a', font: { weight: 600 }, autoSkip: false, maxRotation: 20, minRotation: 0 }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(15,23,42,0.08)' },
                        ticks: { precision: 0, color: '#64748b', font: { weight: 500 } }
                    }
                },
                // barras ainda mais finas e delicadas (afinação fina)
                elements: { bar: { borderRadius: { topLeft: 12, topRight: 12, bottomLeft: 0, bottomRight: 0 }, borderSkipped: false, barThickness: 6, maxBarThickness: 8 } },
                animation: { duration: 420, easing: 'easeOutQuad' }
            };
            chartMetodos = new Chart(ctxMetodos, {
                type: 'bar',
                data: { labels: [], datasets: [{ label: 'Métodos', data: [], categoryPercentage: 0.28, barPercentage: 0.45, backgroundColor: (ctx)=>{ const chart = ctx.chart; return gradientFor(chart,'#60a5fa','#2563eb'); }, hoverBackgroundColor: (ctx)=>{ const chart = ctx.chart; return gradientFor(chart,'#2563eb','#1e40af'); } }] },
                options: metodosOptions,
                plugins: [softShadow, valueLabelTop]
            });
        }
    }

    // utilitário para comparação rasa de arrays
    function arraysEqual(a, b) {
        if (!a || !b) return false;
        if (a.length !== b.length) return false;
        for (let i = 0; i < a.length; i++) {
            if (String(a[i]) !== String(b[i])) return false;
        }
        return true;
    }

    function gerarCores(n) {
        const cores = [];
        const palette = ['#3e95cd','#8e5ea2','#3cba9f','#e8c3b9','#c45850','#ffb74d','#4db6ac','#9575cd','#64b5f6','#81c784'];
        for (let i=0;i<n;i++) cores.push(palette[i % palette.length]);
        return cores;
    }

    // Paleta moderna para o ranking (variação em HSL)
    function gerarCoresRanking(n){
        const hues = [222, 200, 180, 160, 140, 262, 280, 300, 20, 12];
        const arr = [];
        for (let i=0;i<n;i++) {
            const h = hues[i % hues.length];
            // HSL moderno com alpha levemente translúcido
            arr.push(`hsl(${h} 70% 55% / 0.9)`);
        }
        return arr;
    }

    // Ajusta a altura de um elemento de ranking (ex: charts horizontais) com fallback
    function ajustarAlturaRanking(labels, preferredId){
        try {
            // ids candidatas (preferredId primeiro, depois alternativas conhecidas)
            const ids = [(preferredId || ''), 'chartTopClientes', 'chartMetodos', 'chartServicos'];
            let el = null;
            for (const id of ids) {
                if (!id) continue;
                const e = document.getElementById(id);
                if (e) { el = e; break; }
            }
            if (!el) return;
            const base = 22; // altura por item (mais compacto para barras finas)
            const padding = 14;
            // limites mais compactos para gráficos com poucos itens
            const desired = Math.max(96, Math.min(380, (Array.isArray(labels) ? labels.length : 0) * base + padding));
            el.style.height = desired + 'px';
        } catch(e) { /* ignore */ }
    }

    async function atualizarKPIs() {
        try {
            const q = buildQuery();
            const resp = await fetchJson('/api/dashboard/kpis/' + q);
            if (resp.success) {
                // Atualizar somente se houver mudança para evitar flicker
                const mapping = [ ['kpi-total-val', resp.total], ['kpi-abertas-val', resp.abertas], ['kpi-concluidas-val', resp.concluidas_mes], ['kpi-media-val', parseFloat(resp.tempo_medio_operacao).toFixed(1)] ];
                mapping.forEach(([id, val]) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    const cur = String(el.textContent || '').trim();
                    const next = String(val === null || val === undefined ? '—' : val);
                    if (cur !== next) {
                        // animação sutil: aplicar classe para highlight e trocar texto
                        el.classList.add('kpi-updating');
                        el.textContent = next;
                        setTimeout(() => el.classList.remove('kpi-updating'), 700);
                    }
                });

                // Atualizar breakdown por status operacional se estiver presente
                if (resp.status_breakdown) {
                    try {
                        const breakdown = resp.status_breakdown;
                        // ordem desejada
                        const statuses = ['Programada','Em Andamento','Paralizada','Finalizada'];
                        statuses.forEach(s => {
                            // criar id slug (ex: 'Em Andamento' -> 'em-andamento')
                            const slug = s.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z\-]/g,'');
                            const elId = 'kpi-status-' + slug + '-val';
                            const el = document.getElementById(elId);
                            const val = breakdown[s] != null ? breakdown[s] : (breakdown[slug] != null ? breakdown[slug] : 0);
                            if (el) {
                                const cur = String(el.textContent || '').trim();
                                const next = String(val === null || val === undefined ? '—' : val);
                                if (cur !== next) {
                                    el.classList.add('kpi-updating');
                                    el.textContent = next;
                                    setTimeout(() => el.classList.remove('kpi-updating'), 700);
                                }
                            }
                        });

                        // Se o chart de status já existe, atualiza os dados a partir do breakdown para manter consistência
                        if (chartStatus) {
                            const labels = ['Programada','Em Andamento','Paralizada','Finalizada'];
                            const data = labels.map(l => {
                                const v = resp.status_breakdown[l];
                                return (v == null) ? 0 : Number(v);
                            });
                            const oldLabels = chartStatus.data.labels || [];
                            const oldData = (chartStatus.data.datasets[0] && chartStatus.data.datasets[0].data) ? chartStatus.data.datasets[0].data : [];
                            // Atualizar somente se houver mudança
                            if (!arraysEqual(oldLabels, labels) || !arraysEqual(oldData, data)) {
                                chartStatus.data.labels = labels;
                                chartStatus.data.datasets[0].data = data;
                                chartStatus.data.datasets[0].backgroundColor = gerarCores(data.length);
                                performChartUpdate(chartStatus, 400);
                            }
                        }
                    } catch(e) {
                        console.warn('Erro ao aplicar status_breakdown nos KPIs', e);
                    }
                }
            }
        } catch (e) {
            console.error('Erro ao atualizar KPIs', e);
        }
    }

    async function atualizarOrdensPorDia() {
        try {
            const q = buildQuery();
            const resp = await fetchJson('/api/dashboard/ordens_por_dia/' + q);
            if (resp.success) {
                // Atualizar somente se labels ou dados mudarem
                const newLabels = resp.labels || [];
                const newDataset = (resp.datasets && resp.datasets[0] && resp.datasets[0].data) ? resp.datasets[0].data : [];
                const oldLabels = chartOrdens.data.labels || [];
                const oldData = (chartOrdens.data.datasets[0] && chartOrdens.data.datasets[0].data) ? chartOrdens.data.datasets[0].data : [];
                if (!arraysEqual(oldLabels, newLabels) || !arraysEqual(oldData, newDataset)) {
                    chartOrdens.data.labels = newLabels;
                    chartOrdens.data.datasets = resp.datasets;
                    performChartUpdate(chartOrdens, 400);
                }
            }
        } catch (e) {
            console.error('Erro ao buscar ordens por dia', e);
        }
    }

    async function atualizarStatus() {
        try {
            const q = buildQuery();
            const resp = await fetchJson('/api/dashboard/status_os/' + q);
            if (resp.success) {
                const newLabels = resp.labels || [];
                const newValues = resp.values || [];
                const oldLabels = chartStatus.data.labels || [];
                const oldValues = chartStatus.data.datasets[0] && chartStatus.data.datasets[0].data ? chartStatus.data.datasets[0].data : [];
                if (!arraysEqual(oldLabels, newLabels) || !arraysEqual(oldValues, newValues)) {
                    chartStatus.data.labels = newLabels;
                    chartStatus.data.datasets[0].data = newValues;
                    chartStatus.data.datasets[0].backgroundColor = gerarCores(newValues.length);
                    performChartUpdate(chartStatus, 400);
                }
            }
        } catch (e) {
            console.error('Erro ao buscar status', e);
        }
    }

    async function atualizarTopClientes() {
        try {
            const q = buildQuery();
            const resp = await fetchJson('/api/dashboard/top_clientes/?top=10' + (q ? '&' + q.replace(/^\?/, '') : ''));
            if (resp.success && chartTopClientes) {
                const labels = resp.labels || [];
                const values = (resp.values || []).map(v => Number(v)||0);
                const pairs = labels.map((l,i)=>({l, v: values[i]||0})).sort((a,b)=> b.v - a.v);
                const TOP_N = 7;
                const top = pairs.slice(0, TOP_N);
                const rest = pairs.slice(TOP_N);
                const restSum = rest.reduce((a,p)=>a+p.v,0);
                if (restSum > 0) top.push({ l: 'Outros', v: restSum });
                const newLabels = top.map(p=>p.l);
                const newValues = top.map(p=>p.v);
                const oldLabels = chartTopClientes.data.labels || [];
                const oldValues = chartTopClientes.data.datasets[0] && chartTopClientes.data.datasets[0].data ? chartTopClientes.data.datasets[0].data : [];
                if (!arraysEqual(oldLabels, newLabels) || !arraysEqual(oldValues, newValues)) {
                    chartTopClientes.data.labels = newLabels;
                    chartTopClientes.data.datasets[0].data = newValues;
                    // manter gradiente configurado na criação
                    performChartUpdate(chartTopClientes, 420);
                }
            }
        } catch (e) { console.error('Erro ao buscar top clientes', e); }
    }

    // gráfico de "tempo médio supervisor" removido conforme solicitação

    async function atualizarMetodos() {
        try {
            const q = buildQuery();
            const resp = await fetchJson('/api/dashboard/metodos_mais_utilizados/?top=10' + (q ? '&' + q.replace(/^\?/, '') : ''));
            if (resp.success && chartMetodos) {
                const labels = resp.labels || [];
                const values = (resp.values || []).map(v => Number(v)||0);
                const pairs = labels.map((l,i)=>({l, v: values[i]||0})).sort((a,b)=> b.v - a.v);
                const TOP_N = 7;
                const top = pairs.slice(0, TOP_N);
                const rest = pairs.slice(TOP_N);
                const restSum = rest.reduce((a,p)=>a+p.v,0);
                if (restSum > 0) top.push({ l: 'Outros', v: restSum });
                const newLabels = top.map(p=>p.l);
                const newValues = top.map(p=>p.v);
                const oldLabels = chartMetodos.data.labels || [];
                const oldValues = chartMetodos.data.datasets[0] && chartMetodos.data.datasets[0].data ? chartMetodos.data.datasets[0].data : [];
                if (!arraysEqual(oldLabels, newLabels) || !arraysEqual(oldValues, newValues)) {
                    // para colunas, não ajustar altura pelo número de labels
                    chartMetodos.data.labels = newLabels;
                    chartMetodos.data.datasets[0].data = newValues;
                    // manter gradiente configurado na criação
                    performChartUpdate(chartMetodos, 420);
                }
            }
        } catch (e) { console.error('Erro ao buscar metodos', e); }
    }

    async function atualizarSupervisores() {
        try {
            const q = buildQuery();
            const resp = await fetchJson('/api/dashboard/supervisores_status/' + q);
            if (resp.success) {
                // Modern UX: mostrar doughnut com Embarque vs Disponíveis
                const summary = resp.summary || { em_embarque: 0, disponiveis: 0 };
                const em = Number(summary.em_embarque || 0);
                const dis = Number(summary.disponiveis || 0);
                if (chartSupervisores) {
                    const oldData = chartSupervisores.data.datasets[0] && chartSupervisores.data.datasets[0].data ? chartSupervisores.data.datasets[0].data : [];
                    if (!arraysEqual(oldData, [em, dis])) {
                        chartSupervisores.data.datasets[0].data = [em, dis];
                        performChartUpdate(chartSupervisores, 420);
                    }
                }

                // Atualizar pequenas KPIs com as contagens resumidas (Evitar lista longa)
                const emEl = document.getElementById('kpi-supervisores-em-val');
                const disEl = document.getElementById('kpi-supervisores-disponiveis-val');
                const totalEl = document.getElementById('kpi-supervisores-total-val');
                if (emEl) {
                    const cur = String(emEl.textContent || '').trim();
                    const next = String(em);
                    if (cur !== next) {
                        emEl.classList.add('kpi-updating');
                        emEl.textContent = next;
                        setTimeout(() => emEl.classList.remove('kpi-updating'), 700);
                    }
                }
                if (disEl) {
                    const cur2 = String(disEl.textContent || '').trim();
                    const next2 = String(dis);
                    if (cur2 !== next2) {
                        disEl.classList.add('kpi-updating');
                        disEl.textContent = next2;
                        setTimeout(() => disEl.classList.remove('kpi-updating'), 700);
                    }
                }
                // atualizar KPI total de supervisores (em + disponíveis)
                if (totalEl) {
                    const total = em + dis;
                    const curT = String(totalEl.textContent || '').trim();
                    const nextT = String(total);
                    if (curT !== nextT) {
                        totalEl.classList.add('kpi-updating');
                        totalEl.textContent = nextT;
                        setTimeout(() => totalEl.classList.remove('kpi-updating'), 700);
                    }
                }
            }
        } catch (e) {
            console.error('Erro ao buscar supervisores', e);
        }
    }

    // utilitário pequeno para escapar HTML em strings usadas no innerHTML
    function escapeHtml(str){
        if (!str && str !== 0) return '';
        return String(str).replace(/[&<>\"']/g, function(s){
            return ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'})[s];
        });
    }

    function buildQuery(){
        const params = new URLSearchParams();
        const start = document.getElementById('dash_start').value;
        const end = document.getElementById('dash_end').value;
        const cliente = document.getElementById('dash_cliente').value;
        const unidade = document.getElementById('dash_unidade').value;
        if (start) params.set('start', start);
        if (end) params.set('end', end);
        if (cliente) params.set('cliente', cliente);
        if (unidade) params.set('unidade', unidade);
        const s = params.toString();
        return s ? ('?' + s) : '';
    }

    async function atualizarDashboard() {
        // show loading skeletons to avoid flicker
        showLoadingIndicators();
        if (!chartOrdens) criarChartsVazios();
        // Atualizar os painéis principais: KPIs, ordens, status, rankings (Top Clientes, Supervisores tempo médio, Métodos) e supervisores
        try {
            await Promise.all([
                atualizarKPIs(),
                atualizarOrdensPorDia(),
                atualizarStatus(),
                atualizarTopClientes(),
                atualizarMetodos(),
                atualizarSupervisores()
            ]);
        } finally {
            // independentemente de sucesso, registre momento da tentativa de atualização
            lastUpdatedAt = new Date();
            renderLastUpdated();
            // hide skeletons após renderizar (ligeiro delay para suavizar transição)
            setTimeout(hideLoadingIndicators, 180);
        }
    }

    // Mostrar e esconder indicadores de loading (toggle de classe no painel)
    // utilitário: checa se um elemento está visível na viewport
    function isElementInViewport(el){
        try{
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const vh = window.innerHeight || document.documentElement.clientHeight;
            return rect.bottom > 0 && rect.top < vh;
        }catch(e){ return false; }
    }

    // utilitário: respeitar prefers-reduced-motion OU reduzir animações se painel não estiver visível
    function shouldReduceAnimations(){
        try{
            if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return true;
        }catch(e){}
        const panelEl = document.getElementById('dashboard-panel');
        if (!panelEl) return true; // sem painel, fique conservador
        // se painel aberto mas fora da viewport, reduzir animações
        if (panelEl.classList.contains('open') && !isElementInViewport(panelEl)) return true;
        return false;
    }

    // wrapper para atualizar charts respeitando a política de animação
    function performChartUpdate(chart, defaultDuration){
        try{
            if (!chart) return;
            // se devemos reduzir animações porque o painel está offscreen, adiar o repaint
            if (shouldReduceAnimations()) {
                try { chart.__deferred = true; } catch(e){}
                return; // não chamar chart.update()
            }
            // se havia atualização adiada, limpa a marcação antes de redesenhar
            try { chart.__deferred = false; } catch(e){}
            const dur = (defaultDuration || 0);
            chart.update({ duration: dur });
        }catch(e){ /* silent */ }
    }

    // forçar flush de todos os charts marcados como adiados
    function flushDeferredCharts() {
        try{
            const charts = [chartOrdens, chartStatus, chartTopClientes, chartMetodos, chartSupervisores];
            charts.forEach(ch => {
                if (!ch) return;
                try {
                    if (ch.__deferred) {
                        // usar duração moderada ao renderizar após voltar à vista
                        ch.__deferred = false;
                        ch.update({ duration: 420 });
                    }
                } catch(e) { /* ignore per-chart */ }
            });
        }catch(e){}
    }

    // observar visibilidade do painel para renderizar charts adiados quando ele voltar à viewport
    (function observePanelVisibility(){
        try{
            const panelEl = document.getElementById('dashboard-panel');
            if (!panelEl) return;
            if ('IntersectionObserver' in window) {
                const io = new IntersectionObserver((entries) => {
                    entries.forEach(ent => {
                        if (ent.isIntersecting) {
                            // painel voltou à vista
                            flushDeferredCharts();
                            // esconder skeleton caso alguma atualização legacy tenha deixado
                            try { panelEl.classList.remove('dashboard-loading'); } catch(e){}
                        }
                    });
                }, { root: null, threshold: 0.05 });
                io.observe(panelEl);
            } else {
                // fallback simples: escutar scroll/resize e checar
                let _t = null;
                const check = () => {
                    if (_t) clearTimeout(_t);
                    _t = setTimeout(() => {
                        if (isElementInViewport(panelEl)) flushDeferredCharts();
                    }, 120);
                };
                window.addEventListener('scroll', check, { passive: true });
                window.addEventListener('resize', check);
                // também checar ao foco da janela
                window.addEventListener('focus', check);
            }
        }catch(e){}
    })();

    function showLoadingIndicators(){
        try{
            const panelEl = document.getElementById('dashboard-panel');
            // só apresentar skeletons se o painel estiver visível; evita overlays/repinturas quando o usuário está em outra área da página
            if (panelEl && isElementInViewport(panelEl)) panelEl.classList.add('dashboard-loading');
        }catch(e){}
    }
    function hideLoadingIndicators(){
        try{
            const panelEl = document.getElementById('dashboard-panel');
            if (panelEl) panelEl.classList.remove('dashboard-loading');
        }catch(e){}
    }

    // Polling automático quando painel visível; intervalo configurável
    let pollInterval = null;
    function getPollSeconds(){
        try { const v = localStorage.getItem('dash_poll_interval'); if (v) return parseInt(v,10); } catch(e){}
        return 15; // padrão
    }
    function startPolling() {
        if (pollInterval) return;
        const secs = getPollSeconds();
        pollInterval = setInterval(() => {
            const panelEl = document.getElementById('dashboard-panel');
            const panelVisible = panelEl && panelEl.classList.contains('open');
            if (panelVisible) atualizarDashboard();
        }, secs * 1000);
    }
    function stopPolling() {
        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    }
    function restartPolling(){ stopPolling(); startPolling(); }

    // iniciar polling (inofensivo se painel não estiver visível)
    startPolling();

    // também disparar primeira atualização se painel já estiver aberto
    if (document.getElementById('dashboard-panel').classList.contains('open')) {
        atualizarDashboard();
    }
});
