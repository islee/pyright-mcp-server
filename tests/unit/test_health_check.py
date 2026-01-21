"""Unit tests for health check tool implementation.

These tests use mocks to avoid running actual Pyright commands.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyright_mcp.tools.health_check import health_check


@pytest.fixture
def reset_health_check_state():
    """Reset health check module state before/after tests."""
    import sys
    module = sys.modules.get("pyright_mcp.tools.health_check")
    if module:
        original = getattr(module, "_server_start_time", None)
        module._server_start_time = None
        yield
        module._server_start_time = original
    else:
        yield


class TestHealthCheck:
    """Tests for health_check() function."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health_check() with valid Pyright installation."""
        # Mock subprocess to return valid pyright version
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"pyright 1.1.350\n", b"")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await health_check()

        assert result["status"] == "success"
        assert result["pyright_version"] == "1.1.350"
        assert result["pyright_available"] is True
        assert "config" in result
        assert "uptime_seconds" in result

    @pytest.mark.asyncio
    async def test_health_check_pyright_not_found(self):
        """Test health_check() when Pyright is not found."""
        with patch(
            "pyright_mcp.tools.health_check.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("pyright not found"),
        ):
            result = await health_check()

        assert result["status"] == "error"
        assert result["error_code"] == "not_found"
        assert "not found" in result["message"].lower()
        assert "pip install pyright" in result["message"]

    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        """Test health_check() when Pyright command times out."""
        # Mock subprocess that never completes
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError("Command timed out")
        )
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await health_check()

        assert result["status"] == "error"
        assert result["error_code"] == "timeout"
        assert "timed out" in result["message"].lower()
        # Verify process was killed
        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_execution_error(self):
        """Test health_check() when Pyright returns non-zero exit code."""
        # Mock subprocess to return non-zero exit code
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"Error: something went wrong")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await health_check()

        assert result["status"] == "error"
        assert result["error_code"] == "execution_error"
        assert "failed" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_health_check_config_summary(self):
        """Test health_check() includes config summary with sanitized paths."""
        # Mock subprocess to return valid pyright version
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"pyright 1.1.350\n", b"")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await health_check()

        assert result["status"] == "success"
        config_summary = result["config"]

        # Verify config fields are present
        assert "log_level" in config_summary
        assert "log_mode" in config_summary
        assert "cli_timeout" in config_summary
        assert "allowed_paths_count" in config_summary
        assert "enable_health_check" in config_summary

        # Verify paths are not exposed (only count)
        assert isinstance(config_summary["allowed_paths_count"], int)

    @pytest.mark.asyncio
    async def test_health_check_uptime(self, reset_health_check_state):
        """Test health_check() calculates uptime correctly."""
        # Mock subprocess to return valid pyright version
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"pyright 1.1.350\n", b"")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            # First call
            result1 = await health_check()
            uptime1 = result1["uptime_seconds"]

            # Wait a bit
            await asyncio.sleep(0.1)

            # Second call
            result2 = await health_check()
            uptime2 = result2["uptime_seconds"]

        # Uptime should increase
        assert uptime2 > uptime1
        assert uptime1 >= 0
        assert uptime2 >= 0.1

    @pytest.mark.asyncio
    async def test_health_check_lazy_start_time(self, reset_health_check_state):
        """Test health_check() initializes start time on first call."""
        import sys

        # Get the actual module (not the function re-exported in __init__.py)
        health_check_module = sys.modules["pyright_mcp.tools.health_check"]

        # Mock subprocess
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"pyright 1.1.350\n", b"")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            # First call should initialize start time
            result = await health_check()
            assert health_check_module._server_start_time is not None
            assert result["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_health_check_version_parsing_no_prefix(self):
        """Test health_check() handles version output without 'pyright' prefix."""
        # Mock subprocess to return version without prefix
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"1.1.350\n", b"")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await health_check()

        assert result["status"] == "success"
        # Should use the whole stdout as version
        assert result["pyright_version"] == "1.1.350"

    @pytest.mark.asyncio
    async def test_health_check_version_parsing_multiline(self):
        """Test health_check() handles version output with multiple lines."""
        # Mock subprocess to return multiline output
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"pyright 1.1.350\nSome other output\n", b"")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await health_check()

        assert result["status"] == "success"
        assert result["pyright_version"] == "1.1.350"

    @pytest.mark.asyncio
    async def test_health_check_version_parsing_whitespace(self):
        """Test health_check() handles version output with extra whitespace."""
        # Mock subprocess to return version with extra whitespace
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"  pyright 1.1.350  \n", b"")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await health_check()

        assert result["status"] == "success"
        assert result["pyright_version"] == "1.1.350"

    @pytest.mark.asyncio
    async def test_health_check_version_parsing_prerelease(self):
        """Test health_check() handles version with prerelease suffix."""
        # Mock subprocess to return version with alpha/beta suffix
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"pyright 1.1.350-beta.1\n", b"")
        )

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await health_check()

        assert result["status"] == "success"
        assert result["pyright_version"] == "1.1.350-beta.1"

    @pytest.mark.asyncio
    async def test_health_check_unexpected_error(self):
        """Test health_check() handles unexpected exceptions."""
        with patch(
            "pyright_mcp.tools.health_check.asyncio.create_subprocess_exec",
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = await health_check()

        assert result["status"] == "error"
        assert result["error_code"] == "execution_error"
        assert "unexpected error" in result["message"].lower()
