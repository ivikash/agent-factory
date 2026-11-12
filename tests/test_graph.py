"""The whole graph, run by the real Strands Graph engine with deterministic nodes in place of models."""

from __future__ import annotations

from conftest import FakeDecider, RecordingCoder, ScriptedReviewer, fake_agents

from agent_factory.config import Settings
from agent_factory.factory import build_graph, run


def test_confident_request_goes_plan_code_review_publish(settings: Settings) -> None:
    decider = FakeDecider(intent="feature", confidence=0.97, actionable=0.9)
    graph = build_graph(settings, decider, fake_agents())
    outcome = run("add a /health endpoint to app.py", graph=graph, settings=settings)

    assert outcome.status == "completed"
    assert outcome.path == ["triage", "plan", "code", "review", "publish"]
    assert outcome.triage is not None and outcome.triage.confident and outcome.triage.intent == "feature"
    assert "print('hello')" in outcome.output
    assert not outcome.output.startswith("code:"), "FunctionNode output is unwrapped, no node-name prefix"
    assert [kind for kind, _ in decider.calls] == ["choose", "yes_no"]


def test_low_confidence_asks_for_clarification_instead_of_building(settings: Settings) -> None:
    decider = FakeDecider(intent="feature", confidence=0.6, actionable=0.9)
    graph = build_graph(settings, decider, fake_agents())
    outcome = run("make it better", graph=graph, settings=settings)

    assert outcome.path == ["triage", "clarify", "publish"]
    assert outcome.triage is not None and not outcome.triage.confident
    assert "Which language?" in outcome.output


def test_not_actionable_asks_even_when_intent_is_confident(settings: Settings) -> None:
    decider = FakeDecider(intent="bugfix", confidence=0.99, actionable=0.2)
    graph = build_graph(settings, decider, fake_agents())
    outcome = run("it crashes sometimes", graph=graph, settings=settings)

    assert outcome.path == ["triage", "clarify", "publish"]


def test_review_loop_revises_once_then_publishes(settings: Settings) -> None:
    reviewer, coder = ScriptedReviewer(revisions=1), RecordingCoder()
    graph = build_graph(settings, FakeDecider(), fake_agents(reviewer, coder))
    outcome = run("add a /health endpoint", graph=graph, settings=settings)

    assert outcome.path == ["triage", "plan", "code", "review", "code", "review", "publish"]
    assert outcome.status == "completed"
    assert len(reviewer.seen) == 2 and len(coder.seen) == 2
    assert "revision needed" in coder.seen[1], "the second code pass received the findings"
    assert "missing test" in coder.seen[1]


def test_review_loop_is_bounded_when_nothing_is_ever_approved(settings: Settings, monkeypatch) -> None:
    monkeypatch.setenv("MAX_REVIEW_ROUNDS", "2")
    bounded = Settings()
    graph = build_graph(bounded, FakeDecider(), fake_agents(ScriptedReviewer(revisions=99)))
    outcome = run("add a /health endpoint", graph=graph, settings=bounded)

    assert outcome.status != "completed"
    assert outcome.path.count("code") <= bounded.max_review_rounds + 1
    assert "publish" not in outcome.path


def test_graph_builds_without_touching_a_model(settings: Settings) -> None:
    graph = build_graph(settings, FakeDecider(), fake_agents())
    assert set(graph.nodes) == {"triage", "clarify", "plan", "code", "review", "publish"}
    assert graph.entry_points and next(iter(graph.entry_points)).node_id == "triage"
