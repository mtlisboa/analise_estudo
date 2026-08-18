(function () {
    var root = document.documentElement;
    var toggle = document.querySelector('.theme-toggle');

    function updateLabel() {
        if (!toggle) return;
        var isDark = root.dataset.theme === 'dark';
        toggle.setAttribute('aria-label', isDark ? 'Ativar tema claro' : 'Ativar tema escuro');
    }

    if (toggle) {
        updateLabel();
        toggle.addEventListener('click', function () {
            root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
            localStorage.setItem('lumini-theme', root.dataset.theme);
            updateLabel();
        });
    }
}());
