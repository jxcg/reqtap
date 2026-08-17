# CLAUDE.md

Guidance for AI assistants working in this repository.

Deliberately contains no description of how the code is organised or what
modules do — read the source for that, it is always current. Stale notes are
worse than none, because they get trusted over the actual files.

## Setup

Dev tools are not preinstalled. Before running anything:

```bash
uv venv .venv && uv pip install -e ".[dev]"
export PATH="$PWD/.venv/bin:$PATH"
```

## Checks

All three must pass before any change is pushed:

```bash
pytest          # full suite
ruff check .    # lint
mypy src tests  # types, strict mode
```

Note: `ruff format --check` currently reports drift in 7 files on `main`.
That is pre-existing. Do not fix it as a side effect of unrelated work.

## Communication

No jargon. Plain, everyday language — especially for anything requiring action.
Where a technical term is unavoidable, say what it means in one short clause.

## Branches

Name branches `issue-X`, where X is the issue number (e.g. `issue-51`).

## Commits

Never add `Co-Authored-By: Claude` or `Claude-Session:` trailers to commit
messages, pull request bodies, or anything else pushed to the repository.

## Pull requests

- **Addresses Issue:** link the issue. If there isn't one, omit the line.
- **Type:** bug / feature / fix.
- **Up to 5 bullet points.** Fewer is fine; never pad to reach five.
- **Short, snappy description.** Never drone on in prose.
- **A before/after table** where applicable — previous vs. current behaviour.

Keep it tight. Brevity over completeness.
