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
    # ARIA role for semantic lookup. Products rewrite their CSS constantly;
    # the role and visible name of a control are what actually survive.
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


class TabInfo(BaseModel):
    """One open tab in the user's Chrome, offered as a demo target."""

    index: int
    title: str = ""
    url: str = ""
    host: str = ""
    active: bool = False


class DemoRequest(BaseModel):
    """Everything the user supplies to define a demo.

    All three are per-run inputs, never configuration: the document they
    uploaded, the flow they want shown, and the tab to show it in.
    """

    doc_id: str = ""
    # Inline document text, for clients that don't want to upload a file first.
    doc: str = ""
    # "the issue triage flow", "how to build a playlist" — free text.
    focus: str = ""
    # Which tab: a title fragment, a host, or a full URL to open.
    tab: str = ""
    # Replay a remembered walkthrough instead of planning a new one.
    workflow: str = ""


class QAResponse(BaseModel):
    """Claude's structured answer to a mid-demo question.

    Answering and deciding whether the customer just redirected the demo are
    the same judgement call, so they share one API round trip — a second
    classifier call would double the pause the customer sits through.
    """

    answer: str = Field(description="What the solutions engineer says out loud")
    wants_plan_change: bool = Field(
        default=False,
        description=(
            "True whenever the customer wants something *shown* — 'show me how "
            "to filter', 'how do I share this', 'skip to the board'. False only "
            "when there is nothing to demonstrate: a question about what is "
            "already on screen, about policy or pricing, or about something "
            "outside this demo's scope."
        ),
    )
    requested_focus: str = Field(
        default="",
        description=(
            "The thing to demonstrate, as a short phrase ('filtering the data "
            "by status'). Required when wants_plan_change is true."
        ),
    )


class ClientEvent(BaseModel):
    """Inbound WebSocket message from the browser."""

    type: Literal[
        "start", "question", "pause", "resume", "skip", "stop", "list_tabs", "reply"
    ]
    text: str = ""
    # Which question is being answered, for "reply". Named rather than implicit
    # so a stale click on an old prompt can't answer the current one.
    prompt_id: str = ""
    workflow: str = ""
    doc_id: str = ""
    doc: str = ""
    focus: str = ""
    tab: str = ""

    def to_request(self) -> DemoRequest:
        return DemoRequest(
            doc_id=self.doc_id,
            doc=self.doc,
            focus=self.focus or self.text,
            tab=self.tab,
            workflow=self.workflow,
        )


class ServerEvent(BaseModel):
    """Outbound WebSocket message to the browser."""

    type: Literal[
        "plan",
        "step_start",
        "narration",
        "screenshot",
        "frame",
        "step_done",
        "answer",
        "status",
        "error",
        "complete",
        "tabs",
        # A question *for the presenter*, with buttons. payload carries
        # {"id": ..., "options": [...]}; the client answers with a "reply".
        "prompt",
    ]
    step_id: int | None = None
    text: str = ""
    # base64-encoded PNG, no data: prefix.
    image: str | None = None
    payload: dict | None = None
