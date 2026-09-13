"""Scripted foundation demo and model-driven local repair entry points."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from agent.runner import run_agent
from config import Settings
from scripts.demo import run_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="AgenticFix foundation tools")
    parser.add_argument("command", choices=["demo", "run"])
    parser.add_argument("--keep-worktrees", action="store_true", help="Retain demo worktrees")
    parser.add_argument("--repo", type=Path, help="Existing trusted local Git repository")
    parser.add_argument("--issue-file", type=Path, help="UTF-8 issue description")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--trusted-local", action="store_true")
    args = parser.parse_args()
    if args.command == "demo" and (args.repo or args.issue_file or args.trusted_local):
        parser.error("Repository options belong to the run command")
    if bool(args.repo) != bool(args.issue_file):
        parser.error("--repo and --issue-file must be provided together")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "demo":
            result = asyncio.run(run_demo(Settings(), keep_worktrees=args.keep_worktrees))
        else:
            result = asyncio.run(
                run_agent(
                    Settings(),
                    source=args.repo,
                    issue=args.issue_file.read_text() if args.issue_file else None,
                    ref=args.ref,
                    trusted_local=args.trusted_local,
                    keep_worktrees=args.keep_worktrees,
                )
            )
    except ValueError as exc:
        logging.error("Configuration: %s", exc)
        raise SystemExit(2) from None
    except Exception as exc:
        logging.error("Run failed (%s); inspect configured runs directory", type(exc).__name__)
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.command == "run" and result["state"]["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
