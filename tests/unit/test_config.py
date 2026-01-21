"""Unit tests for configuration management."""

import os
from pathlib import Path

import pytest

from pyright_mcp.config import Config, get_config, load_config, reset_config


class TestLoadConfig:
    """Tests for load_config() function."""

    def test_load_config_with_defaults(self):
        """Test load_config() returns defaults when no env vars set."""
        config = load_config()
        assert config.allowed_paths is None
        assert config.cli_timeout == 30.0
        assert config.lsp_timeout == 300.0
        assert config.lsp_command == ["pyright-langserver", "--stdio"]
        assert config.log_level == "INFO"
        assert config.log_mode == "stderr"
        assert config.log_file is None
        assert config.enable_health_check is True

    def test_load_config_with_custom_cli_timeout(self, set_env_vars):
        """Test load_config() with custom CLI timeout."""
        set_env_vars(PYRIGHT_MCP_CLI_TIMEOUT="60.0")
        config = load_config()
        assert config.cli_timeout == 60.0

    def test_load_config_with_custom_lsp_timeout(self, set_env_vars):
        """Test load_config() with custom LSP timeout."""
        set_env_vars(PYRIGHT_MCP_LSP_TIMEOUT="600.0")
        config = load_config()
        assert config.lsp_timeout == 600.0

    def test_load_config_with_custom_log_level(self, set_env_vars):
        """Test load_config() with custom log level."""
        set_env_vars(PYRIGHT_MCP_LOG_LEVEL="DEBUG")
        config = load_config()
        assert config.log_level == "DEBUG"

    def test_load_config_with_custom_log_mode(self, set_env_vars):
        """Test load_config() with custom log mode."""
        set_env_vars(PYRIGHT_MCP_LOG_MODE="file")
        config = load_config()
        assert config.log_mode == "file"

    def test_load_config_with_log_file(self, set_env_vars, tmp_path: Path):
        """Test load_config() with log file path."""
        log_file = tmp_path / "test.log"
        set_env_vars(PYRIGHT_MCP_LOG_FILE=str(log_file))
        config = load_config()
        assert config.log_file == log_file.resolve()

    def test_load_config_with_allowed_paths(self, set_env_vars, tmp_path: Path):
        """Test load_config() with allowed paths."""
        path1 = tmp_path / "path1"
        path2 = tmp_path / "path2"
        path1.mkdir()
        path2.mkdir()

        set_env_vars(PYRIGHT_MCP_ALLOWED_PATHS=f"{path1}:{path2}")
        config = load_config()
        assert config.allowed_paths is not None
        assert len(config.allowed_paths) == 2
        assert path1.resolve() in config.allowed_paths
        assert path2.resolve() in config.allowed_paths

    def test_load_config_with_custom_lsp_command(self, set_env_vars):
        """Test load_config() with custom LSP command."""
        set_env_vars(PYRIGHT_MCP_LSP_COMMAND="custom-pyright --stdio --verbose")
        config = load_config()
        assert config.lsp_command == ["custom-pyright", "--stdio", "--verbose"]

    def test_load_config_with_health_check_disabled(self, set_env_vars):
        """Test load_config() with health check disabled."""
        set_env_vars(PYRIGHT_MCP_ENABLE_HEALTH_CHECK="false")
        config = load_config()
        assert config.enable_health_check is False

    def test_load_config_invalid_cli_timeout_raises_error(self, set_env_vars):
        """Test load_config() raises ValueError for invalid CLI timeout."""
        set_env_vars(PYRIGHT_MCP_CLI_TIMEOUT="invalid")
        with pytest.raises(ValueError, match="must be a number"):
            load_config()

    def test_load_config_negative_cli_timeout_raises_error(self, set_env_vars):
        """Test load_config() raises ValueError for negative CLI timeout."""
        set_env_vars(PYRIGHT_MCP_CLI_TIMEOUT="-10.0")
        with pytest.raises(ValueError, match="must be positive"):
            load_config()

    def test_load_config_zero_cli_timeout_raises_error(self, set_env_vars):
        """Test load_config() raises ValueError for zero CLI timeout."""
        set_env_vars(PYRIGHT_MCP_CLI_TIMEOUT="0")
        with pytest.raises(ValueError, match="must be positive"):
            load_config()

    def test_load_config_invalid_lsp_timeout_raises_error(self, set_env_vars):
        """Test load_config() raises ValueError for invalid LSP timeout."""
        set_env_vars(PYRIGHT_MCP_LSP_TIMEOUT="invalid")
        with pytest.raises(ValueError, match="must be a number"):
            load_config()

    def test_load_config_negative_lsp_timeout_raises_error(self, set_env_vars):
        """Test load_config() raises ValueError for negative LSP timeout."""
        set_env_vars(PYRIGHT_MCP_LSP_TIMEOUT="-10.0")
        with pytest.raises(ValueError, match="must be positive"):
            load_config()

    def test_load_config_invalid_log_level_raises_error(self, set_env_vars):
        """Test load_config() raises ValueError for invalid log level."""
        set_env_vars(PYRIGHT_MCP_LOG_LEVEL="INVALID")
        with pytest.raises(ValueError, match="must be one of"):
            load_config()

    def test_load_config_invalid_log_mode_raises_error(self, set_env_vars):
        """Test load_config() raises ValueError for invalid log mode."""
        set_env_vars(PYRIGHT_MCP_LOG_MODE="invalid")
        with pytest.raises(ValueError, match="must be one of"):
            load_config()

    def test_load_config_log_level_case_insensitive(self, set_env_vars):
        """Test load_config() handles log level case-insensitively."""
        set_env_vars(PYRIGHT_MCP_LOG_LEVEL="debug")
        config = load_config()
        assert config.log_level == "DEBUG"


class TestGetConfig:
    """Tests for get_config() singleton function."""

    def test_get_config_returns_config_instance(self):
        """Test get_config() returns Config instance."""
        config = get_config()
        assert isinstance(config, Config)

    def test_get_config_is_singleton(self):
        """Test get_config() returns same instance on multiple calls."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_get_config_after_reset(self):
        """Test get_config() creates new instance after reset."""
        config1 = get_config()
        reset_config()
        config2 = get_config()
        # Should be different instances
        assert config1 is not config2


class TestResetConfig:
    """Tests for reset_config() function."""

    def test_reset_config_clears_singleton(self):
        """Test reset_config() clears the singleton instance."""
        # Get initial config
        config1 = get_config()
        assert config1 is not None

        # Reset
        reset_config()

        # Get new config
        config2 = get_config()

        # Should be different instance
        assert config1 is not config2

    def test_reset_config_for_test_isolation(self, set_env_vars):
        """Test reset_config() provides test isolation."""
        # First test: set env var and get config
        set_env_vars(PYRIGHT_MCP_CLI_TIMEOUT="60.0")
        config1 = get_config()
        assert config1.cli_timeout == 60.0

        # Simulate test cleanup
        reset_config()
        del os.environ["PYRIGHT_MCP_CLI_TIMEOUT"]

        # Second test: should get default value
        config2 = get_config()
        assert config2.cli_timeout == 30.0

    def test_reset_config_idempotent(self):
        """Test reset_config() can be called multiple times safely."""
        get_config()
        reset_config()
        reset_config()  # Should not raise
        reset_config()
        config = get_config()
        assert isinstance(config, Config)


class TestConfigDataclass:
    """Tests for Config dataclass."""

    def test_config_creation(self):
        """Test Config can be created with all fields."""
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
        assert config.cli_timeout == 30.0
        assert config.log_level == "INFO"

    def test_config_with_allowed_paths(self, tmp_path: Path):
        """Test Config with allowed_paths set."""
        path1 = tmp_path / "path1"
        path1.mkdir()

        config = Config(
            allowed_paths=[path1],
            cli_timeout=30.0,
            lsp_timeout=300.0,
            lsp_command=["pyright-langserver", "--stdio"],
            log_level="INFO",
            log_mode="stderr",
            log_file=None,
            enable_health_check=True,
        )
        assert config.allowed_paths == [path1]

    def test_config_with_log_file(self, tmp_path: Path):
        """Test Config with log_file set."""
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
        assert config.log_file == log_file
        assert config.log_mode == "file"
