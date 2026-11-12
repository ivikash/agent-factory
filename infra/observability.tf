# observe-on-aws minimum set for this stage and Region: three alarms on the
# function's own metrics (error rate, p99 duration, throttles), one composite
# alarm that pages, one dashboard with the function's log group, retention set
# above on the log group. Alarm names carry <app>-<stage>-<region>-, which the
# deploy-stage.yml bake watches for 60 s (staging) or 300 s (production).

module "observability" {
  source = "./modules/observability"

  app_name           = var.app_name
  stage              = var.stage
  region             = var.region
  compute            = "lambda"
  function_name      = aws_lambda_function.this.function_name
  error_rate_percent = var.error_rate_percent
  p99_latency_ms     = var.p99_latency_ms
  alert_email        = var.alert_email
  otel_log_group     = aws_cloudwatch_log_group.function.name
}
