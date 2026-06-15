#!/usr/bin/env python3
"""
Collect YiXiaoEr account overview daily metrics into SQLite.

Usage:
  set YIXIAOER_API_KEY=...
  python collect_daily_accounts.py
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


DEFAULT_API_URL = "https://www.yixiaoer.cn/api"
DEFAULT_DB = Path(__file__).resolve().parent / "data" / "yixiaoer_daily_accounts.sqlite"
CN_TZ = timezone(timedelta(hours=8))

STANDARD_METRIC_MAPPINGS = [
    # standard_key, standard_name, metric_key, metric_name, content_type, platform_name, aggregation, notes
    ("play", "播放/阅读", "playCount", None, None, None, "sum", "不同平台可能叫播放、观看、阅读，跨平台展示时需保留平台口径。"),
    ("read", "阅读", "readCount", None, None, None, "sum", "主要用于动态/图文阅读，不默认并入视频播放。"),
    ("exposure", "曝光/展现", "impressionCount", None, None, None, "sum", "曝光、展现类指标。"),
    ("exposure", "曝光/展现", "recommendCount", None, None, None, "sum", "小红书等平台的曝光数。"),
    ("fans_exposure", "粉丝展现", "fansImpressionCount", None, None, None, "sum", "粉丝展现不默认并入总曝光。"),
    ("like", "点赞", "greatCount", None, None, None, "sum", "多数平台点赞指标。"),
    ("favorite_like", "喜欢", "likeCount", None, None, None, "sum", "视频号喜欢，与点赞分开保留。"),
    ("comment", "评论", "commentCount", None, None, None, "sum", "评论量/评论数/作品评论等。"),
    ("share", "分享/转发", "shareCount", None, None, None, "sum", "分享、转发类指标。"),
    ("collect", "收藏", "collectCount", None, None, None, "sum", "收藏数。"),
    ("interaction", "互动", "interCount", None, None, None, "sum", "新浪微博转评赞总数等聚合互动。"),
    ("net_fans", "净增粉丝/关注", "netFansCount", None, None, None, "sum", "净增粉丝、净增关注、粉丝变化。"),
    ("new_fans", "新增关注", "fansCount", "新增关注", None, None, "sum", "新增关注口径。"),
    ("fans_count", "关注/粉丝数", "fansCount", "关注", None, None, "last", "关注数量快照，不默认与新增关注合并。"),
    ("cancel_fans", "取关/取消关注", "cancelFansCount", None, None, None, "sum", "取关粉丝、取消关注。"),
    ("total_fans", "总粉丝量", "totalFansCount", None, None, None, "last", "总粉丝量快照。"),
    ("homepage_view", "主页访问", "homepageViewCount", None, None, None, "sum", "主页访问/主页访客。"),
    ("homepage_conversion_rate", "主页转粉率", "homeConversionRate", None, None, None, "avg", "比例类指标，汇总时建议取平均或按业务加权。"),
    ("completion_rate", "完播率", "playCompletionRate", None, None, None, "avg", "比例类指标，汇总时建议取平均或按业务加权。"),
    ("cover_click_rate", "封面点击率", "coverClickRatio", None, None, None, "avg", "比例类指标，汇总时建议取平均或按业务加权。"),
    ("avg_play_time", "平均观看时长", "averagePlayTime", None, None, None, "avg", "时长类平均指标。"),
    ("play_duration", "观看总时长", "playDuration", None, None, None, "sum", "观看总时长。"),
    ("work_count", "作品数", "workCount", None, None, None, "sum", "发博总数、视频发布总数等。"),
    ("publish_count", "发布数", "publishCount", None, None, None, "sum", "由 /contents/overviews 按账号和发布时间统计得到。"),
]


@dataclass(frozen=True)
class APIClient:
    api_key: str
    api_url: str = DEFAULT_API_URL
    timeout: int = 60

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.api_url.rstrip("/") + "/" + path.lstrip("/")
        if params:
            clean_params = {
                key: value
                for key, value in params.items()
                if value is not None and value != ""
            }
            if clean_params:
                url += "?" + urlencode(clean_params, doseq=True)

        req = Request(
            url,
            headers={
                "Authorization": self.api_key,
                "Content-Type": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"HTTP request failed for {url}: {exc}") from exc

        payload = json.loads(body)
        status_code = payload.get("statusCode")
        if status_code not in (None, 0):
            raise RuntimeError(f"YiXiaoEr API error statusCode={status_code}: {payload}")
        return payload


def data_body(payload: dict[str, Any]) -> Any:
    return payload.get("data", payload)


def paged_items(client: APIClient, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    params = dict(params or {})
    params.setdefault("page", 1)
    params.setdefault("size", 100)

    all_items: list[dict[str, Any]] = []
    page = int(params["page"])
    total_page = 1
    while page <= total_page:
        params["page"] = page
        payload = client.get(path, params)
        body = data_body(payload)
        if isinstance(body, list):
            items = body
            total_page = page
        elif isinstance(body, dict):
            items = (
                body.get("data")
                or body.get("list")
                or body.get("records")
                or body.get("items")
                or body.get("rows")
                or []
            )
            total_page = int(body.get("totalPage") or body.get("pages") or page)
        else:
            items = []
            total_page = page

        all_items.extend(item for item in items if isinstance(item, dict))
        page += 1
    return all_items


def normalize_timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None
    try:
        ts = int(float(value))
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    if ts < 100_000_000_000:
        ts *= 1000
    return ts


def ms_to_date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, CN_TZ).date().isoformat()


def ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, CN_TZ).isoformat(timespec="seconds")


def numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;

        CREATE TABLE IF NOT EXISTS collection_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            api_url TEXT NOT NULL,
            account_count INTEGER DEFAULT 0,
            overview_account_count INTEGER DEFAULT 0,
            metric_row_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS accounts (
            platform_account_id TEXT PRIMARY KEY,
            platform_name TEXT,
            platform_account_name TEXT,
            platform_author_id TEXT,
            status INTEGER,
            parent_id TEXT,
            principal_name TEXT,
            raw_json TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS account_overview_raw (
            platform_account_id TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            update_time TEXT,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (platform_account_id, collected_at)
        );

        CREATE TABLE IF NOT EXISTS daily_account_metrics (
            metric_date TEXT NOT NULL,
            platform_account_id TEXT NOT NULL,
            platform_name TEXT,
            platform_account_name TEXT,
            content_type TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            metric_name TEXT,
            metric_value REAL,
            collected_at TEXT NOT NULL,
            update_time TEXT,
            PRIMARY KEY (metric_date, platform_account_id, content_type, metric_key)
        );

        CREATE INDEX IF NOT EXISTS idx_daily_account_metrics_date
            ON daily_account_metrics(metric_date);
        CREATE INDEX IF NOT EXISTS idx_daily_account_metrics_account
            ON daily_account_metrics(platform_account_id);
        CREATE INDEX IF NOT EXISTS idx_daily_account_metrics_metric
            ON daily_account_metrics(metric_key);

        CREATE TABLE IF NOT EXISTS metric_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            standard_key TEXT NOT NULL,
            standard_name TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            metric_name TEXT NOT NULL DEFAULT '',
            content_type TEXT NOT NULL DEFAULT '',
            platform_name TEXT NOT NULL DEFAULT '',
            aggregation TEXT NOT NULL DEFAULT 'sum',
            notes TEXT,
            UNIQUE (metric_key, metric_name, content_type, platform_name)
        );
        """
    )
    seed_metric_mappings(conn)


def seed_metric_mappings(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO metric_mappings (
            standard_key, standard_name, metric_key, metric_name,
            content_type, platform_name, aggregation, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                standard_key,
                standard_name,
                metric_key,
                metric_name or "",
                content_type or "",
                platform_name or "",
                aggregation,
                notes,
            )
            for (
                standard_key,
                standard_name,
                metric_key,
                metric_name,
                content_type,
                platform_name,
                aggregation,
                notes,
            ) in STANDARD_METRIC_MAPPINGS
        ],
    )


def account_id(account: dict[str, Any]) -> str:
    value = account.get("platformAccountId") or account.get("id")
    return "" if value is None else str(value)


def store_accounts(conn: sqlite3.Connection, accounts: list[dict[str, Any]], seen_at: str) -> int:
    rows = []
    for account in accounts:
        pid = account_id(account)
        if not pid:
            continue
        rows.append(
            (
                pid,
                account.get("platformName"),
                account.get("platformAccountName") or account.get("name") or account.get("nickname"),
                account.get("platformAuthorId"),
                account.get("status") if account.get("status") is not None else account.get("loginStatus"),
                account.get("parentId"),
                account.get("principalName"),
                json.dumps(account, ensure_ascii=False, sort_keys=True),
                seen_at,
            )
        )
    conn.executemany(
        """
        INSERT INTO accounts (
            platform_account_id, platform_name, platform_account_name, platform_author_id,
            status, parent_id, principal_name, raw_json, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform_account_id) DO UPDATE SET
            platform_name = excluded.platform_name,
            platform_account_name = excluded.platform_account_name,
            platform_author_id = excluded.platform_author_id,
            status = excluded.status,
            parent_id = excluded.parent_id,
            principal_name = excluded.principal_name,
            raw_json = excluded.raw_json,
            last_seen_at = excluded.last_seen_at
        """,
        rows,
    )
    return len(rows)


def store_overview(conn: sqlite3.Connection, overview_account: dict[str, Any], collected_at: str) -> int:
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
    value = overview.get("value") or {}
    if not isinstance(value, dict):
        return 0

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
                rows.append(
                    (
                        ms_to_date(metric_ms),
                        pid,
                        overview_account.get("platformName"),
                        overview_account.get("platformAccountName"),
                        content_type,
                        str(metric_key),
                        metric_name,
                        metric_value,
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


def content_publish_date(item: dict[str, Any]) -> str | None:
    content_data = item.get("contentData")
    if not isinstance(content_data, dict):
        return None
    raw_date = content_data.get("date")
    if not raw_date:
        return None
    text = str(raw_date).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt).date().isoformat()
        except ValueError:
            continue
    return text[:10] if len(text) >= 10 else None


def content_type(item: dict[str, Any]) -> str:
    content_data = item.get("contentData")
    if isinstance(content_data, dict) and content_data.get("type"):
        return str(content_data.get("type"))
    if item.get("type"):
        return str(item.get("type"))
    return "all"


def store_publish_counts(
    conn: sqlite3.Connection,
    client: APIClient,
    accounts: list[dict[str, Any]],
    collected_at: str,
    ) -> int:
    rows = []
    for account in accounts:
        pid = account_id(account)
        if not pid:
            continue
        items = paged_items(
            client,
            "/contents/overviews",
            {"platformAccountId": pid, "page": 1, "size": 100},
        )
        publish_counts: dict[tuple[str, str], int] = {}
        for item in items:
            publish_date = content_publish_date(item)
            if not publish_date:
                continue
            ctype = content_type(item)
            key = (publish_date, ctype)
            publish_counts[key] = publish_counts.get(key, 0) + 1
        for (publish_date, ctype), count in publish_counts.items():
            rows.append(
                (
                    publish_date,
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


def collect(client: APIClient, conn: sqlite3.Connection) -> dict[str, int]:
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
            metric_row_count += store_overview(conn, overview_account, started_at)
    metric_row_count += store_publish_counts(conn, client, accounts, started_at)

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
    parser = argparse.ArgumentParser(description="Collect YiXiaoEr daily account overview metrics into SQLite.")
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
        result = collect(client, conn)
        result["db"] = str(db_path)
        result["elapsed_seconds"] = round(time.time() - started, 2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
