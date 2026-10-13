# Contexto consolidado — Análise de Estudo

Atualizado em: 24/09/2026.
Responsável: Matheus Lira Lisboa.
Nomes usados: analise_desempenho_estudo / analise_estudo.

## 1. Finalidade e confiabilidade deste documento

Preservar o contexto do projeto para continuidade em outras conversas ou no Codex/VS Code, inclusive após exclusão das conversas anteriores.

Este documento reúne pedidos do usuário, decisões registradas e documentação consultada no GitHub. Requisito solicitado não significa implementação concluída. “Documentado” significa descrito no README da dev, sem auditoria funcional completa nesta entrega. O estado do código deve ser conferido antes de implementar, integrar ou publicar.

Não misturar este projeto com Pede Aí, Agenda Médico, Inventory Manager ou sistemas de documentos municipais. Logs, URLs e decisões desses projetos não são evidência deste sistema educacional.

## 2. Links e referências

| Recurso | Endereço / situação |
|---|---|
| Repositório principal | https://github.com/mtlisboa/analise_estudo |
| Branch de trabalho solicitada atualmente | https://github.com/mtlisboa/analise_estudo/tree/dev |
| Branch main | https://github.com/mtlisboa/analise_estudo/tree/main |
| README consultado | https://github.com/mtlisboa/analise_estudo/blob/dev/README.md |
| Exemplo de ambiente | https://github.com/mtlisboa/analise_estudo/blob/dev/.env.example |
| Histórico da dev | https://github.com/mtlisboa/analise_estudo/commits/dev |
| Pull requests | https://github.com/mtlisboa/analise_estudo/pulls |
| Branch histórica de demonstração | https://github.com/mtlisboa/analise_estudo/tree/feature/mock-deploy-mode |
| Branch histórica de papéis/instituições | https://github.com/mtlisboa/analise_estudo/tree/feature/manager-institution-roles |
| Branch histórica de sessão/landing | https://github.com/mtlisboa/analise_estudo/tree/fix/public-landing-session |
| Railway — painel geral | https://railway.com/dashboard |
| Railway — link específico do projeto | PENDENTE: não localizado nas conversas recuperadas nem no README consultado |
| Railway — domínio público da aplicação | PENDENTE: não localizado; consultar o domínio do serviço no Railway ou RAILWAY_PUBLIC_DOMAIN |
| Repositório separado de frontend/backend | Nenhum outro repositório deste projeto foi confirmado |

“Rails” no pedido foi interpretado como Railway, serviço de hospedagem citado no contexto. O projeto documentado usa Django, não Ruby on Rails.

Última verificação de branches nesta conversa: dev em c74d48cf179f8037286f345410175ba735ce1368; main em 88056464f5b994d20055393ac1381d14ba9cf94c. Esses identificadores são um registro temporal, não garantia do estado futuro.

## 3. Objetivo do produto

Plataforma educacional para acompanhar progressão e avaliar desempenho dos alunos de forma inteligente.

Escopo:
- Gestão de organizações, instituições, turmas, grupos, usuários, questões e avaliações.
- Análise individual e coletiva da aprendizagem.
- Mentoria e assistência por IA.
- Gamificação e interação lúdica.
- Visão de coordenação para acompanhar alunos e a qualidade do trabalho dos professores.
- Análises por regras e recursos de IA.
- Planejamento pedagógico com atenção ao Ensino Fundamental I e II.

Gamificação e métricas de qualidade docente ainda não possuem especificação detalhada no contexto.

## 4. Perfis, identidade e acesso

Perfis discutidos: aluno, professor, gestor, administrador e sys admin.

Requisitos:
- Professores e alunos têm acesso limitado às respectivas turmas.
- Professores criam turmas, questões e avaliações conforme vínculos e permissões.
- Gestores e administradores possuem visões adequadas ao seu escopo.
- Sys admin executa funções globais, incluindo aprovação e exclusão de instituições.
- O criador de uma organização fica associado à sua gestão.

Modelo descrito atualmente no README:
- Uma única identidade autenticável por pessoa.
- Professor e aluno são flags contextuais dentro de cada organização; a mesma pessoa pode ter ambas.
- Gestor e administrador continuam como papéis globais.
- Qualquer usuário autenticado pode criar uma organização.
- O criador escolhe participar como professor, aluno ou ambos e pode alterar isso nas configurações.
- O responsável adiciona usuários existentes à organização e atribui suas flags.
- Somente professores da organização podem criar turmas nela.
- Só podem ser adicionados à turma membros da organização com flag compatível.
- Professores da turma criam e publicam testes.
- Vínculos educacionais antigos permanecem por compatibilidade.

Rotas documentadas:
- Landing: /
- Painel autenticado: /painel/
- Cadastro: /conta/cadastro/
- Login comum: /conta/entrar/
- Login exclusivo de sys admin: /sysadmin/entrar/

O usuário reportou login automático indevido e landing com layout operacional. Solicitou corrigir sessão e separar a apresentação pública da interface autenticada. Há merge relacionado no histórico, mas não foi realizado novo teste de navegador nesta compilação.

## 5. Onboarding e área pessoal

Onboarding:
- Perfil professor/aluno.
- Como conheceu a plataforma.
- Escolaridade.
- Objetivo principal.
- Opção de teste diagnóstico com IA, imediatamente ou depois.

O perfil informado no onboarding personaliza a experiência; não concede administração nem substitui papéis contextuais.

Área pessoal solicitada:
- Visualizar e alterar dados.
- Preferências do usuário.
- Alterar foto de perfil.

Há commits de configurações pessoais e upload de foto com validação, prévia e remoção. Não foram auditados nesta entrega.

## 6. Organizações, instituições, grupos e turmas

Criar entidade de instituição de ensino separada da organização, para escolas públicas e privadas.

Regras solicitadas:
- Gestor solicita o cadastro e envia documentos probatórios.
- Sys admin analisa e aprova.
- Somente sys admin pode excluir instituição.
- Exclusão exige exportação dos dados em CSV.
- Suportar grupos dentro de grupos.
- Permitir agrupamento de turmas e alunos para exploração analítica.

Pontos ainda a especificar ou verificar:
- Relação exata organização/instituição/grupo/turma.
- Fluxo de aprovação, rejeição e reenvio de documentos.
- Conteúdo e ordem da exportação obrigatória antes de excluir.
- Tratamento de vínculos compartilhados na exclusão.
- Não presumir que instituição e organização são a mesma entidade.

## 7. Banco de questões e importação

Questões devem ser reutilizáveis.

Formas de criação:
1. Manual.
2. Edição de questão existente.
3. Edição de questão por IA.
4. Geração de questão completamente nova por IA.

A criação de questão deve estar acessível no contexto das avaliações.

Importação solicitada:
- Preencher o banco a partir de CSV ou JSON.
- Receber imagens associadas às questões.

O contrato de importação não está definido neste contexto: esquema dos arquivos, forma de transporte das imagens, validação, deduplicação e tratamento de erros precisam ser conferidos no código ou especificados. Não tratar uma escolha técnica como requisito previamente aprovado.

## 8. Avaliações, atividades e provas

Módulo para buscar “minhas avaliações”, registrar novas e editar existentes.

Modal de criação:
- Matéria.
- Assunto.
- Lista de observações/restrições.
- Um ou mais tipos/objetivos de questão.
- Técnica avaliativa opcional.

Tipos descritos no README:
- Memorização.
- Compreensão.
- Dedução.
- Aplicação.
- Análise.
- Pensamento crítico.

Regra pedida: aplicar técnica padrão do método avaliativo quando nenhuma for escolhida.
Comportamento documentado: aplicar técnica padrão do primeiro tipo selecionado. Conferir se esta interpretação atende ao modelo pedagógico desejado.

Formas de montagem:
1. Manual com questões existentes.
2. Algorítmica.
3. IA selecionando questões existentes.
4. IA gerando todas as questões novas.

Rota documentada: /avaliacoes/.

## 9. Fundamentação pedagógica

Demandas de pesquisa:
- Métodos e técnicas de avaliação escolar.
- Elaboração de questionários objetivos.
- Proporção/distribuição de questões para Fundamental I e II.
- Pontuação por questão.
- Redução de acertos por chute.
- Elaboração que dificulte respostas obtidas apenas com IA.
- Revisão de questões abertas e redações com IA.
- Redução confiável da carga de correção do professor.

Não foi consolidada fórmula final de pontuação, proporção de questões ou política final de correção automática. Não prometer eliminação de chutes ou detecção infalível de uso de IA.

## 10. Dashboard e análise

Escopos: organização, grupos/subgrupos, turma, coleção selecionada de alunos e aluno individual.

Pedido inicial: muitos gráficos e distribuições 2D/3D.
Decisão posterior: reduzir variedade inicial para:
- Dispersão com filtros todos/grupos/turmas/coleção de alunos/aluno específico.
- Pizza com desenvolvimento do total dos alunos.
- Linhas.
- Barras.

Interações:
- Expandir gráfico.
- Aproximar/afastar por zoom.
- Explorar mais dados.
- Navegar em grupos hierárquicos.

O README também descreve autoavaliações de foco, organização, compreensão e motivação.

Pendente: definição final de eixos, métricas, categorias de desenvolvimento, agregações e comparabilidade entre avaliações. Gráficos não devem apresentar métricas inventadas como indicadores validados.

## 11. Design e experiência de uso

Diretriz mais recente: usar skills de Emil Kowalski, Impeccable e Taste para retirar aspecto genérico da interface.

Aplicação desejada: tipografia, hierarquia, espaçamento, cores, componentes, estados e animações coerentes com o produto.

Histórico:
- Antes, preservar estética da main ao integrar branches.
- Depois, solicitada refatoração com essas skills; a estética anterior pode ser revista para cumprir essa orientação.
- O usuário informou ter atualizado o repositório e pediu nova tentativa.
- Nenhuma refatoração foi implementada nesta conversa.
- As três skills não constavam no catálogo desta sessão; fontes/pastas exatas ainda precisam ser localizadas no repositório atualizado ou fornecidas.

Requisitos visuais adicionais:
- Assistente de IA no canto inferior direito.
- Botão claro/escuro bem posicionado.
- Tema inicialmente acompanha o sistema; escolha é salva no navegador, conforme README.
- Navegação móvel com quatro botões inferiores.
- Sino de notificações à direita; pedido posterior para ficar abaixo da top bar.
- Landing deve ter layout público próprio.
- Interface de criação e seleção de questões integrada ao fluxo de avaliações.

Não afirmar uso de uma skill apenas por conhecer seu nome. Ler SKILL.md e referências aplicáveis antes de executar.

## 12. Notificações

Solicitado backend com WebSocket e sino na interface.

Documentado no README:
- Sino com contador de não lidas e últimas 30 notificações.
- Marcar uma ou todas como lidas.
- Oculto na landing e no onboarding.
- Socket /ws/notifications/ autenticado pela sessão Django.
- Rejeição de anônimos e origens não permitidas.
- Destinatário não é escolhido pelo cliente.
- Reconexão, recuperação do banco e sincronização entre abas.
- Revalidação da sessão por mensagem e heartbeat aproximadamente a cada minuto.
- Notificações persistidas no banco; Redis transporta eventos entre workers.
- Publicação após commit da transação.
- Serviço features.notifications.services.notify_user.
- Envio administrativo disponível; gatilhos automáticos de negócio precisam ser conectados.
- bulk_create e QuerySet.update não disparam sinais de publicação.

Contrato:
- Servidor: notifications.snapshot, com items e unread_count.
- Cliente: notifications.sync, notifications.read com id, notifications.read_all.
- Mensagens renderizadas como texto.

## 13. Stack, arquitetura e estrutura

Conforme README consultado:
- Python 3.12+.
- Django 5.2.
- Django Channels, ASGI e WebSocket.
- MCP Python SDK v2.
- SQLite.
- Autenticação por sessão.
- Uvicorn.
- Redis para comunicação entre processos nas notificações.
- Frontend Django com templates e CSS próprio, conforme histórico recuperado.

Arquitetura Django MVC/MTV organizada por feature:
- src/config/: configurações e roteamento.
- src/features/accounts/: identidade e acesso.
- src/features/users_manager/: organizações, membros, turmas, testes e autoavaliações.
- src/features/organization_settings/: configurações da organização.
- src/features/notifications/: notificações.
- src/contexts/ia_integrations/features/chat_bot/: chatbot.
- src/static/css/: estilos.
- src/templates/: templates.
- src/manage.py: comandos Django.

Configuração observada na árvore da dev: src/config/settings/ com base.py, development.py, production.py e environment.py; ASGI em src/config/asgi.py.

Não aplicar comandos de FastAPI/src.main:app encontrados em históricos de outros projetos. A documentação atual deste repositório aponta para config.asgi:application.

## 14. Chatbot, MCP e RAG

Chatbot documentado:
- Navegador → WebSocket Django → agente externo via MCP Streamable HTTP.
- Sessão autenticada obrigatória.
- Endpoint: /ws/ia-integrations/chat-bot/.
- Indexação/obtenção da documentação pertence ao agente MCP.

Entrada:
```json
{
  "type": "chat.message",
  "message": "Como posso melhorar meu desempenho?",
  "conversation_id": "identificador-opcional"
}
```

Servidor cria UUID se conversation_id for omitido.
Saída bem-sucedida: chat.response. Erros: chat.error.
Ferramenta MCP recebe message, conversation_id e user_id e retorna texto ou objeto com message, answer ou result.

RAG solicitado separadamente:
- Cliente httpx.AsyncClient.
- URL em settings.RAG_SERVICE_URL.
- Token em settings.RAG_SERVICE_TOKEN.
- Authorization: Bearer.
- Gerenciar criação/encerramento e reutilização das conexões.
- Serviço para selecionar questões existentes e montar atividade.
- Serviço para criar questão nova a partir do prompt.

Nomes provisórios: client_rag, montage_lession_rag_service, create_assessment_rag_service.
Não presumir que o esboço httpx já substituiu ou foi integrado ao MCP existente.
Também foram solicitadas explicações passo a passo sobre RAG, bancos vetoriais e tecnologias abertas.

## 15. Ambiente e execução local

Variáveis documentadas:
| Variável | Finalidade |
|---|---|
| DJANGO_SECRET_KEY | Segredo Django |
| DJANGO_DEBUG | Modo debug |
| DJANGO_ALLOWED_HOSTS | Hosts autorizados |
| DJANGO_CSRF_TRUSTED_ORIGINS | Origens HTTPS adicionais |
| DJANGO_SYSADMIN_NAME | Nome da conta de sistema |
| DJANGO_SYSADMIN_LOGIN | Login da conta de sistema |
| DJANGO_SYSADMIN_EMAIL | Email da conta de sistema |
| DJANGO_SYSADMIN_PASSWORD | Senha provisionada |
| IA_MCP_SERVER_URL | URL do servidor MCP |
| IA_MCP_CHAT_TOOL | Ferramenta MCP |
| IA_MCP_TIMEOUT_SECONDS | Timeout MCP |
| REDIS_URL | Camada de comunicação entre workers |
| DEPLOY_MODE | MOCK para carga demonstrativa |
| MOCK_USER_PASSWORD | Senha definida para contas demonstrativas |
| RAILWAY_PUBLIC_DOMAIN | Domínio fornecido pelo Railway |
| RAG_SERVICE_URL / RAG_SERVICE_TOKEN | Integração RAG proposta; verificar implementação |

Não registrar credenciais reais neste documento.

Comandos do README, executados na raiz:
```bash
python -m venv .venv
pip install -r requirements.txt
python src/manage.py migrate
python -m uvicorn config.asgi:application --app-dir src --host 127.0.0.1 --port 8000
```

Antes do pip, ativar a venv. No PowerShell: .\.venv\Scripts\Activate.ps1.
Criar .env com base em .env.example.
Testes: python src/manage.py test.

## 16. Docker e Railway

README:
- Dockerfile executa Uvicorn com usuário não-root.
- Entrypoint aplica migrations antes de iniciar.
- Compose: docker compose up --build.
- SQLite persiste no volume sqlite_data do Compose.
- Compose inclui Redis.
- Em produção ASGI usa config.settings.production.
- Proxy HTTPS do Railway e cookies seguros.
- RAILWAY_PUBLIC_DOMAIN incluído automaticamente em hosts e origens CSRF.
- Domínios próprios exigem DJANGO_CSRF_TRUSTED_ORIGINS.
- DJANGO_SECRET_KEY deve ser configurada.
- REDIS_URL é necessária para entrega imediata entre os dois workers do Docker.
- Sem Redis, camada em memória é adequada apenas ao desenvolvimento com um processo.

Verificar montagem persistente efetiva do SQLite no Railway; existência de volume no Compose não comprova volume configurado no serviço hospedado.

Histórico de problemas: CSRF 403, 502, persistência SQLite, entrypoint, configuração ASGI/ambiente e transporte WebSocket. Não presumir que todos continuam pendentes.

## 17. Dados demonstrativos e usuários mock

Modo documentado:
```dotenv
DEPLOY_MODE=MOCK
MOCK_USER_PASSWORD=<senha-definida-no-ambiente>
```

Contas citadas no README:
- demo_professor.
- demo_professor_aux.
- demo_gestor.
- demo_responsavel.
- 20 alunos, incluindo demo_ana e demo_bruno; lista completa deve ser consultada na carga.

Todas usam a senha definida em MOCK_USER_PASSWORD; não há senha universal confirmada.
Carga idempotente após migrations, atualizando os mesmos registros.
Inclui duas instituições, grupos de até quatro níveis, turmas em quatro turnos, membros, convites, testes, autoavaliações, avaliações e quatro análises salvas.
Remover DEPLOY_MODE=MOCK impede novas cargas, mas não exclui dados persistidos.

## 18. Git e estado observado

Histórico de instruções:
1. Criar branches a partir de dev e subir alterações.
2. Normalizar dev com estética da main.
3. Integrar branches em main e apagar demais branches.
4. Pedidos posteriores retomaram trabalho/publicação em dev.
5. Diretriz atual explícita de publicação: dev.

Não executar exclusão histórica de branches automaticamente: há branches existentes e instruções posteriores.

Commits observados na dev:
| Commit | Descrição |
|---|---|
| c74d48c | Transporte WebSocket para deploy Uvicorn |
| 5c0edc0 | Foto de perfil com validação, prévia e remoção |
| c309e2a | Configurações pessoais e sino móvel abaixo da top bar |
| e6a1cc1 | Merge PR #8: sessão/landing e notificações |
| 9710a85 | Notificações persistentes por WebSocket |

A presença do commit confirma registro no Git; não substitui teste funcional.
O pedido de subir a refatoração não foi executado nesta conversa porque não havia alterações locais correspondentes.

## 19. Pesquisa de mercado

Solicitado pesquisar concorrentes no Brasil, especialmente Nordeste:
- Acompanhamento de progressão.
- Avaliação inteligente.
- Análise de dados.
- Mentoria por IA.
- Gamificação.
- Oferta white label.
- Custo de fine-tuning de LLM para educação.

Não há lista final de concorrentes, orçamento aprovado nem decisão de fine-tuning neste documento.

## 20. Pendências para continuidade

- Recuperar link específico do projeto Railway e domínio público.
- Atualizar checkout da dev antes de qualquer mudança.
- Localizar skills Emil Kowalski, Impeccable e Taste no repositório atualizado; confirmar origem e ler instruções.
- Executar/refinar refatoração visual solicitada e publicar em dev após validação.
- Verificar implementação da importação CSV/JSON com imagens.
- Auditar quatro modos de montagem de avaliações e quatro formas de criação de questões.
- Validar regras de instituição, documentos, aprovação e exportação na exclusão.
- Definir métricas/eixos e regras pedagógicas ainda abertas.
- Verificar integração dos serviços RAG propostos.
- Conectar notificações aos eventos de negócio desejados.
- Validar sessão, landing, área pessoal, foto e navegação responsiva.
- Confirmar persistência, Redis e configuração efetiva no Railway.

## 21. Instruções para um próximo agente

Use este documento como contexto inicial e confira o código atual.
Trabalhe no repositório https://github.com/mtlisboa/analise_estudo.
Siga o pedido atual de branch dev.
Leia AGENTS.md e SKILL.md aplicáveis antes de alterar código.
Preserve regras de negócio, permissões, acessibilidade e comportamento funcional na refatoração.
Use as skills de design solicitadas quando seus arquivos estiverem disponíveis.
Separe claramente requisito, implementação documentada, teste realizado e pendência.
Não invente links Railway, credenciais, usuários, resultados de testes ou status.
Não importe arquitetura/comandos de outros projetos.
Ao concluir mudanças, informe o que mudou, validação realizada, limitações e commit/branch publicado.

## 22. Fontes desta consolidação

- Pedidos e decisões visíveis nesta conversa.
- Histórico recuperado específico do projeto.
- README e .env.example da dev consultados em 24/09/2026.
- Árvore da dev e branches/commits consultados nesta sessão.

Limite: este arquivo consolida o contexto disponível; não é auditoria integral do repositório nem comprovação do estado do deploy.

