import json
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from companion.config import SimbriefConfig
from companion.simbrief import SimbriefError, SimbriefLoader

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ofp_krdu_katl.json").read_text())


async def fake_simbrief(aiohttp_server: Any, seen: list[dict[str, str]]) -> TestServer:
    async def handler(request: web.Request) -> web.Response:
        seen.append(dict(request.query))
        if request.query.get("username") == "bad":
            return web.json_response({"fetch": {"status": "Error: Unknown UserID"}}, status=400)
        if request.query.get("username") == "garbage":
            return web.Response(text="<html>oops</html>", content_type="text/html")
        return web.json_response(FIXTURE)

    app = web.Application()
    app.router.add_get("/api/xml.fetcher.php", handler)
    server: TestServer = await aiohttp_server(app)
    return server


async def test_refresh_fetches_normalizes_and_caches(aiohttp_server: Any, tmp_path: Path) -> None:
    seen: list[dict[str, str]] = []
    server = await fake_simbrief(aiohttp_server, seen)
    cache = tmp_path / "ofp.json"
    loader = SimbriefLoader(
        SimbriefConfig(username="pilot"), cache, str(server.make_url("/api/xml.fetcher.php"))
    )

    ofp = await loader.refresh()

    assert ofp.origin == "KRDU"
    assert seen == [{"username": "pilot", "json": "v2"}]
    assert json.loads(cache.read_text()) == FIXTURE
    assert loader.cached() == ofp


async def test_userid_is_sent_when_configured(aiohttp_server: Any, tmp_path: Path) -> None:
    seen: list[dict[str, str]] = []
    server = await fake_simbrief(aiohttp_server, seen)
    loader = SimbriefLoader(
        SimbriefConfig(userid="123"),
        tmp_path / "o.json",
        str(server.make_url("/api/xml.fetcher.php")),
    )
    await loader.refresh()
    assert seen == [{"userid": "123", "json": "v2"}]


async def test_bad_user_raises_and_keeps_cache(aiohttp_server: Any, tmp_path: Path) -> None:
    server = await fake_simbrief(aiohttp_server, [])
    cache = tmp_path / "ofp.json"
    cache.write_text(json.dumps(FIXTURE))
    loader = SimbriefLoader(
        SimbriefConfig(username="bad"), cache, str(server.make_url("/api/xml.fetcher.php"))
    )

    with pytest.raises(SimbriefError, match="Unknown UserID"):
        await loader.refresh()

    assert json.loads(cache.read_text()) == FIXTURE


async def test_non_json_response_raises(aiohttp_server: Any, tmp_path: Path) -> None:
    server = await fake_simbrief(aiohttp_server, [])
    loader = SimbriefLoader(
        SimbriefConfig(username="garbage"),
        tmp_path / "o.json",
        str(server.make_url("/api/xml.fetcher.php")),
    )
    with pytest.raises(SimbriefError, match="JSON"):
        await loader.refresh()


def test_cached_is_none_without_a_file(tmp_path: Path) -> None:
    assert SimbriefLoader(SimbriefConfig(username="x"), tmp_path / "missing.json").cached() is None


def test_cached_is_none_for_a_corrupt_file(tmp_path: Path) -> None:
    cache = tmp_path / "ofp.json"
    cache.write_text("{not json")
    assert SimbriefLoader(SimbriefConfig(username="x"), cache).cached() is None


def test_cached_is_none_for_an_undecodable_file(tmp_path: Path) -> None:
    cache = tmp_path / "ofp.json"
    cache.write_bytes(b"\xff\xfe{")
    assert SimbriefLoader(SimbriefConfig(username="x"), cache).cached() is None
