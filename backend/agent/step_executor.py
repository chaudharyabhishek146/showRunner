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
import time
from collections.abc import Awaitable, Callable
from enum import Enum

from . import config
from .browser import BrowserSession
from .models import ServerEvent, StepPlan

log = logging.getLogger(__name__)

Emit = Callable[[ServerEvent], Awaitable[None]]

# Cycled rather than repeated: the same sentence after every step is how a
# presenter starts sounding like a recording.
_STEP_PROMPTS = (
    "Any questions on that before I move on?",
    "Anything there you'd like me to go over again?",
    "Questions on this one?",
    "Anything you want a closer look at?",
)


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
        # Set by replace_plan; makes the loop re-read the step it is on.
        self._plan_replaced = False

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
        # The run loop is holding the *old* step object and iterating its
        # actions. Without this flag it would finish that step and advance past
        # the new one — so the customer who just asked "show me how to filter"
        # would watch the demo carry on as if they had said nothing.
        self._plan_replaced = True
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

    async def _stream_frames(self) -> None:
        """Push the viewport continuously so the panel reads as a live browser.

        Deliberately independent of the step loop: it keeps running through
        page loads, scrolls, and — importantly — through a Q&A pause, so the
        audience sees the frozen page rather than a panel that stops updating.
        """
        interval = 1.0 / max(config.LIVE_FPS, 0.5)
        while True:
            try:
                image = await self.browser.screenshot_b64(live=True)
                if image:
                    await self.emit(ServerEvent(type="frame", image=image))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # a dropped frame must never kill the demo
                log.debug("Frame skipped: %s", exc)
            await asyncio.sleep(interval)

    async def run(self) -> None:
        """Execute every remaining step, streaming narration and screenshots."""
        self.state = RunState.RUNNING
        self._skip_requested = False
        await self.emit(
            ServerEvent(type="status", text="running", payload={"total": len(self.plan.steps)})
        )
        frame_task = asyncio.create_task(self._stream_frames())
        try:
            await self._run_steps()
        finally:
            frame_task.cancel()

    async def _run_steps(self) -> None:
        """Run the plan, then hold the floor for closing questions.

        The outer loop exists because a question asked at the end can add steps:
        "can you show me the sharing flow too?" re-plans, and the demo carries
        on rather than ending on an answer nobody got to see performed.
        """
        while True:
            await self._steps_loop()
            if self._stop:
                break

            await self._question_break(
                config.CLOSING_QUESTION_SECONDS,
                "That's the walkthrough. Any questions before we wrap up?",
                step_id=None,
            )
            if self._stop:
                break
            if self._plan_replaced and self.current_index < len(self.plan.steps):
                continue
            break

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

    async def _question_break(
        self, seconds: float, prompt: str, step_id: int | None
    ) -> None:
        """Stop talking and let the room ask something.

        A demo that runs start to finish without pausing is a screen recording.
        The window resets every time someone actually asks — one question almost
        always has a follow-up, and cutting that off is worse than being slow.
        Skip ends the wait early, for when the room is quiet and you can tell.
        """
        if seconds <= 0:
            return

        await self.emit(ServerEvent(type="narration", step_id=step_id, text=prompt))
        await self.browser.set_caption(prompt)

        async def announce() -> None:
            # The payload drives the countdown in the UI, so the presenter can
            # see how long the silence is going to last and cut it short.
            await self.emit(
                ServerEvent(
                    type="status",
                    text="taking questions",
                    payload={"seconds": seconds},
                )
            )

        await announce()
        self._skip_requested = False
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop:
                return
            if self._skip_requested:  # "carry on" — someone moved us along
                self._skip_requested = False
                return
            if self._plan_replaced:
                # They didn't just ask, they redirected. Stop waiting and go
                # show them the thing.
                return
            if not self._gate.is_set():
                # A question landed and is being answered. Wait that out, then
                # give the room the full window again for the follow-up.
                await self._gate.wait()
                if self._stop:
                    return
                deadline = time.monotonic() + seconds
                await announce()  # the UI was showing "paused"; we're listening again
            await asyncio.sleep(0.2)

    async def _steps_loop(self) -> None:
        while self.current_index < len(self.plan.steps):
            if not await self._checkpoint():
                break

            step = self.plan.steps[self.current_index]
            self._skip_requested = False
            self._plan_replaced = False

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
            # Also burn it into the page, so the browser view explains itself
            # when it is the only thing on the screen share.
            await self.browser.set_caption(step.narration)

            for action in step.actions:
                if not await self._checkpoint():
                    break
                # Checked after the gate: a question answered mid-step is
                # exactly when this becomes true.
                if self._plan_replaced:
                    break
                if self._skip_requested:
                    log.info("Skipping remainder of step %d", step.id)
                    break

                trace = await self.browser.run_action(action)
                log.debug("step %d: %s", step.id, trace)
                await self._push_screenshot(step.id, trace)

            if self._stop:
                break

            if self._plan_replaced:
                # Re-enter without advancing, so the step now sitting at this
                # index — the one the customer just asked for — actually runs.
                log.info(
                    "Plan changed mid-step; running the revised step %d",
                    self.current_index + 1,
                )
                continue

            await self.emit(ServerEvent(type="step_done", step_id=step.id))
            # Advance only after the step is genuinely finished — this is what
            # makes resume-after-question land on the right step.
            self.current_index += 1
            await asyncio.sleep(config.STEP_DWELL_SECONDS)

            # Ask before moving on, not at the end. A question about step 2 is
            # worth far more while step 2 is still on screen.
            if self.current_index < len(self.plan.steps):
                await self._question_break(
                    config.QUESTION_BREAK_SECONDS,
                    _STEP_PROMPTS[(self.current_index - 1) % len(_STEP_PROMPTS)],
                    step_id=step.id,
                )
                if self._plan_replaced:
                    # They redirected during the break; the loop re-reads the
                    # plan on the next pass, which now holds what they asked for.
                    continue

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
