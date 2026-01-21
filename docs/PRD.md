# Product Requirements Document: pyright-mcp

## Executive Summary

pyright-mcp is an MCP server designed as a **Claude Code companion tool** for Python codebases. It gives Claude Code real-time type intelligence so it can write better Python code, understand existing APIs, and catch type errors before suggesting changes.

## Problem Statement

When Claude Code works on Python codebases, it lacks real-time static analysis:
- Cannot verify type correctness before proposing changes
- May misunderstand types of variables, function signatures, or return values
- Cannot navigate to symbol definitions to understand implementations
- Relies on inference rather than actual type information

This leads to suggestions that may introduce type errors or make incorrect assumptions about APIs.

## Solution

An MCP server purpose-built for Claude Code that provides Python type intelligence:
- **Type checking** - Verify code has no type errors before suggesting changes
- **Hover information** - Understand types and signatures of symbols being worked with
- **Go-to-definition** - Find implementations to understand behavior
- **Project-aware** - Respects pyrightconfig.json, pyproject.toml, and virtual environments

## Goals

1. **Claude Code Integration**: Seamless setup with Claude Code, optimized for LLM consumption
2. **Accuracy**: Expose Pyright's full diagnostic output without loss of information
3. **Project-Aware**: Auto-detect Python project configuration and virtual environments
4. **Performance**: Fast response times for interactive use (< 2s for typical files)

## Non-Goals

- Generic LSP-to-MCP bridge (use [lsp-mcp](https://github.com/Tritlo/lsp-mcp) for that)
- IDE replacement (this complements Claude Code, not IDEs)
- Multi-language support (Python only via Pyright)
- Real-time file watching (on-demand analysis)

## User Stories

### US1: Verify Changes Before Suggesting
As Claude Code working on a Python codebase, I want to type-check my proposed changes so I don't suggest code with type errors.

**Acceptance Criteria:**
- Can invoke `check_types` on a file or directory path
- Returns all diagnostics with file, line, column, severity, message
- Output is LLM-friendly (clear, structured, actionable)

### US2: Understand Existing Code
As Claude Code, I want to see the type signature and documentation of symbols so I understand how to use existing APIs correctly.

**Acceptance Criteria:**
- Can invoke `get_hover` with file path and position (line, column)
- Returns type signature and docstring if available
- Returns clear "no information" message when not available

### US3: Navigate to Implementation
As Claude Code, I want to find where a symbol is defined so I can understand its implementation before modifying or using it.

**Acceptance Criteria:**
- Can invoke `go_to_definition` with file path and position
- Returns definition location (file, line, column)
- Works for symbols in dependencies and stdlib

### US4: Get Completions (Phase 2)
As Claude Code, I want type-aware completion suggestions to discover available methods and attributes.

**Acceptance Criteria:**
- Can invoke `get_completions` with file path and position
- Returns list of completion items with labels and types
- Lower priority - Claude Code has existing completion context

## Technical Architecture

### Component Overview

```
┌─────────────────┐     MCP Protocol      ┌─────────────────┐
│   MCP Client    │◄────────────────────►│  pyright-mcp    │
│ (Claude, etc.)  │       (stdio)         │    server       │
└─────────────────┘                       └────────┬────────┘
                                                   │
                                                   │ subprocess
                                                   │ --outputjson
                                                   ▼
                                          ┌─────────────────┐
                                          │     Pyright     │
                                          │      CLI        │
                                          └─────────────────┘
```

### Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.10+ | Target audience is Python developers |
| MCP SDK | FastMCP (`mcp[cli]`) | Official Python SDK, decorator-based |
| Package Manager | uv | Fast, modern Python packaging |
| Type Checker | Pyright CLI | JSON output, well-maintained |
| Transport | stdio | Standard for local MCP servers |

### API Design

#### Tool: `check_types`

Runs Pyright type checking on specified files/directories.

**Input:**
```json
{
  "path": "/path/to/file_or_directory",
  "python_version": "3.11",       // optional
  "python_platform": "Darwin"     // optional
}
```

**Output:**
```json
{
  "diagnostics": [
    {
      "file": "/path/to/file.py",
      "line": 10,
      "column": 5,
      "severity": "error",
      "message": "Argument of type \"str\" cannot be assigned to parameter \"x\" of type \"int\"",
      "rule": "reportArgumentType"
    }
  ],
  "summary": {
    "files_analyzed": 5,
    "error_count": 1,
    "warning_count": 0,
    "time_sec": 0.45
  }
}
```

#### Tool: `get_hover`

Returns type information and documentation for symbol at position.

**Input:**
```json
{
  "file": "/path/to/file.py",
  "line": 15,
  "column": 8
}
```

**Output:**
```json
{
  "type": "(x: int, y: int) -> int",
  "documentation": "Add two integers and return the result.",
  "symbol": "add"
}
```

#### Tool: `go_to_definition`

Finds the definition location of a symbol.

**Input:**
```json
{
  "file": "/path/to/file.py",
  "line": 20,
  "column": 12
}
```

**Output:**
```json
{
  "definition": {
    "file": "/path/to/module.py",
    "line": 5,
    "column": 4
  }
}
```

#### Tool: `get_completions`

Returns completion suggestions at cursor position.

**Input:**
```json
{
  "file": "/path/to/file.py",
  "line": 25,
  "column": 10
}
```

**Output:**
```json
{
  "completions": [
    {"label": "append", "kind": "method", "type": "(object) -> None"},
    {"label": "extend", "kind": "method", "type": "(Iterable) -> None"},
    {"label": "pop", "kind": "method", "type": "(int) -> T"}
  ]
}
```

## Implementation Phases

### Phase 1: MVP - Type Checking (CLI-based)
**Goal:** Working MCP server that Claude Code can use to verify Python code has no type errors.

**Scope:**
- Project scaffolding with uv + FastMCP
- `check_types` tool using `pyright --outputjson`
- Project detection (find pyrightconfig.json, pyproject.toml)
- Virtual environment detection
- LLM-friendly error formatting
- Claude Code configuration docs

**Deliverables:**
- Working `check_types` tool
- README with Claude Code setup instructions
- Basic test coverage

### Phase 2: Hover & Definition (LSP-based)
**Goal:** Claude Code can understand types and navigate to definitions.

**Scope:**
- LSP subprocess management (pyright-langserver)
- Lazy initialization (start on first use)
- Idle timeout (kill after 5 min inactive)
- `get_hover` tool implementation
- `go_to_definition` tool implementation
- Workspace initialization with detected project root

**Technical Approach:**
- Use `pygls` or direct JSON-RPC for LSP communication
- Persistent subprocess for performance
- Graceful restart on LSP crash

### Phase 3: Completions & Polish
**Goal:** Full feature set with production quality.

**Scope:**
- `get_completions` tool (if needed)
- Performance optimization
- Caching layer (optional)
- Comprehensive error handling
- Full test coverage
- Documentation

## Technical Considerations

### Approach: CLI First, LSP Later

**Phase 1 (CLI):** Use `pyright --outputjson` for type checking
- Simple, stateless, reliable
- Sufficient for `check_types` tool

**Phase 2+ (LSP):** Add `pyright-langserver` subprocess for hover/definition
- Required for `get_hover` and `go_to_definition`
- Persistent subprocess with lazy init and idle timeout

### Project Detection Strategy

Detection order (first found wins):
1. `pyrightconfig.json` in target directory or parents
2. `pyproject.toml` with `[tool.pyright]` section
3. `pyproject.toml` (use directory as root)
4. Fall back to target file's directory

### Workspace Scope

**Phase 1-2: Single-project assumption**
- LSP initialized with detected project root from first file
- Optimized for Claude Code working in one repository at a time
- If file from different project requested, reinitialize LSP (with warning)

**Future: Multi-project support**
- Multiple LSP instances (one per project root)
- Or LSP workspace folders (multi-root workspaces)
- Add when real usage patterns demand it

### Transport & Hosting

**Phase 1-2: stdio (default)**
- Client spawns server as subprocess
- Communication via stdin/stdout
- Zero configuration, automatic lifecycle management
- Standard for local MCP servers with Claude Code

**Future: Additional options**

| Option | Transport | Use Case |
|--------|-----------|----------|
| SSE | HTTP | Persistent server, multi-client, remote access |
| Streamable HTTP | HTTP | Newer MCP spec, similar to SSE |
| Daemon | SSE | Background service with system integration |

**Daemon support (future):**
- macOS: launchd plist (`~/Library/LaunchAgents/`)
- Linux: systemd user service (`~/.config/systemd/user/`)
- Persistent LSP state, survives terminal close
- Pairs with SSE transport for client connection
- Add when users need always-on server without manual startup

### Virtual Environment Detection

Detection order:
1. `VIRTUAL_ENV` environment variable
2. `.venv/` directory in project root
3. `venv/` directory in project root
4. Poetry/PDM managed environments via config files

### LSP Server Options

| Option | Command | Notes |
|--------|---------|-------|
| Pyright (default) | `pyright-langserver --stdio` | Standard, widely used |
| basedpyright | `basedpyright-langserver --stdio` | More features, Pylance parity |

Make LSP binary configurable to support both.

### Error Handling

| Scenario | Handling |
|----------|----------|
| File not found | Return error with clear message |
| Syntax errors in Python | Return Pyright's syntax diagnostics |
| Missing dependencies | Return diagnostics about import errors |
| Pyright not installed | Clear error message with install instructions |
| Timeout | Kill subprocess after 30s, return timeout error |
| LSP crash | Log error, restart on next request |

## Success Metrics

1. **Functionality**: `check_types`, `get_hover`, `go_to_definition` working correctly
2. **Performance**: < 2s response time for single file type check
3. **Reliability**: Graceful handling of all error scenarios
4. **Integration**: Seamless Claude Code setup and usage

## Prior Art

| Project | Approach | Differentiation |
|---------|----------|-----------------|
| [lsp-mcp](https://github.com/Tritlo/lsp-mcp) | Generic LSP-to-MCP bridge (Node.js) | pyright-mcp is Python-native, Pyright-optimized |
| [mcp-language-server](https://github.com/isaacphi/mcp-language-server) | Generic LSP bridge (Go) | pyright-mcp focuses on Claude Code UX |

## References

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Pyright Documentation](https://microsoft.github.io/pyright/)
- [Pyright CLI Options](https://github.com/microsoft/pyright/blob/main/docs/command-line.md)
- [basedpyright](https://github.com/DetachHead/basedpyright)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)
