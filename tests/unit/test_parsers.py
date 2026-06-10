"""
Unit tests for language parsers
"""

import tempfile
from pathlib import Path

import pytest

from bob.parsers.base import SymbolType
from bob.parsers.python_parser import PythonParser


class TestPythonParser:
    """Tests for Python parser"""

    def setup_method(self):
        """Setup test fixtures"""
        self.parser = PythonParser()

    def test_parser_properties(self):
        """Test parser properties"""
        assert self.parser.language_name == "python"
        assert ".py" in self.parser.file_extensions
        assert ".pyi" in self.parser.file_extensions

    def test_can_parse(self):
        """Test file extension detection"""
        assert self.parser.can_parse(Path("test.py"))
        assert self.parser.can_parse(Path("test.pyi"))
        assert not self.parser.can_parse(Path("test.js"))
        assert not self.parser.can_parse(Path("test.txt"))

    def test_parse_simple_function(self):
        """Test parsing a simple function"""
        code = '''
def hello_world():
    """Say hello"""
    print("Hello, World!")
    return True
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = Path(f.name)

        try:
            result = self.parser.parse_file(temp_path)

            assert result.success
            assert result.language == "python"
            assert len(result.symbols) == 1

            func = result.symbols[0]
            assert func.name == "hello_world"
            assert func.symbol_type == SymbolType.FUNCTION
            assert func.docstring == "Say hello"
            assert func.start_line > 0
        finally:
            temp_path.unlink()

    def test_parse_class_with_methods(self):
        """Test parsing a class with methods"""
        code = '''
class Calculator:
    """A simple calculator"""
    
    def __init__(self):
        self.result = 0
    
    def add(self, x: int, y: int) -> int:
        """Add two numbers"""
        return x + y
    
    def subtract(self, x: int, y: int) -> int:
        """Subtract two numbers"""
        return x - y
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = Path(f.name)

        try:
            result = self.parser.parse_file(temp_path)

            assert result.success
            assert len(result.symbols) == 4  # 1 class + 3 methods

            # Check class
            class_symbol = result.symbols[0]
            assert class_symbol.name == "Calculator"
            assert class_symbol.symbol_type == SymbolType.CLASS
            assert class_symbol.docstring == "A simple calculator"

            # Check methods
            method_names = [s.name for s in result.symbols[1:]]
            assert "__init__" in method_names
            assert "add" in method_names
            assert "subtract" in method_names

            # Check method details
            add_method = [s for s in result.symbols if s.name == "add"][0]
            assert add_method.symbol_type == SymbolType.METHOD
            assert add_method.parent == "Calculator"
            assert "x" in add_method.parameters
            assert "y" in add_method.parameters
        finally:
            temp_path.unlink()

    def test_parse_imports(self):
        """Test parsing import statements"""
        code = """
import os
import sys
from pathlib import Path
from typing import List, Dict
from . import utils
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = Path(f.name)

        try:
            result = self.parser.parse_file(temp_path)

            assert result.success
            assert len(result.imports) >= 3

            # Check import types
            import_modules = [imp.module for imp in result.imports]
            assert "os" in import_modules
            assert "sys" in import_modules
            assert "pathlib" in import_modules

            # Check from imports
            pathlib_import = [imp for imp in result.imports if imp.module == "pathlib"][0]
            assert "Path" in pathlib_import.imported_names

            # Check relative import
            relative_imports = [imp for imp in result.imports if imp.is_relative]
            assert len(relative_imports) > 0
        finally:
            temp_path.unlink()

    def test_parse_invalid_syntax(self):
        """Test parsing file with syntax errors"""
        code = """
def broken_function(
    # Missing closing parenthesis
    print("This won't parse")
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = Path(f.name)

        try:
            result = self.parser.parse_file(temp_path)

            # Should still return a result, but with errors
            assert not result.success
            assert len(result.parse_errors) > 0
        finally:
            temp_path.unlink()

    def test_is_binary_file(self):
        """Test binary file detection"""
        # Create a binary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".py", delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            temp_path = Path(f.name)

        try:
            assert self.parser.is_binary_file(temp_path)
        finally:
            temp_path.unlink()

    def test_file_not_found(self):
        """Test parsing non-existent file"""
        with pytest.raises(FileNotFoundError):
            self.parser.parse_file(Path("/nonexistent/file.py"))


# Made with Bob
