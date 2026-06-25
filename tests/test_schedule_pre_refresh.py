import unittest
from unittest.mock import patch

import app


class SchedulePreRefreshTest(unittest.TestCase):
    def test_execute_refresh_can_refresh_accounts_before_fetching(self):
        calls = []

        def fake_refresh(api_key):
            calls.append(("refresh", api_key))
            return {"ok": True, "triggered": 2, "skipped": 0, "errors": 0}

        def fake_sleep(seconds):
            calls.append(("sleep", seconds))

        def fake_fetch(mode, api_key, db_path):
            calls.append(("fetch", mode, api_key, str(db_path)))
            with app._FETCH_LOCK:
                app._FETCH_STATE["error"] = ""
                app._FETCH_STATE["result"] = {"daysFetched": 3, "accountsWritten": 6}

        with patch.object(app, "stored_api_key", return_value="key-1"), \
             patch.object(app, "resolve_db_path", return_value="db.sqlite"), \
             patch.object(app, "_refresh_accounts_for_overview", side_effect=fake_refresh), \
             patch.object(app, "sleep", side_effect=fake_sleep), \
             patch.object(app, "_run_fetch", side_effect=fake_fetch):
            result = app._execute_refresh("latest", pre_refresh=True, pre_refresh_wait_seconds=60)

        self.assertTrue(result["ok"])
        self.assertEqual(
            calls,
            [
                ("refresh", "key-1"),
                ("sleep", 60),
                ("fetch", "recent", "key-1", "db.sqlite"),
            ],
        )
        self.assertEqual(result["preRefresh"], {"ok": True, "triggered": 2, "skipped": 0, "errors": 0})


if __name__ == "__main__":
    unittest.main()
