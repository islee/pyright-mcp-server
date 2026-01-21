"""Integration tests for check_types tool.

These tests actually invoke Pyright CLI, so they require pyright to be installed.
"""

from pathlib import Path

import pytest

from pyright_mcp.tools.check_types import check_types


@pytest.mark.integration
@pytest.mark.asyncio
class TestCheckTypesIntegration:
    """Integration tests for check_types() function."""

    async def test_check_types_with_valid_file(self, valid_python_file: Path):
        """Test check_types() with a valid Python file (no errors)."""
        result = await check_types(str(valid_python_file))

        assert result["status"] == "success"
        assert result["files_analyzed"] >= 1
        assert result["error_count"] == 0
        assert "summary" in result
        assert "diagnostics" in result
        assert isinstance(result["diagnostics"], list)

    async def test_check_types_with_file_containing_errors(
        self, python_file_with_errors: Path
    ):
        """Test check_types() with a file containing type errors."""
        result = await check_types(str(python_file_with_errors))

        assert result["status"] == "success"
        assert result["files_analyzed"] >= 1
        assert result["error_count"] > 0
        assert len(result["diagnostics"]) > 0

        # Check diagnostic structure
        diag = result["diagnostics"][0]
        assert "file" in diag
        assert "location" in diag
        assert "severity" in diag
        assert "message" in diag

    async def test_check_types_with_nonexistent_path(self, tmp_path: Path):
        """Test check_types() with non-existent path returns error."""
        nonexistent = tmp_path / "does_not_exist.py"
        result = await check_types(str(nonexistent))

        assert result["status"] == "error"
        assert result["error_code"] == "validation_error"
        assert "does not exist" in result["message"].lower()

    async def test_check_types_discriminated_union_response_format(
        self, valid_python_file: Path
    ):
        """Test check_types() returns discriminated union with status field."""
        result = await check_types(str(valid_python_file))

        # Should have status field
        assert "status" in result
        assert result["status"] in ["success", "error"]

        # Success response should have specific fields
        if result["status"] == "success":
            assert "summary" in result
            assert "files_analyzed" in result
            assert "error_count" in result
            assert "warning_count" in result
            assert "information_count" in result
            assert "hint_count" in result
            assert "diagnostics" in result

    async def test_check_types_with_directory(self, project_with_config: Path):
        """Test check_types() can analyze an entire directory."""
        result = await check_types(str(project_with_config))

        assert result["status"] == "success"
        assert result["files_analyzed"] >= 1

    async def test_check_types_with_python_version_parameter(
        self, valid_python_file: Path
    ):
        """Test check_types() accepts python_version parameter."""
        result = await check_types(str(valid_python_file), python_version="3.11")

        assert result["status"] == "success"
        assert result["files_analyzed"] >= 1

    async def test_check_types_diagnostic_positions_are_one_indexed(
        self, python_file_with_errors: Path
    ):
        """Test check_types() returns 1-indexed positions for display."""
        result = await check_types(str(python_file_with_errors))

        assert result["status"] == "success"
        if len(result["diagnostics"]) > 0:
            diag = result["diagnostics"][0]
            location = diag["location"]
            # Location should be in format "line:col" or "line:col-line:col"
            assert ":" in location
            # Lines and columns should be 1-indexed (>= 1)
            parts = location.split("-")[0].split(":")
            line = int(parts[0])
            col = int(parts[1])
            assert line >= 1
            assert col >= 1

    async def test_check_types_detects_project_context(
        self, project_with_config: Path
    ):
        """Test check_types() detects and uses project configuration."""
        src_file = project_with_config / "src.py"
        result = await check_types(str(src_file))

        # Should successfully analyze using project config
        assert result["status"] == "success"
        assert result["files_analyzed"] >= 1

    async def test_check_types_with_relative_path(self, valid_python_file: Path):
        """Test check_types() handles relative paths by normalizing them."""
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(valid_python_file.parent)
            relative_path = valid_python_file.name
            result = await check_types(relative_path)

            assert result["status"] == "success"
            assert result["files_analyzed"] >= 1
        finally:
            os.chdir(original_cwd)

    async def test_check_types_with_empty_string_returns_error(self):
        """Test check_types() returns validation error for empty string."""
        result = await check_types("")

        assert result["status"] == "error"
        assert result["error_code"] == "validation_error"
        assert "cannot be empty" in result["message"]

    async def test_check_types_with_allowed_paths_restriction(
        self, valid_python_file: Path, tmp_path: Path, set_env_vars
    ):
        """Test check_types() respects allowed_paths configuration."""
        # Create a forbidden directory
        forbidden_dir = tmp_path / "forbidden"
        forbidden_dir.mkdir()
        forbidden_file = forbidden_dir / "test.py"
        forbidden_file.write_text("def foo(): pass")

        # Set allowed paths to a different directory
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()

        # Set environment variable and reset config
        set_env_vars(PYRIGHT_MCP_ALLOWED_PATHS=str(allowed_dir))

        # Import after setting env var to get new config
        from pyright_mcp.config import reset_config

        reset_config()

        # This should fail because forbidden_file is not in allowed_paths
        result = await check_types(str(forbidden_file))

        assert result["status"] == "error"
        assert result["error_code"] == "validation_error"
        assert "not in allowed workspace" in result["message"]

    async def test_check_types_summary_counts_match_diagnostics(
        self, python_file_with_errors: Path
    ):
        """Test check_types() summary counts match actual diagnostics."""
        result = await check_types(str(python_file_with_errors))

        assert result["status"] == "success"

        # Count diagnostics by severity
        error_count = sum(
            1 for d in result["diagnostics"] if d["severity"] == "error"
        )
        warning_count = sum(
            1 for d in result["diagnostics"] if d["severity"] == "warning"
        )
        information_count = sum(
            1 for d in result["diagnostics"] if d["severity"] == "information"
        )
        hint_count = sum(
            1 for d in result["diagnostics"] if d["severity"] == "hint"
        )

        # Should match reported counts
        assert result["error_count"] == error_count
        assert result["warning_count"] == warning_count
        assert result["information_count"] == information_count
        assert result["hint_count"] == hint_count

    async def test_check_types_diagnostic_includes_rule(
        self, python_file_with_errors: Path
    ):
        """Test check_types() diagnostics include rule field when available."""
        result = await check_types(str(python_file_with_errors))

        assert result["status"] == "success"
        if len(result["diagnostics"]) > 0:
            diag = result["diagnostics"][0]
            # Rule field should exist (may be None or a string)
            assert "rule" in diag

    async def test_check_types_with_multiple_files(self, tmp_path: Path):
        """Test check_types() can analyze multiple files in a directory."""
        # Create multiple Python files
        file1 = tmp_path / "file1.py"
        file1.write_text("def foo() -> int: return 42")

        file2 = tmp_path / "file2.py"
        file2.write_text("def bar() -> str: return 'hello'")

        result = await check_types(str(tmp_path))

        assert result["status"] == "success"
        assert result["files_analyzed"] >= 2

    async def test_check_types_handles_syntax_errors(self, tmp_path: Path):
        """Test check_types() handles files with syntax errors."""
        syntax_error_file = tmp_path / "syntax_error.py"
        syntax_error_file.write_text("def foo(\n")  # Incomplete syntax

        result = await check_types(str(syntax_error_file))

        # Pyright should report syntax error
        assert result["status"] == "success"
        # Should have at least one diagnostic (syntax error)
        assert len(result["diagnostics"]) > 0

    async def test_check_types_empty_directory(self, tmp_path: Path):
        """Test check_types() with empty directory (no Python files)."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = await check_types(str(empty_dir))

        # Should succeed but analyze 0 files
        assert result["status"] == "success"
        assert result["files_analyzed"] == 0
