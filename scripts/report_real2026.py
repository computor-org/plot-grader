#!/usr/bin/env python3
"""Round-5 aggregates: the round-4 judge on real 2026 submissions.

Usage: report_real2026.py RESULTS_DIR MANIFEST [--sample N] [--seed S]

No human labels exist yet, so everything is compared with the official
graphics tests. Prints Markdown tables (aggregates only, no ids) and writes,
next to the manifest (gitignored):

- disagreements.jsonl  tests vs combined judge, with the model's differences,
- sample_for_human.jsonl  stratified sample in manifest schema (blind),
- sample_key.jsonl  stratum, test label and judge verdicts for that sample.
"""

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from plot_grader.tolerant import tolerant_check, unseeded_random

EXERCISES = Path("data/real2026/examples_deployed/python")

STAGES = {"tolerant": "r5_tolerant", "strict": "r5_strict"}


def load_rows(res: Path, key: str) -> tuple[dict, dict]:
    f = res / key / "rows.jsonl"
    if not (res / key / "summary.json").exists():  # run missing or unfinished
        return {}, {}
    rows = {r["case"]: r for r in map(json.loads, open(f))}
    cell = json.loads((res / key / "summary.json").read_text())["cells"][0]
    return rows, cell


def checks_for(c: dict):
    try:
        data = [json.loads(Path(p).with_suffix(".json").read_text())["plot_data"]
                for p in (c["png"], c["reference_png"])]
    except (OSError, KeyError, ValueError):
        return None
    ref_src = EXERCISES / f"itpcp.pgph.py.{c['slug']}" / c["entry"]
    random_data = ref_src.exists() and unseeded_random(ref_src.read_text())
    return tolerant_check(*data, random_data=random_data)


def matrix(title: str, cases: dict, get) -> list:
    m = Counter((c["label"], get(i, c) or "none") for i, c in cases.items())
    cols = ["PASS", "FAIL", "none"]
    lines = [f"| {title} | " + " | ".join(f"judge {k}" for k in cols) + " |",
             "|---|---|---|---|"]
    for t in ("PASS", "FAIL"):
        lines.append(f"| tests {t} | " + " | ".join(str(m[(t, k)]) for k in cols) + " |")
    agree = m[("PASS", "PASS")] + m[("FAIL", "FAIL")]
    decided = agree + m[("PASS", "FAIL")] + m[("FAIL", "PASS")]
    lines.append(f"\nAgreement with the tests: {agree}/{decided} "
                 f"({agree / decided:.2f}) of decided cases." if decided else "")
    return lines


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results")
    p.add_argument("manifest")
    p.add_argument("--sample", type=int, default=80)
    p.add_argument("--max-disagree", type=int, default=40)
    p.add_argument("--seed", type=int, default=5)
    a = p.parse_args()
    res, manifest = Path(a.results), Path(a.manifest)
    allrows = [json.loads(line) for line in open(manifest)]
    cases = {r["id"]: r for r in allrows if r.get("label") and "png" in r}
    stages = {k: load_rows(res, v) for k, v in STAGES.items()}
    tol, tol_cell = stages["tolerant"]
    strict, strict_cell = stages["strict"]
    for i, c in cases.items():
        c["checks"] = checks_for(c)
        c["tier1"] = (tol.get(i) or strict.get(i) or {}).get("tier1")
        c["model"] = (tol.get(i) or {}).get("verdict")
        c["strict"] = (strict.get(i) or {}).get("verdict")
        c["combined"] = ("FAIL" if c["checks"] else c["model"]) if c["checks"] is not None \
            else c["model"]

    out = []
    students = {r["id"].rsplit("__", 1)[1] for r in allrows}
    err = Counter("no entry file" if "no " in (r.get("harness_error") or "")
                  else "harness error" if r.get("label") is None
                  else "render error" for r in allrows if not (r.get("label") and "png" in r))
    out += ["## Counts", "",
            f"- students: {len(students)}; exercises: {len({r['slug'] for r in allrows})}; "
            f"submissions (latest per student and exercise): {len(allrows)}",
            f"- judged (harness label and rendered image): {len(cases)}; excluded: "
            + ", ".join(f"{k} {v}" for k, v in err.items()), ""]
    out += ["| decider | PASS | FAIL | none |", "|---|---|---|---|"]
    for name, key in [("official tests", "label"), ("Tier 1 (data)", "tier1"),
                      ("strict model (pair)", "strict"), ("tolerant model", "model"),
                      ("combined judge (model and checks)", "combined")]:
        cnt = Counter(c[key] for c in cases.values())
        out.append(f"| {name} | {cnt['PASS']} | {cnt['FAIL']} | {cnt[None]} |")
    chk = Counter("error" if c["checks"] is None else "problems" if c["checks"] else "ok"
                  for c in cases.values())
    kinds = Counter(pr.split()[0] for c in cases.values() for pr in (c["checks"] or []))
    kinds_cases = Counter(k for c in cases.values()
                          for k in {pr.split()[0] for pr in (c["checks"] or [])})
    out += [f"| tolerant data checks | {chk['ok']} | {chk['problems']} | {chk['error']} |", "",
            "Check problems by criterion (cases): "
            + ", ".join(f"{k} {kinds_cases[k]}" for k in sorted(kinds)), ""]

    out += ["## Tests vs combined judge", ""] + matrix("combined", cases, lambda i, c: c["combined"])
    out += ["", "## Tests vs tolerant model alone", ""] + matrix("model", cases, lambda i, c: c["model"])
    if strict:
        out += ["", "## Tests vs strict model", ""] + matrix("strict", cases, lambda i, c: c["strict"])
    out += ["", "## Tests vs Tier 1", ""] + matrix("Tier 1", cases, lambda i, c: c["tier1"])

    per = defaultdict(Counter)
    for c in cases.values():
        per[c["slug"]]["n"] += 1
        per[c["slug"]]["tests"] += c["label"] == "PASS"
        per[c["slug"]]["judge"] += c["combined"] == "PASS"
        per[c["slug"]]["t-j+"] += c["label"] == "FAIL" and c["combined"] == "PASS"
        per[c["slug"]]["t+j-"] += c["label"] == "PASS" and c["combined"] == "FAIL"
    out += ["", "## Per exercise", "",
            "| exercise | cases | tests PASS | judge PASS | tests FAIL, judge PASS | tests PASS, judge FAIL |",
            "|---|---|---|---|---|---|"]
    for s in sorted(per):
        d = per[s]
        out.append(f"| {s} | {d['n']} | {d['tests']} | {d['judge']} | {d['t-j+']} | {d['t+j-']} |")

    out += ["", "## Throughput", ""]
    for name, cell in (("tolerant", tol_cell), ("strict", strict_cell)):
        if cell:
            out.append(f"- {name}: {cell['calls']} calls; last invocation {cell.get('timed_calls')} "
                       f"calls in {cell.get('wall_s')} s, "
                       f"{cell.get('throughput_per_min')} calls/min at {cell.get('workers')} workers, "
                       f"p50 {cell['latency_p50_s']:.1f} s, p95 {cell['latency_p95_s']:.1f} s, "
                       f"unusable {sum(1 for r in (tol if name == 'tolerant' else strict).values() if not r['verdict'])}")
    print("\n".join(out))

    # Disagreements and the blind sample for the human check.
    dis = [i for i, c in cases.items() if c["combined"] and c["combined"] != c["label"]]
    with open(manifest.parent / "disagreements.jsonl", "w") as fh:
        for i in dis:
            c = cases[i]
            fh.write(json.dumps({"id": i, "slug": c["slug"], "tests": c["label"],
                                 "graphics_failed": c.get("graphics_failed"),
                                 "model": c["model"], "checks": c["checks"],
                                 "differences": (tol.get(i) or {}).get("differences"),
                                 "png": c["png"], "reference_png": c["reference_png"]}) + "\n")
    rng = random.Random(a.seed)
    by_dir = defaultdict(list)
    for i in dis:
        by_dir[cases[i]["label"]].append(i)
    for v in by_dir.values():
        rng.shuffle(v)
    pick, k = [], 0
    while len(pick) < min(a.max_disagree, len(dis)):  # alternate both directions
        lst = by_dir[("FAIL", "PASS")[k % 2]]
        if lst:
            pick.append(lst.pop())
        k += 1
    agree = [i for i, c in cases.items() if c["combined"] == c["label"]]
    rng.shuffle(agree)
    pick += agree[:max(0, a.sample - len(pick))]
    rng.shuffle(pick)
    keep = {"id", "slug", "source", "entry", "reference_png", "png", "label",
            "graphics_failed", "graphics_total", "overall", "n_figures"}
    with open(manifest.parent / "sample_for_human.jsonl", "w") as fh, \
            open(manifest.parent / "sample_key.jsonl", "w") as kh:
        for i in pick:
            c = cases[i]
            fh.write(json.dumps({k: v for k, v in c.items() if k in keep}) + "\n")
            kh.write(json.dumps({"id": i, "stratum": "disagree" if i in dis else "agree",
                                 "tests": c["label"], "combined": c["combined"],
                                 "model": c["model"], "checks": c["checks"]}) + "\n")


if __name__ == "__main__":
    main()
