(() => {
    const dialog = document.querySelector('[data-print-dialog]');
    if (!dialog) return;
    const frame = dialog.querySelector('[data-print-frame]');
    const status = dialog.querySelector('[data-print-status]');
    const open = dialog.querySelector('[data-print-open]');
    dialog.querySelector('[data-close-print]').addEventListener('click', () => dialog.close());
    let objectUrl;
    let loading = false;
    document.querySelectorAll('[data-preview-pdf]').forEach(link => {
        link.addEventListener('click', async event => {
            event.preventDefault();
            if (loading) return;
            loading = true;
            frame.hidden = true;
            open.href = link.href;
            open.hidden = false;
            status.textContent = 'Carregando documento salvo do aluno…';
            dialog.showModal();
            try {
                const response = await fetch(link.href, {credentials: 'same-origin'});
                if (!response.ok || !(response.headers.get('content-type') || '').includes('application/pdf')) {
                    throw new Error('Não foi possível carregar o documento. Verifique seu acesso e tente novamente.');
                }
                if (objectUrl) URL.revokeObjectURL(objectUrl);
                objectUrl = URL.createObjectURL(await response.blob());
                frame.src = objectUrl;
                frame.hidden = false;
                status.textContent = 'Documento pronto para reimpressão.';
            } catch (error) {
                status.textContent = error.message;
            } finally {
                loading = false;
            }
        });
    });
})();
