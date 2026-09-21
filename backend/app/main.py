from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import CORS_ORIGINS
from app.api.routes.health import health_router
from app.api.routes.repos import repos_router

app = FastAPI(
    title="DecodeIt",
    description="AI-powered legacy codebase understanding system",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins = CORS_ORIGINS,
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],    # needed for the Authorization: Bearer <supabase JWT> header
)

app.include_router(health_router)
app.include_router(repos_router)