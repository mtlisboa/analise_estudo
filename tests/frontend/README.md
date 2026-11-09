# Regressões do front

Com as dependências Python do projeto instaladas e Node.js 24+:

```bash
npm install --prefix tests/frontend --no-save --package-lock=false jsdom@31.0.0
node tests/frontend/regressions.cjs
```

O script renderiza os templates Django com banco SQLite em memória e executa o
JavaScript real no DOM. Cobre o reinício do modal após edição inválida, o envio
de observações ainda não adicionadas, o tratamento literal de HTML/aspas,
a rota de pesquisa e respostas atrasadas de conversas anteriores.
Também cobre os filtros dependentes do gestor e a falha de carregamento dos gráficos.
O agente MCP é simulado; estes testes não substituem testes visuais em navegador.

## Validação visual

```bash
npm install --prefix tests/frontend --no-save --package-lock=false jsdom@31.0.0 playwright plotly.js-dist-min@2.35.2
npx --prefix tests/frontend playwright install chromium
node tests/frontend/visual.cjs
```

É possível indicar um navegador existente com `CHROMIUM_EXECUTABLE_PATH`.
O teste usa templates reais, dados descartáveis em SQLite e Plotly local, sem
serviços externos. Confere temas claro/escuro, quatro dimensões, abertura 3D,
estado vazio e ausência de transbordamento em 390 e 768 px. As capturas ficam
no diretório temporário `lumini-analytics-visual` ou em `SCREENSHOT_DIR`.
