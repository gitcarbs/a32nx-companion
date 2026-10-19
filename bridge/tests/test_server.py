import asyncio
import json
from pathlib import Path
from typing import Any

from aiohttp.test_utils import TestClient

from companion.server import make_app
from companion.simbrief import Ofp, SimbriefError, normalize, to_wire

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ofp_krdu_katl.json").read_text())


class FakeOfpSource:
    def __init__(self, cached: Ofp | None, fresh: Ofp | Exception | None) -> None:
        self._cached = cached
        self._fresh = fresh
        self.refreshes = 0

    def cached(self) -> Ofp | None:
        return self._cached

    async def refresh(self) -> Ofp:
        self.refreshes += 1
        if isinstance(self._fresh, Exception):
            raise self._fresh
        assert self._fresh is not None
        return self._fresh


async def client_for(aiohttp_client: Any, source: FakeOfpSource, tmp_path: Path) -> TestClient:
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>t</title>")
    client: TestClient = await aiohttp_client(make_app(source, index))
    return client


async def recv(ws: Any) -> dict[str, Any]:
    msg: dict[str, Any] = await asyncio.wait_for(ws.receive_json(), timeout=2)
    return msg


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

    source._fresh = ofp
    await first.send_json({"type": "ofp_refresh"})

    for ws in (first, second):
        assert await recv(ws) == {"type": "ofp", "data": to_wire(ofp)}
        assert await recv(ws) == {"type": "sources", "sim": False, "mcdu": False, "ofp": True}


async def test_failed_refresh_keeps_connection_open(aiohttp_client: Any, tmp_path: Path) -> None:
    source = FakeOfpSource(None, SimbriefError("bad user"))
    client = await client_for(aiohttp_client, source, tmp_path)
    ws = await client.ws_connect("/ws")
    await recv(ws)
    await ws.send_json({"type": "ofp_refresh"})
    await ws.send_str("not json")
    await ws.send_json({"type": "dismiss", "id": "x"})
    source._fresh = normalize(FIXTURE)
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
