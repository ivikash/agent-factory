app_name           = "agent-factory"
stage              = "staging"
handler            = "agent_factory.handler.handler"
runtime            = "python3.12"
log_retention_days = 7
memory_mb          = 1024
timeout_seconds    = 300
# observe-on-aws: thresholds are provisional until two weeks of traffic exist (set 2026-11-12).
error_rate_percent = 5
p99_latency_ms     = 60000
alert_email        = ""
