"""HTTP API tests for tandem.server (v1 contract)."""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tandem import server as tandem_server


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.review = self.tmp / "review"
        self.review.mkdir()
        self.web = self.tmp / "web"
        self.web.mkdir()
        (self.web / "index.html").write_text("<html>ok</html>", encoding="utf-8")

        self.config = self.tmp / "config"
        self.config.mkdir()
        self._old_config = os.environ.get("TANDEM_CONFIG_DIR")
        os.environ["TANDEM_CONFIG_DIR"] = str(self.config)

        (self.review / "review.json").write_text(
            json.dumps(
                {
                    "meta": {
                        "repo": "pingcap/tidb",
                        "pr": 73235,
                        "title": {"en": "t", "zh": "t"},
                        "mode": "self",
                        "root": str(self.review),
                        "base": "b",
                        "head": "h",
                    },
                    "files": [],
                    "units": [],
                    "filesrc": {},
                    "newfiles": [],
                }
            ),
            encoding="utf-8",
        )

        self.srv = tandem_server.create_server(self.review, 0, web_dir=self.web)
        self.port = self.srv.server_address[1]
        self.token = self.srv.token
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(timeout=5)
        if self._old_config is None:
            os.environ.pop("TANDEM_CONFIG_DIR", None)
        else:
            os.environ["TANDEM_CONFIG_DIR"] = self._old_config
        self._tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdrs = dict(headers or {})
        data = None
        if body is not None:
            if isinstance(body, (dict, list)):
                data = json.dumps(body).encode("utf-8")
            elif isinstance(body, str):
                data = body.encode("utf-8")
            else:
                data = body
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        status = resp.status
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        return status, resp_headers, raw

    def test_api_requires_token(self):
        status, _, _ = self.request("GET", "/api/review")
        self.assertEqual(status, 403)

    def test_body_too_large_413(self):
        # Claim a huge Content-Length without actually sending 2 MB: the server
        # must reject based on the header alone (413) before reading the body.
        status, _, _ = self.request(
            "POST",
            f"/api/send?t={self.token}",
            body=b"x",
            headers={"Content-Length": str(tandem_server.MAX_BODY + 1)},
        )
        self.assertEqual(status, 413)

    def test_wrong_host_403(self):
        status, _, _ = self.request(
            "GET",
            "/api/version",
            headers={
                "Host": f"evil.example:{self.port}",
                tandem_server.TOKEN_HEADER: self.token,
            },
        )
        self.assertEqual(status, 403)

    def test_static_path_traversal_404(self):
        status, _, _ = self.request("GET", "/../secret.txt")
        self.assertEqual(status, 404)

    def test_static_hidden_404(self):
        status, _, _ = self.request("GET", "/.hidden")
        self.assertEqual(status, 404)

    def test_static_index(self):
        status, _, raw = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"<html>ok</html>")

    def test_review_includes_version(self):
        status, _, raw = self.request(
            "GET", "/api/review", headers={tandem_server.TOKEN_HEADER: self.token}
        )
        self.assertEqual(status, 200)
        data = json.loads(raw)
        self.assertIn("meta", data)
        self.assertEqual(data["version"], 0)

    def test_version_endpoint(self):
        status, _, raw = self.request(
            "GET", f"/api/version?t={self.token}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {"version": 0})

        tandem_server.increment_version(self.review)
        status, _, raw = self.request("GET", f"/api/version?t={self.token}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {"version": 1})

    def test_prefs_merge(self):
        status, _, raw = self.request("GET", f"/api/prefs?t={self.token}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {})

        status, _, _ = self.request(
            "PUT",
            f"/api/prefs?t={self.token}",
            body={"theme": "dark", "lang": "zh"},
        )
        self.assertEqual(status, 200)

        status, _, _ = self.request(
            "PUT", f"/api/prefs?t={self.token}", body={"notes": True, "custom": 1}
        )
        self.assertEqual(status, 200)

        prefs = json.loads((self.config / "prefs.json").read_text(encoding="utf-8"))
        self.assertEqual(prefs["theme"], "dark")
        self.assertEqual(prefs["lang"], "zh")
        self.assertIs(prefs["notes"], True)
        self.assertEqual(prefs["custom"], 1)

        status, _, raw = self.request("GET", f"/api/prefs?t={self.token}")
        self.assertEqual(json.loads(raw)["theme"], "dark")

    def test_state_roundtrip(self):
        status, _, raw = self.request("GET", f"/api/state?t={self.token}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {})

        body = {"done": {"a": True}, "drafts": [{"x": 1}]}
        status, _, _ = self.request("PUT", f"/api/state?t={self.token}", body=body)
        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads((self.review / "state.json").read_text(encoding="utf-8")), body
        )

        status, _, raw = self.request("GET", f"/api/state?t={self.token}")
        self.assertEqual(json.loads(raw), body)

    def test_send_single_line(self):
        body = {
            "comments": [
                {
                    "file": "pkg/ddl/engine_attribute.go",
                    "from": 139,
                    "to": 139,
                    "kind": "must",
                    "text": "fix this",
                    "unit": "onModifyTableEngineAttribute",
                }
            ],
            "final": False,
        }
        status, _, raw = self.request("POST", f"/api/send?t={self.token}", body=body)
        self.assertEqual(status, 200)
        data = json.loads(raw)
        self.assertEqual(data["round"], 1)

        md = (self.review / "comments-round-1.md").read_text(encoding="utf-8")
        self.assertIn(
            "- [Must fix] pkg/ddl/engine_attribute.go:139 (onModifyTableEngineAttribute)",
            md,
        )
        self.assertIn("  fix this", md)

        jdata = json.loads(
            (self.review / "comments-round-1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(jdata["round"], 1)
        self.assertEqual(jdata["final"], False)

    def test_send_multi_line_and_round_increment(self):
        self.request(
            "POST",
            f"/api/send?t={self.token}",
            body={"comments": [], "final": False},
        )
        body = {
            "comments": [
                {
                    "file": "pkg/ddl/engine_attribute.go",
                    "from": 139,
                    "to": 142,
                    "kind": "followup",
                    "text": "multi\nline",
                    "unit": "onModifyTableEngineAttribute",
                }
            ],
            "final": True,
        }
        status, _, raw = self.request("POST", f"/api/send?t={self.token}", body=body)
        self.assertEqual(status, 200)
        data = json.loads(raw)
        self.assertEqual(data["round"], 2)

        md = (self.review / "comments-round-2.md").read_text(encoding="utf-8")
        self.assertIn(
            "- [Follow-up] pkg/ddl/engine_attribute.go:139-142 (onModifyTableEngineAttribute)",
            md,
        )
        self.assertIn("  multi\n  line", md)

    def test_open_rejects_out_of_bounds(self):
        with mock.patch("tandem.server.subprocess.Popen") as popen:
            status, _, raw = self.request(
                "POST",
                f"/api/open?t={self.token}",
                body={"path": "../outside.txt", "line": 3},
            )
            self.assertEqual(status, 200)
            data = json.loads(raw)
            self.assertFalse(data["ok"])
            self.assertIn("error", data)
            popen.assert_not_called()

    def test_open_calls_editor_with_arg_list(self):
        with mock.patch("tandem.server.subprocess.Popen") as popen:
            status, _, raw = self.request(
                "POST",
                f"/api/open?t={self.token}",
                body={"path": "a.go", "line": 139},
            )
            self.assertEqual(status, 200)
            data = json.loads(raw)
            self.assertTrue(data["ok"])
            popen.assert_called_once()
            args, kwargs = popen.call_args
            cmd = args[0]
            self.assertIsInstance(cmd, list)
            self.assertNotIn("shell", kwargs)
            self.assertEqual(cmd[0], "rustrover")
            self.assertEqual(cmd[1], "--line")
            self.assertEqual(cmd[2], "139")


if __name__ == "__main__":
    unittest.main()
