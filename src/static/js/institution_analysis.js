document.querySelectorAll('.analysis-shell form, .analysis-record form').forEach(form => {
  form.addEventListener('submit', () => {
    form.setAttribute('aria-busy', 'true');
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.textContent = form.method.toLowerCase() === 'post' ? 'Salvando registro…' : 'Carregando análise…';
    status.dataset.analysisLoading = 'true';
    form.append(status);
    form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = true; });
  });
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('[data-analysis-loading]').forEach(node => node.remove());
  document.querySelectorAll('.analysis-shell form, .analysis-record form').forEach(form => {
    form.removeAttribute('aria-busy');
    form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = false; });
  });
});

// Native SVG keeps the institutional charts available without an external CDN.
(() => {
  const source = document.getElementById('institution-analysis-chart-data');
  if (!source) return;
  const data = JSON.parse(source.textContent);
  const ns = 'http://www.w3.org/2000/svg';
  const number = value => Number(value).toLocaleString('pt-BR', {maximumFractionDigits: 1});
  function node(tag, attributes = {}, text) {
    const el = document.createElementNS(ns, tag);
    Object.entries(attributes).forEach(([key, value]) => el.setAttribute(key, value));
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function label(svg, x, y, text, attributes = {}) { svg.append(node('text', {x, y, ...attributes}, text)); }
  function accessible(el, text) { el.setAttribute('tabindex', '0'); el.setAttribute('aria-label', text); el.append(node('title', {}, text)); return el; }
  function empty(container) {
    const box = document.createElement('div'); box.className = 'chart-empty';
    const title = document.createElement('strong'); title.textContent = 'Ainda não há resultados';
    const copy = document.createElement('span'); copy.textContent = 'Ajuste os filtros ou registre evidências neste recorte.';
    box.append(title, copy); container.replaceChildren(box); container.dataset.state = 'empty';
  }
  function render(container) {
    const type = container.dataset.analysisChart;
    const rows = data[type] || [];
    if (!rows.length || (type === 'distribution' && !rows.some(row => row.count > 0)) || (type === 'classes' && !rows.some(row => row.average !== null))) return empty(container);
    container.dataset.state = 'ready';
    const width = Math.max(320, container.clientWidth);
    const height = type === 'classes' ? Math.max(260, rows.length * 58 + 35) : 280;
    const svg = node('svg', {viewBox: `0 0 ${width} ${height}`, 'aria-hidden': 'false'});
    if (type === 'timeline') {
      const left = 42, right = width - 18, top = 20, bottom = height - 45;
      const x = index => rows.length === 1 ? (left + right) / 2 : left + index * (right - left) / (rows.length - 1);
      const y = value => bottom - Number(value) * (bottom - top) / 100;
      [0, 25, 50, 75, 100].forEach(value => { svg.append(node('line', {x1:left,y1:y(value),x2:right,y2:y(value),class:'chart-grid'})); label(svg, left - 10, y(value) + 4, value + '%', {'text-anchor':'end'}); });
      const points = rows.map((row, i) => `${x(i)},${y(row.average)}`);
      if (rows.length > 1) { svg.append(node('polygon', {points:`${left},${bottom} ${points.join(' ')} ${right},${bottom}`,class:'chart-area'})); svg.append(node('polyline', {points:points.join(' '),class:'chart-line'})); }
      const labelCount = Math.min(rows.length, width < 450 ? 3 : 5);
      const labels = new Set(Array.from({length:labelCount}, (_, i) => Math.round(i * (rows.length - 1) / Math.max(1, labelCount - 1))));
      rows.forEach((row, i) => {
        const date = String(row.date).split('-').reverse().join('/');
        svg.append(accessible(node('circle', {cx:x(i),cy:y(row.average),r:4.5,class:'chart-dot'}), `${date}: ${number(row.average)}%, ${row.count} resultados`));
        if (labels.has(i)) label(svg,x(i),bottom + 28,date.slice(0,5),{'text-anchor':'middle'});
      });
    } else {
      const classes = type === 'classes';
      const max = classes ? 100 : Math.max(...rows.map(row => row.count), 1);
      const left = classes ? 12 : 76, right = width - 56;
      rows.forEach((row, i) => {
        const y = classes ? 28 + i * 58 : 32 + i * 58;
        const value = classes ? row.average : row.count;
        if (classes) label(svg,left,y - 10,row.label.length > width / 9 ? row.label.slice(0,Math.floor(width / 9)) + '…' : row.label);
        else label(svg,0,y + 17,row.label);
        svg.append(node('rect',{x:left,y,width:Math.max(1,right-left),height:28,class:'chart-track'}));
        if (value !== null) svg.append(accessible(node('rect',{x:left,y,width:Math.max(0,Number(value)/max*(right-left)),height:28,class:'chart-bar'}), `${row.label}: ${number(value)}${classes ? '%' : ' resultados'}`));
        label(svg,right + 10,y + 18,value === null ? '—' : number(value) + (classes ? '%' : ''),{class:'chart-value'});
      });
    }
    container.replaceChildren(svg);
  }
  const charts = [...document.querySelectorAll('[data-analysis-chart]')];
  charts.forEach(render);
  let frame;
  const observer = new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => charts.forEach(render)); });
  charts.forEach(chart => observer.observe(chart));
  document.querySelectorAll('.analysis-shell .analytics-table-wrap').forEach(table => { table.tabIndex = 0; table.setAttribute('role','region'); table.setAttribute('aria-label','Tabela de dados, role para consultar todas as colunas'); });
})();

(() => {
  const list = document.querySelector('[data-skill-list]');
  if (!list) return;
  const rows = [...list.querySelectorAll('.learning-skill')];
  if (!rows.length) return;
  const controls = document.querySelector('.learning-controls');
  const search = controls.querySelector('[data-skill-search]');
  const sort = controls.querySelector('[data-skill-sort]');
  const expand = controls.querySelector('[data-skill-expand]');
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
  function update() {
    const query = normalize(search.value.trim());
    rows.forEach(row => { row.hidden = !normalize(row.dataset.skill + ' ' + row.dataset.subject).includes(query); });
    rows.sort((a, b) => {
      if (sort.value === 'name') return a.dataset.skill.localeCompare(b.dataset.skill, 'pt-BR');
      if (!a.dataset.score) return b.dataset.score ? 1 : 0;
      if (!b.dataset.score) return -1;
      const difference = Number(a.dataset.score.replace(',', '.')) - Number(b.dataset.score.replace(',', '.'));
      return sort.value === 'desc' ? -difference : difference;
    }).forEach(row => list.append(row));
    document.querySelector('[data-skill-empty]').hidden = rows.some(row => !row.hidden);
  }
  search.addEventListener('input', update);
  sort.addEventListener('change', update);
  expand.addEventListener('click', () => {
    const visible = rows.filter(row => !row.hidden);
    const open = visible.some(row => !row.open);
    visible.forEach(row => { row.open = open; });
    expand.textContent = open ? 'Recolher todas' : 'Expandir todas';
  });
  controls.hidden = false;
})();
