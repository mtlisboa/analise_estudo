# Revisão funcional — 09/11/2026

Base examinada: `main`, commit `88056464f5b994d20055393ac1381d14ba9cf94c`.

## Funcionalidades presentes

| Módulo | Implementação encontrada |
| --- | --- |
| Contas | Cadastro, sessão, saída por POST, onboarding e login separado de sysadmin |
| Organizações | Criação, inclusão de usuários existentes e configuração dos papéis do responsável |
| Turmas | Criação por professor, inclusão de membros e cadastro de testes publicados ou rascunhos |
| Avaliações | Planejamento por matéria/assunto, tipos, técnica automática/manual, observações, busca e edição |
| Autoavaliações | Registro de foco, organização, compreensão e motivação na escala 1–5 |
| Análises | Filtros por organização/turma/aluno/período, indicadores, gráficos e ranking de autoavaliações |
| Assistente | Chat por WebSocket com agente MCP externo e conversa inicial de diagnóstico |

## Problemas corrigidos

- Painel pessoal mostrava progresso, sequência, totais e insights fixos. Agora usa registros reais e estado vazio explícito; não apresenta autoavaliação como nota de prova.
- A ação de novo questionário levava a uma âncora de insight e o diagnóstico era um botão inerte. Agora há navegação para avaliações e diagnóstico.
- Professor consultava todas as turmas/alunos da organização. A análise respeita suas turmas; o responsável mantém a visão organizacional.
- A lista organizacional oferecia links para turmas sem acesso. Listagem e destino compartilham o mesmo escopo, incluindo leitura pelo responsável.
- Vínculos de turma antigos continuavam válidos após a remoção do membro da organização ou de seu papel. A autorização exige vínculo e papel compatíveis na mesma organização.
- Organizações inativas ainda permitiam acesso direto a turmas e formulários. As rotas passam a exigir organização ativa.
- Rascunhos eram contados nas análises de alunos. Agora ficam restritos aos professores da turma e responsável.
- Gráfico de papéis duplicava pessoas de várias organizações; datas eram agrupadas em UTC. Agora conta pessoas distintas e usa o fuso configurado.
- Contagem de testes ignorava período. O filtro temporal agora também se aplica aos testes. Consultas e agrupamentos por turma foram reduzidos.
- Rotas antigas de vínculos/convites ainda escreviam no fluxo descontinuado. Redirecionam para organizações sem alterar os registros antigos.
- Formulários de turma voltavam para a lista geral. Retornam ao contexto de origem; autoavaliação retorna ao painel pessoal.
- Nova avaliação herdava valores de uma edição inválida; o texto pendente de observação se perdia ao salvar. Ambos corrigidos.
- Observações eram interpoladas em atributos HTML. São criadas como texto e atributos via DOM.
- Busca após erro de edição usava a rota de atualização. Agora aponta explicitamente para a listagem.
- Limpar o chat não liberava o estado de espera e respostas antigas contaminavam a conversa nova. As respostas são filtradas por identificador de conversa.

## Limites da implementação existente

O cadastro de avaliações é um planejamento: não existe neste código um banco de
questões, aplicação de respostas, correção automática ou cálculo de notas de
provas. Os testes de turma armazenam título, instruções e pontuação máxima; não
há submissões de alunos. O ranking usa autoavaliações pessoais, não desempenho
objetivo por disciplina. O diagnóstico depende de um agente MCP configurado;
a integração com esse serviço externo não foi validada ao vivo nesta revisão.

Nenhuma migração de banco é necessária. Os dados históricos de vínculos são
preservados. A revisão cobre código, respostas HTTP, permissões, templates e
comportamento JavaScript em DOM e validação visual em navegador.

## Complemento: análise de professores pelo gestor

A visão de alunos foi preservada. O responsável da organização dispõe também
de filtro por professor e resumo de turmas, alunos vinculados, testes criados no
período, alunos com autoavaliação e média da última autoavaliação de cada aluno.
Essa média é um indicador dos registros dos alunos, não uma nota de desempenho
do professor. Professores sem turma continuam visíveis, com valores zero e
estado sem dados. A consulta não cresce uma vez por professor.

O filtro por professor só opera nas organizações administradas pelo usuário;
alunos e professores comuns não recebem o seletor ou os dados de gestão.
Filtros por aluno também limitam turmas e testes ao vínculo desse aluno. A troca
de organização/professor/turma limpa os filtros dependentes, impedindo a
reutilização de seleções de outro contexto. Se a biblioteca de gráficos não
carregar, a tela informa a falha e mantém tabelas e indicadores disponíveis.
As instruções salvas dos testes publicados passam a aparecer na turma.

A integração MCP permanece fora deste complemento, conforme o escopo solicitado.

## Reestilização do módulo de análise

Layout responsivo com hierarquia tipográfica, cartões de indicadores, filtros
agrupados, navegação por seções e tabelas legíveis. A análise de alunos e
professores pelo gestor permanece disponível, com as permissões existentes.

Os gráficos seguem os temas claro e escuro. A evolução alterna entre índice
percentual e quatro dimensões de 1 a 5, evitando escalas misturadas. Barras
horizontais e mapa de calor acomodam nomes e listas longas; o mapa 3D permanece
disponível em uma seção expansível, carregada ao abrir. Estados vazios e erros
não ocultam tabelas e indicadores. Autoavaliações são identificadas como tal.

Validação em Chromium com Plotly real: temas claro/escuro, dimensões, 3D,
resoluções de 390, 768 e 1440 px e estado sem registros.

## Integração de dev e main

A revisão acima descreve a base antiga da main. A integração preserva os módulos
institucionais, banco de questões, provas físicas/virtuais, gabaritos e correção
que já existiam na dev. Portanto, a limitação anterior sobre inexistência desses
módulos não se aplica à versão unificada.

Os gráficos novos foram integrados ao fluxo de gerar, selecionar alunos e salvar
análises, preservando grupos hierárquicos e snapshots anteriores. O filtro e o
resumo por professor acompanham a geração e o salvamento. As próximas alterações
devem ser desenvolvidas na branch dev.

Validação da integração: 81 testes de análise, navegação, gestão e acesso de
professor institucional passaram; regressões DOM e navegador passaram. Nenhuma
migração adicional foi gerada. A suíte completa foi comparada com a dev original:
402 testes na base, com 31 falhas e 2 erros preexistentes; 431 na integração.
A única falha adicional foi corrigida e revalidada nos 81 testes focados.
As falhas preexistentes concentram-se nos testes de aplicação/agendamento de
questionários e seus contratos de formulário; não foram mascaradas ou removidas.
