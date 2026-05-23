# Cortex Template

> **Base template for building a new Cortex instance.**
> Product: Cortex by AgentX.

This repo is the **starting point**. To create a new Cortex for a client, follow this README step by step. Estimated time: **1–2 days** of customization to have something testable, **5–7 days** for a production-ready deployment.

## What is Cortex?

A B2B agentic platform where a company deploys multiple specialized AI assistants (called "agents"), each with its own prompt, knowledge domain, and set of tools.

**Not a ChatGPT wrapper** — it's a full-stack application with multi-agent support, granular permissions, a knowledge base, tool calling, an admin panel, and a hardened security layer.

**One instance = one client.** Each company gets its own isolated Cortex with its own domain, agents, and data.

## Workflow: creating an instance for `<Client>` from scratch

### Step 1 — Create a new repo from this template

**Option A — Via GitHub (recommended):**

1. Go to this repo on GitHub
2. Click **"Use this template"** → **"Create a new repository"**
3. Name: `<client>-cortex` (e.g., `acme-cortex`)
4. Set visibility to **Private**
5. Clone it locally:

```bash
git clone https://github.com/AgentX/<client>-cortex
cd <client>-cortex
```

**Option B — Clone manually:**

```bash
git clone https://github.com/AgentX/cortex-template <client>-cortex
cd <client>-cortex
# Start a clean git history:
rm -rf .git
git init
git add -A
git commit -m "initial: <client> cortex from template v1"
```

### Step 2 — Set up the Python environment

```bash
python --version  # must be >= 3.11
pip install -r requirements.txt
python -m pytest tests/ -v  # all tests must pass
```

> If tests don't pass at this point, **do not continue** — something is broken in the template.

### Step 3 — Configure client identity

```bash
copy .env.example .env
```

Edit `.env`:

```env
# Client identity
COMPANY_NAME=Acme
COMPANY_FULL_NAME=Acme S.A.
COMPANY_INDUSTRY=manufacturing
CORTEX_INSTANCE_ID=acme_cortex

# First user
CHAT_USER=admin_client
CHAT_PASSWORD=SomethingStrong123!

# CORS — real domains where the app will be served
CORS_ORIGINS=http://localhost:8000,https://cortex.acme.com
```

Set secrets without plain-text exposure:

```bash
python set_secret.py JWT_SECRET      # any random string >= 32 chars
python set_secret.py GOOGLE_API_KEY  # generate at aistudio.google.com/apikey
python set_secret.py TAVILY_API_KEY  # optional — $5/mo at tavily.com
python set_secret.py ADMIN_PASSWORD  # use a strong password
```

### Step 4 — Load the client dataset

Replace `stock.csv` (which ships with 20 demo products) with the client's real catalog. Expected format:

```
;;;;;;
[descriptive title];;;;;;
[company name];;;;;;
[extra metadata];;;;;;
;;;;;;
Code;Description;;;;;
ABC-001;PRODUCT 1;;;;;
ABC-002;PRODUCT 2;;;;;
```

- Separator: `;` (semicolon)
- Encoding: UTF-8 (with or without BOM)
- Header on line 7, data starts on line 8

If the client's CSV format differs, edit `search.py` to adapt the parsing. Keep the interface: `search_stock(query, limit, offset) -> dict`.

### Step 5 — Define the initial agents

Edit `app/agents/registry.py` → `_INITIAL_AGENTS` and replace the "Demo Assistant" with the client's real agents.

Example:

```python
_INITIAL_AGENTS: list[AgentDefinition] = [
    AgentDefinition(
        id="ana",
        name="ANA · Sales Assistant",
        description="Product and inventory advisory for Acme S.A.",
        icon="💼",
        allowed_tools=["catalog_search", "tavily_search", "generate_word_document"],
        default_tier="auto",
        visibility="public",
        is_default=True,
    ),
    AgentDefinition(
        id="quality_check",
        name="Quality Checker",
        description="ISO 9001 compliance + Acme internal standards",
        icon="✅",
        allowed_tools=["tavily_search", "verify_pdf_url"],
        default_tier="pro",
        visibility="private",
    ),
]
```

### Step 6 — Write each agent's system prompt

Create `app/agents/definitions/<agent_id>.md` with the agent's full system prompt. Typical structure:

```markdown
# Identity
You are [NAME], the [ROLE] at [COMPANY].

## Capabilities
- ...

## Behavior rules
- ...

## Available tools
- ...

## Response format
- ...
```

### Step 7 — Knowledge base per agent (optional)

For agents that need reference documents (standards, internal catalogs, client-specific manuals):

```
app/agents/knowledge/<agent_id>/
├── _README.md          # ignored (underscore prefix)
├── internal_manual.md  # loaded into the system prompt
└── iso_standards.md    # loaded into the system prompt
```

Only `.md` files. For PDFs, convert the text to markdown (ideally with well-formatted tables).

### Step 8 — Remove Demo Assistant references

```bash
# Remove the demo after defining real agents
rm app/agents/definitions/demo_assistant.md
```

And in `app/config.py`:

```python
DEFAULT_AGENT_ID = "ana"  # the client's flagship agent id
```

### Step 9 — Frontend branding

Edit `static/index.html` and find/replace `Demo Company` with the client's name. Key locations:

- `<title>` (line ~6)
- `.brand-logo` and `.brand-cortex` (topbar)
- `.login-logo` and "Internal access" (login screen)
- Welcome screen message if customized

### Step 10 — Run tests with the real setup

```bash
python -m pytest tests/ -v
```

If any agent or catalog test fails, adjust the tests to match the client's actual data. **Never skip tests.**

### Step 11 — Local smoke test

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

- `http://localhost:8000` → log in with `CHAT_USER` and `CHAT_PASSWORD` from `.env`
- Test each agent with 3–5 real queries
- `/api/health` → all checks green
- Create/delete a test user from the admin panel
- Edit an agent prompt from the admin → verify it applies immediately

### Step 12 — Commit + push

```bash
git add -A
git commit -m "config: initial setup for <Client>"
git push origin main
```

### Step 13 — Deployment

Options in order of preference (see `CORTEX_BLUEPRINT.md` for details):

- **Dedicated PC at client's office** (Windows Service via NSSM):
  ```bat
  install_service.bat  # run as administrator
  ```
- **Dedicated VPS** (Hetzner/DigitalOcean/Antel Cloud) — Linux + systemd + Caddy/Cloudflare for HTTPS
- **Client's cloud** (AWS/Azure/GCP) — only if the client requires it

### Step 14 — Final checklist before go-live

- [ ] All tests pass
- [ ] `/api/health` returns `status: ok` with all checks green
- [ ] `JWT_SECRET` unique, >= 32 chars, randomly generated
- [ ] `ADMIN_PASSWORD` strong, shared via a secure channel
- [ ] `CORS_ORIGINS` points only to the real domain
- [ ] HTTPS working (valid certificate)
- [ ] Backups running (verify `backups/YYYY-MM-DD/`)
- [ ] Audit log active (admin login → entry in `audit_log.jsonl`)
- [ ] Each agent tested with 3–5 real client queries
- [ ] Documentation delivered to admin
- [ ] Support plan for the first 2 weeks agreed upon
- [ ] Service auto-starts on boot (NSSM or systemd)

**If any item is missing, do not go live.**

---

## Instance maintenance

### When I update the template, how do I propagate changes to the client?

If the client was created with "Use this template" (no upstream remote), add the template as a remote and merge:

```bash
cd <client>-cortex
git remote add upstream https://github.com/AgentX/cortex-template
git fetch upstream
git merge upstream/main --allow-unrelated-histories
# Resolve conflicts if any (typically in static/index.html due to branding)
```

### When a client wants to add a new agent

Best option: do it from the admin panel (tab "🤖 Assistants" → "+ New agent" → edit prompt → save).

If knowledge files are needed, upload the `.md` files via SFTP/VS Code Remote and confirm availability (mtime cache — no restart required).

---

## Template structure

See `CLAUDE.md` for the detailed file structure and `CORTEX_BLUEPRINT.md` (AgentX repo) for the complete architectural blueprint.

## Support

- Full blueprint: `CORTEX_BLUEPRINT.md`
- Issues / bugs: open an issue in this repo

---

*Cortex Template v1.0 — by AgentX*
