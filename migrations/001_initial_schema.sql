
-- ============================================================================
-- TaskFlow — Initial Schema
-- Run this in: Supabase Dashboard → SQL Editor
-- Or via Supabase CLI: supabase db push
-- ============================================================================

-- ── Enable UUID extension ────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Users ────────────────────────────────────────────────────────────────────
-- Note: Supabase Auth manages authentication in auth.users.
-- This table stores application-level profile data and links to auth.users.
CREATE TABLE IF NOT EXISTS public.users (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    email            TEXT        NOT NULL,
    hashed_password  TEXT        NOT NULL,         -- kept for custom JWT path
    full_name        TEXT,
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    is_superuser     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON public.users (email);

-- ── Projects ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.projects (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         TEXT        NOT NULL CHECK (char_length(name) <= 255),
    description  TEXT,
    owner_id     UUID        NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_projects_owner_id ON public.projects (owner_id);

-- ── Tasks ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tasks (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    title        TEXT        NOT NULL CHECK (char_length(title) <= 500),
    description  TEXT,
    status       TEXT        NOT NULL DEFAULT 'todo'
                             CHECK (status IN ('todo', 'in_progress', 'in_review', 'done')),
    priority     TEXT        NOT NULL DEFAULT 'medium'
                             CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    project_id   UUID        NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
    assignee_id  UUID        REFERENCES public.users (id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_tasks_project_id  ON public.tasks (project_id);
CREATE INDEX IF NOT EXISTS ix_tasks_assignee_id ON public.tasks (assignee_id);
CREATE INDEX IF NOT EXISTS ix_tasks_status      ON public.tasks (status);
CREATE INDEX IF NOT EXISTS ix_tasks_priority    ON public.tasks (priority);

-- ── Refresh Token Blocklist ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.token_blocklist (
    jti         TEXT        PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    revoked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_blocklist_user_id    ON public.token_blocklist (user_id);
CREATE INDEX IF NOT EXISTS ix_blocklist_expires_at ON public.token_blocklist (expires_at);

-- ── Auto-update updated_at via trigger ───────────────────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE OR REPLACE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON public.projects
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE OR REPLACE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON public.tasks
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── Row Level Security ────────────────────────────────────────────────────────
-- Enable RLS on all tables (service role bypasses these automatically)
ALTER TABLE public.users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.token_blocklist ENABLE ROW LEVEL SECURITY;

-- Users can only read/update their own profile
CREATE POLICY "users_select_own" ON public.users
    FOR SELECT USING (id::text = auth.uid()::text);

CREATE POLICY "users_update_own" ON public.users
    FOR UPDATE USING (id::text = auth.uid()::text);

-- Projects: owners can do everything
CREATE POLICY "projects_owner_all" ON public.projects
    FOR ALL USING (owner_id::text = auth.uid()::text);

-- Tasks: access through project ownership
CREATE POLICY "tasks_owner_all" ON public.tasks
    FOR ALL USING (
        project_id IN (
            SELECT id FROM public.projects WHERE owner_id::text = auth.uid()::text
        )
    );

-- Blocklist: users manage their own tokens
CREATE POLICY "blocklist_owner_all" ON public.token_blocklist
    FOR ALL USING (user_id::text = auth.uid()::text);

-- ── Cleanup function (call periodically) ─────────────────────────────────────
CREATE OR REPLACE FUNCTION public.sweep_expired_tokens()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM public.token_blocklist WHERE expires_at <= NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
