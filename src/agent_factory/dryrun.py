"""Dry run: the whole graph, no model tokens.

System 2 nodes are replaced by deterministic stand-ins that write the same shapes the real
agents write (a ``Plan``, fenced code, a ``Review`` verdict), so every edge condition is
exercised for real. System 1 is the real Strands Decider when ``DECIDER_URL`` is set, and a
fixed, clearly labelled verdict otherwise. Nothing here calls Bedrock.
"""

from __future__ import annotations

import json
from typing import Any

from agent_factory.config import Settings
from agent_factory.decider import Decision, SystemOne
from agent_factory.factory import HttpDecider, build_graph
from agent_factory.nodes import FunctionNode

DRY_RUN_MARK = "[dry run]"


class FixedDecider:
    """System 1 stand-in for a dry run without a decider server: always a confident feature."""

    def choose(self, state: str, question: str, options: list[str]) -> Decision:
        return Decision(label="feature", confidence=0.95, scores={"feature": 0.95})

    def yes_no(self, state: str, question: str) -> float:
        return 0.9


def _plan(task: str) -> str:
    request = task.splitlines()[0].removeprefix("Original Task:").strip() if task else ""
    return json.dumps(
        {
            "summary": f"{DRY_RUN_MARK} would plan: {request[:80]}",
            "language": "python",
            "files": ["app.py", "tests/test_app.py"],
            "acceptance": ["the change is covered by a test", "the test passes"],
        }
    )


def _code(task: str) -> str:
    revised = "revision needed" in task
    return (
        f"```python\n# app.py  {DRY_RUN_MARK}{' (revised after review)' if revised else ''}\n"
        "def handler():\n    return {'status': 'ok'}\n```\n"
        f"```python\n# tests/test_app.py  {DRY_RUN_MARK}\nfrom app import handler\n\n"
        "def test_handler():\n    assert handler()['status'] == 'ok'\n```"
    )


class _Reviewer:
    """Asks for one revision, then approves, so the loop edge is exercised once per run."""

    def __init__(self) -> None:
        self.rounds = 0

    def __call__(self, task: str) -> str:
        self.rounds += 1
        if self.rounds == 1:
            return json.dumps(
                {"verdict": "revision needed", "findings": [f"{DRY_RUN_MARK} add a failing-path test"]}
            )
        return json.dumps({"verdict": "approved", "findings": []})


def _clarify(task: str) -> str:
    return (
        f"{DRY_RUN_MARK} the request is not specific enough to build. Three questions:\n"
        "1. Which file or service does this change?\n"
        "2. What should the user see when it works?\n"
        "3. Is there an existing test to extend?"
    )


def dry_run_agents() -> dict[str, Any]:
    return {
        "clarify": FunctionNode(_clarify, "clarify"),
        "plan": FunctionNode(_plan, "plan"),
        "code": FunctionNode(_code, "code"),
        "review": FunctionNode(_Reviewer(), "review"),
    }


def dry_run_decider(settings: Settings) -> tuple[SystemOne, str]:
    """The real decider when a server is configured, otherwise the fixed stand-in. Says which."""
    if settings.decider_url:
        return HttpDecider(
            settings.decider_url, timeout_s=settings.decider_timeout_s
        ), f"strands decider at {settings.decider_url}"
    return FixedDecider(), "fixed stand-in (set DECIDER_URL for the real System 1)"


def build_dry_run_graph(settings: Settings):
    decider, _ = dry_run_decider(settings)
    return build_graph(settings, decider=decider, agents=dry_run_agents())
