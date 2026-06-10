"""
IBM Bob - TypeScript Language Parser
Tree-sitter based parser for TypeScript source files
"""

import logging
from typing import Any

try:
    from tree_sitter import Language, Parser
    from tree_sitter_typescript import language_typescript as typescript_language
except ImportError:
    Language = None
    Parser = None
    typescript_language = None

from bob.parsers.base import (
    CodeSymbol,
    ImportStatement,
    LanguageParser,
    SymbolType,
)

logger = logging.getLogger(__name__)


class TypeScriptParser(LanguageParser):
    """
    TypeScript language parser using Tree-sitter.

    Extracts:
    - Classes and methods
    - Functions and arrow functions
    - Interfaces and types
    - Imports and exports
    - Type annotations
    """

    @property
    def language_name(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> list[str]:
        return [".ts", ".tsx"]

    def _setup_parser(self) -> None:
        """Initialize Tree-sitter parser for TypeScript"""
        if Parser is None or typescript_language is None:
            raise ImportError(
                "tree-sitter-typescript not installed. "
                "Install with: pip install tree-sitter tree-sitter-typescript"
            )

        self._parser = Parser()
        self._language = typescript_language()
        self._parser.set_language(self._language)
        logger.debug("TypeScript parser initialized")

    def _extract_symbols(self, tree: Any, source_code: bytes) -> list[CodeSymbol]:
        """Extract classes, functions, interfaces from TypeScript AST"""
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

            # Extract interface declarations
            elif node.type == "interface_declaration":
                interface_symbol = self._extract_interface(node, source_code)
                if interface_symbol:
                    symbols.append(interface_symbol)

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

            # Extract arrow functions assigned to variables
            elif node.type == "lexical_declaration" or node.type == "variable_declaration":
                func_symbol = self._extract_arrow_function(node, source_code)
                if func_symbol:
                    symbols.append(func_symbol)

            # Extract type aliases
            elif node.type == "type_alias_declaration":
                type_symbol = self._extract_type_alias(node, source_code)
                if type_symbol:
                    symbols.append(type_symbol)

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

            # Get heritage (extends/implements)
            heritage = []
            heritage_node = node.child_by_field_name("heritage")
            if heritage_node:
                heritage_text = self._get_node_text(heritage_node, source_code)
                heritage.append(heritage_text)

            # Get modifiers (export, abstract, etc.)
            modifiers = self._extract_modifiers(node, source_code)

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
                modifiers=modifiers,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract class: {e}")
            return None

    def _extract_interface(self, node: Any, source_code: bytes) -> CodeSymbol | None:
        """Extract interface declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Get extends clause
            extends = []
            for child in node.children:
                if child.type == "extends_clause":
                    extends_text = self._get_node_text(child, source_code)
                    extends.append(extends_text)

            modifiers = self._extract_modifiers(node, source_code)

            signature = f"interface {name}"
            if extends:
                signature += f" {' '.join(extends)}"

            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=SymbolType.INTERFACE,
                file_path="",
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                signature=signature,
                docstring=None,
                parent=None,
                modifiers=modifiers,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract interface: {e}")
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

            # Get return type
            return_type = None
            return_node = node.child_by_field_name("return_type")
            if return_node:
                return_type = self._get_node_text(return_node, source_code)

            modifiers = self._extract_modifiers(node, source_code)

            # Build signature
            params_str = ", ".join(parameters)
            signature = f"function {name}({params_str})"
            if return_type:
                signature += f": {return_type}"

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
                return_type=return_type,
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

            return_type = None
            return_node = node.child_by_field_name("return_type")
            if return_node:
                return_type = self._get_node_text(return_node, source_code)

            modifiers = self._extract_modifiers(node, source_code)

            params_str = ", ".join(parameters)
            signature = f"{name}({params_str})"
            if return_type:
                signature += f": {return_type}"

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
                return_type=return_type,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract method: {e}")
            return None

    def _extract_arrow_function(
        self,
        node: Any,
        source_code: bytes,
    ) -> CodeSymbol | None:
        """Extract arrow function assigned to variable"""
        try:
            # Look for variable declarator with arrow function
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")

                    if name_node and value_node and value_node.type == "arrow_function":
                        name = self._get_node_text(name_node, source_code)
                        start_line, end_line = self._get_node_line_range(value_node)

                        parameters = self._extract_parameters(value_node, source_code)

                        return_type = None
                        return_node = value_node.child_by_field_name("return_type")
                        if return_node:
                            return_type = self._get_node_text(return_node, source_code)

                        params_str = ", ".join(parameters)
                        signature = f"const {name} = ({params_str}) =>"
                        if return_type:
                            signature += f": {return_type}"

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
                            modifiers=["arrow"],
                            parameters=parameters,
                            return_type=return_type,
                            body=body,
                        )

            return None
        except Exception as e:
            logger.warning(f"Failed to extract arrow function: {e}")
            return None

    def _extract_type_alias(self, node: Any, source_code: bytes) -> CodeSymbol | None:
        """Extract type alias declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=SymbolType.CONSTANT,  # Using CONSTANT for type aliases
                file_path="",
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                signature=body,
                docstring=None,
                parent=None,
                modifiers=["type"],
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to extract type alias: {e}")
            return None

    def _extract_parameters(self, node: Any, source_code: bytes) -> list[str]:
        """Extract function/method parameters"""
        parameters = []

        params_node = node.child_by_field_name("parameters")
        if not params_node:
            return parameters

        for child in params_node.children:
            if child.type == "required_parameter":
                param_text = self._get_node_text(child, source_code)
                parameters.append(param_text)
            elif child.type == "optional_parameter":
                param_text = self._get_node_text(child, source_code)
                parameters.append(param_text)

        return parameters

    def _extract_modifiers(self, node: Any, source_code: bytes) -> list[str]:
        """Extract modifiers (export, async, static, etc.)"""
        modifiers = []

        # Check parent for export
        if node.parent and node.parent.type == "export_statement":
            modifiers.append("export")

        # Check for other modifiers in children
        for child in node.children:
            if child.type in ("public", "private", "protected", "static", "async", "abstract"):
                modifiers.append(child.type)

        return modifiers

    def _extract_imports(self, tree: Any, source_code: bytes) -> list[ImportStatement]:
        """Extract import statements from TypeScript AST"""
        imports = []

        def traverse(node: Any) -> None:
            """Recursively find import statements"""

            if node.type == "import_statement":
                import_stmt = self._extract_import_statement(node, source_code)
                if import_stmt:
                    imports.append(import_stmt)

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return imports

    def _extract_import_statement(
        self,
        node: Any,
        source_code: bytes,
    ) -> ImportStatement | None:
        """Extract import statement"""
        try:
            module = ""
            imported_names = []

            # Get source (module path)
            source_node = node.child_by_field_name("source")
            if source_node:
                module = self._get_node_text(source_node, source_code).strip('"').strip("'")

            # Get import clause
            import_clause = node.child_by_field_name("import_clause")
            if import_clause:
                for child in import_clause.children:
                    if child.type == "identifier":
                        imported_names.append(self._get_node_text(child, source_code))
                    elif child.type == "named_imports":
                        for named_child in child.children:
                            if named_child.type == "import_specifier":
                                name_node = named_child.child_by_field_name("name")
                                if name_node:
                                    imported_names.append(
                                        self._get_node_text(name_node, source_code)
                                    )
                    elif child.type == "namespace_import":
                        for ns_child in child.children:
                            if ns_child.type == "identifier":
                                imported_names.append(self._get_node_text(ns_child, source_code))

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
        """Check if a line is a TypeScript comment"""
        return line.startswith("//") or line.startswith("/*") or line.startswith("*")


# Made with Bob
