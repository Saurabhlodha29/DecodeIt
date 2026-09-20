# Basic Application health check

from fastapi import APIRouter

health_router = APIRouter()


@health_router.get("/health", tags = ["health"])
async def get_health():
    
    return {"status" : "ok"}