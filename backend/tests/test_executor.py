"""Tests for the parts that make or break a live demo.

The CI stage gates the deploy on these, so they are deliberately fast and
hermetic: no network, no Claude calls, and a fake browser. The one test that
needs real Chromium is marked `integration` and skipped when it isn't installed.
"""

from __future__ import annotations

import asyncio
import io
import zipfile

import pytest

from agent import config, docs, memory
from agent.doc_parser import _fallback_plan, _sanitise
from agent.models import Action, ActionType, ServerEvent, Step, StepPlan, TabInfo
from agent.browser import can_auto_launch
from agent.session import WalkthroughSession, locked_request
from agent.step_executor import RunState, StepExecutor
from agent.tabs import guess_url, match_tab, normalise_url

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def instant_pacing(monkeypatch):
    """Strip the deliberate slowness out of every test.

    In a meeting the dwell and the question windows are the feature; in CI they
    are a minute of dead air per test. Tests that care about them set their own.
    """
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    monkeypatch.setattr("agent.config.QUESTION_BREAK_SECONDS", 0)
    monkeypatch.setattr("agent.config.CLOSING_QUESTION_SECONDS", 0)


class FakeBrowser:
    """Records actions instead of performing them."""

    def __init__(self, delay: float = 0.0) -> None:
        self.performed: list[str] = []
        self.captions: list[str] = []
        self.delay = delay

    async def run_action(self, action: Action) -> str:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.performed.append(f"{action.type.value}:{action.target}")
        return "ok"

    async def screenshot_b64(self, live: bool = False) -> str | None:
        return None

    async def set_caption(self, text: str) -> None:
        self.captions.append(text)

    async def clear_marks(self) -> None:
        self.captions.append("")

    async def current_url(self) -> str:
        return "https://example.com/demo"


def _plan(step_count: int = 3, actions_per_step: int = 2) -> StepPlan:
    return StepPlan(
        workflow_name="test-workflow",
        summary="A test walkthrough.",
        steps=[
            Step(
                id=i,
                title=f"Step {i}",
                goal="goal",
                narration=f"narration {i}",
                actions=[
                    Action(type=ActionType.HIGHLIGHT, target=f"s{i}a{j}", role="button")
                    for j in range(actions_per_step)
                ],
            )
            for i in range(1, step_count + 1)
        ],
    )


def _collector() -> tuple[list[ServerEvent], object]:
    events: list[ServerEvent] = []

    async def emit(event: ServerEvent) -> None:
        events.append(event)

    return events, emit


async def test_runs_every_step_in_order(monkeypatch):
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    events, emit = _collector()
    browser = FakeBrowser()
    executor = StepExecutor(_plan(), browser, emit)

    await executor.run()

    assert executor.state is RunState.DONE
    assert executor.current_index == 3
    assert [e.step_id for e in events if e.type == "step_start"] == [1, 2, 3]
    assert browser.performed == [
        "highlight:s1a0", "highlight:s1a1",
        "highlight:s2a0", "highlight:s2a1",
        "highlight:s3a0", "highlight:s3a1",
    ]


async def test_narration_is_emitted_before_actions(monkeypatch):
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    events, emit = _collector()
    await StepExecutor(_plan(1, 1), FakeBrowser(), emit).run()

    types = [e.type for e in events]
    assert types.index("narration") < types.index("step_done")


async def test_pause_freezes_and_resume_continues_same_step(monkeypatch):
    """The core guarantee: an interruption never rewinds or skips a step."""
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    _, emit = _collector()
    browser = FakeBrowser(delay=0.02)
    executor = StepExecutor(_plan(3, 3), browser, emit)

    task = asyncio.create_task(executor.run())
    await asyncio.sleep(0.05)
    executor.pause()
    await asyncio.sleep(0.05)

    frozen_index = executor.current_index
    frozen_actions = len(browser.performed)
    assert executor.is_paused

    # Nothing may happen while paused.
    await asyncio.sleep(0.1)
    assert len(browser.performed) == frozen_actions
    assert executor.current_index == frozen_index

    executor.resume()
    await task

    assert executor.current_index == 3
    assert len(browser.performed) == 9  # no action replayed, none dropped


async def test_stop_abandons_the_run(monkeypatch):
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    events, emit = _collector()
    browser = FakeBrowser(delay=0.02)
    executor = StepExecutor(_plan(5, 3), browser, emit)

    task = asyncio.create_task(executor.run())
    await asyncio.sleep(0.05)
    executor.stop()
    await task

    assert executor.state is RunState.STOPPED
    assert executor.current_index < 5
    assert not any(e.type == "complete" for e in events)


async def test_replace_plan_keeps_progress(monkeypatch):
    """Re-planning mid-demo must not replay steps the customer already saw."""
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    _, emit = _collector()
    executor = StepExecutor(_plan(4), FakeBrowser(), emit)
    executor.current_index = 2

    executor.replace_plan(_plan(4))
    assert executor.current_index == 2

    # A shorter revised plan clamps rather than running off the end.
    executor.replace_plan(_plan(2))
    assert executor.current_index == 1


async def test_asks_for_questions_after_each_step_and_at_the_end(monkeypatch):
    """The room gets asked, every step, and held longer at the close."""
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    monkeypatch.setattr("agent.config.QUESTION_BREAK_SECONDS", 0.1)
    monkeypatch.setattr("agent.config.CLOSING_QUESTION_SECONDS", 0.2)
    events, emit = _collector()
    browser = FakeBrowser()

    await StepExecutor(_plan(3, 1), browser, emit).run()

    prompts = [e.text for e in events if e.type == "narration" and "?" in e.text]
    # Two mid-demo breaks (after steps 1 and 2, not after the last) plus the
    # closing one — asking "anything else?" and then immediately starting the
    # next step would be worse than not asking.
    assert len(prompts) == 3
    assert "wrap up" in prompts[-1]
    # The prompt is on the page too, for whoever is watching the browser rather
    # than the app.
    assert any("?" in caption for caption in browser.captions)


async def test_a_question_at_the_end_can_extend_the_demo(monkeypatch):
    """"Can you show me X too?" after the last step has to actually show X."""
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    monkeypatch.setattr("agent.config.QUESTION_BREAK_SECONDS", 0)
    # Short, because the extension is followed by a *second* closing window —
    # the agent asks again after showing the thing, which is the right
    # behaviour and would otherwise be dead time in CI.
    monkeypatch.setattr("agent.config.CLOSING_QUESTION_SECONDS", 0.5)
    events, emit = _collector()
    browser = FakeBrowser()
    executor = StepExecutor(_plan(2, 1), browser, emit)

    task = asyncio.create_task(executor.run())
    # Wait until the steps are done and it's holding for closing questions.
    for _ in range(200):
        await asyncio.sleep(0.005)
        if any(e.text == "taking questions" for e in events):
            break

    extended = _plan(3, 1)
    extended.steps[2].actions = [
        Action(type=ActionType.CLICK, target="Share", role="button")
    ]
    executor.replace_plan(extended)
    await task

    assert "click:Share" in browser.performed
    assert any(e.type == "complete" for e in events)


async def test_skip_ends_a_question_break_early(monkeypatch):
    """A quiet room shouldn't cost a full minute of silence."""
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    monkeypatch.setattr("agent.config.QUESTION_BREAK_SECONDS", 0)
    monkeypatch.setattr("agent.config.CLOSING_QUESTION_SECONDS", 30)
    events, emit = _collector()
    executor = StepExecutor(_plan(1, 1), FakeBrowser(), emit)

    task = asyncio.create_task(executor.run())
    for _ in range(100):
        await asyncio.sleep(0.01)
        if any(e.text == "taking questions" for e in events):
            break

    executor.skip()
    await asyncio.wait_for(task, timeout=2)  # not the full 30 seconds
    assert executor.state is RunState.DONE


async def test_replan_mid_step_runs_the_new_step(monkeypatch):
    """"Show me how to filter" has to actually filter.

    The run loop holds the step it is executing in a local, so a plan swapped
    in mid-step used to finish the old step and advance straight past the new
    one — the customer got an answer and watched the demo carry on unchanged,
    which is the single most embarrassing way for this to fail.
    """
    monkeypatch.setattr("agent.config.STEP_DWELL_SECONDS", 0)
    _, emit = _collector()
    browser = FakeBrowser(delay=0.02)
    # Long steps so the pause lands *inside* one — parking between steps would
    # exercise a different (already working) path and hide the bug.
    executor = StepExecutor(_plan(3, 8), browser, emit)

    task = asyncio.create_task(executor.run())
    await asyncio.sleep(0.05)
    executor.pause()
    await asyncio.sleep(0.05)
    assert executor.is_paused
    assert executor.current_index == 0, "test needs to pause mid-step"

    # What the customer asked to be shown, planned into the slot the demo is
    # sitting on — which is what doc_parser.replan produces.
    revised = _plan(3, 1)
    revised.steps[0].actions = [
        Action(type=ActionType.CLICK, target="Filter", role="button")
    ]
    executor.replace_plan(revised)
    executor.resume()
    await task

    assert "click:Filter" in browser.performed
    assert executor.current_index == 3


async def test_sanitiser_drops_navigation_outside_the_chosen_tab():
    """Scope is enforced in code, and it comes from the tab — not a constant."""
    plan = StepPlan(
        workflow_name="w",
        summary="s",
        steps=[
            Step(
                id=1,
                title="t",
                goal="g",
                actions=[
                    Action(type=ActionType.NAVIGATE, target="https://evil.example/x"),
                    Action(type=ActionType.NAVIGATE, target="https://app.acme.com/a"),
                    Action(type=ActionType.NAVIGATE, target="https://acme.com/b"),
                ],
            )
        ],
    )
    cleaned = _sanitise(plan, {"acme.com"})
    targets = [a.target for a in cleaned.steps[0].actions]
    assert targets == ["https://app.acme.com/a", "https://acme.com/b"]


async def test_sanitiser_with_no_scope_allows_nothing():
    """An empty allowlist means no tab was chosen — fail closed, not open."""
    plan = StepPlan(
        workflow_name="w",
        summary="s",
        steps=[
            Step(
                id=1,
                title="t",
                goal="g",
                actions=[Action(type=ActionType.NAVIGATE, target="https://acme.com/")],
            )
        ],
    )
    assert _sanitise(plan, set()).steps[0].actions == []


async def test_fallback_plan_comes_from_the_uploaded_doc():
    """No API key must still yield a demo, not a stack trace — and it must be
    about the document the user actually uploaded."""
    doc = "# Playlists\nSome text.\n\n## Sharing\nMore text.\n"
    plan = _fallback_plan(doc, "https://www.youtube.com/feed", "building a playlist")
    assert [s.title for s in plan.steps] == ["Playlists", "Sharing"]
    assert all(step.actions for step in plan.steps)
    # It narrates; it never invents navigation on a site it can't reason about.
    assert all(
        a.type is not ActionType.NAVIGATE for s in plan.steps for a in s.actions
    )


def _tabs() -> list[TabInfo]:
    return [
        TabInfo(index=0, title="Inbox (12)", url="https://mail.google.com/u/0", host="mail.google.com"),
        TabInfo(index=1, title="chaudharyabhishek146/showRunner", url="https://github.com/chaudharyabhishek146/showRunner", host="github.com"),
        TabInfo(index=2, title="Lo-fi beats - YouTube", url="https://www.youtube.com/watch?v=x", host="www.youtube.com", active=True),
    ]


async def test_tab_matching_picks_the_named_product():
    assert match_tab(_tabs(), "show the demo on YouTube").index == 2
    assert match_tab(_tabs(), "github").index == 1
    assert match_tab(_tabs(), "https://github.com/x").index == 1
    # Title words work too, for products whose name isn't in the host.
    assert match_tab(_tabs(), "showRunner").index == 1


async def test_tab_matching_defaults_to_what_theyre_looking_at():
    assert match_tab(_tabs(), "").index == 2


async def test_tab_matching_refuses_to_guess():
    """A wrong tab in front of a customer is worse than an error message."""
    assert match_tab(_tabs(), "salesforce") is None
    assert match_tab([], "anything") is None


async def test_bare_domains_become_openable_urls():
    assert normalise_url("figma.com") == "https://figma.com"
    assert normalise_url("https://app.figma.com/files") == "https://app.figma.com/files"
    assert normalise_url("the youtube tab") is None
    assert normalise_url("github") is None


async def test_workflow_memory_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.config.WORKFLOWS_PATH", tmp_path / "workflows.json")
    plan = _plan(2)

    assert memory.recall("test-workflow") is None
    memory.remember(plan)

    recalled = memory.recall("test-workflow")
    assert recalled is not None
    assert [s.title for s in recalled.steps] == ["Step 1", "Step 2"]

    memory.remember(plan)
    assert memory.list_workflows()[0]["runs"] == 2
    assert memory.forget("test-workflow") is True
    assert memory.recall("test-workflow") is None


async def test_fill_never_targets_something_you_cannot_type_into():
    """A search step that types into a button is worse than one that errors.

    YouTube's search field is a `combobox`, so a plan saying "textbox" used to
    fall through the role chain onto the *Search button*, click it, type
    nothing, and report success. The demo then searched for nothing.
    """

    class FakePage:
        def __init__(self):
            self.roles: list[str] = []

        def get_by_role(self, role, name=None, exact=None):
            self.roles.append(role)
            return object()

        def get_by_label(self, name, exact=None):
            return object()

        def get_by_placeholder(self, name, exact=None):
            return object()

        def get_by_text(self, name, exact=None):
            return object()

    from agent.browser import BrowserSession

    session = BrowserSession()
    session.page = FakePage()

    session._candidates(
        Action(type=ActionType.FILL, target="Search", role="textbox", value="x"), True
    )
    assert set(session.page.roles) <= set(BrowserSession._EDITABLE_ROLES)
    assert "combobox" in session.page.roles  # what YouTube actually uses

    # Clicks keep the wider chain — a link that looks like a button is fine.
    session.page.roles.clear()
    session._candidates(Action(type=ActionType.CLICK, target="Save", role="button"), True)
    assert "link" in session.page.roles


async def test_locked_demo_ignores_whatever_the_client_sends():
    """On stage the run must be the preset, not whatever a stale tab posted."""
    preset = locked_request()
    assert preset.tab == config.LOCKED_DEMO_TAB
    assert preset.focus == config.LOCKED_DEMO_FOCUS
    assert preset.doc_id == "" and preset.doc == ""
    # And the document it runs from is bundled, not uploaded.
    assert config.read_sample_doc(config.LOCKED_DEMO_SAMPLE).strip()


async def test_signed_out_plans_are_told_not_to_need_an_account():
    """The plan has to know which product it's looking at."""
    events, emit = _collector()
    session = WalkthroughSession(emit)

    session.signed_in = False
    signed_out = session._account_constraint()
    assert "NOT signed in" in signed_out
    assert "never plan a step that signs in" in signed_out

    session.signed_in = True
    assert "IS signed in" in session._account_constraint()


async def test_presenter_prompt_resolves_and_times_out():
    """A dialog nobody clicks must not strand a demo in front of an audience."""
    events, emit = _collector()
    session = WalkthroughSession(emit)

    asking = asyncio.create_task(
        session.ask_presenter("sign_in", "Sign in?", ["Yes", "No"], timeout=5)
    )
    for _ in range(200):
        await asyncio.sleep(0.005)
        if any(e.type == "prompt" for e in events):
            break
    session.reply("sign_in", "Yes")
    assert await asking == "Yes"

    prompt = next(e for e in events if e.type == "prompt")
    assert prompt.payload["options"] == ["Yes", "No"]

    # Unanswered, it gives up rather than hanging.
    assert await session.ask_presenter("x", "?", ["a"], timeout=0.05) == ""
    # A reply to a prompt nobody is waiting on is ignored, not a crash.
    session.reply("gone", "Yes")


async def test_url_guessing_only_covers_product_names():
    """Used only when we launched an empty browser and have nothing to match."""
    assert guess_url("youtube") == "https://youtube.com"
    assert guess_url("github.com") == "https://github.com"
    assert guess_url("https://app.internal.dev/x") == "https://app.internal.dev/x"

    # A description isn't a hostname; better a blank tab than a wrong site.
    assert guess_url("the issue triage flow") is None
    assert guess_url("") is None
    # And a word that only ever describes the instruction is not a product.
    assert guess_url("demo") is None


async def test_auto_launch_refuses_anything_but_this_machine(monkeypatch):
    """A deployed backend must never try to open a browser on the server."""
    monkeypatch.setattr("agent.config.AUTO_LAUNCH_CHROME", True)
    monkeypatch.setattr("agent.config.CHROME_CDP_URL", "http://10.0.0.5:9222")
    allowed, why = can_auto_launch()
    assert not allowed and "this machine" in why

    monkeypatch.setattr("agent.config.CHROME_CDP_URL", "http://localhost:9222")
    monkeypatch.setattr("agent.config.AUTO_LAUNCH_CHROME", False)
    allowed, why = can_auto_launch()
    assert not allowed and "switched off" in why


async def test_uploads_become_plain_text(tmp_path, monkeypatch):
    """The whole demo is grounded in the upload, so reading it has to work.

    Markup and .docx are the two formats a product team actually hands you, and
    both would otherwise reach the planner as angle brackets.
    """
    monkeypatch.setattr("agent.config.UPLOAD_DIR", tmp_path)

    html = b"<html><style>p{color:red}</style><h1>Playlists</h1><p>Add a video.</p>"
    text = docs.extract_text("flow.html", html)
    assert "Playlists" in text and "Add a video." in text
    assert "<" not in text and "color:red" not in text

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            "<w:document><w:p><w:t>Create a playlist</w:t></w:p>"
            "<w:p><w:t>Then share it</w:t></w:p></w:document>",
        )
    docx = docs.extract_text("flow.docx", buffer.getvalue())
    assert "Create a playlist" in docx and "Then share it" in docx

    # A mislabelled file is treated as text rather than failing the demo.
    assert docs.extract_text("flow.weird", b"just words") == "just words"


async def test_documents_survive_a_restart(tmp_path, monkeypatch):
    """Storage is content-addressed and on disk, so a reload mid-call is safe."""
    monkeypatch.setattr("agent.config.UPLOAD_DIR", tmp_path)

    stored = docs.store("flow.md", "# Playlists\n\nAdd a video.")
    assert docs.store("flow.md", "# Playlists\n\nAdd a video.").id == stored.id

    docs._cache.clear()  # what a process restart looks like
    assert docs.get(stored.id) is not None
    assert docs.resolve(stored.id) == stored.text

    # An unknown id falls back rather than demoing against nothing.
    docs._cache.clear()
    assert docs.resolve("nosuchdoc", inline="pasted flow") == "pasted flow"


@pytest.mark.integration
async def test_browser_opens_a_tab_and_scopes_itself(monkeypatch):
    """Smoke test against a real browser; skipped when Playwright isn't installed.

    Attaching is switched off here on purpose — a test must never open tabs in
    the developer's own Chrome.
    """
    playwright = pytest.importorskip("playwright.async_api")
    monkeypatch.setattr("agent.config.ATTACH_TO_CHROME", False)
    monkeypatch.setattr("agent.config.HEADLESS", True)
    from agent.browser import BrowserSession

    session = BrowserSession()
    try:
        await session.start()
    except Exception as exc:  # browser binary missing in this environment
        pytest.skip(f"Browser unavailable: {exc}")

    try:
        await session.open_tab("https://example.com")
        # Scope is derived from the tab, so it is right without configuration…
        assert session.host_allowed("https://example.com/anything")
        # …and everything else is out.
        assert not session.host_allowed("https://evil.example/")

        blocked = await session.run_action(
            Action(type=ActionType.NAVIGATE, target="https://evil.example/")
        )
        assert "outside this demo's scope" in blocked

        outline = await session.page_outline()
        assert outline["url"].startswith("https://example.com")

        shot = await session.screenshot_b64()
        assert shot and len(shot) > 1000
    finally:
        await session.stop()
    del playwright
