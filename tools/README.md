# Submission tools

Fetch and analyse real student submissions from a GitLab group. All output
goes to `data/`, which is gitignored. See the Rules section of `../README.md`.

## Setup

```bash
glab auth login --hostname gitlab.example.org   # token scopes: read_api, read_repository
glab auth status --hostname gitlab.example.org
```

The fetch script needs `glab` and `jq`. Cloning uses SSH, so your key must be
registered on that GitLab instance.

## Fetch

```bash
GITLAB_HOST=gitlab.example.org ./tools/fetch_student_submissions.sh my-course/2025/students
```

The group path is a required argument; `GITLAB_HOST` defaults to `gitlab.com`.
This clones or updates every project in the given group (including subgroups) into
`data/student_submissions/<student>/`, and writes `index.json` and
`plotting_files.txt` next to them. The log goes to `data/fetch_log.txt`.

## Analyse

```bash
uv run python tools/analyze_submissions.py
```

This counts how submissions to the plotting assignments vary (colour notation,
line styles, plot order) and writes `data/student_submissions/analysis_results.json`.
Use the counts to choose realistic variants for `plot_grader.stress_tests`.

Student code stays in `data/`. Do not share it outside the grading work.
