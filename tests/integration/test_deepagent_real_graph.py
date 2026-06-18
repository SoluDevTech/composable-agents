"""Integration tests for the REAL deepagents graph.

Unlike the unit tests (which mock create_deep_agent and the LangGraph), these
tests build an actual ``create_deep_agent`` graph with a deterministic fake
chat model and exercise the full agent -> tool -> agent -> final cycle.

Purpose: catch breaking changes in the ``deepagents`` SDK (create_deep_agent
signature, tool execution, graph structure) that the mocked unit tests cannot
detect. The fake model (GenericFakeChatModel) requires no API key and is fully
deterministic.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from src.infrastructure.deepagent.factory import create_deep_agent


class _FakeToolCallingModel(GenericFakeChatModel):
    """GenericFakeChatModel that accepts bind_tools (deepagents calls it).

    The returned tool calls are predetermined, so bind_tools just returns self.
    """

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self


def _fake_model() -> _FakeToolCallingModel:
    """A deterministic chat model that issues one tool call then a final answer."""
    return _FakeToolCallingModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "echo", "args": {"text": "hello"}, "id": "call_1", "type": "tool_call"}
                    ],
                ),
                AIMessage(content="final answer"),
                AIMessage(content="final answer"),
            ]
        )
    )


@tool
def echo(text: str) -> str:
    """Echo the provided text back."""
    return f"echoed: {text}"


class TestRealDeepAgentGraph:
    def test_agent_executes_tool_then_final_answer(self):
        """The graph must call the tool, ingest its result, then produce a final answer."""
        graph = create_deep_agent(
            model=_fake_model(),
            tools=[echo],
            system_prompt="You are a helpful agent. Use the echo tool once then answer.",
            checkpointer=MemorySaver(),
        )

        result = graph.invoke(
            {"messages": [HumanMessage(content="echo hello please")]},
            config={"configurable": {"thread_id": "test-thread"}},
        )

        messages = result["messages"]
        # Human -> AI(tool_call) -> Tool(result) -> AI(final)
        roles = [type(m).__name__ for m in messages]
        assert "ToolMessage" in roles, f"Expected a ToolMessage in the cycle, got: {roles}"

        final = messages[-1]
        assert isinstance(final, AIMessage)
        assert final.content == "final answer"

    def test_graph_has_tools_node(self):
        """The runner adapter relies on a 'tools' node existing on the compiled graph."""
        graph = create_deep_agent(
            model=_fake_model(),
            tools=[echo],
            system_prompt="You are a helper.",
            checkpointer=MemorySaver(),
        )
        assert "tools" in graph.nodes, "deepagents graph must expose a 'tools' node"
