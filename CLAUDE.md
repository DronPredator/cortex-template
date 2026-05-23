# RR Mecánica Cortex

Cortex instance for **RR Mecánica Automotriz** — automotive workshop. Built on top of the generic Cortex template (multi-agent agentic platform).

**Product:** Cortex by AgentX
**Client:** RR Mecánica Automotriz (taller mecánico)
**Language:** Spanish (rioplatense) — enforced via `LANGUAGE_DIRECTIVE` in `.env`

## Initial agents

- **Consultor Técnico** (`consultor_tecnico`, default) — diagnóstico, procedimientos, especificaciones, investigación técnica. Tools: `tavily_search`, `verify_pdf_url`, `fetch_product_data`, `catalog_search`.
- **Generador de Reportes** (`generador_reportes`) — informes técnicos, presupuestos, órdenes de reparación, planillas. Tools: `generate_word_document`, `generate_excel_spreadsheet`, `generate_datasheet_pdf`, `catalog_search`, `tavily_search`.

Definitions live in `app/agents/definitions/<id>.md` (editable from the admin panel or directly on disk; mtime-cached). Knowledge files (optional) in `app/agents/knowledge/<id>/*.md`.

## Tech stack

- **Backend:** FastAPI + Uvicorn + Python 3.11+
- **LLM:** Google Gemini (default: `gemini-3-flash-preview`) — configurable to Anthropic Claude
- **Catalog search:** pandas over CSV with relevance ranking + pagination
- **Auth:** JWT (PBKDF2-SHA256 for passwords)
- **Frontend:** React 18 via CDN + Babel standalone (no build step), single file `static/index.html`
- **Rate limiting:** slowapi (in-memory)
- **Agent tools:**
  - `catalog_search(query, offset)` — searches the client's dataset
  - `verify_pdf_url(url)` — verifies via HTTP that a URL serves a real PDF (with SSRF guard)
  - `fetch_product_data(url)` — scrapes HTML pages (with SSRF guard)
  - `generate_datasheet_pdf(...)` — generates a PDF spec sheet with client branding
  - `generate_word_document` / `generate_excel_spreadsheet` — Office document generators
  - `tavily_search` — web search (requires `TAVILY_API_KEY`)

## Quick setup on a new machine

```bash
# 1. Verify Python 3.11+
python --version

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env from the template
copy .env.example .env

# 4. Set secrets securely
python set_secret.py JWT_SECRET      # >= 32 random chars
python set_secret.py GOOGLE_API_KEY  # aistudio.google.com/apikey
python set_secret.py ADMIN_PASSWORD

# 5. Set client identity in .env:
# COMPANY_NAME=Acme
# COMPANY_FULL_NAME=Acme S.A.
# CORTEX_INSTANCE_ID=acme_cortex

# 6. Start
python -m uvicorn main:app --host 0.0.0.0 --port 8000
# or double-click start_server.bat
```

Then open `http://localhost:8000`.

## Project structure

```
cortex-template/
├── main.py               # entry point (just `from app.main import app`)
├── search.py             # CSV search (customize columns if format changes)
├── stock.csv             # client dataset (demo placeholder in the template)
├── gemini_engine.py      # Gemini provider (streaming + tool calling)
├── datasheet_tools.py    # HTML scraping + PDF generation
├── office_generators.py  # Word + Excel generators
├── document_extract.py   # text extraction from PDF/DOCX/PPTX
├── set_secret.py         # helper to set secrets via getpass
│
├── app/
│   ├── main.py           # FastAPI app + middlewares + routers
│   ├── config.py         # Pydantic Settings (company_name, etc.)
│   ├── auth.py           # JWT helpers + dependencies
│   ├── errors.py         # global exception handlers
│   ├── models.py         # Pydantic request models
│   ├── logging_config.py
│   │
│   ├── agents/
│   │   ├── base.py          # AgentDefinition dataclass
│   │   ├── registry.py      # CRUD + _INITIAL_AGENTS
│   │   ├── permissions.py
│   │   ├── knowledge.py     # concatenates per-agent docs into the prompt
│   │   ├── definitions/     # one .md file per agent
│   │   │   ├── consultor_tecnico.md
│   │   │   └── generador_reportes.md
│   │   └── knowledge/       # per-agent reference docs
│   │       ├── consultor_tecnico/
│   │       └── generador_reportes/
│   │
│   ├── llm/       # providers + router + tool_specs
│   ├── tools/     # catalog, pdf_verify, tavily
│   ├── prompts/   # system.md, admin.md (admin chat)
│   ├── routes/    # endpoints (auth, chat, agents, admin_*)
│   ├── security/  # rate_limit, url_safety, headers, body_limit, files, log_sanitize
│   └── storage/   # users, conversations, audit, memory, backups, atomic
│
├── static/
│   ├── index.html    # React frontend (single file)
│   ├── datasheets/   # generated PDFs (gitignored)
│   └── documents/    # generated Word/Excel (gitignored)
│
├── tests/            # pytest
└── (runtime — gitignored)
    ├── users.json, agents.json, conversations_log.jsonl, audit_log.jsonl
    ├── memory.json, runtime_config.json
    ├── backups/YYYY-MM-DD/, logs/
```

## Runtime files (gitignored)

| File | Description |
|---|---|
| `users.json` | registered users with PBKDF2 hashes |
| `agents.json` | assistant definitions (created on first startup from `_INITIAL_AGENTS`) |
| `conversations_log.jsonl` | append-only Q&A log (rotated at 5 MB), includes `agent_id` |
| `audit_log.jsonl` | immutable admin action log |
| `memory.json` | daily memory generated by log analysis |
| `runtime_config.json` | runtime overrides |
| `backups/YYYY-MM-DD/` | automatic daily snapshot of critical files |

## Active security layers

- **Rate limiting** (slowapi): 5/min on login, 30/min on chat
- **SSRF defense**: blocks fetches to private IPs, loopback, link-local, metadata services
- **HTTP headers**: X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy
- **Body size limits**: login 4 KB, chat 5 MB, admin 200 KB
- **Password policy**: minimum 8 characters for new users
- **Immutable audit log** of admin actions
- **Filename sanitization** on uploads
- **Log sanitization** of passwords/tokens in error messages
- **Prompt injection guard** with `<<<USER_CONTEXT>>>` markers
- **Automatic daily backups** (14-day retention)

## Agent system

- `app/agents/definitions/<id>.md` — prompts editable without restarting
- `app/agents/knowledge/<id>/*.md` — reference docs concatenated into the system prompt
- `app/agents/registry.py:_INITIAL_AGENTS` — agents created on first startup
- Each agent declares `allowed_tools` → filters available tools for the model
- `visibility: public / private / users` (granular list)
- Admin sees and uses all. Regular users see only public ones + `users` entries they belong to

### Adding / editing agents

**Option A — From the admin panel (recommended):**

1. Log in as admin at `/api/admin/login`
2. Tab "🤖 Assistants" → Edit prompt → save

**Option B — Editing files:**

1. Create `app/agents/definitions/<id>.md` with the prompt
2. Add an entry to `_INITIAL_AGENTS` in `registry.py` (or create via API)
3. If a knowledge base is needed: `app/agents/knowledge/<id>/*.md`

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `COMPANY_NAME` | `Demo Company` | Short client name (visible in PDFs/Word) |
| `COMPANY_FULL_NAME` | `Demo Company S.A.` | Legal name |
| `COMPANY_INDUSTRY` | `generic` | Industry (free-form) |
| `CORTEX_INSTANCE_ID` | `demo_cortex` | Unique instance ID |
| `LLM_PROVIDER` | `gemini` | `gemini` or `anthropic` |
| `GOOGLE_API_KEY` | — | Required if `gemini` |
| `ANTHROPIC_API_KEY` | — | Required if `anthropic` |
| `TAVILY_API_KEY` | — | Optional. Enables web search |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Active model |
| `CHAT_USER` | `demo` | Initial user (migrated to `users.json` on first login) |
| `CHAT_PASSWORD` | — | Initial password |
| `ADMIN_USER` | `admin` | Admin panel user |
| `ADMIN_PASSWORD` | — | Admin password |
| `JWT_SECRET` | — | Required. >= 32 random chars, unique per instance |
| `CORS_ORIGINS` | `http://localhost:8000,...` | CSV list |
| `MOCK_MODE` | `false` | If `true`, responds without calling the LLM |
| `RATE_LIMIT_ENABLED` | `true` | Set to `false` only in tests |

### ⚠️ How to NEVER configure secrets

```
❌ Do not paste secrets directly into .env from a terminal with history enabled
❌ Do not commit .env (it's in .gitignore)
❌ Do not read .env with Read/cat if you'll pass it to another context
✅ Use python set_secret.py <VAR> — uses getpass, does not echo
```

## Main API endpoints

### Public

- `POST /api/login` — user auth
- `POST /api/admin/login` — admin auth

### Auth required (JWT)

- `GET /api/agents` — list agents the user can see/use
- `POST /api/chat/stream` — SSE streaming. Body: `{messages, system_context, agent_id?}`. Events: `text`, `thinking`, `done`, `error`, `model_selected`
- `POST /api/reload-stock` — reload the CSV dataset in memory
- `POST /api/upload-document` — upload a document to extract text into context

### Admin required

- `GET/POST /api/admin/system-prompt` — global customization
- `GET/POST /api/admin/model` — active Gemini model
- `GET/POST /api/admin/auto-route` — automatic router on/off
- `GET/POST/DELETE /api/admin/users[/{username}]`
- `GET/POST/DELETE /api/admin/agents[/{id}]`
- `GET/PUT /api/admin/agents/{id}/prompt` — prompt editor
- `GET /api/admin/memory` + `POST /api/admin/memory/refresh`
- `GET /api/admin/conversations?user=X&limit=N`
- `POST /api/admin/chat/stream` — admin chat with `save_behavior` tool

## Codebase conventions

### SSE streaming format

```
data: {"type": "text", "text": "..."}\n\n
data: {"type": "thinking", "tool": "catalog_search", "query": "...", "status": "done", "count": 10, "total": 50}\n\n
data: {"type": "done"}\n\n
```

The frontend uses `readSSE(res, onEvent)` (helper in `index.html`).

### Agentic loop

- Max 12 iterations per query (`settings.max_agent_iterations`)
- If `verify_pdf_url` or `fetch_product_data` return a URL blocked by SSRF, the agent discards it
- If `generate_datasheet_pdf` is called, the file is served at `/datasheets/cortex_<id>.pdf`

### Frontend

- Single file `static/index.html` with React via CDN + Babel standalone
- **Do not use JSX comments** (`{/* ... */}`) after closing tags at the end of a `return` — Babel standalone rejects them
- Design tokens in `:root` CSS vars
- Dark mode via `data-theme="dark"` on `<html>`
- Mobile responsive with off-canvas sidebar at < 720px

### Logging and privacy

- Conversations logged to `conversations_log.jsonl` (truncated to 600+1200 chars)
- Immutable audit log in `audit_log.jsonl`
- Password/token sanitization before logging errors
- Automatic log rotation at 5 MB

## For Claude Code

When an AI Claude reads this repo to implement or modify:

1. Verify Python 3.11+ and dependencies are installed
2. Do not read `.env` with Read if it contains real secrets
3. Do not replace `stock.csv` without notifying the admin (it's the client's catalog)
4. Do not commit without confirming — the repo has `.gitignore` but still review
5. Before touching `app/security/`, read the blueprint and understand each security layer
6. Always run tests: `python -m pytest tests/` before any change
7. After changes: run tests and verify `/api/health`

## Useful commands

```bash
# Dev with auto-reload
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Tests
python -m pytest tests/ -v

# Test login
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo1234"}'

# LAN access setup (requires admin)
powershell -ExecutionPolicy Bypass -File setup_lan.ps1

# Install as Windows Service (requires admin)
install_service.bat
```
