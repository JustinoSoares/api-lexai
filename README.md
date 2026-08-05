# api-lexai

API para o sistema de perguntas sobre leis em Angola. Backend em FastAPI com agente LLM (Groq), SQLAlchemy 2.0 async e PostgreSQL.

O agente pesquisa legislação angolana na web (com priorização de fontes jurídicas de referência, como Lex.ao e o Diário da República), extrai o texto de diplomas e responde com base em artigos citados, sempre com a fonte.

## Stack

- **FastAPI** + **Uvicorn**
- **SQLAlchemy 2.0** (async, com `asyncpg`)
- **Alembic** (migrations)
- **Pydantic v2** + **pydantic-settings**
- **Groq** (LLM)
- **Redis** (rate limiting) — com fallback em memória
- **structlog** (logging)

## Estrutura de pastas

```
├── alembic/            # migrations Alembic
├── alembic.ini
├── app/
│   ├── api/            # rotas / endpoints FastAPI
│   ├── agent/          # lógica do agente LLM
│   │   ├── tools/      # ferramentas do agente (busca web, HTML, PDF, cache)
│   │   └── system_prompt.py
│   ├── core/           # configuração, logging, utilitários
│   ├── data/           # seed curado das leis prioritárias (app/data/laws.py)
│   ├── db/             # engine, sessão, Base declarativa, cliente Redis
│   ├── models/         # modelos ORM (SQLAlchemy)
│   └── schemas/        # esquemas Pydantic de entrada/saída
├── scripts/
│   └── seed_laws.py    # extrai e popula law_cache com as leis prioritárias
├── tests/              # testes (pytest)
├── docker-compose.yml  # PostgreSQL, Redis e RabbitMQ para desenvolvimento
└── .env.example        # modelo das variáveis de ambiente
```

## Pré-requisitos

- Python 3.11+
- PostgreSQL e Redis (locais ou via `docker compose`)
- Chave de API da [Groq](https://console.groq.com/)

## Setup local

### 1. Dependências de infraestrutura (PostgreSQL, Redis)

Com Docker (recomendado):

```bash
docker compose up -d
```

Os containers expõem PostgreSQL na porta `5434`, Redis na `6378` e RabbitMQ em `5673/15673`. Ajuste `DATABASE_URL` e `REDIS_URL` no `.env` em conformidade (ver abaixo).

Sem Docker: instale PostgreSQL e Redis localmente e ajuste as portas no `.env`.

### 2. Ambiente Python e dependências

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Nota: o `ddgs` usa `pyproject` e pode exigir pip recente. Se houver erros de resolução, atualize o pip com `pip install --upgrade pip`.

### 3. Variáveis de ambiente

```bash
cp .env.example .env
```

Preencha pelo menos `GROQ_API_KEY` e `DATABASE_URL`. O mínimo para correr contra o `docker compose`:

```
GROQ_API_KEY=sua_chave
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5434/lexai
REDIS_URL=redis://localhost:6378/0
```

### 4. Migrations

```bash
alembic upgrade head
```

### 5. Seed das leis prioritárias (opcional, mas recomendado)

Carrega o texto integral das 3 leis curadas no `law_cache` (base de grounding do agente):

```bash
python -m scripts.seed_laws
```

Para só listar o que seria gravado, sem escrever na base:

```bash
python -m scripts.seed_laws --list
```

### 6. Correr a API

```bash
uvicorn app.main:app --reload
```

Servidor disponível em `http://localhost:8000`, documentação interativa em `/docs` e verificação de saúde em `/health`.

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `APP_NAME` | `api-lexai` | Nome da aplicação |
| `DEBUG` | `false` | Modo debug do FastAPI |
| `LOG_LEVEL` | `INFO` | Nível de logging |
| `APP_HOST` | `0.0.0.0` | Host do servidor |
| `APP_PORT` | `8000` | Porta do servidor |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Origens CORS permitidas (lista JSON) |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/lexai` | URL da base de dados (com `docker compose`, porta `5434`) |
| `REDIS_URL` | `redis://localhost:6379/0` | URL do Redis (com `docker compose`, porta `6378`) |
| `GROQ_API_KEY` | *(vazio)* | Chave de API da Groq — obrigatória |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Modelo LLM da Groq |
| `LLM_MAX_TOKENS` | `2048` | Máximo de tokens por resposta |
| `LLM_TEMPERATURE` | `0.3` | Temperatura do modelo |
| `LLM_GROUND_MAX_CHARS` | `12000` | Orçamento (chars) de texto de diploma injetado como grounding |
| `WEB_SEARCH_ENABLED` | `true` | Ativa/desativa a busca web |
| `RATE_LIMIT_ENABLED` | `false` | Ativa o rate limiting do `/chat` |
| `RATE_LIMIT_MAX_REQUESTS` | `10` | Máximo de pedidos por janela |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Janela do rate limit (segundos) |
| `RATE_LIMIT_USER_HEADER` | `X-User-Id` | Header usado para identificar o utilizador |

## API

- `GET /health` — verificação de saúde.
- `POST /chat` — pergunta jurídica ao agente. Corpo:

```json
{
  "question": "Qual o prazo de prescrição dos créditos do trabalhador?",
  "conversation_id": "uuid-opcional"
}
```

Resposta: `conversation_id`, `question`, `answer` e `sources` (URLs citadas).

O rate limiting (quando ativo) identifica o utilizador pelo header `X-User-Id`.

## Testes

```bash
pytest
```

## Limitações do MVP

Este é um MVP; conhece e aceita as seguintes limitações:

- **Dependência de `ddgs` não-oficial** — a busca web usa `ddgs` (cliente não oficial da DuckDuckGo), que não tem garantia de estabilidade nem SLA. Pode falhar ou ser bloqueada sem aviso; nesses casos o agente degrada para o grounding local (`law_cache`). Não usar como única fonte de verdade em produção.
- **Apenas 3 leis pré-carregadas** — o seed curado cobre a Lei Geral do Trabalho (Lei n.º 7/15), a Lei de Defesa do Consumidor (Lei n.º 15/03) e a Lei do Sistema de Pagamentos (Lei n.º 40/20). Perguntas sobre outras leis dependem de busca web em tempo real e não têm a mesma fiabilidade do grounding local.
- **Sem autenticação completa** — não existe registo de utilizadores, login, JWT ou controlo de acesso por perfil. O rate limiting usa um header opcional (`X-User-Id`) e não constitui autenticação. O `POST /chat` é publicamente acessível.
- **Sem revisão jurídica formal das respostas** — as respostas são geradas por LLM e não passam por revisão humana ou validação jurídica. Ainda que o prompt instrua a não inventar leis nem fontes e a citar apenas fontes verificadas, pode haver erros, omissões ou interpretações incorretas. Não substitui aconselhamento jurídico profissional.
