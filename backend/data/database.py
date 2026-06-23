"""Governed database access layer over the internal connectors.

The connectors (CRM / ERP / ticketing) are loaded into a per-request **in-memory
SQLite** database so the assistant can run real, ad-hoc structured queries against
the raw records — not just the fixed pre-aggregated summaries. The LLM never writes
raw SQL; it emits a constrained **query spec** (table / columns / filters /
aggregations / group-by / order / limit) which this module validates against the
known schema and compiles to a single, **read-only, parameterised** SELECT.

Governance is enforced at the data layer:
- only whitelisted tables/columns/operators/functions are allowed;
- results are clamped to a row limit;
- PII columns are masked on output (defence in depth on top of `pii.py`).

This is the safe alternative to free-form text-to-SQL: the model gets full querying
power without SQL-injection or data-exfiltration risk.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from governance import pii

# Whitelisted schema. Keys are table names; values are the queryable columns.
SCHEMA: dict[str, list[str]] = {
    "crm": ["customerId", "name", "segment", "city", "email", "phone",
            "lifetimeValueEgp", "lastInteraction", "preferredChannel", "status"],
    "erp": ["recordId", "entityType", "name", "revenueEgp", "costEgp",
            "marginPercent", "utilizationPercent", "period"],
    "ticketing": ["ticketId", "customerId", "category", "priority", "status",
                  "createdAt", "channel", "summary", "sentiment", "slaStatus",
                  "linkedEntity"],
}

# Columns whose values must be masked on output (PII).
PII_COLUMNS: dict[str, set[str]] = {
    "crm": {"name", "email", "phone"},
}

_OPS = {"=", "!=", ">", "<", ">=", "<=", "like", "in"}
_AGG_FNS = {"count", "sum", "avg", "min", "max"}
MAX_LIMIT = 200


class QueryError(Exception):
    """Raised when a query spec is invalid or unsafe."""


def schema_for(table: str | None = None) -> dict:
    if table:
        if table not in SCHEMA:
            raise QueryError(f"Unknown table '{table}'.")
        return {table: SCHEMA[table]}
    return dict(SCHEMA)


def _connector_records(connectors: dict, table: str) -> list[dict]:
    return connectors.get(table, {}).get("records", []) or []


def build_db(connectors: dict) -> sqlite3.Connection:
    """Build a fresh in-memory SQLite DB from the project's connector records."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for table, columns in SCHEMA.items():
        cols_ddl = ", ".join(f'"{c}"' for c in columns)
        conn.execute(f'CREATE TABLE "{table}" ({cols_ddl})')
        placeholders = ", ".join("?" for _ in columns)
        rows = [
            tuple(rec.get(c) for c in columns)
            for rec in _connector_records(connectors, table)
        ]
        if rows:
            conn.executemany(
                f'INSERT INTO "{table}" ({cols_ddl}) VALUES ({placeholders})', rows
            )
    conn.commit()
    return conn


def _validate_column(table: str, column: str) -> None:
    if column not in SCHEMA[table]:
        raise QueryError(f"Unknown column '{column}' for table '{table}'.")


def _compile(spec: dict) -> tuple[str, list[Any], list[str]]:
    """Validate the spec and compile to (sql, params, output_columns)."""
    if not isinstance(spec, dict):
        raise QueryError("Query must be an object.")
    table = spec.get("table")
    if table not in SCHEMA:
        raise QueryError(f"Unknown or missing table. Valid: {sorted(SCHEMA)}.")

    select = spec.get("select") or []
    if select in ("*", ["*"]):
        select = list(SCHEMA[table])
    if not isinstance(select, list):
        raise QueryError("'select' must be a list of column names or '*'.")
    for c in select:
        _validate_column(table, c)

    aggregates = spec.get("aggregate") or []
    if not isinstance(aggregates, list):
        raise QueryError("'aggregate' must be a list.")
    select_parts: list[str] = [f'"{c}"' for c in select]
    out_cols: list[str] = list(select)
    for agg in aggregates:
        fn = str(agg.get("fn", "")).lower()
        if fn not in _AGG_FNS:
            raise QueryError(f"Unsupported aggregate '{fn}'. Allowed: {sorted(_AGG_FNS)}.")
        col = agg.get("column")
        if fn == "count" and col in (None, "*"):
            expr = "count(*)"
        else:
            _validate_column(table, col)
            expr = f'{fn}("{col}")'
        alias = str(agg.get("as") or f"{fn}_{col or 'all'}")
        if not alias.replace("_", "").isalnum():
            raise QueryError(f"Invalid alias '{alias}'.")
        select_parts.append(f'{expr} AS "{alias}"')
        out_cols.append(alias)

    if not select_parts:
        raise QueryError("Query selects no columns.")

    sql = f'SELECT {", ".join(select_parts)} FROM "{table}"'
    params: list[Any] = []

    filters = spec.get("filters") or []
    if not isinstance(filters, list):
        raise QueryError("'filters' must be a list.")
    where: list[str] = []
    for f in filters:
        col = f.get("column")
        op = str(f.get("op", "=")).lower()
        _validate_column(table, col)
        if op not in _OPS:
            raise QueryError(f"Unsupported operator '{op}'. Allowed: {sorted(_OPS)}.")
        val = f.get("value")
        if op == "in":
            if not isinstance(val, list) or not val:
                raise QueryError("'in' requires a non-empty list value.")
            where.append(f'"{col}" IN ({", ".join("?" for _ in val)})')
            params.extend(val)
        else:
            where.append(f'"{col}" {op.upper()} ?')
            params.append(val)
    if where:
        sql += " WHERE " + " AND ".join(where)

    group_by = spec.get("group_by") or []
    if group_by:
        if not isinstance(group_by, list):
            raise QueryError("'group_by' must be a list.")
        for c in group_by:
            _validate_column(table, c)
        sql += " GROUP BY " + ", ".join(f'"{c}"' for c in group_by)

    order_by = spec.get("order_by") or []
    if order_by:
        if not isinstance(order_by, list):
            raise QueryError("'order_by' must be a list.")
        order_parts: list[str] = []
        valid_order_cols = set(out_cols)
        for o in order_by:
            col = o.get("column")
            if col not in valid_order_cols:
                raise QueryError(f"Cannot order by '{col}'; not a selected column.")
            direction = "DESC" if str(o.get("dir", "asc")).lower() == "desc" else "ASC"
            order_parts.append(f'"{col}" {direction}')
        sql += " ORDER BY " + ", ".join(order_parts)

    limit = spec.get("limit", 50)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise QueryError("'limit' must be an integer.")
    limit = max(1, min(limit, MAX_LIMIT))
    sql += f" LIMIT {limit}"

    return sql, params, out_cols


def _mask_row(table: str, row: dict) -> dict:
    pii_cols = PII_COLUMNS.get(table, set())
    out = {}
    for k, v in row.items():
        if k in pii_cols and v not in (None, ""):
            out[k] = "[REDACTED]"
        elif isinstance(v, str):
            out[k] = pii.redact_text(v).text
        else:
            out[k] = v
    return out


def run_query(connectors: dict, spec: dict) -> dict:
    """Validate + compile + execute a query spec; return masked rows + the SQL."""
    sql, params, out_cols = _compile(spec)
    conn = build_db(connectors)
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    except sqlite3.Error as exc:
        raise QueryError(f"Query failed: {exc}")
    finally:
        conn.close()
    table = spec["table"]
    masked = [_mask_row(table, r) for r in rows]
    return {
        "table": table,
        "columns": out_cols,
        "rowCount": len(masked),
        "rows": masked,
        "sql": sql,  # surfaced for transparency / auditability
        "governance": "Read-only, schema-validated query; PII columns masked.",
    }
