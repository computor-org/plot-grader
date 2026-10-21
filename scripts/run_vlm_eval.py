#!/usr/bin/env python3
"""Compare vision judges on the synthetic plot_docstr variants (round 2).

For every model in the endpoint config, every mode (chat completions, JEV) and
every view (student image only as in round 1, or reference + student), judge
the 15 stress-test variants and record verdict, probabilities, latency and
tokens. Tier 1 runs on the same cases for comparison.

Outputs in data/vlm_eval/<timestamp>/ (gitignored): rows.jsonl, summary.json,
summary.md, images/.
"""

import argparse
import json
import io
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from plot_grader.executor import execute_plot_code, extract_plot_data, render_figure_to_bytes  # noqa: E402
from plot_grader.judges import DEFAULT_ENDPOINTS, load_endpoints, make_judge  # noqa: E402
from plot_grader.stress_tests import PlotDocstrStressTests  # noqa: E402
from plot_grader.tier1 import Tier1Grader  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = Path.home() / "code/codeability/examples/python"


def scale_png(png: bytes, scale: float) -> bytes:
    if scale == 1.0:
        return png
    from PIL import Image
    im = Image.open(io.BytesIO(png))
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def task_text(slug: str, limit: int = 6000) -> str | None:
    """Assignment text shown to students (English if available)."""
    for name in ("index_en.md", "index_de.md", "index.md"):
        f = EXAMPLES / f"itpcp.pgph.py.{slug}" / "content" / name
        if f.exists():
            return f.read_text()[:limit]
    return None


def find_reference(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    root = REPO.parent / "assignments"
    matches = sorted(root.rglob("_reference/plot_docstr.py")) if root.exists() else []
    if not matches:
        sys.exit("Reference not found; pass --reference path/to/plot_docstr_master.py")
    return matches[0]


def build_cases(out: Path, ref_data: dict) -> list:
    """Generate variants, render them, and grade them with Tier 1."""
    vdir = out / "variants"
    groups = {
        "positive": PlotDocstrStressTests.generate_positive_variants(vdir / "positive"),
        "negative": PlotDocstrStressTests.generate_negative_variants(vdir / "negative"),
        "ambiguous": PlotDocstrStressTests.generate_ambiguous_variants(vdir / "ambiguous"),
    }
    tier1 = Tier1Grader()
    cases = []
    for group, paths in groups.items():
        for path in paths:
            res = execute_plot_code(path)
            if not res["success"]:
                print(f"skip {path.name}: {res.get('error')}")
                continue
            png = render_figure_to_bytes(res["figure"])
            (out / "images" / f"{path.stem}.png").write_bytes(png)
            t1 = tier1.grade(extract_plot_data(res["figure"]), ref_data)
            cases.append({
                "case": path.stem,
                "group": group,
                "label": {"positive": "PASS", "negative": "FAIL"}.get(group),
                "tier1": "PASS" if t1.passed else "FAIL",
                "png": png,
            })
    return cases


def load_manifest(path: Path) -> list:
    """Cases from scripts/build_eval_set.py: labelled by the official graphics tests."""
    tier1 = Tier1Grader()
    ref_cache = {}
    cases = []
    for line in open(path):
        row = json.loads(line)
        if row.get("label") is None or "png" not in row:
            continue
        ref_png_path = Path(row["reference_png"])
        if ref_png_path not in ref_cache:
            ref_json = ref_png_path.with_suffix(".json")
            ref_cache[ref_png_path] = (ref_png_path.read_bytes(),
                                       json.loads(ref_json.read_text())["plot_data"])
        ref_png, ref_data = ref_cache[ref_png_path]
        try:
            student_data = json.loads(Path(row["png"]).with_suffix(".json").read_text())["plot_data"]
            t1 = "PASS" if tier1.grade(student_data, ref_data).passed else "FAIL"
        except Exception:  # Tier 1 on JSON-roundtripped data is best effort
            t1 = None
        cases.append({
            "case": row["id"],
            "group": row["source"].split("/")[0],
            "source": row["source"],
            "label": row["label"],
            "tier1": t1,
            "png": Path(row["png"]).read_bytes(),
            "ref_png": ref_png,
            "task": task_text(row["slug"]),
        })
    return cases


def pct(values: list, q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def summarize(rows: list) -> list:
    cells = {}
    for r in rows:
        cells.setdefault((r["model"], r["mode"], r["view"]), []).append(r)
    summary = []
    for (model, mode, view), rs in cells.items():
        labelled = [r for r in rs if r["label"]]
        usable = [r for r in labelled if r["verdict"]]
        correct = sum(r["verdict"] == r["label"] for r in usable)
        false_pass = sum(r["label"] == "FAIL" and r["verdict"] == "PASS" for r in usable)
        false_fail = sum(r["label"] == "PASS" and r["verdict"] == "FAIL" for r in usable)
        probs = [(r["p_pass"], r["label"] == "PASS") for r in labelled if r["p_pass"] is not None]
        lat = [r["latency_s"] for r in rs if not r["error"]]
        tokens_in = [r["usage"].get("prompt_tokens") or r["usage"].get("input_tokens")
                     for r in rs if r["usage"]]
        tokens_out = [r["usage"].get("completion_tokens") or r["usage"].get("output_tokens")
                      for r in rs if r["usage"]]
        summary.append({
            "model": model, "mode": mode, "view": view,
            "calls": len(rs),
            "labelled": len(labelled),
            "accuracy": correct / len(labelled) if labelled else None,
            "false_pass": false_pass,
            "false_fail": false_fail,
            "unusable": len(labelled) - len(usable),
            "brier": (statistics.fmean((p - y) ** 2 for p, y in probs) if probs else None),
            "ambiguous": {r["case"]: r["verdict"] for r in rs
                          if r["group"] == "ambiguous" and r["rep"] == 0},
            "by_group": {g: {"n": len(gr), "accuracy": sum(r["verdict"] == r["label"] for r in gr) / len(gr)}
                         for g in sorted({r["group"] for r in labelled})
                         for gr in [[r for r in labelled if r["group"] == g]]},
            "mutations_flagged": (lambda ms: sum(r["verdict"] == "FAIL" for r in ms) / len(ms) if ms else None)(
                [r for r in rs if r["group"] == "mutation"]),
            "latency_p50_s": pct(lat, 0.5),
            "latency_p95_s": pct(lat, 0.95),
            "tokens_in_mean": statistics.fmean(t for t in tokens_in if t) if any(tokens_in) else None,
            "tokens_out_mean": statistics.fmean(t for t in tokens_out if t) if any(tokens_out) else None,
        })
    return summary


def fmt(v, spec=".2f"):
    return "-" if v is None else format(v, spec)


def write_markdown(summary: list, tier1_line: str, path: Path) -> str:
    lines = [tier1_line, "",
             "| model | mode | view | acc | false pass | false fail | unusable | Brier "
             "| p50 s | p95 s | tok in | tok out | workers | calls/min |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        lines.append(
            f"| {s['model']} | {s['mode']} | {s['view']} | {fmt(s['accuracy'])} "
            f"| {s['false_pass']} | {s['false_fail']} | {s['unusable']} | {fmt(s['brier'], '.3f')} "
            f"| {fmt(s['latency_p50_s'])} | {fmt(s['latency_p95_s'])} "
            f"| {fmt(s['tokens_in_mean'], '.0f')} | {fmt(s['tokens_out_mean'], '.0f')} "
            f"| {s.get('workers', '-')} | {fmt(s.get('throughput_per_min'), '.1f')} |")
    if any(s["by_group"] for s in summary):
        groups = sorted({g for s in summary for g in s["by_group"]})
        lines += ["", "Accuracy by source (vs official graphics tests), and share of "
                  "mutants judged FAIL:", "",
                  "| model | mode | view | " + " | ".join(groups) + " | mutants flagged |",
                  "|---|---|---|" + "---|" * (len(groups) + 1)]
        for s in summary:
            cells = [fmt(s["by_group"].get(g, {}).get("accuracy")) for g in groups]
            lines.append(f"| {s['model']} | {s['mode']} | {s['view']} | " + " | ".join(cells)
                         + f" | {fmt(s['mutations_flagged'])} |")
    lines += ["", "Ambiguous variants (first repeat):", ""]
    for s in summary:
        amb = ", ".join(f"{k.split('_', 2)[-1]}={v or 'none'}" for k, v in s["ambiguous"].items())
        lines.append(f"- {s['model']}/{s['mode']}/{s['view']}: {amb}")
    text = "\n".join(lines) + "\n"
    path.write_text(text)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", help="reference solution (plot_docstr master)")
    parser.add_argument("--endpoints", default=str(DEFAULT_ENDPOINTS))
    parser.add_argument("--models", help="comma list (default: all in config)")
    parser.add_argument("--modes", default="chat,jev")
    parser.add_argument("--views", default="student,pair")
    parser.add_argument("--repeat", type=int, default=1,
                        help="passes over all cases; later passes measure warm latency and stability")
    parser.add_argument("--manifest", help="data/eval_set/manifest.jsonl from build_eval_set.py "
                        "instead of the 15 synthetic variants")
    parser.add_argument("--cases", type=int, help="limit number of cases (smoke test)")
    parser.add_argument("--workers", type=int, default=8,
                        help="parallel requests per cell (default 8)")
    parser.add_argument("--scale", type=float, default=1.0, help="resize images before sending")
    parser.add_argument("--jev-overall-only", action="store_true",
                        help="JEV asks only the overall question")
    parser.add_argument("--thinking", action="store_true", help="enable reasoning for chat mode")
    parser.add_argument("--resume", action="store_true",
                        help="append to an existing rows.jsonl and skip finished jobs")
    parser.add_argument("--out", help="output directory (default: data/vlm_eval/<timestamp>)")
    args = parser.parse_args()

    endpoints = load_endpoints(Path(args.endpoints))
    models = args.models.split(",") if args.models else list(endpoints)
    out = Path(args.out) if args.out else REPO / "data" / "vlm_eval" / time.strftime("%Y%m%d-%H%M%S")
    (out / "images").mkdir(parents=True, exist_ok=True)

    if args.manifest:
        ref_path = Path(args.manifest)
        cases = load_manifest(ref_path)
    else:
        ref_path = find_reference(args.reference)
        ref_exec = execute_plot_code(ref_path)
        if not ref_exec["success"]:
            sys.exit(f"Reference failed to run: {ref_exec.get('error')}")
        ref_png = render_figure_to_bytes(ref_exec["figure"])
        (out / "images" / "reference.png").write_bytes(ref_png)
        cases = build_cases(out, extract_plot_data(ref_exec["figure"]))
        for c in cases:
            c["ref_png"] = ref_png
            c["task"] = task_text("plot_docstr")
    if args.cases:
        cases = cases[:args.cases]

    t1_correct = sum(c["tier1"] == c["label"] for c in cases if c["label"])
    t1_labelled = sum(1 for c in cases if c["label"])
    tier1_line = (f"Tier 1: {t1_correct}/{t1_labelled} labelled correct; ambiguous: "
                  + ", ".join(f"{c['case'].split('_', 2)[-1]}={c['tier1']}"
                              for c in cases if c["group"] == "ambiguous"))
    print(f"Reference: {ref_path}\n{len(cases)} cases. {tier1_line}")

    rows = []
    wall = {}
    lock = threading.Lock()
    rows_path = out / "rows.jsonl"
    if args.resume and rows_path.exists():
        for line in rows_path.read_text().splitlines():
            row = json.loads(line)
            if not row["error"]:
                rows.append(row)
    finished = {(r["model"], r["mode"], r["view"], r["rep"], r["case"]) for r in rows}
    with open(rows_path, "w" if not args.resume else "a") as fh:
        for model in models:
            for mode in args.modes.split(","):
                if mode not in endpoints[model]:
                    print(f"{model}: no {mode} endpoint, skipped")
                    continue
                judge = make_judge(endpoints, model, mode)
                if mode == "chat" and args.thinking:
                    judge.thinking = True
                    judge.max_tokens = max(judge.max_tokens, 4096)
                if mode == "jev" and args.jev_overall_only:
                    judge.overall_only = True
                for view in args.views.split(","):
                    if mode == "jev" and view.startswith("task"):
                        print(f"{model}: JEV has no {view} view, skipped")
                        continue

                    def run_one(job, judge=judge, model=model, mode=mode, view=view):
                        rep, c = job
                        res = judge.judge(scale_png(c["png"], args.scale),
                                          scale_png(c["ref_png"], args.scale),
                                          view=view, task=c.get("task"))
                        row = {
                            "model": model, "mode": mode, "view": view, "rep": rep,
                            "endpoint_model": judge.model, "case": c["case"],
                            "group": c["group"], "source": c.get("source", c["group"]),
                            "label": c["label"], "tier1": c["tier1"],
                            "workers": args.workers, "scale": args.scale,
                            "thinking": bool(getattr(judge, "thinking", False)),
                            "verdict": res.verdict, "p_pass": res.p_pass,
                            "criteria": res.criteria, "differences": res.differences,
                            "hint": res.hint, "latency_s": round(res.latency_s, 3),
                            "usage": res.usage, "error": res.error, "raw": res.raw[:2000],
                        }
                        with lock:
                            rows.append(row)
                            fh.write(json.dumps(row) + "\n")
                            fh.flush()
                        status = res.verdict or f"ERR {(res.error or '')[:60]}"
                        print(f"{model:10} {mode:4} {view:9} r{rep} {c['case'][:40]:40} "
                              f"{status:8} {res.latency_s:6.2f}s", flush=True)

                    jobs = [(rep, c) for rep in range(args.repeat) for c in cases
                            if (model, mode, view, rep, c["case"]) not in finished]
                    start = time.perf_counter()
                    with ThreadPoolExecutor(max_workers=args.workers) as pool:
                        list(pool.map(run_one, jobs))
                    wall[(model, mode, view)] = (time.perf_counter() - start, len(jobs))

    summary = summarize(rows)
    for cell in summary:
        # timed over the calls of this invocation only (a resume skips earlier ones)
        w, n = wall.get((cell["model"], cell["mode"], cell["view"]), (None, 0))
        cell["workers"] = args.workers
        cell["timed_calls"] = n
        cell["wall_s"] = round(w, 1) if w else None
        cell["throughput_per_min"] = round(60 * n / w, 1) if w and n else None
    (out / "summary.json").write_text(json.dumps(
        {"reference": str(ref_path), "tier1": tier1_line, "cells": summary}, indent=2))
    print("\n" + write_markdown(summary, tier1_line, out / "summary.md"))
    print(f"Results in {out}")


if __name__ == "__main__":
    main()
