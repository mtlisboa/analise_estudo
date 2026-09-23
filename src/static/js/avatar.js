(() => {
    const input = document.getElementById('id_photo');
    const preview = document.getElementById('avatar-preview');
    const status = document.getElementById('avatar-preview-status');
    if (!input || !preview) return;
    let url;
    input.addEventListener('change', () => {
        if (url) URL.revokeObjectURL(url);
        preview.hidden = true;
        preview.removeAttribute('src');
        status.textContent = '';
        const file = input.files[0];
        if (!file) return;
        if (file.size > 5 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
            status.textContent = 'Escolha uma foto JPG, PNG ou WebP de até 5 MB.';
            input.value = '';
            return;
        }
        url = URL.createObjectURL(file);
        preview.onload = () => { preview.hidden = false; };
        preview.onerror = () => { status.textContent = 'Não foi possível exibir a prévia.'; };
        preview.src = url;
    });
    window.addEventListener('pagehide', () => { if (url) URL.revokeObjectURL(url); });
})();
