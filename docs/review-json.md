# review.json

`review.json` is the data the Tandem page renders. An agent writes one file per review, next to
`version`, `server.json` and `state.json` (see `docs/v1-contract.md`). It is plain JSON. Every
human-readable string is a **bilingual object** `{"en": str, "zh": str}`, written `T` below.

The schema lives in `schema/review.schema.json` (JSON Schema draft 2020-12). A small standalone
validator lives in `tests/test_schema.py`; run `python3 -m unittest tests.test_schema -v`.

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

`units` is an array of exactly the objects defined in `prototypes/data.js` `window.UNITS`. Fields:

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
- `hunk`: `oldStart`/`newStart` are the `@@ -old +new @@` numbers of the displayed diff hunk.
- `lines`: the diff hunk body. Each line is `[mark, text]`; `mark` is `"+"`, `"-"` or `" "`.
  These are the lines the page renders and the reviewer comments on.
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

- `name`, `file`, `line`: the symbol and its location.
- `key`: `true` marks a frame the tree should keep unfolded (important boundary functions).
- `pr`: set **only when the node is itself a unit in this PR**; the value is that unit's `id`.
  Nodes that are not part of this PR must **not** carry `pr`. The page uses `pr` to jump within
  the review, and opens all other nodes in the editor.

### How to fill `chains`

Start at the entry point (`main`) and walk down to the direct caller(s) of the unit. Keep a node
in the chain when it is `key`, when it is a unit in this PR (`pr` set), or when the stack branches
there; everything else can be collapsed later by the page or replaced by a short string.

## `filesrc`

```json
{"<path>": ["line 1", "line 2", ...]}
```

The full source of the files the page needs, keyed by repo-relative path. Used to show context
lines above and below each unit.

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
    "cover": [["✓", {"en": "covered", "zh": "覆盖"}]],
    "decide": [[{"en": "Q", "zh": "问"}, {"en": "?", "zh": "？"},
                {"en": "note", "zh": "注"}, ["u1", 10]]]
  },
  "glossary": [["term", {"en": "def", "zh": "定义"}]],
  "files": [{"path": "pkg/a.go", "a": 10, "d": 0, "st": "new", "tier": 1,
             "what": {"en": "what", "zh": "内容"}}],
  "chapters": [{"n": {"en": "C", "zh": "章"}, "sub": {"en": "s", "zh": "节"},
                "items": ["u1"]}],
  "units": [{
    "id": "u1", "tier": 1, "name": "fn", "file": "pkg/a.go", "sig": 3,
    "hunk": {"oldStart": 0, "newStart": 1},
    "lines": [["+", "func fn() {}"]],
    "why": {"en": "why", "zh": "为什么"},
    "gist": {"en": "gist", "zh": "概要"},
    "notes": [[3, 3, "en note", "zh note"]],
    "callers": [], "callees": [],
    "chains": [[{"name": "main", "file": "cmd/main.go", "line": 1, "key": true}]]
  }],
  "filesrc": {"pkg/a.go": ["func fn() {}"]},
  "newfiles": ["pkg/a.go"]
}
```
