import asyncio
import io
import json
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from aiohttp import web

from companion.mcdu_capture import capture
from tests.mcdu_samples import init_a, update_frame

PATH = "/interfaces/v1/mcdu"


async def until(condition: Callable[[], bool]) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout=3)


async def test_records_every_frame_and_only_requests_updates(aiohttp_server: Any) -> None:
    frames = [update_frame(init_a()), "event:left:INIT", "mcduConnected", 'print:{"lines":[]}']
    received: list[str] = []

    async def mcdu(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        for frame in frames:
            await ws.send_str(frame)
        async for msg in ws:
            received.append(msg.data)
        return ws

    app = web.Application()
    app.router.add_get(PATH, mcdu)
    server = await aiohttp_server(app)
    out = io.StringIO()
    reports: list[str] = []
    task = asyncio.create_task(capture(str(server.make_url(PATH)), out, reports.append))
    try:
        await until(
            lambda: (
                len(received) >= 2
                and out.getvalue().count("\n") == len(frames)
                and any("INIT_A  ci=25 crz_fl=350" in r for r in reports)
            )
        )
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert received == ["requestUpdate", "requestUpdate"]
    recorded = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["raw"] for r in recorded] == frames
    times = [r["t"] for r in recorded]
    assert times == sorted(times)


async def test_keeps_retrying_when_simbridge_is_down(unused_tcp_port: int) -> None:
    reports: list[str] = []
    url = f"ws://127.0.0.1:{unused_tcp_port}{PATH}"
    task = asyncio.create_task(capture(url, io.StringIO(), reports.append, retry_s=0.01))
    try:
        await until(lambda: sum("cannot reach" in r for r in reports) >= 2)
        assert not task.done()
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
