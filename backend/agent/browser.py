"""Playwright wrapper — the agent's hands.

By default this does not launch a browser. It *attaches* to the Chrome the user
already has open, over the DevTools protocol, and drives one of their existing
tabs. That choice does most of the work in this project:

  - the demo runs against whatever product they're actually signed into, so
    nothing here needs a site name, a repo, or a session cookie;
  - the agent never sees or types a credential, because the session already
    exists in the profile it attached to;
  - the audience watches the presenter's own browser move, not a sterile
    automation window that looks nothing like the product.

Every element lookup goes through role + accessible name. Products rewrite
their CSS constantly; what a control *is* and what it's *called* are what
survive a deploy.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

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
from .models import Action, ActionType, TabInfo
from .overlay import OVERLAY_EVAL_JS, OVERLAY_INIT_JS
from .tabs import describe, match_tab, normalise_url

log = logging.getLogger(__name__)

ACTION_TIMEOUT_MS = 8000
CDP_CONNECT_TIMEOUT_MS = 4000
# A cold profile on a slow disk is the worst case; anything past this and the
# presenter deserves an error rather than a spinner.
CHROME_LAUNCH_TIMEOUT_S = 20


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

# Where Chrome actually is, per platform. Checked in order; the first that
# exists wins. CHROME_BINARY overrides the lot.
_CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
)
_CHROME_COMMANDS = ("google-chrome", "google-chrome-stable", "chromium", "chrome")


def chrome_binary() -> str:
    """The Chrome executable on this machine, or "" if there isn't one."""
    if config.CHROME_BINARY:
        return config.CHROME_BINARY if Path(config.CHROME_BINARY).exists() else ""
    for path in _CHROME_PATHS:
        if Path(path).exists():
            return path
    for command in _CHROME_COMMANDS:
        found = shutil.which(command)
        if found:
            return found
    return ""


def can_auto_launch() -> tuple[bool, str]:
    """Whether we may start Chrome ourselves, and why not when we may not.

    Two hard conditions. The CDP URL has to point at this machine — a deployed
    backend starting a browser on the server would be pointless, since the
    presenter's screen is somewhere else entirely. And Chrome has to exist here
    at all, which on that same deployed backend it does not.
    """
    if not config.AUTO_LAUNCH_CHROME:
        return False, "auto-launch is switched off (AUTO_LAUNCH_CHROME=false)"
    host = (urlparse(config.CHROME_CDP_URL).hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        return False, f"Chrome at {host} isn't on this machine"
    if not chrome_binary():
        return False, "no Chrome install found on this machine"
    return True, ""


def chrome_launch_hint() -> str:
    """The exact command to make Chrome attachable, as one copyable line.

    Three flags, each load-bearing, and every one of them is a thing people
    lose an afternoon to:
      --remote-debugging-port  opens the DevTools endpoint we attach to
      --user-data-dir          required since Chrome 136, which refuses the
                               debug port on the default profile
      --enable-automation      Chrome 151 stable otherwise rejects the CDP
                               handshake with "Browser context management is
                               not supported"

    Use a dedicated profile directory and sign into the demo accounts there
    once — it stays signed in, and the agent never sees personal browsing.
    """
    port = urlparse(config.CHROME_CDP_URL).port or 9222
    binary = chrome_binary() or (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    )
    return (
        f'"{binary}" --remote-debugging-port={port} '
        f'--user-data-dir="{config.CHROME_PROFILE_DIR}" --enable-automation'
    )


def _launch_argv(port: int, url: str = "") -> list[str]:
    """The launch command as argv — never a shell string.

    A path with a space in it (which the macOS one has) is a quoting bug
    waiting to happen, and the URL comes from user input.
    """
    argv = [
        chrome_binary(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={config.CHROME_PROFILE_DIR}",
        "--enable-automation",
        "--no-first-run",
        "--no-default-browser-check",
        # Chrome's own restore prompt would be the first thing on screen.
        "--hide-crash-restore-bubble",
    ]
    if url:
        argv.append(url)
    return argv


async def chrome_port_open(timeout: float = 1.0) -> bool:
    """Is anything listening on the debug port?

    A plain socket check, so callers that only need to know whether Chrome is
    there — a health probe, a "should I launch?" decision — don't have to start
    Playwright and a driver process to find out.
    """
    parsed = urlparse(config.CHROME_CDP_URL)
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(parsed.hostname or "localhost", parsed.port or 9222),
            timeout=timeout,
        )
        writer.close()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


def _cdp_base() -> str:
    parsed = urlparse(config.CHROME_CDP_URL)
    return f"http://{parsed.hostname or 'localhost'}:{parsed.port or 9222}"


async def chrome_page_count() -> int | None:
    """How many page targets the debug endpoint reports. None if unreachable.

    Plain HTTP, no Playwright driver. Worth asking before attaching, because
    zero is a state that looks perfectly healthy from outside and then fails
    the handshake.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as http:
            targets = (await http.get(f"{_cdp_base()}/json/list")).json()
    except (httpx.HTTPError, ValueError):
        return None
    return sum(1 for t in targets if t.get("type") == "page")


async def open_chrome_window(url: str = "about:blank") -> bool:
    """Ask a window-less Chrome to open a tab, over the CDP HTTP endpoint.

    On macOS, closing the last window leaves Chrome *running* with no browser
    context at all. The debug port still answers, so everything looks fine —
    but attaching fails with "Browser context management is not supported",
    which is an unhelpful way to say "there are no windows". Rather than send
    the presenter off to open one mid-demo, open one for them.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            # PUT, not GET: Chrome 111+ rejects GET on /json/new.
            response = await http.put(f"{_cdp_base()}/json/new?{url}")
            opened = response.status_code == 200 and "id" in response.json()
    except (httpx.HTTPError, ValueError):
        return False
    if opened:
        log.info("Chrome had no windows open — opened one at %s", url)
        await asyncio.sleep(1.0)  # let the new target register
    return opened


async def launch_user_chrome(url: str = "") -> bool:
    """Start Chrome with the debug port open. True once it answers.

    Detached on purpose: this browser outlives the demo, so the presenter keeps
    their signed-in profile between runs instead of logging in every time.
    """
    port = urlparse(config.CHROME_CDP_URL).port or 9222
    argv = _launch_argv(port, url)
    log.info("Starting Chrome for the demo: %s", " ".join(argv))
    try:
        config.CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        log.warning("Could not start Chrome: %s", exc)
        return False

    # Chrome takes a moment to open the port, and a cold profile takes longer
    # than a warm one. Poll rather than sleeping a fixed guess.
    deadline = time.monotonic() + CHROME_LAUNCH_TIMEOUT_S
    while time.monotonic() < deadline:
        if await chrome_port_open(timeout=0.5):
            return True
        await asyncio.sleep(0.25)
    log.warning("Chrome did not open port %s within %ss", port, CHROME_LAUNCH_TIMEOUT_S)
    return False

# The outline persists while the presenter talks about the element, so it is
# cleared by the *next* highlight rather than by a timer. Without that hand-off
# a six-step demo ends with the page covered in orange boxes and nothing being
# pointed at.
HIGHLIGHT_JS = """
(el) => {
  const prev = window.__agentHighlight;
  if (prev && prev.el && prev.el !== el) {
    prev.el.style.outline = prev.outline;
    prev.el.style.outlineOffset = prev.offset;
  }
  window.__agentHighlight = {
    el: el,
    outline: el.style.outline,
    offset: el.style.outlineOffset,
  };
  el.style.outline = '3px solid #ff5c00';
  el.style.outlineOffset = '3px';
  el.style.transition = 'outline 160ms ease-in';
  el.scrollIntoView({ block: 'center', behavior: 'smooth' });
}
"""

# Chrome's own surfaces are not demo targets and several of them reject
# script injection outright.
_HIDDEN_SCHEMES = ("devtools://", "chrome://", "chrome-extension://", "edge://")

# Reads the page the way a person would: what can I interact with, and what is
# it called? This is what lets the planner name real controls on a site it has
# never seen instead of guessing.
OUTLINE_JS = r"""
() => {
  const roleFor = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit.split(/\s+/)[0];
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return el.hasAttribute('href') ? 'link' : 'generic';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (/^h[1-6]$/.test(tag)) return 'heading';
    if (tag === 'input') {
      const t = (el.type || 'text').toLowerCase();
      if (t === 'submit' || t === 'button' || t === 'reset') return 'button';
      if (t === 'checkbox') return 'checkbox';
      if (t === 'radio') return 'radio';
      return 'textbox';
    }
    return 'generic';
  };

  const nameFor = (el) => {
    const labelled = el.getAttribute('aria-labelledby');
    if (labelled) {
      const parts = labelled.split(/\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((n) => n.innerText || '');
      if (parts.join(' ').trim()) return parts.join(' ');
    }
    return (
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      el.getAttribute('alt') ||
      el.getAttribute('title') ||
      (el.labels && el.labels[0] && el.labels[0].innerText) ||
      el.innerText ||
      el.value ||
      ''
    );
  };

  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    if (r.bottom < 0 || r.top > (window.innerHeight || 0) * 3) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };

  const out = [];
  const seen = new Set();
  const nodes = document.querySelectorAll(
    'a[href],button,input,textarea,select,summary,[role],h1,h2,h3'
  );
  for (const el of nodes) {
    if (el.id && el.id.startsWith('__agent_')) continue;
    if (!visible(el)) continue;
    const role = roleFor(el);
    if (role === 'generic') continue;
    const name = nameFor(el).replace(/\s+/g, ' ').trim().slice(0, 70);
    if (!name) continue;
    const key = role + '|' + name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ role, name });
    if (out.length >= 90) break;
  }
  return out;
}
"""


class TabNotFound(RuntimeError):
    """Raised when the user's description doesn't match any open tab."""


class BrowserSession:
    """Owns the agent's connection to a browser for one walkthrough."""

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

        # True when we joined the user's Chrome rather than launching our own.
        # Governs teardown: we must never close a browser we did not open.
        self.attached = False
        # True when we started that Chrome ourselves. It is still theirs to
        # close — the profile stays signed in for the next demo.
        self.launched_chrome = False
        # Built from the tab the user chose, so the demo can't wander off the
        # product being shown. Empty until a tab is selected.
        self.allowed_hosts: set[str] = set()
        # Parallel to the last list_tabs() result, mapping index -> page.
        self._tab_pages: list[Page] = []

    # ---------------------------------------------------------------- lifecycle

    async def start(
        self, attach_only: bool = False, auto_launch: bool = False, url: str = ""
    ) -> str:
        """Get a browser, preferring the user's own. Returns what happened.

        `attach_only` skips the fallback launch. The tab picker polls this on
        every page load, and popping a fresh browser window each time just to
        report "not attached" would be worse than the error it's reporting.

        `auto_launch` starts Chrome with the debug flags when the port isn't
        open. Off by default for the same reason: only the act of starting a
        demo should be allowed to open a window on the presenter's screen.
        """
        # A closed port is the normal state on a deployed backend, where there
        # is no browser at all and this gets polled. Answer from a socket check
        # instead of spawning a Playwright driver to rediscover it every time.
        if attach_only and config.ATTACH_TO_CHROME and not await chrome_port_open():
            return self._no_chrome_note()

        # A running Chrome with every window closed still answers on the debug
        # port, but has no browser context — and the attach fails with an error
        # that says nothing about windows. Give it a tab first.
        if config.ATTACH_TO_CHROME and await chrome_page_count() == 0:
            await open_chrome_window(url or "about:blank")

        self._pw = await async_playwright().start()

        if config.ATTACH_TO_CHROME:
            note = await self._attach()
            if note:
                return note

            if auto_launch:
                allowed, why_not = can_auto_launch()
                if allowed:
                    self.launched_chrome = await launch_user_chrome(url)
                    if self.launched_chrome:
                        note = await self._attach()
                        if note:
                            return (
                                "Started Chrome with the debug port open. "
                                "It's a separate demo profile, so sign in there "
                                "once if the product asks."
                            )
                else:
                    log.info("Not auto-launching Chrome: %s", why_not)

        if attach_only:
            return self._no_chrome_note()

        await self._launch()
        return (
            "Launched a fresh browser — it has none of your logins. To demo a "
            "signed-in product, quit Chrome and start it with:\n"
            f"{chrome_launch_hint()}"
        )

    def _no_chrome_note(self) -> str:
        """Why we have no browser, phrased for wherever this is running.

        On a laptop the answer is a command to run. On a deployed backend it
        never can be: the presenter's Chrome is on their machine, and the
        DevTools port is not something to expose across the internet.
        """
        if not chrome_binary():
            return (
                "This backend has no browser and can't reach yours — your Chrome "
                "runs on your machine, and its debug port is not safe to expose "
                "publicly. Run the backend locally to drive your own browser."
            )
        return f"Not connected to your Chrome. Start it with:\n{chrome_launch_hint()}"

    async def _attach(self) -> str | None:
        """Join the running Chrome over CDP. Returns a note, or None on failure."""
        try:
            self._browser = await self._pw.chromium.connect_over_cdp(
                config.CHROME_CDP_URL, timeout=CDP_CONNECT_TIMEOUT_MS
            )
        except (PlaywrightError, PlaywrightTimeout) as exc:
            detail = str(exc).splitlines()[0]
            log.warning("Could not attach to Chrome at %s (%s)", config.CHROME_CDP_URL, detail)
            if "context management" in detail:
                # Two very different causes share this message. Zero windows is
                # by far the more common one, and the only one the presenter
                # can fix in a second.
                if await chrome_page_count() == 0:
                    log.warning(
                        "Chrome is running with no windows open. Open any tab in "
                        "it, or quit it and let the agent relaunch it."
                    )
                else:
                    log.warning(
                        "Chrome is refusing to be driven — it may be running "
                        "without --enable-automation. Restart it with:\n%s",
                        chrome_launch_hint(),
                    )
            return None

        contexts = self._browser.contexts
        if not contexts:
            log.warning("Attached to Chrome but it has no browser context")
            await self._browser.close()
            self._browser = None
            return None

        self._context = contexts[0]
        self.attached = True
        for context in contexts:
            # Covers every page opened from here on; existing tabs get the
            # overlay injected directly when they're selected.
            await context.add_init_script(OVERLAY_INIT_JS)
            context.set_default_timeout(ACTION_TIMEOUT_MS)

        tabs = await self.list_tabs()
        log.info("Attached to Chrome at %s — %d tabs", config.CHROME_CDP_URL, len(tabs))
        return f"Attached to your Chrome — {len(tabs)} tabs available."

    async def _launch(self) -> None:
        """Fallback: our own browser, when the user's isn't reachable."""
        assert self._pw is not None
        launch_args = {
            "headless": config.HEADLESS,
            "slow_mo": config.SLOW_MO_MS,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if config.BROWSER_CHANNEL:
            launch_args["channel"] = config.BROWSER_CHANNEL

        try:
            self._browser = await self._pw.chromium.launch(**launch_args)
        except PlaywrightError as exc:
            # Real Chrome isn't installed everywhere (CI containers in
            # particular). Fall back rather than failing the demo outright.
            if not config.BROWSER_CHANNEL:
                raise
            log.warning(
                "Channel %r unavailable (%s) — falling back to bundled Chromium",
                config.BROWSER_CHANNEL,
                str(exc).splitlines()[0],
            )
            launch_args.pop("channel")
            self._browser = await self._pw.chromium.launch(**launch_args)

        self._context = await self._browser.new_context(
            viewport={
                "width": config.VIEWPORT_WIDTH,
                "height": config.VIEWPORT_HEIGHT,
            },
            device_scale_factor=1,
        )
        await self._context.add_init_script(OVERLAY_INIT_JS)
        self.page = await self._context.new_page()
        self.page.set_default_timeout(ACTION_TIMEOUT_MS)
        log.info("Launched own browser (headless=%s)", config.HEADLESS)

    async def stop(self) -> None:
        """Release the browser; safe to call twice.

        When attached, this disconnects and leaves every tab exactly as it was.
        Closing a presenter's browser at the end of a demo would be its own
        small disaster.
        """
        try:
            if self.attached:
                if self._browser is not None:
                    await self._browser.close()  # disconnects; Chrome stays up
            else:
                for closer in (self._context, self._browser):
                    if closer is not None:
                        await closer.close()
        except PlaywrightError:  # pragma: no cover - best-effort teardown
            pass

        if self._pw is not None:
            await self._pw.stop()
        self._pw = self._browser = self._context = self.page = None
        self._tab_pages = []
        self.attached = False
        log.info("Browser session released")

    # --------------------------------------------------------------------- tabs

    def _contexts(self) -> list[BrowserContext]:
        if self._browser is None:
            return [self._context] if self._context else []
        return list(self._browser.contexts) or (
            [self._context] if self._context else []
        )

    async def list_tabs(self) -> list[TabInfo]:
        """Every real page open in the attached browser, in window order."""
        tabs: list[TabInfo] = []
        pages: list[Page] = []

        for context in self._contexts():
            for page in context.pages:
                if page.is_closed():
                    continue
                url = page.url or ""
                if not url or url.startswith(_HIDDEN_SCHEMES) or url == "about:blank":
                    continue
                try:
                    title = await page.title()
                    # The closest the protocol gets to "the tab they're looking
                    # at" — but only a hint: freshly restored tabs report
                    # visible too, so several can claim it at once. It is worth
                    # a tiebreak and nothing more.
                    active = await page.evaluate(
                        "() => document.visibilityState === 'visible'"
                    )
                except PlaywrightError:
                    title, active = "", False
                tabs.append(
                    TabInfo(
                        index=len(tabs),
                        title=title,
                        url=url,
                        host=(urlparse(url).hostname or "").lower(),
                        active=bool(active),
                    )
                )
                pages.append(page)

        self._tab_pages = pages
        return tabs

    async def select_tab(self, hint: str) -> TabInfo:
        """Focus the tab the user asked for, opening one if they named a URL.

        Raises TabNotFound with the actual tab list, because "no matching tab"
        is only useful if it tells the presenter what they *do* have open.
        """
        tabs = await self.list_tabs()
        chosen = match_tab(tabs, hint)

        if chosen is None:
            url = normalise_url(hint)
            if url is None:
                raise TabNotFound(
                    f"No open tab matches {hint!r}. Open tabs:\n{describe(tabs)}"
                )
            return await self.open_tab(url)

        page = self._tab_pages[chosen.index]
        await self._adopt(page)
        log.info("Demoing in tab %r (%s)", chosen.title, chosen.host)
        return chosen

    async def open_tab(self, url: str) -> TabInfo:
        """Open a new tab in the user's browser and demo there."""
        context = self._context or (self._contexts() or [None])[0]
        if context is None:
            raise RuntimeError("No browser context available")
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await self._adopt(page)
        info = TabInfo(
            index=0,
            title=await page.title(),
            url=page.url,
            host=(urlparse(page.url).hostname or "").lower(),
            active=True,
        )
        log.info("Opened a new tab at %s", url)
        return info

    async def _adopt(self, page: Page) -> None:
        """Make this page the demo surface: focus it, scope it, dress it."""
        self.page = page
        page.set_default_timeout(ACTION_TIMEOUT_MS)
        try:
            await page.bring_to_front()
        except PlaywrightError:
            pass
        self.allowed_hosts = self._scope_for(page.url)
        await self._ensure_overlay()

    @staticmethod
    def _scope_for(url: str) -> set[str]:
        """Which hosts the demo may visit, given the tab it starts on.

        The registrable domain plus its subdomains: a product demo legitimately
        crosses app./www./docs., and legitimately never leaves the product.
        """
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return set(config.EXTRA_ALLOWED_HOSTS)
        parts = host.split(".")
        base = ".".join(parts[-2:]) if len(parts) > 2 else host
        return {host, base, *config.EXTRA_ALLOWED_HOSTS}

    def host_allowed(self, url: str) -> bool:
        """True when a URL is inside the demo's scope."""
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        if not self.allowed_hosts:  # no tab chosen yet — nothing is in scope
            return False
        return any(
            host == allowed or host.endswith(f".{allowed}")
            for allowed in self.allowed_hosts
        )

    async def page_outline(self) -> dict:
        """What is on screen right now: title, URL, and named controls.

        This is what makes the agent site-agnostic. Rather than shipping
        knowledge of any particular product, it reads the page and hands the
        planner the actual roles and labels it can act on.
        """
        if self.page is None:
            return {"title": "", "url": "", "elements": []}
        try:
            elements = await self.page.evaluate(OUTLINE_JS)
            return {
                "title": await self.page.title(),
                "url": self.page.url,
                "elements": elements,
            }
        except PlaywrightError as exc:
            log.warning("Could not read the page outline: %s", exc)
            return {"title": "", "url": self.page.url if self.page else "", "elements": []}

    # ------------------------------------------------------------------ actions

    async def run_action(self, action: Action) -> str:
        """Execute one action. Returns a short human-readable trace line.

        Failures are reported, never raised: a missing button should degrade the
        demo by one beat, not end it.
        """
        if self.page is None:
            raise RuntimeError("No tab selected — call select_tab() first")

        await self._ensure_overlay()

        try:
            if action.type is ActionType.NAVIGATE:
                # Second gate. The planner is told the scope and the plan is
                # sanitised, but this is the one that actually holds, because
                # it sits between the instruction and the browser.
                if not self.host_allowed(action.target):
                    log.warning("Blocked out-of-scope navigation: %s", action.target)
                    return f"skipped {action.target} — outside this demo's scope"
                await self.page.goto(action.target, wait_until="domcontentloaded")
                return f"navigated to {action.target}"

            if action.type is ActionType.WAIT:
                await asyncio.sleep(_as_seconds(action.value))
                return f"waited {action.value}s"

            if action.type is ActionType.PRESS:
                await self.page.keyboard.press(action.value or "Enter")
                return f"pressed {action.value}"

            locator = await self._locate(action)
            point = await self._point_at(locator, spotlight=True)

            if action.type is ActionType.CLICK:
                if point:
                    await self._overlay("click", *point)
                await locator.click()
                # Long-poll connections mean networkidle often never arrives and
                # we just burn the timeout. Keep it short: the gate is only
                # checked between actions, so every second here is a second a
                # pause request sits unanswered.
                await self.page.wait_for_load_state("networkidle", timeout=2000)
                return f"clicked {action.target!r}"

            if action.type is ActionType.FILL:
                if point:
                    await self._overlay("click", *point)
                await locator.click()
                # `type()` on a non-editable element is a no-op that raises
                # nothing, so without this check the trace would report a
                # successful search that never happened and the next step
                # would fail somewhere far less obvious.
                editable = await locator.evaluate(
                    "e => e.isContentEditable || /^(INPUT|TEXTAREA)$/.test(e.tagName)"
                )
                if not editable:
                    log.warning("%r is not a text field — nothing typed", action.target)
                    return f"couldn't type into {action.target!r} — not a text field"
                # type() rather than fill(): the audience should see the text
                # appear character by character, not materialise instantly.
                await locator.type(action.value, delay=config.TYPING_DELAY_MS)
                return f"typed into {action.target!r}"

            if action.type is ActionType.HIGHLIGHT:
                await locator.evaluate(HIGHLIGHT_JS)
                return f"highlighted {action.target!r}"

        except (PlaywrightTimeout, PlaywrightError) as exc:
            first_line = str(exc).splitlines()[0]
            log.warning("Action %s failed: %s", action.type.value, first_line)
            return f"could not {action.type.value} {action.target!r} — continuing"

        return f"skipped unknown action {action.type}"

    # -------------------------------------------------------------- overlay

    async def _ensure_overlay(self) -> None:
        """Install the cursor/caption overlay on the current page.

        Tabs that were already open when we attached never ran the init script,
        so it is injected directly. The script no-ops if it's already there.
        """
        if self.page is None or not (config.SHOW_CURSOR or config.SHOW_CAPTIONS):
            return
        try:
            await self.page.evaluate(OVERLAY_EVAL_JS)
        except PlaywrightError:
            pass  # mid-navigation; the next action retries

    async def _overlay(self, fn: str, *args) -> None:
        """Call into the injected overlay, ignoring pages where it isn't up yet."""
        if self.page is None or not config.SHOW_CURSOR:
            return
        try:
            await self.page.evaluate(
                f"(a) => window.__agentOverlay && window.__agentOverlay.{fn}(...a)",
                list(args),
            )
        except PlaywrightError:
            pass  # mid-navigation; the next action re-installs the overlay

    async def _point_at(
        self, locator, spotlight: bool = False
    ) -> tuple[float, float] | None:
        """Glide the drawn cursor to an element and let the motion land.

        Returns the viewport-space centre so the caller can fire a click pulse
        at the same spot. The real mouse is moved too — a drawn cursor that
        didn't trigger hover states would misrepresent what the product does.
        """
        if self.page is None or not config.SHOW_CURSOR:
            return None
        try:
            await locator.scroll_into_view_if_needed(timeout=3000)
            box = await locator.bounding_box()
        except PlaywrightError:
            return None
        if not box:
            return None

        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2

        if spotlight:
            await self._overlay(
                "spotlight", box["x"], box["y"], box["width"], box["height"]
            )
        await self._overlay("moveTo", cx, cy)
        try:
            await self.page.mouse.move(cx, cy, steps=12)
        except PlaywrightError:
            pass
        # Let the CSS glide finish before acting, or the click lands before the
        # pointer visibly arrives and the motion reads as a glitch.
        await asyncio.sleep(config.CURSOR_TRAVEL_SECONDS)
        return cx, cy

    async def clear_marks(self) -> None:
        """Take the demo's marks off the page — caption and last highlight.

        The presenter's tabs are their own; a demo shouldn't leave an orange
        box around a button after it has finished talking about it.
        """
        await self.set_caption("")
        if self.page is None:
            return
        try:
            await self.page.evaluate(
                """() => {
                  const h = window.__agentHighlight;
                  if (h && h.el) {
                    h.el.style.outline = h.outline;
                    h.el.style.outlineOffset = h.offset;
                  }
                  window.__agentHighlight = null;
                }"""
            )
        except PlaywrightError:
            pass

    async def set_caption(self, text: str) -> None:
        """Burn the current narration into the page as a subtitle bar."""
        if self.page is None or not config.SHOW_CAPTIONS:
            return
        try:
            await self.page.evaluate(
                "(t) => window.__agentOverlay && window.__agentOverlay.caption(t)",
                text,
            )
        except PlaywrightError:
            pass

    # Roles that are visually interchangeable and constantly confused. A "New
    # issue" button is often an <a>; a plan that calls it a button is
    # describing what the user sees, and it is right to. "combobox" is in here
    # because search fields with suggestions are comboboxes, and they are just
    # as clickable as anything else.
    _EQUIVALENT_ROLES = ("button", "link", "menuitem", "tab", "combobox")
    # What a text field can actually be. YouTube's search box is a combobox,
    # not a textbox — a plan that says "textbox" is describing what the user
    # sees and should not be punished for it.
    _EDITABLE_ROLES = ("textbox", "combobox", "searchbox")

    def _candidates(self, action: Action, exact: bool) -> list:
        """Every way the named element might be addressed, best guess first."""
        assert self.page is not None
        name = action.target

        if action.type is ActionType.FILL:
            # Typing into a button silently does nothing — no exception, no
            # text, and a trace that claims success. So a fill never falls back
            # to a non-editable role, however well the name matches.
            roles = [action.role] if action.role in self._EDITABLE_ROLES else []
            roles += [r for r in self._EDITABLE_ROLES if r != action.role]
            return [
                self.page.get_by_role(role, name=name, exact=exact) for role in roles
            ] + [
                self.page.get_by_label(name, exact=exact),
                self.page.get_by_placeholder(name, exact=exact),
            ]

        found = []
        if action.role:
            found.append(self.page.get_by_role(action.role, name=name, exact=exact))
            for role in self._EQUIVALENT_ROLES:
                if role != action.role:
                    found.append(self.page.get_by_role(role, name=name, exact=exact))
        found += [
            self.page.get_by_label(name, exact=exact),
            self.page.get_by_placeholder(name, exact=exact),
            self.page.get_by_text(name, exact=exact),
        ]
        return found

    async def _locate(self, action: Action):
        """Resolve an accessible name to something clickable.

        Two orderings matter, and neither survives being folded into a single
        `.or_()` union — a union returns matches in *DOM order*, so the page
        decides which candidate wins rather than us.

        Exact names are tried before substrings. Short labels are the common
        case in real navigation, and substring matching on them is actively
        wrong: on YouTube, `name="You"` also matches the "YouTube Home" logo,
        which sits earlier in the DOM and would swallow every click meant for
        the sidebar.

        Within each pass the requested role comes first, then the roles that
        look identical to a human. The planner names elements the way a person
        would describe them; insisting its guess at the underlying ARIA role is
        exactly right would break the demo on markup we do not control.
        """
        assert self.page is not None
        fallback = None
        for exact in (True, False):
            for candidate in self._candidates(action, exact):
                # Visible only: apps keep duplicate markup for responsive
                # layouts, and a hidden match just times out on click.
                visible = candidate.locator("visible=true")
                try:
                    if await visible.count():
                        return visible.first
                except PlaywrightError:  # pragma: no cover - page navigated
                    continue
                if fallback is None:
                    fallback = candidate.first
        # Nothing is on screen yet. Return the first candidate anyway so the
        # action waits on it and reports a real timeout, rather than an
        # internal error the presenter can't interpret.
        return fallback if fallback is not None else self.page.get_by_text(
            action.target, exact=False
        ).first

    # -------------------------------------------------------------- observation

    async def screenshot_b64(self, live: bool = False) -> str | None:
        """Capture the viewport as a base64 image for WebSocket transport.

        `live=True` is the continuous-stream path: JPEG at reduced quality,
        roughly a fifth the bytes of the PNG. At streaming frame rates the
        difference between 250KB and 45KB per frame is the difference between
        a smooth panel and one that falls behind the browser it is showing.
        """
        if self.page is None:
            return None
        try:
            if live:
                raw = await self.page.screenshot(
                    type="jpeg", quality=config.FRAME_QUALITY, full_page=False
                )
            else:
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
