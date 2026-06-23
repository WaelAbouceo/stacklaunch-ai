"""Tests for the governed database access layer (database.py)."""

import pytest

from data import database
from data import projectbuilder


def _connectors() -> dict:
    scan = {"websiteUrl": "https://b.com", "siteSummary": "Bank",
            "knowledgeBase": {"pagesIndexed": 1, "pages": [
                {"title": "Home", "url": "https://b.com", "summary": "Bank",
                 "topics": [], "content": "bank"}]}}
    return projectbuilder.build_project(scan, "B Bank", "banking", 1.0)["connectors"]


def test_build_db_loads_all_rows():
    conn = database.build_db(_connectors())
    assert conn.execute("SELECT count(*) FROM crm").fetchone()[0] == 250
    assert conn.execute("SELECT count(*) FROM erp").fetchone()[0] == 80
    assert conn.execute("SELECT count(*) FROM ticketing").fetchone()[0] == 120
    conn.close()


def test_group_by_aggregate_query():
    out = database.run_query(_connectors(), {
        "table": "ticketing",
        "select": ["category"],
        "aggregate": [{"fn": "count", "as": "n"}],
        "group_by": ["category"],
        "order_by": [{"column": "n", "dir": "desc"}],
        "limit": 5,
    })
    assert out["rowCount"] <= 5
    assert out["columns"] == ["category", "n"]
    assert "GROUP BY" in out["sql"]
    # Counts are positive and sorted descending.
    counts = [r["n"] for r in out["rows"]]
    assert counts == sorted(counts, reverse=True)


def test_filter_query_with_params():
    out = database.run_query(_connectors(), {
        "table": "crm",
        "select": ["customerId", "status"],
        "filters": [{"column": "status", "op": "=", "value": "at_risk"}],
        "limit": 10,
    })
    assert all(r["status"] == "at_risk" for r in out["rows"])


def test_pii_columns_are_masked():
    out = database.run_query(_connectors(), {
        "table": "crm",
        "select": ["customerId", "name", "email", "phone", "segment"],
        "limit": 5,
    })
    for row in out["rows"]:
        assert row["name"] == "[REDACTED]"
        assert row["email"] == "[REDACTED]"
        assert row["phone"] == "[REDACTED]"
        assert row["customerId"].startswith("CUST-")  # non-PII passes through


def test_rejects_unknown_table():
    with pytest.raises(database.QueryError):
        database.run_query(_connectors(), {"table": "salaries", "select": ["*"]})


def test_rejects_unknown_column():
    with pytest.raises(database.QueryError):
        database.run_query(_connectors(), {"table": "crm", "select": ["ssn"]})


def test_rejects_bad_operator():
    with pytest.raises(database.QueryError):
        database.run_query(_connectors(), {
            "table": "crm", "select": ["customerId"],
            "filters": [{"column": "status", "op": "DROP", "value": "x"}],
        })


def test_limit_is_clamped():
    out = database.run_query(_connectors(), {"table": "crm", "select": ["customerId"],
                                             "limit": 99999})
    assert f"LIMIT {database.MAX_LIMIT}" in out["sql"]


def test_in_operator():
    out = database.run_query(_connectors(), {
        "table": "ticketing", "select": ["ticketId", "sentiment"],
        "filters": [{"column": "sentiment", "op": "in", "value": ["negative", "neutral"]}],
        "limit": 20,
    })
    assert all(r["sentiment"] in ("negative", "neutral") for r in out["rows"])
