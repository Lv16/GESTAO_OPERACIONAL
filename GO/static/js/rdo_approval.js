;(function () {
  'use strict';

  function ready(callback) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback, { once: true });
    } else {
      callback();
    }
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function showConfirmationModal(message) {
    return new Promise(function (resolve) {
      var overlay = document.getElementById('rdo-confirm-approval-overlay');
      var messageElement = document.getElementById('rdo-confirm-message');
      var confirmButton = document.getElementById('rdo-confirm-btn-ok');
      var cancelButton = document.getElementById('rdo-confirm-btn-cancel');

      if (!overlay || !messageElement || !confirmButton || !cancelButton) {
        resolve(window.confirm(message));
        return;
      }

      messageElement.textContent = message;
      overlay.style.display = 'flex';
      overlay.setAttribute('aria-hidden', 'false');

      function cleanup() {
        confirmButton.removeEventListener('click', confirm);
        cancelButton.removeEventListener('click', cancel);
        overlay.style.display = 'none';
        overlay.setAttribute('aria-hidden', 'true');
      }

      function confirm() {
        cleanup();
        resolve(true);
      }

      function cancel() {
        cleanup();
        resolve(false);
      }

      confirmButton.addEventListener('click', confirm);
      cancelButton.addEventListener('click', cancel);
    });
  }

  ready(function () {
    document.querySelectorAll('.rdo-approval-checkbox').forEach(function (checkbox) {
      checkbox.addEventListener('change', async function () {
        var priorValue = !checkbox.checked;
        var rdoId = checkbox.getAttribute('data-rdo-id');
        var confirmed = await showConfirmationModal('Deseja realmente aprovar este RDO?');

        if (!confirmed) {
          checkbox.checked = priorValue;
          return;
        }

        checkbox.disabled = true;
        try {
          var form = new FormData();
          form.append('approved', 'true');

          var headers = { 'X-Requested-With': 'XMLHttpRequest' };
          var csrf = csrfToken();
          if (csrf) headers['X-CSRFToken'] = csrf;

          var response = await fetch('/api/rdo/' + encodeURIComponent(rdoId) + '/aprovar/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: headers,
            body: form
          });
          var payload = await response.json();

          if (!response.ok || !payload || !payload.success) {
            throw new Error(payload && payload.error ? payload.error : 'Ocorreu um erro desconhecido.');
          }

          checkbox.checked = payload.approved;
          var approvedBy = document.getElementById('rdo-approved-by-' + rdoId);
          var approvedAt = document.getElementById('rdo-approved-em-' + rdoId);
          if (approvedBy) approvedBy.textContent = payload.aprovado_por;
          if (approvedAt) approvedAt.textContent = payload.aprovado_em;
        } catch (error) {
          checkbox.checked = priorValue;
          checkbox.disabled = false;
          window.alert('Erro ao atualizar aprovação: ' + error.message);
          return;
        }

        checkbox.disabled = checkbox.checked;
      });
    });
  });
})();
