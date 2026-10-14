// Render static question text and previews inserted by the question dialogs.
(() => {
    let loading;
    const hasMath = node => /\$[^$]+\$|\\\(|\\\[/.test(node.textContent);
    window.renderQuestionMath = async node => {
        if (!node || !hasMath(node)) return;
        try {
            if (!window.MathJax?.typesetPromise) {
                loading ||= new Promise((resolve, reject) => {
                    window.MathJax = {
                        tex: { inlineMath: [['$', '$'], ['\\(', '\\)']], processEscapes:true },
                        options: { skipHtmlTags:['script','noscript','style','textarea','pre','code','input'] },
                        startup: { typeset:false }
                    };
                    const script=document.createElement('script');
                    script.src='https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js';
                    script.async=true;
                    script.onload=() => window.MathJax.startup.promise.then(resolve,reject);
                    script.onerror=reject;
                    document.head.appendChild(script);
                });
                await loading;
            }
            await window.MathJax.typesetPromise([node]);
        } catch { /* Keep the original mathematical text readable if CDN is unavailable. */ }
    };
    window.renderQuestionMath(document.querySelector('main'));
})();
