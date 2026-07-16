const resumoControlePropostas = {
    mes: "06",
    ano: "2026",
    mensal: {
        indicadores: {
            totalEmitidoMes: 40093831.27,
            emAnalise: { valor: 38811440.39, percentual: 96.8 },
            fechadaContratada: { valor: 1089992.88, percentual: 2.72 },
            perdidaRecusada: { valor: 192398.0, percentual: 0.48 },
            qtdPropostasMes: 19,
            totalAcumuladoAno: 1264294812.79,
        },
        porSegmentoReais: [
            { segmento: "Locação", emAnalise: 0, fechadaContratada: 0, perdidaRecusada: 0, total: 0 },
            { segmento: "Vendas", emAnalise: 0, fechadaContratada: 0, perdidaRecusada: 0, total: 0 },
            { segmento: "Offshore", emAnalise: 21651695.08, fechadaContratada: 332645.0, perdidaRecusada: 192398.0, total: 22176738.08 },
            { segmento: "Onshore", emAnalise: 17159745.4, fechadaContratada: 757347.88, perdidaRecusada: 0, total: 17917092.47 },
            { segmento: "Total", emAnalise: 38811440.39, fechadaContratada: 1089992.88, perdidaRecusada: 192398.0, total: 40093831.27 },
        ],
        receitaPorStatus: [
            { status: "Em Análise", valor: 38811440.39, percentual: 96.8, tone: "is-analysis" },
            { status: "Fechada / Contratada", valor: 1089992.88, percentual: 2.72, tone: "is-closed" },
            { status: "Perdida / Recusada", valor: 192398.0, percentual: 0.48, tone: "is-lost" },
            { status: "Total", valor: 40093831.27, percentual: 100, tone: "is-total" },
        ],
        porGestorReais: [
            { gestor: "Daniel Cunha", emAnalise: 0, fechadaContratada: 0, perdidaRecusada: 0, total: 0 },
            { gestor: "Rafael Paz", emAnalise: 0, fechadaContratada: 0, perdidaRecusada: 0, total: 0 },
            { gestor: "Sathia Mayene", emAnalise: 0, fechadaContratada: 0, perdidaRecusada: 0, total: 0 },
            { gestor: "Marcos França", emAnalise: 0, fechadaContratada: 0, perdidaRecusada: 0, total: 0 },
            { gestor: "Felipe Segundo", emAnalise: 13712390.39, fechadaContratada: 332645.0, perdidaRecusada: 192398.0, total: 14233333.39 },
            { gestor: "Fernanda Braz", emAnalise: 5164310.35, fechadaContratada: 757347.88, perdidaRecusada: 0, total: 5921658.23 },
            { gestor: "Kaitlyn Britto", emAnalise: 2676100.39, fechadaContratada: 0, perdidaRecusada: 0, total: 2676100.39 },
            { gestor: "André SanSao", emAnalise: 17107460.06, fechadaContratada: 0, perdidaRecusada: 0, total: 17107460.06 },
            { gestor: "Gabriel Diniz", emAnalise: 0, fechadaContratada: 0, perdidaRecusada: 0, total: 0 },
            { gestor: "Jorge Brasil", emAnalise: 0, fechadaContratada: 0, perdidaRecusada: 0, total: 0 },
            { gestor: "Total", emAnalise: 38811440.39, fechadaContratada: 1089992.88, perdidaRecusada: 192398.0, total: 40093831.27 },
        ],
        distribuicaoStatusQuantidade: [
            { status: "Em Análise", quantidade: 12, percentual: 63.16, tone: "is-analysis" },
            { status: "Fechada / Contratada", quantidade: 7, percentual: 36.84, tone: "is-closed" },
            { status: "Perdida / Recusada", quantidade: 0, percentual: 0, tone: "is-lost" },
        ],
        porGestorQuantidade: [
            { gestor: "Fernanda Braz", emAnalise: 9, fechadaContratada: 5, perdidaRecusada: 0, total: 14 },
            { gestor: "Kaitlyn Britto", emAnalise: 3, fechadaContratada: 2, perdidaRecusada: 0, total: 5 },
            { gestor: "Total", emAnalise: 12, fechadaContratada: 7, perdidaRecusada: 0, total: 19 },
        ],
        periodoLabel: "Visão mensal - Junho/2026",
    },
    acumuladoAno: {
        indicadores: {
            totalEmitidoMes: 1264294812.79,
            emAnalise: { valor: 973412004.15, percentual: 76.99 },
            fechadaContratada: { valor: 249230110.26, percentual: 19.71 },
            perdidaRecusada: { valor: 41652698.38, percentual: 3.3 },
            qtdPropostasMes: 248,
            totalAcumuladoAno: 1264294812.79,
        },
        porSegmentoReais: [
            { segmento: "Locação", emAnalise: 94220000.0, fechadaContratada: 35400000.0, perdidaRecusada: 3840000.0, total: 133460000.0 },
            { segmento: "Vendas", emAnalise: 118300000.0, fechadaContratada: 47850000.0, perdidaRecusada: 6210000.0, total: 172360000.0 },
            { segmento: "Offshore", emAnalise: 449892004.15, fechadaContratada: 104980110.26, perdidaRecusada: 16802698.38, total: 571674812.79 },
            { segmento: "Onshore", emAnalise: 311000000.0, fechadaContratada: 61000000.0, perdidaRecusada: 14800000.0, total: 386800000.0 },
            { segmento: "Total", emAnalise: 973412004.15, fechadaContratada: 249230110.26, perdidaRecusada: 41652698.38, total: 1264294812.79 },
        ],
        receitaPorStatus: [
            { status: "Em Análise", valor: 973412004.15, percentual: 76.99, tone: "is-analysis" },
            { status: "Fechada / Contratada", valor: 249230110.26, percentual: 19.71, tone: "is-closed" },
            { status: "Perdida / Recusada", valor: 41652698.38, percentual: 3.3, tone: "is-lost" },
            { status: "Total", valor: 1264294812.79, percentual: 100, tone: "is-total" },
        ],
        porGestorReais: [
            { gestor: "Daniel Cunha", emAnalise: 84500000.0, fechadaContratada: 21600000.0, perdidaRecusada: 1800000.0, total: 107900000.0 },
            { gestor: "Rafael Paz", emAnalise: 103200000.0, fechadaContratada: 28150000.0, perdidaRecusada: 2600000.0, total: 133950000.0 },
            { gestor: "Sathia Mayene", emAnalise: 98600000.0, fechadaContratada: 16400000.0, perdidaRecusada: 2950000.0, total: 117950000.0 },
            { gestor: "Marcos França", emAnalise: 67200000.0, fechadaContratada: 19400000.0, perdidaRecusada: 1300000.0, total: 87900000.0 },
            { gestor: "Felipe Segundo", emAnalise: 74500000.0, fechadaContratada: 18300000.0, perdidaRecusada: 2450000.0, total: 95250000.0 },
            { gestor: "Fernanda Braz", emAnalise: 141300000.0, fechadaContratada: 40200000.0, perdidaRecusada: 8120000.0, total: 189620000.0 },
            { gestor: "Kaitlyn Britto", emAnalise: 121700000.0, fechadaContratada: 29800000.0, perdidaRecusada: 4530000.0, total: 156030000.0 },
            { gestor: "André SanSao", emAnalise: 75212004.15, fechadaContratada: 14580110.26, perdidaRecusada: 3902698.38, total: 93694812.79 },
            { gestor: "Gabriel Diniz", emAnalise: 160000000.0, fechadaContratada: 61200000.0, perdidaRecusada: 10000000.0, total: 231200000.0 },
            { gestor: "Jorge Brasil", emAnalise: 47200000.0, fechadaContratada: 19600000.0, perdidaRecusada: 4000000.0, total: 70800000.0 },
            { gestor: "Total", emAnalise: 973412004.15, fechadaContratada: 249230110.26, perdidaRecusada: 41652698.38, total: 1264294812.79 },
        ],
        distribuicaoStatusQuantidade: [
            { status: "Em Análise", quantidade: 170, percentual: 68.55, tone: "is-analysis" },
            { status: "Fechada / Contratada", quantidade: 60, percentual: 24.19, tone: "is-closed" },
            { status: "Perdida / Recusada", quantidade: 18, percentual: 7.26, tone: "is-lost" },
        ],
        porGestorQuantidade: [
            { gestor: "Fernanda Braz", emAnalise: 31, fechadaContratada: 10, perdidaRecusada: 3, total: 44 },
            { gestor: "Kaitlyn Britto", emAnalise: 22, fechadaContratada: 8, perdidaRecusada: 2, total: 32 },
            { gestor: "Total", emAnalise: 170, fechadaContratada: 60, perdidaRecusada: 18, total: 248 },
        ],
        periodoLabel: "Visão acumulada - 2026",
    },
};

const resumoState = {
    modo: "mensal",
    mes: resumoControlePropostas.mes,
    ano: resumoControlePropostas.ano,
};

document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("resumoIndicadores")) {
        return;
    }

    hydrateResumoFilters();
    bindResumoEvents();
    renderResumo();
});

function hydrateResumoFilters() {
    const monthSelect = document.getElementById("resumoMes");
    const yearSelect = document.getElementById("resumoAno");
    const months = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
    const years = ["2024", "2025", "2026"];

    monthSelect.innerHTML = months.map((month) => (
        `<option value="${month}" ${month === resumoState.mes ? "selected" : ""}>${month}</option>`
    )).join("");

    yearSelect.innerHTML = years.map((year) => (
        `<option value="${year}" ${year === resumoState.ano ? "selected" : ""}>${year}</option>`
    )).join("");
}

function bindResumoEvents() {
    document.getElementById("resumoMes").addEventListener("change", (event) => {
        resumoState.mes = event.target.value;
    });

    document.getElementById("resumoAno").addEventListener("change", (event) => {
        resumoState.ano = event.target.value;
    });

    document.getElementById("resumoModoToggle").addEventListener("click", (event) => {
        const button = event.target.closest("button[data-mode]");
        if (!button) {
            return;
        }

        resumoState.modo = button.dataset.mode;
        document.querySelectorAll("#resumoModoToggle button").forEach((item) => {
            item.classList.toggle("is-active", item === button);
        });
        renderResumo();
    });

    document.getElementById("resumoAplicar").addEventListener("click", () => {
        renderResumo();
    });
}

function getResumoData() {
    return resumoState.modo === "acumulado"
        ? resumoControlePropostas.acumuladoAno
        : resumoControlePropostas.mensal;
}

function renderResumo() {
    const data = getResumoData();
    renderIndicadores(data.indicadores);
    renderTable("segmentoReaisTabela", [
        { key: "segmento", label: "Segmento" },
        { key: "emAnalise", label: "Em Análise", type: "currency" },
        { key: "fechadaContratada", label: "Fechada/Contratada", type: "currency" },
        { key: "perdidaRecusada", label: "Perdida/Recusada", type: "currency" },
        { key: "total", label: "Total", type: "currency" },
    ], data.porSegmentoReais, "segmento");
    renderSegmentoComparativo(data.porSegmentoReais);
    renderReceitaPorStatus(data.receitaPorStatus, data.periodoLabel);
    renderTable("gestorReaisTabela", [
        { key: "gestor", label: "Gestor" },
        { key: "emAnalise", label: "Em Análise", type: "currency" },
        { key: "fechadaContratada", label: "Fechada/Contratada", type: "currency" },
        { key: "perdidaRecusada", label: "Perdida/Recusada", type: "currency" },
        { key: "total", label: "Total", type: "currency" },
    ], data.porGestorReais, "gestor");
    renderDistribuicaoQuantidade(data.distribuicaoStatusQuantidade, data.indicadores.qtdPropostasMes);
    renderTable("gestorQuantidadeTabela", [
        { key: "gestor", label: "Gestor" },
        { key: "emAnalise", label: "Em Análise", type: "number" },
        { key: "fechadaContratada", label: "Fechada/Contratada", type: "number" },
        { key: "perdidaRecusada", label: "Perdida/Recusada", type: "number" },
        { key: "total", label: "Total", type: "number" },
    ], data.porGestorQuantidade, "gestor");
    renderTotalBox(data.indicadores.qtdPropostasMes);
}

function renderIndicadores(indicadores) {
    const items = [
        {
            icon: "paid",
            iconClass: "is-highlight",
            label: "Total Emitido no Mês",
            value: formatCurrency(indicadores.totalEmitidoMes),
            meta: "",
            dotClass: "",
        },
        {
            icon: "",
            iconClass: "",
            label: "Em Análise",
            value: formatCurrency(indicadores.emAnalise.valor),
            meta: formatPercent(indicadores.emAnalise.percentual),
            dotClass: "is-analysis",
        },
        {
            icon: "",
            iconClass: "",
            label: "Fechada / Contratada",
            value: formatCurrency(indicadores.fechadaContratada.valor),
            meta: formatPercent(indicadores.fechadaContratada.percentual),
            dotClass: "is-closed",
        },
        {
            icon: "",
            iconClass: "",
            label: "Perdida / Recusada",
            value: formatCurrency(indicadores.perdidaRecusada.valor),
            meta: formatPercent(indicadores.perdidaRecusada.percentual),
            dotClass: "is-lost",
        },
        {
            icon: "description",
            iconClass: "",
            label: "Qtd. de Propostas no Mês",
            value: formatInteger(indicadores.qtdPropostasMes),
            meta: "",
            dotClass: "",
        },
        {
            icon: "bar_chart",
            iconClass: "",
            label: "Total Acumulado no Ano",
            value: formatCurrency(indicadores.totalAcumuladoAno),
            meta: "",
            dotClass: "",
        },
    ];

    document.getElementById("resumoIndicadores").innerHTML = items.map((item) => `
        <article class="resumo-indicator ${item.icon ? "" : "is-compact"}">
            ${item.icon ? `
                <div class="resumo-indicator__icon ${item.iconClass}">
                    <span class="material-icons" aria-hidden="true">${item.icon}</span>
                </div>
            ` : `
                <div class="resumo-indicator__body">
                    <span class="resumo-indicator__dotline">
                        <span class="resumo-indicator__dot ${item.dotClass}"></span>
                        <span class="resumo-indicator__label">${item.label}</span>
                    </span>
                    <strong class="resumo-indicator__value">${item.value}</strong>
                    <span class="resumo-indicator__meta">${item.meta}</span>
                </div>
            `}
            ${item.icon ? `
                <div class="resumo-indicator__body">
                    <span class="resumo-indicator__label">${item.label}</span>
                    <strong class="resumo-indicator__value">${item.value}</strong>
                    ${item.meta ? `<span class="resumo-indicator__meta">${item.meta}</span>` : ""}
                </div>
            ` : ""}
        </article>
    `).join("");
}

function renderTable(containerId, columns, rows, identityKey) {
    document.getElementById(containerId).innerHTML = `
        <table class="resumo-table">
            <thead>
                <tr>
                    ${columns.map((column) => `<th class="${column.type ? "is-number" : ""}">${column.label}</th>`).join("")}
                </tr>
            </thead>
            <tbody>
                ${rows.map((row) => `
                    <tr class="${String(row[identityKey]).toLowerCase() === "total" ? "is-total" : ""}">
                        ${columns.map((column) => `<td class="${column.type ? "is-number" : ""}">${formatValue(row[column.key], column.type)}</td>`).join("")}
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;
}

function renderSegmentoComparativo(rows) {
    const list = rows.filter((row) => row.segmento === "Offshore" || row.segmento === "Onshore");
    const maxValue = Math.max(...list.map((item) => item.total), 1);
    const ticks = ["0", "10 mi", "20 mi", "30 mi"];

    document.getElementById("segmentoComparativoChart").innerHTML = `
        <div class="segment-compare">
            ${list.map((item) => `
                <div class="segment-compare__row">
                    <span class="segment-compare__label">${item.segmento}</span>
                    <div class="segment-compare__track">
                        <span class="segment-compare__fill" style="width:${(item.total / maxValue) * 100}%"></span>
                    </div>
                    <strong class="segment-compare__value">${formatCurrency(item.total)}</strong>
                </div>
            `).join("")}
            <div class="segment-compare__axis">
                ${ticks.map((tick) => `<span>${tick}</span>`).join("")}
            </div>
        </div>
    `;
}

function renderReceitaPorStatus(rows, hint) {
    const maxValue = Math.max(...rows.map((item) => item.valor), 1);

    document.getElementById("receitaPorStatusTabela").innerHTML = `
        <div class="status-list">
            <div class="status-list__header">
                <span>Status</span>
                <span></span>
                <span class="status-list__money">Em Reais</span>
                <span class="status-list__percent">% do Total</span>
            </div>
            ${rows.map((item) => `
                <div class="status-list__row ${item.tone === "is-total" ? "is-total" : ""}">
                    <span class="status-list__status">
                        <span class="status-list__dot ${item.tone}"></span>
                        ${item.status}
                    </span>
                    <div class="status-list__track">
                        ${item.tone !== "is-total" ? `<span class="status-list__fill ${item.tone}" style="width:${(item.valor / maxValue) * 100}%"></span>` : ""}
                    </div>
                    <span class="status-list__money">${formatCurrency(item.valor)}</span>
                    <span class="status-list__percent">${formatPercent(item.percentual)}</span>
                </div>
            `).join("")}
        </div>
    `;

    document.getElementById("receitaStatusHint").textContent = hint;
}

function renderDistribuicaoQuantidade(rows, total) {
    const maxValue = Math.max(...rows.map((item) => item.quantidade), 1);

    document.getElementById("distribuicaoStatusQuantidade").innerHTML = `
        <div class="dist-list">
            <div class="dist-list__header">
                <span>Status</span>
                <span class="dist-list__count">Quantidade</span>
                <span class="dist-list__percent">% do Total</span>
            </div>
            ${rows.map((item) => `
                <div class="dist-list__row">
                    <div class="dist-list__status">
                        <span class="dist-list__label">
                            <span class="dist-list__dot ${item.tone}"></span>
                            ${item.status}
                        </span>
                        <div class="dist-list__track">
                            <span class="dist-list__fill ${item.tone}" style="width:${(item.quantidade / maxValue) * 100}%"></span>
                        </div>
                    </div>
                    <span class="dist-list__count">${formatInteger(item.quantidade)}</span>
                    <span class="dist-list__percent">${formatPercent(item.percentual)}</span>
                </div>
            `).join("")}
            <div class="dist-list__total">
                <span>Total de Propostas no Mês</span>
                <span class="dist-list__count">${formatInteger(total)}</span>
                <span class="dist-list__percent">${formatPercent(100)}</span>
            </div>
        </div>
    `;
}

function renderTotalBox(total) {
    document.getElementById("totalPropostasMesBox").innerHTML = `
        <div class="total-box">
            <span class="total-box__label">Total de Propostas no Mês</span>
            <strong class="total-box__value">${formatInteger(total)}</strong>
        </div>
    `;
}

function formatValue(value, type) {
    if (type === "currency") {
        return formatCurrency(value);
    }

    if (type === "number") {
        return formatInteger(value);
    }

    return value ?? "-";
}

function formatCurrency(value) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(Number(value) || 0);
}

function formatInteger(value) {
    return new Intl.NumberFormat("pt-BR").format(Number(value) || 0);
}

function formatPercent(value) {
    return `${Number(value || 0).toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}%`;
}
