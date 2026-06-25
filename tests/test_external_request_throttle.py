import unittest
from unittest.mock import patch

import app


class ExternalRequestThrottleTest(unittest.TestCase):
    def test_throttled_urlopen_sleeps_before_each_external_request(self):
        calls = []

        def fake_sleep(seconds):
            calls.append(("sleep", seconds))

        def fake_urlopen(request, timeout):
            calls.append(("urlopen", timeout))
            return object()

        with patch.object(app, "sleep", side_effect=fake_sleep), \
             patch.object(app.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = app.throttled_urlopen("request", timeout=15)

        self.assertIsNotNone(result)
        self.assertEqual(calls, [("sleep", 1), ("urlopen", 15)])


if __name__ == "__main__":
    unittest.main()
