"""
Structured logging configuration for Nurliya Pipeline.
Supports JSON format for GCP Cloud Logging and human-readable format for development.
"""

import os
import sys
import logging
import json
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging compatible with GCP Cloud Logging.

    Output format matches Cloud Logging's expected structure:
    https://cloud.google.com/logging/docs/structured-logging
    """

    LEVEL_MAP = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": self.LEVEL_MAP.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add trace context for GCP if available
        if hasattr(record, "trace_id"):
            log_entry["logging.googleapis.com/trace"] = record.trace_id

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        level = record.levelname.ljust(8)

        # Format: [LEVEL] logger: message
        formatted = f"{color}[{level}]{self.RESET} {record.name}: {record.getMessage()}"

        # Add extra data if present
        if hasattr(record, "extra_data") and record.extra_data:
            formatted += f" | {record.extra_data}"

        # Add exception if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that allows adding context to log messages."""

    def process(self, msg: str, kwargs: dict) -> tuple:
        extra = kwargs.get("extra", {})
        if self.extra:
            extra["extra_data"] = {**self.extra, **extra.get("extra_data", {})}
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str, **context) -> logging.LoggerAdapter:
    """
    Get a logger with optional context.

    Args:
        name: Logger name (typically __name__)
        **context: Additional context to include in all log messages

    Returns:
        ContextLogger instance

    Example:
        logger = get_logger(__name__, service="worker", worker_id="1")
        logger.info("Processing review", extra={"extra_data": {"review_id": "123"}})
    """
    logger = logging.getLogger(name)
    return ContextLogger(logger, context)


def setup_logging():
    """
    Configure logging based on environment.

    Environment variables:
        LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
        LOG_FORMAT: json, console (default: console, auto-detects GCP)
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "").lower()

    # Auto-detect GCP environment
    is_gcp = bool(
        os.getenv("K_SERVICE") or           # Cloud Run
        os.getenv("GOOGLE_CLOUD_PROJECT") or # GCP
        os.getenv("GCP_PROJECT_ID")          # Our custom var
    )

    # Default to JSON in GCP, console locally
    if not log_format:
        log_format = "json" if is_gcp else "console"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("pika").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    return root_logger


# Initialize logging on import
setup_logging()
