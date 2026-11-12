output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "function_arn" {
  value = aws_lambda_function.this.arn
}

output "function_version" {
  value = aws_lambda_function.this.version
}

output "health_url" {
  description = "Read by deploy-stage.yml after apply and handed to the bake as the health URL."
  value       = var.create_function_url ? aws_lambda_function_url.this[0].function_url : ""
}

output "log_group" {
  value = aws_cloudwatch_log_group.function.name
}

output "alarm_names" {
  description = "The three alarms the deploy bake watches."
  value       = module.observability.alarm_names
}

output "dashboard_name" {
  value = module.observability.dashboard_name
}

output "sns_topic_arn" {
  description = "Subscribe a pager or Slack here."
  value       = module.observability.sns_topic_arn
}
