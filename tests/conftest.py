from __future__ import annotations

import pytest

from agent_factory.config import Settings
from agent_factory.decider import Decision
from agent_factory.nodes import FunctionNode


class FakeDecider:
    """A System 1 stand-in with scripted answers."""

    def __init__(self, intent: str = "feature", confidence: float = 0.97, actionable: float = 0.9) -> None:
        self.intent, self.confidence, self.actionable = intent, confidence, actionable
        self.calls: list[tuple[str, str]] = []

    def choose(self, state: str, question: str, options: list[str]) -> Decision:
        self.calls.append(("choose", question))
        return Decision(label=self.intent, confidence=self.confidence, scores={self.intent: self.confidence})

    def yes_no(self, state: str, question: str) -> float:
        self.calls.append(("yes_no", question))
        return self.actionable


class ScriptedReviewer:
    """Returns 'revision needed' n times, then 'approved'."""

    def __init__(self, revisions: int) -> None:
        self.remaining = revisions
        self.seen: list[str] = []

    def __call__(self, text: str) -> str:
        self.seen.append(text)
        if self.remaining > 0:
            self.remaining -= 1
            return '{"verdict": "revision needed", "findings": ["missing test"]}'
        return '{"verdict": "approved", "findings": []}'


class RecordingCoder:
    """Writes the same code every time and remembers what it was asked."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def __call__(self, text: str) -> str:
        self.seen.append(text)
        return "```python\n# app.py\nprint('hello')\n```"


def fake_agents(reviewer: ScriptedReviewer | None = None, coder: RecordingCoder | None = None) -> dict:
    reviewer = reviewer or ScriptedReviewer(0)
    coder = coder or RecordingCoder()
    plan = '{"summary": "a cli", "language": "python", "files": ["app.py"], "acceptance": ["prints hello"]}'
    return {
        "clarify": FunctionNode(
            lambda t: "1. Which language?\n2. Where does it run?\n3. What is the input?", "clarify"
        ),
        "plan": FunctionNode(lambda t: plan, "plan"),
        "code": FunctionNode(coder, "code"),
        "review": FunctionNode(reviewer, "review"),
    }


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in (
        "DECIDER_URL",
        "APP_NAME",
        "STAGE",
        "SERVICE_VERSION",
        "MAX_REVIEW_ROUNDS",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("STAGE", "test")
    monkeypatch.setenv("SERVICE_VERSION", "abc123")
    return Settings()
