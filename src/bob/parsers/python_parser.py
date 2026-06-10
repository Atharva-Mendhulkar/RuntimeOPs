"""
IBM Bob - Python Language Parser
Tree-sitter based parser for Python source files
"""

import logging
from typing import Any

try:
    from tree_sitter import Language, Parser
    from tree_sitter_python import language as python_language
except ImportError:
    # Graceful degradation if tree-sitter not installed
    Language = None
    Parser = None
    python_language = None

from bob.parsers.base import (
    CodeSymbol,
    ImportStatement,
    LanguageParser,
    SymbolType,
)

logger = logging.getLogger(__name__)


class PythonParser(LanguageParser):
    """
    Python language parser using Tree-sitter.

    Extracts:
    - Classes and methods
    - Functions
    - Imports (import, from...import)
    - Docstrings
    - Type hints
    """

    @property
    def language_name(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> list[str]:
        return [".py", ".pyi"]

    def _setup_parser(self) -> None:
        """Initialize Tree-sitter parser for Python"""
        if Parser is None or python_language is None:
            raise ImportError(
                "tree-sitter-python not installed. "
                "Install with: pip install tree-sitter tree-sitter-python"
            )

        self._parser = Parser()
        self._language = python_language()
        self._parser.set_language(self._language)
        logger.debug("Python parser initialized")

    def _extract_symbols(self, tree: Any, source_code: bytes) -> list[CodeSymbol]:
        """Extract classes, functions, and methods from Python AST"""
        symbols = []

        def traverse(node: Any, parent_class: str | None = None) -> None:
            """Recursively traverse AST and extract symbols"""

            # Extract class definitions
            if node.type == "class_definition":
                class_symbol = self._extract_class(node, source_code)
                if class_symbol:
                    symbols.append(class_symbol)
                    # Traverse class body for methods
                    for child in node.children:
                        if child.type == "block":
                            for stmt in child.children:
                                traverse(stmt, class_symbol.name)

            # Extract function definitions
            elif node.type == "function_definition":
                func_symbol = self._extract_function(node, source_code, parent_class)
                if func_symbol:
                    symbols.append(func_symbol)

            # Extract decorated definitions
            elif node.type == "decorated_definition":
                for child in node.children:
                    if child.type in ("class_definition", "function_definition"):
                        traverse(child, parent_class)

            # Continue traversing for top-level definitions
            elif parent_class is None:
                for child in node.children:
                    traverse(child, parent_class)

        traverse(tree.root_node)
        return symbols

    def _extract_class(self, node: Any, source_code: bytes) -> CodeSymbol | None:
        """Extract class definition"""
        try:
            # Get class name
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Get base classes
            superclasses = []
            superclass_node = node.child_by_field_name("superclasses")
            if superclass_node:
                for child in superclass_node.children:
                    if child.type == "identifier":
                        superclasses.append(self._get_node_text(child, source_code))

            # Get docstring
            docstring = self._extract_docstring(node, source_code)

            # Get full body
            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=SymbolType.CLASS,
                file_path="",  # Set by caller
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                signature=(
                    f"class {name}({', '.join(superclasses)})" if superclasses else f"class {name}"
                ),
                docstring=docstring,
                parent=None,
                modifiers=[],
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract class: {e}")
            return None

    def _extract_function(
        self,
        node: Any,
        source_code: bytes,
        parent_class: str | None = None,
    ) -> CodeSymbol | None:
        """Extract function or method definition"""
        try:
            # Get function name
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Determine if it's a method or function
            symbol_type = SymbolType.METHOD if parent_class else SymbolType.FUNCTION

            # Get parameters
            parameters = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for child in params_node.children:
                    if child.type == "identifier":
                        parameters.append(self._get_node_text(child, source_code))
                    elif child.type == "typed_parameter":
                        param_name = child.child_by_field_name("name")
                        if param_name:
                            param_text = self._get_node_text(param_name, source_code)
                            param_type = child.child_by_field_name("type")
                            if param_type:
                                param_text += f": {self._get_node_text(param_type, source_code)}"
                            parameters.append(param_text)
                    elif child.type == "default_parameter":
                        param_name = child.child_by_field_name("name")
                        if param_name:
                            parameters.append(self._get_node_text(param_name, source_code))

            # Get return type
            return_type = None
            return_node = node.child_by_field_name("return_type")
            if return_node:
                return_type = self._get_node_text(return_node, source_code)

            # Get docstring
            docstring = self._extract_docstring(node, source_code)

            # Build signature
            params_str = ", ".join(parameters)
            signature = f"def {name}({params_str})"
            if return_type:
                signature += f" -> {return_type}"

            # Get modifiers (async, etc.)
            modifiers = []
            if node.parent and node.parent.type == "decorated_definition":
                for child in node.parent.children:
                    if child.type == "decorator":
                        decorator_text = self._get_node_text(child, source_code)
                        modifiers.append(decorator_text)

            # Check for async
            for child in node.children:
                if child.type == "async":
                    modifiers.append("async")
                    break

            # Get full body
            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=symbol_type,
                file_path="",  # Set by caller
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                signature=signature,
                docstring=docstring,
                parent=parent_class,
                modifiers=modifiers,
                parameters=parameters,
                return_type=return_type,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract function: {e}")
            return None

    def _extract_docstring(self, node: Any, source_code: bytes) -> str | None:
        """Extract docstring from a class or function definition"""
        try:
            # Look for body block
            body_node = node.child_by_field_name("body")
            if not body_node:
                return None

            # First statement in body should be expression_statement with string
            for child in body_node.children:
                if child.type == "expression_statement":
                    for expr_child in child.children:
                        if expr_child.type == "string":
                            docstring = self._get_node_text(expr_child, source_code)
                            # Remove quotes
                            docstring = docstring.strip('"""').strip("'''").strip('"').strip("'")
                            return docstring.strip()
                    break

            return None
        except Exception:
            return None

    def _extract_imports(self, tree: Any, source_code: bytes) -> list[ImportStatement]:
        """Extract import statements from Python AST"""
        imports = []

        def traverse(node: Any) -> None:
            """Recursively find import statements"""

            # Handle 'import module' statements
            if node.type == "import_statement":
                import_stmt = self._extract_import_statement(node, source_code)
                if import_stmt:
                    imports.append(import_stmt)

            # Handle 'from module import name' statements
            elif node.type == "import_from_statement":
                import_stmt = self._extract_import_from_statement(node, source_code)
                if import_stmt:
                    imports.append(import_stmt)

            # Continue traversing
            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return imports

    def _extract_import_statement(
        self,
        node: Any,
        source_code: bytes,
    ) -> ImportStatement | None:
        """Extract 'import module' statement"""
        try:
            imported_names = []
            module = ""
            alias = None

            for child in node.children:
                if child.type == "dotted_name":
                    module = self._get_node_text(child, source_code)
                    imported_names.append(module)
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node:
                        module = self._get_node_text(name_node, source_code)
                        imported_names.append(module)
                    if alias_node:
                        alias = self._get_node_text(alias_node, source_code)

            if not module:
                return None

            start_line, _ = self._get_node_line_range(node)

            return ImportStatement(
                module=module,
                imported_names=imported_names,
                alias=alias,
                is_relative=False,
                line_number=start_line,
            )
        except Exception as e:
            logger.warning(f"Failed to extract import statement: {e}")
            return None

    def _extract_import_from_statement(
        self,
        node: Any,
        source_code: bytes,
    ) -> ImportStatement | None:
        """Extract 'from module import name' statement"""
        try:
            module = ""
            imported_names = []
            is_relative = False

            # Get module name
            module_node = node.child_by_field_name("module_name")
            if module_node:
                module = self._get_node_text(module_node, source_code)
            else:
                # Check for relative imports (from . import ...)
                for child in node.children:
                    if child.type == "relative_import":
                        is_relative = True
                        module = self._get_node_text(child, source_code)
                        break

            # Get imported names
            for child in node.children:
                if child.type == "dotted_name":
                    imported_names.append(self._get_node_text(child, source_code))
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        imported_names.append(self._get_node_text(name_node, source_code))
                elif child.type == "wildcard_import":
                    imported_names.append("*")

            if not module and not is_relative:
                return None

            start_line, _ = self._get_node_line_range(node)

            return ImportStatement(
                module=module,
                imported_names=imported_names,
                alias=None,
                is_relative=is_relative,
                line_number=start_line,
            )
        except Exception as e:
            logger.warning(f"Failed to extract from-import statement: {e}")
            return None

    def _is_comment_line(self, line: str) -> bool:
        """Check if a line is a Python comment"""
        return line.startswith("#")


# Made with Bob
