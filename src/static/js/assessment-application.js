(() => {
    const form = document.querySelector('[data-application-form]');
    if (!form) return;
    const mode = form.querySelector('[name="delivery_mode"]');
    const settings = form.querySelector('[data-virtual-settings]');
    const deadline = form.querySelector('[name="due_at"]');
    const kind = form.querySelector('[name="kind"]');
    const physicalSettings = form.querySelector('[data-physical-exam-settings]');
    const sync = () => {
        const action = form.querySelector('[data-confirm-application]');
        if (action) action.textContent = mode.value === 'printed' ? 'Imprimir' : 'Confirmar aplicação';
        const virtual = mode.value === 'online';
        settings.hidden = !virtual;
        settings.disabled = !virtual;
        deadline.required = virtual;
        const physicalExam = !virtual && kind.value === 'EXAM';
        physicalSettings.hidden = !physicalExam;
        physicalSettings.disabled = !physicalExam;
    };
    mode.addEventListener('change', sync);
    kind.addEventListener('change', sync);
    sync();

    const picker = form.querySelector('#application-offer-dialog');
    if (!picker) return;
    const rows = [...picker.querySelectorAll('[data-offer-choice]')];
    const search = picker.querySelector('[data-offer-search]');
    const summary = form.querySelector('[data-offers-summary]');
    const selectedList = form.querySelector('[data-selected-offers]');
    const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
    const update = () => {
        const selected = rows.filter(row => row.querySelector('input').checked);
        summary.textContent = `${selected.length} de ${rows.length} turmas selecionadas.`;
        selectedList.replaceChildren();
        selected.forEach(row => {
            const label = document.createElement('p');
            label.textContent = row.querySelector('span').textContent;
            selectedList.append(label);
        });
    };
    const filter = () => {
        const query = normalize(search.value.trim());
        rows.forEach(row => { row.hidden = !normalize(row.textContent).includes(query); });
        const count = rows.filter(row => !row.hidden).length;
        picker.querySelector('[data-offer-search-status]').textContent = count ? `${count} turmas encontradas.` : 'Nenhuma turma encontrada.';
    };
    form.querySelector('[data-open-offer-picker]').addEventListener('click', () => {
        search.value = '';
        filter();
        picker.showModal();
        search.focus();
    });
    picker.querySelector('[data-close-offer-picker]').addEventListener('click', () => picker.close());
    search.addEventListener('input', filter);
    search.addEventListener('keydown', event => { if (event.key === 'Enter') event.preventDefault(); });
    picker.addEventListener('change', update);
    picker.querySelector('[data-select-all-offers]').addEventListener('click', () => {
        rows.forEach(row => { row.querySelector('input').checked = true; });
        update();
    });
    picker.querySelector('[data-select-matching-offers]').addEventListener('click', () => {
        rows.filter(row => !row.hidden).forEach(row => { row.querySelector('input').checked = true; });
        update();
    });
    picker.querySelector('[data-clear-offers]').addEventListener('click', () => {
        rows.forEach(row => { row.querySelector('input').checked = false; });
        update();
    });
    form.addEventListener('submit', event => {
        if (!rows.some(row => row.querySelector('input').checked)) {
            event.preventDefault();
            picker.showModal();
            picker.querySelector('[data-offer-search-status]').textContent = 'Selecione pelo menos uma turma.';
        }
    });
    update();
})();
