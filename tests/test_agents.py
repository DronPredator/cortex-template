"""Tests del sistema de agentes — registry, permisos, endpoint público."""

from __future__ import annotations


# ── Registry ─────────────────────────────────────────────────────────


def test_ensure_agents_file_creates_initial_agents(tmp_path, monkeypatch):
    from app.agents import registry as reg

    fake_path = tmp_path / "agents.json"
    monkeypatch.setattr(reg, "AGENTS_PATH", fake_path)

    reg.ensure_agents_file()
    assert fake_path.exists()

    agents = reg.load_agents()
    assert "consultor_tecnico" in agents
    assert agents["consultor_tecnico"].is_default is True


def test_get_agent_or_default_falls_back(tmp_path, monkeypatch):
    from app.agents import registry as reg

    fake_path = tmp_path / "agents.json"
    monkeypatch.setattr(reg, "AGENTS_PATH", fake_path)
    reg.ensure_agents_file()

    # ID inexistente → cae al default
    agent = reg.get_agent_or_default("no_existe_xxx")
    assert agent.id == "consultor_tecnico"

    # ID None → también cae al default
    agent2 = reg.get_agent_or_default(None)
    assert agent2.id == "consultor_tecnico"


def test_upsert_and_delete_agent(tmp_path, monkeypatch):
    from app.agents import registry as reg
    from app.agents.base import AgentDefinition

    fake_path = tmp_path / "agents.json"
    monkeypatch.setattr(reg, "AGENTS_PATH", fake_path)
    reg.ensure_agents_file()

    new_agent = AgentDefinition(
        id="test_nuevo",
        name="Test Nuevo",
        description="Para testing",
        allowed_tools=["catalog_search"],
    )
    reg.upsert_agent(new_agent)

    fetched = reg.get_agent("test_nuevo")
    assert fetched is not None
    assert fetched.name == "Test Nuevo"
    assert fetched.created_at != ""

    deleted = reg.delete_agent("test_nuevo")
    assert deleted is True
    assert reg.get_agent("test_nuevo") is None


def test_cannot_delete_default_agent(tmp_path, monkeypatch):
    import pytest
    from app.agents import registry as reg

    fake_path = tmp_path / "agents.json"
    monkeypatch.setattr(reg, "AGENTS_PATH", fake_path)
    reg.ensure_agents_file()

    with pytest.raises(ValueError):
        reg.delete_agent("consultor_tecnico")


# ── Permisos ─────────────────────────────────────────────────────────


def test_admin_can_access_any_agent():
    from app.agents.base import AgentDefinition
    from app.agents.permissions import can_user_access

    private = AgentDefinition(id="x", name="X", visibility="private")
    public = AgentDefinition(id="y", name="Y", visibility="public")
    users = AgentDefinition(id="z", name="Z", visibility="users", allowed_users=["juan"])

    assert can_user_access("admin_user", is_admin=True, agent=private) is True
    assert can_user_access("admin_user", is_admin=True, agent=public) is True
    assert can_user_access("admin_user", is_admin=True, agent=users) is True


def test_regular_user_cannot_access_private():
    from app.agents.base import AgentDefinition
    from app.agents.permissions import can_user_access

    private = AgentDefinition(id="x", name="X", visibility="private")
    assert can_user_access("alguien", is_admin=False, agent=private) is False


def test_regular_user_can_access_public():
    from app.agents.base import AgentDefinition
    from app.agents.permissions import can_user_access

    public = AgentDefinition(id="x", name="X", visibility="public")
    assert can_user_access("alguien", is_admin=False, agent=public) is True


def test_user_access_with_users_visibility():
    from app.agents.base import AgentDefinition
    from app.agents.permissions import can_user_access

    agent = AgentDefinition(
        id="x", name="X", visibility="users", allowed_users=["juan", "maria"]
    )
    assert can_user_access("juan", is_admin=False, agent=agent) is True
    assert can_user_access("maria", is_admin=False, agent=agent) is True
    assert can_user_access("pedro", is_admin=False, agent=agent) is False


# ── Endpoint /api/agents ─────────────────────────────────────────────


def test_agents_endpoint_requires_auth(client):
    r = client.get("/api/agents")
    assert r.status_code in (401, 403)


def test_agents_endpoint_returns_visible_only_for_user(client, user_token):
    r = client.get("/api/agents", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "agents" in data
    # Usuario regular ve los públicos. Los 3 base son públicos.
    ids = {a["id"] for a in data["agents"]}
    assert "consultor_tecnico" in ids


def test_agents_endpoint_admin_sees_all(client, admin_token):
    r = client.get("/api/agents", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()["agents"]}
    assert "consultor_tecnico" in ids


# ── Knowledge base ───────────────────────────────────────────────────


def test_knowledge_load_empty_when_no_dir(tmp_path, monkeypatch):
    from app.agents import knowledge as kb

    monkeypatch.setattr(kb, "AGENT_KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(kb, "_cache", {})

    assert kb.load_knowledge("no_existe") == ""


def test_knowledge_load_concatenates_md_files(tmp_path, monkeypatch):
    from app.agents import knowledge as kb

    monkeypatch.setattr(kb, "AGENT_KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(kb, "_cache", {})

    agent_dir = tmp_path / "test_agent"
    agent_dir.mkdir()
    (agent_dir / "doc1.md").write_text("Contenido 1", encoding="utf-8")
    (agent_dir / "doc2.md").write_text("Contenido 2", encoding="utf-8")

    result = kb.load_knowledge("test_agent")
    assert "Contenido 1" in result
    assert "Contenido 2" in result
    assert "doc1.md" in result
    assert "doc2.md" in result


def test_knowledge_excludes_underscore_files(tmp_path, monkeypatch):
    from app.agents import knowledge as kb

    monkeypatch.setattr(kb, "AGENT_KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(kb, "_cache", {})

    agent_dir = tmp_path / "test_agent"
    agent_dir.mkdir()
    (agent_dir / "doc_real.md").write_text("contenido_real", encoding="utf-8")
    (agent_dir / "_README.md").write_text("readme_interno", encoding="utf-8")

    result = kb.load_knowledge("test_agent")
    assert "contenido_real" in result
    assert "readme_interno" not in result


def test_knowledge_cache_invalidates_on_change(tmp_path, monkeypatch):
    import time
    from app.agents import knowledge as kb

    monkeypatch.setattr(kb, "AGENT_KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(kb, "_cache", {})

    agent_dir = tmp_path / "test_agent"
    agent_dir.mkdir()
    f = agent_dir / "doc.md"
    f.write_text("v1", encoding="utf-8")

    r1 = kb.load_knowledge("test_agent")
    assert "v1" in r1

    time.sleep(0.05)  # asegurar mtime distinto
    f.write_text("v2_actualizado", encoding="utf-8")

    r2 = kb.load_knowledge("test_agent")
    assert "v2_actualizado" in r2
    assert "v1" not in r2


# ── Admin endpoints ──────────────────────────────────────────────────


def test_admin_list_agents(client, admin_token):
    r = client.get(
        "/api/admin/agents", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert "agents" in data
    ids = {a["id"] for a in data["agents"]}
    assert ids == {"consultor_tecnico", "generador_reportes"}


def test_admin_get_agent_prompt(client, admin_token):
    r = client.get(
        "/api/admin/agents/consultor_tecnico/prompt",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"] == "consultor_tecnico"
    assert "Consultor Técnico" in data["content"] or "RR Mecánica" in data["content"]


def test_admin_save_and_load_agent_prompt(client, admin_token, tmp_path, monkeypatch):
    from app.agents import registry as reg

    # Aislar el directorio donde se guardan los .md
    monkeypatch.setattr(reg, "AGENT_DEFINITIONS_DIR", tmp_path)
    monkeypatch.setattr(reg, "_prompt_cache", {})

    new_content = "Sos un agente de prueba.\n\n## Reglas\nTesting only."
    r = client.put(
        "/api/admin/agents/consultor_tecnico/prompt",
        json={"content": new_content},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r2 = client.get(
        "/api/admin/agents/consultor_tecnico/prompt",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r2.json()["content"] == new_content


def test_admin_prompt_endpoint_404_for_missing_agent(client, admin_token):
    r = client.get(
        "/api/admin/agents/no_existe_xyz/prompt",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404


def test_admin_endpoints_require_admin(client, user_token):
    r = client.get(
        "/api/admin/agents", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert r.status_code == 403


# ── Filter tools ─────────────────────────────────────────────────────


def test_filter_tools_returns_allowed_only():
    from app.llm.tool_specs import filter_tools

    tools = filter_tools(["catalog_search", "tavily_search"])
    names = {t["name"] for t in tools}
    assert names == {"catalog_search", "tavily_search"}


def test_filter_tools_ignores_unknown():
    from app.llm.tool_specs import filter_tools

    tools = filter_tools(["catalog_search", "no_existe_xxx"])
    names = {t["name"] for t in tools}
    assert names == {"catalog_search"}


def test_filter_tools_empty_returns_empty():
    from app.llm.tool_specs import filter_tools

    assert filter_tools([]) == []
