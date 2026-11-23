"""Command-line interface for Tandem Review (v1 contract)."""

from __future__ import annotations

import argparse
import importlib
import sys
import time
import webbrowser
from pathlib import Path

from tandem import server


def _cmd_serve(args) -> int:
    review = Path(args.review)
    srv = server.create_server(review, args.port or 0)
    info = server.write_server_json(srv)
    print(info["url"])
    if args.open:
        webbrowser.open(info["url"])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


def _cmd_wait(args) -> int:
    review = Path(args.review)
    existing = {p.name for p in review.glob("comments-round-*.md")}
    started = time.monotonic()
    while True:
        new_files = sorted(
            p for p in review.glob("comments-round-*.md") if p.name not in existing
        )
        if new_files:
            sys.stdout.write(new_files[0].read_text(encoding="utf-8"))
            return 0
        if args.timeout is not None and time.monotonic() - started >= args.timeout:
            return 2
        time.sleep(0.5)


def _cmd_publish(args) -> int:
    server.increment_version(args.review)
    return 0


def _run_task_module(name: str, argv) -> int:
    try:
        module = importlib.import_module(f"tandem.{name}")
    except ImportError:
        print("not available yet")
        return 1
    return module.main(argv)


def _cmd_preflight(args) -> int:
    return _run_task_module("preflight", args.argv)


def _cmd_post_github(args) -> int:
    return _run_task_module("github", args.argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tandem")
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="start the local server")
    p_serve.add_argument("--review", required=True, help="review directory")
    p_serve.add_argument("--port", type=int, default=0, help="port (default: free port)")
    p_serve.add_argument("--open", action="store_true", help="open the URL in a browser")
    p_serve.set_defaults(func=_cmd_serve)

    p_wait = sub.add_parser("wait", help="block until a new comments round appears")
    p_wait.add_argument("--review", required=True, help="review directory")
    p_wait.add_argument("--timeout", type=float, default=None, help="timeout in seconds")
    p_wait.set_defaults(func=_cmd_wait)

    p_publish = sub.add_parser("publish", help="increment the review version")
    p_publish.add_argument("--review", required=True, help="review directory")
    p_publish.set_defaults(func=_cmd_publish)

    p_preflight = sub.add_parser("preflight", help="run the preflight checks")
    p_preflight.add_argument("argv", nargs=argparse.REMAINDER)
    p_preflight.set_defaults(func=_cmd_preflight)

    p_post = sub.add_parser("post-github", help="post the review to GitHub")
    p_post.add_argument("argv", nargs=argparse.REMAINDER)
    p_post.set_defaults(func=_cmd_post_github)

    return parser


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    # preflight / post-github pass their remaining arguments verbatim to the
    # task-4 modules. argparse.REMAINDER chokes when the first remaining token
    # looks like an option (e.g. "--review"), so dispatch these two directly.
    task_modules = {"preflight": "preflight", "post-github": "github"}
    if argv and argv[0] in task_modules:
        return _run_task_module(task_modules[argv[0]], argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
