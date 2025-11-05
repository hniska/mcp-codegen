"""Pytest configuration for mcp-codegen tests."""
import sys
from pathlib import Path

# Add src directory to path so we can import mcp_codegen
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
