from __future__ import annotations

import pytest

from agent_factory.config import Settings


def test_defaults_are_the_cheap_tier(settings: Settings) -> None:
    assert (
        settings.plan_model_id
        == settings.code_model_id
        == settings.review_model_id
        == "us.anthropic.claude-haiku-5-5"
    )
    assert settings.decider_url == "" and settings.confidence_floor == 0.8
    assert settings.max_review_rounds == 2


def test_env_overrides_and_resource_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "factory")
    monkeypatch.setenv("STAGE", "production")
    monkeypatch.setenv("SERVICE_VERSION", "deadbeef")
    monkeypatch.setenv("DECIDER_URL", "http://localhost:8000")
    monkeypatch.setenv("MODEL_CODE", "us.anthropic.claude-sonnet-5-5")
    s = Settings()
    assert s.decider_url == "http://localhost:8000" and s.code_model_id == "us.anthropic.claude-sonnet-5-5"
    assert s.resource_attributes == {
        "service.name": "factory",
        "service.namespace": "factory",
        "service.version": "deadbeef",
        "deployment.environment.name": "production",
    }
