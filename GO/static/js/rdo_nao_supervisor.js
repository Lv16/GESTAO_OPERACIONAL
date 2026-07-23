/* Seleção em lote do RDO administrativo. Carregado exclusivamente fora do grupo Supervisor. */
;(function () {
  'use strict';

  function ready(callback) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', callback, { once: true });
    else callback();
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  ready(function () {
    var layout = document.querySelector('.rdo-admin-layout');
    if (!layout) return;

    // A página possui handlers legados para ações da tabela. A paginação é
    // navegação comum e deve prevalecer sobre qualquer preventDefault genérico.
    document.addEventListener('click', function (event) {
      var target = event.target;
      var link = target && target.closest ? target.closest('.rdo-admin-layout .rdo-pagination a.page-btn[href]') : null;
      if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      window.location.assign(link.href);
    }, true);

    var selectAll = layout.querySelector('#rdo-admin-select-all');
    var selectionBar = layout.querySelector('#rdo-admin-selection-bar');
    var selectionCount = layout.querySelector('#rdo-admin-selection-count');
    var clearButton = layout.querySelector('#rdo-admin-selection-clear');
    var deleteButton = layout.querySelector('#rdo-admin-selection-delete');
    var notificationCount = layout.querySelector('.rdo-admin-notification__count');

    // O painel de OS pendentes participa do fluxo da pagina. Assim ele empurra
    // a tabela para baixo, em vez de ficar sobre as linhas quando aberto.
    var notificationButton = layout.querySelector('#rdo-notification-btn');
    var pendingPanel = layout.querySelector('#rdo-desktop-notification-popover');
    var filtersPanel = layout.querySelector('#rdo-filters-panel');
    if (pendingPanel && filtersPanel) {
      filtersPanel.insertAdjacentElement('afterend', pendingPanel);

      var header = pendingPanel.querySelector('.rdo-popover-header');
      var title = pendingPanel.querySelector('.rdo-popover-title');
      if (header && title && !header.querySelector('.rdo-popover-heading')) {
        var heading = document.createElement('div');
        heading.className = 'rdo-popover-heading';
        title.parentNode.insertBefore(heading, title);
        heading.appendChild(title);
        var subtitle = document.createElement('span');
        subtitle.className = 'rdo-popover-subtitle';
        subtitle.textContent = 'Lista de ordens de serviço que ainda não possuem RDO.';
        heading.appendChild(subtitle);
      }

      var headerIcon = header && header.querySelector('.material-icons');
      if (headerIcon) headerIcon.textContent = 'description';

      if (header && !header.querySelector('.rdo-popover-close')) {
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'rdo-popover-close material-icons';
        close.setAttribute('aria-label', 'Fechar lista de OS');
        close.textContent = 'close';
        close.addEventListener('click', function () {
          if (notificationButton) notificationButton.click();
        });
        header.appendChild(close);
      }

      var searchWrap = pendingPanel.querySelector('.rdo-popover-search');
      if (searchWrap && !searchWrap.querySelector('.material-icons')) {
        var searchIcon = document.createElement('span');
        searchIcon.className = 'material-icons';
        searchIcon.setAttribute('aria-hidden', 'true');
        searchIcon.textContent = 'search';
        searchWrap.insertBefore(searchIcon, searchWrap.firstChild);
      }
    }

    function rowChecks() {
      return Array.prototype.slice.call(layout.querySelectorAll('.rdo-admin-row-select'));
    }

    function selectedChecks() {
      return rowChecks().filter(function (input) { return input.checked; });
    }

    function updateNotificationLabel() {
      if (!notificationCount) return;
      var badge = layout.querySelector('#rdo-notification-btn .count');
      var value = badge ? Number.parseInt(badge.textContent || '0', 10) : 0;
      notificationCount.textContent = Number.isFinite(value) && value > 0 ? String(value) : '0';
    }

    function updateSelection() {
      var checks = rowChecks();
      var selected = selectedChecks();
      if (selectionBar) selectionBar.hidden = selected.length === 0;
      if (selectionCount) selectionCount.textContent = selected.length + (selected.length === 1 ? ' selecionado' : ' selecionados');
      if (selectAll) {
        selectAll.checked = checks.length > 0 && selected.length === checks.length;
        selectAll.indeterminate = selected.length > 0 && selected.length < checks.length;
      }
      checks.forEach(function (input) {
        var row = input.closest('tr');
        if (row) row.classList.toggle('rdo-admin-row-selected', input.checked);
      });
    }

    if (selectAll) {
      selectAll.addEventListener('change', function () {
        rowChecks().forEach(function (input) { input.checked = selectAll.checked; });
        updateSelection();
      });
    }

    rowChecks().forEach(function (input) {
      input.addEventListener('change', updateSelection);
    });

    if (clearButton) {
      clearButton.addEventListener('click', function () {
        rowChecks().forEach(function (input) { input.checked = false; });
        updateSelection();
      });
    }

    if (deleteButton) {
      deleteButton.addEventListener('click', async function () {
        var selected = selectedChecks();
        if (!selected.length) return;
        var total = selected.length;
        if (!window.confirm('Excluir definitivamente ' + total + (total === 1 ? ' RDO selecionado?' : ' RDOs selecionados?'))) return;

        deleteButton.disabled = true;
        deleteButton.setAttribute('aria-busy', 'true');
        var failed = [];
        try {
          for (var index = 0; index < selected.length; index += 1) {
            var id = selected[index].value;
            var form = new FormData();
            form.append('rdo_id', id);
            var headers = { 'X-Requested-With': 'XMLHttpRequest' };
            var csrf = csrfToken();
            if (csrf) headers['X-CSRFToken'] = csrf;
            var response = await fetch('/api/rdo/' + encodeURIComponent(id) + '/delete/', {
              method: 'POST',
              credentials: 'same-origin',
              headers: headers,
              body: form
            });
            var payload = null;
            try { payload = await response.json(); } catch (_) { payload = null; }
            if (!response.ok || !(payload && (payload.ok || payload.success))) failed.push(id);
          }
        } catch (_) {
          failed.push('request');
        } finally {
          deleteButton.disabled = false;
          deleteButton.removeAttribute('aria-busy');
        }

        if (failed.length) {
          window.alert('Não foi possível excluir ' + failed.length + ' registro(s). Verifique suas permissões e tente novamente.');
          updateSelection();
          return;
        }
        window.location.reload();
      });
    }

    var pendingBadge = layout.querySelector('#rdo-notification-btn .count');
    if (pendingBadge && window.MutationObserver) {
      new MutationObserver(updateNotificationLabel).observe(pendingBadge, { childList: true, characterData: true, subtree: true });
    }
    updateNotificationLabel();
    updateSelection();
  });
}());

/* Popover de OS sem RDO para usuarios nao supervisores. Reutiliza o popover e os dados existentes. */
;(function () {
  'use strict';

  function ready(callback) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', callback, { once: true });
    else callback();
  }

  ready(function () {
    var layout = document.querySelector('.rdo-admin-layout');
    var trigger = document.getElementById('rdo-notification-btn');
    var panel = document.getElementById('rdo-desktop-notification-popover');
    if (!layout || !trigger || !panel) return;

    trigger.classList.add('rdo-open-os-trigger');
    trigger.setAttribute('aria-controls', 'rdo-desktop-notification-popover');
    trigger.setAttribute('aria-expanded', 'false');
    panel.classList.add('rdo-open-os-popover');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'false');

    var header = panel.querySelector('.rdo-popover-header');
    var title = panel.querySelector('.rdo-popover-title');
    if (header && title && !header.querySelector('.rdo-popover-heading')) {
      var heading = document.createElement('div');
      heading.className = 'rdo-popover-heading';
      title.parentNode.insertBefore(heading, title);
      heading.appendChild(title);
      var subtitle = document.createElement('span');
      subtitle.className = 'rdo-popover-subtitle';
      subtitle.textContent = 'Lista de ordens de serviço que ainda não possuem RDO.';
      heading.appendChild(subtitle);
    }

    var icon = header && header.querySelector('.material-icons');
    if (icon) {
      icon.removeAttribute('style');
      icon.textContent = 'description';
    }

    if (header && !header.querySelector('.rdo-popover-close')) {
      var close = document.createElement('button');
      close.type = 'button';
      close.className = 'rdo-popover-close';
      close.setAttribute('aria-label', 'Fechar lista de OS');
      close.textContent = 'close';
      close.addEventListener('click', function () { trigger.click(); });
      header.appendChild(close);
    }

    var searchWrap = panel.querySelector('.rdo-popover-search');
    if (searchWrap && !searchWrap.querySelector('.material-icons')) {
      var searchIcon = document.createElement('span');
      searchIcon.className = 'material-icons';
      searchIcon.setAttribute('aria-hidden', 'true');
      searchIcon.textContent = 'search';
      searchWrap.insertBefore(searchIcon, searchWrap.firstChild);
    }

    function normalizeList() {
      var columns = panel.querySelector('.rdo-admin-pending-columns');
      if (columns) {
        columns.className = 'rdo-open-os-popover__columns';
        var titles = ['Nº OS', 'Empresa', 'Unidade / Embarcação', 'Ações'];
        while (columns.children.length > titles.length) columns.removeChild(columns.lastElementChild);
        titles.forEach(function (value, index) {
          if (columns.children[index] && columns.children[index].textContent !== value) columns.children[index].textContent = value;
        });
      }

      panel.querySelectorAll('.rdo-admin-pending-row').forEach(function (row) {
        row.classList.remove('rdo-admin-pending-row');
        row.classList.add('rdo-open-os-popover__row');
        while (row.children.length > 4) row.removeChild(row.children[3]);
        Array.prototype.forEach.call(row.children, function (cell, index) {
          cell.className = index === 0 ? 'rdo-open-os-popover__os' : (index === 3 ? 'rdo-open-os-popover__action' : '');
        });
      });

      var count = panel.querySelector('[data-role="count"]');
      var total = count ? (count.textContent.match(/\d+/) || [])[0] : '';
      var summary = panel.querySelector('[data-role="summary"]');
      var all = panel.querySelector('#rdo-popover-ver-todas');
      if (total && summary && summary.textContent !== total + ' OS abertas') summary.textContent = total + ' OS abertas';
      if (total && all && all.textContent !== 'Ver todas (' + total + ')') all.textContent = 'Ver todas (' + total + ')';
    }

    function isOpen() {
      return panel.getAttribute('aria-hidden') === 'false' || panel.classList.contains('open');
    }

    function position() {
      // O painel permanece no fluxo do conteudo, como os filtros. Nenhuma
      // coordenada fixa e aplicada: ao abrir, ele empurra a tabela para baixo.
      panel.style.removeProperty('left');
      panel.style.removeProperty('top');
      panel.style.removeProperty('width');
      panel.style.removeProperty('max-height');
    }

    function syncState(restoreFocus) {
      var open = isOpen();
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        requestAnimationFrame(function () {
          position();
          var search = panel.querySelector('#rdo-popover-search-input');
          if (search) search.focus();
        });
      } else if (restoreFocus) {
        trigger.focus();
      }
    }

    new MutationObserver(function () { syncState(true); }).observe(panel, {
      attributes: true,
      attributeFilter: ['aria-hidden', 'class']
    });

    new MutationObserver(normalizeList).observe(panel, { childList: true, subtree: true });
    normalizeList();

    trigger.addEventListener('click', function () {
      window.setTimeout(function () { syncState(false); }, 0);
    });
    window.addEventListener('resize', position, { passive: true });
    window.addEventListener('scroll', position, { passive: true, capture: true });
  });
}());
