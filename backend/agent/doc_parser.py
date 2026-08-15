"""Turn an uploaded product document into an executable, narratable step plan.

The planner knows nothing about any particular product. It gets three things at
run time — the document the user uploaded, the flow they asked to see, and a
reading of the page that is actually open in their browser — and writes a plan
against the controls that are really there.

Claude emits a StepPlan via structured outputs. There is no prompt-and-hope JSON
parsing here and no assistant-turn prefill — prefills are rejected with a 400 on
Opus 4.6 / Sonnet 4.6 and later, and structured outputs are the replacement.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import anthropic

from . import config
from .claude_client import cached_doc_block, describe_error, get_client, has_api_key
from .models import Action, ActionType, Step, StepPlan

log = logging.getLogger(__name__)

PLANNER_PREAMBLE = """\
You are the planning half of a live product-walkthrough agent. A presenter will \
play your plan back to a prospective customer while a real browser — the \
presenter's own, already signed in — drives the real product on screen. \
Everything you emit is spoken aloud and executed for real, so it must be both \
accurate and demo-safe.

You are given the product document, the flow the presenter asked to show, and a \
reading of the page that is currently open: its title, its URL, and the roles \
and visible names of the controls on it. Plan against THOSE controls. Do not \
invent element names, and do not assume conventions from other products.

Produce 4 to 6 steps that teach the requested flow through actions a browser \
can perform — unless the document states a length or a step count of its own \
("about two minutes", "plan exactly three steps"), in which case that wins. A \
presenter who wrote down how long they have has already made that decision.

Each step must:
  - demonstrate one idea from the document, named in `doc_reference`
  - carry a short imperative `title` and a viewer-facing `goal`
  - contain 1-4 actions drawn ONLY from the allowed vocabulary

Allowed action types and their fields:
  navigate  -> target = an absolute https:// URL inside the demo scope
  click     -> target = the element's visible/accessible name, role = ARIA role
               ("button", "link", "textbox", "menuitem", "tab")
  fill      -> target = the field's accessible name, role = "textbox",
               value = the text to type
  press     -> value = a key name such as "Enter" or "Escape"
  wait      -> value = seconds as a string, e.g. "2"
  highlight -> target = accessible name of an element to point at, role = ARIA role

Hard rules:
  - Never navigate outside the demo scope you are given.
  - Never emit CSS or XPath selectors. Accessible names and roles only.
  - Never log in, enter credentials, or change account or billing settings.
  - Never delete anything, and never send, publish, or pay for anything.
  - Prefer showing over changing: open, filter, and explain existing state \
rather than creating records on someone's live account. Use a `fill` only when \
the flow genuinely requires typing, and stop short of the final submit unless \
the presenter asked for it.
  - Leave `narration` empty; a later pass writes it.
"""

_HEADING = re.compile(r"^\s{0,3}(#{1,4})\s+(.+?)\s*#*\s*$", re.MULTILINE)


def _fallback_plan(doc: str, url: str, focus: str) -> StepPlan:
    """A plan built without Claude, from the document's own structure.

    A live demo must never open with a stack trace. With no API key the agent
    can't reason about the page, so it does the one thing it can still do
    honestly: hold on the screen the presenter chose and walk the document's
    sections aloud, one beat at a time.
    """
    sections = [title.strip() for _, title in _HEADING.findall(doc)][:5]
    if not sections:
        sections = [line.strip() for line in doc.splitlines() if line.strip()][:5]
    if not sections:
        sections = ["Overview"]

    host = (urlparse(url).hostname or "the product").lower()
    steps = [
        Step(
            id=index,
            title=section[:60],
            goal=f"Explain {section[:60]} on the screen in front of us.",
            doc_reference=section[:80],
            actions=[Action(type=ActionType.WAIT, value="3")],
        )
        for index, section in enumerate(sections, start=1)
    ]
    return StepPlan(
        workflow_name=(focus or f"{host} walkthrough")[:60],
        summary=(
            f"A narrated tour of {focus or host} using the document's own outline. "
            "Set ANTHROPIC_API_KEY for a plan that drives the page."
        ),
        steps=steps,
    )


def _sanitise(plan: StepPlan, allowed_hosts: set[str]) -> StepPlan:
    """Enforce in code the governance the prompt merely asked for.

    An LLM-authored plan drives a real browser inside someone's signed-in
    session, so scope is checked here rather than trusted to the model. The
    allowlist is whatever the chosen tab implies — this file names no site.
    """
    clean_steps: list[Step] = []
    for index, step in enumerate(plan.steps, start=1):
        actions = []
        for action in step.actions:
            if action.type is ActionType.NAVIGATE and not _in_scope(
                action.target, allowed_hosts
            ):
                log.warning("Dropping out-of-scope navigation to %s", action.target)
                continue
            actions.append(action)
        step.id = index
        step.actions = actions
        clean_steps.append(step)
    plan.steps = clean_steps
    return plan


def _in_scope(url: str, allowed_hosts: set[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host or not allowed_hosts:
        return False
    return any(
        host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts
    )


def _describe_page(outline: dict) -> str:
    """Render the live page reading into something a prompt can carry."""
    elements = outline.get("elements") or []
    listing = "\n".join(f"  {e['role']}: {e['name']}" for e in elements)
    return (
        f"Page title: {outline.get('title', '')}\n"
        f"Page URL: {outline.get('url', '')}\n"
        f"Controls visible on this page ({len(elements)}):\n"
        f"{listing or '  (none readable)'}"
    )


async def parse_document(
    doc: str,
    focus: str,
    outline: dict,
    allowed_hosts: set[str],
    constraint: str = "",
) -> StepPlan:
    """Ask Claude for a step plan, falling back to a doc outline on failure."""
    url = outline.get("url", "")
    if not has_api_key():
        log.warning("No ANTHROPIC_API_KEY — using the document-outline plan.")
        return _fallback_plan(doc, url, focus)

    scope = ", ".join(sorted(allowed_hosts)) or "(none)"
    try:
        response = await get_client().messages.parse(
            model=config.MODEL,
            max_tokens=8000,
            system=cached_doc_block(doc, PLANNER_PREAMBLE),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"The presenter wants to show: {focus or 'the core workflow in the document'}\n\n"
                        f"Demo scope — you may navigate only within: {scope}\n\n"
                        + (f"{constraint}\n\n" if constraint else "")
                        + f"{_describe_page(outline)}\n\n"
                        "Build the plan for that flow, starting from this screen."
                    ),
                }
            ],
            output_format=StepPlan,
        )
        plan = response.parsed_output
        if plan is None or not plan.steps:
            raise ValueError("Claude returned an empty plan")
        log.info(
            "Parsed %d steps (cache read: %s tokens)",
            len(plan.steps),
            getattr(response.usage, "cache_read_input_tokens", 0),
        )
        return _sanitise(plan, allowed_hosts)
    except (anthropic.APIError, ValueError) as exc:
        log.error("Doc parsing failed (%s) — using fallback plan", describe_error(exc))
        return _fallback_plan(doc, url, focus)


async def replan(
    plan: StepPlan,
    doc: str,
    focus: str,
    completed_index: int,
    outline: dict,
    allowed_hosts: set[str],
) -> StepPlan | None:
    """Rewrite the *remaining* steps when a customer redirects the demo.

    Returns None if re-planning fails, so the caller can simply carry on with
    the original plan rather than stranding the run.
    """
    if not has_api_key():
        return None

    done = plan.steps[:completed_index]
    remaining = plan.steps[completed_index:]
    outline_text = "\n".join(f"{s.id}. {s.title} — {s.goal}" for s in remaining)
    scope = ", ".join(sorted(allowed_hosts)) or "(none)"

    try:
        response = await get_client().messages.parse(
            model=config.MODEL,
            max_tokens=8000,
            system=cached_doc_block(doc, PLANNER_PREAMBLE),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"A walkthrough is already running. {len(done)} steps are "
                        "finished and must not be repeated.\n\n"
                        f"Demo scope — you may navigate only within: {scope}\n\n"
                        f"{_describe_page(outline)}\n\n"
                        f"Remaining steps as originally planned:\n{outline_text}\n\n"
                        f"The customer just asked to see: {focus!r}\n\n"
                        "Re-plan ONLY the remaining steps so they cover that instead, "
                        "starting from the screen described above. Return the full "
                        f"plan: the {len(done)} completed steps unchanged, followed "
                        "by the new ones."
                    ),
                }
            ],
            output_format=StepPlan,
        )
        revised = response.parsed_output
        if revised is None or len(revised.steps) <= completed_index:
            return None
        # Preserve history verbatim; only the future is allowed to change.
        revised.steps = done + revised.steps[completed_index:]
        log.info("Re-planned around %r", focus)
        return _sanitise(revised, allowed_hosts)
    except (anthropic.APIError, ValueError) as exc:
        log.error("Re-planning failed: %s", describe_error(exc))
        return None
