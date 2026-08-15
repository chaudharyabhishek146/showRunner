"""Claude as the voice of the demo.

Two jobs:
  1. `write_narration` — pre-generates the spoken line for every step *before*
     execution starts. Doing this up front is what keeps playback snappy; if we
     called Claude between steps, every transition would stall on a round trip.
  2. `answer_question` — the only live call. It runs while the browser is frozen
     mid-step and sees the current screenshot, so answers are grounded in what
     the customer is actually looking at.
"""

from __future__ import annotations

import logging

import anthropic

from . import config
from .claude_client import (
    cached_doc_block,
    describe_error,
    get_client,
    has_api_key,
    text_of,
)
from .models import QAResponse, StepPlan

log = logging.getLogger(__name__)

NARRATOR_PREAMBLE = """\
You are narrating a live product demo to a prospective customer. You speak while \
a real browser performs each action on screen.

Voice: a confident solutions engineer. Warm, concise, never breathless. You are \
explaining why the product is built this way, not reading a feature list.

Rules for every line you write:
  - 2 to 3 sentences. It is spoken aloud, so it must be easy to say.
  - Tie the on-screen action to the idea from the product doc it demonstrates.
  - No bullet points, no markdown, no stage directions, no "as you can see".
  - Never invent product capabilities that are not in the doc.
"""

QA_PREAMBLE = """\
You are the solutions engineer running a live product demo. The demo is paused \
mid-step because the customer asked a question, and the current screen is \
attached as an image.

Answer in 2-4 sentences, grounded in the product doc and in what is visible on \
screen. If the doc does not cover it, say so plainly and offer to follow up — \
do not speculate about roadmap or invent behaviour. Close by pointing back to \
where the demo is about to resume.

Also judge whether they were asking a *question* or steering the *demo*. Set \
`wants_plan_change` to true only when they asked to see something different \
("skip ahead to the board", "can you show labels instead") — never for a \
plain question about what is already on screen. When it is true, put what they \
want to see into `requested_focus`.
"""


async def write_narration(plan: StepPlan, doc: str) -> StepPlan:
    """Fill in `narration` for every step in the plan, in one Claude call."""
    if not has_api_key():
        for step in plan.steps:
            step.narration = f"{step.goal} ({step.doc_reference})"
        return plan

    outline = "\n".join(
        f"{s.id}. {s.title} — goal: {s.goal} — doc concept: {s.doc_reference} — "
        f"on screen: {'; '.join(a.type.value + ' ' + a.target for a in s.actions)}"
        for s in plan.steps
    )

    try:
        response = await get_client().messages.create(
            model=config.MODEL,
            max_tokens=4000,
            system=cached_doc_block(doc, NARRATOR_PREAMBLE),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Walkthrough: {plan.workflow_name}\n"
                        f"Thesis: {plan.summary}\n\nSteps:\n{outline}\n\n"
                        "Write the spoken line for each step. Output one line per "
                        "step, prefixed with the step number and a pipe, like:\n"
                        "1| <narration>\n2| <narration>\n"
                        "Nothing else."
                    ),
                }
            ],
        )
        _apply_lines(plan, text_of(response))
        log.info(
            "Narration ready (cache read: %s tokens)",
            getattr(response.usage, "cache_read_input_tokens", 0),
        )
    except anthropic.APIError as exc:
        log.error("Narration generation failed: %s", describe_error(exc))
        for step in plan.steps:
            if not step.narration:
                step.narration = f"{step.goal} ({step.doc_reference})"
    return plan


def _apply_lines(plan: StepPlan, raw: str) -> None:
    """Map `N| text` lines back onto steps, tolerating a stray preamble."""
    by_id = {step.id: step for step in plan.steps}
    for line in raw.splitlines():
        if "|" not in line:
            continue
        head, _, body = line.partition("|")
        head = head.strip().rstrip(".")
        if head.isdigit() and int(head) in by_id:
            by_id[int(head)].narration = body.strip()
    for step in plan.steps:
        if not step.narration:
            step.narration = f"{step.goal} ({step.doc_reference})"


async def answer_question(
    question: str,
    doc: str,
    plan: StepPlan,
    step_index: int,
    screenshot_b64: str | None,
) -> QAResponse:
    """Answer a customer's mid-demo question using the frozen screen as context."""
    if not has_api_key():
        return QAResponse(
            answer=(
                "Claude isn't configured in this environment, so I can't answer live "
                "questions right now — but the walkthrough will continue."
            )
        )

    current = plan.steps[step_index] if 0 <= step_index < len(plan.steps) else None
    where = (
        f"Currently on step {current.id} of {len(plan.steps)}: {current.title} "
        f"(demonstrating: {current.doc_reference})."
        if current
        else "The walkthrough has not started yet."
    )

    content: list[dict] = []
    if screenshot_b64:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": screenshot_b64,
                },
            }
        )
    content.append({"type": "text", "text": f"{where}\n\nCustomer asks: {question}"})

    try:
        response = await get_client().messages.parse(
            model=config.MODEL,
            max_tokens=2000,
            system=cached_doc_block(doc, QA_PREAMBLE),
            messages=[{"role": "user", "content": content}],
            output_format=QAResponse,
        )
        parsed = response.parsed_output
        if parsed is None or not parsed.answer:
            return QAResponse(answer=text_of(response) or "Let me follow up on that.")
        return parsed
    except anthropic.APIError as exc:
        log.error("Q&A failed: %s", describe_error(exc))
        return QAResponse(
            answer=f"I couldn't reach Claude to answer that — {describe_error(exc)}"
        )
