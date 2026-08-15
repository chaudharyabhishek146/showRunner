"""Turn a product document into an executable, narratable step plan.

Claude reads the doc and emits a StepPlan via structured outputs. There is no
prompt-and-hope JSON parsing here and no assistant-turn prefill — prefills are
rejected with a 400 on Opus 4.6 / Sonnet 4.6 and later, and structured outputs
are the supported replacement.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import anthropic

from . import config
from .claude_client import cached_doc_block, describe_error, get_client, has_api_key
from .models import Action, ActionType, Step, StepPlan

log = logging.getLogger(__name__)

ALLOWED_HOSTS = {"github.com", "www.github.com"}

PLANNER_PREAMBLE = """\
You are the planning half of a live product-walkthrough agent. A salesperson \
will play your plan back to a prospective customer while a real browser drives \
a real GitHub repository on screen. Everything you emit is spoken aloud and \
executed for real, so it must be both accurate and demo-safe.

Produce exactly 5 steps that teach the product doc's core workflow through \
actions a browser can perform. Each step must:
  - demonstrate one idea from the doc, named in `doc_reference`
  - carry a short imperative `title` and a viewer-facing `goal`
  - contain 1-4 actions drawn ONLY from the allowed vocabulary

Allowed action types and their fields:
  navigate  -> target = absolute https://github.com/... URL
  click     -> target = the element's visible/accessible name, role = ARIA role
               ("button", "link", "textbox", "menuitem", "tab")
  fill      -> target = the field's accessible name, role = "textbox",
               value = the text to type
  press     -> value = a key name such as "Enter" or "Escape"
  wait      -> value = seconds as a string, e.g. "2"
  highlight -> target = accessible name of an element to point at, role = ARIA role

Hard rules:
  - Never navigate anywhere outside github.com.
  - Never emit CSS or XPath selectors. Accessible names and roles only.
  - Never attempt to log in, enter credentials, or change account settings.
  - Never delete anything.
  - Leave `narration` empty; a later pass writes it.
"""


def _fallback_plan(repo: str) -> StepPlan:
    """A hand-verified plan used when Claude is unavailable.

    A live demo must never open with a stack trace, so the agent always has a
    working plan even with no API key and no network.
    """
    base = f"https://github.com/{repo}" if repo else "https://github.com"
    return StepPlan(
        workflow_name="github-issue-to-board",
        summary=(
            "Take a piece of work from an idea to a tracked card on the team board "
            "without ever leaving GitHub."
        ),
        steps=[
            Step(
                id=1,
                title="Open the issue tracker",
                goal="Show that planning lives in the same place as the code.",
                doc_reference="Issues are permanent, addressable records",
                actions=[Action(type=ActionType.NAVIGATE, target=f"{base}/issues")],
            ),
            Step(
                id=2,
                title="File a new issue",
                goal="Turn a vague request into a titled, described unit of work.",
                doc_reference="Title and Body",
                actions=[
                    Action(type=ActionType.NAVIGATE, target=f"{base}/issues/new"),
                    Action(
                        type=ActionType.FILL,
                        target="Title",
                        role="textbox",
                        value="Fix crash on empty telemetry payload",
                    ),
                ],
            ),
            Step(
                id=3,
                title="Describe the work",
                goal="Capture reproduction steps so anyone can pick this up.",
                doc_reference="Body — reproduction steps, acceptance criteria",
                actions=[
                    Action(
                        type=ActionType.FILL,
                        target="Body",
                        role="textbox",
                        value=(
                            "Steps:\n1. POST an empty telemetry batch\n"
                            "2. Observe 500\n\nExpected: 400 with a clear message."
                        ),
                    ),
                    Action(type=ActionType.WAIT, value="1"),
                ],
            ),
            Step(
                id=4,
                title="Submit and triage",
                goal="Create the record, then classify it with labels.",
                doc_reference="Labels drive filtering, automation, and board routing",
                actions=[
                    Action(
                        type=ActionType.CLICK, target="Create", role="button"
                    ),
                    Action(type=ActionType.WAIT, value="2"),
                    Action(type=ActionType.HIGHLIGHT, target="Labels", role="button"),
                ],
            ),
            Step(
                id=5,
                title="Put it on the board",
                goal="Show the same issue rendering as a card in Todo.",
                doc_reference="A Project Board is a live view over a set of issues",
                actions=[
                    Action(type=ActionType.NAVIGATE, target=f"{base}/projects"),
                    Action(type=ActionType.WAIT, value="2"),
                ],
            ),
        ],
    )


def _sanitise(plan: StepPlan) -> StepPlan:
    """Enforce the governance rules the prompt merely asked for.

    An LLM-authored plan drives a real browser, so the domain allowlist is
    checked in code rather than trusted to the model.
    """
    clean_steps: list[Step] = []
    for index, step in enumerate(plan.steps, start=1):
        actions = []
        for action in step.actions:
            if action.type is ActionType.NAVIGATE:
                host = (urlparse(action.target).hostname or "").lower()
                if host not in ALLOWED_HOSTS:
                    log.warning("Dropping out-of-policy navigation to %s", action.target)
                    continue
            actions.append(action)
        step.id = index
        step.actions = actions
        clean_steps.append(step)
    plan.steps = clean_steps
    return plan


async def parse_document(doc: str, repo: str = "") -> StepPlan:
    """Ask Claude for a step plan, falling back to the verified plan on failure."""
    repo = repo or config.DEMO_REPO
    if not has_api_key():
        log.warning("No ANTHROPIC_API_KEY — using the built-in fallback plan.")
        return _fallback_plan(repo)

    target = f"https://github.com/{repo}" if repo else "https://github.com"
    try:
        response = await get_client().messages.parse(
            model=config.MODEL,
            max_tokens=8000,
            system=cached_doc_block(doc, PLANNER_PREAMBLE),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"The demo repository is {target}. Build the 5-step plan that "
                        "walks a customer from filing an issue to seeing it as a card "
                        "on the project board."
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
        return _sanitise(plan)
    except (anthropic.APIError, ValueError) as exc:
        log.error("Doc parsing failed (%s) — using fallback plan", describe_error(exc))
        return _fallback_plan(repo)


async def replan(
    plan: StepPlan, doc: str, focus: str, completed_index: int
) -> StepPlan | None:
    """Rewrite the *remaining* steps when a customer redirects the demo.

    Returns None if re-planning fails, so the caller can simply carry on with
    the original plan rather than stranding the run.
    """
    if not has_api_key():
        return None

    done = plan.steps[:completed_index]
    remaining = plan.steps[completed_index:]
    outline = "\n".join(f"{s.id}. {s.title} — {s.goal}" for s in remaining)

    try:
        response = await get_client().messages.parse(
            model=config.MODEL,
            max_tokens=8000,
            system=cached_doc_block(doc, PLANNER_PREAMBLE),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"A walkthrough is already running on {config.TARGET_URL}. "
                        f"{len(done)} steps are finished and must not be repeated.\n\n"
                        f"Remaining steps as originally planned:\n{outline}\n\n"
                        f"The customer just asked to see: {focus!r}\n\n"
                        "Re-plan ONLY the remaining steps so they cover that instead. "
                        f"Return the full plan: the {len(done)} completed steps "
                        "unchanged, followed by the new ones."
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
        return _sanitise(revised)
    except (anthropic.APIError, ValueError) as exc:
        log.error("Re-planning failed: %s", describe_error(exc))
        return None
