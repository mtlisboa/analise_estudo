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
    var initialMessage = messages.innerHTML;
    var socket;
    var waiting = false;
    var conversationId = window.crypto && window.crypto.randomUUID
        ? window.crypto.randomUUID()
        : String(Date.now());

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
    }

    function finishWaiting() {
        waiting = false;
        thinking.hidden = true;
        setStatus(socket && socket.readyState === WebSocket.OPEN ? 'online' : 'offline',
            socket && socket.readyState === WebSocket.OPEN ? 'Online' : 'Desconectado');
        input.focus();
    }

    function connect() {
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
                setStatus('online', 'Online');
            } else if (payload.type === 'chat.response') {
                addMessage('assistant', payload.message);
                finishWaiting();
            } else if (payload.type === 'chat.error') {
                addMessage('assistant', payload.message || 'Não consegui responder agora. Tente novamente.');
                finishWaiting();
            }
        });

        socket.addEventListener('close', function () {
            finishWaiting();
            setStatus('offline', 'Desconectado');
        });

        socket.addEventListener('error', function () {
            setStatus('offline', 'Erro na conexão');
        });
    }

    function sendMessage(text) {
        var message = text.trim();
        if (!message || !socket || socket.readyState !== WebSocket.OPEN || waiting) return;

        addMessage('user', message);
        socket.send(JSON.stringify({
            type: 'chat.message',
            message: message,
            conversation_id: conversationId
        }));
        input.value = '';
        input.style.height = '';
        waiting = true;
        thinking.hidden = false;
        sendButton.disabled = true;
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
            input.value = button.dataset.chatSuggestion;
            input.dispatchEvent(new Event('input'));
            input.focus();
        });
    });

    clearButton.addEventListener('click', function () {
        messages.innerHTML = initialMessage;
        conversationId = window.crypto && window.crypto.randomUUID
            ? window.crypto.randomUUID()
            : String(Date.now());
        input.focus();
    });

    connect();
}());
