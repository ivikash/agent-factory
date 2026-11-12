"""AWS Lambda handler behind a function URL.

    GET  /health          -> 200 {"status":"ok", ...}      (the deploy pipeline's health check)
    POST /                -> run the factory on {"request": "..."}
    anything else         -> 404

The graph is built once per execution environment and reused across invocations. Errors return a
JSON body with a request id and never a stack trace.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from agent_factory import telemetry
from agent_factory.config import Settings
from agent_factory.factory import build_graph, run

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(message)s")
log = logging.getLogger(__name__)

_settings = Settings()
_telemetry = telemetry.setup(_settings)
_graph = None

MAX_REQUEST_CHARS = 4000


def _graph_instance():
    global _graph
    if _graph is None:
        _graph = build_graph(_settings)
    return _graph


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def _log(event_name: str, **fields: Any) -> None:
    log.info(json.dumps({"event": event_name, "service.version": _settings.service_version, **fields}))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = event.get("rawPath", "/")
    request_id = getattr(context, "aws_request_id", "local")

    if method == "GET" and path == "/health":
        return _response(
            200,
            {
                "status": "ok",
                "version": _settings.service_version,
                "stage": _settings.stage,
                "telemetry": _telemetry,
            },
        )

    if method != "POST" or path != "/":
        return _response(404, {"error": "not found", "request_id": request_id})

    try:
        payload = json.loads(event.get("body") or "{}")
    except ValueError:
        return _response(400, {"error": "body must be JSON", "request_id": request_id})
    request = str(payload.get("request", "")).strip()
    if not request:
        return _response(400, {"error": "request is required", "request_id": request_id})
    if len(request) > MAX_REQUEST_CHARS:
        return _response(
            413, {"error": f"request longer than {MAX_REQUEST_CHARS} characters", "request_id": request_id}
        )

    started = time.monotonic()
    try:
        outcome = run(request, graph=_graph_instance(), settings=_settings)
    except Exception as exc:  # noqa: BLE001 - the caller gets a request id, the log gets the type
        _log(
            "factory.failed",
            request_id=request_id,
            error_type=type(exc).__name__,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
        log.exception("factory run failed")
        return _response(
            502, {"error": "the factory could not complete this request", "request_id": request_id}
        )

    _log(
        "factory.completed",
        request_id=request_id,
        status=outcome.status,
        path=outcome.path,
        elapsed_ms=outcome.execution_ms,
    )
    return _response(200, {"request_id": request_id, **outcome.to_dict()})
