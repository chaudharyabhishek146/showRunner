"""One live walkthrough: browser + tab + plan + executor + interruptions.

The ordering here is the design. The browser is attached and the tab is chosen
*before* anything is planned, because the plan is written against the page that
is actually open — its real controls, its real URL, its real scope. Planning
first and hoping the page matches is how demo agents end up clicking at
coordinates that moved last sprint.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from . import config, doc_parser, docs, memory, narrator
from .browser import (
    BrowserSession,
    NoBrowserAvailable,
    TabNotFound,
    can_auto_launch,
    chrome_port_open,
)
from .models import DemoRequest, ServerEvent, StepPlan, TabInfo
from .step_executor import RunState, StepExecutor
from .tabs import guess_url

log = logging.getLogger(__name__)

Emit = Callable[[ServerEvent], Awaitable[None]]


def locked_request() -> DemoRequest:
    """The one demo this build runs when DEMO_LOCKED is on."""
    return DemoRequest(
        focus=config.LOCKED_DEMO_FOCUS,
        tab=config.LOCKED_DEMO_TAB,
    )


class WalkthroughSession:
    """Coordinates planning, browsing, and questions for a single viewer."""

    def __init__(self, emit: Emit) -> None:
        self.emit = emit
        self.browser = BrowserSession()
        self.doc = ""
        self.focus = ""
        self.tab: TabInfo | None = None
        self.plan: StepPlan | None = None
        self.executor: StepExecutor | None = None
        self._run_task: asyncio.Task | None = None
        # Serialises interruptions so two rapid-fire questions can't both
        # pause, answer, and resume out of order.
        self._interrupt_lock = asyncio.Lock()
        # Outstanding prompt-for-the-presenter, resolved by a "reply" event.
        self._pending: dict[str, asyncio.Future[str]] = {}
        # Set while start() is mid-flight: it now waits on presenter input, so
        # "is a demo already going?" can't be answered by _run_task alone.
        self._starting = False
        # Whether the demo is running against a signed-in account. Drives the
        # plan, because signed-out YouTube is a different product.
        self.signed_in = False

    # ------------------------------------------------------------------ prompts

    async def ask_presenter(
        self, prompt_id: str, question: str, options: list[str], timeout: float
    ) -> str:
        """Put a question with buttons to the presenter and wait for the answer.

        Times out rather than blocking forever: an unanswered dialog must not
        be able to strand a demo in front of an audience.
        """
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[prompt_id] = future
        await self.emit(
            ServerEvent(
                type="prompt",
                text=question,
                payload={"id": prompt_id, "options": options, "timeout": timeout},
            )
        )
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            log.info("Prompt %r timed out after %ss", prompt_id, timeout)
            return ""
        finally:
            self._pending.pop(prompt_id, None)

    def reply(self, prompt_id: str, answer: str) -> None:
        """Deliver a presenter's button click to whoever is waiting on it."""
        future = self._pending.get(prompt_id)
        if future is not None and not future.done():
            future.set_result(answer)

    # --------------------------------------------------------------------- tabs

    async def ensure_browser(self, tab_hint: str = "", auto_launch: bool = False) -> str:
        """Attach to the user's Chrome if we haven't already.

        `auto_launch` is only ever true on the path that starts a demo. When it
        fires we hand Chrome the URL the presenter named, so a freshly launched
        browser opens on the product instead of a blank page they then have to
        navigate themselves.
        """
        if self.browser.page is not None or self.browser.attached:
            return "Already connected."

        opening = guess_url(tab_hint) if auto_launch else None
        # Only promise a launch we can actually perform — on a deployed backend
        # there is no Chrome to start, and saying otherwise sends the presenter
        # looking for a window that will never appear.
        if auto_launch and can_auto_launch()[0] and not await chrome_port_open():
            await self.emit(
                ServerEvent(
                    type="status",
                    text=(
                        f"Starting Chrome and opening {opening}…"
                        if opening
                        else "Starting Chrome for the demo…"
                    ),
                )
            )
        note = await self.browser.start(auto_launch=auto_launch, url=opening or "")
        await self.emit(ServerEvent(type="status", text=note))
        return note

    async def send_tabs(self) -> list[TabInfo]:
        """Push the current tab list so the UI can offer a target picker."""
        await self.ensure_browser()
        tabs = await self.browser.list_tabs()
        await self.emit(
            ServerEvent(
                type="tabs",
                text=f"{len(tabs)} tabs open",
                payload={"tabs": [t.model_dump(mode="json") for t in tabs]},
            )
        )
        return tabs

    # ----------------------------------------------------------------- planning

    async def prepare(self, request: DemoRequest) -> StepPlan:
        """Produce the plan, from memory when possible, from Claude otherwise."""
        remembered = memory.recall(request.workflow) if request.workflow else None
        if remembered is not None:
            await self.emit(
                ServerEvent(
                    type="status",
                    text=f"Recalled '{request.workflow}' from workflow memory — skipping planning.",
                )
            )
            self.plan = remembered
        else:
            await self.emit(
                ServerEvent(type="status", text="Reading the page and the document…")
            )
            outline = await self.browser.page_outline()
            plan = await doc_parser.parse_document(
                doc=self.doc,
                focus=self.focus,
                outline=outline,
                allowed_hosts=self.browser.allowed_hosts,
                constraint=self._account_constraint(),
            )
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

    async def start(self, request: DemoRequest) -> None:
        """Attach, pick the tab, plan against it, then execute in the background.

        Must be awaited off the WebSocket receive loop: this now blocks on the
        presenter answering the sign-in prompt, and that answer arrives *on*
        the socket. Run it inline and the two deadlock until the keepalive
        gives up — which is exactly how this was found.
        """
        if self._starting or (self._run_task is not None and not self._run_task.done()):
            await self.emit(
                ServerEvent(type="status", text="A walkthrough is already running.")
            )
            return
        self._starting = True
        try:
            await self._start(request)
        finally:
            self._starting = False

    async def _start(self, request: DemoRequest) -> None:

        if config.DEMO_LOCKED:
            # Hackathon mode: the run is the preset, whatever the client sent.
            request = locked_request()
            self.doc = config.read_sample_doc(config.LOCKED_DEMO_SAMPLE)
        else:
            self.doc = docs.resolve(request.doc_id, request.doc)
        self.focus = request.focus
        if not self.doc.strip():
            await self.emit(
                ServerEvent(
                    type="error",
                    text="No product document yet — upload one and I'll plan from it.",
                )
            )
            return

        # The only place auto-launch is allowed: the presenter just asked for a
        # demo, so opening a browser window is what they expect to happen.
        try:
            await self.ensure_browser(tab_hint=request.tab, auto_launch=True)
        except NoBrowserAvailable as exc:
            await self.emit(ServerEvent(type="error", text=str(exc)))
            return

        await self.emit(
            ServerEvent(
                type="status",
                text=f"Finding the tab for {request.tab or 'this demo'}…",
            )
        )
        try:
            self.tab = await self.browser.select_tab(request.tab)
        except TabNotFound as exc:
            await self.emit(ServerEvent(type="error", text=str(exc)))
            await self.send_tabs()
            return

        await self.emit(
            ServerEvent(
                type="status",
                text=f"Demoing in: {self.tab.title or self.tab.url}",
                payload={
                    "tab": self.tab.model_dump(mode="json"),
                    "scope": sorted(self.browser.allowed_hosts),
                },
            )
        )

        # Before anything is planned: signed-in and signed-out are different
        # products, and a plan written for one is wrong for the other.
        await self._offer_sign_in()

        plan = await self.prepare(request)
        self.executor = StepExecutor(plan, self.browser, self.emit)
        self._run_task = asyncio.create_task(self._run_guarded())

    # -------------------------------------------------------------- signing in

    async def _offer_sign_in(self) -> None:
        """Ask whether to wait for a sign-in, and hold the demo while they do.

        The agent never touches the credentials — it opens the page, waits, and
        checks the result. Typing someone's password is not something this tool
        does, and holding the demo for thirty seconds costs nothing next to
        demoing the signed-out shell of a product by accident.
        """
        if not config.ASK_TO_SIGN_IN:
            return

        already = await self._is_signed_in()
        if already:
            self.signed_in = True
            await self.emit(
                ServerEvent(type="status", text="You're already signed in — good to go.")
            )
            return

        answer = await self.ask_presenter(
            "sign_in",
            "You're not signed in. Do you want to sign in first, so I can show "
            "the logged-in features?",
            ["Yes, I'll sign in", "No, continue signed out"],
            timeout=config.SIGN_IN_PROMPT_TIMEOUT,
        )

        if not answer.lower().startswith("yes"):
            await self.emit(
                ServerEvent(
                    type="status",
                    text=(
                        "Continuing signed out — I'll show what a visitor sees, "
                        "and I'll skip the parts that need an account."
                    ),
                )
            )
            return

        await self.ask_presenter(
            "signed_in_yet",
            "Go ahead and sign in in the Chrome window I opened. Click below "
            "when you're done and I'll plan the demo around your account.",
            ["I'm signed in"],
            timeout=config.SIGN_IN_PROMPT_TIMEOUT,
        )

        self.signed_in = await self._is_signed_in()
        await self.emit(
            ServerEvent(
                type="status",
                text=(
                    "Signed in — I'll include the account features."
                    if self.signed_in
                    # Checked rather than assumed: planning a demo of Watch
                    # Later for a signed-out browser fails in front of the room.
                    else "Still looks signed out from here, so I'll stick to "
                    "what a visitor can see."
                ),
            )
        )

    def _account_constraint(self) -> str:
        """What the planner needs to know about the account, in one line."""
        if self.signed_in:
            return (
                "The browser IS signed in, so account features (saved lists, "
                "subscriptions, history) are available and worth showing."
            )
        return (
            "The browser is NOT signed in. Plan only what a signed-out visitor "
            "can actually do: do not plan steps that save, subscribe, or open "
            "a personal list, and never plan a step that signs in. Where the "
            "flow would need an account, point at where the feature lives and "
            "say plainly that it needs one."
        )

    async def _is_signed_in(self) -> bool:
        """Best-effort read of whether the page thinks we have an account.

        A visible "Sign in" control is the signal every consumer product gives
        for this, and it costs one outline read we were about to do anyway.
        """
        try:
            outline = await self.browser.page_outline()
        except Exception:  # pragma: no cover - page mid-navigation
            return False
        names = {e.get("name", "").strip().lower() for e in outline.get("elements", [])}
        return not names & {"sign in", "log in", "login", "sign-in"}

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
            # Same asymmetry as the manual pause control: "pausing" is a request,
            # and the executor emits "paused" once the browser has truly stopped.
            await self.emit(ServerEvent(type="status", text="pausing"))

            await self.browser.set_caption(f"❓ {question}")
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
            await self.browser.set_caption(reply.answer)

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
        # Re-read the page: the demo has moved since the original plan, and the
        # new steps have to start from where it actually is.
        outline = await self.browser.page_outline()
        revised = await doc_parser.replan(
            plan=self.plan,
            doc=self.doc,
            focus=focus,
            completed_index=self.executor.current_index,
            outline=outline,
            allowed_hosts=self.browser.allowed_hosts,
        )
        if revised is None:
            # The answer just promised a demonstration. Saying so out loud beats
            # a status line nobody reads while the browser quietly does nothing.
            await self.emit(
                ServerEvent(
                    type="answer",
                    step_id=self.executor.current_index + 1,
                    text=(
                        f"I can't work {focus} into this flow from where we are — "
                        "let me finish this thread and come back to it."
                    ),
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
        """Stop execution and let go of the browser."""
        if self.executor:
            self.executor.stop()
        if self._run_task is not None:
            self._run_task.cancel()
            try:
                await self._run_task
            except (asyncio.CancelledError, Exception):
                pass
            self._run_task = None
        await self.browser.clear_marks()
        await self.browser.stop()
