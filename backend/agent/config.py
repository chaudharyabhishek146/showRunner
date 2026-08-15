"""Runtime configuration.

Nothing here names a site, a repository, or an account. The demo target is
whatever tab the user points the agent at, at run time; the product document is
whatever they upload. This file only holds *how* the agent behaves — pacing,
overlay, where Chrome's debug port is — never *what* it demos.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", DATA_DIR / "uploads"))
WORKFLOWS_PATH = Path(os.getenv("WORKFLOWS_PATH", DATA_DIR / "workflows.json"))
# Optional. Docs dropped here are offered as starting points in the UI, but the
# real source is whatever the user uploads for this demo.
SAMPLES_DIR = Path(os.getenv("SAMPLES_DIR", DATA_DIR / "samples"))
SAMPLE_DOC_PATH = Path(os.getenv("SAMPLE_DOC_PATH", DATA_DIR / "product_doc.md"))

# --- Locked demo -----------------------------------------------------------
# For a hackathon run the demo must be identical every time, so the UI offers
# no document, no flow, and no tab to choose — it starts the preset below and
# nothing else. The site-agnostic engine underneath is untouched:
# DEMO_LOCKED=false hands the choice back to the presenter.
DEMO_LOCKED = os.getenv("DEMO_LOCKED", "true").lower() != "false"
LOCKED_DEMO_SAMPLE = os.getenv("LOCKED_DEMO_SAMPLE", "youtube-2-minute")
LOCKED_DEMO_FOCUS = os.getenv(
    "LOCKED_DEMO_FOCUS",
    "the two-minute version: the home feed, an intentional search, and where "
    "the saved list lives",
)
LOCKED_DEMO_TAB = os.getenv("LOCKED_DEMO_TAB", "youtube")
LOCKED_DEMO_TITLE = os.getenv("LOCKED_DEMO_TITLE", "YouTube — the two-minute version")

# Offer to wait while the presenter signs in, before anything is planned.
# Signed-out and signed-in YouTube are different products, and the plan has to
# know which one it is looking at.
ASK_TO_SIGN_IN = os.getenv("ASK_TO_SIGN_IN", "true").lower() != "false"
# How long to hold for that answer before assuming "no" — a demo must never
# hang on a dialog nobody clicked.
SIGN_IN_PROMPT_TIMEOUT = float(os.getenv("SIGN_IN_PROMPT_TIMEOUT", "180"))

# Claude
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Chrome attachment -----------------------------------------------------
# The agent drives the user's *own* Chrome over the DevTools protocol rather
# than launching a clean profile. That is the whole point: their tabs are
# already open and already signed in, so the demo runs against the real product
# and the agent never handles a credential.
#
# Chrome must be started with a debug port, e.g.
#   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
#       --remote-debugging-port=9222
CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "http://localhost:9222")
ATTACH_TO_CHROME = os.getenv("ATTACH_TO_CHROME", "true").lower() != "false"

# If the debug port isn't open when a demo starts, start Chrome ourselves with
# the right flags rather than making the presenter paste a command mid-meeting.
# Only ever applies to a CDP URL on this machine — see browser.can_auto_launch.
AUTO_LAUNCH_CHROME = os.getenv("AUTO_LAUNCH_CHROME", "true").lower() != "false"
# A dedicated profile: Chrome 136+ refuses the debug port on the default one,
# and it keeps the demo's sign-ins away from the presenter's personal browsing.
CHROME_PROFILE_DIR = Path(
    os.getenv("CHROME_PROFILE_DIR", Path.home() / "chrome-demo-profile")
)
# Set when Chrome lives somewhere non-standard; empty means "go and find it".
CHROME_BINARY = os.getenv("CHROME_BINARY", "")

# Used only when attaching is off or the debug port isn't there. "chrome" drives
# the real Chrome install, "msedge" drives Edge, empty uses bundled Chromium.
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
VIEWPORT_WIDTH = int(os.getenv("VIEWPORT_WIDTH", "1440"))
VIEWPORT_HEIGHT = int(os.getenv("VIEWPORT_HEIGHT", "900"))
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "250"))  # human-watchable pacing

# --- Navigation policy -----------------------------------------------------
# The allowlist is built at run time from the tab the user selected, so the demo
# cannot wander off the product being shown. Extra hosts (a docs site, an SSO
# domain) can be permitted here as a comma-separated list.
EXTRA_ALLOWED_HOSTS = [
    h.strip().lower()
    for h in os.getenv("EXTRA_ALLOWED_HOSTS", "").split(",")
    if h.strip()
]

# Pacing between steps so a viewer can actually read the narration. Slower than
# feels right when you're the one who already knows what happens next.
STEP_DWELL_SECONDS = float(os.getenv("STEP_DWELL_SECONDS", "3"))

# --- Taking questions ------------------------------------------------------
# After each step the agent asks the room for questions and waits. The window
# resets whenever someone actually asks, so a follow-up is never cut off, and
# the Skip control ends it early when the room is quiet.
QUESTION_BREAK_SECONDS = float(os.getenv("QUESTION_BREAK_SECONDS", "12"))
# The longer hold at the end, where questions actually tend to arrive.
CLOSING_QUESTION_SECONDS = float(os.getenv("CLOSING_QUESTION_SECONDS", "60"))

# Continuous frame streaming. Without this the panel only refreshes after each
# action, which on a screen share looks like a slideshow rather than a browser.
LIVE_FPS = float(os.getenv("LIVE_FPS", "4"))
FRAME_QUALITY = int(os.getenv("FRAME_QUALITY", "62"))  # JPEG quality, 1-100

# On-page overlay. The OS mouse pointer is not captured in screenshots, so
# without a drawn cursor the audience sees buttons activate by themselves.
SHOW_CURSOR = os.getenv("SHOW_CURSOR", "true").lower() != "false"
CURSOR_TRAVEL_SECONDS = float(os.getenv("CURSOR_TRAVEL_SECONDS", "0.6"))
# Burn the narration into the browser view itself, so the page is
# self-explanatory even when shared without the app's chat panel.
SHOW_CAPTIONS = os.getenv("SHOW_CAPTIONS", "true").lower() != "false"
# Per-keystroke delay so text visibly types rather than appearing at once.
TYPING_DELAY_MS = int(os.getenv("TYPING_DELAY_MS", "45"))

VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() != "false"


def list_samples() -> list[dict]:
    """The bundled example docs, for the "try it on something" picker.

    Sorted by filename so the order doesn't shuffle between restarts, and the
    title is read from the doc's own H1 rather than invented from the filename.
    """
    found = []
    for path in sorted(SAMPLES_DIR.glob("*.md")) if SAMPLES_DIR.exists() else []:
        first = path.read_text(encoding="utf-8").lstrip().split("\n", 1)[0]
        found.append(
            {
                "name": path.stem,
                "title": first.lstrip("# ").strip() or path.stem,
            }
        )
    return found


def read_sample_doc(name: str = "") -> str:
    """One bundled example doc. Purely a convenience default.

    `name` is matched against the samples directory only — a stem, never a
    path — so a crafted name can't walk out of it and read the .env sitting
    two directories up.
    """
    if name:
        candidate = SAMPLES_DIR / f"{Path(name).name}.md"
        if candidate.exists() and candidate.parent == SAMPLES_DIR:
            return candidate.read_text(encoding="utf-8")
        return ""

    samples = list_samples()
    if samples:
        return read_sample_doc(samples[0]["name"])
    if SAMPLE_DOC_PATH.exists():  # legacy single-file location
        return SAMPLE_DOC_PATH.read_text(encoding="utf-8")
    return ""
