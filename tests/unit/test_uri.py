"""Unit tests for URI and path conversion utilities."""

import sys
from pathlib import Path

import pytest

from pyright_mcp.utils.uri import normalize_path, path_to_uri, uri_to_path


class TestPathToUri:
    """Tests for path_to_uri() function."""

    def test_path_to_uri_unix_path(self, tmp_path: Path):
        """Test path_to_uri() with Unix paths."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        uri = path_to_uri(test_file)
        assert uri.startswith("file://")
        assert str(test_file) in uri or str(test_file.resolve()) in uri

    def test_path_to_uri_with_spaces(self, tmp_path: Path):
        """Test path_to_uri() with paths containing spaces."""
        test_file = tmp_path / "test file.py"
        test_file.touch()

        uri = path_to_uri(test_file)
        assert uri.startswith("file://")
        # Spaces should be URL-encoded
        assert "%20" in uri or " " not in uri

    def test_path_to_uri_returns_absolute_uri(self, tmp_path: Path):
        """Test path_to_uri() returns absolute file:// URI."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        uri = path_to_uri(test_file)
        # Should have file:// prefix
        assert uri.startswith("file://")
        # Should contain absolute path
        assert test_file.resolve().name in uri

    def test_path_to_uri_resolves_relative_paths(self, tmp_path: Path):
        """Test path_to_uri() resolves relative paths."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        # Get relative path
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            relative = Path("test.py")
            uri = path_to_uri(relative)
            assert uri.startswith("file://")
            # Should be resolved to absolute
            assert str(test_file.resolve()) in uri or test_file.resolve().name in uri
        finally:
            os.chdir(original_cwd)


class TestUriToPath:
    """Tests for uri_to_path() function."""

    def test_uri_to_path_unix_uri(self, tmp_path: Path):
        """Test uri_to_path() with Unix file:// URI."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        uri = f"file://{test_file}"
        path = uri_to_path(uri)
        assert path == test_file

    def test_uri_to_path_with_spaces(self, tmp_path: Path):
        """Test uri_to_path() with URL-encoded spaces."""
        test_file = tmp_path / "test file.py"
        test_file.touch()

        # Create URI with encoded space
        uri = f"file://{str(test_file).replace(' ', '%20')}"
        path = uri_to_path(uri)
        assert path == test_file
        assert " " in str(path)

    def test_uri_to_path_round_trip(self, tmp_path: Path):
        """Test path_to_uri() and uri_to_path() round-trip."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        uri = path_to_uri(test_file)
        path = uri_to_path(uri)
        # Should resolve to same absolute path
        assert path.resolve() == test_file.resolve()

    def test_uri_to_path_invalid_scheme_raises_error(self):
        """Test uri_to_path() raises ValueError for non-file:// URI."""
        with pytest.raises(ValueError, match="Expected file:// URI"):
            uri_to_path("http://example.com/file.py")

    def test_uri_to_path_handles_triple_slash(self, tmp_path: Path):
        """Test uri_to_path() handles file:/// (triple slash)."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        # Triple slash is common on Unix
        uri = f"file:///{test_file}"
        path = uri_to_path(uri)
        # Should strip extra slash
        assert path.is_absolute()

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Windows-specific test"
    )
    def test_uri_to_path_windows_drive_letter(self):
        """Test uri_to_path() handles Windows drive letters."""
        uri = "file:///C:/Users/test/file.py"
        path = uri_to_path(uri)
        assert str(path).startswith("C:")


class TestNormalizePath:
    """Tests for normalize_path() function."""

    def test_normalize_path_returns_absolute_path(self, tmp_path: Path):
        """Test normalize_path() returns absolute path."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            relative = Path("test.py")
            normalized = normalize_path(relative)
            assert normalized.is_absolute()
        finally:
            os.chdir(original_cwd)

    def test_normalize_path_accepts_string(self, tmp_path: Path):
        """Test normalize_path() accepts string path."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        normalized = normalize_path(str(test_file))
        assert isinstance(normalized, Path)
        assert normalized.is_absolute()

    def test_normalize_path_accepts_path_object(self, tmp_path: Path):
        """Test normalize_path() accepts Path object."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        normalized = normalize_path(test_file)
        assert isinstance(normalized, Path)
        assert normalized.is_absolute()

    def test_normalize_path_resolves_symlinks(self, tmp_path: Path):
        """Test normalize_path() resolves symlinks."""
        # Create a file and a symlink to it
        target = tmp_path / "target.py"
        target.touch()
        link = tmp_path / "link.py"

        try:
            link.symlink_to(target)
            normalized = normalize_path(link)
            # Should resolve to target
            assert normalized == target.resolve()
        except OSError:
            # Symlink creation might fail on some systems (e.g., Windows without admin)
            pytest.skip("Symlink creation not supported")

    def test_normalize_path_idempotent(self, tmp_path: Path):
        """Test normalize_path() is idempotent."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        normalized1 = normalize_path(test_file)
        normalized2 = normalize_path(normalized1)
        assert normalized1 == normalized2
