# Technical Design Document: pyright-mcp

## 1. Overview

### 1.1 Purpose
This document describes the technical design for pyright-mcp, an MCP server that provides Pyright type checking capabilities to Claude Code.

### 1.2 Scope
- Phase 1: `check_types` tool via Pyright CLI
- Phase 2: `get_hover`, `go_to_definition` via Pyright LSP
- Phase 3: `get_completions`, polish, optional transports

### 1.3 References
- [PRD](./PRD.md) - Product requirements and user stories
- [IMPLEMENTATION](./IMPLEMENTATION.md) - Implementation steps and code scaffolding
- [MCP Specification](https://modelcontextprotocol.io/docs)
- [Pyright CLI](https://github.com/microsoft/pyright/blob/main/docs/command-line.md)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Claude Code                              │
└─────────────────────────────┬───────────────────────────────────┘
                              │ MCP Protocol (stdio)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        pyright-mcp                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ MCP Server  │  │   Tools     │  │   Backend Adapters      │  │
│  │ (FastMCP)   │◄─┤             │◄─┤                         │  │
│  │             │  │ check_types │  │ ┌─────────────────────┐ │  │
│  │ - stdio     │  │ get_hover   │  │ │  Pyright CLI Runner │ │  │
│  │ - tool reg  │  │ go_to_def   │  │ │  (Phase 1)          │ │  │
│  │ - dispatch  │  │ completions │  │ └─────────────────────┘ │  │
│  └─────────────┘  └─────────────┘  │ ┌─────────────────────┐ │  │
│                                     │ │  LSP Client         │ │  │
│  ┌─────────────────────────────┐   │ │  (Phase 2)          │ │  │
│  │     Project Detection       │   │ └─────────────────────┘ │  │
│  │ - find project root         │   └─────────────────────────┘  │
│  │ - detect venv               │                                 │
│  │ - load config               │                                 │
│  └─────────────────────────────┘                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
     ┌────────────┐   ┌────────────┐   ┌────────────────┐
     │  Pyright   │   │  Pyright   │   │  Python Files  │
     │  CLI       │   │  LSP       │   │  (workspace)   │
     └────────────┘   └────────────┘   └────────────────┘
```

### 2.2 Component Overview

| Component | Responsibility | Phase |
|-----------|---------------|-------|
| MCP Server | Protocol handling, tool registration | 1 |
| Tools | MCP tool implementations | 1-3 |
| Pyright CLI Runner | Invoke `pyright --outputjson` | 1 |
| LSP Client | Manage pyright-langserver subprocess | 2 |
| Project Detection | Find root, venv, config | 1 |

---

## 3. Position Indexing Convention

**All positions in pyright-mcp use 0-indexed line and column numbers.**

| Component | Line | Column | Notes |
|-----------|------|--------|-------|
| MCP Tool API | 0-indexed | 0-indexed | External interface |
| Internal data structures | 0-indexed | 0-indexed | Diagnostic, Location, Range |
| Pyright CLI JSON | 0-indexed | 0-indexed | Native format |
| Pyright LSP | 0-indexed | 0-indexed | LSP specification |

**Rationale:** Pyright CLI and LSP both use 0-indexed positions natively. Using 0-indexed throughout eliminates conversion errors and aligns with LSP specification.

**User-facing display:** When formatting diagnostics for human readability (e.g., in summary messages), convert to 1-indexed: `f"{line + 1}:{column + 1}"`.

---

## 4. Utility Functions

### 4.1 Position Utilities

**File:** `src/pyright_mcp/utils/position.py`

```python
@dataclass
class Position:
    """A 0-indexed position in a file."""
    line: int    # 0-indexed
    column: int  # 0-indexed

    def to_display(self) -> str:
        """Convert to 1-indexed human-readable format."""
        return f"{self.line + 1}:{self.column + 1}"

    @classmethod
    def from_lsp(cls, lsp_position: dict) -> "Position":
        """Create from LSP position dict."""
        return cls(line=lsp_position["line"], column=lsp_position["character"])

    def to_lsp(self) -> dict:
        """Convert to LSP position dict."""
        return {"line": self.line, "character": self.column}


@dataclass
class Range:
    """A 0-indexed range in a file."""
    start: Position
    end: Position

    def to_display(self) -> str:
        """Convert to human-readable format."""
        return f"{self.start.to_display()}-{self.end.to_display()}"

    @classmethod
    def from_lsp(cls, lsp_range: dict) -> "Range":
        """Create from LSP range dict."""
        return cls(
            start=Position.from_lsp(lsp_range["start"]),
            end=Position.from_lsp(lsp_range["end"]),
        )

    def to_lsp(self) -> dict:
        """Convert to LSP range dict."""
        return {"start": self.start.to_lsp(), "end": self.end.to_lsp()}
```

### 4.2 Path/URI Utilities

**File:** `src/pyright_mcp/utils/uri.py`

```python
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
import sys

def path_to_uri(path: Path) -> str:
    """
    Convert filesystem path to file:// URI.

    Handles platform differences (Windows drive letters, etc.)
    """
    path = path.resolve()
    if sys.platform == "win32":
        # Windows: file:///C:/path/to/file
        return f"file:///{quote(str(path), safe='/:')}"
    else:
        # Unix: file:///path/to/file
        return f"file://{quote(str(path))}"


def uri_to_path(uri: str) -> Path:
    """
    Convert file:// URI to filesystem path.

    Raises ValueError if URI is not a file:// URI.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Expected file:// URI, got: {uri}")

    path_str = unquote(parsed.path)

    # Handle Windows drive letters (e.g., /C:/path)
    if sys.platform == "win32" and path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
        path_str = path_str[1:]

    return Path(path_str)


def normalize_path(path: str | Path) -> Path:
    """
    Normalize a path for consistent handling.

    - Resolves to absolute path
    - Resolves symlinks
    - Normalizes separators
    """
    return Path(path).resolve()
```

### 4.3 Pyright Command Builder

**File:** `src/pyright_mcp/backends/cli_runner.py` (addition)

```python
def build_pyright_command(
    path: Path,
    context: ProjectContext,
    python_version: str | None = None,
    output_json: bool = True,
) -> list[str]:
    """
    Build Pyright CLI command with all relevant flags.

    Precedence for options:
    1. Explicit function arguments (highest)
    2. pyrightconfig.json settings
    3. Auto-detected values from ProjectContext (lowest)

    Args:
        path: File or directory to analyze
        context: Detected project context
        python_version: Override Python version (e.g., "3.10")
        output_json: Include --outputjson flag

    Returns:
        Command as list of strings for subprocess
    """
    cmd = ["pyright"]

    if output_json:
        cmd.append("--outputjson")

    # Python version: explicit arg > context detection
    version = python_version or context.python_version
    if version:
        cmd.extend(["--pythonversion", version])

    # Virtual environment path
    if context.venv:
        cmd.extend(["--venvpath", str(context.venv.parent)])

    # Project root for config resolution
    if context.root:
        cmd.extend(["--project", str(context.root)])

    # Target path (must be last)
    cmd.append(str(path))

    return cmd
```

---

## 5. Component Design

### 5.1 MCP Server Layer

**Technology:** FastMCP (from `mcp` package)

**Responsibilities:**
- Handle MCP protocol over stdio
- Register and dispatch tool calls
- Serialize responses

**Interface:**
```python
# server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pyright-mcp")

@mcp.tool()
async def check_types(path: str, python_version: str | None = None) -> dict:
    ...
```

### 5.2 Project Detection Module

**File:** `src/pyright_mcp/project_detection.py`

**Data Structures:**
```python
@dataclass
class ProjectContext:
    """Detected project configuration."""
    root: Path                    # Project root directory
    venv: Path | None             # Virtual environment path
    pyright_config: Path | None   # pyrightconfig.json path
    pyproject: Path | None        # pyproject.toml path
    python_version: str | None    # Detected Python version
```

**Functions:**
```python
def detect_project(target_path: Path) -> ProjectContext:
    """
    Detect project context from a target file or directory.

    Detection order:
    1. Walk up from target_path looking for config files
    2. Find venv in project root
    3. Extract Python version from config if present
    """

def find_project_root(start_path: Path) -> Path:
    """Find project root by locating config files."""

def find_venv(project_root: Path) -> Path | None:
    """Find virtual environment for project."""

def get_python_version(project_context: ProjectContext) -> str | None:
    """Extract Python version from project config."""
```

### 5.3 Pyright CLI Runner (Phase 1)

**File:** `src/pyright_mcp/backends/cli_runner.py`

**Data Structures:**
```python
@dataclass
class Diagnostic:
    """Single diagnostic from Pyright."""
    file: str
    line: int           # 0-indexed
    column: int         # 0-indexed
    end_line: int
    end_column: int
    severity: Literal["error", "warning", "information"]
    message: str
    rule: str | None    # e.g., "reportArgumentType"

@dataclass
class DiagnosticsResult:
    """Result from check_types operation."""
    diagnostics: list[Diagnostic]
    files_analyzed: int
    error_count: int
    warning_count: int
    information_count: int
    time_sec: float

@dataclass
class CLIError:
    """Error from CLI execution."""
    code: Literal["not_found", "timeout", "parse_error", "execution_error"]
    message: str
```

**Functions:**
```python
async def run_check(
    path: Path,
    project: ProjectContext,
    timeout: float = 30.0,
) -> DiagnosticsResult | CLIError:
    """
    Run Pyright CLI and return structured diagnostics.

    Invokes: pyright --outputjson [options] <path>
    """
```

**Pyright CLI Output Format:**
```json
{
  "version": "1.1.x",
  "time": "0.45sec",
  "generalDiagnostics": [
    {
      "file": "/path/to/file.py",
      "severity": 1,  // 1=error, 2=warning, 3=information
      "message": "...",
      "range": {
        "start": {"line": 10, "character": 5},
        "end": {"line": 10, "character": 15}
      },
      "rule": "reportArgumentType"
    }
  ],
  "summary": {
    "filesAnalyzed": 5,
    "errorCount": 1,
    "warningCount": 0,
    "informationCount": 0,
    "timeInSec": 0.45
  }
}
```

### 5.4 LSP Client (Phase 2)

**File:** `src/pyright_mcp/backends/lsp_client.py`

**State Management:**
```python
@dataclass
class LSPState:
    """LSP subprocess state."""
    process: asyncio.subprocess.Process | None
    initialized: bool
    workspace_root: Path | None
    last_activity: float  # timestamp

class LSPClient:
    """Manages pyright-langserver subprocess."""

    def __init__(
        self,
        server_command: list[str] = ["pyright-langserver", "--stdio"],
        idle_timeout: float = 300.0,  # 5 minutes
    ):
        self._state: LSPState | None = None
        self._server_command = server_command
        self._idle_timeout = idle_timeout
        self._request_id = 0
        self._lock = asyncio.Lock()

    async def ensure_initialized(self, workspace_root: Path) -> None:
        """Start LSP if not running, reinitialize if workspace changed."""

    async def hover(self, file: Path, line: int, column: int) -> HoverResult | None:
        """Send textDocument/hover request."""

    async def definition(self, file: Path, line: int, column: int) -> list[Location]:
        """Send textDocument/definition request."""

    async def shutdown(self) -> None:
        """Gracefully shutdown LSP subprocess."""

    async def _send_request(self, method: str, params: dict) -> dict:
        """Send JSON-RPC request and await response."""

    async def _check_idle_timeout(self) -> None:
        """Kill subprocess if idle too long."""
```

**LSP Initialization Sequence:**
```
Client → Server: initialize {
    "processId": <pid>,
    "rootUri": "file:///path/to/project",
    "capabilities": { ... }
}
Server → Client: InitializeResult { "capabilities": { ... } }
Client → Server: initialized {}
// Ready for requests
```

**Data Structures:**
```python
@dataclass
class HoverResult:
    """Result from get_hover operation."""
    type_info: str | None       # Type signature
    documentation: str | None   # Docstring
    range: Range | None         # Source range of symbol

@dataclass
class Location:
    """A location in a file."""
    file: str
    line: int
    column: int

@dataclass
class Range:
    """A range in a file."""
    start_line: int
    start_column: int
    end_line: int
    end_column: int
```

### 5.5 Tools Layer

**File:** `src/pyright_mcp/tools/`

Each tool:
1. Validates input
2. Detects project context
3. Delegates to appropriate backend
4. Formats response for LLM consumption

**Tool Interfaces:**
```python
# tools/check_types.py
async def check_types(
    path: str,
    python_version: str | None = None,
) -> dict:
    """
    Returns:
        {
            "summary": "Analyzed 5 files in 0.45s. Found 1 error(s).",
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [
                {
                    "file": "/path/to/file.py",
                    "location": "10:5",
                    "severity": "error",
                    "message": "...",
                    "rule": "reportArgumentType"
                }
            ]
        }
    """

# tools/hover.py (Phase 2)
async def get_hover(
    file: str,
    line: int,
    column: int,
) -> dict:
    """
    Returns:
        {
            "symbol": "add",
            "type": "(x: int, y: int) -> int",
            "documentation": "Add two integers.",
        }
        OR
        {
            "error": "No information available at this position"
        }
    """

# tools/definition.py (Phase 2)
async def go_to_definition(
    file: str,
    line: int,
    column: int,
) -> dict:
    """
    Returns:
        {
            "definition": {
                "file": "/path/to/module.py",
                "line": 5,
                "column": 4
            }
        }
        OR
        {
            "definitions": [ ... ]  // Multiple definitions
        }
        OR
        {
            "error": "No definition found"
        }
    """
```

---

## 6. Data Flow

### 6.1 check_types Flow (Phase 1)

```
Claude Code                pyright-mcp                    Pyright CLI
    │                           │                              │
    │  check_types(path)        │                              │
    │─────────────────────────►│                              │
    │                           │  detect_project(path)        │
    │                           │─────────────┐                │
    │                           │◄────────────┘                │
    │                           │  ProjectContext              │
    │                           │                              │
    │                           │  pyright --outputjson path   │
    │                           │─────────────────────────────►│
    │                           │                              │
    │                           │◄─────────────────────────────│
    │                           │  JSON output                 │
    │                           │                              │
    │                           │  parse + format              │
    │                           │─────────────┐                │
    │                           │◄────────────┘                │
    │                           │                              │
    │◄─────────────────────────│                              │
    │  { summary, diagnostics } │                              │
```

### 6.2 get_hover Flow (Phase 2)

```
Claude Code                pyright-mcp                    LSP Server
    │                           │                              │
    │  get_hover(file,line,col) │                              │
    │─────────────────────────►│                              │
    │                           │                              │
    │                           │  ensure_initialized()        │
    │                           │─────────────┐                │
    │                           │             │ (if not running)
    │                           │             │  spawn + initialize
    │                           │             │─────────────────►│
    │                           │             │◄─────────────────│
    │                           │◄────────────┘                │
    │                           │                              │
    │                           │  textDocument/didOpen        │
    │                           │─────────────────────────────►│
    │                           │                              │
    │                           │  textDocument/hover          │
    │                           │─────────────────────────────►│
    │                           │◄─────────────────────────────│
    │                           │  HoverResult                 │
    │                           │                              │
    │                           │  format response             │
    │◄─────────────────────────│                              │
    │  { type, documentation }  │                              │
```

---

## 7. Error Handling

### 7.1 Error Categories

| Category | Examples | Handling |
|----------|----------|----------|
| Input validation | Invalid path, bad line/column | Return error dict with clear message |
| File system | File not found, permission denied | Return error with path context |
| Pyright CLI | Not installed, timeout, parse failure | Return error with install/debug instructions |
| LSP | Subprocess crash, init failure, timeout | Log, attempt restart, return error |
| Project detection | No config found | Fall back to defaults, proceed |

### 7.2 Error Response Format

All tools return errors in a consistent format:
```python
{
    "error": "Human-readable error message",
    "error_code": "file_not_found",  # machine-readable code
    "details": { ... }  # optional additional context
}
```

### 7.3 LSP Recovery Strategy

```python
async def _handle_lsp_error(self, error: Exception) -> None:
    """Handle LSP errors with recovery."""
    if isinstance(error, (BrokenPipeError, ConnectionResetError)):
        # Subprocess crashed - restart on next request
        await self._cleanup()
        self._state = None
    elif isinstance(error, asyncio.TimeoutError):
        # Request timeout - log and continue
        logger.warning("LSP request timed out")
    else:
        # Unknown error - log and attempt restart
        logger.error(f"LSP error: {error}")
        await self._cleanup()
        self._state = None
```

---

## 8. Configuration

### 8.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYRIGHT_MCP_LOG_MODE` | `stderr` | Logging mode: `stderr`, `file`, or `both` |
| `PYRIGHT_MCP_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PYRIGHT_MCP_LSP_COMMAND` | `pyright-langserver` | LSP server binary |
| `PYRIGHT_MCP_LSP_TIMEOUT` | `300` | LSP idle timeout (seconds) |
| `PYRIGHT_MCP_CLI_TIMEOUT` | `30` | CLI execution timeout (seconds) |

### 8.2 Logging Strategy

**Dual-mode logging** with configurable output via `PYRIGHT_MCP_LOG_MODE`:

| Mode | Output | Format | Use Case |
|------|--------|--------|----------|
| `stderr` (default) | stderr | JSON Lines | Production, log aggregation |
| `file` | `~/.pyright-mcp/logs/` | Human-readable | Local development |
| `both` | stderr + file | JSON + Human | Debugging production issues |

**File:** `src/pyright_mcp/logging_config.py`

```python
import logging
import json
import os
import sys
from datetime import datetime, timezone
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextvars import ContextVar

# Request ID for correlation across async operations
request_id_ctx: ContextVar[str | None] = ContextVar('request_id', default=None)


class LogMode(Enum):
    STDERR = 'stderr'  # JSON to stderr (production)
    FILE = 'file'      # Human-readable to file (development)
    BOTH = 'both'      # Both modes simultaneously


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        if request_id := request_id_ctx.get():
            log_obj['request_id'] = request_id

        if hasattr(record, 'path'):
            log_obj['path'] = record.path
        if hasattr(record, 'command'):
            log_obj['command'] = record.command

        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def setup_logging(
    level: str | None = None,
    mode: LogMode | None = None,
) -> None:
    """Configure logging based on environment and mode."""
    level = level or os.getenv('PYRIGHT_MCP_LOG_LEVEL', 'INFO')
    if mode is None:
        mode_str = os.getenv('PYRIGHT_MCP_LOG_MODE', 'stderr').lower()
        mode = LogMode(mode_str)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    human_formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Stderr JSON logging (for stderr/both modes)
    if mode in (LogMode.STDERR, LogMode.BOTH):
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(stderr_handler)

    # File logging (for file/both modes)
    if mode in (LogMode.FILE, LogMode.BOTH):
        log_dir = _get_log_directory()
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        log_file = log_dir / f'pyright-mcp-{timestamp}.log'

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(human_formatter)
        root_logger.addHandler(file_handler)

        # Symlink to current.log for easy tailing
        current_link = log_dir / 'current.log'
        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()
        current_link.symlink_to(log_file.name)

    # For file-only mode, also log errors to stderr
    if mode == LogMode.FILE:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.setFormatter(human_formatter)
        root_logger.addHandler(stderr_handler)

    logging.info(f'Logging initialized (mode={mode.value}, level={level})')


def _get_log_directory() -> Path:
    """Get platform-appropriate log directory."""
    if sys.platform == 'win32':
        return Path.home() / 'AppData' / 'Local' / 'pyright-mcp' / 'logs'
    return Path.home() / '.pyright-mcp' / 'logs'
```

**Critical Logging Points:**

| Event | Level | Extra Fields |
|-------|-------|--------------|
| Server startup | INFO | version, python_version, mode |
| Tool invocation | INFO | tool_name, request_id, parameters |
| Pyright CLI start | DEBUG | command, cwd, request_id |
| Pyright CLI stderr | DEBUG | stderr_output, request_id |
| Tool completion | INFO | duration, request_id |
| Tool error | ERROR | error_type, message, traceback |
| Server shutdown | INFO | uptime, total_requests |

### 8.3 Runtime Configuration

Future: Support configuration via MCP resources or initialization options.

---

## 9. Testing Strategy

### 9.1 Test Categories

| Category | Scope | Tools |
|----------|-------|-------|
| Unit | Individual functions | pytest |
| Integration | Tool + backend | pytest + temp files |
| E2E | Full MCP flow | pytest + MCP client |

### 9.2 Test Structure

```
tests/
├── unit/
│   ├── test_project_detection.py
│   ├── test_cli_runner.py
│   └── test_lsp_client.py
├── integration/
│   ├── test_check_types.py
│   ├── test_hover.py
│   └── test_definition.py
├── e2e/
│   └── test_mcp_server.py
└── fixtures/
    ├── valid_project/
    ├── invalid_project/
    └── sample_files/
```

### 9.3 Test Fixtures

```python
# fixtures/valid_project/
valid_project/
├── pyproject.toml
├── src/
│   └── example.py  # Valid Python with type hints
└── .venv/
    └── bin/python

# fixtures/sample_files/
sample_files/
├── valid.py        # No type errors
├── with_errors.py  # Has type errors
├── syntax_error.py # Invalid Python syntax
└── no_hints.py     # No type annotations
```

---

## 10. Performance Considerations

### 10.1 Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| `check_types` (single file) | < 2s | CLI cold start |
| `check_types` (directory) | < 10s | Depends on size |
| `get_hover` (warm LSP) | < 200ms | LSP already running |
| `get_hover` (cold LSP) | < 3s | Includes LSP init |
| `go_to_definition` | < 200ms | Similar to hover |

### 10.2 Optimization Strategies

**Phase 1:**
- Async subprocess execution (non-blocking)
- Timeout enforcement

**Phase 2:**
- Persistent LSP subprocess (avoid cold start)
- Lazy initialization (don't start until needed)
- Idle timeout (free resources when unused)

**Future:**
- File content caching (avoid re-reading unchanged files)
- Incremental analysis (if LSP supports it)

---

## 11. Security Considerations

### 11.1 Input Validation

- Validate all file paths are absolute
- Reject paths outside workspace (optional, configurable)
- Sanitize paths before passing to subprocess

### 11.2 Subprocess Security

- No shell=True in subprocess calls
- Explicit argument lists
- Timeout enforcement to prevent hangs

### 11.3 File System Access

- Read-only operations only (no file modifications)
- Follow symlinks cautiously
- Respect file permissions

---

## 12. Dependencies

### 12.1 Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp` | >= 1.0.0 | MCP SDK (includes FastMCP) |
| `pyright` | >= 1.1.0 | Type checker (CLI + LSP) |

### 12.2 Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | >= 8.0 | Testing |
| `pytest-asyncio` | >= 0.23 | Async test support |
| `ruff` | >= 0.4 | Linting + formatting |

### 12.3 System Requirements

- Python 3.10+
- Node.js (for Pyright, installed via pyright package)

---

## 13. Deployment

### 13.1 Installation

```bash
# Via uv (recommended)
uv add pyright-mcp

# Via pip
pip install pyright-mcp
```

### 13.2 Claude Code Configuration

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

Or for development:
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

---

## 14. Open Technical Decisions

### 14.1 Resolved

| Decision | Resolution | Rationale |
|----------|------------|-----------|
| CLI vs LSP | CLI for Phase 1, LSP for Phase 2 | CLI simpler for diagnostics, LSP required for hover/definition |
| Single vs multi-project | Single first | Covers common case, defer complexity |
| Transport | stdio default | Standard for local MCP servers |

### 14.2 Deferred

| Decision | Options | Decide When |
|----------|---------|-------------|
| LSP library | pygls vs raw JSON-RPC | Phase 2 implementation |
| Caching strategy | None vs file-based vs in-memory | After performance profiling |
| Multi-project handling | Reinit vs multiple instances | When use case emerges |

---

## 15. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2025-01-21 | Claude Code | Initial draft |
| 0.2 | 2026-01-21 | Claude Code | Added Section 3 (Position Indexing), Section 4 (Utilities), Section 8.2 (Logging Strategy), renumbered sections |
