"""Especificaciones de tools del LLM en formato Anthropic.

Estas specs se le pasan al modelo. El handler real (qué hace cuando se
llama una tool) está en `app/routes/chat.py` y `app/routes/admin_chat.py`.
"""

from __future__ import annotations

from app.config import settings


CATALOG_TOOL = {
    "name": "catalog_search",
    "description": (
        "Busca ítems en el catálogo completo del cliente. "
        f"Devuelve hasta {settings.catalog_result_limit} resultados ranqueados por relevancia "
        "+ el total real de coincidencias. "
        "Para ver más allá de los primeros 200, pasar `offset: 200`, `offset: 400`, etc. "
        "Llamar múltiples veces con diferentes términos para búsquedas exhaustivas. "
        "Usar términos técnicos del dominio del cliente: marca, tipo de producto, "
        "tamaño, material, norma técnica o código de producto. "
        "Personalizar esta descripción al vocabulario real del catálogo del cliente."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Términos de búsqueda separados por espacios.",
            },
            "offset": {
                "type": "integer",
                "description": "Offset para paginación (default 0). Usar 200, 400... para páginas siguientes cuando hay >200 coincidencias.",
                "default": 0,
            },
        },
        "required": ["query"],
    },
}

FETCH_PAGE_TOOL = {
    "name": "fetch_product_data",
    "description": (
        "Descarga una página web (HTML) y extrae el título, el texto principal limpio y las "
        "tablas de especificaciones. Usar cuando NO encontraste un PDF descargable verificado "
        "del fabricante, pero hay páginas con datos técnicos disponibles. "
        "Devuelve {title, text, tables, char_count}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL de la página HTML a scrapear"}
        },
        "required": ["url"],
    },
}

GENERATE_DATASHEET_TOOL = {
    "name": "generate_datasheet_pdf",
    "description": (
        "Genera una ficha técnica PDF profesional con branding del cliente. "
        "Usar SOLO como ÚLTIMO RECURSO cuando NO existe un datasheet PDF oficial descargable. "
        "Devuelve {filename, url} — usá la URL en tu respuesta al usuario."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Título del producto"},
            "manufacturer": {"type": "string", "description": "Marca del fabricante"},
            "model": {"type": "string", "description": "Modelo o código"},
            "description": {"type": "string", "description": "Descripción técnica (1-3 párrafos)"},
            "specifications": {
                "type": "object",
                "description": (
                    "Specs técnicas como pares clave-valor. Pasar como JSON-encoded string. "
                    'Ejemplo: {"Presión nominal":"PN16","Material":"Hierro dúctil"}'
                ),
            },
            "applications": {"type": "string", "description": "Aplicaciones típicas"},
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "URLs oficiales consultadas",
            },
        },
        "required": ["title", "manufacturer", "model", "specifications"],
    },
}

GENERATE_WORD_TOOL = {
    "name": "generate_word_document",
    "description": (
        "Genera un documento Word (.docx) con branding del cliente. "
        "Usar cuando el usuario pide informes, propuestas, cotizaciones, memorias técnicas. "
        "Soporta títulos, párrafos, tablas y listas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Título principal"},
            "subtitle": {"type": "string", "description": "Subtítulo opcional"},
            "sections": {
                "type": "string",
                "description": (
                    "JSON-string con lista de secciones. Cada una uno de:\n"
                    '{"type":"heading","level":1|2|3,"text":"..."}\n'
                    '{"type":"paragraph","text":"..."}\n'
                    '{"type":"bullet","items":["a","b"]}\n'
                    '{"type":"numbered","items":["1","2"]}\n'
                    '{"type":"table","header":true,"rows":[["Col1","Col2"],["v1","v2"]]}'
                ),
            },
        },
        "required": ["title", "sections"],
    },
}

GENERATE_EXCEL_TOOL = {
    "name": "generate_excel_spreadsheet",
    "description": (
        "Genera planilla Excel (.xlsx) con una o más hojas. "
        "Usar para listados, comparativas, cotizaciones tabulares, inventarios."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Nombre del archivo"},
            "sheets": {
                "type": "string",
                "description": (
                    "JSON-string con lista de hojas. Cada una:\n"
                    '{"name":"NombreHoja","headers":["Col1","Col2"],"rows":[["v1","v2"]]}'
                ),
            },
        },
        "required": ["title", "sheets"],
    },
}

VERIFY_PDF_TOOL = {
    "name": "verify_pdf_url",
    "description": (
        "Verifica HTTP que una URL apunta a un PDF real "
        "(responde 200 + Content-Type pdf + magic bytes %PDF). "
        "Devuelve {valid, status, content_type, size_bytes, final_url, reason}. "
        "REGLAS DE USO:\n"
        "1) SIEMPRE llamala antes de citar al usuario una URL como datasheet/manual PDF.\n"
        "2) Usá SOLO URLs verbatim de búsquedas — NO inventes ni modifiques URLs.\n"
        "3) NO le agregues `.pdf` a URLs que no lo tienen — casi siempre da 404.\n"
        "4) Si retorna valid=false, ESA URL NO EXISTE — descartala, NO intentes variantes.\n"
        "5) Si retorna 'redirige a login' o 'no es PDF' — tampoco la cites."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL completa a verificar (http/https).",
            }
        },
        "required": ["url"],
    },
}

TAVILY_SEARCH_TOOL = {
    "name": "tavily_search",
    "description": (
        "Búsqueda web avanzada con Tavily AI, optimizada para agentes. "
        "Devuelve título, URL y contenido extraído. "
        "Ideal para datasheets, manuales, fichas de fabricantes, distribuidores."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Consulta. Puede incluir filetype:pdf, site:dominio.com.",
            },
            "search_depth": {
                "type": "string",
                "description": "'basic' (rápido) o 'advanced' (default, mejor para datasheets).",
                "default": "advanced",
            },
        },
        "required": ["query"],
    },
}

SAVE_BEHAVIOR_TOOL = {
    "name": "save_behavior",
    "description": (
        "Actualiza el prompt personalizado del agente. "
        "Proporcionar el texto COMPLETO actualizado. Vacío para resetear."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "new_custom_prompt": {
                "type": "string",
                "description": "Texto completo del nuevo prompt personalizado.",
            }
        },
        "required": ["new_custom_prompt"],
    },
}


# Bundle de tools para cada tipo de chat
CHAT_TOOLS = [
    CATALOG_TOOL,
    VERIFY_PDF_TOOL,
    FETCH_PAGE_TOOL,
    GENERATE_DATASHEET_TOOL,
    GENERATE_WORD_TOOL,
    GENERATE_EXCEL_TOOL,
    TAVILY_SEARCH_TOOL,
]

ADMIN_CHAT_TOOLS = [SAVE_BEHAVIOR_TOOL]


# Lookup por nombre — para filtrar dinámicamente según el agente activo
TOOLS_BY_NAME: dict[str, dict] = {t["name"]: t for t in CHAT_TOOLS}


def filter_tools(allowed_names: list[str]) -> list[dict]:
    """Devuelve solo las tools cuyo nombre está en `allowed_names`.

    Si `allowed_names` está vacío, devuelve lista vacía (agente sin tools).
    Si una tool listada no existe en TOOLS_BY_NAME, se ignora silenciosamente
    (forward-compat: permite que agentes referencien tools futuras).
    """
    return [TOOLS_BY_NAME[name] for name in allowed_names if name in TOOLS_BY_NAME]
