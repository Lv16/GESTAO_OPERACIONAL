function getCsrfTokenLogistica() {
    try {
        const input = document.querySelector('#form-logistica-upload [name=csrfmiddlewaretoken]') || document.querySelector('[name=csrfmiddlewaretoken]');
        if (input && input.value) return input.value;
    } catch (e) {}
    try {
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    } catch (e) {
        return '';
    }
}

function escapeHtmlLogistica(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function getLogisticaElements() {
    return {
        modal: document.getElementById('modal-logistica'),
        form: document.getElementById('form-logistica-upload'),
        osIdInput: document.getElementById('logistica-os-id-input'),
        osNumeroText: document.getElementById('logistica-os-numero'),
        osUnidadeText: document.getElementById('logistica-os-unidade'),
        arquivosInput: document.getElementById('logistica-arquivos'),
        lista: document.getElementById('logistica-anexos-lista'),
        emptyState: document.getElementById('logistica-empty-state'),
    };
}

function getLogisticaRowData(osId) {
    try {
        const trigger = document.getElementById(`btn_logistica_${osId}`);
        const row = trigger ? trigger.closest('tr') : null;
        if (!row) return { numeroOs: '', unidade: '' };

        const cells = row.querySelectorAll('td');
        const numeroOs = cells && cells[1] ? String(cells[1].textContent || '').trim() : '';
        let unidade = '';

        try {
            unidade = String(row.dataset.unidade || '').trim();
        } catch (e) {}
        if (!unidade && cells && cells[3]) {
            unidade = String(cells[3].textContent || '').trim();
        }

        return { numeroOs, unidade };
    } catch (e) {
        return { numeroOs: '', unidade: '' };
    }
}

function renderLogisticaAnexos(anexos) {
    const { lista, emptyState } = getLogisticaElements();
    if (!lista || !emptyState) return;

    if (!Array.isArray(anexos) || !anexos.length) {
        lista.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }

    emptyState.style.display = 'none';
    lista.innerHTML = anexos.map((anexo) => {
        const nome = escapeHtmlLogistica(anexo.nome_original || 'Arquivo');
        const url = escapeHtmlLogistica(anexo.url || '#');
        const meta = [anexo.criado_em, anexo.enviado_por].filter(Boolean).join(' • ');
        return `
            <li class="logistica-anexo-item">
                <a href="${url}" target="_blank" rel="noopener noreferrer">${nome}</a>
                <span class="logistica-anexo-meta">${escapeHtmlLogistica(meta)}</span>
            </li>
        `;
    }).join('');
}

async function carregarAnexosLogistica(osId) {
    const response = await fetch(`/api/os/${encodeURIComponent(osId)}/logistica/anexos/`, {
        method: 'GET',
        credentials: 'same-origin',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error((data && data.error) || 'Falha ao carregar anexos.');
    }
    return data;
}

async function abrirLogisticaModal(osId) {
    const els = getLogisticaElements();
    if (!els.modal) return;
    const rowData = getLogisticaRowData(osId);

    els.modal.style.display = 'flex';
    els.osIdInput.value = osId || '';
    els.osNumeroText.textContent = rowData.numeroOs || '-';
    els.osUnidadeText.textContent = rowData.unidade || '-';
    renderLogisticaAnexos([]);

    try {
        if (window.NotificationManager && typeof window.NotificationManager.showLoading === 'function') {
            window.NotificationManager.showLoading();
        }
        const data = await carregarAnexosLogistica(osId);
        els.osNumeroText.textContent = data.numero_os || rowData.numeroOs || '-';
        els.osUnidadeText.textContent = data.unidade || rowData.unidade || '-';
        renderLogisticaAnexos(data.anexos || []);
    } catch (e) {
        console.error('abrirLogisticaModal erro:', e);
        els.osNumeroText.textContent = rowData.numeroOs || '-';
        els.osUnidadeText.textContent = rowData.unidade || '-';
        if (window.NotificationManager && typeof window.NotificationManager.show === 'function') {
            window.NotificationManager.show(e.message || 'Não foi possível carregar os anexos.', 'error');
        } else {
            alert(e.message || 'Não foi possível carregar os anexos.');
        }
    } finally {
        try {
            if (window.NotificationManager && typeof window.NotificationManager.hideLoading === 'function') {
                window.NotificationManager.hideLoading();
            }
        } catch (e) {}
    }
}

function fecharLogisticaModal() {
    const els = getLogisticaElements();
    if (!els.modal) return;
    els.modal.style.display = 'none';
    if (els.form) els.form.reset();
    if (els.osIdInput) els.osIdInput.value = '';
    if (els.osNumeroText) els.osNumeroText.textContent = '-';
    if (els.osUnidadeText) els.osUnidadeText.textContent = '-';
    renderLogisticaAnexos([]);
}

document.addEventListener('DOMContentLoaded', function () {
    const els = getLogisticaElements();
    if (!els.form) return;

    els.form.addEventListener('submit', async function (event) {
        event.preventDefault();

        const osId = els.osIdInput ? els.osIdInput.value : '';
        const files = els.arquivosInput && els.arquivosInput.files ? Array.from(els.arquivosInput.files) : [];
        if (!osId) {
            if (window.NotificationManager && typeof window.NotificationManager.show === 'function') {
                window.NotificationManager.show('OS inválida para upload.', 'error');
            }
            return;
        }
        if (!files.length) {
            if (window.NotificationManager && typeof window.NotificationManager.show === 'function') {
                window.NotificationManager.show('Selecione ao menos um arquivo.', 'warning');
            } else {
                alert('Selecione ao menos um arquivo.');
            }
            return;
        }

        const formData = new FormData();
        files.forEach((file) => formData.append('arquivos', file));

        try {
            if (window.NotificationManager && typeof window.NotificationManager.showLoading === 'function') {
                window.NotificationManager.showLoading();
            }

            const response = await fetch(`/api/os/${encodeURIComponent(osId)}/logistica/anexos/upload/`, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCsrfTokenLogistica()
                }
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error((data && data.error) || 'Falha ao salvar anexos.');
            }

            const refreshed = await carregarAnexosLogistica(osId);
            renderLogisticaAnexos(refreshed.anexos || []);
            els.form.reset();

            if (window.NotificationManager && typeof window.NotificationManager.show === 'function') {
                window.NotificationManager.show(data.message || 'Anexos salvos com sucesso.', 'success');
            }
        } catch (e) {
            console.error('upload logistica erro:', e);
            if (window.NotificationManager && typeof window.NotificationManager.show === 'function') {
                window.NotificationManager.show(e.message || 'Erro ao enviar anexos.', 'error');
            } else {
                alert(e.message || 'Erro ao enviar anexos.');
            }
        } finally {
            try {
                if (window.NotificationManager && typeof window.NotificationManager.hideLoading === 'function') {
                    window.NotificationManager.hideLoading();
                }
            } catch (e) {}
        }
    });
});
