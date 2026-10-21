# plot-grader

Grades matplotlib plot submissions against a reference solution. This is the
plot-evaluation prototype for [Computor](https://github.com/computor-org)
(netidee project 8012). [docs/criteria.md](docs/criteria.md) defines when a
plot is acceptable, [docs/integration.md](docs/integration.md) describes the
hook into the Computor test harness, and [docs/history/](docs/history/)
records past evaluation runs.

**Data is not included.** This repository contains code only: no assignments,
reference solutions or student submissions. The evaluation scripts in
`scripts/` and `tools/` need your own assignment and submission data; the
library and the test suite do not.

## Install

```bash
uv sync               # base
uv sync --extra dev   # ruff, mypy, pytest-cov
uv sync --extra mlx   # Qwen3-VL Tier 4 via mlx-vlm (Apple Silicon only)
```

## How it works

`PlotGrader` (`grader.py`) runs the student script and the reference, then
applies the tiers in order. It stops at the first tier whose confidence
reaches `confidence_threshold` (default 0.90). The older catester tests compared
exact properties such as `figure(1).axes[0].lines[0]._linestyle`. They fail
correct plots that differ in line order, colour notation or OOP vs pyplot
style. The tiers normalise these differences first and compare images only
when the extracted data cannot decide.

1. `tier1.py`: checks on the extracted plot data (values, colours, line
   styles, markers, labels), independent of plotting order.
2. `tier2.py`: looser structural matching (sets of colours and styles, curve
   count, fuzzy labels).
3. `tier3.py`: image similarity with OpenCV (SSIM, histograms, edges).
4. Tier 4, a vision-language model, used only when one is configured.
   `judges.py` calls models over HTTP: chat completions with a JSON verdict,
   or JEV `/v1/systemone` with yes/no probabilities. Endpoints are in
   `configs/vlm_endpoints.json`, which ships with placeholder hosts and model
   names to replace with your own OpenAI-compatible endpoints. `tier4_real.py` runs Qwen3-VL-4B locally
   through `mlx-vlm` (`use_real_ai=True`).

## Run

```bash
uv run python scripts/run_validation.py          # synthetic variants; --ai, --test-mode
uv run python scripts/run_ai_eval.py             # Tier-1 failures from real submissions, writes data/ai_eval/
uv run python scripts/run_vlm_eval.py --reference REF   # models x chat/JEV x views, writes data/vlm_eval/
```

`run_validation.py` and `run_ai_eval.py` take `--judge 27b|4b|flash-next
--mode chat|jev --view pair|student` to use an HTTP model as Tier 4.

These scripts expect your own assignment repository in `../assignments/`
(`XX_UnitXX/YY_name/` with `*_master.py`, `test.yaml` and
`localTests/_reference/`) or a reference given with `--reference`. All output
goes to `data/`, which is gitignored.

```python
from pathlib import Path
from plot_grader.grader import PlotGrader

result = PlotGrader().grade_submission(
    submission_path=Path("student_plot.py"),
    reference_path=Path("reference_plot.py"),
)
print(result.status, result.tier, result.score, result.confidence)
```

## Tests

```bash
uv sync --extra dev
uv run pytest tests webjudge/tests
```

The tests use only trivial synthetic plots and a stub model.

## Rules for contributors

Never commit reference solutions or student data: students could find the
solutions here. `.gitignore` covers `data/`, `assignments/`, `submissions/`
and the solution patterns; check `git status` before committing.
`tools/` contains the scripts that fetch submissions from a GitLab group into
`data/` (see [tools/README.md](tools/README.md)).

## License

Code: MIT (see [LICENSE](LICENSE)). Documentation (`docs/` and Markdown guides): CC BY 4.0 (see [LICENSE-DOCS](LICENSE-DOCS)).
