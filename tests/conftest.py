"""Pytest configuration for mcp-codegen tests."""
import sys
import tempfile
from pathlib import Path

import pytest

# Add src directory to path so we can import mcp_codegen
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))


# ============================================================================
# Shared Fixtures for Integration Tests
# ============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for test projects.

    This fixture provides a clean temporary directory that is automatically
    cleaned up after each test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for generated files.

    Use this when you need to generate files and verify their contents.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_workspace_dir():
    """Create a temporary workspace directory for agent outputs.

    Use this when testing agent code that writes to workspace.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ============================================================================
# Test Markers
# ============================================================================

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test that requires external services"
    )
    config.addinivalue_line(
        "markers",
        "unit: mark test as a unit test with no external dependencies"
    )


# ============================================================================
# Pytest Options
# ============================================================================

def pytest_collection_modifyitems(config, items):
    """Automatically mark integration tests.

    Any test that uses the @pytest.mark.integration decorator
    will be collected and can be filtered with -m integration.
    """
    # This is handled by explicit markers in test files
