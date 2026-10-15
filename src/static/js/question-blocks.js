(() => {
  function init(editor) {
    if (editor.dataset.initialized) return;
    const input = editor.querySelector('[data-content-blocks-input]');
    let initial;
    try { initial = JSON.parse(input.value || '[]'); } catch (_) { return; }
    if (!Array.isArray(initial)) return;
    editor.dataset.initialized = 'true';
    const form = editor.closest('form'), list = editor.querySelector('[data-block-list]');
    const status = editor.querySelector('[data-block-status]');
    const urls = new Set();
    function sync() {
      input.value = JSON.stringify(Array.from(list.children, row => {
        if (row.dataset.type === 'text') return {type: 'text', text: row.querySelector('textarea').value};
        if (row.dataset.imageId) return {type: 'image', id: Number(row.dataset.imageId)};
        return {type: 'image', upload: row.querySelector('input[type=file]').name,
          description: row.querySelector('input[type=text]').value};
      }));
      Array.from(list.children).forEach((row, i) => {
        row.querySelector('[data-block-heading]').textContent = `${i + 1}. ${row.dataset.type === 'text' ? 'Parágrafo' : 'Imagem'}`;
        row.querySelector('[data-up]').disabled = i === 0;
        row.querySelector('[data-down]').disabled = i === list.children.length - 1;
      });
    }
    function button(text, action) {
      const node = document.createElement('button');
      node.type = 'button'; node.textContent = text;
      node.addEventListener('click', action); return node;
    }
    function move(row, direction) {
      const target = direction < 0 ? row.previousElementSibling : row.nextElementSibling;
      if (!target) return;
      if (direction < 0) list.insertBefore(row, target); else list.insertBefore(target, row);
      sync(); status.textContent = 'Ordem dos blocos atualizada.';
    }
    function add(block, focus = false) {
      if (list.children.length >= 50) { status.textContent = 'Limite de 50 blocos.'; return; }
      if (block.type === 'image' && list.querySelectorAll('[data-type=image]').length >= 5) {
        status.textContent = 'Limite de cinco imagens por questão.'; return;
      }
      const row = document.createElement('section'); row.className = 'content-block'; row.dataset.type = block.type;
      const toolbar = document.createElement('div'); toolbar.className = 'content-block-toolbar';
      const handle = button('⠿ Arrastar', () => {}); handle.className = 'content-block-handle';
      handle.setAttribute('aria-label', 'Arrastar bloco para reordenar');
      const title = document.createElement('strong'); title.dataset.blockHeading = '';
      const up = button('Subir', () => move(row, -1)); up.dataset.up = '';
      const down = button('Descer', () => move(row, 1)); down.dataset.down = '';
      const remove = button('Remover', () => {
        if (row.dataset.previewUrl) { URL.revokeObjectURL(row.dataset.previewUrl); urls.delete(row.dataset.previewUrl); }
        row.remove(); sync(); status.textContent = 'Bloco removido.';
      });
      toolbar.append(handle, title, up, down, remove); row.append(toolbar);
      if (block.type === 'text') {
        const label = document.createElement('label'); label.textContent = 'Texto do parágrafo';
        const text = document.createElement('textarea'); text.rows = 4; text.maxLength = 15000; text.required = true;
        text.value = block.text || ''; label.append(text); row.append(label);
      } else {
        const picture = document.createElement('img'); picture.className = 'content-block-preview';
        if (block.id) {
          row.dataset.imageId = block.id;
          picture.src = editor.dataset.imagePattern.replace('987654321', String(block.id));
          picture.alt = block.description || 'Imagem da questão';
          row.append(picture);
        } else {
          const label = document.createElement('label'); label.textContent = 'Arquivo da imagem';
          const file = document.createElement('input'); file.type = 'file';
          file.accept = 'image/png,image/jpeg,image/webp'; file.required = true;
          file.name = block.upload || ('block_image_' + (window.crypto?.randomUUID ? window.crypto.randomUUID() : Date.now() + '_' + Math.random().toString(36).slice(2)));
          file.addEventListener('change', () => {
            if (row.dataset.previewUrl) { URL.revokeObjectURL(row.dataset.previewUrl); urls.delete(row.dataset.previewUrl); }
            picture.hidden = !file.files.length;
            if (file.files.length) { const url = URL.createObjectURL(file.files[0]); urls.add(url); row.dataset.previewUrl = url; picture.src = url; }
          });
          picture.hidden = true;
          const description = document.createElement('label'); description.textContent = 'Descrição da imagem';
          const alt = document.createElement('input'); alt.type = 'text'; alt.maxLength = 300; alt.required = true;
          alt.value = block.description || ''; description.append(alt);
          label.append(file); row.append(label, description, picture);
        }
      }
      let drag = null;
      handle.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        drag = {id: event.pointerId, y: event.clientY, moved: false}; handle.setPointerCapture(event.pointerId);
      });
      handle.addEventListener('pointermove', event => {
        if (!drag || drag.id !== event.pointerId) return;
        if (!drag.moved && Math.abs(event.clientY - drag.y) < 5) return;
        drag.moved = true; row.classList.add('is-dragging');
        const next = Array.from(list.children).find(other => other !== row && event.clientY < other.getBoundingClientRect().top + other.getBoundingClientRect().height / 2);
        list.insertBefore(row, next || null);
        handle.setPointerCapture(event.pointerId);
        if (event.clientY < 70) window.scrollBy(0, -15);
        if (event.clientY > window.innerHeight - 70) window.scrollBy(0, 15);
      });
      const end = () => { if (!drag) return; drag = null; row.classList.remove('is-dragging'); sync(); status.textContent = 'Ordem dos blocos atualizada.'; };
      handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end);
      row.addEventListener('input', sync); list.append(row); sync();
      if (focus) row.querySelector('textarea,input')?.focus();
    }
    initial.forEach(block => add(block));
    editor.querySelector('[data-add-text]').addEventListener('click', () => add({type: 'text'}, true));
    editor.querySelector('[data-add-image]').addEventListener('click', () => add({type: 'image'}, true));
    form.addEventListener('submit', sync);
    ['support_text', 'new_images', 'image_description', 'remove_images'].forEach(name => {
      Array.from(form.elements).filter(field => field.name === name || field.name.endsWith('-' + name)).forEach(field => {
        field.disabled = true;
        const container = field.closest('.form-field') || field.closest('p');
        if (container) container.hidden = true; else field.hidden = true;
      });
    });
    form.querySelectorAll('.question-image-preview').forEach(figure => figure.hidden = true);
    input.hidden = true; editor.querySelector('[data-block-controls]').hidden = false;
    window.addEventListener('pagehide', () => urls.forEach(url => URL.revokeObjectURL(url)), {once: true});
  }
  function boot() { document.querySelectorAll('[data-content-block-editor]').forEach(init); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
