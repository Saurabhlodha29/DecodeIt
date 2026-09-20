-- 001_initial_schema.sql

-- Phase 0 schema: profiles, repos, commits, jobs, files, symbols, code_edges, chunks.

-- Designed for a Supabase Postgres database (it references auth.users).

-- Authentication, OAuth, and Row Level Security (RLS) are already configured
-- separately in the Supabase database. This schema is designed to work with
-- the authenticated Supabase users and their ownership relationships.

-- The profiles table is linked directly to auth.users.
-- Application data follows the ownership chain:
-- auth.users -> profiles -> repos -> commits -> files/symbols/chunks.

-- RLS is enabled on the application tables and policies restrict users
-- to resources they are authorized to access.

-- Supabase Auth/OAuth is responsible for user authentication.
-- The backend uses the Supabase secret key for server-side operations,
-- while the frontend uses the Supabase publishable key.

-- Indexes and constraints required for repository ownership, commit/file
-- uniqueness, graph traversal, full-text search, and vector similarity
-- are already part of the database configuration.

--
-- The enum type names for language, job type, symbol kind and edge type below were
-- re-created from the schema export, which only showed "USER-DEFINED". If the live
-- database uses different names or values, compare with:
--
--   select t.typname, e.enumlabel
--   from pg_type t join pg_enum e on e.enumtypid = t.oid
--   order by t.typname, e.enumsortorder;

-- ---------- Extensions ----------

create extension if not exists vector with schema extensions;

-- ---------- Enum types ----------

do $$ begin
  create type public.user_role as enum ('viewer', 'reviewer');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.repo_language as enum ('python', 'java');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.commit_status as enum ('pending', 'ingesting', 'ready', 'failed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.job_type as enum ('ingest_repo', 'embed_chunks', 'build_graph');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.job_status as enum ('queued', 'running', 'succeeded', 'failed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.symbol_kind as enum ('function', 'method', 'class', 'db_table');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.edge_type as enum ('calls', 'imports', 'reads', 'writes', 'inherits');
exception when duplicate_object then null; end $$;

-- ---------- Tables ----------

create table if not exists public.profiles (
  id uuid not null,
  display_name text,
  role public.user_role not null default 'viewer',
  created_at timestamptz not null default now(),
  constraint profiles_pkey primary key (id),
  constraint profiles_id_fkey foreign key (id) references auth.users (id)
);

create table if not exists public.repos (
  id uuid not null default gen_random_uuid(),
  owner_id uuid not null,
  url text not null,
  name text not null,
  language public.repo_language not null,
  default_branch text not null,
  created_at timestamptz not null default now(),
  constraint repos_pkey primary key (id),
  constraint repos_owner_id_fkey foreign key (owner_id) references public.profiles (id)
);

create table if not exists public.commits (
  id uuid not null default gen_random_uuid(),
  repo_id uuid not null,
  commit_sha text not null,
  status public.commit_status not null default 'pending',
  error text,
  ingested_at timestamptz,
  created_at timestamptz not null default now(),
  constraint commits_pkey primary key (id),
  constraint commits_repo_id_fkey foreign key (repo_id) references public.repos (id)
);

create table if not exists public.jobs (
  id uuid not null default gen_random_uuid(),
  type public.job_type not null,
  payload jsonb not null default '{}'::jsonb,
  status public.job_status not null default 'queued',
  attempts integer not null default 0,
  max_attempts integer not null default 3,
  run_after timestamptz,
  locked_at timestamptz,
  finished_at timestamptz,
  error text,
  repo_id uuid,
  created_by uuid,
  created_at timestamptz not null default now(),
  constraint jobs_pkey primary key (id),
  constraint jobs_repo_id_fkey foreign key (repo_id) references public.repos (id),
  constraint jobs_created_by_fkey foreign key (created_by) references public.profiles (id)
);

create table if not exists public.files (
  id uuid not null default gen_random_uuid(),
  commit_id uuid not null,
  path text not null,
  language text not null,
  content text not null,
  content_hash text not null,
  line_count integer not null,
  created_at timestamptz not null default now(),
  constraint files_pkey primary key (id),
  constraint files_commit_id_fkey foreign key (commit_id) references public.commits (id)
);

create table if not exists public.symbols (
  id uuid not null default gen_random_uuid(),
  commit_id uuid not null,
  file_id uuid,
  parent_symbol_id uuid,
  kind public.symbol_kind not null,
  name text not null,
  qualified_name text not null,
  signature text,
  docstring text,
  start_line integer,
  end_line integer,
  code_hash text not null,
  created_at timestamptz not null default now(),
  constraint symbols_pkey primary key (id),
  constraint symbols_commit_id_fkey foreign key (commit_id) references public.commits (id),
  constraint symbols_file_id_fkey foreign key (file_id) references public.files (id),
  constraint symbols_parent_symbol_id_fkey foreign key (parent_symbol_id) references public.symbols (id)
);

create table if not exists public.code_edges (
  id uuid not null default gen_random_uuid(),
  commit_id uuid not null,
  src_symbol_id uuid not null,
  dst_symbol_id uuid,
  dst_name text,
  edge_type public.edge_type not null,
  confidence real not null check (confidence >= 0 and confidence <= 1),
  line integer,
  created_at timestamptz not null default now(),
  constraint code_edges_pkey primary key (id),
  constraint code_edges_commit_id_fkey foreign key (commit_id) references public.commits (id),
  constraint code_edges_src_symbol_id_fkey foreign key (src_symbol_id) references public.symbols (id),
  constraint code_edges_dst_symbol_id_fkey foreign key (dst_symbol_id) references public.symbols (id)
);

create table if not exists public.chunks (
  id uuid not null default gen_random_uuid(),
  commit_id uuid not null,
  file_id uuid not null,
  symbol_id uuid,
  content text not null,
  start_line integer not null,
  end_line integer not null,
  token_count integer not null,
  embedding vector(1024),
  fts tsvector generated always as (to_tsvector('simple', content)) stored,
  created_at timestamptz not null default now(),
  constraint chunks_pkey primary key (id),
  constraint chunks_commit_id_fkey foreign key (commit_id) references public.commits (id),
  constraint chunks_file_id_fkey foreign key (file_id) references public.files (id),
  constraint chunks_symbol_id_fkey foreign key (symbol_id) references public.symbols (id)
);