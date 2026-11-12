"""Deterministic graph nodes: plain Python inside a Strands Graph.

A ``FunctionNode`` runs a function and wraps its text result the way an agent node would, so the
graph can route on it. The ``TriageNode`` is the gate: it asks the System 1 decider two questions and
writes a JSON verdict the edges read. No model call happens here unless the decider itself is a
model.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from strands.agent.agent_result import AgentResult
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.telemetry.metrics import EventLoopMetrics
from strands.types.content import ContentBlock, Message

from agent_factory.decider import SystemOne

INTENTS = ["feature", "bugfix", "question"]


def _task_text(task: Any) -> str:
    if isinstance(task, str):
        return task
    parts: list[str] = []
    for block in task:
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


class FunctionNode(MultiAgentBase):
    """Run ``func(task_text) -> str`` as a graph node."""

    def __init__(self, func: Callable[[str], str], name: str) -> None:
        super().__init__()
        self.func = func
        self.name = name

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> MultiAgentResult:
        started = time.monotonic()
        text = self.func(_task_text(task))
        elapsed_ms = int((time.monotonic() - started) * 1000)
        agent_result = AgentResult(
            stop_reason="end_turn",
            message=Message(role="assistant", content=[ContentBlock(text=text)]),
            metrics=EventLoopMetrics(),
            state={},
        )
        node = NodeResult(
            result=agent_result, execution_time=elapsed_ms, status=Status.COMPLETED, execution_count=1
        )
        return MultiAgentResult(
            status=Status.COMPLETED,
            results={self.name: node},
            execution_count=1,
            execution_time=elapsed_ms,
        )


@dataclass(frozen=True)
class Triage:
    """The gate's verdict, serialized into the triage node's output."""

    intent: str
    intent_confidence: float
    actionable: float
    confident: bool

    def to_json(self) -> str:
        return json.dumps(
            {
                "triage": {
                    "intent": self.intent,
                    "intent_confidence": round(self.intent_confidence, 3),
                    "actionable": round(self.actionable, 3),
                    "confident": self.confident,
                }
            }
        )

    @staticmethod
    def parse(text: str) -> Triage | None:
        """Read a verdict back out of a node's text. The graph's edges call this."""
        start = text.find('{"triage"')
        if start < 0:
            return None
        try:
            data = json.loads(text[start:])["triage"]
        except (ValueError, KeyError):
            # The verdict may be embedded in a larger node input; take the first balanced object.
            depth = 0
            for i, ch in enumerate(text[start:], start):
                depth += ch == "{"
                depth -= ch == "}"
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])["triage"]
                        break
                    except (ValueError, KeyError):
                        return None
            else:
                return None
        return Triage(
            intent=str(data["intent"]),
            intent_confidence=float(data["intent_confidence"]),
            actionable=float(data["actionable"]),
            confident=bool(data["confident"]),
        )


def triage(decider: SystemOne, request: str, floor: float) -> Triage:
    """Two System 1 questions: what kind of request, and is it actionable as written."""
    intent = decider.choose(request, "What kind of software request is this?", INTENTS)
    actionable = decider.yes_no(
        request, "Is this request specific enough to start building without asking a question?"
    )
    confident = intent.confident(floor) and actionable >= 0.5
    return Triage(
        intent=intent.label, intent_confidence=intent.confidence, actionable=actionable, confident=confident
    )


class TriageNode(FunctionNode):
    def __init__(self, decider: SystemOne, floor: float) -> None:
        super().__init__(lambda request: triage(decider, request, floor).to_json(), name="triage")
