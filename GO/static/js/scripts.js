
document.querySelector("#logout").addEventListener("click", () => {
    
    window.location.href = "login.html";  
});


const btnNovaOS = document.querySelector("#btn_nova_os");
const radioOS = document.querySelector("#radio_os");
const modal = document.getElementById("modal-os");


function abrirModal() {
    modal.style.display = "flex";
}

function fecharModal() {
    modal.style.display = "none";
}


btnNovaOS.addEventListener("click", () => {
    if (radioOS.style.display === "none" || radioOS.style.display === "") {
        radioOS.style.display = "block";
    } else {
        radioOS.style.display = "none";
    }
});


const radios = radioOS.querySelectorAll("input[name='radio']");
radios.forEach(radio => {
    radio.addEventListener("change", abrirModal);
});


document.querySelector("#modal-os .close-btn").addEventListener("click", fecharModal);

window.addEventListener("click", (e) => {
    if (e.target === modal) {
        fecharModal();
    }
});

const inputPesquisa = document.querySelector(".pesquisar_os");
const linhas = document.querySelectorAll("tbody tr");

inputPesquisa.addEventListener("keyup", () => {
    const valor = inputPesquisa.value.toLowerCase();
    linhas.forEach(linha => {
        const textoLinha = linha.textContent.toLowerCase();
        linha.style.display = textoLinha.includes(valor) ? "" : "none";
    });
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

function abrirDetalhesModal() {
    detalhesModal.style.display = "flex";
}

function fecharDetalhesModal() {
    detalhesModal.style.display = "none";
}

document.querySelectorAll(".btn_tabela").forEach(botao => {
    botao.addEventListener("click", abrirDetalhesModal);
});

document.querySelector("#detalhes_os .close-btn").addEventListener("click", fecharDetalhesModal);

window.addEventListener("click", (e) => {
    if (e.target === detalhesModal) {
        fecharDetalhesModal();
    }
});

