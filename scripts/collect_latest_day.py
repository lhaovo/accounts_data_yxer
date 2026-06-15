#!/usr/bin/env python3
"""
Collect only the latest available daily YiXiaoEr account metrics into SQLite.

Usage:
  set YIXIAOER_API_KEY=...
  python collect_latest_day.py
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from collect_daily_accounts import (
    APIClient,
    CN_TZ,
    DEFAULT_API_URL,
    DEFAULT_DB,
    account_id,
    content_publish_date,
    content_type,
    init_db,
    ms_to_date,
    ms_to_iso,
    normalize_timestamp_ms,
    numeric_value,
    paged_items,
    store_accounts,
)


def latest_points_by_metric(overview: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    value = overview.get("value") or {}
    if not isinstance(value, dict):
        return latest

    for content_type, metrics in value.items():
        if not isinstance(metrics, list):
            continue
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            metric_key = metric.get("key")
            if not metric_key:
                continue
            metric_name = metric.get("name")
            for point in metric.get("list") or []:
                if not isinstance(point, dict):
                    continue
                metric_ms = normalize_timestamp_ms(point.get("date"))
                metric_value = numeric_value(point.get("value"))
                if metric_ms is None or metric_value is None:
                    continue
                key = (str(content_type), str(metric_key))
                previous = latest.get(key)
                if previous is None or metric_ms > previous["metric_ms"]:
                    latest[key] = {
                        "metric_ms": metric_ms,
                        "content_type": str(content_type),
                        "metric_key": str(metric_key),
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                    }
    return latest


def store_latest_overview(conn: sqlite3.Connection, overview_account: dict[str, Any], collected_at: str) -> int:
    pid = account_id(overview_account)
    if not pid:
        return 0

    overview_raw = overview_account.get("overviewData")
    if not overview_raw:
        return 0

    try:
        overview = json.loads(overview_raw) if isinstance(overview_raw, str) else overview_raw
    except json.JSONDecodeError:
        return 0

    update_ms = normalize_timestamp_ms(overview.get("updateTime"))
    update_time = ms_to_iso(update_ms)
    conn.execute(
        """
        INSERT OR REPLACE INTO account_overview_raw (
            platform_account_id, collected_at, update_time, raw_json
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            pid,
            collected_at,
            update_time,
            json.dumps(overview_account, ensure_ascii=False, sort_keys=True),
        ),
    )

    rows = []
    for point in latest_points_by_metric(overview).values():
        rows.append(
            (
                ms_to_date(point["metric_ms"]),
                pid,
                overview_account.get("platformName"),
                overview_account.get("platformAccountName"),
                point["content_type"],
                point["metric_key"],
                point["metric_name"],
                point["metric_value"],
                collected_at,
                update_time,
            )
        )

    conn.executemany(
        """
        INSERT INTO daily_account_metrics (
            metric_date, platform_account_id, platform_name, platform_account_name,
            content_type, metric_key, metric_name, metric_value, collected_at, update_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(metric_date, platform_account_id, content_type, metric_key) DO UPDATE SET
            platform_name = excluded.platform_name,
            platform_account_name = excluded.platform_account_name,
            metric_name = excluded.metric_name,
            metric_value = excluded.metric_value,
            collected_at = excluded.collected_at,
            update_time = excluded.update_time
        """,
        rows,
    )
    return len(rows)


def day_bounds_ms(date_text: str) -> tuple[int, int]:
    day = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=CN_TZ)
    start_ms = int(day.timestamp() * 1000)
    end_ms = start_ms + 86_400_000 - 1
    return start_ms, end_ms


def store_latest_publish_counts(
    conn: sqlite3.Connection,
    client: APIClient,
    accounts: list[dict[str, Any]],
    collected_at: str,
) -> int:
    # First discover the latest content date visible in the account list.
    latest_date: str | None = None
    first_pages: dict[str, list[dict[str, Any]]] = {}
    for account in accounts:
        pid = account_id(account)
        if not pid:
            continue
        items = paged_items(
            client,
            "/contents/overviews",
            {"platformAccountId": pid, "page": 1, "size": 100},
        )
        first_pages[pid] = items
        for item in items:
            publish_date = content_publish_date(item)
            if publish_date and (latest_date is None or publish_date > latest_date):
                latest_date = publish_date

    if latest_date is None:
        return 0

    start_ms, end_ms = day_bounds_ms(latest_date)
    rows = []
    for account in accounts:
        pid = account_id(account)
        if not pid:
            continue
        items = paged_items(
            client,
            "/contents/overviews",
            {
                "platformAccountId": pid,
                "publishStartTime": start_ms,
                "publishEndTime": end_ms,
                "page": 1,
                "size": 100,
            },
        )
        publish_counts: dict[str, int] = {}
        for item in items:
            publish_date = content_publish_date(item)
            if publish_date != latest_date:
                continue
            ctype = content_type(item)
            publish_counts[ctype] = publish_counts.get(ctype, 0) + 1
        for ctype, count in publish_counts.items():
            rows.append(
                (
                    latest_date,
                    pid,
                    account.get("platformName"),
                    account.get("platformAccountName") or account.get("name") or account.get("nickname"),
                    ctype,
                    "publishCount",
                    "发布数",
                    float(count),
                    collected_at,
                    collected_at,
                )
            )

    conn.executemany(
        """
        INSERT INTO daily_account_metrics (
            metric_date, platform_account_id, platform_name, platform_account_name,
            content_type, metric_key, metric_name, metric_value, collected_at, update_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(metric_date, platform_account_id, content_type, metric_key) DO UPDATE SET
            platform_name = excluded.platform_name,
            platform_account_name = excluded.platform_account_name,
            metric_name = excluded.metric_name,
            metric_value = excluded.metric_value,
            collected_at = excluded.collected_at,
            update_time = excluded.update_time
        """,
        rows,
    )
    return len(rows)


def collect_latest_day(client: APIClient, conn: sqlite3.Connection) -> dict[str, int]:
    started_at = datetime.now(CN_TZ).isoformat(timespec="seconds")
    run_id = conn.execute(
        "INSERT INTO collection_runs (started_at, api_url) VALUES (?, ?)",
        (started_at, client.api_url),
    ).lastrowid

    accounts = paged_items(client, "/v2/platform/accounts", {"page": 1, "size": 1000})
    account_count = store_accounts(conn, accounts, started_at)

    platforms = sorted({account.get("platformName") for account in accounts if account.get("platformName")})
    overview_account_count = 0
    metric_row_count = 0
    for platform in platforms:
        overview_accounts = paged_items(
            client,
            "/platform-accounts/overviews-v2",
            {"platform": platform, "page": 1, "size": 100},
        )
        for overview_account in overview_accounts:
            overview_account_count += 1
            metric_row_count += store_latest_overview(conn, overview_account, started_at)
    metric_row_count += store_latest_publish_counts(conn, client, accounts, started_at)

    finished_at = datetime.now(CN_TZ).isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE collection_runs
        SET finished_at = ?, account_count = ?, overview_account_count = ?, metric_row_count = ?
        WHERE id = ?
        """,
        (finished_at, account_count, overview_account_count, metric_row_count, run_id),
    )
    conn.commit()
    return {
        "run_id": int(run_id),
        "account_count": account_count,
        "overview_account_count": overview_account_count,
        "metric_row_count": metric_row_count,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect only latest available YiXiaoEr daily account metrics into SQLite.")
    parser.add_argument("--api-url", default=os.getenv("YIXIAOER_API_URL", DEFAULT_API_URL))
    parser.add_argument("--api-key", default=os.getenv("YIXIAOER_API_KEY"), help="Defaults to YIXIAOER_API_KEY.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite path. Default: {DEFAULT_DB}")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.api_key:
        print("Missing API key. Set YIXIAOER_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    client = APIClient(api_key=args.api_key.strip(), api_url=args.api_url.strip())
    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        started = time.time()
        result = collect_latest_day(client, conn)
        result["db"] = str(db_path)
        result["elapsed_seconds"] = round(time.time() - started, 2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
