"""Tests for FastAPI routes.

Uses real InMemoryThreadRepository and YamlAgentConfigLoader (internal).
Uses AsyncMock for AgentRunner (external LLM boundary).
Uses real PersistentAgentRegistry with mocked store/repository for agent creation.
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

VALID_YAML = 'name: {name}\nmodel: test-model\nsystem_prompt: "Test prompt."\ntools: []\ndebug: false\n'

AGENTS = [
    "my-agent",
    "agent-1",
    "agent-2",
    "example-agent",
    "code-reviewer",
    "minimal-agent",
    "research-assistant",
    "mcp-agent",
]


@pytest.fixture
def yaml_store():
    """In-memory YAML store keyed by agent name."""
    return {name: VALID_YAML.format(name=name) for name in AGENTS}


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

    async def mock_stream_with_message(_thread_id, _message):
        for word in ["I", "am", "a", "mock", "agent."]:
            yield word + " "
        yield Message(
            role=MessageRole.AI,
            content="I am a mock agent.",
            status=MessageStatus.COMPLETED,
        )

    runner.stream_with_message = mock_stream_with_message
    return runner


@pytest.fixture
def real_threads():
    return InMemoryThreadRepository()


@pytest.fixture
def real_loader():
    return YamlAgentConfigLoader()


@pytest.fixture
def mock_config_store(yaml_store):
    """AsyncMock for AgentConfigStore that reads from the in-memory yaml_store."""
    store = AsyncMock()

    async def _get(name):
        if name not in yaml_store:
            from src.domain.exceptions import AgentNotFoundError

            raise AgentNotFoundError(f"Agent config not found: {name}")
        return yaml_store[name]

    store.get.side_effect = _get
    return store


@pytest.fixture
def mock_config_repository(yaml_store):
    """AsyncMock for AgentConfigRepository that lists agents from the in-memory store."""
    repo = AsyncMock()

    now = datetime.now(UTC)
    metadata_list = []
    for name in sorted(yaml_store.keys()):
        metadata_list.append(
            AgentConfigMetadata(
                name=name,
                model="test-model",
                minio_path=f"{name}.yaml",
                created_at=now,
                updated_at=now,
            )
        )
    repo.list_all.return_value = metadata_list
    return repo


@pytest.fixture
def real_registry(real_loader, mock_config_store, mock_config_repository, mock_mcp_tool_loader):
    return PersistentAgentRegistry(
        config_loader=real_loader,
        config_store=mock_config_store,
        config_repository=mock_config_repository,
        mcp_tool_loader=mock_mcp_tool_loader,
    )


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


# -- Stream Message Event ------------------------------------------------------


class TestStreamMessageEvent:
    """Tests for the new event: message SSE event in the stream endpoint."""

    async def test_stream_message_emits_message_event(self, client):
        """The SSE response should contain an event: message with Message JSON."""
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}/stream",
            json={"message": "Hello agent"},
        )
        assert resp.status_code == 200
        body = resp.text

        # Should contain event: message line
        assert "event:message" in body or "event: message" in body

        # The data line after event: message should contain valid Message JSON
        # SSE format: event: message\r\ndata: {...}\r\n\r\n
        lines = body.replace("\r\n", "\n").split("\n")
        found_message_event = False
        for i, line in enumerate(lines):
            if line.strip() == "event: message":
                found_message_event = True
                # Next non-empty line should be data: with JSON
                data_line = lines[i + 1] if i + 1 < len(lines) else ""
                assert data_line.startswith("data:"), f"Expected data line after event: message, got: {data_line!r}"
                json_str = data_line[len("data:") :].strip()
                import json

                msg_data = json.loads(json_str)
                assert msg_data["role"] == "ai"
                break
        assert found_message_event, f"event: message not found in SSE body:\n{body}"

    async def test_stream_message_final_message_format_matches_sync(self, client):
        """The Message JSON from event: message should have the same fields as the sync endpoint response."""
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Get sync response for comparison
        sync_resp = await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Compare me"})
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()

        # Create a fresh thread for the stream test (thread already has messages)
        create_resp2 = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id2 = create_resp2.json()["id"]

        stream_resp = await client.post(
            f"/api/v1/chat/{thread_id2}/stream",
            json={"message": "Hello agent"},
        )
        assert stream_resp.status_code == 200
        body = stream_resp.text

        # Extract Message JSON from the event: message line
        import json

        lines = body.replace("\r\n", "\n").split("\n")
        message_json = None
        for i, line in enumerate(lines):
            if line.strip() == "event: message":
                data_line = lines[i + 1] if i + 1 < len(lines) else ""
                json_str = data_line[len("data:") :].strip()
                message_json = json.loads(json_str)
                break

        assert message_json is not None, f"event: message not found in SSE body:\n{body}"

        # The stream Message should have the same structural fields as the sync response
        for field in ["role", "content", "timestamp", "status"]:
            assert field in message_json, f"Missing field {field!r} in stream Message: {message_json}"

        # Role must match
        assert message_json["role"] == sync_data["role"]

    async def test_stream_message_done_after_message_event(self, client):
        """event: done should appear after event: message, not before."""
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}/stream",
            json={"message": "Hello agent"},
        )
        assert resp.status_code == 200
        body = resp.text

        lines = body.replace("\r\n", "\n").split("\n")
        event_lines = [line.strip() for line in lines if line.strip().startswith("event:")]

        # Find indices of event: message and event: done
        message_idx = None
        done_idx = None
        for i, line in enumerate(event_lines):
            if line == "event: message":
                message_idx = i
            elif line == "event: done":
                done_idx = i

        assert message_idx is not None, f"event: message not found in event lines: {event_lines}"
        assert done_idx is not None, f"event: done not found in event lines: {event_lines}"
        assert done_idx > message_idx, (
            f"event: done (idx={done_idx}) should come after event: message (idx={message_idx})"
        )
