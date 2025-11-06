"""Agent logger with PII scrubbing.

Provides structured logging that redacts sensitive data before output,
aligning with privacy-first design.
"""
from __future__ import annotations
import sys
from typing import Any, Dict
from .privacy import _scrubber

class Logger:
    """Logger that automatically scrubs PII."""

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self._log("INFO", message, **kwargs)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self._log("DEBUG", message, **kwargs)

    def warn(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self._log("WARN", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self._log("ERROR", message, **kwargs)

    def _log(self, level: str, message: str, **kwargs) -> None:
        """Internal log method."""
        # Scrub message
        safe_message = _scrubber.scrub_text(message)

        # Scrub kwargs
        safe_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, str):
                safe_kwargs[key] = _scrubber.scrub_text(value)
            elif isinstance(value, (dict, list)):
                safe_kwargs[key] = _scrubber.scrub_dict(value) if isinstance(value, dict) else value
            else:
                safe_kwargs[key] = value

        # Format output
        if safe_kwargs:
            print(f"[{level}] {safe_message} {safe_kwargs}", file=sys.stderr)
        else:
            print(f"[{level}] {safe_message}", file=sys.stderr)

# Global logger instance
logger = Logger()
