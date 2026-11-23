"""Post tandem review comments to GitHub (tandem post-github)."""
import argparse
import json
import os
import re
import subprocess
import sys


KIND_PREFIX = {
    "must": "**Must fix**",
    "followup": "**Follow-up**",
    "question": "**Question**",
}


def gh(args, stdin=None):
    """Run gh with an argument list (never a shell) and return the result."""
    return subprocess.run(["gh"] + args, input=stdin, capture_output=True, text=True)


def parse_patch_lines(patch):
    """Return the set of new-file line numbers that appear in a unified diff patch."""
    lines = set()
    if not patch:
        return lines
    new_line = None
    for raw in patch.splitlines():
        if raw.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", raw)
            if match:
                new_line = int(match.group(1))
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith("\\"):
            continue
        if new_line is None:
            continue
        if raw.startswith("-"):
            continue
        if raw.startswith("+") or raw.startswith(" "):
            lines.add(new_line)
            new_line += 1
    return lines


def diff_line_map(files):
    """Map filename -> set of new-file line numbers from a gh /files JSON array."""
    result = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        name = item.get("filename")
        if not name:
            continue
        result[name] = parse_patch_lines(item.get("patch") or "")
    return result


def comment_body(comment):
    """Prefix a comment's text with its kind marker."""
    prefix = KIND_PREFIX.get(comment.get("kind"))
    text = comment.get("text", "")
    if prefix:
        return "%s %s" % (prefix, text)
    return text


def to_inline_comment(comment):
    """Build a GitHub review comment dict from a tandem comment."""
    to_line = int(comment.get("to"))
    from_line = int(comment.get("from", to_line))
    result = {
        "path": comment.get("file"),
        "line": to_line,
        "side": "RIGHT",
        "body": comment_body(comment),
    }
    if from_line != to_line:
        result["start_line"] = from_line
        result["start_side"] = "RIGHT"
    return result


def format_ref(path, from_line, to_line):
    if from_line == to_line:
        return "%s:%d" % (path, from_line)
    return "%s:%d-%d" % (path, from_line, to_line)


def body_text(body_comments):
    """Build the review body from comments that cannot be inline."""
    parts = []
    for comment in body_comments:
        from_line = int(comment.get("from", comment.get("to")))
        to_line = int(comment.get("to", from_line))
        ref = format_ref(comment.get("file"), from_line, to_line)
        parts.append("- `%s` %s" % (ref, comment_body(comment)))
    return "\n".join(parts)


def latest_round_file(review_dir):
    """Return the path of the highest-numbered comments-round-*.json, or None."""
    best_n = -1
    best = None
    try:
        names = os.listdir(review_dir)
    except OSError:
        return None
    for name in names:
        match = re.fullmatch(r"comments-round-(\d+)\.json", name)
        if match:
            number = int(match.group(1))
            if number > best_n:
                best_n = number
                best = os.path.join(review_dir, name)
    return best


def _parse_pr(spec):
    if "#" not in spec or "/" not in spec:
        return None
    repo, num = spec.split("#", 1)
    if "/" not in repo or not num.isdigit():
        return None
    owner, repo_name = repo.split("/", 1)
    if not owner or not repo_name:
        return None
    return owner, repo_name, int(num)


def main(argv):
    parser = argparse.ArgumentParser(prog="tandem post-github")
    parser.add_argument("--review", required=True, help="review directory")
    parser.add_argument("--pr", required=True, help="PR as owner/repo#N")
    parser.add_argument("--event", default="COMMENT",
                        choices=["COMMENT", "APPROVE", "REQUEST_CHANGES"])
    parser.add_argument("--round", type=int, default=None, help="round number (default: latest)")
    parser.add_argument("--yes", action="store_true", help="actually post to GitHub")
    args = parser.parse_args(argv)

    review_dir = args.review

    pr = _parse_pr(args.pr)
    if pr is None:
        print("error: --pr must be owner/repo#N, got %r" % args.pr, file=sys.stderr)
        return 1
    owner, repo, num = pr

    # Locate the comments file for the requested round.
    if args.round is not None:
        comments_path = os.path.join(review_dir, "comments-round-%d.json" % args.round)
        if not os.path.isfile(comments_path):
            print("error: %s does not exist" % comments_path, file=sys.stderr)
            return 1
    else:
        comments_path = latest_round_file(review_dir)
        if comments_path is None:
            print("error: no comments-round-*.json found in %s" % review_dir, file=sys.stderr)
            return 1

    try:
        with open(comments_path, "r", encoding="utf-8") as fh:
            comments_data = json.load(fh)
    except OSError as exc:
        print("error: cannot read %s: %s" % (comments_path, exc), file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print("error: %s is not valid JSON: %s" % (comments_path, exc), file=sys.stderr)
        return 1

    if not isinstance(comments_data, dict):
        print("error: %s must be a JSON object" % comments_path, file=sys.stderr)
        return 1
    comments = comments_data.get("comments")
    if not isinstance(comments, list):
        print("error: %s has no comments list" % comments_path, file=sys.stderr)
        return 1

    # meta.head is the commit_id for the review.
    review_path = os.path.join(review_dir, "review.json")
    try:
        with open(review_path, "r", encoding="utf-8") as fh:
            review = json.load(fh)
    except OSError as exc:
        print("error: cannot read %s: %s" % (review_path, exc), file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print("error: %s is not valid JSON: %s" % (review_path, exc), file=sys.stderr)
        return 1
    meta = review.get("meta") if isinstance(review, dict) else {}
    head = meta.get("head") if isinstance(meta, dict) else None
    if not head:
        print("error: review.json meta.head is missing", file=sys.stderr)
        return 1

    # Fetch the PR's changed files and their patches.
    proc = gh(["api", "repos/%s/%s/pulls/%d/files" % (owner, repo, num), "--paginate"])
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        print("error: gh api files failed: %s" % detail, file=sys.stderr)
        return 1
    try:
        files = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print("error: gh api files returned invalid JSON: %s" % exc, file=sys.stderr)
        return 1
    line_map = diff_line_map(files)

    inline_comments = []
    body_comments = []
    for comment in comments:
        from_line = int(comment.get("from", comment.get("to")))
        to_line = int(comment.get("to", from_line))
        file_lines = line_map.get(comment.get("file", ""), set())
        if all(line in file_lines for line in range(from_line, to_line + 1)):
            inline_comments.append(to_inline_comment(comment))
        else:
            body_comments.append(comment)

    payload = {
        "commit_id": head,
        "event": args.event,
        "body": body_text(body_comments) if body_comments else "",
        "comments": inline_comments,
    }

    if not args.yes:
        print(json.dumps(payload, indent=2))
        return 0

    proc = gh(
        ["api", "--method", "POST",
         "repos/%s/%s/pulls/%d/reviews" % (owner, repo, num), "--input", "-"],
        stdin=json.dumps(payload),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        print("error: gh api POST failed: %s" % detail, file=sys.stderr)
        return 1
    try:
        response = json.loads(proc.stdout)
        html_url = response.get("html_url") if isinstance(response, dict) else None
    except json.JSONDecodeError:
        html_url = None
    if html_url:
        print(html_url)
    else:
        print("posted review (no html_url in response)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
