import unittest
from datetime import date

import app


class FetchDateRangeTest(unittest.TestCase):
    def test_all_mode_uses_april_first_through_today(self):
        dates = app.fetch_dates_for_mode("all", today=date(2026, 4, 3))

        self.assertEqual(dates, ["2026-04-01", "2026-04-02", "2026-04-03"])

    def test_full_mode_keeps_recent_thirty_days(self):
        dates = app.fetch_dates_for_mode("full", today=date(2026, 6, 25))

        self.assertEqual(len(dates), 30)
        self.assertEqual(dates[0], "2026-06-24")
        self.assertEqual(dates[-1], "2026-05-26")


if __name__ == "__main__":
    unittest.main()
