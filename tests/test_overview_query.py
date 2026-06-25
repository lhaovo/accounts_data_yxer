import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from app import AppHandler, _overview_table_ddl


class OverviewQueryTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.sqlite"
        self.previous_db_path = os.environ.get("YIXIAOER_DB_PATH")
        os.environ["YIXIAOER_DB_PATH"] = str(self.db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def tearDown(self):
        self.conn.close()
        if self.previous_db_path is None:
            os.environ.pop("YIXIAOER_DB_PATH", None)
        else:
            os.environ["YIXIAOER_DB_PATH"] = self.previous_db_path
        self.tmpdir.cleanup()

    def _create_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE accounts (
                platform_account_id TEXT PRIMARY KEY,
                platform_name TEXT,
                platform_account_name TEXT,
                status INTEGER,
                raw_json TEXT NOT NULL DEFAULT '{}',
                last_seen_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self.conn.execute(_overview_table_ddl())
        self.conn.execute(
            "INSERT INTO accounts(platform_account_id, platform_name, platform_account_name, status) VALUES (?, ?, ?, ?)",
            ("acct-1", "抖音", "脂控小齐说", 1),
        )
        self.conn.executemany(
            """
            INSERT INTO daily_account_overviews(
                metric_date, platform_name, platform_account_name, platform_account_id,
                login_status, fans, play, like_count, comment_count, collect_count,
                publish_count, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-20", "抖音", "脂控小齐说", "acct-1", 1, 1, 3, 1, 0, 0, 0, "migrated"),
                ("2026-06-21", "抖音", "脂控小齐说", "acct-1", 1, 0, 7, 0, 0, 0, 0, "new"),
                ("2026-06-22", "抖音", "脂控小齐说", "acct-1", 1, 0, 7, 0, 0, 0, 0, "new"),
                ("2026-06-23", "抖音", "脂控小齐说", "acct-1", 1, 1, 50, 0, 0, 0, 0, "new"),
            ],
        )
        self.conn.commit()

    def test_range_merge_uses_overview_rows_and_returns_one_row_per_account(self):
        handler = object.__new__(AppHandler)
        query = urlencode(
            {
                "start": "2026-06-20",
                "end": "2026-06-23",
                "platforms": "抖音",
                "accountIds": "acct-1",
                "merge": "1",
            }
        )

        rows = handler.query_rows_from_params(query)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["platform_account_id"], "acct-1")
        self.assertEqual(rows[0]["metric_date"], "2026-06-20")
        self.assertEqual(rows[0]["play"], 67)
        self.assertEqual(rows[0]["fans"], 2)


if __name__ == "__main__":
    unittest.main()
