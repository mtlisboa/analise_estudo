# Instruções permanentes para agentes

## Carregamento obrigatório de contexto

Antes de planejar, responder ou alterar qualquer arquivo neste repositório:

1. Inspecione recursivamente a pasta `agents/` para conhecer todos os arquivos disponíveis.
2. Leia integralmente todos os arquivos de texto em `agents/contexto/` e use seu conteúdo como contexto ativo do projeto.
3. Inspecione `agents/skills/` (e qualquer pasta `skill/` ou `skills/` que venha a ser adicionada dentro de `agents/`). Leia integralmente cada `SKILL.md` e os arquivos de instrução ou referência exigidos por ele antes de executar uma tarefa relacionada.
4. Considere essas leituras uma etapa obrigatória no início de cada nova tarefa, mesmo que os arquivos tenham sido lidos em uma conversa anterior. Se algum deles mudar durante a tarefa, releia-o antes de continuar.
5. Confronte o contexto documental com o estado atual do código. Não trate requisitos, planos ou funcionalidades apenas documentadas como implementação comprovada.

Em caso de divergência, siga primeiro as instruções do usuário na conversa atual e as instruções de maior prioridade; depois, registre claramente a divergência antes de tomar uma decisão irreversível.
