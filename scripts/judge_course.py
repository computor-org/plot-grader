#!/usr/bin/env python3
"""Judge the plots of a course and write a bilingual feedback page per submission.

Uses the round-4 verdict of plot_grader.tolerant_judge (pixel-identical, or
Flash-Next tolerant prompt PASS and tolerant data checks clean). Inputs, any
combination:

- --localtests correctSolution,gptSolution: the named localTests/* of every
  exercise in --examples with a `type: graphics` collection;
- --submissions DIR: DIR/<slug>/<name>/*.py, one submission per folder;
- --manifest data/eval_set/manifest.jsonl with --sources (prefixes) and
  --per-kind N: already rendered eval-set cases, e.g. round-4 mutants.

References are the exercises' own solutions, rendered with plot_grader.render.
Output (gitignored): OUT/index.html, OUT/results.jsonl, OUT/summary.md and
OUT/<slug>/<case>.html with the images next to it.
"""

import argparse
import html
import json
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from build_eval_set import graphics_entry, render_case  # noqa: E402

from plot_grader.tolerant_judge import default_judge, judge_plot  # noqa: E402

EXAMPLES = Path.home() / "code/codeability/examples/python"
PREFIX = "itpcp.pgph.py."

CRITERIA = {  # docs/criteria.md, (German, English)
    "M1": ("Gleiche Kurven: jede Kurve der Referenz ist da, keine zusätzliche "
           "Datenreihe.",
           "Same curves: every curve of the reference is present, no extra series."),
    "M2": ("Gleiche Daten: Form und Werte jeder Kurve stimmen mit der Referenz "
           "überein.",
           "Same data: each curve has the same shape and values as the reference."),
    "M3": ("Gleiche Achsen: gleicher Achsentyp (linear/log), der relevante "
           "Datenbereich ist sichtbar.",
           "Same axes: same axis type (linear/log), the relevant data range is shown."),
    "M4": ("Achsenbeschriftung: beschriftete Achsen der Referenz sind mit derselben "
           "Größe (und Einheit) beschriftet.",
           "Axis labels: axes labelled in the reference carry the same quantity "
           "(and unit)."),
    "M5": ("Kurven erkennbar: Kurven sind unterscheidbar und wie in der Referenz "
           "(Legende) zugeordnet.",
           "Curves identifiable: curves are distinguishable and identified as in the "
           "reference (legend)."),
    "M6": ("Gleiche Teilbilder: jedes Teilbild (subplot) der Referenz ist vorhanden.",
           "Same panels: every subplot of the reference exists."),
}
VERDICT = {"PASS": ("Bestanden", "Passed"), "FAIL": ("Nicht bestanden", "Failed"),
           "ERROR": ("Keine Bewertung (Modell nicht erreichbar)",
                     "Not graded (model unavailable)")}
PROBLEM_DE = [  # tolerant_check messages -> German
    (r"M6 (\d+) panels instead of (\d+)", r"M6: \1 Teilbilder statt \2"),
    (r"M4 axis (\d+) (x|y)label missing", r"M4: Achse \2 in Teilbild \1 ist unbeschriftet"),
    (r"M1/M2 axis (\d+) curve (\d+) not found in the student plot",
     r"M1/M2: Kurve \2 der Referenz (Teilbild \1) fehlt oder hat andere Werte"),
    (r"M3 axis (\d+) x range hides the data",
     r"M3: der x-Bereich in Teilbild \1 verdeckt einen Teil der Daten"),
]


def problem_de(text: str) -> str:
    for pat, rep in PROBLEM_DE:
        if re.fullmatch(pat, text):
            return re.sub(pat, rep, text)
    return text


def exercises(examples: Path) -> dict:
    """{slug: (exercise dir, graphics entry point)} for exercises with graphics tests."""
    found = {}
    for test_yaml in sorted(examples.glob(PREFIX + "*/test.yaml")):
        entry = graphics_entry(test_yaml)
        if entry:
            found[test_yaml.parent.name.removeprefix(PREFIX)] = (test_yaml.parent, entry)
    return found


def reference(ex: dict, slug: str, out: Path, cache: dict) -> dict | None:
    if slug not in cache:
        ex_dir, entry = ex[slug]
        r = render_case(ex_dir, [ex_dir / entry], entry, out / slug, "reference")
        shutil.rmtree(out / slug / "work", ignore_errors=True)
        cache[slug] = r.get("png")
        if not cache[slug]:
            print(f"{slug}: reference does not render: {r}")
    return cache[slug] and {"reference_png": cache[slug]}


def submission_jobs(ex: dict, subs: list, out: Path, cache: dict,
                    labels: dict) -> list:
    """Render (slug, source, folder) submissions next to the exercise's data files."""
    jobs = []
    for slug, source, folder in subs:
        ex_dir, entry = ex[slug]
        ref = reference(ex, slug, out, cache)
        job_id = f"{slug}__" + re.sub(r"\W+", "_", source)
        if not ref or not folder.is_dir():
            continue
        if not (folder / entry).exists():
            jobs.append({"id": job_id, "slug": slug, "source": source,
                         "render_error": f"entry point {entry} missing"})
            continue
        r = render_case(ex_dir, sorted(folder.glob("*.py")), entry, out / slug, job_id)
        shutil.rmtree(out / slug / "work", ignore_errors=True)
        job = {"id": job_id, "slug": slug, "source": source, **ref,
               **{k: v for k, v in labels.get((slug, source), {}).items()
                  if k in ("label", "visual", "visual_criterion")}}
        if "png" in r:
            jobs.append({**job, "png": r["png"]})
        else:
            jobs.append({**job, "render_error": r.get("render_error")})
    return jobs


def manifest_rows(path: Path, visual_path: Path) -> list:
    visual = {}
    if visual_path.exists():
        for line in open(visual_path):
            v = json.loads(line)
            visual[v["id"]] = v
    rows = []
    for line in open(path):
        row = json.loads(line)
        v = visual.get(row["id"], {})
        row.update(visual=v.get("visual"), visual_criterion=v.get("criterion"))
        rows.append(row)
    return rows


def manifest_jobs(rows: list, sources: list, per_kind: int) -> list:
    """Rendered cases whose source starts with one of `sources`, at most
    `per_kind` per source; each source starts at another exercise."""
    by_source = {}
    for r in sorted(rows, key=lambda r: r["id"]):
        if "png" in r and any(r["source"].startswith(s) for s in sources):
            by_source.setdefault(r["source"], []).append(r)
    jobs = []
    for k, (source, group) in enumerate(sorted(by_source.items())):
        shift = (5 * k) % len(group)
        for row in (group[shift:] + group[:shift])[:per_kind]:
            jobs.append({key: row.get(key) for key in (
                "id", "slug", "source", "png", "reference_png", "label", "visual",
                "visual_criterion")})
    return jobs


CSS = """:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#6b6b66;--line:#dddcd6;--card:#fff;
--pass:#1f7a3f;--fail:#b3261e;--err:#8a6d00}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#a3a29b;
--line:#34332f;--card:#1f1f1d;--pass:#6fcf8f;--fail:#f28b82;--err:#e6c35c}}
body{background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif;
margin:0 auto;max-width:1100px;padding:16px}
h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:1.5rem}.muted{color:var(--muted)}
.v{font-weight:700;font-size:1.2rem}.PASS{color:var(--pass)}.FAIL{color:var(--fail)}
.ERROR{color:var(--err)}.imgs{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:700px){.imgs{grid-template-columns:1fr}}
figure{margin:0;background:var(--card);border:1px solid var(--line);padding:8px}
img{max-width:100%;height:auto;display:block;background:#fff}
.lang{display:grid;grid-template-columns:1fr 1fr;gap:24px}
@media (max-width:700px){.lang{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);
padding:4px 8px;text-align:left;vertical-align:top}"""


def e(text) -> str:
    return html.escape(str(text))


def feedback(v: dict, lang: int) -> str:
    """Feedback block in German (lang=0) or English (lang=1)."""
    t = [("Ergebnis", "Result"), ("Verletzte Kriterien", "Violated criteria"),
         ("Befund der Datenprüfung", "Data check findings"),
         ("Unterschiede laut Modell (englisch)", "Differences seen by the model"),
         ("Hinweis des Modells (englisch)", "Hint from the model"),
         ("Pixelgleich mit der Referenz.", "Pixel-identical to the reference."),
         ("Der Plot zeigt denselben Inhalt wie die Referenz. Farben, Linienstile, "
          "Legendenposition und Formulierungen dürfen abweichen.",
          "The plot shows the same content as the reference. Colours, line styles, "
          "legend position and wording may differ.")]
    L = [x[lang] for x in t]
    out = [f"<p>{L[0]}: <span class='v {v['verdict']}'>"
           f"{e(VERDICT[v['verdict']][lang])}</span></p>"]
    if v["verdict"] == "PASS":
        out.append(f"<p>{L[5] if v['pixel_identical'] else L[6]}</p>")
    if v["criteria"]:
        out.append(f"<h3>{L[1]}</h3><ul>" + "".join(
            f"<li><b>{c}</b> {e(CRITERIA[c][lang])}</li>" for c in v["criteria"]
            if c in CRITERIA) + "</ul>")
    if v["problems"]:
        out.append(f"<h3>{L[2]}</h3><ul>" + "".join(
            f"<li>{e(problem_de(p) if lang == 0 else p)}</li>" for p in v["problems"])
            + "</ul>")
    if v["differences"]:
        out.append(f"<h3>{L[3]}</h3><ul>" + "".join(
            f"<li>{e(d)}</li>" for d in v["differences"]) + "</ul>")
    if v["hint"]:
        out.append(f"<h3>{L[4]}</h3><p>{e(v['hint'])}</p>")
    return "\n".join(out)


def write_page(job: dict, v: dict, out: Path) -> str:
    d = out / job["slug"]
    d.mkdir(parents=True, exist_ok=True)

    def place(src: str, name: str) -> str:
        """Copy an image next to the page unless it already lives there."""
        if Path(src).resolve().parent != d.resolve():
            shutil.copy(src, d / name)
            return name
        return Path(src).name

    ref_img = place(job["reference_png"], f"{job['id']}.reference.png")
    stu_img = place(job["png"], f"{job['id']}.png")
    body = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(job['slug'])} Plot-Feedback</title><style>{CSS}</style></head><body>
<p class="muted"><a href="../index.html">Übersicht / overview</a></p>
<h1>Plot-Feedback: {e(job['slug'])}</h1>
<p class="muted">{e(job['source'])} · {e(job['id'])}</p>
<div class="imgs"><figure><img src="{e(ref_img)}" alt="Referenz / reference">
<figcaption>Referenz / reference</figcaption></figure>
<figure><img src="{e(stu_img)}" alt="Abgabe / submission">
<figcaption>Abgabe / submission</figcaption></figure></div>
<div class="lang"><section><h2>Deutsch</h2>{feedback(v, 0)}</section>
<section><h2>English</h2>{feedback(v, 1)}</section></div>
<p class="muted">Kriterien / criteria: docs/criteria.md (plot-grader). Urteil /
verdict: pixelgleich, oder Flash-Next (tolerant) und Datenprüfung bestanden.</p>
</body></html>"""
    page = d / f"{job['id']}.html"
    page.write_text(body)
    return str(page.relative_to(out))


def write_index(results: list, out: Path) -> str:
    rows = []
    for r in sorted(results, key=lambda r: (r["slug"], r["source"])):
        v = r.get("verdict") or "ERROR"
        link = (f"<a href='{e(r['page'])}'>{e(r['source'])}</a>" if r.get("page")
                else e(r["source"]) + f" ({e(r.get('render_error', ''))[:60]})")
        rows.append(f"<tr><td>{e(r['slug'])}</td><td>{link}</td>"
                    f"<td class='{v}'>{v}</td><td>{e(', '.join(r.get('criteria', [])))}"
                    f"</td><td>{e(r.get('label') or '')}</td>"
                    f"<td>{e(r.get('visual') or '')}</td></tr>")
    (out / "index.html").write_text(
        f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plot-Feedback Demo</title><style>{CSS}</style></head><body>
<h1>Plot-Feedback: Data Science with Python</h1>
<p class="muted">Urteil / verdict: plot_grader.tolerant_judge. Offizielle Tests /
official tests: graphics collections of test.yaml (pytester). Sichtprüfung / visual:
round-4 label by eye (docs/criteria.md).</p>
<table><tr><th>Aufgabe / exercise</th><th>Abgabe / submission</th>
<th>Urteil / verdict</th><th>Kriterien</th><th>offizielle Tests</th>
<th>Sichtprüfung</th></tr>
{''.join(rows)}</table></body></html>""")
    return str(out / "index.html")


def summarize(results: list, seconds: float) -> str:
    def group(r):
        return "mutation" if r["source"].startswith("mutation/") else "solution"
    lines = ["# Plot-judge demo", "", f"{len(results)} submissions, "
             f"{seconds / 60:.1f} min wall time.", "",
             "| group | n | PASS | FAIL | ERROR | render error | pixel-identical | "
             "agrees with visual label | agrees with official tests |",
             "|---|---|---|---|---|---|---|---|---|"]
    for g in ("solution", "mutation"):
        rs = [r for r in results if group(r) == g]
        if not rs:
            continue
        n = {k: sum(r.get("verdict") == k for r in rs) for k in ("PASS", "FAIL", "ERROR")}
        vis = [r for r in rs if r.get("visual") and r.get("verdict") in ("PASS", "FAIL")]
        off = [r for r in rs if r.get("label") and r.get("verdict") in ("PASS", "FAIL")]
        lines.append(
            f"| {g} | {len(rs)} | {n['PASS']} | {n['FAIL']} | {n['ERROR']} | "
            f"{sum('render_error' in r for r in rs)} | "
            f"{sum(bool(r.get('pixel_identical')) for r in rs)} | "
            f"{sum(r['verdict'] == r['visual'] for r in vis)}/{len(vis)} | "
            f"{sum(r['verdict'] == r['label'] for r in off)}/{len(off)} |")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description="Judge a course's plots, write feedback pages")
    p.add_argument("--examples", default=str(EXAMPLES))
    p.add_argument("--localtests", default="",
                   help="comma list of localTests/* folders to judge, e.g. "
                        "correctSolution,gptSolution")
    p.add_argument("--submissions", help="DIR/<slug>/<name>/*.py")
    p.add_argument("--manifest", default=str(REPO / "data/eval_set/manifest.jsonl"))
    p.add_argument("--sources", default="", help="comma list of manifest source "
                   "prefixes to judge, e.g. mutation/")
    p.add_argument("--per-kind", type=int, default=1)
    p.add_argument("--slugs", help="comma list to restrict")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--out", default=str(REPO / "data/demo"))
    args = p.parse_args()

    import time
    start = time.time()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ex = exercises(Path(args.examples))
    if args.slugs:
        ex = {s: v for s, v in ex.items() if s in args.slugs.split(",")}
    manifest = Path(args.manifest)
    rows = manifest_rows(manifest, manifest.parent / "visual_labels.jsonl") \
        if manifest.exists() else []
    labels = {(r["slug"], r["source"]): r for r in rows}
    subs = [(slug, f"examples/{name}", ex_dir / "localTests" / name)
            for slug, (ex_dir, _) in ex.items()
            for name in filter(None, args.localtests.split(","))]
    if args.submissions:
        for folder in sorted(Path(args.submissions).glob("*/*/")):
            if folder.parent.name in ex:
                subs.append((folder.parent.name, f"submissions/{folder.name}", folder))
    cache = {}
    jobs = submission_jobs(ex, subs, out, cache, labels)
    if args.sources:
        jobs += [j for j in manifest_jobs(rows, args.sources.split(","), args.per_kind)
                 if j["slug"] in ex]
    print(f"{len(jobs)} submissions, judging with {args.workers} workers")

    judge = default_judge()
    lock = threading.Lock()
    results_file = open(out / "results.jsonl", "w")

    def run(job):
        if "png" not in job:
            res = {**job}
        else:
            s_json = Path(job["png"]).with_suffix(".json")
            r_json = Path(job["reference_png"]).with_suffix(".json")
            v = judge_plot(Path(job["png"]).read_bytes(),
                           Path(job["reference_png"]).read_bytes(),
                           json.loads(s_json.read_text()), json.loads(r_json.read_text()),
                           judge=judge).to_dict()
            res = {**job, **v, "page": write_page(job, v, out)}
        with lock:
            results_file.write(json.dumps(res, ensure_ascii=False) + "\n")
            results_file.flush()
            print(f"{res['id']}: {res.get('verdict', 'render error')} "
                  f"{','.join(res.get('criteria', []))}", flush=True)
        return res

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(run, jobs))
    results_file.close()
    write_index(results, out)
    summary = summarize(results, time.time() - start)
    (out / "summary.md").write_text(summary)
    print(summary)
    print(f"index: {out / 'index.html'}")


if __name__ == "__main__":
    main()
