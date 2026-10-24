import datetime as dt
from decimal import Decimal

import pytest

from config import get_settings
from ingest.commit import ColumnEdit, TableEdit, apply_edits
from ingest.drafts import build_draft
from ingest.parsers import IngestError, parse_csv, parse_file, parse_json
from ingest.types import coerce, infer_type, sanitize_identifier

S = get_settings()


def test_infer_types():
    assert infer_type(["1", "2", "-3"]) == "integer"
    assert infer_type(["1", "2.5"]) == "numeric"
    assert infer_type(["true", "No", None]) == "boolean"
    assert infer_type(["2024-01-31", "2024-02-01"]) == "date"
    assert infer_type(["2024-01-31", "2024-02-01 10:00:00"]) == "timestamp"
    assert infer_type(["2024-13-45"]) == "text"
    assert infer_type(["007", "010"]) == "text"  # leading zeros are identifiers
    assert infer_type(["12345678901234567890"]) == "text"  # beyond bigint
    assert infer_type(["1", "x"]) == "text"
    assert infer_type([None, None]) == "text"
    assert infer_type([1, 2.0, 3]) == "integer"
    assert infer_type([True, False]) == "boolean"
    assert infer_type([dt.datetime(2024, 1, 1), dt.datetime(2024, 1, 2)]) == "date"


def test_coerce():
    assert coerce("42", "integer") == 42
    assert coerce("5.0", "integer") == 5
    assert coerce("12.50", "numeric") == Decimal("12.50")
    assert coerce("yes", "boolean") is True
    assert coerce("2024-03-05", "date") == dt.date(2024, 3, 5)
    assert coerce("2024-03-05T10:00:00+02:00", "timestamp") == dt.datetime(2024, 3, 5, 8, 0)
    assert coerce(None, "integer") is None
    with pytest.raises(ValueError):
        coerce("abc", "integer")
    with pytest.raises(ValueError):
        coerce("5.5", "integer")


def test_sanitize_identifier():
    taken: set[str] = set()
    assert sanitize_identifier("Order ID", taken) == "order_id"
    assert sanitize_identifier("order-id", taken) == "order_id_2"
    assert sanitize_identifier("2024 Sales", taken) == "c_2024_sales"
    assert sanitize_identifier("", taken) == "col"
    assert sanitize_identifier("customerName", taken) == "customer_name"
    assert sanitize_identifier("Café", taken) == "cafe"
    assert len(sanitize_identifier("x" * 200, taken)) <= 50


def test_parse_csv_and_build_draft():
    content = b"Order ID,Amount,Placed On,Active,Zip\n1,10.5,2024-01-01,true,02134\n2,,2024-01-02,false,10001\n"
    raw = parse_csv("My Orders.csv", content, 1000)
    draft = build_draft(raw, visitor_id="v", dataset_name="x", settings=S)
    table = draft.tables[0]
    assert table.name == "my_orders"
    assert [(c.name, c.type) for c in table.columns] == [
        ("order_id", "integer"),
        ("amount", "numeric"),
        ("placed_on", "date"),
        ("active", "boolean"),
        ("zip", "text"),
    ]
    assert table.rows[1][1] is None
    assert table.rows[0][4] == "02134"


def test_parse_csv_semicolon_delimiter():
    raw = parse_csv("a.csv", b"a;b\n1;2\n3;4\n", 100)
    assert raw[0].columns == ["a", "b"]


def test_parse_json_variants():
    assert parse_json("a.json", b'[{"a": 1, "b": {"c": 2}}]')[0].rows[0][1] == '{"c": 2}'
    tables = parse_json("a.json", b'{"x": [{"a": 1}], "y": [{"b": 2}]}')
    assert [t.name for t in tables] == ["x", "y"]
    with pytest.raises(IngestError):
        parse_json("a.json", b"not json")
    with pytest.raises(IngestError):
        parse_json("a.json", b"[1, 2]")


def test_unsupported_extension():
    with pytest.raises(IngestError):
        parse_file("a.exe", b"x", 10)


def test_limits():
    big = b"a\n" + b"1\n" * (S.max_total_rows + 5)
    with pytest.raises(IngestError):
        build_draft(
            parse_csv("a.csv", big, S.max_total_rows), visitor_id="v", dataset_name="x", settings=S
        )
    wide = (
        ",".join(f"c{i}" for i in range(S.max_columns_per_table + 1))
        + "\n"
        + ",".join("1" for _ in range(S.max_columns_per_table + 1))
    ).encode()
    with pytest.raises(IngestError):
        build_draft(parse_csv("w.csv", wide, 100), visitor_id="v", dataset_name="x", settings=S)


def test_apply_edits_renames_retypes_and_drops():
    raw = parse_csv("t.csv", b"a,b,c\n1,2,x\n3,4,y\n", 100)
    draft = build_draft(raw, visitor_id="v", dataset_name="x", settings=S)
    edits = [
        TableEdit(
            source="t",
            name="Renamed Table",
            columns=[
                ColumnEdit(source="a", name="A Col", type="text"),
                ColumnEdit(source="c", name="c", type="text"),
            ],
        )
    ]
    final = apply_edits(draft, edits, S)
    assert final[0].name == "renamed_table"
    assert final[0].columns == [("a_col", "text"), ("c", "text")]
    assert final[0].rows == [("1", "x"), ("3", "y")]


def test_apply_edits_rejects_impossible_cast():
    raw = parse_csv("t.csv", b"a\nfoo\nbar\n", 100)
    draft = build_draft(raw, visitor_id="v", dataset_name="x", settings=S)
    edits = [
        TableEdit(source="t", name="t", columns=[ColumnEdit(source="a", name="a", type="integer")])
    ]
    with pytest.raises(IngestError):
        apply_edits(draft, edits, S)
