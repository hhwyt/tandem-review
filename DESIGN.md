# Tandem Review: design decisions

The state of the design as agreed so far. The prototypes in `prototypes/` follow it.

## Two review modes

| | Self review | PR review |
|---|---|---|
| Whose code | Changes the agent wrote in this session | Someone else's pull request |
| Rounds | As many as needed: comment, the agent edits, the page shows the new code | Usually one |
| Where comments go | Back to the agent, which edits the local branch | GitHub, as inline review comments on the PR |
| What "Send" does | Hands the comments to the agent (`tandem wait` returns) | Shows a preview of the GitHub review, then the agent posts it with `gh` after the reviewer confirms |

The page always shows the latest state. It does not display a round number; earlier rounds stay in
`.tandem/` for the agent, not on screen.

### PR review: posting to GitHub

- Comments become one GitHub review (`gh api repos/<owner>/<repo>/pulls/<n>/reviews`), each
  comment anchored to `path`, `line` (and `start_line` for a range) on the PR's head commit.
- A comment on a line that is not part of the diff cannot be inline; it goes into the review body
  with its file and line.
- Posting is an outward action: the page shows exactly what will be posted and posts only after
  the reviewer confirms. The review event defaults to `COMMENT`; approving or requesting changes
  is the reviewer's explicit choice.

### Preflight (run by the skill before opening the page)

- Python 3 is available (the server uses only the standard library).
- The working tree and the base commit resolve; the diff is not empty.
- PR review only: `gh` is installed and authenticated, the PR exists, its head commit matches the
  local checkout, and the account can comment on it.
- A free local port; the server binds to 127.0.0.1 with a per-session token.

## Page

- Two tabs: **Overview** and **Code**.
- Overview, in this order: summary, background and approach, where the change attaches (changed nodes jump to code), decisions that need the reviewer's call (each jumps to the code it is about), boundary, files. A faint animated tandem sits in the background. No code on this page.
- Code: two orderings only. **Reading order** (default): chapters along the paths the code runs,
  callers before callees. **By file**: for reference. Critical functions carry a ⚑; importance
  does not change the order.
- Notes appear as faint lines above the code they explain, are never copied with the code, and
  can be hidden.
- Call hierarchy panel: the call stack from the entry point (`main`) down to the function as a
  tree, with unimportant frames folded; and what the function calls. Functions in the change jump
  within the page; others open in the editor.
- Comments on a line or a range, kinds Must fix / Follow-up / Question, sent in one batch.
- English by default, Chinese available; a one-time hint points at the switch.
- Ten color themes; every color on the page derives from the active theme.
- Keyboard: J/K, C, N/P, E, `?` (help button in the bottom-right corner).

## Persistence

- Preferences (theme, language, notes on/off, ordering, editor) live in
  `~/.config/tandem/prefs.json`, written by the local server. The agent reads the same file.
- Review progress (reviewed functions, draft comments) lives in `.tandem/` in the reviewed
  repository, ignored by git.

## Live update

After the agent applies comments it runs `tandem publish`; the server bumps a version and the page
reloads the data in place, keeping the scroll position and unsent drafts.
