"""Tests de la búsqueda en catálogo + paginación + ranking."""

from __future__ import annotations


def test_catalog_size_is_positive():
    from search import catalog_size

    assert catalog_size() > 0, "El catálogo no cargó"


def test_search_returns_items_for_common_query():
    from search import search_stock

    data = search_stock("service", limit=10)
    assert "items" in data
    assert "total" in data
    assert "truncated" in data
    assert "offset" in data
    assert len(data["items"]) <= 10
    assert data["total"] >= len(data["items"])


def test_search_empty_query_returns_empty():
    from search import search_stock

    data = search_stock("", limit=10)
    assert data["items"] == []
    assert data["total"] == 0


def test_search_pagination_with_offset():
    from search import search_stock

    page1 = search_stock("service", limit=5, offset=0)
    page2 = search_stock("service", limit=5, offset=5)
    assert len(page1["items"]) <= 5
    # Si hay >5 resultados, page2 debe traer items distintos a page1
    if page1["total"] > 5:
        page1_codes = {it["codigo"] for it in page1["items"]}
        page2_codes = {it["codigo"] for it in page2["items"]}
        assert page1_codes.isdisjoint(page2_codes), "Paginación devolvió duplicados"


def test_search_truncated_flag_correct():
    from search import search_stock

    # Una búsqueda muy genérica seguro tiene más resultados que el limit
    data = search_stock("service", limit=3)
    if data["total"] > 3:
        assert data["truncated"] is True
    else:
        assert data["truncated"] is False


def test_search_with_specific_term():
    """Catálogo inicial del taller — código SRV-001 (service básico) debe estar."""
    from search import search_stock

    data = search_stock("SRV-001", limit=20)
    assert data["total"] > 0, "SRV-001 debería estar en el catálogo inicial"


def test_format_catalog_result_returns_string():
    from app.tools.catalog import format_catalog_result

    data = {"items": [{"codigo": "ABC123", "descripcion": "Válvula test"}], "total": 1, "truncated": False, "offset": 0}
    out = format_catalog_result("test", data)
    assert isinstance(out, str)
    assert "ABC123" in out
    assert "Válvula test" in out


def test_format_catalog_result_empty():
    from app.tools.catalog import format_catalog_result

    data = {"items": [], "total": 0, "truncated": False, "offset": 0}
    out = format_catalog_result("xyz", data)
    assert "No se encontraron" in out
