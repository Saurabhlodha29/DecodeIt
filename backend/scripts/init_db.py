"""Apply the SQL migrations in db/migrations/ to the database in DATABASE_URL.

Usage (from the repository root, virtual environment active):

    python backend/scripts/init_db.py

- Reads DATABASE_URL from the .env file in the repository root.
- Use the Supabase *direct connection* or *session pooler* string, not the transaction pooler.
- Migrations run in filename order (001_..., 002_...). Applied files are recorded in
  public.schema_migrations, so running the script again only applies new files.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "db" / "migrations"


def main() -> None:
    load_dotenv(ROOT / ".env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set. Add it to your .env file (see .env.example).")

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        sys.exit(f"No .sql files found in {MIGRATIONS_DIR}")

    print(f"Target database host: {urlparse(database_url).hostname}")

    with psycopg.connect(database_url) as conn:
        # Bookkeeping table. RLS is enabled with no policies so the public API cannot read it.
        conn.execute(
            """
            create table if not exists public.schema_migrations (
              filename text primary key,
              applied_at timestamptz not null default now()
            );
            alter table public.schema_migrations enable row level security;
            """
        )
        conn.commit()

        applied = {row[0] for row in conn.execute("select filename from public.schema_migrations")}

        for path in migration_files:
            if path.name in applied:
                print(f"Skipping {path.name} (already applied)")
                continue

            print(f"Applying {path.name} ...")
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "insert into public.schema_migrations (filename) values (%s)",
                (path.name,),
            )
            conn.commit()

    print("Done.")


if __name__ == "__main__":
    main()
