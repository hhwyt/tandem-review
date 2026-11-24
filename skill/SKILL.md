---
name: tandem-review
description: Review a code change together with a person in the browser. The agent prepares an overview, a reading order and notes between the lines; the person reads, comments and sends; the agent applies the comments (self review) or posts them to the GitHub pull request (PR review). Use when the user asks to review a change, a branch or a pull request "in Tandem", "in the browser", or "with notes".
---

# Tandem Review

You prepare the review, the person judges it. Write for a reader who will decide, not for yourself.

**Write only what the reader needs and does not already know.** Every word on the page is for a
person deciding about the change, not a log of your work. Before keeping a sentence, ask what the
reader loses if it is deleted; if nothing, delete it. That removes your process (what you read, ran
or did not run, how you worked it out), verdict words, hedges, code restated in prose, and anything
another section already says. When a single claim is unverified and the reader must know, say so
once, next to that claim.

Tandem lives in this repository: `bin/tandem` (Python 3.9+, standard library only),
`web/index.html`, `schema/review.schema.json`. Read `docs/review-json.md` once before writing your
first `review.json`.

## 1. Pick the mode

- **self**: the change is yours (written in this session or on the user's branch). Comments come
  back to you; you edit the code; the page updates; repeat until the user finishes.
- **pr**: someone else's pull request. Usually one round. Comments go to GitHub as one review with
  inline comments, after the user confirms.

## 2. Preflight

```bash
tandem preflight --review <dir>                      # self
tandem preflight --review <dir> --pr owner/repo#123  # pr
```

`<dir>` is `<repo>/.tandem/<branch-or-pr>/`; add `.tandem/` to the file
`git rev-parse --git-path info/exclude` prints (in a worktree that is the main repository's
`.git/info/exclude`) so it is never committed. Fix every `FAIL` line before going on; `todo
review.json` is expected the first time. In pr mode the checkout must be the PR head commit, or a
commit with the same tree (a review branch with the PR squashed into one commit is fine).

Run preflight again after writing `review.json`: it checks the schema and that every unit id,
line number and `pr` reference points at something that exists.

## 3. Write review.json

Follow `docs/review-json.md` and validate against `schema/review.schema.json`. What makes a good
review:

- **Language.** Write every text in both English and Chinese. Read `~/.config/tandem/prefs.json`;
  write the language in `lang` first and with the most care.
- **Terms.** Keep technical terms, project terms and identifiers exactly as the code and the
  project write them, in both languages. Do not translate them; translate only the words around
  them.
- **Readable text.** No wall of text anywhere: one idea per sentence, short paragraphs, lists for
  parallel items, numbered steps for anything that happens in order.
- **Diagrams.** Draw only when the reader needs to see a relationship at a glance that text
  takes several sentences to say; if the picture is not faster to read than those sentences, do
  not draw. Use the kind of diagram people in the project's field already use, one the reader
  does not have to learn to read; if there is none, write text. Every element must be something
  that exists in the system and every line a real relationship between them; boxes that only
  split your sentences are not a diagram.
- **Overview, in this order of thought:** summary (three lines: problem, change, risk; describe the change, not your notes), background (what exists today and what is wrong with it),
  approach (the idea, in two to four steps), the change map (`overview.map`: one lane per path the
  code runs, each a few steps from the entry to the effect, marked new, modified or unchanged and
  opening the unit that implements them), decisions that need the reader's call (each pointing at the line it is about), boundary
  (covered, not covered, watch out), files (one line each on what the file does).
- **Background depth.** `bg` is two or three sentences for someone who knows the module. `bgLong`
  adds definitions and one concrete worked example for someone new to it, laid out as
  blocks, never one paragraph: **Terms** as bullets, then the **Example**. If the change alters
  existing behavior, show **Before** and **After** as numbered steps; if it adds something new,
  show the steps of the new flow (format in `docs/review-json.md`). `depthWhy` says in one
  sentence why the default level fits this reader. Default to brief in self mode; in pr mode,
  brief if `git log --author` shows the reader has commits in the touched paths or CODEOWNERS
  names them, detailed otherwise.
- **Glossary.** Every domain term a newcomer would stop at, with a one-line definition and, where
  it helps, an example.
- **Reading order.** Group units into chapters, one per path the code actually runs. Inside a
  chapter put callers before callees, so
  every function is read with its caller already known. Mark the units whose mistakes would hurt
  the most with tier 1; tier does not change the order.
- **Units.** One unit per changed function (or struct). `lines` is the whole function from the
  diff, with its comments. Test functions are not units; say what the tests cover in the
  boundary. `why` says why the reader should care about this function; `gist` says
  what it does in one sentence.
- **Notes.** One note per block of a few lines, attached to the block's first new-file line. Say
  what the block is for and anything non-obvious (an invariant, a reason, a risk). Do not restate
  the code.
- **Call stacks.** `chains` run from the real entry point (`main`, a request handler, a background
  loop) down to the direct caller, one chain per distinct entry. Verify every frame's file and line
  with `grep -n`; never guess. A frame's `line` is its call site, the line that calls the next
  frame. Mark a frame `key` when the reader should notice it; the page folds
  the rest. Set `pr` on frames that are units of this review.
- **Decisions.** Only real choices the reader must make or confirm: compatibility, behavior,
  defaults, scope. Say what is unverified as unverified.

## 4. Open the page

```bash
tandem serve --review <dir> --open
```

Run it in the background; it prints the page URL and writes it, with the port and token, to
`<dir>/server.json`. Tell the user the
URL. The server binds 127.0.0.1 only and every API call needs the session token in the URL.

## 5. Wait for comments

```bash
tandem wait --review <dir>
```

It blocks until the user presses **Send** or **Finish** and prints the comments as Markdown (also
saved as `<dir>/comments-round-N.md`). Run it in the background if your harness supports
notifications on exit (Claude Code does); otherwise run it in the foreground with a long timeout,
or ask the user to tell you when they have sent and read the newest `comments-round-N.md`.

## 6. Act on the comments

**self mode**

1. Apply every Must fix. Answer every Question in your reply to the user. Record Follow-ups for
   the user; do not act on them.
2. If you think a comment is wrong, do not apply it; say why.
3. Regenerate `review.json` from the new code (keep unit ids stable so drafts still attach).
4. `tandem publish --review <dir>` — the page reloads in place.
5. Go back to step 5 until the user presses **Finish**.

**pr mode**

1. Show the user what will be posted: `tandem post-github --review <dir> --pr owner/repo#123`
   (dry run, prints the review JSON).
2. Post only after the user confirms in their own words:
   `tandem post-github --review <dir> --pr owner/repo#123 --yes`. The event is `COMMENT` unless the
   user chose `--event APPROVE` or `--event REQUEST_CHANGES`.
3. Lines outside the diff cannot be inline comments; they go into the review body with file and
   line. Tell the user which ones.

## Never

- Post to GitHub, push, or approve without the user's explicit confirmation.
- Put secrets, tokens or private data in `review.json`.
- Bind the server to anything but 127.0.0.1.
