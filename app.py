#!/usr/bin/env python3
"""
Local web service for YiXiaoEr account metrics stored in SQLite.

Run:
  python app.py --host 127.0.0.1 --port 8787

Optional environment variables:
  YIXIAOER_DB_PATH       SQLite database path.
  YIXIAOER_SCRIPTS_DIR  Directory containing collector scripts.
  YIXIAOER_API_KEY      API key used by refresh endpoints.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sqlite3
import urllib.request
import sys
import threading
import traceback
from datetime import date, datetime, timezone, timedelta
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from time import sleep, time as time_now
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SETTINGS_PATH = ROOT / "config" / "settings.json"
DEFAULT_DB_CANDIDATES = [
    ROOT / "data" / "yixiaoer_daily_accounts.sqlite",
]
DEFAULT_SCRIPTS_DIR = ROOT / "scripts"

REPORT_COLUMNS = [
    "metric_date",
    "platform_name",
    "platform_account_name",
    "platform_account_id",
    "login_status",
    "fans",
    "play",
    "read",
    "like",
    "comment",
    "collect",
    "publish_count",
]

STANDARD_KEYS = [
    "total_fans",
    "fans_count",
    "net_fans",
    "new_fans",
    "play",
    "read",
    "exposure",
    "like",
    "favorite_like",
    "comment",
    "share",
    "collect",
    "publish_count",
]





CN_TZ = timezone(timedelta(hours=8))


def ms_day_bounds(date_str: str) -> tuple[int, int]:
    day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CN_TZ)
    return int(day.timestamp() * 1000), int(day.timestamp() * 1000) + 86_399_999


def recent_dates(days: int) -> list[str]:
    today = datetime.now(CN_TZ).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(1, days + 1)]


def fetch_dates_for_mode(mode: str, today: date | None = None) -> list[str]:
    today = today or datetime.now(CN_TZ).date()
    latest_complete_day = today - timedelta(days=1)
    if mode == "all":
        start = date(2026, 4, 1)
        if latest_complete_day < start:
            return []
        days = (latest_complete_day - start).days + 1
        return [(start + timedelta(days=i)).isoformat() for i in range(days)]
    if mode == "full":
        return [(today - timedelta(days=i)).isoformat() for i in range(1, 31)]
    return [(today - timedelta(days=i)).isoformat() for i in range(1, 4)]


# Background fetch state -----------------------------------------------------------------

_FETCH_STATE: dict[str, Any] = {
    "running": False,
    "mode": "",
    "current": 0,
    "total": 0,
    "currentDate": "",
    "error": "",
    "result": None,
}
_FETCH_LOCK = threading.Lock()
EXTERNAL_REQUEST_INTERVAL_SECONDS = 1


def start_fetch_state(mode: str, total: int) -> bool:
    with _FETCH_LOCK:
        if _FETCH_STATE["running"]:
            return False
        _FETCH_STATE["running"] = True
        _FETCH_STATE["mode"] = mode
        _FETCH_STATE["current"] = 0
        _FETCH_STATE["total"] = total
        _FETCH_STATE["currentDate"] = ""
        _FETCH_STATE["error"] = ""
        _FETCH_STATE["result"] = None
    return True


def _overview_table_ddl() -> str:
    return """
CREATE TABLE IF NOT EXISTS daily_account_overviews (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_date           TEXT NOT NULL,
    platform_name         TEXT NOT NULL,
    platform_account_name TEXT NOT NULL,
    platform_account_id   TEXT NOT NULL,
    login_status          INTEGER,
    fans                  REAL,
    play                  REAL,
    like_count            REAL,
    comment_count         REAL,
    collect_count         REAL,
    publish_count         REAL,
    collected_at          TEXT NOT NULL,
    UNIQUE(metric_date, platform_account_id)
)"""


def throttled_urlopen(request: urllib.request.Request, timeout: int = 30):
    sleep(EXTERNAL_REQUEST_INTERVAL_SECONDS)
    return urllib.request.urlopen(request, timeout=timeout)


def resolve_db_path() -> Path:
    env_path = os.environ.get("YIXIAOER_DB_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    for path in DEFAULT_DB_CANDIDATES:
        if path.exists():
            return path.resolve()
    return DEFAULT_DB_CANDIDATES[0].resolve()


def scripts_dir() -> Path:
    env_path = os.environ.get("YIXIAOER_SCRIPTS_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_SCRIPTS_DIR.resolve()


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stored_api_key() -> str:
    env_key = (os.environ.get("YIXIAOER_API_KEY") or "").strip()
    # 忽略占位值，回落 settings.json
    if env_key and env_key not in ("your_api_key_here", "your_api_key", "xxx", "changeme"):
        return env_key
    value = load_settings().get("apiKey") or ""
    return str(value).strip()


def settings_payload() -> dict[str, Any]:
    return {
        "hasApiKey": bool(stored_api_key()),
        "usesEnvironmentApiKey": bool(os.environ.get("YIXIAOER_API_KEY")),
        "hasSettingsKey": bool(load_settings().get("apiKey")),
    }


def parse_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def status_text(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "-"
    if number == 1:
        return "正常"
    if number == 2:
        return "登录过期"
    return "未知"


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def apply_value(current: float | None, value: float | None, aggregation: str) -> float | None:
    if value is None:
        return current
    if current is None:
        return value
    if aggregation == "last":
        return value
    if aggregation == "avg":
        return (current + value) / 2
    return current + value


def connect_db() -> sqlite3.Connection:
    db_path = resolve_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def query_metric_rows(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    platforms: list[str] | None,
    account_ids: list[str] | None,
) -> list[sqlite3.Row]:
    params: list[Any] = [start, end]
    filters = ["m.metric_date BETWEEN ? AND ?"]
    if platforms:
        placeholders_p = ",".join("?" for _ in platforms)
        filters.append(f"m.platform_name IN ({placeholders_p})")
        params.extend(platforms)
    if account_ids:
        placeholders_ids = ",".join("?" for _ in account_ids)
        filters.append(f"m.platform_account_id IN ({placeholders_ids})")
        params.extend(account_ids)
    placeholders = ",".join("?" for _ in STANDARD_KEYS)
    params.extend(STANDARD_KEYS)
    where = " AND ".join(filters)
    return conn.execute(
        f"""
        SELECT
            m.metric_date,
            m.platform_name,
            m.platform_account_name,
            m.platform_account_id,
            m.content_type,
            m.metric_key,
            m.metric_name,
            m.metric_value,
            a.status AS login_status,
            COALESCE(mm.standard_key, m.metric_key) AS standard_key,
            COALESCE(mm.standard_name, m.metric_name) AS standard_name,
            COALESCE(mm.aggregation, 'sum') AS aggregation
        FROM daily_account_metrics m
        LEFT JOIN accounts a ON a.platform_account_id = m.platform_account_id
        LEFT JOIN metric_mappings mm
          ON mm.metric_key = m.metric_key
         AND (mm.metric_name = m.metric_name OR mm.metric_name = '')
         AND (mm.content_type = m.content_type OR mm.content_type = '')
         AND (mm.platform_name = m.platform_name OR mm.platform_name = '')
        WHERE {where}
          AND COALESCE(mm.standard_key, m.metric_key) IN ({placeholders})
        ORDER BY m.metric_date, m.platform_name, m.platform_account_name, m.platform_account_id
        """,
        params,
    ).fetchall()

def empty_rows(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    platforms: list[str] | None,
    account_ids: list[str] | None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    filters = ["1 = 1"]
    if platforms:
        placeholders_p = ",".join("?" for _ in platforms)
        filters.append(f"platform_name IN ({placeholders_p})")
        params.extend(platforms)
    if account_ids:
        placeholders_ids = ",".join("?" for _ in account_ids)
        filters.append(f"platform_account_id IN ({placeholders_ids})")
        params.extend(account_ids)
    accounts = conn.execute(
        f"""
        SELECT platform_name, platform_account_name, platform_account_id, status AS login_status
        FROM accounts
        WHERE {" AND ".join(filters)}
        ORDER BY platform_account_name, platform_account_id
        """,
        params,
    ).fetchall()
    dates = conn.execute(
        """
        WITH RECURSIVE dates(d) AS (
          SELECT date(?)
          UNION ALL
          SELECT date(d, '+1 day') FROM dates WHERE d < date(?)
        )
        SELECT d FROM dates
        """,
        (start, end),
    ).fetchall()
    result = []
    for date_row in dates:
        for account in accounts:
            result.append(
                {
                    "metric_date": date_row["d"],
                    "platform_name": account["platform_name"],
                    "platform_account_name": account["platform_account_name"],
                    "platform_account_id": account["platform_account_id"],
                    "login_status": account["login_status"],
                    "fans": None,
                    "play": None,
                    "exposure": None,
                    "like": None,
                    "comment": None,
                    "share": None,
                    "collect": None,
                    "publish_count": None,
                }
            )
    return result

def summarize(rows: list[sqlite3.Row], base: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in base or []:
        result[(item["metric_date"], item["platform_account_id"])] = dict(item)

    for row in rows:
        key = (row["metric_date"], row["platform_account_id"])
        item = result.setdefault(
            key,
            {
                "metric_date": row["metric_date"],
                "platform_name": row["platform_name"],
                "platform_account_name": row["platform_account_name"],
                "platform_account_id": row["platform_account_id"],
                "login_status": row["login_status"],
                "fans": None,
                "play": None,
                "exposure": None,
                "like": None,
                "comment": None,
                "share": None,
                "collect": None,
                "publish_count": None,
            },
        )
        standard_key = row["standard_key"]
        value = row["metric_value"]
        aggregation = row["aggregation"]
        if standard_key in ("net_fans", "new_fans"):
            item["fans"] = apply_value(item["fans"], value, aggregation)
        elif standard_key == "play":
            item["play"] = apply_value(item["play"], value, aggregation)
        elif standard_key == "read":
            item["play"] = apply_value(item["play"], value, aggregation)
        elif standard_key == "exposure":
            item["exposure"] = apply_value(item["exposure"], value, aggregation)
        elif standard_key in ("like", "favorite_like"):
            item["like"] = apply_value(item["like"], value, aggregation)
        elif standard_key == "comment":
            item["comment"] = apply_value(item["comment"], value, aggregation)
        elif standard_key == "share":
            item["share"] = apply_value(item["share"], value, aggregation)
        elif standard_key == "collect":
            item["collect"] = apply_value(item["collect"], value, aggregation)
        elif standard_key == "publish_count":
            item["publish_count"] = apply_value(item["publish_count"], value, aggregation)

    return sorted(
        result.values(),
        key=lambda x: (
            x["metric_date"],
            x["platform_name"] or "",
            x["platform_account_name"] or "",
            x["platform_account_id"] or "",
        ),
    )

def _merge_accounts(rows):
    merged = {}
    for row in rows:
        pid = row["platform_account_id"]
        if pid not in merged:
            merged[pid] = {
                "metric_date": row["metric_date"],
                "platform_name": row["platform_name"],
                "platform_account_name": row["platform_account_name"],
                "platform_account_id": pid,
                "login_status": row["login_status"],
                "fans": 0.0,
                "play": 0.0,
                "exposure": 0.0,
                "like": 0.0,
                "comment": 0.0,
                "share": 0.0,
                "collect": 0.0,
                "publish_count": 0.0,
                "_has_data": False,
            }
        m = merged[pid]
        for key in ("fans", "play", "exposure", "like", "comment", "share", "collect", "publish_count"):
            val = row.get(key)
            if val is not None:
                m[key] = float(m[key]) + float(val)
                m["_has_data"] = True
        if row.get("login_status") and row["login_status"] != "-":
            m["login_status"] = row["login_status"]
    for m in merged.values():
        if not m["_has_data"]:
            for key in ("fans", "play", "exposure", "like", "comment", "share", "collect", "publish_count"):
                m[key] = None
        m.pop("_has_data", None)
    return sorted(merged.values(), key=lambda x: (x["platform_name"] or "", x["platform_account_name"] or ""))


OVERVIEW_COLUMNS_MAP = {
    "fans": "fans",
    "play": "play",
    "like_count": "like",
    "comment_count": "comment",
    "collect_count": "collect",
    "publish_count": "publish_count",
}


def query_overview_rows(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    platforms: list[str] | None,
    account_ids: list[str] | None,
) -> list[dict[str, Any]]:
    params: list[Any] = [start, end]
    filters = ["metric_date BETWEEN ? AND ?"]
    if platforms:
        placeholders = ",".join("?" for _ in platforms)
        filters.append(f"platform_name IN ({placeholders})")
        params.extend(platforms)
    if account_ids:
        placeholders = ",".join("?" for _ in account_ids)
        filters.append(f"platform_account_id IN ({placeholders})")
        params.extend(account_ids)
    where = " AND ".join(filters)
    rows = conn.execute(
        f"""
        SELECT metric_date, platform_name, platform_account_name,
               platform_account_id, login_status,
               fans, play, like_count, comment_count, collect_count, publish_count
        FROM daily_account_overviews
        WHERE {where}
        ORDER BY metric_date, platform_name, platform_account_name, platform_account_id
        """,
        params,
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append({
            "metric_date": row["metric_date"],
            "platform_name": row["platform_name"],
            "platform_account_name": row["platform_account_name"],
            "platform_account_id": row["platform_account_id"],
            "login_status": row["login_status"],
            "fans": row["fans"],
            "play": row["play"],
            "exposure": None,
            "like": row["like_count"],
            "comment": row["comment_count"],
            "share": None,
            "collect": row["collect_count"],
            "publish_count": row["publish_count"],
        })
    return result


def overlay_rows(base: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = {(row["metric_date"], row["platform_account_id"]): dict(row) for row in base}
    for row in rows:
        result[(row["metric_date"], row["platform_account_id"])] = dict(row)
    return sorted(
        result.values(),
        key=lambda x: (
            x["metric_date"],
            x["platform_name"] or "",
            x["platform_account_name"] or "",
            x["platform_account_id"] or "",
        ),
    )


def display_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    result = []
    for row in rows:
        result.append({col: status_text(row.get(col)) if col == "login_status" else format_value(row.get(col)) for col in REPORT_COLUMNS})
    return result


def status_payload() -> dict[str, Any]:
    db_path = resolve_db_path()
    payload: dict[str, Any] = {
        "dbPath": str(db_path),
        "dbExists": db_path.exists(),
        "scriptsDir": str(scripts_dir()),
        "scriptsDirExists": scripts_dir().exists(),
    }
    if not db_path.exists():
        return payload
    conn = connect_db()
    try:
        overview_dates = conn.execute("SELECT min(metric_date) AS minDate, max(metric_date) AS maxDate FROM daily_account_overviews").fetchone()
        payload["dateRange"] = dict(
            overview_dates
        ) if overview_dates else {"minDate": None, "maxDate": None}
        payload["platforms"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT platform_name AS name, count(DISTINCT platform_account_id) AS accountCount
                FROM accounts
                GROUP BY platform_name
                ORDER BY platform_name
                """
            )
        ]
        payload["accountCount"] = conn.execute("SELECT count(*) FROM accounts").fetchone()[0]
        payload["accounts"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT platform_account_id, platform_name, platform_account_name
                FROM accounts ORDER BY platform_account_name
                """
            )
        ]
        payload["metricCount"] = conn.execute("SELECT count(*) FROM daily_account_overviews").fetchone()[0]
        payload["overviewRowCount"] = conn.execute("SELECT count(*) FROM daily_account_overviews").fetchone()[0]
        payload["overviewDateRange"] = dict(overview_dates) if overview_dates else None
    finally:
        conn.close()
    return payload


# ---------------------------------------------------------------------------
# Auto-refresh scheduler
# ---------------------------------------------------------------------------

SCHEDULER_LOCK = threading.RLock()

class Scheduler:
    def __init__(self) -> None:
        self._timer: threading.Timer | None = None
        self._enabled = False
        self._interval_minutes = 360
        self._mode = "latest"
        self._pre_refresh = False
        self._next_run: float | None = None
        self._last_run: str | None = None
        self._last_result: dict[str, Any] | None = None
        self._load_config()
        if self._enabled:
            self._start()

    def _load_config(self) -> None:
        cfg = load_settings().get("schedule", {})
        if isinstance(cfg, dict):
            self._enabled = bool(cfg.get("enabled"))
            self._interval_minutes = max(5, int(cfg.get("intervalMinutes") or 360))
            self._mode = cfg.get("mode") if cfg.get("mode") in ("latest", "full") else "latest"
            self._pre_refresh = bool(cfg.get("preRefresh"))
            self._last_run = cfg.get("lastRun")
            self._next_run = cfg.get("nextRun")

    def _save_config(self) -> None:
        with SCHEDULER_LOCK:
            settings = load_settings()
            settings["schedule"] = {
                "enabled": self._enabled,
                "intervalMinutes": self._interval_minutes,
                "mode": self._mode,
                "preRefresh": self._pre_refresh,
                "lastRun": self._last_run,
                "nextRun": self._next_run,
            }
            save_settings(settings)

    def _start(self) -> None:
        if self._timer:
            self._timer.cancel()
        delay = self._next_run - time_now() if self._next_run else 0
        if delay <= 0:
            delay = self._interval_minutes * 60
            self._next_run = time_now() + delay
        self._timer = threading.Timer(delay, self._run)
        self._timer.daemon = True
        self._timer.start()
        self._save_config()

    def _stop(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._next_run = None

    def _run(self) -> None:
        with SCHEDULER_LOCK:
            if not self._enabled:
                return
        try:
            result = _execute_refresh(self._mode, pre_refresh=self._pre_refresh)
            self._last_run = datetime.now(CN_TZ).isoformat(timespec="seconds")
            self._last_result = result
        except Exception as exc:
            self._last_run = datetime.now(CN_TZ).isoformat(timespec="seconds")
            self._last_result = {"ok": False, "error": str(exc)}
        with SCHEDULER_LOCK:
            if self._enabled:
                delay = self._interval_minutes * 60
                self._next_run = time_now() + delay
                self._timer = threading.Timer(delay, self._run)
                self._timer.daemon = True
                self._timer.start()
            else:
                self._timer = None
                self._next_run = None
        self._save_config()

    def update(self, enabled: bool, interval_minutes: int, mode: str, pre_refresh: bool = False) -> None:
        with SCHEDULER_LOCK:
            self._enabled = enabled
            self._interval_minutes = max(5, interval_minutes)
            self._mode = mode if mode in ("latest", "full") else "latest"
            self._pre_refresh = pre_refresh
            self._stop()
            if self._enabled:
                self._start()
            self._save_config()

    def status(self) -> dict[str, Any]:
        with SCHEDULER_LOCK:
            return {
                "enabled": self._enabled,
                "intervalMinutes": self._interval_minutes,
                "mode": self._mode,
                "preRefresh": self._pre_refresh,
                "nextRun": self._next_run,
                "lastRun": self._last_run,
                "lastResult": self._last_result,
            }


_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


def load_refresh_account_ids(account_ids: list[str] | None = None) -> list[str]:
    conn = connect_db()
    try:
        if account_ids:
            placeholders = ",".join("?" for _ in account_ids)
            rows = conn.execute(
                f"SELECT platform_account_id FROM accounts WHERE platform_account_id IN ({placeholders})",
                account_ids,
            ).fetchall()
        else:
            rows = conn.execute("SELECT platform_account_id FROM accounts").fetchall()
    finally:
        conn.close()
    return [row["platform_account_id"] for row in rows]


def _refresh_accounts_for_overview(
    api_key: str,
    account_ids: list[str] | None = None,
    track_progress: bool = False,
    state_started: bool = False,
) -> dict[str, int | bool]:
    platform_account_ids = load_refresh_account_ids(account_ids)
    triggered = 0
    skipped = 0
    errors = 0
    total = len(platform_account_ids)
    if track_progress and not state_started and not start_fetch_state("refresh-accounts", total):
        return {"ok": False, "triggered": 0, "skipped": 0, "errors": 0}
    try:
        for pid in platform_account_ids:
            if track_progress:
                with _FETCH_LOCK:
                    _FETCH_STATE["currentDate"] = pid
            url = f"https://www.yixiaoer.cn/api/platform-accounts/{pid}/overview"
            req = urllib.request.Request(url, headers={"Authorization": api_key}, method="PUT")
            try:
                throttled_urlopen(req, timeout=15)
                triggered += 1
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    skipped += 1
                else:
                    errors += 1
            except Exception:
                errors += 1
            finally:
                if track_progress:
                    with _FETCH_LOCK:
                        _FETCH_STATE["current"] += 1
    finally:
        result = {"ok": True, "triggered": triggered, "skipped": skipped, "errors": errors}
        if track_progress:
            with _FETCH_LOCK:
                _FETCH_STATE["running"] = False
                _FETCH_STATE["currentDate"] = ""
                _FETCH_STATE["error"] = ""
                _FETCH_STATE["result"] = result
    return {"ok": True, "triggered": triggered, "skipped": skipped, "errors": errors}


def _execute_refresh(mode: str, pre_refresh: bool = False, pre_refresh_wait_seconds: int = 60) -> dict[str, Any]:
    api_key = stored_api_key()
    if not api_key:
        return {"ok": False, "error": "missing apiKey"}
    fetch_mode = "full" if mode == "full" else "recent"
    dates = fetch_dates_for_mode(fetch_mode)
    if not start_fetch_state(fetch_mode, len(dates)):
        return {"ok": False, "mode": fetch_mode, "preRefresh": None, "result": None, "error": "已有任务正在运行，请等待完成"}
    pre_refresh_result = None
    try:
        if pre_refresh:
            pre_refresh_result = _refresh_accounts_for_overview(api_key)
            sleep(pre_refresh_wait_seconds)
        _run_fetch(fetch_mode, api_key, resolve_db_path(), dates, True)
        with _FETCH_LOCK:
            result = dict(_FETCH_STATE)
        return {
            "ok": not result.get("error"),
            "mode": fetch_mode,
            "preRefresh": pre_refresh_result,
            "result": result.get("result"),
            "error": result.get("error"),
        }
    except Exception as exc:
        with _FETCH_LOCK:
            _FETCH_STATE["running"] = False
            _FETCH_STATE["error"] = str(exc)
            _FETCH_STATE["result"] = None
        return {"ok": False, "mode": fetch_mode, "preRefresh": pre_refresh_result, "result": None, "error": str(exc)}


def schedule_payload() -> dict[str, Any]:
    return get_scheduler().status()


def store_overview_payload(conn: sqlite3.Connection, date_str: str, payload: dict[str, Any], collected_at: str) -> int:
    accounts = payload.get("accounts") or []
    written = 0
    for a in accounts:
        account_id = a.get("platformAccountId") or ""
        incoming_play = a.get("playTotal")
        existing = conn.execute(
            """
            SELECT play
            FROM daily_account_overviews
            WHERE metric_date = ? AND platform_account_id = ?
            """,
            (date_str, account_id),
        ).fetchone()
        if existing is not None:
            existing_play = existing["play"] if isinstance(existing, sqlite3.Row) else existing[0]
            existing_value = float(existing_play or 0)
            incoming_value = float(incoming_play or 0)
            if existing_value >= incoming_value:
                continue

        conn.execute(
            """
            INSERT OR REPLACE INTO daily_account_overviews (
                metric_date, platform_name, platform_account_name,
                platform_account_id, login_status,
                fans, play, like_count, comment_count,
                collect_count, publish_count, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
            date_str,
            a.get("platformName") or "",
            a.get("platformAccountName") or "",
            account_id,
            a.get("status"),
            a.get("fansTotal"),
            incoming_play,
            a.get("likesTotal"),
            a.get("commentsTotal"),
            a.get("favoritesTotal"),
            a.get("publishTotal"),
            collected_at,
            ),
        )
        written += 1
    return written



def _run_fetch(
    mode: str,
    api_key: str,
    db_path: Path,
    dates: list[str] | None = None,
    state_started: bool = False,
) -> None:
    from datetime import datetime as dt
    dates = dates or fetch_dates_for_mode(mode)
    if not state_started and not start_fetch_state(mode, len(dates)):
        return
    total_accounts = 0
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute(_overview_table_ddl())
        conn.commit()
        for date_str in dates:
            with _FETCH_LOCK:
                _FETCH_STATE["currentDate"] = date_str
            start_ms, end_ms = ms_day_bounds(date_str)
            url = (
                "https://www.yixiaoer.cn/api/overview/incremental"
                f"?startTime={start_ms}&endTime={end_ms}"
            )
            req = urllib.request.Request(url, headers={"Authorization": api_key})
            try:
                resp = throttled_urlopen(req, timeout=30)
                data = json.loads(resp.read())
            except Exception as exc:
                with _FETCH_LOCK:
                    _FETCH_STATE["error"] = f"{date_str}: {exc}"
                    _FETCH_STATE["current"] += 1
                continue
            payload = data.get("data") if isinstance(data, dict) else None
            if not payload:
                with _FETCH_LOCK:
                    _FETCH_STATE["current"] += 1
                continue
            collected_at = dt.now(CN_TZ).isoformat(timespec="seconds")
            rows_written = store_overview_payload(conn, date_str, payload, collected_at)
            conn.commit()
            total_accounts += rows_written
            with _FETCH_LOCK:
                _FETCH_STATE["current"] += 1
    except Exception as exc:
        with _FETCH_LOCK:
            _FETCH_STATE["error"] = str(exc)
    finally:
        if conn is not None:
            conn.close()
        with _FETCH_LOCK:
            _FETCH_STATE["running"] = False
            _FETCH_STATE["result"] = {
                "daysFetched": _FETCH_STATE["current"],
                "accountsWritten": total_accounts,
            }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "YiXiaoErAccountService/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", file=sys.stderr)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str, detail: str | None = None) -> None:
        payload = {"error": {"message": message}}
        if detail:
            payload["error"]["detail"] = detail
        self.send_json(payload, status)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length == 0:
            return {}
        data = self.rfile.read(length).decode("utf-8")
        return json.loads(data) if data else {}

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.serve_static("index.html")
            elif parsed.path.startswith("/static/"):
                self.serve_static(parsed.path.removeprefix("/static/"))
            elif parsed.path == "/api/status":
                self.send_json(status_payload())
            elif parsed.path == "/api/merge-accounts":
                self.handle_merge_accounts()
            elif parsed.path == "/api/schedule":
                self.handle_schedule()
            elif parsed.path == "/api/account-detail":
                self.handle_account_detail()
            elif parsed.path == "/api/settings":
                self.send_json(settings_payload())
            elif parsed.path == "/api/fetch-status":
                self.handle_fetch_status()
            elif parsed.path == "/api/metrics":
                self.handle_metrics(parsed.query)
            elif parsed.path == "/api/export.csv":
                self.handle_csv(parsed.query)
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "not found")
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc), traceback.format_exc())

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/refresh":
                self.handle_refresh()
            elif parsed.path == "/api/fetch":
                self.handle_fetch()
            elif parsed.path == "/api/refresh-accounts":
                self.handle_refresh_accounts()
            elif parsed.path == "/api/merge-accounts":
                self.handle_merge_accounts()
            elif parsed.path == "/api/schedule":
                self.handle_schedule()
            elif parsed.path == "/api/settings":
                self.handle_settings()
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "not found")
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc), traceback.format_exc())

    def serve_static(self, name: str) -> None:
        safe_name = name.replace("\\", "/").lstrip("/")
        path = (STATIC_DIR / safe_name).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.exists() or path.is_dir():
            self.send_error_json(HTTPStatus.NOT_FOUND, "static file not found")
            return
        content_type = "text/html; charset=utf-8"
        if path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def query_rows_from_params(self, query: str) -> list[dict[str, Any]]:
        params = parse_qs(query)
        date_value = (params.get("date") or [""])[0].strip()
        start_value = (params.get("start") or [""])[0].strip()
        end_value = (params.get("end") or [""])[0].strip()
        if date_value:
            start = end = parse_date(date_value)
        else:
            start = parse_date(start_value)
            end = parse_date(end_value)
        if start > end:
            raise ValueError("start must be <= end")
        platform_raw = (params.get("platforms") or [""])[0].strip()
        platforms = [p.strip() for p in platform_raw.split(",") if p.strip()] if platform_raw else None
        account_id_raw = (params.get("accountIds") or [""])[0].strip()
        account_ids = [a.strip() for a in account_id_raw.split(",") if a.strip()] if account_id_raw else None
        include_empty = (params.get("includeEmpty") or ["0"])[0] in ("1", "true", "yes")
        merge = (params.get("merge") or ["0"])[0] in ("1", "true", "yes")

        conn = connect_db()
        try:
            overview_rows = query_overview_rows(conn, start, end, platforms, account_ids)
            if include_empty:
                overview_rows = overlay_rows(empty_rows(conn, start, end, platforms, account_ids), overview_rows)
        finally:
            conn.close()

        if merge:
            return _merge_accounts(overview_rows)
        return overview_rows

    def handle_metrics(self, query: str) -> None:
        rows = self.query_rows_from_params(query)
        self.send_json({"rows": display_rows(rows), "rawRows": rows, "count": len(rows), "columns": REPORT_COLUMNS})

    def handle_csv(self, query: str) -> None:
        rows = display_rows(self.query_rows_from_params(query))
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        body = buffer.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="yixiaoer-account-metrics.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)



    def handle_merge_accounts(self) -> None:
        body = self.read_json_body()
        from_id = str(body.get("fromId") or "").strip()
        to_id = str(body.get("toId") or "").strip()
        to_name = str(body.get("toName") or "").strip()
        if not from_id or not to_id:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "missing fromId or toId")
            return
        if from_id == to_id:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "fromId and toId must be different")
            return
        conn = connect_db()
        try:
            # Delete target rows for overlapping dates to avoid UNIQUE conflict
            conn.execute(
                "DELETE FROM daily_account_overviews WHERE platform_account_id = ? AND metric_date IN (SELECT metric_date FROM daily_account_overviews WHERE platform_account_id = ?)",
                (to_id, from_id),
            )
            over_updated = conn.execute(
                "UPDATE daily_account_overviews SET platform_account_id = ?, platform_account_name = ? WHERE platform_account_id = ?",
                (to_id, to_name, from_id),
            ).rowcount
            # accounts: delete old row if target already exists, then update
            conn.execute("DELETE FROM accounts WHERE platform_account_id = ?", (to_id,))
            conn.execute(
                "UPDATE accounts SET platform_account_id = ?, platform_account_name = ? WHERE platform_account_id = ?",
                (to_id, to_name, from_id),
            )
            conn.commit()
        finally:
            conn.close()
        self.send_json({"ok": True, "overviewRowsUpdated": over_updated})

    def handle_fetch(self) -> None:
        body = self.read_json_body()
        mode = body.get("mode") or "recent"
        if mode not in ("all", "full", "recent"):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "mode must be all, full or recent")
            return
        api_key = stored_api_key()
        if not api_key:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "missing backend apiKey")
            return
        dates = fetch_dates_for_mode(mode)
        with _FETCH_LOCK:
            if _FETCH_STATE["running"]:
                self.send_error_json(HTTPStatus.CONFLICT, "已有任务正在运行，请等待完成")
                return
        if not start_fetch_state(mode, len(dates)):
            with _FETCH_LOCK:
                self.send_error_json(HTTPStatus.CONFLICT, "已有任务正在运行，请等待完成")
            return
        db_path = resolve_db_path()
        t = threading.Thread(target=_run_fetch, args=(mode, api_key, db_path, dates, True), daemon=True)
        t.start()
        with _FETCH_LOCK:
            self.send_json({"ok": True, "message": "fetch started", "status": dict(_FETCH_STATE)})

    def handle_refresh_accounts(self) -> None:
        body = self.read_json_body()
        account_ids = body.get("accountIds")
        api_key = stored_api_key()
        if not api_key:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "missing backend apiKey")
            return
        selected_ids = account_ids if account_ids and isinstance(account_ids, list) else None
        platform_account_ids = load_refresh_account_ids(selected_ids)
        with _FETCH_LOCK:
            if _FETCH_STATE["running"]:
                self.send_error_json(HTTPStatus.CONFLICT, "已有任务正在运行，请等待完成")
                return
        if not start_fetch_state("refresh-accounts", len(platform_account_ids)):
            with _FETCH_LOCK:
                self.send_error_json(HTTPStatus.CONFLICT, "已有任务正在运行，请等待完成")
            return
        thread = threading.Thread(
            target=_refresh_accounts_for_overview,
            args=(api_key, platform_account_ids, True, True),
            daemon=True,
        )
        thread.start()
        with _FETCH_LOCK:
            self.send_json({"ok": True, "message": "refresh started", "status": dict(_FETCH_STATE)})

    def handle_fetch_status(self) -> None:
        with _FETCH_LOCK:
            self.send_json(dict(_FETCH_STATE))


    def handle_account_detail(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        pid = (params.get("platformAccountId") or [""])[0].strip()
        if not pid:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "missing platformAccountId")
            return
        api_key = stored_api_key()
        if not api_key:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "missing backend apiKey")
            return
        url = f"https://www.yixiaoer.cn/api/platform-accounts/{pid}"
        req = urllib.request.Request(url, headers={"Authorization": api_key})
        try:
            resp = throttled_urlopen(req, timeout=15)
            data = json.loads(resp.read())
            self.send_json(data.get("data") or {})
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self.send_error_json(e.code, body[:200])
        except Exception as exc:
            self.send_error_json(HTTPStatus.BAD_GATEWAY, str(exc))

    def handle_settings(self) -> None:
        body = self.read_json_body()
        if body.get("clear"):
            settings = load_settings()
            settings.pop("apiKey", None)
            if settings:
                save_settings(settings)
            elif SETTINGS_PATH.exists():
                SETTINGS_PATH.unlink()
            self.send_json(settings_payload())
            return
        api_key = str(body.get("apiKey") or "").strip()
        if not api_key:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "missing apiKey")
            return
        settings = load_settings()
        settings["apiKey"] = api_key
        save_settings(settings)
        self.send_json(settings_payload())


    def handle_schedule(self) -> None:
        if self.command == "GET":
            self.send_json(schedule_payload())
            return
        body = self.read_json_body()
        enabled = bool(body.get("enabled"))
        interval = int(body.get("intervalMinutes") or 360)
        mode = str(body.get("mode") or "latest")
        pre_refresh = bool(body.get("preRefresh"))
        get_scheduler().update(enabled, interval, mode, pre_refresh)
        self.send_json(schedule_payload())


    def handle_refresh(self) -> None:
        body = self.read_json_body()
        mode = body.get("mode") or "latest"
        result = _execute_refresh(mode)
        self.send_json(result, 200 if result.get("ok") else 500)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YiXiaoEr account metrics web service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    sch = get_scheduler()
    print(f"Auto-refresh scheduler: enabled={sch.status()['enabled']}, "
          f"interval={sch.status()['intervalMinutes']}min, mode={sch.status()['mode']}", file=sys.stderr)
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"YiXiaoEr account service listening on http://{args.host}:{args.port}", file=sys.stderr)
    print(f"Database: {resolve_db_path()}", file=sys.stderr)
    print(f"Scripts: {scripts_dir()}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
