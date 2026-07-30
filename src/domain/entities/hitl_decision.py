"""HITL decision domain entity.

A ``HitlDecision`` represents a single human decision (approve / reject / edit)
applied to one interrupted tool call during a Human-In-The-Loop resume flow.
"""

from typing import Literal

from pydantic import BaseModel


class HitlDecision(BaseModel):
    """A single human decision for an interrupted tool call.

    Attributes:
        tool_call_id: The id of the interrupted tool call this decision targets.
        action: The decision kind: ``"approve"``, ``"reject"`` or ``"edit"``.
        reason: Optional reject reason (ignored for approve/edit).
        edits: Edited args dict, required for ``action="edit"``.
    """

    tool_call_id: str
    action: Literal["approve", "reject", "edit"]
    reason: str | None = None
    edits: dict | None = None
