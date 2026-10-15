(() => {
  function init(editor) {
    if (editor.dataset.initialized) return;
    const input=editor.querySelector('[data-alternatives-input]'), form=editor.closest('form');
    const type=form.querySelector('[name=question_type]'); if (!type) return;
    let initial; try { initial=JSON.parse(input.value || '[]'); } catch (_) { return; }
    if (!Array.isArray(initial)) return;
    editor.dataset.initialized='true';
    const list=editor.querySelector('[data-alternative-list]'), status=editor.querySelector('[data-alternative-status]');
    const controls=editor.querySelector('[data-alternative-controls]');
    const addButton=editor.querySelector('[data-add-alternative]');
    const group='correct_'+(window.crypto?.randomUUID?.() || Math.random().toString(36).slice(2));
    function sync() {
      input.value=JSON.stringify(Array.from(list.children,row=>({text:row.querySelector('textarea').value,correct:row.querySelector('input[type=radio]').checked})));
      addButton.disabled=list.children.length>=5;
      list.querySelectorAll('[data-answer-status]').forEach(label=>label.textContent=label.closest('section').querySelector('input').checked ? 'Correta' : 'Errada');
    }
    function add(value={}, focus=false) {
      if (list.children.length>=5) {status.textContent='Limite de cinco alternativas.';return;}
      const row=document.createElement('section');row.className='content-block alternative-block';
      const toolbar=document.createElement('div');toolbar.className='content-block-toolbar';
      const heading=document.createElement('strong');heading.textContent='Alternativa';
      toolbar.append(heading);
      const label=document.createElement('label'); label.textContent='Texto da alternativa';
      const text=document.createElement('textarea');text.rows=2;text.maxLength=10000;text.required=true;text.value=value.text || ''; label.append(text);
      const marker=document.createElement('label'), radio=document.createElement('input');radio.type='radio';radio.name=group;radio.checked=!!value.correct;radio.setAttribute('aria-label','Marcar esta alternativa como correta');marker.className='alternative-correctness';
      const state=document.createElement('span');state.dataset.answerStatus='';marker.append(radio,state);
      const remove=document.createElement('button');remove.type='button';remove.textContent='Remover';remove.setAttribute('aria-label','Remover alternativa');remove.addEventListener('click',()=>{const next=row.nextElementSibling || row.previousElementSibling;row.remove();sync();status.textContent='Alternativa removida.';(next?.querySelector('textarea') || addButton).focus();});
      toolbar.append(marker,remove);row.append(toolbar,label);row.addEventListener('input',sync);row.addEventListener('change',sync);list.append(row);sync();update();
      if(focus){text.focus();status.textContent='Nova alternativa adicionada.';}
    }
    const lines=form.querySelector('[name=answer_lines]');
    const container=field=>field?.closest('.form-field') || field?.closest('p');
    function update() {
      const closed=type.value==='multiple_choice';
      controls.hidden=!closed;
      list.querySelectorAll('textarea,input').forEach(field=>field.disabled=!closed);
      if (lines) {lines.required=!closed;lines.disabled=closed;const parent=container(lines);if(parent)parent.hidden=closed;else lines.hidden=closed;}
      ['options','correct_answer'].forEach(name=>form.querySelectorAll(`[name=${name}]`).forEach(field=>{field.disabled=true;const parent=container(field);if(parent)parent.hidden=true;else field.hidden=true;}));
      const parent=container(input);if(parent)parent.hidden=!closed;
    }
    initial.forEach(value=>add(value));if(!initial.length){add();add();}
    input.hidden=true;type.addEventListener('change',update);form.addEventListener('submit',sync);
    addButton.addEventListener('click',()=>add({},true));sync();update();
  }
  const boot=()=>document.querySelectorAll('[data-question-type-editor]').forEach(init);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
