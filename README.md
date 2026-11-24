**English** | [简体中文](README.zh-CN.md)

# Tandem Review

<p align="center"><img src="brand/tandem.svg" alt="Tandem: a person and an agent riding a tandem bicycle over a road of code" width="560"></p>

**Human steers. Agent pedals. Review together.**

Tandem Review is a browser page where a person and a coding agent review a change together.
The agent prepares the review; the person reads, judges and comments; the agent applies the
comments; the next round begins.

It works with any agent that can write a JSON file and run a shell command: Claude Code, Codex,
DeepSeek and others.

## What the reviewer sees

1. **Overview first.** A summary of the change, the decisions that need the reviewer's call, the
   background, the approach, a diagram of where the change attaches, what is covered and what is
   not, and every file with one line on what it does.
2. **Reading order.** Functions grouped into chapters along the paths the code actually runs,
   callers before callees, so every function is read with its context. Critical functions carry a
   ⚑. A by-file view is available for reference.
3. **Notes between the lines.** The agent's explanation of each block appears as a faint line above
   the code it describes. Notes are never copied with the code and can be hidden with one key.
4. **Call hierarchy.** A side panel shows who calls the current function, from which entry points,
   and what it calls, as trees. Functions in the change jump within the page; others open in your
   editor.
5. **Comments in one batch.** Comment on a line or a range, mark it Must fix, Follow-up or Question,
   and send all comments to the agent at once. The agent replies with what it changed and the next
   round starts.

The interface is in English or Chinese; switch in the top right corner.

## Install

### With your agent (recommended)

Copy this prompt and send it to your coding agent (Claude Code, Codex, or any agent that can run
shell commands):

```text
Install Tandem Review for me:
1. Clone https://github.com/hhwyt/tandem-review into ~/tandem-review (git pull if it is already there).
2. Check that python3 is 3.9 or newer.
3. Make the `tandem` command available: link ~/tandem-review/bin/tandem into a directory on my PATH,
   such as ~/.local/bin; create the directory and add it to PATH in my shell profile if needed.
4. Install the skill: for Claude Code, link ~/tandem-review/skill to ~/.claude/skills/tandem-review;
   for other agents, add ~/tandem-review/skill/SKILL.md to your instructions.
5. Run `tandem --help` and tell me the result.
```

### Manually

Requirements: Python 3.9 or newer. `gh` (GitHub CLI, logged in) only for posting to pull requests.

```bash
git clone https://github.com/hhwyt/tandem-review.git ~/tandem-review
mkdir -p ~/.local/bin && ln -s ~/tandem-review/bin/tandem ~/.local/bin/tandem  # ~/.local/bin must be on PATH
```

Give your agent the skill:

- **Claude Code**: `ln -s ~/tandem-review/skill ~/.claude/skills/tandem-review`
- **Codex and others**: point the agent at `skill/SKILL.md`, or paste it into its instructions.

## Use

Ask your agent: *"Review my change in Tandem"* or *"Review pingcap/tidb#123 in Tandem"*. The agent
then:

1. runs `tandem preflight`, writes `review.json` (see [docs/review-json.md](docs/review-json.md)),
2. starts the page with `tandem serve --review <dir> --open`,
3. waits with `tandem wait --review <dir>` while you read and comment,
4. applies your comments and runs `tandem publish` (your own change), or posts them to the pull
   request with `tandem post-github ... --yes` after you confirm (someone else's).

The page keeps your settings (language, theme, editor, notes) in `~/.config/tandem/prefs.json` and
your progress in the review directory. It binds to 127.0.0.1 only and every request carries a
per-session token.

Try it without an agent:

```bash
mkdir -p /tmp/tandem-demo && cp examples/pr-73235/review.json /tmp/tandem-demo/
tandem serve --review /tmp/tandem-demo --open
```

## Development

```bash
python3 -m unittest discover -s tests
node scripts/build_example.js   # rebuild the example from prototypes/
```

Design decisions: [DESIGN.md](DESIGN.md). Interfaces: [docs/v1-contract.md](docs/v1-contract.md).
Early clickable prototypes: [`prototypes/`](prototypes/).

## License

[MIT](LICENSE)
