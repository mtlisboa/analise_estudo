# Sistema visual LuminiAI

## Direção

Uma evolução da identidade existente, construída como um caderno de progresso contemporâneo: superfícies minerais, tipografia direta, fotografia humana e laranja queimado como único acento dominante. A landing page é editorial; o produto autenticado é mais denso e operacional.

## Tokens

- Fundo claro: `#f7f2ea`; superfície: `#fffdf8`; texto: `#251f19`.
- Fundo escuro: `#151512`; superfície: `#22221e`; texto: `#f3f2ec`.
- Acento claro: `#b64716`; acento escuro: `#ff7935`.
- Bordas: `#ded3c5` no claro e `#393933` no escuro.
- Raios: 9px para controles e 14px para superfícies.
- Largura editorial máxima: 1240px.

## Tipografia

Usar a pilha nativa Aptos, Segoe UI Variable, Segoe UI e system-ui. Títulos têm peso forte e espaçamento negativo discreto; textos corridos preservam alta legibilidade. Rótulos auxiliares usam caixa normal, nunca texto inteiro em maiúsculas como decoração.

## Componentes

- Botões têm hierarquia primária e secundária, alvo confortável e estado pressionado com escala sutil.
- Cartões dependem de borda, contraste e espaçamento; sombras são reservadas para elementos elevados.
- A navegação autenticada usa barra lateral em telas grandes e dock inferior de quatro destinos no celular.
- O assistente de IA permanece acessível por um botão flutuante no canto inferior direito.
- Formulários exibem foco visível, mensagens próximas ao campo e controles com altura consistente.

## Movimento

Interações de interface duram entre 160ms e 260ms, priorizando `ease-out`. A entrada editorial da landing page é breve e escalonada. Animações não devem bloquear ações e são removidas quando `prefers-reduced-motion` está ativo. Efeitos de hover só aparecem em dispositivos que realmente suportam hover.

## Imagens

Fotografia documental, luminosa e natural, com estudantes e educadores brasileiros em espaços reais. Evitar texto gerado dentro das imagens, poses publicitárias e ilustrações genéricas de tecnologia.

## Responsividade e acessibilidade

- O conteúdo deve funcionar a partir de 320px sem rolagem horizontal.
- A navegação móvel deve permanecer alcançável sem cobrir conteúdo interativo.
- Contraste, foco, ordem semântica, rótulos e redução de movimento são requisitos do sistema.
- Nenhuma informação importante pode depender apenas de cor ou animação.
