# Announcements

Drafts for the launch. Facts in these posts are the ones verified on 2026-11-12 (test counts, tool
versions, prices). Update the numbers after the first production deploy and before posting.

## Blog post

### A Software Agent Factory on AWS, with a System 1 gate

Most agent demos spend a frontier model's tokens deciding things a classifier could decide. "Is this
a feature request or a bug?" "Is this request specific enough to act on?" Those are not reasoning
problems. They are fast, pattern-shaped choices, and the right tool for them is a small model that
answers in half a second with a calibrated confidence.

That is the idea behind Agent Factory, a small open-source project I built this week with the
[Strands Agents SDK](https://strandsagents.com): a graph of cheap Amazon Bedrock models that turns a
one-line software request into a plan, code and a review, with
[Strands Decider](https://github.com/strands-labs/strands-decider), a 2B "system one" model, at the
gate.

**How it works.** A request enters a Strands Graph. The first node asks the decider two questions:
what kind of request is this (feature, bugfix, question), and is it specific enough to build without
asking. The decider answers in about 700 ms on eight CPU cores, and every answer carries a
confidence. Below the floor (0.8 on intent, 0.5 on actionable), the graph routes to a clarify node
that asks three questions and stops. The floor came from measuring, not guessing: a precise feature
request scored 0.90, a precise bug report 0.97, "make it better" 0.44. Above it, the graph
runs plan, code and review on Claude Haiku 5.5, the cheap tier on Bedrock ($0.11 per million input
tokens), with the reviewer returning structured output so the revision loop is a deterministic edge
with a bound.

Every edge condition reads structured text a node wrote, never prose. The whole graph runs offline
in the test suite with deterministic nodes in place of the models, which is how 20 tests cover the
happy path, the clarify path, a bounded review loop and the Lambda handler in under a second.

**Production shape, not a notebook.** The factory runs as a Lambda function behind a function URL.
It deploys from GitHub Actions with OIDC (no access keys anywhere), to staging on every push to
`main` and to production on a `v*` tag, one Region at a time, with a health check and an alarm bake
after each deploy. OpenTelemetry traces leave through the ADOT Lambda layer, every span carries the
commit SHA as `service.version`, and three CloudWatch alarms (error rate, p99 latency, throttles)
page through one composite alarm and fail a deploy that regresses. CloudWatch Omni reads the same
telemetry once a Space exists, with no second pipeline.

**The part I did not expect.** The pipeline and the observability came from two new skills I
contributed to the AWS Agent Toolkit's `aws-startup-advisor` plugin, `deploy-from-github` and
`observe-on-aws`. Writing them as skills first, with offline Terraform tests and contract tests on
the workflow templates, made applying them to the agent a copy-and-fill exercise. The skills carry
the opinions (two stages not three, tag-gated production, one artifact promoted, thresholds grounded
in the service's own data), and the project inherits them.

**What it costs.** Under $5 a month for the pipeline's own resources, about $3 a month of CloudWatch
for a hello-world level of traffic, and Bedrock at cents per request. The decider runs locally for
development. In the cloud a cheap Bedrock model answers its two questions through structured output,
because a 2B model does not fit in a Lambda function.

Code: https://github.com/ivikash/agent-factory. The skills: the `deploy-from-github` and
`observe-on-aws` folders under `plugins/aws-startup-advisor/skills` in my fork of
aws/agent-toolkit-for-aws.

## X.com

Built a Software Agent Factory on AWS this week:

- Strands Graph of cheap Bedrock models (Claude Haiku 5.5): plan, code, review
- Strands Decider 2B at the gate: "feature or bug?" "specific enough?" in 700 ms on CPU with a calibrated confidence. Not confident? It asks instead of guessing
- Lambda + function URL, GitHub Actions with OIDC, staging on push, production on a tag, alarm bake per Region
- OpenTelemetry to CloudWatch, 3 alarms, 1 dashboard, Omni-ready

System 1 for the fast choices, System 2 for the slow ones. 20 offline tests, under $10 a month.

https://github.com/ivikash/agent-factory

## LinkedIn

I spent this week building something small and complete: a Software Agent Factory on AWS.

The idea: agents make dozens of tiny decisions per task, and most frameworks spend a frontier
model's tokens on each one. Strands Decider, a 2B open-weight "system one" model from Strands
Labs, answers those choices in under a second on a CPU with a calibrated confidence. So the factory
puts it at the gate. Two questions per request: what kind of request is this, and is it specific
enough to build. When the confidence is below the floor, the graph asks three clarifying questions
and stops. Above it, cheap Bedrock models (Claude Haiku 5.5) plan, write and review the code, with the review loop
bounded by a deterministic edge.

What made it feel like production rather than a demo:

- A Strands Graph where every edge reads structured output, so routing is testable offline. 20 tests run the real graph engine with deterministic nodes in under a second.
- GitHub Actions to AWS with OIDC and no access keys. Staging on every push, production on a version tag, one Region at a time, a health check and an alarm bake after each deploy, rollback by re-running an old tag.
- OpenTelemetry through the ADOT Lambda layer, three CloudWatch alarms that page through one composite alarm and fail a bad deploy, one dashboard, and CloudWatch Omni over the same telemetry.

The deployment and observability came from two skills I wrote for the AWS Agent Toolkit's
`aws-startup-advisor` plugin: `deploy-from-github` and `observe-on-aws`. Each ships with offline
Terraform tests and contract tests on its templates. Writing the opinions down once as skills, then
applying them, was faster than doing either by hand, and the project inherited decisions I would
otherwise have argued with myself about.

Repository: https://github.com/ivikash/agent-factory

## GitHub release note (v0.1.0)

### Agent Factory v0.1.0

A Strands Graph that turns a one-line software request into a plan, code and a review.

- **System 1 gate.** `TriageNode` asks Strands Decider 2B (over HTTP) or a Bedrock stand-in two
  questions and writes a JSON verdict. Below `DECIDER_CONFIDENCE_FLOOR` (0.8 on intent) or 0.5 on
  actionable, the graph routes to `clarify`.
- **System 2 workers.** `plan`, `code` and `review` on Claude Haiku 5.5 through Bedrock inference
  profiles. `plan` and `review` return structured output. The review loop is bounded by
  `MAX_REVIEW_ROUNDS`.
- **Runs as** a Lambda function behind a function URL (`GET /health`, `POST /`) and as a CLI
  (`agent-factory "..."`, `--triage-only` to see the gate's verdict without System 2 tokens).
- **Deploys** from GitHub Actions with OIDC: staging on push to `main`, production on `v*` tags,
  `us-west-2` then `us-east-1`, health check and alarm bake per Region.
- **Observability.** ADOT Lambda layer, `service.version` = commit SHA on every span, three alarms
  and a dashboard per stage and Region, CloudWatch Omni ready.

Verified: ruff clean, 20 tests, `terraform validate` and `terraform test` (3/3 observability, 5/5
bootstrap), actionlint and shellcheck clean, 29 MB Lambda zip built for x86_64.
