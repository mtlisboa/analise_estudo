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
O agente MCP é simulado; estes testes não substituem testes visuais em navegador.
