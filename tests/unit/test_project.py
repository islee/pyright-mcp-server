"""Unit tests for project context detection."""

import os
from pathlib import Path

import pytest

from pyright_mcp.context.project import (
    ProjectContext,
    detect_project,
    detect_venv,
    extract_python_version,
    find_config_file,
)


class TestFindConfigFile:
    """Tests for find_config_file() function."""

    def test_find_config_file_with_pyrightconfig(
        self, project_with_config: Path
    ):
        """Test find_config_file() finds pyrightconfig.json."""
        config_file = find_config_file(project_with_config)
        assert config_file is not None
        assert config_file.name == "pyrightconfig.json"
        assert config_file.parent == project_with_config

    def test_find_config_file_with_pyproject(self, project_with_pyproject: Path):
        """Test find_config_file() finds pyproject.toml with [tool.pyright]."""
        config_file = find_config_file(project_with_pyproject)
        assert config_file is not None
        assert config_file.name == "pyproject.toml"
        assert config_file.parent == project_with_pyproject

    def test_find_config_file_priority_pyrightconfig_over_pyproject(
        self, tmp_path: Path
    ):
        """Test find_config_file() prioritizes pyrightconfig.json over pyproject.toml."""
        # Create both config files
        pyrightconfig = tmp_path / "pyrightconfig.json"
        pyrightconfig.write_text('{"pythonVersion": "3.11"}')

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.pyright]\npythonVersion = "3.10"')

        config_file = find_config_file(tmp_path)
        assert config_file is not None
        assert config_file.name == "pyrightconfig.json"

    def test_find_config_file_walks_up_directory_tree(self, tmp_path: Path):
        """Test find_config_file() walks up directory tree to find config."""
        # Create config in parent
        pyrightconfig = tmp_path / "pyrightconfig.json"
        pyrightconfig.write_text('{"pythonVersion": "3.11"}')

        # Start search from nested directory
        nested = tmp_path / "src" / "package"
        nested.mkdir(parents=True)

        config_file = find_config_file(nested)
        assert config_file is not None
        assert config_file == pyrightconfig

    def test_find_config_file_returns_none_when_not_found(self, tmp_path: Path):
        """Test find_config_file() returns None when no config found."""
        config_file = find_config_file(tmp_path)
        assert config_file is None

    def test_find_config_file_ignores_pyproject_without_pyright_section(
        self, tmp_path: Path
    ):
        """Test find_config_file() ignores pyproject.toml without [tool.pyright]."""
        # Create pyproject.toml without [tool.pyright]
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[build-system]\nrequires = ["hatchling"]')

        config_file = find_config_file(tmp_path)
        assert config_file is None

    def test_find_config_file_fallback_to_parent(self, tmp_path: Path):
        """Test find_config_file() falls back to parent directories."""
        # Create config in root
        root_config = tmp_path / "pyrightconfig.json"
        root_config.write_text("{}")

        # Create nested structure
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)

        # Should find root config
        config_file = find_config_file(deep)
        assert config_file == root_config


class TestDetectVenv:
    """Tests for detect_venv() function."""

    def test_detect_venv_finds_dot_venv(self, project_with_venv: Path):
        """Test detect_venv() finds .venv directory."""
        # Clear VIRTUAL_ENV to avoid interference
        original = os.environ.get("VIRTUAL_ENV")
        try:
            if "VIRTUAL_ENV" in os.environ:
                del os.environ["VIRTUAL_ENV"]
            venv_path = detect_venv(project_with_venv)
            assert venv_path is not None
            assert venv_path.name == ".venv"
            assert venv_path.parent == project_with_venv
        finally:
            if original is not None:
                os.environ["VIRTUAL_ENV"] = original

    def test_detect_venv_finds_venv_directory(self, tmp_path: Path):
        """Test detect_venv() finds venv/ directory."""
        # Clear VIRTUAL_ENV to avoid interference
        original = os.environ.get("VIRTUAL_ENV")
        try:
            if "VIRTUAL_ENV" in os.environ:
                del os.environ["VIRTUAL_ENV"]
            # Create venv/ with python executable
            venv_dir = tmp_path / "venv"
            venv_dir.mkdir()
            bin_dir = venv_dir / "bin"
            bin_dir.mkdir()
            python = bin_dir / "python"
            python.touch()
            python.chmod(0o755)

            venv_path = detect_venv(tmp_path)
            assert venv_path is not None
            assert venv_path.name == "venv"
        finally:
            if original is not None:
                os.environ["VIRTUAL_ENV"] = original

    def test_detect_venv_prefers_dot_venv_over_venv(self, tmp_path: Path):
        """Test detect_venv() prefers .venv over venv."""
        # Create both .venv and venv
        dot_venv = tmp_path / ".venv"
        dot_venv.mkdir()
        (dot_venv / "bin").mkdir()
        (dot_venv / "bin" / "python").touch()

        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").touch()

        venv_path = detect_venv(tmp_path)
        assert venv_path is not None
        assert venv_path.name == ".venv"

    def test_detect_venv_respects_virtual_env_var(self, tmp_path: Path):
        """Test detect_venv() respects VIRTUAL_ENV environment variable."""
        # Create venv in custom location
        custom_venv = tmp_path / "custom_venv"
        custom_venv.mkdir()
        bin_dir = custom_venv / "bin"
        bin_dir.mkdir()
        python = bin_dir / "python"
        python.touch()
        python.chmod(0o755)

        # Set VIRTUAL_ENV
        original = os.environ.get("VIRTUAL_ENV")
        try:
            os.environ["VIRTUAL_ENV"] = str(custom_venv)
            venv_path = detect_venv(tmp_path)
            assert venv_path == custom_venv.resolve()
        finally:
            if original is not None:
                os.environ["VIRTUAL_ENV"] = original
            elif "VIRTUAL_ENV" in os.environ:
                del os.environ["VIRTUAL_ENV"]

    def test_detect_venv_returns_none_when_not_found(self, tmp_path: Path):
        """Test detect_venv() returns None when no venv found."""
        # Clear VIRTUAL_ENV to avoid interference
        original = os.environ.get("VIRTUAL_ENV")
        try:
            if "VIRTUAL_ENV" in os.environ:
                del os.environ["VIRTUAL_ENV"]
            venv_path = detect_venv(tmp_path)
            assert venv_path is None
        finally:
            if original is not None:
                os.environ["VIRTUAL_ENV"] = original

    def test_detect_venv_validates_venv_has_python(self, tmp_path: Path):
        """Test detect_venv() validates venv has python executable."""
        # Clear VIRTUAL_ENV to avoid interference
        original = os.environ.get("VIRTUAL_ENV")
        try:
            if "VIRTUAL_ENV" in os.environ:
                del os.environ["VIRTUAL_ENV"]
            # Create .venv without python executable
            venv_dir = tmp_path / ".venv"
            venv_dir.mkdir()
            (venv_dir / "bin").mkdir()  # No python inside

            venv_path = detect_venv(tmp_path)
            assert venv_path is None
        finally:
            if original is not None:
                os.environ["VIRTUAL_ENV"] = original

    def test_detect_venv_finds_python3_executable(self, tmp_path: Path):
        """Test detect_venv() recognizes python3 executable."""
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        # Create python3 instead of python
        python3 = bin_dir / "python3"
        python3.touch()
        python3.chmod(0o755)

        venv_path = detect_venv(tmp_path)
        assert venv_path is not None


class TestExtractPythonVersion:
    """Tests for extract_python_version() function."""

    def test_extract_python_version_from_pyrightconfig(self, tmp_path: Path):
        """Test extract_python_version() from pyrightconfig.json."""
        config_file = tmp_path / "pyrightconfig.json"
        config_file.write_text('{"pythonVersion": "3.11"}')

        version = extract_python_version(config_file)
        assert version == "3.11"

    def test_extract_python_version_from_pyproject(self, tmp_path: Path):
        """Test extract_python_version() from pyproject.toml."""
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text('[tool.pyright]\npythonVersion = "3.10"')

        version = extract_python_version(config_file)
        assert version == "3.10"

    def test_extract_python_version_returns_none_when_not_present(
        self, tmp_path: Path
    ):
        """Test extract_python_version() returns None when version not in config."""
        config_file = tmp_path / "pyrightconfig.json"
        config_file.write_text('{"typeCheckingMode": "strict"}')

        version = extract_python_version(config_file)
        assert version is None

    def test_extract_python_version_handles_invalid_json(self, tmp_path: Path):
        """Test extract_python_version() handles invalid JSON gracefully."""
        config_file = tmp_path / "pyrightconfig.json"
        config_file.write_text("invalid json{")

        version = extract_python_version(config_file)
        assert version is None

    def test_extract_python_version_handles_unknown_file_type(self, tmp_path: Path):
        """Test extract_python_version() handles unknown file types."""
        config_file = tmp_path / "unknown.conf"
        config_file.write_text("some content")

        version = extract_python_version(config_file)
        assert version is None


@pytest.mark.asyncio
class TestDetectProject:
    """Tests for detect_project() async function."""

    async def test_detect_project_finds_pyrightconfig(
        self, project_with_config: Path
    ):
        """Test detect_project() finds project with pyrightconfig.json."""
        src_file = project_with_config / "src.py"
        context = await detect_project(src_file)

        assert context.root == project_with_config
        assert context.config_file is not None
        assert context.config_file.name == "pyrightconfig.json"

    async def test_detect_project_finds_pyproject_toml(
        self, project_with_pyproject: Path
    ):
        """Test detect_project() finds project with pyproject.toml."""
        src_file = project_with_pyproject / "src.py"
        context = await detect_project(src_file)

        assert context.root == project_with_pyproject
        assert context.config_file is not None
        assert context.config_file.name == "pyproject.toml"

    async def test_detect_project_extracts_python_version(
        self, project_with_config: Path
    ):
        """Test detect_project() extracts Python version from config."""
        src_file = project_with_config / "src.py"
        context = await detect_project(src_file)

        assert context.python_version == "3.11"

    async def test_detect_project_detects_venv(self, tmp_path: Path):
        """Test detect_project() detects virtual environment."""
        # Create project with config and venv
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        config_file = project_dir / "pyrightconfig.json"
        config_file.write_text("{}")

        venv_dir = project_dir / ".venv"
        venv_dir.mkdir()
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        python = bin_dir / "python"
        python.touch()
        python.chmod(0o755)

        src_file = project_dir / "src.py"
        src_file.touch()

        context = await detect_project(src_file)
        assert context.venv_path is not None
        assert context.venv_path.name == ".venv"

    async def test_detect_project_fallback_to_path_when_no_config(
        self, tmp_path: Path
    ):
        """Test detect_project() uses path as root when no config found."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        context = await detect_project(test_file)
        assert context.root == tmp_path
        assert context.config_file is None

    async def test_detect_project_with_directory(self, project_with_config: Path):
        """Test detect_project() works with directory path."""
        context = await detect_project(project_with_config)

        assert context.root == project_with_config
        assert context.config_file is not None

    async def test_detect_project_walks_up_from_nested_file(self, tmp_path: Path):
        """Test detect_project() walks up from nested file to find config."""
        # Create config in root
        config_file = tmp_path / "pyrightconfig.json"
        config_file.write_text('{"pythonVersion": "3.11"}')

        # Create nested file
        nested = tmp_path / "src" / "package" / "module.py"
        nested.parent.mkdir(parents=True)
        nested.touch()

        context = await detect_project(nested)
        assert context.root == tmp_path
        assert context.config_file == config_file
        assert context.python_version == "3.11"

    async def test_detect_project_returns_project_context(self, tmp_path: Path):
        """Test detect_project() returns ProjectContext instance."""
        test_file = tmp_path / "test.py"
        test_file.touch()

        context = await detect_project(test_file)
        assert isinstance(context, ProjectContext)
        assert hasattr(context, "root")
        assert hasattr(context, "config_file")
        assert hasattr(context, "venv_path")
        assert hasattr(context, "python_version")
