# First trials, 2025-11-19/20

Round 1 of the plot evaluation. Later rounds are recorded in this directory.

## Setup

- One assignment: `01_Unit01/04_plot_docstr` (several curves with given colours
  and line styles).
- Test data: synthetic variants of the reference solution generated with
  `plot_grader.stress_tests`, plus two files from `../assignments/`.
- Tier 4, vision-language model: `lmstudio-community/Qwen3-VL-4B-Instruct-MLX-8bit`
  through `mlx-vlm` on Apple Silicon. The earliest runs used `MockAIGrader`,
  which writes fake feedback from the tier results without a model.

## Results

Synthetic set of 15 variants:

| Group | Variants | Outcome |
|---|---|---|
| Should pass | reverse plot order, mixed plot order, colour name, hex colour, OOP interface | all passed |
| Should fail | missing curve, wrong colour, wrong line style, data off by 10 %, missing label | all failed |
| Borderline | data off by 3 %, dark red vs red, dash-dot vs dashed | failed |
| Borderline | axis limits 5 % larger, 50 instead of 200 points | passed |

Tier 1 decided all 15 with confidence 1.0, so Tiers 2 and 3 never ran. A
separate set of 10 variants (5 positive, 5 negative) gave the same picture.
Of the two files from `../assignments/`, the template failed, and a solution
written by GPT failed because of a wrong colour. The old report called this a
"50 % pass rate", which does not match two failures.

Qwen3-VL-4B (from commit messages):

- 292add9: in the first system test with the real model, 8 cases were all
  correct, but Tier 1 decided each case and the model was never called.
- 8b5dd66: the prompt asked for JSON (`verdict`, `has_differences`,
  `differences`, `overall_assessment`, `hint`) at temperature 0.1. It got
  5 of 5 known cases right.
- 31c09ba: the earlier tiers' findings were removed from the prompt so the
  model judged alone (data leakage), on all 15 variants. No accuracy numbers
  were recorded.
- 6a227fa: back to using the tier findings. The model writes feedback and no
  longer makes the verdict.
- b562b0e (2025-11-20): `scripts/run_ai_eval.py` ran the model on real
  submissions that Tier 1 had failed. Its output in `data/ai_eval/` was never
  committed.

## What we took from it

- For a strictly specified plotting task, exact checks on the extracted plot
  data are enough and fast (under 50 ms). The image tiers were never needed.
- The 4B vision model was not trusted as an independent judge. The team's
  impression was that its verdicts were too weak, so it was used only for
  feedback text. No numbers were recorded for this, and round 2 has to
  measure it.
- Borderline cases are a question of course policy, not of the grader.
