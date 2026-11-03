# Contributing

1. Create a branch from `main`.
2. Set up the environment and run the tests (see [README.md](README.md)):

   ```bash
   uv sync --extra dev
   uv run pytest tests webjudge/tests
   ```

3. Never commit assignments, reference solutions, student submissions or
   anything under `data/`; check `git status` before committing (see the
   rules in the README).
4. Open a pull request against `main`; it is squash-merged after review.

Code contributions are licensed under MIT ([LICENSE](LICENSE)), documentation
under CC BY 4.0 ([LICENSE-DOCS](LICENSE-DOCS)).
