import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_metrics_to_overviews import migrate_metrics_to_overviews


class MigrateMetricsToOverviewsTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.sqlite"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def _create_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE accounts (
                platform_account_id TEXT PRIMARY KEY,
                platform_name TEXT,
                platform_account_name TEXT,
                status INTEGER
            );

            CREATE TABLE metric_mappings (
                standard_key TEXT,
                standard_name TEXT,
                metric_key TEXT,
                metric_name TEXT,
                content_type TEXT,
                platform_name TEXT,
                aggregation TEXT
            );

            CREATE TABLE daily_account_metrics (
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
                PRIMARY KEY(metric_date, platform_account_id, content_type, metric_key)
            );

            CREATE TABLE daily_account_overviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_date TEXT NOT NULL,
                platform_name TEXT NOT NULL,
                platform_account_name TEXT NOT NULL,
                platform_account_id TEXT NOT NULL,
                login_status INTEGER,
                fans REAL,
                play REAL,
                like_count REAL,
                comment_count REAL,
                collect_count REAL,
                publish_count REAL,
                collected_at TEXT NOT NULL,
                UNIQUE(metric_date, platform_account_id)
            );
            """
        )
        self.conn.execute(
            "INSERT INTO accounts(platform_account_id, platform_name, platform_account_name, status) VALUES (?, ?, ?, ?)",
            ("acct-1", "抖音", "脂控小齐说", 1),
        )
        self.conn.executemany(
            """
            INSERT INTO daily_account_metrics(
                metric_date, platform_account_id, platform_name, platform_account_name,
                content_type, metric_key, metric_name, metric_value, collected_at, update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-20", "acct-1", "抖音", "脂控小齐说", "all", "play", "播放", 10, "old", None),
                ("2026-06-20", "acct-1", "抖音", "脂控小齐说", "all", "like", "点赞", 2, "old", None),
                ("2026-06-21", "acct-1", "抖音", "脂控小齐说", "all", "play", "播放", 20, "old", None),
            ],
        )
        self.conn.execute(
            """
            INSERT INTO daily_account_overviews(
                metric_date, platform_name, platform_account_name, platform_account_id,
                login_status, fans, play, like_count, comment_count, collect_count,
                publish_count, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-06-21", "抖音", "脂控小齐说", "acct-1", 1, 0, 999, 0, 0, 0, 0, "new"),
        )
        self.conn.commit()

    def test_apply_fills_missing_overview_rows_without_overwriting_existing_rows(self):
        result = migrate_metrics_to_overviews(self.conn, apply=True)

        self.assertEqual(result.legacy_daily_rows, 2)
        self.assertEqual(result.inserted, 1)
        self.assertEqual(result.skipped_existing, 1)

        rows = self.conn.execute(
            """
            SELECT metric_date, play, like_count, collected_at
            FROM daily_account_overviews
            WHERE platform_account_id = ?
            ORDER BY metric_date
            """,
            ("acct-1",),
        ).fetchall()

        self.assertEqual([row["metric_date"] for row in rows], ["2026-06-20", "2026-06-21"])
        self.assertEqual(rows[0]["play"], 10)
        self.assertEqual(rows[0]["like_count"], 2)
        self.assertEqual(rows[0]["collected_at"], "migration-from-daily-account-metrics")
        self.assertEqual(rows[1]["play"], 999)
        self.assertEqual(rows[1]["collected_at"], "new")


if __name__ == "__main__":
    unittest.main()
