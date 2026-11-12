#!/usr/bin/env bash
# Run the whole deploy pipeline against AWS Emulator, locally, with no AWS account and
# no GitHub: bootstrap both stages, build and publish the artifact, deploy staging to
# every Region, then production Region by Region, then verify the observability.
#
# What this proves: the Terraform roots apply, the scripts the workflows call behave,
# the alarms, composite, dashboard, topic and log groups exist with the right names,
# the function answers /health and a request, and the bake passes against real
# DescribeAlarms calls. What it cannot prove: Bedrock answers (the emulator returns a
# fixed sentence), function URLs (not emulated), vended Lambda metrics and Omni.
#
# Prerequisites: the emulator running on 127.0.0.1:9297 (see the aws-emulator skill),
# terraform >= 1.11, uv, jq, zip.
#
# The emulator run needs two deviations from the real pipeline, both temporary files
# this script writes and removes:
#   * hashicorp/aws ~> 5.100 instead of ~> 6.0. Provider 6 reads S3 bucket tags
#     through S3 Control with an account-id-prefixed hostname
#     (000000000000.127.0.0.1), which no emulator endpoint can serve.
#   * no function URL (create_function_url = false); health is checked with Invoke.
#   * function code from S3 (artifact_s3_bucket) because the emulator rejects a 29 MB
#     inline zip with HTTP 413; real Lambda accepts up to 50 MB inline.
#   * no ADOT layer (adot_layer_arns = {}): AWS's public layer does not exist in the
#     emulator, so the function runs without the OpenTelemetry wrapper.
#   * one Region (EMU_REGIONS, default us-west-2): the emulator keeps one namespace for
#     Lambda, Logs and CloudWatch across Regions, so a second Region collides on names.
#
# Two things the emulator cannot do, and this script says so instead of pretending:
#   * run this function's code. Its Lambda runtime is RustPython, which cannot load
#     CPython native extensions, and Strands needs pydantic_core. Step 3b runs the same
#     handler on the host against the emulator's Bedrock endpoint instead.
#   * CloudWatch Omni (ListDomains is scaffolded, not implemented).
set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT=$(pwd)
PORT="${EMULATOR_PORT:-9297}"
ENV_FILE="$HOME/.aws/emulator/$PORT.env"
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE: start the emulator first (aws-emulator skill, connect.md)" >&2; exit 2; }
# shellcheck source=/dev/null
. "$ENV_FILE"
export AWS_ENDPOINT_URL_S3="$AWS_ENDPOINT_URL" TF_IN_AUTOMATION=1 TF_INPUT=0

APP_NAME=agent-factory
read -r -a REGIONS <<< "${EMU_REGIONS:-us-west-2}"
PRIMARY_REGION=us-west-2
SHA=$(git rev-parse HEAD)
EMU_MODEL="${EMU_MODEL:-anthropic.claude-haiku-4-5-20251001-v1:0}"   # a model id the emulator knows
LOG="$ROOT/.aws-emulator/e2e-$(date -u +%Y%m%dT%H%M%SZ).log"
mkdir -p "$(dirname "$LOG")"

say() { printf '\n==> %s\n' "$*" | tee -a "$LOG"; }
run() { "$@" 2>&1 | tee -a "$LOG"; }

OVERRIDES=()
override() {
  local dir="$1" f="$1/zz_emulator_override.tf"
  cat > "$f" <<'EOF'
# Written by scripts/dev/emulator-e2e.sh for the emulator run only. Removed on exit.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
  }
}
EOF
  OVERRIDES+=("$f")
  # Provider 5 and 6 share the lock file name; a 6.x lock blocks the 5.x override.
  rm -f "$dir/.terraform.lock.hcl"
}
cleanup() {
  for f in "${OVERRIDES[@]:-}"; do [[ -n "$f" ]] && rm -f "$f"; done
  find "$ROOT/infra" -name .terraform.lock.hcl -delete
}
trap cleanup EXIT
override infra/bootstrap
override infra/bootstrap/modules/ecr-regional
override infra
override infra/modules/observability

# ---- 1. bootstrap, once per stage (single account) ----------------------------------
say "1. bootstrap: staging then production (emulator account $(aws sts get-caller-identity --query Account --output text))"
pushd infra/bootstrap >/dev/null
run terraform init -input=false -upgrade >/dev/null; terraform get -update >/dev/null
for stage in staging production; do
  terraform workspace select "emu-$stage" >/dev/null 2>&1 || terraform workspace new "emu-$stage" >/dev/null
  run terraform apply -input=false -auto-approve -no-color -var-file="env/$stage.tfvars" | grep -E "Apply complete|Error" || true
  terraform output -json > "$ROOT/.aws-emulator/bootstrap-$stage.json"
done
popd >/dev/null
ARTIFACT_BUCKET=$(jq -r .artifact_bucket.value .aws-emulator/bootstrap-staging.json)
STATE_STAGING=$(jq -r .state_bucket.value .aws-emulator/bootstrap-staging.json)
STATE_PRODUCTION=$(jq -r .state_bucket.value .aws-emulator/bootstrap-production.json)
say "roles: $(aws iam list-roles --query 'Roles[].RoleName' --output text | tr '\t' ' ')"
say "subject trusted by production: $(jq -r .deploy_role_trusts.value .aws-emulator/bootstrap-production.json)"

# ---- 2. build once, publish to the artifact bucket (what deploy.yml's build job does) -----------
say "2. build and publish artifact $SHA"
LAMBDA_PLATFORM=aarch64-manylinux2014 APP_NAME=$APP_NAME DEPLOY_TARGET=terraform \
  REGIONS='["us-west-2","us-east-1"]' ARTIFACT_BUCKET=$ARTIFACT_BUCKET IMAGE_TAG=$SHA \
  run ./scripts/ci/build.sh publish | tail -3

# ---- 3. deploy one stage to one Region (what deploy-stage.yml does) --------------------------
deploy_stage() {
  local stage="$1" region="$2" bucket="$3" tmp
  tmp=$(mktemp -d)
  say "3. deploy $stage $region"
  GITHUB_OUTPUT="$tmp/out" RUNNER_TEMP="$tmp" APP_NAME=$APP_NAME DEPLOY_TARGET=terraform \
    ARTIFACT_BUCKET=$ARTIFACT_BUCKET IMAGE_TAG=$SHA REGION=$region WAIT_SECONDS=30 \
    run ./scripts/ci/wait-for-artifact.sh | tail -1
  local artifact_path
  artifact_path=$(grep '^artifact_path=' "$tmp/out" | cut -d= -f2-)

  pushd infra >/dev/null
  rm -rf .terraform
  run terraform init -input=false -reconfigure -no-color \
    -backend-config="bucket=$bucket" \
    -backend-config="key=$APP_NAME/$stage/$region/terraform.tfstate" \
    -backend-config="region=$PRIMARY_REGION" \
    -backend-config="use_lockfile=true" \
    -backend-config="encrypt=true" \
    -backend-config="skip_credentials_validation=true" \
    -backend-config="skip_requesting_account_id=true" \
    -backend-config="use_path_style=true" >/dev/null
  TF_VAR_region=$region TF_VAR_image_tag=$SHA TF_VAR_artifact_path=$artifact_path \
  TF_VAR_architecture=arm64 TF_VAR_create_function_url=false \
  TF_VAR_artifact_s3_bucket=$ARTIFACT_BUCKET TF_VAR_artifact_s3_key="$APP_NAME/$SHA/function.zip" \
  TF_VAR_adot_layer_arns='{}' \
  TF_VAR_bedrock_model_ids="[\"$EMU_MODEL\"]" \
  TF_VAR_environment="{\"MODEL_PLAN\":\"$EMU_MODEL\",\"MODEL_CODE\":\"$EMU_MODEL\",\"MODEL_REVIEW\":\"$EMU_MODEL\",\"MODEL_DECIDER\":\"$EMU_MODEL\",\"AWS_ENDPOINT_URL\":\"$AWS_ENDPOINT_URL\"}" \
    run terraform apply -input=false -auto-approve -no-color -var-file="env/$stage.tfvars" | grep -E "Apply complete|Error|^Plan" || true
  terraform output -json > "$tmp/tf.json"
  popd >/dev/null

  local fn
  fn=$(jq -r .function_name.value "$tmp/tf.json")
  say "   invoke $fn in $region (the emulator's RustPython runtime cannot import pydantic_core; the invoke itself and its metric are what this checks)"
  aws lambda invoke --region "$region" --function-name "$fn" --cli-binary-format raw-in-base64-out \
    --payload '{"rawPath":"/health","requestContext":{"http":{"method":"GET"}}}' "$tmp/health.json" \
    --query '[StatusCode,FunctionError]' --output text | tee -a "$LOG"
  run head -c 160 "$tmp/health.json"; echo
  say "   3b. the same handler on the host, pointed at the emulator's Bedrock (System 2 plumbing end to end)"
  (
    cd "$ROOT"
    export APP_NAME STAGE=$stage SERVICE_VERSION=$SHA AWS_REGION=$region AWS_DEFAULT_REGION=$region \
      MODEL_PLAN=$EMU_MODEL MODEL_CODE=$EMU_MODEL MODEL_REVIEW=$EMU_MODEL MODEL_DECIDER=$EMU_MODEL LOG_LEVEL=WARNING
    uv run --quiet python - <<'PY' 2>/dev/null | tee -a "$LOG"
import json
from agent_factory import handler
class Ctx: aws_request_id = "emulator-e2e"
ev = {"rawPath": "/health", "requestContext": {"http": {"method": "GET"}}}
print("health:", handler.handler(ev, Ctx())["body"])
ev = {"rawPath": "/", "requestContext": {"http": {"method": "POST"}}, "body": json.dumps({"request": "add a /health endpoint to app.py"})}
r = handler.handler(ev, Ctx()); b = json.loads(r["body"])
print("request:", r["statusCode"], "status", b.get("status"), "path", b.get("path"))
print("output:", (b.get("output") or b.get("error"))[:160].replace("\n", " "))
PY
  )

  say "   bake: $(jq -r '.alarm_names.value | join(", ")' "$tmp/tf.json")"
  GITHUB_OUTPUT="$tmp/out2" GITHUB_STEP_SUMMARY="$tmp/summary" APP_NAME=$APP_NAME STAGE=$stage REGION=$region \
    BAKE_SECONDS=5 run ./scripts/ci/verify-deploy.sh | tail -3
}

# staging: every Region (parallel in the workflow, sequential here for readable logs)
for region in "${REGIONS[@]}"; do deploy_stage staging "$region" "$STATE_STAGING"; done
# production: the tag run checks the artifact first, then one Region at a time
say "check-artifact (tag run): artifact for $SHA must already exist"
GITHUB_OUTPUT=/dev/null APP_NAME=$APP_NAME DEPLOY_TARGET=terraform ARTIFACT_BUCKET=$ARTIFACT_BUCKET \
  IMAGE_TAG=$SHA REGION=$PRIMARY_REGION WAIT_SECONDS=0 run ./scripts/ci/wait-for-artifact.sh
for region in "${REGIONS[@]}"; do deploy_stage production "$region" "$STATE_PRODUCTION"; done

# ---- 4. observability, as the observe-on-aws verifying.md checks it -----------------------
say "4. observability inventory"
for region in "${REGIONS[@]}"; do
  echo "--- $region ---" | tee -a "$LOG"
  run aws cloudwatch describe-alarms --region "$region" --alarm-name-prefix "$APP_NAME-" \
    --query 'MetricAlarms[].[AlarmName,StateValue,Threshold]' --output text
  run aws cloudwatch describe-alarms --region "$region" --alarm-name-prefix "$APP_NAME-" --alarm-types CompositeAlarm \
    --query 'CompositeAlarms[].[AlarmName,StateValue]' --output text
  run aws cloudwatch list-dashboards --region "$region" --query 'DashboardEntries[].DashboardName' --output text
  run aws sns list-topics --region "$region" --query 'Topics[].TopicArn' --output text
  run aws logs describe-log-groups --region "$region" --log-group-name-prefix "/aws/lambda/$APP_NAME" \
    --query 'logGroups[].[logGroupName,retentionInDays]' --output text
done

say "5. alarm drill in production $PRIMARY_REGION: force error-rate to ALARM, the composite must follow"
aws cloudwatch set-alarm-state --region "$PRIMARY_REGION" --alarm-name "$APP_NAME-production-$PRIMARY_REGION-error-rate" \
  --state-value ALARM --state-reason "emulator e2e drill"
sleep 3
run aws cloudwatch describe-alarms --region "$PRIMARY_REGION" --alarm-name-prefix "$APP_NAME-production-$PRIMARY_REGION-" \
  --alarm-types MetricAlarm CompositeAlarm --query '[MetricAlarms[].[AlarmName,StateValue],CompositeAlarms[].[AlarmName,StateValue]]' --output text
say "   bake during the drill must FAIL"
if GITHUB_OUTPUT=/dev/null GITHUB_STEP_SUMMARY=/dev/null APP_NAME=$APP_NAME STAGE=production REGION=$PRIMARY_REGION BAKE_SECONDS=0 \
    ./scripts/ci/verify-deploy.sh >>"$LOG" 2>&1; then echo "UNEXPECTED: bake passed with a firing alarm" | tee -a "$LOG"; exit 1
else echo "bake failed as designed (exit $?)" | tee -a "$LOG"; fi
aws cloudwatch set-alarm-state --region "$PRIMARY_REGION" --alarm-name "$APP_NAME-production-$PRIMARY_REGION-error-rate" \
  --state-value OK --state-reason "emulator e2e drill over"

say "6. metrics: Lambda Invocations in $PRIMARY_REGION over the last 15 minutes"
run aws cloudwatch get-metric-statistics --region "$PRIMARY_REGION" --namespace AWS/Lambda --metric-name Invocations \
  --dimensions Name=FunctionName,Value="$APP_NAME-production" \
  --start-time "$(date -u -d '-15 min' +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" --period 300 --statistics Sum \
  --query 'Datapoints[].Sum' --output text

say "done. log: $LOG"
