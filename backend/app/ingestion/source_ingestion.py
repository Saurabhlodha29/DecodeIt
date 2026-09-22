"""
Walks a checked-out repo on disk and persists its Python/Java source files
into the `files` table for a commit: filters out build/dependency/binary
noise, hashes and reads each accepted file, and inserts the new ones.
"""

import hashlib
from pathlib import Path
from app.database import supabase


MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024  # 1 MB

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".java": "java",
}

SKIP_DIRECTORIES = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "target",
    "build",
    "dist",
    "out",
    "bin",
}

BINARY_EXTENSIONS = {
    ".class",
    ".jar",
    ".war",
    ".zip",
    ".tar",
    ".gz",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pyc",
}


def should_skip_directory(directory_name: str) -> bool:
    return directory_name in SKIP_DIRECTORIES

def is_binary_file(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            sample = file.read(8192)
    except OSError:
        return True

    return b"\x00" in sample

def read_source_file(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8",
            errors="strict",
        )
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"File is not valid UTF-8: {path}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Could not read file: {path}"
        ) from exc
        
        
def build_file_record(
    path: Path,
    repo_root: Path,
    commit_id: str,
    language: str,
) -> dict | None:

    try:
        file_size = path.stat().st_size
    except OSError:
        print(f"Skipping unreadable file: {path}")
        return None

    if file_size > MAX_FILE_SIZE_BYTES:
        print(
            f"Skipping oversized file: "
            f"{path.relative_to(repo_root)} "
            f"({file_size} bytes)"
        )
        return None

    if path.suffix.lower() in BINARY_EXTENSIONS:
        print(
            f"Skipping binary file: "
            f"{path.relative_to(repo_root)}"
        )
        return None

    if is_binary_file(path):
        print(
            f"Skipping binary file: "
            f"{path.relative_to(repo_root)}"
        )
        return None

    try:
        content = read_source_file(path)
    except (ValueError, RuntimeError) as exc:
        print(f"Skipping file: {exc}")
        return None

    content_hash = hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()

    line_count = len(content.splitlines())

    relative_path = path.relative_to(repo_root).as_posix()

    return {
        "commit_id": commit_id,
        "path": relative_path,
        "language": language,
        "content": content,
        "content_hash": content_hash,
        "line_count": line_count,
    }


def collect_source_files(
    repo_root: Path,
    commit_id: str,
) -> list[dict]:

    records = []

    for path in repo_root.rglob("*"):

        if not path.is_file():
            continue

        relative_parts = path.relative_to(repo_root).parts

        if any(
            should_skip_directory(part)
            for part in relative_parts[:-1]
        ):
            continue

        extension = path.suffix.lower()

        language = SUPPORTED_EXTENSIONS.get(extension)

        if language is None:
            continue

        record = build_file_record(
            path=path,
            repo_root=repo_root,
            commit_id=commit_id,
            language=language,
        )

        if record is not None:
            records.append(record)

    return records


def ingest_files(repo_root: Path, commit_id: str) -> int:
    records = collect_source_files(
        repo_root=repo_root,
        commit_id=commit_id,
    )

    print(f"Collected {len(records)} source files.")

    if not records:
        raise RuntimeError(
            "No supported Python or Java source files were found."
        )

    existing_response = (
        supabase
        .table("files")
        .select("path")
        .eq("commit_id", commit_id)
        .execute()
    )

    existing_paths = {
        row["path"]
        for row in existing_response.data
    }

    records_to_insert = [
        record
        for record in records
        if record["path"] not in existing_paths
    ]

    if not records_to_insert:
        print("All source files are already ingested.")
        return len(records)

    response = (
        supabase
        .table("files")
        .insert(records_to_insert)
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Failed to insert source files."
        )

    print(
        f"Inserted {len(response.data)} source files "
        f"into the database."
    )

    return len(records)