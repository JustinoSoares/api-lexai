# api-lexai

API para o sistema de perguntas sobre leis em Angola. Backend em FastAPI com agente LLM (Groq), SQLAlchemy 2.0 async e PostgreSQL.

## Stack

- **FastAPI** + **Uvicorn**
- **SQLAlchemy 2.0** (async, com `asyncpg`)
- **Alembic** (migrations)
- **Pydantic v2** + **pydantic-settings**
- **Groq** (LLM)
- **structlog** (logging)

## Estrutura de pastas

```
├── alembic/            # migrations Alembic
├── alembic.ini
├── app/
│   ├── api/            # rotas / endpoints FastAPI
│   ├── agent/          # lógica do agente LLM
│   │   └── tools/      # ferramentas do agente (busca web, PDF, etc.)
│   ├── db/             # engine, sessão, Base declarativa
│   ├── models/         # modelos ORM (SQLAlchemy)
│   └── core/           # configuração, logging, utilitários
└── .env.example        # modelo das variáveis de ambiente
```

## Setup

```bash
# 1. Criar e ativar o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
cp .env.example .env
#   -> preencha GROQ_API_KEY e DATABASE_URL no .env

# 4. Migrations de base de dados
alembic revision --autogenerate -m "initial"
alembic upgrade head

# 5. Correr a API
uvicorn app.main:app --reload
```

Servidor disponível em `http://localhost:8000`, documentação interativa em `/docs` e verificação de saúde em `/health`.

## Testes

```bash
pytest
```