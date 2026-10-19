import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import aiohttp
from aiohttp import web
from yarl import URL

from companion.simbrief import Ofp, OfpError, SimbriefError, to_wire

PROTOCOL_VERSION = 1
INDEX_PATH = Path(__file__).resolve().parents[2] / "index.html"
log = logging.getLogger(__name__)


class OfpSource(Protocol):
    def cached(self) -> Ofp | None: ...
    async def refresh(self) -> Ofp: ...


@dataclass
class Hub:
    source: OfpSource
    ofp: Ofp | None = None
    clients: set[web.WebSocketResponse] = field(default_factory=set)
    _refreshing: asyncio.Lock = field(default_factory=asyncio.Lock)

    def sources(self) -> dict[str, bool]:
        return {"sim": False, "mcdu": False, "ofp": self.ofp is not None}

    async def broadcast(self, message: dict[str, Any]) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except ConnectionResetError:
                self.clients.discard(ws)

    async def refresh_ofp(self) -> None:
        # Serialized so a burst of refresh clicks costs one SimBrief request at a time.
        async with self._refreshing:
            # OSError covers cache writes on a read-only or full disk; ValueError covers a
            # non-UTF-8 SimBrief body.
            try:
                ofp = await self.source.refresh()
            except (
                SimbriefError,
                OfpError,
                aiohttp.ClientError,
                TimeoutError,
                OSError,
                ValueError,
            ) as exc:
                log.warning("OFP refresh failed: %s", exc)
                return
            had_ofp = self.ofp is not None
            self.ofp = ofp
            await self.broadcast({"type": "ofp", "data": to_wire(ofp)})
            if not had_ofp:
                await self.broadcast({"type": "sources", **self.sources()})


HUB = web.AppKey("hub", Hub)
STARTUP_TASK = web.AppKey("startup_task", asyncio.Task[None])


def make_app(ofp_source: OfpSource, index_path: Path = INDEX_PATH) -> web.Application:
    app = web.Application()
    app[HUB] = Hub(source=ofp_source, ofp=ofp_source.cached())

    async def index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(index_path)

    async def start_refresh(app: web.Application) -> None:
        app[STARTUP_TASK] = asyncio.create_task(app[HUB].refresh_ofp())

    async def stop_refresh(app: web.Application) -> None:
        app[STARTUP_TASK].cancel()

    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket)
    app.on_startup.append(start_refresh)
    app.on_cleanup.append(stop_refresh)
    return app


async def websocket(request: web.Request) -> web.WebSocketResponse:
    # Browsers let any site open a WebSocket to localhost; only this page's origin may connect.
    origin = request.headers.get("Origin")
    if origin is not None and URL(origin).authority != request.host:
        log.warning("rejected WebSocket from a foreign origin")
        raise web.HTTPForbidden()
    hub = request.app[HUB]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    hub.clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "version": PROTOCOL_VERSION, "sources": hub.sources()})
        if hub.ofp is not None:
            await ws.send_json({"type": "ofp", "data": to_wire(hub.ofp)})
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await handle(hub, msg.data)
    finally:
        hub.clients.discard(ws)
    return ws


async def handle(hub: Hub, text: str) -> None:
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        log.debug("ignoring non-JSON frame")
        return
    if not isinstance(message, dict):
        return
    if message.get("type") == "ofp_refresh":
        await hub.refresh_ofp()
    else:
        log.debug("ignoring message type %r", message.get("type"))
