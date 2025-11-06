"""Workspace utilities for agent code.

Provides safe file I/O for agents to write results without
sending everything to the model (Anthropic's "write to workspace" pattern).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional
import sys

class Workspace:
    """Simple workspace for file I/O."""

    def __init__(self, root: str = ".workspace"):
        """Initialize workspace.

        Args:
            root: Workspace root directory
        """
        self.root = Path(root)
        self.root.mkdir(exist_ok=True)

    def write(self, path: str, data: Any) -> None:
        """Write data to file.

        Args:
            path: Relative path within workspace
            data: Data to write (str, dict, or list)
        """
        file_path = self.root / path

        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, (dict, list)):
            with file_path.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        else:
            with file_path.open('w', encoding='utf-8') as f:
                f.write(str(data))

        print(f"[workspace] Wrote {path} ({len(str(data))} bytes)", file=sys.stderr)

    def read(self, path: str) -> Optional[str]:
        """Read data from file.

        Args:
            path: Relative path within workspace

        Returns:
            File contents or None if not found
        """
        file_path = self.root / path

        if not file_path.exists():
            return None

        with file_path.open('r', encoding='utf-8') as f:
            return f.read()

    def list(self, pattern: str = "*") -> list[str]:
        """List files in workspace.

        Args:
            pattern: Glob pattern

        Returns:
            List of file paths
        """
        return [str(p.relative_to(self.root)) for p in self.root.glob(pattern)]

    def clear(self) -> None:
        """Clear workspace."""
        import shutil
        shutil.rmtree(self.root)
        self.root.mkdir(exist_ok=True)

# Global workspace instance
workspace = Workspace()
