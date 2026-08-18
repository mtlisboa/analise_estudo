# Análise de Estudo

Base de uma aplicação para análise da capacidade e do desempenho de estudantes.

## Stack

- Python 3.12+
- Django 5.2
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

## Estrutura

```text
src/
├── config/                 # configuração e roteamento global
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
