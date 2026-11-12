from __future__ import annotations

import json

import pytest

from agent_factory import handler
from agent_factory.factory import Outcome
from agent_factory.nodes import Triage


class Ctx:
    aws_request_id = "req-1"


def _event(method: str, path: str, body: str | None = None) -> dict:
    return {"rawPath": path, "requestContext": {"http": {"method": method}}, "body": body}


def test_health_returns_200_with_version(monkeypatch: pytest.MonkeyPatch) -> None:
    response = handler.handler(_event("GET", "/health"), Ctx())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "ok" and "version" in body and "telemetry" in body


def test_unknown_route_is_404() -> None:
    assert handler.handler(_event("GET", "/nope"), Ctx())["statusCode"] == 404
    assert handler.handler(_event("DELETE", "/"), Ctx())["statusCode"] == 404


def test_bad_bodies_are_400_and_413() -> None:
    assert handler.handler(_event("POST", "/", "not json"), Ctx())["statusCode"] == 400
    assert handler.handler(_event("POST", "/", json.dumps({"request": ""})), Ctx())["statusCode"] == 400
    assert (
        handler.handler(_event("POST", "/", json.dumps({"request": "x" * 5000})), Ctx())["statusCode"] == 413
    )


def test_post_runs_the_factory_and_returns_the_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    outcome = Outcome(
        "completed",
        ["triage", "plan", "code", "review", "publish"],
        Triage("feature", 0.97, 0.9, True),
        "code here",
        1234,
    )
    monkeypatch.setattr(handler, "_graph_instance", lambda: object())
    monkeypatch.setattr(handler, "run", lambda request, graph, settings: outcome)

    response = handler.handler(_event("POST", "/", json.dumps({"request": "add /health"})), Ctx())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert (
        body["request_id"] == "req-1"
        and body["path"][-1] == "publish"
        and body["triage"]["intent"] == "feature"
    )


def test_factory_failure_is_502_without_a_stack_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handler, "_graph_instance", lambda: object())

    def boom(request, graph, settings):
        raise RuntimeError("bedrock exploded with secret details")

    monkeypatch.setattr(handler, "run", boom)
    response = handler.handler(_event("POST", "/", json.dumps({"request": "add /health"})), Ctx())
    assert response["statusCode"] == 502
    assert "secret details" not in response["body"]
    assert json.loads(response["body"])["request_id"] == "req-1"
