# webjudge (plotcheck)

Blind human judging of student plots against the reference, for an
independent check of our visual labels, the official tests and the model.
The judge sees one pair per screen (reference left, submission right) and
answers Akzeptabel / Nicht akzeptabel / Unsicher against `docs/criteria.md`
(German translation in `static/anleitung.html`), optionally with the
violated criterion M1–M6 and a comment. Python standard library only; every
click goes to SQLite (`answers`: current answer, `events`: every click).

Judge links and the admin token are written to
`data/judge_package/private/links.txt` (never in git).

## Package

```bash
uv run python scripts/build_judge_package.py        # eval set: 120 cases + 10 repeats
```

`data/judge_package/public/` (images ≤1000 px wide, metadata stripped, random
ids only) is uploaded. `data/judge_package/private/mapping.json` maps the ids
back to source cases and stays local.

## Add the real2026 sample later

Re-run with every manifest; ids and order of existing cases are kept, the new
cases are appended (shuffled), and answers already given stay valid:

```bash
uv run python scripts/build_judge_package.py \
    --manifest data/eval_set/manifest.jsonl \
    --manifest data/real2026/sample_for_human.jsonl
# then copy data/judge_package/public/ and webjudge/ to the host and restart
```

## Export and report

```bash
uv run python scripts/fetch_human_labels.py --base https://<plotcheck-host>   # -> data/human_labels/*.jsonl
uv run python scripts/report_human.py --judge rater1 [--out report.md]
```

The report gives agreement and Cohen's kappa of the human with our visual
labels, the tests, Tier 1, the tolerant model and model + tolerant checks,
plus self-consistency on the repeated cases. Judge `test` is for smoke tests.

## Tests and local run

```bash
uv run pytest webjudge/tests
python3 webjudge/app.py tokens /tmp/t.json /tmp/links.txt http://127.0.0.1:18790 me
PLOTCHECK_PACKAGE=data/judge_package/public PLOTCHECK_DB=/tmp/j.sqlite \
  PLOTCHECK_TOKENS=/tmp/t.json PLOTCHECK_INSECURE_COOKIE=1 python3 webjudge/app.py serve
```

## Deployment

Serve `webjudge/app.py serve` behind a TLS reverse proxy that answers 403
without the token cookie, with `PLOTCHECK_PACKAGE`, `PLOTCHECK_DB` and
`PLOTCHECK_TOKENS` set as in the local run above. Only
`data/judge_package/public/` goes to the host. After the check, fetch the
labels once more and delete the package, database and tokens from the host.
