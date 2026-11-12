from __future__ import annotations

import json

import httpx
import pytest
import respx

from agent_factory.decider import Decision, HttpDecider
from agent_factory.nodes import INTENTS, Triage, triage


def test_decision_confidence_floor() -> None:
    assert Decision("feature", 0.9).confident(0.9)
    assert not Decision("feature", 0.89).confident(0.9)


@respx.mock
def test_http_decider_choose_sends_strands_decider_request_shape() -> None:
    route = respx.post("http://decider:8000/v1/systemone").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "strands-decider-2B-qwen3.5-v1-2610",
                "answers": {
                    "q": {
                        "type": "choice",
                        "choice": "bugfix",
                        "confidence": 0.91,
                        "probabilities": {"feature": 0.05, "bugfix": 0.91, "question": 0.04},
                    }
                },
                "usage": {"input_tokens": 40, "output_tokens": 1},
                "latency_ms": 120.5,
            },
        )
    )
    decider = HttpDecider("http://decider:8000/", client=httpx.Client())
    decision = decider.choose("the login page 500s", "What kind of software request is this?", INTENTS)

    sent = json.loads(route.calls.last.request.read())
    assert sent == {
        "state": "the login page 500s",
        "questions": {
            "q": {
                "type": "choice",
                "instructions": "What kind of software request is this?",
                "criteria": {"feature": None, "bugfix": None, "question": None},
            }
        },
    }
    assert decision == Decision("bugfix", 0.91, {"feature": 0.05, "bugfix": 0.91, "question": 0.04})


@respx.mock
def test_http_decider_yes_no_returns_noul() -> None:
    respx.post("http://decider:8000/v1/systemone").mock(
        return_value=httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": 0.858}}})
    )
    decider = HttpDecider("http://decider:8000", client=httpx.Client())
    assert decider.yes_no("Help!", "Does this convey urgency?") == 0.858


@respx.mock
def test_http_decider_surfaces_server_errors() -> None:
    respx.post("http://decider:8000/v1/systemone").mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        HttpDecider("http://decider:8000", client=httpx.Client()).yes_no("x", "y")


def test_triage_round_trips_through_text() -> None:
    class D:
        def choose(self, state, question, options):
            return Decision("question", 0.95, {"question": 0.95})

        def yes_no(self, state, question):
            return 0.7

    verdict = triage(D(), "how do I rotate logs?", floor=0.9)
    text = "The original task\n\n" + verdict.to_json() + "\n\nmore"
    parsed = Triage.parse(text)
    assert parsed == verdict and parsed.confident


def test_triage_parse_returns_none_without_a_verdict() -> None:
    assert Triage.parse("no verdict here") is None
