# v1 contract (shared by all v1 tasks)

Read `DESIGN.md` for the product decisions. This file fixes the interfaces so the pieces can be
built in parallel. Python 3.9+ standard library only. No third-party packages, no build step.

## Layout

```
bin/tandem                 # #!/usr/bin/env python3 launcher: from tandem.cli import main; sys.exit(main())
tandem/__init__.py
tandem/cli.py              # argparse subcommands (task 1)
tandem/server.py           # HTTP server (task 1)
tandem/preflight.py        # def main(argv: list[str]) -> int   (task 4)
tandem/github.py           # def main(argv: list[str]) -> int   (task 4)
web/index.html             # the page (task 3)
schema/review.schema.json  # JSON Schema of review.json (task 2)
docs/review-json.md        # human description of review.json (task 2)
examples/pr-73235/review.json  # sample built from prototypes/ (task 2)
tests/                     # unittest, run with: python3 -m unittest discover -s tests
```

## Review directory

A review lives in a directory `<dir>` (the skill uses `<repo>/.tandem/<name>/`):

| File | Written by | Content |
|---|---|---|
| `review.json` | agent | the data the page shows (schema below) |
| `version` | `tandem publish` | an integer, incremented on each publish |
| `server.json` | `tandem serve` | `{"port": int, "token": str, "pid": int, "url": str}` |
| `state.json` | server (`PUT /api/state`) | page state: `{"done": {...}, "drafts": [...]}` |
| `comments-round-N.md` / `.json` | server (`POST /api/send`) | the comments of one send, N starts at 1 |

Preferences live in `~/.config/tandem/prefs.json` (override the directory with env
`TANDEM_CONFIG_DIR`): `{"theme": str, "lang": "en"|"zh", "notes": bool, "order": "reading"|"file",
"editor": "rustrover"|"vscode"|"cursor", "depth": {"<owner/repo>": "brief"|"detail"},
"hinted": bool}`. Unknown keys are kept.

## review.json (top level)

Every human-readable string is a bilingual object `{"en": str, "zh": str}` (written `T` below).

```json
{
  "meta": {"repo": "pingcap/tidb", "pr": 73235, "title": T, "mode": "self"|"pr",
           "root": "/abs/path/of/checkout/", "base": "<sha>", "head": "<sha>"},
  "overview": {
    "summary": T, "bg": T, "bgLong": T, "depthWhy": T,
    "design": [T, ...],
    "map": [{"lane": T, "steps": [{"t": T, "sub": T, "k": "new"|"mod"|"same", "go"?: ["<unitId>", <line>]}]}],
    "cover": [["✓"|"✗"|"!", T], ...],
    "decide": [[T /*kind*/, T /*question*/, T /*note*/, ["<unitId>", <line>]], ...]
  },
  "glossary": [["<term>", T], ...],
  "files": [{"path": str, "a": int, "d": int, "st": "new"|"mod", "tier": 1..5, "what": T}],
  "chapters": [{"n": T, "sub": T, "items": ["<unitId>", ...]}],
  "units": [ /* see docs/review-json.md */ ],
  "filesrc": {"<path>": ["line 1", "line 2", ...]},
  "newfiles": ["<path>", ...]
}
```

`units[i]` fields: `id, tier, name, file, sig, hunk:{oldStart,newStart},
lines:[["+"|"-"|" ", text]], why:T, gist:T, notes:[[from,to,en,zh]], callers:[node],
callees:[node], chains:[[node|str]]`, where `node = {name, file, line, key?:bool, pr?:unitId}`.

## HTTP API (server)

- Binds `127.0.0.1` only, port from `--port` or a free one. Token: 32 hex chars from `secrets`.
- Every `/api/*` request must carry the token as header `X-Tandem-Token` or query `?t=`; otherwise
  403. Static files are served without the token, but only from `web/`; paths containing `..` or
  starting with `.` are rejected (404). `Host` must be `127.0.0.1:<port>` or `localhost:<port>`,
  else 403.
- `GET /` → `web/index.html`.
- `GET /api/review` → review.json content plus `"version": int`.
- `GET /api/version` → `{"version": int}` (read from `<dir>/version`, 0 if missing).
- `GET /api/prefs`, `PUT /api/prefs` (JSON body, merged into the file, atomic write).
- `GET /api/state`, `PUT /api/state` (JSON body replaces `state.json`, atomic write).
- `POST /api/send` body `{"comments": [{"file": str, "from": int, "to": int, "kind": "must"|"followup"|"question", "text": str, "unit": str}], "final": bool}`
  → writes `comments-round-N.md` and `.json`, returns `{"round": N, "path": "<md path>"}`.
- `POST /api/open` body `{"path": str, "line": int}` → runs the editor from prefs:
  `rustrover --line L <abs>` / `code -g <abs>:L` / `cursor -g <abs>:L` (absolute path =
  `meta.root` + path; refuse paths that resolve outside `meta.root`). Uses `subprocess.Popen`
  with an argument list, never a shell. Returns `{"ok": bool, "error"?: str}`.
- Request bodies over 2 MB → 413.

## Markdown of a send (`comments-round-N.md`)

```
# Review comments, round N

- [Must fix] pkg/ddl/engine_attribute.go:139-142 (onModifyTableEngineAttribute)
  <text, indented two spaces on every line>
```

Kinds print as `Must fix`, `Follow-up`, `Question`. A single line prints `:139`.

## CLI

- `tandem serve --review <dir> [--port P] [--open]` — start the server in the foreground, write
  `server.json`, print the URL `http://127.0.0.1:P/?t=TOKEN`; `--open` opens it with
  `webbrowser.open`.
- `tandem wait --review <dir> [--timeout SECONDS]` — block until a `comments-round-N.md` newer than
  the ones that existed when it started appears; print its content to stdout; exit 0. On timeout
  exit 2 with nothing on stdout. Default timeout: none.
- `tandem publish --review <dir>` — increment `<dir>/version`.
- `tandem preflight ...` → `tandem.preflight.main(argv)`.
- `tandem post-github ...` → `tandem.github.main(argv)`.
