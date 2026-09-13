"""Milestone 1 entry point: run the trusted, scripted tool-chain demo."""

import argparse
import asyncio
import json
import logging

from config import Settings
from scripts.demo import run_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="AgenticFix foundation tools")
    parser.add_argument("command", choices=["demo"])
    parser.add_argument("--keep-worktrees", action="store_true", help="Retain demo worktrees")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = asyncio.run(run_demo(Settings(), keep_worktrees=args.keep_worktrees))
    except Exception:
        logging.exception("Demo failed; inspect runs/ for artifacts and retained workspaces")
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
