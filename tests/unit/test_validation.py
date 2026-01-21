"""Unit tests for path validation and input validation."""

from pathlib import Path

import pytest

from pyright_mcp.validation.inputs import validate_check_types_input
from pyright_mcp.validation.paths import (
    ValidationError,
    is_path_allowed,
    validate_path,
)


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_validation_error_creation(self):
        """Test ValidationError can be created with field and message."""
        error = ValidationError("path", "Invalid path")
        assert error.field == "path"
        assert error.message == "Invalid path"
        assert str(error) == "Invalid path"

    def test_validation_error_to_error_response(self):
        """Test to_error_response() returns correct format."""
        error = ValidationError("path", "Path does not exist")
        response = error.to_error_response()
        assert response["status"] == "error"
        assert response["error_code"] == "validation_error"
        assert "path" in response["message"]
        assert "Path does not exist" in response["message"]


class TestValidatePath:
    """Tests for validate_path() function."""

    def test_validate_path_with_valid_path(self, tmp_path: Path):
        """Test validate_path() with existing path."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        result = validate_path(test_file)
        assert result == test_file.resolve()
        assert result.is_absolute()

    def test_validate_path_with_string_path(self, tmp_path: Path):
        """Test validate_path() accepts string path."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        result = validate_path(str(test_file))
        assert result == test_file.resolve()
        assert isinstance(result, Path)

    def test_validate_path_with_nonexistent_path_raises_error(self, tmp_path: Path):
        """Test validate_path() raises ValidationError for non-existent path."""
        nonexistent = tmp_path / "does_not_exist.py"

        with pytest.raises(ValidationError) as exc_info:
            validate_path(nonexistent)

        assert exc_info.value.field == "path"
        assert "does not exist" in exc_info.value.message.lower()

    def test_validate_path_with_allowed_paths_restriction(self, tmp_path: Path):
        """Test validate_path() enforces allowed_paths restriction."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        test_file = allowed_dir / "test.py"
        test_file.touch()

        result = validate_path(test_file, allowed_paths=[allowed_dir])
        assert result == test_file.resolve()

    def test_validate_path_outside_allowed_paths_raises_error(self, tmp_path: Path):
        """Test validate_path() raises error for path outside allowed_paths."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()

        forbidden_dir = tmp_path / "forbidden"
        forbidden_dir.mkdir()
        forbidden_file = forbidden_dir / "test.py"
        forbidden_file.touch()

        with pytest.raises(ValidationError) as exc_info:
            validate_path(forbidden_file, allowed_paths=[allowed_dir])

        assert exc_info.value.field == "path"
        assert "not in allowed workspace" in exc_info.value.message

    def test_validate_path_resolves_symlinks(self, tmp_path: Path):
        """Test validate_path() resolves symlinks."""
        target = tmp_path / "target.py"
        target.touch()
        link = tmp_path / "link.py"

        try:
            link.symlink_to(target)
            result = validate_path(link)
            # Should resolve to target
            assert result == target.resolve()
        except OSError:
            pytest.skip("Symlink creation not supported")

    def test_validate_path_with_relative_path(self, tmp_path: Path):
        """Test validate_path() converts relative to absolute path."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            relative = Path("test.py")
            result = validate_path(relative)
            assert result.is_absolute()
            assert result == test_file.resolve()
        finally:
            os.chdir(original_cwd)

    def test_validate_path_with_directory(self, tmp_path: Path):
        """Test validate_path() works with directories."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        result = validate_path(test_dir)
        assert result == test_dir.resolve()
        assert result.is_dir()


class TestIsPathAllowed:
    """Tests for is_path_allowed() function."""

    def test_is_path_allowed_returns_true_for_allowed_path(self, tmp_path: Path):
        """Test is_path_allowed() returns True for path within allowed directory."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        test_file = allowed_dir / "test.py"
        test_file.touch()

        result = is_path_allowed(test_file, [allowed_dir])
        assert result is True

    def test_is_path_allowed_returns_true_for_nested_path(self, tmp_path: Path):
        """Test is_path_allowed() returns True for nested path."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        nested_dir = allowed_dir / "nested" / "deep"
        nested_dir.mkdir(parents=True)
        test_file = nested_dir / "test.py"
        test_file.touch()

        result = is_path_allowed(test_file, [allowed_dir])
        assert result is True

    def test_is_path_allowed_returns_false_for_forbidden_path(self, tmp_path: Path):
        """Test is_path_allowed() returns False for path outside allowed directories."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()

        forbidden_dir = tmp_path / "forbidden"
        forbidden_dir.mkdir()
        test_file = forbidden_dir / "test.py"
        test_file.touch()

        result = is_path_allowed(test_file, [allowed_dir])
        assert result is False

    def test_is_path_allowed_with_multiple_allowed_paths(self, tmp_path: Path):
        """Test is_path_allowed() with multiple allowed directories."""
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        dir2 = tmp_path / "dir2"
        dir2.mkdir()

        file1 = dir1 / "test1.py"
        file1.touch()
        file2 = dir2 / "test2.py"
        file2.touch()

        allowed = [dir1, dir2]
        assert is_path_allowed(file1, allowed) is True
        assert is_path_allowed(file2, allowed) is True

    def test_is_path_allowed_with_parent_path(self, tmp_path: Path):
        """Test is_path_allowed() allows parent directory."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        # Parent should be allowed if it's the allowed path
        result = is_path_allowed(tmp_path, [tmp_path])
        assert result is True

    def test_is_path_allowed_resolves_symlinks(self, tmp_path: Path):
        """Test is_path_allowed() resolves symlinks before checking."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        target = allowed_dir / "target.py"
        target.touch()

        forbidden_dir = tmp_path / "forbidden"
        forbidden_dir.mkdir()
        link = forbidden_dir / "link.py"

        try:
            link.symlink_to(target)
            # Link points to allowed location, so should be allowed
            result = is_path_allowed(link, [allowed_dir])
            assert result is True
        except OSError:
            pytest.skip("Symlink creation not supported")


class TestValidateCheckTypesInput:
    """Tests for validate_check_types_input() function."""

    def test_validate_check_types_input_with_valid_path(self, tmp_path: Path):
        """Test validate_check_types_input() with valid path."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        result = validate_check_types_input(str(test_file))
        assert result == test_file.resolve()

    def test_validate_check_types_input_with_none_raises_error(self):
        """Test validate_check_types_input() raises error for None."""
        with pytest.raises(ValidationError) as exc_info:
            validate_check_types_input(None)

        assert exc_info.value.field == "path"
        assert "required" in exc_info.value.message

    def test_validate_check_types_input_with_empty_string_raises_error(self):
        """Test validate_check_types_input() raises error for empty string."""
        with pytest.raises(ValidationError) as exc_info:
            validate_check_types_input("")

        assert exc_info.value.field == "path"
        assert "cannot be empty" in exc_info.value.message

    def test_validate_check_types_input_with_whitespace_raises_error(self):
        """Test validate_check_types_input() raises error for whitespace-only string."""
        with pytest.raises(ValidationError) as exc_info:
            validate_check_types_input("   ")

        assert exc_info.value.field == "path"
        assert "cannot be empty" in exc_info.value.message

    def test_validate_check_types_input_with_nonexistent_path_raises_error(
        self, tmp_path: Path
    ):
        """Test validate_check_types_input() raises error for non-existent path."""
        nonexistent = tmp_path / "does_not_exist.py"

        with pytest.raises(ValidationError) as exc_info:
            validate_check_types_input(str(nonexistent))

        assert exc_info.value.field == "path"
        assert "does not exist" in exc_info.value.message.lower()

    def test_validate_check_types_input_returns_absolute_path(self, tmp_path: Path):
        """Test validate_check_types_input() returns normalized absolute path."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            relative = "test.py"
            result = validate_check_types_input(relative)
            assert result.is_absolute()
            assert result == test_file.resolve()
        finally:
            os.chdir(original_cwd)

    def test_validate_check_types_input_with_directory(self, tmp_path: Path):
        """Test validate_check_types_input() accepts directories."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        result = validate_check_types_input(str(test_dir))
        assert result == test_dir.resolve()
        assert result.is_dir()
