# Responsible for fetching all the API keys from .env and loading them with their keywords

import os
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")

# Which NVIDIA NIM model the LLM gateway uses. Change it in .env without touching code.
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "openai/gpt-oss-20b")

# Fail early, with one clear message, if a required setting is missing.
_REQUIRED = {
    "NVIDIA_API_KEY": NVIDIA_API_KEY,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SECRET_KEY": SUPABASE_SECRET_KEY,
    "VOYAGE_API_KEY": VOYAGE_API_KEY,
}

_missing = [name for name, value in _REQUIRED.items() if not value]
if _missing:
    raise RuntimeError(
        "Missing required environment variables: "
        + ", ".join(_missing)
        + ". Copy .env.example to .env and fill them in."
    )
    
# Origins allowed to call the API from a browser. Comma-separated in .env.
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]