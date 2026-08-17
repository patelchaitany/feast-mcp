"""Observability for the Feast MCP server: logging fanned out to stdout and OTEL.

    from feast_mcp.observability import configure_logging, load_logging_config, get_logger

    configure_logging(load_logging_config())
    log = get_logger(__name__)
    log.info("hello")   # -> stdout and, if configured, the OTLP endpoint
"""

from feast_mcp.observability.config import LoggingConfig, load_logging_config
from feast_mcp.observability.logger import (
    ROOT_LOGGER_NAME,
    JsonFormatter,
    configure_logging,
    get_logger,
    shutdown_logging,
)

__all__ = [
    "LoggingConfig",
    "load_logging_config",
    "configure_logging",
    "get_logger",
    "shutdown_logging",
    "JsonFormatter",
    "ROOT_LOGGER_NAME",
]
