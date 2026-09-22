"""
Git operations for the ingestion pipeline: fetching one exact commit into a
temporary directory, verifying it, and creating/reusing its `commits` row.

Nothing here parses source or touches `files`/`symbols` — this module's only
job is "get the exact requested commit onto disk and record that it exists".
"""

from app.database import supabase


def run_git_command(args: list[str], cwd: str | None = None) -> str:
    """Run a git subcommand and return its stdout, raising on failure."""
    import subprocess

    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Git command failed: {' '.join(args)}\n"
            f"{result.stderr.strip()}"
        )

    return result.stdout.strip()


def checkout_commit(repo_url: str, commit_sha: str, temp_dir: str) -> str:
    """
    Fetch and check out exactly one commit into temp_dir, without cloning
    the repo's full history (`--depth 1`).

    Verifies that the commit actually checked out matches commit_sha, since
    a branch name or short SHA could otherwise silently resolve to something
    else. Raises RuntimeError if they don't match.

    Returns the verified full commit SHA.
    """

    run_git_command(["init"], cwd=temp_dir)

    run_git_command(
        ["remote", "add", "origin", repo_url],
        cwd=temp_dir,
    )

    run_git_command(
        ["fetch", "--depth", "1", "origin", commit_sha],
        cwd=temp_dir,
    )

    run_git_command(
        ["checkout", "--detach", commit_sha],
        cwd=temp_dir,
    )

    actual_sha = run_git_command(["rev-parse", "HEAD"], cwd=temp_dir)

    if actual_sha != commit_sha:
        raise RuntimeError(
            f"Commit verification failed. "
            f"Expected {commit_sha}, got {actual_sha}"
        )

    return actual_sha


def get_or_create_commit(repo_id: str, commit_sha: str) -> dict:
    """
    Return the existing `commits` row for (repo_id, commit_sha) if one
    exists, otherwise create it.

    This makes ingestion idempotent: retrying a job for a commit that was
    already fetched reuses the same commit row instead of duplicating it.
    """
    existing_commit = (
        supabase
        .table("commits")
        .select("id, commit_sha, status")
        .eq("repo_id", repo_id)
        .eq("commit_sha", commit_sha)
        .limit(1)
        .execute()
    )

    if existing_commit.data:
        commit = existing_commit.data[0]
        print(f"Commit record already exists: {commit['id']}")
        return commit

    response = (
        supabase
        .table("commits")
        .insert({
            "repo_id": repo_id,
            "commit_sha": commit_sha,
        })
        .execute()
    )

    if not response.data:
        raise RuntimeError("Failed to create commit record.")

    commit = response.data[0]
    print(f"Created commit record: {commit['id']}")
    return commit
