# Observability

What is watched in production, why those numbers, and what to do when something fires. Generated
by the `observe-on-aws` skill on `2026-11-12`. Edit freely, it is yours.

## What is watched

Stage `staging and production`, Region `us-west-2 and us-east-1 (one set per Region)`, compute `Lambda`.

| Alarm | Fires when | Threshold | Evidence |
|---|---|---|---|
| `agent-factory-staging and production-us-west-2 and us-east-1 (one set per Region)-error-rate` | More than 5 (staging) / 2 (production)% of requests fail, 2 of 3 minutes | 5 (staging) / 2 (production)% | provisional, no traffic history on 2026-11-12 |
| `agent-factory-staging and production-us-west-2 and us-east-1 (one set per Region)-p99-latency` | p99 above 60,000 (staging) / 45,000 (production) ms, 2 of 3 minutes | 60,000 (staging) / 45,000 (production) ms | provisional: a factory run makes 3 to 5 Bedrock calls of a few seconds each, so a 45 s p99 is the symptom threshold, not a performance target |
| `agent-factory-staging and production-us-west-2 and us-east-1 (one set per Region)-throttles` | at least one invocation throttled, 2 of 3 minutes | 1 | Any is too many |

`agent-factory-staging and production-us-west-2 and us-east-1 (one set per Region)-health` is the one alarm that pages. It fires when any of the
three does, and notifies `the `sns_topic_arn` output of `infra/` per stage` (currently: no subscription yet, set `alert_email` in `infra/env/<stage>.tfvars`).

Thresholds were set without traffic history on 2026-11-12. Review them on 2026-11-26 against two weeks of data.

## Where to look

- Dashboard: `agent-factory-<stage>-<region>` in the CloudWatch console for `us-west-2 and us-east-1 (one set per Region)`. Thirty seconds every
  morning.
- Logs: group(s) `/aws/lambda/agent-factory-<stage>`, retention 7 in staging, 30 in production days.
- Traces: CloudWatch Transaction Search, filter `service.name = agent-factory`.
- Omni: not yet enabled. The telemetry is already in CloudWatch, so a Space can be created over it at any time (observe-on-aws, `omni.md`).

Every signal carries `service.version` = the deployed commit SHA, so a chart that changes shape at
a deploy names the commit.

## When an alarm fires

1. Open the dashboard. Which of the three is it, and when did it start?
2. Did a deploy happen then? `gh run list --workflow deploy.yml --limit 5`. If yes, roll back:
   `gh workflow run deploy.yml --ref <previous tag> -f stage=production`. Investigate after.
3. If not a deploy: the errors panel on the dashboard (or Omni) shows the failing requests. The
   trace for one of them shows where the time or the error is.
4. Stuck for more than 30 minutes: `operate-on-aws` runs an investigation with AWS DevOps Agent.
5. Afterwards, write three lines in this file under "Incidents": what, why, what changed.

## How telemetry flows

The application runs the OpenTelemetry SDK (ADOT), configured by environment variables
(`OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, sampler). On Lambda the ADOT layer (`AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`, Application Signals off) exports traces to the function's X-Ray receiver, and logs go to the function's log group as JSON. Strands emits a span per graph node, agent and model call. The alarms read the
Lambda's own metrics, which exist without any instrumentation.

## Changing things

- **A threshold:** `error_rate_percent` or `p99_latency_ms` in the observability module's
  variables, then apply. Write the new evidence in the table above.
- **Who gets paged:** subscribe to `the `sns_topic_arn` output of `infra/` per stage` (email, Slack via AWS Chatbot, a pager).
- **Sampling:** `OTEL_TRACES_SAMPLER_ARG` on the application. 0.1 in production is the default.
- **Retention:** `aws logs put-retention-policy`, or `retention_in_days` in the Terraform. Lowering
  it deletes older data.

## When to add more

From `architect-for-startups`: the first outage that takes more than 30 minutes to diagnose,
three or more services calling each other, a SOC 2 audit (90-day retention everywhere), or a
CloudWatch bill over $500 a month (audit log volume first). Not before.

## Incidents

| Date | What | Why | What changed |
|---|---|---|---|
