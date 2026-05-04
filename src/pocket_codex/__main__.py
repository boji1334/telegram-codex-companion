import argparse
import logging
from collections.abc import Sequence

from . import __version__
from .app import run
from .config import load_settings


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pocket-codex",
        description="Private Telegram companion for OpenAI project conversations.",
    )
    parser.add_argument("--version", action="version", version=f"pocket-codex {__version__}")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate environment and project configuration without starting Telegram polling",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.check_config:
        settings = load_settings()
        print(f"Configuration OK. Loaded {len(settings.projects)} project(s).")
        return
    run()


if __name__ == "__main__":
    main()
