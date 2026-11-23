# review.json

`review.json` is the data the Tandem page renders. An agent writes one file per review, next to
`version`, `server.json` and `state.json` (see `docs/v1-contract.md`). It is plain JSON. Every
human-readable string is a **bilingual object** `{"en": str, "zh": str}`, written `T` below.

The schema lives in `schema/review.schema.json` (JSON Schema draft 2020-12). Check a file with
`tandem preflight --review <dir>`: it runs the schema and the reference checks in
`tandem/validate.py` (every unit id, line number and `pr` points at something that exists).

## Top level

```json
{
  "meta": { ... },
  "overview": { ... },
  "glossary": [...],
  "files": [...],
  "chapters": [...],
  "units": [...],
  "filesrc": { ... },
  "newfiles": [...]
}
```

All eight keys are required. No other top-level keys are allowed.

## `meta`

```json
{
  "repo": "pingcap/tidb",
  "pr": 73235,
  "title": T,
  "mode": "self" | "pr",
  "root": "/abs/path/of/checkout/",
  "base": "<sha>",
  "head": "<sha>"
}
```

- `repo`, `pr`: the repository and pull request. Self review also fills these; `pr` may be `0`.
- `title`: the review's one-line title, a `T`.
- `mode`: `"self"` for code the agent wrote, `"pr"` for someone else's PR.
- `root`: absolute path of the checkout, with a trailing slash. The server resolves file paths
  against it; `""` is used when no editor integration is configured.
- `base`, `head`: the two commit SHAs of the diff under review.

## `overview`

```json
{
  "verdict": T,
  "bg": T,
  "bgLong": T,
  "depthWhy": T,
  "design": [T, ...],
  "map": [{"lane": T, "steps": [{"t": T, "sub": T, "k": "new" | "mod" | "same", "go": ["<unitId>", <line>]}]}],
  "cover": [["✓" | "✗" | "!", T], ...],
  "decide": [[T, T, T, ["<unitId>", <line>]], ...]
}
```

- `verdict`: the summary verdict shown under the title.
- `bg`: the **Brief** background (two or three sentences for someone who knows the module).
- `bgLong`: the **Detailed** background (definitions plus a worked example for a newcomer).
- `depthWhy`: one line explaining why the default depth was chosen (e.g. commit count in the
  touched paths). Shown next to the Brief/Detailed switch.
- `design`: the approach as ordered steps; one `T` per step.
- `map`: the change map, drawn as boxes and arrows. One lane per path the code runs (for example
  "statement time" and "every period"), each a list of steps from the entry to the effect. A step
  has a title `t`, a one-line `sub`, `k` = `"new"`, `"mod"` or `"same"` (unchanged context), and
  optionally `go`: `["<unitId>", <line>]`, the new-file line the box opens. Decisions whose target
  unit is a step's `go` unit show as a badge on that box. Keep a lane to five steps or fewer.
- `cover`: the boundary. Each entry is a two-element array `[mark, text]` where `mark` is
  `"✓"` (covered), `"✗"` (not covered) or `"!"` (caveat).
- `decide`: decisions that need the reviewer's call. Each entry is
  `[kind, question, note, target]`:
  - `kind`: a short label (e.g. `"Compat"`, `"Behavior"`).
  - `question`: the question, a `T`.
  - `note`: the current thinking or the alternative, a `T`.
  - `target`: `["<unitId>", <line>]` — where this decision is anchored. `<line>` is a
    **new-file line number** in that unit.

## `glossary`

```json
[["<term>", T], ...]
```

A list of `[term, definition]` pairs. Terms are underlined in the overview and listed at the end.
Prefer short definitions with one concrete example.

## `files`

```json
[{"path": str, "a": int, "d": int, "st": "new" | "mod", "tier": 1..5, "what": T}]
```

One entry per changed file, ordered by importance.

- `path`: repo-relative path.
- `a`, `d`: added and deleted line counts.
- `st`: `"new"` if the file is added, `"mod"` if modified.
- `tier`: importance 1 (critical) to 5 (docs/build).
- `what`: one sentence describing what changed here, a `T`.

## `chapters`

```json
[{"n": T, "sub": T, "items": ["<unitId>", ...]}]
```

The reading order. `n` is the chapter name, `sub` its one-line subtitle, and `items` lists unit
ids in the order a reviewer should read them (callers before callees).

## `units`

One unit per changed function, method or type. Test functions are not units: list test files in
`files` and say what they cover in `overview.cover`. Fields:

```json
{
  "id": str,
  "tier": int,
  "name": str,
  "file": str,
  "sig": int,
  "hunk": {"oldStart": int, "newStart": int},
  "lines": [["+" | "-" | " ", str], ...],
  "why": T,
  "gist": T,
  "notes": [[from, to, en, zh], ...],
  "callers": [node, ...],
  "callees": [node, ...],
  "chains": [[node | str], ...]
}
```

- `id`: stable id used by `chapters.items`, `overview.decide` targets and `node.pr`.
- `tier`: importance 1..5, like `files.tier`.
- `name`: function or symbol name, as written in code.
- `file`, `sig`: repo-relative path and the line where the function signature starts (new file).
- `lines`: the whole function (or type) with its doc comment, as diff lines: `[mark, text]`, where
  `mark` is `"+"`, `"-"` or `" "`. Deleted lines stay in place. These are the lines the page
  renders and the reviewer comments on. Easiest source: `git diff -U100000 <base> <head> -- <file>`,
  cut to the function's new-file line range.
- `hunk`: `oldStart`/`newStart` are the old-file and new-file line numbers of the first entry of
  `lines` (for a first `"+"` line, `oldStart` is the old line it is inserted before).
- `why`: why this function matters (shown only for tier 1).
- `gist`: one-sentence summary of what the function does.
- `notes`: explanatory notes shown as faint lines above the code. Each note is
  `[from, to, en, zh]`; `from`/`to` are **new-file line numbers** (inclusive) and `en`/`zh` are
  the two languages directly (a note is not a `T` — the four values sit in one array).
- `callers`, `callees`: arrays of `node` objects (see below) for the functions that call this one
  and the functions this one calls.
- `chains`: the call stack(s) from the entry point down to this function, used by the call-hierarchy
  panel. Each chain is an array of `node` (or a string, used as a folded-frames placeholder).

### `node`

```json
{"name": str, "file": str, "line": int, "key": bool, "pr": "<unitId>"}
```

- `name`, `file`, `line`: the function and a line in it. In `chains` and `callers`, `line` is the
  call site: the line in that function that calls the next frame (or this unit). In `callees`, it
  is the line where the callee is defined. Check every line with `grep -n`.
- `key`: `true` marks a frame the tree should keep unfolded (important boundary functions).
- `pr`: set **only when the node is itself a unit in this PR**; the value is that unit's `id`.
  Nodes that are not part of this PR must **not** carry `pr`. The page uses `pr` to jump within
  the review, and opens all other nodes in the editor.

### How to fill `chains`

Start at the entry point (`main`, a connection handler, a background loop) and walk down to the
direct caller(s) of the unit; the unit itself is not a frame. Keep a node
in the chain when it is `key`, when it is a unit in this PR (`pr` set), or when the stack branches
there; everything else can be collapsed later by the page or replaced by a short string.

## `filesrc`

```json
{"<path>": ["line 1", "line 2", ...]}
```

The full new-file source of every file that has a unit, keyed by repo-relative path, one string
per line without the newline. The page uses it to show context lines above and below a unit.

## `newfiles`

```json
["<path>", ...]
```

Paths that are newly added in this PR; the page renders their lines as additions.

## Minimal example

```json
{
  "meta": {
    "repo": "pingcap/tidb", "pr": 73235,
    "title": {"en": "Title", "zh": "标题"},
    "mode": "pr", "root": "",
    "base": "aa4109", "head": "61d912"
  },
  "overview": {
    "verdict": {"en": "Verdict", "zh": "结论"},
    "bg": {"en": "Brief", "zh": "简"},
    "bgLong": {"en": "Detailed", "zh": "详"},
    "depthWhy": {"en": "why", "zh": "原因"},
    "design": [{"en": "step", "zh": "步骤"}],
    "map": [{"lane": {"en": "Request", "zh": "请求"},
             "steps": [{"t": {"en": "fn", "zh": "fn"}, "sub": {"en": "new", "zh": "新增"},
                        "k": "new", "go": ["u1", 1]}]}],
    "cover": [["✓", {"en": "covered", "zh": "覆盖"}]],
    "decide": [[{"en": "Q", "zh": "问"}, {"en": "?", "zh": "？"},
                {"en": "note", "zh": "注"}, ["u1", 1]]]
  },
  "glossary": [["term", {"en": "def", "zh": "定义"}]],
  "files": [{"path": "pkg/a.go", "a": 10, "d": 0, "st": "new", "tier": 1,
             "what": {"en": "what", "zh": "内容"}}],
  "chapters": [{"n": {"en": "C", "zh": "章"}, "sub": {"en": "s", "zh": "节"},
                "items": ["u1"]}],
  "units": [{
    "id": "u1", "tier": 1, "name": "fn", "file": "pkg/a.go", "sig": 1,
    "hunk": {"oldStart": 0, "newStart": 1},
    "lines": [["+", "func fn() {}"]],
    "why": {"en": "why", "zh": "为什么"},
    "gist": {"en": "gist", "zh": "概要"},
    "notes": [[1, 1, "en note", "zh note"]],
    "callers": [], "callees": [],
    "chains": [[{"name": "main", "file": "cmd/main.go", "line": 1, "key": true}]]
  }],
  "filesrc": {"pkg/a.go": ["func fn() {}"]},
  "newfiles": ["pkg/a.go"]
}
```
