"""
IBM Bob - Go Language Parser
Tree-sitter based parser for Go source files
"""

import logging
from typing import Any

try:
    from tree_sitter import Language, Parser
    from tree_sitter_go import language as go_language
except ImportError:
    Language = None
    Parser = None
    go_language = None

from bob.parsers.base import (
    CodeSymbol,
    ImportStatement,
    LanguageParser,
    SymbolType,
)

logger = logging.getLogger(__name__)


class GoParser(LanguageParser):
    """
    Go language parser using Tree-sitter.

    Extracts:
    - Structs and methods
    - Functions
    - Interfaces
    - Imports
    - Type definitions
    """

    @property
    def language_name(self) -> str:
        return "go"

    @property
    def file_extensions(self) -> list[str]:
        return [".go"]

    def _setup_parser(self) -> None:
        """Initialize Tree-sitter parser for Go"""
        if Parser is None or go_language is None:
            raise ImportError(
                "tree-sitter-go not installed. "
                "Install with: pip install tree-sitter tree-sitter-go"
            )

        self._parser = Parser()
        self._language = go_language()
        self._parser.set_language(self._language)
        logger.debug("Go parser initialized")

    def _extract_symbols(self, tree: Any, source_code: bytes) -> list[CodeSymbol]:
        """Extract structs, functions, interfaces from Go AST"""
        symbols = []

        def traverse(node: Any, parent_struct: str | None = None) -> None:
            """Recursively traverse AST and extract symbols"""

            # Extract type declarations (structs, interfaces)
            if node.type == "type_declaration":
                for child in node.children:
                    if child.type == "type_spec":
                        type_symbol = self._extract_type_spec(child, source_code)
                        if type_symbol:
                            symbols.append(type_symbol)

            # Extract function declarations
            elif node.type == "function_declaration":
                func_symbol = self._extract_function(node, source_code)
                if func_symbol:
                    symbols.append(func_symbol)

            # Extract method declarations
            elif node.type == "method_declaration":
                method_symbol = self._extract_method(node, source_code)
                if method_symbol:
                    symbols.append(method_symbol)

            # Continue traversing
            for child in node.children:
                traverse(child, parent_struct)

        traverse(tree.root_node)
        return symbols

    def _extract_type_spec(self, node: Any, source_code: bytes) -> CodeSymbol | None:
        """Extract type specification (struct, interface, type alias)"""
        try:
            name_node = node.child_by_field_name("name")
            type_node = node.child_by_field_name("type")

            if not name_node or not type_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Determine symbol type based on type node
            symbol_type = SymbolType.CLASS  # Default
            if type_node.type == "struct_type":
                symbol_type = SymbolType.CLASS
            elif type_node.type == "interface_type":
                symbol_type = SymbolType.INTERFACE
            else:
                symbol_type = SymbolType.CONSTANT  # Type alias

            # Build signature
            type_text = self._get_node_text(type_node, source_code)
            signature = f"type {name} {type_text}"

            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=symbol_type,
                file_path="",
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                signature=signature,
                docstring=None,
                parent=None,
                modifiers=[],
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract type spec: {e}")
            return None

    def _extract_function(self, node: Any, source_code: bytes) -> CodeSymbol | None:
        """Extract function declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Get parameters
            parameters = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                parameters = self._extract_parameters(params_node, source_code)

            # Get return type
            return_type = None
            result_node = node.child_by_field_name("result")
            if result_node:
                return_type = self._get_node_text(result_node, source_code)

            # Build signature
            params_str = ", ".join(parameters)
            signature = f"func {name}({params_str})"
            if return_type:
                signature += f" {return_type}"

            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=SymbolType.FUNCTION,
                file_path="",
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                signature=signature,
                docstring=None,
                parent=None,
                modifiers=[],
                parameters=parameters,
                return_type=return_type,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract function: {e}")
            return None

    def _extract_method(self, node: Any, source_code: bytes) -> CodeSymbol | None:
        """Extract method declaration"""
        try:
            name_node = node.child_by_field_name("name")
            receiver_node = node.child_by_field_name("receiver")

            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Get receiver (parent struct/type)
            parent = None
            if receiver_node:
                receiver_text = self._get_node_text(receiver_node, source_code)
                # Extract type name from receiver (e.g., "(s *Service)" -> "Service")
                parent = receiver_text.strip("()").split()[-1].strip("*")

            # Get parameters
            parameters = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                parameters = self._extract_parameters(params_node, source_code)

            # Get return type
            return_type = None
            result_node = node.child_by_field_name("result")
            if result_node:
                return_type = self._get_node_text(result_node, source_code)

            # Build signature
            receiver_text = self._get_node_text(receiver_node, source_code) if receiver_node else ""
            params_str = ", ".join(parameters)
            signature = f"func {receiver_text} {name}({params_str})"
            if return_type:
                signature += f" {return_type}"

            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=SymbolType.METHOD,
                file_path="",
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                signature=signature,
                docstring=None,
                parent=parent,
                modifiers=[],
                parameters=parameters,
                return_type=return_type,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract method: {e}")
            return None

    def _extract_parameters(self, params_node: Any, source_code: bytes) -> list[str]:
        """Extract function/method parameters"""
        parameters = []

        for child in params_node.children:
            if child.type == "parameter_declaration":
                param_text = self._get_node_text(child, source_code)
                parameters.append(param_text)
            elif child.type == "variadic_parameter_declaration":
                param_text = self._get_node_text(child, source_code)
                parameters.append(param_text)

        return parameters

    def _extract_imports(self, tree: Any, source_code: bytes) -> list[ImportStatement]:
        """Extract import statements from Go AST"""
        imports = []

        def traverse(node: Any) -> None:
            """Recursively find import statements"""

            if node.type == "import_declaration":
                import_stmts = self._extract_import_declaration(node, source_code)
                imports.extend(import_stmts)

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return imports

    def _extract_import_declaration(
        self,
        node: Any,
        source_code: bytes,
    ) -> list[ImportStatement]:
        """Extract import declaration (can have multiple imports)"""
        imports = []

        try:
            start_line, _ = self._get_node_line_range(node)

            for child in node.children:
                if child.type == "import_spec":
                    # Get package path
                    path_node = child.child_by_field_name("path")
                    if path_node:
                        module = self._get_node_text(path_node, source_code).strip('"')

                        # Get alias if present
                        alias = None
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            alias = self._get_node_text(name_node, source_code)

                        imports.append(
                            ImportStatement(
                                module=module,
                                imported_names=[module.split("/")[-1]],  # Package name
                                alias=alias,
                                is_relative=False,
                                line_number=start_line,
                            )
                        )
        except Exception as e:
            logger.warning(f"Failed to extract import declaration: {e}")

        return imports

    def _is_comment_line(self, line: str) -> bool:
        """Check if a line is a Go comment"""
        return line.startswith("//") or line.startswith("/*") or line.startswith("*")


# Made with Bob
