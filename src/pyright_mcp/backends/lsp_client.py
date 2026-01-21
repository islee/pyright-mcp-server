"""LSP client for Pyright language server.

Manages the pyright-langserver subprocess with JSON-RPC over stdin/stdout.
Provides hover, go-to-definition, and completion functionality via LSP protocol.

Key features:
- Lazy initialization on first request
- Idle timeout (configurable via PYRIGHT_MCP_LSP_TIMEOUT, default 5 minutes)
- Activity tracking on all requests (hover, definition, complete)
- Automatic crash recovery (restart on next request)
- Document lifecycle management via DocumentManager

Note: check_idle_timeout() must be called periodically for timeout enforcement.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..config import Config, get_config
from ..logging_config import get_logger
from ..utils.position import Position, Range
from ..utils.uri import path_to_uri, uri_to_path
from .base import (
    BackendError,
    CompletionItem,
    CompletionResult,
    DefinitionResult,
    HoverResult,
    Location,
)
from .document_manager import DocumentManager

logger = get_logger("backends.lsp_client")


class LSPState(Enum):
    """LSP subprocess lifecycle states."""

    NOT_STARTED = "not_started"
    INITIALIZING = "initializing"
    READY = "ready"
    SHUTDOWN = "shutdown"


@dataclass
class LSPProcess:
    """LSP subprocess state container.

    Attributes:
        process: The asyncio subprocess
        workspace_root: Current workspace root (for re-initialization detection)
        last_activity: Timestamp of last request (for idle timeout)
    """

    process: asyncio.subprocess.Process
    workspace_root: Path
    last_activity: float


class LSPClient:
    """Manages pyright-langserver subprocess for hover and definition requests.

    This client implements the LSP protocol over JSON-RPC via stdin/stdout.
    It handles:
    - Subprocess lifecycle (start, initialize, shutdown)
    - Request/response correlation via request IDs
    - Document lifecycle via DocumentManager
    - Crash recovery (auto-restart on next request)
    - Idle timeout (shutdown after inactivity)

    Example:
        client = LSPClient()
        await client.ensure_initialized(Path("/path/to/project"))
        result = await client.hover(Path("/path/to/file.py"), line=10, column=5)
        await client.shutdown()
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize LSP client.

        Args:
            config: Configuration instance (uses get_config() if not provided)
        """
        self.config = config or get_config()
        self._state = LSPState.NOT_STARTED
        self._process: LSPProcess | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._documents = DocumentManager()
        self._pending_requests: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> LSPState:
        """Current LSP client state."""
        return self._state

    @property
    def workspace_root(self) -> Path | None:
        """Current workspace root, or None if not initialized."""
        return self._process.workspace_root if self._process else None

    async def ensure_initialized(self, workspace_root: Path) -> None:
        """Ensure LSP server is running and initialized for workspace.

        If server is not running, starts it and runs initialization sequence.
        If workspace has changed, shuts down and reinitializes.

        Args:
            workspace_root: Project root for LSP workspace configuration

        Raises:
            BackendError: If initialization fails
        """
        async with self._lock:
            # Check if already initialized for this workspace
            if (
                self._state == LSPState.READY
                and self._process
                and self._process.workspace_root == workspace_root
            ):
                # Update activity timestamp
                self._process.last_activity = time.time()
                logger.debug(f"LSP already ready for workspace: {workspace_root}")
                return

            # Need to (re)initialize
            if self._state != LSPState.NOT_STARTED:
                logger.info("Workspace changed or LSP not ready, reinitializing")
                await self._shutdown_internal()

            await self._start_and_initialize(workspace_root)

    async def _start_and_initialize(self, workspace_root: Path) -> None:
        """Start LSP subprocess and run initialization sequence.

        Args:
            workspace_root: Project root for workspace configuration

        Raises:
            BackendError: If startup or initialization fails
        """
        self._state = LSPState.INITIALIZING
        logger.info(f"Starting LSP server for workspace: {workspace_root}")

        try:
            # Start subprocess
            cmd = self.config.lsp_command
            logger.debug(f"LSP command: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self._process = LSPProcess(
                process=process,
                workspace_root=workspace_root,
                last_activity=time.time(),
            )

            # Start background reader task
            self._reader_task = asyncio.create_task(self._read_responses())

            # Send initialize request
            workspace_uri = path_to_uri(workspace_root)
            init_params = {
                "processId": os.getpid(),
                "rootUri": workspace_uri,
                "rootPath": str(workspace_root),
                "capabilities": {
                    "textDocument": {
                        "hover": {
                            "contentFormat": ["plaintext", "markdown"],
                        },
                        "definition": {
                            "linkSupport": False,
                        },
                    },
                },
                "workspaceFolders": [
                    {"uri": workspace_uri, "name": workspace_root.name}
                ],
            }

            result = await self._send_request("initialize", init_params)
            capabilities = result.get("capabilities", {}) if result else {}
            logger.debug(f"LSP initialized: {capabilities.keys()}")

            # Send initialized notification
            await self.send_notification("initialized", {})

            self._state = LSPState.READY
            logger.info(f"LSP server ready for workspace: {workspace_root}")

        except FileNotFoundError as e:
            self._state = LSPState.NOT_STARTED
            cmd_name = self.config.lsp_command[0]
            raise BackendError(
                error_code="not_found",
                message=f"LSP server not found: {cmd_name}. Is pyright installed?",
                recoverable=False,
            ) from e
        except asyncio.TimeoutError as e:
            await self._cleanup()
            raise BackendError(
                error_code="timeout",
                message="LSP server initialization timed out",
                recoverable=True,
            ) from e
        except Exception as e:
            await self._cleanup()
            logger.error(f"LSP initialization failed: {e}", exc_info=True)
            raise BackendError(
                error_code="lsp_crash",
                message=f"LSP server initialization failed: {e}",
                recoverable=True,
            ) from e

    async def hover(
        self,
        file: Path,
        line: int,
        column: int,
        *,
        project_root: Path | None = None,
    ) -> HoverResult:
        """Get hover information at a position.

        Args:
            file: Path to the file
            line: 0-indexed line number
            column: 0-indexed column number
            project_root: Optional project root (uses file's parent if not specified)

        Returns:
            HoverResult with type and documentation info

        Raises:
            BackendError: If operation fails
        """
        # Determine workspace root
        workspace = project_root or file.parent

        # Ensure LSP is ready
        await self.ensure_initialized(workspace)

        async with self._lock:
            if self._state != LSPState.READY:
                raise BackendError(
                    error_code="lsp_not_ready",
                    message="LSP server is not ready",
                    recoverable=True,
                )

            # Update activity timestamp for idle timeout tracking
            if self._process:
                self._process.last_activity = time.time()

            try:
                # Ensure document is open
                await self._documents.ensure_open(self, file)

                # Send hover request
                uri = path_to_uri(file)
                params = {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": column},
                }

                result = await self._send_request("textDocument/hover", params)

                # Parse response
                return self._parse_hover_response(result)

            except BackendError:
                raise
            except Exception as e:
                logger.error(f"Hover request failed: {e}", exc_info=True)
                await self._handle_error(e)
                raise BackendError(
                    error_code="lsp_crash",
                    message=f"Hover request failed: {e}",
                    recoverable=True,
                ) from e

    async def definition(
        self,
        file: Path,
        line: int,
        column: int,
        *,
        project_root: Path | None = None,
    ) -> DefinitionResult:
        """Get definition locations for a symbol at a position.

        Args:
            file: Path to the file
            line: 0-indexed line number
            column: 0-indexed column number
            project_root: Optional project root (uses file's parent if not specified)

        Returns:
            DefinitionResult with list of definition locations

        Raises:
            BackendError: If operation fails
        """
        # Determine workspace root
        workspace = project_root or file.parent

        # Ensure LSP is ready
        await self.ensure_initialized(workspace)

        async with self._lock:
            if self._state != LSPState.READY:
                raise BackendError(
                    error_code="lsp_not_ready",
                    message="LSP server is not ready",
                    recoverable=True,
                )

            # Update activity timestamp for idle timeout tracking
            if self._process:
                self._process.last_activity = time.time()

            try:
                # Ensure document is open
                await self._documents.ensure_open(self, file)

                # Send definition request
                uri = path_to_uri(file)
                params = {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": column},
                }

                result = await self._send_request("textDocument/definition", params)

                # Parse response
                return self._parse_definition_response(result)

            except BackendError:
                raise
            except Exception as e:
                logger.error(f"Definition request failed: {e}", exc_info=True)
                await self._handle_error(e)
                raise BackendError(
                    error_code="lsp_crash",
                    message=f"Definition request failed: {e}",
                    recoverable=True,
                ) from e

    async def complete(
        self,
        file: Path,
        line: int,
        column: int,
        *,
        project_root: Path | None = None,
        trigger_character: str | None = None,
    ) -> CompletionResult:
        """Get completion suggestions at a position.

        Args:
            file: Path to the file
            line: 0-indexed line number
            column: 0-indexed column number
            project_root: Optional project root (uses file's parent if not specified)
            trigger_character: Character that triggered completion (e.g., ".")

        Returns:
            CompletionResult with completion suggestions

        Raises:
            BackendError: If operation fails
        """
        # Determine workspace root
        workspace = project_root or file.parent

        # Ensure LSP is ready
        await self.ensure_initialized(workspace)

        async with self._lock:
            if self._state != LSPState.READY:
                raise BackendError(
                    error_code="lsp_not_ready",
                    message="LSP server is not ready",
                    recoverable=True,
                )

            # Update activity timestamp for idle timeout tracking
            if self._process:
                self._process.last_activity = time.time()

            try:
                # Ensure document is open
                await self._documents.ensure_open(self, file)

                # Send completion request
                uri = path_to_uri(file)
                params: dict[str, Any] = {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": column},
                }

                # Add completion context
                if trigger_character:
                    params["context"] = {
                        "triggerKind": 2,  # TriggerCharacter
                        "triggerCharacter": trigger_character,
                    }
                else:
                    params["context"] = {
                        "triggerKind": 1,  # Invoked
                    }

                result = await self._send_request("textDocument/completion", params)

                # Parse response
                return self._parse_completion_response(result)

            except BackendError:
                raise
            except Exception as e:
                logger.error(f"Completion request failed: {e}", exc_info=True)
                await self._handle_error(e)
                raise BackendError(
                    error_code="lsp_crash",
                    message=f"Completion request failed: {e}",
                    recoverable=True,
                ) from e

    async def shutdown(self) -> None:
        """Gracefully shutdown the LSP server.

        Sends shutdown request, exit notification, and terminates subprocess.
        """
        async with self._lock:
            await self._shutdown_internal()

    async def _shutdown_internal(self) -> None:
        """Internal shutdown implementation (assumes lock is held)."""
        if self._state == LSPState.NOT_STARTED:
            return

        logger.info("Shutting down LSP server")

        try:
            # Close all documents
            if self._state == LSPState.READY:
                await self._documents.close_all(self)

            # Send shutdown request
            if self._process and self._process.process.returncode is None:
                try:
                    await asyncio.wait_for(
                        self._send_request("shutdown", None),
                        timeout=5.0,
                    )
                    await self.send_notification("exit", None)
                except Exception as e:
                    logger.warning(f"Shutdown request failed: {e}")

        except Exception as e:
            logger.warning(f"Error during shutdown: {e}")
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up subprocess and state."""
        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        # Kill process
        if self._process and self._process.process.returncode is None:
            self._process.process.kill()
            try:
                await asyncio.wait_for(self._process.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Process did not terminate, forcing")
                self._process.process.terminate()

        # Clear state
        self._process = None
        self._state = LSPState.NOT_STARTED
        self._documents.clear()
        self._pending_requests.clear()
        self._request_id = 0

    async def _send_request(
        self,
        method: str,
        params: dict[str, Any] | None,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        """Send JSON-RPC request and wait for response.

        Args:
            method: LSP method name (e.g., "textDocument/hover")
            params: Request parameters
            timeout: Response timeout in seconds

        Returns:
            Response result (may be None for some requests)

        Raises:
            BackendError: If request fails or times out
        """
        if not self._process or not self._process.process.stdin:
            raise BackendError(
                error_code="lsp_not_ready",
                message="LSP server is not running",
                recoverable=True,
            )

        # Generate request ID
        self._request_id += 1
        request_id = self._request_id

        # Build request
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        # Create future for response
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            # Send request
            content = json.dumps(request)
            message = f"Content-Length: {len(content)}\r\n\r\n{content}"

            logger.debug(f"Sending request: {method} (id={request_id})")
            self._process.process.stdin.write(message.encode("utf-8"))
            await self._process.process.stdin.drain()

            # Wait for response
            response = await asyncio.wait_for(future, timeout=timeout)

            # Check for error
            if "error" in response:
                error = response["error"]
                raise BackendError(
                    error_code="lsp_crash",
                    message=f"LSP error: {error.get('message', 'Unknown error')}",
                    recoverable=True,
                    details={"lsp_error": error},
                )

            return response.get("result")

        except asyncio.TimeoutError as e:
            raise BackendError(
                error_code="timeout",
                message=f"LSP request timed out: {method}",
                recoverable=True,
            ) from e
        finally:
            self._pending_requests.pop(request_id, None)

    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | None,
    ) -> None:
        """Send JSON-RPC notification (no response expected).

        This method is public to allow DocumentManager to send
        didOpen/didClose notifications.

        Args:
            method: LSP method name
            params: Notification parameters
        """
        if not self._process or not self._process.process.stdin:
            logger.warning(f"Cannot send notification {method}: LSP not running")
            return

        # Build notification (no id)
        notification: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        # Send notification
        content = json.dumps(notification)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"

        logger.debug(f"Sending notification: {method}")
        self._process.process.stdin.write(message.encode("utf-8"))
        await self._process.process.stdin.drain()

    async def _read_responses(self) -> None:
        """Background task to read responses from LSP server."""
        if not self._process or not self._process.process.stdout:
            return

        buffer = b""

        try:
            while True:
                # Read data
                chunk = await self._process.process.stdout.read(4096)
                if not chunk:
                    logger.warning("LSP stdout closed")
                    break

                buffer += chunk

                # Parse messages from buffer
                while True:
                    # Look for Content-Length header
                    header_end = buffer.find(b"\r\n\r\n")
                    if header_end == -1:
                        break

                    # Parse headers
                    headers = buffer[:header_end].decode("utf-8")
                    content_length = None
                    for line in headers.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            break

                    if content_length is None:
                        logger.error("Missing Content-Length header")
                        break

                    # Check if we have complete message
                    message_start = header_end + 4
                    message_end = message_start + content_length

                    if len(buffer) < message_end:
                        break  # Wait for more data

                    # Extract and parse message
                    message_bytes = buffer[message_start:message_end]
                    buffer = buffer[message_end:]

                    try:
                        message = json.loads(message_bytes.decode("utf-8"))
                        await self._handle_message(message)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse LSP message: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading LSP responses: {e}", exc_info=True)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming LSP message (response or notification)."""
        # Check if it's a response
        if "id" in message:
            request_id = message["id"]
            future = self._pending_requests.get(request_id)
            if future and not future.done():
                future.set_result(message)
            else:
                logger.warning(f"Received response for unknown request: {request_id}")
        else:
            # It's a notification
            method = message.get("method", "unknown")
            if method == "window/logMessage":
                params = message.get("params", {})
                logger.debug(f"LSP log: {params.get('message', '')}")
            elif method == "textDocument/publishDiagnostics":
                # Ignore diagnostics (we use CLI for type checking)
                pass
            else:
                logger.debug(f"Received notification: {method}")

    async def _handle_error(self, error: Exception) -> None:
        """Handle LSP errors with potential recovery."""
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            logger.warning("LSP subprocess crashed, will restart on next request")
            await self._cleanup()
        elif isinstance(error, asyncio.TimeoutError):
            logger.warning("LSP request timed out")
        else:
            logger.error(f"LSP error: {error}")
            await self._cleanup()

    def _parse_hover_response(self, result: dict[str, Any] | None) -> HoverResult:
        """Parse LSP hover response into HoverResult.

        Args:
            result: LSP hover response (may be None)

        Returns:
            HoverResult with parsed data
        """
        if result is None:
            return HoverResult(type_info=None, documentation=None, range=None)

        # Extract contents
        contents = result.get("contents")
        type_info = None
        documentation = None

        if contents is None:
            pass
        elif isinstance(contents, str):
            type_info = contents
        elif isinstance(contents, dict):
            # MarkupContent or MarkedString
            value = contents.get("value", "")
            if value:
                type_info = value
        elif isinstance(contents, list):
            # Array of MarkedString
            parts = []
            for item in contents:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("value", ""))
            if parts:
                type_info = parts[0] if parts else None
                documentation = "\n".join(parts[1:]) if len(parts) > 1 else None

        # Extract range
        range_data = result.get("range")
        hover_range = Range.from_lsp(range_data) if range_data else None

        return HoverResult(
            type_info=type_info,
            documentation=documentation,
            range=hover_range,
        )

    def _parse_definition_response(
        self, result: dict[str, Any] | list[dict[str, Any]] | None
    ) -> DefinitionResult:
        """Parse LSP definition response into DefinitionResult.

        Args:
            result: LSP definition response (Location, Location[], or LocationLink[])

        Returns:
            DefinitionResult with parsed locations
        """
        if result is None:
            return DefinitionResult(definitions=[])

        locations: list[Location] = []

        # Handle single location
        if isinstance(result, dict) and "uri" in result:
            location = self._parse_location(result)
            if location:
                locations.append(location)
        # Handle array of locations
        elif isinstance(result, list):
            for item in result:
                location = self._parse_location(item)
                if location:
                    locations.append(location)

        return DefinitionResult(definitions=locations)

    def _parse_location(self, loc: dict[str, Any]) -> Location | None:
        """Parse a single LSP Location or LocationLink.

        Args:
            loc: LSP Location or LocationLink dict

        Returns:
            Location or None if parsing fails
        """
        try:
            # Handle LocationLink (has targetUri)
            if "targetUri" in loc:
                uri = loc["targetUri"]
                range_data = loc.get("targetSelectionRange") or loc.get("targetRange")
            # Handle Location (has uri)
            elif "uri" in loc:
                uri = loc["uri"]
                range_data = loc.get("range")
            else:
                return None

            file_path = uri_to_path(uri)
            if range_data:
                start = range_data.get("start", {})
                position = Position(
                    line=start.get("line", 0),
                    column=start.get("character", 0),
                )
            else:
                position = Position(line=0, column=0)

            return Location(file=file_path, position=position)

        except Exception as e:
            logger.warning(f"Failed to parse location: {e}")
            return None

    def _parse_completion_response(
        self, result: dict[str, Any] | list[dict[str, Any]] | None
    ) -> CompletionResult:
        """Parse LSP completion response into CompletionResult.

        Args:
            result: LSP completion response (CompletionList or CompletionItem[])

        Returns:
            CompletionResult with parsed items
        """
        if result is None:
            return CompletionResult(items=[], is_incomplete=False)

        # Handle CompletionList vs array of CompletionItem
        if isinstance(result, dict) and "items" in result:
            items_data = result.get("items", [])
            is_incomplete = result.get("isIncomplete", False)
        elif isinstance(result, list):
            items_data = result
            is_incomplete = False
        else:
            return CompletionResult(items=[], is_incomplete=False)

        items: list[CompletionItem] = []
        for item_data in items_data:
            item = self._parse_completion_item(item_data)
            if item:
                items.append(item)

        return CompletionResult(items=items, is_incomplete=is_incomplete)

    def _parse_completion_item(self, item: dict[str, Any]) -> CompletionItem | None:
        """Parse a single LSP CompletionItem.

        Args:
            item: LSP CompletionItem dict

        Returns:
            CompletionItem or None if parsing fails
        """
        try:
            label = item.get("label", "")
            if not label:
                return None

            # Map LSP CompletionItemKind to string
            kind_map = {
                1: "text",
                2: "method",
                3: "function",
                4: "constructor",
                5: "field",
                6: "variable",
                7: "class",
                8: "interface",
                9: "module",
                10: "property",
                11: "unit",
                12: "value",
                13: "enum",
                14: "keyword",
                15: "snippet",
                16: "color",
                17: "file",
                18: "reference",
                19: "folder",
                20: "enum_member",
                21: "constant",
                22: "struct",
                23: "event",
                24: "operator",
                25: "type_parameter",
            }
            kind_num = item.get("kind", 1)
            kind = kind_map.get(kind_num, "text")

            # Extract detail and documentation
            detail = item.get("detail")
            doc = item.get("documentation")
            if isinstance(doc, dict):
                doc = doc.get("value", "")

            # Extract insert text
            insert_text = item.get("insertText")
            if not insert_text:
                text_edit = item.get("textEdit")
                if isinstance(text_edit, dict):
                    insert_text = text_edit.get("newText")

            return CompletionItem(
                label=label,
                kind=kind,
                detail=detail,
                documentation=doc,
                insert_text=insert_text,
            )

        except Exception as e:
            logger.warning(f"Failed to parse completion item: {e}")
            return None

    async def check_idle_timeout(self) -> bool:
        """Check if LSP should be shut down due to idle timeout.

        This method must be called periodically to enforce idle timeout.
        Current implementation expects manual invocation, e.g.:

        - Per-request check: Call after each request completes
        - Background task: asyncio.create_task() checking periodically
        - Tool wrapper: Check before/after tool execution

        Phase 3 Note: Consider adaptive timeout strategies:
        - Shorter timeout after period of high activity (e.g., 1 min after completions)
        - Longer timeout during low activity (current 5 min default)
        - Or keep simple: single configurable timeout via PYRIGHT_MCP_LSP_TIMEOUT

        Activity is tracked via _process.last_activity, updated on:
        - ensure_initialized() - LSP startup
        - hover() - hover requests
        - definition() - go-to-definition requests
        - complete() - completion requests

        Returns:
            True if LSP was shut down due to timeout, False otherwise
        """
        async with self._lock:
            if self._state != LSPState.READY or not self._process:
                return False

            idle_time = time.time() - self._process.last_activity
            if idle_time >= self.config.lsp_timeout:
                logger.info(
                    f"LSP idle timeout ({idle_time:.1f}s >= {self.config.lsp_timeout}s)"
                )
                await self._shutdown_internal()
                return True

            return False
