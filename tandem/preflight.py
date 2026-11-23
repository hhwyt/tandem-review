"""Preflight checks for a tandem review directory (tandem preflight)."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys

from tandem.github import same_tree
from tandem.validate import check_review


def _run(cmd):
    """Run a command with an argument list (never a shell) and return the result."""
    return subprocess.run(cmd, capture_output=True, text=True)


def _parse_pr(spec):
    """Parse owner/repo#N; return (owner, repo, number) or None."""
    if "#" not in spec or "/" not in spec:
        return None
    repo, num = spec.split("#", 1)
    if "/" not in repo or not num.isdigit():
        return None
    owner, repo_name = repo.split("/", 1)
    if not owner or not repo_name:
        return None
    return owner, repo_name, int(num)


def _load_review(review_dir):
    """Return (data, error). data is the parsed review.json or None on failure."""
    path = os.path.join(review_dir, "review.json")
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        return None, "review.json is not valid JSON: %s" % exc
    except OSError as exc:
        return None, "review.json cannot be read: %s" % exc
    if not isinstance(data, dict):
        return None, "review.json must be a JSON object"
    units = data.get("units")
    if not isinstance(units, list) or not units:
        return None, "review.json units is empty or missing; add at least one unit"
    problems = check_review(data)
    if problems:
        shown = "; ".join(problems[:5])
        if len(problems) > 5:
            shown += "; and %d more" % (len(problems) - 5)
        return None, shown
    return data, None


def main(argv):
    parser = argparse.ArgumentParser(prog="tandem preflight")
    parser.add_argument("--review", required=True, help="review directory")
    parser.add_argument("--pr", default=None, help="PR as owner/repo#N")
    args = parser.parse_args(argv)

    review_dir = args.review
    failures = []

    def check(passed, item, detail=""):
        if passed:
            print("ok  %s" % item)
        else:
            failures.append(item)
            print("FAIL %s: %s" % (item, detail))

    # 1. Python >= 3.9
    if sys.version_info >= (3, 9):
        check(True, "Python >= 3.9")
    else:
        check(
            False,
            "Python >= 3.9",
            "found Python %d.%d; install Python 3.9 or newer" % (
                sys.version_info[0], sys.version_info[1]),
        )

    # 2. review.json exists, valid JSON, units non-empty
    # Preflight runs once before review.json is written and once after.
    data, review_err = _load_review(review_dir)
    written = data is not None or review_err is not None
    if data is not None:
        check(True, "review.json valid")
    elif review_err is None:
        print("todo review.json: not written yet; run preflight again after writing it")
        data = {}
    else:
        check(False, "review.json valid", review_err)
        data = {}

    meta = data.get("meta") if isinstance(data, dict) else None

    # 3. meta.root is an existing directory and a git repository
    root = meta.get("root") if isinstance(meta, dict) else None
    if not written:
        pass
    elif not isinstance(root, str) or not root:
        check(False, "meta.root git repo",
              "meta.root is missing from review.json; set it to the checkout directory")
    elif not os.path.isdir(root):
        check(False, "meta.root git repo",
              "meta.root %r is not a directory; point it at the checkout" % root)
    else:
        proc = _run(["git", "-C", root, "rev-parse", "--show-toplevel"])
        if proc.returncode == 0:
            check(True, "meta.root git repo")
        else:
            detail = (proc.stderr or proc.stdout or "").strip()
            check(False, "meta.root git repo",
                  "git rev-parse failed in %r: %s" % (root, detail or "not a git repository"))

    # 4. a free port can be found by binding 127.0.0.1:0
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        check(True, "free port")
    except OSError as exc:
        check(False, "free port", "cannot bind 127.0.0.1:0: %s" % exc)
    finally:
        sock.close()

    # 5. PR-only checks
    if args.pr:
        pr = _parse_pr(args.pr)
        if pr is None:
            check(False, "gh PR", "--pr must be owner/repo#N, got %r" % args.pr)
        else:
            owner, repo, num = pr
            base_api = "repos/%s/%s" % (owner, repo)

            # gh on PATH
            if shutil.which("gh"):
                check(True, "gh in PATH")
            else:
                check(False, "gh in PATH",
                      "gh is not installed or not on PATH; install the GitHub CLI")

            # gh auth status
            proc = _run(["gh", "auth", "status"])
            if proc.returncode == 0:
                check(True, "gh auth status")
            else:
                detail = (proc.stderr or proc.stdout or "").strip()
                check(False, "gh auth status",
                      "gh auth status failed: %s" % (detail or "run: gh auth login"))

            # gh api can read the PR
            pr_data = None
            proc = _run(["gh", "api", "%s/pulls/%d" % (base_api, num)])
            if proc.returncode == 0:
                try:
                    pr_data = json.loads(proc.stdout)
                    check(True, "gh PR readable")
                except json.JSONDecodeError as exc:
                    check(False, "gh PR readable", "gh api returned invalid JSON: %s" % exc)
            else:
                detail = (proc.stderr or proc.stdout or "").strip()
                check(False, "gh PR readable",
                      "gh api %s/pulls/%d failed: %s" % (base_api, num, detail))

            # returned head.sha must equal meta.head
            head_sha = None
            if isinstance(pr_data, dict):
                head = pr_data.get("head")
                if isinstance(head, dict):
                    head_sha = head.get("sha")
            local_head = meta.get("head") if isinstance(meta, dict) else None
            if not written:
                pass
            elif pr_data is None:
                check(False, "gh head matches", "PR could not be read")
            elif head_sha is None:
                check(False, "gh head matches", "gh api response has no head.sha")
            elif local_head is None:
                check(False, "gh head matches",
                      "meta.head is missing from review.json")
            elif head_sha == local_head or same_tree(root, local_head, head_sha, _run):
                check(True, "gh head matches")
            else:
                check(False, "gh head matches",
                      "PR head.sha %s != meta.head %s and the trees differ; check out the PR head commit"
                      % (head_sha, local_head))

            # current account can comment (warn if we cannot tell)
            proc = _run(["gh", "api", base_api])
            if proc.returncode == 0:
                try:
                    repo_data = json.loads(proc.stdout)
                except json.JSONDecodeError as exc:
                    repo_data = None
                    print("warn gh comment permission: gh api %s returned invalid JSON: %s"
                          % (base_api, exc))
                perms = None
                if isinstance(repo_data, dict):
                    perms = repo_data.get("permissions")
                if isinstance(perms, dict) and ("pull" in perms or "triage" in perms):
                    if perms.get("pull") or perms.get("triage"):
                        check(True, "gh can comment")
                    else:
                        check(False, "gh can comment",
                              "account has neither pull nor triage permission on %s" % base_api)
                else:
                    print("warn gh comment permission: no permissions in gh api %s response"
                          % base_api)
            else:
                detail = (proc.stderr or proc.stdout or "").strip()
                print("warn gh comment permission: gh api %s failed: %s"
                      % (base_api, detail or "unknown error"))

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
