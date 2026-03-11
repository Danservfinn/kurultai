#!/usr/bin/env python3
"""
Centralized Logging Configuration for Kurultai agents.

Provides structured JSON logging with configurable levels and formats.
All Kurultai scripts should use this module for consistent logging.

Usage:
    from kurultai_logging import setup_logging, get_logger

    setup_logging(level='INFO', json_format=True)
    logger = get_logger('my_agent')
    logger.info("Task completed", extra={'task_id': '123'})
"""

import logging
import json
import sys
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path


LOG_DIR = Path(os.environ.get('KURULTAI_LOG_DIR', '/Users/kublai/.openclaw/logs'))
DEBUG_LOG_DIR = LOG_DIR / 'debug'


class StructuredFormatter(logging.Formatter):
    """
    JSON-structured log formatter.

    Outputs logs as JSON objects with consistent fields:
    - ts: ISO timestamp
    - level: Log level
    - agent: Agent name (from extra)
    - message: Log message
    - Additional extra fields included
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "agent": getattr(record, 'agent', 'unknown'),
            "message": record.getMessage(),
        }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'pathname', 'process', 'processName', 'relativeCreated',
                          'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                          'message', 'ts', 'level', 'agent'):
                try:
                    json.dumps(value)  # Check serializability
                    log_obj[key] = value
                except (TypeError, ValueError):
                    log_obj[key] = str(value)

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


class AgentLogFilter(logging.Filter):
    """Add agent name to all log records."""

    def __init__(self, agent_name: str = 'unknown'):
        super().__init__()
        self.agent_name = agent_name

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, 'agent'):
            record.agent = self.agent_name
        return True


def setup_logging(
    level: str = 'INFO',
    json_format: bool = False,
    log_file: Optional[Path] = None,
    agent_name: str = 'unknown'
) -> logging.Logger:
    """
    Configure logging for a Kurultai agent.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON structured logging
        log_file: Optional file to log to
        agent_name: Name of the agent for log records

    Returns:
        Configured root logger
    """
    # Ensure log directories exist
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Get log level
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers = []

    # Create formatter
    if json_format:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Add agent filter
    agent_filter = AgentLogFilter(agent_name)
    for handler in root_logger.handlers:
        handler.addFilter(agent_filter)

    return root_logger


def get_logger(name: str, agent: Optional[str] = None) -> logging.Logger:
    """
    Get a logger with optional agent name.

    Args:
        name: Logger name (usually __name__)
        agent: Agent name override

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    if agent:
        logger.addFilter(AgentLogFilter(agent))
    return logger


class LogContext:
    """
    Context manager for adding extra context to all logs within a block.

    Usage:
        with LogContext(logger, task_id='123', agent='kublai'):
            logger.info("Processing")  # Includes task_id and agent
    """

    def __init__(self, logger: logging.Logger, **context):
        self.logger = logger
        self.context = context
        self.old_factory = None

    def __enter__(self):
        self.old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory)
        return False


def log_exception(logger: logging.Logger, exc: Exception, context: Optional[Dict[str, Any]] = None):
    """
    Log an exception with context.

    Args:
        logger: Logger to use
        exc: Exception to log
        context: Additional context
    """
    extra = context or {}
    extra['exception_type'] = type(exc).__name__
    logger.error(f"Exception: {exc}", exc_info=True, extra=extra)


# Convenience function for scripts
def init_agent_logging(script_name: str) -> logging.Logger:
    """
    Initialize logging for an agent script.

    Reads configuration from environment:
    - KURULTAI_LOG_LEVEL: Log level (default: INFO)
    - KURULTAI_LOG_FORMAT: 'json' for structured logging
    - KURULTAI_LOG_FILE: Path to log file

    Args:
        script_name: Name of the script (without .py)

    Returns:
        Configured logger
    """
    level = os.environ.get('KURULTAI_LOG_LEVEL', 'INFO')
    json_format = os.environ.get('KURULTAI_LOG_FORMAT', '').lower() == 'json'
    log_file_env = os.environ.get('KURULTAI_LOG_FILE')

    log_file = Path(log_file_env) if log_file_env else None

    setup_logging(
        level=level,
        json_format=json_format,
        log_file=log_file,
        agent_name=script_name
    )

    return get_logger(script_name, agent=script_name)


if __name__ == "__main__":
    # Demo the logging
    print("Testing Kurultai logging...")

    # Setup JSON logging
    setup_logging(level='DEBUG', json_format=True, agent_name='test_agent')
    logger = get_logger('test')

    logger.info("Starting test")
    logger.debug("Debug message", extra={'extra_field': 'value'})

    try:
        1 / 0
    except Exception as e:
        log_exception(logger, e, {'operation': 'division'})

    # Test context manager
    with LogContext(logger, task_id='test-123'):
        logger.info("Processing task")

    print("\nDone!")
