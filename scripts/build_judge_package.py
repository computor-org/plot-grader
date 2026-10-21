#!/usr/bin/env python3
"""Anonymised judging package for the human judge (webjudge/).

Usage:
  build_judge_package.py [--manifest M ...] [--out data/judge_package]

The first manifest is the eval set: a stratified selection of --n cases
(all cases where our visual label, the official tests and the tolerant
model or model+checks disagree, at least --min-per-kind per kind of change,
the rest proportional), plus --repeats cases shown a second time later.
Every further manifest (e.g. data/real2026/sample_for_human.jsonl) is taken
in full. Rows need "id", "png" and "reference_png".

Output:
  OUT/public/cases.json, OUT/public/img/*.png   -> uploaded to the server
  OUT/private/mapping.json                      -> stays local (data/ is ignored)

Case ids are random. Re-running keeps the ids and order of cases already in
private/mapping.json and appends new ones, so a judge who has started keeps
her answers.
"""

import argparse
import json
import random
import secrets
from collections import defaultdict
from pathlib import Path

from PIL import Image

MAX_W = 1000
EVAL = "data/eval_set/manifest.jsonl"
# Worked examples on the instruction page (never among the judged cases);
# webjudge/static/anleitung.html explains them in this order.
EXAMPLES = [
    "lab_exercise2__examples_gptSolution__1c4943",  # PASS: colours, legend (T1)
    "basis3__mutation_half_x__3b476f",  # FAIL M3: half the x range
    "basis2__mutation_drop_curve__5cbeb7",  # FAIL M1: a curve missing
]


def kind(row: dict) -> str:
    src = row.get("source", "")
    return src.split("/", 1)[1] if src.startswith("mutation/") else "solution"


def load(path: str) -> list:
    return [json.loads(line) for line in open(path) if line.strip()]


def disagreement(rows: dict, labels: dict, results: Path) -> set:
    """Ids where visual label, tests, tolerant model or model+checks differ."""
    from plot_grader.tolerant import tolerant_check

    tol = {r["case"]: r.get("verdict")
           for r in load(results / "r4_tolerant" / "rows.jsonl")}
    out = set()
    for i, c in rows.items():
        pd = [json.loads(Path(p).with_suffix(".json").read_text())["plot_data"]
              for p in (c["png"], c["reference_png"])]
        comb = "FAIL" if tolerant_check(*pd) else tol.get(i)
        if len({labels[i]["visual"], c["label"], tol.get(i), comb}) > 1:
            out.add(i)
    return out


def select_eval(rows: dict, labels: dict, results: Path, n: int, min_kind: int,
                rng: random.Random) -> list:
    rows = {i: r for i, r in rows.items() if i in labels}
    chosen = set(disagreement(rows, labels, results))
    by_kind = defaultdict(list)
    for i in sorted(rows):
        by_kind[kind(rows[i])].append(i)
    for ids in by_kind.values():
        rest = [i for i in ids if i not in chosen]
        rng.shuffle(rest)
        need = max(0, min(min_kind, len(ids)) - sum(i in chosen for i in ids))
        chosen.update(rest[:need])
    # Fill up to n proportionally to what is left per kind.
    pool = [i for ids in by_kind.values() for i in ids if i not in chosen]
    rng.shuffle(pool)
    left = defaultdict(list)
    for i in pool:
        left[kind(rows[i])].append(i)
    while len(chosen) < n and any(left.values()):
        k = max(left, key=lambda k: len(left[k]))
        chosen.add(left[k].pop())
    out = sorted(chosen)
    rng.shuffle(out)
    return out


def pick_examples(rows: dict, taken: set) -> list:
    ids = [i for i in EXAMPLES if i in rows]
    clash = taken.intersection(ids)
    if clash:
        raise SystemExit(f"example ids among the judged cases: {clash}")
    return ids


def write_image(src: str, dst: Path):
    im = Image.open(src)
    im.load()
    im = im.convert("RGB")  # drops alpha, palette and every metadata chunk
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    im.save(dst, "PNG", optimize=True)  # no pnginfo -> no text chunks


def new_id(used: set) -> str:
    while True:
        cid = secrets.token_hex(4)
        if cid not in used:
            used.add(cid)
            return cid


def insert_repeats(order: list, k: int, gap: int, rng: random.Random) -> list:
    """Return (order with repeats, list of (repeat_index_in_order, original))."""
    cands = list(range(max(1, len(order) - gap)))
    firsts = sorted(rng.sample(cands, min(k, len(cands))))
    out = [(x, None) for x in order]
    for pos in reversed(firsts):
        lo = pos + gap
        at = rng.randint(min(lo, len(out)), len(out))
        out.insert(at, (order[pos], order[pos]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", action="append", default=None)
    ap.add_argument("--labels", default="data/eval_set/visual_labels.jsonl")
    ap.add_argument("--results", default="data/vlm_eval/r4")
    ap.add_argument("--out", default="data/judge_package")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--min-per-kind", type=int, default=3)
    ap.add_argument("--gap", type=int, default=30, help="min distance of a repeat")
    ap.add_argument("--seed", type=int, default=8012)
    a = ap.parse_args()
    manifests = a.manifest or [EVAL]
    out = Path(a.out)
    pub, priv = out / "public", out / "private"
    (pub / "img").mkdir(parents=True, exist_ok=True)
    priv.mkdir(parents=True, exist_ok=True)
    mpath = priv / "mapping.json"
    mapping = (json.loads(mpath.read_text()) if mpath.exists()
               else {"seed": a.seed, "manifests": [], "cases": [], "examples": []})
    rng = random.Random(mapping["seed"])
    used = {c["case_id"] for c in mapping["cases"] + mapping["examples"]}
    rows_of = {m: {r["id"]: r for r in load(m) if r.get("png") and r.get("reference_png")}
               for m in manifests}

    for m in manifests:
        if m in mapping["manifests"]:
            continue
        rows = rows_of[m]
        if m == EVAL:
            labels = {r["id"]: r for r in load(a.labels)}
            rows = {i: r for i, r in rows.items() if r.get("label")}
            rows_sel = {i: r for i, r in rows.items() if i not in EXAMPLES}
            order = select_eval(rows_sel, labels, Path(a.results), a.n,
                                a.min_per_kind, rng)
            for i in pick_examples(rows, set(order)):
                mapping["examples"].append({
                    "case_id": new_id(used), "manifest": m, "source_id": i,
                    "verdict": labels[i]["visual"],
                    "criterion": labels[i].get("criterion", "")})
        else:
            order = sorted(rows)
            rng.shuffle(order)
        first = {}
        for src, rep in insert_repeats(order, a.repeats if m == EVAL else 0,
                                       a.gap, rng):
            cid = new_id(used)
            mapping["cases"].append({"case_id": cid, "manifest": m, "source_id": src,
                                     "kind": kind(rows[src]),
                                     "repeat_of": first[rep] if rep else None})
            first.setdefault(src, cid)
        mapping["manifests"].append(m)

    all_rows = {m: {r["id"]: r for r in load(m)} for m in mapping["manifests"]}
    public = {"cases": [], "examples": []}
    keep = set()
    for key in ("cases", "examples"):
        for c in mapping[key]:
            row = all_rows[c["manifest"]][c["source_id"]]
            entry = {"id": c["case_id"]}
            for side, src in (("ref", row["reference_png"]), ("stu", row["png"])):
                name = f"{c['case_id']}{side[0]}.png"
                write_image(src, pub / "img" / name)
                entry[side] = f"img/{name}"
                keep.add(name)
            if key == "examples":
                entry["verdict"] = c["verdict"]
                entry["criterion"] = c["criterion"]
            public[key].append(entry)
    for f in (pub / "img").glob("*.png"):
        if f.name not in keep:
            f.unlink()
    (pub / "cases.json").write_text(json.dumps(public, indent=1))
    mpath.write_text(json.dumps(mapping, indent=1))
    n_rep = sum(c["repeat_of"] is not None for c in mapping["cases"])
    print(f"{len(public['cases'])} screens ({n_rep} repeats), "
          f"{len(public['examples'])} examples -> {pub}; mapping {mpath}")


if __name__ == "__main__":
    main()
