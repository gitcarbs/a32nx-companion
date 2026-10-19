import argparse
import logging
import sys
from pathlib import Path

from aiohttp import web

from companion.config import ConfigError, load_config
from companion.server import make_app
from companion.simbrief import SimbriefLoader, default_cache_path


def main() -> int:
    parser = argparse.ArgumentParser(prog="companion")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="serve the page and the /ws bridge")
    run.add_argument("--config", type=Path, default=Path("config.toml"))
    args = parser.parse_args()

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
