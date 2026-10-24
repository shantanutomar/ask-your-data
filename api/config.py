from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    openai_api_key: str
    model_fast: str
    model_sql: str
    free_actions: int
    gate_namespace: str
    gate_ttl_days: int
    dataset_ttl_hours: int
    max_upload_mb: int
    max_total_rows: int
    max_tables: int
    max_columns_per_table: int
    max_result_rows: int
    sql_statement_timeout_ms: int
    max_free_text_chars: int
    max_sql_retries: int
    fake_llm: bool
    max_active_datasets: int
    enable_docs: bool
    log_level: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://localhost:5432/ask_your_data"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        model_fast=os.getenv("OPENAI_MODEL_FAST", "gpt-4o-mini"),
        model_sql=os.getenv("OPENAI_MODEL_SQL", "gpt-4o"),
        free_actions=_int("FREE_ACTIONS", 3),
        gate_namespace=os.getenv("GATE_NAMESPACE", "ask-your-data"),
        gate_ttl_days=_int("GATE_TTL_DAYS", 7),
        dataset_ttl_hours=_int("DATASET_TTL_HOURS", 24),
        max_upload_mb=_int("MAX_UPLOAD_MB", 5),
        max_total_rows=_int("MAX_TOTAL_ROWS", 50000),
        max_tables=_int("MAX_TABLES", 5),
        max_columns_per_table=_int("MAX_COLUMNS_PER_TABLE", 50),
        max_result_rows=_int("MAX_RESULT_ROWS", 500),
        sql_statement_timeout_ms=_int("SQL_STATEMENT_TIMEOUT_MS", 5000),
        max_free_text_chars=_int("MAX_FREE_TEXT_CHARS", 20000),
        max_sql_retries=_int("MAX_SQL_RETRIES", 2),
        fake_llm=os.getenv("FAKE_LLM", "") in ("1", "true", "yes"),
        max_active_datasets=_int("MAX_ACTIVE_DATASETS", 300),
        enable_docs=os.getenv("ENABLE_DOCS", "") in ("1", "true", "yes"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
