import sqlite3
import unittest

from app import _overview_table_ddl, store_overview_payload


class OverviewFetchStoreTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_overview_table_ddl())

    def tearDown(self):
        self.conn.close()

    def insert_existing(self, account_id, play, collected_at="existing"):
        self.conn.execute(
            """
            INSERT INTO daily_account_overviews (
                metric_date, platform_name, platform_account_name, platform_account_id,
                login_status, fans, play, like_count, comment_count, collect_count,
                publish_count, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-05-20", "douyin", "account", account_id, 1, 0, play, 1, 0, 0, 0, collected_at),
        )
        self.conn.commit()

    def payload(self, account_id, play):
        return {
            "accounts": [
                {
                    "platformName": "douyin",
                    "platformAccountName": "account",
                    "platformAccountId": account_id,
                    "status": 1,
                    "fansTotal": 1,
                    "playTotal": play,
                    "likesTotal": 3,
                    "commentsTotal": 4,
                    "favoritesTotal": 5,
                    "publishTotal": 6,
                }
            ]
        }

    def row_for(self, account_id):
        return self.conn.execute(
            """
            SELECT platform_account_id, fans, play, like_count, comment_count, collect_count,
                   publish_count, collected_at
            FROM daily_account_overviews
            WHERE platform_account_id = ?
            """,
            (account_id,),
        ).fetchone()

    def test_store_payload_inserts_when_local_row_is_missing(self):
        written = store_overview_payload(self.conn, "2026-05-20", self.payload("acct-1", 2), "fresh")

        row = self.row_for("acct-1")
        self.assertEqual(written, 1)
        self.assertEqual(row["play"], 2)
        self.assertEqual(row["collected_at"], "fresh")

    def test_store_payload_keeps_existing_row_when_existing_play_is_larger(self):
        self.insert_existing("acct-1", 188, "migration")

        written = store_overview_payload(self.conn, "2026-05-20", self.payload("acct-1", 2), "fresh")

        row = self.row_for("acct-1")
        self.assertEqual(written, 0)
        self.assertEqual(row["play"], 188)
        self.assertEqual(row["collected_at"], "migration")

    def test_store_payload_replaces_existing_row_when_incoming_play_is_larger(self):
        self.insert_existing("acct-1", 2, "migration")

        written = store_overview_payload(self.conn, "2026-05-20", self.payload("acct-1", 188), "fresh")

        row = self.row_for("acct-1")
        self.assertEqual(written, 1)
        self.assertEqual(row["play"], 188)
        self.assertEqual(row["collected_at"], "fresh")

    def test_store_payload_works_with_default_sqlite_tuple_rows(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(_overview_table_ddl())
            conn.execute(
                """
                INSERT INTO daily_account_overviews (
                    metric_date, platform_name, platform_account_name, platform_account_id,
                    login_status, fans, play, like_count, comment_count, collect_count,
                    publish_count, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("2026-05-20", "douyin", "account", "acct-1", 1, 0, 188, 1, 0, 0, 0, "migration"),
            )
            conn.commit()

            written = store_overview_payload(conn, "2026-05-20", self.payload("acct-1", 2), "fresh")

            row = conn.execute(
                "SELECT play, collected_at FROM daily_account_overviews WHERE platform_account_id = ?",
                ("acct-1",),
            ).fetchone()
            self.assertEqual(written, 0)
            self.assertEqual(row[0], 188)
            self.assertEqual(row[1], "migration")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
