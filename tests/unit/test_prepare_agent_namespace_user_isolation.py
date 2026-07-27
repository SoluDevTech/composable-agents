"""Tests for per-user namespace isolation in ``_prepare_agent_namespace``.

The factory copies selected skills/memories from the user-scoped source
namespace (``(user_id, "filesystem")``) into the agent's namespace
(``/agents/{name}/...`` within the same user-scoped namespace). When user A
runs an agent, only user A's skills are copied — user B's are invisible.

Uses a real :class:`InMemoryStore` (no DB required).
"""

import pytest
from langgraph.store.memory import InMemoryStore

from src.infrastructure.database.rls_context import current_user_id
from src.infrastructure.deepagent.factory import _prepare_agent_namespace


@pytest.fixture
def store() -> InMemoryStore:
    """Provide a fresh real InMemoryStore per test."""
    return InMemoryStore()


async def _put(store: InMemoryStore, ns: tuple[str, ...], key: str, content: str) -> None:
    """Helper: write a file into the store under the given namespace."""
    await store.aput(ns, key, {"content": content, "encoding": "utf-8"})


class TestPrepareAgentNamespaceUserIsolation:
    """Skills/memories are copied from the current user's namespace only."""

    async def test_user_a_run_copies_only_user_a_skills(self, store: InMemoryStore) -> None:
        # Arrange — seed a skill under uA and a different skill under uB
        await _put(store, ("uA", "filesystem"), "/skills/foo/SKILL.md", "# A foo skill")
        await _put(store, ("uB", "filesystem"), "/skills/foo/SKILL.md", "# B foo skill")

        # Act — run _prepare_agent_namespace as uA, selecting /skills/foo/
        tok_a = current_user_id.set("uA")
        try:
            skills_dir, _mem = await _prepare_agent_namespace(store, "agent1", ["/skills/foo/"], [])
        finally:
            current_user_id.reset(tok_a)

        # Assert — the copied SKILL.md under uA's agent namespace is uA's content
        item = await store.aget(("uA", "filesystem"), f"{skills_dir}foo/SKILL.md")
        assert item is not None
        assert item.value["content"] == "# A foo skill"

        # And uB's namespace does NOT contain the agent copy
        item_b = await store.aget(("uB", "filesystem"), f"{skills_dir}foo/SKILL.md")
        assert item_b is None

    async def test_user_b_run_copies_only_user_b_skills(self, store: InMemoryStore) -> None:
        # Arrange — seed skills under uA and uB
        await _put(store, ("uA", "filesystem"), "/skills/foo/SKILL.md", "# A")
        await _put(store, ("uB", "filesystem"), "/skills/foo/SKILL.md", "# B")

        # Act — run as uB
        tok_b = current_user_id.set("uB")
        try:
            skills_dir, _mem = await _prepare_agent_namespace(store, "agent1", ["/skills/foo/"], [])
        finally:
            current_user_id.reset(tok_b)

        # Assert — uB's agent namespace contains uB's content
        item = await store.aget(("uB", "filesystem"), f"{skills_dir}foo/SKILL.md")
        assert item is not None
        assert item.value["content"] == "# B"

    async def test_memories_scoped_per_user(self, store: InMemoryStore) -> None:
        # Arrange — seed memory under uA and uB
        await _put(store, ("uA", "filesystem"), "/memories/AGENTS.md", "# A agents")
        await _put(store, ("uB", "filesystem"), "/memories/AGENTS.md", "# B agents")

        # Act — run as uA
        tok_a = current_user_id.set("uA")
        try:
            _skills_dir, mem_paths = await _prepare_agent_namespace(store, "agent1", [], ["/memories/AGENTS.md"])
        finally:
            current_user_id.reset(tok_a)

        # Assert — uA's agent memory is uA's content
        item = await store.aget(("uA", "filesystem"), mem_paths[0])
        assert item is not None
        assert item.value["content"] == "# A agents"

    async def test_legacy_no_contextvar_uses_global_namespace(self, store: InMemoryStore) -> None:
        # Arrange — seed a skill under the legacy ("filesystem",) namespace
        await _put(store, ("filesystem",), "/skills/foo/SKILL.md", "# legacy")

        # Act — no contextvar
        assert current_user_id.get() is None
        skills_dir, _mem = await _prepare_agent_namespace(store, "agent1", ["/skills/foo/"], [])

        # Assert — the copy lives under ("filesystem",)
        item = await store.aget(("filesystem",), f"{skills_dir}foo/SKILL.md")
        assert item is not None
        assert item.value["content"] == "# legacy"

    async def test_cleanup_only_affects_current_user_namespace(self, store: InMemoryStore) -> None:
        # Arrange — uA has a stale agent skill; uB has its own
        await _put(store, ("uA", "filesystem"), "/agents/agent1/skills/old/SKILL.md", "# old A")
        await _put(store, ("uB", "filesystem"), "/agents/agent1/skills/old/SKILL.md", "# old B")

        # Act — run as uA selecting a DIFFERENT skill (triggers cleanup of "old")
        tok_a = current_user_id.set("uA")
        try:
            await _prepare_agent_namespace(store, "agent1", ["/skills/new/"], [])
        finally:
            current_user_id.reset(tok_a)

        # Assert — uA's "old" is deleted, uB's "old" is preserved
        item_a = await store.aget(("uA", "filesystem"), "/agents/agent1/skills/old/SKILL.md")
        assert item_a is None
        item_b = await store.aget(("uB", "filesystem"), "/agents/agent1/skills/old/SKILL.md")
        assert item_b is not None
        assert item_b.value["content"] == "# old B"
