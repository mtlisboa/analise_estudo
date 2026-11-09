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
comportamento JavaScript em DOM; a validação visual em navegador fica pendente.
