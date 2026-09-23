(function () {
    var root = document.documentElement;
    var toggle = document.querySelector('.theme-toggle');
    var media = window.matchMedia('(prefers-color-scheme: dark)');
    function updateLabel() {
        if (toggle) toggle.setAttribute('aria-label', root.dataset.theme === 'dark' ? 'Ativar tema claro' : 'Ativar tema escuro');
    }
    updateLabel();
    media.addEventListener('change', function (event) {
        if (root.dataset.themePreference === 'system') { root.dataset.theme = event.matches ? 'dark' : 'light'; updateLabel(); }
    });
    if (toggle) toggle.addEventListener('click', async function () {
        var previous = root.dataset.theme;
        var theme = previous === 'dark' ? 'light' : 'dark';
        root.dataset.theme = theme;
        updateLabel();
        if (root.dataset.themeUrl) {
            toggle.disabled = true;
            try {
                var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
                var response = await fetch(root.dataset.themeUrl, {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'X-CSRFToken': csrf ? csrf.value : '', 'Content-Type': 'application/x-www-form-urlencoded'},
                    body: new URLSearchParams({theme: theme})
                });
                if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('save');
                root.dataset.themePreference = theme;
                var select = document.getElementById('id_theme_preference');
                if (select) select.value = theme;
            } catch (error) {
                root.dataset.theme = previous;
                updateLabel();
                window.alert('Não foi possível salvar o tema. Tente novamente.');
            } finally { toggle.disabled = false; }
        } else {
            try { localStorage.setItem('lumini-theme', theme); } catch (error) {}
        }
    });
}());
