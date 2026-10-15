(() => {
    const form = document.querySelector('[data-application-form]');
    if (!form) return;
    const mode = form.querySelector('[name="delivery_mode"]');
    const settings = form.querySelector('[data-virtual-settings]');
    const deadline = form.querySelector('[name="due_at"]');
    const sync = () => {
        const virtual = mode.value === 'online';
        settings.hidden = !virtual;
        settings.disabled = !virtual;
        deadline.required = virtual;
    };
    mode.addEventListener('change', sync);
    sync();
})();
