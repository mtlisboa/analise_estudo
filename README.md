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
python src/manage.py runserver
```

Acesse `http://127.0.0.1:8000/` para ver a landing page. O painel individual
fica em `/painel/` e exige autenticação; uma nova conta pode ser criada em
`/conta/cadastro/`.

O tema claro/escuro acompanha a preferência do sistema no primeiro acesso e a
escolha feita no botão do cabeçalho fica salva no navegador.

## Gestão de usuários

O módulo `users_manager` mantém uma única identidade autenticável para cada
pessoa. Professor e aluno são papéis contextuais definidos por vínculos e
participações em turmas; gestor e administrador são papéis globais. O módulo
permite:

- solicitar e aceitar vínculos entre professores e alunos;
- criar turmas e convidar participantes como professor ou aluno;
- registrar autoavaliações de foco, organização, compreensão e motivação;
- usar o login comum em `/conta/entrar/` para todas as contas, exceto sysadmin;
- autenticar sysadmins exclusivamente em `/sysadmin/entrar/`.

Organizações não fazem parte deste módulo.

## Testes

```bash
python src/manage.py test
```

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

A imagem executa a aplicação com Gunicorn na porta `8000` usando um usuário
não-root. Antes da primeira execução, aplique as migrações ou utilize o
Docker Compose descrito abaixo.

## Docker Compose

```bash
docker compose up --build
```

O serviço aplica as migrações antes de iniciar o Gunicorn. O banco SQLite fica
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
│   └── users_manager/      # vínculos, turmas e autoavaliações
├── static/css/
├── templates/
└── manage.py
```
