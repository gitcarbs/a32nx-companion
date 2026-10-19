import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient

from companion.server import make_app
from companion.simbrief import Ofp, SimbriefError, normalize, to_wire

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ofp_krdu_katl.json").read_text())


class FakeOfpSource:
    def __init__(self, cached: Ofp | None, fresh: Ofp | Exception | None) -> None:
        self._cached = cached
        self.fresh = fresh
        self.refreshes = 0

    def cached(self) -> Ofp | None:
        return self._cached

    async def refresh(self) -> Ofp:
        self.refreshes += 1
        if isinstance(self.fresh, Exception):
            raise self.fresh
        assert self.fresh is not None
        return self.fresh


async def client_for(
    aiohttp_client: Any, source: FakeOfpSource, tmp_path: Path
) -> TestClient[web.Request, web.Application]:
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>t</title>")
    client: TestClient[web.Request, web.Application] = await aiohttp_client(make_app(source, index))
    return client


async def recv(ws: Any) -> dict[str, Any]:
    msg: dict[str, Any] = await asyncio.wait_for(ws.receive_json(), timeout=2)
    return msg


async def until(condition: Callable[[], bool]) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout=2)


async def test_serves_index(aiohttp_client: Any, tmp_path: Path) -> None:
    client = await client_for(aiohttp_client, FakeOfpSource(None, SimbriefError("x")), tmp_path)
    response = await client.get("/")
    assert response.status == 200
    assert "<title>t</title>" in await response.text()


async def test_hello_then_cached_ofp(aiohttp_client: Any, tmp_path: Path) -> None:
    ofp = normalize(FIXTURE)
    client = await client_for(
        aiohttp_client, FakeOfpSource(ofp, SimbriefError("offline")), tmp_path
    )
    ws = await client.ws_connect("/ws")
    assert await recv(ws) == {
        "type": "hello",
        "version": 1,
        "sources": {"sim": False, "mcdu": False, "ofp": True},
    }
    assert await recv(ws) == {"type": "ofp", "data": to_wire(ofp)}


async def test_hello_without_ofp(aiohttp_client: Any, tmp_path: Path) -> None:
    client = await client_for(
        aiohttp_client, FakeOfpSource(None, SimbriefError("offline")), tmp_path
    )
    ws = await client.ws_connect("/ws")
    assert (await recv(ws))["sources"]["ofp"] is False


async def test_refresh_broadcasts_ofp_and_sources(aiohttp_client: Any, tmp_path: Path) -> None:
    ofp = normalize(FIXTURE)
    source = FakeOfpSource(None, SimbriefError("offline at startup"))
    client = await client_for(aiohttp_client, source, tmp_path)
    first = await client.ws_connect("/ws")
    second = await client.ws_connect("/ws")
    await recv(first)
    await recv(second)

    source.fresh = ofp
    await first.send_json({"type": "ofp_refresh"})

    for ws in (first, second):
        assert await recv(ws) == {"type": "ofp", "data": to_wire(ofp)}
        assert await recv(ws) == {"type": "sources", "sim": False, "mcdu": False, "ofp": True}


@pytest.mark.parametrize(
    "failure",
    [SimbriefError("bad user"), OSError("read-only home"), ValueError("non-UTF-8 body")],
    ids=["simbrief", "os", "value"],
)
async def test_failed_refresh_keeps_connection_open(
    aiohttp_client: Any, tmp_path: Path, failure: Exception
) -> None:
    source = FakeOfpSource(None, failure)
    client = await client_for(aiohttp_client, source, tmp_path)
    ws = await client.ws_connect("/ws")
    await recv(ws)
    await ws.send_json({"type": "ofp_refresh"})
    # Swapping the outcome before the server reads the frame would turn the failing refresh
    # into a successful one, so wait until both the startup and the requested refresh ran.
    await until(lambda: source.refreshes == 2)
    await ws.send_str("not json")
    await ws.send_json({"type": "dismiss", "id": "x"})
    source.fresh = normalize(FIXTURE)
    await ws.send_json({"type": "ofp_refresh"})
    assert (await recv(ws))["type"] == "ofp"
    assert not ws.closed


async def test_startup_refresh_runs_once(aiohttp_client: Any, tmp_path: Path) -> None:
    source = FakeOfpSource(None, normalize(FIXTURE))
    client = await client_for(aiohttp_client, source, tmp_path)
    ws = await client.ws_connect("/ws")
    first = await recv(ws)
    if first["sources"]["ofp"] is False:
        assert (await recv(ws))["type"] == "ofp"
    assert source.refreshes == 1


async def test_rejects_foreign_origin(aiohttp_client: Any, tmp_path: Path) -> None:
    client = await client_for(aiohttp_client, FakeOfpSource(None, SimbriefError("x")), tmp_path)
    response = await client.get(
        "/ws",
        headers={
            "Origin": "http://evil.example",
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            "Sec-WebSocket-Version": "13",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
        },
    )
    assert response.status == 403


async def test_accepts_own_origin(aiohttp_client: Any, tmp_path: Path) -> None:
    client = await client_for(aiohttp_client, FakeOfpSource(None, SimbriefError("x")), tmp_path)
    ws = await client.ws_connect("/ws", origin=str(client.make_url("/").origin()))
    assert (await recv(ws))["type"] == "hello"
