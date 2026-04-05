"""Tests for FastAPI routes.

Uses real InMemoryThreadRepository and YamlAgentConfigLoader (internal).
Uses AsyncMock for AgentRunner (external LLM boundary).
Uses a real PersistentAgentRegistry with patched factory for agent creation.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.exceptions import AgentError
from src.infrastructure.persistent_registry.adapter import PersistentAgentRegistry
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader
from src.main import app
from tests.fixtures.in_memory_thread_repository import InMemoryThreadRepository


@pytest.fixture
def agents_dir(tmp_path):
    """Create a temporary agents directory with real YAML files."""
    d = tmp_path / "agents"
    d.mkdir()
    (d / "my-agent.yaml").write_text("name: my-agent")
    (d / "agent-1.yaml").write_text("name: agent-1")
    (d / "agent-2.yaml").write_text("name: agent-2")
    (d / "example-agent.yaml").write_text('name: example-agent\nmodel: "test-model"\nsystem_prompt: "Test prompt."')
    (d / "code-reviewer.yaml").write_text('name: code-reviewer\nmodel: "test-model"')
    (d / "minimal.yaml").write_text("name: minimal-agent")
    (d / "research-assistant.yaml").write_text('name: research-assistant\nmodel: "test-model"')
    (d / "mcp-agent.yaml").write_text('name: mcp-agent\nmodel: "test-model"\nsystem_prompt: "MCP agent."')
    return d


@pytest.fixture
def mock_runner():
    """AsyncMock for the agent runner (external LLM boundary)."""
    runner = AsyncMock()
    runner.invoke.return_value = Message(
        role=MessageRole.AI, content="I am a mock agent.", status=MessageStatus.COMPLETED
    )
    runner.approve_hitl.return_value = Message(
        role=MessageRole.AI, content="Action approved.", status=MessageStatus.COMPLETED
    )
    runner.reject_hitl.return_value = Message(
        role=MessageRole.AI, content="Action rejected: Too risky", status=MessageStatus.COMPLETED
    )
    runner.edit_hitl.return_value = Message(
        role=MessageRole.AI, content="Action edited and approved.", status=MessageStatus.COMPLETED
    )

    async def mock_stream(_thread_id, _message):
        for word in ["I", "am", "a", "mock", "agent."]:
            yield word + " "

    runner.stream = mock_stream
    return runner


@pytest.fixture
def real_threads():
    return InMemoryThreadRepository()


@pytest.fixture
def real_loader():
    return YamlAgentConfigLoader()


@pytest.fixture
def real_registry(mock_config_store, mock_config_repository, real_loader, mock_mcp_tool_loader):
    return PersistentAgentRegistry(
        config_loader=real_loader,
        config_store=mock_config_store,
        config_repository=mock_config_repository,
        mcp_tool_loader=mock_mcp_tool_loader,
    )


@pytest.fixture
def mock_config_store(agents_dir):
    """AsyncMock for AgentConfigStore that reads from the tmp agents_dir."""
    store = AsyncMock()

    async def _get(name):
        from pathlib import Path

        path = Path(agents_dir) / f"{name}.yaml"
        if not path.exists():
            from src.domain.exceptions import AgentNotFoundError

            raise AgentNotFoundError(f"Agent config not found: {name}")
        return path.read_text()

    store.get.side_effect = _get
    return store


@pytest.fixture
def mock_config_repository(agents_dir):
    """AsyncMock for AgentConfigRepository that lists agents from the tmp agents_dir."""
    repo = AsyncMock()
    from pathlib import Path

    now = datetime.now(UTC)
    metadata_list = []
    for f in sorted(Path(agents_dir).glob("*.yaml")):
        metadata_list.append(
            AgentConfigMetadata(
                name=f.stem,
                model="test-model",
                minio_path=f"{f.stem}.yaml",
                is_builtin=False,
                created_at=now,
                updated_at=now,
            )
        )
    repo.list_all.return_value = metadata_list
    return repo


@pytest.fixture(autouse=True)
def _wire_dependencies(
    real_threads, real_registry, real_loader, mock_runner, mock_config_store, mock_config_repository
):
    """Wire real internal components + mocked runner into the app dependencies."""
    with (
        patch(
            "src.infrastructure.persistent_registry.adapter.create_agent_from_config",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.persistent_registry.adapter.DeepAgentRunner",
            return_value=mock_runner,
        ),
        patch("src.dependencies.thread_repository", real_threads),
        patch("src.dependencies.agent_registry", real_registry),
        patch("src.dependencies.agent_config_loader", real_loader),
        patch("src.dependencies._minio_store", mock_config_store),
        patch("src.dependencies._pg_repository", mock_config_repository),
    ):
        yield


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# -- Thread CRUD ---------------------------------------------------------------


class TestThreadRoutes:
    async def test_create_thread(self, client):
        resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_name"] == "my-agent"
        assert "id" in data

    async def test_create_thread_unknown_agent_returns_404(self, client):
        resp = await client.post("/api/v1/threads", json={"agent_name": "nonexistent"})
        assert resp.status_code == 404

    async def test_create_thread_empty_name_returns_422(self, client):
        resp = await client.post("/api/v1/threads", json={"agent_name": ""})
        assert resp.status_code == 422

    async def test_list_threads_empty(self, client):
        resp = await client.get("/api/v1/threads")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_threads(self, client):
        await client.post("/api/v1/threads", json={"agent_name": "agent-1"})
        await client.post("/api/v1/threads", json={"agent_name": "agent-2"})
        resp = await client.get("/api/v1/threads")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_thread(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/threads/{thread_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == thread_id

    async def test_get_thread_not_found(self, client):
        resp = await client.get("/api/v1/threads/nonexistent")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_delete_thread(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/threads/{thread_id}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/v1/threads/{thread_id}")
        assert resp.status_code == 404

    async def test_delete_thread_not_found(self, client):
        resp = await client.delete("/api/v1/threads/nonexistent")
        assert resp.status_code == 404

    async def test_list_messages_empty(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/threads/{thread_id}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_messages_after_chat(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello"})
        resp = await client.get(f"/api/v1/threads/{thread_id}/messages")
        assert resp.status_code == 200
        assert len(resp.json()) == 2  # human + ai


# -- Chat -----------------------------------------------------------------------


class TestChatRoutes:
    async def test_send_message(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello agent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "ai"
        assert "content" in data
        assert "timestamp" in data

    async def test_send_message_thread_not_found(self, client):
        resp = await client.post("/api/v1/chat/nonexistent", json={"message": "Hello"})
        assert resp.status_code == 404

    async def test_send_message_empty_body_returns_422(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={})
        assert resp.status_code == 422

    async def test_stream_message(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}/stream",
            json={"message": "Hello agent"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data:" in body

    async def test_stream_message_thread_not_found(self, client):
        resp = await client.post(
            "/api/v1/chat/nonexistent/stream",
            json={"message": "Hello"},
        )
        assert resp.status_code == 404


# -- HITL -----------------------------------------------------------------------


class TestHITLRoutes:
    async def test_approve(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "approve"},
        )
        assert resp.status_code == 200
        assert "approved" in resp.json()["content"].lower()

    async def test_reject(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "reject", "reason": "Too risky"},
        )
        assert resp.status_code == 200
        assert "rejected" in resp.json()["content"].lower()

    async def test_edit(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={
                "tool_call_id": "tc-1",
                "action": "edit",
                "edits": {"param": "new_value"},
            },
        )
        assert resp.status_code == 200
        assert "edited" in resp.json()["content"].lower()

    async def test_edit_without_edits_returns_422(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "edit"},
        )
        assert resp.status_code == 422

    async def test_unknown_action_returns_422(self, client):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "unknown"},
        )
        assert resp.status_code == 422


# -- Agents --------------------------------------------------------------------


class TestAgentRoutes:
    async def test_list_agents(self, client):
        resp = await client.get("/api/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = [a["name"] for a in data]
        assert "example-agent" in names

    async def test_get_agent(self, client):
        resp = await client.get("/api/v1/agents/example-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "example-agent"

    async def test_get_agent_not_found(self, client):
        resp = await client.get("/api/v1/agents/nonexistent")
        assert resp.status_code == 404


# -- Exception handlers ---------------------------------------------------------


class TestExceptionHandlers:
    async def test_thread_not_found_returns_404(self, client):
        resp = await client.get("/api/v1/threads/does-not-exist")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_config_not_found_returns_404(self, client):
        resp = await client.get("/api/v1/agents/missing-agent")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_agent_not_found_returns_404(self, client):
        resp = await client.post("/api/v1/threads", json={"agent_name": "unknown-agent"})
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_agent_error_returns_502(self, client, mock_runner):
        """Verify that AgentError from the runner maps to a 502 response."""
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        mock_runner.invoke.side_effect = AgentError("Backend failed")
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello"})
        assert resp.status_code == 502
        assert "Backend failed" in resp.json()["detail"]

        # Reset for other tests
        mock_runner.invoke.side_effect = None
        mock_runner.invoke.return_value = Message(
            role=MessageRole.AI, content="I am a mock agent.", status=MessageStatus.COMPLETED
        )
