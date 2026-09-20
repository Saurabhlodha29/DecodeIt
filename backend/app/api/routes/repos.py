from app.database import supabase
from fastapi import APIRouter


repos_router = APIRouter(
    prefix = "/repos",
    tags = ["Repositories"]
)

@repos_router.get("/")
def get_repositories():
    response = supabase.table("repos").select("*").execute()
    
    return response.data