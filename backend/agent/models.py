"""Shared data models for the walkthrough agent.

These are the contract between the doc parser, the executor, the WebSocket
layer, and the frontend. Keep them boring and serialisable.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """The only browser verbs the agent is allowed to emit.

    Constraining the action vocabulary is what makes an LLM-authored plan
    executable — Claude picks from this set, it does not invent selectors.
    """

    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    PRESS = "press"
    WAIT = "wait"
    HIGHLIGHT = "highlight"


class Action(BaseModel):
    """One browser operation inside a step."""

    type: ActionType
    # For NAVIGATE: the URL. For CLICK/FILL/HIGHLIGHT: the accessible name.
    target: str = ""
    # ARIA role for semantic lookup — far more stable than CSS on GitHub.
    role: str | None = None
    # For FILL: the text to type. For PRESS: the key. For WAIT: seconds.
    value: str = ""


class Step(BaseModel):
    """A single narrated beat of the walkthrough."""

    id: int
    title: str = Field(description="Short imperative label, e.g. 'Create the issue'")
    goal: str = Field(description="What the viewer should understand after this step")
    doc_reference: str = Field(
        default="",
        description="The concept from the product doc this step demonstrates",
    )
    actions: list[Action] = Field(default_factory=list)
    # Filled in by the narrator before execution starts, so playback is instant.
    narration: str = ""


class StepPlan(BaseModel):
    """Claude's structured output when parsing the product doc."""

    workflow_name: str
    summary: str = Field(description="One sentence on what this walkthrough proves")
    steps: list[Step]


class QAResponse(BaseModel):
    """Claude's structured answer to a mid-demo question.

    Answering and deciding whether the customer just redirected the demo are
    the same judgement call, so they share one API round trip — a second
    classifier call would double the pause the customer sits through.
    """

    answer: str = Field(description="What the solutions engineer says out loud")
    wants_plan_change: bool = Field(
        default=False,
        description="True only if the customer asked to see something different",
    )
    requested_focus: str = Field(
        default="",
        description="What they want to see instead, if wants_plan_change is true",
    )


class ClientEvent(BaseModel):
    """Inbound WebSocket message from the browser."""

    type: Literal["start", "question", "pause", "resume", "skip", "stop"]
    text: str = ""
    workflow: str = ""


class ServerEvent(BaseModel):
    """Outbound WebSocket message to the browser."""

    type: Literal[
        "plan",
        "step_start",
        "narration",
        "screenshot",
        "step_done",
        "answer",
        "status",
        "error",
        "complete",
    ]
    step_id: int | None = None
    text: str = ""
    # base64-encoded PNG, no data: prefix.
    image: str | None = None
    payload: dict | None = None
