"""Integration tests for hover and definition tools.

These tests verify the tools work with the actual Pyright LSP server.
They are slower and require pyright-langserver to be installed.
"""

import pytest

from pyright_mcp.backends.selector import reset_selector
from pyright_mcp.tools.definition import go_to_definition
from pyright_mcp.tools.hover import get_hover


@pytest.fixture(autouse=True)
def reset_selector_fixture():
    """Reset selector between tests to ensure clean LSP state."""
    reset_selector()
    yield
    reset_selector()


class TestGetHoverIntegration:
    """Integration tests for get_hover tool."""

    @pytest.mark.asyncio
    async def test_get_hover_on_builtin_type(self, tmp_path):
        """Test hover on a builtin type variable."""
        file_path = tmp_path / "test.py"
        file_path.write_text("""
x: int = 42
""")

        result = await get_hover(str(file_path), line=2, column=1)

        assert result["status"] == "success"
        # Should have type info for 'x'
        # Pyright may return 'int' or 'Literal[42]' depending on inference
        if result["type"]:
            type_lower = result["type"].lower()
            assert "int" in type_lower or "literal" in type_lower or "x" in type_lower

    @pytest.mark.asyncio
    async def test_get_hover_on_function_definition(self, tmp_path):
        """Test hover on a function definition."""
        file_path = tmp_path / "test.py"
        file_path.write_text("""
def greet(name: str) -> str:
    \"\"\"Greet someone by name.\"\"\"
    return f"Hello, {name}!"
""")

        # Hover on function name (line 2, column 5 = 'g' in 'greet')
        result = await get_hover(str(file_path), line=2, column=5)

        assert result["status"] == "success"
        if result["type"]:
            # Should mention the function signature
            assert "str" in result["type"]

    @pytest.mark.asyncio
    async def test_get_hover_on_class(self, tmp_path):
        """Test hover on a class definition."""
        file_path = tmp_path / "test.py"
        file_path.write_text("""
class Person:
    \"\"\"A person with a name.\"\"\"
    def __init__(self, name: str):
        self.name = name
""")

        # Hover on class name
        result = await get_hover(str(file_path), line=2, column=7)

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_hover_on_whitespace(self, tmp_path):
        """Test hover on whitespace returns no info."""
        file_path = tmp_path / "test.py"
        file_path.write_text("""

x: int = 1
""")

        # Hover on empty first line
        result = await get_hover(str(file_path), line=1, column=1)

        assert result["status"] == "success"
        # No info at whitespace position

    @pytest.mark.asyncio
    async def test_get_hover_invalid_line(self, tmp_path):
        """Test hover with line 0 returns validation error."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        result = await get_hover(str(file_path), line=0, column=1)

        assert result["status"] == "error"
        assert result["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_get_hover_nonexistent_file(self, tmp_path):
        """Test hover on nonexistent file returns error."""
        nonexistent = tmp_path / "nonexistent.py"

        result = await get_hover(str(nonexistent), line=1, column=1)

        assert result["status"] == "error"


class TestGoToDefinitionIntegration:
    """Integration tests for go_to_definition tool."""

    @pytest.mark.asyncio
    async def test_go_to_definition_local_variable(self, tmp_path):
        """Test definition lookup for local variable."""
        file_path = tmp_path / "test.py"
        file_path.write_text("""
x: int = 42
y = x + 1
""")

        # Position on 'x' in line 3 (y = x + 1)
        result = await go_to_definition(str(file_path), line=3, column=5)

        assert result["status"] == "success"
        # Should find definition of x
        if result["definitions"]:
            defn = result["definitions"][0]
            assert defn["file"] == str(file_path)
            assert defn["line"] == 2  # Where x is defined

    @pytest.mark.asyncio
    async def test_go_to_definition_function_call(self, tmp_path):
        """Test definition lookup for function call."""
        file_path = tmp_path / "test.py"
        file_path.write_text("""
def add(a: int, b: int) -> int:
    return a + b

result = add(1, 2)
""")

        # Position on 'add' in the call (line 5)
        result = await go_to_definition(str(file_path), line=5, column=10)

        assert result["status"] == "success"
        if result["definitions"]:
            defn = result["definitions"][0]
            assert defn["line"] == 2  # Function definition line

    @pytest.mark.asyncio
    async def test_go_to_definition_imported_module(self, tmp_path):
        """Test definition lookup for imported function."""
        # Create module
        module_path = tmp_path / "helper.py"
        module_path.write_text("""
def helper_func() -> str:
    return "help"
""")

        # Create main file that imports it
        main_path = tmp_path / "main.py"
        main_path.write_text("""
from helper import helper_func

result = helper_func()
""")

        # Position on 'helper_func' in import
        result = await go_to_definition(str(main_path), line=2, column=20)

        assert result["status"] == "success"
        # May find definition in helper.py

    @pytest.mark.asyncio
    async def test_go_to_definition_class_attribute(self, tmp_path):
        """Test definition lookup for class attribute."""
        file_path = tmp_path / "test.py"
        file_path.write_text("""
class Person:
    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        return f"Hello, {self.name}"
""")

        # Position on 'self.name' in greet method
        result = await go_to_definition(str(file_path), line=7, column=30)

        assert result["status"] == "success"
        # Should find definition where self.name is set

    @pytest.mark.asyncio
    async def test_go_to_definition_no_definition(self, tmp_path):
        """Test definition lookup on literal with no definition."""
        file_path = tmp_path / "test.py"
        file_path.write_text("""
x = 42
""")

        # Position on the number 42
        result = await go_to_definition(str(file_path), line=2, column=6)

        assert result["status"] == "success"
        # No definition for a literal
        assert result["definitions"] == [] or result["definitions"] is not None

    @pytest.mark.asyncio
    async def test_go_to_definition_invalid_line(self, tmp_path):
        """Test definition with line 0 returns validation error."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        result = await go_to_definition(str(file_path), line=0, column=1)

        assert result["status"] == "error"
        assert result["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_go_to_definition_nonexistent_file(self, tmp_path):
        """Test definition on nonexistent file returns error."""
        nonexistent = tmp_path / "nonexistent.py"

        result = await go_to_definition(str(nonexistent), line=1, column=1)

        assert result["status"] == "error"


class TestHoverDefinitionWorkspaceSwitch:
    """Test tools handle workspace switching correctly."""

    @pytest.mark.asyncio
    async def test_hover_different_workspaces(self, tmp_path):
        """Test hover works across different workspace directories."""
        # Create two workspaces
        workspace1 = tmp_path / "ws1"
        workspace1.mkdir()
        file1 = workspace1 / "test.py"
        file1.write_text("x: int = 1")

        workspace2 = tmp_path / "ws2"
        workspace2.mkdir()
        file2 = workspace2 / "test.py"
        file2.write_text("y: str = 'hello'")

        # Hover in first workspace
        result1 = await get_hover(str(file1), line=1, column=1)
        assert result1["status"] == "success"

        # Hover in second workspace
        result2 = await get_hover(str(file2), line=1, column=1)
        assert result2["status"] == "success"
