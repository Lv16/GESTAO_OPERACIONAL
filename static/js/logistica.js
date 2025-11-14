// Função para abrir o link de logística
function abrirLinkLogistica() {
    // Garantir que o NotificationManager está inicializado e disponível
    if (!window.NotificationManager) {
        console.error('NotificationManager não está disponível');
        return;
    }

    const linkLogistica = document.getElementById('edit_logistica').value;
    if (linkLogistica) {
        window.open(linkLogistica, '_blank');
    } else {
        NotificationManager.show('Nenhum link de logística definido', 'warning');
    }
}

// Atualizar o estado do botão quando o campo de link muda
document.addEventListener('DOMContentLoaded', function() {
    const inputLogistica = document.getElementById('edit_logistica');
    const btnOpenLogistica = document.getElementById('btn_open_logistica');
    
    if (inputLogistica && btnOpenLogistica) {
        inputLogistica.addEventListener('input', function() {
            btnOpenLogistica.disabled = !this.value;
        });
    }
});

// Função para abrir o link de logística da tabela
function abrirLogisticaModal(osId) {
    // Garantir que o NotificationManager está inicializado e disponível
    if (!window.NotificationManager) {
        console.error('NotificationManager não está disponível');
        return;
    }

    // Fazer uma requisição para buscar o link de logística
    fetch(`/os/${osId}/detalhes/`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.os && data.os.link_logistica) {
                window.open(data.os.link_logistica, '_blank');
            } else {
                NotificationManager.show('Nenhum link de logística definido para esta OS', 'warning');
            }
        })
        .catch(error => {
            console.error('Erro ao buscar link de logística:', error);
            NotificationManager.show('Erro ao buscar link de logística', 'error');
        });
}