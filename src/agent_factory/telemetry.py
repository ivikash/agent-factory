"""OpenTelemetry for the factory, set up once per process.

Strands emits spans for every agent, model call and graph node on its own tracer. This module
decides where they go:

- ``OTEL_EXPORTER_OTLP_ENDPOINT`` set (a CloudWatch agent sidecar, or any collector): export OTLP.
- On Lambda the ADOT layer owns the exporter and the SDK; this module only adds the resource
  attributes and does not install a second exporter.
- Neither: a console exporter when ``OTEL_CONSOLE=1``, otherwise nothing, so a laptop run stays quiet.

Metrics follow the same switch. Logs stay on the process's logger; the collector or the Lambda log
group carries them.
"""

from __future__ import annotations

import logging
import os

from agent_factory.config import Settings

log = logging.getLogger(__name__)
_configured = False


def setup(settings: Settings | None = None) -> str:
    """Configure telemetry once. Returns which exporter was chosen, for the health endpoint."""
    global _configured
    if _configured:
        return os.environ.get("AGENT_FACTORY_TELEMETRY", "already configured")
    settings = settings or Settings()

    attrs = ",".join(f"{k}={v}" for k, v in settings.resource_attributes.items())
    existing = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = f"{existing},{attrs}" if existing else attrs
    os.environ.setdefault("OTEL_SERVICE_NAME", settings.app_name)

    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") and os.environ.get("AWS_LAMBDA_EXEC_WRAPPER"):
        choice = "adot-lambda-layer"
    elif os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from strands.telemetry import StrandsTelemetry

        StrandsTelemetry().setup_otlp_exporter().setup_meter(enable_otlp_exporter=True)
        choice = "otlp"
    elif os.environ.get("OTEL_CONSOLE") == "1":
        from strands.telemetry import StrandsTelemetry

        StrandsTelemetry().setup_console_exporter()
        choice = "console"
    else:
        choice = "none"

    os.environ["AGENT_FACTORY_TELEMETRY"] = choice
    _configured = True
    log.info("telemetry: %s, resource %s", choice, attrs)
    return choice
