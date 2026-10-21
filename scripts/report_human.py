#!/usr/bin/env python3
"""Agreement of the human judge with our labels, the tests and the model.

Usage: report_human.py [--answers data/human_labels/answers.jsonl]
                       [--mapping data/judge_package/private/mapping.json]
                       [--judge rater1] [--out report.md]

Joins the human answers (random case ids) to the source cases via the
private mapping. For eval-set cases the deciders are: our visual label
(visual_labels.jsonl), the official tests (manifest "label"), Tier 1 and the
tolerant model with and without the tolerant data checks (round-4 results).
For other manifests only fields present in the manifest row are used
("visual", "label"). Agreement is over cases where both the human and the
decider give PASS/FAIL; "Unsicher" answers are counted separately. Repeated
cases enter the agreement once (first showing) and give self-consistency.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

EVAL = "data/eval_set/manifest.jsonl"
DECIDERS = [("visual", "our visual label"), ("tests", "official tests"),
            ("tier1", "Tier 1 (data)"), ("model", "tolerant model"),
            ("model_checks", "tolerant model and tolerant checks")]


def load(path) -> list:
    return [json.loads(x) for x in open(path) if x.strip()]


def kappa(pairs: list) -> tuple:
    """Percent agreement and Cohen's kappa for (a, b) PASS/FAIL pairs."""
    n = len(pairs)
    if not n:
        return None, None
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a == "PASS" for a, _ in pairs) / n
    pb = sum(b == "PASS" for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return po, (po - pe) / (1 - pe) if pe < 1 else None


def eval_deciders(ids: set, labels_path: str, results: Path) -> dict:
    from plot_grader.tolerant import tolerant_check, unseeded_random

    examples = Path.home() / "code/codeability/examples/python"

    man = {r["id"]: r for r in load(EVAL)}
    vis = {r["id"]: r for r in load(labels_path)}
    tol = {r["case"]: r for r in load(results / "r4_tolerant" / "rows.jsonl")}
    out = {}
    for i in ids:
        c = man[i]
        pd = [json.loads(Path(p).with_suffix(".json").read_text())["plot_data"]
              for p in (c["png"], c["reference_png"])]
        model = tol.get(i, {}).get("verdict")
        ref_src = examples / f"itpcp.pgph.py.{c['slug']}" / c["entry"]
        rnd = ref_src.exists() and unseeded_random(ref_src.read_text())
        out[i] = {"visual": vis.get(i, {}).get("visual"), "tests": c.get("label"),
                  "tier1": tol.get(i, {}).get("tier1"), "model": model,
                  "model_checks": "FAIL" if tolerant_check(*pd, random_data=rnd) else model,
                  "criterion": vis.get(i, {}).get("criterion", "")}
    return out


def fmt(x, spec=".2f"):
    return "-" if x is None else format(x, spec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", default="data/human_labels/answers.jsonl")
    ap.add_argument("--mapping", default="data/judge_package/private/mapping.json")
    ap.add_argument("--labels", default="data/eval_set/visual_labels.jsonl")
    ap.add_argument("--results", default="data/vlm_eval/r4")
    ap.add_argument("--judge", default="rater1")
    ap.add_argument("--out", help="write Markdown here instead of stdout")
    a = ap.parse_args()
    mapping = json.loads(Path(a.mapping).read_text())
    cases = {c["case_id"]: c for c in mapping["cases"]}
    human = {r["case_id"]: r for r in load(a.answers)
             if r["judge"] == a.judge and r["case_id"] in cases}
    eval_ids = {c["source_id"] for c in cases.values() if c["manifest"] == EVAL}
    dec = eval_deciders(eval_ids, a.labels, Path(a.results)) if eval_ids else {}
    for m in set(mapping["manifests"]) - {EVAL}:
        for r in load(m):
            dec[r["id"]] = {"visual": r.get("visual"), "tests": r.get("label")}

    firsts = [c for c in mapping["cases"] if not c["repeat_of"]]
    answered = [c for c in firsts if human.get(c["case_id"], {}).get("verdict")]
    verdicts = Counter(human[c["case_id"]]["verdict"] for c in answered)
    lines = [f"# Human judge `{a.judge}` vs deciders", "",
             f"{len(answered)} of {len(firsts)} cases answered "
             f"(PASS {verdicts['PASS']}, FAIL {verdicts['FAIL']}, "
             f"UNSURE {verdicts['UNSURE']}); agreement over PASS/FAIL answers only.",
             "The eval-set selection over-represents cases where our label, the",
             "tests and the model disagree, so absolute agreement is lower than",
             "on all 244 cases; compare the deciders with each other.", ""]
    for m in mapping["manifests"]:
        sub = [c for c in answered if c["manifest"] == m
               and human[c["case_id"]]["verdict"] != "UNSURE"]
        lines += [f"## {m} ({len(sub)} cases)", "",
                  "| decider | n | agreement | Cohen's kappa | human PASS, decider FAIL "
                  "| human FAIL, decider PASS |", "|---|---|---|---|---|---|"]
        for key, name in DECIDERS:
            pairs = [(human[c["case_id"]]["verdict"], dec[c["source_id"]].get(key))
                     for c in sub]
            pairs = [(h, d) for h, d in pairs if d in ("PASS", "FAIL")]
            if not pairs:
                continue
            po, k = kappa(pairs)
            lines.append(f"| {name} | {len(pairs)} | {fmt(po)} | {fmt(k)} "
                         f"| {sum(h == 'PASS' and d == 'FAIL' for h, d in pairs)} "
                         f"| {sum(h == 'FAIL' and d == 'PASS' for h, d in pairs)} |")
        lines.append("")

    # Self-consistency on the repeated cases.
    reps = [(c["repeat_of"], c["case_id"]) for c in mapping["cases"] if c["repeat_of"]]
    both = [(human[x]["verdict"], human[y]["verdict"]) for x, y in reps
            if human.get(x, {}).get("verdict") and human.get(y, {}).get("verdict")]
    pf = [(x, y) for x, y in both if "UNSURE" not in (x, y)]
    po, k = kappa(pf)
    lines += ["## Self-consistency", "",
              f"{len(both)} of {len(reps)} repeated cases answered twice; "
              f"{sum(x == y for x, y in both)} identical answers (including UNSURE). "
              f"PASS/FAIL both times: {len(pf)}, agreement {fmt(po)}, kappa {fmt(k)}.",
              ""]

    # Disagreements with our visual label, for review.
    by = defaultdict(list)
    for c in answered:
        h, d = human[c["case_id"]], dec[c["source_id"]]
        if d.get("visual") and h["verdict"] != d["visual"]:
            by[c["kind"]].append((c, h, d))
    lines += ["## Human differs from our visual label", "",
              "| kind | source id | human | criteria | ours | our criterion | comment |",
              "|---|---|---|---|---|---|---|"]
    for kind in sorted(by):
        for c, h, d in by[kind]:
            com = (h.get("comment") or "").replace("|", "/").replace("\n", " ")[:120]
            lines.append(f"| {kind} | {c['source_id']} | {h['verdict']} "
                         f"| {','.join(h.get('criteria') or [])} | {d['visual']} "
                         f"| {d.get('criterion', '')} | {com} |")
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text)
        print(f"wrote {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
