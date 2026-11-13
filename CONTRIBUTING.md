# Contributing to cluster-mcp

Feedback comes in as GitHub issues. Each issue should read as a **seed**: a short, self-contained
write-up that a maintainer, or the maintainer's own agent, can turn into a fix without asking you
anything else. The format below is the one the project already uses for its own deferred work in
[`issues/`](issues/).

**If you are an AI agent** helping a user report something, this file is for you. Follow it step by
step. Show the user the finished issue text and get their go-ahead before you file it: an issue is
public, and it goes out under their name.

## Before you file

1. **Security problems never go in a public issue.** Anything that lets one user reach another
   user's files, jobs or identity, gets around authentication, or runs a command the server should
   refuse: report it privately to rcac-help@purdue.edu, as [SECURITY.md](SECURITY.md) says. Stop here.
2. **Search first.** Look through the [open issues](https://github.com/PurdueRCAC/cluster-mcp/issues)
   and the repository's [`issues/`](issues/) folder and [ROADMAP.md](ROADMAP.md). If your problem is
   already there, add a comment with your new evidence rather than opening a duplicate.
3. **Strip private data.** Remove tokens, passwords, keys, host keys, and the contents of your
   files or jobs. Your username, cluster name, and generic paths such as `/scratch/<cluster>/<user>`
   are fine. Replace anything else with a placeholder such as `<redacted>`.

## What to collect

The issue needs enough for someone else to see the same thing.

- **Version:** the output of `cluster-mcp --version`, or the release you installed (for example `0.2.1`).
- **How you installed it:** the exact `uvx` or `uv` line, including the extras (`[rcac]`, `[slurm,rcac]`
  and so on).
- **How you ran it:** the run mode (local, SSH, or the hosted HTTP server), the cluster, and the
  MCP client or agent you used (for example Claude Code, Claude Desktop, Cursor, VS Code).
- **What you did:** the tool you called and the arguments you passed. Exact values are best.
- **What happened:** the tool's output or error, verbatim, trimmed to the part that matters.
- **What you expected instead,** and why. Point at the tool's description or the docs
  ([docs/core](docs/core/README.md), [docs/slurm](docs/slurm/README.md), [docs/rcac](docs/rcac/README.md))
  if they say something different from what you saw.
- **How often:** every time, sometimes, or once.

If you have read the code, say where the behaviour comes from: a file and function, such as
`packages/cluster-mcp-slurm/src/cluster_mcp/slurm/tools.py`, `sbatch`. That shortens the fix a lot.
Guesses are welcome when they are labelled as guesses.

## The issue

**Title:** state the problem as a fact, in one line. Write "`squeue` drops jobs from a second
partition", not "squeue bug" or "Suggestion".

**Body:** use these headings, in this order.

```markdown
## Problem

What goes wrong, or what is missing, in plain words. Then the evidence: the version, the install
line, the run mode, the cluster and the client, the tool call, and its output verbatim.

## Outcome / vision

What it should do instead, from the user's side. One short paragraph.

## Sketch of the acceptance criteria

- **R1**: WHEN <situation>, the server SHALL <observable behaviour>.
- **R2**: ...

Each criterion is something a test could check. Keep to the behaviour; leave the design to the fix.

## Proposed fix (optional)

Where the fix would go and roughly what it changes. Include a patch if you have one, but say whether
you ran the test suite (`uv sync`, then `pytest`) against it.

## Notes

Anything else: workarounds you found, related issues, what you ruled out.
```

**Labels:** add `bug` for wrong behaviour and `enhancement` for something new. Leave everything else
to the maintainers.

## What happens next

A maintainer reads the issue and may ask a question in the thread. A clear issue becomes a seed in
[`issues/`](issues/), gets an entry in [ROADMAP.md](ROADMAP.md), and is fixed in a cycle with its own
tests. The issue is closed with a link to the change that fixed it.

## Pull requests

Small fixes are welcome. Open the issue first, so the fix has a stated problem to answer. Then follow
[AGENTS.md](AGENTS.md), which holds the repository's rules for code, tests and documentation:

- branch from `develop`, not `main`;
- run the full suite (`pytest`) before you push;
- keep the change to the one problem the issue states.
