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

Acesse `http://127.0.0.1:8000/`. A página inicial exige autenticação; um
usuário novo pode ser criado em `/conta/cadastro/`.

## Testes

```bash
python src/manage.py test
```

## Estrutura

```text
src/
├── config/                 # configuração e roteamento global
├── features/
│   └── accounts/           # feature de identidade e acesso
│       ├── migrations/
│       ├── templates/accounts/
│       ├── forms.py
│       ├── models.py
│       ├── urls.py
│       └── views.py
├── static/css/
├── templates/
└── manage.py
```
