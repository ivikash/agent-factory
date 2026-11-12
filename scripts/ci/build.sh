#!/usr/bin/env bash
# Build the project. Two modes:
#
#   build.sh check    lint, test, build. Publishes nothing. Needs no AWS sign-in.
#   build.sh publish  build the deployable artifact and publish it:
#                       container  -> push to the ECR repository ECR_REPOSITORY:IMAGE_TAG
#                                     in every Region listed in REGIONS (JSON array)
#                       zip        -> upload to s3://<ARTIFACT_BUCKET>/<APP_NAME>/<IMAGE_TAG>/function.zip
#
# The artifact kind comes from the repository: a Dockerfile means container, otherwise
# the build produces dist/function.zip. DEPLOY_TARGET=lambda always means zip.
#
# This file is the one place the pipeline calls into the project. Edit the three
# functions marked PROJECT to match how this project lints, tests, and builds.
# Everything else is the publishing contract and should not need changes.
set -euo pipefail

MODE="${1:-}"
case "$MODE" in
  check|publish) ;;
  *) echo "usage: $0 check|publish" >&2; exit 2 ;;
esac

# ---- PROJECT: this is a uv project. uv is installed on the runner if missing. --
ensure_uv() {
  command -v uv >/dev/null 2>&1 && return
  python3 -m pip install --quiet --user uv
  export PATH="$HOME/.local/bin:$PATH"
}

# ---- PROJECT: lint ---------------------------------------------------------
project_lint() {
  ensure_uv
  uv sync --all-groups --quiet
  uv run ruff format --check .
  uv run ruff check .
}

# ---- PROJECT: test ---------------------------------------------------------
project_test() {
  ensure_uv
  uv run pytest -q
}

# ---- PROJECT: build the zip ------------------------------------------------
# Lambda runtime python3.12. Dependencies are resolved for the Lambda platform
# (LAMBDA_PLATFORM, default x86_64-manylinux2014; aarch64-manylinux2014 for Graviton),
# not for the machine running this script, then the package itself is added.
project_build_zip() {
  ensure_uv
  rm -rf dist build/zip
  mkdir -p dist build/zip
  # Dependencies as wheels for the Lambda platform, then this package built once as a wheel.
  uv export --no-dev --no-emit-project --no-hashes --quiet -o build/requirements.txt
  uv pip install --quiet --target build/zip --python-version 3.12 \
    --python-platform "${LAMBDA_PLATFORM:-x86_64-manylinux2014}" --only-binary :all: -r build/requirements.txt
  uv build --wheel --quiet -o build/wheel
  uv pip install --quiet --target build/zip --python-version 3.12 --no-deps build/wheel/*.whl
  find build/zip -name '__pycache__' -type d -prune -exec rm -rf {} +
  (cd build/zip && zip -qr ../../dist/function.zip .)
  echo "built dist/function.zip ($(du -h dist/function.zip | cut -f1))"
}

# ---- publishing contract ---------------------------------------------------
artifact_kind() {
  if [[ "${DEPLOY_TARGET:-}" == "lambda" ]]; then echo zip
  elif [[ -f Dockerfile ]]; then echo container
  else echo zip
  fi
}

require() {
  local name
  for name in "$@"; do
    [[ -n "${!name:-}" ]] || { echo "::error::$name is not set" >&2; exit 1; }
  done
}

publish_container() {
  require ECR_REPOSITORY IMAGE_TAG REGIONS
  local account_id
  account_id="$(aws sts get-caller-identity --query Account --output text)"
  local built=0 region registry image
  # Same local image pushed to every Region: identical bits, no replication lag.
  for region in $(echo "$REGIONS" | jq -r '.[]'); do
    registry="${account_id}.dkr.ecr.${region}.amazonaws.com"
    image="${registry}/${ECR_REPOSITORY}:${IMAGE_TAG}"
    aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry" >/dev/null
    # Tags are immutable in the bootstrap's repositories: an existing tag means
    # this commit was already published to this Region. Never rebuild it.
    if aws ecr describe-images --region "$region" --repository-name "$ECR_REPOSITORY" \
        --image-ids "imageTag=${IMAGE_TAG}" >/dev/null 2>&1; then
      echo "already published: $image"
      continue
    fi
    if (( built == 0 )); then
      docker build \
        --label "org.opencontainers.image.revision=${IMAGE_TAG}" \
        --label "org.opencontainers.image.source=${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}" \
        -t "local/${ECR_REPOSITORY}:${IMAGE_TAG}" .
      built=1
    fi
    docker tag "local/${ECR_REPOSITORY}:${IMAGE_TAG}" "$image"
    docker push "$image"
    echo "published $image"
  done
}

publish_zip() {
  require ARTIFACT_BUCKET APP_NAME IMAGE_TAG
  local key="${APP_NAME}/${IMAGE_TAG}/function.zip"
  if aws s3api head-object --bucket "$ARTIFACT_BUCKET" --key "$key" >/dev/null 2>&1; then
    echo "artifact already published: s3://${ARTIFACT_BUCKET}/${key}"
    return
  fi
  project_build_zip
  aws s3 cp dist/function.zip "s3://${ARTIFACT_BUCKET}/${key}" --only-show-errors
  echo "published s3://${ARTIFACT_BUCKET}/${key}"
}

project_lint
project_test

if [[ "$MODE" == "check" ]]; then
  case "$(artifact_kind)" in
    container) docker build -t "local/check:${GITHUB_SHA:-dev}" . ;;
    zip)       project_build_zip ;;
  esac
  echo "check passed"
  exit 0
fi

case "$(artifact_kind)" in
  container) publish_container ;;
  zip)       publish_zip ;;
esac
