"""Static validation of LLM-written SQL. Part of the security boundary.

Defence in depth: this module rejects anything but a single read-only SELECT that only touches
the dataset's own tables. The executor then runs the *regenerated* SQL (not the original text)
under a read-only role pinned to the dataset schema.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


class SqlValidationError(ValueError):
    pass


_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable",
    "TruncateTable", "Command", "Copy", "Set", "SetItem", "Transaction", "Commit", "Rollback",
    "Grant", "Revoke", "Use", "Pragma", "Analyze", "Kill", "Declare", "Execute", "Refresh",
    "LoadData", "Attach", "Detach", "Cache", "Uncache", "Into", "Lock", "Show", "Describe",
)  # fmt: skip
_FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NODE_NAMES if hasattr(exp, n))

_BLOCKED_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "txid_", "pgp_", "xpath")
_BLOCKED_FUNCTIONS = frozenset(
    {
        "set_config", "current_setting", "copy", "query_to_xml", "table_to_xml",
        "database_to_xml", "schema_to_xml", "cursor_to_xml", "query_to_xml_and_xmlschema",
        "table_to_xml_and_xmlschema", "schema_to_xml_and_xmlschema", "nextval", "setval",
        "currval", "lastval", "current_database", "current_user", "session_user", "version",
        "inet_server_addr", "inet_server_port", "inet_client_addr", "inet_client_port",
        "has_table_privilege", "has_schema_privilege", "has_database_privilege",
        "current_version", "current_catalog", "current_schema", "current_schemas",
    }
)  # fmt: skip
_BLOCKED_SCHEMAS = frozenset({"pg_catalog", "information_schema", "app", "public", "pg_toast"})


def _norm(ident: exp.Identifier | None) -> str:
    """Postgres folds unquoted identifiers to lower case; quoted ones are exact."""
    if ident is None:
        return ""
    return ident.name if ident.args.get("quoted") else ident.name.lower()


def _function_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return node.sql_name().lower()


def validate_select(sql: str, schema_name: str, allowed_tables: set[str] | None = None) -> str:
    """Return normalised, safe SQL text or raise SqlValidationError.

    `allowed_tables`, when given, restricts unqualified table references to the dataset's tables
    (plus CTE names) - this also blocks implicit `pg_catalog` lookups like `FROM pg_class`.
    """
    if not sql or not sql.strip():
        raise SqlValidationError("Empty query.")
    if "\x00" in sql:
        raise SqlValidationError("Invalid character in query.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except SqlglotError as exc:
        raise SqlValidationError(f"Could not parse SQL: {str(exc).splitlines()[0][:200]}") from exc

    if len(statements) != 1:
        raise SqlValidationError("Exactly one SQL statement is allowed.")
    root = statements[0]
    if not isinstance(root, exp.Query):
        raise SqlValidationError("Only SELECT queries are allowed.")
    if isinstance(root, exp.Subquery):
        inner = root.unnest()
        if not isinstance(inner, exp.Query):
            raise SqlValidationError("Only SELECT queries are allowed.")

    cte_names = {_norm(cte.args.get("alias").this) for cte in root.find_all(exp.CTE)
                 if cte.args.get("alias") is not None}  # fmt: skip
    allowed = {t.lower() for t in allowed_tables} if allowed_tables is not None else None

    for node in root.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlValidationError(f"{type(node).__name__.upper()} is not allowed.")
        if isinstance(node, exp.Select) and (node.args.get("into") or node.args.get("locks")):
            raise SqlValidationError("SELECT INTO / locking clauses are not allowed.")
        if isinstance(node, exp.Table):
            _check_table(node, schema_name, allowed, cte_names)
        if isinstance(node, exp.Func):
            name = _function_name(node)
            if name in _BLOCKED_FUNCTIONS or name.startswith(_BLOCKED_FUNCTION_PREFIXES):
                raise SqlValidationError(f"Function {name}() is not allowed.")
        if isinstance(node, (exp.Parameter, exp.Placeholder)):
            raise SqlValidationError("Query parameters are not allowed.")

    return root.sql(dialect="postgres", comments=False)


def _check_table(
    node: exp.Table, schema_name: str, allowed: set[str] | None, cte_names: set[str]
) -> None:
    if node.args.get("catalog") is not None:
        raise SqlValidationError("Cross-database references are not allowed.")
    this = node.this
    if not isinstance(this, exp.Identifier):  # table-valued function, e.g. generate_series()
        return
    name = _norm(this)
    db = node.args.get("db")
    if db is not None:
        db_name = _norm(db) if isinstance(db, exp.Identifier) else str(db)
        if db_name != schema_name or db_name in _BLOCKED_SCHEMAS:
            raise SqlValidationError(f"Schema '{db_name}' is not allowed; use plain table names.")
    elif name in cte_names:
        return
    if re.match(r"^(pg_|sql_)", name) or name in {"information_schema"}:
        raise SqlValidationError(f"Table '{name}' is not allowed.")
    if allowed is not None and name not in allowed and (db is not None or name not in cte_names):
        raise SqlValidationError(f"Unknown table '{name}'.")
