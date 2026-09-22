"""
Parses one source file's text into a flat list of ParsedSymbol records
(classes, functions, methods) using tree-sitter. Pure parsing only — no
database access here; symbol_ingestion.py handles persistence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from tree_sitter import Language, Parser
import tree_sitter_java
import tree_sitter_python

JAVA_LANGUAGE = Language(tree_sitter_java.language())
PYTHON_LANGUAGE = Language(tree_sitter_python.language())

@dataclass
class ParsedSymbol:
    kind: str
    name: str
    qualified_name: str
    signature: Optional[str]
    docstring: Optional[str]
    start_line: int
    end_line: int
    code_hash: str
    parent_index: Optional[int] = None
    
def _create_parser(language: str) -> Parser:
    parser = Parser()
    
    if language == "java":
        parser.language = JAVA_LANGUAGE
    elif language == "python":
        parser.language = PYTHON_LANGUAGE
    else:
        raise ValueError(f"Unsupported language : {language}")    
    
    return parser

def _node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode(
        "utf-8",
        errors = "replace",
    )
    
def _code_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _signature(text: str) -> str:
    """
    Extract a useful declaration signature without the implementation body.
    """
    
    # Java
    brace_index = text.find("{")
    if brace_index != -1:
        text = text[:brace_index]
        
    # Python
    colon_index = text.find(":")
    if colon_index != -1:
        text = text[:colon_index]
        
    return " ".join(text.strip().split())

def _python_docstring(source: bytes, node) -> Optional[str]:
    body = node.child_by_field_name("body")

    if body is None or not body.children:
        return None

    first_statement = body.children[0]

    if first_statement.type != "expression_statement":
        return None

    if not first_statement.children:
        return None

    expression = first_statement.children[0]

    if expression.type != "string":
        return None

    return _node_text(source, expression).strip()

def _symbol_definition(node, language: str):
    if language == "java":
        mapping = {
            "class_declaration": "class",
            "interface_declaration": "class",
            "enum_declaration": "class",
            "method_declaration": "method",
            "constructor_declaration": "method",
        }
        return mapping.get(node.type)

    if language == "python":
        mapping = {
            "class_definition": "class",
            "function_definition": "function",
        }
        return mapping.get(node.type)

    return None

def parse_source(
    source: str,
    language: str,
) -> list[ParsedSymbol]:
    """
    Parse one source file and return its symbols.

    parent_index refers to another ParsedSymbol in the returned list.
    This lets symbol_ingestion.py resolve parent_symbol_id after insertion.
    """

    source_bytes = source.encode("utf-8")

    parser = _create_parser(language)
    tree = parser.parse(source_bytes)

    symbols: list[ParsedSymbol] = []

    def visit(node, parent_index: Optional[int] = None):
        kind = _symbol_definition(node, language)

        current_parent_index = parent_index

        if kind is not None:
            name_node = node.child_by_field_name("name")

            if name_node is not None:
                name = _node_text(source_bytes, name_node).strip()

                if parent_index is not None:
                    parent_qualified_name = symbols[parent_index].qualified_name
                    qualified_name = f"{parent_qualified_name}.{name}"
                else:
                    qualified_name = name

                node_text = _node_text(source_bytes, node)

                if language == "python":
                    docstring = _python_docstring(source_bytes, node)
                else:
                    docstring = None

                symbol = ParsedSymbol(
                    kind=kind,
                    name=name,
                    qualified_name=qualified_name,
                    signature=_signature(node_text),
                    docstring=docstring,
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    code_hash=_code_hash(node_text),
                    parent_index=parent_index,
                )

                symbols.append(symbol)
                current_parent_index = len(symbols) - 1

        for child in node.children:
            visit(child, current_parent_index)

    visit(tree.root_node)

    return symbols