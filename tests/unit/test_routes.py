"""Tests for FastAPI routes.

Uses real internal components (PostgresThreadRepository via the shared
``thread_repo`` fixture, YamlAgentConfigLoader). The agent runner is mocked at
the ``AgentRunner`` port boundary via ``mock_agent_runner``.

Dependencies are wired through ``app.dependency_overrides`` instead of patching
module-level globals, so the FastAPI container remains in control of its own
providers.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.application.use_cases.create_agent_config import CreateAgentConfigUseCase
from src.application.use_cases.create_thread import CreateThreadUseCase
from src.application.use_cases.delete_agent_config import DeleteAgentConfigUseCase
from src.application.use_cases.delete_thread import DeleteThreadUseCase
from src.application.use_cases.get_agent_config import GetAgentConfigUseCase
from src.application.use_cases.get_thread import GetThreadUseCase
from src.application.use_cases.get_thread_history import GetThreadHistoryUseCase
from src.application.use_cases.list_agent_configs import ListAgentConfigsUseCase
from src.application.use_cases.list_threads import ListThreadsUseCase
from src.application.use_cases.send_message import SendMessageUseCase
from src.application.use_cases.stream_message import StreamMessageUseCase
from src.application.use_cases.update_agent_config import UpdateAgentConfigUseCase
from src.dependencies import (
    get_create_agent_config_use_case,
    get_create_thread_use_case,
    get_delete_agent_config_use_case,
    get_delete_thread_use_case,
    get_get_agent_config_use_case,
    get_get_thread_history_use_case,
    get_get_thread_use_case,
    get_list_agent_configs_use_case,
    get_list_threads_use_case,
    get_send_message_use_case,
    get_stream_message_use_case,
    get_trace_event_repository,
    get_update_agent_config_use_case,
)
from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.agent import AgentError
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.agent_runner import AgentRunner
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader
from src.main import app, security

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


class StubAgentRegistry(AgentRegistry):
    """In-memory AgentRegistry backed by the mocked agent runner.

    Lists agent names from the YAML store and returns the shared mock runner
    for every agent. This avoids the real PersistentAgentRegistry which would
    require create_agent_from_config (LLM) and a config store.
    """

    def __init__(self, agent_names: list[str], runner: AgentRunner) -> None:
        self._names = agent_names
        self._runner = runner

    async def get_runner(self, agent_name: str) -> AgentRunner:
        if agent_name not in self._names:
            from src.domain.errors.agent import AgentNotFoundError

            raise AgentNotFoundError(f"Agent not found: {agent_name}")
        return self._runner

    async def list_agents(self) -> list[str]:
        return list(self._names)

    async def invalidate(self, agent_name: str) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest.fixture
def mock_runner():
    """AsyncMock for the agent runner (external LLM boundary)."""
    runner = AsyncMock(spec=AgentRunner)
    final_msg = Message(role=MessageRole.AI, content="I am a mock agent.", status=MessageStatus.COMPLETED)

    async def _invoke(_thread_id: str, _message: str, _turn_id: str):
        # Return (Message, list[TraceEvent]) with the real thread_id/turn_id
        # so persistence FK constraints are satisfied.
        return (
            final_msg,
            [
                _trace_event(_thread_id, _turn_id, TraceEventType.HUMAN_MESSAGE, _message, seq=0),
                _trace_event(_thread_id, _turn_id, TraceEventType.AI_MESSAGE, final_msg.model_dump_json(), seq=1),
            ],
        )

    runner.invoke.side_effect = _invoke
    runner.approve_hitl.return_value = Message(
        role=MessageRole.AI, content="Action approved.", status=MessageStatus.COMPLETED
    )
    runner.reject_hitl.return_value = Message(
        role=MessageRole.AI, content="Action rejected: Too risky", status=MessageStatus.COMPLETED
    )
    runner.edit_hitl.return_value = Message(
        role=MessageRole.AI, content="Action edited and approved.", status=MessageStatus.COMPLETED
    )

    async def mock_stream(_thread_id, _message, _turn_id):
        # Yield a full TraceEvent sequence: HUMAN_MESSAGE, intermediates, AI_MESSAGE.
        yield _trace_event(_thread_id, _turn_id, TraceEventType.HUMAN_MESSAGE, _message, seq=0)
        yield _trace_event(_thread_id, _turn_id, TraceEventType.THINKING, "hmm", seq=1)
        for word in ["I", "am", "a", "mock", "agent."]:
            yield _trace_event(_thread_id, _turn_id, TraceEventType.CONTENT, word + " ", seq=2)
        yield _trace_event(
            _thread_id,
            _turn_id,
            TraceEventType.AI_MESSAGE,
            Message(
                role=MessageRole.AI,
                content="I am a mock agent.",
                status=MessageStatus.COMPLETED,
                structured_response={"key": "value"},
            ).model_dump_json(),
            seq=3,
        )

    runner.stream = mock_stream
    return runner


def _trace_event(thread_id: str, turn_id: str, type_: TraceEventType, content: str, seq: int) -> TraceEvent:
    """Helper to build a TraceEvent for tests."""
    return TraceEvent(
        id=str(uuid4()),
        thread_id=thread_id,
        turn_id=turn_id,
        type=type_,
        content=content,
        timestamp=datetime.now(UTC),
        sequence=seq,
    )


@pytest.fixture
def stub_registry(mock_runner):
    return StubAgentRegistry(AGENTS, mock_runner)


@pytest.fixture
def mock_config_store():
    """AsyncMock for AgentConfigStore that returns VALID_YAML by name."""
    store = AsyncMock()

    async def _get(name):
        if name not in AGENTS:
            from src.domain.errors.agent import AgentNotFoundError

            raise AgentNotFoundError(f"Agent config not found: {name}")
        return VALID_YAML.format(name=name)

    store.get.side_effect = _get
    return store


@pytest.fixture
def mock_config_repository():
    """AsyncMock for AgentConfigRepository that lists agents from AGENTS."""
    repo = AsyncMock()
    now = datetime.now(UTC)
    repo.list_all.return_value = [
        AgentConfigMetadata(
            name=name,
            model="test-model",
            minio_path=f"{name}.yaml",
            created_at=now,
            updated_at=now,
        )
        for name in sorted(AGENTS)
    ]

    # ``get`` mirrors the RLS-filtered Postgres repository: returns metadata
    # for known agents, raises AgentNotFoundError for unknown ones. This is
    # what GetAgentConfigUseCase now relies on for the ownership check before
    # touching the shared MinIO bucket.
    async def _get(name):
        from src.domain.errors.agent import AgentNotFoundError

        if name not in AGENTS:
            raise AgentNotFoundError(f"Agent config not found: {name}")
        return AgentConfigMetadata(
            name=name,
            model="test-model",
            minio_path=f"{name}.yaml",
            created_at=now,
            updated_at=now,
        )

    repo.get.side_effect = _get
    return repo


@pytest.fixture(autouse=True)
def _override_dependencies(stub_registry, thread_repo, trace_repo, mock_config_store, mock_config_repository):
    """Wire real internal components + mocked runner via app.dependency_overrides."""
    yaml_loader = YamlAgentConfigLoader()

    def _send_message():
        return SendMessageUseCase(stub_registry, thread_repo, trace_repo)

    def _stream_message():
        return StreamMessageUseCase(stub_registry, thread_repo, trace_repo)

    def _get_thread_history():
        return GetThreadHistoryUseCase(thread_repo, trace_repo)

    def _create_thread():
        return CreateThreadUseCase(thread_repo, stub_registry)

    def _get_thread():
        return GetThreadUseCase(thread_repo)

    def _list_threads():
        return ListThreadsUseCase(thread_repo)

    def _delete_thread():
        return DeleteThreadUseCase(thread_repo)

    def _get_agent_config():
        return GetAgentConfigUseCase(yaml_loader, mock_config_store, mock_config_repository)

    def _list_agent_configs():
        return ListAgentConfigsUseCase(mock_config_repository)

    def _create_agent_config():
        return CreateAgentConfigUseCase(yaml_loader, mock_config_store, mock_config_repository)

    def _update_agent_config():
        return UpdateAgentConfigUseCase(yaml_loader, mock_config_store, mock_config_repository, stub_registry)

    def _delete_agent_config():
        return DeleteAgentConfigUseCase(mock_config_store, mock_config_repository, stub_registry)

    # Bypass dual-auth security for route tests — security is covered by
    # tests/unit/test_security.py and tests/unit/test_verify_credentials_wiring.py
    # with dedicated apps. The protected router now depends on
    # ``verify_credentials`` (dual JWT/API-key); we override it to a no-op
    # returning a fixed AuthContext so the route handlers run without auth.
    from src.domain.entities.auth.auth_context import AuthContext

    app.dependency_overrides[security.verify_credentials] = lambda: AuthContext(
        user_id="test-user", method="api_key", raw_credential=""
    )

    app.dependency_overrides[get_send_message_use_case] = _send_message
    app.dependency_overrides[get_stream_message_use_case] = _stream_message
    app.dependency_overrides[get_get_thread_history_use_case] = _get_thread_history
    app.dependency_overrides[get_trace_event_repository] = lambda: trace_repo
    app.dependency_overrides[get_create_thread_use_case] = _create_thread
    app.dependency_overrides[get_get_thread_use_case] = _get_thread
    app.dependency_overrides[get_list_threads_use_case] = _list_threads
    app.dependency_overrides[get_delete_thread_use_case] = _delete_thread
    app.dependency_overrides[get_get_agent_config_use_case] = _get_agent_config
    app.dependency_overrides[get_list_agent_configs_use_case] = _list_agent_configs
    app.dependency_overrides[get_create_agent_config_use_case] = _create_agent_config
    app.dependency_overrides[get_update_agent_config_use_case] = _update_agent_config
    app.dependency_overrides[get_delete_agent_config_use_case] = _delete_agent_config

    yield

    app.dependency_overrides.clear()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# -- Thread CRUD ---------------------------------------------------------------


class TestThreadRoutes:
    """Tests for thread CRUD routes."""

    async def test_create_thread_returns_201_with_agent_name(self, client):
        # Arrange
        # Act
        resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})

        # Assert
        assert resp.status_code == 201
        assert resp.json()["agent_name"] == "my-agent"

    async def test_create_thread_unknown_agent_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.post("/api/v1/threads", json={"agent_name": "nonexistent"})

        # Assert
        assert resp.status_code == 404

    async def test_create_thread_empty_name_returns_422(self, client):
        # Arrange
        # Act
        resp = await client.post("/api/v1/threads", json={"agent_name": ""})

        # Assert
        assert resp.status_code == 422

    async def test_list_threads_empty_returns_200_with_empty_list(self, client):
        # Arrange
        # Act
        resp = await client.get("/api/v1/threads")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_threads_returns_created_threads(self, client):
        # Arrange
        await client.post("/api/v1/threads", json={"agent_name": "agent-1"})
        await client.post("/api/v1/threads", json={"agent_name": "agent-2"})

        # Act
        resp = await client.get("/api/v1/threads")

        # Assert
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_thread_returns_thread_by_id(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.get(f"/api/v1/threads/{thread_id}")

        # Assert
        assert resp.status_code == 200
        assert resp.json()["id"] == thread_id

    async def test_get_thread_not_found_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.get("/api/v1/threads/nonexistent")

        # Assert
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_delete_thread_returns_204_then_404(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        delete_resp = await client.delete(f"/api/v1/threads/{thread_id}")
        get_resp = await client.get(f"/api/v1/threads/{thread_id}")

        # Assert
        assert delete_resp.status_code == 204
        assert get_resp.status_code == 404

    async def test_delete_thread_not_found_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.delete("/api/v1/threads/nonexistent")

        # Assert
        assert resp.status_code == 404

    async def test_list_messages_empty_returns_200_with_empty_list(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.get(f"/api/v1/threads/{thread_id}/messages")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_messages_after_chat_returns_human_and_ai(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        chat_resp = await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello"})
        msgs_resp = await client.get(f"/api/v1/threads/{thread_id}/messages")

        # Assert
        assert chat_resp.status_code == 200
        assert chat_resp.json()["role"] == "ai"
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()
        assert len(messages) == 2
        assert messages[0]["role"] == "human"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "ai"
        assert messages[1]["content"] == "I am a mock agent."


# -- Chat -----------------------------------------------------------------------


class TestChatRoutes:
    """Tests for chat send/stream routes."""

    async def test_send_message_returns_ai_message(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello agent"})

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "ai"
        assert body["content"] == "I am a mock agent."
        assert body["status"] == "completed"

    async def test_send_message_thread_not_found_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.post("/api/v1/chat/nonexistent", json={"message": "Hello"})

        # Assert
        assert resp.status_code == 404

    async def test_send_message_empty_body_returns_422(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={})

        # Assert
        assert resp.status_code == 422

    async def test_stream_message_returns_event_stream(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(
            f"/api/v1/chat/{thread_id}/stream",
            json={"message": "Hello agent"},
        )

        # Assert
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "data:" in resp.text

    async def test_stream_message_thread_not_found_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.post(
            "/api/v1/chat/nonexistent/stream",
            json={"message": "Hello"},
        )

        # Assert
        assert resp.status_code == 404


# -- HITL -----------------------------------------------------------------------


class TestHITLRoutes:
    """Tests for human-in-the-loop decision routes."""

    async def test_approve_returns_200_with_approved_content(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "approve"},
        )

        # Assert
        assert resp.status_code == 200
        assert resp.json()["content"] == "Action approved."

    async def test_reject_returns_200_with_rejected_content(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "reject", "reason": "Too risky"},
        )

        # Assert
        assert resp.status_code == 200
        assert resp.json()["content"] == "Action rejected: Too risky"

    async def test_edit_returns_200_with_edited_content(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "edit", "edits": {"param": "new_value"}},
        )

        # Assert
        assert resp.status_code == 200
        assert resp.json()["content"] == "Action edited and approved."

    async def test_edit_without_edits_returns_422(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "edit"},
        )

        # Assert
        assert resp.status_code == 422

    async def test_unknown_action_returns_422(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "unknown"},
        )

        # Assert
        assert resp.status_code == 422


# -- Agents --------------------------------------------------------------------


class TestAgentRoutes:
    """Tests for agent config routes (list/get)."""

    async def test_list_agents_returns_known_names(self, client):
        # Arrange
        # Act
        resp = await client.get("/api/v1/agents")

        # Assert
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()]
        assert "example-agent" in names

    async def test_get_agent_returns_config_by_name(self, client):
        # Arrange
        # Act
        resp = await client.get("/api/v1/agents/example-agent")

        # Assert
        assert resp.status_code == 200
        assert resp.json()["name"] == "example-agent"

    async def test_get_agent_not_found_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.get("/api/v1/agents/nonexistent")

        # Assert
        assert resp.status_code == 404


# -- Exception handlers ---------------------------------------------------------


class TestExceptionHandlers:
    """Tests for domain error -> HTTP response mapping."""

    async def test_thread_not_found_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.get("/api/v1/threads/does-not-exist")

        # Assert
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_config_not_found_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.get("/api/v1/agents/missing-agent")

        # Assert
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_agent_not_found_returns_404(self, client):
        # Arrange
        # Act
        resp = await client.post("/api/v1/threads", json={"agent_name": "unknown-agent"})

        # Assert
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_agent_error_returns_502(self, client, mock_runner):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        mock_runner.invoke.side_effect = AgentError("Backend failed")

        # Act
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello"})

        # Assert
        assert resp.status_code == 502
        assert "Backend failed" in resp.json()["detail"]

        # Reset for other tests — restore the side_effect-based invoke.
        mock_runner.invoke.side_effect = None


# -- Stream Message Event ------------------------------------------------------


class TestStreamMessageEvent:
    """Tests for SSE stream: TraceEvents then [DONE] terminator."""

    async def test_stream_yields_trace_events_then_done(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(
            f"/api/v1/chat/{thread_id}/stream",
            json={"message": "Hello agent"},
        )

        # Assert
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        data_lines = _extract_data_lines(resp.text)
        # Last line is [DONE]
        assert data_lines[-1] == "[DONE]"
        # Parse the trace events: HUMAN_MESSAGE, THINKING, CONTENT..., AI_MESSAGE
        event_types: list[str] = []
        for line in data_lines[:-1]:
            event = json.loads(line)
            event_types.append(event["type"])
        assert event_types[0] == TraceEventType.HUMAN_MESSAGE.value
        assert event_types[-1] == TraceEventType.AI_MESSAGE.value
        assert TraceEventType.THINKING.value in event_types
        assert TraceEventType.CONTENT.value in event_types

    async def test_stream_emits_ai_message_event(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.post(
            f"/api/v1/chat/{thread_id}/stream",
            json={"message": "Hello agent"},
        )

        # Assert
        assert resp.status_code == 200
        data_lines = _extract_data_lines(resp.text)
        ai_event = _find_event(data_lines, TraceEventType.AI_MESSAGE.value)
        assert ai_event is not None
        # AI_MESSAGE content is a JSON-serialized Message payload
        payload = json.loads(ai_event["content"])
        assert payload["content"] == "I am a mock agent."
        assert payload["status"] == "completed"


class TestThreadHistoryRoute:
    """Tests for GET /api/v1/threads/{id}/history."""

    async def test_history_returns_thread_history(self, client):
        # Arrange — send a message first so trace events exist
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello"})

        # Act
        resp = await client.get(f"/api/v1/threads/{thread_id}/history")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["thread"]["id"] == thread_id
        assert len(body["turns"]) == 1
        turn = body["turns"][0]
        assert turn["human_message"] is not None
        assert turn["human_message"]["role"] == "human"
        assert turn["ai_message"] is not None
        assert turn["ai_message"]["role"] == "ai"
        # Intermediate events (THINKING/CONTENT) present, no HUMAN/AI duplicates
        types = {e["type"] for e in turn["events"]}
        assert "human_message" not in types
        assert "ai_message" not in types

    async def test_history_empty_thread_returns_no_turns(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.get(f"/api/v1/threads/{thread_id}/history")

        # Assert
        assert resp.status_code == 200
        assert resp.json()["turns"] == []


class TestTraceRoute:
    """Tests for GET /api/v1/threads/{id}/trace (flat list of trace events)."""

    async def test_trace_endpoint_returns_events(self, client):
        # Arrange — send a message first so trace events exist
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello"})

        # Act
        resp = await client.get(f"/api/v1/threads/{thread_id}/trace")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert "events" in body
        assert len(body["events"]) >= 2
        types = [e["type"] for e in body["events"]]
        assert "human_message" in types
        assert "ai_message" in types

    async def test_trace_endpoint_empty_thread(self, client):
        # Arrange
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Act
        resp = await client.get(f"/api/v1/threads/{thread_id}/trace")

        # Assert
        assert resp.status_code == 200
        assert resp.json()["events"] == []


def _extract_data_lines(body: str) -> list[str]:
    """Extract the payload after 'data:' from each SSE line."""
    return [
        line.strip()[len("data:") :].strip()
        for line in body.replace("\r\n", "\n").split("\n")
        if line.strip().startswith("data:")
    ]


def _find_event(data_lines: list[str], event_type: str) -> dict | None:
    """Find the first SSE event of the given type (parsed from JSON)."""
    for line in reversed(data_lines):
        if line == "[DONE]":
            continue
        event = json.loads(line)
        if event.get("type") == event_type:
            return event
    return None
