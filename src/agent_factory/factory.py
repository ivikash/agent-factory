"""The factory: a Strands Graph with a System 1 gate and cheap System 2 workers.

    request ──▶ triage (decider) ──┬─ confident ──▶ plan ──▶ code ──▶ review ──┬─ approved ──▶ publish
                                   │                          ▲                 │
                                   │                          └── revision ─────┘ (bounded)
                                   └─ not confident ──▶ clarify ──▶ publish

Every edge condition reads structured text a node wrote, never free prose, so routing is
deterministic. The review loop is bounded by ``max_review_rounds`` through the graph's execution
limit, so a reviewer that never approves cannot spend money forever.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel
from strands.multiagent import GraphBuilder
from strands.multiagent.base import Status
from strands.multiagent.graph import GraphState

from agent_factory.config import Settings
from agent_factory.decider import BedrockDecider, HttpDecider, SystemOne
from agent_factory.nodes import FunctionNode, Triage, TriageNode

log = logging.getLogger(__name__)


class Plan(BaseModel):
    summary: str = Field(description="One sentence: what will be built.")
    language: str = Field(description="Programming language, lower case, e.g. python.")
    files: list[str] = Field(description="File paths to create, relative, at most five.")
    acceptance: list[str] = Field(description="Observable checks a reviewer can verify, at most five.")


class Review(BaseModel):
    verdict: str = Field(description="approved or revision needed")
    findings: list[str] = Field(description="Specific problems, empty when approved.")


def _node_text(node: Any) -> str:
    """The text a node produced, whether it is an agent or a FunctionNode (one nested result)."""
    result = node.result
    inner = getattr(result, "results", None)
    if isinstance(inner, dict) and len(inner) == 1:
        return str(next(iter(inner.values())).result)
    return str(result)


def _text_of(state: GraphState, node_id: str) -> str:
    node = state.results.get(node_id)
    return _node_text(node) if node else ""


def _triage_of(state: GraphState) -> Triage | None:
    return Triage.parse(_text_of(state, "triage"))


def is_confident(state: GraphState) -> bool:
    verdict = _triage_of(state)
    return bool(verdict and verdict.confident)


def needs_clarification(state: GraphState) -> bool:
    verdict = _triage_of(state)
    return bool(verdict and not verdict.confident)


def _review_verdict(state: GraphState) -> str:
    text = _text_of(state, "review").lower()
    if "revision needed" in text:
        return "revision needed"
    if "approved" in text:
        return "approved"
    return ""


def is_approved(state: GraphState) -> bool:
    return _review_verdict(state) == "approved"


def needs_revision(state: GraphState) -> bool:
    return _review_verdict(state) == "revision needed"


def _agent(
    model_id: str, settings: Settings, name: str, system_prompt: str, output: type[BaseModel] | None = None
) -> Agent:
    model = BedrockModel(
        model_id=model_id, region_name=settings.region, max_tokens=settings.max_tokens, temperature=0.2
    )
    return Agent(
        model=model,
        name=name,
        system_prompt=system_prompt,
        structured_output_model=output,
        callback_handler=None,
        trace_attributes={
            "deployment.environment.name": settings.stage,
            "service.version": settings.service_version,
        },
    )


def make_decider(settings: Settings) -> SystemOne:
    if settings.decider_url:
        log.info("system one: strands decider at %s", settings.decider_url)
        return HttpDecider(settings.decider_url, timeout_s=settings.decider_timeout_s)
    log.info("system one: bedrock stand-in %s", settings.decider_model_id)
    return BedrockDecider(settings.decider_model_id, settings.region)


def publish(text: str) -> str:
    """The last node: a stable envelope the handler returns as is."""
    return json.dumps({"published": True, "length": len(text)})


def build_graph(
    settings: Settings | None = None, decider: SystemOne | None = None, agents: dict[str, Any] | None = None
):
    """Wire the graph. ``decider`` and ``agents`` are injectable so tests run without a model."""
    settings = settings or Settings()
    decider = decider or make_decider(settings)
    agents = agents or {
        "clarify": _agent(
            settings.plan_model_id,
            settings,
            "clarify",
            "The request is not specific enough to build. Ask the three most useful clarifying questions, "
            "as a numbered list, and nothing else.",
        ),
        "plan": _agent(
            settings.plan_model_id,
            settings,
            "planner",
            "You plan small software changes. Keep the plan to what the request asks for, no extras. "
            "Prefer the standard library. Name real file paths.",
            Plan,
        ),
        "code": _agent(
            settings.code_model_id,
            settings,
            "coder",
            "You write the code the plan describes, complete and runnable, with a short test. "
            "Output each file as a fenced block whose first line is a comment with the file path. "
            "When the input contains review findings, fix every finding.",
        ),
        "review": _agent(
            settings.review_model_id,
            settings,
            "reviewer",
            "You review code against the plan's acceptance checks. Be specific. "
            "Say 'approved' only when every acceptance check is met and the code would run.",
            Review,
        ),
    }

    builder = GraphBuilder()
    builder.add_node(TriageNode(decider, settings.confidence_floor), "triage")
    builder.add_node(agents["clarify"], "clarify")
    builder.add_node(agents["plan"], "plan")
    builder.add_node(agents["code"], "code")
    builder.add_node(agents["review"], "review")
    builder.add_node(FunctionNode(publish, "publish"), "publish")

    builder.add_edge("triage", "plan", condition=is_confident)
    builder.add_edge("triage", "clarify", condition=needs_clarification)
    builder.add_edge("plan", "code")
    builder.add_edge("code", "review")
    builder.add_edge("review", "code", condition=needs_revision)
    builder.add_edge("review", "publish", condition=is_approved)
    builder.add_edge("clarify", "publish")
    builder.set_entry_point("triage")

    # triage + plan + (code + review) * rounds + publish, plus one for the clarify path.
    builder.set_max_node_executions(4 + 2 * settings.max_review_rounds)
    builder.set_execution_timeout(settings.graph_timeout_s)
    builder.reset_on_revisit(True)
    return builder.build()


@dataclass(frozen=True)
class Outcome:
    status: str
    path: list[str]
    triage: Triage | None
    output: str
    execution_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "path": self.path,
            "triage": None if self.triage is None else json.loads(self.triage.to_json())["triage"],
            "output": self.output,
            "execution_ms": self.execution_ms,
        }


def run(request: str, graph=None, settings: Settings | None = None) -> Outcome:
    """Run one request through the factory and return a flat outcome."""
    graph = graph or build_graph(settings)
    result = graph(request)
    path = [node.node_id for node in result.execution_order]
    final = "clarify" if "clarify" in path else "code"
    output = _node_text(result.results[final]) if final in result.results else ""
    triage_text = _node_text(result.results["triage"]) if "triage" in result.results else ""
    return Outcome(
        status="completed" if result.status == Status.COMPLETED else result.status.value,
        path=path,
        triage=Triage.parse(triage_text),
        output=output,
        execution_ms=result.execution_time,
    )
