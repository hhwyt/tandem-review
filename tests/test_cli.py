"""CLI tests for tandem.cli (v1 contract)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tandem import cli
from tandem import server as tandem_server


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.review = self.tmp / "review"
        self.review.mkdir()
        self.config = self.tmp / "config"
        self.config.mkdir()
        self._old_config = os.environ.get("TANDEM_CONFIG_DIR")
        os.environ["TANDEM_CONFIG_DIR"] = str(self.config)

    def tearDown(self):
        if self._old_config is None:
            os.environ.pop("TANDEM_CONFIG_DIR", None)
        else:
            os.environ["TANDEM_CONFIG_DIR"] = self._old_config
        self._tmp.cleanup()

    def test_publish_increments_version(self):
        self.assertEqual(cli.main(["publish", "--review", str(self.review)]), 0)
        self.assertEqual((self.review / "version").read_text(encoding="utf-8").strip(), "1")

        self.assertEqual(cli.main(["publish", "--review", str(self.review)]), 0)
        self.assertEqual((self.review / "version").read_text(encoding="utf-8").strip(), "2")

    def test_wait_returns_new_round(self):
        result = {}
        real_sleep = cli.time.sleep
        state = {"written": False}

        def sleeper(seconds):
            # Wait records the existing files before its first sleep, so writing
            # here makes the test deterministic regardless of thread scheduling.
            if not state["written"]:
                state["written"] = True
                (self.review / "comments-round-1.md").write_text(
                    "hello\n", encoding="utf-8"
                )
            real_sleep(seconds)

        def run_wait():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                result["rc"] = cli.main(
                    ["wait", "--review", str(self.review), "--timeout", "10"]
                )
            result["out"] = buf.getvalue()

        with mock.patch.object(cli.time, "sleep", side_effect=sleeper):
            t = threading.Thread(target=run_wait)
            t.start()
            t.join(timeout=10)
        self.assertFalse(t.is_alive())
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["out"], "hello\n")

    def test_wait_timeout_returns_2(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["wait", "--review", str(self.review), "--timeout", "1"])
        self.assertEqual(rc, 2)
        self.assertEqual(buf.getvalue(), "")

    def test_preflight_delegates(self):
        with mock.patch("tandem.preflight.main", return_value=7) as fn:
            rc = cli.main(["preflight", "--review", str(self.review), "--extra", "x"])
        self.assertEqual(rc, 7)
        fn.assert_called_once_with(["--review", str(self.review), "--extra", "x"])

    def test_post_github_delegates(self):
        with mock.patch("tandem.github.main", return_value=3) as fn:
            rc = cli.main(["post-github", "--review", str(self.review), "--pr", "a/b#1"])
        self.assertEqual(rc, 3)
        fn.assert_called_once_with(["--review", str(self.review), "--pr", "a/b#1"])

    def test_task_module_not_available(self):
        with mock.patch("tandem.cli.importlib.import_module", side_effect=ImportError):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(["preflight", "--review", str(self.review)])
        self.assertEqual(rc, 1)
        self.assertEqual(buf.getvalue().strip(), "not available yet")

    def test_serve_registers_and_unregisters_review(self):
        key = str(self.review.resolve())
        during = {}

        def serve_forever():
            during.update(
                json.loads(
                    (self.config / "reviews.json").read_text(encoding="utf-8")
                )
            )

        with mock.patch(
            "tandem.server.TandemServer.serve_forever", side_effect=serve_forever
        ):
            rc = cli.main(["serve", "--review", str(self.review)])
        self.assertEqual(rc, 0)

        self.assertIn(key, during)
        self.assertEqual(during[key]["pid"], os.getpid())
        self.assertIn("url", during[key])
        self.assertIn("port", during[key])

        after = json.loads(
            (self.config / "reviews.json").read_text(encoding="utf-8")
        )
        self.assertNotIn(key, after)

    def test_serve_writes_server_json_and_prints_url(self):
        with mock.patch(
            "tandem.server.TandemServer.serve_forever", return_value=None
        ):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(["serve", "--review", str(self.review)])
        self.assertEqual(rc, 0)
        url = buf.getvalue().strip()
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        self.assertIn("?t=", url)

        sj = json.loads((self.review / "server.json").read_text(encoding="utf-8"))
        self.assertEqual(sj["url"], url)
        self.assertEqual(sj["pid"], __import__("os").getpid())
        self.assertRegex(sj["token"], r"^[0-9a-f]{32}$")
        self.assertEqual(sj["port"], int(url.split(":")[2].split("/")[0]))

    def test_serve_prints_url_when_stdout_is_a_file(self):
        import subprocess
        import sys
        log = self.tmp / "serve.log"
        bin_tandem = Path(__file__).resolve().parent.parent / "bin" / "tandem"
        with open(log, "w") as out:
            proc = subprocess.Popen([sys.executable, str(bin_tandem), "serve", "--review",
                                     str(self.review)], stdout=out, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and "?t=" not in log.read_text():
                time.sleep(0.05)
            self.assertIn("http://127.0.0.1:", log.read_text())
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_serve_open(self):
        with mock.patch(
            "tandem.server.TandemServer.serve_forever", return_value=None
        ), mock.patch("tandem.cli.webbrowser.open") as browser_open:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(["serve", "--review", str(self.review), "--open"])
        self.assertEqual(rc, 0)
        browser_open.assert_called_once_with(buf.getvalue().strip())


if __name__ == "__main__":
    unittest.main()
