"""Runtime configuration. Everything sensitive comes from the environment."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
PRODUCT_DOC_PATH = Path(os.getenv("PRODUCT_DOC_PATH", DATA_DIR / "product_doc.md"))
WORKFLOWS_PATH = Path(os.getenv("WORKFLOWS_PATH", DATA_DIR / "workflows.json"))

# Claude
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Demo target. Credentials are never hardcoded — they are read here or not at all.
TARGET_URL = os.getenv("TARGET_URL", "https://github.com")
DEMO_REPO = os.getenv("DEMO_REPO", "")  # e.g. "flytbase-demo/walkthrough-sandbox"
GITHUB_USER = os.getenv("GITHUB_USER", "")
GITHUB_PASSWORD = os.getenv("GITHUB_PASSWORD", "")
GITHUB_SESSION_COOKIE = os.getenv("GITHUB_SESSION_COOKIE", "")

# Browser
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
VIEWPORT_WIDTH = int(os.getenv("VIEWPORT_WIDTH", "1440"))
VIEWPORT_HEIGHT = int(os.getenv("VIEWPORT_HEIGHT", "900"))
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "250"))  # human-watchable pacing

# Pacing between steps so a viewer can actually read the narration.
STEP_DWELL_SECONDS = float(os.getenv("STEP_DWELL_SECONDS", "1.5"))

VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() != "false"


def read_product_doc() -> str:
    """Load the teaching document the agent narrates from."""
    if PRODUCT_DOC_PATH.exists():
        return PRODUCT_DOC_PATH.read_text(encoding="utf-8")
    return ""
