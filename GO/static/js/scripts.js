document.querySelector("#logout").addEventListener("click", () => { 
    window.location.href = "login.html";  
});

const btnNovaOS = document.querySelector("#btn_nova_os");
const modal = document.getElementById("modal-os");

function abrirModal() {
    console.log("Opening modal...");  
    console.log("Modal element:", modal);
    if (!modal) {
        console.error("Modal element not found!");
        return;
    } 
    modal.style.display = "flex";

    
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

btnNovaOS.addEventListener("click", () => {
    abrirModal();
});

document.querySelector("#modal-os .close-btn").addEventListener("click", fecharModal);

window.addEventListener("click", (e) => {
    if (e.target === modal) {
        fecharModal();
    }
});

document.getElementById("form-os").addEventListener("submit", function(e) {
    e.preventDefault(); 
    
    const formData = new FormData(this);
    
    console.log("=== FORM DATA ===");
    for (const [key, value] of formData.entries()) {
        console.log(`${key}: ${value}`);
    }
    console.log("=================");

    const submitBtn = this.querySelector('.btn-confirmar');
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Enviando...';
    submitBtn.disabled = true;

    fetch(this.action, {
        method: "POST",
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        }
    })
    .then(response => {
        console.log("Response status:", response.status);
        
        if (response.redirected) {
            window.location.reload();
            return;
        }
        
        if (!response.ok) {
            return response.text().then(errorText => {
                console.error("Raw error response:", errorText);
                try {
                    const errorData = JSON.parse(errorText);
                    throw new Error(`HTTP ${response.status}: ${JSON.stringify(errorData)}`);
                } catch (e) {
                    throw new Error(`HTTP ${response.status}: ${errorText}`);
                }
            }).catch(() => {
                throw new Error(`HTTP ${response.status}: Failed to get error response`);
            });
        }
        
        return response.json();
    })
    .then(data => {
        console.log("Response data:", data);

        if (data && data.success) {
            alert("OS criada com sucesso!");
            fecharModal();
            window.location.reload();
        } else if (data && data.errors) {
            clearFormErrors();
            console.log("Form validation errors:", data.errors);
            for (const [field, errors] of Object.entries(data.errors)) {
                const fieldElement = document.querySelector(`[name="${field}"]`);
                if (fieldElement) {
                    fieldElement.classList.add('error-field');
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'error-message';
                    errorDiv.style.color = 'red';
                    errorDiv.style.fontSize = '12px';
                    errorDiv.style.marginTop = '5px';
                    errorDiv.textContent = errors.join(', ');
                    fieldElement.parentNode.appendChild(errorDiv);
                } else {
                    alert(`Erro: ${errors.join(', ')}`);
                }
            }
        } else {
            console.error("Unexpected response format:", data);
            alert("Resposta inesperada do servidor. Por favor, tente novamente.");
        }
    })
    .catch(error => {
        console.error("Error during form submission:", error);
        alert("Erro ao criar OS. Por favor, verifique o console para mais detalhes e tente novamente.");
    })
    .finally(() => {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    });
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
    
    // Campos não editáveis
    document.getElementById('edit_num_os').textContent = os.numero_os || 'N/A';
    document.getElementById('edit_cod_os').textContent = os.codigo_os || 'N/A';
    document.getElementById('edit_id_os').textContent = os.id || 'N/A';
    
    
    document.getElementById('edit_os_id').value = os.id;
    
    // Campos editáveis
    if (os.cliente) document.getElementById('edit_cliente').value = os.cliente;
    if (os.unidade) document.getElementById('edit_unidade').value = os.unidade;
    if (os.solicitante) document.getElementById('edit_solicitante').value = os.solicitante;
    if (os.servico) document.getElementById('edit_servico').value = os.servico;
    if (os.tag) document.getElementById('edit_tag').value = os.tag;
    if (os.metodo) document.getElementById('edit_metodo').value = os.metodo;
    if (os.tanque) document.getElementById('edit_tanque').value = os.tanque;
    if (os.volume_tanque) document.getElementById('edit_volume_tanque').value = os.volume_tanque;
    if (os.especificacao) document.getElementById('edit_especificacao').value = os.especificacao;
    if (os.tipo_operacao) document.getElementById('edit_tipo_operacao').value = os.tipo_operacao;
    if (os.status_operacao) document.getElementById('edit_status_operacao').value = os.status_operacao;
    if (os.status_comercial) document.getElementById('edit_status_comercial').value = os.status_comercial;
    if (os.data_inicio) document.getElementById('edit_data_inicio').value = os.data_inicio;
    if (os.data_fim) document.getElementById('edit_data_fim').value = os.data_fim;
    if (os.pob) document.getElementById('edit_pob').value = os.pob;
    if (os.coordenador) document.getElementById('edit_coordenador').value = os.coordenador;
    if (os.supervisor) document.getElementById('edit_supervisor').value = os.supervisor;
    
    // Debug observacao field
    console.log("Observacao value from API:", os.observacao);
    const observacoesField = document.getElementById('edit_observacoes');
    console.log("Observacoes field element:", observacoesField);
    if (os.observacao) {
        observacoesField.value = os.observacao;
        console.log("Set observacoes field value to:", observacoesField.value);
    } else {
        console.log("No observacao value in API response");
    }
    
    if (os.link_rdo) document.getElementById('edit_link_rdo').value = os.link_rdo;
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
            alert('OS atualizada com sucesso!');
            fecharModalEdicao();

            // Update the report modal's histórico field in real-time
            const observacoesValue = document.getElementById('edit_observacoes').value;
            const observacaoSpan = document.getElementById('observacao');
            if (observacaoSpan) {
                observacaoSpan.innerText = observacoesValue || "Nenhuma observação registrada.";
            }
        } else {
            alert('Erro ao atualizar OS: ' + data.error);
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
                    alert('OS atualizada com sucesso!');
                    fecharModalEdicao();

                    
                    const observacoesValue = document.getElementById('edit_observacoes').value;
                    const observacaoSpan = document.getElementById('observacao');
                    if (observacaoSpan) {
                        observacaoSpan.innerText = observacoesValue || "Nenhuma observação registrada.";
                    }
                } else {
                    alert('Erro ao atualizar OS: ' + data.error);
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
