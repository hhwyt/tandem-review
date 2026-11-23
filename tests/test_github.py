import contextlib
import io
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import tandem.github as github


PATCH_ONE = (
    "@@ -5,4 +5,5 @@\n"
    " context1\n"
    "-old\n"
    "+new\n"
    "+added\n"
    " context2\n"
    " context3\n"
)

PATCH_TWO = (
    "@@ -1,3 +1,3 @@\n"
    " a\n"
    "-b\n"
    "+c\n"
    "@@ -10,2 +11,3 @@\n"
    " d\n"
    "+e\n"
    " f\n"
)


def write_review(review_dir, head="abc123"):
    with open(os.path.join(review_dir, "review.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": {"root": review_dir, "head": head}, "units": [{"id": "u1"}]}, fh)


def write_comments(review_dir, round_num, comments):
    with open(os.path.join(review_dir, "comments-round-%d.json" % round_num), "w",
              encoding="utf-8") as fh:
        json.dump({"comments": comments, "final": False}, fh)


def make_gh(files_json, review_json=None, returncode=0, stderr="", pr_head="abc123"):
    calls = []

    def fake(args, stdin=None):
        calls.append((args, stdin))
        if len(args) >= 2 and args[0] == "api" and args[1] == "--method":
            stdout = json.dumps(review_json) if review_json is not None else ""
            return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        if args[0] == "api" and not args[1].endswith("/files"):
            return SimpleNamespace(returncode=0, stdout=json.dumps({"head": {"sha": pr_head}}),
                                   stderr="")
        if args[0] == "api":
            return SimpleNamespace(returncode=returncode, stdout=files_json, stderr=stderr)
        return SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)

    return fake, calls


def run_github(argv):
    buf = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = github.main(argv)
    return rc, buf.getvalue(), err.getvalue()


def comment(file, frm, to, kind="must", text="hello"):
    return {"file": file, "from": frm, "to": to, "kind": kind, "text": text, "unit": "u1"}


class PatchTest(unittest.TestCase):
    def test_single_hunk(self):
        self.assertEqual(github.parse_patch_lines(PATCH_ONE), {5, 6, 7, 8, 9})

    def test_two_hunks(self):
        self.assertEqual(github.parse_patch_lines(PATCH_TWO), {1, 2, 11, 12, 13})

    def test_empty_patch(self):
        self.assertEqual(github.parse_patch_lines(""), set())
        self.assertEqual(github.parse_patch_lines(None), set())

    def test_diff_line_map(self):
        files = [
            {"filename": "a.txt", "patch": PATCH_ONE},
            {"filename": "b.txt", "patch": None},
        ]
        self.assertEqual(github.diff_line_map(files), {
            "a.txt": {5, 6, 7, 8, 9},
            "b.txt": set(),
        })


class CommentTest(unittest.TestCase):
    def test_single_line_inline(self):
        got = github.to_inline_comment(comment("f.txt", 5, 5, "must", "fix it"))
        self.assertEqual(got, {
            "path": "f.txt",
            "line": 5,
            "side": "RIGHT",
            "body": "**Must fix** fix it",
        })

    def test_range_inline(self):
        got = github.to_inline_comment(comment("f.txt", 5, 7, "followup", "later"))
        self.assertEqual(got, {
            "path": "f.txt",
            "line": 7,
            "side": "RIGHT",
            "body": "**Follow-up** later",
            "start_line": 5,
            "start_side": "RIGHT",
        })

    def test_comment_body_kinds(self):
        self.assertEqual(github.comment_body(comment("f", 1, 1, "must", "m")), "**Must fix** m")
        self.assertEqual(github.comment_body(comment("f", 1, 1, "followup", "f")), "**Follow-up** f")
        self.assertEqual(github.comment_body(comment("f", 1, 1, "question", "q")), "**Question** q")
        self.assertEqual(github.comment_body(comment("f", 1, 1, "other", "x")), "x")

    def test_body_text_single_and_range(self):
        items = [comment("a.txt", 3, 3, "must", "one"), comment("b.txt", 4, 6, "question", "two")]
        text = github.body_text(items)
        self.assertEqual(text,
                         "- `a.txt:3` **Must fix** one\n"
                         "- `b.txt:4-6` **Question** two")


class MainTest(unittest.TestCase):
    def test_dry_run_split(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, head="abc123")
        write_comments(tmp.name, 1, [
            comment("a.txt", 5, 5, "must", "single"),
            comment("a.txt", 5, 6, "followup", "range"),
            comment("a.txt", 4, 5, "question", "out"),
            comment("b.txt", 1, 1, "must", "not-in-diff"),
        ])
        files_json = json.dumps([{"filename": "a.txt", "patch": PATCH_ONE}])
        fake, calls = make_gh(files_json)
        with mock.patch.object(github, "gh", side_effect=fake):
            rc, out, err = run_github(["--review", tmp.name, "--pr", "owner/repo#1"])
        self.assertEqual(rc, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["commit_id"], "abc123")
        self.assertEqual(payload["event"], "COMMENT")
        self.assertEqual(len(payload["comments"]), 2)
        self.assertEqual(payload["comments"][0]["line"], 5)
        self.assertEqual(payload["comments"][0]["body"], "**Must fix** single")
        self.assertEqual(payload["comments"][1]["line"], 6)
        self.assertEqual(payload["comments"][1]["start_line"], 5)
        self.assertIn("a.txt:4-5", payload["body"])
        self.assertIn("b.txt:1", payload["body"])
        # only the PR and files calls happened, no POST
        self.assertEqual(len(calls), 2)
        self.assertIn("--paginate", calls[1][0])

    def test_squashed_head_uses_pr_head(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, head="squashed")
        write_comments(tmp.name, 1, [comment("a.txt", 5, 5)])
        files_json = json.dumps([{"filename": "a.txt", "patch": PATCH_ONE}])
        fake, _ = make_gh(files_json, pr_head="pr-head")
        same = SimpleNamespace(returncode=0, stdout="t1\nt1\n", stderr="")
        with mock.patch.object(github, "gh", side_effect=fake), \
             mock.patch.object(github, "run_cmd", return_value=same):
            rc, out, err = run_github(["--review", tmp.name, "--pr", "owner/repo#1"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out)["commit_id"], "pr-head")

    def test_stale_head_refused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, head="old")
        write_comments(tmp.name, 1, [comment("a.txt", 5, 5)])
        files_json = json.dumps([{"filename": "a.txt", "patch": PATCH_ONE}])
        fake, calls = make_gh(files_json, pr_head="new")
        differ = SimpleNamespace(returncode=0, stdout="t1\nt2\n", stderr="")
        with mock.patch.object(github, "gh", side_effect=fake), \
             mock.patch.object(github, "run_cmd", return_value=differ):
            rc, out, err = run_github(["--review", tmp.name, "--pr", "owner/repo#1", "--yes"])
        self.assertEqual(rc, 1)
        self.assertIn("PR head is new", err)
        self.assertFalse(any(c[0][1] == "--method" for c in calls))

    def test_body_indents_continuation_lines(self):
        text = github.body_text([comment("a.txt", 3, 3, "must", "one\ntwo")])
        self.assertEqual(text, "- `a.txt:3` **Must fix** one\n  two")

    def test_dry_run_event_approve(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, head="abc123")
        write_comments(tmp.name, 1, [comment("a.txt", 5, 5)])
        files_json = json.dumps([{"filename": "a.txt", "patch": PATCH_ONE}])
        fake, _ = make_gh(files_json)
        with mock.patch.object(github, "gh", side_effect=fake):
            rc, out, _ = run_github([
                "--review", tmp.name, "--pr", "owner/repo#1", "--event", "APPROVE"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload["event"], "APPROVE")

    def test_yes_posts(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, head="abc123")
        write_comments(tmp.name, 1, [comment("a.txt", 5, 5, "must", "inline")])
        files_json = json.dumps([{"filename": "a.txt", "patch": PATCH_ONE}])
        review_json = {"html_url": "https://github.com/owner/repo/pull/1#review-9"}
        fake, calls = make_gh(files_json, review_json)
        with mock.patch.object(github, "gh", side_effect=fake):
            rc, out, err = run_github([
                "--review", tmp.name, "--pr", "owner/repo#1", "--yes"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(calls), 3)
        post_args, post_stdin = calls[2]
        self.assertEqual(post_args[1], "--method")
        self.assertEqual(post_args[2], "POST")
        self.assertIn("reviews", post_args[3])
        self.assertEqual(post_args[-1], "-")
        sent = json.loads(post_stdin)
        self.assertEqual(sent["commit_id"], "abc123")
        self.assertEqual(sent["event"], "COMMENT")
        self.assertEqual(sent["comments"][0]["body"], "**Must fix** inline")
        self.assertIn("https://github.com/owner/repo/pull/1#review-9", out)

    def test_round_latest(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, head="abc123")
        write_comments(tmp.name, 1, [comment("a.txt", 5, 5, "must", "round one")])
        write_comments(tmp.name, 2, [comment("a.txt", 5, 5, "must", "round two")])
        files_json = json.dumps([{"filename": "a.txt", "patch": PATCH_ONE}])
        fake, _ = make_gh(files_json)
        with mock.patch.object(github, "gh", side_effect=fake):
            rc, out, _ = run_github(["--review", tmp.name, "--pr", "owner/repo#1"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertIn("round two", payload["comments"][0]["body"])

    def test_round_explicit(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, head="abc123")
        write_comments(tmp.name, 1, [comment("a.txt", 5, 5, "must", "round one")])
        write_comments(tmp.name, 2, [comment("a.txt", 5, 5, "must", "round two")])
        files_json = json.dumps([{"filename": "a.txt", "patch": PATCH_ONE}])
        fake, _ = make_gh(files_json)
        with mock.patch.object(github, "gh", side_effect=fake):
            rc, out, _ = run_github(["--review", tmp.name, "--pr", "owner/repo#1", "--round", "1"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertIn("round one", payload["comments"][0]["body"])

    def test_latest_round_file(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_comments(tmp.name, 1, [])
        write_comments(tmp.name, 7, [])
        self.assertEqual(
            github.latest_round_file(tmp.name),
            os.path.join(tmp.name, "comments-round-7.json"))


if __name__ == "__main__":
    unittest.main()
