"""Tests for the parts that make or break a live demo.

The CI stage gates the deploy on these, so they are deliberately fast and
hermetic: no network, no Claude calls, and a fake browser. The one test that
needs real Chromium is marked `integration` and skipped when it isn't installed.
"""

from __future__ import annotations

import asyncio

import pytest

from agent import memory
from agent.doc_parser import _fallback_plan, _sanitise
from agent.models import Action, ActionType, ServerEvent, Step, StepPlan
from agent.step_executor import RunState, StepExecutor

pytestmark = pytest.mark.asyncio


class FakeBrowser:
    """Records actions instead of performing them."""

    def __init__(self, delay: float = 0.0) -> None:
        self.performed: list[str] = []
        self.delay = delay

    async def run_action(self, action: Action) -> str:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.performed.append(f"{action.type.value}:{action.target}")
        return "ok"

    async def screenshot_b64(self) -> str | None:
        return None

    async def current_url(self) -> str:
        return "https://github.com/demo/repo"


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


async def test_sanitiser_drops_off_domain_navigation():
    """The domain allowlist is enforced in code, not left to the model."""
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
                    Action(type=ActionType.NAVIGATE, target="https://github.com/a/b"),
                ],
            )
        ],
    )
    cleaned = _sanitise(plan)
    targets = [a.target for a in cleaned.steps[0].actions]
    assert targets == ["https://github.com/a/b"]


async def test_fallback_plan_is_executable():
    """No API key must still yield a demo, not a stack trace."""
    plan = _fallback_plan("flytbase/demo")
    assert len(plan.steps) == 5
    assert all(step.actions for step in plan.steps)
    assert _sanitise(plan).steps[0].actions[0].target.startswith("https://github.com/")


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


@pytest.mark.integration
async def test_browser_can_screenshot():
    """Smoke test against real Chromium; skipped when Playwright isn't installed."""
    playwright = pytest.importorskip("playwright.async_api")
    from agent.browser import BrowserSession

    session = BrowserSession()
    try:
        await session.start()
    except Exception as exc:  # browser binary missing in this environment
        pytest.skip(f"Chromium unavailable: {exc}")

    try:
        await session.run_action(
            Action(type=ActionType.NAVIGATE, target="https://github.com")
        )
        shot = await session.screenshot_b64()
        assert shot and len(shot) > 1000
    finally:
        await session.stop()
    del playwright
