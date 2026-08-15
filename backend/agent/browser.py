"""Playwright wrapper — the agent's hands.

Every lookup goes through `get_by_role` with an accessible name. GitHub rewrites
its CSS classes constantly but its ARIA roles are stable, so semantic selectors
are the difference between a demo that survives a deploy and one that doesn't.
"""

from __future__ import annotations

import asyncio
import base64
import logging

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from . import config
from .models import Action, ActionType

log = logging.getLogger(__name__)

ACTION_TIMEOUT_MS = 8000
HIGHLIGHT_JS = """
(el) => {
  el.style.outline = '3px solid #ff5c00';
  el.style.outlineOffset = '3px';
  el.style.transition = 'outline 160ms ease-in';
  el.scrollIntoView({ block: 'center', behavior: 'smooth' });
}
"""


class BrowserSession:
    """Owns one Chromium instance for the lifetime of a walkthrough."""

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

    # ---------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        """Launch Chromium and open the first tab."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=config.HEADLESS,
            slow_mo=config.SLOW_MO_MS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={
                "width": config.VIEWPORT_WIDTH,
                "height": config.VIEWPORT_HEIGHT,
            },
            device_scale_factor=1,
        )
        await self._inject_session_cookie()
        self.page = await self._context.new_page()
        self.page.set_default_timeout(ACTION_TIMEOUT_MS)
        log.info("Browser session started (headless=%s)", config.HEADLESS)

    async def _inject_session_cookie(self) -> None:
        """Authenticate by reusing an existing session cookie, if one is provided.

        The agent never types credentials into a login form. Auth is supplied
        out-of-band through the environment or the demo runs signed out.
        """
        if not config.GITHUB_SESSION_COOKIE or self._context is None:
            return
        await self._context.add_cookies(
            [
                {
                    "name": "user_session",
                    "value": config.GITHUB_SESSION_COOKIE,
                    "domain": ".github.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ]
        )
        log.info("Injected GitHub session cookie from environment")

    async def stop(self) -> None:
        """Tear everything down; safe to call twice."""
        for closer in (self._context, self._browser):
            try:
                if closer is not None:
                    await closer.close()
            except PlaywrightError:  # pragma: no cover - best-effort teardown
                pass
        if self._pw is not None:
            await self._pw.stop()
        self._pw = self._browser = self._context = self.page = None
        log.info("Browser session stopped")

    # ------------------------------------------------------------------ actions

    async def run_action(self, action: Action) -> str:
        """Execute one action. Returns a short human-readable trace line.

        Failures are reported, never raised: a missing button should degrade the
        demo by one beat, not end it.
        """
        if self.page is None:
            raise RuntimeError("Browser session has not been started")

        try:
            if action.type is ActionType.NAVIGATE:
                await self.page.goto(action.target, wait_until="domcontentloaded")
                return f"navigated to {action.target}"

            if action.type is ActionType.WAIT:
                await asyncio.sleep(_as_seconds(action.value))
                return f"waited {action.value}s"

            if action.type is ActionType.PRESS:
                await self.page.keyboard.press(action.value or "Enter")
                return f"pressed {action.value}"

            locator = self._locate(action)

            if action.type is ActionType.CLICK:
                await locator.click()
                await self.page.wait_for_load_state("networkidle", timeout=5000)
                return f"clicked {action.target!r}"

            if action.type is ActionType.FILL:
                await locator.click()
                await locator.fill(action.value)
                return f"typed into {action.target!r}"

            if action.type is ActionType.HIGHLIGHT:
                await locator.evaluate(HIGHLIGHT_JS)
                return f"highlighted {action.target!r}"

        except (PlaywrightTimeout, PlaywrightError) as exc:
            first_line = str(exc).splitlines()[0]
            log.warning("Action %s failed: %s", action.type.value, first_line)
            return f"could not {action.type.value} {action.target!r} — continuing"

        return f"skipped unknown action {action.type}"

    def _locate(self, action: Action):
        """Resolve an accessible name to a locator, preferring role lookup."""
        assert self.page is not None
        if action.role:
            return self.page.get_by_role(
                action.role, name=action.target, exact=False
            ).first
        # No role given: fall back through the other semantic strategies.
        return self.page.get_by_label(action.target).or_(
            self.page.get_by_placeholder(action.target)
        ).or_(self.page.get_by_text(action.target, exact=False)).first

    # -------------------------------------------------------------- observation

    async def screenshot_b64(self) -> str | None:
        """Capture the viewport as base64 PNG for WebSocket transport."""
        if self.page is None:
            return None
        try:
            raw = await self.page.screenshot(type="png", full_page=False)
        except PlaywrightError as exc:  # page may be mid-navigation
            log.debug("Screenshot skipped: %s", exc)
            return None
        return base64.b64encode(raw).decode("ascii")

    async def current_url(self) -> str:
        return self.page.url if self.page else ""


def _as_seconds(value: str) -> float:
    """Parse a wait duration, clamped so a bad plan can't stall the demo."""
    try:
        return max(0.0, min(float(value or 1), 10.0))
    except ValueError:
        return 1.0
