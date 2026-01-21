"""Unit tests for Pyright CLI runner backend.

These tests use mocks to avoid running actual Pyright commands.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyright_mcp.backends.base import BackendError, Diagnostic
from pyright_mcp.backends.cli_runner import (
    PyrightCLIRunner,
    build_pyright_command,
    parse_pyright_output,
    run_pyright,
)
from pyright_mcp.config import Config
from pyright_mcp.utils.position import Position, Range


class TestBuildPyrightCommand:
    """Tests for build_pyright_command() function."""

    def test_build_pyright_command_basic(self, tmp_path: Path):
        """Test build_pyright_command() with minimal arguments."""
        test_file = tmp_path / "test.py"
        cmd = build_pyright_command(test_file)

        assert cmd[0] == "pyright"
        assert "--outputjson" in cmd
        assert str(test_file) in cmd

    def test_build_pyright_command_with_project_root(self, tmp_path: Path):
        """Test build_pyright_command() with project_root."""
        test_file = tmp_path / "src" / "test.py"
        project_root = tmp_path

        cmd = build_pyright_command(test_file, project_root=project_root)

        assert "--project" in cmd
        assert str(project_root) in cmd

    def test_build_pyright_command_with_python_version(self, tmp_path: Path):
        """Test build_pyright_command() with python_version."""
        test_file = tmp_path / "test.py"

        cmd = build_pyright_command(test_file, python_version="3.11")

        assert "--pythonversion" in cmd
        assert "3.11" in cmd

    def test_build_pyright_command_with_all_options(self, tmp_path: Path):
        """Test build_pyright_command() with all options."""
        test_file = tmp_path / "src" / "test.py"
        project_root = tmp_path

        cmd = build_pyright_command(
            test_file, project_root=project_root, python_version="3.10"
        )

        assert cmd[0] == "pyright"
        assert "--outputjson" in cmd
        assert "--project" in cmd
        assert str(project_root) in cmd
        assert "--pythonversion" in cmd
        assert "3.10" in cmd
        assert str(test_file) == cmd[-1]  # Path should be last

    def test_build_pyright_command_returns_list(self, tmp_path: Path):
        """Test build_pyright_command() returns list of strings."""
        test_file = tmp_path / "test.py"
        cmd = build_pyright_command(test_file)

        assert isinstance(cmd, list)
        assert all(isinstance(arg, str) for arg in cmd)

    def test_build_pyright_command_safe_from_shell_injection(self, tmp_path: Path):
        """Test build_pyright_command() is safe from shell injection."""
        # Create file with shell metacharacters in name
        malicious_name = "test; rm -rf /;"
        test_file = tmp_path / malicious_name

        cmd = build_pyright_command(test_file)

        # Command should be a list (not a shell string)
        assert isinstance(cmd, list)
        # Malicious characters should be in the path argument as-is
        assert any(malicious_name in arg for arg in cmd)


class TestParseyrightOutput:
    """Tests for parse_pyright_output() function."""

    def test_parse_pyright_output_with_valid_json(self):
        """Test parse_pyright_output() with valid Pyright JSON output."""
        stdout = json.dumps(
            {
                "generalDiagnostics": [
                    {
                        "file": "/path/to/file.py",
                        "severity": 1,  # error
                        "message": "Type error message",
                        "range": {
                            "start": {"line": 10, "character": 5},
                            "end": {"line": 10, "character": 10},
                        },
                        "rule": "reportArgumentType",
                    }
                ],
                "summary": {
                    "filesAnalyzed": 1,
                    "errorCount": 1,
                    "warningCount": 0,
                    "informationCount": 0,
                    "timeInSec": 0.5,
                },
            }
        )

        result = parse_pyright_output(stdout, "", 0)

        assert result.files_analyzed == 1
        assert len(result.diagnostics) == 1
        assert "1 error" in result.summary

    def test_parse_pyright_output_severity_mapping(self):
        """Test parse_pyright_output() maps severity codes correctly."""
        stdout = json.dumps(
            {
                "generalDiagnostics": [
                    {
                        "file": "/path/to/file.py",
                        "severity": 1,
                        "message": "Error",
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 0, "character": 1},
                        },
                    },
                    {
                        "file": "/path/to/file.py",
                        "severity": 2,
                        "message": "Warning",
                        "range": {
                            "start": {"line": 1, "character": 0},
                            "end": {"line": 1, "character": 1},
                        },
                    },
                    {
                        "file": "/path/to/file.py",
                        "severity": 3,
                        "message": "Information",
                        "range": {
                            "start": {"line": 2, "character": 0},
                            "end": {"line": 2, "character": 1},
                        },
                    },
                ],
                "summary": {
                    "filesAnalyzed": 1,
                    "errorCount": 1,
                    "warningCount": 1,
                    "informationCount": 1,
                    "timeInSec": 0.5,
                },
            }
        )

        result = parse_pyright_output(stdout, "", 0)

        assert result.diagnostics[0].severity == "error"
        assert result.diagnostics[1].severity == "warning"
        assert result.diagnostics[2].severity == "information"

    def test_parse_pyright_output_with_parse_error(self):
        """Test parse_pyright_output() raises BackendError for invalid JSON."""
        stdout = "invalid json{"

        with pytest.raises(BackendError) as exc_info:
            parse_pyright_output(stdout, "", 0)

        assert exc_info.value.error_code == "parse_error"
        assert not exc_info.value.recoverable

    def test_parse_pyright_output_handles_nonzero_exit_code(self):
        """Test parse_pyright_output() handles non-zero exit code (still valid)."""
        stdout = json.dumps(
            {
                "generalDiagnostics": [],
                "summary": {
                    "filesAnalyzed": 1,
                    "errorCount": 0,
                    "warningCount": 0,
                    "informationCount": 0,
                    "timeInSec": 0.5,
                },
            }
        )

        # Pyright returns non-zero on errors, but output is still valid
        result = parse_pyright_output(stdout, "", 1)

        assert result.files_analyzed == 1
        assert len(result.diagnostics) == 0

    def test_parse_pyright_output_with_no_diagnostics(self):
        """Test parse_pyright_output() with no diagnostics."""
        stdout = json.dumps(
            {
                "generalDiagnostics": [],
                "summary": {
                    "filesAnalyzed": 5,
                    "errorCount": 0,
                    "warningCount": 0,
                    "informationCount": 0,
                    "timeInSec": 1.2,
                },
            }
        )

        result = parse_pyright_output(stdout, "", 0)

        assert result.files_analyzed == 5
        assert len(result.diagnostics) == 0
        assert "No issues found" in result.summary


@pytest.mark.asyncio
class TestRunPyright:
    """Tests for run_pyright() async function."""

    async def test_run_pyright_success(self):
        """Test run_pyright() with successful execution."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b'{"summary": {}}', b"")
        )
        mock_proc.returncode = 0

        with patch(
            "pyright_mcp.backends.cli_runner.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            stdout, stderr, return_code = await run_pyright(
                ["pyright", "--outputjson", "test.py"], timeout=30.0
            )

            assert stdout == '{"summary": {}}'
            assert stderr == ""
            assert return_code == 0

    async def test_run_pyright_timeout(self):
        """Test run_pyright() raises BackendError on timeout."""
        mock_proc = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        # Create a mock that raises TimeoutError
        async def mock_communicate():
            raise asyncio.TimeoutError()

        mock_proc.communicate = mock_communicate

        with patch(
            "pyright_mcp.backends.cli_runner.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_subprocess:
            # Also need to mock wait_for to raise TimeoutError
            async def mock_wait_for(coro, timeout):
                raise asyncio.TimeoutError()

            with patch(
                "pyright_mcp.backends.cli_runner.asyncio.wait_for",
                side_effect=mock_wait_for,
            ):
                with pytest.raises(BackendError) as exc_info:
                    await run_pyright(
                        ["pyright", "--outputjson", "test.py"], timeout=0.1
                    )

                assert exc_info.value.error_code == "timeout"
                assert exc_info.value.recoverable

    async def test_run_pyright_executable_not_found(self):
        """Test run_pyright() raises BackendError when pyright not found."""
        with patch(
            "pyright_mcp.backends.cli_runner.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("pyright not found"),
        ):
            with pytest.raises(BackendError) as exc_info:
                await run_pyright(
                    ["pyright", "--outputjson", "test.py"], timeout=30.0
                )

            assert exc_info.value.error_code == "not_found"
            assert not exc_info.value.recoverable


@pytest.mark.asyncio
class TestPyrightCLIRunner:
    """Tests for PyrightCLIRunner class."""

    async def test_pyright_cli_runner_initialization(self):
        """Test PyrightCLIRunner can be initialized."""
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
        runner = PyrightCLIRunner(config)
        assert runner.config == config

    async def test_pyright_cli_runner_check_success(self, tmp_path: Path):
        """Test PyrightCLIRunner.check() with successful type check."""
        test_file = tmp_path / "test.py"

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
        runner = PyrightCLIRunner(config)

        # Mock run_pyright
        mock_stdout = json.dumps(
            {
                "generalDiagnostics": [],
                "summary": {
                    "filesAnalyzed": 1,
                    "errorCount": 0,
                    "warningCount": 0,
                    "informationCount": 0,
                    "timeInSec": 0.5,
                },
            }
        )

        with patch(
            "pyright_mcp.backends.cli_runner.run_pyright",
            return_value=(mock_stdout, "", 0),
        ):
            result = await runner.check(test_file)

            assert result.files_analyzed == 1
            assert len(result.diagnostics) == 0

    async def test_pyright_cli_runner_check_with_errors(self, tmp_path: Path):
        """Test PyrightCLIRunner.check() with type errors."""
        test_file = tmp_path / "test.py"

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
        runner = PyrightCLIRunner(config)

        # Mock run_pyright with errors
        mock_stdout = json.dumps(
            {
                "generalDiagnostics": [
                    {
                        "file": str(test_file),
                        "severity": 1,
                        "message": "Type error",
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 0, "character": 1},
                        },
                        "rule": "reportArgumentType",
                    }
                ],
                "summary": {
                    "filesAnalyzed": 1,
                    "errorCount": 1,
                    "warningCount": 0,
                    "informationCount": 0,
                    "timeInSec": 0.5,
                },
            }
        )

        with patch(
            "pyright_mcp.backends.cli_runner.run_pyright",
            return_value=(mock_stdout, "", 1),  # Non-zero exit code
        ):
            result = await runner.check(test_file)

            assert result.files_analyzed == 1
            assert len(result.diagnostics) == 1
            assert result.diagnostics[0].severity == "error"

    async def test_pyright_cli_runner_check_timeout(self, tmp_path: Path):
        """Test PyrightCLIRunner.check() propagates timeout error."""
        test_file = tmp_path / "test.py"

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
        runner = PyrightCLIRunner(config)

        # Mock timeout
        with patch(
            "pyright_mcp.backends.cli_runner.run_pyright",
            side_effect=BackendError(
                error_code="timeout", message="Timeout", recoverable=True
            ),
        ):
            with pytest.raises(BackendError) as exc_info:
                await runner.check(test_file)

            assert exc_info.value.error_code == "timeout"
