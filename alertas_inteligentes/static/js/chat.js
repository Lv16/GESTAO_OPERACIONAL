document.addEventListener('DOMContentLoaded', function() {
    const formChat = document.querySelector('.ia-form');
    const inputPergunta = document.querySelector('input[name="pergunta"]');
    const buttonSubmit = document.querySelector('.ia-pergunta-principal button');
    const chatBox = document.querySelector('.ia-chat-box');

    if (!formChat || !inputPergunta || !buttonSubmit || !chatBox) {
        console.warn('Chat form elements not found');
        return;
    }

    formChat.addEventListener('submit', function(e) {
        e.preventDefault();

        const pergunta = inputPergunta.value.trim();
        if (!pergunta) {
            return;
        }

        inputPergunta.disabled = true;
        buttonSubmit.disabled = true;

        adicionarMensagemUsuario(pergunta);
        const indicadorPensando = mostrarIndicadorPensando();

        const url = new URL(window.location.href);
        url.searchParams.set('pergunta', pergunta);
        url.searchParams.set('acao', 'pergunta_livre');

        fetch(url.toString(), {
            method: 'GET',
            headers: {
                'Accept': 'text/html',
                'X-Requested-With': 'XMLHttpRequest',
            },
            credentials: 'same-origin',
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error('Erro na requisicao');
                }
                return response.text();
            })
            .then((html) => {
                indicadorPensando.remove();

                const parser = new DOMParser();
                const novoDoc = parser.parseFromString(html, 'text/html');
                const mensagensAssistente = novoDoc.querySelectorAll('.ia-message.ia-message-assistant');
                const resultadoDiv = mensagensAssistente.length
                    ? mensagensAssistente[mensagensAssistente.length - 1]
                    : null;

                if (resultadoDiv) {
                    chatBox.appendChild(resultadoDiv.cloneNode(true));
                }

                inputPergunta.value = '';
                scrollParaFinal();
            })
            .catch((error) => {
                console.error('Erro:', error);
                indicadorPensando.remove();

                const msgErro = document.createElement('div');
                msgErro.className = 'ia-message ia-message-assistant';
                msgErro.innerHTML = `
                    <div class="ia-avatar">SI</div>
                    <div class="ia-bubble">
                        <div class="ia-rich-text">
                            <p style="color: #ff6b6b;">Desculpe, ocorreu um erro ao processar sua pergunta. Tente novamente.</p>
                        </div>
                    </div>
                `;
                chatBox.appendChild(msgErro);
                scrollParaFinal();
            })
            .finally(() => {
                inputPergunta.disabled = false;
                buttonSubmit.disabled = false;
                inputPergunta.focus();
            });
    });

    function adicionarMensagemUsuario(texto) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'ia-message ia-message-user';
        msgDiv.innerHTML = `<div class="ia-user-bubble">${escaparHTML(texto)}</div>`;
        chatBox.appendChild(msgDiv);
        scrollParaFinal();
    }

    function mostrarIndicadorPensando() {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'ia-message ia-message-assistant ia-pensando';
        msgDiv.innerHTML = `
            <div class="ia-avatar">SI</div>
            <div class="ia-bubble">
                <div class="ia-pensando-indicador">
                    <span></span>
                    <span></span>
                    <span></span>
                    <p>Processando...</p>
                </div>
            </div>
        `;
        chatBox.appendChild(msgDiv);
        scrollParaFinal();
        return msgDiv;
    }

    function scrollParaFinal() {
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function escaparHTML(texto) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;',
        };
        return texto.replace(/[&<>"']/g, (m) => map[m]);
    }

    inputPergunta.focus();

});
