(function () {
    const app = document.getElementById('planejamentoApp');
    if (!app) {
        return;
    }

    const funcoes = JSON.parse((document.getElementById('planejamento-funcoes-data') || {}).textContent || '[]');
    const pessoas = JSON.parse((document.getElementById('planejamento-pessoas-data') || {}).textContent || '[]');
    const pessoasById = new Map(pessoas.map((pessoa) => [String(pessoa.id), pessoa]));
    const pessoasByName = new Map(pessoas.map((pessoa) => [String(pessoa.nome || '').trim().toLowerCase(), pessoa]));

    const refs = {
        search: document.getElementById('planejamentoSearch'),
        sort: document.getElementById('planejamentoSort'),
        statusFilter: document.getElementById('planejamentoStatusFilter'),
        clienteFilter: document.getElementById('planejamentoClienteFilter'),
        unidadeFilter: document.getElementById('planejamentoUnidadeFilter'),
        coordenadorFilter: document.getElementById('planejamentoCoordenadorFilter'),
        toggleFilters: document.getElementById('planejamentoToggleFilters'),
        advancedFilters: document.getElementById('planejamentoAdvancedFilters'),
        clearFilters: document.getElementById('planejamentoClearFilters'),
        activeFilters: document.getElementById('planejamentoActiveFilters'),
        results: document.getElementById('planejamentoResultsText'),
        alerts: document.getElementById('planejamentoAlerts'),
        cards: document.getElementById('planejamentoCards'),
        paginationSummary: document.getElementById('planejamentoPaginationSummary'),
        pageIndicator: document.getElementById('planejamentoPageIndicator'),
        prevPage: document.getElementById('planejamentoPrevPage'),
        nextPage: document.getElementById('planejamentoNextPage'),
        panel: document.getElementById('planejamentoPanel'),
        panelBody: document.getElementById('planejamentoPanelBody'),
        panelTitle: document.getElementById('planejamentoPanelTitle'),
        panelSubtitle: document.getElementById('planejamentoPanelSubtitle'),
        panelHeaderBadge: document.getElementById('planejamentoPanelHeaderBadge'),
        panelClose: document.getElementById('planejamentoPanelClose'),
        panelBackdrop: document.getElementById('planejamentoPanelBackdrop'),
        modal: document.getElementById('planejamentoActionModal'),
        modalBody: document.getElementById('planejamentoActionModalBody'),
        modalTitle: document.getElementById('planejamentoActionModalTitle'),
        modalClose: document.getElementById('planejamentoActionModalClose'),
        modalBackdrop: document.getElementById('planejamentoActionModalBackdrop')
    };

    const state = {
        allItems: [],
        filters: { q: '', status: 'all', cliente: '', unidade: '', coordenador: '' },
        sort: 'os_desc',
        advancedFiltersOpen: true,
        selectedGroupNumeroOs: null,
        selectedOsId: null,
        detail: null,
        memberTab: 'ativos',
        currentPage: 1,
        pageSize: getPageSize(),
        alertTimer: null,
        searchTimer: null,
        modalOnClose: null,
        editFlow: {
            action: '',
            justification: ''
        }
    };

    function getPageSize() {
        return window.innerWidth <= 760 ? 2 : 3;
    }

    function isMobile() {
        return window.innerWidth <= 760;
    }

    function endpoint(template, replacements) {
        let url = template;
        Object.keys(replacements).forEach((key) => {
            url = url.replace(key, String(replacements[key]));
        });
        return url;
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderPlanButton(config) {
        const options = config || {};
        const attrs = String(options.attrs || '').trim();
        const extraClass = String(options.extraClass || '').trim();
        return `
            <button
                type="${escapeHtml(options.type || 'button')}"
                class="plan-btn plan-btn--${escapeHtml(options.tone || 'success')}${extraClass ? ` ${escapeHtml(extraClass)}` : ''}"
                ${attrs ? `${attrs} ` : ''}${options.disabled ? 'disabled' : ''}
            >
                <span class="plan-btn__icon">
                    <span class="material-icons" aria-hidden="true">${escapeHtml(options.icon || 'check_circle')}</span>
                </span>
                <span class="plan-btn__label">${escapeHtml(options.label || '')}</span>
            </button>
        `;
    }

    function normalize(value) {
        return String(value || '').trim().toLowerCase();
    }

    function isOperacaoFinalizada(status) {
        const normalized = normalize(status);
        return normalized === 'finalizado' || normalized === 'finalizada';
    }

    function formatDate(value) {
        if (!value) {
            return '-';
        }
        const date = new Date(`${value}T00:00:00`);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleDateString('pt-BR');
    }

    function formatDateTimeLabel(dateValue, timeValue) {
        const dateLabel = dateValue ? formatDate(dateValue) : '';
        const timeLabel = String(timeValue || '').trim();
        if (dateLabel && timeLabel) {
            return `${dateLabel} ${timeLabel}`;
        }
        return dateLabel || timeLabel || '-';
    }

    function getMemberDisembarkInfo(member, planejamento) {
        return {
            data: member && member.data_desembarque ? member.data_desembarque : (planejamento ? planejamento.data_prevista_desembarque : ''),
            horario: member && member.horario_desembarque ? member.horario_desembarque : (planejamento ? planejamento.horario_previsto_desembarque : ''),
            local: member && member.local_desembarque_membro ? member.local_desembarque_membro : (planejamento ? planejamento.local_desembarque : ''),
            observacao: member && member.observacao_desembarque ? member.observacao_desembarque : (planejamento ? planejamento.observacao_desembarque : '')
        };
    }

    function getCsrfToken() {
        const cookie = document.cookie
            .split(';')
            .map((value) => value.trim())
            .find((value) => value.startsWith('csrftoken='));
        return cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : '';
    }

    async function apiRequest(url, options) {
        const opts = Object.assign({ method: 'GET' }, options || {});
        const headers = Object.assign({ 'X-Requested-With': 'XMLHttpRequest' }, opts.headers || {});

        if (opts.method !== 'GET') {
            headers['X-CSRFToken'] = getCsrfToken();
        }
        if (opts.jsonBody !== undefined) {
            headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(opts.jsonBody);
        } else if (opts.formData) {
            opts.body = opts.formData;
        }

        delete opts.headers;
        delete opts.jsonBody;
        delete opts.formData;

        const response = await fetch(url, Object.assign({}, opts, { headers }));
        const contentType = response.headers.get('content-type') || '';
        const data = contentType.includes('application/json') ? await response.json() : {};
        if (!response.ok || data.success === false) {
            throw new Error((data && data.error) || 'Não foi possível concluir a operação.');
        }
        return data;
    }

    function showAlert(message, kind) {
        refs.alerts.innerHTML = `
            <div class="planejamento-alert planejamento-alert--${kind === 'error' ? 'error' : 'success'}">
                <span class="material-icons" aria-hidden="true">${kind === 'error' ? 'error' : 'check_circle'}</span>
                <span>${escapeHtml(message)}</span>
            </div>
        `;
        window.clearTimeout(state.alertTimer);
        state.alertTimer = window.setTimeout(() => {
            refs.alerts.innerHTML = '';
        }, 4200);
    }

    function getPlanningLabel(osItem) {
        return osItem.tem_planejamento ? (osItem.planejamento_status || 'Rascunho') : 'Sem planejamento';
    }

    function getCardPlanningLabel(osItem) {
        const statusLinha = String(osItem.status_linha || osItem.status_operacao || '').trim();
        const planejamentoStatus = normalize(osItem.planejamento_status || osItem.status_planejamento);

        if (isOperacaoFinalizada(statusLinha)) {
            return 'Concluído';
        }

        if (!osItem.tem_planejamento) {
            return 'Sem planejamento';
        }

        if (planejamentoStatus === 'cancelado') {
            return 'Cancelado';
        }

        if (planejamentoStatus === 'rascunho') {
            return 'Rascunho';
        }

        return 'Planejada';
    }

    function getPlanningClass(status) {
        const normalized = normalize(status);
        if (!normalized || normalized === 'sem planejamento') {
            return 'planejamento-badge--sem';
        }
        if (normalized === 'rascunho' || normalized === 'parcial' || normalized === 'planejada') {
            return 'planejamento-badge--rascunho';
        }
        if (normalized === 'concluido' || normalized === 'concluído' || normalized === 'ativo') {
            return 'planejamento-badge--concluido';
        }
        if (normalized === 'cancelado') {
            return 'planejamento-badge--cancelado';
        }
        if (normalized === 'somente leitura') {
            return 'planejamento-badge--readonly';
        }
        return 'planejamento-badge--operacao';
    }

    function cardActionLabel(osItem) {
        if (!osItem.tem_planejamento) {
            return 'Iniciar planejamento';
        }
        return osItem.permite_edicao ? 'Editar planejamento' : 'Ver planejamento';
    }

    function cardActionIcon(osItem) {
        if (!osItem.tem_planejamento) {
            return 'playlist_add';
        }
        return osItem.permite_edicao ? 'edit' : 'visibility';
    }

    function getNumeroOsAsNumber(value) {
        const parsed = Number(String(value || '').replace(/\D/g, ''));
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function compareTextValues(left, right) {
        return String(left || '').localeCompare(String(right || ''), 'pt-BR');
    }

    function sortGroups(groups) {
        const sorted = groups.slice();
        sorted.sort((left, right) => {
            const leftSummary = getGroupPlanningSummary(left);
            const rightSummary = getGroupPlanningSummary(right);

            if (state.sort === 'os_asc') {
                return getNumeroOsAsNumber(left.numero_os) - getNumeroOsAsNumber(right.numero_os)
                    || compareTextValues(left.numero_os, right.numero_os);
            }

            if (state.sort === 'cliente') {
                return compareTextValues(left.cliente, right.cliente)
                    || getNumeroOsAsNumber(right.numero_os) - getNumeroOsAsNumber(left.numero_os);
            }

            if (state.sort === 'unidade') {
                return compareTextValues(left.unidade, right.unidade)
                    || getNumeroOsAsNumber(right.numero_os) - getNumeroOsAsNumber(left.numero_os);
            }

            if (state.sort === 'planejadas_desc') {
                return rightSummary.planejadas - leftSummary.planejadas
                    || getNumeroOsAsNumber(right.numero_os) - getNumeroOsAsNumber(left.numero_os);
            }

            if (state.sort === 'planejadas_asc') {
                return leftSummary.planejadas - rightSummary.planejadas
                    || getNumeroOsAsNumber(right.numero_os) - getNumeroOsAsNumber(left.numero_os);
            }

            return getNumeroOsAsNumber(right.numero_os) - getNumeroOsAsNumber(left.numero_os)
                || compareTextValues(right.numero_os, left.numero_os);
        });
        return sorted;
    }

    function itemMatchesFilters(item) {
        const query = normalize(state.filters.q);
        const statusFilter = normalize(state.filters.status);
        const clienteFilter = normalize(state.filters.cliente);
        const unidadeFilter = normalize(state.filters.unidade);
        const coordenadorFilter = normalize(state.filters.coordenador);
        const planningLabel = normalize(getPlanningLabel(item));
        if (statusFilter !== 'all') {
            if (statusFilter === 'sem_planejamento' && item.tem_planejamento) {
                return false;
            }
            if (statusFilter !== 'sem_planejamento' && planningLabel !== statusFilter) {
                return false;
            }
        }

        if (clienteFilter && normalize(item.cliente) !== clienteFilter) {
            return false;
        }

        if (unidadeFilter && normalize(item.unidade) !== unidadeFilter) {
            return false;
        }

        if (coordenadorFilter) {
            const coordenador = normalize(item.coordenador);
            if (coordenador !== coordenadorFilter) {
                return false;
            }
        }

        if (!query) {
            return true;
        }

        const haystack = [
            item.numero_os,
            item.cliente,
            item.unidade,
            item.coordenador,
            item.supervisor_nome,
            item.status_operacao,
            getPlanningLabel(item),
            item.servico
        ]
            .map((value) => normalize(value))
            .join(' ');

        return haystack.includes(query);
    }

    function getVisibleBaseItems() {
        return state.allItems.filter((item) => !item.home_finalizada);
    }

    function getGroupKey(itemOrNumeroOs) {
        if (itemOrNumeroOs && typeof itemOrNumeroOs === 'object') {
            return String(itemOrNumeroOs.numero_os || itemOrNumeroOs.id || '').trim();
        }
        return String(itemOrNumeroOs || '').trim();
    }

    function groupItemsByNumeroOs(items) {
        const groups = new Map();
        items.forEach((item) => {
            const key = getGroupKey(item);
            if (!groups.has(key)) {
                groups.set(key, {
                    numero_os: item.numero_os,
                    cliente: item.cliente,
                    unidade: item.unidade,
                    coordenador: item.coordenador,
                    movimentacoes: []
                });
            }
            groups.get(key).movimentacoes.push(item);
        });
        return Array.from(groups.values());
    }

    function getAllGroupMovements(numeroOs) {
        const key = getGroupKey(numeroOs);
        return state.allItems.filter((item) => getGroupKey(item) === key);
    }

    function findGroup(numeroOs, options) {
        const settings = options || {};
        if (settings.includeAllMovements) {
            const movements = getAllGroupMovements(numeroOs);
            if (!movements.length) {
                return null;
            }
            return groupItemsByNumeroOs(movements)[0] || null;
        }
        return getFilteredGroups().find((group) => String(group.numero_os) === String(numeroOs)) || null;
    }

    function getGroupPlanningSummary(group) {
        const total = group.movimentacoes.length;
        const planejadas = group.movimentacoes.filter((item) => item.tem_planejamento).length;
        const somenteLeitura = group.movimentacoes.filter((item) => !item.permite_edicao).length;
        const semPlanejamento = group.movimentacoes.filter((item) => !item.tem_planejamento).length;
        const todasFinalizadas = total > 0 && group.movimentacoes.every((item) => {
            return isOperacaoFinalizada(item.status_linha || item.status_operacao);
        });
        const temRascunho = group.movimentacoes.some((item) => normalize(item.planejamento_status || item.status_planejamento) === 'rascunho');
        const temCancelado = group.movimentacoes.some((item) => normalize(item.planejamento_status || item.status_planejamento) === 'cancelado');
        let label = 'Sem planejamento';

        if (todasFinalizadas) {
            label = 'Concluído';
        } else if (planejadas === 0) {
            label = 'Sem planejamento';
        } else if (temRascunho) {
            label = 'Rascunho';
        } else if (temCancelado && planejadas === total) {
            label = 'Cancelado';
        } else if (planejadas === total) {
            label = 'Planejada';
        } else {
            label = 'Parcial';
        }
        return { total, planejadas, somenteLeitura, semPlanejamento, label };
    }

    function getFilteredGroups() {
        const visibleItems = getVisibleBaseItems();
        const groups = groupItemsByNumeroOs(visibleItems);
        return sortGroups(
            groups.filter((group) => group.movimentacoes.some((item) => itemMatchesFilters(item)))
        );
    }

    function uniqueSortedValues(values) {
        return Array.from(new Set(values.filter(Boolean).map((value) => String(value).trim()).filter(Boolean)))
            .sort((left, right) => left.localeCompare(right, 'pt-BR'));
    }

    function renderFilterSelectOptions(select, values, placeholder, currentValue) {
        if (!select) {
            return;
        }
        const normalizedCurrent = String(currentValue || '');
        select.innerHTML = [
            `<option value="">${escapeHtml(placeholder)}</option>`,
            ...values.map((value) => `<option value="${escapeHtml(value)}" ${value === normalizedCurrent ? 'selected' : ''}>${escapeHtml(value)}</option>`)
        ].join('');
        select.value = normalizedCurrent;
    }

    function renderFilterOptions() {
        const items = getVisibleBaseItems();
        renderFilterSelectOptions(refs.clienteFilter, uniqueSortedValues(items.map((item) => item.cliente)), 'Selecione o cliente', state.filters.cliente);
        renderFilterSelectOptions(refs.unidadeFilter, uniqueSortedValues(items.map((item) => item.unidade)), 'Selecione a unidade', state.filters.unidade);
        renderFilterSelectOptions(
            refs.coordenadorFilter,
            uniqueSortedValues(items.map((item) => item.coordenador)),
            'Selecione o coordenador',
            state.filters.coordenador
        );
        if (refs.statusFilter) {
            refs.statusFilter.value = state.filters.status;
        }
        if (refs.sort) {
            refs.sort.value = state.sort;
        }
        if (refs.search && refs.search.value !== state.filters.q) {
            refs.search.value = state.filters.q;
        }
    }

    function buildActiveFilterChips() {
        const chips = [];
        if (state.filters.q) {
            chips.push(`Busca: ${state.filters.q}`);
        }
        if (state.filters.status && state.filters.status !== 'all') {
            const statusLabels = {
                sem_planejamento: 'Sem planejamento',
                rascunho: 'Rascunho',
                concluido: 'Concluído',
                cancelado: 'Cancelado'
            };
            chips.push(`Status: ${statusLabels[state.filters.status] || state.filters.status}`);
        }
        if (state.filters.cliente) {
            chips.push(`Cliente: ${state.filters.cliente}`);
        }
        if (state.filters.unidade) {
            chips.push(`Unidade: ${state.filters.unidade}`);
        }
        if (state.filters.coordenador) {
            chips.push(`Coordenador: ${state.filters.coordenador}`);
        }
        return chips;
    }

    function renderActiveFiltersSummary() {
        if (!refs.activeFilters) {
            return;
        }
        const chips = buildActiveFilterChips();
        if (!chips.length) {
            refs.activeFilters.innerHTML = '<span class="planejamento-filter-summary__empty">Nenhum filtro aplicado</span>';
            return;
        }
        refs.activeFilters.innerHTML = chips.map((chip) => `<span class="planejamento-filter-chip">${escapeHtml(chip)}</span>`).join('');
    }

    function syncAdvancedFiltersState() {
        if (!refs.advancedFilters || !refs.toggleFilters) {
            return;
        }
        refs.advancedFilters.hidden = !state.advancedFiltersOpen;
        refs.toggleFilters.setAttribute('aria-expanded', state.advancedFiltersOpen ? 'true' : 'false');
        refs.toggleFilters.classList.toggle('is-open', state.advancedFiltersOpen);
    }

    function clearAllFilters() {
        state.filters = { q: '', status: 'all', cliente: '', unidade: '', coordenador: '' };
        state.sort = 'os_desc';
        state.currentPage = 1;
        renderFilterOptions();
        renderActiveFiltersSummary();
        renderCards();
        renderPanel();
    }

    function getVisualListItems() {
        const groups = getFilteredGroups();
        return groups.map((group) => {
            const completeGroup = findGroup(group.numero_os, { includeAllMovements: true }) || group;
            const summary = getGroupPlanningSummary(completeGroup);
            if (completeGroup.movimentacoes.length === 1) {
                return {
                    tipo: 'single',
                    key: String(group.numero_os),
                    item: completeGroup.movimentacoes[0],
                    group: completeGroup,
                    summary
                };
            }
            return {
                tipo: 'group',
                key: String(group.numero_os),
                group: completeGroup,
                summary
            };
        });
    }

    function getPaginatedItems() {
        const visualItems = getVisualListItems();
        const totalPages = Math.max(1, Math.ceil(visualItems.length / state.pageSize));
        if (state.currentPage > totalPages) {
            state.currentPage = totalPages;
        }
        const start = (state.currentPage - 1) * state.pageSize;
        return {
            total: visualItems.length,
            totalPages,
            visible: visualItems.slice(start, start + state.pageSize),
            start,
            end: Math.min(start + state.pageSize, visualItems.length)
        };
    }

    function renderPagination(total, start, end, totalPages) {
        if (!total) {
            refs.paginationSummary.textContent = '';
            refs.pageIndicator.textContent = 'P\u00e1gina 1 de 1';
            refs.prevPage.disabled = true;
            refs.nextPage.disabled = true;
            return;
        }
        refs.paginationSummary.textContent = `Mostrando ${start + 1}-${end} de ${total} OS`;
        refs.pageIndicator.textContent = `P\u00e1gina ${state.currentPage} de ${totalPages}`;
        refs.prevPage.disabled = state.currentPage <= 1;
        refs.nextPage.disabled = state.currentPage >= totalPages;
    }

    function renderGroupCard(group, summary) {
        const selectedClass = String(state.selectedGroupNumeroOs) === String(group.numero_os) ? ' is-selected' : '';
        return `
            <article class="planejamento-card planejamento-card--group${selectedClass}" data-card-group="${escapeHtml(group.numero_os)}">
                <div class="planejamento-card__icon">
                    <span class="material-icons" aria-hidden="true">assignment</span>
                </div>
                <div class="planejamento-card__content">
                    <div class="planejamento-card__top">
                        <div class="planejamento-card__title">
                            <h3>OS ${escapeHtml(group.numero_os || '-')}</h3>
                        </div>
                        <div class="planejamento-badges">
                            <span class="planejamento-badge ${getPlanningClass(summary.label)}">${escapeHtml(summary.label)}</span>
                        </div>
                    </div>
                    <div class="planejamento-card__compact-grid">
                        <div class="planejamento-data"><span>Cliente</span><strong>${escapeHtml(group.cliente || '-')}</strong></div>
                        <div class="planejamento-data"><span>Unidade</span><strong>${escapeHtml(group.unidade || '-')}</strong></div>
                        <div class="planejamento-data"><span>Coordenador</span><strong>${escapeHtml(group.coordenador || '-')}</strong></div>
                    </div>
                    <div class="planejamento-card__summary">
                        <span>${escapeHtml(summary.total)} movimenta${summary.total === 1 ? '\u00e7\u00e3o' : '\u00e7\u00f5es'}</span>
                        <span>${escapeHtml(summary.planejadas)} planejada${summary.planejadas === 1 ? '' : 's'}</span>
                        ${summary.somenteLeitura > 0
                            ? `<span>${escapeHtml(summary.somenteLeitura)} somente leitura</span>`
                            : `<span>${escapeHtml(summary.semPlanejamento)} sem planejamento</span>`}
                    </div>
                    <div class="planejamento-card__actions">
                        ${renderPlanButton({
                            label: 'Ver movimentações',
                            icon: 'visibility',
                            tone: 'success',
                            attrs: `data-card-group-open="${escapeHtml(group.numero_os)}"`
                        })}
                    </div>
                </div>
            </article>
        `;
    }

    function renderSingleCard(item, summary) {
        const planningLabel = getCardPlanningLabel(item);
        const selectedClass = String(state.selectedOsId) === String(item.id) ? ' is-selected' : '';
        const readonlyBadge = item.permite_edicao ? '' : '<span class="planejamento-badge planejamento-badge--readonly">Somente leitura</span>';
        return `
            <article class="planejamento-card${selectedClass}" data-card-open="${item.id}">
                <div class="planejamento-card__icon">
                    <span class="material-icons" aria-hidden="true">assignment</span>
                </div>
                <div class="planejamento-card__content">
                    <div class="planejamento-card__top">
                        <div class="planejamento-card__title">
                            <h3>OS ${escapeHtml(item.numero_os || '-')}</h3>
                        </div>
                        <div class="planejamento-badges">
                            <span class="planejamento-badge ${getPlanningClass(planningLabel)}">${escapeHtml(planningLabel)}</span>
                            ${readonlyBadge}
                        </div>
                    </div>
                    <div class="planejamento-card__compact-grid">
                        <div class="planejamento-data"><span>Cliente</span><strong>${escapeHtml(item.cliente || '-')}</strong></div>
                        <div class="planejamento-data"><span>Unidade</span><strong>${escapeHtml(item.unidade || '-')}</strong></div>
                        <div class="planejamento-data"><span>Supervisor</span><strong>${escapeHtml(item.supervisor_nome || '-')}</strong></div>
                        <div class="planejamento-data"><span>POB</span><strong>${escapeHtml(item.pob || '-')}</strong></div>
                        <div class="planejamento-data"><span>Coordenador</span><strong>${escapeHtml(item.coordenador || '-')}</strong></div>
                        <div class="planejamento-data"><span>Status operacional</span><strong>${escapeHtml(item.status_operacao || '-')}</strong></div>
                    </div>
                    <div class="planejamento-card__summary">
                        <span>${escapeHtml(summary.total)} movimenta\u00e7\u00e3o</span>
                        <span>${escapeHtml(summary.planejadas)} planejada${summary.planejadas === 1 ? '' : 's'}</span>
                        ${summary.somenteLeitura > 0
                            ? `<span>${escapeHtml(summary.somenteLeitura)} somente leitura</span>`
                            : `<span>${escapeHtml(summary.semPlanejamento)} sem planejamento</span>`}
                    </div>
                    <div class="planejamento-card__actions">
                        ${renderPlanButton({
                            label: cardActionLabel(item),
                            icon: cardActionIcon(item),
                            tone: 'success',
                            attrs: `data-card-action="${item.tem_planejamento ? 'open' : 'start'}" data-os-id="${item.id}"`,
                            disabled: !item.permite_edicao && !item.tem_planejamento
                        })}
                    </div>
                </div>
            </article>
        `;
    }

    function renderCards() {
        const page = getPaginatedItems();
        refs.results.textContent = `${page.total || 0} OS agrupada${page.total === 1 ? '' : 's'}`;
        if (!page.total) {
            refs.cards.innerHTML = `
                <div class="planejamento-empty">
                    <span class="material-icons planejamento-empty__icon" aria-hidden="true">search_off</span>
                    <h3>Nenhuma OS encontrada</h3>
                    <p>Ajuste a busca ou o filtro para localizar outras linhas da OS.</p>
                </div>
            `;
            renderPagination(0, 0, 0, 1);
            return;
        }

        refs.cards.innerHTML = page.visible.map((entry) => {
            return entry.tipo === 'group'
                ? renderGroupCard(entry.group, entry.summary)
                : renderSingleCard(entry.item, entry.summary);
        }).join('');

        renderPagination(page.total, page.start, page.end, page.totalPages);
    }

    function renderEmptyDetail() {
        refs.panelTitle.textContent = 'Selecione uma OS';
        refs.panelSubtitle.textContent = '';
        refs.panelHeaderBadge.innerHTML = '';
        refs.panelBody.innerHTML = `
            <div class="planejamento-empty">
                <span class="material-icons planejamento-empty__icon" aria-hidden="true">assignment</span>
                <h3>Nenhuma OS selecionada</h3>
                <p>Escolha um card na lista \u00e0 esquerda para abrir o planejamento desta linha da OS.</p>
            </div>
        `;
    }

    function renderSingleHeader(osItem, planejamento) {
        const planningLabel = planejamento ? getCardPlanningLabel(Object.assign({}, osItem, { planejamento_status: planejamento.status, tem_planejamento: true })) : 'Sem planejamento';
        refs.panelTitle.textContent = `OS ${osItem.numero_os}`;
        refs.panelSubtitle.textContent = `Cliente: ${osItem.cliente || '-'} | Unidade: ${osItem.unidade || '-'} | Servi\u00e7o: ${osItem.servico || '-'}`;
        refs.panelHeaderBadge.innerHTML = `<span class="planejamento-badge ${getPlanningClass(planningLabel)}">${escapeHtml(planningLabel)}</span>`;
    }

    function renderGroupHeader(group) {
        const summary = getGroupPlanningSummary(group);
        refs.panelTitle.textContent = `OS ${group.numero_os}`;
        refs.panelSubtitle.textContent = `${group.cliente || '-'} | ${group.unidade || '-'}`;
        refs.panelHeaderBadge.innerHTML = `<span class="planejamento-badge ${getPlanningClass(summary.label)}">${escapeHtml(summary.label)}</span>`;
    }

    async function loadCards() {
        refs.cards.innerHTML = `<div class="planejamento-empty"><p>Carregando cards...</p></div>`;
        renderPagination(0, 0, 0, 1);
        try {
            const data = await apiRequest(app.dataset.osListUrl);
            state.allItems = data.items || [];
            renderFilterOptions();
            renderActiveFiltersSummary();
            if (state.selectedGroupNumeroOs && !findGroup(state.selectedGroupNumeroOs)) {
                state.selectedGroupNumeroOs = null;
                state.selectedOsId = null;
                state.detail = null;
            }
            renderCards();
            renderPanel();
        } catch (error) {
            refs.results.textContent = 'Falha ao carregar a lista';
            refs.cards.innerHTML = `<div class="planejamento-empty"><p>${escapeHtml(error.message)}</p></div>`;
            showAlert(error.message, 'error');
        }
    }

    function openMobileDetailPane() {
        if (!isMobile()) {
            refs.panel.classList.remove('is-open');
            refs.panelBackdrop.hidden = true;
            return;
        }
        refs.panel.classList.add('is-open');
        refs.panelBackdrop.hidden = false;
    }

    function closeMobileDetailPane() {
        if (!isMobile()) {
            return;
        }
        refs.panel.classList.remove('is-open');
        refs.panelBackdrop.hidden = true;
    }

    function clearSelectedDetail() {
        state.selectedGroupNumeroOs = null;
        state.selectedOsId = null;
        state.detail = null;
        renderCards();
        renderEmptyDetail();
        closeMobileDetailPane();
    }

    function closeModal(reason) {
        const onClose = state.modalOnClose;
        state.modalOnClose = null;
        refs.modal.classList.remove('is-plan-edit');
        refs.modal.querySelector('.planejamento-modal__dialog')?.classList.remove('plan-edit-modal-shell');
        refs.modal.querySelector('.planejamento-modal__header')?.classList.remove('is-hidden');
        refs.modalBody.classList.remove('is-plan-edit-body');
        refs.modal.hidden = true;
        refs.modalBody.innerHTML = '';
        if (typeof onClose === 'function') {
            onClose(reason || 'dismiss');
        }
    }

    function openModal(title, bodyHtml, onSubmit, onClose, options) {
        const config = options || {};
        state.modalOnClose = onClose || null;
        refs.modalTitle.textContent = title;
        refs.modalBody.innerHTML = bodyHtml;
        refs.modal.classList.toggle('is-plan-edit', config.variant === 'plan-edit');
        refs.modal.querySelector('.planejamento-modal__dialog')?.classList.toggle('plan-edit-modal-shell', config.variant === 'plan-edit');
        refs.modal.querySelector('.planejamento-modal__header')?.classList.toggle('is-hidden', config.hideDefaultHeader === true);
        refs.modalBody.classList.toggle('is-plan-edit-body', config.variant === 'plan-edit');
        refs.modal.hidden = false;
        initPersonComboboxes(refs.modalBody);
        const form = refs.modalBody.querySelector('form');
        if (form) {
            form.addEventListener('submit', async function (event) {
                event.preventDefault();
                try {
                    await onSubmit(form);
                } catch (error) {
                    showAlert(error.message, 'error');
                }
            });
        }
    }

    function currentPlanning() {
        return state.detail && state.detail.planejamento ? state.detail.planejamento : null;
    }

    function currentOs() {
        return state.detail ? state.detail.os : null;
    }

    function currentPlanningRequiresJustification() {
        const planejamento = currentPlanning();
        return Boolean(planejamento && planejamento.requer_justificativa_alteracao && !planejamento.motivo_bloqueio_edicao);
    }

    function canGeneratePlanningDocument(planejamento) {
        if (!planejamento || !planejamento.id) {
            return false;
        }
        if ((planejamento.quantidade_membros_ativos || 0) > 0) {
            return true;
        }
        return Boolean(
            planejamento.titulo_planejamento
            || planejamento.data_prevista_subida
            || planejamento.horario_previsto_subida
            || planejamento.local_subida
            || planejamento.observacao
            || planejamento.data_prevista_desembarque
            || planejamento.horario_previsto_desembarque
            || planejamento.local_desembarque
            || planejamento.observacao_desembarque
        );
    }

    function buildJustificationField(fieldName) {
        return `
            <div class="planejamento-field planejamento-field--span-12">
                <label for="${fieldName}">Justificativa obrigatória</label>
                <textarea id="${fieldName}" class="planejamento-textarea" name="justificativa" required></textarea>
            </div>
        `;
    }

    function requestPlanningJustification(actionLabel) {
        return new Promise((resolve) => {
            openModal(
                'Alterar planejamento concluido',
                `
                    <form>
                        <div class="planejamento-form-grid">
                            <div class="planejamento-field planejamento-field--span-12">
                                <p class="planejamento-field__hint">Este planejamento ja foi concluido. Informe a justificativa para ${escapeHtml(actionLabel || 'continuar com a alteracao')}.</p>
                            </div>
                            ${buildJustificationField('justificativaPlanejamento')}
                        </div>
                        <div class="planejamento-action-row">
                            ${renderPlanButton({
                                label: 'Cancelar',
                                icon: 'close',
                                tone: 'danger',
                                attrs: 'data-dismiss-justificativa'
                            })}
                            ${renderPlanButton({
                                label: 'Confirmar alteração',
                                icon: 'check_circle',
                                tone: 'success',
                                type: 'submit'
                            })}
                        </div>
                    </form>
                `,
                async function (form) {
                    const justificativa = String((form.justificativa && form.justificativa.value) || '').trim();
                    if (!justificativa) {
                        throw new Error('Informe uma justificativa para alterar um planejamento ja concluido.');
                    }
                    closeModal('submit');
                    resolve(justificativa);
                },
                function (reason) {
                    if (reason !== 'submit') {
                        resolve(null);
                    }
                }
            );
            const dismissButton = refs.modalBody.querySelector('[data-dismiss-justificativa]');
            if (dismissButton) {
                dismissButton.addEventListener('click', function () {
                    closeModal('cancel');
                });
            }
        });
    }

    function getConcludedPlanningActions() {
        const planejamento = currentPlanning();
        const activeMembers = (planejamento && planejamento.membros_ativos) ? planejamento.membros_ativos : [];
        const hasActiveMembers = activeMembers.length > 0;
        return [
            { value: 'add_member', title: 'Adicionar membro', subtitle: 'Justifica e adiciona', icon: 'person_add', disabled: false },
            { value: 'edit_member', title: 'Editar membro', subtitle: 'Justifica e edita', icon: 'edit', disabled: !hasActiveMembers },
            { value: 'replace_member', title: 'Substituir membro', subtitle: 'Justifica e substitui', icon: 'swap_horiz', disabled: !hasActiveMembers },
            { value: 'cancel_member', title: 'Cancelar membro', subtitle: 'Justifica e cancela', icon: 'person_remove', disabled: !hasActiveMembers },
            { value: 'edit_header', title: 'Editar informações do embarque', subtitle: 'Justifica e salva alterações', icon: 'event', disabled: false }
        ];
    }

    function buildWorkflowSummary(context) {
        return `
            <div class="planejamento-justificativa-box">
                <h5>Justificativa vinculada</h5>
                <div class="planejamento-justificativa-box__line"><strong>Ação:</strong> <span>${escapeHtml(context.label)}</span></div>
                <div class="planejamento-justificativa-box__line"><strong>Justificativa:</strong> <span>${escapeHtml(context.justificativa)}</span></div>
            </div>
        `;
    }

    function buildWorkflowIntro(context) {
        return `
            <div class="planejamento-workflow-banner">
                <span class="material-icons" aria-hidden="true">check_circle</span>
                <div>Justificativa registrada. Esta alteração ficará no histórico do planejamento.</div>
            </div>
            ${buildWorkflowSummary(context)}
        `;
    }

    function closeAndOpen(callback) {
        closeModal('switch');
        callback();
    }

    function openConcludedPlanningActionSelector(selectedAction, justification) {
        const actions = getConcludedPlanningActions();
        const defaultAction = (actions.find((item) => !item.disabled) || {}).value || '';
        const chosenAction = selectedAction || defaultAction;
        const chosenJustification = justification || '';
        state.editFlow.action = chosenAction;
        state.editFlow.justification = chosenJustification;
        openModal(
            'Alterar planejamento concluído',
            `
                <div class="plan-edit-modal">
                    <div class="plan-edit-modal__header">
                        <div class="plan-edit-modal__title-area">
                            <span class="material-icons plan-edit-modal__alert-icon" aria-hidden="true">warning_amber</span>
                            <div>
                                <h3>Alterar planejamento concluído</h3>
                                <p>Planejamento já concluído. Alterações exigem justificativa.</p>
                            </div>
                        </div>
                        <button type="button" class="plan-edit-modal__close" data-workflow-close aria-label="Fechar">
                            <span class="material-icons" aria-hidden="true">close</span>
                        </button>
                    </div>
                    <form>
                        <div class="plan-edit-modal__body">
                            <div class="plan-edit-modal__section-title">
                                <h4>Escolha o que deseja fazer</h4>
                                <p>Selecione o tipo de alteração que deseja realizar neste planejamento.</p>
                            </div>
                            <div class="plan-action-list">
                                ${actions.map((action) => `
                                    <label class="plan-action-option${chosenAction === action.value ? ' is-selected' : ''}${action.disabled ? ' is-disabled' : ''}">
                                        <input type="radio" name="acao_concluida" value="${escapeHtml(action.value)}" ${chosenAction === action.value ? 'checked' : ''} ${action.disabled ? 'disabled' : ''}>
                                        <span class="plan-action-option__icon">
                                            <span class="material-icons" aria-hidden="true">${action.icon}</span>
                                        </span>
                                        <span class="plan-action-option__content">
                                            <strong>${escapeHtml(action.title)}</strong>
                                            <small>${escapeHtml(action.subtitle)}</small>
                                        </span>
                                        <span class="plan-action-option__radio" aria-hidden="true"></span>
                                    </label>
                                `).join('')}
                            </div>
                            <div class="plan-justification-field">
                                <label for="workflowJustificativa">Justificativa *</label>
                                <p>Informe o motivo da alteração. Este texto ficará registrado no histórico.</p>
                                <textarea id="workflowJustificativa" name="justificativa" maxlength="1000" placeholder="Descreva aqui a justificativa da alteração..." required>${escapeHtml(chosenJustification)}</textarea>
                                <div class="plan-justification-field__counter">0/1000</div>
                            </div>
                        </div>
                        <div class="plan-edit-modal__footer">
                            ${renderPlanButton({
                                label: 'Cancelar',
                                icon: 'close',
                                tone: 'danger',
                                attrs: 'data-workflow-cancel'
                            })}
                            ${renderPlanButton({
                                label: 'Continuar',
                                icon: 'arrow_forward',
                                tone: 'success',
                                type: 'submit',
                                attrs: 'data-workflow-continue',
                                disabled: true
                            })}
                        </div>
                    </form>
                </div>
            `,
            async function (form) {
                const data = new FormData(form);
                const actionValue = String(state.editFlow.action || data.get('acao_concluida') || '').trim();
                const action = actions.find((item) => item.value === actionValue && !item.disabled);
                const text = String(state.editFlow.justification || data.get('justificativa') || '').trim();
                if (!action) {
                    throw new Error('Escolha a ação que deseja realizar.');
                }
                if (text.length < 10) {
                    throw new Error('Informe uma justificativa com pelo menos 10 caracteres.');
                }
                const context = { action: action.value, label: action.title, justificativa: text };
                if (action.value === 'add_member') {
                    closeAndOpen(() => openConcludedAddMemberModal(context));
                    return;
                }
                if (action.value === 'edit_member') {
                    closeAndOpen(() => openConcludedMemberPicker(context, 'edit'));
                    return;
                }
                if (action.value === 'replace_member') {
                    closeAndOpen(() => openConcludedMemberPicker(context, 'replace'));
                    return;
                }
                if (action.value === 'cancel_member') {
                    closeAndOpen(() => openConcludedMemberPicker(context, 'cancel'));
                    return;
                }
                if (action.value === 'edit_header') {
                    closeAndOpen(() => openConcludedHeaderModal(context));
                }
            },
            null,
            { variant: 'plan-edit', hideDefaultHeader: true }
        );
        const cancelButton = refs.modalBody.querySelector('[data-workflow-cancel]');
        if (cancelButton) {
            cancelButton.addEventListener('click', function () {
                closeModal('cancel');
            });
        }
        const closeButton = refs.modalBody.querySelector('[data-workflow-close]');
        if (closeButton) {
            closeButton.addEventListener('click', function () {
                closeModal('cancel');
            });
        }
        const justificationField = document.getElementById('workflowJustificativa');
        const counter = refs.modalBody.querySelector('.plan-justification-field__counter');
        const continueButton = refs.modalBody.querySelector('[data-workflow-continue]');
        const actionInputs = Array.from(refs.modalBody.querySelectorAll('input[name="acao_concluida"]'));
        const updateFlowOptionState = function () {
            refs.modalBody.querySelectorAll('.plan-action-option').forEach((option) => {
                const input = option.querySelector('input[name="acao_concluida"]');
                const checked = Boolean(input && input.checked);
                option.classList.toggle('is-selected', checked);
            });
        };
        const canContinueEditFlow = function () {
            return Boolean(state.editFlow.action) && state.editFlow.justification.trim().length >= 10;
        };
        const syncContinueButton = function () {
            if (continueButton) {
                continueButton.disabled = !canContinueEditFlow();
            }
        };
        actionInputs.forEach((input) => {
            input.addEventListener('change', function () {
                state.editFlow.action = this.checked ? this.value : '';
                updateFlowOptionState();
                syncContinueButton();
            });
        });
        if (justificationField && counter) {
            const updateCounter = function () {
                state.editFlow.justification = justificationField.value;
                counter.textContent = `${justificationField.value.length}/1000`;
                syncContinueButton();
            };
            justificationField.addEventListener('input', updateCounter);
            updateCounter();
        }
        updateFlowOptionState();
        syncContinueButton();
    }

    function getActivePlanningMembers() {
        const planejamento = currentPlanning();
        return planejamento ? (planejamento.membros_ativos || []) : [];
    }

    function openConcludedMemberPicker(context, mode) {
        const members = getActivePlanningMembers();
        const labels = {
            edit: {
                title: 'Editar membro com justificativa',
                subtitle: 'Selecione o membro que deseja editar. A justificativa será vinculada à alteração.',
                button: 'Selecionar'
            },
            replace: {
                title: 'Substituir membro com justificativa',
                subtitle: 'Selecione o membro que será substituído. Depois informe o novo membro.',
                button: 'Substituir este membro'
            },
            cancel: {
                title: 'Cancelar membro com justificativa',
                subtitle: 'Selecione o membro que deseja cancelar. Essa ação ficará registrada no histórico.',
                button: 'Cancelar este membro'
            }
        };
        const copy = labels[mode];
        openModal(
            copy.title,
            `
                <div class="planejamento-modal-stack">
                    ${buildWorkflowIntro(context)}
                    <div class="planejamento-modal-copy">
                        <p>${escapeHtml(copy.subtitle)}</p>
                    </div>
                    <div class="planejamento-picker-list">
                        ${members.length ? members.map((member) => `
                            <article class="planejamento-picker-card">
                                <div class="planejamento-picker-card__content">
                                    <strong>${escapeHtml(member.nome_snapshot || '-')}</strong>
                                    <span>${escapeHtml(member.funcao_planejada || '-')}</span>
                                    <small>Data início: ${escapeHtml(formatDate(member.data_inicio))}</small>
                                </div>
                                ${renderPlanButton({
                                    label: copy.button,
                                    icon: mode === 'replace' ? 'swap_horiz' : mode === 'cancel' ? 'person_remove' : 'task_alt',
                                    tone: mode === 'cancel' ? 'danger' : mode === 'replace' ? 'success' : 'neutral',
                                    attrs: `data-workflow-member="${member.id}"`
                                })}
                            </article>
                        `).join('') : '<div class="planejamento-member-empty">Nenhum membro ativo disponível.</div>'}
                    </div>
                    <div class="planejamento-action-row">
                        ${renderPlanButton({
                            label: 'Cancelar',
                            icon: 'close',
                            tone: 'danger',
                            attrs: 'data-workflow-cancel'
                        })}
                        ${renderPlanButton({
                            label: 'Voltar',
                            icon: 'arrow_back',
                            tone: 'neutral',
                            attrs: 'data-workflow-back'
                        })}
                    </div>
                </div>
            `
        );
        refs.modalBody.querySelectorAll('[data-workflow-member]').forEach((button) => {
            button.addEventListener('click', function () {
                const member = findMember(this.dataset.workflowMember);
                if (!member) {
                    showAlert('Membro não encontrado.', 'error');
                    return;
                }
                if (mode === 'edit') {
                    closeAndOpen(() => openConcludedEditMemberModal(context, member));
                    return;
                }
                if (mode === 'replace') {
                    closeAndOpen(() => openConcludedReplaceMemberModal(context, member));
                    return;
                }
                closeAndOpen(() => openConcludedCancelMemberModal(context, member));
            });
        });
        const cancelButton = refs.modalBody.querySelector('[data-workflow-cancel]');
        if (cancelButton) {
            cancelButton.addEventListener('click', function () {
                closeModal('cancel');
            });
        }
        const backButton = refs.modalBody.querySelector('[data-workflow-back]');
        if (backButton) {
            backButton.addEventListener('click', function () {
                closeAndOpen(() => openConcludedPlanningActionSelector(context.action, context.justificativa));
            });
        }
    }

    function openConcludedAddMemberModal(context) {
        openModal(
            'Adicionar membro com justificativa',
            `
                <form>
                    <div class="planejamento-modal-stack">
                        <div class="planejamento-modal-copy">
                            <p>Alteração autorizada para este planejamento. Preencha os dados do novo membro e confirme a inclusão.</p>
                        </div>
                        ${buildWorkflowIntro(context)}
                        <div class="planejamento-member-form-grid">
                            <div class="planejamento-field">
                                <label for="workflowNovoNome">Nome</label>
                                ${renderPersonCombobox({
                                    inputId: 'workflowNovoNome',
                                    targetFuncao: '#workflowNovaFuncao',
                                    placeholder: 'Pesquisar pessoa',
                                    required: true
                                })}
                            </div>
                            <div class="planejamento-field">
                                <label for="workflowNovaFuncao">Função</label>
                                <select id="workflowNovaFuncao" class="planejamento-select" name="funcao_planejada" required>
                                    ${functionOptions('')}
                                </select>
                            </div>
                            <div class="planejamento-field">
                                <label for="workflowNovaDataInicio">Data início</label>
                                <input id="workflowNovaDataInicio" type="date" class="planejamento-input" name="data_inicio">
                            </div>
                            <div class="planejamento-field field-observacao">
                                <label for="workflowNovaObservacao">Observação (opcional)</label>
                                <textarea id="workflowNovaObservacao" class="planejamento-textarea" name="observacao"></textarea>
                            </div>
                        </div>
                        <div class="planejamento-action-row">
                            ${renderPlanButton({
                                label: 'Cancelar',
                                icon: 'close',
                                tone: 'danger',
                                attrs: 'data-workflow-cancel'
                            })}
                            ${renderPlanButton({
                                label: 'Voltar',
                                icon: 'arrow_back',
                                tone: 'neutral',
                                attrs: 'data-workflow-back'
                            })}
                            ${renderPlanButton({
                                label: 'Confirmar adição',
                                icon: 'check_circle',
                                tone: 'success',
                                type: 'submit'
                            })}
                        </div>
                    </div>
                </form>
            `,
            async function (form) {
                const planejamento = currentPlanning();
                if (!planejamento) {
                    throw new Error('Planejamento não encontrado.');
                }
                const formData = buildMemberFormData(form);
                formData.set('justificativa', context.justificativa);
                const data = await apiRequest(endpoint(app.dataset.planejamentoAddMembroUrlTemplate, { '__PLANEJAMENTO_ID__': planejamento.id }), {
                    method: 'POST',
                    formData
                });
                closeModal('submit');
                state.memberTab = 'ativos';
                syncDetailFromResponse(data);
                showAlert('Membro adicionado com sucesso.', 'success');
            }
        );
        const cancelButton = refs.modalBody.querySelector('[data-workflow-cancel]');
        if (cancelButton) {
            cancelButton.addEventListener('click', function () {
                closeModal('cancel');
            });
        }
        const backButton = refs.modalBody.querySelector('[data-workflow-back]');
        if (backButton) {
            backButton.addEventListener('click', function () {
                closeAndOpen(() => openConcludedPlanningActionSelector(context.action, context.justificativa));
            });
        }
    }

    function openConcludedEditMemberModal(context, member) {
        openModal(
            'Editar membro com justificativa',
            `
                <form>
                    <div class="planejamento-modal-stack">
                        <div class="planejamento-modal-copy">
                            <p>Alteração autorizada para este planejamento. Ajuste os dados do membro selecionado e confirme.</p>
                        </div>
                        ${buildWorkflowIntro(context)}
                        <div class="planejamento-form-grid">
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Nome</label>
                                ${renderPersonCombobox({
                                    inputId: 'workflowEditNome',
                                    personId: member.pessoa_id,
                                    personName: member.nome_snapshot || '',
                                    targetFuncao: '#workflowEditFuncao',
                                    placeholder: 'Pesquisar pessoa',
                                    required: true
                                })}
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Função</label>
                                <select id="workflowEditFuncao" class="planejamento-select" name="funcao_planejada" required>
                                    ${functionOptions(member.funcao_planejada || '')}
                                </select>
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Data início</label>
                                <input type="date" class="planejamento-input" name="data_inicio" value="${escapeHtml(member.data_inicio || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Ordem</label>
                                <input type="number" class="planejamento-input" name="ordem" min="0" value="${escapeHtml(member.ordem || 0)}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label>Observação</label>
                                <textarea class="planejamento-textarea" name="observacao">${escapeHtml(member.observacao || '')}</textarea>
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label class="planejamento-field__group-title">Desembarque individual</label>
                            </div>
                            <div class="planejamento-field planejamento-field--span-3">
                                <label>Data desembarque</label>
                                <input type="date" class="planejamento-input" name="data_desembarque" value="${escapeHtml(member.data_desembarque || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-3">
                                <label>Horário desembarque</label>
                                <input type="time" step="60" class="planejamento-input" name="horario_desembarque" value="${escapeHtml(member.horario_desembarque || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Local desembarque</label>
                                <input class="planejamento-input" name="local_desembarque_membro" value="${escapeHtml(member.local_desembarque_membro || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label>Observação desembarque</label>
                                <textarea class="planejamento-textarea" name="observacao_desembarque">${escapeHtml(member.observacao_desembarque || '')}</textarea>
                            </div>
                        </div>
                        <div class="planejamento-action-row">
                            ${renderPlanButton({
                                label: 'Cancelar',
                                icon: 'close',
                                tone: 'danger',
                                attrs: 'data-workflow-cancel'
                            })}
                            ${renderPlanButton({
                                label: 'Voltar para lista',
                                icon: 'arrow_back',
                                tone: 'neutral',
                                attrs: 'data-workflow-back'
                            })}
                            ${renderPlanButton({
                                label: 'Confirmar edição',
                                icon: 'done',
                                tone: 'success',
                                type: 'submit'
                            })}
                        </div>
                    </div>
                </form>
            `,
            async function (form) {
                const formData = buildMemberFormData(form);
                formData.set('justificativa', context.justificativa);
                const data = await apiRequest(endpoint(app.dataset.membroUpdateUrlTemplate, { '__MEMBRO_ID__': member.id }), {
                    method: 'POST',
                    formData
                });
                closeModal('submit');
                syncDetailFromResponse(data);
                showAlert('Membro atualizado.', 'success');
            }
        );
        refs.modalBody.querySelector('[data-workflow-cancel]')?.addEventListener('click', function () {
            closeModal('cancel');
        });
        refs.modalBody.querySelector('[data-workflow-back]')?.addEventListener('click', function () {
            closeAndOpen(() => openConcludedMemberPicker(context, 'edit'));
        });
    }

    function openConcludedReplaceMemberModal(context, member) {
        openModal(
            'Substituir membro com justificativa',
            `
                <form>
                    <div class="planejamento-modal-stack">
                        <div class="planejamento-modal-copy">
                            <p>Selecione o novo membro e confirme a substituição. O vínculo com o membro substituído será preservado.</p>
                        </div>
                        ${buildWorkflowIntro(context)}
                        <div class="planejamento-picked-member">
                            <span class="planejamento-picked-member__label">Membro substituído</span>
                            <strong>${escapeHtml(member.nome_snapshot || '-')}</strong>
                            <small>${escapeHtml(member.funcao_planejada || '-')} | Data início: ${escapeHtml(formatDate(member.data_inicio))}</small>
                        </div>
                        <div class="planejamento-form-grid">
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Novo nome</label>
                                ${renderPersonCombobox({
                                    inputId: 'workflowReplaceNome',
                                    targetFuncao: '#workflowReplaceFuncao',
                                    placeholder: 'Pesquisar pessoa',
                                    required: true
                                })}
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Nova função</label>
                                <select id="workflowReplaceFuncao" class="planejamento-select" name="funcao_planejada" required>
                                    ${functionOptions('')}
                                </select>
                            </div>
                            <div class="planejamento-field planejamento-field--span-4">
                                <label>Data início do novo</label>
                                <input type="date" class="planejamento-input" name="data_inicio">
                            </div>
                            <div class="planejamento-field planejamento-field--span-4">
                                <label>Data fim do antigo</label>
                                <input type="date" class="planejamento-input" name="data_fim">
                            </div>
                            <div class="planejamento-field planejamento-field--span-4">
                                <label>Observação</label>
                                <input class="planejamento-input" name="observacao">
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label>Motivo da substituição</label>
                                <textarea class="planejamento-textarea" name="motivo_substituicao"></textarea>
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label class="planejamento-field__group-title">Desembarque do membro substituído</label>
                            </div>
                            <div class="planejamento-field planejamento-field--span-3">
                                <label>Data desembarque do antigo</label>
                                <input type="date" class="planejamento-input" name="data_desembarque_antigo" value="${escapeHtml(member.data_desembarque || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-3">
                                <label>Horário desembarque do antigo</label>
                                <input type="time" step="60" class="planejamento-input" name="horario_desembarque_antigo" value="${escapeHtml(member.horario_desembarque || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Local desembarque do antigo</label>
                                <input class="planejamento-input" name="local_desembarque_membro_antigo" value="${escapeHtml(member.local_desembarque_membro || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label>Observação desembarque do antigo</label>
                                <textarea class="planejamento-textarea" name="observacao_desembarque_antigo">${escapeHtml(member.observacao_desembarque || '')}</textarea>
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label class="planejamento-field__group-title">Desembarque individual do novo membro</label>
                            </div>
                            <div class="planejamento-field planejamento-field--span-3">
                                <label>Data desembarque do novo</label>
                                <input type="date" class="planejamento-input" name="data_desembarque">
                            </div>
                            <div class="planejamento-field planejamento-field--span-3">
                                <label>Horário desembarque do novo</label>
                                <input type="time" step="60" class="planejamento-input" name="horario_desembarque">
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Local desembarque do novo</label>
                                <input class="planejamento-input" name="local_desembarque_membro">
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label>Observação desembarque do novo</label>
                                <textarea class="planejamento-textarea" name="observacao_desembarque"></textarea>
                            </div>
                        </div>
                        <div class="planejamento-action-row">
                            ${renderPlanButton({
                                label: 'Cancelar',
                                icon: 'close',
                                tone: 'danger',
                                attrs: 'data-workflow-cancel'
                            })}
                            ${renderPlanButton({
                                label: 'Voltar para lista',
                                icon: 'arrow_back',
                                tone: 'neutral',
                                attrs: 'data-workflow-back'
                            })}
                            ${renderPlanButton({
                                label: 'Confirmar substituição',
                                icon: 'swap_horiz',
                                tone: 'success',
                                type: 'submit'
                            })}
                        </div>
                    </div>
                </form>
            `,
            async function (form) {
                const formData = buildMemberFormData(form);
                formData.set('justificativa', context.justificativa);
                const data = await apiRequest(endpoint(app.dataset.membroSubstituirUrlTemplate, { '__MEMBRO_ID__': member.id }), {
                    method: 'POST',
                    formData
                });
                closeModal('submit');
                state.memberTab = 'ativos';
                syncDetailFromResponse(data);
                showAlert('Substituição registrada.', 'success');
            }
        );
        refs.modalBody.querySelector('[data-workflow-cancel]')?.addEventListener('click', function () {
            closeModal('cancel');
        });
        refs.modalBody.querySelector('[data-workflow-back]')?.addEventListener('click', function () {
            closeAndOpen(() => openConcludedMemberPicker(context, 'replace'));
        });
    }

    function openConcludedCancelMemberModal(context, member) {
        openModal(
            'Cancelar membro com justificativa',
            `
                <form>
                    <div class="planejamento-modal-stack">
                        <div class="planejamento-modal-copy">
                            <p>Você está cancelando o membro abaixo. Essa ação ficará registrada no histórico.</p>
                        </div>
                        ${buildWorkflowIntro(context)}
                        <div class="planejamento-picked-member">
                            <span class="planejamento-picked-member__label">Você está cancelando</span>
                            <strong>${escapeHtml(member.nome_snapshot || '-')}</strong>
                            <small>${escapeHtml(member.funcao_planejada || '-')} | Data início: ${escapeHtml(formatDate(member.data_inicio))}</small>
                        </div>
                        <div class="planejamento-form-grid">
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Data fim</label>
                                <input type="date" class="planejamento-input" name="data_fim">
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Observação</label>
                                <input class="planejamento-input" name="observacao">
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label>Motivo do cancelamento</label>
                                <textarea class="planejamento-textarea" name="motivo_substituicao"></textarea>
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label class="planejamento-field__group-title">Desembarque do membro</label>
                            </div>
                            <div class="planejamento-field planejamento-field--span-3">
                                <label>Data desembarque</label>
                                <input type="date" class="planejamento-input" name="data_desembarque" value="${escapeHtml(member.data_desembarque || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-3">
                                <label>Horário desembarque</label>
                                <input type="time" step="60" class="planejamento-input" name="horario_desembarque" value="${escapeHtml(member.horario_desembarque || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-6">
                                <label>Local desembarque</label>
                                <input class="planejamento-input" name="local_desembarque_membro" value="${escapeHtml(member.local_desembarque_membro || '')}">
                            </div>
                            <div class="planejamento-field planejamento-field--span-12">
                                <label>Observação desembarque</label>
                                <textarea class="planejamento-textarea" name="observacao_desembarque">${escapeHtml(member.observacao_desembarque || '')}</textarea>
                            </div>
                        </div>
                        <div class="planejamento-action-row">
                            ${renderPlanButton({
                                label: 'Cancelar',
                                icon: 'close',
                                tone: 'danger',
                                attrs: 'data-workflow-cancel'
                            })}
                            ${renderPlanButton({
                                label: 'Voltar para lista',
                                icon: 'arrow_back',
                                tone: 'neutral',
                                attrs: 'data-workflow-back'
                            })}
                            ${renderPlanButton({
                                label: 'Confirmar cancelamento',
                                icon: 'close',
                                tone: 'danger',
                                type: 'submit'
                            })}
                        </div>
                    </div>
                </form>
            `,
            async function (form) {
                const formData = new FormData(form);
                formData.set('justificativa', context.justificativa);
                const data = await apiRequest(endpoint(app.dataset.membroCancelarUrlTemplate, { '__MEMBRO_ID__': member.id }), {
                    method: 'POST',
                    formData
                });
                closeModal('submit');
                state.memberTab = 'cancelados';
                syncDetailFromResponse(data);
                showAlert('Membro cancelado.', 'success');
            }
        );
        refs.modalBody.querySelector('[data-workflow-cancel]')?.addEventListener('click', function () {
            closeModal('cancel');
        });
        refs.modalBody.querySelector('[data-workflow-back]')?.addEventListener('click', function () {
            closeAndOpen(() => openConcludedMemberPicker(context, 'cancel'));
        });
    }

    function openConcludedHeaderModal(context) {
        const planejamento = currentPlanning();
        if (!planejamento) {
            showAlert('Planejamento não encontrado.', 'error');
            return;
        }
        openModal(
            'Editar embarque e desembarque com justificativa',
            `
                <form>
                    <div class="planejamento-modal-stack">
                        <div class="planejamento-modal-copy">
                            <p>Altere as informações gerais de embarque e desembarque e confirme o salvamento.</p>
                        </div>
                        ${buildWorkflowIntro(context)}
                        <div class="planejamento-schedule-stack">
                            <section class="planejamento-schedule-section">
                                <div class="planejamento-subsection-title">
                                    <p class="planejamento-section__eyebrow">Programação de embarque</p>
                                </div>
                                <div class="planejamento-boarding-grid">
                                    <div class="planejamento-field field-title">
                                        <label for="workflowCabTitulo">Título do planejamento</label>
                                        <input id="workflowCabTitulo" class="planejamento-input" name="titulo_planejamento" value="${escapeHtml(planejamento.titulo_planejamento || '')}">
                                    </div>
                                    <div class="planejamento-field field-date">
                                        <label for="workflowCabData">Data embarque</label>
                                        <input id="workflowCabData" type="date" class="planejamento-input" name="data_prevista_subida" value="${escapeHtml(planejamento.data_prevista_subida || '')}">
                                    </div>
                                    <div class="planejamento-field field-time">
                                        <label for="workflowCabHorario">Horário embarque</label>
                                        <div class="planejamento-input-shell">
                                            <input id="workflowCabHorario" type="time" step="60" class="planejamento-input planejamento-input--with-icon" name="horario_previsto_subida" value="${escapeHtml(planejamento.horario_previsto_subida || '')}">
                                            <span class="material-icons planejamento-input-shell__icon" aria-hidden="true">schedule</span>
                                        </div>
                                    </div>
                                    <div class="planejamento-field field-local">
                                        <label for="workflowCabLocal">Local de embarque</label>
                                        <input id="workflowCabLocal" class="planejamento-input" name="local_subida" value="${escapeHtml(planejamento.local_subida || '')}">
                                    </div>
                                    <div class="planejamento-field field-observacao">
                                        <label for="workflowCabObservacao">Observações de embarque</label>
                                        <textarea id="workflowCabObservacao" class="planejamento-textarea planejamento-textarea--compact" name="observacao">${escapeHtml(planejamento.observacao || '')}</textarea>
                                    </div>
                                </div>
                            </section>
                            <section class="planejamento-schedule-section">
                                <div class="planejamento-subsection-title">
                                    <p class="planejamento-section__eyebrow">Programação de desembarque</p>
                                </div>
                                <div class="planejamento-boarding-grid">
                                    <div class="planejamento-field field-date">
                                        <label for="workflowCabDataDesembarque">Data desembarque</label>
                                        <input id="workflowCabDataDesembarque" type="date" class="planejamento-input" name="data_prevista_desembarque" value="${escapeHtml(planejamento.data_prevista_desembarque || '')}">
                                    </div>
                                    <div class="planejamento-field field-time">
                                        <label for="workflowCabHorarioDesembarque">Horário desembarque</label>
                                        <div class="planejamento-input-shell">
                                            <input id="workflowCabHorarioDesembarque" type="time" step="60" class="planejamento-input planejamento-input--with-icon" name="horario_previsto_desembarque" value="${escapeHtml(planejamento.horario_previsto_desembarque || '')}">
                                            <span class="material-icons planejamento-input-shell__icon" aria-hidden="true">schedule</span>
                                        </div>
                                    </div>
                                    <div class="planejamento-field field-local planejamento-field--span-full">
                                        <label for="workflowCabLocalDesembarque">Local de desembarque</label>
                                        <input id="workflowCabLocalDesembarque" class="planejamento-input" name="local_desembarque" value="${escapeHtml(planejamento.local_desembarque || '')}">
                                    </div>
                                    <div class="planejamento-field field-observacao planejamento-field--span-full">
                                        <label for="workflowCabObservacaoDesembarque">Observações de desembarque</label>
                                        <textarea id="workflowCabObservacaoDesembarque" class="planejamento-textarea planejamento-textarea--compact" name="observacao_desembarque">${escapeHtml(planejamento.observacao_desembarque || '')}</textarea>
                                    </div>
                                </div>
                            </section>
                        </div>
                        <div class="planejamento-action-row">
                            ${renderPlanButton({
                                label: 'Cancelar',
                                icon: 'close',
                                tone: 'danger',
                                attrs: 'data-workflow-cancel'
                            })}
                            ${renderPlanButton({
                                label: 'Voltar',
                                icon: 'arrow_back',
                                tone: 'neutral',
                                attrs: 'data-workflow-back'
                            })}
                            ${renderPlanButton({
                                label: 'Salvar alterações',
                                icon: 'save',
                                tone: 'success',
                                type: 'submit'
                            })}
                        </div>
                    </div>
                </form>
            `,
            async function (form) {
                const horario = String(form.horario_previsto_subida.value || '').trim();
                const horarioDesembarque = String(form.horario_previsto_desembarque.value || '').trim();
                if (horario && !/^([01]\d|2[0-3]):[0-5]\d$/.test(horario)) {
                    throw new Error('Informe um horário válido no formato HH:MM.');
                }
                if (horarioDesembarque && !/^([01]\d|2[0-3]):[0-5]\d$/.test(horarioDesembarque)) {
                    throw new Error('Informe um horário de desembarque válido no formato HH:MM.');
                }
                const payload = {
                    titulo_planejamento: form.titulo_planejamento.value,
                    data_prevista_subida: form.data_prevista_subida.value,
                    horario_previsto_subida: horario,
                    local_subida: form.local_subida.value,
                    observacao: form.observacao.value,
                    data_prevista_desembarque: form.data_prevista_desembarque.value,
                    horario_previsto_desembarque: horarioDesembarque,
                    local_desembarque: form.local_desembarque.value,
                    observacao_desembarque: form.observacao_desembarque.value,
                    justificativa: context.justificativa
                };
                const data = await apiRequest(endpoint(app.dataset.planejamentoCabecalhoUrlTemplate, { '__PLANEJAMENTO_ID__': planejamento.id }), {
                    method: 'POST',
                    jsonBody: payload
                });
                closeModal('submit');
                syncDetailFromResponse(data);
                showAlert('Informações de embarque e desembarque salvas.', 'success');
            }
        );
        refs.modalBody.querySelector('[data-workflow-cancel]')?.addEventListener('click', function () {
            closeModal('cancel');
        });
        refs.modalBody.querySelector('[data-workflow-back]')?.addEventListener('click', function () {
            closeAndOpen(() => openConcludedPlanningActionSelector(context.action, context.justificativa));
        });
    }

    function syncDetailFromResponse(payload) {
        if (!payload) {
            return;
        }
        state.detail = {
            success: true,
            os: payload.os || currentOs(),
            tem_planejamento: Boolean(payload.planejamento),
            planejamento: payload.planejamento || null
        };
        state.selectedOsId = state.detail.os ? state.detail.os.id : null;
        state.selectedGroupNumeroOs = state.detail.os ? state.detail.os.numero_os : state.selectedGroupNumeroOs;
        renderCards();
        renderPanel();
        loadCards();
    }

    function functionOptions(selected) {
        return [
            '<option value="">Selecione</option>',
            ...funcoes.map((funcao) => `<option value="${escapeHtml(funcao.value)}" ${funcao.value === selected ? 'selected' : ''}>${escapeHtml(funcao.label)}</option>`)
        ].join('');
    }

    function getPessoaInicial(personId, personName) {
        const normalizedId = String(personId || '').trim();
        if (normalizedId && pessoasById.has(normalizedId)) {
            return pessoasById.get(normalizedId);
        }
        const normalizedName = normalize(personName);
        return normalizedName ? (pessoasByName.get(normalizedName) || null) : null;
    }

    function renderPersonCombobox(config) {
        const initialPerson = getPessoaInicial(config.personId, config.personName);
        const inputId = config.inputId || '';
        const targetFuncao = config.targetFuncao || '';
        const disabled = config.disabled ? 'disabled' : '';
        const required = config.required ? 'required' : '';
        const placeholder = config.placeholder || 'Pesquisar pessoa';
        const selectedId = initialPerson ? String(initialPerson.id) : String(config.personId || '');
        const selectedName = initialPerson ? (initialPerson.nome || '') : String(config.personName || '');

        return `
            <div class="planejamento-combobox" data-person-combobox>
                <div class="planejamento-combobox__control">
                    <input
                        id="${escapeHtml(inputId)}"
                        class="planejamento-input planejamento-combobox__input"
                        name="pessoa_nome"
                        data-person-field="true"
                        data-target-funcao="${escapeHtml(targetFuncao)}"
                        data-selected-person-id="${escapeHtml(selectedId)}"
                        autocomplete="off"
                        placeholder="${escapeHtml(placeholder)}"
                        value="${escapeHtml(selectedName)}"
                        role="combobox"
                        aria-autocomplete="list"
                        aria-expanded="false"
                        aria-haspopup="listbox"
                        ${disabled}
                        ${required}
                    >
                    <button
                        type="button"
                        class="planejamento-combobox__toggle"
                        tabindex="-1"
                        aria-label="Abrir lista de pessoas"
                        ${disabled}
                    >
                        <span class="material-icons" aria-hidden="true">expand_more</span>
                    </button>
                </div>
                <input type="hidden" name="pessoa_id" value="${escapeHtml(selectedId)}">
                <div class="planejamento-combobox__menu" role="listbox" hidden></div>
            </div>
        `;
    }

    function buildReadonlyBanner(message) {
        if (!message) {
            return '';
        }
        return `
            <div class="planejamento-readonly-banner">
                <span class="material-icons" aria-hidden="true">lock</span>
                <div>${escapeHtml(message)}</div>
            </div>
        `;
    }

    function personCard(title, value) {
        return `
            <article class="planejamento-responsavel-card">
                <div class="planejamento-responsavel-card__avatar">
                    <span class="material-icons" aria-hidden="true">account_circle</span>
                </div>
                <div class="planejamento-responsavel-card__content">
                    <div class="planejamento-responsavel-card__label">${escapeHtml(title)}</div>
                    <div class="planejamento-responsavel-card__name">${escapeHtml(value || '-')}</div>
                    <div class="planejamento-responsavel-card__meta">${escapeHtml(value ? 'Responsável vindo da OS' : 'Não definido na OS')}</div>
                </div>
            </article>
        `;
    }

    function buildPlanningMeta(osItem, planejamento) {
        const meta = [];
        if (osItem.tanque) {
            meta.push(`Tanque: ${osItem.tanque}`);
        }
        if (osItem.pob) {
            meta.push(` POB: ${osItem.pob}`);
        }
        if (planejamento && planejamento.data_prevista_subida) {
            meta.push(` Embarque: ${formatDate(planejamento.data_prevista_subida)}`);
        }
        if (planejamento && planejamento.data_prevista_desembarque) {
            meta.push(` Desembarque: ${formatDate(planejamento.data_prevista_desembarque)}`);
        }
        if (osItem.status_operacao) {
            meta.push(` Operação: ${osItem.status_operacao}`);
        }
        if (!meta.length) {
            return '';
        }
        return `
            <section class="planejamento-detail-block">
                <div class="planejamento-member-row__details">
                    <div class="planejamento-member-row__details-list">
                        ${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join('')}
                    </div>
                </div>
            </section>
        `;
    }

    function buildNoPlanningBody(osItem) {
        return `
            <div class="planejamento-detail-stack">
                ${osItem.motivo_bloqueio_edicao ? `<div class="planejamento-detail-block">${buildReadonlyBanner(osItem.motivo_bloqueio_edicao)}</div>` : ''}
                ${buildPlanningMeta(osItem, null)}
                <section class="planejamento-detail-block">
                    <div class="planejamento-section__title">
                        <div>
                            <p class="planejamento-section__eyebrow">Planejamento</p>
                            <h4>Esta linha da OS ainda não possui planejamento de equipe.</h4>
                        </div>
                    </div>
                    <div class="planejamento-action-row">
                        ${renderPlanButton({
                            label: 'Iniciar planejamento',
                            icon: 'playlist_add',
                            tone: 'success',
                            attrs: 'id="iniciarPlanejamentoBtn"',
                            disabled: !osItem.permite_edicao
                        })}
                    </div>
                </section>
            </div>
        `;
    }

    function getMembersByTab(planejamento, tab) {
        if (tab === 'substituidos') {
            return planejamento.membros_substituidos || [];
        }
        if (tab === 'cancelados') {
            return planejamento.membros_cancelados || [];
        }
        return planejamento.membros_ativos || [];
    }

    function renderMemberStatusBadge(member) {
        const status = String(member.status || '-');
        const normalized = normalize(status);
        let badgeClass = 'planejamento-badge--sem';
        if (normalized === 'ativo') {
            badgeClass = 'planejamento-badge--rascunho';
        } else if (normalized === 'substituído' || normalized === 'substituido') {
            badgeClass = 'planejamento-badge--operacao';
        } else if (normalized === 'cancelado') {
            badgeClass = 'planejamento-badge--cancelado';
        }
        return `<span class="planejamento-badge ${badgeClass}">${escapeHtml(status)}</span>`;
    }

    function renderMemberRow(member, planejamento, allowDirectActions) {
        const allowActions = allowDirectActions && normalize(member.status) === 'ativo';
        const desembarque = getMemberDisembarkInfo(member, planejamento);
        const details = [];
        if (member.data_fim) {
            details.push({
                label: 'Data fim',
                value: formatDate(member.data_fim)
            });
        }
        if (member.local_desembarque_membro) {
            details.push({
                label: 'Local desembarque',
                value: member.local_desembarque_membro
            });
        }
        if (member.observacao_desembarque) {
            details.push({
                label: 'Obs. desembarque',
                value: member.observacao_desembarque
            });
        }
        if (member.motivo_substituicao) {
            details.push({
                label: 'Motivo',
                value: member.motivo_substituicao
            });
        }
        if (member.observacao) {
            details.push({
                label: 'Observação',
                value: member.observacao
            });
        }

        return `
            <article class="plan-member-card">
                <div class="plan-member-card__header">
                    <div class="plan-member-card__avatar">
                        <span class="material-icons" aria-hidden="true">person</span>
                    </div>
                    <div class="plan-member-card__identity">
                        <strong class="plan-member-card__name">${escapeHtml(member.nome_snapshot || '-')}</strong>
                        <span class="plan-member-card__role">${escapeHtml(member.funcao_planejada || '-')}</span>
                    </div>
                </div>
                <div class="plan-member-card__meta">
                    <div class="plan-member-card__meta-item">
                        <span>Embarque</span>
                        <strong>${escapeHtml(formatDate(member.data_inicio))}</strong>
                    </div>
                    <div class="plan-member-card__meta-item">
                        <span>Desembarque</span>
                        <strong>${escapeHtml(formatDateTimeLabel(desembarque.data, desembarque.horario))}</strong>
                    </div>
                </div>
                ${member.substitui_nome_snapshot ? `
                    <div class="plan-member-card__replacement">
                        <span>Substitui:</span>
                        <strong>${escapeHtml(member.substitui_nome_snapshot)}</strong>
                    </div>
                ` : ''}
                ${details.length ? `
                    <div class="plan-member-card__details">
                        ${details.map((item) => `
                            <div class="plan-member-card__detail-item">
                                <span>${escapeHtml(item.label)}</span>
                                <strong>${escapeHtml(item.value || '-')}</strong>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
                <div class="plan-member-card__actions">
                    <div class="planejamento-member-actions">
                        ${allowActions ? `
                            <button type="button" class="planejamento-icon-button plan-member-action" title="Editar" aria-label="Editar membro" data-member-action="edit" data-member-id="${member.id}">
                                <span class="material-icons" aria-hidden="true">edit</span>
                            </button>
                            <button type="button" class="planejamento-icon-button plan-member-action" title="Substituir" aria-label="Substituir membro" data-member-action="replace" data-member-id="${member.id}">
                                <span class="material-icons" aria-hidden="true">swap_horiz</span>
                            </button>
                            <button type="button" class="planejamento-icon-button plan-member-action plan-member-action--danger" title="Cancelar" aria-label="Cancelar membro" data-member-action="cancel" data-member-id="${member.id}">
                                <span class="material-icons" aria-hidden="true">delete</span>
                            </button>
                        ` : `<div class="plan-member-card__status">${renderMemberStatusBadge(member)}</div>`}
                    </div>
                </div>
            </article>
        `;
    }

    function renderMembersSection(planejamento, allowDirectActions, needsJustification) {
        const counters = {
            ativos: (planejamento.membros_ativos || []).length,
            substituidos: (planejamento.membros_substituidos || []).length,
            cancelados: (planejamento.membros_cancelados || []).length
        };
        const currentMembers = getMembersByTab(planejamento, state.memberTab);
        const emptyMessage = state.memberTab === 'ativos'
            ? 'Nenhum membro ativo.'
            : state.memberTab === 'substituidos'
                ? 'Nenhum membro substituído.'
                : 'Nenhum membro cancelado.';

        return `
            <section class="planejamento-detail-block">
                <div class="planejamento-section__title">
                    <div>
                        <p class="planejamento-section__eyebrow">Equipe</p>
                        <h4>Equipe</h4>
                    </div>
                </div>
                <div class="planejamento-member-tabs">
                    <button type="button" class="member-tab ${state.memberTab === 'ativos' ? 'is-active' : ''}" data-member-tab="ativos">Ativos (${counters.ativos})</button>
                    <button type="button" class="member-tab ${state.memberTab === 'substituidos' ? 'is-active' : ''}" data-member-tab="substituidos">Substituídos (${counters.substituidos})</button>
                    <button type="button" class="member-tab ${state.memberTab === 'cancelados' ? 'is-active' : ''}" data-member-tab="cancelados">Cancelados (${counters.cancelados})</button>
                </div>
                ${needsJustification ? `
                    <div class="planejamento-inline-message">
                        <span class="material-icons" aria-hidden="true">info</span>
                        <div>Este planejamento está concluído. Para adicionar, editar, substituir ou cancelar membros, clique em <strong>Editar planejamento</strong> e informe a justificativa.</div>
                    </div>
                ` : ''}
                <div class="planejamento-members-body">
                    ${currentMembers.length ? `
                        <div class="plan-member-list">
                            ${currentMembers.map((member) => renderMemberRow(member, planejamento, allowDirectActions)).join('')}
                        </div>
                    ` : `<div class="planejamento-member-empty">${escapeHtml(emptyMessage)}</div>`}
                </div>
            </section>
        `;
    }

    function buildMemberForm(editable, needsJustification) {
        if (!editable && needsJustification) {
            return '';
        }
        return `
            <section class="planejamento-detail-block">
                <div class="planejamento-section__title">
                    <div>
                        <p class="planejamento-section__eyebrow">Adicionar membro</p>
                        <h4>Adicionar membro</h4>
                    </div>
                </div>
                <form id="planejamentoAddMembroForm">
                    <div class="planejamento-member-form-grid">
                        <div class="planejamento-field">
                            <label for="novoNome">Nome</label>
                            ${renderPersonCombobox({
                                inputId: 'novoNome',
                                targetFuncao: '#novaFuncao',
                                placeholder: 'Pesquisar pessoa',
                                disabled: !editable
                            })}
                        </div>
                        <div class="planejamento-field">
                            <label for="novaFuncao">Função</label>
                            <select id="novaFuncao" class="planejamento-select" name="funcao_planejada" ${editable ? '' : 'disabled'}>
                                ${functionOptions('')}
                            </select>
                        </div>
                        <div class="planejamento-field">
                            <label for="novaDataInicio">Data início</label>
                            <input id="novaDataInicio" type="date" class="planejamento-input" name="data_inicio" ${editable ? '' : 'disabled'}>
                        </div>
                        <div class="planejamento-field field-observacao">
                            <label for="novaObservacao">Observação (opcional)</label>
                            <textarea id="novaObservacao" class="planejamento-textarea" name="observacao" ${editable ? '' : 'disabled'}></textarea>
                        </div>
                    </div>
                    <div class="planejamento-add-member-actions">
                        ${renderPlanButton({
                            label: 'Adicionar membro',
                            icon: 'person_add',
                            tone: 'success',
                            type: 'submit',
                            disabled: !editable
                        })}
                    </div>
                </form>
            </section>
        `;
    }

    function buildPlanningBody(osItem, planejamento) {
        const editable = Boolean(planejamento.permite_edicao);
        const needsJustification = Boolean(planejamento.requer_justificativa_alteracao && !planejamento.motivo_bloqueio_edicao);
        const directEditEnabled = editable && !needsJustification;
        const canGenerateDocument = canGeneratePlanningDocument(planejamento);
        return `
            <div class="planejamento-detail-stack">
                ${planejamento.motivo_bloqueio_edicao ? `<div class="planejamento-detail-block">${buildReadonlyBanner(planejamento.motivo_bloqueio_edicao)}</div>` : ''}
                ${needsJustification ? `
                    <div class="planejamento-detail-block">
                        <div class="planejamento-planned-edit-row">
                            <div class="planejamento-warning-banner">
                                <span class="material-icons" aria-hidden="true">info</span>
                                <div>Planejamento concluído. Para alterar, clique em <strong>Editar planejamento</strong>.</div>
                            </div>
                            ${renderPlanButton({
                                label: 'Editar planejamento',
                                icon: 'edit',
                                tone: 'success',
                                attrs: 'id="editarPlanejamentoBtn"'
                            })}
                        </div>
                    </div>
                ` : ''}
                ${buildPlanningMeta(osItem, planejamento)}
                <section class="planejamento-detail-block">
                    <div class="planejamento-section__title">
                        <div>
                            <p class="planejamento-section__eyebrow">Programação da equipe</p>
                        </div>
                        <div class="planejamento-inline-counters">
                            <span class="planejamento-chip">Ativos: ${escapeHtml(planejamento.quantidade_membros_ativos || 0)}</span>
                            <span class="planejamento-chip">Substituídos: ${escapeHtml(planejamento.quantidade_membros_substituidos || 0)}</span>
                            <span class="planejamento-chip">Cancelados: ${escapeHtml(planejamento.quantidade_membros_cancelados || 0)}</span>
                        </div>
                    </div>
                    <form id="planejamentoCabecalhoForm">
                        <div class="planejamento-schedule-stack">
                            <section class="planejamento-schedule-section">
                                <div class="planejamento-subsection-title">
                                    <p class="planejamento-section__eyebrow">Programação de embarque</p>
                                </div>
                                <div class="planejamento-boarding-grid">
                                    <div class="planejamento-field field-title">
                                        <label for="cabTitulo">Título do planejamento</label>
                                        <input id="cabTitulo" class="planejamento-input" name="titulo_planejamento" value="${escapeHtml(planejamento.titulo_planejamento || '')}" ${directEditEnabled ? '' : 'disabled'}>
                                    </div>
                                    <div class="planejamento-field field-date">
                                        <label for="cabData">Data embarque</label>
                                        <input id="cabData" type="date" class="planejamento-input" name="data_prevista_subida" value="${escapeHtml(planejamento.data_prevista_subida || '')}" ${directEditEnabled ? '' : 'disabled'}>
                                    </div>
                                    <div class="planejamento-field field-time">
                                        <label for="cabHorario">Horário embarque</label>
                                        <div class="planejamento-input-shell">
                                            <input id="cabHorario" type="time" step="60" class="planejamento-input planejamento-input--with-icon" name="horario_previsto_subida" value="${escapeHtml(planejamento.horario_previsto_subida || '')}" ${directEditEnabled ? '' : 'disabled'}>
                                            <span class="material-icons planejamento-input-shell__icon" aria-hidden="true">schedule</span>
                                        </div>
                                    </div>
                                    <div class="planejamento-field field-local">
                                        <label for="cabLocal">Local de embarque</label>
                                        <input id="cabLocal" class="planejamento-input" name="local_subida" value="${escapeHtml(planejamento.local_subida || '')}" ${directEditEnabled ? '' : 'disabled'}>
                                    </div>
                                    <div class="planejamento-field field-observacao">
                                        <label for="cabObservacao">Observações de embarque</label>
                                        <textarea id="cabObservacao" class="planejamento-textarea planejamento-textarea--compact" name="observacao" ${directEditEnabled ? '' : 'disabled'}>${escapeHtml(planejamento.observacao || '')}</textarea>
                                    </div>
                                </div>
                            </section>
                            <section class="planejamento-schedule-section">
                                <div class="planejamento-subsection-title">
                                    <p class="planejamento-section__eyebrow">Programação de desembarque</p>
                                </div>
                                <div class="planejamento-boarding-grid">
                                    <div class="planejamento-field field-date">
                                        <label for="cabDataDesembarque">Data desembarque</label>
                                        <input id="cabDataDesembarque" type="date" class="planejamento-input" name="data_prevista_desembarque" value="${escapeHtml(planejamento.data_prevista_desembarque || '')}" ${directEditEnabled ? '' : 'disabled'}>
                                    </div>
                                    <div class="planejamento-field field-time">
                                        <label for="cabHorarioDesembarque">Horário desembarque</label>
                                        <div class="planejamento-input-shell">
                                            <input id="cabHorarioDesembarque" type="time" step="60" class="planejamento-input planejamento-input--with-icon" name="horario_previsto_desembarque" value="${escapeHtml(planejamento.horario_previsto_desembarque || '')}" ${directEditEnabled ? '' : 'disabled'}>
                                            <span class="material-icons planejamento-input-shell__icon" aria-hidden="true">schedule</span>
                                        </div>
                                    </div>
                                    <div class="planejamento-field field-local planejamento-field--span-full">
                                        <label for="cabLocalDesembarque">Local de desembarque</label>
                                        <input id="cabLocalDesembarque" class="planejamento-input" name="local_desembarque" value="${escapeHtml(planejamento.local_desembarque || '')}" ${directEditEnabled ? '' : 'disabled'}>
                                    </div>
                                    <div class="planejamento-field field-observacao planejamento-field--span-full">
                                        <label for="cabObservacaoDesembarque">Observações de desembarque</label>
                                        <textarea id="cabObservacaoDesembarque" class="planejamento-textarea planejamento-textarea--compact" name="observacao_desembarque" ${directEditEnabled ? '' : 'disabled'}>${escapeHtml(planejamento.observacao_desembarque || '')}</textarea>
                                    </div>
                                </div>
                            </section>
                        </div>
                    </form>
                    <div class="planejamento-responsaveis-grid">
                        ${personCard('Coordenador', osItem.coordenador)}
                        ${personCard('Supervisor', planejamento.supervisor_nome_snapshot || osItem.supervisor_nome)}
                    </div>
                </section>
                ${renderMembersSection(planejamento, directEditEnabled, needsJustification)}
                ${buildMemberForm(directEditEnabled, needsJustification)}
                <section class="planejamento-detail-block planejamento-detail-footer">
                    <div class="planejamento-footer-actions">
                        ${renderPlanButton({
                            label: 'Salvar embarque e desembarque',
                            icon: 'save',
                            tone: 'success',
                            type: 'submit',
                            attrs: 'form="planejamentoCabecalhoForm"',
                            disabled: !directEditEnabled
                        })}
                        ${renderPlanButton({
                            label: 'Gerar documento',
                            icon: 'description',
                            tone: 'neutral',
                            attrs: 'id="gerarDocumentoBtn"',
                            disabled: !canGenerateDocument
                        })}
                        ${renderPlanButton({
                            label: 'Concluir planejamento',
                            icon: 'check_circle',
                            tone: 'success',
                            attrs: 'id="concluirPlanejamentoBtn"',
                            disabled: !(directEditEnabled && planejamento.status !== 'Concluído' && (planejamento.quantidade_membros_ativos || 0) > 0)
                        })}
                    </div>
                </section>
            </div>
        `;
    }

    function renderMovementRow(item, index) {
        const visualState = getMovementVisualState(item);
        const selectedClass = String(state.selectedOsId) === String(item.id) ? ' is-selected' : '';
        const stateClass = visualState.state === 'finalizado' ? ' planejamento-movement-row--done' : '';
        const dataEmbarque = item.data_embarque ? formatDate(item.data_embarque) : '';
        const badges = [];
        if (visualState.label) {
            badges.push(`
                <span class="planejamento-badge ${visualState.badgeClass}">
                    <span class="material-icons" aria-hidden="true">${visualState.badgeIcon}</span>
                    ${escapeHtml(visualState.label)}
                </span>
            `);
        }
        if (visualState.readonly) {
            badges.push('<span class="planejamento-badge planejamento-badge--readonly">Somente leitura</span>');
        }
        const hasActionContent = badges.length > 0;
        return `
            <article class="planejamento-movement-row${stateClass}${selectedClass}" data-movement-open="${item.id}">
                <div class="planejamento-movement-row__index${visualState.state === 'finalizado' ? ' is-done' : ''}">
                    ${visualState.state === 'finalizado'
                        ? '<span class="material-icons" aria-hidden="true">check</span>'
                        : String(index + 1)}
                </div>
                <div class="planejamento-movement-row__grid">
                    <div class="planejamento-data"><span>Supervisor</span><strong>${escapeHtml(item.supervisor_nome || '-')}</strong></div>
                    <div class="planejamento-data"><span>POB</span><strong>${escapeHtml(item.pob || '-')}</strong></div>
                    <div class="planejamento-data"><span>Data embarque</span><strong>${dataEmbarque ? escapeHtml(dataEmbarque) : '&nbsp;'}</strong></div>
                </div>
                <div class="planejamento-movement-row__actions${hasActionContent ? '' : ' is-empty'}">
                    ${badges.join('')}
                </div>
            </article>
        `;
    }

    function getMovementVisualState(item) {
        const rawStatusLinha = String(item.status_linha || item.status_operacao || '').trim();
        const linhaFinalizada = Boolean(item.home_finalizada) || isOperacaoFinalizada(rawStatusLinha);
        const statusLabel = rawStatusLinha || 'Em andamento';

        if (linhaFinalizada) {
            return {
                state: 'finalizado',
                label: statusLabel,
                readonly: true,
                badgeClass: 'planejamento-badge--concluido',
                badgeIcon: 'check_circle'
            };
        }

        return {
            state: 'ativo',
            label: statusLabel,
            readonly: !item.permite_edicao,
            badgeClass: 'planejamento-badge--operacao',
            badgeIcon: 'radio_button_unchecked'
        };
    }

    function buildGroupPanel(group) {
        const selectedItem = group.movimentacoes.find((item) => String(item.id) === String(state.selectedOsId)) || null;
        const selectedDetailMatches = selectedItem && state.detail && state.detail.os && String(state.detail.os.id) === String(selectedItem.id);
        const allMovementsDone = group.movimentacoes.length > 0
            && group.movimentacoes.every((item) => getMovementVisualState(item).state === 'finalizado');
        const movementStack = `
            <div class="planejamento-detail-stack">
                <section class="planejamento-detail-block">
                    <div class="planejamento-section__title">
                        <div>
                            <p class="planejamento-section__eyebrow">Movimenta\u00e7\u00f5es da OS</p>
                            <h4>Movimenta\u00e7\u00f5es da OS</h4>
                        </div>
                    </div>
                    <div class="planejamento-movements-list">
                        ${group.movimentacoes.map((item, index) => renderMovementRow(item, index)).join('')}
                    </div>
                </section>
            </div>
        `;

        if (!selectedItem) {
            return `
                ${movementStack}
                <div class="planejamento-detail-stack">
                    <section class="planejamento-detail-block">
                        <div class="planejamento-group-selection-empty">
                            <span class="material-icons" aria-hidden="true">playlist_add_check</span>
                            <div>
                                <h4>${allMovementsDone ? 'Movimenta\u00e7\u00f5es conclu\u00eddas' : 'Selecione uma movimenta\u00e7\u00e3o'}</h4>
                                <p>${allMovementsDone
                                    ? 'Todas as movimenta\u00e7\u00f5es desta OS j\u00e1 possuem status conclu\u00eddo. Clique em uma movimenta\u00e7\u00e3o para visualizar os detalhes do planejamento.'
                                    : 'Escolha uma movimenta\u00e7\u00e3o acima para ver ou editar o planejamento desta linha da OS.'}</p>
                            </div>
                        </div>
                    </section>
                </div>
            `;
        }

        const detailHtml = selectedDetailMatches
            ? (state.detail.planejamento ? buildPlanningBody(state.detail.os, state.detail.planejamento) : buildNoPlanningBody(state.detail.os))
            : `
                <div class="planejamento-detail-stack">
                    <section class="planejamento-detail-block">
                        <div class="planejamento-group-selection-empty">
                            <span class="material-icons" aria-hidden="true">hourglass_top</span>
                            <div>
                                <h4>Carregando movimenta\u00e7\u00e3o</h4>
                                <p>Buscando os dados do planejamento selecionado.</p>
                            </div>
                        </div>
                    </section>
                </div>
            `;

        return `
            ${movementStack}
            <section class="planejamento-group-editor-title">
                <p class="planejamento-section__eyebrow">Planejamento da movimenta\u00e7\u00e3o selecionada</p>
                <h4>Planejamento da movimenta\u00e7\u00e3o selecionada</h4>
            </section>
            ${detailHtml}
        `;
    }

    function renderPanel() {
        if (!state.selectedGroupNumeroOs) {
            renderEmptyDetail();
            return;
        }

        const group = findGroup(state.selectedGroupNumeroOs, { includeAllMovements: true });
        const visibleGroup = findGroup(state.selectedGroupNumeroOs);
        if (!group || !visibleGroup) {
            renderEmptyDetail();
            return;
        }

        if (group.movimentacoes.length === 1) {
            const item = group.movimentacoes[0];
            const osItem = state.detail && state.detail.os && String(state.detail.os.id) === String(item.id) ? state.detail.os : item;
            const planejamento = state.detail && state.detail.os && String(state.detail.os.id) === String(item.id) ? state.detail.planejamento : null;
            renderSingleHeader(osItem, planejamento);
            refs.panelBody.innerHTML = planejamento ? buildPlanningBody(osItem, planejamento) : buildNoPlanningBody(osItem);
            bindDetailEvents();
            return;
        }

        renderGroupHeader(group);
        refs.panelBody.innerHTML = buildGroupPanel(group);
        bindDetailEvents();
    }

    async function loadOsDetail(osId) {
        refs.panelBody.innerHTML = '<div class="planejamento-empty"><p>Carregando planejamento...</p></div>';
        try {
            state.detail = await apiRequest(endpoint(app.dataset.osDetailUrlTemplate, { '__OS_ID__': osId }));
            state.selectedOsId = osId;
            state.selectedGroupNumeroOs = state.detail.os ? state.detail.os.numero_os : state.selectedGroupNumeroOs;
            state.memberTab = 'ativos';
            renderCards();
            renderPanel();
        } catch (error) {
            refs.panelBody.innerHTML = `<div class="planejamento-empty"><p>${escapeHtml(error.message)}</p></div>`;
            showAlert(error.message, 'error');
        }
    }

    async function openSingleCard(item) {
        state.selectedGroupNumeroOs = item.numero_os;
        state.selectedOsId = item.id;
        renderCards();
        openMobileDetailPane();
        refs.panelTitle.textContent = 'Carregando...';
        refs.panelSubtitle.textContent = '';
        refs.panelHeaderBadge.innerHTML = '';
        await loadOsDetail(item.id);
    }

    function openGroupCard(numeroOs) {
        state.selectedGroupNumeroOs = numeroOs;
        if (!findGroup(numeroOs, { includeAllMovements: true })?.movimentacoes.some((item) => String(item.id) === String(state.selectedOsId))) {
            state.selectedOsId = null;
            state.detail = null;
        }
        renderCards();
        openMobileDetailPane();
        renderPanel();
    }

    async function startPlanning(osId) {
        try {
            const data = await apiRequest(endpoint(app.dataset.openPlanejamentoUrlTemplate, { '__OS_ID__': osId }), { method: 'POST' });
            state.selectedGroupNumeroOs = data.os ? data.os.numero_os : state.selectedGroupNumeroOs;
            state.selectedOsId = osId;
            state.memberTab = 'ativos';
            syncDetailFromResponse({ os: data.os, planejamento: data.planejamento });
            openMobileDetailPane();
            showAlert(data.created ? 'Planejamento iniciado com sucesso.' : 'Planejamento carregado.', 'success');
        } catch (error) {
            showAlert(error.message, 'error');
        }
    }

    function filterPessoas(query) {
        const value = normalize(query);
        if (!value) {
            return pessoas.slice(0, 20);
        }
        return pessoas
            .filter((pessoa) => {
                const nome = normalize(pessoa.nome);
                const funcao = normalize(pessoa.funcao);
                return nome.includes(value) || funcao.includes(value);
            })
            .slice(0, 20);
    }

    function closePersonCombobox(combobox) {
        if (!combobox) {
            return;
        }
        const menu = combobox.querySelector('.planejamento-combobox__menu');
        const input = combobox.querySelector('[data-person-field="true"]');
        if (menu) {
            menu.hidden = true;
            menu.innerHTML = '';
        }
        combobox.classList.remove('is-open');
        if (input) {
            input.setAttribute('aria-expanded', 'false');
        }
        delete combobox.dataset.activeIndex;
    }

    function closeAllPersonComboboxes(exceptCombobox) {
        document.querySelectorAll('.planejamento-combobox[data-person-combobox]').forEach((combobox) => {
            if (combobox !== exceptCombobox) {
                closePersonCombobox(combobox);
            }
        });
    }

    function getPersonComboboxOptions(combobox) {
        return Array.from(combobox.querySelectorAll('.planejamento-combobox__option'));
    }

    function setActivePersonOption(combobox, index) {
        const options = getPersonComboboxOptions(combobox);
        if (!options.length) {
            combobox.dataset.activeIndex = '-1';
            return;
        }
        const safeIndex = Math.max(0, Math.min(index, options.length - 1));
        options.forEach((option, optionIndex) => {
            option.classList.toggle('is-active', optionIndex === safeIndex);
            option.setAttribute('aria-selected', optionIndex === safeIndex ? 'true' : 'false');
        });
        combobox.dataset.activeIndex = String(safeIndex);
    }

    function renderPersonOptions(combobox, query) {
        const menu = combobox.querySelector('.planejamento-combobox__menu');
        const hidden = combobox.querySelector('input[name="pessoa_id"]');
        const selectedId = String(hidden ? hidden.value : '');
        const results = filterPessoas(query);

        if (!menu) {
            return;
        }

        if (!results.length) {
            menu.innerHTML = '<div class="planejamento-combobox__empty">Nenhuma pessoa encontrada.</div>';
            menu.hidden = false;
            combobox.classList.add('is-open');
            const input = combobox.querySelector('[data-person-field="true"]');
            if (input) {
                input.setAttribute('aria-expanded', 'true');
            }
            combobox.dataset.activeIndex = '-1';
            return;
        }

        menu.innerHTML = results.map((pessoa, index) => {
            const isSelected = selectedId && String(pessoa.id) === selectedId;
            return `
                <button
                    type="button"
                    class="planejamento-combobox__option${isSelected || (!selectedId && index === 0) ? ' is-active' : ''}"
                    role="option"
                    aria-selected="${isSelected ? 'true' : 'false'}"
                    data-person-id="${escapeHtml(pessoa.id)}"
                    data-person-name="${escapeHtml(pessoa.nome || '')}"
                    data-person-funcao="${escapeHtml(pessoa.funcao || '')}"
                >
                    <strong>${escapeHtml(pessoa.nome || '-')}</strong>
                </button>
            `;
        }).join('');

        menu.hidden = false;
        combobox.classList.add('is-open');
        const input = combobox.querySelector('[data-person-field="true"]');
        if (input) {
            input.setAttribute('aria-expanded', 'true');
        }
        const initialIndex = Math.max(0, results.findIndex((pessoa) => selectedId && String(pessoa.id) === selectedId));
        setActivePersonOption(combobox, initialIndex);
    }

    function selectPessoaOption(combobox, option) {
        const input = combobox.querySelector('[data-person-field="true"]');
        const hidden = combobox.querySelector('input[name="pessoa_id"]');
        const id = option.dataset.personId || '';
        const name = option.dataset.personName || '';

        if (input) {
            input.value = name;
            input.dataset.selectedPersonId = id;
        }
        if (hidden) {
            hidden.value = id;
        }

        closePersonCombobox(combobox);
    }

    function initPersonComboboxes(scope) {
        scope.querySelectorAll('[data-person-combobox]').forEach((combobox) => {
            if (combobox.dataset.bound === 'true') {
                return;
            }

            const input = combobox.querySelector('[data-person-field="true"]');
            const toggle = combobox.querySelector('.planejamento-combobox__toggle');
            const hidden = combobox.querySelector('input[name="pessoa_id"]');

            if (!input || !hidden) {
                return;
            }

            const initialPerson = getPessoaInicial(hidden.value, input.value);
            if (initialPerson) {
                hidden.value = initialPerson.id;
                input.value = initialPerson.nome || '';
                input.dataset.selectedPersonId = String(initialPerson.id);
            }

            input.addEventListener('focus', function () {
                if (input.disabled) {
                    return;
                }
                closeAllPersonComboboxes(combobox);
                renderPersonOptions(combobox, input.value);
            });

            input.addEventListener('input', function () {
                hidden.value = '';
                input.dataset.selectedPersonId = '';
                closeAllPersonComboboxes(combobox);
                renderPersonOptions(combobox, input.value);
            });

            input.addEventListener('keydown', function (event) {
                if (input.disabled) {
                    return;
                }
                const menu = combobox.querySelector('.planejamento-combobox__menu');
                const isOpen = menu && !menu.hidden;

                if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    if (!isOpen) {
                        renderPersonOptions(combobox, input.value);
                        return;
                    }
                    const activeIndex = Number(combobox.dataset.activeIndex || 0);
                    setActivePersonOption(combobox, activeIndex + 1);
                    return;
                }

                if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    if (!isOpen) {
                        renderPersonOptions(combobox, input.value);
                        return;
                    }
                    const activeIndex = Number(combobox.dataset.activeIndex || 0);
                    setActivePersonOption(combobox, activeIndex - 1);
                    return;
                }

                if (event.key === 'Enter' && isOpen) {
                    const activeIndex = Number(combobox.dataset.activeIndex || -1);
                    const options = getPersonComboboxOptions(combobox);
                    if (activeIndex >= 0 && options[activeIndex]) {
                        event.preventDefault();
                        selectPessoaOption(combobox, options[activeIndex]);
                    }
                    return;
                }

                if (event.key === 'Escape') {
                    closePersonCombobox(combobox);
                }
            });

            if (toggle) {
                toggle.addEventListener('click', function () {
                    if (input.disabled) {
                        return;
                    }
                    const menu = combobox.querySelector('.planejamento-combobox__menu');
                    if (menu && !menu.hidden) {
                        closePersonCombobox(combobox);
                        return;
                    }
                    closeAllPersonComboboxes(combobox);
                    renderPersonOptions(combobox, input.value);
                    input.focus();
                });
            }

            combobox.addEventListener('click', function (event) {
                const option = event.target.closest('.planejamento-combobox__option');
                if (!option) {
                    return;
                }
                selectPessoaOption(combobox, option);
            });

            combobox.dataset.bound = 'true';
        });
    }

    function buildMemberFormData(form) {
        const data = new FormData(form);
        const pessoaId = String(data.get('pessoa_id') || '').trim();

        if (!pessoaId) {
            throw new Error('Selecione uma pessoa cadastrada na lista de nomes.');
        }

        const pessoa = pessoasById.get(pessoaId);
        if (!pessoa) {
            throw new Error('Pessoa selecionada não encontrada. Selecione novamente.');
        }

        data.set('pessoa_id', pessoa.id);
        data.set('nome_snapshot', pessoa.nome || '');

        if (!String(data.get('funcao_planejada') || '').trim()) {
            throw new Error('Selecione uma função válida.');
        }
        return data;
    }

    function collectHeaderDraft(form) {
        if (!form) {
            return null;
        }
        return {
            titulo_planejamento: String(form.titulo_planejamento ? form.titulo_planejamento.value : ''),
            data_prevista_subida: String(form.data_prevista_subida ? form.data_prevista_subida.value : ''),
            horario_previsto_subida: String(form.horario_previsto_subida ? form.horario_previsto_subida.value : '').trim(),
            local_subida: String(form.local_subida ? form.local_subida.value : ''),
            observacao: String(form.observacao ? form.observacao.value : ''),
            data_prevista_desembarque: String(form.data_prevista_desembarque ? form.data_prevista_desembarque.value : ''),
            horario_previsto_desembarque: String(form.horario_previsto_desembarque ? form.horario_previsto_desembarque.value : '').trim(),
            local_desembarque: String(form.local_desembarque ? form.local_desembarque.value : ''),
            observacao_desembarque: String(form.observacao_desembarque ? form.observacao_desembarque.value : '')
        };
    }

    function isSameHeaderDraft(planejamento, draft) {
        if (!planejamento || !draft) {
            return true;
        }
        return String(planejamento.titulo_planejamento || '') === String(draft.titulo_planejamento || '')
            && String(planejamento.data_prevista_subida || '') === String(draft.data_prevista_subida || '')
            && String(planejamento.horario_previsto_subida || '') === String(draft.horario_previsto_subida || '')
            && String(planejamento.local_subida || '') === String(draft.local_subida || '')
            && String(planejamento.observacao || '') === String(draft.observacao || '')
            && String(planejamento.data_prevista_desembarque || '') === String(draft.data_prevista_desembarque || '')
            && String(planejamento.horario_previsto_desembarque || '') === String(draft.horario_previsto_desembarque || '')
            && String(planejamento.local_desembarque || '') === String(draft.local_desembarque || '')
            && String(planejamento.observacao_desembarque || '') === String(draft.observacao_desembarque || '');
    }

    async function persistHeaderDraftIfNeeded(options) {
        const planejamento = currentPlanning();
        const form = document.getElementById('planejamentoCabecalhoForm');
        if (!planejamento || !form || !planejamento.permite_edicao) {
            return null;
        }
        const config = options || {};

        const draft = collectHeaderDraft(form);
        if (!draft || isSameHeaderDraft(planejamento, draft)) {
            return null;
        }

        if (draft.horario_previsto_subida && !/^([01]\d|2[0-3]):[0-5]\d$/.test(draft.horario_previsto_subida)) {
            throw new Error('Informe um horário válido no formato HH:MM.');
        }
        if (draft.horario_previsto_desembarque && !/^([01]\d|2[0-3]):[0-5]\d$/.test(draft.horario_previsto_desembarque)) {
            throw new Error('Informe um horário de desembarque válido no formato HH:MM.');
        }

        if (config.justificativa) {
            draft.justificativa = config.justificativa;
        }

        const data = await apiRequest(endpoint(app.dataset.planejamentoCabecalhoUrlTemplate, { '__PLANEJAMENTO_ID__': planejamento.id }), {
            method: 'POST',
            jsonBody: draft
        });
        syncDetailFromResponse(data);
        return data;
    }

    async function saveHeader(form) {
        const planejamento = currentPlanning();
        if (!planejamento) {
            return;
        }
        const horario = String(form.horario_previsto_subida.value || '').trim();
        const horarioDesembarque = String(form.horario_previsto_desembarque.value || '').trim();
        if (horario && !/^([01]\d|2[0-3]):[0-5]\d$/.test(horario)) {
            throw new Error('Informe um horário válido no formato HH:MM.');
        }
        if (horarioDesembarque && !/^([01]\d|2[0-3]):[0-5]\d$/.test(horarioDesembarque)) {
            throw new Error('Informe um horário de desembarque válido no formato HH:MM.');
        }
        const payload = {
            titulo_planejamento: form.titulo_planejamento.value,
            data_prevista_subida: form.data_prevista_subida.value,
            horario_previsto_subida: horario,
            local_subida: form.local_subida.value,
            observacao: form.observacao.value,
            data_prevista_desembarque: form.data_prevista_desembarque.value,
            horario_previsto_desembarque: horarioDesembarque,
            local_desembarque: form.local_desembarque.value,
            observacao_desembarque: form.observacao_desembarque.value
        };
        if (currentPlanningRequiresJustification()) {
            const justificativa = await requestPlanningJustification('salvar os dados de embarque e desembarque');
            if (!justificativa) {
                return;
            }
            payload.justificativa = justificativa;
        }
        const data = await apiRequest(endpoint(app.dataset.planejamentoCabecalhoUrlTemplate, { '__PLANEJAMENTO_ID__': planejamento.id }), {
            method: 'POST',
            jsonBody: payload
        });
        syncDetailFromResponse(data);
        showAlert('Informações de embarque e desembarque salvas.', 'success');
    }

    async function addMember(form) {
        const planejamento = currentPlanning();
        if (!planejamento) {
            return;
        }
        let justificativa = '';
        if (currentPlanningRequiresJustification()) {
            justificativa = await requestPlanningJustification('adicionar um novo membro');
            if (!justificativa) {
                return;
            }
        }
        await persistHeaderDraftIfNeeded({ justificativa });
        const formData = buildMemberFormData(form);
        if (justificativa) {
            formData.set('justificativa', justificativa);
        }
        const data = await apiRequest(endpoint(app.dataset.planejamentoAddMembroUrlTemplate, { '__PLANEJAMENTO_ID__': planejamento.id }), {
            method: 'POST',
            formData
        });
        state.memberTab = 'ativos';
        syncDetailFromResponse(data);
        showAlert('Membro adicionado com sucesso.', 'success');
    }

    async function concludePlanning() {
        const planejamento = currentPlanning();
        if (!planejamento) {
            return;
        }
        await persistHeaderDraftIfNeeded();
        const data = await apiRequest(endpoint(app.dataset.planejamentoConcluirUrlTemplate, { '__PLANEJAMENTO_ID__': planejamento.id }), {
            method: 'POST'
        });
        syncDetailFromResponse(data);
        showAlert('Planejamento concluído.', 'success');
    }

    function findMember(memberId) {
        const planejamento = currentPlanning();
        if (!planejamento) {
            return null;
        }
        return []
            .concat(planejamento.membros_ativos || [])
            .concat(planejamento.membros_substituidos || [])
            .concat(planejamento.membros_cancelados || [])
            .find((member) => String(member.id) === String(memberId)) || null;
    }

    function openEditMemberModal(member) {
        const requiresJustification = currentPlanningRequiresJustification();
        openModal(
            `Editar membro: ${member.nome_snapshot}`,
            `
                <form>
                    <div class="planejamento-form-grid">
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Nome</label>
                            ${renderPersonCombobox({
                                inputId: 'editNome',
                                personId: member.pessoa_id,
                                personName: member.nome_snapshot || '',
                                targetFuncao: '#editFuncao',
                                placeholder: 'Pesquisar pessoa',
                                required: true
                            })}
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Função</label>
                            <select id="editFuncao" class="planejamento-select" name="funcao_planejada" required>
                                ${functionOptions(member.funcao_planejada || '')}
                            </select>
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Data início</label>
                            <input type="date" class="planejamento-input" name="data_inicio" value="${escapeHtml(member.data_inicio || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Ordem</label>
                            <input type="number" class="planejamento-input" name="ordem" min="0" value="${escapeHtml(member.ordem || 0)}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label>Observação</label>
                            <textarea class="planejamento-textarea" name="observacao">${escapeHtml(member.observacao || '')}</textarea>
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label class="planejamento-field__group-title">Desembarque individual</label>
                        </div>
                        <div class="planejamento-field planejamento-field--span-3">
                            <label>Data desembarque</label>
                            <input type="date" class="planejamento-input" name="data_desembarque" value="${escapeHtml(member.data_desembarque || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-3">
                            <label>Horário desembarque</label>
                            <input type="time" step="60" class="planejamento-input" name="horario_desembarque" value="${escapeHtml(member.horario_desembarque || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Local desembarque</label>
                            <input class="planejamento-input" name="local_desembarque_membro" value="${escapeHtml(member.local_desembarque_membro || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label>Observação desembarque</label>
                            <textarea class="planejamento-textarea" name="observacao_desembarque">${escapeHtml(member.observacao_desembarque || '')}</textarea>
                        </div>
                        ${requiresJustification ? buildJustificationField('editJustificativa') : ''}
                    </div>
                    <div class="planejamento-action-row">
                        ${renderPlanButton({
                            label: 'Salvar membro',
                            icon: 'done',
                            tone: 'success',
                            type: 'submit'
                        })}
                    </div>
                </form>
            `,
            async function (form) {
                const formData = buildMemberFormData(form);
                const justificativa = String(formData.get('justificativa') || '').trim();
                await persistHeaderDraftIfNeeded({ justificativa });
                if (justificativa) {
                    formData.set('justificativa', justificativa);
                }
                const data = await apiRequest(endpoint(app.dataset.membroUpdateUrlTemplate, { '__MEMBRO_ID__': member.id }), {
                    method: 'POST',
                    formData
                });
                closeModal('submit');
                syncDetailFromResponse(data);
                showAlert('Membro atualizado.', 'success');
            }
        );
    }

    function openReplaceMemberModal(member) {
        const requiresJustification = currentPlanningRequiresJustification();
        openModal(
            `Substituir membro: ${member.nome_snapshot}`,
            `
                <form>
                    <div class="planejamento-form-grid">
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Novo nome</label>
                            ${renderPersonCombobox({
                                inputId: 'replaceNome',
                                targetFuncao: '#replaceFuncao',
                                placeholder: 'Pesquisar pessoa',
                                required: true
                            })}
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Nova função</label>
                            <select id="replaceFuncao" class="planejamento-select" name="funcao_planejada" required>
                                ${functionOptions('')}
                            </select>
                        </div>
                        <div class="planejamento-field planejamento-field--span-4">
                            <label>Data início do novo</label>
                            <input type="date" class="planejamento-input" name="data_inicio">
                        </div>
                        <div class="planejamento-field planejamento-field--span-4">
                            <label>Data fim do antigo</label>
                            <input type="date" class="planejamento-input" name="data_fim">
                        </div>
                        <div class="planejamento-field planejamento-field--span-4">
                            <label>Observação</label>
                            <input class="planejamento-input" name="observacao">
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label>Motivo da substituição</label>
                            <textarea class="planejamento-textarea" name="motivo_substituicao"></textarea>
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label class="planejamento-field__group-title">Desembarque do membro substituído</label>
                        </div>
                        <div class="planejamento-field planejamento-field--span-3">
                            <label>Data desembarque do antigo</label>
                            <input type="date" class="planejamento-input" name="data_desembarque_antigo" value="${escapeHtml(member.data_desembarque || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-3">
                            <label>Horário desembarque do antigo</label>
                            <input type="time" step="60" class="planejamento-input" name="horario_desembarque_antigo" value="${escapeHtml(member.horario_desembarque || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Local desembarque do antigo</label>
                            <input class="planejamento-input" name="local_desembarque_membro_antigo" value="${escapeHtml(member.local_desembarque_membro || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label>Observação desembarque do antigo</label>
                            <textarea class="planejamento-textarea" name="observacao_desembarque_antigo">${escapeHtml(member.observacao_desembarque || '')}</textarea>
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label class="planejamento-field__group-title">Desembarque individual do novo membro</label>
                        </div>
                        <div class="planejamento-field planejamento-field--span-3">
                            <label>Data desembarque do novo</label>
                            <input type="date" class="planejamento-input" name="data_desembarque">
                        </div>
                        <div class="planejamento-field planejamento-field--span-3">
                            <label>Horário desembarque do novo</label>
                            <input type="time" step="60" class="planejamento-input" name="horario_desembarque">
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Local desembarque do novo</label>
                            <input class="planejamento-input" name="local_desembarque_membro">
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label>Observação desembarque do novo</label>
                            <textarea class="planejamento-textarea" name="observacao_desembarque"></textarea>
                        </div>
                        ${requiresJustification ? buildJustificationField('replaceJustificativa') : ''}
                    </div>
                    <div class="planejamento-action-row">
                        ${renderPlanButton({
                            label: 'Confirmar substituição',
                            icon: 'swap_horiz',
                            tone: 'success',
                            type: 'submit'
                        })}
                    </div>
                </form>
            `,
            async function (form) {
                const formData = buildMemberFormData(form);
                const justificativa = String(formData.get('justificativa') || '').trim();
                await persistHeaderDraftIfNeeded({ justificativa });
                if (justificativa) {
                    formData.set('justificativa', justificativa);
                }
                const data = await apiRequest(endpoint(app.dataset.membroSubstituirUrlTemplate, { '__MEMBRO_ID__': member.id }), {
                    method: 'POST',
                    formData
                });
                closeModal('submit');
                state.memberTab = 'ativos';
                syncDetailFromResponse(data);
                showAlert('Substituição registrada.', 'success');
            }
        );
    }

    function openCancelMemberModal(member) {
        const requiresJustification = currentPlanningRequiresJustification();
        openModal(
            `Cancelar membro: ${member.nome_snapshot}`,
            `
                <form>
                    <div class="planejamento-form-grid">
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Data fim</label>
                            <input type="date" class="planejamento-input" name="data_fim">
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Observação</label>
                            <input class="planejamento-input" name="observacao">
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label>Motivo</label>
                            <textarea class="planejamento-textarea" name="motivo_substituicao"></textarea>
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label class="planejamento-field__group-title">Desembarque do membro</label>
                        </div>
                        <div class="planejamento-field planejamento-field--span-3">
                            <label>Data desembarque</label>
                            <input type="date" class="planejamento-input" name="data_desembarque" value="${escapeHtml(member.data_desembarque || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-3">
                            <label>Horário desembarque</label>
                            <input type="time" step="60" class="planejamento-input" name="horario_desembarque" value="${escapeHtml(member.horario_desembarque || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-6">
                            <label>Local desembarque</label>
                            <input class="planejamento-input" name="local_desembarque_membro" value="${escapeHtml(member.local_desembarque_membro || '')}">
                        </div>
                        <div class="planejamento-field planejamento-field--span-12">
                            <label>Observação desembarque</label>
                            <textarea class="planejamento-textarea" name="observacao_desembarque">${escapeHtml(member.observacao_desembarque || '')}</textarea>
                        </div>
                        ${requiresJustification ? buildJustificationField('cancelJustificativa') : ''}
                    </div>
                    <div class="planejamento-action-row">
                        ${renderPlanButton({
                            label: 'Confirmar cancelamento',
                            icon: 'close',
                            tone: 'danger',
                            type: 'submit'
                        })}
                    </div>
                </form>
            `,
            async function (form) {
                const formData = new FormData(form);
                const justificativa = String(formData.get('justificativa') || '').trim();
                await persistHeaderDraftIfNeeded({ justificativa });
                if (justificativa) {
                    formData.set('justificativa', justificativa);
                }
                const data = await apiRequest(endpoint(app.dataset.membroCancelarUrlTemplate, { '__MEMBRO_ID__': member.id }), {
                    method: 'POST',
                    formData
                });
                closeModal('submit');
                state.memberTab = 'cancelados';
                syncDetailFromResponse(data);
                showAlert('Membro cancelado.', 'success');
            }
        );
    }

    function handleMemberAction(memberId, action) {
        const member = findMember(memberId);
        if (!member) {
            showAlert('Membro não encontrado.', 'error');
            return;
        }
        if (action === 'edit') {
            openEditMemberModal(member);
            return;
        }
        if (action === 'replace') {
            openReplaceMemberModal(member);
            return;
        }
        if (action === 'cancel') {
            openCancelMemberModal(member);
        }
    }

    function bindDetailEvents() {
        const startButton = document.getElementById('iniciarPlanejamentoBtn');
        if (startButton && state.detail && state.detail.os) {
            startButton.addEventListener('click', function () {
                startPlanning(state.detail.os.id);
            });
        }

        const headerForm = document.getElementById('planejamentoCabecalhoForm');
        if (headerForm) {
            headerForm.addEventListener('submit', function (event) {
                event.preventDefault();
                saveHeader(headerForm).catch((error) => showAlert(error.message, 'error'));
            });
        }

        const editPlanningButton = document.getElementById('editarPlanejamentoBtn');
        if (editPlanningButton) {
            editPlanningButton.addEventListener('click', function () {
                openConcludedPlanningActionSelector('', '');
            });
        }

        const addForm = document.getElementById('planejamentoAddMembroForm');
        if (addForm) {
            initPersonComboboxes(addForm);
            addForm.addEventListener('submit', function (event) {
                event.preventDefault();
                addMember(addForm).catch((error) => showAlert(error.message, 'error'));
            });
        }

        const concludeButton = document.getElementById('concluirPlanejamentoBtn');
        if (concludeButton) {
            concludeButton.addEventListener('click', function () {
                concludePlanning().catch((error) => showAlert(error.message, 'error'));
            });
        }

        const documentButton = document.getElementById('gerarDocumentoBtn');
        if (documentButton) {
            documentButton.addEventListener('click', function () {
                const planejamento = currentPlanning();
                if (!planejamento || !planejamento.id) {
                    return;
                }
                window.open(
                    endpoint(app.dataset.planejamentoDocumentoUrlTemplate, { '__PLANEJAMENTO_ID__': planejamento.id }),
                    '_blank',
                    'noopener'
                );
            });
        }

        refs.panelBody.querySelectorAll('[data-member-tab]').forEach((button) => {
            button.addEventListener('click', function () {
                state.memberTab = this.dataset.memberTab;
                renderPanel();
            });
        });

        refs.panelBody.querySelectorAll('[data-member-action]').forEach((button) => {
            button.addEventListener('click', function () {
                handleMemberAction(this.dataset.memberId, this.dataset.memberAction);
            });
        });

        refs.panelBody.querySelectorAll('[data-movement-open]').forEach((row) => {
            row.addEventListener('click', function (event) {
                if (event.target.closest('[data-movement-action]')) {
                    return;
                }
                loadOsDetail(this.dataset.movementOpen);
            });
        });

        refs.panelBody.querySelectorAll('[data-movement-action]').forEach((button) => {
            button.addEventListener('click', function () {
                const action = this.dataset.movementAction;
                const osId = this.dataset.osId;
                if (action === 'start') {
                    startPlanning(osId);
                    return;
                }
                loadOsDetail(osId);
            });
        });
    }

    refs.cards.addEventListener('click', function (event) {
        const actionButton = event.target.closest('[data-card-action]');
        if (actionButton) {
            event.stopPropagation();
            const osId = actionButton.dataset.osId;
            const item = state.allItems.find((entry) => String(entry.id) === String(osId));
            if (item) {
                state.selectedGroupNumeroOs = item.numero_os;
                state.selectedOsId = item.id;
                renderCards();
                openMobileDetailPane();
            }
            if (actionButton.dataset.cardAction === 'start') {
                startPlanning(osId);
            } else {
                loadOsDetail(osId);
            }
            return;
        }

        const groupAction = event.target.closest('[data-card-group-open]');
        if (groupAction) {
            event.stopPropagation();
            openGroupCard(groupAction.dataset.cardGroupOpen);
            return;
        }

        const groupCard = event.target.closest('[data-card-group]');
        if (groupCard) {
            openGroupCard(groupCard.dataset.cardGroup);
            return;
        }

        const card = event.target.closest('[data-card-open]');
        if (!card) {
            return;
        }
        const item = state.allItems.find((entry) => String(entry.id) === String(card.dataset.cardOpen));
        if (item) {
            openSingleCard(item);
        }
    });

    refs.search.addEventListener('input', function () {
        window.clearTimeout(state.searchTimer);
        state.searchTimer = window.setTimeout(() => {
            state.filters.q = refs.search.value.trim();
            state.currentPage = 1;
            renderActiveFiltersSummary();
            renderCards();
            renderPanel();
        }, 220);
    });

    refs.sort.addEventListener('change', function () {
        state.sort = refs.sort.value;
        state.currentPage = 1;
        renderCards();
        renderPanel();
    });

    refs.statusFilter?.addEventListener('change', function () {
        state.filters.status = this.value;
        state.currentPage = 1;
        renderActiveFiltersSummary();
        renderCards();
        renderPanel();
    });

    refs.clienteFilter?.addEventListener('change', function () {
        state.filters.cliente = this.value;
        state.currentPage = 1;
        renderActiveFiltersSummary();
        renderCards();
        renderPanel();
    });

    refs.unidadeFilter?.addEventListener('change', function () {
        state.filters.unidade = this.value;
        state.currentPage = 1;
        renderActiveFiltersSummary();
        renderCards();
        renderPanel();
    });

    refs.coordenadorFilter?.addEventListener('change', function () {
        state.filters.coordenador = this.value;
        state.currentPage = 1;
        renderActiveFiltersSummary();
        renderCards();
        renderPanel();
    });

    refs.toggleFilters?.addEventListener('click', function () {
        state.advancedFiltersOpen = !state.advancedFiltersOpen;
        syncAdvancedFiltersState();
    });

    refs.clearFilters?.addEventListener('click', function () {
        clearAllFilters();
    });

    refs.prevPage.addEventListener('click', function () {
        if (state.currentPage > 1) {
            state.currentPage -= 1;
            renderCards();
        }
    });

    refs.nextPage.addEventListener('click', function () {
        const totalPages = Math.max(1, Math.ceil(getVisualListItems().length / state.pageSize));
        if (state.currentPage < totalPages) {
            state.currentPage += 1;
            renderCards();
        }
    });

    refs.panelClose.addEventListener('click', clearSelectedDetail);
    refs.panelBackdrop.addEventListener('click', closeMobileDetailPane);
    refs.modalClose.addEventListener('click', function () { closeModal('cancel'); });
    refs.modalBackdrop.addEventListener('click', function () { closeModal('cancel'); });

    document.addEventListener('click', function (event) {
        document.querySelectorAll('.planejamento-combobox[data-person-combobox]').forEach((combobox) => {
            if (!combobox.contains(event.target)) {
                closePersonCombobox(combobox);
            }
        });
    });

    window.addEventListener('resize', function () {
        const newPageSize = getPageSize();
        if (newPageSize !== state.pageSize) {
            state.pageSize = newPageSize;
            state.currentPage = 1;
            renderCards();
        }
        if (!isMobile()) {
            closeMobileDetailPane();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            const openCombobox = document.querySelector('.planejamento-combobox.is-open');
            if (openCombobox) {
                closePersonCombobox(openCombobox);
                return;
            }
            if (!refs.modal.hidden) {
                closeModal('cancel');
                return;
            }
            if (state.selectedGroupNumeroOs || state.selectedOsId) {
                clearSelectedDetail();
            } else {
                closeMobileDetailPane();
            }
        }
    });

    renderEmptyDetail();
    syncAdvancedFiltersState();
    loadCards();
})();
