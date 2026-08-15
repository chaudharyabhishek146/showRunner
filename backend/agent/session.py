"""One live walkthrough: browser + plan + executor + interruption handling.

The WebSocket layer stays thin because everything stateful lives here.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from . import config, doc_parser, memory, narrator
from .browser import BrowserSession
from .models import ServerEvent, StepPlan
from .step_executor import RunState, StepExecutor

log = logging.getLogger(__name__)

Emit = Callable[[ServerEvent], Awaitable[None]]


class WalkthroughSession:
    """Coordinates planning, browsing, and questions for a single viewer."""

    def __init__(self, emit: Emit) -> None:
        self.emit = emit
        self.doc = config.read_product_doc()
        self.browser = BrowserSession()
        self.plan: StepPlan | None = None
        self.executor: StepExecutor | None = None
        self._run_task: asyncio.Task | None = None
        # Serialises interruptions so two rapid-fire questions can't both
        # pause, answer, and resume out of order.
        self._interrupt_lock = asyncio.Lock()

    # ----------------------------------------------------------------- planning

    async def prepare(self, workflow: str = "") -> StepPlan:
        """Produce the plan, from memory when possible, from Claude otherwise."""
        remembered = memory.recall(workflow) if workflow else None
        if remembered is not None:
            await self.emit(
                ServerEvent(
                    type="status",
                    text=f"Recalled '{workflow}' from workflow memory — skipping planning.",
                )
            )
            self.plan = remembered
        else:
            await self.emit(
                ServerEvent(type="status", text="Reading the product doc…")
            )
            plan = await doc_parser.parse_document(self.doc)
            await self.emit(
                ServerEvent(type="status", text="Writing the narration…")
            )
            self.plan = await narrator.write_narration(plan, self.doc)
            memory.remember(self.plan)

        await self.emit(
            ServerEvent(
                type="plan",
                text=self.plan.summary,
                payload=self.plan.model_dump(mode="json"),
            )
        )
        return self.plan

    # ---------------------------------------------------------------- execution

    async def start(self, workflow: str = "") -> None:
        """Plan, launch the browser, and begin executing in the background."""
        if self._run_task is not None and not self._run_task.done():
            await self.emit(
                ServerEvent(type="status", text="A walkthrough is already running.")
            )
            return

        plan = await self.prepare(workflow)
        await self.emit(ServerEvent(type="status", text="Launching the browser…"))
        await self.browser.start()

        self.executor = StepExecutor(plan, self.browser, self.emit)
        self._run_task = asyncio.create_task(self._run_guarded())

    async def _run_guarded(self) -> None:
        """Run the executor, surfacing any crash to the client instead of the log."""
        assert self.executor is not None
        try:
            await self.executor.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a broken demo should still explain itself
            log.exception("Walkthrough failed")
            await self.emit(
                ServerEvent(type="error", text=f"Walkthrough stopped: {exc}")
            )

    # ------------------------------------------------------------- interruption

    async def ask(self, question: str) -> None:
        """Freeze the demo, answer with the current screen in view, then resume.

        This is the whole point of the agent: the browser holds its position at
        `current_index` for as long as the answer takes, and resumes into the
        same step rather than restarting it.
        """
        if self.executor is None or self.plan is None:
            await self.emit(
                ServerEvent(
                    type="answer",
                    text="The walkthrough hasn't started yet — hit Start and ask again.",
                )
            )
            return

        async with self._interrupt_lock:
            was_running = self.executor.state is RunState.RUNNING
            if was_running:
                self.executor.pause()
            await self.emit(
                ServerEvent(type="status", text="Paused — thinking about that…")
            )

            shot = await self.browser.screenshot_b64()
            reply = await narrator.answer_question(
                question=question,
                doc=self.doc,
                plan=self.plan,
                step_index=self.executor.current_index,
                screenshot_b64=shot,
            )
            await self.emit(
                ServerEvent(
                    type="answer",
                    step_id=self.executor.current_index + 1,
                    text=reply.answer,
                )
            )

            if reply.wants_plan_change and reply.requested_focus:
                await self._apply_plan_change(reply.requested_focus)

            if was_running:
                self.executor.resume()

    async def _apply_plan_change(self, focus: str) -> None:
        """Rewrite the remaining steps around what the customer asked to see."""
        assert self.executor is not None and self.plan is not None
        await self.emit(
            ServerEvent(type="status", text=f"Re-planning around: {focus}")
        )
        revised = await doc_parser.replan(
            self.plan, self.doc, focus, self.executor.current_index
        )
        if revised is None:
            await self.emit(
                ServerEvent(
                    type="status",
                    text="Couldn't re-plan cleanly — continuing with the original flow.",
                )
            )
            return

        revised = await narrator.write_narration(revised, self.doc)
        self.plan = revised
        self.executor.replace_plan(revised)
        await self.emit(
            ServerEvent(
                type="plan", text=revised.summary, payload=revised.model_dump(mode="json")
            )
        )

    # --------------------------------------------------------------- lifecycle

    def pause(self) -> None:
        if self.executor:
            self.executor.pause()

    def resume(self) -> None:
        if self.executor:
            self.executor.resume()

    def skip(self) -> None:
        if self.executor:
            self.executor.skip()

    async def stop(self) -> None:
        """Stop execution and release the browser."""
        if self.executor:
            self.executor.stop()
        if self._run_task is not None:
            self._run_task.cancel()
            try:
                await self._run_task
            except (asyncio.CancelledError, Exception):
                pass
            self._run_task = None
        await self.browser.stop()
