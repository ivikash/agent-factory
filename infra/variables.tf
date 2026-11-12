# The pipeline contract (region, image_tag, image_uri, artifact_path) plus this
# root's own settings. Stage settings live in env/<stage>.tfvars.

variable "region" {
  description = "Region this apply targets. Supplied by the workflow as TF_VAR_region."
  type        = string
}

variable "image_tag" {
  description = "Commit SHA of the deployed version. Supplied by the workflow as TF_VAR_image_tag."
  type        = string
  default     = ""
}

variable "image_uri" {
  description = "Container image URI. Not used by this root, declared for the contract."
  type        = string
  default     = ""
}

variable "artifact_path" {
  description = "Local path to function.zip. Supplied by the workflow as TF_VAR_artifact_path."
  type        = string
}

variable "artifact_s3_bucket" {
  description = "Optional. Deploy the function code from this S3 bucket (same Region as the function) instead of uploading artifact_path inline."
  type        = string
  default     = ""
}

variable "artifact_s3_key" {
  description = "Object key of function.zip when artifact_s3_bucket is set."
  type        = string
  default     = ""
}

variable "app_name" {
  description = "Application name. Must match the bootstrap's app_name."
  type        = string
}

variable "stage" {
  description = "staging or production."
  type        = string
}

variable "handler" {
  description = "Function handler, e.g. app.handler."
  type        = string
}

variable "runtime" {
  description = "Lambda runtime identifier, e.g. python3.13 or nodejs22.x."
  type        = string
}

variable "architecture" {
  description = "x86_64 or arm64. Must match how build.sh built the zip's dependencies."
  type        = string
  default     = "x86_64"
}

variable "memory_mb" {
  type    = number
  default = 512
}

variable "timeout_seconds" {
  type    = number
  default = 30
}

variable "environment" {
  description = "Extra environment variables for the function."
  type        = map(string)
  default     = {}
}

variable "log_retention_days" {
  description = "7 in staging, 30 in production is the usual startup setting."
  type        = number
}

variable "adot_layer_arns" {
  description = "ADOT Python Lambda layer per Region. Source of truth: https://github.com/aws-otel/aws-otel.github.io/blob/main/src/config/lambdaLayerArns.js (read 2026-11-12)."
  type        = map(string)
  default = {
    "us-west-2" = "arn:aws:lambda:us-west-2:615299751070:layer:AWSOpenTelemetryDistroPython:36"
    "us-east-1" = "arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroPython:32"
  }
}

variable "bedrock_model_ids" {
  description = "Inference profile ids the function may invoke. Must cover MODEL_PLAN, MODEL_CODE, MODEL_REVIEW and MODEL_DECIDER."
  type        = list(string)
  default     = ["us.anthropic.claude-haiku-5-5"]
}

# observe-on-aws: the minimum set's two thresholds, grounded per stage in env/<stage>.tfvars.
variable "error_rate_percent" {
  description = "Alarm when function errors exceed this share of invocations."
  type        = number
}

variable "p99_latency_ms" {
  description = "Alarm when p99 duration exceeds this many milliseconds."
  type        = number
}

variable "alert_email" {
  description = "Where the composite alarm pages. Empty leaves the SNS topic without a subscription."
  type        = string
  default     = ""
}

variable "create_function_url" {
  description = "Create the function URL. False when something else fronts the function (API Gateway, an ALB) or the target environment has no function URLs."
  type        = bool
  default     = true
}

variable "function_url_auth" {
  description = "NONE for a public URL (the health check needs to reach it), AWS_IAM otherwise."
  type        = string
  default     = "NONE"

  validation {
    condition     = contains(["NONE", "AWS_IAM"], var.function_url_auth)
    error_message = "function_url_auth must be NONE or AWS_IAM."
  }
}
