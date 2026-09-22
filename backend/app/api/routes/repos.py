"""
/repos endpoints: create a repo + ingest_repo job for the authenticated
user, and list that user's own repos. Uses the Supabase secret key
(bypasses RLS) but scopes every query explicitly by user_id from
get_current_user_id, so ownership is still enforced in application code.
"""

from pydantic import BaseModel, HttpUrl
from fastapi import APIRouter, Depends, HTTPException

from app.database import supabase
from app.auth import get_current_user_id


repos_router = APIRouter(
    prefix="/repos",
    tags=["Repositories"],
)


class CreateRepoRequest(BaseModel):
    url: HttpUrl
    name: str
    language: str
    default_branch: str = "main"
    commit_sha: str


@repos_router.get("/")
def get_repositories(
    user_id: str = Depends(get_current_user_id),
):
    response = (
        supabase
        .table("repos")
        .select("*")
        .eq("owner_id", user_id)
        .execute()
    )

    return response.data


@repos_router.post("/")
def create_repository(
    repo: CreateRepoRequest,
    user_id: str = Depends(get_current_user_id),
):
    response = (
        supabase
        .table("repos")
        .insert({
            "owner_id": user_id,
            "url": str(repo.url),
            "name": repo.name,
            "language": repo.language,
            "default_branch": repo.default_branch,
        })
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to create repository",
        )

    created_repo = response.data[0]

    job_response = (
        supabase
        .table("jobs")
        .insert({
            "type": "ingest_repo",
            "payload": {
                "repo_url": str(repo.url),
                "commit_sha": repo.commit_sha,
            },
            "repo_id": created_repo["id"],
            "created_by": user_id,
        })
        .execute()
    )

    if not job_response.data:
        raise HTTPException(
            status_code=500,
            detail="Repository created but ingestion job could not be created",
        )

    return {
        "repo": created_repo,
        "job": job_response.data[0],
    }