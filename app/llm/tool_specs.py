"""LLM tool specifications (Anthropic-compatible format).

These specs are passed to the model. The actual handlers (what runs when
a tool is called) live in `app/routes/chat.py` and `app/routes/admin_chat.py`.
"""

from __future__ import annotations

from app.config import settings


CATALOG_TOOL = {
    "name": "catalog_search",
    "description": (
        "Search the product catalog. "
        f"Returns up to {settings.catalog_result_limit} results ranked by "
        "relevance plus the real total of matches. "
        "To page beyond the first 200, pass `offset: 200`, `offset: 400`, etc. "
        "Call multiple times with different terms for exhaustive searches. "
        "Use technical terms: brand, component type, size, material, "
        "standard, or product code."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search terms. Example: 'BRAND component type'.",
            },
            "offset": {
                "type": "integer",
                "description": "Pagination offset (default 0). Use 200, 400... for next pages when there are >200 matches.",
                "default": 0,
            },
        },
        "required": ["query"],
    },
}

FETCH_PAGE_TOOL = {
    "name": "fetch_product_data",
    "description": (
        "Download an HTML page and extract title, main clean text, and "
        "specification tables. Use this when you couldn't find a verified "
        "downloadable PDF datasheet from the manufacturer but there are "
        "web pages with technical data. "
        "Returns {title, text, tables, char_count}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL of the HTML page to scrape"}
        },
        "required": ["url"],
    },
}

GENERATE_DATASHEET_TOOL = {
    "name": "generate_datasheet_pdf",
    "description": (
        "Generate a professional product datasheet PDF. "
        "Use ONLY as a LAST RESORT when no official downloadable datasheet "
        "PDF exists. Returns {filename, url} — show the URL to the user."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Product title"},
            "manufacturer": {"type": "string", "description": "Manufacturer brand"},
            "model": {"type": "string", "description": "Model or code"},
            "description": {"type": "string", "description": "Technical description (1-3 paragraphs)"},
            "specifications": {
                "type": "object",
                "description": (
                    "Technical specs as key-value pairs. Pass as a JSON-encoded string. "
                    'Example: {"Nominal pressure":"PN16","Material":"Ductile iron"}'
                ),
            },
            "applications": {"type": "string", "description": "Typical applications"},
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Official URLs consulted",
            },
        },
        "required": ["title", "manufacturer", "model", "specifications"],
    },
}

GENERATE_WORD_TOOL = {
    "name": "generate_word_document",
    "description": (
        "Generate a Word (.docx) document with deployment branding. "
        "Use when the user requests reports, proposals, quotes, or technical "
        "memos. Supports titles, paragraphs, tables, and lists."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Main title"},
            "subtitle": {"type": "string", "description": "Optional subtitle"},
            "sections": {
                "type": "string",
                "description": (
                    "JSON-string with a list of sections. Each one of:\n"
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
        "Generate an Excel (.xlsx) spreadsheet with one or more sheets. "
        "Use for lists, comparison tables, tabular quotes, or inventories."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "File name"},
            "sheets": {
                "type": "string",
                "description": (
                    "JSON-string with a list of sheets. Each one:\n"
                    '{"name":"SheetName","headers":["Col1","Col2"],"rows":[["v1","v2"]]}'
                ),
            },
        },
        "required": ["title", "sheets"],
    },
}

VERIFY_PDF_TOOL = {
    "name": "verify_pdf_url",
    "description": (
        "Verify via HTTP that a URL points to a real PDF "
        "(responds 200 + Content-Type pdf + magic bytes %PDF). "
        "Returns {valid, status, content_type, size_bytes, final_url, reason}. "
        "USAGE RULES:\n"
        "1) ALWAYS call this before citing a URL to the user as a datasheet/manual PDF.\n"
        "2) Use ONLY verbatim URLs from search results — DO NOT invent or modify URLs.\n"
        "3) DO NOT append `.pdf` to URLs that don't already have it — almost always 404.\n"
        "4) If returns valid=false, THAT URL DOES NOT EXIST — discard it, don't try variants.\n"
        "5) If it returns 'redirects to login' or 'not a PDF' — don't cite it either."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to verify (http/https).",
            }
        },
        "required": ["url"],
    },
}

TAVILY_SEARCH_TOOL = {
    "name": "tavily_search",
    "description": (
        "Advanced web search via Tavily AI, optimized for agents. "
        "Returns title, URL, and extracted content. "
        "Ideal for datasheets, manuals, manufacturer pages, distributors."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query. Can include filetype:pdf, site:domain.com.",
            },
            "search_depth": {
                "type": "string",
                "description": "'basic' (fast) or 'advanced' (default, better for datasheets).",
                "default": "advanced",
            },
        },
        "required": ["query"],
    },
}

SAVE_AGENT_PROMPT_TOOL = {
    "name": "save_agent_prompt",
    "description": (
        "Replace a specific agent's full SYSTEM PROMPT. "
        "Provide the COMPLETE updated prompt text (markdown). "
        "The previous prompt is REPLACED (not merged). "
        "Before calling this tool, confirm with the admin: 'I'm about to save "
        "the complete prompt for agent X, you'll lose what was there — proceed?'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "ID of the agent to edit (e.g.: 'demo_assistant').",
            },
            "new_prompt": {
                "type": "string",
                "description": "COMPLETE markdown text of the new agent prompt.",
            },
        },
        "required": ["agent_id", "new_prompt"],
    },
}

# DEPRECATED — spec kept for backward compat with admin sessions that
# haven't updated to the new flow. NOT exported in ADMIN_CHAT_TOOLS.
SAVE_BEHAVIOR_TOOL = {
    "name": "save_behavior",
    "description": (
        "[DEPRECATED] Previously edited a 'global behavior' that no longer exists. "
        "Use save_agent_prompt instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "new_custom_prompt": {"type": "string"},
        },
        "required": ["new_custom_prompt"],
    },
}


# Tool bundle for each chat type
CHAT_TOOLS = [
    CATALOG_TOOL,
    VERIFY_PDF_TOOL,
    FETCH_PAGE_TOOL,
    GENERATE_DATASHEET_TOOL,
    GENERATE_WORD_TOOL,
    GENERATE_EXCEL_TOOL,
    TAVILY_SEARCH_TOOL,
]

ADMIN_CHAT_TOOLS = [SAVE_AGENT_PROMPT_TOOL]


# Lookup by name — used to dynamically filter tools based on the active agent
TOOLS_BY_NAME: dict[str, dict] = {t["name"]: t for t in CHAT_TOOLS}


def filter_tools(allowed_names: list[str]) -> list[dict]:
    """Return only the tools whose name is in `allowed_names`.

    If `allowed_names` is empty, returns an empty list (agent with no tools).
    If a listed tool doesn't exist in TOOLS_BY_NAME, it's silently ignored
    (forward-compat: allows agents to reference future tools).
    """
    return [TOOLS_BY_NAME[name] for name in allowed_names if name in TOOLS_BY_NAME]
