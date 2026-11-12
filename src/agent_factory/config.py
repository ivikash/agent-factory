"""Settings, read once from the environment.

Every knob the deploy pipeline or a developer changes is here, with the production default. Model
ids are Bedrock inference-profile ids. Claude Haiku 5.5 is the cheap tier the toolkit's registry
marks active ($0.11 per million input tokens in the US geo profile on 2026-11-09).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: _env("APP_NAME", "agent-factory"))
    stage: str = field(default_factory=lambda: _env("STAGE", "local"))
    service_version: str = field(default_factory=lambda: _env("SERVICE_VERSION", "dev"))
    region: str = field(default_factory=lambda: _env("AWS_REGION", _env("AWS_DEFAULT_REGION", "us-west-2")))

    # System 2: the models that plan, write and review. One id per role so a team can move one role
    # to a stronger model without touching the others.
    plan_model_id: str = field(default_factory=lambda: _env("MODEL_PLAN", "us.anthropic.claude-haiku-5-5"))
    code_model_id: str = field(default_factory=lambda: _env("MODEL_CODE", "us.anthropic.claude-haiku-5-5"))
    review_model_id: str = field(
        default_factory=lambda: _env("MODEL_REVIEW", "us.anthropic.claude-haiku-5-5")
    )
    max_tokens: int = field(default_factory=lambda: int(_env("MODEL_MAX_TOKENS", "2048")))

    # System 1: the decider at the gate. With DECIDER_URL set, the Strands Decider server answers.
    # Without it, a cheap Bedrock model answers the same questions through structured output.
    decider_url: str = field(default_factory=lambda: _env("DECIDER_URL", ""))
    decider_model_id: str = field(
        default_factory=lambda: _env("MODEL_DECIDER", "us.anthropic.claude-haiku-5-5")
    )
    decider_timeout_s: float = field(default_factory=lambda: float(_env("DECIDER_TIMEOUT_S", "10")))
    # Below this confidence the factory asks for clarification instead of building. Strands Decider
    # answers at 0.9 or above are right about 95 percent of the time on unseen classification tasks.
    confidence_floor: float = field(default_factory=lambda: float(_env("DECIDER_CONFIDENCE_FLOOR", "0.9")))

    # Graph limits. A review loop that never approves stops here.
    max_review_rounds: int = field(default_factory=lambda: int(_env("MAX_REVIEW_ROUNDS", "2")))
    graph_timeout_s: int = field(default_factory=lambda: int(_env("GRAPH_TIMEOUT_S", "240")))

    @property
    def resource_attributes(self) -> dict[str, str]:
        """OpenTelemetry resource attributes every signal carries."""
        return {
            "service.name": self.app_name,
            "service.namespace": self.app_name,
            "service.version": self.service_version,
            "deployment.environment.name": self.stage,
        }
