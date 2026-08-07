(function () {
    "use strict";

    const center = document.getElementById("ai-notification-center");
    const overlay = document.getElementById("ai-notification-overlay");
    const openButton = document.getElementById("ai-notification-center-open");
    if (!center || !overlay || !openButton) return;

    const closeButton = document.getElementById("ai-notification-center-close");
    const markAllButton = document.getElementById("ai-notification-mark-all");
    const searchInput = document.getElementById("ai-notification-search");
    const searchLoading = document.getElementById("ai-notification-search-loading");
    const prioritySelect = document.getElementById("ai-notification-priority");
    const typeSelect = document.getElementById("ai-notification-type");
    const list = document.getElementById("ai-notification-list");
    const details = document.getElementById("ai-notification-details");
    const listFooter = document.getElementById("ai-notification-list-footer");
    const range = document.getElementById("ai-notification-range");
    const loadMoreButton = document.getElementById("ai-notification-load-more");
    const subtitle = document.getElementById("ai-notification-center-subtitle");
    const toast = document.getElementById("ai-notification-toast");
    const tabs = Array.from(center.querySelectorAll("[data-ai-tab]"));
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const state = {
        open: false,
        tab: "pendentes",
        query: "",
        priority: "",
        alertType: "",
        page: 1,
        total: 0,
        hasMore: false,
        items: [],
        selectedKey: null,
        opener: null,
        requestId: 0,
        initialized: false,
        toastTimer: null,
        previousOverflow: ""
    };

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function csrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    async function request(url, options) {
        const response = await fetch(url, Object.assign({
            credentials: "same-origin",
            headers: { "Accept": "application/json" }
        }, options || {}));
        let payload;
        try { payload = await response.json(); } catch (_) { payload = {}; }
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || "Não foi possível concluir a solicitação.");
        }
        return payload;
    }

    function templateUrl(template, item, suffix) {
        let url = template.replace("SOURCE", encodeURIComponent(item.source));
        url = url.replace("999999999", String(item.id));
        return suffix ? url.replace(/\/$/, "") + suffix : url;
    }

    function listUrl(page) {
        const url = new URL(center.dataset.listUrl, window.location.origin);
        url.searchParams.set("tab", state.tab);
        url.searchParams.set("page", String(page));
        url.searchParams.set("page_size", "20");
        if (state.query) url.searchParams.set("q", state.query);
        if (state.priority) url.searchParams.set("prioridade", state.priority);
        if (state.alertType) url.searchParams.set("tipo", state.alertType);
        return url.toString();
    }

    function showToast(message, isError) {
        window.clearTimeout(state.toastTimer);
        toast.textContent = message;
        toast.classList.toggle("is-error", Boolean(isError));
        toast.hidden = false;
        state.toastTimer = window.setTimeout(function () { toast.hidden = true; }, 3500);
    }

    function setLoading(loading, append) {
        searchLoading.hidden = !loading;
        center.setAttribute("aria-busy", loading ? "true" : "false");
        if (loading && !append) {
            list.replaceChildren();
            for (let i = 0; i < 5; i += 1) {
                const skeleton = element("div", "ai-notification-center__skeleton");
                skeleton.append(element("span"), element("span"), element("span"));
                list.append(skeleton);
            }
        }
    }

    function updateCounts(payload) {
        const counts = payload.counts || {};
        center.querySelectorAll("[data-ai-count]").forEach(function (node) {
            const name = node.dataset.aiCount;
            const map = { all: "all", pending: "pending", read: "read" };
            node.textContent = String(counts[map[name]] || 0);
        });
        const unread = Number(payload.unread_count || 0);
        subtitle.textContent = unread + (unread === 1 ? " notificação pendente" : " notificações pendentes");
        markAllButton.disabled = unread === 0;
    }

    function updateBellBadge(unread) {
        const toggle = document.getElementById("synchro-alerts-toggle");
        if (!toggle) return;
        const compactSummary = document.querySelector("#synchro-alerts-dropdown .synchro-dropdown-heading div > span");
        if (compactSummary) {
            compactSummary.textContent = unread
                ? unread + (unread === 1 ? " pendente desde ontem" : " pendentes desde ontem")
                : "Nenhum alerta pendente desde ontem";
        }
        let badge = toggle.querySelector(".synchro-alert-count");
        if (!unread) {
            if (badge) badge.remove();
            return;
        }
        if (!badge) {
            badge = element("span", "synchro-alert-count");
            toggle.append(badge);
        }
        badge.textContent = unread > 99 ? "99+" : String(unread);
        badge.setAttribute("aria-label", unread + " alertas da IA não lidos");
    }

    function renderPriorityOptions(priorities) {
        if (!priorities || prioritySelect.options.length > 1) return;
        priorities.forEach(function (priority) {
            prioritySelect.append(new Option(priority.label, priority.value));
        });
    }

    function renderAlertTypeOptions(alertTypes) {
        if (!alertTypes || !typeSelect || typeSelect.options.length > 1) return;
        const groups = {};
        alertTypes.forEach(function (alertType) {
            const groupName = alertType.group || "Alertas";
            if (!groups[groupName]) {
                groups[groupName] = document.createElement("optgroup");
                groups[groupName].label = groupName;
                typeSelect.append(groups[groupName]);
            }
            groups[groupName].append(new Option(alertType.label, alertType.value));
        });
    }

    function emptyMessage() {
        if (state.query || state.priority || state.alertType) return ["Nenhum alerta encontrado com os filtros selecionados.", "Limpar filtros"];
        if (state.tab === "pendentes") return ["Você não possui notificações pendentes.", "Novos alertas da IA aparecerão aqui."];
        if (state.tab === "lidas") return ["Nenhuma notificação lida.", ""];
        return ["Nenhuma notificação disponível.", ""];
    }

    function renderEmpty() {
        const copy = emptyMessage();
        const empty = element("div", "ai-notification-center__empty");
        empty.append(element("span", "material-icons", "notifications_none"), element("strong", "", copy[0]));
        if (state.query || state.priority || state.alertType) {
            const clear = element("button", "", copy[1]);
            clear.type = "button";
            clear.addEventListener("click", function () {
                searchInput.value = "";
                state.query = "";
                prioritySelect.value = "";
                state.priority = "";
                typeSelect.value = "";
                state.alertType = "";
                loadPage(1, false);
            });
            empty.append(clear);
        } else if (copy[1]) {
            empty.append(element("p", "", copy[1]));
        }
        list.replaceChildren(empty);
        detailsEmpty("Selecione uma notificação para visualizar os detalhes.");
    }

    function priorityClass(value) {
        return "ai-notification-priority--" + String(value || "media").toLowerCase();
    }

    function createListItem(item) {
        const button = element("article", "ai-notification-center__item");
        button.tabIndex = 0;
        button.setAttribute("role", "button");
        button.dataset.key = item.key;
        button.setAttribute("aria-current", item.key === state.selectedKey ? "true" : "false");
        button.classList.toggle("ai-notification-center__item--unread", !item.is_read);
        button.classList.toggle("ai-notification-center__item--active", item.key === state.selectedKey);

        const top = element("div", "ai-notification-center__item-top");
        const titleWrap = element("div", "ai-notification-center__item-title");
        if (!item.is_read) titleWrap.append(element("span", "ai-notification-center__unread-dot"));
        titleWrap.append(element("strong", "", item.title));
        top.append(titleWrap, element("time", "", item.created_time));
        const client = item.client ? "Cliente: " + item.client : (item.unit ? "Unidade: " + item.unit : item.type_label);
        const summary = element("p", "ai-notification-center__item-summary", item.summary || item.message);
        const bottom = element("div", "ai-notification-center__item-bottom");
        bottom.append(element("span", "ai-notification-center__priority " + priorityClass(item.priority), item.priority_label));
        const readLabel = item.is_read ? "Marcar como não lido" : "Marcar como lido";
        const read = element("button", "ai-notification-center__read-action");
        read.type = "button";
        read.dataset.readAction = "true";
        read.dataset.tooltip = readLabel;
        read.setAttribute("aria-label", readLabel);
        const readIcon = element("span", "material-icons", item.is_read ? "mark_email_unread" : "done");
        readIcon.setAttribute("aria-hidden", "true");
        read.append(readIcon);
        read.addEventListener("click", function (event) {
            event.stopPropagation();
            toggleRead(item, !item.is_read);
        });
        bottom.append(read);
        button.append(top, element("span", "ai-notification-center__item-client", client), summary, bottom);
        button.addEventListener("click", function () { selectItem(item); });
        button.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectItem(item);
            }
        });
        return button;
    }

    function renderList(append) {
        if (!append) list.replaceChildren();
        if (!state.items.length) {
            renderEmpty();
            listFooter.hidden = true;
            return;
        }
        const fragment = document.createDocumentFragment();
        const start = append ? list.querySelectorAll(".ai-notification-center__item").length : 0;
        state.items.slice(start).forEach(function (item) { fragment.append(createListItem(item)); });
        list.append(fragment);
        listFooter.hidden = false;
        range.textContent = "Mostrando 1–" + state.items.length + " de " + state.total;
        loadMoreButton.hidden = !state.hasMore;
    }

    function detailRow(label, value) {
        if (value === undefined || value === null || value === "") return null;
        const row = element("div", "ai-notification-center__detail-field");
        row.append(element("span", "", label), element("strong", "", value));
        return row;
    }

    function detailsEmpty(message) {
        const empty = element("div", "ai-notification-center__details-empty");
        empty.append(element("span", "material-icons", "notifications_none"), element("p", "", message));
        details.replaceChildren(empty);
    }

    function renderDetails(item) {
        details.replaceChildren();
        const back = element("button", "ai-notification-center__back");
        back.type = "button";
        back.append(element("span", "material-icons", "arrow_back"), document.createTextNode("Voltar às notificações"));
        back.addEventListener("click", function () { center.classList.remove("is-detail-open"); });
        details.append(back);

        const meta = element("div", "ai-notification-center__details-meta");
        meta.append(element("span", "ai-notification-center__priority " + priorityClass(item.priority), item.priority_label));
        meta.append(element("time", "", item.created_date + " às " + item.created_time));
        details.append(meta, element("h3", "", item.title));
        if (item.client) details.append(element("p", "ai-notification-center__details-client", item.client));

        const grid = element("div", "ai-notification-center__details-grid");
        [
            detailRow("OS", item.os_number), detailRow("RDO", item.rdo_number),
            detailRow("Unidade / local", item.unit), detailRow("Tipo", item.type_label),
            detailRow("Origem", item.origin), detailRow("Estado", item.is_read ? "Lida" : "Pendente")
        ].filter(Boolean).forEach(function (row) { grid.append(row); });
        if (grid.childElementCount) details.append(grid);

        const description = element("section", "ai-notification-center__description");
        description.append(element("h4", "", "Descrição"), element("p", "", item.message));
        details.append(description);
        if (item.recommendation) {
            const recommendation = element("section", "ai-notification-center__recommendation");
            const heading = element("h4");
            heading.append(element("span", "material-icons", "auto_awesome"), document.createTextNode("Recomendação da IA"));
            recommendation.append(heading, element("p", "", item.recommendation));
            details.append(recommendation);
        }

        const actions = element("div", "ai-notification-center__actions");
        const read = element("button", "ai-notification-center__primary-action", item.is_read ? "Marcar como não lido" : "Marcar como lido");
        read.type = "button";
        read.addEventListener("click", function () { toggleRead(item, !item.is_read); });
        actions.append(read);
        if (item.detail_url) {
            const detail = element("a", "ai-notification-center__secondary-action", "Ver detalhe");
            detail.href = item.detail_url;
            actions.append(detail);
        }
        if (item.os_url && item.os_url !== item.detail_url) {
            const os = element("a", "ai-notification-center__secondary-action", "Abrir OS");
            os.href = item.os_url;
            actions.append(os);
        }
        details.append(actions);
        center.classList.add("is-detail-open");
    }

    async function selectItem(item) {
        state.selectedKey = item.key;
        list.querySelectorAll(".ai-notification-center__item").forEach(function (node) {
            const active = node.dataset.key === item.key;
            node.classList.toggle("ai-notification-center__item--active", active);
            node.setAttribute("aria-current", active ? "true" : "false");
        });
        details.setAttribute("aria-busy", "true");
        try {
            const payload = await request(templateUrl(center.dataset.detailUrlTemplate, item));
            if (state.selectedKey === item.key) renderDetails(payload.item);
        } catch (error) {
            detailsEmpty("Não foi possível carregar os detalhes deste alerta.");
            showToast(error.message, true);
        } finally {
            details.removeAttribute("aria-busy");
        }
    }

    async function loadPage(page, append) {
        const requestId = ++state.requestId;
        setLoading(true, append);
        try {
            const payload = await request(listUrl(page));
            if (requestId !== state.requestId) return;
            state.page = page;
            state.total = payload.total;
            state.hasMore = payload.has_more;
            state.items = append ? state.items.concat(payload.items) : payload.items.slice();
            updateCounts(payload);
            renderPriorityOptions(payload.priorities);
            renderAlertTypeOptions(payload.alert_types);
            if (!state.initialized) {
                state.initialized = true;
                if (state.tab === "pendentes" && Number(payload.counts.pending || 0) === 0 && Number(payload.counts.all || 0) > 0) {
                    state.tab = "todas";
                    tabs.forEach(function (tab) {
                        tab.setAttribute("aria-selected", tab.dataset.aiTab === state.tab ? "true" : "false");
                    });
                    await loadPage(1, false);
                    return;
                }
            }
            if (!append) {
                let selected = state.items.find(function (item) { return item.key === state.selectedKey; });
                if (!selected) selected = state.items.find(function (item) { return !item.is_read; }) || state.items[0];
                state.selectedKey = selected ? selected.key : null;
            }
            renderList(append);
            const selected = state.items.find(function (item) { return item.key === state.selectedKey; });
            if (selected && !append) selectItem(selected);
        } catch (error) {
            if (requestId !== state.requestId) return;
            const box = element("div", "ai-notification-center__error");
            box.append(element("strong", "", "Não foi possível carregar os alertas."));
            const retry = element("button", "", "Tentar novamente");
            retry.type = "button";
            retry.addEventListener("click", function () { loadPage(1, false); });
            box.append(retry);
            list.replaceChildren(box);
            listFooter.hidden = true;
            detailsEmpty("Não foi possível carregar os alertas.");
        } finally {
            if (requestId === state.requestId) setLoading(false, append);
        }
    }

    async function toggleRead(item, isRead) {
        const previous = item.is_read;
        item.is_read = isRead;
        try {
            const payload = await request(templateUrl(center.dataset.readUrlTemplate, item), {
                method: "POST",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken()
                },
                body: JSON.stringify({ lido: isRead })
            });
            updateBellBadge(payload.unread_count);
            renderCompact(payload.compact_items || []);
            showToast(isRead ? "Notificação marcada como lida." : "Notificação marcada como não lida.");
            if (state.open) await loadPage(1, false);
        } catch (error) {
            item.is_read = previous;
            renderList(false);
            showToast(error.message, true);
        }
    }

    async function markAllRead() {
        if (markAllButton.disabled) return;
        markAllButton.disabled = true;
        try {
            const payload = await request(center.dataset.markAllUrl, {
                method: "POST",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken()
                },
                body: "{}"
            });
            updateBellBadge(payload.unread_count);
            renderCompact(payload.compact_items || []);
            showToast("Todas as notificações foram marcadas como lidas.");
            await loadPage(1, false);
        } catch (error) {
            markAllButton.disabled = false;
            showToast(error.message, true);
        }
    }

    function renderCompact(items) {
        const compact = document.querySelector("#synchro-alerts-dropdown .synchro-alert-list");
        if (!compact) return;
        compact.replaceChildren();
        if (!items.length) {
            const empty = element("div", "synchro-dropdown-empty");
            empty.append(element("span", "material-icons", "task_alt"), element("strong", "", "Tudo em dia"), element("p", "", "Não há alertas da IA pendentes desde ontem."));
            compact.append(empty);
            return;
        }
        items.forEach(function (item) {
            const article = element("article", "synchro-alert-item" + (!item.is_read ? " synchro-alert-item--unread" : ""));
            article.dataset.source = item.source;
            article.dataset.alertId = item.id;
            const head = element("div", "synchro-alert-item-head");
            head.append(element("span", "synchro-alert-dot"), element("strong", "", item.title), element("time", "", item.created_time));
            article.append(head, element("p", "", item.summary || item.message));
            const actions = element("div", "synchro-alert-item-actions");
            actions.append(element("span", "synchro-alert-category", item.priority_label));
            if (!item.is_read) {
                const read = element("button", "synchro-alert-read-button");
                read.type = "button";
                read.dataset.compactMarkRead = "true";
                read.dataset.source = item.source;
                read.dataset.alertId = item.id;
                read.setAttribute("aria-label", "Marcar " + item.title + " como lido");
                read.title = "Marcar como lido";
                read.append(element("span", "material-icons", "done"));
                actions.append(read);
            }
            article.append(actions);
            compact.append(article);
        });
    }

    function closeCompactDropdown() {
        const dropdown = document.getElementById("synchro-alerts-dropdown");
        const toggle = document.getElementById("synchro-alerts-toggle");
        if (dropdown) dropdown.hidden = true;
        if (toggle) toggle.setAttribute("aria-expanded", "false");
    }

    function openCenter(event) {
        if (event) event.preventDefault();
        if (state.open) return;
        state.open = true;
        state.opener = document.getElementById("synchro-alerts-toggle") || document.activeElement || openButton;
        state.tab = "pendentes";
        state.initialized = false;
        tabs.forEach(function (tab) {
            tab.setAttribute("aria-selected", tab.dataset.aiTab === state.tab ? "true" : "false");
        });
        closeCompactDropdown();
        openButton.setAttribute("aria-expanded", "true");
        overlay.hidden = false;
        center.hidden = false;
        center.setAttribute("aria-hidden", "false");
        state.previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        requestAnimationFrame(function () {
            overlay.classList.add("is-open");
            center.classList.add("is-open");
        });
        loadPage(1, false);
        window.setTimeout(function () { closeButton.focus(); }, reducedMotion.matches ? 0 : 180);
    }

    function closeCenter() {
        if (!state.open) return;
        state.open = false;
        center.classList.remove("is-open", "is-detail-open");
        overlay.classList.remove("is-open");
        center.setAttribute("aria-hidden", "true");
        openButton.setAttribute("aria-expanded", "false");
        document.body.style.overflow = state.previousOverflow;
        const finish = function () {
            center.hidden = true;
            overlay.hidden = true;
            center.setAttribute("aria-hidden", "true");
            if (state.opener && document.contains(state.opener)) state.opener.focus();
        };
        window.setTimeout(finish, reducedMotion.matches ? 0 : 230);
    }

    function trapFocus(event) {
        if (!state.open || event.key !== "Tab") return;
        const focusable = Array.from(center.querySelectorAll("button:not([disabled]):not([hidden]), input:not([disabled]), select:not([disabled]), a[href]"))
            .filter(function (node) { return node.offsetParent !== null; });
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }

    let debounceTimer;
    searchInput.addEventListener("input", function () {
        window.clearTimeout(debounceTimer);
        debounceTimer = window.setTimeout(function () {
            state.query = searchInput.value.trim();
            loadPage(1, false);
        }, 400);
    });
    prioritySelect.addEventListener("change", function () {
        state.priority = prioritySelect.value;
        loadPage(1, false);
    });
    typeSelect.addEventListener("change", function () {
        state.alertType = typeSelect.value;
        loadPage(1, false);
    });
    tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
            state.tab = tab.dataset.aiTab;
            tabs.forEach(function (candidate) { candidate.setAttribute("aria-selected", candidate === tab ? "true" : "false"); });
            center.classList.remove("is-detail-open");
            state.selectedKey = null;
            loadPage(1, false);
        });
        tab.addEventListener("keydown", function (event) {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            event.preventDefault();
            const current = tabs.indexOf(tab);
            const direction = event.key === "ArrowRight" ? 1 : -1;
            tabs[(current + direction + tabs.length) % tabs.length].focus();
        });
    });
    loadMoreButton.addEventListener("click", function () { if (state.hasMore) loadPage(state.page + 1, true); });
    markAllButton.addEventListener("click", markAllRead);
    openButton.addEventListener("click", openCenter);
    closeButton.addEventListener("click", closeCenter);
    overlay.addEventListener("click", closeCenter);
    center.addEventListener("click", function (event) { event.stopPropagation(); });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && state.open) { event.preventDefault(); closeCenter(); }
        else trapFocus(event);
    });
    document.addEventListener("click", function (event) {
        const button = event.target.closest("[data-compact-mark-read]");
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();
        toggleRead({ source: button.dataset.source, id: Number(button.dataset.alertId), is_read: false, key: button.dataset.source + ":" + button.dataset.alertId }, true);
    });

    center.setAttribute("aria-hidden", "true");
}());
