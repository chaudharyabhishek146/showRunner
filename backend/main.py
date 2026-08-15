"""FastAPI entrypoint for the Platform Walkthrough Agent.

The WebSocket at /ws is the demo transport: the browser sends control events,
the agent streams narration, screenshots, and answers back. REST endpoints exist
for health checks (the CD pipeline gates on /health) and workflow memory.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from agent import config, memory
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
    version="1.0.0",
    description="An agent that runs a live product demo in a real browser.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo-scoped; tighten to the Vercel origin in prod
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- REST


class Health(BaseModel):
    status: str
    claude_configured: bool
    model: str
    product_doc_loaded: bool
    target: str


@app.get("/health", response_model=Health)
async def health() -> Health:
    """Readiness probe — the deploy stage rolls back if this doesn't pass."""
    return Health(
        status="ok",
        claude_configured=has_api_key(),
        model=config.MODEL,
        product_doc_loaded=bool(config.read_product_doc()),
        target=config.TARGET_URL,
    )


@app.get("/workflows")
async def workflows() -> dict:
    """Everything the agent has learned, for the 'resume a demo' picker."""
    return {"workflows": memory.list_workflows()}


@app.delete("/workflows/{name}")
async def forget_workflow(name: str) -> dict:
    return {"forgotten": memory.forget(name)}


@app.get("/product-doc")
async def product_doc() -> dict:
    """The teaching document, so the UI can show what grounds the answers."""
    return {"path": str(config.PRODUCT_DOC_PATH), "content": config.read_product_doc()}


# ---------------------------------------------------------------- WebSocket


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
            text="Connected. Load a walkthrough to begin.",
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
                await session.start(event.workflow)
            elif event.type == "question":
                # Fire-and-forget so the socket keeps reading while Claude
                # thinks — otherwise a second question would queue behind it.
                asyncio.create_task(session.ask(event.text))
            elif event.type == "pause":
                session.pause()
                await emit(ServerEvent(type="status", text="paused"))
            elif event.type == "resume":
                session.resume()
                await emit(ServerEvent(type="status", text="running"))
            elif event.type == "skip":
                session.skip()
            elif event.type == "stop":
                await session.stop()
                await emit(ServerEvent(type="status", text="stopped"))

    except WebSocketDisconnect:
        log.info("Client disconnected — tearing down the browser")
    except Exception:
        log.exception("WebSocket handler failed")
    finally:
        await session.stop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
