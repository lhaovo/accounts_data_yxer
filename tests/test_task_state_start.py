import unittest

import app


class TaskStateStartTest(unittest.TestCase):
    def setUp(self):
        with app._FETCH_LOCK:
            app._FETCH_STATE.update(
                {
                    "running": False,
                    "mode": "recent",
                    "current": 3,
                    "total": 3,
                    "currentDate": "",
                    "error": "",
                    "result": {"daysFetched": 3, "accountsWritten": 12},
                }
            )

    def tearDown(self):
        with app._FETCH_LOCK:
            app._FETCH_STATE.update(
                {
                    "running": False,
                    "mode": "",
                    "current": 0,
                    "total": 0,
                    "currentDate": "",
                    "error": "",
                    "result": None,
                }
            )

    def test_refresh_account_state_replaces_previous_fetch_result_before_worker_runs(self):
        started = app.start_fetch_state("refresh-accounts", 5)

        self.assertTrue(started)
        with app._FETCH_LOCK:
            self.assertTrue(app._FETCH_STATE["running"])
            self.assertEqual(app._FETCH_STATE["mode"], "refresh-accounts")
            self.assertEqual(app._FETCH_STATE["current"], 0)
            self.assertEqual(app._FETCH_STATE["total"], 5)
            self.assertEqual(app._FETCH_STATE["currentDate"], "")
            self.assertEqual(app._FETCH_STATE["error"], "")
            self.assertIsNone(app._FETCH_STATE["result"])

    def test_start_fetch_state_refuses_to_replace_running_task(self):
        with app._FETCH_LOCK:
            app._FETCH_STATE["running"] = True
            app._FETCH_STATE["mode"] = "recent"

        started = app.start_fetch_state("refresh-accounts", 5)

        self.assertFalse(started)
        with app._FETCH_LOCK:
            self.assertEqual(app._FETCH_STATE["mode"], "recent")


if __name__ == "__main__":
    unittest.main()
