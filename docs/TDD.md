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

**MCP Tool API uses 1-indexed positions. Internal data structures use 0-indexed.**

| Component | Line | Column | Notes |
|-----------|------|--------|-------|
| MCP Tool API | 1-indexed | 1-indexed | External interface (user-friendly) |
| Internal data structures | 0-indexed | 0-indexed | Diagnostic, Location, Range |
| Pyright CLI JSON | 0-indexed | 0-indexed | Native format |
| Pyright LSP | 0-indexed | 0-indexed | LSP specification |

**Conversion boundary:** Tool implementations convert at the API boundary:
- Input: `line_0 = line - 1`, `column_0 = column - 1`
- Output: `line = line_0 + 1`, `column = column_0 + 1`

**Rationale:**
- **API (1-indexed):** Matches what editors display to users. When Claude reports "error at line 42", users can directly navigate to line 42 in their editor without mental conversion.
- **Internal (0-indexed):** Pyright CLI and LSP both use 0-indexed positions natively. Using 0-indexed internally eliminates conversion errors when interfacing with Pyright.

**Implementation:** See `tools/hover.py:validate_hover_input()` and `tools/definition.py:validate_definition_input()` for conversion examples.

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

### 4.4 Input Validation

**File:** `src/pyright_mcp/validation/paths.py`

```python
"""Path validation and workspace restriction."""

from pathlib import Path
from typing import Sequence

from ..config import get_config
from ..logging_config import get_logger

logger = get_logger('validation.paths')


class PathValidationError(Exception):
    """Raised when a path fails validation."""
    pass


def validate_path(path: Path) -> None:
    """
    Validate a path for security and correctness.

    Args:
        path: Path to validate (should be absolute)

    Raises:
        PathValidationError: If path is invalid or not allowed
    """
    # Ensure path is absolute
    if not path.is_absolute():
        raise PathValidationError(f"Path must be absolute: {path}")

    # Check workspace restriction
    if not is_path_allowed(path):
        config = get_config()
        allowed = config.allowed_paths or ["(all paths allowed)"]
        raise PathValidationError(
            f"Path not in allowed workspace: {path}\n"
            f"Allowed paths: {', '.join(str(p) for p in allowed)}"
        )


def is_path_allowed(path: Path) -> bool:
    """
    Check if path is within allowed workspace.

    Uses PYRIGHT_MCP_ALLOWED_PATHS environment variable.
    If not set, all paths are allowed (trusted client mode).

    Args:
        path: Path to check

    Returns:
        True if path is allowed, False otherwise
    """
    config = get_config()

    # If no restriction set, allow all paths
    if config.allowed_paths is None:
        return True

    # Check if path is within any allowed root
    path = path.resolve()
    for allowed_root in config.allowed_paths:
        try:
            path.relative_to(allowed_root)
            return True
        except ValueError:
            continue

    return False
```

**File:** `src/pyright_mcp/validation/inputs.py`

```python
"""Input validation for MCP tool parameters."""

from pathlib import Path
from typing import Tuple


class InputValidationError(Exception):
    """Raised when input parameters are invalid."""
    pass


def validate_position(line: int, column: int) -> Tuple[int, int]:
    """
    Validate line and column position.

    Args:
        line: 0-indexed line number
        column: 0-indexed column number

    Returns:
        Tuple of (line, column) if valid

    Raises:
        InputValidationError: If position is invalid
    """
    if line < 0:
        raise InputValidationError(f"Line must be >= 0, got: {line}")
    if column < 0:
        raise InputValidationError(f"Column must be >= 0, got: {column}")

    return (line, column)


def validate_python_version(version: str | None) -> str | None:
    """
    Validate Python version string.

    Args:
        version: Python version (e.g., "3.11") or None

    Returns:
        Version string if valid, None if input was None

    Raises:
        InputValidationError: If version format is invalid
    """
    if version is None:
        return None

    # Expected format: "3.10", "3.11", etc.
    import re
    if not re.match(r"^\d+\.\d+$", version):
        raise InputValidationError(
            f"Invalid Python version format: {version}. "
            f"Expected format: '3.10', '3.11', etc."
        )

    return version
```

**File:** `src/pyright_mcp/validation/__init__.py`

```python
"""Input validation utilities."""

from .paths import validate_path, is_path_allowed, PathValidationError
from .inputs import validate_position, validate_python_version, InputValidationError

__all__ = [
    "validate_path",
    "is_path_allowed",
    "PathValidationError",
    "validate_position",
    "validate_python_version",
    "InputValidationError",
]
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

### 5.1.1 Configuration Module

**File:** `src/pyright_mcp/config.py`

```python
"""Runtime configuration management."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Runtime configuration for pyright-mcp."""
    allowed_paths: list[Path] | None  # Workspace restriction (None = allow all)
    cli_timeout: float                # CLI execution timeout (seconds)
    lsp_timeout: float                # LSP idle timeout (seconds)
    lsp_command: list[str]            # LSP server command
    log_mode: str                     # Logging mode: stderr, file, both
    log_level: str                    # Logging level: DEBUG, INFO, WARNING, ERROR
    enable_health_check: bool         # Enable health_check tool


_config: Config | None = None


def load_config() -> Config:
    """
    Load configuration from environment variables.

    Environment Variables:
        PYRIGHT_MCP_ALLOWED_PATHS: Colon-separated list of allowed paths (default: None)
        PYRIGHT_MCP_CLI_TIMEOUT: CLI timeout in seconds (default: 30)
        PYRIGHT_MCP_LSP_TIMEOUT: LSP idle timeout in seconds (default: 300)
        PYRIGHT_MCP_LSP_COMMAND: LSP server command (default: pyright-langserver)
        PYRIGHT_MCP_LOG_MODE: Logging mode (default: stderr)
        PYRIGHT_MCP_LOG_LEVEL: Logging level (default: INFO)
        PYRIGHT_MCP_ENABLE_HEALTH_CHECK: Enable health_check tool (default: true)

    Returns:
        Config instance
    """
    # Parse allowed paths
    allowed_paths = None
    if allowed_paths_str := os.getenv("PYRIGHT_MCP_ALLOWED_PATHS"):
        allowed_paths = [Path(p).resolve() for p in allowed_paths_str.split(":")]

    # Parse LSP command
    lsp_command_str = os.getenv("PYRIGHT_MCP_LSP_COMMAND", "pyright-langserver")
    lsp_command = lsp_command_str.split() if lsp_command_str else ["pyright-langserver", "--stdio"]

    return Config(
        allowed_paths=allowed_paths,
        cli_timeout=float(os.getenv("PYRIGHT_MCP_CLI_TIMEOUT", "30")),
        lsp_timeout=float(os.getenv("PYRIGHT_MCP_LSP_TIMEOUT", "300")),
        lsp_command=lsp_command,
        log_mode=os.getenv("PYRIGHT_MCP_LOG_MODE", "stderr"),
        log_level=os.getenv("PYRIGHT_MCP_LOG_LEVEL", "INFO"),
        enable_health_check=os.getenv("PYRIGHT_MCP_ENABLE_HEALTH_CHECK", "true").lower() == "true",
    )


def get_config() -> Config:
    """
    Get singleton config instance.

    Returns:
        Config instance (loads on first call)
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config
```

### 5.2 Project Detection Module

**File:** `src/pyright_mcp/context/project.py`

**Note:** Project detection is organized in the `context/` module to group related functionality (project root, venv, config parsing) and prepare for Phase 2 workspace management.

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
async def detect_project(target_path: Path) -> ProjectContext:
    """
    Detect project context from a target file or directory (async).

    Detection order:
    1. Walk up from target_path looking for config files
    2. Find venv in project root
    3. Extract Python version from config if present

    Note: Made async in Phase 1 to prepare for Phase 2 workspace indexing
    and I/O-heavy operations (e.g., scanning large directories, reading
    multiple config files in parallel).
    """

async def find_project_root(start_path: Path) -> Path:
    """Find project root by locating config files (async)."""

def find_venv(project_root: Path) -> Path | None:
    """Find virtual environment for project."""

def get_python_version(project_context: ProjectContext) -> str | None:
    """Extract Python version from project config."""
```

### 5.3 Backend Interface Protocol

**File:** `src/pyright_mcp/backends/base.py`

All backends implement a common protocol for consistent error handling and testability:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class PyrightBackend(Protocol):
    """Protocol for Pyright backend implementations."""

    async def check(
        self,
        path: Path,
        context: ProjectContext,
        python_version: str | None = None,
    ) -> "DiagnosticsResult | BackendError":
        """Run type checking on path."""
        ...

    async def shutdown(self) -> None:
        """Clean up resources."""
        ...


class BackendError(Exception):
    """Exception for backend operation errors.

    Design rationale: Using exceptions instead of dataclasses for error handling
    in Python async code. This approach integrates naturally with try/except blocks
    and exception chaining, making error propagation clearer than result types.
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        recoverable: bool = False,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize backend error.

        Args:
            error_code: One of: not_found, timeout, parse_error, invalid_path,
                        execution_error, lsp_crash, validation_error,
                        path_not_allowed, cancelled
            message: Human-readable error description
            recoverable: Whether the operation can be retried
            details: Optional additional context
        """
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.recoverable = recoverable
        self.details = details or {}
```

### 5.4 Pyright CLI Runner (Phase 1)

**File:** `src/pyright_mcp/backends/cli_runner.py`

**Data Structures:**
```python
@dataclass
class Diagnostic:
    """Single diagnostic from Pyright.

    Uses Range object for position data, matching LSP structure.
    This simplifies Phase 2 transition and provides consistent
    position handling via Range.to_display() for human output.
    """
    file: str
    range: Range                  # 0-indexed start/end positions
    severity: Literal["error", "warning", "information"]
    message: str
    rule: str | None = None       # e.g., "reportArgumentType"

    @property
    def start(self) -> Position:
        """Convenience accessor for start position."""
        return self.range.start

    @property
    def end(self) -> Position:
        """Convenience accessor for end position."""
        return self.range.end


@dataclass
class DiagnosticsResult:
    """Result from check_types operation."""
    diagnostics: list[Diagnostic]
    files_analyzed: int
    error_count: int
    warning_count: int
    information_count: int
    time_sec: float
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

### 5.5 LSP Client (Phase 2)

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
        self._documents = DocumentManager()

    async def ensure_initialized(self, workspace_root: Path) -> None:
        """Start LSP if not running, reinitialize if workspace changed."""

    async def hover(self, file: Path, line: int, column: int) -> HoverResult | BackendError:
        """Send textDocument/hover request."""

    async def definition(self, file: Path, line: int, column: int) -> list[Location] | BackendError:
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

### 5.6 Document Lifecycle Management (Phase 2)

**File:** `src/pyright_mcp/backends/document_manager.py`

LSP requires explicit document open/close notifications. The DocumentManager tracks opened documents to avoid redundant didOpen calls and ensure proper cleanup.

**Design Decisions:**
- **didOpen strategy:** Send once per unique file, track in memory
- **didClose strategy:** Send on idle timeout or workspace change (not per-request)
- **Content sync:** Read from disk on first open; Pyright watches files for changes

```python
@dataclass
class OpenDocument:
    """Tracked open document state."""
    uri: str
    version: int
    opened_at: float  # timestamp

class DocumentManager:
    """Track opened documents for LSP lifecycle."""

    def __init__(self):
        self._opened: dict[Path, OpenDocument] = {}

    def is_open(self, path: Path) -> bool:
        """Check if document is already open."""
        return path in self._opened

    async def ensure_open(self, lsp: "LSPClient", path: Path) -> None:
        """
        Send didOpen if document not already open.

        Reads current file content from disk.
        """
        if path in self._opened:
            return

        content = path.read_text(encoding="utf-8")
        uri = path_to_uri(path)

        await lsp._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "python",
                "version": 1,
                "text": content,
            }
        })

        self._opened[path] = OpenDocument(
            uri=uri,
            version=1,
            opened_at=time.time(),
        )

    async def close_all(self, lsp: "LSPClient") -> None:
        """Send didClose for all tracked documents."""
        for path, doc in self._opened.items():
            await lsp._send_notification("textDocument/didClose", {
                "textDocument": {"uri": doc.uri}
            })
        self._opened.clear()

    def clear(self) -> None:
        """Clear tracking without sending notifications (e.g., after LSP crash)."""
        self._opened.clear()
```

**Lifecycle Flow:**
```
hover(file.py)
    │
    ├── DocumentManager.ensure_open(file.py)
    │       │
    │       ├── (if not open) → didOpen notification
    │       └── (if open) → skip
    │
    └── textDocument/hover request

LSP idle timeout or workspace change:
    │
    └── DocumentManager.close_all()
            │
            └── didClose for each tracked document
```

### 5.7 LSP Data Structures

**Data Structures:**
```python
@dataclass
class HoverResult:
    """Result from get_hover operation."""
    type_info: str | None       # Type signature
    documentation: str | None   # Docstring
    range: Range | None         # Source range of symbol (uses utils/position.py Range)

@dataclass
class Location:
    """A location in a file (uses Position from utils)."""
    file: str
    position: Position          # 0-indexed position
```

### 5.8 Tools Layer

**File:** `src/pyright_mcp/tools/`

Each tool:
1. Validates input (using validation module from Section 4.4)
2. Detects project context
3. Delegates to appropriate backend
4. Formats response for LLM consumption

**Response Format (Discriminated Union):**

All tools use a discriminated union pattern with `status` field for clear success/error handling:

```python
# Success response
{
    "status": "success",
    "summary": "...",
    "data": { ... }
}

# Error response
{
    "status": "error",
    "error_code": "file_not_found",
    "message": "Human-readable error message"
}
```

**Rationale:** This pattern eliminates ambiguity in client-side handling. Clients check `status` first rather than probing for error fields mixed with success fields.

**Tool Interfaces:**
```python
# tools/check_types.py
async def check_types(
    path: str,
    python_version: str | None = None,
) -> dict:
    """
    Returns (success):
        {
            "status": "success",
            "summary": "Analyzed 5 files in 0.45s. Found 1 error(s).",
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [
                {
                    "file": "/path/to/file.py",
                    "location": "10:5",  # 1-indexed for human readability
                    "severity": "error",
                    "message": "...",
                    "rule": "reportArgumentType"
                }
            ]
        }

    Returns (error):
        {
            "status": "error",
            "error_code": "file_not_found",
            "message": "Path not found: /path/to/file.py"
        }
    """

# tools/hover.py (Phase 2)
async def get_hover(
    file: str,
    line: int,
    column: int,
) -> dict:
    """
    Returns (success):
        {
            "status": "success",
            "symbol": "add",
            "type": "(x: int, y: int) -> int",
            "documentation": "Add two integers.",
        }

    Returns (no info):
        {
            "status": "success",
            "symbol": null,
            "type": null,
            "documentation": null
        }

    Returns (error):
        {
            "status": "error",
            "error_code": "lsp_crash",
            "message": "LSP server crashed, please retry"
        }
    """

# tools/definition.py (Phase 2)
async def go_to_definition(
    file: str,
    line: int,
    column: int,
) -> dict:
    """
    Returns (single definition):
        {
            "status": "success",
            "definitions": [
                {
                    "file": "/path/to/module.py",
                    "line": 5,
                    "column": 4
                }
            ]
        }

    Returns (no definition):
        {
            "status": "success",
            "definitions": []
        }

    Returns (error):
        {
            "status": "error",
            "error_code": "file_not_found",
            "message": "File not found: /path/to/file.py"
        }
    """
```

### 5.9 Health Check Tool

**File:** `src/pyright_mcp/tools/health_check.py`

**Purpose:** Diagnostic tool for verifying server configuration and runtime state.

**Enabled by:** `PYRIGHT_MCP_ENABLE_HEALTH_CHECK` environment variable (default: true)

**Interface:**
```python
async def health_check() -> dict:
    """
    Check server health and configuration.

    Returns diagnostic information about:
    - Pyright CLI version and availability
    - LSP server status (if initialized)
    - Current configuration
    - Runtime statistics

    Returns:
        {
            "status": "success",
            "pyright_version": "1.1.350",
            "pyright_available": true,
            "lsp_status": "not_initialized" | "running" | "crashed",
            "config": {
                "allowed_paths": ["/path/to/workspace"],
                "cli_timeout": 30,
                "lsp_timeout": 300,
                "log_mode": "stderr",
                "log_level": "INFO"
            },
            "uptime_seconds": 123.45
        }
    """
```

**Implementation Notes:**
- Check Pyright CLI availability: `pyright --version`
- Query LSP client state (if Phase 2 implemented)
- Sanitize config (don't expose sensitive paths in untrusted mode)
- Include basic runtime stats (uptime, request count)

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

### 6.3 Cancellation Support (Phase 2+)

**File:** `src/pyright_mcp/utils/cancellation.py`

MCP protocol supports request cancellation via notifications. This allows clients to cancel long-running operations.

**CancellationToken:**
```python
class CancellationToken:
    """Token for checking if operation has been cancelled."""

    def __init__(self):
        self._cancelled = False
        self._callbacks: list[Callable[[], None]] = []

    def cancel(self) -> None:
        """Mark operation as cancelled and run callbacks."""
        self._cancelled = True
        for callback in self._callbacks:
            callback()

    def is_cancelled(self) -> bool:
        """Check if operation has been cancelled."""
        return self._cancelled

    def on_cancel(self, callback: Callable[[], None]) -> None:
        """Register callback to run when cancelled."""
        self._callbacks.append(callback)

    def raise_if_cancelled(self) -> None:
        """Raise exception if cancelled."""
        if self._cancelled:
            raise CancellationError("Operation cancelled")


class CancellationError(Exception):
    """Raised when operation is cancelled."""
    pass
```

**Cancellation Flow:**
```
Client                     pyright-mcp                    Backend
  │                             │                             │
  │  request (id=123)           │                             │
  │────────────────────────────►│                             │
  │                             │  start operation            │
  │                             │────────────────────────────►│
  │                             │                             │
  │  cancel notification (123)  │                             │
  │────────────────────────────►│                             │
  │                             │  token.cancel()             │
  │                             │  kill subprocess / abort    │
  │                             │────────────────────────────►│
  │                             │                             │
  │◄────────────────────────────│                             │
  │  { status: "error",                                       │
  │    error_code: "cancelled" }│                             │
```

**Integration with Backends:**
- CLI backend: Kill subprocess on cancellation
- LSP backend: Send `$/cancelRequest` to language server
- Check `token.is_cancelled()` at async yield points

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

All tools return errors using the discriminated union pattern (matching Section 5.8):
```python
{
    "status": "error",
    "error_code": "file_not_found",  # machine-readable code
    "message": "Human-readable error message"
}
```

**Note:** The `status` field distinguishes success from error responses. Clients check `status` first.

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
| `PYRIGHT_MCP_ALLOWED_PATHS` | (none) | Colon-separated list of allowed workspace paths. If not set, all paths allowed. |
| `PYRIGHT_MCP_LOG_MODE` | `stderr` | Logging mode: `stderr`, `file`, or `both` |
| `PYRIGHT_MCP_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PYRIGHT_MCP_LSP_COMMAND` | `pyright-langserver` | LSP server binary (Phase 2+) |
| `PYRIGHT_MCP_LSP_TIMEOUT` | `300` | LSP idle timeout in seconds (Phase 2+) |
| `PYRIGHT_MCP_CLI_TIMEOUT` | `30` | CLI execution timeout in seconds |
| `PYRIGHT_MCP_ENABLE_HEALTH_CHECK` | `true` | Enable `health_check` tool |
| `PYRIGHT_MCP_TRANSPORT` | (none) | Transport mode: `stdio` (default), `http`, `sse` (Phase 3) |

**Workspace Restriction Example:**
```bash
# Allow access only to specific projects
export PYRIGHT_MCP_ALLOWED_PATHS="/home/user/projects:/home/user/work"

# Allow all paths (default behavior)
unset PYRIGHT_MCP_ALLOWED_PATHS
```

### 8.2 Logging Strategy

**Dual-mode logging** with configurable output via `PYRIGHT_MCP_LOG_MODE`:

| Mode | Output | Format | Use Case |
|------|--------|--------|----------|
| `stderr` (default) | stderr | JSON Lines | Production, log aggregation |
| `file` | `~/.pyright-mcp/logs/` | Human-readable | Local development |
| `both` | stderr + file | JSON + Human | Debugging production issues |

**File:** `src/pyright_mcp/logging_config.py`

**Initialization Pattern:**

Logging must be initialized explicitly in `__main__.py`, NOT at module import time. This avoids:
- Import side effects that complicate testing
- Inability to control logging in unit tests
- Issues with multiple entry points

```python
# __main__.py (correct)
from .logging_config import setup_logging
from .server import create_mcp_server

def main():
    setup_logging()  # Explicit initialization
    mcp = create_mcp_server()
    mcp.run()

# server.py (incorrect - avoid)
# setup_logging()  # DON'T call at import time
```

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
| `mcp` | >= 1.1.0 | MCP SDK (includes FastMCP) |
| `pyright` | >= 1.1.0 | Type checker (CLI + LSP) |

**Note:** The `mcp[cli]` extra is deprecated. Use `mcp>=1.1.0` directly.

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

## 14. Implementation Phases

### 14.1 Phase 1: CLI-based check_types (Current)

**Deliverables:**
- `check_types` tool using Pyright CLI (`--outputjson`)
- Project detection (async, prepares for Phase 2)
- Input validation and path restriction
- Configuration module
- Logging infrastructure
- Health check tool

**Backend:** CLI only

**Status:** In progress

### 14.2 Phase 2: LSP Integration for Hover and Definition

**Scope:** Add `get_hover` and `go_to_definition` tools using Pyright LSP server

**Key Architectural Decision:** LSP for IDE features only, CLI stays for type checking

| Tool | Backend | Rationale |
|------|---------|-----------|
| `check_types` | CLI | Synchronous, predictable; `publishDiagnostics` is async notification |
| `get_hover` | LSP | `textDocument/hover` is synchronous request/response |
| `go_to_definition` | LSP | `textDocument/definition` is synchronous request/response |

**Why NOT use LSP for check_types:** The `textDocument/publishDiagnostics` is a server→client *notification*, not a request. You cannot "request" diagnostics - they're published asynchronously after document changes.

**Architecture Changes:**

1. **Protocol Extension**
   - Add `HoverBackend` and `DefinitionBackend` protocols to `base.py`
   - Add `HoverResult` and `Location` data structures
   - Keep existing `Backend` protocol for check operations

2. **LSP Client Infrastructure**
   - Raw JSON-RPC over stdin/stdout (no pygls dependency)
   - Lifecycle states: `not_started` → `initializing` → `ready` → `shutdown`
   - Lazy initialization on first hover/definition request
   - Idle timeout: shutdown after 5 minutes of inactivity
   - Crash recovery: restart on next request

3. **Document Manager**
   - Track opened documents with `didOpen`/`didClose` lifecycle
   - Per-file locking for concurrency safety
   - Async file reads to avoid blocking
   - Clear tracking on LSP crash (no didClose sent)

4. **Backend Selector Extension**
   - Add `get_hover_backend()` and `get_definition_backend()` methods
   - `HybridSelector`: CLI for check, LSP for hover/definition
   - Workspace detection from `ProjectContext.root`

5. **Error Code Standardization**
   - Migrate from string error codes to `ErrorCode` enum
   - Add LSP-specific codes: `lsp_error`, `lsp_not_ready`

**New Files:**
```
src/pyright_mcp/
├── backends/
│   ├── lsp_client.py         # LSP subprocess manager
│   └── document_manager.py   # didOpen/didClose tracking
└── tools/
    ├── hover.py              # get_hover tool
    └── definition.py         # go_to_definition tool
```

**Modified Files:**
- `backends/base.py` - Add protocols and data structures
- `backends/selector.py` - Add HybridSelector

**LSP Communication:**
- Raw JSON-RPC over stdin/stdout
- Initialize sequence: `initialize` → `initialized` → ready
- Document sync: `didOpen` (with content) → Pyright file watcher → `didClose`
- Requests: `textDocument/hover`, `textDocument/definition`

**Testing Strategy:**
- Unit tests with mocked LSP responses
- Integration tests with recorded pyright-langserver responses
- Test LSP crash recovery and restart
- Test document manager concurrency
- Test workspace switching

**Deliverables:**
- `get_hover` tool via LSP
- `go_to_definition` tool via LSP
- LSP client with lifecycle management
- Document manager with concurrency handling
- HybridSelector for operation-specific routing
- ErrorCode enum standardization
- LSP integration tests with recorded fixtures

**NOT in Phase 2 scope:**
- LSP for check_types (architectural mismatch)
- Completions (Phase 3)
- Result caching (Phase 3)
- Multi-workspace LSP pooling (Phase 3)

### 14.3 Phase 3: Completions, References, and Multi-Workspace Support

**Scope:** Complete IDE feature set; production-ready multi-workspace support

**Prerequisites:** Phase 2 complete (LSP client, document manager, hover, definition)

**Features:**

1. **get_completions Tool**
   - Use `textDocument/completion` LSP request
   - Return completion items with kind, type signature, documentation
   - Support trigger characters (`.`, `(`, etc.)
   - Map LSP completion kinds to readable strings

2. **find_references Tool**
   - Use `textDocument/references` LSP request
   - Return all locations where symbol is used
   - Option to include/exclude declaration

3. **Multi-Workspace LSP Pool**
   - Pool of LSP clients, one per workspace root
   - LRU eviction when at capacity (default: 3 instances)
   - Per-workspace document managers
   - Graceful shutdown of evicted clients

4. **Performance Metrics**
   - Track per-operation latencies (count, avg, min, max)
   - Error rate tracking
   - Expose via health_check tool
   - Context manager for easy integration

5. **get_signature Tool** (Optional)
   - Use `textDocument/signatureHelp` LSP request
   - Display function signatures during argument entry
   - Track active parameter position

**New Files:**
```
src/pyright_mcp/
├── backends/
│   └── lsp_pool.py           # Multi-workspace LSP pooling
├── metrics.py                # Performance tracking
└── tools/
    ├── completions.py        # get_completions tool
    ├── references.py         # find_references tool
    └── signature.py          # get_signature tool (optional)
```

**Modified Files:**
- `backends/base.py` - Add CompletionResult, CompletionItem, CompletionBackend, ReferencesBackend
- `backends/lsp_client.py` - Add complete(), references(), signature() methods
- `backends/selector.py` - Add PooledSelector
- `tools/health_check.py` - Add metrics and pool status

**Environment Variables:**
```bash
PYRIGHT_MCP_LSP_POOL_SIZE=3       # Max LSP instances (default: 3)
PYRIGHT_MCP_METRICS_ENABLED=true  # Enable metrics collection (default: true)
```

**Deliverables:**
- `get_completions` tool via LSP
- `find_references` tool via LSP
- Multi-workspace LSP pooling with LRU eviction
- Performance metrics with health_check integration
- `get_signature` tool (optional)
- PooledSelector for production deployments

**NOT in Phase 3 scope (potential future work):**
- Result caching (LSP handles this internally)
- Rate limiting (single-client MCP doesn't need it)
- HTTP/SSE transports (stdio sufficient for Claude Code)
- Rename refactoring (complex, requires file writes)
- Code actions/quick fixes (complex, requires file writes)

---

## 15. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2025-01-21 | Claude Code | Initial draft |
| 0.2 | 2026-01-21 | Claude Code | Added Section 3 (Position Indexing), Section 4 (Utilities), Section 8.2 (Logging Strategy), renumbered sections |
| 0.3 | 2026-01-21 | Claude Code | Added Section 5.3 (Backend Interface Protocol with BackendError), Section 5.6 (Document Lifecycle Management), updated Diagnostic to Range-based design, discriminated union response format, explicit logging initialization pattern, context/ module reorganization, mcp dependency update |
| 0.4 | 2026-01-21 | Claude Code | Added Section 4.4 (Input Validation), Section 5.1.1 (Configuration Module), Section 5.9 (Health Check Tool), Section 6.3 (Cancellation Support). Updated Section 5.2 (async project detection), Section 5.3 (ErrorCode enum), Section 8.1 (new env vars: ALLOWED_PATHS, ENABLE_HEALTH_CHECK, TRANSPORT). Expanded Section 14 with detailed Phase 2 (LSP for all tools, document manager, backend selection) and Phase 3 (completions, caching, rate limiting, transports, metrics, LSP pooling) implementation plans. |
| 0.5 | 2026-01-22 | Claude Code | **Phase 2 revision:** Removed LSP for check_types (publishDiagnostics is async notification, not request). Phase 2 now focused on hover and definition only. Added protocol extension (HoverBackend, DefinitionBackend), document manager concurrency handling, HybridSelector. **Phase 3 revision:** Replaced caching/rate-limiting/transports with completions, references, multi-workspace LSP pooling, and performance metrics. Added PooledSelector and optional signature help. |
| 0.6 | 2026-01-22 | Claude Code | **Section 3 update:** Changed MCP Tool API from 0-indexed to 1-indexed positions. Rationale: 1-indexed matches editor display, improving UX when users navigate to reported locations. Internal data structures remain 0-indexed for Pyright compatibility. Added conversion boundary documentation. |
