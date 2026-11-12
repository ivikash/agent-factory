"""System 1: fast, calibrated decisions at the gate.

Two implementations of one small protocol:

- ``HttpDecider`` talks to a running Strands Decider server (``strands-decider serve``). It picks
  between options and answers yes/no questions in about half a second on a CPU, and every answer
  carries a calibrated confidence. That is what makes the gate honest: below the floor the factory
  asks instead of guessing.
- ``BedrockDecider`` asks a cheap Bedrock model the same questions through structured output. It is
  the stand-in where the 2B model cannot run (Lambda has no room for it). Its confidence is the
  model's own self-report, which is not calibrated, so the floor still applies but means less.

Both return the same ``Decision``. The factory never knows which one answered.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Decision:
    """One answer: the chosen label, how sure the decider is, and the full distribution."""

    label: str
    confidence: float
    scores: dict[str, float] = field(default_factory=dict)

    def confident(self, floor: float) -> bool:
        return self.confidence >= floor


class SystemOne(Protocol):
    def choose(self, state: str, question: str, options: list[str]) -> Decision: ...

    def yes_no(self, state: str, question: str) -> float:
        """Probability of yes, 0 to 1."""
        ...


class HttpDecider:
    """Client for the Strands Decider server's ``POST /v1/systemone`` (strands_decider.schema)."""

    def __init__(self, base_url: str, timeout_s: float = 10.0, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_s)

    def _ask(self, state: str, questions: dict) -> dict:
        response = self._client.post(
            f"{self.base_url}/v1/systemone", json={"state": state, "questions": questions}
        )
        response.raise_for_status()
        body = response.json()
        log.debug("decider answered in %s ms", body.get("latency_ms"))
        return body["answers"]

    def choose(self, state: str, question: str, options: list[str]) -> Decision:
        # ChoiceQuestion: the options are the keys of ``criteria``; a None value means "no description".
        question_body = {
            "type": "choice",
            "instructions": question,
            "criteria": {option: None for option in options},
        }
        answer = self._ask(state, {"q": question_body})["q"]
        scores = {str(k): float(v) for k, v in answer["probabilities"].items()}
        return Decision(label=str(answer["choice"]), confidence=float(answer["confidence"]), scores=scores)

    def yes_no(self, state: str, question: str) -> float:
        answers = self._ask(state, {"q": {"type": "noul", "instructions": question}})
        return float(answers["q"]["noul"])


class _Choice(BaseModel):
    label: str = Field(description="Exactly one of the offered options, spelled as offered.")
    confidence: float = Field(ge=0.0, le=1.0, description="How sure you are, 0 to 1.")


class _YesNo(BaseModel):
    probability_yes: float = Field(ge=0.0, le=1.0)


class BedrockDecider:
    """A cheap Bedrock model answering the decider's questions through structured output."""

    def __init__(self, model_id: str, region: str) -> None:
        # Imported here so the module imports without the SDK (tests stub the protocol).
        from strands import Agent
        from strands.models import BedrockModel

        model = BedrockModel(model_id=model_id, region_name=region, max_tokens=200, temperature=0.0)
        system = (
            "You are a decision model. You answer only the question asked, as the structured output "
            "requested, choosing strictly among the offered options. You never explain."
        )
        self._choice_agent = Agent(
            model=model, system_prompt=system, structured_output_model=_Choice, name="decider"
        )
        self._yes_no_agent = Agent(
            model=model, system_prompt=system, structured_output_model=_YesNo, name="decider"
        )

    def choose(self, state: str, question: str, options: list[str]) -> Decision:
        prompt = f"State:\n{state}\n\nQuestion: {question}\nOptions: {json.dumps(options)}"
        result = self._choice_agent(prompt)
        out = result.structured_output
        if not isinstance(out, _Choice) or out.label not in options:
            return Decision(label=options[0], confidence=0.0)
        return Decision(label=out.label, confidence=out.confidence, scores={out.label: out.confidence})

    def yes_no(self, state: str, question: str) -> float:
        result = self._yes_no_agent(f"State:\n{state}\n\nQuestion: {question}")
        out = result.structured_output
        return out.probability_yes if isinstance(out, _YesNo) else 0.0
