(() => {
    const dialog = document.getElementById('application-mode-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    document.addEventListener('click', event => {
        const trigger = event.target.closest('[data-choose-application-mode]');
        if (!trigger || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button > 0) return;
        event.preventDefault();
        dialog.querySelectorAll('[data-application-mode]').forEach(choice => {
            const url = new URL(trigger.href, window.location.href);
            url.searchParams.set('delivery_mode', choice.dataset.applicationMode);
            choice.href = url.href;
        });
        dialog.showModal();
    });
    dialog.querySelector('[data-close-application-mode]').addEventListener('click', () => dialog.close());
})();
