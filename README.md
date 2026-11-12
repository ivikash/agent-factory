# Agent Factory

A Software Agent Factory on AWS: a one-line request goes in, a plan, code and a review come out.
Built with the [Strands Agents SDK](https://strandsagents.com) as a **Graph** of cheap Amazon
Bedrock models, with **Strands Decider**, a 2B "system one" decision model, making the fast choices
at the gate.

```
request ──▶ triage (System 1) ──┬─ confident ──▶ plan ──▶ code ──▶ review ──┬─ approved ──▶ publish
                                │                          ▲                 │
                                │                          └── revision ─────┘  (bounded)
                                └─ not confident ──▶ clarify ──▶ publish
```

- **System 1 at the gate.** The triage node asks the decider two questions: what kind of request is
  this (feature, bugfix, question), and is it specific enough to build without asking. Every answer
  carries a calibrated confidence. Below 0.9 the factory asks three clarifying questions instead of
  spending model tokens on a guess.
- **System 2 in the nodes.** Claude Haiku 5.5 on Bedrock plans, writes and reviews. The reviewer
  returns structured output, so the review loop is a deterministic edge, bounded by
  `MAX_REVIEW_ROUNDS`.
- **Deterministic routing.** Every edge condition reads structured text a node wrote, never prose.
- **Production shape.** A Lambda function behind a function URL (`GET /health`, `POST /`), deployed
  from GitHub Actions to staging on every push and to production on a `v*` tag, with OpenTelemetry
  traces, metrics and logs in CloudWatch, three alarms that gate every deploy, and CloudWatch Omni on
  the same telemetry. See [DEPLOYMENT.md](DEPLOYMENT.md) and [OBSERVABILITY.md](OBSERVABILITY.md).

## Run it locally

```sh
uv sync --all-groups
uv run pytest                      # offline: the real Strands graph engine with deterministic nodes

# System 1 with the real decider (CPU is fine, about half a second per question)
uv run --extra decider strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8000 &
export DECIDER_URL=http://localhost:8000

# System 2 needs AWS credentials with Bedrock access to Claude Haiku 5.5 in your Region
export AWS_REGION=us-west-2
uv run agent-factory "add a /health endpoint to the Flask app in app.py"
```

Without `DECIDER_URL`, a cheap Bedrock model answers the gate's questions through structured output.
That is what the Lambda deployment uses, because a 2B model does not fit in a function.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `MODEL_PLAN`, `MODEL_CODE`, `MODEL_REVIEW` | `us.anthropic.claude-haiku-5-5` | Bedrock inference profile per role |
| `DECIDER_URL` | empty | Strands Decider server. Empty means the Bedrock stand-in. |
| `DECIDER_CONFIDENCE_FLOOR` | `0.9` | Below this, clarify instead of build |
| `MAX_REVIEW_ROUNDS` | `2` | Review loop bound |
| `GRAPH_TIMEOUT_S` | `240` | Whole-graph timeout |
| `STAGE`, `SERVICE_VERSION` | `local`, `dev` | Set by the deploy pipeline; carried on every trace |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Export OTLP to a collector. On Lambda the ADOT layer owns this. |

## Layout

```
src/agent_factory/   config, decider (System 1), nodes, factory (the graph), telemetry, handler, cli
tests/               offline tests: graph routing, loop bounds, decider client, handler, config
infra/               Terraform: the Lambda root (deploy-from-github contract) and the observability module
infra/bootstrap/     once per account: OIDC provider, roles, state bucket, artifact bucket
.github/workflows/   ci.yml, deploy.yml, deploy-stage.yml
scripts/ci/          build, wait-for-artifact, verify-deploy, set-github-variables
```

## License

MIT.
