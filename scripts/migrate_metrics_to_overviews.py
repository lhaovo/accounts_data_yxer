#!/usr/bin/env python3
"""
Migrate legacy daily_account_metrics data into daily_account_overviews.

The script is dry-run by default. Add --apply to write rows.
Existing daily_account_overviews rows are preserved unless --overwrite is used.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import _overview_table_ddl, query_metric_rows, resolve_db_path, summarize


MIGRATION_COLLECTED_AT = "migration-from-daily-account-metrics"


@dataclass(frozen=True)
class MigrationResult:
    start: str | None
    end: str | None
    legacy_metric_rows: int
    legacy_daily_rows: int
    existing_overview_rows: int
    inserted: int
    skipped_existing: int
    apply: bool
    overwrite: bool


def connect_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def inspect_table(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    if not table_exists(conn, table):
        return {"exists": False, "columns": [], "indexes": [], "rowCount": 0}

    indexes = []
    for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
        index_info = [dict(row) for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()]
        item = dict(index)
        item["columns"] = [row["name"] for row in index_info]
        indexes.append(item)

    row_count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return {
        "exists": True,
        "columns": [dict(row) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()],
        "indexes": indexes,
        "rowCount": row_count,
    }


def legacy_date_range(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT min(metric_date) AS min_date, max(metric_date) AS max_date FROM daily_account_metrics"
    ).fetchone()
    return row["min_date"], row["max_date"]


def existing_overview_keys(conn: sqlite3.Connection, start: str, end: str) -> set[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT metric_date, platform_account_id
        FROM daily_account_overviews
        WHERE metric_date BETWEEN ? AND ?
        """,
        (start, end),
    ).fetchall()
    return {(row["metric_date"], row["platform_account_id"]) for row in rows}


def legacy_metric_count(conn: sqlite3.Connection, start: str, end: str) -> int:
    return conn.execute(
        """
        SELECT count(*)
        FROM daily_account_metrics
        WHERE metric_date BETWEEN ? AND ?
        """,
        (start, end),
    ).fetchone()[0]


def overview_row_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["metric_date"],
        row["platform_name"] or "",
        row["platform_account_name"] or "",
        row["platform_account_id"],
        row.get("login_status"),
        row.get("fans"),
        row.get("play"),
        row.get("like"),
        row.get("comment"),
        row.get("collect"),
        row.get("publish_count"),
        MIGRATION_COLLECTED_AT,
    )


def upsert_overview_row(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO daily_account_overviews (
            metric_date, platform_name, platform_account_name, platform_account_id,
            login_status, fans, play, like_count, comment_count, collect_count,
            publish_count, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        overview_row_tuple(row),
    )


def migrate_metrics_to_overviews(
    conn: sqlite3.Connection,
    *,
    start: str | None = None,
    end: str | None = None,
    apply: bool = False,
    overwrite: bool = False,
) -> MigrationResult:
    if not table_exists(conn, "daily_account_metrics"):
        raise RuntimeError("daily_account_metrics table does not exist")

    conn.execute(_overview_table_ddl())
    detected_start, detected_end = legacy_date_range(conn)
    if not detected_start or not detected_end:
        return MigrationResult(start, end, 0, 0, 0, 0, 0, apply, overwrite)

    start = start or detected_start
    end = end or detected_end
    metric_rows = legacy_metric_count(conn, start, end)
    daily_rows = summarize(query_metric_rows(conn, start, end, None, None))
    existing_keys = existing_overview_keys(conn, start, end)

    inserted = 0
    skipped_existing = 0
    for row in daily_rows:
        key = (row["metric_date"], row["platform_account_id"])
        if key in existing_keys and not overwrite:
            skipped_existing += 1
            continue
        inserted += 1
        if apply:
            upsert_overview_row(conn, row)

    if apply:
        conn.commit()
    else:
        conn.rollback()

    return MigrationResult(
        start=start,
        end=end,
        legacy_metric_rows=metric_rows,
        legacy_daily_rows=len(daily_rows),
        existing_overview_rows=len(existing_keys),
        inserted=inserted,
        skipped_existing=skipped_existing,
        apply=apply,
        overwrite=overwrite,
    )


def print_schema(conn: sqlite3.Connection) -> None:
    for table in ("daily_account_metrics", "daily_account_overviews"):
        info = inspect_table(conn, table)
        print(f"\n[{table}]")
        print(f"exists: {info['exists']}")
        print(f"rows: {info['rowCount']}")
        for col in info["columns"]:
            pk = " pk" if col["pk"] else ""
            notnull = " not-null" if col["notnull"] else ""
            print(f"  column: {col['name']} {col['type']}{notnull}{pk}")
        for index in info["indexes"]:
            unique = " unique" if index["unique"] else ""
            print(f"  index: {index['name']}{unique} ({', '.join(index['columns'])})")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy daily_account_metrics rows into daily_account_overviews.")
    parser.add_argument("--db", type=Path, default=resolve_db_path(), help="SQLite database path.")
    parser.add_argument("--start", help="Inclusive start date, YYYY-MM-DD. Defaults to old table minimum date.")
    parser.add_argument("--end", help="Inclusive end date, YYYY-MM-DD. Defaults to old table maximum date.")
    parser.add_argument("--apply", action="store_true", help="Write migrated rows. Default is dry-run.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing overview rows for matching date/account keys.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 2

    with connect_db(db_path) as conn:
        print(f"database: {db_path}")
        print_schema(conn)
        result = migrate_metrics_to_overviews(
            conn,
            start=args.start,
            end=args.end,
            apply=args.apply,
            overwrite=args.overwrite,
        )

    mode = "APPLY" if result.apply else "DRY-RUN"
    print(f"\n[{mode} result]")
    print(f"date range: {result.start or '-'} to {result.end or '-'}")
    print(f"legacy metric rows scanned: {result.legacy_metric_rows}")
    print(f"legacy daily rows summarized: {result.legacy_daily_rows}")
    print(f"existing overview keys in range: {result.existing_overview_rows}")
    print(f"rows {'written' if result.apply else 'that would be written'}: {result.inserted}")
    print(f"rows skipped because overview already exists: {result.skipped_existing}")
    print(f"overwrite existing rows: {result.overwrite}")
    if not result.apply:
        print("\nNo data was changed. Re-run with --apply after reviewing this output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
