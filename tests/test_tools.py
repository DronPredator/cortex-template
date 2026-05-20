"""Tests de las tools del agente (verify_pdf_url, etc.)."""

from __future__ import annotations


def test_verify_pdf_url_empty_string():
    from app.tools.pdf_verify import verify_pdf_url

    r = verify_pdf_url("")
    assert r["valid"] is False
    assert "inválida" in r["reason"].lower()


def test_verify_pdf_url_non_http_rejected():
    from app.tools.pdf_verify import verify_pdf_url

    r = verify_pdf_url("ftp://example.com/file.pdf")
    assert r["valid"] is False
    assert "http" in r["reason"].lower()


def test_verify_pdf_url_invalid_type():
    from app.tools.pdf_verify import verify_pdf_url

    r = verify_pdf_url(None)  # type: ignore[arg-type]
    assert r["valid"] is False


def test_tavily_format_handles_empty_response():
    from app.tools.tavily import format_tavily_results

    out = format_tavily_results("test query", {})
    assert "test query" in out
    assert "No se encontraron" in out


def test_tavily_format_with_results():
    from app.tools.tavily import format_tavily_results

    response = {
        "results": [
            {"title": "Datasheet BERMAD", "url": "https://example.com/d.pdf", "content": "Specs..."},
            {"title": "Manual técnico", "url": "https://example.com/m.pdf", "content": "Info..."},
        ],
        "answer": "Resumen",
    }
    out = format_tavily_results("BERMAD", response)
    assert "Datasheet BERMAD" in out
    assert "https://example.com/d.pdf" in out
    assert "2 resultado(s)" in out


def test_classify_task_tier_returns_valid():
    from app.llm.router import classify_task_tier

    # Doc adjunto → pro
    assert classify_task_tier("hola", has_documents=True) == "pro"
    # Palabra clave de análisis → pro
    assert classify_task_tier("hacé un informe técnico de BERMAD", has_documents=False) == "pro"
    # Mensaje corto → lite
    assert classify_task_tier("hola", has_documents=False) == "lite"
    # Default → flash
    long_msg = "necesito alguna valvula para un sistema de agua potable que tenga DN50"
    assert classify_task_tier(long_msg, has_documents=False) == "flash"


def test_tier_to_model_returns_valid_model():
    from app.config import MODEL_TIER_FLASH, MODEL_TIER_LITE, MODEL_TIER_PRO
    from app.llm.router import tier_to_model

    assert tier_to_model("pro") == MODEL_TIER_PRO
    assert tier_to_model("flash") == MODEL_TIER_FLASH
    assert tier_to_model("lite") == MODEL_TIER_LITE
    assert tier_to_model("unknown") == MODEL_TIER_FLASH  # fallback


def test_prompt_loader_caches():
    from app.prompts.loader import _load

    p1 = _load("system")
    p2 = _load("system")
    assert p1 == p2
    # El prompt base del template menciona {n_items} como placeholder
    assert "{n_items}" in p1 or "catálogo" in p1.lower()


def test_system_prompt_includes_n_items():
    from app.prompts.loader import system_prompt

    p = system_prompt(n_items=12500)
    assert "12500" in p or "12.500" in p or "12,500" in p


def test_system_prompt_with_custom_appends_section():
    from app.prompts.loader import system_prompt

    base = system_prompt(n_items=100, custom="")
    with_custom = system_prompt(n_items=100, custom="Siempre responder en inglés")
    assert len(with_custom) > len(base)
    assert "Siempre responder en inglés" in with_custom
    assert "PRIORIDAD MÁXIMA" in with_custom


def test_atomic_write_creates_file(tmp_path):
    from app.storage.atomic import atomic_write

    target = tmp_path / "test.txt"
    atomic_write(target, "hola mundo")
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hola mundo"


def test_atomic_write_overwrites_existing(tmp_path):
    from app.storage.atomic import atomic_write

    target = tmp_path / "test.txt"
    target.write_text("contenido viejo")
    atomic_write(target, "contenido nuevo")
    assert target.read_text(encoding="utf-8") == "contenido nuevo"
