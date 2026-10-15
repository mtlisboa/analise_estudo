(() => {
    const root = document.querySelector('[data-question-workspace]');
    if (!root) return;
    const preview = root.querySelector('#question-preview-dialog');
    const picker = root.querySelector('#question-picker-dialog');
    const selectedRoot = root.querySelector('[data-selected-questions]');
    let selected = new Map();
    const pickerSelected = root.querySelector('[data-picker-selected]');
    const scores = new Map();
    selectedRoot?.querySelectorAll('[data-selected-id]').forEach(row => selected.set(row.dataset.selectedId, row.querySelector('span').textContent));
    const states = new Map();
    root.querySelectorAll('[data-infinite-list]').forEach(list => states.set(list, {cursor:list.dataset.next || null, loading:false, controller:null, initialized:!list.hasAttribute('data-picker-list')}));
    function syncChecks() {
        picker?.querySelectorAll('[data-select-question]').forEach(input => { input.checked = selected.has(input.value); });
    }
    function announce() {
        const status=root.querySelector('[data-selection-status]');
        if(status) status.textContent='Ordem atualizada. '+selected.size+' questão(ões) selecionada(s).';
    }
    function moveQuestion(id,direction) {
        const ids=Array.from(selected.keys()), index=ids.indexOf(id), next=index+direction;
        if(index<0 || next<0 || next>=ids.length)return;
        [ids[index],ids[next]]=[ids[next],ids[index]];
        selected=new Map(ids.map(key=>[key,selected.get(key)]));renderSelection();announce();
    }
    function selectionRow(id,title,index,modal) {
        const row=document.createElement('div');row.className='selected-question';row.dataset.selectedId=id;
        const position=document.createElement('strong');position.textContent=(index+1)+'.';position.dataset.questionPosition='';
        const label=document.createElement('span');label.textContent=title;
        const controls=document.createElement('div');controls.className='selected-question-actions';
        const action=(text,callback)=>{const button=document.createElement('button');button.type='button';button.textContent=text;button.addEventListener('click',callback);return button;};
        const up=action('Subir',()=>moveQuestion(id,-1)), down=action('Descer',()=>moveQuestion(id,1));
        up.disabled=index===0;down.disabled=index===selected.size-1;
        const show=action('Prévia',()=>{});show.dataset.preview=root.dataset.previewPattern?.replace('987654321',id) || '';
        const remove=action('Remover',()=>{});remove.dataset.removeQuestion=id;
        if(modal) {
            const handle=action('⠿ Arrastar',()=>{});handle.className='question-order-handle';handle.setAttribute('aria-label','Arrastar questão para reordenar');
            let dragging=null;
            handle.addEventListener('pointerdown',event=>{if(event.button!==0)return;dragging={id:event.pointerId,y:event.clientY,moved:false};handle.setPointerCapture(event.pointerId);});
            handle.addEventListener('pointermove',event=>{
                if(!dragging || event.pointerId!==dragging.id)return;
                if(!dragging.moved && Math.abs(event.clientY-dragging.y)<5)return;
                dragging.moved=true;row.classList.add('is-dragging');
                const next=Array.from(pickerSelected.children).find(other=>other!==row && event.clientY<other.getBoundingClientRect().top+other.getBoundingClientRect().height/2);
                pickerSelected.insertBefore(row,next || null);handle.setPointerCapture(event.pointerId);
                const bounds=picker.getBoundingClientRect();
                if(event.clientY<bounds.top+65)picker.scrollBy(0,-15);
                if(event.clientY>bounds.bottom-65)picker.scrollBy(0,15);
            });
            const stop=()=>{if(!dragging)return;dragging=null;row.classList.remove('is-dragging');
                const ids=Array.from(pickerSelected.querySelectorAll('[data-selected-id]'),item=>item.dataset.selectedId);
                selected=new Map(ids.map(key=>[key,selected.get(key)]));renderSelection();announce();
                pickerSelected.querySelector(`[data-selected-id="${id}"] .question-order-handle`)?.focus();};
            handle.addEventListener('pointerup',stop);handle.addEventListener('pointercancel',stop);row.append(handle);
        } else {
            const input=document.createElement('input');input.type='hidden';input.name='questions';input.value=id;row.append(input);
            const scoreLabel=document.createElement('label');scoreLabel.textContent='Pontuação';
            const score=document.createElement('input');score.type='number';score.name=`points_${id}`;score.min='.01';score.max='9999.99';score.step='.01';score.required=true;score.value=scores.get(id) ?? '1';scoreLabel.append(score);controls.append(scoreLabel);
        }
        controls.append(show,up,down,remove);row.append(position,label,controls);return row;
    }
    function renderSelection() {
        if (!selectedRoot) return;
        selectedRoot.querySelectorAll('[data-selected-id]').forEach(row=>{const field=row.querySelector('input[type=number]');if(field)scores.set(row.dataset.selectedId,field.value);});
        selectedRoot.replaceChildren();pickerSelected?.replaceChildren();
        let index=0;
        for(const [id,title] of selected) {
            selectedRoot.append(selectionRow(id,title,index,false));
            pickerSelected?.append(selectionRow(id,title,index,true));index++;
        }
        if(pickerSelected && !selected.size){const empty=document.createElement('p');empty.textContent='Selecione questões na lista abaixo para organizar a sequência.';empty.dataset.selectionEmpty='';pickerSelected.append(empty);}
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
            renderSelection();
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
        if(event.target.matches('[data-picker-search] select[name=scope]')) {const list=picker.querySelector('[data-picker-list]');list.dataset.scope=event.target.value;list.dataset.query=picker.querySelector('[name=q]').value;load(list,true);return;}
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
    if(selectedRoot) renderSelection();
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
