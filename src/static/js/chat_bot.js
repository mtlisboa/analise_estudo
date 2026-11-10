(function () {
    var root = document.querySelector('[data-chat-root]');
    if (!root) return;

    var form = root.querySelector('[data-chat-form]');
    var input = root.querySelector('[data-chat-input]');
    var sendButton = root.querySelector('[data-chat-send]');
    var messages = root.querySelector('[data-chat-messages]');
    var thinking = root.querySelector('[data-chat-thinking]');
    var status = root.querySelector('[data-chat-status]');
    var clearButton = root.querySelector('[data-chat-clear]');
    var diagnosticPromptElement = document.getElementById('diagnostic-prompt');
    var diagnosticPrompt = diagnosticPromptElement ? JSON.parse(diagnosticPromptElement.textContent) : '';
    var diagnosticStarted = false;
    var initialMessage = messages.innerHTML;
    var socket;
    var waiting = false;
    var mode = 'doubts';
    var modeButtons = root.querySelectorAll('[data-chat-mode]');
    function selectMode(value) {
        if (waiting || (value !== 'assembly' && value !== 'doubts')) return;
        mode = value;
        modeButtons.forEach(function (button) {
            button.setAttribute('aria-pressed', String(button.dataset.chatMode === mode));
        });
        var hint = root.querySelector('[data-chat-mode-hint]');
        if (hint) hint.textContent = mode === 'assembly'
            ? 'Crie questões, edite uma questão existente ou monte um questionário.'
            : 'Tire dúvidas sobre conteúdos, o aplicativo e seus resultados.';
        input.placeholder = mode === 'assembly' ? 'Descreva a atividade ou a questão que deseja preparar…' : 'Qual é sua dúvida?';
    }
    modeButtons.forEach(function (button) {
        button.addEventListener('click', function () { selectMode(button.dataset.chatMode); });
    });
    var conversationId = null;
    var responseTimer;
    var partialCopy = null;
    var oldestId = null;
    var olderButton = document.createElement('button');
    olderButton.type = 'button';
    olderButton.textContent = 'Carregar mensagens anteriores';
    olderButton.hidden = true;
    messages.parentNode.insertBefore(olderButton, messages);
    olderButton.addEventListener('click', function () {
        if (socket && socket.readyState === WebSocket.OPEN && oldestId) {
            socket.send(JSON.stringify({type: 'chat.history', before: oldestId}));
        }
    });
    var timeoutMs = 130000;
    var reconnect = document.createElement('button');
    reconnect.type = 'button';
    reconnect.textContent = 'Reconectar';
    reconnect.hidden = true;
    status.appendChild(reconnect);
    reconnect.addEventListener('click', connect);

    function startWaiting(limit) {
        window.clearTimeout(responseTimer);
        waiting = true;
        modeButtons.forEach(function (button) { button.disabled = true; });
        thinking.hidden = false;
        if (thinking.querySelector('small')) thinking.querySelector('small').textContent = 'Preparando resposta…';
        sendButton.disabled = true;
        responseTimer = window.setTimeout(function () {
            finishWaiting();
            addMessage('assistant', 'A conexão não trouxe uma resposta no prazo. Reconecte para recuperar o histórico e tentar novamente.');
            if (socket) socket.close();
        }, limit || timeoutMs);
    }

    function setStatus(state, label) {
        status.dataset.state = state;
        status.querySelector('strong').textContent = label;
        sendButton.disabled = state !== 'online' || waiting || !input.value.trim();
    }

    function scrollToLatest() {
        messages.scrollTop = messages.scrollHeight;
    }

    function addMessage(role, text) {
        var wrapper = document.createElement('div');
        var copy = document.createElement('div');
        var paragraph = document.createElement('p');
        wrapper.className = 'chat-message ' + (role === 'user' ? 'user-message' : 'assistant-message');

        if (role === 'assistant') {
            var avatar = document.createElement('span');
            var label = document.createElement('small');
            avatar.className = 'message-avatar';
            avatar.setAttribute('aria-hidden', 'true');
            avatar.textContent = '✦';
            label.textContent = 'Assistente Lumini';
            wrapper.appendChild(avatar);
            copy.appendChild(label);
        }

        paragraph.textContent = text;
        copy.appendChild(paragraph);
        wrapper.appendChild(copy);
        messages.appendChild(wrapper);
        scrollToLatest();
        return copy;
    }

    function element(parent, tag, text) {
        var node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        parent.appendChild(node);
        return node;
    }

    function table(parent, title, rows, columns) {
        if (!rows || !rows.length) return;
        element(parent, 'h4', title);
        var scroll = element(parent, 'div');
        scroll.className = 'chat-table-scroll';
        var grid = element(scroll, 'table');
        var header = element(element(grid, 'thead'), 'tr');
        columns.forEach(function (c) { element(header, 'th', c[1]); });
        var body = element(grid, 'tbody');
        rows.forEach(function (row) {
            var tr = element(body, 'tr');
            columns.forEach(function (c) {
                var value = row[c[0]];
                element(tr, 'td', value === null || value === undefined ? 'Sem dados' : String(value));
            });
        });
    }

    function renderMetadata(parent, metadata) {
        if (metadata.mode) element(parent, 'small', metadata.mode === 'assembly' ? 'Montagem' : 'Dúvidas');
        if (metadata.url && metadata.url.charAt(0) === '/' && metadata.url.charAt(1) !== '/') {
            var link = element(parent, 'a', 'Abrir no aplicativo');
            link.href = metadata.url;
        }
        if (metadata.sources) element(parent, 'small', 'Fontes consultadas: ' + metadata.sources.join('; '));
        if (metadata.data) {
            var details = element(parent, 'details');
            element(details, 'summary', 'Ver dados consultados e limites');
            element(details, 'p', metadata.data.limits);
            table(details, 'Meus resultados revisados', metadata.data.results, [['publication__title', 'Atividade'], ['score', 'Nota'], ['maximum_score', 'Máximo']]);
            table(details, 'Minhas autoavaliações', metadata.data.self_assessments, [['created_at', 'Data'], ['focus', 'Foco'], ['organization', 'Organização'], ['comprehension', 'Compreensão'], ['motivation', 'Motivação']]);
            var report = metadata.data.institutional_analysis;
            if (report && typeof report === 'object') {
                element(details, 'p', (report.demo ? 'Dados de demonstração. ' : 'Registros internos autorizados. ') + report.method);
                table(details, 'Indicadores', report.metrics, [[0, 'Indicador'], [1, 'Valor']]);
                table(details, 'Distribuição', report.distribution, [['label', 'Faixa'], ['count', 'Quantidade']]);
                table(details, 'Evolução', report.timeline, [['date', 'Data'], ['average', 'Média (%)'], ['count', 'Registros']]);
                table(details, 'Alunos (até 30)', report.students, [['name', 'Aluno'], ['total', 'Registros'], ['average', 'Média (%)']]);
            }
        }
        if (metadata.consultations && metadata.consultations.length) {
            var queries = element(parent, 'details');
            element(queries, 'summary', 'Consultas adicionais realizadas');
            metadata.consultations.forEach(function (entry) {
                var r = entry.result;
                if (r.error) { element(queries, 'p', r.error); return; }
                if (r.metrics) {
                    element(queries, 'p', 'Análise do recorte solicitado. ' + r.method);
                    table(queries, 'Indicadores', r.metrics, [[0, 'Indicador'], [1, 'Valor']]);
                    table(queries, 'Evolução (até 30 datas)', r.timeline, [['date', 'Data'], ['average', 'Média (%)']]);
                    table(queries, 'Alunos (até 30)', r.student_rows, [['name', 'Aluno'], ['average', 'Média (%)']]);
                    table(queries, 'Hipóteses de erro (até 30)', r.hypotheses, [['student', 'Aluno'], ['hypothesis', 'Hipótese'], ['count', 'Ocorrências']]);
                } else if (r.results || r.self_assessments) {
                    table(queries, 'Resultados revisados', r.results, [['publication__title', 'Atividade'], ['score', 'Nota'], ['maximum_score', 'Máximo']]);
                    table(queries, 'Autoavaliações', r.self_assessments, [['created_at', 'Data'], ['focus', 'Foco'], ['comprehension', 'Compreensão']]);
                } else if (r.questions) {
                    table(queries, r.topic || 'Questões consultadas (até 30)', r.questions, [['id', 'Código'], ['statement', 'Enunciado']]);
                } else if (r.statement) {
                    element(queries, 'p', 'Questão ' + r.id + ': ' + r.statement);
                }

            });
        }
        if (metadata.proposal) {
            var p = metadata.proposal;
            var preview = element(parent, 'section');
            preview.className = 'chat-proposal';
            element(preview, 'h4', p.action === 'edit_question' ? 'Revisar nova versão da questão' : 'Revisar antes de salvar');
            element(preview, 'p', p.subject + ' — ' + p.topic);
            if (p.source_id) element(preview, 'p', 'Questão de origem: ' + p.source_id + '. Será salva uma nova versão.');
            if (p.question_ids && p.question_ids.length) element(preview, 'p', 'Questões do banco: ' + p.question_ids.join(', '));
            var questions = p.question ? [p.question] : (p.selected_questions || []).concat(p.questions || []);
            questions.forEach(function (q, i) {
                element(preview, 'h4', 'Questão ' + (i + 1) + ' · ' + q.points + ' ponto(s)');
                if (q.support_text) element(preview, 'p', q.support_text);
                element(preview, 'p', q.statement);
                var alternatives = element(preview, 'ol');
                (q.options || []).forEach(function (o) { element(alternatives, 'li', o); });
                element(preview, 'p', 'Resposta: ' + q.correct_answer);
                element(preview, 'p', q.explanation);
            });
            element(preview, 'small', 'Não será publicada ou aplicada aos alunos. Proposta válida por 10 minutos nesta conexão.');
            var save = element(preview, 'button', 'Salvar no aplicativo');
            save.type = 'button';
            if (!metadata.confirmation_token) {
                save.disabled = true;
                save.textContent = 'Proposta anterior — solicite uma nova para salvar';
            }
            save.dataset.chatConfirm = 'true';
            save.addEventListener('click', function () {
                if (waiting || !socket || socket.readyState !== WebSocket.OPEN) return;
                save.disabled = true;
                startWaiting();
                socket.send(JSON.stringify({type: 'chat.confirm', token: metadata.confirmation_token, conversation_id: conversationId}));
            });
        }
        scrollToLatest();
    }

    function removePartial() {
        if (partialCopy) partialCopy.parentNode.remove();
        partialCopy = null;
    }

    function finishWaiting() {
        removePartial();
        window.clearTimeout(responseTimer);
        waiting = false;
        modeButtons.forEach(function (button) { button.disabled = false; });
        thinking.hidden = true;
        setStatus(socket && socket.readyState === WebSocket.OPEN ? 'online' : 'offline',
            socket && socket.readyState === WebSocket.OPEN ? 'Online' : 'Desconectado');
        input.focus();
    }

    function connect() {
        if (socket && socket.readyState === WebSocket.OPEN) return;
        reconnect.hidden = true;
        var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        setStatus('connecting', 'Conectando');
        socket = new WebSocket(protocol + '//' + window.location.host + root.dataset.websocketPath);

        socket.addEventListener('message', function (event) {
            var payload;
            try {
                payload = JSON.parse(event.data);
            } catch (error) {
                addMessage('assistant', 'Recebi uma resposta em formato inesperado.');
                finishWaiting();
                return;
            }

            if (payload.type === 'chat.ready') {
                conversationId = payload.conversation_id;
                timeoutMs = (Number(payload.timeout_seconds) || 120) * 1000 + 10000;
                messages.innerHTML = initialMessage;
                (payload.messages || []).forEach(function (row) {
                    var copy = addMessage(row.role, row.content);
                    if (row.role === 'assistant') {
                        try { renderMetadata(copy, row.metadata || {}); } catch (error) { /* Text remains readable. */ }
                    }
                });
                var restored = payload.messages || [];
                var lastMode = restored.length ? (restored[restored.length - 1].metadata || {}).mode : null;
                oldestId = restored.length ? restored[0].id : null;
                olderButton.hidden = (payload.messages || []).length < 200;
                finishWaiting();
                if (lastMode) selectMode(lastMode);
            } else if (payload.type === 'chat.history') {
                var anchor = messages.firstChild;
                var previousHeight = messages.scrollHeight;
                (payload.messages || []).forEach(function (row) {
                    var copy = addMessage(row.role, row.content);
                    try { if (row.role === 'assistant') renderMetadata(copy, row.metadata || {}); } catch (error) {}
                    messages.insertBefore(copy.parentNode, anchor);
                });
                if ((payload.messages || []).length) oldestId = payload.messages[0].id;
                olderButton.hidden = (payload.messages || []).length < 200;
                messages.scrollTop = messages.scrollHeight - previousHeight;
                return;
            } else if (payload.type === 'chat.cleared') {
                conversationId = payload.conversation_id;
                olderButton.hidden = true;
                oldestId = null;
                messages.innerHTML = initialMessage;
                finishWaiting();
                return;
            }
            if (payload.conversation_id && payload.conversation_id !== conversationId) return;

            if (payload.type === 'chat.ready') {
                setStatus('online', 'Online');
                if (diagnosticPrompt && !diagnosticStarted && !(payload.messages || []).length) {
                    diagnosticStarted = true;
                    sendMessage(diagnosticPrompt);
                }
            } else if (payload.type === 'chat.delta') {
                if (!waiting) return;
                if (!partialCopy) partialCopy = addMessage('assistant', '');
                partialCopy.querySelector('p').textContent = payload.message;
                if (thinking.querySelector('small')) thinking.querySelector('small').textContent = 'Gerando resposta…';
                scrollToLatest();
            } else if (payload.type === 'chat.response') {
                removePartial();
                var copy = addMessage('assistant', payload.message);
                try {
                    renderMetadata(copy, payload.metadata || {});
                } catch (error) {
                    element(copy, 'small', 'Não foi possível exibir os detalhes desta resposta.');
                } finally {
                    finishWaiting();
                }
            } else if (payload.type === 'chat.error') {
                addMessage('assistant', payload.message || 'Não consegui responder agora. Tente novamente.');
                finishWaiting();
            }
        });

        socket.addEventListener('close', function () {
            finishWaiting();
            setStatus('offline', 'Desconectado');
            reconnect.hidden = false;
        });

        socket.addEventListener('error', function () {
            finishWaiting();
            reconnect.hidden = false;
            setStatus('offline', 'Erro na conexão');
            socket.close();
        });
    }

    function sendMessage(text) {
        var message = text.trim();
        if (!message || !socket || socket.readyState !== WebSocket.OPEN || waiting) return;

        root.querySelectorAll('[data-chat-confirm]').forEach(function (button) { button.disabled = true; });
        addMessage('user', message);
        socket.send(JSON.stringify({
            type: 'chat.message',
            message: message,
            conversation_id: conversationId,
            mode: mode
        }));
        input.value = '';
        input.style.height = '';
        startWaiting();
        scrollToLatest();
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        sendMessage(input.value);
    });

    input.addEventListener('input', function () {
        input.style.height = '';
        input.style.height = Math.min(input.scrollHeight, 130) + 'px';
        sendButton.disabled = !input.value.trim() || waiting || !socket || socket.readyState !== WebSocket.OPEN;
    });

    input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage(input.value);
        }
    });

    root.querySelectorAll('[data-chat-suggestion]').forEach(function (button) {
        button.addEventListener('click', function () {
            if (waiting) return;
            selectMode(button.dataset.suggestionMode || 'doubts');
            input.value = button.dataset.chatSuggestion;
            input.dispatchEvent(new Event('input'));
            input.focus();
        });
    });

    clearButton.addEventListener('click', function () {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            addMessage('assistant', 'Reconecte antes de limpar o histórico salvo.');
            return;
        }
        if (!window.confirm('Apagar o histórico desta conversa? Questões e atividades já salvas serão mantidas.')) return;
        root.querySelectorAll('[data-chat-confirm]').forEach(function (button) { button.disabled = true; });
        socket.send(JSON.stringify({type: 'chat.clear'}));
        startWaiting(10000);
    });

    selectMode('doubts');
    connect();
}());
