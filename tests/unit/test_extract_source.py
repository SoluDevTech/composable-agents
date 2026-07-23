"""Unit tests for DeepAgentRunner._extract_source static method."""

from src.infrastructure.deepagent.adapter import DeepAgentRunner


class TestExtractSource:
    """Tests for _extract_source namespace parsing."""

    def test_extracts_subagent_name_from_task_namespace(self) -> None:
        """Should extract subagent name from 'Agent|task|name|tools' pattern."""
        metadata = {"langgraph_checkpoint_ns": "Agent|task|security-auditor|tools"}
        result = DeepAgentRunner._extract_source(metadata)
        assert result == "security-auditor"

    def test_returns_none_for_empty_namespace(self) -> None:
        """Should return None when namespace is empty."""
        result = DeepAgentRunner._extract_source({"langgraph_checkpoint_ns": ""})
        assert result is None

    def test_returns_none_for_missing_namespace_key(self) -> None:
        """Should return None when langgraph_checkpoint_ns key is absent."""
        result = DeepAgentRunner._extract_source({})
        assert result is None

    def test_returns_none_when_task_not_in_namespace(self) -> None:
        """Should return None when 'task' token is not found."""
        result = DeepAgentRunner._extract_source(
            {"langgraph_checkpoint_ns": "Agent|some-other-path"}
        )
        assert result is None

    def test_returns_none_when_task_is_last_token(self) -> None:
        """Should return None when 'task' is the last token (no name follows)."""
        result = DeepAgentRunner._extract_source(
            {"langgraph_checkpoint_ns": "Agent|task"}
        )
        assert result is None

    def test_extracts_name_with_multiple_separators(self) -> None:
        """Should extract the token immediately after 'task'."""
        metadata = {
            "langgraph_checkpoint_ns": "Agent|task|my-agent|some|extra|tokens"
        }
        result = DeepAgentRunner._extract_source(metadata)
        assert result == "my-agent"