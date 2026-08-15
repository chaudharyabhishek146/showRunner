"""The execution loop — and the interruption handling that makes this a demo
rather than a screen recording.

Pause/resume is an `asyncio.Event`, not a boolean flag. A flag forces the loop
to poll, which either burns CPU or adds latency to every resume; the Event lets
the coroutine park at `await self._resume.wait()` and wake the instant a
question is answered. The gate is checked between *actions*, not just between
steps, so a customer interrupting mid-step freezes the browser where it stands.

`current_index` is only advanced after a step fully completes. Resuming
therefore continues the same step — it never rewinds and never skips.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import Enum

from . import config
from .browser import BrowserSession
from .models import ServerEvent, StepPlan

log = logging.getLogger(__name__)

Emit = Callable[[ServerEvent], Awaitable[None]]


class RunState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    STOPPED = "stopped"


class StepExecutor:
    """Drives a StepPlan through a BrowserSession, streaming events outward."""

    def __init__(self, plan: StepPlan, browser: BrowserSession, emit: Emit) -> None:
        self.plan = plan
        self.browser = browser
        self.emit = emit

        self.current_index = 0
        self.state = RunState.IDLE

        # Set == free to run. Cleared == parked at the gate.
        self._gate = asyncio.Event()
        self._gate.set()
        self._stop = False
        self._skip_requested = False

    # ------------------------------------------------------------------ control

    def pause(self) -> None:
        """Freeze before the next action. Idempotent."""
        if self.state is RunState.RUNNING:
            self.state = RunState.PAUSED
        self._gate.clear()
        log.info("Paused at step %d", self.current_index + 1)

    def resume(self) -> None:
        """Release the gate; execution continues from the exact same action."""
        if self.state is RunState.PAUSED:
            self.state = RunState.RUNNING
        self._gate.set()
        log.info("Resumed at step %d", self.current_index + 1)

    def stop(self) -> None:
        """Abandon the run. Releases the gate so the loop can observe the flag."""
        self._stop = True
        self._gate.set()

    def skip(self) -> None:
        """Jump to the next step without executing the rest of the current one."""
        self._skip_requested = True
        self._gate.set()

    def replace_plan(self, plan: StepPlan) -> None:
        """Swap in a re-planned walkthrough mid-run.

        Used when a customer says "actually, show me labels instead". Steps
        already completed stay completed; the pointer is clamped into the new
        plan rather than reset, so we don't replay what they've already seen.
        """
        self.plan = plan
        self.current_index = min(self.current_index, max(0, len(plan.steps) - 1))
        log.info("Plan replaced — continuing at step %d", self.current_index + 1)

    @property
    def is_paused(self) -> bool:
        return not self._gate.is_set()

    # --------------------------------------------------------------------- loop

    async def _checkpoint(self) -> bool:
        """Park at the gate. Returns False when the run should abandon."""
        if not self._gate.is_set():
            await self.emit(ServerEvent(type="status", text="paused"))
            await self._gate.wait()
            if not self._stop:
                await self.emit(ServerEvent(type="status", text="running"))
        return not self._stop

    async def run(self) -> None:
        """Execute every remaining step, streaming narration and screenshots."""
        self.state = RunState.RUNNING
        self._skip_requested = False
        await self.emit(
            ServerEvent(type="status", text="running", payload={"total": len(self.plan.steps)})
        )

        while self.current_index < len(self.plan.steps):
            if not await self._checkpoint():
                break

            step = self.plan.steps[self.current_index]
            self._skip_requested = False

            await self.emit(
                ServerEvent(
                    type="step_start",
                    step_id=step.id,
                    text=step.title,
                    payload={
                        "index": self.current_index,
                        "total": len(self.plan.steps),
                        "goal": step.goal,
                        "doc_reference": step.doc_reference,
                    },
                )
            )
            # Narration was pre-generated at plan time, so it lands instantly.
            await self.emit(
                ServerEvent(type="narration", step_id=step.id, text=step.narration)
            )

            for action in step.actions:
                if not await self._checkpoint():
                    break
                if self._skip_requested:
                    log.info("Skipping remainder of step %d", step.id)
                    break

                trace = await self.browser.run_action(action)
                log.debug("step %d: %s", step.id, trace)
                await self._push_screenshot(step.id, trace)

            if self._stop:
                break

            await self.emit(ServerEvent(type="step_done", step_id=step.id))
            # Advance only after the step is genuinely finished — this is what
            # makes resume-after-question land on the right step.
            self.current_index += 1
            await asyncio.sleep(config.STEP_DWELL_SECONDS)

        if self._stop:
            self.state = RunState.STOPPED
            await self.emit(ServerEvent(type="status", text="stopped"))
            return

        self.state = RunState.DONE
        await self.emit(
            ServerEvent(
                type="complete",
                text=self.plan.summary,
                payload={"steps_completed": self.current_index},
            )
        )

    async def _push_screenshot(self, step_id: int, caption: str) -> None:
        """Send the current viewport to the client."""
        image = await self.browser.screenshot_b64()
        if image is None:
            return
        await self.emit(
            ServerEvent(
                type="screenshot",
                step_id=step_id,
                text=caption,
                image=image,
                payload={"url": await self.browser.current_url()},
            )
        )
