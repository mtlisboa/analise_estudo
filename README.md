# Análise de Estudo

Base de uma aplicação para análise da capacidade e do desempenho de estudantes.

## Stack

- Python 3.12+
- Django 5.2
- Django Channels (WebSocket/ASGI)
- MCP Python SDK v2
- SQLite
- Autenticação por sessão

O projeto segue a arquitetura MVC/MTV do Django organizada por feature. Cada
funcionalidade fica em `src/features/<feature>`, reunindo modelos, formulários,
views, URLs, templates e testes do mesmo contexto.

## Executando localmente

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python src/manage.py migrate
python -m uvicorn config.asgi:application --app-dir src --host 127.0.0.1 --port 8000
```

Acesse `http://127.0.0.1:8000/` para ver a landing page. O painel individual
fica em `/painel/` e exige autenticação; uma nova conta pode ser criada em
`/conta/cadastro/`.

O tema claro/escuro acompanha a preferência do sistema no primeiro acesso e a
escolha feita no botão do cabeçalho fica salva no navegador.

### Sysadmin por variáveis de ambiente

Uma conta de sistema pode ser criada ou atualizada automaticamente depois das
migrations. Configure as quatro variáveis no ambiente de execução:

```dotenv
DJANGO_SYSADMIN_NAME=Administrador do Sistema
DJANGO_SYSADMIN_LOGIN=sysadmin
DJANGO_SYSADMIN_EMAIL=sysadmin@example.com
DJANGO_SYSADMIN_PASSWORD=uma-senha-forte
```

O provisionamento é idempotente e permite rotacionar a senha alterando a
variável. O acesso dessa conta é exclusivo pela rota `/sysadmin/entrar/`.

## Onboarding do primeiro acesso

No primeiro login, a pessoa informa seu perfil, como conheceu a plataforma,
grau de escolaridade e objetivo principal. Ao concluir, pode entrar em um teste
diagnóstico personalizado no assistente de IA ou seguir para o painel e fazer o
teste depois. O perfil declarado no onboarding personaliza a experiência, mas
não concede permissões administrativas nem substitui os papéis contextuais das
organizações.

## Organizações, usuários, turmas e testes

O módulo `users_manager` mantém uma única identidade autenticável para cada
pessoa. Professor e aluno são flags contextuais atribuídas dentro de cada
organização; gestor e administrador continuam sendo papéis globais. O fluxo é:

- qualquer usuário autenticado pode criar uma organização;
- ao criar a organização, o responsável escolhe participar como professor,
  aluno ou ambos e pode alterar essa escolha nas configurações;
- o responsável adiciona usuários existentes e marca as flags de professor,
  aluno ou ambas;
- somente professores da organização podem criar turmas dentro dela;
- professores adicionam à turma apenas membros da organização cuja flag seja
  compatível com o papel escolhido;
- professores da turma criam e publicam testes para seus alunos;
- registrar autoavaliações de foco, organização, compreensão e motivação;
- usar o login comum em `/conta/entrar/` para todas as contas, exceto sysadmin;
- autenticar sysadmins exclusivamente em `/sysadmin/entrar/`.

Os vínculos educacionais antigos permanecem no banco apenas para compatibilidade
com dados existentes, mas o novo fluxo é delimitado pela organização.

## Testes

```bash
python src/manage.py test
```

## Avaliações

O módulo `/avaliacoes/` permite buscar, criar e editar avaliações próprias. Cada
avaliação registra matéria, assunto, uma lista de observações ou restrições e um
ou mais tipos de questão (memorização, compreensão, dedução, aplicação, análise
e pensamento crítico). A técnica avaliativa pode ser escolhida manualmente; se
ficar em branco, o sistema aplica a técnica padrão do primeiro tipo selecionado.

## Chatbot com agente MCP

O bounded context `ia-integrations` fica em `src/contexts/ia_integrations` e
contém a feature `chat_bot`. O navegador se comunica com a aplicação por
WebSocket, enquanto a aplicação consulta o agente externo pelo transporte MCP
Streamable HTTP. A obtenção e indexação da documentação pertencem ao agente MCP
e podem ser implementadas depois sem alterar o contrato WebSocket.

Configure a conexão no `.env`:

```dotenv
IA_MCP_SERVER_URL=http://localhost:9000/mcp
IA_MCP_CHAT_TOOL=answer_from_documentation
IA_MCP_TIMEOUT_SECONDS=30
```

O socket exige uma sessão Django autenticada e está disponível em:

```text
ws://localhost:8000/ws/ia-integrations/chat-bot/
```

Contrato de entrada:

```json
{
  "type": "chat.message",
  "message": "Como posso melhorar meu desempenho?",
  "conversation_id": "identificador-opcional"
}
```

Quando `conversation_id` não é informado, o servidor cria um UUID. Uma resposta
bem-sucedida usa `chat.response`; falhas de validação ou indisponibilidade do
agente usam `chat.error`. O tool MCP configurado deve aceitar `message`,
`conversation_id` e `user_id`, retornando texto ou um objeto com uma das chaves
`message`, `answer` ou `result`.

## Imagem Docker

```bash
docker build -t analise-estudo:local .
docker run --rm -p 8000:8000 \
  -e DJANGO_SECRET_KEY=chave-local \
  -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
  analise-estudo:local
```

A imagem executa a aplicação com Uvicorn na porta `8000` usando um usuário
não-root. Antes da primeira execução, aplique as migrações ou utilize o
Docker Compose descrito abaixo.

## Docker Compose

```bash
docker compose up --build
```

O entrypoint aplica as migrações antes de iniciar o Uvicorn, tanto no Railway
quanto no Docker Compose. O banco SQLite fica
armazenado no volume nomeado `sqlite_data`, portanto os dados persistem entre
reinicializações dos containers. Para encerrar:

```bash
docker compose down
```

Para também remover os dados persistidos, execute conscientemente
`docker compose down --volumes`.

## Deploy no Railway

O processo ASGI usa `config.settings.production` por padrão. Nesse modo, a
aplicação confia no proxy HTTPS do Railway, ativa cookies seguros e adiciona
automaticamente `https://$RAILWAY_PUBLIC_DOMAIN` a `CSRF_TRUSTED_ORIGINS`. Não é
necessário copiar manualmente o domínio gerado pelo Railway.

Para domínios próprios, informe as origens completas, incluindo o esquema
`https://`, separadas por vírgula:

```dotenv
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.exemplo.com,https://admin.exemplo.com
```

Mantenha `DJANGO_SECRET_KEY` configurada no serviço. O domínio público do
Railway também é incluído automaticamente em `ALLOWED_HOSTS`.

### Deploy demonstrativo com dados mock

Para carregar automaticamente um conjunto demonstrativo depois das migrations,
configure no serviço Railway:

```dotenv
DEPLOY_MODE=MOCK
MOCK_USER_PASSWORD=defina-uma-senha-segura
```

O comando é idempotente e atualiza os mesmos registros a cada inicialização.
Ele cria os perfis `demo_professor`, `demo_professor_aux`, `demo_gestor`,
`demo_responsavel` e 20 alunos (`demo_ana`, `demo_bruno`, etc.). A carga inclui
duas instituições, hierarquias com até quatro níveis de grupos terminando em
turmas nos quatro turnos, membros e
convites em estados diferentes, vínculos educacionais, testes publicados e em
rascunho, histórico de autoavaliações, avaliações cobrindo todo o catálogo de
tipos e técnicas e quatro análises salvas. Todas as contas mock usam a senha
definida em `MOCK_USER_PASSWORD`. Remova `DEPLOY_MODE=MOCK` para impedir novas
cargas; os dados já persistidos não são apagados automaticamente.

## Estrutura

```text
src/
├── config/                 # configuração e roteamento global
├── contexts/
│   └── ia_integrations/    # contexto ia-integrations
│       └── features/
│           └── chat_bot/   # WebSocket, aplicação e adaptador MCP
├── features/
│   ├── accounts/           # feature de identidade e acesso
│   │   ├── migrations/
│   │   ├── templates/accounts/
│   │   ├── forms.py
│   │   ├── models.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── organization_settings/ # dados e papéis do criador da organização
│   └── users_manager/      # organizações, membros, turmas, testes e autoavaliações
├── static/css/
├── templates/
└── manage.py
```


## Notificações em tempo real

A área interna exibe um sino no canto superior direito com contador de não lidas,
as últimas 30 notificações e ações para marcar uma ou todas como lidas.
A landing e o onboarding não exibem esse componente.

Execute `python src/manage.py migrate` antes de iniciar o ASGI. O WebSocket
`/ws/notifications/` usa a mesma sessão do login; visitantes anônimos e origens
não permitidas são rejeitados. Nunca é aceito um destinatário enviado pelo cliente.
A conexão é refeita automaticamente e recupera os dados persistidos no banco.
A interface sincroniza as abas e verifica a sessão novamente a cada mensagem;
um heartbeat verifica sessões ociosas aproximadamente a cada minuto.

Configure `REDIS_URL` no Railway apontando para o serviço Redis. Isso é necessário
para entrega imediata entre os dois workers do Docker. O Compose já inclui Redis.
Sem a variável, a camada em memória serve apenas ao desenvolvimento com um processo.
Redis transporta os eventos; as notificações são persistidas no banco Django.
Uma falha de publicação é registrada no log e a próxima sincronização recupera
as notificações salvas.

Para enviar uma notificação, crie-a na seção **Notificações** do Django admin ou
chame o serviço nos eventos de negócio desejados:

```python
from features.notifications.services import notify_user

notify_user(recipient=user, title="Nova avaliação", message="Sua avaliação está disponível.")
```

A publicação ocorre após o commit da transação, incluindo criações pelo admin.
`bulk_create` e `QuerySet.update` não disparam os sinais de publicação: utilize
o serviço para criar notificações. Esta entrega oferece a infraestrutura e o
envio administrativo; os gatilhos automáticos de negócio podem usar esse serviço.

Contrato do socket: o servidor envia `notifications.snapshot` com `items` e
`unread_count`. O cliente envia `notifications.sync`, `notifications.read` com
`id`, ou `notifications.read_all`. Só são consultadas e alteradas notificações
do usuário autenticado. A mensagem é renderizada como texto, sem HTML.
