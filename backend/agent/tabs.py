"""Turning "show the demo on YouTube" into one specific open tab.

Kept free of Playwright imports so the matching logic can be tested without a
browser — picking the wrong tab in front of a customer is the most visible
failure this agent has, and it deserves tests that run in milliseconds.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import TabInfo

# Words that describe the *instruction*, not the target. Without stripping
# these, "show the demo on youtube" would score every tab on "demo".
_STOPWORDS = {
    "a", "an", "and", "browser", "chrome", "demo", "do", "for", "give", "in",
    "into", "it", "me", "my", "of", "on", "open", "page", "please", "screen",
    "show", "site", "tab", "the", "this", "to", "walkthrough", "web", "window",
}

_URLISH = re.compile(r"^(https?://|[\w-]+(\.[\w-]+)+(/|$))", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+")

# Below this, a "match" is really just an accident of a shared word.
MATCH_THRESHOLD = 10


def normalise_url(hint: str) -> str | None:
    """Return a loadable URL if the hint names one, else None.

    Lets the user say "open figma.com" and get a new tab, rather than an error
    about no matching tab.
    """
    candidate = hint.strip()
    if not candidate or " " in candidate or not _URLISH.match(candidate):
        return None
    if not candidate.lower().startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    return candidate


_BARE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$", re.IGNORECASE)


def guess_url(hint: str) -> str | None:
    """A URL for a hint that names a product but not an address.

    Only for the case where we have just launched an empty browser: there are
    no tabs to match against, so the choice is a reasonable guess or a blank
    window. "youtube" becomes https://youtube.com; anything with a space in it
    is a description rather than a product name, and gets nothing.

    Deliberately *not* used when tabs exist. Guessing among a presenter's open
    tabs risks showing a customer the wrong one; guessing on an empty browser
    risks a page that visibly isn't the product, which they can see and fix.
    """
    candidate = normalise_url(hint)
    if candidate:
        return candidate
    stripped = hint.strip()
    if _BARE_NAME.match(stripped) and stripped.lower() not in _STOPWORDS:
        return f"https://{stripped.lower()}.com"
    return None


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


def _host_of(hint: str) -> str:
    url = normalise_url(hint)
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower()


def score_tab(tab: TabInfo, hint: str) -> int:
    """How well one tab answers the user's description of where to demo."""
    host = (tab.host or urlparse(tab.url).hostname or "").lower()
    title = tab.title.lower()
    path = urlparse(tab.url).path.lower()

    score = 0
    hint_host = _host_of(hint)
    if hint_host:
        if hint_host == host:
            score += 100
        elif host.endswith(f".{hint_host}") or hint_host.endswith(f".{host}"):
            score += 80

    for token in set(_tokens(hint)):
        # The host is the strongest signal: a product's name is usually in it.
        if token in host:
            score += 40
        if token in title:
            score += 12
        if token in path:
            score += 6

    if tab.active:
        score += 1  # tiebreak only — never enough to win on its own
    return score


def match_tab(tabs: list[TabInfo], hint: str) -> TabInfo | None:
    """Pick the tab the user meant.

    With no hint, fall back to a foreground tab — they pointed the agent at
    their own browser, so what's in front of them is the likeliest target.
    Chrome can report more than one tab as visible, so this is a guess; naming
    the product is always better, and the UI asks for it.
    """
    if not tabs:
        return None
    if not hint.strip():
        return next((t for t in tabs if t.active), tabs[0])

    ranked = sorted(tabs, key=lambda t: score_tab(t, hint), reverse=True)
    best = ranked[0]
    return best if score_tab(best, hint) >= MATCH_THRESHOLD else None


def describe(tabs: list[TabInfo]) -> str:
    """A one-line-per-tab listing, for error messages the user can act on."""
    return "\n".join(f"  [{t.index}] {t.title or t.url} — {t.host}" for t in tabs)
