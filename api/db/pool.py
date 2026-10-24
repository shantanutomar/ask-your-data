from __future__ import annotations

import json
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_LOCK_ID = 7_240_001


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        database_url, min_size=1, max_size=10, init=_init_connection, command_timeout=60
    )


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Apply db/migrations/*.sql in filename order, once each."""
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_ID)
        try:
            await conn.execute(
                """
                CREATE SCHEMA IF NOT EXISTS app;
                CREATE TABLE IF NOT EXISTS app.schema_migrations (
                    name text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                );
                """
            )
            applied = {
                r["name"] for r in await conn.fetch("SELECT name FROM app.schema_migrations")
            }
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in applied:
                    continue
                async with conn.transaction():
                    await conn.execute(path.read_text())
                    await conn.execute(
                        "INSERT INTO app.schema_migrations (name) VALUES ($1)", path.name
                    )
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_ID)
