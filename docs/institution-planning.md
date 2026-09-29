# Montagem de turmas e itinerário docente

Acesso: `/instituicao/montagem/`, com atalho nos contextos administrativo e operador.
Gestor, aluno, professor e responsável não recebem permissão de edição.
Menu lateral e sino são reutilizados sem alteração.

## Fluxo

1. Criar um período com início e fim.
2. Criar ofertas de turma, série, turno e vagas. Cada oferta recebe UUID único permanente.
3. Cadastrar alunos individualmente ou colar lista de até 500 linhas por lote:
   `matrícula;nome;série;turno;turma anterior`. Última coluna opcional.
   Turnos: MORNING, AFTERNOON, EVENING, FULL_TIME.
4. Distribuir automaticamente ou editar o aluno e escolher sua turma. Fixar a
   distribuição impede sua alteração pela próxima geração.
5. Cadastrar intervalos de aula e configurar professores já provisionados pelo
   administrativo: disciplinas, horários disponíveis e máximo semanal de aulas.
6. Definir disciplinas e quantidade semanal de aulas para cada turma.
7. Gerar professores/horários ou cadastrar aulas manualmente. Fixar professor
   preserva o vínculo; fixar aula preserva horário e professor na regeneração.
8. Revisar pendências e publicar para sincronizar as turmas e vínculos existentes.

O cadastro da lista escolar **não cria credenciais nem caixas de e-mail**. Quando
a matrícula já corresponde a um acesso institucional STUDENT ativo, publicar
cria/atualiza seu vínculo na turma. Alunos sem acesso continuam na lista e são
contabilizados no aviso de publicação; o administrativo pode criar seus acessos e
publicar novamente. Operador não passa a provisionar contas ou redefinir senhas.

## Regras

- Cada aluno tem uma matrícula por período. Matrícula identifica histórico dentro
  da instituição; não é alterada na edição para evitar trocar a identidade.
- Importação falha por inteiro se qualquer linha for inválida ou duplicada.
- Série, turno e capacidade são restrições obrigatórias. Coexistência anterior
  é preferência: a heurística determinística conta grupos compartilhados,
  preserva alunos fixados e usa ocupação relativa para desempatar.
- O histórico considera listas publicadas de períodos encerrados antes do novo
  período e a turma anterior informada manualmente. Inclua ano e escola nessa
  informação. Não inferimos relações entre alunos sem registros.
- A geração de horários usa professores habilitados e explicitamente disponíveis,
  considera intervalos reais (inclusive sobrepostos com IDs diferentes), carga
  semanal e conflitos com planejamentos de períodos concorrentes.
- A geração é heurística, não um solucionador ótimo: uma pendência pode exigir
  ajuste manual mesmo quando outra combinação completa existe. Não preenche
  conflitos à força. Limites: 3.000 alunos, 100 ofertas, 300 disciplinas/ofertas e
  200 intervalos por geração.
- Intervalos de descanso não devem ser cadastrados como horários disponíveis.
  Sala física, deslocamento entre campi e regras trabalhistas não são modelados.
- Alterações manuais passam pelas mesmas validações; edições incompatíveis com
  aulas já cadastradas são rejeitadas até que essas aulas sejam ajustadas.
- Uma revisão detecta abas desatualizadas. Mutações são transacionais e serializadas
  por instituição; erros não deixam importação ou geração pela metade.
- Publicar exige todos os alunos distribuídos e todas as cargas semanais completas.
  É idempotente e só remove vínculos previamente administrados pelo planejamento.
- Professor e aluno consultam horários publicados em seus próprios contextos,
  com os vínculos ativos existentes. Rascunhos não entram na grade publicada.
- Novas ofertas publicadas geram Classroom e ClassroomMembership no módulo
  existente. Turmas legadas não são convertidas automaticamente nem excluídas.

## Instalação e validação

`python src/manage.py migrate`

`python src/manage.py test contexts.institutions.planning features.accounts features.users_manager features.notifications`

`python src/manage.py makemigrations --check --dry-run`

Migração aditiva `institution_planning.0001_initial`. Nenhuma credencial ou variável
de ambiente adicional. A branch inclui workflow de verificação no GitHub Actions.
A implementação foi preparada sem terminal local; consulte o resultado do workflow
antes de integrar à dev. A revisão visual no navegador permanece necessária.
