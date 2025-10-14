"""
Production logging configuration with structured logging.
"""

import logging
import sys
from typing import Any, Dict

import structlog
from src.config import get_config

config = get_config()


def configure_logging():
    """Configure structured logging for production."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if config.environment == "production" 
            else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, config.log_level.upper()),
    )
    
    # Set third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("voyageai").setLevel(logging.WARNING)


def get_structured_logger(name: str) -> Any:
    """Get a structured logger instance."""
    return structlog.get_logger(name)