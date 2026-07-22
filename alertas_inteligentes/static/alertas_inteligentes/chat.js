document.addEventListener('DOMContentLoaded', function() {
    const formChat = document.querySelector('.ia-form');
    const inputPergunta = document.querySelector('input[name="pergunta"]');
    const buttonSubmit = document.querySelector('.ia-submit-btn');
    const chatBox = document.querySelector('.ia-chat-box');
    const emptyState = document.querySelector('.ia-empty-state');
    const voiceButton = document.querySelector('[data-voice-trigger="true"]');
    const voiceStatus = document.querySelector('[data-voice-status="true"]');
    const assistantLogoSrc = (
        document.querySelector('.ia-avatar-logo')?.getAttribute('src') ||
        document.querySelector('.ia-topbar-logo')?.getAttribute('src') ||
        ''
    );

    if (!formChat || !inputPergunta || !buttonSubmit || !chatBox) {
        console.warn('Chat form elements not found');
        return;
    }

    const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition || null;
    let recognition = null;
    let voiceSupported = Boolean(SpeechRecognitionClass);
    let isListening = false;
    let isStopping = false;
    let voiceBaseValue = '';
    let finalTranscript = '';
    let interimTranscript = '';

    function assistantAvatarMarkup() {
        if (assistantLogoSrc) {
            return `
                <div class="ia-avatar">
                    <img src="${assistantLogoSrc}" alt="Synchro AI" class="ia-avatar-logo">
                </div>
            `;
        }

        return '<div class="ia-avatar">SI</div>';
    }

    function setVoiceState(state, message) {
        if (voiceButton) {
            voiceButton.dataset.voiceState = state;
            voiceButton.setAttribute('aria-pressed', state === 'listening' ? 'true' : 'false');
            voiceButton.title = message || 'Ditado por voz';
        }

        if (voiceStatus) {
            voiceStatus.textContent = message || '';
            voiceStatus.dataset.voiceState = state;
        }
    }

    function setVoiceAvailability(available, message) {
        voiceSupported = available;

        if (!voiceButton) {
            return;
        }

        voiceButton.disabled = !available;
        voiceButton.setAttribute('aria-disabled', available ? 'false' : 'true');
        setVoiceState(available ? 'idle' : 'unavailable', message);
    }

    function composeInputValue() {
        const parts = [voiceBaseValue, finalTranscript, interimTranscript]
            .map((item) => (item || '').trim())
            .filter(Boolean);
        inputPergunta.value = parts.join(' ');
    }

    function resetRecognitionBuffer() {
        voiceBaseValue = '';
        finalTranscript = '';
        interimTranscript = '';
        isListening = false;
        isStopping = false;
    }

    function stopRecognition() {
        if (!recognition || !isListening) {
            return;
        }

        isStopping = true;
        setVoiceState('processing', 'Finalizando audio...');
        try {
            recognition.stop();
        } catch (error) {
            console.warn('Falha ao parar reconhecimento de voz', error);
        }
    }

    function buildRecognition() {
        if (!SpeechRecognitionClass || !voiceButton) {
            setVoiceAvailability(false, 'Ditado por voz indisponivel neste navegador.');
            return;
        }

        recognition = new SpeechRecognitionClass();
        recognition.lang = 'pt-BR';
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.continuous = false;

        recognition.onstart = function() {
            isListening = true;
            isStopping = false;
            voiceBaseValue = inputPergunta.value.trim();
            finalTranscript = '';
            interimTranscript = '';
            setVoiceState('listening', 'Ouvindo... fale sua pergunta.');
        };

        recognition.onresult = function(event) {
            let nextFinal = '';
            let nextInterim = '';

            for (let index = 0; index < event.results.length; index += 1) {
                const result = event.results[index];
                const transcript = (result[0] && result[0].transcript ? result[0].transcript : '').trim();
                if (!transcript) {
                    continue;
                }

                if (result.isFinal) {
                    nextFinal = `${nextFinal} ${transcript}`.trim();
                } else {
                    nextInterim = `${nextInterim} ${transcript}`.trim();
                }
            }

            if (nextFinal) {
                finalTranscript = nextFinal;
            }
            interimTranscript = nextInterim;
            composeInputValue();
        };

        recognition.onerror = function(event) {
            const errorCode = event && event.error ? event.error : 'erro';
            const messages = {
                'not-allowed': 'Permissao de microfone negada.',
                'service-not-allowed': 'Ditado por voz bloqueado neste navegador.',
                'audio-capture': 'Nao foi possivel acessar o microfone.',
                'network': 'Falha de rede durante a transcricao.',
                'no-speech': 'Nenhuma fala detectada. Tente novamente.',
                'aborted': 'Ditado interrompido.',
            };

            if (errorCode === 'not-allowed' || errorCode === 'service-not-allowed') {
                setVoiceAvailability(false, messages[errorCode]);
            } else {
                setVoiceState('error', messages[errorCode] || 'Erro ao capturar audio.');
            }

            isListening = false;
            isStopping = false;
        };

        recognition.onend = function() {
            const hadTranscript = Boolean(finalTranscript || interimTranscript);
            const hadText = Boolean(inputPergunta.value.trim());
            const wasStopping = isStopping;

            isListening = false;
            isStopping = false;

            if (!voiceSupported) {
                return;
            }

            if (hadTranscript) {
                interimTranscript = '';
                composeInputValue();
                setVoiceState('idle', 'Audio transcrito. Revise e envie.');
            } else if (wasStopping && hadText) {
                setVoiceState('idle', 'Ditado encerrado.');
            } else if (!hadText) {
                setVoiceState('idle', 'Toque no microfone para falar.');
            }

            resetRecognitionBuffer();
        };

        voiceButton.addEventListener('click', function() {
            if (!voiceSupported || !recognition || voiceButton.disabled) {
                return;
            }

            if (isListening) {
                stopRecognition();
                return;
            }

            try {
                recognition.start();
            } catch (error) {
                console.warn('Falha ao iniciar reconhecimento de voz', error);
                setVoiceState('error', 'Nao foi possivel iniciar o ditado por voz.');
            }
        });

        setVoiceAvailability(true, 'Toque no microfone para falar.');
    }

    function setChatBusy(busy) {
        inputPergunta.disabled = busy;
        buttonSubmit.disabled = busy;

        if (voiceButton && voiceSupported) {
            voiceButton.disabled = busy;
        }
    }

    formChat.addEventListener('submit', function(e) {
        e.preventDefault();

        const pergunta = inputPergunta.value.trim();
        if (!pergunta) {
            return;
        }

        if (isListening) {
            stopRecognition();
        }

        setChatBusy(true);

        if (emptyState) {
            emptyState.remove();
        }

        chatBox.classList.add('has-messages');
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
                if (voiceSupported) {
                    setVoiceState('idle', 'Toque no microfone para falar.');
                }
                scrollParaFinal();
            })
            .catch((error) => {
                console.error('Erro:', error);
                indicadorPensando.remove();

                const msgErro = document.createElement('div');
                msgErro.className = 'ia-message ia-message-assistant';
                msgErro.innerHTML = `
                    ${assistantAvatarMarkup()}
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
                setChatBusy(false);
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
            ${assistantAvatarMarkup()}
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
    buildRecognition();

    // Mobile sidebar toggle
    (function() {
        const hamburger = document.getElementById('ia-hamburger');
        const shell = document.getElementById('ia-shell') || document.querySelector('.ia-shell');
        const sidebar = document.getElementById('ia-sidebar');
        const overlay = document.getElementById('ia-sidebar-overlay');

        function openDrawer() {
            if (!shell) return;
            shell.classList.add('drawer-open');
            if (hamburger) hamburger.setAttribute('aria-expanded', 'true');
            if (overlay) { overlay.setAttribute('aria-hidden', 'false'); }
            document.body.style.overflow = 'hidden';
            if (sidebar) {
                const firstLink = sidebar.querySelector('a, button');
                if (firstLink) {
                    try { firstLink.focus(); } catch (e) {}
                }
            }
        }

        function closeDrawer() {
            if (!shell) return;
            shell.classList.remove('drawer-open');
            if (hamburger) hamburger.setAttribute('aria-expanded', 'false');
            if (overlay) { overlay.setAttribute('aria-hidden', 'true'); }
            document.body.style.overflow = '';
            if (hamburger) {
                try { hamburger.focus(); } catch (e) {}
            }
        }

        if (hamburger) {
            hamburger.addEventListener('click', function(e) {
                e.preventDefault();
                if (shell && shell.classList.contains('drawer-open')) {
                    closeDrawer();
                } else {
                    openDrawer();
                }
            });
        }

        if (overlay) {
            overlay.addEventListener('click', function(e) {
                e.preventDefault();
                closeDrawer();
            });
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && shell && shell.classList.contains('drawer-open')) {
                closeDrawer();
            }
        });
    })();
});
