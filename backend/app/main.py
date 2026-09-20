from fastapi import FastAPI
from app.api.routes.health import health_router
from app.api.routes.repos import repos_router

app = FastAPI(
    title="DecodeIt",
    description="AI-powered legacy codebase understanding system",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(repos_router)