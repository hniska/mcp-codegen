# Firejail profile for MCP agent code
# Usage: firejail --profile=firejail-mcp.profile python runner/run.py --code "..."
#
# TROUBLESHOOTING:
# - Permission errors? Add: --writable-cwd --tmpfs /tmp
# - Python cache issues? Add: --writable-cwd
# - Still broken? Try: private --tmpfs /tmp (instead of --read-only /)
#
# This profile is designed for maximum isolation. Test your code first.

# Network disabled - strongest isolation
net none

# Filesystem options (choose one approach):
# Option A: Private home + read-only root + tmpfs
private
read-only /
tmpfs /tmp
# Note: May need --writable-cwd for __pycache__ in current directory

# Option B: Full private mode (simpler, more isolated)
# private
# net none
# tmpfs /tmp
# (omit --read-only / for simpler setup)

# Capabilities - drop all for minimal privileges
caps.drop all

# Seccomp - filter dangerous syscalls
seccomp

# Noexec on mount points (prevents code execution from filesystems)
noexec /home
noexec /var

# Deny access to sensitive files and directories
blacklist /etc/shadow
blacklist /etc/sudoers
blacklist ~/.ssh
blacklist ~/.aws
blacklist ~/.config/gcloud
blacklist ~/.docker

# Allow read-only access to Python standard library
# (Add paths based on your Python installation)
read-only /usr/lib/python*
read-only /usr/local/lib/python*

# For virtual environments, add:
# read-only /path/to/venv/lib/python*/site-packages
