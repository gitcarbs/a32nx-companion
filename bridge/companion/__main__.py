import argparse
import asyncio
import logging
import sys
from contextlib import suppress
from pathlib import Path

from aiohttp import web

from companion.config import ConfigError, load_config
from companion.mcdu_capture import DEFAULT_URL, capture
from companion.server import make_app
from companion.simbrief import SimbriefLoader, default_cache_path


def main() -> int:
    parser = argparse.ArgumentParser(prog="companion")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="serve the page and the /ws bridge")
    run.add_argument("--config", type=Path, default=Path("config.toml"))
    mcdu = commands.add_parser("mcdu-capture", help="record SimBridge MCDU frames to JSONL")
    mcdu.add_argument("out", type=Path)
    mcdu.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()

    if args.command == "mcdu-capture":
        with args.out.open("w", encoding="utf-8") as out, suppress(KeyboardInterrupt):
            asyncio.run(capture(args.url, out, lambda line: print(line, flush=True)))
        return 0

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"companion: {exc}", file=sys.stderr)
        return 2

    loader = SimbriefLoader(config.simbrief, default_cache_path())
    web.run_app(make_app(loader), host=config.server.host, port=config.server.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
