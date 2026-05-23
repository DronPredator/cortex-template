# Changelog — Cortex Template

Todos los cambios notables al blueprint base de Cortex se documentan acá.
El template sirve como punto de partida para nuevos despliegues de la
plataforma agéntica multi-agente.

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
SemVer: `MAJOR.MINOR.PATCH`.

---

## [2.0.0] — 2026-05-21

Sync masivo desde el despliegue de referencia que llevamos
de v1.0 → v1.4.1 con muchas mejoras de seguridad, UX y estabilidad. Esta
release importa **todas las mejoras genéricas** al blueprint, dejando
afuera lo específico de la instancia de referencia.

### Added — Seguridad

- **Discovery surface cerrada**: `/docs`, `/redoc`, `/openapi.json` ya no
  responden por default. Se activan con `DOCS_ENABLED=true` en `.env`
  (recomendado solo en dev). `/api/health` público minimizado a
  `{status, version, timestamp}`. Nuevo `/api/admin/health` con auth
  admin para el detalle profundo de checks.
- **Zip-bomb protection** en `document_extract.py`: DOCX/PPTX/XLSX (que
  son ZIPs) se validan antes de descomprimir. Max 5K entries, 200 MB
  descomprimido, ratio 1000:1. Mitiga DoS por upload chico malicioso.
- **Pin exacto de versiones CDN** en `static/index.html`: `react@18.3.1`,
  `react-dom@18.3.1`, `@babel/standalone@7.29.4`, `marked@12.0.2`,
  `dompurify@3.2.4`. Antes algunos usaban `@latest` → app rota si el
  upstream publicaba breaking change.
- **Subresource Integrity (SRI) hashes** en todos los `<script>` de CDN:
  `integrity="sha384-..."` + `crossorigin="anonymous"`. Si unpkg sirve
  JS modificado, el browser lo rechaza. Helper nuevo:
  `scripts/sri_hashes.ps1` para regenerar los hashes cuando se suba
  alguna versión.
- **`defusedxml.defuse_stdlib()`** al startup (`app/main.py`): reemplaza
  los parsers XML de la stdlib por versiones que rechazan entity
  expansion / external entity / decompression bomb. Hardening defensivo.
  Nueva dep: `defusedxml==0.7.1`.
- **Audit log de `user_login_failed`** en `POST /api/login`: además del
  `logger.warning` (que rota y se pierde), escribe al `audit_log.jsonl`
  para forense de brute-force que sobrevive al rate-limit por rotación
  de IPs.
- **`.gitignore` con claves criptográficas**: `*.key`, `*.pem`, `*.p12`,
  `*.pfx`, `id_rsa*`, `id_ed25519*`, `*.crt`. Defensivo.

### Added — Razonamiento visible

- **Panel "Pensando…" colapsible** en el frontend (`ReasoningPanel`)
  durante la generación. Muestra en vivo los thoughts internos del modelo
  (Gemini `include_thoughts=True`). El backend emite un evento SSE nuevo
  (`reasoning`) además de `text`/`thinking`/`done`/`error`. Es ephemeral:
  no se persiste en el log ni en el body de la respuesta.
- **Idioma configurable** (`LANGUAGE_DIRECTIVE` env var): el template
  NO fuerza idioma por default (el modelo elige). Cuando el deploy
  apunta a un público hispanohablante, setear en `.env`:
  ```
  LANGUAGE_DIRECTIVE="## IDIOMA\nRespondé SIEMPRE en español
  rioplatense. Tus thoughts internos también deben ser en español."
  ```
  Se prepend al system prompt → los thoughts del panel "Pensando…"
  aparecen en español, no en inglés (default de Gemini).

### Added — UX del chat

- **Refactor `streamFromMessages`** (frontend): core de streaming
  reusable entre `sendMessage`, `regenerateLast` y `editMessage`.
- **Regenerar respuesta sin parpadeo**: el mensaje del user queda
  visible, solo se rehace la respuesta del asistente.
- **Editar mensaje del usuario inline** (estilo Gemini): botón ✏️ en
  hover sobre el user-bubble, textarea inline, `Esc` cancela,
  `Ctrl/Cmd+Enter` guarda. Trunca mensajes posteriores y re-streamea.
- **Composer del chat más grande**: `min-height: 56px` base (antes 24px),
  expande a `96px` al focus con transición suave (160ms),
  `max-height: 240px` antes de habilitar scroll.
- **Editor de prompts del admin más grande**: `rows={36}` + `minHeight:
  70vh`. Antes `rows={26}` sin minHeight era muy chico para prompts
  largos.
- **Selector de agentes maneja 401 con auto-logout**: si el token JWT
  expiraba (8h max) y `/api/agents` devolvía 401, el catch silencioso
  dejaba `agents=[]` → selector desaparecía sin razón visible. Ahora
  401 → `onLogout()` automático y otros errores → toast visible.

### Added — Modelos y badges

- **Modelos Gemini al día**: `gemini-3.5-flash` como tier balanced
  default (antes `gemini-3-flash-preview`). `AVAILABLE_GEMINI_MODELS`
  actualizado con 3.1 Pro / 3.5 Flash / 3.1 Flash-Lite + fallbacks
  estables (3-flash-preview, 2.5 Flash, 2.0 Flash). Verificable vs la
  API real con el nuevo script `scripts/list_gemini_models.py`.
- **Badge Pro/Flash/Lite visible en TODOS los agentes** (no solo en el
  que usa auto-router). Función `inferTier(modelName)` que detecta el
  tier por nombre del modelo. Da feedback al usuario de cuánto se
  está "esforzando" el sistema en su consulta.
- **Registry de routers por agente** (`_AGENT_ROUTERS` en
  `app/llm/router.py`): permite a cada deploy agregar su propia
  heurística de routing para agentes específicos del dominio. El
  template lo deja vacío con un ejemplo comentado.

### Added — Infraestructura

- **`UpdateBanner` (frontend)**: polling silencioso cada 60s al
  `/api/version`. Cuando detecta versión nueva, muestra banner azul
  flotante con botón "Recargar" que desregistra service workers, limpia
  todos los caches y hace reload — sin que el usuario tenga que pasar
  por DevTools.
- **Página `/reset-cache.html`**: emergencia manual cuando el SW está
  servido tan viejo que ni siquiera tiene el `UpdateBanner`. Navegar a
  esa URL ejecuta limpieza automática y redirige a `/?fresh=<ts>`.
  Excluida del intercept del SW para que el script siempre llegue.
- **SW `CACHE_VERSION` bumpeado** + exclusión de `/reset-cache.html`
  del fetch handler.

### Added — Upload de iconos custom desde admin

- **`POST /api/admin/agents/{id}/icon`** (multipart): upload de PNG/JPG
  con validación estricta de **magic bytes** (no se confía en la
  extensión declarada — un EXE renombrado a `.png` se rechaza). Max
  2 MB. Guarda como `static/agents/<id>.<ext>` con la extensión real
  detectada. Borra logos previos del mismo agente. Actualiza `icon_url`
  con cache-buster `?v=<ts>` → rompe cache negativo de 404 anteriores.
- **`DELETE /api/admin/agents/{id}/icon`**: idempotente, limpia archivos
  y `icon_url`.
- **`IconSection`** en el editor del agente (admin panel): preview 72×72
  + botones "Subir / Reemplazar / Quitar icono". Reemplaza el flujo
  viejo de dropear PNGs manualmente en `static/agents/`.
- Ambos endpoints están en el audit log (`agent_icon_uploaded` /
  `agent_icon_deleted`).

### Changed — Configuración

- **`ctx_max`: 30K → 120K** caracteres en `ChatRequest.system_context`.
  Antes era el doble de chico que `MAX_CHARS=60K` del extractor → al
  adjuntar un Excel/PDF grande, Pydantic devolvía 422 "Validación de
  datos falló". Ahora consistente con margen para múltiples adjuntos.
- **Filename de Word ASCII-only** (`office_generators._safe_filename`):
  tildes y eñes se reemplazan con `_` antes de guardar. Antes el round-
  trip por URL con `safe_filename()` (que normaliza NFKD) fallaba con
  400 al descargar Words con título acentuado.

### Tests

- **138 tests passing** (template antes tenía 80). Suite nueva:
  - `test_security_backlog.py`: zip-bomb, defusedxml, SRI hashes, CDN pin.
  - `test_v131_ux_bugs.py`: Word filename ASCII, composer grande.
  - `test_v132_auto_update.py`: UpdateBanner, reset-cache.html, SW exclusion.
  - `test_v133_bugs.py`: ctx_max consistente, editor prompts grande.
  - `test_v134_agents_error_handling.py`: selector de agentes con 401.
  - `test_v140_icon_upload.py`: 14 tests del upload de iconos
    (magic bytes, size limits, happy path, replace, delete, audit).
- Test `test_health.py` actualizado al endpoint público mínimo +
  `/api/admin/health` detallado con auth.

### Scripts nuevos

- `scripts/sri_hashes.ps1`: recalcula los SHA-384 SRI de los CDN scripts
  cuando se suben versiones nuevas.
- `scripts/list_gemini_models.py`: lista modelos Gemini disponibles en
  la cuenta del proyecto (útil para verificar antes de bumpear el
  default model).
- `scripts/test_reasoning.py`: smoke test que verifica si un modelo
  Gemini emite thoughts con `include_thoughts=True`.

### Lo que NO se importó (específico de la instancia de referencia)

- Agente "Generador de Informes" + tool `generate_service_report_pdf`
  + módulo `report_generators.py` — específico del cliente.
- Knowledge files específicos de los agentes de la instancia de referencia.
- Logo y branding del cliente en `static/branding/`.
- Router específico de Steamy (`classify_task_tier_steamy`).
- Catálogo BIT real.
- Scripts `inspect_docx.py` y `extract_logo.py` (eran para reverse-
  engineering de un .docx específico).

### Migration notes

Para deploys que vengan de la versión v1.0 del template:

1. **Backup** de `users.json`, `agents.json`, `conversations_log.jsonl`,
   `audit_log.jsonl`, `memory.json` antes de actualizar.
2. **`pip install -r requirements.txt`** para instalar `defusedxml`.
3. **Revisar el `.env`**:
   - Agregar opcionalmente `DOCS_ENABLED=true` si tu workflow usa
     `/docs` para explorar el API. Si no, dejar sin esa variable.
   - Agregar opcionalmente `LANGUAGE_DIRECTIVE="..."` si querés forzar
     idioma de los thoughts.
4. **Monitoring externo** que chequee `/api/health`: si dependía del
   detalle (`llm_reachable`, `catalog_size`, etc.), mover a
   `/api/admin/health` con token admin. Para uptime check,
   `{status: "ok"}` del público sigue siendo suficiente.
5. **Browsers de usuarios existentes**: van a tener cache viejo del SW.
   La primera vez que carguen verán el `UpdateBanner` y al click se
   actualiza automáticamente. Como emergencia tienen `/reset-cache.html`.
