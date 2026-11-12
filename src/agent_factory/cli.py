"""Run the factory from a terminal: ``agent-factory "add a /health endpoint to the Flask app"``."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from agent_factory import telemetry
from agent_factory.config import Settings
from agent_factory.dryrun import dry_run_agents, dry_run_decider
from agent_factory.factory import build_graph, make_decider, run
from agent_factory.nodes import Triage, triage


def _triage_line(verdict: Triage) -> str:
    return (
        f"triage: {verdict.intent} ({verdict.intent_confidence:.2f}), "
        f"actionable {verdict.actionable:.2f}, confident={verdict.confident}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-factory", description="Turn a one-line software request into a plan, code and a review."
    )
    parser.add_argument("request", help="what to build, in one sentence")
    parser.add_argument("--json", action="store_true", help="print the full outcome as JSON")
    parser.add_argument(
        "--triage-only",
        action="store_true",
        help="ask the System 1 decider only and print its verdict, spending no System 2 tokens",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the whole graph with deterministic System 2 stand-ins: no Bedrock call, no tokens. "
        "System 1 is the real decider when DECIDER_URL is set",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(name)s %(message)s"
    )
    settings = Settings()
    telemetry.setup(settings)

    if args.triage_only:
        verdict = triage(make_decider(settings), args.request, settings.confidence_floor)
        print(verdict.to_json() if args.json else _triage_line(verdict))
        return 0

    if args.dry_run:
        decider, which = dry_run_decider(settings)
        print(f"dry run: System 2 is canned, System 1 is {which}", file=sys.stderr)
        graph = build_graph(settings, decider=decider, agents=dry_run_agents())
        outcome = run(args.request, graph=graph, settings=settings)
    else:
        outcome = run(args.request, settings=settings)

    if args.json:
        print(json.dumps(outcome.to_dict(), indent=2))
    else:
        if outcome.triage:
            print(_triage_line(outcome.triage))
        print(f"path: {' -> '.join(outcome.path)}  ({outcome.execution_ms} ms)\n")
        print(outcome.output)
    return 0 if outcome.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
