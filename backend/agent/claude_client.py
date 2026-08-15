"""Thin wrapper around the Anthropic SDK.

One shared AsyncAnthropic client for the whole process — creating a client per
request would leak connection pools inside FastAPI's event loop.
"""

from __future__ import annotations

import logging

import anthropic

from . import config

log = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    """Return the process-wide async client, creating it on first use."""
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        _client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def has_api_key() -> bool:
    """True when Claude calls are possible; lets callers fall back gracefully."""
    return bool(config.ANTHROPIC_API_KEY)


def cached_doc_block(doc: str, preamble: str) -> list[dict]:
    """Build a system block whose product-doc suffix is cached.

    The doc is identical on every narration and Q&A call, so marking it
    ephemeral turns repeat reads into ~0.1x input cost. The cache breakpoint
    goes on the *last* block of the stable prefix.
    """
    return [
        {"type": "text", "text": preamble},
        {
            "type": "text",
            "text": f"<product_doc>\n{doc}\n</product_doc>",
            "cache_control": {"type": "ephemeral"},
        },
    ]


def text_of(message: anthropic.types.Message) -> str:
    """Concatenate the text blocks of a response.

    Content is a discriminated union — thinking blocks are not text blocks, so
    indexing content[0].text is a latent crash.
    """
    return "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ).strip()


def describe_error(exc: Exception) -> str:
    """Human-readable, non-leaky error text for the client panel."""
    if isinstance(exc, anthropic.NotFoundError):
        return f"Model '{config.MODEL}' is not available on this API key."
    if isinstance(exc, anthropic.RateLimitError):
        return "Claude is rate limited right now — retrying shortly."
    if isinstance(exc, anthropic.APIStatusError):
        return f"Claude API returned {exc.status_code}."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach the Claude API — check network connectivity."
    return f"Unexpected error: {exc.__class__.__name__}"
