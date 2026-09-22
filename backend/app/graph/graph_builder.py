"""
Builds the code relationship graph for one commit: reads the symbols and
files already persisted for that commit, re-parses each file with
tree-sitter to find calls/imports/inheritance, and writes the resulting
relationships into `code_edges`.

Resolution is intentionally pragmatic, not compiler-grade: when a call or
superclass name can be matched to a known symbol, the edge is "resolved"
(dst_symbol_id set, higher confidence); otherwise it's stored unresolved
(dst_symbol_id null, dst_name holds the raw name, lower confidence). This
keeps the graph useful without a full type-aware static analyzer.
"reads"/"writes" edges and file/module-level symbols are deliberately out
of scope for now (see code_edges.edge_type and the imports note below).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tree_sitter import Language, Parser
import tree_sitter_java
import tree_sitter_python

from app.database import supabase


JAVA_LANGUAGE = Language(tree_sitter_java.language())
PYTHON_LANGUAGE = Language(tree_sitter_python.language())


@dataclass
class SymbolRecord:
    id: str
    file_id: Optional[str]
    kind: str
    name: str
    qualified_name: str
    start_line: Optional[int]
    end_line: Optional[int]


@dataclass
class ExtractedEdge:
    src_symbol_id: str
    dst_symbol_id: Optional[str]
    dst_name: Optional[str]
    edge_type: str
    confidence: float
    line: Optional[int]


def _create_parser(language: str) -> Parser:
    parser = Parser()

    if language == "java":
        parser.language = JAVA_LANGUAGE
    elif language == "python":
        parser.language = PYTHON_LANGUAGE
    else:
        raise ValueError(f"Unsupported language: {language}")

    return parser


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode(
        "utf-8",
        errors="replace",
    )


def _load_symbols(commit_id: str) -> list[SymbolRecord]:
    response = (
        supabase
        .table("symbols")
        .select(
            "id,file_id,kind,name,qualified_name,start_line,end_line"
        )
        .eq("commit_id", commit_id)
        .execute()
    )

    return [
        SymbolRecord(
            id=row["id"],
            file_id=row["file_id"],
            kind=row["kind"],
            name=row["name"],
            qualified_name=row["qualified_name"],
            start_line=row["start_line"],
            end_line=row["end_line"],
        )
        for row in (response.data or [])
    ]


def _load_files(commit_id: str) -> list[dict]:
    response = (
        supabase
        .table("files")
        .select("id,path,language,content")
        .eq("commit_id", commit_id)
        .execute()
    )

    return response.data or []


def _symbol_index(
    symbols: list[SymbolRecord],
) -> dict[str, list[SymbolRecord]]:
    index: dict[str, list[SymbolRecord]] = {}

    for symbol in symbols:
        index.setdefault(symbol.name, []).append(symbol)

    return index


def _symbols_for_file(
    symbols: list[SymbolRecord],
    file_id: str,
) -> list[SymbolRecord]:
    return [
        symbol
        for symbol in symbols
        if symbol.file_id == file_id
    ]


def _containing_symbol(
    symbols: list[SymbolRecord],
    line: int,
) -> Optional[SymbolRecord]:
    candidates = [
        symbol
        for symbol in symbols
        if symbol.start_line is not None
        and symbol.end_line is not None
        and symbol.start_line <= line <= symbol.end_line
    ]

    if not candidates:
        return None

    # Smallest containing range = most specific symbol.
    return min(
        candidates,
        key=lambda symbol: symbol.end_line - symbol.start_line,
    )


def _extract_inheritance_edges(
    source: str,
    language: str,
    file_symbols: list[SymbolRecord],
) -> list[ExtractedEdge]:
    source_bytes = source.encode("utf-8")
    parser = _create_parser(language)
    tree = parser.parse(source_bytes)

    edges: list[ExtractedEdge] = []

    def visit(node):
        if language == "java":
            if node.type == "class_declaration":
                class_name_node = node.child_by_field_name("name")
                superclass_node = node.child_by_field_name("superclass")

                if class_name_node and superclass_node:
                    class_name = _node_text(
                        source_bytes,
                        class_name_node,
                    ).strip()

                    parent_name = _node_text(
                        source_bytes,
                        superclass_node,
                    ).strip()

                    src_symbol = next(
                        (
                            symbol
                            for symbol in file_symbols
                            if symbol.name == class_name
                            and symbol.kind == "class"
                        ),
                        None,
                    )

                    if src_symbol:
                        edges.append(
                            ExtractedEdge(
                                src_symbol_id=src_symbol.id,
                                dst_symbol_id=None,
                                dst_name=parent_name,
                                edge_type="inherits",
                                confidence=0.95,
                                line=node.start_point.row + 1,
                            )
                        )

        elif language == "python":
            if node.type == "class_definition":
                class_name_node = node.child_by_field_name("name")
                body_node = node.child_by_field_name("body")

                if class_name_node and body_node:
                    class_name = _node_text(
                        source_bytes,
                        class_name_node,
                    ).strip()

                    src_symbol = next(
                        (
                            symbol
                            for symbol in file_symbols
                            if symbol.name == class_name
                            and symbol.kind == "class"
                        ),
                        None,
                    )

                    if src_symbol:
                        for child in node.children:
                            if child.type == "argument_list":
                                for argument in child.children:
                                    if argument.type in {
                                        "identifier",
                                        "attribute",
                                    }:
                                        parent_name = _node_text(
                                            source_bytes,
                                            argument,
                                        ).strip()

                                        edges.append(
                                            ExtractedEdge(
                                                src_symbol_id=src_symbol.id,
                                                dst_symbol_id=None,
                                                dst_name=parent_name,
                                                edge_type="inherits",
                                                confidence=0.95,
                                                line=node.start_point.row + 1,
                                            )
                                        )

        for child in node.children:
            visit(child)

    visit(tree.root_node)

    return edges


def _extract_call_edges(
    source: str,
    language: str,
    file_symbols: list[SymbolRecord],
    symbols_by_name: dict[str, list[SymbolRecord]],
) -> list[ExtractedEdge]:
    source_bytes = source.encode("utf-8")
    parser = _create_parser(language)
    tree = parser.parse(source_bytes)

    edges: list[ExtractedEdge] = []

    def visit(node):
        if language == "java":
            call_node_types = {
                "method_invocation",
                "object_creation_expression",
            }
        else:
            call_node_types = {
                "call",
            }

        if node.type in call_node_types:
            caller = _containing_symbol(
                file_symbols,
                node.start_point.row + 1,
            )

            if caller is not None:
                target_name = None

                if language == "java":
                    name_node = node.child_by_field_name("name")

                    if name_node:
                        target_name = _node_text(
                            source_bytes,
                            name_node,
                        ).strip()

                    if target_name is None:
                        target_name = _node_text(
                            source_bytes,
                            node,
                        ).split("(")[0].split(".")[-1].strip()

                elif language == "python":
                    function_node = node.child_by_field_name(
                        "function"
                    )

                    if function_node:
                        target_name = _node_text(
                            source_bytes,
                            function_node,
                        ).strip()

                        target_name = target_name.split(".")[-1]

                if target_name:
                    candidates = symbols_by_name.get(
                        target_name,
                        [],
                    )

                    # Prefer methods/functions over classes.
                    candidates = [
                        symbol
                        for symbol in candidates
                        if symbol.kind in {
                            "function",
                            "method",
                        }
                    ]

                    destination = None

                    # Prefer a destination in the same file.
                    same_file = [
                        symbol
                        for symbol in candidates
                        if symbol.file_id == caller.file_id
                    ]

                    if same_file:
                        destination = same_file[0]
                    elif candidates:
                        destination = candidates[0]

                    edges.append(
                        ExtractedEdge(
                            src_symbol_id=caller.id,
                            dst_symbol_id=(
                                destination.id
                                if destination
                                else None
                            ),
                            dst_name=target_name,
                            edge_type="calls",
                            confidence=(
                                0.90
                                if destination
                                else 0.55
                            ),
                            line=node.start_point.row + 1,
                        )
                    )

        for child in node.children:
            visit(child)

    visit(tree.root_node)

    return edges


def _extract_import_edges(
    source: str,
    language: str,
    file_symbols: list[SymbolRecord],
) -> list[ExtractedEdge]:
    """
    Imports are currently stored as unresolved graph edges.

    code_edges requires src_symbol_id, while the schema has no file-level
    source node. Therefore module-level imports are attached to the first
    top-level symbol in the file when one exists.

    dst_symbol_id remains null and dst_name contains the imported target.
    """

    source_bytes = source.encode("utf-8")
    parser = _create_parser(language)
    tree = parser.parse(source_bytes)

    edges: list[ExtractedEdge] = []

    top_level_symbols = [
        symbol
        for symbol in file_symbols
        if symbol.start_line is not None
    ]

    if not top_level_symbols:
        return edges

    source_symbol = min(
        top_level_symbols,
        key=lambda symbol: symbol.start_line,
    )

    def visit(node):
        is_import = False

        if language == "java":
            is_import = node.type == "import_declaration"
        elif language == "python":
            is_import = node.type in {
                "import_statement",
                "import_from_statement",
            }

        if is_import:
            imported_name = _node_text(
                source_bytes,
                node,
            ).strip()

            edges.append(
                ExtractedEdge(
                    src_symbol_id=source_symbol.id,
                    dst_symbol_id=None,
                    dst_name=imported_name,
                    edge_type="imports",
                    confidence=0.95,
                    line=node.start_point.row + 1,
                )
            )

        for child in node.children:
            visit(child)

    visit(tree.root_node)

    return edges


def _deduplicate_edges(
    edges: list[ExtractedEdge],
) -> list[ExtractedEdge]:
    seen = set()
    result = []

    for edge in edges:
        key = (
            edge.src_symbol_id,
            edge.dst_symbol_id,
            edge.dst_name,
            edge.edge_type,
            edge.line,
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(edge)

    return result


def build_graph_for_commit(commit_id: str) -> int:
    symbols = _load_symbols(commit_id)
    files = _load_files(commit_id)

    if not symbols:
        return 0

    symbols_by_name = _symbol_index(symbols)

    all_edges: list[ExtractedEdge] = []

    for file_record in files:
        file_symbols = _symbols_for_file(
            symbols,
            file_record["id"],
        )

        if not file_symbols:
            continue

        source = file_record["content"]
        language = file_record["language"]

        all_edges.extend(
            _extract_inheritance_edges(
                source,
                language,
                file_symbols,
            )
        )

        all_edges.extend(
            _extract_call_edges(
                source,
                language,
                file_symbols,
                symbols_by_name,
            )
        )

        all_edges.extend(
            _extract_import_edges(
                source,
                language,
                file_symbols,
            )
        )

    all_edges = _deduplicate_edges(all_edges)

    if not all_edges:
        return 0

    # Idempotency for worker retries.
    existing = (
        supabase
        .table("code_edges")
        .select("id")
        .eq("commit_id", commit_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        return 0

    rows = [
        {
            "commit_id": commit_id,
            "src_symbol_id": edge.src_symbol_id,
            "dst_symbol_id": edge.dst_symbol_id,
            "dst_name": edge.dst_name,
            "edge_type": edge.edge_type,
            "confidence": edge.confidence,
            "line": edge.line,
        }
        for edge in all_edges
    ]

    # Insert in batches to avoid oversized requests.
    batch_size = 100

    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]

        response = (
            supabase
            .table("code_edges")
            .insert(batch)
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                f"Failed to insert graph edges "
                f"for commit {commit_id}"
            )

    return len(rows)