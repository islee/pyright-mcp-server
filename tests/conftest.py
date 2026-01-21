"""Pytest configuration and shared fixtures."""

import os
from pathlib import Path
from typing import Iterator

import pytest

from pyright_mcp.config import reset_config


@pytest.fixture(autouse=True)
def reset_config_fixture() -> Iterator[None]:
    """Reset config singleton between tests for isolation."""
    reset_config()
    yield
    reset_config()


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def valid_python_file(tmp_path: Path) -> Path:
    """Create a valid Python file with no type errors."""
    file_path = tmp_path / "valid.py"
    file_path.write_text(
        """
def greet(name: str) -> str:
    return f"Hello, {name}!"

result: str = greet("World")
"""
    )
    return file_path


@pytest.fixture
def invalid_python_file(tmp_path: Path) -> Path:
    """Create a Python file with type errors."""
    file_path = tmp_path / "invalid.py"
    file_path.write_text(
        """
def add(a: int, b: int) -> int:
    return a + b

# Type error: passing str to function expecting int
result: int = add("5", 10)  # type: ignore
"""
    )
    return file_path


@pytest.fixture
def python_file_with_errors(tmp_path: Path) -> Path:
    """Create a Python file with multiple type errors."""
    file_path = tmp_path / "errors.py"
    file_path.write_text(
        """
def process(value: int) -> str:
    return str(value)

# Multiple type errors
x: str = 123  # Error: int not assignable to str
y: int = process(10)  # Error: str not assignable to int
z = process("invalid")  # Error: str not assignable to int parameter
"""
    )
    return file_path


@pytest.fixture
def project_with_config(tmp_path: Path) -> Path:
    """Create a project directory with pyrightconfig.json."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    # Create pyrightconfig.json
    config_file = project_dir / "pyrightconfig.json"
    config_file.write_text(
        """
{
    "pythonVersion": "3.11",
    "typeCheckingMode": "strict"
}
"""
    )

    # Create a Python file
    src_file = project_dir / "src.py"
    src_file.write_text(
        """
def example() -> int:
    return 42
"""
    )

    return project_dir


@pytest.fixture
def project_with_pyproject(tmp_path: Path) -> Path:
    """Create a project directory with pyproject.toml."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    # Create pyproject.toml with [tool.pyright] section
    config_file = project_dir / "pyproject.toml"
    config_file.write_text(
        """
[tool.pyright]
pythonVersion = "3.10"
typeCheckingMode = "basic"
"""
    )

    # Create a Python file
    src_file = project_dir / "src.py"
    src_file.write_text(
        """
def example() -> str:
    return "hello"
"""
    )

    return project_dir


@pytest.fixture
def project_with_venv(tmp_path: Path) -> Path:
    """Create a project directory with a .venv directory."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    # Create .venv directory with bin/python
    venv_dir = project_dir / ".venv"
    venv_dir.mkdir()
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir()
    python_path = bin_dir / "python"
    python_path.touch()
    python_path.chmod(0o755)

    return project_dir


@pytest.fixture
def set_env_vars():
    """Fixture to temporarily set environment variables."""

    def _set_env_vars(**kwargs: str) -> None:
        for key, value in kwargs.items():
            os.environ[key] = value

    yield _set_env_vars

    # Cleanup: remove all PYRIGHT_MCP_ env vars
    keys_to_remove = [key for key in os.environ if key.startswith("PYRIGHT_MCP_")]
    for key in keys_to_remove:
        del os.environ[key]
