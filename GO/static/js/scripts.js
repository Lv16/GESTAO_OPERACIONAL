// Recarrega a página ao submeter o formulário de edição do modal-edicao
document.addEventListener('DOMContentLoaded', function() {
    var formEdicao = document.getElementById('form-edicao');
    if (formEdicao) {
        formEdicao.addEventListener('submit', function() {
            setTimeout(function() {
                window.location.reload();
            }, 700); 
        });
    }
});

// Drawer lateral expansível
document.addEventListener('DOMContentLoaded', function() {
    const hamburger = document.getElementById('hamburger-menu');
    const drawer = document.getElementById('drawer-nav');
    const siteWrapper = document.getElementById('site-wrapper');
    const body = document.body;
    function openDrawer() {
        drawer.classList.add('open');
        body.classList.add('drawer-open');
    }
    function closeDrawer() {
        drawer.classList.remove('open');
        body.classList.remove('drawer-open');
    }
    if (hamburger && drawer) {
        hamburger.addEventListener('click', function(e) {
            e.stopPropagation();
            if (drawer.classList.contains('open')) {
                closeDrawer();
            } else {
                openDrawer();
            }
        });
    }
    // Fecha ao clicar fora do drawer
    document.addEventListener('click', function(e) {
        if (drawer.classList.contains('open') && !drawer.contains(e.target) && !hamburger.contains(e.target)) {
            closeDrawer();
        }
    });
    // Fecha com ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && drawer.classList.contains('open')) {
            closeDrawer();
        }
    });
});
// Menu Hamburguer
document.addEventListener('DOMContentLoaded', function() {
    const hamburger = document.getElementById('hamburger-menu');
    const nav = document.getElementById('main-nav');
    if (hamburger && nav) {
        hamburger.addEventListener('click', function() {
            nav.classList.toggle('open');
        });
        hamburger.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' || e.key === ' ') nav.classList.toggle('open');
        });
    }
});
// Limpa a flag do sessionStorage ao fazer logout ANTES do submit
document.addEventListener('DOMContentLoaded', function() {
    var logoutForm = document.getElementById('logoutForm');
    var logoutOverlay = document.getElementById('logoutOverlay');
    if (logoutForm) {
        logoutForm.addEventListener('submit', function(e) {
            e.preventDefault();
            // Exibe overlay de logout
            if (logoutOverlay) {
                logoutOverlay.classList.add('show');
                logoutOverlay.style.display = 'flex';
            }
            setTimeout(function() {
                sessionStorage.removeItem('welcome_shown');
                logoutForm.submit();
            }, 1000); // 1 segundo de tela de logout
        });
    }
});

// Preencher e travar cliente/unidade ao selecionar OS existente no modal de nova OS
document.addEventListener('DOMContentLoaded', function() {
    const radioButtons = document.querySelectorAll('#box-opcao-container input[type="radio"]');
    const osExistenteField = document.getElementById('os-existente-Field');
    const clienteField = document.getElementById('id_cliente');
    const unidadeField = document.getElementById('id_unidade');
    const osExistenteSelect = document.getElementById('os_existente_select');

    function setFieldsDisabled(disabled) {
        if (clienteField) clienteField.disabled = disabled;
        if (unidadeField) unidadeField.disabled = disabled;
    }

    function preencherClienteUnidadeDaOS(osId) {
        if (!osId) return;
        fetch(`/buscar_os/${osId}/`)
            .then(async response => {
                let data;
                try {
                    data = await response.json();
                } catch (e) {
                    NotificationManager.show('Erro inesperado: resposta do servidor não é JSON. Faça login novamente ou recarregue a página.', 'error');
                    return;
                }
                if (data && data.os) {
                    if (clienteField && data.os.cliente) {
                        clienteField.value = data.os.cliente;
                    }
                    if (unidadeField && data.os.unidade) {
                        unidadeField.value = data.os.unidade;
                    }
                } else if (data && data.error) {
                    NotificationManager.show(data.error, 'error');
                }
            })
            .catch(error => {
                NotificationManager.show('Erro ao buscar dados da OS existente', 'error');

            });
    }

    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.value === 'existente') {
                setFieldsDisabled(true);
                if (osExistenteSelect && osExistenteSelect.value) {
                    preencherClienteUnidadeDaOS(osExistenteSelect.value);
                }
            } else {
                setFieldsDisabled(false);
                if (clienteField) clienteField.value = '';
                if (unidadeField) unidadeField.value = '';
            }
        });
    });

    if (osExistenteSelect) {
        osExistenteSelect.addEventListener('change', function() {
            const radioExistente = Array.from(radioButtons).find(r => r.value === 'existente' && r.checked);
            if (radioExistente) {
                preencherClienteUnidadeDaOS(this.value);
            }
        });
    }

    const radioExistente = Array.from(radioButtons).find(r => r.value === 'existente' && r.checked);
    if (radioExistente && osExistenteSelect && osExistenteSelect.value) {
        setFieldsDisabled(true);
        preencherClienteUnidadeDaOS(osExistenteSelect.value);
    } else {
        setFieldsDisabled(false);
    }
});


const servicosEspeciais = [
    "acompanhamento de flushing ou transferência", "armazenamento temporário", "carreta de armazenamento temporário", "certificação gas fire", "certificação gas free", "coleta e análise da água", "coleta e análise do ar", "descarte de resíduos", "descomissionamento", "descontaminação profunda na embarcação", "desmobilização de equipamentos", "desmobilização de pessoas", "desmobilização de pessoas e equipamentos", "desobstrução", "desobstrução da linha de drenagem aberta", "diária da equipe de limpeza de tanques", "diária de ajudante operacional", "diária de consumíveis para limpeza", "diária de consumíveis para pintura", "diária de resgatista", "diária de supervisor", "diária do técnico de segurança do trabalho", "elaboração do pmoc", "emissão de free for fire", "ensacamento e remoção", "equipamentos em stand by", "equipe em stand by", "esgotamento de resíduo", "fornecimento de almoxarife", "fornecimento de auxiliar offshore", "fornecimento de caminhão vácuo", "fornecimento de carreta tanque", "fornecimento de eletricista", "fornecimento de engenheiro químico", "fornecimento de equipamentos e consumíveis", "fornecimento de equipe de alpinista industrial", "fornecimento de equipe de resgate", "fornecimento de irata n1 ou n2", "fornecimento de irata n3", "fornecimento de mão de obra operacional", "fornecimento de materiais", "fornecimento de mecânico", "fornecimento de químicos", "fornecimento de técnico offshore", "hotel, alimentação e transfer por paxinspeção por boroscópio", "inventário", "lista de verificação e planejamento dos materiais a bordo", "limpeza (dutos + coifa + coleta e análise de ar + lavanderia)", "limpeza (dutos + coifa + coleta e análise de ar)", "limpeza (dutos + coifa)", "limpeza da casa de bombas", "limpeza de área do piso de praça", "limpeza de coifa", "limpeza de coifa de cozinha", "limpeza de compartimentos void e cofferdans", "limpeza de dutos", "limpeza de dutos da lavanderia", "limpeza de dutos de ar condicionado", "limpeza de exaustor de cozinha", "limpeza de lavanderia", "limpeza de silos", "limpeza de vaso", "limpeza e descontaminação de carreta", "limpeza geral na embarcação", "limpeza, tratamento e pintura", "locação de equipamentos", "medição de espessura", "mobilização de equipamentos", "mobilização de pessoas", "mobilização de pessoas e equipamentos", "mobilização/desmobilização de carreta tanque", "pintura", "radioproteção norm", "renovação do pmoc", "segregação", "sinalização e isolamento de rejeitos", "serviço de irata", "shut down", "survey para avaliação de atividade", "taxa diária de auxiliar à disposição", "taxa diária de supervisor/operador à disposição", "taxa mensal de equipe onshore", "vigia"
];

// Verifica se o serviço selecionado é especial

function verificaServicoEspecial(valor) {
    if (!valor) return false;
    valor = valor.toLowerCase().trim();
    return servicosEspeciais.some(s => valor === s.toLowerCase());
}
// Atualiza os campos "tanque" e "volume do tanque" com base no serviço selecionado
function atualizarCamposTanque(servicoId, tanqueId, volumeId) {
   
    let servico = document.getElementById(servicoId) || document.querySelector(`[name='servico']`);
    let tanque = document.getElementById(tanqueId) || document.querySelector(`[name='tanque']`);
    let volume = document.getElementById(volumeId) || document.querySelector(`[name='volume_tanque']`);
    if (!servico || !tanque || !volume) return;
    function handler() {
        const selecionado = servico.options ? servico.options[servico.selectedIndex].text : servico.value;
        if (verificaServicoEspecial(selecionado)) {
            tanque.value = "-";
            tanque.readOnly = true;
            tanque.setAttribute('tabindex', '-1');
            tanque.style.backgroundColor = '#e0e0e0';
            tanque.placeholder = 'Bloqueado automaticamente';
            volume.value = 0;
            volume.readOnly = true;
            volume.setAttribute('tabindex', '-1');
            volume.style.backgroundColor = '#e0e0e0';
            volume.placeholder = 'Bloqueado automaticamente';
        } else {
            tanque.readOnly = false;
            tanque.removeAttribute('tabindex');
            tanque.style.backgroundColor = '';
            tanque.placeholder = '';
            volume.readOnly = false;
            volume.removeAttribute('tabindex');
            volume.style.backgroundColor = '';
            volume.placeholder = '';
        }
    }
    servico.addEventListener('change', handler);

    handler();
}

// Gerenciamento de notificações

document.addEventListener('DOMContentLoaded', function() {
    // Botão Limpar Filtros
        // Corrige o botão Limpar Filtros para limpar todos os campos do painel de filtros e filtros ativos
        var btnLimpar = document.getElementById('btn-limpar-filtros');
        if (btnLimpar) {
            btnLimpar.addEventListener('click', function(e) {
                e.preventDefault();
                var filterPanel = document.getElementById('campos-filtro');
                if (filterPanel) {
                    var inputs = filterPanel.querySelectorAll('input, select');
                    inputs.forEach(function(input) {
                        if (input.type === 'checkbox' || input.type === 'radio') {
                            input.checked = false;
                        } else if (input.type === 'date' || input.type === 'text' || input.type === 'number' || input.tagName === 'SELECT') {
                            input.value = '';
                        }
                    });
                }
                // Limpa os chips de filtros ativos (se existirem)
                var filtrosAtivosBar = document.getElementById('filtros-ativos-bar');
                if (filtrosAtivosBar) {
                    // Redireciona para a página sem parâmetros de filtro
                    window.location.href = window.location.pathname;
                }
            });
    }

        // Corrige o botão Limpar Filtros da barra de filtros ativos
        var btnLimparBar = document.querySelector('.btn-limpar-filtros-bar');
        if (btnLimparBar) {
            btnLimparBar.addEventListener('click', function(e) {
                e.preventDefault();
                window.location.href = window.location.pathname;
            });
        }
    
    const btnLimparDatas = document.getElementById('btn-limpar-datas');
    if (btnLimparDatas) {
        btnLimparDatas.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = '?';
        });
    }
    
    // Gerenciamento do toggle de datas
    var btnToggleDatas = document.getElementById('btn-toggle-datas');
    var filtroDataInicial = document.getElementById('filtro-data-inicial');
    var filtroDataFinal = document.getElementById('filtro-data-final');
    if (filtroDataInicial) filtroDataInicial.classList.remove('ativo');
    if (filtroDataFinal) filtroDataFinal.classList.remove('ativo');
    if (btnToggleDatas && filtroDataInicial && filtroDataFinal) {
        btnToggleDatas.addEventListener('click', function() {
            filtroDataInicial.classList.toggle('ativo');
            filtroDataFinal.classList.toggle('ativo');
        });
    }
   
    atualizarCamposTanque('id_servico', 'id_tanque', 'id_volume_tanque');
    
    atualizarCamposTanque('edit_servico', 'edit_tanque', 'edit_volume_tanque');

});
function showLoading() {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.classList.remove('fade-out');
    }
}



function hideLoading() {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.classList.add('fade-out');
    }
}

// Animação do barco

document.addEventListener('DOMContentLoaded', function() {
    const barco = document.querySelector('.barco');
    const fumaca = document.querySelector('.fumaca');
    if (barco && fumaca) {
        const barcoContainer = barco.parentElement;
        const barcoWidth = barco.offsetWidth;
        const caminho = barcoContainer.offsetWidth - barcoWidth;
        let start = null;
        function animarBarco(ts) {
            if (!start) start = ts;
            const dur = 6000;
            let elapsed = (ts - start) % dur;
            let pct = elapsed / dur;
            let left = caminho * pct;
            let amplitude = 4;
            let yBase = 10;
            let freq = 2;
            let y = Math.sin(pct * Math.PI * 2 * freq) * amplitude + yBase;
            barco.style.left = left + 'px';
            barco.style.bottom = y + 'px';
            fumaca.style.left = (left + 18) + 'px';
            fumaca.style.top = (y) + 'px';
            requestAnimationFrame(animarBarco);
        }
        requestAnimationFrame(animarBarco);
        barco.style.filter = 'brightness(0) saturate(100%)';
    }
});

// Função para verificar se a tabela foi carregada
function isTableLoaded() {
    const table = document.querySelector('table');
    return table && table.rows.length > 1; 
}


async function fetchTableData() {
    let attempts = 0;
    const maxAttempts = 10;
    
    while (!isTableLoaded() && attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 200));
        attempts++;
    }
    
    if (!isTableLoaded()) {
        throw new Error("Tempo limite excedido ao carregar a tabela");
    }
    
    return true;
}

 // Função principal para inicializar dados
async function initializeData() {
    showLoading();
    
    try {
        
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        
        if (typeof fetchTableData === 'function') {
            await fetchTableData();
        }


       await new Promise(resolve => setTimeout(resolve, 2500));

        hideLoading();
    } catch (error) {


        if (error && error.message !== "fetchTableData is not defined") {
            NotificationManager.show("Erro ao carregar dados do sistema", "error");
        }
        hideLoading();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Gerenciamento da tela de loading: só mostra após login
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        if (!sessionStorage.getItem('welcome_shown')) {
            setTimeout(() => {
                hideLoading();
                setTimeout(() => {
                    if (loadingScreen && loadingScreen.parentNode) {
                        loadingScreen.parentNode.removeChild(loadingScreen);
                    }
                }, 800); // tempo do fade-out em ms
            }, 2500);
            sessionStorage.setItem('welcome_shown', '1');
        } else {
            loadingScreen.parentNode.removeChild(loadingScreen);
        }
    }

    // Animação do barco
    const barco = document.querySelector('.barco');
    const fumaca = document.querySelector('.fumaca');
    if (barco && fumaca) {
        const barcoContainer = barco.parentElement;
        const barcoWidth = barco.offsetWidth;
        const caminho = barcoContainer.offsetWidth - barcoWidth;
        let start = null;
        function animarBarco(ts) {
            if (!start) start = ts;
            const dur = 6000;
            let elapsed = (ts - start) % dur;
            let pct = elapsed / dur;
            let left = caminho * pct;
            let amplitude = 4;
            let yBase = 10;
            let freq = 2;
            let y = Math.sin(pct * Math.PI * 2 * freq) * amplitude + yBase;
            barco.style.left = left + 'px';
            barco.style.bottom = y + 'px';
            fumaca.style.left = (left + 18) + 'px';
            fumaca.style.top = (y) + 'px';
            requestAnimationFrame(animarBarco);
        }
        requestAnimationFrame(animarBarco);
        barco.style.filter = 'brightness(0) saturate(100%)';
    }
});

// Gerenciamento do modal de nova OS
const btnNovaOS = document.querySelector("#btn_nova_os");
const modal = document.getElementById("modal-os");

function abrirModal() {
    if (!modal) {
        NotificationManager.show("Erro ao abrir o modal", "error");
        return;
    } 
    modal.style.display = "flex";
    NotificationManager.show("Criando nova Ordem de Serviço", "info");
    
    setTimeout(() => {
        const radioButtons = document.querySelectorAll('#box-opcao-container input[type="radio"]');
        const osExistenteField = document.getElementById('os-existente-Field');

        if (osExistenteField) {
            osExistenteField.style.display = 'none';
        }

        radioButtons.forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.value === 'existente') {
                    osExistenteField.style.display = 'block';
                } else {
                    osExistenteField.style.display = 'none';
                }
            });
           
            if (radio.checked && radio.value === 'existente') {
                osExistenteField.style.display = 'block';
            }
        });
    }, 100);
}

function fecharModal() {
    modal.style.display = "none";
}

// Função para exibir erros de formulário
function handleFormErrors(errors) {
    clearFormErrors();
    for (const [field, messages] of Object.entries(errors)) {
        const fieldElement = document.querySelector(`[name="${field}"]`);
        if (fieldElement) {
            fieldElement.classList.add('error-field');
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.style.color = 'red';
            errorDiv.style.fontSize = '12px';
            errorDiv.style.marginTop = '5px';
            errorDiv.textContent = messages.join(', ');
            fieldElement.parentNode.appendChild(errorDiv);
        } else {
            NotificationManager.show(`${field}: ${messages.join(', ')}`, 'error');
        }
    }
}

// Função para limpar erros de formulário
async function submitFormAjax(form) {
    try {
        NotificationManager.showLoading();
        const formData = new FormData(form);
        
        const response = await fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (response.redirected) {
            window.location.href = response.url;
            return true;
        }

        const data = await response.json();

        if (response.ok) {
            NotificationManager.show(data.message || 'Operação realizada com sucesso!', 'success');
            if (data.redirect) {
                setTimeout(() => window.location.href = data.redirect, 1500);
            }
            return true;
        } else {
            if (data.errors) {
                handleFormErrors(data.errors);
            } else {
                NotificationManager.show(data.error || 'Erro ao processar sua solicitação', 'error');
            }
            return false;
        }
    } catch (error) {
        NotificationManager.show('Erro ao conectar com o servidor', 'error');
        return false;
    } finally {
        NotificationManager.hideLoading();
    }
}


// Eventos para abrir e fechar o modal
btnNovaOS.addEventListener("click", () => {
    abrirModal();
});

document.querySelector("#modal-os .close-btn").addEventListener("click", fecharModal);

window.addEventListener("click", (e) => {
    
    if (e.target === modal) {
        fecharModal();
    }
    const detalhesModal = document.getElementById('detalhes_os');
    if (detalhesModal && detalhesModal.style.display === 'flex' && e.target === detalhesModal) {
        fecharDetalhesModal();
    }
    const modalEdicao = document.getElementById('modal-edicao');
    if (modalEdicao && modalEdicao.style.display === 'flex' && e.target === modalEdicao) {
        fecharModalEdicao();
    }

    
    const filterPanel = document.getElementById('campos-filtro');
    const filterToggle = document.getElementById('filter-toggle');
    const isPanelVisible = filterPanel && (getComputedStyle(filterPanel).display !== 'none' && getComputedStyle(filterPanel).visibility !== 'hidden');
    if (filterPanel && isPanelVisible && !filterPanel.contains(e.target) && e.target !== filterToggle) {
        if (typeof toggleFiltros === 'function') {
            toggleFiltros();
        }
    }
    const datasRangeBar = document.querySelector('.datas-range-bar');
    const btnDatasToggle = document.getElementById('btn-datas-toggle');
    const isDatasVisible = datasRangeBar && (datasRangeBar.classList.contains('active') || (getComputedStyle(datasRangeBar).display !== 'none' && getComputedStyle(datasRangeBar).visibility !== 'hidden'));

    const isBtnDatasClick = btnDatasToggle && (e.target === btnDatasToggle || btnDatasToggle.contains(e.target));
    if (datasRangeBar && isDatasVisible && !datasRangeBar.contains(e.target) && !isBtnDatasClick) {
        if (btnDatasToggle) btnDatasToggle.click();
    }
});

// Submissão do formulário via AJAX
document.getElementById("form-os").addEventListener("submit", async function(e) {
    e.preventDefault();
    
    
    const submitBtn = this.querySelector('.btn-confirmar');
    if (submitBtn && submitBtn.disabled) {
        return;
    }

    try {
        const formData = new FormData(this);
        NotificationManager.showLoading();

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Enviando...';
        }

        const response = await fetch(this.action, {
            method: "POST",
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        });

        if (response.redirected) {
            window.location.href = response.url;
            return;
        }

        let data;
        try {
            data = await response.json();
        } catch (e) {
            NotificationManager.show('Erro inesperado: resposta do servidor não é JSON. Faça login novamente ou recarregue a página.', 'error');
            return;
        }
        if (data.success) {
            NotificationManager.show(data.message || "OS criada com sucesso!", "success");
            fecharModal();
            setTimeout(() => window.location.reload(), 1500);
        } else if (data.errors) {
            handleFormErrors(data.errors);
        } else {
            NotificationManager.show("Erro ao processar sua solicitação", "error");
        }
    } catch (error) {

        NotificationManager.show("Erro ao conectar com o servidor", "error");
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Confirmar';
        }
        NotificationManager.hideLoading();
    }
});


function clearFormErrors() {
    const errorMessages = document.querySelectorAll('.error-message');
    errorMessages.forEach(msg => msg.remove());
    const errorFields = document.querySelectorAll('.error-field');
    errorFields.forEach(field => field.classList.remove('error-field'));
}

const inputPesquisa = document.querySelector(".pesquisar_os");

inputPesquisa.addEventListener("keyup", (event) => {
    if (event.key === 'Enter') {
        const valor = inputPesquisa.value.trim();
        if (valor) {
            window.location.href = `?search=${encodeURIComponent(valor)}`;
        } else {
            window.location.href = '?page=1';
        }
    }
});

// Cálculo de dias de operação
function calcularDiasOperacao() {
    const tabela = document.querySelector("table tbody");
    const linhas = tabela.querySelectorAll("tr");

    linhas.forEach(linha => {
        const colDataInicio = linha.cells[4].textContent.trim(); 
        const colDataFim = linha.cells[5].textContent.trim();   

        const partesInicio = colDataInicio.split("/");
        const partesFim = colDataFim.split("/");

        if (partesInicio.length === 3 && partesFim.length === 3) {
            const dataInicio = new Date(partesInicio[2], partesInicio[1]-1, partesInicio[0]);
            const dataFim = new Date(partesFim[2], partesFim[1]-1, partesFim[0]);

            const diffTime = dataFim - dataInicio;
            const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24)) + 1; 

            linha.cells[16].textContent = diffDays + " Dias";
        }
    });
}

window.addEventListener("load", calcularDiasOperacao);

const detalhesModal = document.getElementById("detalhes_os");

// Função para abrir o modal de detalhes da OS
function abrirDetalhesModal(osId) {

    var detalhesModal = document.getElementById("detalhes_os");
    fetch(`/os/${osId}/detalhes/`)
        .then(response => {
            if (!response.ok) {
                throw new Error("Erro HTTP " + response.status);
            }
            return response.json();
        }) 
        .then(data => {
            // Preencher os campos do modal com os dados recebidos
            document.getElementById("id_os").innerText = data.id || "";
            document.getElementById("num_os").innerText = data.numero_os || "";
            document.getElementById("tag").innerText = data.tag || "";
            document.getElementById("cod_os").innerText = data.codigo_os || "";
            document.getElementById("data_inicio").innerText = data.data_inicio || "";
            document.getElementById("data_fim").innerText = data.data_fim || "";
            document.getElementById("dias_op").innerText = data.dias_de_operacao || "";
            document.getElementById("cliente").innerText = data.cliente || "";
            document.getElementById("unidade").innerText = data.unidade || "";
            document.getElementById("solicitante").innerText = data.solicitante || "";
            document.getElementById("regime").innerText = data.tipo_operacao || "";
            document.getElementById("servico").innerText = data.servico || "";
            document.getElementById("metodo").innerText = data.metodo || "";
            if (document.getElementById("metodo_secundario")) {
                document.getElementById("metodo_secundario").innerText = data.metodo_secundario || "";
            }
            document.getElementById("tanque").innerText = data.tanque || "";
            document.getElementById("volume_tq").innerText = data.volume_tanque || "";
            document.getElementById("especificacao").innerText = data.especificacao || "";
            document.getElementById("pob").innerText = data.pob || "";
            document.getElementById("coordenador").innerText = data.coordenador || "";
            document.getElementById("supervisor").innerText = data.supervisor || "";
            document.getElementById("status_os").innerText = data.status_operacao || "";
            document.getElementById("status_comercial").innerText = data.status_comercial || "";
            document.getElementById("observacao").innerText = data.observacao || "Nenhuma observação registrada.";
            document.getElementById("link_rdo").innerHTML = data.link_rdo ? `<a href="${data.link_rdo}" target="_blank">Controle de Atividades</a>` : "Nenhum link registrado.";
            document.getElementById("link_materiais").innerHTML = data.materiais_equipamentos ? `<a href="${data.materiais_equipamentos}" target="_blank">Materiais e Equipamentos</a>` : "Nenhum link registrado.";

            detalhesModal.style.display = "flex";

            exibirNotificacaoExportarPDF();

            const btnExportar = document.getElementById('confirmar-exportar-pdf');
            const btnRecusar = document.getElementById('recusar-exportar-pdf');
            if (btnExportar) {
                btnExportar.onclick = function() {
                    window.location.href = `/os/${osId}/exportar_pdf/`;
                };
            }
            if (btnRecusar) btnRecusar.onclick = minimizarNotificacaoPDF;
        })
        .catch(error => {

            detalhesModal.style.display = "flex";

            exibirNotificacaoExportarPDF();
        });
}

// Gerenciamento da notificação de exportação PDF
function exibirNotificacaoExportarPDF() {
    var notificacao = document.getElementById('notificacao-exportar-pdf');
    var minimizada = document.getElementById('notificacao-pdf-minimizada');
    if (notificacao) {
        notificacao.style.display = 'block';
        notificacao.setAttribute('aria-hidden', 'false');
    }
    if (minimizada) {
        minimizada.style.display = 'none';
        minimizada.setAttribute('aria-hidden', 'true');
    }
}

// Eventos para abrir e fechar o modal de detalhes
document.querySelectorAll(".btn_tabela[id^='btn_detalhes_']").forEach(botao => {
    botao.addEventListener("click", function () {
        const osId = this.getAttribute("data-id");
    // Em produção, não exibe debug
        abrirDetalhesModal(osId);
    });
});

document.querySelector("#detalhes_os .close-btn").addEventListener("click", fecharDetalhesModal);

window.addEventListener("click", (e) => {
    if (e.target === detalhesModal) {
        fecharDetalhesModal();
    }
});


function fecharDetalhesModal() {
    var detalhesModal = document.getElementById("detalhes_os");
    if (detalhesModal) {
        detalhesModal.style.display = "none";
    }
}

document.querySelector("#detalhes_os .close-btn").addEventListener("click", fecharDetalhesModal);

window.addEventListener("click", (e) => {
    if (e.target === detalhesModal) {
        fecharDetalhesModal();
    }
});

// Filtro por status
const filtroIcon = document.querySelector(".fa-filter");
const dropdown = document.getElementById("dropdown-filtro");

filtroIcon.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation(); 
    dropdown.style.display = dropdown.style.display === "flex" ? "none" : "flex";
});

document.addEventListener("click", (e) => {
    if (!dropdown.contains(e.target) && e.target !== filtroIcon) {
        dropdown.style.display = "none";
    }
});

document.querySelectorAll(".opcao-filtro").forEach(opcao => {
    opcao.addEventListener("click", function () {
        const statusSelecionado = this.getAttribute("data-status").toLowerCase();
        filtrarPorStatus(statusSelecionado);
        dropdown.style.display = "none";
    });
});

// Função para filtrar linhas da tabela por status
function filtrarPorStatus(statusFiltro) {
    const linhas = document.querySelectorAll("tbody tr");
    linhas.forEach(linha => {
        const celulas = linha.querySelectorAll("td");
        const statusCell = celulas[19];
        if (statusCell) {
            const statusTexto = statusCell.textContent.toLowerCase().trim();
            linha.style.display = statusTexto === statusFiltro ? "" : "none";
        }
    });
}

// Gerenciamento do painel de filtros
function toggleFiltros() {
    const filterPanel = document.getElementById("campos-filtro");
    filterPanel.classList.toggle("visible");
    
    
    const toggleButton = document.querySelector(".filter-toggle");
    if (filterPanel.classList.contains("visible")) {
        toggleButton.textContent = "Ocultar Filtros";
    } else {
        toggleButton.textContent = "Mostrar Filtros";
    }
}

// Evento para o botão de alternar filtros
document.addEventListener('click', function(event) {
    const filterPanel = document.getElementById("campos-filtro");
    const toggleButton = document.querySelector(".filter-toggle");
    
    if (filterPanel.classList.contains("visible") && 
        !filterPanel.contains(event.target) && 
        event.target !== toggleButton) {
        filterPanel.classList.remove("visible");
        toggleButton.textContent = "Mostrar Filtros";
    }
});

document.querySelector('.filter-panel').addEventListener('click', function(event) {
    event.stopPropagation();
});

document.addEventListener('DOMContentLoaded', function() {
    const radioButtons = document.querySelectorAll('#box-opcao-container input[type="radio"]');
    const osExistenteField = document.getElementById('os-existente-Field');



    if (osExistenteField) {
        osExistenteField.style.display = 'none';
    }

    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {

            if (this.value === 'existente') {
                osExistenteField.style.display = 'block';
            } else {
                osExistenteField.style.display = 'none';
            }
        });
    });
});

document.addEventListener('DOMContentLoaded', function() {
    var btnLimpar = document.getElementById('btn-limpar-filtros');
    if (btnLimpar) {
        btnLimpar.addEventListener('click', function() {
            window.location.href = window.location.pathname;
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    // Mostrar/ocultar campos de data no painel de filtros
    var btnToggleDatas = document.getElementById('btn-toggle-datas');
    var filtroDataInicial = document.getElementById('filtro-data-inicial');
    var filtroDataFinal = document.getElementById('filtro-data-final');
    if (btnToggleDatas && filtroDataInicial && filtroDataFinal) {
        btnToggleDatas.addEventListener('click', function() {
            filtroDataInicial.classList.toggle('ativo');
            filtroDataFinal.classList.toggle('ativo');
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    var btnLimparDatasChip = document.getElementById('btn-limpar-datas-chip');
    if (btnLimparDatasChip) {
        btnLimparDatasChip.addEventListener('click', function() {
            const url = new URL(window.location.href);
            url.searchParams.delete('data_inicial');
            url.searchParams.delete('data_final');
            window.location.href = url.pathname + (url.searchParams.toString() ? '?' + url.searchParams.toString() : '');
        });
    }

   
    var btnLimparFiltros = document.getElementById('btn-limpar-filtros');
    if (btnLimparFiltros) {
        btnLimparFiltros.addEventListener('click', function() {
           
            window.location.href = window.location.pathname;
        });
    }

});
// Gerenciamento do modal de edição de OS
function abrirModalEdicao(osId) {

    
    
    fetch(`/buscar_os/${osId}/`)
        .then(response => response.json())
        .then(data => {

            if (data.success) {

                preencherFormularioEdicao(data.os);
                document.getElementById('modal-edicao').style.display = 'flex';
                    const novaObs = document.getElementById('nova_observacao');
                    if (novaObs) novaObs.value = '';
            } else {
                NotificationManager.show('Erro ao carregar dados da OS: ' + data.error, 'error');
            }
        })
        .catch(error => {
            // Em produção, não exibe erro no console
            NotificationManager.show('Erro ao carregar dados da OS', 'error');
        });
}

function fecharModalEdicao() {
    document.getElementById('modal-edicao').style.display = 'none';
    limparFormularioEdicao();
}

// Eventos para abrir e fechar o modal de edição
function preencherFormularioEdicao(os) {

    const setValue = (id, value, prop = 'value') => {
        const el = document.getElementById(id);
        if (el) {
            if (prop === 'value') {
                el.value = value || '';
            } else {
                el.textContent = value || 'N/A';
            }
        }
    };
    // Preencher os campos do formulário
    setValue('edit_num_os', os.numero_os, 'textContent');
    setValue('edit_cod_os', os.codigo_os, 'textContent');
    setValue('edit_id_os', os.id, 'textContent');
    setValue('edit_os_id', os.id);
    setValue('edit_cliente', os.cliente);
    setValue('edit_unidade', os.unidade);
    setValue('edit_solicitante', os.solicitante);
    setValue('edit_servico', os.servico);
    setValue('edit_tag', os.tag);
    setValue('edit_metodo', os.metodo);
    setValue('edit_metodo_secundario', os.metodo_secundario);
    setValue('edit_tanque', os.tanque);
    setValue('edit_volume_tanque', os.volume_tanque);
    setValue('edit_especificacao', os.especificacao);
    setValue('edit_tipo_operacao', os.tipo_operacao);
    setValue('edit_status_operacao', os.status_operacao);
    setValue('edit_status_comercial', os.status_comercial);
    setValue('edit_data_inicio', os.data_inicio);
    setValue('edit_data_fim', os.data_fim);
    setValue('edit_pob', os.pob);
    setValue('edit_coordenador', os.coordenador);
    setValue('edit_supervisor', os.supervisor);

    const observacoesField = document.getElementById('edit_observacoes');
    if (observacoesField) {
        observacoesField.value = os.observacao || '';
    }
    setValue('edit_link_rdo', os.link_rdo);
    setValue('edit_link_materiais', os.materiais_equipamentos);

    const historicoDiv = document.getElementById('historico_observacoes');
    if (historicoDiv) {
        historicoDiv.textContent = os.observacao || "Nenhuma observação registrada.";
    }
    const novaObs = document.getElementById('nova_observacao');
    if (novaObs) novaObs.value = '';
}

function limparFormularioEdicao() {
    
    const campos = [
    'edit_cliente', 'edit_unidade', 'edit_solicitante', 'edit_servico', 'edit_tag',
    'edit_metodo', 'edit_metodo_secundario', 'edit_tanque', 'edit_volume_tanque', 'edit_especificacao',
        'edit_tipo_operacao', 'edit_status_operacao', 'edit_status_comercial',
        'edit_data_inicio', 'edit_data_fim', 'edit_pob', 'edit_coordenador',
    'edit_supervisor', 'edit_link_rdo', 'edit_link_materiais', 'edit_observacoes'
    ];
    
    campos.forEach(campo => {
        const element = document.getElementById(campo);
        if (element) {
            if (element.tagName === 'SELECT') {
                element.selectedIndex = 0;
            } else {
                element.value = '';
            }
        }
    });
    
    
    document.getElementById('edit_num_os').textContent = '';
    document.getElementById('edit_cod_os').textContent = '';
    document.getElementById('edit_id_os').textContent = '';
    document.getElementById('edit_os_id').value = '';
}

// Função para lidar com a submissão do formulário de edição via onclick

// Eventos para abrir e fechar o modal de edição
document.addEventListener('DOMContentLoaded', function() {
    
    window.addEventListener('click', (e) => {
        const modalEdicao = document.getElementById('modal-edicao');
        if (e.target === modalEdicao) {
            fecharModalEdicao();
        }
    });
    
   
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            fecharModalEdicao();
        }
    });
    
    // Envio do formulário de edição via AJAX
    const formEdicao = document.getElementById('form-edicao');
    if (formEdicao) {
 
        formEdicao.addEventListener('submit', function(e) {

            e.preventDefault();

            
            const submitBtn = this.querySelector('.btn-confirmar');
            const originalText = submitBtn.textContent;
            submitBtn.textContent = 'Salvando...';
            submitBtn.disabled = true;
            
            const formData = new FormData(this);

            
            fetch(this.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            })
            .then(response => {
                if (response.redirected) {
                    window.location.href = response.url;
                    return;
                }
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.indexOf('application/json') !== -1) {
                    return response.json();
                } else {
                    return {};
                }
            })
            .then(data => {

                if (data.success) {
                    NotificationManager.show("OS atualizada com sucesso!", "success");
                    fecharModalEdicao();
                    const novaObs = document.getElementById('nova_observacao');
                    if (novaObs) novaObs.value = '';
                    NotificationManager.hideLoading();
                    if (NotificationManager.loadingOverlay && NotificationManager.loadingOverlay.parentNode) {
                        NotificationManager.loadingOverlay.parentNode.removeChild(NotificationManager.loadingOverlay);
                    }
                    setTimeout(() => {
                        location.href = location.href;
                    }, 100);
                } else {
                    NotificationManager.show('Erro ao atualizar OS: ' + data.error, "error");
                }
            })
            .catch(error => {

                NotificationManager.show("Erro ao atualizar OS", "error");
            })
            .finally(() => {
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
            });
            return false;
        });
    }
});

// Atualiza a exibição da observação em tempo real enquanto o usuário digita
document.addEventListener('DOMContentLoaded', function() {
    const observacoesField = document.getElementById('edit_observacoes');
    const observacaoSpan = document.getElementById('observacao');
    if (observacoesField && observacaoSpan) {
        observacoesField.addEventListener('input', function() {
            observacaoSpan.innerText = observacoesField.value || "Nenhuma observação registrada.";
        });
    }
});
    

// Exportar tabela para Excel
document.addEventListener('DOMContentLoaded', function() {
    var btnExportar = document.getElementById('exportar_excel');
    if (btnExportar) {
        btnExportar.addEventListener('click', function(e) {
            e.preventDefault();
            if (window.NotificationManager && typeof NotificationManager.show === 'function') {
                NotificationManager.show('Tabela exportada com sucesso!', 'success', 4000);
            } else {
                alert('Tabela exportada com sucesso!');
            }
            setTimeout(function() {
                window.location.href = '/exportar_excel/';
            }, 700);
        });
    }
});

