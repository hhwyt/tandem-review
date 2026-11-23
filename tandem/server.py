"""Local HTTP server for Tandem Review (v1 contract).

Standard library only. Binds 127.0.0.1 and serves the review directory over
HTTP for the in-browser review page.
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

#: The directory served for static files. Relative to the repository root.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

MAX_BODY = 2 * 1024 * 1024  # 2 MB

TOKEN_HEADER = "X-Tandem-Token"

KIND_LABELS = {
    "must": "Must fix",
    "followup": "Follow-up",
    "question": "Question",
}


def atomic_write(path: Path, data: str) -> None:
    """Write ``data`` to ``path`` atomically (temp file + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, obj) -> None:
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def read_version(review_dir) -> int:
    """Read ``<review_dir>/version``; 0 when missing or unparseable."""
    p = Path(review_dir) / "version"
    if p.is_file():
        try:
            return int(p.read_text(encoding="utf-8").strip() or "0")
        except (ValueError, OSError):
            return 0
    return 0


def increment_version(review_dir) -> int:
    """Increment and persist ``<review_dir>/version``. Returns the new value."""
    review_dir = Path(review_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    nxt = read_version(review_dir) + 1
    atomic_write(review_dir / "version", str(nxt) + "\n")
    return nxt


def render_markdown(round_no: int, comments) -> str:
    """Render one send as ``comments-round-N.md`` per the contract."""
    lines = [f"# Review comments, round {round_no}", ""]
    for i, c in enumerate(comments):
        if i > 0:
            lines.append("")
        kind = KIND_LABELS.get(c.get("kind"), str(c.get("kind", "")))
        start = c.get("from")
        end = c.get("to")
        if start == end:
            loc = f"{c.get('file', '')}:{start}"
        else:
            loc = f"{c.get('file', '')}:{start}-{end}"
        head = f"- [{kind}] {loc}"
        unit = c.get("unit")
        if unit:
            head += f" ({unit})"
        lines.append(head)
        for text_line in (c.get("text", "")).splitlines() or [""]:
            lines.append("  " + text_line)
    return "\n".join(lines) + "\n"


def server_json(server) -> dict:
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/?t={server.token}"
    return {"port": port, "token": server.token, "pid": os.getpid(), "url": url}


def write_server_json(server) -> dict:
    obj = server_json(server)
    atomic_write_json(server.review_dir / "server.json", obj)
    return obj


class TandemHandler(BaseHTTPRequestHandler):
    """Request handler. Config is attached to the server instance."""

    server_version = "Tandem/1.0"
    protocol_version = "HTTP/1.1"

    # --- helpers ---------------------------------------------------------
    def log_message(self, format, *args):  # noqa: A002 - keep tests quiet
        return

    def _send_json(self, obj, status: int = 200) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _token_ok(self, parsed) -> bool:
        token = self.headers.get(TOKEN_HEADER)
        if token and secrets.compare_digest(token, self.server.token):
            return True
        values = parse_qs(parsed.query).get("t", [])
        return len(values) == 1 and secrets.compare_digest(values[0], self.server.token)

    def _prefs_path(self) -> Path:
        base = os.environ.get("TANDEM_CONFIG_DIR")
        directory = Path(base) if base else Path.home() / ".config" / "tandem"
        return directory / "prefs.json"

    def _load_prefs(self) -> dict:
        p = self._prefs_path()
        if p.is_file():
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
                return obj if isinstance(obj, dict) else {}
            except (ValueError, OSError):
                return {}
        return {}

    def _read_body(self):
        clen = self.headers.get("Content-Length")
        if clen is None:
            return (400, "missing Content-Length")
        try:
            length = int(clen)
        except ValueError:
            return (400, "bad Content-Length")
        if length < 0:
            return (400, "bad Content-Length")
        if length > MAX_BODY:
            return (413, "body too large")
        if length == 0:
            return (400, "empty body")
        return self.rfile.read(length)

    def _read_json(self):
        raw = self._read_body()
        if isinstance(raw, tuple):
            return raw
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return (400, "invalid json")

    # --- static files -----------------------------------------------------
    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            rel = "index.html"
        else:
            rel = path.lstrip("/")
        parts = [p for p in rel.split("/") if p != ""]
        if any(p == ".." or p.startswith(".") for p in parts):
            self._send_error_json(404, "not found")
            return
        root = self.server.web_dir.resolve()
        candidate = (self.server.web_dir / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            self._send_error_json(404, "not found")
            return
        if not candidate.is_file():
            self._send_error_json(404, "not found")
            return
        data = candidate.read_bytes()
        ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/json":
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    # --- API -------------------------------------------------------------
    def _api_get(self, path: str) -> None:
        review = self.server.review_dir
        if path == "/api/review":
            rp = review / "review.json"
            if not rp.is_file():
                self._send_error_json(404, "review.json missing")
                return
            try:
                data = json.loads(rp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._send_error_json(500, "invalid review.json")
                return
            data["version"] = read_version(review)
            self._send_json(data)
            return
        if path == "/api/version":
            self._send_json({"version": read_version(review)})
            return
        if path == "/api/prefs":
            self._send_json(self._load_prefs())
            return
        if path == "/api/state":
            sp = review / "state.json"
            if sp.is_file():
                try:
                    self._send_json(json.loads(sp.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    self._send_json({})
            else:
                self._send_json({})
            return
        self._send_error_json(404, "not found")

    def _api_put(self, path: str, body) -> None:
        review = self.server.review_dir
        if path == "/api/prefs":
            prefs = self._load_prefs()
            if isinstance(prefs, dict) and isinstance(body, dict):
                prefs.update(body)
            else:
                prefs = body
            atomic_write_json(self._prefs_path(), prefs)
            self._send_json(prefs)
            return
        if path == "/api/state":
            atomic_write_json(review / "state.json", body)
            self._send_json({"ok": True})
            return
        self._send_error_json(404, "not found")

    def _next_round(self) -> int:
        max_n = 0
        prefix = "comments-round-"
        for p in self.server.review_dir.glob(prefix + "*.md"):
            suffix = p.stem[len(prefix):]
            if suffix.isdigit():
                max_n = max(max_n, int(suffix))
        return max_n + 1

    def _api_send(self, body) -> None:
        review = self.server.review_dir
        if not isinstance(body, dict):
            body = {}
        comments = body.get("comments")
        if not isinstance(comments, list):
            comments = []
        final = bool(body.get("final"))
        n = self._next_round()
        md_path = review / f"comments-round-{n}.md"
        json_path = review / f"comments-round-{n}.json"
        atomic_write(md_path, render_markdown(n, comments))
        atomic_write_json(json_path, {"round": n, "comments": comments, "final": final})
        self._send_json({"round": n, "path": str(md_path)})

    def _api_open(self, body) -> None:
        review = self.server.review_dir
        rp = review / "review.json"
        if not isinstance(body, dict):
            body = {}
        if not rp.is_file():
            self._send_json({"ok": False, "error": "review.json missing"})
            return
        try:
            meta = json.loads(rp.read_text(encoding="utf-8")).get("meta", {})
        except (ValueError, OSError):
            meta = {}
        root_str = meta.get("root")
        path = body.get("path")
        line = body.get("line")
        if not root_str or path is None:
            self._send_json({"ok": False, "error": "missing root or path"})
            return
        try:
            line = max(1, int(line))
        except (TypeError, ValueError):
            self._send_json({"ok": False, "error": "line must be an integer"})
            return
        root = Path(str(root_str)).resolve()
        raw_path = str(path)
        if Path(raw_path).is_absolute():
            self._send_json({"ok": False, "error": "absolute paths are not allowed"})
            return
        target = (root / raw_path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._send_json({"ok": False, "error": "path outside review root"})
            return
        prefs = self._load_prefs()
        editor = prefs.get("editor") or "rustrover"
        if editor == "rustrover":
            cmd = ["rustrover", "--line", str(line), str(target)]
        elif editor == "vscode":
            cmd = ["code", "-g", f"{target}:{line}"]
        elif editor == "cursor":
            cmd = ["cursor", "-g", f"{target}:{line}"]
        else:
            self._send_json({"ok": False, "error": f"unknown editor: {editor}"})
            return
        try:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            self._send_json({"ok": False, "error": f"cannot run {cmd[0]}: {exc.strerror or exc}"})
            return
        self._send_json({"ok": True})

    # --- HTTP verbs ------------------------------------------------------
    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            self._send_error_json(403, "bad Host")
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            if not self._token_ok(parsed):
                self._send_error_json(403, "missing token")
                return
            self._api_get(path)
            return
        self._serve_static(path)

    def do_PUT(self):  # noqa: N802
        if not self._host_ok():
            self._send_error_json(403, "bad Host")
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self._send_error_json(404, "not found")
            return
        if not self._token_ok(parsed):
            self._send_error_json(403, "missing token")
            return
        body = self._read_json()
        if isinstance(body, tuple):
            self._send_error_json(body[0], body[1])
            return
        self._api_put(path, body)

    def do_POST(self):  # noqa: N802
        if not self._host_ok():
            self._send_error_json(403, "bad Host")
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self._send_error_json(404, "not found")
            return
        if not self._token_ok(parsed):
            self._send_error_json(403, "missing token")
            return
        body = self._read_json()
        if isinstance(body, tuple):
            self._send_error_json(body[0], body[1])
            return
        if path == "/api/send":
            self._api_send(body)
            return
        if path == "/api/open":
            self._api_open(body)
            return
        self._send_error_json(404, "not found")


class TandemServer(ThreadingHTTPServer):
    """Threading HTTP server bound to 127.0.0.1 with per-session token."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, review_dir, port: int = 0, web_dir=WEB_DIR):
        self.review_dir = Path(review_dir).resolve()
        self.web_dir = Path(web_dir).resolve()
        self.token = secrets.token_hex(16)
        self.review_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(("127.0.0.1", int(port)), TandemHandler)


def create_server(review_dir, port: int = 0, web_dir=None):
    """Create a bound ``TandemServer`` (port 0 selects a free port)."""
    if web_dir is None:
        web_dir = WEB_DIR
    return TandemServer(review_dir, int(port), web_dir)
