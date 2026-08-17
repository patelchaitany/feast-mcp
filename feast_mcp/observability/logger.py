"""Custom logger that fans out to stdout and (optionally) OpenTelemetry.

``configure_logging`` sets up the ``feast_mcp`` logger with a stdout handler
and, when enabled, an OTEL ``LoggingHandler`` that exports records via OTLP —
so the same log line is visible on the console *and* in your observability
backend. All server modules use ``logging.getLogger(__name__)`` (children of
``feast_mcp``), so they flow through this configuration automatically.

OpenTelemetry is an optional dependency. If the SDK/exporter is not installed
the server logs a warning and continues with stdout only.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

from feast_mcp.observability.config import LoggingConfig

#: Root logger name; every module logger is a child of this.
ROOT_LOGGER_NAME = "feast_mcp"

#: Third-party loggers whose output we adopt so their lines land on the same
#: console + OTEL handlers as our own. FastMCP (and the MCP SDK / uvicorn /
#: gunicorn it runs under) log to their own logger trees; without this bridge
#: those lines would either be dropped or formatted differently and never
#: reach the OpenTelemetry backend.
BRIDGED_LOGGERS = (
    "fastmcp",
    "mcp",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "gunicorn",
    "gunicorn.error",
    "gunicorn.access",
)

#: Kept so the exporter can be flushed/shut down cleanly.
_otel_provider = None


class JsonFormatter(logging.Formatter):
    """Minimal structured formatter for machine-readable stdout logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _build_formatter(fmt: str) -> logging.Formatter:
    if fmt == "json":
        return JsonFormatter()
    return logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")


def _parse_headers(headers: Optional[str]) -> Optional[dict]:
    """Parse ``k1=v1,k2=v2`` OTLP headers into a dict."""
    if not headers:
        return None
    result = {}
    for pair in headers.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
    return result or None


def _build_otel_handler(config: LoggingConfig) -> Optional[logging.Handler]:
    """Build the OTEL logging handler, or None if OTEL is unavailable."""
    global _otel_provider

    root = logging.getLogger(ROOT_LOGGER_NAME)
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        root.warning(
            "OTEL logging requested but the OpenTelemetry SDK is not installed; "
            "logging to stdio only. Install with: pip install 'feast-mcp[otel]'"
        )
        return None

    proto = config.otel_protocol
    headers = _parse_headers(config.otel_headers)
    try:
        if proto in ("http", "http/protobuf", "httpprotobuf"):
            from opentelemetry.exporter.otlp.proto.http._log_exporter import (
                OTLPLogExporter,
            )

            exporter = OTLPLogExporter(endpoint=config.otel_endpoint, headers=headers)
        else:
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
                OTLPLogExporter,
            )

            exporter = OTLPLogExporter(
                endpoint=config.otel_endpoint,
                insecure=config.otel_insecure,
                headers=headers,
            )
    except ImportError:
        root.warning(
            "OTEL exporter for protocol %r is not installed; logging to stdio "
            "only. Install with: pip install 'feast-mcp[otel]'",
            proto,
        )
        return None

    resource = Resource.create({"service.name": config.otel_service_name})
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)
    _otel_provider = provider

    return LoggingHandler(level=logging.NOTSET, logger_provider=provider)


def _apply_handlers(
    logger: logging.Logger,
    handlers: list[logging.Handler],
    level: int,
) -> None:
    """Reset ``logger`` to exactly ``handlers`` at ``level``. Idempotent.

    Handlers are *shared* across every logger we configure, so one console
    write and one OTEL export happen per record no matter which logger
    emitted it. ``propagate`` is turned off so a record isn't also handled
    by an ancestor (which would duplicate it).
    """
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    for handler in handlers:
        logger.addHandler(handler)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())


def configure_logging(config: LoggingConfig) -> logging.Logger:
    """Configure the ``feast_mcp`` logger from ``config``. Idempotent.

    Also bridges third-party loggers (FastMCP, MCP SDK, uvicorn, gunicorn)
    onto the same handlers so *their* output shows up on the console and in
    OpenTelemetry too.
    """
    level = getattr(logging, config.level, logging.INFO)
    formatter = _build_formatter(config.format)

    handlers: list[logging.Handler] = []

    if config.stdio:
        # stderr, not stdout: the MCP stdio transport reserves stdout for
        # JSON-RPC, so logging there would corrupt the protocol. stderr is
        # still shown on the console.
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        stream.setLevel(level)
        handlers.append(stream)

    if config.otel_enabled:
        otel_handler = _build_otel_handler(config)
        if otel_handler is not None:
            otel_handler.setLevel(level)
            handlers.append(otel_handler)

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    _apply_handlers(logger, handlers, level)

    # Route FastMCP / MCP SDK / uvicorn / gunicorn through the same handlers.
    for name in BRIDGED_LOGGERS:
        _apply_handlers(logging.getLogger(name), handlers, level)

    if config.otel_enabled and any(
        h
        for h in handlers
        if h is not None and h.__class__.__name__ == "LoggingHandler"
    ):
        logger.info(
            "OTEL log export enabled -> %s (%s)",
            config.otel_endpoint,
            config.otel_protocol,
        )

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger under the ``feast_mcp`` namespace."""
    if not name:
        return logging.getLogger(ROOT_LOGGER_NAME)
    if name == ROOT_LOGGER_NAME or name.startswith(ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def shutdown_logging() -> None:
    """Flush and shut down the OTEL exporter, if one was created."""
    global _otel_provider
    if _otel_provider is not None:
        try:
            _otel_provider.shutdown()
        finally:
            _otel_provider = None
