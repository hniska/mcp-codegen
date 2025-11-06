"""Sandboxing options for Linux.

Provides seccomp-based syscall filtering and Firejail integration
for stronger isolation than resource limits alone.
"""
from __future__ import annotations
import os
import sys
from typing import List, Optional

def use_seccomp(deny_list: Optional[List[str]] = None) -> bool:
    """Enable seccomp syscall filtering.

    Args:
        deny_list: List of syscalls to deny (default: dangerous syscalls)

    Returns:
        True if seccomp is available and enabled

    Note:
        Requires: pip install python3-seccomp
        Default behavior: ALLOW all, then KILL specific dangerous syscalls
    """
    if sys.platform != 'linux':
        print("[sandbox] seccomp not supported on non-Linux platforms", file=sys.stderr)
        return False

    try:
        import seccomp
    except ImportError:
        print("[sandbox] python3-seccomp not installed (pip install python3-seccomp)", file=sys.stderr)
        return False

    # Default deny list - blocks dangerous syscalls
    # Note: execve is intentionally NOT blocked to allow Python's subprocess module
    # Use Firejail profiles for stricter execution control if needed
    if deny_list is None:
        deny_list = [
            'socket',          # No network sockets
            'connect',         # No network connections
            'bind',            # No binding ports
            'listen',          # No listening
            'accept',          # No accepting connections
            'ptrace',          # No process tracing
            'process_vm_readv', # No reading other processes
            'process_vm_writev', # No writing to other processes
            # 'execve',        # NOT BLOCKED - allows subprocess module
        ]

    # Build filter with ALLOW default (then KILL specific dangerous ones)
    # CRITICAL: Default ALLOW prevents bricking Python's essential syscalls
    f = seccomp.SyscallFilter(defact=seccomp.ALLOW)

    for syscall in deny_list:
        try:
            f.add_rule(seccomp.KILL, syscall)  # KILL on dangerous syscalls
        except OSError:
            # Some syscalls might not exist on all kernels
            pass

    try:
        f.load()
        print(f"[sandbox] Enabled seccomp filtering ({len(deny_list)} syscalls blocked)", file=sys.stderr)
        return True
    except OSError as e:
        print(f"[sandbox] Failed to enable seccomp: {e}", file=sys.stderr)
        return False

def check_firejail_available() -> bool:
    """Check if Firejail is installed.

    Returns:
        True if Firejail command is available
    """
    return os.system("which firejail > /dev/null 2>&1") == 0

def launch_with_firejail(
    cmd: List[str],
    profile: Optional[str] = None
) -> int:
    """Launch command with Firejail sandbox.

    Args:
        cmd: Command to execute (including current script)
        profile: Firejail profile to use

    Returns:
        Exit code (never returns, uses os.execvp)

    Example:
        exit_code = launch_with_firejail(
            [sys.executable, __file__, "--code", code],
            profile="seccomp"
        )

    Note:
        Uses os.execvp to replace current process. Must be called early
        in main() before any setup, or wrap in a helper script.
    """
    if not check_firejail_available():
        print("[sandbox] Firejail not installed", file=sys.stderr)
        return 127

    # Build firejail command
    firejail_cmd = ["firejail"]

    if profile:
        firejail_cmd.extend(["--profile", profile])

    # Security options
    firejail_cmd.extend([
        "--net=none",      # No network
        "--private",       # Private /tmp
        "--read-only=/",   # Read-only root filesystem
        "--caps-drop=all", # Drop all capabilities
        "--no-x11",        # No X11 forwarding
        "--no-sound",      # No sound
    ])

    # Add command
    firejail_cmd.extend(cmd)

    print(f"[sandbox] Launching with Firejail: {' '.join(firejail_cmd)}", file=sys.stderr)
    print(f"[sandbox] Note: This replaces current process", file=sys.stderr)

    # Execute (replaces current process)
    os.execvp("firejail", firejail_cmd)

    # Never reached
    return 1
