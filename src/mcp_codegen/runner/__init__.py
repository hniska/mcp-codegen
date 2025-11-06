"""Runner module for executing agent code with sandboxing.

This module provides secure execution of Python code with:
- Resource limits (CPU, memory, file descriptors, processes)
- Network isolation (optional)
- Output truncation
- PII scrubbing
- Optional seccomp/Firejail hardening
"""
from .workspace import workspace
from .logger import logger
from .privacy import scrub

__all__ = ["workspace", "logger", "scrub"]
