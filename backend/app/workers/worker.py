"""
Background job worker: polls the `jobs` table and processes ingestion jobs.

Run standalone, separate from the FastAPI process:
    python -m app.workers.worker

This module is orchestration only. Each stage's real logic lives in its own
module (git_repository, source_ingestion, symbol_ingestion, graph_builder) —
worker.py just calls them in order and updates job/commit status.

Pipeline for an `ingest_repo` job:
    claim job
      -> checkout exact commit (git_repository)
      -> create/reuse commits row, status = ingesting
      -> ingest source files (source_ingestion)
      -> parse + persist symbols (symbol_ingestion)
      -> build the call/import/inherit graph (graph_builder)
      -> commits row, status = ready
      -> job succeeded
    on any failure: commits row status = failed, job retried up to max_attempts
"""

import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database import supabase
from app.graph.graph_builder import build_graph_for_commit
from app.ingestion.git_repository import checkout_commit, get_or_create_commit
from app.ingestion.source_ingestion import ingest_files
from app.ingestion.symbol_ingestion import ingest_symbols_for_commit

POLL_INTERVAL_SECONDS = 2
RETRY_COOLDOWN_SECONDS = 30


def claim_next_job():
    """
    Atomically claim the next queued job via the claim_next_job() Postgres
    function (FOR UPDATE SKIP LOCKED), so multiple worker instances can run
    without claiming the same job twice. Returns None if nothing is queued.
    """
    response = supabase.rpc("claim_next_job").execute()

    if not response.data:
        return None

    return response.data[0]


def mark_job_succeeded(job_id: str):
    supabase.table("jobs").update({
        "status": "succeeded",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "locked_at": None,
        "error": None,
    }).eq("id", job_id).execute()


def mark_job_failed(job: dict, error: str):
    """
    Requeue the job with a cooldown if attempts remain, otherwise mark it
    permanently failed. Timestamps are always sent as ISO strings — the
    Supabase client can't serialize raw datetime objects.
    """
    now = datetime.now(timezone.utc)

    attempts = job["attempts"]
    max_attempts = job["max_attempts"]

    if attempts < max_attempts:
        next_run = now + timedelta(seconds=RETRY_COOLDOWN_SECONDS)

        supabase.table("jobs").update({
            "status": "queued",
            "run_after": next_run.isoformat(),
            "locked_at": None,
            "error": error,
        }).eq("id", job["id"]).execute()

        print(
            f"Job {job['id']} failed "
            f"(attempt {attempts}/{max_attempts}). "
            f"Retrying at {next_run.isoformat()}."
        )

    else:
        supabase.table("jobs").update({
            "status": "failed",
            "finished_at": now.isoformat(),
            "locked_at": None,
            "error": error,
        }).eq("id", job["id"]).execute()

        print(
            f"Job {job['id']} permanently failed "
            f"after {attempts}/{max_attempts} attempts."
        )


def process_job(job):
    """Run one ingest_repo job end to end. Raises on failure (caller retries)."""
    commit_id = None

    try:
        payload = job["payload"]
        repo_url = payload["repo_url"]
        commit_sha = payload["commit_sha"]
        repo_id = job["repo_id"]

        print(f"Cloning {repo_url}")
        print(f"Target commit {commit_sha}")

        with tempfile.TemporaryDirectory(prefix="decodeit-") as temp_dir:
            temp_path = Path(temp_dir)

            # Fetch + verify the exact commit. A branch can move; the SHA can't,
            # so this guarantees we analyze exactly what the user selected.
            actual_sha = checkout_commit(
                repo_url=repo_url,
                commit_sha=commit_sha,
                temp_dir=str(temp_path),
            )

            print(f"Successfully checked out commit: {actual_sha}")

            commit = get_or_create_commit(repo_id=repo_id, commit_sha=actual_sha)
            commit_id = commit["id"]

            supabase.table("commits").update({
                "status": "ingesting",
                "error": None,
            }).eq("id", commit_id).execute()

            # Stage 1: persist source files from the temp checkout.
            file_count = ingest_files(repo_root=temp_path, commit_id=commit_id)
            print(f"File ingestion complete: {file_count} source files.")

            # Stage 2: parse persisted files into symbols (classes/functions/methods).
            total_symbols = ingest_symbols_for_commit(commit_id)

            # Stage 3: extract relationships (calls/imports/inherits) between symbols.
            total_edges = build_graph_for_commit(commit_id)

            print(
                f"Commit {commit_id}: "
                f"{total_symbols} symbols, "
                f"{total_edges} graph edges"
            )

            supabase.table("commits").update({
                "status": "ready",
                "error": None,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", commit_id).execute()

        print("Temporary repository deleted.")

    except Exception as exc:
        # A commit row that exists but never reached "ready" must be marked
        # failed, so it doesn't sit forever looking like it's still ingesting.
        if commit_id is not None:
            supabase.table("commits").update({
                "status": "failed",
                "error": str(exc),
            }).eq("id", commit_id).execute()

        raise


def worker_loop():
    """Poll forever: claim a job, process it, mark success/failure, repeat."""
    print("DecodeIt worker started.")

    while True:
        job = claim_next_job()

        if job is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        try:
            process_job(job)
            mark_job_succeeded(job["id"])

        except Exception as exc:
            print(f"Job {job['id']} raised an exception: {exc}")
            mark_job_failed(job, str(exc))


if __name__ == "__main__":
    worker_loop()
