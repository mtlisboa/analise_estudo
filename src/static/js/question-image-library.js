(() => {
  if (window.questionImageLibrary) return;
  const source = document.querySelector('[data-image-library-url]');
  if (!source) return;
  const dialog = document.createElement('dialog'); dialog.className = 'question-image-library';
  dialog.setAttribute('aria-label', 'Selecionar imagem existente');
  const header = document.createElement('div'); header.className = 'image-library-toolbar';
  const title = document.createElement('h2'); title.textContent = 'Imagens das questões';
  const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Fechar'; close.addEventListener('click', () => dialog.close());
  header.append(title, close);
  const search = document.createElement('form'); search.className = 'image-library-toolbar';
  const label = document.createElement('label'); label.textContent = 'Buscar pela descrição';
  const query = document.createElement('input'); query.type = 'search'; query.maxLength = 100; label.append(query);
  const searchButton = document.createElement('button'); searchButton.type = 'submit'; searchButton.textContent = 'Buscar'; search.append(label, searchButton);
  const grid = document.createElement('div'); grid.className = 'image-library-grid';
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const more = document.createElement('button'); more.type = 'button'; more.textContent = 'Carregar mais'; more.hidden = true;
  dialog.append(header, search, grid, status, more); document.body.append(dialog);
  const enlarged = document.createElement('dialog'); enlarged.className = 'question-image-enlarged'; enlarged.setAttribute('aria-label', 'Imagem ampliada');
  const image = document.createElement('img'), caption = document.createElement('p');
  const back = document.createElement('button'); back.type = 'button'; back.textContent = 'Voltar às imagens'; back.addEventListener('click', () => enlarged.close());
  enlarged.append(back, image, caption); document.body.append(enlarged);
  let select = null, cursor = null, controller = null, pending = false, loaded = false;
  function card(asset) {
    const item = document.createElement('article'); item.className = 'image-library-card';
    const thumb = document.createElement('button'); thumb.type = 'button'; thumb.className = 'image-library-thumb';
    thumb.setAttribute('aria-label', 'Selecionar: ' + asset.description);
    const background = document.createElement('img'); background.src = asset.thumbnail; background.alt = ''; background.setAttribute('aria-hidden', 'true'); background.className = 'image-library-blur';
    const foreground = document.createElement('img'); foreground.src = asset.thumbnail; foreground.alt = asset.description; foreground.className = 'image-library-foreground';
    thumb.append(background, foreground);
    const text = document.createElement('p'); text.textContent = asset.description;
    const actions = document.createElement('div'); actions.className = 'image-library-toolbar';
    const choose = document.createElement('button'); choose.type = 'button'; choose.textContent = 'Selecionar';
    const zoom = document.createElement('button'); zoom.type = 'button'; zoom.textContent = 'Ampliar'; zoom.setAttribute('aria-label', 'Ampliar: ' + asset.description);
    const pick = () => { if (select) select(asset); dialog.close(); };
    thumb.addEventListener('click', pick); choose.addEventListener('click', pick);
    zoom.addEventListener('click', () => { image.src = asset.url; image.alt = asset.description; caption.textContent = asset.description; enlarged.showModal(); });
    actions.append(choose, zoom); item.append(thumb, text, actions); grid.append(item);
  }
  async function load(reset = false) {
    if (pending && !reset) return;
    if (reset) { controller?.abort(); cursor = null; grid.replaceChildren(); loaded = false; }
    const current = new AbortController(); controller = current; pending = true; more.disabled = true; status.textContent = 'Carregando imagens…';
    const url = new URL(source.dataset.imageLibraryUrl, location.origin);
    url.searchParams.set('q', query.value.trim()); if (cursor) url.searchParams.set('before', cursor);
    try {
      const response = await fetch(url, {credentials: 'same-origin', signal: current.signal});
      if (!response.ok) throw new Error('Não foi possível carregar as imagens. Tente novamente.');
      const data = await response.json(); if (controller !== current) return;
      data.images.forEach(card); cursor = data.next; loaded = true; more.hidden = !cursor; more.textContent = 'Carregar mais';
      status.textContent = grid.children.length ? '' : 'Nenhuma imagem disponível neste filtro.';
    } catch (error) {
      if (error.name !== 'AbortError' && controller === current) { status.textContent = error.message; more.hidden = false; more.textContent = 'Tentar novamente'; }
    } finally {
      if (controller === current) { pending = false; more.disabled = false; }
    }
  }
  search.addEventListener('submit', event => { event.preventDefault(); load(true); });
  more.addEventListener('click', () => load());
  dialog.addEventListener('close', () => { select = null; if (enlarged.open) enlarged.close(); });
  enlarged.addEventListener('close', () => { image.removeAttribute('src'); });
  window.questionImageLibrary = {open(callback) { select = callback; dialog.showModal(); if (!loaded && !pending) load(true); }};
  // Preload the first page and its small thumbnails before the picker is opened.
  load(true);
})();
