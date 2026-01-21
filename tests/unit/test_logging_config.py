"""Unit tests for logging configuration.

These tests verify JSON formatting, request ID handling, and logging setup.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pyright_mcp.config import Config
from pyright_mcp.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    get_logger,
    request_id_var,
    setup_logging,
)


@pytest.fixture(autouse=True)
def clean_logger_state():
    """Ensure clean logger state before and after each test."""
    root = logging.getLogger()
    pyright_logger = logging.getLogger("pyright_mcp")

    # Store original state
    original_root_handlers = root.handlers[:]
    original_root_level = root.level
    original_pyright_handlers = pyright_logger.handlers[:]
    original_pyright_level = pyright_logger.level

    yield

    # Restore original state
    root.handlers = original_root_handlers
    root.setLevel(original_root_level)
    pyright_logger.handlers = original_pyright_handlers
    pyright_logger.setLevel(original_pyright_level)


class TestJsonFormatter:
    """Tests for JsonFormatter class."""

    def test_json_formatter_basic(self):
        """Test JsonFormatter outputs valid JSON with basic fields."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_obj = json.loads(output)

        # Verify all expected fields present
        assert "timestamp" in log_obj
        assert "level" in log_obj
        assert "logger" in log_obj
        assert "message" in log_obj

        # Verify field values
        assert log_obj["level"] == "INFO"
        assert log_obj["logger"] == "test.logger"
        assert log_obj["message"] == "Test message"

        # Verify timestamp is valid ISO format
        datetime.fromisoformat(log_obj["timestamp"])  # Will raise if invalid

        # Verify no unexpected fields (only standard fields should be present)
        expected_fields = {"timestamp", "level", "logger", "message"}
        assert set(log_obj.keys()) == expected_fields

    def test_json_formatter_with_request_id(self):
        """Test JsonFormatter includes request_id when set in context."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Set request_id in context
        token = request_id_var.set("req-123")
        try:
            output = formatter.format(record)
            log_obj = json.loads(output)

            assert log_obj["request_id"] == "req-123"
        finally:
            request_id_var.reset(token)

    def test_json_formatter_with_extras(self):
        """Test JsonFormatter includes extra fields from record."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Add extra fields
        record.path = "/some/path"
        record.command = "pyright"
        record.duration = 1.23
        record.error_code = "not_found"

        output = formatter.format(record)
        log_obj = json.loads(output)

        assert log_obj["path"] == "/some/path"
        assert log_obj["command"] == "pyright"
        assert log_obj["duration"] == 1.23
        assert log_obj["error_code"] == "not_found"

    def test_json_formatter_with_exception(self):
        """Test JsonFormatter formats exception info."""
        formatter = JsonFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        log_obj = json.loads(output)

        assert "exception" in log_obj
        assert "ValueError: Test error" in log_obj["exception"]
        assert "Traceback" in log_obj["exception"]

    def test_json_formatter_without_request_id(self):
        """Test JsonFormatter omits request_id when not set."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Ensure request_id is not set
        token = request_id_var.set(None)
        try:
            output = formatter.format(record)
            log_obj = json.loads(output)

            assert "request_id" not in log_obj
        finally:
            request_id_var.reset(token)

    def test_json_formatter_with_non_ascii(self):
        """Test JsonFormatter handles non-ASCII characters in messages."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message with émojis 🚀 and ünïcödë",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_obj = json.loads(output)

        assert log_obj["message"] == "Test message with émojis 🚀 and ünïcödë"
        # Verify timestamp is still valid
        datetime.fromisoformat(log_obj["timestamp"])

    def test_json_formatter_empty_request_id_vs_none(self):
        """Test JsonFormatter omits empty and None request_id (both falsy)."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Test with empty string (treated as falsy, should be omitted)
        token = request_id_var.set("")
        try:
            output = formatter.format(record)
            log_obj = json.loads(output)
            # Empty string is falsy in Python, so it's omitted
            assert "request_id" not in log_obj
        finally:
            request_id_var.reset(token)

        # Test with None (should be omitted)
        token = request_id_var.set(None)
        try:
            output = formatter.format(record)
            log_obj = json.loads(output)
            assert "request_id" not in log_obj
        finally:
            request_id_var.reset(token)

        # Test with non-empty string (should be included)
        token = request_id_var.set("req-123")
        try:
            output = formatter.format(record)
            log_obj = json.loads(output)
            assert "request_id" in log_obj
            assert log_obj["request_id"] == "req-123"
        finally:
            request_id_var.reset(token)


class TestRequestIdFilter:
    """Tests for RequestIdFilter class."""

    def test_request_id_filter(self):
        """Test RequestIdFilter injects request_id into log records."""
        log_filter = RequestIdFilter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Set request_id in context
        token = request_id_var.set("req-456")
        try:
            result = log_filter.filter(record)

            assert result is True  # Always passes through
            assert hasattr(record, "request_id")
            assert record.request_id == "req-456"  # type: ignore[attr-defined]
        finally:
            request_id_var.reset(token)

    def test_request_id_filter_without_context(self):
        """Test RequestIdFilter passes through when no request_id in context."""
        log_filter = RequestIdFilter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Ensure request_id is not set
        token = request_id_var.set(None)
        try:
            result = log_filter.filter(record)

            assert result is True  # Always passes through
            assert not hasattr(record, "request_id")
        finally:
            request_id_var.reset(token)


class TestRequestIdContextVar:
    """Tests for request_id context variable."""

    @pytest.mark.asyncio
    async def test_request_id_context_var_across_async_calls(self):
        """Test request_id context variable works across async calls."""
        async def async_task(request_id: str) -> str:
            """Async task that uses request_id context."""
            token = request_id_var.set(request_id)
            try:
                # Simulate some async work
                import asyncio
                await asyncio.sleep(0.01)
                return request_id_var.get()  # type: ignore[return-value]
            finally:
                request_id_var.reset(token)

        import asyncio

        # Run multiple tasks concurrently
        results = await asyncio.gather(
            async_task("req-1"),
            async_task("req-2"),
            async_task("req-3"),
        )

        # Each task should have maintained its own request_id
        assert results == ["req-1", "req-2", "req-3"]


class TestGetLogger:
    """Tests for get_logger() function."""

    def test_get_logger_namespace(self):
        """Test get_logger() returns logger with correct namespace."""
        logger = get_logger("cli_runner")

        assert logger.name == "pyright_mcp.cli_runner"

    def test_get_logger_different_names(self):
        """Test get_logger() returns different loggers for different names."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        assert logger1.name == "pyright_mcp.module1"
        assert logger2.name == "pyright_mcp.module2"
        assert logger1 is not logger2


class TestSetupLogging:
    """Tests for setup_logging() function."""

    def test_setup_logging_stderr_mode(self):
        """Test setup_logging() adds stderr handler in stderr mode."""
        config = Config(
            allowed_paths=None,
            cli_timeout=30.0,
            lsp_timeout=300.0,
            lsp_command=["pyright-langserver", "--stdio"],
            log_level="INFO",
            log_mode="stderr",
            log_file=None,
            enable_health_check=True,
        )

        # Clear existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(config)

        # Verify stderr handler was added
        assert len(root_logger.handlers) == 1
        handler = root_logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream == sys.stderr

        # Verify JSON formatter
        from pyright_mcp.logging_config import JsonFormatter
        assert isinstance(handler.formatter, JsonFormatter)

    def test_setup_logging_file_mode(self, tmp_path: Path):
        """Test setup_logging() adds file handler in file mode."""
        log_file = tmp_path / "test.log"
        config = Config(
            allowed_paths=None,
            cli_timeout=30.0,
            lsp_timeout=300.0,
            lsp_command=["pyright-langserver", "--stdio"],
            log_level="DEBUG",
            log_mode="file",
            log_file=log_file,
            enable_health_check=True,
        )

        # Clear existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(config)

        # Verify file handler was added
        assert len(root_logger.handlers) == 1
        handler = root_logger.handlers[0]
        from logging.handlers import RotatingFileHandler
        assert isinstance(handler, RotatingFileHandler)

        # Verify log file was created
        assert log_file.exists()

        # Cleanup
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

    def test_setup_logging_both_mode(self, tmp_path: Path):
        """Test setup_logging() adds both handlers in both mode."""
        log_file = tmp_path / "test.log"
        config = Config(
            allowed_paths=None,
            cli_timeout=30.0,
            lsp_timeout=300.0,
            lsp_command=["pyright-langserver", "--stdio"],
            log_level="WARNING",
            log_mode="both",
            log_file=log_file,
            enable_health_check=True,
        )

        # Clear existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(config)

        # Verify both handlers were added
        assert len(root_logger.handlers) == 2

        handler_types = [type(h).__name__ for h in root_logger.handlers]
        assert "StreamHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

        # Cleanup
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

    def test_setup_logging_clears_existing_handlers(self):
        """Test setup_logging() clears existing handlers to avoid duplicates."""
        config = Config(
            allowed_paths=None,
            cli_timeout=30.0,
            lsp_timeout=300.0,
            lsp_command=["pyright-langserver", "--stdio"],
            log_level="INFO",
            log_mode="stderr",
            log_file=None,
            enable_health_check=True,
        )

        # Add a dummy handler
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        dummy_handler = logging.StreamHandler()
        root_logger.addHandler(dummy_handler)

        assert len(root_logger.handlers) == 1

        # Setup logging should clear and add new handler
        setup_logging(config)

        assert len(root_logger.handlers) == 1
        assert root_logger.handlers[0] is not dummy_handler

    def test_setup_logging_sets_log_level(self):
        """Test setup_logging() sets correct log level."""
        config = Config(
            allowed_paths=None,
            cli_timeout=30.0,
            lsp_timeout=300.0,
            lsp_command=["pyright-langserver", "--stdio"],
            log_level="DEBUG",
            log_mode="stderr",
            log_file=None,
            enable_health_check=True,
        )

        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(config)

        assert root_logger.level == logging.DEBUG

    def test_setup_logging_adds_request_id_filter(self):
        """Test setup_logging() adds RequestIdFilter to handlers."""
        config = Config(
            allowed_paths=None,
            cli_timeout=30.0,
            lsp_timeout=300.0,
            lsp_command=["pyright-langserver", "--stdio"],
            log_level="INFO",
            log_mode="stderr",
            log_file=None,
            enable_health_check=True,
        )

        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(config)

        # Verify filter was added to handler
        handler = root_logger.handlers[0]
        filters = [f for f in handler.filters if isinstance(f, RequestIdFilter)]
        assert len(filters) == 1
