import pytest

from sql.validator import SqlValidationError, validate_select

SCHEMA = "ds_0123456789ab"
TABLES = {"orders", "customers"}


def ok(sql: str) -> str:
    return validate_select(sql, SCHEMA, TABLES)


def bad(sql: str) -> None:
    with pytest.raises(SqlValidationError):
        validate_select(sql, SCHEMA, TABLES)


def test_simple_select_and_trailing_semicolon():
    assert "orders" in ok("SELECT * FROM orders;")


def test_cte_and_join_and_union_allowed():
    ok("WITH t AS (SELECT customer_id, count(*) c FROM orders GROUP BY 1) SELECT * FROM t")
    ok("SELECT id FROM orders UNION ALL SELECT id FROM customers")
    ok('SELECT o."id" FROM "orders" o JOIN customers c ON c.id = o.customer_id')
    ok(f'SELECT * FROM "{SCHEMA}".orders')
    ok("SELECT g FROM generate_series(1, 3) g")


def test_comments_are_stripped_from_output():
    out = ok("SELECT 1 /* ; drop table x */ FROM orders -- trailing")
    assert "drop" not in out.lower()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; SELECT 2",
        "SELECT 1; DROP TABLE orders",
        "DROP TABLE orders",
        "DELETE FROM orders",
        "UPDATE orders SET id = 1",
        "INSERT INTO orders VALUES (1)",
        "CREATE TABLE x (a int)",
        "ALTER TABLE orders ADD COLUMN x int",
        "TRUNCATE orders",
        "COPY orders TO '/tmp/x'",
        "SET ROLE postgres",
        "RESET ROLE",
        "BEGIN",
        "COMMIT",
        "GRANT ALL ON orders TO public",
        "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
        "WITH d AS (INSERT INTO orders VALUES (1) RETURNING *) SELECT * FROM d",
        "SELECT * INTO newt FROM orders",
        "SELECT * FROM orders FOR UPDATE",
        "",
        "   ",
        "SELEC FROM",
        "EXPLAIN ANALYZE DELETE FROM orders",
        "DO $$ BEGIN PERFORM 1; END $$",
        "CALL foo()",
        "VACUUM orders",
    ],
)
def test_rejects_non_select(sql):
    bad(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM pg_catalog.pg_class",
        "SELECT * FROM pg_class",
        "SELECT * FROM pg_user",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM app.datasets",
        "SELECT * FROM public.orders",
        "SELECT * FROM ds_ffffffffffff.orders",
        "SELECT * FROM mydb.ds_0123456789ab.orders",
        'SELECT * FROM "pg_catalog"."pg_authid"',
        "SELECT * FROM unknown_table",
        "SELECT * FROM orders o JOIN app.messages m ON true",
        "SELECT (SELECT count(*) FROM app.datasets)",
    ],
)
def test_rejects_other_schemas_and_unknown_tables(sql):
    bad(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_ls_dir('.')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT set_config('role', 'postgres', false)",
        "SELECT current_setting('is_superuser')",
        "SELECT * FROM dblink('host=x', 'select 1') AS t(a int)",
        "SELECT query_to_xml('select * from app.datasets', true, true, '')",
        "SELECT pg_terminate_backend(1)",
        "SELECT nextval('x')",
        "SELECT version()",
        "SELECT current_user",
        "SELECT * FROM pg_sleep(5)",
    ],
)
def test_rejects_dangerous_functions(sql):
    bad(sql)


def test_stacked_statement_hidden_in_string_is_just_a_string():
    out = ok("SELECT 'a; DROP TABLE orders' AS s FROM orders")
    assert out.count(";") == 1 and "'a; DROP TABLE orders'" in out


def test_case_insensitive_unquoted_tables():
    ok("SELECT * FROM ORDERS")
    bad('SELECT * FROM "ORDERS"')


def test_quoted_identifier_tricks():
    bad('SELECT * FROM "orders"; DROP TABLE "orders"')
    ok("SELECT * FROM orders WHERE id = 1;")
