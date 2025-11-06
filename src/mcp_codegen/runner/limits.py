"""Resource limits for Python code execution.

This module applies Linux resource limits to prevent runaway code:
- CPU time limits
- Memory limits
- File descriptor limits
- Process count limits
"""
from __future__ import annotations
import resource
import sys
import os

def apply_limits(
    cpu_seconds: int = 10,
    max_memory_mb: int = 512,
    max_files: int = 64,
    max_processes: int = 64
) -> None:
    """Apply resource limits to current process.

    Args:
        cpu_seconds: Maximum CPU seconds
        max_memory_mb: Maximum address space in MB
        max_files: Maximum open file descriptors
        max_processes: Maximum number of processes

    Note:
        Limits are applied to the current process and child processes.
        On non-Linux systems, this may have limited effect.
    """
    if sys.platform != 'linux':
        print(f"Warning: Resource limits not fully supported on {sys.platform}", file=sys.stderr)
        return

    try:
        # CPU time limit
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))

        # Address space limit (memory)
        mem_bytes = max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

        # Open files limit
        resource.setrlimit(resource.RLIMIT_NOFILE, (max_files, max_files))

        # Process count limit
        resource.setrlimit(resource.RLIMIT_NPROC, (max_processes, max_processes))

        print(f"[runner] Applied limits: CPU={cpu_seconds}s, Memory={max_memory_mb}MB, "
              f"Files={max_files}, Processes={max_processes}", file=sys.stderr)

    except (OSError, ValueError) as e:
        print(f"[runner] Warning: Could not apply all resource limits: {e}", file=sys.stderr)

def get_usage() -> dict:
    """Get current resource usage.

    Returns:
        Dictionary with CPU time, memory usage, etc.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)

    return {
        "cpu_time": usage.ru_utime + usage.ru_stime,
        "max_rss_kb": usage.ru_maxrss,
        "page_faults": usage.ru_majflt,
        "voluntary_switches": usage.ru_nvcsw,
        "involuntary_switches": usage.ru_nivcsw,
    }

def check_limit(limit_type: str, current_value: float, soft_limit: float) -> bool:
    """Check if current usage exceeds limit.

    Args:
        limit_type: Type of limit ("cpu_time", "memory", etc.)
        current_value: Current usage value
        soft_limit: Soft limit threshold

    Returns:
        True if limit exceeded
    """
    if limit_type == "cpu_time":
        return current_value >= soft_limit
    elif limit_type == "memory":
        return current_value >= soft_limit * 1024 * 1024  # Convert MB to KB
    else:
        return False
