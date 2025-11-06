"""Python code execution runner.

Executes agent-written Python in a subprocess with resource limits,
network control, and PII scrubbing.
"""
from __future__ import annotations
import argparse
import asyncio
import sys
import os
import inspect
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_codegen.runtime.search import search_tools, ToolRef
from mcp_codegen.runner.workspace import workspace
from mcp_codegen.runner.privacy import scrub
from mcp_codegen.runner.logger import logger
from mcp_codegen.runner.limits import apply_limits, get_usage

def _disable_network() -> None:
    """Disable network access by patching socket module.

    This is a light-weight cross-platform guard that blocks socket operations.
    However, it only works at the Python level - libraries using lower-level
    syscalls (C extensions) may still access the network on Linux.

    For stronger guarantees on Linux:
    - Use --seccomp to block socket/connect/bind syscalls
    - Use --firejail with --net=none for namespace isolation

    Network is enabled by default (for MCP tool calls). Use --disable-network to block.
    """
    import socket

    def _denied(*args, **kwargs):
        """Blocked socket operation."""
        raise RuntimeError("Network access blocked by --disable-network flag")

    # Block socket creation
    socket.socket = _denied
    socket.socketpair = _denied
    socket.create_connection = _denied
    socket.create_server = _denied
    if hasattr(socket, 'fromfd'):
        socket.fromfd = _denied

def run_async(coro_or_fn):
    """Execute async code or functions in agent scripts.

    Agents can write either sync or async code:

        # Sync code (runs immediately)
        x = 1 + 1
        print(x)

        # Async code (wrap in async function)
        async def main():
            result = await some_async_call()
            return result

        run_async(main)

    Handles nested event loops (e.g., Jupyter notebooks) gracefully.
    In environments with a running loop, creates a new task instead of
    using asyncio.run() which would raise RuntimeError.

    Args:
        coro_or_fn: Coroutine function, coroutine, or regular callable

    Returns:
        Result of execution
    """
    if inspect.iscoroutinefunction(coro_or_fn):
        coro = coro_or_fn()
    elif inspect.iscoroutine(coro_or_fn):
        coro = coro_or_fn
    else:
        return coro_or_fn()

    # Handle nested event loops (e.g., Jupyter notebooks)
    try:
        loop = asyncio.get_running_loop()
        # Already in an async context, create and await task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        return asyncio.run(coro)

class TruncatedStringIO:
    """StringIO with size limit to prevent OOM from excessive output."""

    def __init__(self, max_size: int = 200 * 1024):  # 200KB default
        self.max_size = max_size
        self.buffer = []
        self.size = 0

    def write(self, text: str) -> int:
        """Write text, truncating if over size limit."""
        if self.size >= self.max_size:
            # Already over limit, skip
            return 0

        available = self.max_size - self.size
        if len(text) > available:
            text = text[:available]
            self.buffer.append(text)
            self.size = self.max_size
            # Mark as truncated
            self.buffer.append(f"\n[OUTPUT TRUNCATED at {self.max_size} bytes]\n")
        else:
            self.buffer.append(text)
            self.size += len(text)

        return len(text)

    def getvalue(self) -> str:
        """Get accumulated output."""
        return ''.join(self.buffer)

async def run_agent_code(code: str, allow_network: bool = False) -> dict:
    """Execute agent code in controlled environment.

    Args:
        code: Python code to execute
        allow_network: If True, allow network access (default: False)

    Returns:
        Execution result with output and statistics
    """
    # Apply resource limits (only in child process)
    apply_limits()

    # Disable network by default
    if not allow_network:
        _disable_network()

    # Capture stdout/stderr with size limits
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    stdout = TruncatedStringIO(max_size=200*1024)  # 200KB cap
    stderr = TruncatedStringIO(max_size=200*1024)  # 200KB cap

    sys.stdout = stdout
    sys.stderr = stderr

    try:
        # Execute code in a limited namespace
        namespace = {
            "__name__": "__main__",
            "__file__": "<agent_code>",
            # Provide runtime utilities
            "search_tools": search_tools,
            "workspace": workspace,
            "logger": logger,
            "scrub": scrub,
            "run_async": run_async,  # Helper for async code
        }

        # Execute the code
        exec(code, namespace)

        # Get usage statistics
        usage = get_usage()

        return {
            "status": "success",
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "usage": usage,
        }

    except KeyboardInterrupt:
        return {
            "status": "interrupted",
            "stdout": stdout.getvalue(),
            "stderr": "Execution interrupted by user",
            "usage": get_usage(),
        }
    except Exception as e:
        return {
            "status": "error",
            "stdout": stdout.getvalue(),
            "stderr": f"{type(e).__name__}: {str(e)}",
            "usage": get_usage(),
        }
    finally:
        # Restore stdout/stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr

def main():
    parser = argparse.ArgumentParser(
        description="Execute Python agent code with resource limits"
    )
    parser.add_argument(
        "--code",
        help="Python code to execute (from stdin if not provided)"
    )
    parser.add_argument(
        "--file",
        help="Execute code from file"
    )
    parser.add_argument(
        "--servers-dir",
        default="servers",
        help="Servers directory (default: servers)"
    )
    parser.add_argument(
        "--workspace",
        default=".workspace",
        help="Workspace directory (default: .workspace)"
    )
    parser.add_argument(
        "--cpu-seconds",
        type=int,
        default=10,
        help="CPU time limit in seconds (default: 10)"
    )
    parser.add_argument(
        "--memory-mb",
        type=int,
        default=512,
        help="Memory limit in MB (default: 512)"
    )
    parser.add_argument(
        "--no-limits",
        action="store_true",
        help="Disable resource limits (unsafe)"
    )
    parser.add_argument(
        "--disable-network",
        action="store_true",
        help="Disable network access (enabled by default for MCP tool calls)"
    )

    args = parser.parse_args()

    # Load code
    if args.file:
        code = Path(args.file).read_text(encoding='utf-8')
    elif args.code:
        code = args.code
    else:
        # Read from stdin
        code = sys.stdin.read()
        if not code:
            print("Error: No code provided. Use --code, --file, or pipe code to stdin.", file=sys.stderr)
            sys.exit(1)

    # Configure workspace
    workspace.root = Path(args.workspace)

    # Run code (limits applied inside run_agent_code)
    # Network is allowed by default (disable_network=False means network is enabled)
    result = asyncio.run(run_agent_code(code, allow_network=not args.disable_network))

    # Output result
    print("\n" + "=" * 60, file=sys.stderr)
    print("EXECUTION RESULT", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Status: {result['status']}", file=sys.stderr)

    if result['stdout']:
        print("\n--- STDOUT ---", file=sys.stderr)
        print(result['stdout'], file=sys.stderr)

    if result['stderr']:
        print("\n--- STDERR ---", file=sys.stderr)
        print(result['stderr'], file=sys.stderr)

    if result['usage']:
        print("\n--- USAGE ---", file=sys.stderr)
        print(f"CPU time: {result['usage']['cpu_time']:.2f}s", file=sys.stderr)
        print(f"Max RSS: {result['usage']['max_rss_kb']} KB", file=sys.stderr)

    # Exit with appropriate code
    if result['status'] == 'error':
        sys.exit(1)
    elif result['status'] == 'interrupted':
        sys.exit(130)  # Standard exit code for SIGINT

if __name__ == "__main__":
    main()
