(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var drawer = document.getElementById('synchro-drawer-nav');
        var overlay = document.getElementById('synchro-drawer-overlay');
        var menuToggle = document.getElementById('synchro-menu-toggle');
        var drawerClose = document.getElementById('synchro-drawer-close');
        var alertToggle = document.getElementById('synchro-alerts-toggle');
        var alertDropdown = document.getElementById('synchro-alerts-dropdown');
        var userToggle = document.getElementById('synchro-user-toggle');
        var userDropdown = document.getElementById('synchro-user-dropdown');
        var searchWrap = document.getElementById('synchro-header-search');
        var searchInput = document.getElementById('synchro-global-search');
        var searchDropdown = document.getElementById('synchro-search-dropdown');
        var searchLoading = searchWrap && searchWrap.querySelector('.synchro-search-loading');
        var lastDrawerFocus = null;
        var searchTimer = null;
        var searchAbort = null;
        var searchItems = [];
        var selectedSearchIndex = -1;
        var searchCache = Object.create(null);

        if (!drawer || !overlay || !menuToggle) return;

        function closeDropdown(toggle, dropdown) {
            if (!toggle || !dropdown) return;
            dropdown.hidden = true;
            toggle.setAttribute('aria-expanded', 'false');
        }

        function closeAllDropdowns(except) {
            if (except !== alertDropdown) closeDropdown(alertToggle, alertDropdown);
            if (except !== userDropdown) closeDropdown(userToggle, userDropdown);
        }

        function toggleDropdown(toggle, dropdown) {
            if (!toggle || !dropdown) return;
            var opening = dropdown.hidden;
            closeAllDropdowns(opening ? dropdown : null);
            closeSearch(false);
            dropdown.hidden = !opening;
            toggle.setAttribute('aria-expanded', opening ? 'true' : 'false');
            if (opening) {
                var focusable = dropdown.querySelector('a,button,input,[tabindex]:not([tabindex="-1"])');
                if (focusable) focusable.focus();
            }
        }

        function openDrawer() {
            closeAllDropdowns();
            closeSearch(false);
            lastDrawerFocus = document.activeElement;
            drawer.classList.add('open');
            overlay.classList.add('is-visible');
            drawer.setAttribute('aria-hidden', 'false');
            overlay.setAttribute('aria-hidden', 'false');
            menuToggle.setAttribute('aria-expanded', 'true');
            menuToggle.setAttribute('aria-label', 'Fechar menu principal');
            document.body.classList.add('synchro-drawer-open');
            (drawer.querySelector('.menu-btn.is-active') || drawer.querySelector('a,button')).focus();
        }

        function closeDrawer(restoreFocus) {
            drawer.classList.remove('open');
            overlay.classList.remove('is-visible');
            drawer.setAttribute('aria-hidden', 'true');
            overlay.setAttribute('aria-hidden', 'true');
            menuToggle.setAttribute('aria-expanded', 'false');
            menuToggle.setAttribute('aria-label', 'Abrir menu principal');
            document.body.classList.remove('synchro-drawer-open');
            if (restoreFocus !== false && lastDrawerFocus && typeof lastDrawerFocus.focus === 'function') lastDrawerFocus.focus();
        }

        function escapeHtml(value) {
            var node = document.createElement('div');
            node.textContent = String(value || '');
            return node.innerHTML;
        }

        function setSearchLoading(isLoading) {
            if (searchLoading) searchLoading.hidden = !isLoading;
            if (searchWrap) searchWrap.classList.toggle('is-loading', isLoading);
        }

        function closeSearch(clearMobile) {
            if (!searchDropdown || !searchWrap) return;
            if (searchAbort) searchAbort.abort();
            clearTimeout(searchTimer);
            setSearchLoading(false);
            searchDropdown.hidden = true;
            searchDropdown.innerHTML = '';
            searchItems = [];
            selectedSearchIndex = -1;
            searchWrap.setAttribute('aria-expanded', 'false');
            if (clearMobile !== false) searchWrap.classList.remove('is-mobile-open');
        }

        function openSearch() {
            if (!searchWrap || !searchDropdown) return;
            closeAllDropdowns();
            searchDropdown.hidden = false;
            searchWrap.setAttribute('aria-expanded', 'true');
        }

        function renderSearchMessage(html) {
            if (!searchDropdown) return;
            openSearch();
            searchDropdown.innerHTML = html;
        }

        function renderSearchResults(payload) {
            var groups = (payload && payload.groups) || [];
            searchItems = [];
            selectedSearchIndex = -1;
            if (!groups.length) {
                renderSearchMessage(
                    '<div class="synchro-search-empty"><span class="material-icons" aria-hidden="true">search_off</span>' +
                    '<strong>Nenhum resultado encontrado para “' + escapeHtml(payload.query) + '”.</strong>' +
                    '<p>Tente pesquisar por número da OS, empresa, unidade, RDO ou equipamento.</p></div>'
                );
                return;
            }
            var markup = '';
            groups.forEach(function (group) {
                markup += '<section class="synchro-search-group"><h2>' + escapeHtml(group.title) + '</h2>';
                group.results.forEach(function (item) {
                    var index = searchItems.length;
                    searchItems.push(item);
                    markup += '<a class="synchro-search-result" role="option" aria-selected="false" data-search-index="' + index + '" href="' + escapeHtml(item.url) + '">' +
                        '<span class="material-icons" aria-hidden="true">' + escapeHtml(item.icon) + '</span>' +
                        '<span class="synchro-search-result-copy"><strong>' + escapeHtml(item.title) + '</strong><small>' + escapeHtml(item.subtitle) + '</small></span>' +
                        '<em>' + escapeHtml(item.category) + '</em></a>';
                });
                markup += '</section>';
            });
            openSearch();
            searchDropdown.innerHTML = markup;
            searchDropdown.querySelectorAll('.synchro-search-result').forEach(function (item) {
                item.addEventListener('mouseenter', function () { setSelectedSearchItem(Number(item.dataset.searchIndex)); });
                item.addEventListener('click', function () { closeSearch(); });
            });
        }

        function setSelectedSearchItem(index) {
            var nodes = searchDropdown ? searchDropdown.querySelectorAll('.synchro-search-result') : [];
            if (!nodes.length) return;
            selectedSearchIndex = (index + nodes.length) % nodes.length;
            nodes.forEach(function (node, nodeIndex) {
                var active = nodeIndex === selectedSearchIndex;
                node.classList.toggle('is-selected', active);
                node.setAttribute('aria-selected', active ? 'true' : 'false');
            });
            nodes[selectedSearchIndex].scrollIntoView({ block: 'nearest' });
        }

        function runSearch() {
            if (!searchInput || !searchWrap) return;
            var term = searchInput.value.trim();
            if (term.length < 2) {
                closeSearch(false);
                return;
            }
            if (searchAbort) searchAbort.abort();
            if (searchCache[term]) {
                renderSearchResults(searchCache[term]);
                return;
            }
            var controller = new AbortController();
            searchAbort = controller;
            setSearchLoading(true);
            openSearch();
            searchDropdown.innerHTML = '<div class="synchro-search-status"><span class="material-icons" aria-hidden="true">progress_activity</span>Buscando…</div>';
            fetch(searchWrap.dataset.searchUrl + '?q=' + encodeURIComponent(term), {
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin',
                signal: controller.signal
            }).then(function (response) {
                if (!response.ok) throw new Error('Falha na busca');
                return response.json();
            }).then(function (payload) {
                searchCache[term] = payload;
                if (searchInput.value.trim() === term) renderSearchResults(payload);
            }).catch(function (error) {
                if (error.name !== 'AbortError') {
                    renderSearchMessage('<div class="synchro-search-empty"><strong>Não foi possível realizar a busca agora.</strong><p>Tente novamente em instantes.</p></div>');
                }
            }).finally(function () {
                if (searchAbort === controller) setSearchLoading(false);
            });
        }

        menuToggle.addEventListener('click', function () { drawer.classList.contains('open') ? closeDrawer() : openDrawer(); });
        overlay.addEventListener('click', function () { closeDrawer(); });
        if (drawerClose) drawerClose.addEventListener('click', function () { closeDrawer(); });
        drawer.querySelectorAll('a[href]').forEach(function (link) { link.addEventListener('click', function () { closeDrawer(false); }); });
        if (alertToggle) alertToggle.addEventListener('click', function (event) { event.stopPropagation(); toggleDropdown(alertToggle, alertDropdown); });
        if (userToggle) userToggle.addEventListener('click', function (event) { event.stopPropagation(); toggleDropdown(userToggle, userDropdown); });

        if (searchInput && searchWrap) {
            searchInput.addEventListener('focus', function () {
                if (window.matchMedia('(max-width: 760px)').matches) searchWrap.classList.add('is-mobile-open');
            });
            searchWrap.addEventListener('click', function () {
                if (window.matchMedia('(max-width: 760px)').matches) searchWrap.classList.add('is-mobile-open');
                searchInput.focus();
            });
            searchInput.addEventListener('input', function () {
                clearTimeout(searchTimer);
                if (searchInput.value.trim().length < 2) {
                    closeSearch(false);
                    return;
                }
                searchTimer = setTimeout(runSearch, 350);
            });
        }

        document.addEventListener('click', function (event) {
            if (!event.target.closest('.synchro-dropdown-wrap')) closeAllDropdowns();
            if (searchWrap && !event.target.closest('#synchro-header-search')) closeSearch();
        });
        document.addEventListener('keydown', function (event) {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && searchInput) {
                event.preventDefault();
                if (window.matchMedia('(max-width: 760px)').matches) searchWrap.classList.add('is-mobile-open');
                searchInput.focus();
                searchInput.select();
                return;
            }
            if (event.key === 'Escape') {
                if (searchDropdown && !searchDropdown.hidden) {
                    closeSearch();
                } else if (drawer.classList.contains('open')) closeDrawer();
                else closeAllDropdowns();
            }
            if (!searchDropdown || searchDropdown.hidden) return;
            if (event.key === 'ArrowDown') { event.preventDefault(); setSelectedSearchItem(selectedSearchIndex + 1); }
            if (event.key === 'ArrowUp') { event.preventDefault(); setSelectedSearchItem(selectedSearchIndex - 1); }
            if (event.key === 'Enter' && selectedSearchIndex >= 0) {
                var selected = searchDropdown.querySelector('[data-search-index="' + selectedSearchIndex + '"]');
                if (selected) { event.preventDefault(); selected.click(); }
            }
        });
    });
}());
