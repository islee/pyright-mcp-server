"""Tests for LSP client."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyright_mcp.backends.base import (
    BackendError,
    DefinitionResult,
    HoverResult,
    Location,
)
from pyright_mcp.backends.lsp_client import LSPClient, LSPProcess, LSPState
from pyright_mcp.config import Config
from pyright_mcp.utils.position import Position, Range


class TestLSPState:
    """Tests for LSPState enum."""

    def test_lsp_state_values(self):
        """Test LSPState has expected values."""
        assert LSPState.NOT_STARTED.value == "not_started"
        assert LSPState.INITIALIZING.value == "initializing"
        assert LSPState.READY.value == "ready"
        assert LSPState.SHUTDOWN.value == "shutdown"


class TestLSPClientInitialization:
    """Tests for LSPClient initialization."""

    def test_lsp_client_creation_with_defaults(self):
        """Test LSPClient is created with default config."""
        client = LSPClient()
        assert client.state == LSPState.NOT_STARTED
        assert client.workspace_root is None

    def test_lsp_client_creation_with_custom_config(self):
        """Test LSPClient accepts custom config."""
        config = Config(
            allowed_paths=None,
            cli_timeout=30.0,
            lsp_timeout=600.0,  # 10 minutes
            lsp_command=["custom-lsp", "--stdio"],
            log_level="DEBUG",
            log_mode="stderr",
            log_file=None,
            enable_health_check=True,
        )
        client = LSPClient(config=config)
        assert client.config.lsp_timeout == 600.0
        assert client.config.lsp_command == ["custom-lsp", "--stdio"]


class TestLSPClientHoverParsing:
    """Tests for LSPClient hover response parsing."""

    def test_parse_hover_response_none(self):
        """Test parsing None hover response."""
        client = LSPClient()
        result = client._parse_hover_response(None)
        assert isinstance(result, HoverResult)
        assert result.type_info is None
        assert result.documentation is None
        assert result.range is None

    def test_parse_hover_response_string_content(self):
        """Test parsing hover response with string content."""
        client = LSPClient()
        result = client._parse_hover_response({"contents": "int"})
        assert result.type_info == "int"

    def test_parse_hover_response_markup_content(self):
        """Test parsing hover response with MarkupContent."""
        client = LSPClient()
        result = client._parse_hover_response({
            "contents": {
                "kind": "plaintext",
                "value": "(x: int, y: int) -> int",
            }
        })
        assert result.type_info == "(x: int, y: int) -> int"

    def test_parse_hover_response_array_content(self):
        """Test parsing hover response with array of content."""
        client = LSPClient()
        result = client._parse_hover_response({
            "contents": [
                {"language": "python", "value": "def add(x: int, y: int) -> int"},
                "Add two numbers.",
            ]
        })
        assert result.type_info == "def add(x: int, y: int) -> int"
        assert result.documentation == "Add two numbers."

    def test_parse_hover_response_with_range(self):
        """Test parsing hover response with range."""
        client = LSPClient()
        result = client._parse_hover_response({
            "contents": "int",
            "range": {
                "start": {"line": 10, "character": 5},
                "end": {"line": 10, "character": 8},
            }
        })
        assert result.type_info == "int"
        assert result.range is not None
        assert result.range.start.line == 10
        assert result.range.start.column == 5


class TestLSPClientDefinitionParsing:
    """Tests for LSPClient definition response parsing."""

    def test_parse_definition_response_none(self):
        """Test parsing None definition response."""
        client = LSPClient()
        result = client._parse_definition_response(None)
        assert isinstance(result, DefinitionResult)
        assert result.definitions == []

    def test_parse_definition_response_single_location(self):
        """Test parsing single Location response."""
        client = LSPClient()
        result = client._parse_definition_response({
            "uri": "file:///path/to/module.py",
            "range": {
                "start": {"line": 5, "character": 4},
                "end": {"line": 5, "character": 10},
            }
        })
        assert len(result.definitions) == 1
        assert result.definitions[0].file == Path("/path/to/module.py")
        assert result.definitions[0].position.line == 5
        assert result.definitions[0].position.column == 4

    def test_parse_definition_response_location_array(self):
        """Test parsing array of Location responses."""
        client = LSPClient()
        result = client._parse_definition_response([
            {
                "uri": "file:///path/to/module1.py",
                "range": {"start": {"line": 5, "character": 4}, "end": {"line": 5, "character": 10}},
            },
            {
                "uri": "file:///path/to/module2.py",
                "range": {"start": {"line": 10, "character": 0}, "end": {"line": 10, "character": 6}},
            },
        ])
        assert len(result.definitions) == 2
        assert result.definitions[0].file == Path("/path/to/module1.py")
        assert result.definitions[1].file == Path("/path/to/module2.py")

    def test_parse_definition_response_location_link(self):
        """Test parsing LocationLink response."""
        client = LSPClient()
        result = client._parse_definition_response([{
            "targetUri": "file:///path/to/target.py",
            "targetRange": {
                "start": {"line": 20, "character": 0},
                "end": {"line": 25, "character": 0},
            },
            "targetSelectionRange": {
                "start": {"line": 20, "character": 4},
                "end": {"line": 20, "character": 12},
            },
        }])
        assert len(result.definitions) == 1
        # Should use targetSelectionRange for position
        assert result.definitions[0].position.line == 20
        assert result.definitions[0].position.column == 4


class TestHoverResultToDict:
    """Tests for HoverResult.to_dict()."""

    def test_hover_result_to_dict_with_all_fields(self):
        """Test HoverResult.to_dict() with all fields populated."""
        result = HoverResult(
            type_info="def add(x: int, y: int) -> int",
            documentation="Add two numbers.",
            range=Range(
                start=Position(line=5, column=4),
                end=Position(line=5, column=7),
            ),
        )
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["type"] == "def add(x: int, y: int) -> int"
        assert d["documentation"] == "Add two numbers."
        # symbol is extracted from type_info (text before first '(')
        assert d["symbol"] == "def add"

    def test_hover_result_to_dict_with_none_fields(self):
        """Test HoverResult.to_dict() with None fields."""
        result = HoverResult(type_info=None, documentation=None, range=None)
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["type"] is None
        assert d["documentation"] is None
        assert d["symbol"] is None


class TestDefinitionResultToDict:
    """Tests for DefinitionResult.to_dict()."""

    def test_definition_result_to_dict_empty(self):
        """Test DefinitionResult.to_dict() with empty definitions."""
        result = DefinitionResult(definitions=[])
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["definitions"] == []

    def test_definition_result_to_dict_with_definitions(self):
        """Test DefinitionResult.to_dict() with definitions."""
        result = DefinitionResult(definitions=[
            Location(file=Path("/path/to/file.py"), position=Position(line=4, column=3)),
        ])
        d = result.to_dict()
        assert d["status"] == "success"
        assert len(d["definitions"]) == 1
        # Positions are converted to 1-indexed
        assert d["definitions"][0]["line"] == 5
        assert d["definitions"][0]["column"] == 4


class TestLocationToDict:
    """Tests for Location.to_dict()."""

    def test_location_to_dict_converts_to_one_indexed(self):
        """Test Location.to_dict() converts 0-indexed to 1-indexed."""
        loc = Location(
            file=Path("/path/to/file.py"),
            position=Position(line=0, column=0),
        )
        d = loc.to_dict()
        assert d["file"] == "/path/to/file.py"
        assert d["line"] == 1  # 0 + 1
        assert d["column"] == 1  # 0 + 1


class TestLSPClientWithMockedProcess:
    """Tests for LSPClient with mocked subprocess."""

    @pytest.fixture
    def mock_subprocess(self):
        """Create a mock subprocess for LSP testing."""
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.drain = AsyncMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        return mock_proc

    @pytest.mark.asyncio
    async def test_ensure_initialized_handles_file_not_found(self, tmp_path: Path):
        """Test ensure_initialized handles missing LSP executable."""
        client = LSPClient()

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_create.side_effect = FileNotFoundError("pyright-langserver not found")

            with pytest.raises(BackendError) as exc_info:
                await client.ensure_initialized(tmp_path)

            assert exc_info.value.error_code == "not_found"
            assert "pyright" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_shutdown_when_not_started(self):
        """Test shutdown is safe when not started."""
        client = LSPClient()
        # Should not raise
        await client.shutdown()
        assert client.state == LSPState.NOT_STARTED

    @pytest.mark.asyncio
    async def test_cleanup_clears_state(self):
        """Test _cleanup resets internal state."""
        client = LSPClient()
        # Simulate some state
        client._state = LSPState.READY
        client._request_id = 10
        client._pending_requests = {1: AsyncMock()}

        await client._cleanup()

        assert client._state == LSPState.NOT_STARTED
        assert client._process is None
        assert client._request_id == 0
        assert client._pending_requests == {}


class TestLSPClientIdleTimeout:
    """Tests for LSP client idle timeout."""

    @pytest.mark.asyncio
    async def test_check_idle_timeout_when_not_ready(self):
        """Test check_idle_timeout returns False when not ready."""
        client = LSPClient()
        result = await client.check_idle_timeout()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_idle_timeout_when_not_expired(self):
        """Test check_idle_timeout returns False when not expired."""
        import time

        client = LSPClient()
        client._state = LSPState.READY
        client._process = MagicMock()
        client._process.last_activity = time.time()  # Just now
        client._process.process = MagicMock()
        client._process.process.returncode = None

        result = await client.check_idle_timeout()
        assert result is False


class TestLSPClientIdleTimeoutWatcher:
    """Tests for LSP idle timeout watcher task."""

    def test_watcher_task_field_initialized(self):
        """Test that watcher task field is initialized to None."""
        client = LSPClient()
        assert client._watcher_task is None

    @pytest.mark.asyncio
    async def test_watcher_stops_on_cleanup(self):
        """Test that watcher task is cancelled during cleanup."""
        import time

        config = Config(
            allowed_paths=None,
            cli_timeout=30.0,
            lsp_timeout=1.0,
            lsp_command=["pyright-langserver", "--stdio"],
            log_level="INFO",
            log_mode="stderr",
            log_file=None,
            enable_health_check=True,
        )
        client = LSPClient(config)

        # Set up LSP in READY state
        client._state = LSPState.READY
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.wait = AsyncMock()
        mock_proc.kill = MagicMock()

        mock_process = MagicMock()
        mock_process.process = mock_proc
        mock_process.last_activity = time.time()
        client._process = mock_process

        # Start the watcher manually
        client._watcher_task = asyncio.create_task(client._idle_timeout_watcher())
        await asyncio.sleep(0.01)  # Let it start

        # Verify watcher task exists
        assert client._watcher_task is not None

        # Call cleanup (which should cancel watcher)
        await client._cleanup()

        # Watcher should be None after cleanup
        assert client._watcher_task is None

    @pytest.mark.asyncio
    async def test_idle_timeout_watcher_respects_state(self):
        """Test that idle timeout watcher stops when state is not READY."""
        import time

        client = LSPClient()

        # Create mock process
        mock_process = MagicMock()
        mock_process.last_activity = time.time()
        client._process = mock_process

        # Set state to NOT_STARTED (should cause watcher to exit immediately)
        client._state = LSPState.NOT_STARTED

        # Run watcher (should exit immediately)
        await client._idle_timeout_watcher()

        # If we get here without hanging, test passes
        assert True
