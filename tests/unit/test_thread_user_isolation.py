"""Tests for per-user isolation in :class:`PostgresThreadRepository`.

The repository reads the ``current_user_id`` contextvar and:

* On **writes** (``create``) — sets the row's ``user_id`` to the contextvar
  value (or ``""`` when the contextvar is unset, preserving existing
  behaviour).
* On **reads** (``get`` / ``list_all``) — filters by ``user_id == contextvar``
  when the contextvar is set. When the contextvar is ``None`` no filter is
  applied (existing behaviour, so the pre-auth-core test suite stays green).
* On **delete** — filters by ``user_id`` when the contextvar is set; deleting
  another user's thread raises :class:`ThreadNotFoundError`.

Uses the shared ``db_engine`` + ``thread_repo`` fixtures (real SQLite).
"""

import pytest

from src.domain.entities.thread import Thread
from src.domain.errors.thread import ThreadNotFoundError
from src.infrastructure.database.rls_context import current_user_id


class TestThreadUserIsolation:
    """Per-user filtering driven by the ``current_user_id`` contextvar."""

    async def test_create_sets_user_id_from_contextvar(self, thread_repo):
        # Arrange
        token = current_user_id.set("uA")
        try:
            # Act
            thread = await thread_repo.create("agent-x")
        finally:
            current_user_id.reset(token)

        # Assert — the persisted row carries user_id="uA"
        # Re-read with the same contextvar to confirm the filter lets us see it.
        token2 = current_user_id.set("uA")
        try:
            refetched = await thread_repo.get(thread.id)
        finally:
            current_user_id.reset(token2)
        assert refetched.id == thread.id
        assert refetched.user_id == "uA"

    async def test_list_under_uB_excludes_uA_thread(self, thread_repo):
        # Arrange — create under uA
        tok_a = current_user_id.set("uA")
        try:
            await thread_repo.create("agent-a")
        finally:
            current_user_id.reset(tok_a)

        # Act — list under uB
        tok_b = current_user_id.set("uB")
        try:
            threads = await thread_repo.list_all()
        finally:
            current_user_id.reset(tok_b)

        # Assert — uA's thread is not visible to uB
        assert threads == []

    async def test_get_under_uB_raises_ThreadNotFoundError_for_uA_thread(self, thread_repo):
        # Arrange
        tok_a = current_user_id.set("uA")
        try:
            thread = await thread_repo.create("agent-a")
        finally:
            current_user_id.reset(tok_a)

        # Act / Assert
        tok_b = current_user_id.set("uB")
        try:
            with pytest.raises(ThreadNotFoundError):
                await thread_repo.get(thread.id)
        finally:
            current_user_id.reset(tok_b)

    async def test_list_under_uB_returns_only_uB_threads(self, thread_repo):
        # Arrange
        tok_a = current_user_id.set("uA")
        try:
            await thread_repo.create("agent-a")
        finally:
            current_user_id.reset(tok_a)

        tok_b = current_user_id.set("uB")
        try:
            thread_b = await thread_repo.create("agent-b")
            threads = await thread_repo.list_all()
        finally:
            current_user_id.reset(tok_b)

        # Assert — only uB's thread is visible
        assert len(threads) == 1
        assert threads[0].id == thread_b.id
        assert threads[0].user_id == "uB"

    async def test_list_with_no_contextvar_returns_all_threads(self, thread_repo):
        # Arrange — no contextvar set; create under uA and uB then unset
        tok_a = current_user_id.set("uA")
        try:
            await thread_repo.create("agent-a")
        finally:
            current_user_id.reset(tok_a)

        tok_b = current_user_id.set("uB")
        try:
            await thread_repo.create("agent-b")
        finally:
            current_user_id.reset(tok_b)

        # Act — no contextvar (default None)
        assert current_user_id.get() is None
        threads = await thread_repo.list_all()

        # Assert — all threads visible (no filter)
        assert len(threads) == 2

    async def test_delete_under_uB_raises_for_uA_thread(self, thread_repo):
        # Arrange
        tok_a = current_user_id.set("uA")
        try:
            thread = await thread_repo.create("agent-a")
        finally:
            current_user_id.reset(tok_a)

        # Act / Assert — uB cannot delete uA's thread
        tok_b = current_user_id.set("uB")
        try:
            with pytest.raises(ThreadNotFoundError):
                await thread_repo.delete(thread.id)
        finally:
            current_user_id.reset(tok_b)

        # The thread is still visible to uA
        tok_a2 = current_user_id.set("uA")
        try:
            refetched = await thread_repo.get(thread.id)
        finally:
            current_user_id.reset(tok_a2)
        assert refetched.id == thread.id

    async def test_created_thread_has_empty_user_id_when_contextvar_unset(self, thread_repo):
        # Arrange — no contextvar
        assert current_user_id.get() is None
        # Act
        thread = await thread_repo.create("agent-x")
        # Assert — defaults to "" (matches DB default and existing behaviour)
        assert thread.user_id == ""

    async def test_thread_entity_has_user_id_field(self):
        # Arrange / Act
        t = Thread(agent_name="x")
        # Assert
        assert hasattr(t, "user_id")
        assert t.user_id == ""
