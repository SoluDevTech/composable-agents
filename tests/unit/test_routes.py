import pytest
from httpx import ASGITransport, AsyncClient

from src.dependencies import override_dependencies
from src.domain.entities.agent_config import AgentConfig
from src.domain.exceptions import AgentError
from src.infrastructure.memory_thread.adapter import InMemoryThreadRepository
from src.main import app
from tests.doubles.fake_agent_config_loader import FakeAgentConfigLoader
from tests.doubles.fake_agent_registry import FakeAgentRegistry


@pytest.fixture()
def fake_registry() -> FakeAgentRegistry:
    registry = FakeAgentRegistry()
    registry.register("my-agent")
    registry.register("agent-1")
    registry.register("agent-2")
    return registry


@pytest.fixture()
def fake_threads() -> InMemoryThreadRepository:
    return InMemoryThreadRepository()


@pytest.fixture()
def fake_loader() -> FakeAgentConfigLoader:
    loader = FakeAgentConfigLoader()
    loader.add_config(
        "agents/example-agent.yaml",
        AgentConfig(name="example-agent", model="test-model", system_prompt="Test prompt."),
    )
    loader.add_config(
        "agents/code-reviewer.yaml",
        AgentConfig(name="code-reviewer", model="test-model"),
    )
    loader.add_config(
        "agents/minimal.yaml",
        AgentConfig(name="minimal-agent"),
    )
    loader.add_config(
        "agents/research-assistant.yaml",
        AgentConfig(name="research-assistant", model="test-model"),
    )
    loader.add_config(
        "agents/mcp-agent.yaml",
        AgentConfig(name="mcp-agent", model="test-model", system_prompt="MCP agent."),
    )
    return loader


@pytest.fixture(autouse=True)
def _wire_dependencies(
    fake_registry: FakeAgentRegistry,
    fake_threads: InMemoryThreadRepository,
    fake_loader: FakeAgentConfigLoader,
) -> None:
    override_dependencies(
        thread_repository=fake_threads,
        agent_registry=fake_registry,
        agent_config_loader=fake_loader,
    )


@pytest.fixture()
def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Thread CRUD ──────────────────────────────────────────────────────────────


class TestThreadRoutes:
    @pytest.mark.asyncio
    async def test_create_thread(self, client: AsyncClient):
        resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_name"] == "my-agent"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_thread_unknown_agent_returns_404(self, client: AsyncClient):
        resp = await client.post("/api/v1/threads", json={"agent_name": "nonexistent"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_thread_empty_name_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/threads", json={"agent_name": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_threads_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/threads")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_threads(self, client: AsyncClient):
        await client.post("/api/v1/threads", json={"agent_name": "agent-1"})
        await client.post("/api/v1/threads", json={"agent_name": "agent-2"})
        resp = await client.get("/api/v1/threads")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_get_thread(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/threads/{thread_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == thread_id

    @pytest.mark.asyncio
    async def test_get_thread_not_found(self, client: AsyncClient):
        resp = await client.get("/api/v1/threads/nonexistent")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_delete_thread(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/threads/{thread_id}")
        assert resp.status_code == 204
        # Verify it is gone
        resp = await client.get(f"/api/v1/threads/{thread_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_thread_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/v1/threads/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_messages_empty(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/threads/{thread_id}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_messages_after_chat(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello"})
        resp = await client.get(f"/api/v1/threads/{thread_id}/messages")
        assert resp.status_code == 200
        assert len(resp.json()) == 2  # human + ai


# ── Chat ─────────────────────────────────────────────────────────────────────


class TestChatRoutes:
    @pytest.mark.asyncio
    async def test_send_message(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello agent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "ai"
        assert "content" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_send_message_thread_not_found(self, client: AsyncClient):
        resp = await client.post("/api/v1/chat/nonexistent", json={"message": "Hello"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_send_message_empty_body_returns_422(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_stream_message(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}/stream",
            json={"message": "Hello agent"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # The response body should contain SSE formatted data chunks
        body = resp.text
        assert "data:" in body

    @pytest.mark.asyncio
    async def test_stream_message_thread_not_found(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/chat/nonexistent/stream",
            json={"message": "Hello"},
        )
        assert resp.status_code == 404


# ── HITL ─────────────────────────────────────────────────────────────────────


class TestHITLRoutes:
    @pytest.mark.asyncio
    async def test_approve(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "approve"},
        )
        assert resp.status_code == 200
        assert "approved" in resp.json()["content"].lower()

    @pytest.mark.asyncio
    async def test_reject(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "reject", "reason": "Too risky"},
        )
        assert resp.status_code == 200
        assert "rejected" in resp.json()["content"].lower()

    @pytest.mark.asyncio
    async def test_edit(self, client: AsyncClient):
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

    @pytest.mark.asyncio
    async def test_edit_without_edits_returns_422(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "edit"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_action_returns_422(self, client: AsyncClient):
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/chat/{thread_id}",
            json={"tool_call_id": "tc-1", "action": "unknown"},
        )
        assert resp.status_code == 422


# ── Agents ───────────────────────────────────────────────────────────────────


class TestAgentRoutes:
    @pytest.mark.asyncio
    async def test_list_agents(self, client: AsyncClient):
        resp = await client.get("/api/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # The agents/ directory contains example-agent.yaml, and the fake loader
        # has it registered, so we should get at least one config back
        names = [a["name"] for a in data]
        assert "example-agent" in names

    @pytest.mark.asyncio
    async def test_get_agent(self, client: AsyncClient):
        resp = await client.get("/api/v1/agents/example-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "example-agent"

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, client: AsyncClient):
        resp = await client.get("/api/v1/agents/nonexistent")
        assert resp.status_code == 404


# ── Exception handlers ───────────────────────────────────────────────────────


class TestExceptionHandlers:
    @pytest.mark.asyncio
    async def test_thread_not_found_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/threads/does-not-exist")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_config_not_found_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/agents/missing-agent")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_agent_not_found_returns_404(self, client: AsyncClient):
        resp = await client.post("/api/v1/threads", json={"agent_name": "unknown-agent"})
        assert resp.status_code == 404
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_agent_error_returns_502(
        self, client: AsyncClient, fake_registry: FakeAgentRegistry
    ):
        """Verify that AgentError from the runner maps to a 502 response."""
        create_resp = await client.post("/api/v1/threads", json={"agent_name": "my-agent"})
        thread_id = create_resp.json()["id"]

        # Monkey-patch the runner to raise AgentError
        runner = fake_registry._runners["my-agent"]
        original_invoke = runner.invoke

        async def failing_invoke(tid: str, msg: str):
            raise AgentError("Backend failed")

        runner.invoke = failing_invoke
        resp = await client.post(f"/api/v1/chat/{thread_id}", json={"message": "Hello"})
        assert resp.status_code == 502
        assert "Backend failed" in resp.json()["detail"]

        runner.invoke = original_invoke
