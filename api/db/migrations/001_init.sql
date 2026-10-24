CREATE TABLE app.datasets (
    id          text PRIMARY KEY,
    visitor_id  text NOT NULL UNIQUE,
    schema_name text NOT NULL,
    name        text NOT NULL,
    version     int NOT NULL DEFAULT 1,
    tables      jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
CREATE INDEX datasets_expires_at_idx ON app.datasets (expires_at);

CREATE TABLE app.conversations (
    id         text PRIMARY KEY,
    dataset_id text NOT NULL REFERENCES app.datasets (id) ON DELETE CASCADE,
    title      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX conversations_dataset_idx ON app.conversations (dataset_id, updated_at DESC);

CREATE TABLE app.messages (
    id              text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES app.conversations (id) ON DELETE CASCADE,
    role            text NOT NULL,
    content         text NOT NULL DEFAULT '',
    sql             jsonb,
    tables          jsonb,
    chart           jsonb,
    status          text NOT NULL DEFAULT 'completed',
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX messages_conversation_idx ON app.messages (conversation_id, created_at);

-- Dedicated read-only role used to run LLM-written SQL. No default privileges:
-- access is granted per dataset schema at commit time.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ayd_reader') THEN
        CREATE ROLE ayd_reader NOLOGIN;
    END IF;
END
$$;
-- The connecting role must be allowed to SET ROLE ayd_reader.
GRANT ayd_reader TO CURRENT_USER;
