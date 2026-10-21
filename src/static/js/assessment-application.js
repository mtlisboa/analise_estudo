(() => {
    const form = document.querySelector('[data-application-form]');
    if (!form) return;
    const totalPoints = form.querySelector('[data-total-points]');
    const questionPoints = [...form.querySelectorAll('[data-question-points]')];
    const pointsStatus = form.querySelector('[data-points-status]');
    const toCents = value => {
        if (!/^\d+(\.\d{1,2})?$/.test(value)) return null;
        const [whole, fraction = ''] = value.split('.');
        const cents = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
        return Number.isSafeInteger(cents) ? cents : null;
    };
    if (totalPoints && questionPoints.length) {
        totalPoints.addEventListener('change', () => {
            const cents = toCents(totalPoints.value);
            if (cents === null || cents < questionPoints.length) {
                totalPoints.setCustomValidity('Informe um total que permita pelo menos 0,01 ponto por questão.');
                pointsStatus.textContent = totalPoints.validationMessage;
                return;
            }
            totalPoints.setCustomValidity('');
            const each = Math.floor(cents / questionPoints.length);
            const remainder = cents % questionPoints.length;
            questionPoints.forEach((input, index) => {
                input.value = ((each + (index < remainder ? 1 : 0)) / 100).toFixed(2);
            });
            pointsStatus.textContent = 'Total distribuído entre as questões. Você pode ajustar cada valor.';
        });
        questionPoints.forEach(input => input.addEventListener('input', () => {
            const values = questionPoints.map(field => toCents(field.value));
            if (values.some(value => value === null || value < 1)) return;
            totalPoints.setCustomValidity('');
            totalPoints.value = (values.reduce((sum, value) => sum + value, 0) / 100).toFixed(2);
            pointsStatus.textContent = 'Pontuação total atualizada pela soma das questões.';
        }));
    }
    const scoreDialog = form.querySelector('#application-score-dialog');
    const scoreList = form.querySelector('[data-application-score-list]');
    if (scoreDialog && scoreList) {
        const refreshPositions = () => {
            const rows = [...scoreList.children];
            rows.forEach((row, index) => {
                row.querySelector('[data-application-position]').textContent = (index + 1) + '.';
                row.querySelector('[data-move-application-question="-1"]').disabled = index === 0;
                row.querySelector('[data-move-application-question="1"]').disabled = index === rows.length - 1;
            });
        };
        form.querySelector('[data-open-application-scores]').addEventListener('click', () => {
            scoreDialog.showModal();
            totalPoints.focus();
        });
        scoreDialog.querySelector('[data-close-application-scores]').addEventListener('click', () => {
            const invalid = [...scoreDialog.querySelectorAll('input')].find(field => !field.checkValidity());
            if (invalid) { invalid.reportValidity(); return; }
            scoreDialog.close();
        });
        scoreList.addEventListener('click', event => {
            const button = event.target.closest('[data-move-application-question]');
            if (!button) return;
            const row = button.closest('[data-application-score-row]');
            if (button.dataset.moveApplicationQuestion === '-1' && row.previousElementSibling) {
                scoreList.insertBefore(row, row.previousElementSibling);
            } else if (button.dataset.moveApplicationQuestion === '1' && row.nextElementSibling) {
                scoreList.insertBefore(row.nextElementSibling, row);
            }
            refreshPositions();
        });
        form.addEventListener('invalid', event => {
            if (scoreDialog.contains(event.target) && !scoreDialog.open) scoreDialog.showModal();
        }, true);
        refreshPositions();
    }
    const mode = form.querySelector('[name="delivery_mode"]');
    const settings = form.querySelector('[data-virtual-settings]');
    const deadline = form.querySelector('[name="due_at"]');
    const kind = form.querySelector('[name="kind"]');
    const physicalSettings = form.querySelector('[data-physical-exam-settings]');
    const sync = () => {
        const action = form.querySelector('[data-confirm-application]');
        if (action) action.textContent = mode.value === 'printed' ? 'Imprimir' : 'Confirmar aplicação';
        const virtual = mode.value === 'online';
        if (settings) {
            settings.hidden = !virtual;
            settings.disabled = !virtual;
        }
        if (deadline) deadline.required = virtual;
        const physicalExam = mode.value === 'printed';
        if (physicalSettings) {
            physicalSettings.hidden = !physicalExam;
            physicalSettings.disabled = !physicalExam;
        }
    };
    mode.addEventListener('change', sync);
    kind.addEventListener('change', sync);
    sync();
    const shufflePhysical = form.querySelector('[data-shuffle-physical]');
    shufflePhysical?.addEventListener('click', () => {
        if (mode.value !== 'printed') return;
        form.querySelector('[name="shuffle_questions"]').checked = true;
        form.querySelector('[name="shuffle_options"]').checked = true;
        physicalSettings.querySelector('[data-physical-shuffle-status]').textContent =
            'Embaralhamento físico ativado: questões e alternativas serão organizadas em A, B e C, com questões abertas no final. Clique em Imprimir para gerar e salvar as versões e os gabaritos.';
    });

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
    const printDialog = document.querySelector('[data-print-dialog]');
    const printStatus = printDialog.querySelector('[data-print-status]');
    const printFrame = printDialog.querySelector('[data-print-frame]');
    const printOpen = printDialog.querySelector('[data-print-open]');
    printDialog.querySelector('[data-close-print]').addEventListener('click', () => printDialog.close());
    let pdfObjectUrl;
    let printing = false;
    form.addEventListener('submit', async event => {
        if (!rows.some(row => row.querySelector('input').checked)) {
            event.preventDefault();
            picker.showModal();
            picker.querySelector('[data-offer-search-status]').textContent = 'Selecione pelo menos uma turma.';
            return;
        }
        if (mode.value !== 'printed') return;
        event.preventDefault();
        if (printing) return;
        printing = true;
        const button = form.querySelector('[data-confirm-application]');
        button.disabled = true;
        printFrame.hidden = true;
        printOpen.hidden = true;
        printStatus.textContent = 'Salvando a aplicação e montando o PDF…';
        printDialog.showModal();
        try {
            const response = await fetch(form.action || location.href, {
                method: 'POST', body: new FormData(form),
                headers: {'Accept': 'application/json'}, credentials: 'same-origin'
            });
            const type = response.headers.get('content-type') || '';
            if (!type.includes('application/json')) throw new Error('Não foi possível salvar a aplicação. Recarregue a página e verifique sua sessão.');
            const result = await response.json();
            if (!response.ok) {
                throw new Error(Object.values(result.errors || {}).flat().map(error => error.message).join(' ') || 'Não foi possível salvar a aplicação.');
            }
            printStatus.textContent = 'Aplicação salva. Carregando o PDF…';
            printOpen.href = result.pdf_url;
            printOpen.hidden = false;
            const pdf = await fetch(result.pdf_url, {credentials: 'same-origin'});
            if (!pdf.ok || !(pdf.headers.get('content-type') || '').includes('application/pdf')) {
                throw new Error('A aplicação foi salva, mas não foi possível carregar o PDF. Tente abrir pelo link acima ou clique em Imprimir novamente.');
            }
            if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
            pdfObjectUrl = URL.createObjectURL(await pdf.blob());
            printFrame.src = pdfObjectUrl;
            printFrame.hidden = false;
            printStatus.textContent = 'PDF pronto: gabaritos individuais, provas A e capa, provas B e capa, provas C e capa.';
        } catch (error) {
            printStatus.textContent = error.message || 'Falha ao gerar o PDF. Tente novamente.';
        } finally {
            printing = false;
            button.disabled = false;
        }
    });
    update();
})();
