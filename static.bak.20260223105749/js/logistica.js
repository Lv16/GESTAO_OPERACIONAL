// Link de logística fixo
const LINK_LOGISTICA_FIXO = 'https://grupoambitec.sharepoint.com/sites/tankc_OPR/Offshore/Forms/AllItems.aspx?id=%2Fsites%2Ftankc%5FOPR%2FOffshore%2F%28Links%29%20Log%C3%ADstica%20%2D%20Materiais%20e%20pessoas&viewid=aa1b4835%2D169f%2D4392%2Da1cc%2D27cbcca9a14f&xsdata=MDV8MDJ8fDg5ZWIzYjQ0YjE0MDRlMGVjZTA5MDhkZTMxZDk0NjI1fGU2OWJhNGUxMWIxNTQ4NjA5NmY4ZTM1M2YwOWEyYzIxfDB8MHw2MzkwMDMwMDYzODc3NDg5NDB8VW5rbm93bnxWR1ZoYlhOVFpXTjFjbWwwZVZObGNuWnBZMlY4ZXlKRFFTSTZJbFJsWVcxelgwRlVVRk5sY25acFkyVmZVMUJQVEU5R0lpd2lWaUk2SWpBdU1DNHdNREF3SWl3aVVDSTZJbGRwYmpNeUlpd2lRVTRpT2lKUGRHaGxjaUlzSWxkVUlqb3hNWDA9fDF8TDJOb1lYUnpMekU1T2pFelpUSmxNVGRtWTJOa09UUmtNREk0WVdSaE9UTXdabUV6WldWaU9ESmhRSFJvY21WaFpDNTJNaTl0WlhOellXZGxjeTh4TnpZME56QXpPRE0zT0RJMXw4MmY5MTA3ODJhOWM0Y2I2NjM0ZDA4ZGUzMWQ5NDYyNXw1OTBmMDRkNjFhOWQ0YmUyYmE0NGU1ZGNlYmNjMWJmZA%3D%3D&sdata=U2dycGNsNGU5Z1ZldUJpdkFvWjB1bE5Nc1ByNm9SMW0wZmM4aVhTdVVwTT0%3D&ovuser=e69ba4e1-1b15-4860-96f8-e353f09a2c21%2Cgabriel.roza%40ambipar.com';

// Função para abrir o link de logística (agora usa link fixo)
function abrirLinkLogistica() {
    try {
        if (LINK_LOGISTICA_FIXO) {
            window.open(LINK_LOGISTICA_FIXO, '_blank');
            return;
        }
        // fallback: mostrar aviso via NotificationManager se disponível, senão alert
        if (window.NotificationManager && typeof window.NotificationManager.show === 'function') {
            window.NotificationManager.show('Link de logística não configurado', 'error');
        } else {
            alert('Link de logística não configurado');
        }
    } catch (e) {
        console.error('abrirLinkLogistica erro:', e);
        try { window.open(LINK_LOGISTICA_FIXO, '_blank'); } catch (_) {}
    }
}

// Função para abrir o link de logística da tabela (agora usa link fixo)
function abrirLogisticaModal(osId) {
    try {
        if (LINK_LOGISTICA_FIXO) {
            window.open(LINK_LOGISTICA_FIXO, '_blank');
            return;
        }
        if (window.NotificationManager && typeof window.NotificationManager.show === 'function') {
            window.NotificationManager.show('Link de logística não configurado para esta OS', 'warning');
        } else {
            alert('Link de logística não configurado para esta OS');
        }
    } catch (e) {
        console.error('abrirLogisticaModal erro:', e);
        try { window.open(LINK_LOGISTICA_FIXO, '_blank'); } catch (_) {}
    }
}