const resumoBootstrapElement = document.getElementById("resumo-bootstrap-data");
const resumoBootstrap = resumoBootstrapElement
    ? JSON.parse(resumoBootstrapElement.textContent)
    : null;

const resumoState = {
    mes: resumoBootstrap?.filters?.mes || "",
    ano: resumoBootstrap?.filters?.ano || "",
    modo: resumoBootstrap?.filters?.modo || "mensal",
};

document.addEventListener("DOMContentLoaded", () => {
    if (!resumoBootstrap || !document.getElementById("resumoIndicadores")) {
        return;
    }

    bindResumoEvents();
    renderResumo(resumoBootstrap.data || {});
});

function bindResumoEvents() {
    const monthSelect = document.getElementById("resumoMes");
    const yearSelect = document.getElementById("resumoAno");
    const toggle = document.getElementById("resumoModoToggle");
    const applyButton = document.getElementById("resumoAplicar");

    if (monthSelect) {
        monthSelect.addEventListener("change", (event) => {
            resumoState.mes = event.target.value;
        });
    }

    if (yearSelect) {
        yearSelect.addEventListener("change", (event) => {
            resumoState.ano = event.target.value;
        });
    }

    if (toggle) {
        toggle.addEventListener("click", (event) => {
            const button = event.target.closest("button[data-mode]");
            if (!button) {
                return;
            }

            resumoState.modo = button.dataset.mode;
            toggle.querySelectorAll("button[data-mode]").forEach((item) => {
                item.classList.toggle("is-active", item === button);
            });
        });
    }

    if (applyButton) {
        applyButton.addEventListener("click", () => {
            const params = new URLSearchParams();
            params.set("mes", resumoState.mes);
            params.set("ano", resumoState.ano);
            params.set("modo", resumoState.modo);
            window.location.search = params.toString();
        });
    }
}

function renderResumo(data) {
    renderIndicadores(data.indicadores || {});
    renderSegmentoTable(data.porSegmentoReais || [], data.emptyMessage);
    renderSegmentoComparativo(data.porSegmentoReais || [], data.emptyMessage);
    renderReceitaPorStatus(data.receitaPorStatus || [], data.periodoLabel || "", data.emptyMessage);
    renderGestorReais(data.porGestorReais || [], data.emptyMessage);
    renderDistribuicaoQuantidade(data.distribuicaoStatusQuantidade || [], data.indicadores?.qtdPropostasPeriodo || 0, data.emptyMessage);
    renderGestorQuantidade(data.porGestorQuantidade || [], data.emptyMessage);
}

function renderIndicadores(indicadores) {
    const items = [
        {
            icon: "paid",
            iconClass: "is-highlight",
            label: "Total Emitido no Período",
            value: formatCurrency(indicadores.totalEmitidoPeriodo),
            meta: "",
            dotClass: "",
        },
        {
            icon: "",
            iconClass: "",
            label: "Em Análise",
            value: formatCurrency(indicadores.emAnalise?.valor),
            meta: formatPercent(indicadores.emAnalise?.percentual),
            dotClass: "is-analysis",
        },
        {
            icon: "",
            iconClass: "",
            label: "Fechada / Contratada",
            value: formatCurrency(indicadores.fechadaContratada?.valor),
            meta: formatPercent(indicadores.fechadaContratada?.percentual),
            dotClass: "is-closed",
        },
        {
            icon: "",
            iconClass: "",
            label: "Perdida / Recusada",
            value: formatCurrency(indicadores.perdidaRecusada?.valor),
            meta: formatPercent(indicadores.perdidaRecusada?.percentual),
            dotClass: "is-lost",
        },
        {
            icon: "description",
            iconClass: "",
            label: "Qtd. de Propostas no Período",
            value: formatInteger(indicadores.qtdPropostasPeriodo),
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

function renderSegmentoTable(rows, emptyMessage) {
    renderTable(
        "segmentoReaisTabela",
        [
            { key: "segmento", label: "Segmento" },
            { key: "emAnalise", label: "Em Análise", type: "currency" },
            { key: "fechadaContratada", label: "Fechada/Contratada", type: "currency" },
            { key: "perdidaRecusada", label: "Perdida/Recusada", type: "currency" },
            { key: "total", label: "Total", type: "currency" },
        ],
        rows,
        "segmento",
        emptyMessage
    );
}

function renderGestorReais(rows, emptyMessage) {
    renderTable(
        "gestorReaisTabela",
        [
            { key: "gestor", label: "Gestor" },
            { key: "emAnalise", label: "Em Análise", type: "currency" },
            { key: "fechadaContratada", label: "Fechada/Contratada", type: "currency" },
            { key: "perdidaRecusada", label: "Perdida/Recusada", type: "currency" },
            { key: "total", label: "Total", type: "currency" },
        ],
        rows,
        "gestor",
        emptyMessage
    );
}

function renderGestorQuantidade(rows, emptyMessage) {
    const total = rows.find((row) => String(row.gestor).toLowerCase() === "total")?.total || 0;

    renderTable(
        "gestorQuantidadeTabela",
        [
            { key: "gestor", label: "Nome" },
            { key: "emAnalise", label: "Em Análise", type: "number" },
            { key: "fechadaContratada", label: "Fechada/Contratada", type: "number" },
            { key: "perdidaRecusada", label: "Perdida/Recusada", type: "number" },
            { key: "total", label: "Total", type: "number" },
        ],
        rows,
        "gestor",
        emptyMessage
    );

    (document.getElementById("totalPropostasMesBox") || {}).innerHTML = `
        <div class="total-box">
            <span class="total-box__label">Total de Propostas no Período</span>
            <strong class="total-box__value">${formatInteger(total)}</strong>
        </div>
    `;
}

function renderTable(containerId, columns, rows, identityKey, emptyMessage) {
    const container = document.getElementById(containerId);
    if (!container) {
        return;
    }

    if (!rows.length) {
        container.innerHTML = renderInlineEmpty(emptyMessage);
        return;
    }

    container.innerHTML = `
        <table class="resumo-table ${getResumoTableClass(containerId)}">
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

function getResumoTableClass(containerId) {
    return {
        segmentoReaisTabela: "segmento-reais-table",
        gestorReaisTabela: "gestor-reais-table",
        gestorQuantidadeTabela: "gestor-quantidade-table",
    }[containerId] || "";
}

function renderSegmentoComparativo(rows, emptyMessage) {
    const container = document.getElementById("segmentoComparativoChart");
    if (!container) {
        return;
    }

    const list = rows.filter((row) => row.segmento === "Offshore" || row.segmento === "Onshore");
    if (!list.length) {
        container.innerHTML = renderInlineEmpty(emptyMessage);
        return;
    }

    const maxValue = Math.max(...list.map((item) => Number(item.total) || 0), 1);
    const ticks = buildMillionsAxis(maxValue);

    container.innerHTML = `
        <div class="segment-compare">
            ${list.map((item) => `
                <div class="segment-compare__row">
                    <span class="segment-compare__label">${item.segmento}</span>
                    <div class="segment-compare__track">
                        <span class="segment-compare__fill" style="width:${((Number(item.total) || 0) / maxValue) * 100}%"></span>
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

function renderReceitaPorStatus(rows, hint, emptyMessage) {
    const table = document.getElementById("receitaPorStatusTabela");
    const hintElement = document.getElementById("receitaStatusHint");
    if (!table || !hintElement) {
        return;
    }

    if (!rows.length) {
        table.innerHTML = renderInlineEmpty(emptyMessage);
        hintElement.textContent = hint;
        return;
    }

    const maxValue = Math.max(...rows.map((item) => Number(item.valor) || 0), 1);

    table.innerHTML = `
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
                        ${item.tone !== "is-total" ? `<span class="status-list__fill ${item.tone}" style="width:${((Number(item.valor) || 0) / maxValue) * 100}%"></span>` : ""}
                    </div>
                    <span class="status-list__money">${formatCurrency(item.valor)}</span>
                    <span class="status-list__percent">${formatPercent(item.percentual)}</span>
                </div>
            `).join("")}
        </div>
    `;

    hintElement.textContent = hint;
}

function renderDistribuicaoQuantidade(rows, total, emptyMessage) {
    const container = document.getElementById("distribuicaoStatusQuantidade");
    if (!container) {
        return;
    }

    if (!rows.length) {
        container.innerHTML = renderInlineEmpty(emptyMessage);
        return;
    }

    const maxValue = Math.max(...rows.map((item) => Number(item.quantidade) || 0), 1);

    container.innerHTML = `
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
                            <span class="dist-list__fill ${item.tone}" style="width:${((Number(item.quantidade) || 0) / maxValue) * 100}%"></span>
                        </div>
                    </div>
                    <span class="dist-list__count">${formatInteger(item.quantidade)}</span>
                    <span class="dist-list__percent">${formatPercent(item.percentual)}</span>
                </div>
            `).join("")}
            <div class="dist-list__total">
                <span>Total de Propostas no Período</span>
                <span class="dist-list__count">${formatInteger(total)}</span>
                <span class="dist-list__percent">${formatPercent(100)}</span>
            </div>
        </div>
    `;
}

function buildMillionsAxis(maxValue) {
    const ceiling = Math.max(1, Math.ceil(maxValue / 1000000));
    const steps = [0, ceiling / 3, (ceiling / 3) * 2, ceiling];
    return steps.map((step) => {
        if (step === 0) {
            return "0";
        }

        return `${Math.round(step)} mi`;
    });
}

function renderInlineEmpty(message) {
    return `
        <div class="resumo-inline-empty">
            <span class="material-icons" aria-hidden="true">info</span>
            <p>${message || "Nenhuma proposta encontrada para o período selecionado."}</p>
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

    if (type === "percent") {
        return formatPercent(value);
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
