(() => {
    const root = document.getElementById('notifications');
    if (!root) return;
    const bell = document.getElementById('notification-bell');
    const panel = document.getElementById('notification-panel');
    const badge = document.getElementById('notification-badge');
    const list = document.getElementById('notification-list');
    const status = document.getElementById('notification-status');
    const readAll = document.getElementById('notifications-read-all');
    let socket, retry, heartbeat, attempts = 0, stopped = false, unread = 0;
    const connected = () => socket && socket.readyState === WebSocket.OPEN;
    const send = payload => { if (connected()) socket.send(JSON.stringify(payload)); };
    function setOpen(open) {
        panel.hidden = !open;
        bell.setAttribute('aria-expanded', String(open));
        if (open) send({type: 'notifications.sync'});
    }
    bell.addEventListener('click', () => setOpen(panel.hidden));
    document.addEventListener('click', event => { if (!root.contains(event.target)) setOpen(false); });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !panel.hidden) { setOpen(false); bell.focus(); }
    });
    readAll.addEventListener('click', () => send({type: 'notifications.read_all'}));
    function render(data) {
        unread = data.unread_count;
        badge.hidden = !unread;
        badge.textContent = unread > 99 ? '99+' : String(unread);
        bell.setAttribute('aria-label', unread ? `Notificações: ${unread} não lidas` : 'Notificações');
        readAll.disabled = !unread || !connected();
        status.textContent = data.items.length ? 'Atualizado em tempo real' : 'Você ainda não tem notificações.';
        list.replaceChildren();
        data.items.forEach(item => {
            const row = document.createElement('li');
            row.className = item.is_read ? '' : 'unread';
            const title = document.createElement('h3');
            title.textContent = item.title;
            const message = document.createElement('p');
            message.textContent = item.message;
            const time = document.createElement('time');
            time.dateTime = item.created_at;
            time.textContent = new Date(item.created_at).toLocaleString('pt-BR');
            row.append(title, message, time);
            if (!item.is_read) {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = 'Marcar como lida';
                button.disabled = !connected();
                button.addEventListener('click', () => send({type: 'notifications.read', id: item.id}));
                row.append(button);
            }
            list.append(row);
        });
    }
    function connect() {
        if (stopped) return;
        const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
        socket = new WebSocket(`${scheme}//${location.host}/ws/notifications/`);
        socket.onopen = () => {
            attempts = 0;
            heartbeat = setInterval(() => send({type: 'notifications.sync'}), 60000);
        };
        socket.onmessage = event => {
            let data;
            try { data = JSON.parse(event.data); } catch { return; }
            if (data.type === 'notifications.snapshot') render(data);
            if (data.type === 'notifications.error') status.textContent = data.message;
        };
        socket.onclose = event => {
            clearInterval(heartbeat);
            readAll.disabled = true;
            list.querySelectorAll('button').forEach(button => { button.disabled = true; });
            if (event.code === 4401 || event.code === 4403) {
                stopped = true;
                unread = 0;
                badge.hidden = true;
                bell.setAttribute('aria-label', 'Notificações');
                list.replaceChildren();
                status.textContent = 'Sessão encerrada. Entre novamente.';
                return;
            }
            if (stopped) return;
            status.textContent = 'Sem conexão. Tentando reconectar…';
            retry = setTimeout(connect, Math.min(30000, 1000 * 2 ** Math.min(attempts++, 5)) + Math.random() * 500);
        };
    }
    window.addEventListener('pagehide', () => { stopped = true; clearTimeout(retry); clearInterval(heartbeat); if (socket) socket.close(); });
    window.addEventListener('pageshow', event => { if (event.persisted) { stopped = false; connect(); } });
    connect();
})();
