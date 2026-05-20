# Cortex Template

> **Plantilla base para construir un Cortex para un cliente nuevo.**
> Producto: Cortex by AgentX.
> Origen: extraído de la primera instancia en producción (Fidemar Cortex).

Este repo es el **molde**. Para crear el Cortex de un cliente nuevo,
seguí este README paso a paso. Estimado: **1-2 días de personalización**
para tener algo testeable, **5-7 días** para deploy en producción.

---

## ¿Qué es Cortex?

Una plataforma agéntica B2B donde una empresa pone a trabajar varios
**asistentes IA especializados** (que llamamos "agentes"), cada uno con
su prompt, su dominio de conocimiento y su set de herramientas.

**No es un wrapper de ChatGPT** — es una aplicación full-stack con
multi-agente, permisos granulares, knowledge base, tool calling, panel
admin y capa de seguridad endurecida.

**Una instancia = un cliente**. Cada empresa tiene su Cortex aislado
con su propio dominio, sus propios agentes, sus propios datos.

---

## Workflow: crear una instancia para `<Cliente>` desde cero

### Paso 1 — Crear el repo nuevo desde este template

**Opción A — Vía GitHub (recomendado):**
1. Ir a este repo en GitHub
2. Click en botón **"Use this template" → "Create a new repository"**
3. Nombre nuevo: `<cliente>-cortex` (ej: `acme-cortex`)
4. Privado
5. Clonarlo localmente:
   ```powershell
   git clone https://github.com/AgentX/<cliente>-cortex
   cd <cliente>-cortex
   ```

**Opción B — Clonando manualmente:**
```powershell
git clone https://github.com/AgentX/cortex-template <cliente>-cortex
cd <cliente>-cortex
# Re-init git para empezar historia limpia:
rm -rf .git
git init
git add -A
git commit -m "initial: <cliente> cortex desde template v1"
```

### Paso 2 — Setup del entorno Python

```powershell
python --version       # >= 3.11
pip install -r requirements.txt
python -m pytest tests/ -v    # debe pasar todo en verde
```

Si los tests no pasan en este punto, **NO sigas** — algo está roto en
el template.

### Paso 3 — Configurar identidad del cliente

```powershell
copy .env.example .env
```

Editar `.env`:

```dotenv
# Identidad del cliente
COMPANY_NAME=Acme
COMPANY_FULL_NAME=Acme S.A.
COMPANY_INDUSTRY=manufactura
CORTEX_INSTANCE_ID=acme_cortex

# Tu primer usuario
CHAT_USER=admin_cliente
CHAT_PASSWORD=PoneAlgoFuerte123!

# CORS — dominios reales donde se va a servir
CORS_ORIGINS=http://localhost:8000,https://cortex.acme.com
```

Setear secrets sin tocarlos en plain text:

```powershell
python set_secret.py JWT_SECRET        # cualquier string aleatorio >= 32 chars
python set_secret.py GOOGLE_API_KEY    # generar en aistudio.google.com/apikey
python set_secret.py TAVILY_API_KEY    # opcional, $5/mes en tavily.com
python set_secret.py ADMIN_PASSWORD    # fuerte
```

### Paso 4 — Cargar el dataset del cliente

Reemplazar `stock.csv` (que viene con 20 productos demo) por el catálogo
real del cliente. Formato esperado:

```
;;;;;;
[título descriptivo];;;;;;
[nombre empresa];;;;;;
[metadata extra];;;;;;
;;;;;;
Código;Descripción;;;;;
ABC-001;PRODUCTO 1;;;;;
ABC-002;PRODUCTO 2;;;;;
```

- Separador: `;` (punto y coma)
- Encoding: UTF-8 con BOM (o sin BOM)
- Header en línea 7, datos a partir de línea 8

Si el formato del CSV del cliente es distinto, editar `search.py` para
adaptar el parsing. Mantener la interfaz: `search_stock(query, limit, offset) -> dict`.

### Paso 5 — Definir los agentes iniciales

Editar `app/agents/registry.py` → `_INITIAL_AGENTS` y reemplazar el
"Demo Assistant" por los agentes reales del cliente.

Ejemplo:

```python
_INITIAL_AGENTS: list[AgentDefinition] = [
    AgentDefinition(
        id="ana",
        name="ANA · Asistente Comercial",
        description="Asesoramiento de productos y stock de Acme S.A.",
        icon="💼",
        allowed_tools=["catalog_search", "tavily_search", "generate_word_document"],
        default_tier="auto",
        visibility="public",
        is_default=True,
    ),
    AgentDefinition(
        id="quality_check",
        name="Verificador de Calidad",
        description="Compliance ISO 9001 + normas internas Acme",
        icon="✅",
        allowed_tools=["tavily_search", "verify_pdf_url"],
        default_tier="pro",
        visibility="private",
    ),
]
```

### Paso 6 — Escribir el prompt de cada agente

Crear `app/agents/definitions/<agent_id>.md` con el system prompt
completo del agente. Estructura típica:

```markdown
# Identidad
Sos [NOMBRE], el [ROL] de [EMPRESA].

## Capacidades
- ...

## Reglas de comportamiento
- ...

## Tools disponibles
- ...

## Formato de respuesta
- ...
```

### Paso 7 — Knowledge base por agente (opcional)

Para agentes que necesitan docs de referencia (normas, catálogos
internos, manuales propios del cliente):

```
app/agents/knowledge/<agent_id>/
├── _README.md           # ignorado (prefijo `_`)
├── manual_interno.md    # cargado al system prompt
└── normas_iso.md        # cargado al system prompt
```

Solo archivos `.md`. Para PDFs, convertir el texto a markdown
(idealmente con tablas bien formateadas).

### Paso 8 — Borrar referencias al Demo Assistant

```powershell
# Borrar el demo del template (después de definir los reales)
rm app/agents/definitions/demo_assistant.md
```

Y en `app/config.py`:
```python
DEFAULT_AGENT_ID = "ana"  # el id del flagship del cliente
```

### Paso 9 — Branding del frontend

Editar `static/index.html` y buscar/reemplazar `Demo Company` por el
nombre del cliente. Lugares clave:
- `<title>` (línea ~6)
- `.brand-logo` y `.brand-cortex` (topbar)
- `.login-logo` y "Acceso interno" (login screen)
- Mensaje del welcome screen si lo personalizás

### Paso 10 — Tests con el setup real

```powershell
python -m pytest tests/ -v
```

Si algún test del agente o catálogo falla, ajustar los tests para que
se adapten a la realidad del cliente. **Nunca skippear tests.**

### Paso 11 — Smoke test local

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

- `http://localhost:8000` → login con el `CHAT_USER` y `CHAT_PASSWORD`
  del .env
- Probar cada agente con 3-5 consultas reales
- `/api/health` → todos los checks en verde
- Crear/borrar un usuario de prueba desde el admin panel
- Editar el prompt de un agente desde el admin → verificar que se aplica
  al instante

### Paso 12 — Commit + push

```powershell
git add -A
git commit -m "config: setup inicial para <Cliente>"
git push origin main
```

### Paso 13 — Deployment

Opciones por orden de preferencia (ver `CORTEX_BLUEPRINT.md` para
detalles):

1. **PC dedicada en oficina del cliente** (Windows Service vía NSSM):
   ```powershell
   install_service.bat   # como administrador
   ```
2. **VPS dedicado** (Hetzner/DigitalOcean/Antel Cloud) — Linux + systemd
   + Caddy/Cloudflare para HTTPS
3. **Cloud del cliente** (AWS/Azure/GCP) — solo si el cliente lo exige

### Paso 14 — Checklist final antes de habilitar al cliente

- [ ] Todos los tests pasan
- [ ] `/api/health` devuelve `status: ok` con todos los checks
- [ ] `JWT_SECRET` único, >=32 chars, generado random
- [ ] `ADMIN_PASSWORD` fuerte, compartido por canal seguro
- [ ] `CORS_ORIGINS` apuntando solo al dominio real
- [ ] HTTPS funcionando (cert válido)
- [ ] Backups corriendo (verificar `backups/YYYY-MM-DD/`)
- [ ] Audit log activo (un login admin → entrada en `audit_log.jsonl`)
- [ ] Cada agente probado con 3-5 consultas reales del cliente
- [ ] Documentación entregada al admin
- [ ] Plan de soporte primeras 2 semanas acordado
- [ ] Servicio auto-start al boot (NSSM o systemd)

Si algún punto falta, **NO se entrega**.

---

## Mantenimiento de instancias

### Cuando actualizo el template, ¿cómo propago el cambio al cliente?

Si el cliente fue creado con "Use this template" (sin upstream),
agregar el template como remote y mergear:

```powershell
cd <cliente>-cortex
git remote add upstream https://github.com/AgentX/cortex-template
git fetch upstream
git merge upstream/main --allow-unrelated-histories
# Resolver conflictos si los hay (típicamente en static/index.html con branding)
```

### Cuando un cliente quiere agregar un agente nuevo

Mejor opción: que lo haga desde el panel admin (tab "🤖 Asistentes" →
"+ Nuevo agente" → editar prompt → guardar).

Si requiere knowledge files, **vos** subís los `.md` por SFTP/VS Code
Remote y le confirmás que ya está disponible (cache mtime → no requiere
restart).

---

## Estructura del template

Ver `CLAUDE.md` para la estructura detallada de archivos y `CORTEX_BLUEPRINT.md`
(repo de AgentX) para el blueprint arquitectónico completo.

---

## Soporte

- Blueprint completo: `CORTEX_BLUEPRINT.md`
- Issues/bugs: en este repo (privado)
- Casos de referencia: Fidemar Cortex (primera instancia productiva)

---

*Cortex Template v1.0 — by AgentX*
