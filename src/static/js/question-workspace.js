(() => {
    const root = document.querySelector('[data-question-workspace]');
    if (!root) return;
    const preview = root.querySelector('#question-preview-dialog');
    const picker = root.querySelector('#question-picker-dialog');
    const selectedRoot = root.querySelector('[data-selected-questions]');
    const selected = new Map();
    const scores = new Map();
    selectedRoot?.querySelectorAll('[data-selected-id]').forEach(row => selected.set(row.dataset.selectedId, row.querySelector('span').textContent));
    const states = new Map();
    root.querySelectorAll('[data-infinite-list]').forEach(list => states.set(list, {cursor:list.dataset.next || null, loading:false, controller:null, initialized:!list.hasAttribute('data-picker-list')}));
    function syncChecks() {
        picker?.querySelectorAll('[data-select-question]').forEach(input => { input.checked = selected.has(input.value); });
    }
    function renderSelection() {
        if (!selectedRoot) return;
        selectedRoot.querySelectorAll('[data-selected-id]').forEach(row=>{ const field=row.querySelector('input[type=number]');if(field)scores.set(row.dataset.selectedId,field.value); });
        selectedRoot.replaceChildren();
        for (const [id, title] of selected) {
            const row = document.createElement('div'); row.className = 'selected-question'; row.dataset.selectedId = id;
            const input = document.createElement('input'); input.type = 'hidden'; input.name = 'questions'; input.value = id;
            const label = document.createElement('span'); label.textContent = title;
            const button = document.createElement('button'); button.type = 'button'; button.dataset.removeQuestion = id; button.textContent = 'Remover';
            const scoreLabel=document.createElement('label');scoreLabel.textContent='Pontuação';
            const score=document.createElement('input');score.type='number';score.name=`points_${id}`;score.min='.01';score.max='9999.99';score.step='.01';score.required=true;score.value=scores.get(id) || '1';scoreLabel.append(score);
            row.append(input,label,scoreLabel,button); selectedRoot.append(row);
        }
        syncChecks();
    }
    async function load(list, reset=false) {
        const state = states.get(list);
        const container = list.parentElement;
        const button = container.querySelector('[data-load-more]');
        const status = container.querySelector('[data-list-status]');
        if (reset) { state.controller?.abort(); state.loading=false; state.cursor=null; state.initialized=false; list.replaceChildren(); }
        if (state.loading || (state.initialized && !state.cursor)) return;
        state.loading=true;
        state.controller=new AbortController();
        const controller=state.controller;
        if (button) button.disabled=true;
        status.textContent='Carregando questões…';
        const url=new URL(list.dataset.url, location.origin);
        url.searchParams.set('fragment','1'); url.searchParams.set('scope',list.dataset.scope || 'public');
        url.searchParams.set('q',list.dataset.query || '');
        if (state.cursor) url.searchParams.set('before',state.cursor);
        if (list.hasAttribute('data-picker-list')) { url.searchParams.set('select','1'); url.searchParams.set('subject',document.getElementById('id_subject').value); }
        try {
            const response=await fetch(url,{credentials:'same-origin',signal:controller.signal});
            if (!response.ok) throw new Error('Não foi possível carregar as questões. Tente novamente.');
            const data=await response.json();
            if (state.controller !== controller) return;
            list.insertAdjacentHTML('beforeend',data.html);
            state.cursor=data.next; state.initialized=true;
            status.textContent=data.next ? '' : 'Todas as questões deste filtro foram carregadas.';
            button.hidden=!data.next;
            syncChecks();
        } catch (error) {
            if (error.name !== 'AbortError') { status.textContent=error.message; button.hidden=false; }
        } finally {
            if (state.controller === controller) { state.loading=false; button.disabled=false; }
        }
    }
    root.addEventListener('click', async event => {
        const close=event.target.closest('[data-close-dialog]');
        if (close) { close.closest('dialog').close(); return; }
        const remove=event.target.closest('[data-remove-question]');
        if (remove) { selected.delete(remove.dataset.removeQuestion); renderSelection(); return; }
        if (event.target.closest('[data-open-picker]')) {
            const subject=document.getElementById('id_subject').value.trim();
            if (!subject) { document.getElementById('id_subject').reportValidity(); document.getElementById('id_subject').focus(); return; }
            picker.showModal(); await load(picker.querySelector('[data-picker-list]'),true); return;
        }
        const more=event.target.closest('[data-load-more]');
        if (more) { await load(more.parentElement.querySelector('[data-infinite-list]')); return; }
        const trigger=event.target.closest('[data-preview]');
        if (trigger) {
            const body=preview.querySelector('[data-preview-body]'); body.textContent='Carregando prévia…';
            preview.showModal();
            try {
                const response=await fetch(trigger.dataset.preview,{credentials:'same-origin'});
                if (!response.ok) throw new Error('Não foi possível abrir esta questão.');
                body.innerHTML=await response.text();
                window.renderQuestionMath?.(body);
            } catch (error) { body.textContent=error.message; }
        }
    });
    root.addEventListener('change',event => {
        if (!event.target.matches('[data-select-question]')) return;
        const row=event.target.closest('[data-question-id]');
        if (event.target.checked) selected.set(event.target.value,row.dataset.title); else selected.delete(event.target.value);
        renderSelection();
    });
    root.querySelector('[data-picker-search]')?.addEventListener('submit',event => {
        event.preventDefault();
        const list=picker.querySelector('[data-picker-list]');
        list.dataset.query=event.target.elements.q.value;
        list.dataset.scope=event.target.elements.scope.value;
        load(list,true);
    });
    if ('IntersectionObserver' in window) {
        states.forEach((state,list) => {
            const button=list.parentElement.querySelector('[data-load-more]');
            const observer=new IntersectionObserver(entries => {
                if (entries.some(entry => entry.isIntersecting) && (!picker?.contains(list) || picker.open)) load(list);
            },{root:picker?.contains(list) ? picker : null, rootMargin:'150px'});
            observer.observe(button);
        });
    }
})();
