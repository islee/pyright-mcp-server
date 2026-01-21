# pyright-mcp

An MCP (Model Context Protocol) server that exposes Pyright's Python static type checking capabilities to LLM clients like Claude.

> **Status:** Planning phase - implementation not yet started. See [STATUS.md](STATUS.md) for current progress.

## Features

| Tool | Description | Phase |
|------|-------------|-------|
| `check_types` | Run type checking on file/directory | 1 (MVP) |
| `health_check` | Check server health and Pyright availability | 1 (MVP) |
| `get_hover` | Get type info and docstring at position | 2 (LSP) |
| `go_to_definition` | Find definition location for symbol | 2 (LSP) |
| `get_completions` | Get completion suggestions at position | 3 (Polish) |

## Installation

> **Note:** Package not yet published. For now, install from source.

```bash
# Clone and install from source
git clone https://github.com/islee/pyright-mcp-server.git
cd pyright-mcp-server
uv sync
```

Once published:
```bash
# Via uv (recommended)
uv add pyright-mcp

# Via pip
pip install pyright-mcp
```

## Configuration

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pyright": {
      "command": "uvx",
      "args": ["pyright-mcp"]
    }
  }
}
```

For development:

```json
{
  "mcpServers": {
    "pyright": {
      "command": "uv",
      "args": ["--directory", "/path/to/pyright-mcp", "run", "python", "-m", "pyright_mcp"]
    }
  }
}
```

## Usage

Once configured, the MCP tools are available in Claude:

```
# Check types in a file
check_types("/path/to/file.py")

# Check entire project
check_types("/path/to/project/")

# Get type info at position (Phase 2)
get_hover("/path/to/file.py", line=10, column=5)

# Go to definition (Phase 2)
go_to_definition("/path/to/file.py", line=10, column=5)
```

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Node.js (for Pyright, installed automatically via pyright package)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYRIGHT_MCP_ALLOWED_PATHS` | (none) | Colon-separated allowed paths. If not set, all paths allowed. |
| `PYRIGHT_MCP_CLI_TIMEOUT` | `30` | CLI execution timeout (seconds) |
| `PYRIGHT_MCP_LOG_MODE` | `stderr` | Logging: `stderr`, `file`, or `both` |
| `PYRIGHT_MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PYRIGHT_MCP_ENABLE_HEALTH_CHECK` | `true` | Enable health_check tool |

## Development

```bash
# Install dependencies
uv sync

# Run the MCP server
uv run python -m pyright_mcp

# Run tests
uv run pytest

# Type check
uv run pyright

# Lint and format
uv run ruff check .
uv run ruff format .
```

## Architecture

```
┌───────────────────────────────────────────────────────┐
│                      Claude Code                      │
└───────────────────────────┬───────────────────────────┘
                            │ MCP Protocol (stdio)
                            ▼
┌───────────────────────────────────────────────────────┐
│                      pyright-mcp                      │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ MCP Server  │  │   Tools     │  │ Backend       │  │
│  │ (FastMCP)   │◄─┤ check_types │◄─┤ Pyright CLI   │  │
│  │             │  │ get_hover   │  │ LSP Client    │  │
│  └─────────────┘  └─────────────┘  └───────────────┘  │
└───────────────────────────────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       ┌──────────┐  ┌──────────┐  ┌──────────────┐
       │ Pyright  │  │ Pyright  │  │ Python Files │
       │ CLI      │  │ LSP      │  │ (workspace)  │
       └──────────┘  └──────────┘  └──────────────┘
```

## Documentation

- [Product Requirements (PRD)](docs/PRD.md)
- [Technical Design (TDD)](docs/TDD.md)
- [Implementation Plan](docs/IMPLEMENTATION.md)

## License

GPL-3.0 - See [LICENSE](LICENSE) for details.
