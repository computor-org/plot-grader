# AGENTS.md

`README.md` describes the project and how to run it.

## Hard rule

No assignment reference solutions and no student data in any commit (see the
Rules section of `README.md`). Test fixtures are trivial synthetic
plots such as `ax.plot([1, 2], [1, 4], 'r-')`, never assignment content.
Fetched and generated files live in `data/`, which is gitignored.

## Commands

```bash
uv sync --extra dev
uvx ruff check .
uv run python scripts/run_validation.py
```

`mlx-vlm` (`--extra mlx`) works only on Apple Silicon. Code outside
`tier4_real.py` must import without it.

## Conventions

- Stage files explicitly, and check `git status` for data before committing.
- ruff, 88 columns. Fix what you touch; do not reformat whole files.
- Keep docs short and factual. Do not add status reports, summaries or
  emoji-decorated checklists to the repo; results go in `docs/history/`.
