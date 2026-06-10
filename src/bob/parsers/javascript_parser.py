"""
IBM Bob - JavaScript Language Parser
Tree-sitter based parser for JavaScript source files
"""

import logging
from typing import Any

try:
    from tree_sitter import Language, Parser
    from tree_sitter_javascript import language as javascript_language
except ImportError:
    Language = None
    Parser = None
    javascript_language = None

from bob.parsers.base import (
    CodeSymbol,
    ImportStatement,
    LanguageParser,
    SymbolType,
)

logger = logging.getLogger(__name__)


class JavaScriptParser(LanguageParser):
    """
    JavaScript language parser using Tree-sitter.

    Extracts:
    - Classes and methods
    - Functions and arrow functions
    - Imports and exports (ES6 modules)
    - CommonJS require statements
    """

    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def file_extensions(self) -> list[str]:
        return [".js", ".jsx", ".mjs", ".cjs"]

    def _setup_parser(self) -> None:
        """Initialize Tree-sitter parser for JavaScript"""
        if Parser is None or javascript_language is None:
            raise ImportError(
                "tree-sitter-javascript not installed. "
                "Install with: pip install tree-sitter tree-sitter-javascript"
            )

        self._parser = Parser()
        self._language = javascript_language()
        self._parser.set_language(self._language)
        logger.debug("JavaScript parser initialized")

    def _extract_symbols(self, tree: Any, source_code: bytes) -> list[CodeSymbol]:
        """Extract classes, functions from JavaScript AST"""
        symbols = []

        def traverse(node: Any, parent_class: str | None = None) -> None:
            """Recursively traverse AST and extract symbols"""

            # Extract class declarations
            if node.type == "class_declaration":
                class_symbol = self._extract_class(node, source_code)
                if class_symbol:
                    symbols.append(class_symbol)
                    # Traverse class body for methods
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            traverse(child, class_symbol.name)

            # Extract function declarations
            elif node.type == "function_declaration":
                func_symbol = self._extract_function(node, source_code, parent_class)
                if func_symbol:
                    symbols.append(func_symbol)

            # Extract method definitions (inside classes)
            elif node.type == "method_definition":
                method_symbol = self._extract_method(node, source_code, parent_class)
                if method_symbol:
                    symbols.append(method_symbol)

            # Extract arrow functions and function expressions assigned to variables
            elif node.type == "lexical_declaration" or node.type == "variable_declaration":
                func_symbol = self._extract_variable_function(node, source_code)
                if func_symbol:
                    symbols.append(func_symbol)

            # Continue traversing for top-level definitions
            elif parent_class is None:
                for child in node.children:
                    traverse(child, parent_class)

        traverse(tree.root_node)
        return symbols

    def _extract_class(self, node: Any, source_code: bytes) -> CodeSymbol | None:
        """Extract class declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Get heritage (extends)
            heritage = []
            heritage_node = node.child_by_field_name("heritage")
            if heritage_node:
                heritage_text = self._get_node_text(heritage_node, source_code)
                heritage.append(heritage_text)

            # Build signature
            signature = f"class {name}"
            if heritage:
                signature += f" {' '.join(heritage)}"

            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=SymbolType.CLASS,
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
            logger.warning(f"Failed to extract class: {e}")
            return None

    def _extract_function(
        self,
        node: Any,
        source_code: bytes,
        parent_class: str | None = None,
    ) -> CodeSymbol | None:
        """Extract function declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Get parameters
            parameters = self._extract_parameters(node, source_code)

            # Check for async
            modifiers = []
            for child in node.children:
                if child.type == "async":
                    modifiers.append("async")
                    break

            # Build signature
            params_str = ", ".join(parameters)
            signature = f"function {name}({params_str})"

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
                parent=parent_class,
                modifiers=modifiers,
                parameters=parameters,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract function: {e}")
            return None

    def _extract_method(
        self,
        node: Any,
        source_code: bytes,
        parent_class: str | None = None,
    ) -> CodeSymbol | None:
        """Extract method definition"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            parameters = self._extract_parameters(node, source_code)

            # Check for modifiers
            modifiers = []
            for child in node.children:
                if child.type in ("static", "async"):
                    modifiers.append(child.type)

            params_str = ", ".join(parameters)
            signature = f"{name}({params_str})"

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
                parent=parent_class,
                modifiers=modifiers,
                parameters=parameters,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract method: {e}")
            return None

    def _extract_variable_function(
        self,
        node: Any,
        source_code: bytes,
    ) -> CodeSymbol | None:
        """Extract arrow function or function expression assigned to variable"""
        try:
            # Look for variable declarator with function value
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")

                    if name_node and value_node:
                        if value_node.type in ("arrow_function", "function_expression"):
                            name = self._get_node_text(name_node, source_code)
                            start_line, end_line = self._get_node_line_range(value_node)

                            parameters = self._extract_parameters(value_node, source_code)

                            # Check for async
                            modifiers = []
                            for val_child in value_node.children:
                                if val_child.type == "async":
                                    modifiers.append("async")
                                    break

                            if value_node.type == "arrow_function":
                                modifiers.append("arrow")

                            params_str = ", ".join(parameters)
                            if value_node.type == "arrow_function":
                                signature = f"const {name} = ({params_str}) =>"
                            else:
                                signature = f"const {name} = function({params_str})"

                            body = self._get_node_text(value_node, source_code)

                            return CodeSymbol(
                                name=name,
                                symbol_type=SymbolType.FUNCTION,
                                file_path="",
                                start_line=start_line,
                                end_line=end_line,
                                start_byte=value_node.start_byte,
                                end_byte=value_node.end_byte,
                                signature=signature,
                                docstring=None,
                                parent=None,
                                modifiers=modifiers,
                                parameters=parameters,
                                body=body,
                            )

            return None
        except Exception as e:
            logger.warning(f"Failed to extract variable function: {e}")
            return None

    def _extract_parameters(self, node: Any, source_code: bytes) -> list[str]:
        """Extract function/method parameters"""
        parameters = []

        params_node = node.child_by_field_name("parameters")
        if not params_node:
            return parameters

        for child in params_node.children:
            if child.type == "identifier":
                parameters.append(self._get_node_text(child, source_code))
            elif child.type == "rest_pattern":
                param_text = self._get_node_text(child, source_code)
                parameters.append(param_text)
            elif child.type == "assignment_pattern":
                # Parameter with default value
                name_node = child.child_by_field_name("left")
                if name_node:
                    parameters.append(self._get_node_text(name_node, source_code))

        return parameters

    def _extract_imports(self, tree: Any, source_code: bytes) -> list[ImportStatement]:
        """Extract import statements from JavaScript AST"""
        imports = []

        def traverse(node: Any) -> None:
            """Recursively find import statements"""

            # ES6 imports
            if node.type == "import_statement":
                import_stmt = self._extract_import_statement(node, source_code)
                if import_stmt:
                    imports.append(import_stmt)

            # CommonJS require
            elif node.type == "variable_declaration":
                require_stmt = self._extract_require_statement(node, source_code)
                if require_stmt:
                    imports.append(require_stmt)

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return imports

    def _extract_import_statement(
        self,
        node: Any,
        source_code: bytes,
    ) -> ImportStatement | None:
        """Extract ES6 import statement"""
        try:
            module = ""
            imported_names = []

            # Get source (module path)
            source_node = node.child_by_field_name("source")
            if source_node:
                module = self._get_node_text(source_node, source_code).strip('"').strip("'")

            # Get import clause
            for child in node.children:
                if child.type == "import_clause":
                    for clause_child in child.children:
                        if clause_child.type == "identifier":
                            imported_names.append(self._get_node_text(clause_child, source_code))
                        elif clause_child.type == "named_imports":
                            for named_child in clause_child.children:
                                if named_child.type == "import_specifier":
                                    name_node = named_child.child_by_field_name("name")
                                    if name_node:
                                        imported_names.append(
                                            self._get_node_text(name_node, source_code)
                                        )
                        elif clause_child.type == "namespace_import":
                            for ns_child in clause_child.children:
                                if ns_child.type == "identifier":
                                    imported_names.append(
                                        self._get_node_text(ns_child, source_code)
                                    )

            if not module:
                return None

            start_line, _ = self._get_node_line_range(node)
            is_relative = module.startswith(".")

            return ImportStatement(
                module=module,
                imported_names=imported_names,
                alias=None,
                is_relative=is_relative,
                line_number=start_line,
            )
        except Exception as e:
            logger.warning(f"Failed to extract import statement: {e}")
            return None

    def _extract_require_statement(
        self,
        node: Any,
        source_code: bytes,
    ) -> ImportStatement | None:
        """Extract CommonJS require statement"""
        try:
            # Look for: const/var name = require('module')
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")

                    if value_node and value_node.type == "call_expression":
                        func_node = value_node.child_by_field_name("function")
                        if func_node and self._get_node_text(func_node, source_code) == "require":
                            # Get module name from arguments
                            args_node = value_node.child_by_field_name("arguments")
                            if args_node:
                                for arg_child in args_node.children:
                                    if arg_child.type == "string":
                                        module = (
                                            self._get_node_text(arg_child, source_code)
                                            .strip('"')
                                            .strip("'")
                                        )

                                        imported_names = []
                                        if name_node:
                                            imported_names.append(
                                                self._get_node_text(name_node, source_code)
                                            )

                                        start_line, _ = self._get_node_line_range(node)
                                        is_relative = module.startswith(".")

                                        return ImportStatement(
                                            module=module,
                                            imported_names=imported_names,
                                            alias=None,
                                            is_relative=is_relative,
                                            line_number=start_line,
                                        )

            return None
        except Exception as e:
            logger.warning(f"Failed to extract require statement: {e}")
            return None

    def _extract_exports(self, tree: Any, source_code: bytes) -> list[str]:
        """Extract exported symbols"""
        exports = []

        def traverse(node: Any) -> None:
            """Recursively find export statements"""

            if node.type == "export_statement":
                # Get exported declaration
                declaration = node.child_by_field_name("declaration")
                if declaration:
                    name_node = declaration.child_by_field_name("name")
                    if name_node:
                        exports.append(self._get_node_text(name_node, source_code))

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return exports

    def _is_comment_line(self, line: str) -> bool:
        """Check if a line is a JavaScript comment"""
        return line.startswith("//") or line.startswith("/*") or line.startswith("*")


# Made with Bob
