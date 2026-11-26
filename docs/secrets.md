# Secrets

This repository is public. Keys are read from environment variables only and
are never committed. `.env.example` lists the variable names; put real values in
your environment or in a local `.env` (gitignored).

## Setup

Run once per clone (the setting is shared by all its worktrees):

    git config core.hooksPath .githooks

The `pre-commit` hook then runs `tools/secret_scan.py` on the staged content,
and the `pre-push` hook runs it on the commits about to be pushed. Both need
Python 3.9 or later: they try `.venv` first, then `python3`, `python` and `py`.
If no Python works, or the scan cannot run, the commit or push is blocked. If
`gitleaks` is on `PATH`, it runs as well and can block too; it is optional.

The hook is read from the checked-out files. A checkout of a branch that does
not contain `.githooks/` runs no hook, and Git does not warn about it.

Development setup (Windows paths; use `.venv/bin/python` elsewhere):

    python -m venv .venv
    .venv/Scripts/python -m pip install -r requirements.txt
    .venv/Scripts/python -m pytest

## Pushing

The commit hook can be skipped, and merges and rebases do not always run it, so
`pre-push` checks each pushed ref again:

- Existing remote branch: the commits between its current commit and yours.
- New branch or tag: the commits that no tracking ref of that remote contains.
  A push to a URL has no tracking refs, so its whole history is checked.
- Remote commit unknown locally (someone else pushed): the whole history of what
  is pushed.
- Deleting a remote ref: nothing to check.
- A ref that does not lead to a commit (for example a tag on a file) is blocked.

The same range scan can be run by hand:

    python tools/secret_scan.py --range origin/main..HEAD

`--range` checks the content each commit introduced (including content removed
again later) and the commit messages. Annotated tag messages are not checked.
Use `--range HEAD` for the whole history. `--all` checks every tracked file as
currently staged. Exit status: 0 clean, 1 findings, 2 the scan could not run.

## What is blocked

- Keys with a known prefix: `sk-` (Anthropic, OpenAI, OpenRouter, DeepSeek),
  Google, xAI and Vercel AI Gateway.
- Private key blocks.
- A literal value assigned to a variable whose name ends in `API_KEY` (upper
  case), or given as the default when looking it up (`getenv`, `.get` or
  `.setdefault`, written on one line). This is the only rule for keys without a recognised prefix, such as
  Mistral keys, so a key stored under another name is not detected.
- Files named `.env`, `.env.*`, `*.env`, `.envrc`, `*.key`, `*.pem`, `*.pem.*`,
  `*.p12`, `*.pfx`, `*.private.md`, or like an SSH private key (`id_rsa`,
  `id_ed25519` and similar), even when force-added. `.env.example` and `*.pub`
  keys are allowed.

Findings show the file, line and rule, never the matched value.

Compressed files, other binary formats and Git LFS content are not inspected.

## False positives

For the `API_KEY` assignment rule:

- Leave the value empty, refer to the environment (`$NAME`, `%NAME%`,
  `os.environ[...]`, `os.getenv(...)`, `process.env.NAME`), or use a
  placeholder in angle brackets such as `<your-key>`.
- If the line is harmless and must stay as it is, add the comment
  `secret-scan: allow` on that line. Review such lines with care.

The marker does not silence key prefixes or private key blocks. In tests,
assemble fake keys at runtime (for example `"sk-" + "ant-" + "x" * 40`). For
any other false positive, change the rule in `tools/secret_scan.py` and add a
test. Do not use `git commit --no-verify` to get past the hook.

## If a secret was committed

Revoke the key at the provider first. Removing it in a later commit is not
enough. Rewrite the unpushed commits before pushing; if it was already pushed,
treat it as public.
