"""Unit tests for FastMCP server setup.

These tests verify tool registration and delegation to implementations.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestServerToolRegistration:
    """Tests for MCP tool registration."""

    def test_mcp_server_instance(self):
        """Test MCP server instance is properly initialized."""
        from pyright_mcp.server import mcp

        # Verify mcp instance exists
        assert mcp is not None
        assert mcp.name == "pyright-mcp"

    @pytest.mark.asyncio
    async def test_check_types_tool_callable(self):
        """Test check_types tool can be called and returns expected format."""
        from pyright_mcp.server import check_types

        # Mock the implementation
        with patch(
            "pyright_mcp.tools.check_types.check_types",
            new_callable=AsyncMock,
            return_value={"status": "success", "diagnostics": []},
        ) as mock:
            result = await check_types("/test/path.py")

            # Verify tool is callable and returns structured response
            assert isinstance(result, dict)
            assert "status" in result
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_tool_callable(self):
        """Test health_check tool can be called and returns expected format."""
        from pyright_mcp.server import health_check

        # Mock the implementation
        with patch(
            "pyright_mcp.tools.health_check.health_check",
            new_callable=AsyncMock,
            return_value={
                "status": "success",
                "pyright_version": "1.1.350",
                "pyright_available": True,
            },
        ) as mock:
            result = await health_check()

            # Verify tool is callable and returns structured response
            assert isinstance(result, dict)
            assert "status" in result
            mock.assert_called_once()


class TestCheckTypesTool:
    """Tests for check_types MCP tool wrapper."""

    @pytest.mark.asyncio
    async def test_check_types_delegates_to_impl(self):
        """Test check_types delegates to tools.check_types implementation."""
        from pyright_mcp.server import check_types

        # Mock the implementation
        mock_result = {
            "status": "success",
            "summary": "No errors",
            "error_count": 0,
            "warning_count": 0,
            "diagnostics": [],
        }

        with patch(
            "pyright_mcp.tools.check_types.check_types",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_impl:
            result = await check_types("/path/to/file.py")

            # Verify implementation was called with correct args
            mock_impl.assert_called_once_with("/path/to/file.py", None)
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_check_types_delegates_with_python_version(self):
        """Test check_types delegates with python_version parameter."""
        from pyright_mcp.server import check_types

        # Mock the implementation
        mock_result = {
            "status": "success",
            "summary": "No errors",
            "error_count": 0,
            "warning_count": 0,
            "diagnostics": [],
        }

        with patch(
            "pyright_mcp.tools.check_types.check_types",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_impl:
            result = await check_types("/path/to/file.py", python_version="3.11")

            # Verify implementation was called with correct args
            mock_impl.assert_called_once_with("/path/to/file.py", "3.11")
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_check_types_returns_error_from_impl(self):
        """Test check_types returns error response from implementation."""
        from pyright_mcp.server import check_types

        # Mock the implementation to return error
        mock_result = {
            "status": "error",
            "error_code": "not_found",
            "message": "File not found",
        }

        with patch(
            "pyright_mcp.tools.check_types.check_types",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_impl:
            result = await check_types("/nonexistent/file.py")

            assert result["status"] == "error"
            assert result["error_code"] == "not_found"

    @pytest.mark.asyncio
    async def test_check_types_success_response_format(self):
        """Test check_types success response has all required fields."""
        from pyright_mcp.server import check_types

        # Mock the implementation with complete success response
        mock_result = {
            "status": "success",
            "summary": "No errors found",
            "error_count": 0,
            "warning_count": 0,
            "diagnostics": [],
        }

        with patch(
            "pyright_mcp.tools.check_types.check_types",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await check_types("/test/path.py")

            # Verify all required success fields are present
            assert result["status"] == "success"
            assert "summary" in result
            assert "error_count" in result
            assert "warning_count" in result
            assert "diagnostics" in result
            assert isinstance(result["diagnostics"], list)

    @pytest.mark.asyncio
    async def test_check_types_error_response_format(self):
        """Test check_types error response has all required fields."""
        from pyright_mcp.server import check_types

        # Mock the implementation with complete error response
        mock_result = {
            "status": "error",
            "error_code": "timeout",
            "message": "Operation timed out",
        }

        with patch(
            "pyright_mcp.tools.check_types.check_types",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await check_types("/test/path.py")

            # Verify all required error fields are present
            assert result["status"] == "error"
            assert "error_code" in result
            assert "message" in result
            assert isinstance(result["error_code"], str)
            assert isinstance(result["message"], str)

    @pytest.mark.asyncio
    async def test_check_types_default_python_version(self):
        """Test check_types with default python_version (None)."""
        from pyright_mcp.server import check_types

        # Mock the implementation
        mock_result = {
            "status": "success",
            "summary": "No errors",
            "error_count": 0,
            "warning_count": 0,
            "diagnostics": [],
        }

        with patch(
            "pyright_mcp.tools.check_types.check_types",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_impl:
            # Call with only path (python_version defaults to None)
            result = await check_types("/path/to/file.py")

            # Verify implementation was called with None for python_version
            mock_impl.assert_called_once_with("/path/to/file.py", None)
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_check_types_explicit_none_python_version(self):
        """Test check_types with explicit python_version=None."""
        from pyright_mcp.server import check_types

        # Mock the implementation
        mock_result = {
            "status": "success",
            "summary": "No errors",
            "error_count": 0,
            "warning_count": 0,
            "diagnostics": [],
        }

        with patch(
            "pyright_mcp.tools.check_types.check_types",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_impl:
            # Call with explicit None
            result = await check_types("/path/to/file.py", python_version=None)

            # Verify implementation was called with None
            mock_impl.assert_called_once_with("/path/to/file.py", None)
            assert result == mock_result


class TestHealthCheckTool:
    """Tests for health_check MCP tool wrapper."""

    @pytest.mark.asyncio
    async def test_health_check_delegates_to_impl(self):
        """Test health_check delegates to tools.health_check implementation."""
        from pyright_mcp.server import health_check

        # Mock the implementation
        mock_result = {
            "status": "success",
            "pyright_version": "1.1.350",
            "pyright_available": True,
            "config": {
                "log_level": "INFO",
                "log_mode": "stderr",
                "cli_timeout": 30.0,
                "allowed_paths_count": 0,
                "enable_health_check": True,
            },
            "uptime_seconds": 123.45,
        }

        with patch(
            "pyright_mcp.tools.health_check.health_check",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_impl:
            result = await health_check()

            # Verify implementation was called
            mock_impl.assert_called_once_with()
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_health_check_disabled_returns_error(self, set_env_vars):
        """Test health_check returns error when disabled in config."""
        from pyright_mcp.config import reset_config
        from pyright_mcp.server import health_check

        # Set environment variable to disable health check
        set_env_vars(PYRIGHT_MCP_ENABLE_HEALTH_CHECK="false")
        reset_config()  # Reload config with new env var

        # Mock the implementation (should not be called)
        with patch(
            "pyright_mcp.tools.health_check.health_check",
            new_callable=AsyncMock,
        ) as mock_impl:
            result = await health_check()

            # Verify implementation was NOT called
            mock_impl.assert_not_called()

            # Verify error response
            assert result["status"] == "error"
            assert result["error_code"] == "disabled"
            assert "disabled" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_health_check_returns_error_from_impl(self):
        """Test health_check returns error response from implementation."""
        from pyright_mcp.server import health_check

        # Mock the implementation to return error
        mock_result = {
            "status": "error",
            "error_code": "not_found",
            "message": "Pyright executable not found",
        }

        with patch(
            "pyright_mcp.tools.health_check.health_check",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_impl:
            result = await health_check()

            assert result["status"] == "error"
            assert result["error_code"] == "not_found"

    @pytest.mark.asyncio
    async def test_health_check_enabled_by_default(self):
        """Test health_check is enabled by default."""
        from pyright_mcp.config import reset_config
        from pyright_mcp.server import health_check

        # Reset config to defaults
        reset_config()

        # Mock the implementation
        mock_result = {
            "status": "success",
            "pyright_version": "1.1.350",
            "pyright_available": True,
            "config": {
                "log_level": "INFO",
                "log_mode": "stderr",
                "cli_timeout": 30.0,
                "allowed_paths_count": 0,
                "enable_health_check": True,
            },
            "uptime_seconds": 123.45,
        }

        with patch(
            "pyright_mcp.tools.health_check.health_check",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_impl:
            result = await health_check()

            # Verify implementation was called (not disabled)
            mock_impl.assert_called_once()
            assert result["status"] == "success"


class TestDefensiveLoggingInitialization:
    """Tests for defensive logging initialization in server creation."""

    def test_multiple_server_creation_no_duplicate_handlers(self):
        """Test that creating multiple servers doesn't register duplicate logging handlers."""
        import logging

        from pyright_mcp.server import create_mcp_server

        # Reset logging to clean state
        root_logger = logging.getLogger()
        initial_handler_count = len(root_logger.handlers)

        # Create first server
        server1 = create_mcp_server()
        handler_count_after_first = len(root_logger.handlers)

        # Create second server
        server2 = create_mcp_server()
        handler_count_after_second = len(root_logger.handlers)

        # Handler count should be the same after second server creation
        # (defensive logging check prevents duplicates)
        assert handler_count_after_second == handler_count_after_first
        assert server1 is not None
        assert server2 is not None

    def test_server_creation_defensively_initializes_logging(self):
        """Test that server creation defensively checks if logging is initialized."""
        import logging

        from pyright_mcp.server import create_mcp_server

        # Get initial handler count
        root_logger = logging.getLogger()
        initial_count = len(root_logger.handlers)

        # Create first server
        server1 = create_mcp_server()
        count_after_first = len(root_logger.handlers)

        # Create second server
        server2 = create_mcp_server()
        count_after_second = len(root_logger.handlers)

        # Handler count should not increase after second server creation
        # (defensive logging prevents duplicate handlers)
        assert count_after_second <= count_after_first
        assert server1 is not None
        assert server2 is not None
