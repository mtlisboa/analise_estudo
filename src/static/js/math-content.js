// Load the pinned renderer only on pages containing mathematical question text.
(() => {
    const content = document.querySelector('main');
    if (!content || !/\$[^$]+\$|\\\(|\\\[/.test(content.textContent)) return;
    window.MathJax = {
        tex: { inlineMath: [['$', '$'], ['\\(', '\\)']], processEscapes: true },
        options: { skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'input'] }
    };
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js';
    script.async = true;
    document.head.appendChild(script);
})();
