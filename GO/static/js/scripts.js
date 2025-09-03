const servicosEspeciais = [
    "acompanhamento de flushing ou transferência", "armazenamento temporário", "carreta de armazenamento temporário", "certificação gas fire", "certificação gas free", "coleta e análise da água", "coleta e análise do ar", "descarte de resíduos", "descomissionamento", "descontaminação profunda na embarcação", "desmobilização de equipamentos", "desmobilização de pessoas", "desmobilização de pessoas e equipamentos", "desobstrução", "desobstrução da linha de drenagem aberta", "diária da equipe de limpeza de tanques", "diária de ajudante operacional", "diária de consumíveis para limpeza", "diária de consumíveis para pintura", "diária de resgatista", "diária de supervisor", "diária do técnico de segurança do trabalho", "elaboração do pmoc", "emissão de free for fire", "ensacamento e remoção", "equipamentos em stand by", "equipe em stand by", "esgotamento de resíduo", "fornecimento de almoxarife", "fornecimento de auxiliar offshore", "fornecimento de caminhão vácuo", "fornecimento de carreta tanque", "fornecimento de eletricista", "fornecimento de engenheiro químico", "fornecimento de equipamentos e consumíveis", "fornecimento de equipe de alpinista industrial", "fornecimento de equipe de resgate", "fornecimento de irata n1 ou n2", "fornecimento de irata n3", "fornecimento de mão de obra operacional", "fornecimento de materiais", "fornecimento de mecânico", "fornecimento de químicos", "fornecimento de técnico offshore", "hotel, alimentação e transfer por paxinspeção por boroscópio", "inventário", "lista de verificação e planejamento dos materiais a bordo", "limpeza (dutos + coifa + coleta e análise de ar + lavanderia)", "limpeza (dutos + coifa + coleta e análise de ar)", "limpeza (dutos + coifa)", "limpeza da casa de bombas", "limpeza de área do piso de praça", "limpeza de coifa", "limpeza de coifa de cozinha", "limpeza de compartimentos void e cofferdans", "limpeza de dutos", "limpeza de dutos da lavanderia", "limpeza de dutos de ar condicionado", "limpeza de exaustor de cozinha", "limpeza de lavanderia", "limpeza de silos", "limpeza de vaso", "limpeza e descontaminação de carreta", "limpeza geral na embarcação", "limpeza, tratamento e pintura", "locação de equipamentos", "medição de espessura", "mobilização de equipamentos", "mobilização de pessoas", "mobilização de pessoas e equipamentos", "mobilização/desmobilização de carreta tanque", "pintura", "radioproteção norm", "renovação do pmoc", "segregação", "sinalização e isolamento de rejeitos", "serviço de irata", "shut down", "survey para avaliação de atividade", "taxa diária de auxiliar à disposição", "taxa diária de supervisor/operador à disposição", "taxa mensal de equipe onshore", "vigia"
];

function verificaServicoEspecial(valor) {
    if (!valor) return false;
    valor = valor.toLowerCase().trim();
    return servicosEspeciais.some(s => valor === s.toLowerCase());
}

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

document.addEventListener('DOMContentLoaded', function() {
    
    const btnLimparDatas = document.getElementById('btn-limpar-datas');
    if (btnLimparDatas) {
        btnLimparDatas.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = '?';
        });
    }
    
    const btnDatasToggle = document.getElementById('btn-datas-toggle');
    const datasRangeBar = document.querySelector('.datas-range-bar');
    if (btnDatasToggle && datasRangeBar) {
        btnDatasToggle.addEventListener('click', function(e) {
            e.preventDefault();
            datasRangeBar.classList.toggle('active');
            if (datasRangeBar.classList.contains('active')) {
                btnDatasToggle.querySelector('span:last-child').textContent = 'Fechar Datas';
            } else {
                btnDatasToggle.querySelector('span:last-child').textContent = 'Datas';
            }
        });
    }
   
    atualizarCamposTanque('id_servico', 'id_tanque', 'id_volume_tanque');
    
    atualizarCamposTanque('edit_servico', 'edit_tanque', 'edit_volume_tanque');
});
const loadingTips = [
    "Organizando as ordens de serviço...",
    "Verificando atualizações recentes...",
    "Preparando os dados do sistema...",
    "Pegando um cafézinho bem rápido...",
    "Sincronizando dados operacionais...",
    "Quase lá! Finalizando o carregamento..."
];

let tipInterval;


function showRandomTip() {
    const tipsElement = document.getElementById('loadingTips');
    if (tipsElement) {
        const randomTip = loadingTips[Math.floor(Math.random() * loadingTips.length)];
        tipsElement.style.opacity = '0';
        
        setTimeout(() => {
            tipsElement.textContent = randomTip;
            tipsElement.style.opacity = '1';
        }, 500);
    }
}


function showLoading() {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.classList.remove('fade-out');

        showRandomTip();
        tipInterval = setInterval(showRandomTip, 4000);
    }
}

function hideLoading() {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {

        clearInterval(tipInterval);
        loadingScreen.classList.add('fade-out');
    }
}


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
        console.error('Erro ao carregar dados:', error);

        if (error && error.message !== "fetchTableData is not defined") {
            NotificationManager.show("Erro ao carregar dados do sistema", "error");
        }
        hideLoading();
    }
}



document.addEventListener('DOMContentLoaded', () => {
    NotificationManager.init();
    
    
    const logoutBtn = document.querySelector("#logout .Btn");
    const logoutForm = document.querySelector("#logout form");
    
    if (logoutBtn && logoutForm) {
        logoutBtn.addEventListener("click", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const logoutOverlay = document.getElementById('logoutOverlay');
            if (logoutOverlay) {
                
                logoutOverlay.style.display = 'flex';
                
                logoutOverlay.offsetHeight;
                
                logoutOverlay.classList.add('show');
                
                
                setTimeout(() => {
                    logoutForm.submit();
                }, 2000);
            } else {
                
                logoutForm.submit();
            }
        });
    }
    
    initializeData();
});

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


btnNovaOS.addEventListener("click", () => {
    abrirModal();
});

document.querySelector("#modal-os .close-btn").addEventListener("click", fecharModal);

window.addEventListener("click", (e) => {
    if (e.target === modal) {
        fecharModal();
    }
});


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

        const data = await response.json();

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
        console.error("Erro durante a submissão do formulário:", error);
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

function abrirDetalhesModal(osId) {
    fetch(`/os/${osId}/detalhes/`)
        .then(response => {
            if (!response.ok) {
                throw new Error("Erro HTTP " + response.status);
            }
            return response.json();
        })
        .then(data => {
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
        })
        .catch(error => {
            console.error("Erro ao buscar detalhes da OS:", error);
            detalhesModal.style.display = "flex";
        });
}

function fecharDetalhesModal() {
    detalhesModal.style.display = "none";
}

document.querySelectorAll(".btn_tabela:not(.btn-editar)").forEach(botao => {
    botao.addEventListener("click", function () {
        const osId = this.getAttribute("data-id");
        abrirDetalhesModal(osId);
    });
});

document.querySelector("#detalhes_os .close-btn").addEventListener("click", fecharDetalhesModal);

window.addEventListener("click", (e) => {
    if (e.target === detalhesModal) {
        fecharDetalhesModal();
    }
});

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

    console.log("Radio buttons encontrados:", radioButtons.length);

    if (osExistenteField) {
        osExistenteField.style.display = 'none';
    }

    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {
            console.log("Radio alterado:", this.value);
            if (this.value === 'existente') {
                osExistenteField.style.display = 'block';
            } else {
                osExistenteField.style.display = 'none';
            }
        });
    });
});


function abrirModalEdicao(osId) {
    console.log("Abrindo modal de edição para OS ID:", osId);
    
    
    fetch(`/buscar_os/${osId}/`)
        .then(response => response.json())
        .then(data => {
            console.log("Dados recebidos da API:", data);
            if (data.success) {
                console.log("Dados da OS:", data.os);
                preencherFormularioEdicao(data.os);
                document.getElementById('modal-edicao').style.display = 'flex';
            } else {
                alert('Erro ao carregar dados da OS: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Erro ao buscar OS:', error);
            alert('Erro ao carregar dados da OS');
        });
}

function fecharModalEdicao() {
    document.getElementById('modal-edicao').style.display = 'none';
    limparFormularioEdicao();
}

function preencherFormularioEdicao(os) {
    console.log("Preenchendo formulário com dados da OS:", os);
    // Função auxiliar para setar valor ou texto, se o elemento existir
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
}

function limparFormularioEdicao() {
    
    const campos = [
        'edit_cliente', 'edit_unidade', 'edit_solicitante', 'edit_servico', 'edit_tag',
        'edit_metodo', 'edit_tanque', 'edit_volume_tanque', 'edit_especificacao',
        'edit_tipo_operacao', 'edit_status_operacao', 'edit_status_comercial',
        'edit_data_inicio', 'edit_data_fim', 'edit_pob', 'edit_coordenador',
        'edit_supervisor', 'edit_link_rdo', 'edit_observacoes'
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

function handleEditFormSubmit() {
    const form = document.getElementById('form-edicao');
    if (!form) {
        console.error('Formulário de edição não encontrado');
        return;
    }
    
    console.log('Edit form submitted via onclick handler');
    
    const submitBtn = form.querySelector('.btn-confirmar');
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Salvando...';
    submitBtn.disabled = true;
    
    const formData = new FormData(form);
    console.log('Form data prepared, action:', form.action);
    
    fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        }
    })
    .then(response => {
        console.log('Response received:', response.status, response.redirected);
        return response.json();
    })
    .then(data => {
        console.log('Response data:', data);
        if (data.success) {
            NotificationManager.show("OS atualizada com sucesso!", "success");
            fecharModalEdicao();
            setTimeout(() => window.location.reload(), 800);
        } else {
            NotificationManager.show('Erro ao atualizar OS: ' + data.error, "error");
        }
    })
    .catch(error => {
        console.error('Erro ao atualizar OS:', error);
        alert('Erro ao atualizar OS');
    })
    .finally(() => {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    });
}


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
    
    
    const formEdicao = document.getElementById('form-edicao');
    if (formEdicao) {
        formEdicao.addEventListener('submit', function(e) {
            console.log('Edit form submit event triggered');
            e.preventDefault();
            console.log('Default form submission prevented');
            
            const submitBtn = this.querySelector('.btn-confirmar');
            const originalText = submitBtn.textContent;
            submitBtn.textContent = 'Salvando...';
            submitBtn.disabled = true;
            
            const formData = new FormData(this);
            console.log('Form data prepared, action:', this.action);
            
            fetch(this.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            })
            .then(response => {
                console.log('Response received:', response.status, response.redirected);
                return response.json();
            })
            .then(data => {
                console.log('Response data:', data);
                if (data.success) {
                    NotificationManager.show("OS atualizada com sucesso!", "success");
                    fecharModalEdicao();
                    setTimeout(() => window.location.reload(), 800);
                } else {
                    NotificationManager.show('Erro ao atualizar OS: ' + data.error, "error");
                }
            })
            .catch(error => {
                console.error('Erro ao atualizar OS:', error);
                NotificationManager.show("Erro ao atualizar OS", "error");
            })
            .finally(() => {
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
            });
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    const observacoesField = document.getElementById('edit_observacoes');
    const observacaoSpan = document.getElementById('observacao');
    if (observacoesField && observacaoSpan) {
        observacoesField.addEventListener('input', function() {
            observacaoSpan.innerText = observacoesField.value || "Nenhuma observação registrada.";
        });
    }
});
