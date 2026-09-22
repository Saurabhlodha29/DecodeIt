"""
Turns parsed symbols (from source_parser.py) into rows in the `symbols` table.

This is the persistence half of the parsing pipeline:
    source code -> source_parser.parse_source() -> ParsedSymbol list -> [this module] -> symbols table

Kept separate from source_parser.py so parsing stays pure (no DB access) and
persistence stays swappable.
"""

from __future__ import annotations

from app.database import supabase
from app.ingestion.source_parser import parse_source


def ingest_symbols_for_file(
    commit_id: str,
    file_record: dict,
) -> int:
    """
    Parse one stored source file and insert its symbols.

    Symbols are inserted in parse order (parents before their children),
    so a child's parent_symbol_id can always be resolved from symbol_ids,
    a list built up as we go where symbol_ids[i] is the DB id of the
    i-th parsed symbol.

    Returns the number of symbols inserted (0 if this file was already
    processed for this commit, to keep retries idempotent).
    """

    file_id = file_record["id"]
    source = file_record["content"]
    language = file_record["language"]

    parsed_symbols = parse_source(
        source=source,
        language=language,
    )

    # Prevent duplicate symbols when the same ingestion job is retried.
    existing = (
        supabase
        .table("symbols")
        .select("id")
        .eq("commit_id", commit_id)
        .eq("file_id", file_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        return 0

    inserted_count = 0
    symbol_ids: list[str] = []

    for symbol in parsed_symbols:
        # Top-level symbols have no parent; only look one up when there is one.
        parent_symbol_id = None
        if symbol.parent_index is not None:
            parent_symbol_id = symbol_ids[symbol.parent_index]

        response = (
            supabase
            .table("symbols")
            .insert({
                "commit_id": commit_id,
                "file_id": file_id,
                "parent_symbol_id": parent_symbol_id,
                "kind": symbol.kind,
                "name": symbol.name,
                "qualified_name": symbol.qualified_name,
                "signature": symbol.signature,
                "docstring": symbol.docstring,
                "start_line": symbol.start_line,
                "end_line": symbol.end_line,
                "code_hash": symbol.code_hash,
            })
            .execute()
        )

        if not response.data:
            file_path = file_record["path"]
            raise RuntimeError(
                f"Failed to insert symbol '{symbol.qualified_name}' "
                f"for file '{file_path}'"
            )

        symbol_ids.append(response.data[0]["id"])
        inserted_count += 1

    return inserted_count


def ingest_symbols_for_commit(commit_id: str) -> int:
    """
    Parse every stored source file belonging to a commit and insert their symbols.

    Reads from the already-persisted `files` rows (not the temp Git checkout),
    so this stage can be re-run independently of the Git/clone stage.
    """

    response = (
        supabase
        .table("files")
        .select("*")
        .eq("commit_id", commit_id)
        .execute()
    )

    files = response.data or []

    total_symbols = 0

    for file_record in files:
        total_symbols += ingest_symbols_for_file(
            commit_id=commit_id,
            file_record=file_record,
        )

    return total_symbols
