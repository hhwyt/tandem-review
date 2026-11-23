import contextlib
import io
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import tandem.preflight as preflight


def run_preflight(review_dir, pr=None):
    argv = ["--review", review_dir]
    if pr is not None:
        argv += ["--pr", pr]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = preflight.main(argv)
    return rc, buf.getvalue()


def write_review(review_dir, root, head="abc123", units=None, meta=None):
    if units is None:
        units = [{"id": "u1"}]
    data_meta = {
        "repo": "owner/repo",
        "pr": 1,
        "title": {"en": "t", "zh": "t"},
        "mode": "pr",
        "root": root,
        "base": "base-sha",
        "head": head,
    }
    if meta:
        data_meta.update(meta)
    with open(os.path.join(review_dir, "review.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": data_meta, "units": units}, fh)


def make_tmp():
    tmp = tempfile.TemporaryDirectory()
    root = os.path.join(tmp.name, "repo")
    os.mkdir(root)
    return tmp, root


def git_ok(cmd):
    return SimpleNamespace(returncode=0, stdout="", stderr="")


class GoodSock:
    def bind(self, address):
        pass

    def close(self):
        pass


def gh_fake(pr_json=None, repo_json=None, auth_rc=0, pr_rc=0, repo_rc=0,
            auth_err="", pr_err="", repo_err=""):
    def fake(cmd):
        if cmd[0] == "git":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[0] == "gh":
            if cmd[1] == "auth":
                return SimpleNamespace(returncode=auth_rc, stdout="", stderr=auth_err)
            if cmd[1] == "api":
                target = cmd[2]
                if "/pulls/" in target:
                    stdout = json.dumps(pr_json) if pr_json is not None else ""
                    return SimpleNamespace(returncode=pr_rc, stdout=stdout, stderr=pr_err)
                stdout = json.dumps(repo_json) if repo_json is not None else ""
                return SimpleNamespace(returncode=repo_rc, stdout=stdout, stderr=repo_err)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return fake


class PreflightTest(unittest.TestCase):
    def test_all_pass_without_pr(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root)
        with mock.patch.object(preflight, "_run", side_effect=git_ok), \
             mock.patch.object(preflight.socket, "socket", return_value=GoodSock()):
            rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 0)
        self.assertIn("ok  Python >= 3.9", out)
        self.assertIn("ok  review.json valid", out)
        self.assertIn("ok  meta.root git repo", out)
        self.assertIn("ok  free port", out)

    def test_python_fail(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root)
        with mock.patch.object(preflight, "_run", side_effect=git_ok), \
             mock.patch.object(preflight.sys, "version_info", (3, 8)):
            rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL Python >= 3.9", out)

    def test_review_json_missing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL review.json valid", out)

    def test_review_json_invalid(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, "review.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL review.json valid", out)

    def test_review_json_units_empty(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, "review.json"), "w", encoding="utf-8") as fh:
            json.dump({"meta": {"root": tmp.name, "head": "abc123"}, "units": []}, fh)
        rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL review.json valid", out)

    def test_meta_root_missing(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root, meta={"root": None})
        with mock.patch.object(preflight, "_run", side_effect=git_ok):
            rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL meta.root git repo", out)

    def test_meta_root_not_dir(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, "/no/such/dir")
        with mock.patch.object(preflight, "_run", side_effect=git_ok):
            rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL meta.root git repo", out)

    def test_meta_root_not_git(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root)

        def fake_git(cmd):
            if cmd[0] == "git":
                return SimpleNamespace(returncode=1, stdout="", stderr="not a git repository")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(preflight, "_run", side_effect=fake_git):
            rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL meta.root git repo", out)
        self.assertIn("not a git repository", out)

    def test_free_port_fail(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root)

        class BadSock:
            def bind(self, address):
                raise OSError("no free ports")

            def close(self):
                pass

        with mock.patch.object(preflight, "_run", side_effect=git_ok), \
             mock.patch.object(preflight.socket, "socket", return_value=BadSock()):
            rc, out = run_preflight(tmp.name)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL free port", out)

    def test_gh_in_path_fail(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root)
        with mock.patch.object(preflight, "_run", side_effect=gh_fake()), \
             mock.patch.object(preflight.shutil, "which", return_value=None):
            rc, out = run_preflight(tmp.name, pr="owner/repo#1")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL gh in PATH", out)

    def test_gh_auth_fail(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root)
        pr_json = {"head": {"sha": "abc123"}}
        repo_json = {"permissions": {"pull": True}}
        fake = gh_fake(pr_json=pr_json, repo_json=repo_json, auth_rc=1, auth_err="not logged in")
        with mock.patch.object(preflight, "_run", side_effect=fake), \
             mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/gh"):
            rc, out = run_preflight(tmp.name, pr="owner/repo#1")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL gh auth status", out)

    def test_gh_pr_fail(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root)
        fake = gh_fake(pr_rc=1, pr_err="boom", repo_json={"permissions": {"pull": True}})
        with mock.patch.object(preflight, "_run", side_effect=fake), \
             mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/gh"):
            rc, out = run_preflight(tmp.name, pr="owner/repo#1")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL gh PR readable", out)

    def test_gh_head_mismatch(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root, head="sha-local")
        pr_json = {"head": {"sha": "sha-remote"}}
        repo_json = {"permissions": {"pull": True}}
        fake = gh_fake(pr_json=pr_json, repo_json=repo_json)
        with mock.patch.object(preflight, "_run", side_effect=fake), \
             mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/gh"):
            rc, out = run_preflight(tmp.name, pr="owner/repo#1")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL gh head matches", out)
        self.assertIn("sha-remote", out)
        self.assertIn("sha-local", out)

    def test_gh_head_match(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root, head="abc123")
        pr_json = {"head": {"sha": "abc123"}}
        repo_json = {"permissions": {"pull": True}}
        fake = gh_fake(pr_json=pr_json, repo_json=repo_json)
        with mock.patch.object(preflight, "_run", side_effect=fake), \
             mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/gh"), \
             mock.patch.object(preflight.socket, "socket", return_value=GoodSock()):
            rc, out = run_preflight(tmp.name, pr="owner/repo#1")
        self.assertEqual(rc, 0)
        self.assertIn("ok  gh head matches", out)

    def test_gh_can_comment_ok(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root, head="abc123")
        pr_json = {"head": {"sha": "abc123"}}
        repo_json = {"permissions": {"pull": True}}
        fake = gh_fake(pr_json=pr_json, repo_json=repo_json)
        with mock.patch.object(preflight, "_run", side_effect=fake), \
             mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/gh"), \
             mock.patch.object(preflight.socket, "socket", return_value=GoodSock()):
            rc, out = run_preflight(tmp.name, pr="owner/repo#1")
        self.assertEqual(rc, 0)
        self.assertIn("ok  gh can comment", out)

    def test_gh_can_comment_false(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root, head="abc123")
        pr_json = {"head": {"sha": "abc123"}}
        repo_json = {"permissions": {"pull": False, "triage": False}}
        fake = gh_fake(pr_json=pr_json, repo_json=repo_json)
        with mock.patch.object(preflight, "_run", side_effect=fake), \
             mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/gh"):
            rc, out = run_preflight(tmp.name, pr="owner/repo#1")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL gh can comment", out)

    def test_gh_can_comment_warn(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root, head="abc123")
        pr_json = {"head": {"sha": "abc123"}}
        repo_json = {"permissions": {}}
        fake = gh_fake(pr_json=pr_json, repo_json=repo_json)
        with mock.patch.object(preflight, "_run", side_effect=fake), \
             mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/gh"), \
             mock.patch.object(preflight.socket, "socket", return_value=GoodSock()):
            rc, out = run_preflight(tmp.name, pr="owner/repo#1")
        self.assertEqual(rc, 0)
        self.assertIn("warn gh comment permission", out)

    def test_pr_spec_invalid(self):
        tmp, root = make_tmp()
        self.addCleanup(tmp.cleanup)
        write_review(tmp.name, root)
        with mock.patch.object(preflight, "_run", side_effect=git_ok), \
             mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/gh"):
            rc, out = run_preflight(tmp.name, pr="badformat")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL gh PR", out)


if __name__ == "__main__":
    unittest.main()
