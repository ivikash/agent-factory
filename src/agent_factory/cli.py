"""Run the factory from a terminal: ``agent-factory "add a /health endpoint to the Flask app"``."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from agent_factory import telemetry
from agent_factory.config import Settings
from agent_factory.factory import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-factory", description="Turn a one-line software request into a plan, code and a review."
    )
    parser.add_argument("request", help="what to build, in one sentence")
    parser.add_argument("--json", action="store_true", help="print the full outcome as JSON")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(name)s %(message)s"
    )
    settings = Settings()
    telemetry.setup(settings)
    outcome = run(args.request, settings=settings)

    if args.json:
        print(json.dumps(outcome.to_dict(), indent=2))
    else:
        verdict = outcome.triage
        if verdict:
            print(
                print(
                    f"triage: {verdict.intent} ({verdict.intent_confidence:.2f}), "
                    f"actionable {verdict.actionable:.2f}, confident={verdict.confident}"
                )
            )
        print(f"path: {' -> '.join(outcome.path)}  ({outcome.execution_ms} ms)\n")
        print(outcome.output)
    return 0 if outcome.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
