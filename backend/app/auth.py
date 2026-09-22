"""
FastAPI dependency that resolves the Supabase-authenticated user from the
request's Bearer token. Routes use this instead of trusting a client-
supplied user id, so ownership checks (.eq("owner_id", user_id)) are based
on a verified identity.
"""

from fastapi import Header, HTTPException
from supabase import create_client, Client

from app.config import SUPABASE_URL, SUPABASE_SECRET_KEY

def get_current_user_id(authorization : str | None = Header(default = None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code = 401,
            detail = "Missing Authorization header"
        )
        
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code = 401,
            detail = "Invalid Authorization header"
        )
        
    token = authorization.removeprefix("Bearer ").strip()
    
    if not token:
        raise HTTPException(
            status_code = 401,
            detail = "Missing Bearer token"
        )
    
    try:
        client : Client = create_client(
            SUPABASE_URL,
            SUPABASE_SECRET_KEY
        )
        
        response = client.auth.get_user(token)
        
        if response.user is None:
            raise HTTPException(
                status_code = 401,
                detail = "Invalid or Expired token"
            )
            
        return response.user.id
    
    except HTTPException:
        raise
    
    except Exception:
        raise HTTPException(
            status_code = 401,
            detail = "Invalid or Expired token"
        )