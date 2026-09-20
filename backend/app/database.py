# Supabase Client will be created here to keep all it's configurations in one place

from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SECRET_KEY

supabase : Client = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)