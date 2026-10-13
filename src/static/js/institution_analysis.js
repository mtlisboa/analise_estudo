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
