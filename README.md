# pyright-mcp

An MCP (Model Context Protocol) server that exposes Pyright's Python static type checking capabilities to LLM clients like Claude.

## Features

| Tool | Description | Phase |
|------|-------------|-------|
| `check_types` | Run type checking on file/directory | 1 |
| `get_hover` | Get type info and docstring at position | 2 |
| `go_to_definition` | Find definition location for symbol | 2 |
| `get_completions` | Get completion suggestions at position | 3 |

## Installation

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

# Lint
uv run ruff check .
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

## License

GPL-3.0 - See [LICENSE](LICENSE) for details.
