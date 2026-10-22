import asyncio
import json
from collections.abc import Callable
from typing import TextIO

import aiohttp

from companion.mcdu import (
    Connected,
    Disconnected,
    McduScreen,
    Settler,
    Update,
    describe,
    parse_frame,
    screen_of,
)

DEFAULT_URL = "ws://localhost:8380/interfaces/v1/mcdu"
Report = Callable[[str], None]


async def capture(url: str, out: TextIO, report: Report, retry_s: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    start = loop.time()

    def clock() -> float:
        return loop.time() - start

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.ws_connect(url, heartbeat=20) as ws:
                    report(f"connected to {url}")
                    await _request_update(ws)
                    await _record(ws, out, report, clock)
                report("SimBridge closed the connection")
            except (aiohttp.ClientError, OSError, TimeoutError) as exc:
                report(f"cannot reach {url}: {exc}")
            await asyncio.sleep(retry_s)


async def _request_update(ws: aiohttp.ClientWebSocketResponse) -> None:
    # The only frame this client ever sends: SimBridge relays everything, and an "event:" frame
    # would press an MCDU key in the sim.
    await ws.send_str("requestUpdate")


async def _record(
    ws: aiohttp.ClientWebSocketResponse, out: TextIO, report: Report, clock: Callable[[], float]
) -> None:
    settler = Settler()
    ticker = asyncio.create_task(_tick(settler, report, clock))
    try:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            t = clock()
            out.write(json.dumps({"t": round(t, 3), "raw": msg.data}) + "\n")
            out.flush()
            frame = parse_frame(msg.data)
            if isinstance(frame, Connected):
                report(f"{t:7.1f}s  sim connected")
                await _request_update(ws)
            elif isinstance(frame, Disconnected):
                report(f"{t:7.1f}s  sim disconnected")
            elif isinstance(frame, Update):
                screen = screen_of(frame)
                if screen is not None:
                    _report_settled(settler.push(t, screen), t, report)
    finally:
        ticker.cancel()


async def _tick(settler: Settler, report: Report, clock: Callable[[], float]) -> None:
    # Separate task so a quiet socket still releases the last screen.
    while True:
        await asyncio.sleep(0.05)
        t = clock()
        _report_settled(settler.poll(t), t, report)


def _report_settled(screen: McduScreen | None, t: float, report: Report) -> None:
    if screen is not None:
        report(f"{t:7.1f}s  {describe(screen)}")
