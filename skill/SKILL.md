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

Follow `docs/review-json.md` and validate against `schema/review.schema.json`.

Before writing, establish the facts:

- **Read the author's account first.** Read the PR description, linked issues and commit
  messages before anything else. Your statement of the problem must agree with the author's;
  where it does not, say where and show the code that settles it.
- **Learn the old behavior from the base commit, not from the diff.** The diff shows what
  changed; only the old code shows how the system behaved and why a change was needed. Every
  sentence about how something worked before rests on code you read at the base commit.
- **Every fact has a source.** Each factual sentence the reader sees rests on something you
  read: code, a test, a code comment, the PR description. If you cannot find the source, cut
  the sentence, or, when the reader needs to know, turn it into a question for the author.

What makes a good review:

- **Language.** Write every text in both English and Chinese. Read `~/.config/tandem/prefs.json`;
  write the language in `lang` first and with the most care.
- **Terms.** Keep technical terms, project terms and identifiers exactly as the code and the
  project write them, in both languages. Do not translate them; translate only the words around
  them.
- **Diagrams.** Draw only when the picture is faster to read than the text. A figure answers one
  question; its title states the answer, and every element helps answer it. Draw what the
  question is about: when it is about state or order, put the things to compare on one shared
  axis and lay steps out in time, rather than drawing the components that hold them; boxes that
  only split your sentences are not a diagram. Use a kind of diagram people in the field already
  read; in a comparison change only what differs; label marks where they are, and give each
  color one meaning. Use the same example and numbers as the text, and let the text lead to the
  figure. Check the rendered figure, not its source: give only the figure and its title to a
  reader who has not seen the code and ask what it shows; if they cannot say, fix it or do not
  draw. Put figures in `overview.figures` and mark where each goes in `bgLong`.
- **Overview, in this order of thought:** summary (three lines: problem, change, risk; describe the
  change, not your notes), background (how the system works here and what goes wrong; it stops at
  the problem), approach (how the change fixes it, in the order the code runs: walk the core
  mechanism through with the background's example, step by step, saying who does what and why, as
  fully as a newcomer needs; name a cost in the step that causes it), the change map
  (`overview.map`: one lane per path the code runs, each a few steps from the entry to the effect,
  marked new, modified or unchanged and opening the unit that implements them), decisions that need
  the reader's call (each pointing at the line it is about), boundary (what the change relies on and
  how behavior changes, see **Assumptions** and **Behavior changes**; covered, not covered, watch
  out), files (one line each on what the file does).
- **Background depth.** `bg` is two or three sentences for someone who knows the module. `bgLong`
  tells the story of the change like the opening chapter of a book, for a capable engineer new to
  the module: what the system does here, how it behaved before the change and what went wrong. The
  fix belongs to the approach. Carry one concrete example through the story, and add a figure when
  the mechanism has moving parts the reader must see together. Later texts refer back to this story
  instead of retelling it.
  `depthWhy` says in one sentence why the default level fits this reader; choose the default from
  what you know about the reader.
- **Glossary.** Every domain term a newcomer would stop at, with a one-line definition and, where
  it helps, an example. The page underlines glossary terms wherever they appear; other texts can
  still explain a concept where the reader needs it, without copying the glossary line.
- **Reading order.** Group units into chapters, one per path the code actually runs. Inside a
  chapter put callers before callees, so
  every function is read with its caller already known. Mark the units whose mistakes would hurt
  the most with tier 1; tier does not change the order. Units that only pass a value through, add
  a field or rename go together in a last chapter, so the main line holds only the units that
  carry the mechanism and a newcomer can see how few they are.
- **Units.** One unit per changed function (or struct). `lines` is the whole function from the
  diff, with its comments. Test functions are not units; say what the tests cover in the
  boundary. `why` says why the reader should care about this function. `gist` is the unit's
  introduction: why the function exists in the story and why it changed here, what the reader
  should doubt while reading it. Make it as long as that takes: long for a central unit, short for
  a small helper. The introduction covers the function as a whole; anything that can only be said
  by pointing at a line belongs in that line's note, not here.
- **Notes.** Goal: a reader new to the code reads one unit (its introduction, code and notes)
  and understands where its inputs come from, where its results go, and why each changed line is
  written the way it is, without going back to the overview.
  - Say where a value or name comes from where it is first used, and who uses a result where it
    leaves the function.
  - For every decision in the code (a condition, a branch, a special value, an order of steps, a
    chosen type, an early return), say what would go wrong without it or with the obvious
    alternative.
  - Translate idioms of the language or codebase the reader may not know into plain words; skip
    the ones any engineer reads at a glance.
  - In the central units, walk the overview's example through the code: on the key lines, say
    what the variables hold for that example at that moment.
  - Cover every changed line, by its own note or by a note for its group ("the next three lines
    only pass the mode down"). Group lines unrelated to the change, such as statistics or
    logging, under one note that says the reader can skip them.
  - A reason needs a source: a code comment, the PR description, a commit message, review
    discussion, a test that would fail, or logic you can show from the code. When there is none,
    say the code gives no reason and ask the author; a choice nobody explains is a finding.
  - Attach each note to the new-file line it explains.
- **Call stacks.** `chains` run from the real entry point (`main`, a request handler, a background
  loop) down to the direct caller, one chain per distinct entry. Verify every frame's file and line
  with `grep -n`; never guess. A frame's `line` is its call site, the line that calls the next
  frame. Mark a frame `key` when the reader should notice it; the page folds
  the rest. Set `pr` on frames that are units of this review.
- **Decisions.** Only real choices the reader must make or confirm: compatibility, behavior,
  defaults, scope. Say what is unverified as unverified.
- **Assumptions.** A change is correct only if certain things hold. Name each one, and say what in
  the code enforces it and which test covers it. An assumption that nothing enforces is a finding:
  put it in `decide` or ask the author.
- **Behavior changes.** Compare the old and new code paths and list everyone whose behavior changes:
  results, memory, latency, sizes, features turned off. Include what gets worse. Derive the list
  from the code, not from the PR description; authors describe what they meant to change. Put both
  lists in `cover`; a change for the worse that the author does not mention also goes to `decide`.

### Writing

Everything a person reads in review.json, from the summary to a one-line note, is written
the way a good engineer writes a design document for a colleague who has to decide on it.

- Understanding comes first, brevity second. Assume a capable engineer new to this module.
  Explain a concept in full the first time the reading order needs it, and refer back to it
  afterwards.
- Each section answers its own question: background what goes wrong, approach how it is fixed,
  boundary what it relies on and leaves out, decisions what the reader must settle. A sentence that
  answers another section's question moves there; nothing is written twice. Unit introductions refer
  back to the overview instead of retelling it.
- Length follows weight. Spend words where the reader must judge: the core mechanism and the risky
  choices. A mechanical change, such as passing a parameter through or extracting a helper, gets a
  sentence or two.
- Let the content choose the form. Reasoning and cause and effect read best as paragraphs;
  parallel items such as cases, conditions or options read best as a list; steps that happen
  in order read best as numbered steps. Mix them freely: a sentence can introduce a list, and
  the text can go on after it.
- Start from what the reader already knows. Say what the mechanism is for before how it
  changes. Use the reader's concepts; code identifiers appear only when the reader must find
  them in the code, and the code view carries the rest.
- Pair an explanation with one concrete example: a query, a config, an incident. A made-up
  example is fine when it is clearly presented as one; never present it as observed data.
- Written, not spoken: no chatty asides, slogans or metaphors.

### Check before publishing

Give only the overview and the unit introductions to a fresh agent that has not seen the code,
and ask it to retell in its own words what problem the change solves, how the fix works and why,
what it leaves out, and what could go wrong, and to list every place it got stuck. Where the
retelling is wrong or it got stuck, rewrite and ask again. Then give it the central units' code
with their notes, pick changed lines, and ask why each one is there; a line it cannot answer
needs a better note; give it one unit at a time, without the overview. This tests clarity only; correctness comes from the sources above.

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
