app_name           = "agent-factory"
stage              = "production"
handler            = "agent_factory.handler.handler"
runtime            = "python3.12"
log_retention_days = 30
memory_mb          = 1024
timeout_seconds    = 300
# observe-on-aws: thresholds are provisional until two weeks of traffic exist (set 2026-11-12).
error_rate_percent = 2
p99_latency_ms     = 45000
alert_email        = ""
