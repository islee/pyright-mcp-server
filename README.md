# pyright-mcp

An MCP (Model Context Protocol) server that exposes Pyright's Python static type checking capabilities to LLM clients like Claude.

> **Status:** Phase 3 Complete - Production-ready with multi-workspace support, completions, and references. See [STATUS.md](STATUS.md) for details.

## Features

| Tool | Description | Phase | Status |
|------|-------------|-------|--------|
| `check_types` | Run type checking on file/directory | 1 (MVP) | ✓ Implemented |
| `health_check` | Check server health and Pyright availability | 1 (MVP) | ✓ Implemented |
| `get_hover` | Get type info and docstring at position | 2 (LSP) | ✓ Implemented |
| `go_to_definition` | Find definition location for symbol | 2 (LSP) | ✓ Implemented |
| `get_completions` | Get completion suggestions at position | 3 (Production) | ✓ Implemented |
| `find_references` | Find all references to a symbol | 3 (Production) | ✓ Implemented |

## Installation

### From Source (Recommended for Development)

```bash
git clone https://github.com/islee/pyright-mcp-server.git
cd pyright-mcp-server
uv sync
uv run python -m pyright_mcp
```

### From PyPI (When Published)
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

# Get completions (Phase 3)
get_completions("/path/to/file.py", line=10, column=5, trigger_character=".")

# Find references (Phase 3)
find_references("/path/to/file.py", line=10, column=5)

# Check health with pool stats and metrics (Phase 3)
health_check()
```

## Phase 3 Features (Production)

### Multi-Workspace Support

pyright-mcp now supports efficient multi-workspace development:

- **LSP Pool Management**: Maintains up to 3 concurrent LSP clients (configurable via `PYRIGHT_MCP_LSP_POOL_SIZE`)
- **LRU Eviction**: Automatically manages memory by evicting least-recently-used workspaces
- **Per-Workspace Metrics**: Tracks operation counts, latencies, and error rates for each workspace

### New Tools

- **`get_completions`** - Get code completion suggestions at a position with context awareness
- **`find_references`** - Find all references to a symbol across the workspace

### Enhanced Health Check

The `health_check` tool now returns detailed pool statistics and per-workspace metrics:

```json
{
  "status": "healthy",
  "lsp_pool": {
    "active_instances": 2,
    "max_instances": 3,
    "cache_hit_rate": 0.667,
    "eviction_count": 1,
    "workspace_switches": 3,
    "workspaces": ["/path/to/workspace1", "/path/to/workspace2"]
  },
  "metrics": {
    "uptime_seconds": 123.45,
    "workspaces": [
      {
        "workspace": "/path/to/workspace1",
        "operations": {
          "hover": {"count": 5, "avg_ms": 25.3, "errors": 0},
          "definition": {"count": 3, "avg_ms": 35.2, "errors": 0},
          "completion": {"count": 2, "avg_ms": 40.1, "errors": 0},
          "references": {"count": 1, "avg_ms": 50.0, "errors": 0}
        }
      }
    ]
  }
}
```

Use metrics to identify slow workspaces and optimize your Pyright configuration.

### Configuration

Control multi-workspace behavior:

```bash
# Increase pool size for more concurrent workspaces
export PYRIGHT_MCP_LSP_POOL_SIZE=5

# Increase idle timeout (useful for slower machines)
export PYRIGHT_MCP_LSP_TIMEOUT=600
```

See [docs/METRICS.md](docs/METRICS.md) for detailed metrics documentation.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Pyright 1.1.350+ (tested with 1.1.350-1.1.408). Run `health_check` to verify compatibility.
- Node.js (for Pyright, installed automatically via pyright package)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYRIGHT_MCP_ALLOWED_PATHS` | (none) | Colon-separated allowed paths. If not set, all paths allowed. |
| `PYRIGHT_MCP_CLI_TIMEOUT` | `30` | CLI execution timeout (seconds) |
| `PYRIGHT_MCP_LOG_MODE` | `stderr` | Logging: `stderr`, `file`, or `both` |
| `PYRIGHT_MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PYRIGHT_MCP_ENABLE_HEALTH_CHECK` | `true` | Enable health_check tool |
| `PYRIGHT_MCP_LSP_TIMEOUT` | `300` | LSP idle timeout (seconds) |
| `PYRIGHT_MCP_LSP_COMMAND` | `pyright-langserver --stdio` | LSP server command |
| `PYRIGHT_MCP_LSP_POOL_SIZE` | `3` | Maximum LSP clients in pool (Phase 3) |

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
