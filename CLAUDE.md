# Cortex Template

> **Plantilla base para construir una instancia de Cortex** (plataforma
> agéntica multi-agente). Ver `README.md` para personalización paso a
> paso y `CORTEX_BLUEPRINT.md` (en el repo de AgentX) para el blueprint
> arquitectónico completo.

**Producto:** Cortex by AgentX
**Tipo:** Plataforma agéntica B2B, deployment por cliente
**Origen:** este template se extrajo de la primera instancia en producción (Fidemar Cortex)

---

## Stack técnico

- **Backend**: FastAPI + Uvicorn + Python 3.11+
- **LLM**: Google Gemini (default: `gemini-3-flash-preview`) — configurable a Anthropic Claude
- **Búsqueda catálogo**: pandas sobre CSV con ranking por relevancia + paginación
- **Auth**: JWT (PBKDF2-SHA256 para passwords)
- **Frontend**: React 18 vía CDN + Babel standalone (sin build), un solo archivo `static/index.html`
- **Rate limiting**: slowapi (in-memory)
- **Tools del agente**:
  - `catalog_search(query, offset)` — busca en el dataset del cliente
  - `verify_pdf_url(url)` — verifica HTTP que una URL sea un PDF real (con SSRF guard)
  - `fetch_product_data(url)` — scrapea páginas HTML (con SSRF guard)
  - `generate_datasheet_pdf(...)` — genera ficha técnica PDF con branding del cliente
  - `generate_word_document / generate_excel_spreadsheet` — generadores de Office
  - `tavily_search` — búsqueda web (requiere TAVILY_API_KEY)

---

## Setup rápido en una PC nueva

```powershell
# 1. Verificar Python 3.11+
python --version

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Crear .env desde el template
copy .env.example .env

# 4. Setear las claves de forma segura
python set_secret.py JWT_SECRET        # >= 32 chars random
python set_secret.py GOOGLE_API_KEY    # aistudio.google.com/apikey
python set_secret.py ADMIN_PASSWORD

# 5. Personalizar identidad del cliente (.env):
#    COMPANY_NAME=Acme
#    COMPANY_FULL_NAME=Acme S.A.
#    CORTEX_INSTANCE_ID=acme_cortex

# 6. Arrancar
python -m uvicorn main:app --host 0.0.0.0 --port 8000
# o doble-click en start_server.bat
```

Después abrir `http://localhost:8000`.

---

## Estructura del proyecto

```
cortex-template/
├── main.py                      # entry point (solo `from app.main import app`)
├── search.py                    # búsqueda en CSV (personalizar columnas si cambia el formato)
├── stock.csv                    # dataset del cliente (placeholder en el template)
├── gemini_engine.py             # provider Gemini (streaming + tool calling)
├── datasheet_tools.py           # scraping HTML + generación PDF
├── office_generators.py         # generadores Word + Excel
├── document_extract.py          # extracción de texto de PDF/DOCX/PPTX
├── set_secret.py                # helper para setear secrets vía getpass
│
├── app/
│   ├── main.py                  # FastAPI app + middlewares + routers
│   ├── config.py                # Pydantic Settings (company_name, etc.)
│   ├── auth.py                  # JWT helpers + dependencies
│   ├── errors.py                # global exception handlers
│   ├── models.py                # request models Pydantic
│   ├── logging_config.py
│   │
│   ├── agents/
│   │   ├── base.py              # AgentDefinition dataclass
│   │   ├── registry.py          # CRUD + _INITIAL_AGENTS
│   │   ├── permissions.py
│   │   ├── knowledge.py         # concat de docs por agente al prompt
│   │   ├── definitions/         # un .md por agente
│   │   │   └── demo_assistant.md
│   │   └── knowledge/           # docs de referencia por agente
│   │
│   ├── llm/                     # providers + router + tool_specs
│   ├── tools/                   # catalog, pdf_verify, tavily
│   ├── prompts/                 # system.md, admin.md (chat admin)
│   ├── routes/                  # endpoints (auth, chat, agents, admin_*)
│   ├── security/                # rate_limit, url_safety, headers, body_limit, files, log_sanitize
│   └── storage/                 # users, conversations, audit, memory, backups, atomic
│
├── static/
│   ├── index.html               # frontend React (un solo archivo)
│   ├── datasheets/              # PDFs generados (gitignored)
│   └── documents/               # Word/Excel generados (gitignored)
│
├── tests/                       # pytest
└── (runtime — gitignored)
    ├── users.json, agents.json, conversations_log.jsonl, audit_log.jsonl
    ├── memory.json, runtime_config.json
    ├── backups/YYYY-MM-DD/, logs/
```

### Archivos generados en runtime (gitignored)

- `users.json` — usuarios registrados con hashes PBKDF2
- `agents.json` — definiciones de asistentes (creado en primer startup desde `_INITIAL_AGENTS`)
- `conversations_log.jsonl` — log append-only de cada Q&A (rotado a 5MB), incluye `agent_id`
- `audit_log.jsonl` — log inmutable de acciones admin
- `memory.json` — memoria diaria generada por análisis del log
- `runtime_config.json` — overrides runtime
- `backups/YYYY-MM-DD/` — snapshot diario automático de los archivos críticos

---

## Capas de seguridad activas

- **Rate limiting** (slowapi): 5/min en login, 30/min en chat
- **SSRF defense**: bloquea fetches a IPs privadas, loopback, link-local, metadata services
- **Headers HTTP**: X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy
- **Body size limits**: login 4KB, chat 5MB, admin 200KB
- **Password policy**: mínimo 8 caracteres en users nuevos
- **Audit log inmutable** de acciones admin
- **Filename sanitization** en uploads
- **Log sanitization** de passwords/tokens en errores
- **Prompt injection guard** con marcadores `<<<USER_CONTEXT>>>`
- **Backups automáticos diarios** (retención 14 días)

---

## Sistema de agentes

- `app/agents/definitions/<id>.md` — prompts editables sin reiniciar
- `app/agents/knowledge/<id>/*.md` — docs de referencia que se concatenan al prompt
- `app/agents/registry.py:_INITIAL_AGENTS` — agentes que se crean en el primer startup
- Cada agente declara `allowed_tools` → se filtran las disponibles al modelo
- `visibility`: `public` / `private` / `users` (lista granular)
- Admin ve y usa todos. Usuario regular ve solo públicos + los `users` donde está incluido

### Para agregar/editar agentes

**Opción A — Desde el panel admin (recomendado)**:
1. Login admin en `/api/admin/login`
2. Tab "🤖 Asistentes" → Editar prompt → guardar

**Opción B — Editando archivos**:
1. Crear `app/agents/definitions/<id>.md` con el prompt
2. Agregar entry a `_INITIAL_AGENTS` en `registry.py` (o crearla por API)
3. Si se necesita knowledge base: `app/agents/knowledge/<id>/*.md`

---

## Variables de entorno (`.env`)

| Variable | Default | Descripción |
|---|---|---|
| `COMPANY_NAME` | `Demo Company` | Nombre corto del cliente (visible en PDFs/Word) |
| `COMPANY_FULL_NAME` | `Demo Company S.A.` | Razón social |
| `COMPANY_INDUSTRY` | `generic` | Industria (clasificación libre) |
| `CORTEX_INSTANCE_ID` | `demo_cortex` | ID único de instancia |
| `LLM_PROVIDER` | `gemini` | `gemini` o `anthropic` |
| `GOOGLE_API_KEY` | — | Obligatorio si gemini |
| `ANTHROPIC_API_KEY` | — | Obligatorio si anthropic |
| `TAVILY_API_KEY` | — | Opcional. Habilita búsqueda web |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Modelo activo |
| `CHAT_USER` | `demo` | Usuario inicial (migrado a users.json en primer login) |
| `CHAT_PASSWORD` | — | Password inicial |
| `ADMIN_USER` | `admin` | Usuario del panel administrativo |
| `ADMIN_PASSWORD` | — | Password admin |
| `JWT_SECRET` | — | **Obligatorio**. >=32 chars random, único por instancia |
| `CORS_ORIGINS` | `http://localhost:8000,...` | Lista CSV |
| `MOCK_MODE` | `false` | Si `true`, responde simulado sin llamar al LLM |
| `RATE_LIMIT_ENABLED` | `true` | Setear `false` solo en tests |

### ⚠️ Cómo NUNCA configurar secrets

- ❌ No pegues secrets directamente en `.env` desde un terminal con history activo
- ❌ No commitees `.env` (está en `.gitignore`)
- ❌ No leas `.env` con `Read`/`cat` si después vas a pasarlo a otro contexto
- ✅ Usá `python set_secret.py <VAR>` — usa `getpass`, no echoea

---

## Endpoints API principales

### Públicos
- `POST /api/login` — auth usuarios regulares
- `POST /api/admin/login` — auth del admin

### Auth requerida (JWT)
- `GET /api/agents` — lista los asistentes que el usuario puede ver/usar
- `POST /api/chat/stream` — SSE streaming. Body: `{messages, system_context, agent_id?}`. Eventos: `text`, `thinking`, `done`, `error`, `model_selected`
- `POST /api/reload-stock` — recarga el dataset CSV en memoria
- `POST /api/upload-document` — subir documento para extraer texto al contexto

### Admin requerido
- `GET/POST /api/admin/system-prompt` — personalización global
- `GET/POST /api/admin/model` — modelo Gemini activo
- `GET/POST /api/admin/auto-route` — router automático on/off
- `GET/POST/DELETE /api/admin/users[/{username}]`
- `GET/POST/DELETE /api/admin/agents[/{id}]`
- `GET/PUT /api/admin/agents/{id}/prompt` — editor de prompts
- `GET /api/admin/memory` + `POST /api/admin/memory/refresh`
- `GET /api/admin/conversations?user=X&limit=N`
- `POST /api/admin/chat/stream` — chat del admin con `save_behavior` tool

---

## Convenciones del codebase

### Streaming SSE
```
data: {"type": "text", "text": "..."}\n\n
data: {"type": "thinking", "tool": "catalog_search", "query": "...", "status": "done", "count": 10, "total": 50}\n\n
data: {"type": "done"}\n\n
```

El frontend usa `readSSE(res, onEvent)` (helper en `index.html`).

### Agentic loop
- Max **12 iteraciones** por consulta (`settings.max_agent_iterations`)
- Si `verify_pdf_url` o `fetch_product_data` devuelven una URL bloqueada por SSRF, el agente la descarta
- Si `generate_datasheet_pdf`, se sirve en `/datasheets/cortex_<id>.pdf`

### Frontend
- Un solo archivo `static/index.html` con React vía CDN + Babel standalone
- **NO usar comentarios JSX (`{/* ... */}`) después de cerrar tags al final del return** — Babel standalone los rechaza
- Design tokens en `:root` CSS vars
- Dark mode con `data-theme="dark"` en `<html>`
- Mobile responsive con sidebar off-canvas en `<720px`

### Logging y privacidad
- Conversaciones se loguean a `conversations_log.jsonl` (truncado a 600+1200 chars)
- Audit log inmutable en `audit_log.jsonl`
- Sanitización de passwords/tokens antes de loguear errores
- Rotación automática de log a 5MB

---

## Para Claude Code

Cuando una IA Claude lea este repo para implementar/modificar:

1. **Verificá Python 3.11+** y dependencias instaladas
2. **No leas `.env`** con `Read` si tiene secrets reales
3. **No reemplaces `stock.csv`** sin avisar al admin (es el catálogo del cliente)
4. **No commitees** sin confirmar — el repo tiene `.gitignore` pero igual revisá
5. **Antes de tocar `app/security/`**, leé el blueprint y entendé qué hace cada capa
6. **Tests siempre**: corré `python -m pytest tests/` antes de cualquier cambio
7. **Después de cambios**: corré los tests y verificá `/api/health`

---

## Comandos útiles

```powershell
# Dev con auto-reload
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Tests
python -m pytest tests/ -v

# Probar login
curl -X POST http://localhost:8000/api/login -H "Content-Type: application/json" -d "{\"username\":\"demo\",\"password\":\"demo1234\"}"

# Setup acceso LAN (necesita admin)
powershell -ExecutionPolicy Bypass -File setup_lan.ps1

# Instalar como Windows Service (necesita admin)
install_service.bat
```
