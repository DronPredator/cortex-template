# Changelog — Cortex Template

All notable changes to the base Cortex blueprint are documented here. This template serves as the starting point for new deployments of the multi-agent agentic platform.

Format: [Keep a Changelog](https://keepachangelog.com) · SemVer: `MAJOR.MINOR.PATCH`.

---

## [2.1.1] — 2026-05-22

Public-release cleanup. No functional changes — only branding,
terminology, and LLM-facing language alignment.

### Removed — Client-specific brand references

- All occurrences of the reference deployment's brand name removed from
  the entire repo: backend Python (constants, FastAPI title, log
  filenames, NSSM service name, color constants), frontend (localStorage
  keys, document title, manifest, login screen, generated PDF headers),
  scripts, and tests.
- Reference-deployment agent names (used as placeholders in tests and
  comments) replaced with the generic `demo_assistant`.
- ~101 replacements across 17 files. Verified: 0 brand references
  remain anywhere in the repo.

### Changed — LLM-facing prompts translated to English

Strings that the model actually reads (tool descriptions, system
prompts, agent definitions, and the prompt-injection guard) are now in
English for clarity in a public template. Deployments can override any
of these in their `.env` / `agents.json` / `app/agents/definitions/*.md`
with their own language.

Files updated:
- `app/llm/tool_specs.py` — all 9 tool descriptions and input schemas.
- `app/prompts/system.md` — minimal admin-chat base prompt.
- `app/prompts/admin.md` — administrator-mode chat prompt.
- `app/agents/definitions/demo_assistant.md` — template demo agent.
- `app/storage/memory.py` — memory-summary analysis prompt.
- `app/routes/chat.py` — prompt-injection guard wrapper around uploaded
  user content (the security-critical text that tells the model to
  treat uploads as data, not instructions).

### Note — UI strings & internal comments

UI strings inside `static/index.html` (welcome screen, button labels,
error toasts) and internal Python comments are left in the original
language for now. Downstream deployments can translate or override per
locale. The `LANGUAGE_DIRECTIVE` env var also gives deployments full
control over the language of model outputs and internal thoughts.

### Tests

Suite unchanged structurally — **160/160 passing**.

---

## [2.1.0] — 2026-05-22

Sync from the reference deployment (Cortex v1.4.1 → v1.5.0) — three
operational improvements landed there that are generic enough to be useful
to any deployment.

### Added — Persistent session (no more mid-shift logouts)

- **`JWT_EXPIRE_HOURS` default raised from 8h → 24h.** 8h forced re-login
  mid-shift (>9h workdays). 24h covers any normal workday. For longer
  sessions, see refresh below. Configurable via env.
- **New `POST /api/auth/refresh` endpoint.** Accepts a valid JWT and
  returns a fresh one with renewed expiration. Preserves the original
  token's `role` claim (admin → admin). Returns 401 if the token already
  expired — frontend sends to login.
- **Automatic background refresh every 6h** in the frontend (Gmail-style).
  While the tab is open and the user is active, the JWT is renewed
  silently — covering both the chat token (localStorage) AND the admin
  token (sessionStorage). Closing the tab overnight means the next day
  the user logs in normally.

### Added — Long-response handling

- **`max_output_tokens` raised from 4096 → 16384.** Gemini Flash supports
  up to 65,536; 16K gives 4× headroom for detailed technical responses
  without forcing the user to type "continue".
- **`finish_reason=MAX_TOKENS` detection** in `gemini_engine.py`. When
  the model hits the cap, emits a new SSE event `truncated` before
  `done`. The frontend persists `truncated: true` on the message and
  renders a **"Continue generation →" button** with a clear notice:
  "The response was cut off because it reached the token limit." Clicking
  appends a synthetic "continue" user message and streams from where the
  model left off — single visible flow for the user, no manual typing.

### Added — Persisted thoughts viewer

- Model thoughts (Gemini's `include_thoughts=True` stream) are now
  **persisted with each message** instead of being ephemeral.
- New **`ThoughtsViewer` component**: collapsible block beneath each
  assistant message, **closed by default** so it doesn't distract
  non-technical readers. Uses native `<details>` (no React state — the
  browser preserves open/closed per instance).
- Header shows a 💭 icon + a chip with the thought size and detected
  language (e.g. `(12,453 characters · in English)`). If the deployment
  sets `LANGUAGE_DIRECTIVE` to force a non-English language, the chip
  updates automatically.
- **Cap of 30,000 characters** per message to avoid bloating localStorage
  in long sessions. Excess is truncated with a clear marker.
- Thoughts persist across page reloads (saved with the message in
  localStorage) but are NOT written to `conversations_log.jsonl` on the
  server — they remain a client-side audit asset.

### Added — Configurable language directive (carried forward from v2.0)

- Confirmed the `LANGUAGE_DIRECTIVE` env var is fully wired: when set,
  `app/routes/chat.py` prepends it to the system prompt before each
  Gemini call. Empty by default — the template forces no specific
  language. Example for a Spanish deployment:
  ```
  LANGUAGE_DIRECTIVE="## LANGUAGE\nAlways respond in Spanish (Latin American).
  Your internal thoughts must also be in Spanish, not English."
  ```

### Changed — Body limits

- New `/api/auth/refresh` endpoint added to body-size limits with a 1 KB
  cap (it only accepts a Bearer header, no body).

### Service Worker

- `CACHE_VERSION`: `cortex-v200` → `cortex-v210`. Existing clients
  see the auto-update banner shortly after the deploy and can refresh
  in one click.

### Tests

- Suite grew from **138 → 160** passing (+22):
  - `test_v141_session_and_truncation.py` (13 tests): JWT default is 24h,
    `/api/auth/refresh` requires bearer / rejects invalid tokens / returns
    a new token / preserves admin role / the new token works on admin
    endpoints. `max_output_tokens >= 16K`. `gemini_engine` emits
    `truncated` events. `chat.py` forwards them. Frontend has the
    "Continue" button + handler + periodic refresh.
  - `test_v150_persisted_thoughts.py` (9 tests): message persists
    `reasoning` field with 30K cap. `ThoughtsViewer` component exists,
    uses native `<details>` (no `useState`), starts closed, mounts in
    the assistant render with `!isStreaming` guard. CSS in place.

### Migration notes

- Tokens issued under the previous 8h policy are still valid until
  they expire — no breaking change. The automatic refresh starts
  running as soon as the new HTML loads.
- Monitoring that polled `/api/health` for `llm_reachable` etc. should
  move to `/api/admin/health` with an admin token (already documented
  in v2.0.0 migration notes).

---

## [2.0.0] — 2026-05-21

Massive sync from the reference deployment, carrying improvements from v1.0 → v1.4.1 across security, UX, and stability. This release imports all generic improvements into the blueprint, leaving out anything specific to the reference instance.

### Added — Security

- **Discovery surface closed:** `/docs`, `/redoc`, `/openapi.json` no longer respond by default. Enable with `DOCS_ENABLED=true` in `.env` (recommended for dev only). `/api/health` public endpoint minimized to `{status, version, timestamp}`. New `/api/admin/health` with admin auth for detailed checks.
- **Zip-bomb protection** in `document_extract.py`: DOCX/PPTX/XLSX (which are ZIPs) are validated before extraction. Max 5K entries, 200 MB uncompressed, 1000:1 ratio. Mitigates DoS via small malicious uploads.
- **Exact CDN version pinning** in `static/index.html`: `react@18.3.1`, `react-dom@18.3.1`, `@babel/standalone@7.29.4`, `marked@12.0.2`, `dompurify@3.2.4`. Previously some used `@latest` → app could break on upstream breaking changes.
- **Subresource Integrity (SRI) hashes** on all CDN `<script>` tags: `integrity="sha384-..."` + `crossorigin="anonymous"`. If unpkg serves modified JS, the browser rejects it. New helper: `scripts/sri_hashes.ps1` to regenerate hashes when bumping versions.
- **`defusedxml.defuse_stdlib()`** at startup (`app/main.py`): replaces stdlib XML parsers with versions that reject entity expansion / external entity / decompression bomb attacks. New dep: `defusedxml==0.7.1`.
- **Audit log for `user_login_failed`** on `POST /api/login`: in addition to `logger.warning`, writes to `audit_log.jsonl` for brute-force forensics that survives rate-limit bypass via IP rotation.
- **`.gitignore` with cryptographic key patterns**: `*.key`, `*.pem`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `*.crt`.

### Added — Visible reasoning

- **Collapsible "Thinking…" panel** in the frontend (`ReasoningPanel`) during generation. Shows the model's internal thoughts live (Gemini `include_thoughts=True`). The backend emits a new SSE event (`reasoning`) alongside `text/thinking/done/error`. Ephemeral: not persisted in the log or response body.
- **Configurable language** (`LANGUAGE_DIRECTIVE` env var): the template does **not** force a language by default (the model chooses). To target a specific language, set in `.env`:
  ```
  LANGUAGE_DIRECTIVE="## LANGUAGE\nAlways respond in Spanish. Your internal thoughts must also be in Spanish."
  ```
  Prepended to the system prompt → the "Thinking…" panel appears in the configured language instead of the model's default.

### Added — Chat UX

- **Refactored `streamFromMessages`** (frontend): reusable streaming core shared between `sendMessage`, `regenerateLast`, and `editMessage`.
- **Regenerate response without flicker**: the user's message stays visible; only the assistant's response is re-streamed.
- **Inline user message editing** (Gemini-style): ✏️ button on hover over user bubbles, inline textarea, Esc to cancel, Ctrl/Cmd+Enter to save. Truncates subsequent messages and re-streams.
- **Larger chat composer**: `min-height: 56px` base (was 24px), expands to 96px on focus with a smooth 160ms transition, `max-height: 240px` before scroll activates.
- **Larger prompt editor in admin**: `rows={36}` + `minHeight: 70vh`. Previously `rows={26}` with no `minHeight`.
- **Agent selector handles 401 with auto-logout**: if the JWT token expired and `/api/agents` returned 401, the silent catch left `agents=[]` with no visible feedback. Now 401 triggers automatic `onLogout()`; other errors show a visible toast.

### Added — Models and badges

- **Gemini models updated**: `gemini-3.5-flash` as the default balanced tier (previously `gemini-3-flash-preview`). `AVAILABLE_GEMINI_MODELS` updated with 3.1 Pro / 3.5 Flash / 3.1 Flash-Lite + stable fallbacks. Verifiable against the real API with `scripts/list_gemini_models.py`.
- **Pro/Flash/Lite badge visible on all agents** (not just the one using the auto-router). `inferTier(modelName)` detects the tier from the model name, giving users feedback on the effort level of each query.
- **Per-agent router registry** (`_AGENT_ROUTERS` in `app/llm/router.py`): allows each deployment to add its own routing heuristic for domain-specific agents. The template ships with an empty, commented example.

### Added — Infrastructure

- **`UpdateBanner`** (frontend): silent polling every 60s to `/api/version`. When a new version is detected, shows a floating blue banner with a "Reload" button that unregisters service workers, clears all caches, and reloads — no DevTools required.
- **`/reset-cache.html`**: manual emergency page for when the SW is so outdated it doesn't include the `UpdateBanner`. Navigating there runs automatic cleanup and redirects to `/?fresh=<ts>`. Excluded from SW fetch interception so it always reaches the browser.
- **SW `CACHE_VERSION` bumped** + `/reset-cache.html` excluded from the fetch handler.

### Added — Custom icon upload from admin

- **`POST /api/admin/agents/{id}/icon`** (multipart): PNG/JPG upload with strict magic-byte validation (file extension is not trusted). Max 2 MB. Saved as `static/agents/<id>.<ext>` with the real detected extension. Clears previous logos for the same agent. Updates `icon_url` with a cache-buster `?v=<ts>`.
- **`DELETE /api/admin/agents/{id}/icon`**: idempotent, cleans files and `icon_url`.
- **`IconSection`** in the agent editor (admin panel): 72×72 preview + "Upload / Replace / Remove icon" buttons. Replaces the old flow of manually dropping PNGs into `static/agents/`.
- Both endpoints are recorded in the audit log (`agent_icon_uploaded` / `agent_icon_deleted`).

### Changed — Configuration

- **`ctx_max`: 30K → 120K** characters in `ChatRequest.system_context`. Previously it was smaller than `MAX_CHARS=60K` in the extractor → attaching a large Excel/PDF caused Pydantic to return 422. Now consistent with margin for multiple attachments.
- **Word filename ASCII-only** (`office_generators._safe_filename`): accented characters are replaced with `_` before saving. Fixes a 400 error when downloading Word files with accented titles.

### Tests

138 tests passing (previously 80). New suites:

- `test_security_backlog.py`: zip-bomb, defusedxml, SRI hashes, CDN pinning.
- `test_v131_ux_bugs.py`: Word filename ASCII, larger composer.
- `test_v132_auto_update.py`: UpdateBanner, reset-cache.html, SW exclusion.
- `test_v133_bugs.py`: consistent ctx_max, larger prompt editor.
- `test_v134_agents_error_handling.py`: agent selector with 401.
- `test_v140_icon_upload.py`: 14 icon upload tests (magic bytes, size limits, happy path, replace, delete, audit).
- `test_health.py` updated to minimal public endpoint + detailed `/api/admin/health` with auth.

### New scripts

- `scripts/sri_hashes.ps1`: recalculates SHA-384 SRI hashes for CDN scripts when bumping versions.
- `scripts/list_gemini_models.py`: lists Gemini models available in the project account.
- `scripts/test_reasoning.py`: smoke test verifying that a Gemini model emits thoughts with `include_thoughts=True`.

### What was NOT imported (reference-instance specific)

- "Report Generator" agent + `generate_service_report_pdf` tool
- `report_generators.py` module — client-specific
- Agent knowledge files from the reference instance
- Client branding assets in `static/branding/`
- Client-specific task routing heuristic
- Real product catalog
- Utility scripts for reverse-engineering client-specific document formats

### Migration notes

For deployments upgrading from template v1.0:

1. Back up `users.json`, `agents.json`, `conversations_log.jsonl`, `audit_log.jsonl`, `memory.json` before updating.
2. Run `pip install -r requirements.txt` to install `defusedxml`.
3. Review `.env`:
   - Optionally add `DOCS_ENABLED=true` if your workflow uses `/docs`. Otherwise leave it unset.
   - Optionally add `LANGUAGE_DIRECTIVE="..."` to force the model's response language.
4. External monitoring on `/api/health`: if it relied on detail fields (`llm_reachable`, `catalog_size`, etc.), move to `/api/admin/health` with an admin token. For uptime checks, `{status: "ok"}` from the public endpoint is sufficient.
5. Existing user browsers will have stale SW cache. On first load they will see the `UpdateBanner`; clicking it auto-updates. As a fallback, `/reset-cache.html` is always available.
