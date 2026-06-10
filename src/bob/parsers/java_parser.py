"""
IBM Bob - Java Language Parser
Tree-sitter based parser for Java source files
"""

import logging
from typing import Any

try:
    from tree_sitter import Language, Parser
    from tree_sitter_java import language as java_language
except ImportError:
    Language = None
    Parser = None
    java_language = None

from bob.parsers.base import (
    CodeSymbol,
    ImportStatement,
    LanguageParser,
    SymbolType,
)

logger = logging.getLogger(__name__)


class JavaParser(LanguageParser):
    """
    Java language parser using Tree-sitter.

    Extracts:
    - Classes and inner classes
    - Methods
    - Interfaces
    - Enums
    - Imports
    - Annotations
    """

    @property
    def language_name(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> list[str]:
        return [".java"]

    def _setup_parser(self) -> None:
        """Initialize Tree-sitter parser for Java"""
        if Parser is None or java_language is None:
            raise ImportError(
                "tree-sitter-java not installed. "
                "Install with: pip install tree-sitter tree-sitter-java"
            )

        self._parser = Parser()
        self._language = java_language()
        self._parser.set_language(self._language)
        logger.debug("Java parser initialized")

    def _extract_symbols(self, tree: Any, source_code: bytes) -> list[CodeSymbol]:
        """Extract classes, methods, interfaces from Java AST"""
        symbols = []

        def traverse(node: Any, parent_class: str | None = None) -> None:
            """Recursively traverse AST and extract symbols"""

            # Extract class declarations
            if node.type == "class_declaration":
                class_symbol = self._extract_class(node, source_code, parent_class)
                if class_symbol:
                    symbols.append(class_symbol)
                    # Traverse class body for methods and inner classes
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            traverse(child, class_symbol.name)

            # Extract interface declarations
            elif node.type == "interface_declaration":
                interface_symbol = self._extract_interface(node, source_code)
                if interface_symbol:
                    symbols.append(interface_symbol)
                    # Traverse interface body
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            traverse(child, interface_symbol.name)

            # Extract enum declarations
            elif node.type == "enum_declaration":
                enum_symbol = self._extract_enum(node, source_code)
                if enum_symbol:
                    symbols.append(enum_symbol)

            # Extract method declarations
            elif node.type == "method_declaration":
                method_symbol = self._extract_method(node, source_code, parent_class)
                if method_symbol:
                    symbols.append(method_symbol)

            # Extract constructor declarations
            elif node.type == "constructor_declaration":
                constructor_symbol = self._extract_constructor(node, source_code, parent_class)
                if constructor_symbol:
                    symbols.append(constructor_symbol)

            # Continue traversing for top-level definitions
            elif parent_class is None:
                for child in node.children:
                    traverse(child, parent_class)

        traverse(tree.root_node)
        return symbols

    def _extract_class(
        self,
        node: Any,
        source_code: bytes,
        parent_class: str | None = None,
    ) -> CodeSymbol | None:
        """Extract class declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            # Get modifiers (public, private, static, abstract, etc.)
            modifiers = self._extract_modifiers(node, source_code)

            # Get superclass
            superclass = None
            superclass_node = node.child_by_field_name("superclass")
            if superclass_node:
                superclass = self._get_node_text(superclass_node, source_code)

            # Get interfaces
            interfaces = []
            interfaces_node = node.child_by_field_name("interfaces")
            if interfaces_node:
                interfaces_text = self._get_node_text(interfaces_node, source_code)
                interfaces.append(interfaces_text)

            # Build signature
            mods_str = " ".join(modifiers) if modifiers else ""
            signature = f"{mods_str} class {name}".strip()
            if superclass:
                signature += f" extends {superclass}"
            if interfaces:
                signature += f" {' '.join(interfaces)}"

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
                parent=parent_class,
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

            modifiers = self._extract_modifiers(node, source_code)

            # Get extends clause
            extends = []
            extends_node = node.child_by_field_name("extends")
            if extends_node:
                extends_text = self._get_node_text(extends_node, source_code)
                extends.append(extends_text)

            mods_str = " ".join(modifiers) if modifiers else ""
            signature = f"{mods_str} interface {name}".strip()
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

    def _extract_enum(self, node: Any, source_code: bytes) -> CodeSymbol | None:
        """Extract enum declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            modifiers = self._extract_modifiers(node, source_code)

            mods_str = " ".join(modifiers) if modifiers else ""
            signature = f"{mods_str} enum {name}".strip()

            body = self._get_node_text(node, source_code)

            return CodeSymbol(
                name=name,
                symbol_type=SymbolType.ENUM,
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
            logger.warning(f"Failed to extract enum: {e}")
            return None

    def _extract_method(
        self,
        node: Any,
        source_code: bytes,
        parent_class: str | None = None,
    ) -> CodeSymbol | None:
        """Extract method declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            modifiers = self._extract_modifiers(node, source_code)

            # Get return type
            return_type = None
            type_node = node.child_by_field_name("type")
            if type_node:
                return_type = self._get_node_text(type_node, source_code)

            # Get parameters
            parameters = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                parameters = self._extract_parameters(params_node, source_code)

            # Build signature
            mods_str = " ".join(modifiers) if modifiers else ""
            params_str = ", ".join(parameters)
            signature = f"{mods_str} {return_type or 'void'} {name}({params_str})".strip()

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

    def _extract_constructor(
        self,
        node: Any,
        source_code: bytes,
        parent_class: str | None = None,
    ) -> CodeSymbol | None:
        """Extract constructor declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node, source_code)
            start_line, end_line = self._get_node_line_range(node)

            modifiers = self._extract_modifiers(node, source_code)
            modifiers.append("constructor")

            # Get parameters
            parameters = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                parameters = self._extract_parameters(params_node, source_code)

            # Build signature
            mods_str = " ".join([m for m in modifiers if m != "constructor"])
            params_str = ", ".join(parameters)
            signature = f"{mods_str} {name}({params_str})".strip()

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
            logger.warning(f"Failed to extract constructor: {e}")
            return None

    def _extract_parameters(self, params_node: Any, source_code: bytes) -> list[str]:
        """Extract method parameters"""
        parameters = []

        for child in params_node.children:
            if child.type == "formal_parameter":
                param_text = self._get_node_text(child, source_code)
                parameters.append(param_text)
            elif child.type == "spread_parameter":
                param_text = self._get_node_text(child, source_code)
                parameters.append(param_text)

        return parameters

    def _extract_modifiers(self, node: Any, source_code: bytes) -> list[str]:
        """Extract modifiers (public, private, static, etc.)"""
        modifiers = []

        for child in node.children:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type in (
                        "public",
                        "private",
                        "protected",
                        "static",
                        "final",
                        "abstract",
                        "synchronized",
                        "native",
                        "strictfp",
                        "transient",
                        "volatile",
                    ):
                        modifiers.append(mod_child.type)
                    elif mod_child.type == "marker_annotation":
                        # Include annotations as modifiers
                        annotation_text = self._get_node_text(mod_child, source_code)
                        modifiers.append(annotation_text)

        return modifiers

    def _extract_imports(self, tree: Any, source_code: bytes) -> list[ImportStatement]:
        """Extract import statements from Java AST"""
        imports = []

        def traverse(node: Any) -> None:
            """Recursively find import statements"""

            if node.type == "import_declaration":
                import_stmt = self._extract_import_declaration(node, source_code)
                if import_stmt:
                    imports.append(import_stmt)

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return imports

    def _extract_import_declaration(
        self,
        node: Any,
        source_code: bytes,
    ) -> ImportStatement | None:
        """Extract import declaration"""
        try:
            # Get the full import text
            import_text = self._get_node_text(node, source_code)

            # Check for static import

            # Check for wildcard import
            is_wildcard = "*" in import_text

            # Extract module path
            module = ""
            for child in node.children:
                if child.type == "scoped_identifier" or child.type == "identifier":
                    module = self._get_node_text(child, source_code)
                    break

            if not module:
                return None

            # Extract imported names
            imported_names = []
            if is_wildcard:
                imported_names.append("*")
            else:
                # Get the last part of the module path as the imported name
                imported_names.append(module.split(".")[-1])

            start_line, _ = self._get_node_line_range(node)

            return ImportStatement(
                module=module,
                imported_names=imported_names,
                alias=None,
                is_relative=False,
                line_number=start_line,
            )
        except Exception as e:
            logger.warning(f"Failed to extract import declaration: {e}")
            return None

    def _is_comment_line(self, line: str) -> bool:
        """Check if a line is a Java comment"""
        return line.startswith("//") or line.startswith("/*") or line.startswith("*")


# Made with Bob
