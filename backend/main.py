"""FastAPI entrypoint for the Platform Walkthrough Agent.

The WebSocket at /ws is the demo transport: the browser sends control events,
the agent streams narration, screenshots, and answers back. REST endpoints
cover the setup a demo needs before it starts — uploading the product document
and listing the tabs the agent could drive — plus health for the CD gate.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from agent import config, docs, memory
from agent.browser import (
    BrowserSession,
    can_auto_launch,
    chrome_launch_hint,
    chrome_port_open,
)
from agent.claude_client import has_api_key
from agent.models import ClientEvent, ServerEvent
from agent.session import WalkthroughSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("walkthrough")

app = FastAPI(
    title="Platform Walkthrough Agent",
    version="2.0.0",
    description=(
        "An agent that runs a live product demo in the presenter's own browser, "
        "from a product document they upload."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo-scoped; tighten to the deployed origin in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploads are capped well below anything a real product doc needs; the limit is
# there so a stray 200MB file can't take the process down mid-demo.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


# --------------------------------------------------------------------- REST


class Health(BaseModel):
    status: str
    claude_configured: bool
    model: str
    chrome_attach_url: str
    chrome_reachable: bool
    chrome_command: str
    # True when starting a demo can open Chrome itself, so nobody has to paste
    # that command. False on a deployed backend, where Chrome isn't the same
    # machine as the presenter's screen.
    chrome_auto_launch: bool


@app.get("/ping")
async def ping() -> dict:
    """Cheapest possible liveness hit, for the keep-alive cron.

    Deliberately not /health: that one probes for a Chrome to attach to, and
    something calling it every couple of minutes just to stop a free-tier host
    from sleeping shouldn't pay for a probe nobody reads.
    """
    return {"ok": True}


@app.get("/health", response_model=Health)
async def health() -> Health:
    """Readiness probe — the deploy stage rolls back if this doesn't pass."""
    return Health(
        status="ok",
        claude_configured=has_api_key(),
        model=config.MODEL,
        chrome_attach_url=config.CHROME_CDP_URL,
        chrome_reachable=await _chrome_reachable(),
        chrome_command=chrome_launch_hint(),
        chrome_auto_launch=can_auto_launch()[0],
    )


async def _chrome_reachable() -> bool:
    """Cheap probe so the UI can tell the presenter to start Chrome, up front."""
    if not config.ATTACH_TO_CHROME:
        return False

    # Check the socket before starting Playwright. On a deployed box there is
    # no Chrome at all, and this endpoint gets polled — spawning a driver
    # process every time to rediscover that would be a silly way to spend a
    # free-tier instance.
    if not await chrome_port_open():
        return False

    session = BrowserSession()
    try:
        await session.start(attach_only=True)
        return session.attached
    except Exception:
        return False
    finally:
        await session.stop()


@app.get("/tabs")
async def tabs() -> dict:
    """The presenter's open tabs, so the UI can offer a demo target.

    Uses its own short-lived connection: the picker has to work before a
    walkthrough — and therefore before a WebSocket session — exists.
    """
    session = BrowserSession()
    try:
        await session.start(attach_only=True)
        if not session.attached:
            can_launch, _ = can_auto_launch()
            hint = (
                # The common case on a laptop: nothing to do by hand.
                "Chrome isn't listening on the debug port yet. Starting a "
                "walkthrough will open one for you — it's a separate demo "
                "profile, so sign in there once when it appears."
                if can_launch
                else
                # Deployed, or Chrome installed somewhere we couldn't find:
                # the presenter has to run it themselves.
                "Can't drive your Chrome yet — it's running without a debug "
                "port. Paste the command below into a terminal. It opens a "
                "second Chrome window on its own profile, so you don't have to "
                "quit the one you're using. Sign into the product you want to "
                "demo in that window, then reload this page."
            )
            return {
                "attached": False,
                "tabs": [],
                "hint": hint,
                "auto_launch": can_launch,
                "command": chrome_launch_hint(),
            }
        found = await session.list_tabs()
        return {
            "attached": True,
            "tabs": [t.model_dump(mode="json") for t in found],
            "hint": "",
            "auto_launch": True,
        }
    finally:
        await session.stop()


@app.post("/document")
async def upload_document(file: UploadFile = File(...)) -> dict:
    """Accept the product document this demo will be planned and narrated from."""
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Document is larger than 8MB.")

    text = docs.extract_text(file.filename or "document", raw)
    if not text.strip():
        raise HTTPException(
            422,
            f"Couldn't read any text out of {file.filename!r}. "
            "Markdown, plain text, HTML, PDF, and .docx are supported.",
        )
    return docs.store(file.filename or "document", text).summary()


class InlineDoc(BaseModel):
    name: str = "pasted document"
    text: str


@app.post("/document/text")
async def paste_document(body: InlineDoc) -> dict:
    """Same as an upload, for a document pasted straight into the UI."""
    if not body.text.strip():
        raise HTTPException(422, "The document is empty.")
    return docs.store(body.name, body.text).summary()


@app.get("/document/{doc_id}")
async def get_document(doc_id: str) -> dict:
    """What grounds the agent's answers, so the UI can show it."""
    found = docs.get(doc_id)
    if found is None:
        raise HTTPException(404, "No such document.")
    return {**found.summary(), "content": found.text}


@app.get("/demo")
async def demo() -> dict:
    """What this build runs, and whether the presenter gets a say.

    Locked is the hackathon default: one demo, no inputs, identical every time.
    """
    return {
        "locked": config.DEMO_LOCKED,
        "title": config.LOCKED_DEMO_TITLE,
        "focus": config.LOCKED_DEMO_FOCUS,
        "tab": config.LOCKED_DEMO_TAB,
        "sample": config.LOCKED_DEMO_SAMPLE,
    }


@app.get("/samples")
async def samples() -> dict:
    """The bundled example documents, so the UI can offer a starting point."""
    return {"samples": config.list_samples()}


@app.get("/sample-doc")
async def sample_doc(name: str = "") -> dict:
    """One bundled example document. Empty name means the first one."""
    content = config.read_sample_doc(name)
    if not content:
        raise HTTPException(404, f"No sample document named {name!r}.")
    return {"content": content}


@app.get("/workflows")
async def workflows() -> dict:
    """Everything the agent has learned, for the 'resume a demo' picker."""
    return {"workflows": memory.list_workflows()}


@app.delete("/workflows/{name}")
async def forget_workflow(name: str) -> dict:
    return {"forgotten": memory.forget(name)}


# ---------------------------------------------------------------- WebSocket


async def _guarded(coro, emit) -> None:
    """Run a backgrounded coroutine, reporting failures to the client.

    A bare create_task swallows exceptions into the event loop's handler; on a
    live call the presenter needs to see that something broke.
    """
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.exception("Background task failed")
        await emit(ServerEvent(type="error", text=f"Something went wrong: {exc}"))


@app.websocket("/ws")
async def walkthrough_socket(ws: WebSocket) -> None:
    await ws.accept()
    send_lock = asyncio.Lock()

    async def emit(event: ServerEvent) -> None:
        # The executor task and the receive loop both emit; without the lock
        # two concurrent sends can interleave frames on one connection.
        async with send_lock:
            await ws.send_json(event.model_dump(mode="json"))

    session = WalkthroughSession(emit)
    await emit(
        ServerEvent(
            type="status",
            text=(
                f"Connected. Ready to demo {config.LOCKED_DEMO_TITLE}."
                if config.DEMO_LOCKED
                else "Connected. Upload a document and tell me what to demo."
            ),
            payload={"claude_configured": has_api_key(), "voice": config.VOICE_ENABLED},
        )
    )

    try:
        while True:
            raw = await ws.receive_json()
            try:
                event = ClientEvent.model_validate(raw)
            except ValidationError:
                await emit(ServerEvent(type="error", text=f"Unrecognised message: {raw}"))
                continue

            if event.type == "start":
                # Backgrounded, not awaited: start() blocks on the presenter
                # answering the sign-in prompt, and that reply arrives on this
                # same socket. Awaiting it here deadlocks the connection.
                asyncio.create_task(_guarded(session.start(event.to_request()), emit))
            elif event.type == "reply":
                session.reply(event.prompt_id, event.text)
            elif event.type == "list_tabs":
                await session.send_tabs()
            elif event.type == "question":
                # Fire-and-forget so the socket keeps reading while Claude
                # thinks — otherwise a second question would queue behind it.
                asyncio.create_task(_guarded(session.ask(event.text), emit))
            elif event.type == "pause":
                session.pause()
                # "pausing", not "paused": a Playwright action already in flight
                # runs to completion before the loop can park at the gate. Only
                # the executor knows when the browser has actually stopped, and
                # it emits the authoritative "paused" itself. Claiming "paused"
                # here would show a PAUSED badge over a still-moving page.
                await emit(ServerEvent(type="status", text="pausing"))
            elif event.type == "resume":
                session.resume()
                # Resuming is instantaneous — releasing the gate cannot fail —
                # so unlike pause there is nothing to wait to confirm.
                await emit(ServerEvent(type="status", text="running"))
            elif event.type == "skip":
                session.skip()
            elif event.type == "stop":
                await session.stop()
                await emit(ServerEvent(type="status", text="stopped"))

    except WebSocketDisconnect:
        log.info("Client disconnected — releasing the browser")
    except Exception:
        log.exception("WebSocket handler failed")
    finally:
        await session.stop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
