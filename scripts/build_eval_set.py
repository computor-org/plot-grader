#!/usr/bin/env python3
"""Build the labelled plot evaluation set from the Computor exercise pool.

For every exercise in codeability/examples/python with a `graphics` test
collection, collect candidate solutions and label each with the official
harness (`run_local_harness.py`, pytester):

- localTests/* of the exercise (correct, GPT, student, ...),
- matching localTests/* in the older assignments_2025 tree,
- blind LLM solutions (scripts/blind_solutions/U*/<slug>/),
- mutations of the reference (colour, line style, marker, dropped curve,
  scaled data, dropped labels).

Label = PASS if every graphics test collection passes, FAIL otherwise. Other
test types (docstrings, variables) are ignored because the vision judge only
sees the plot. Duplicates (same file contents) are dropped.

Output (gitignored): data/eval_set/manifest.jsonl and data/eval_set/cases/.
Student and solution code stays in data/, never in git.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
COLOR_SWAP = {"r": "g", "g": "m", "b": "r", "k": "c", "y": "b", "m": "k", "c": "r"}
PLOT_CALL = re.compile(r"^(\s*)((?:plt|ax\w*)\.(?:plot|semilogy|semilogx|loglog|errorbar|scatter)\()(.*)\)\s*$")
FMT = re.compile(r"""(["'])([rgbkymcw]?)(-{1,2}|:|-\.)?([o.xs^v*+dD]?)\1""")
LABEL_LINE = re.compile(r"^\s*(plt|ax\w*)\.(xlabel|ylabel|title|legend|set_xlabel|set_ylabel|set_title)\(")


def graphics_entry(test_yaml: Path) -> str | None:
    """Entry point of the first graphics collection, or None."""
    text = test_yaml.read_text()
    block = text.split("type: graphics", 1)
    if len(block) < 2:
        return None
    m = re.search(r"entryPoint:\s*(\S+)", block[1])
    return m.group(1) if m else None


def mutate(source: str) -> dict:
    """Generic mutations of a reference script; each returns changed source or is absent."""
    lines = source.splitlines()
    calls = [i for i, line in enumerate(lines) if PLOT_CALL.match(line)]
    out = {}

    def with_line(i, new):
        copy = list(lines)
        copy[i] = new
        return "\n".join(copy) + "\n"

    for i in calls:  # colour, line style, marker on the first call with a format string
        m = FMT.search(lines[i])
        if not m:
            continue
        q, color, style, marker = m.groups()
        if color and "color" not in out:
            out["color"] = with_line(i, lines[i][:m.start()] + f"{q}{COLOR_SWAP.get(color, 'r')}{style or ''}{marker}{q}" + lines[i][m.end():])
        if "linestyle" not in out and (style or not marker):
            new_style = {"-": "--", "--": ":", ":": "-", "-.": "-"}.get(style or "-", "--")
            out["linestyle"] = with_line(i, lines[i][:m.start()] + f"{q}{color}{new_style}{marker}{q}" + lines[i][m.end():])
        if marker and "marker" not in out:
            out["marker"] = with_line(i, lines[i][:m.start()] + f"{q}{color}{style or ''}{'s' if marker != 's' else 'o'}{q}" + lines[i][m.end():])
    if "color" not in out:  # color="name" keyword
        for i in calls:
            m = re.search(r"color\s*=\s*([\"'])(\w+)\1", lines[i])
            if m:
                new = "purple" if m.group(2) != "purple" else "orange"
                out["color"] = with_line(i, lines[i][:m.start(2)] + new + lines[i][m.end(2):])
                break
    if len(calls) >= 2:
        i = calls[-1]
        out["drop_curve"] = with_line(i, re.sub(r"^(\s*)", r"\1pass  # ", lines[i], count=1))
    if calls:  # scale the second positional argument of the first single-line call
        i = calls[0]
        m = PLOT_CALL.match(lines[i])
        args, depth, cur = [], 0, ""
        for ch in m.group(3):
            if ch == "," and depth == 0:
                args.append(cur)
                cur = ""
                continue
            depth += ch in "([{"
            depth -= ch in ")]}"
            cur += ch
        args.append(cur)
        if len(args) >= 2 and "=" not in args[1] and not FMT.fullmatch(args[1].strip()):
            args[1] = f" 1.25 * ({args[1].strip()})"
            out["scale_data"] = with_line(i, m.group(1) + m.group(2) + ",".join(args) + ")")
    label_idx = [i for i, line in enumerate(lines) if LABEL_LINE.match(line) and line.rstrip().endswith(")")]
    if label_idx:
        copy = list(lines)
        for i in label_idx:
            copy[i] = re.sub(r"^(\s*)", r"\1pass  # ", copy[i], count=1)
        out["drop_labels"] = "\n".join(copy) + "\n"
    out.update(mutate_round4(lines, calls))
    return out


# Round 4 (docs/criteria.md): changes a teacher would accept (T1-T5) and
# changes that alter the content (M1-M6). Intended class per mutation kind;
# the visual labels are checked by eye afterwards.
MUTATION_CLASS = {
    "color": "tolerated", "linestyle": "tolerated", "marker": "tolerated",
    "drop_curve": "content", "scale_data": "content", "drop_labels": "content",
    "reorder": "tolerated", "color_shade": "tolerated", "linewidth": "tolerated",
    "sampling": "tolerated", "title_case": "tolerated", "figsize": "tolerated",
    "grid": "tolerated", "legend_loc": "tolerated",
    "log_y": "content", "half_x": "content",
}
TAB = {"r": "tab:red", "g": "tab:green", "b": "tab:blue", "k": "dimgray",
       "y": "tab:olive", "m": "tab:purple", "c": "tab:cyan"}
LINSPACE = re.compile(r"(np\.linspace\([^,()]+,[^,()]+,\s*)(\d+)(\s*\))")
TITLE_CALL = re.compile(r"""((?:plt\.title|\.set_title)\(\s*f?)(["'])(.*?)\2""")
APPEND = {
    "figsize": "_f.set_size_inches(9, 4)",
    "grid": "[_a.grid(True) for _a in _f.axes]",
    "legend_loc": "[_a.legend(loc='lower left') for _a in _f.axes if _a.get_legend()]",
    "log_y": "[_a.set_yscale('log') for _a in _f.axes]",
    "half_x": "[_a.set_xlim(_a.get_xlim()[0], sum(_a.get_xlim()) / 2) for _a in _f.axes]",
}


def mutate_round4(lines: list, calls: list) -> dict:
    out = {}

    def text(copy):
        return "\n".join(copy) + "\n"

    if len(calls) >= 2 and calls[1] == calls[0] + 1:  # swap two adjacent plot calls
        copy = list(lines)
        copy[calls[0]], copy[calls[1]] = copy[calls[1]], copy[calls[0]]
        out["reorder"] = text(copy)
    for i in calls:  # 'r-' -> '-', color='tab:red'
        m = FMT.search(lines[i])
        if m and m.group(2) and "color" not in lines[i]:
            q, color, style, marker = m.groups()
            new = lines[i][:m.start()] + f"{q}{style or ''}{marker}{q}" + lines[i][m.end():]
            out["color_shade"] = text(lines[:i] + [new[:new.rstrip().rfind(")")]
                                      + f", color='{TAB[color]}')"] + lines[i + 1:])
            break
    for i in calls:
        if not re.search(r"\b(lw|linewidth)\s*=", lines[i]) and "scatter" not in lines[i]:
            end = lines[i].rstrip().rfind(")")
            out["linewidth"] = text(lines[:i] + [lines[i][:end] + ", linewidth=3)"] + lines[i + 1:])
            break
    for i, line in enumerate(lines):
        m = LINSPACE.search(line)
        if m and int(m.group(2)) >= 200:
            new = line[:m.start(2)] + str(int(m.group(2)) // 2) + line[m.end(2):]
            out["sampling"] = text(lines[:i] + [new] + lines[i + 1:])
            break
    for i, line in enumerate(lines):
        m = TITLE_CALL.search(line)
        if m and m.group(3) and m.group(3) != m.group(3).upper():
            new = line[:m.end()] + ".upper()" + line[m.end():]
            out["title_case"] = text(lines[:i] + [new] + lines[i + 1:])
            break
    if calls:  # applied after the script has run, to every figure
        for kind, stmt in APPEND.items():
            out[kind] = text(lines + ["", "import matplotlib.pyplot as _plt",
                                      "for _n in _plt.get_fignums():",
                                      "    _f = _plt.figure(_n)", f"    {stmt}"])
    return out


def collect(slug: str, ex_dir: Path, entry: str, assignments: Path, blind: Path) -> list:
    """Candidate solution dirs as (source, [py files])."""
    found = []
    for d in sorted((ex_dir / "localTests").glob("*/")):
        found.append((f"examples/{d.name}", sorted(d.glob("*.py"))))
    if assignments.exists():
        for d in sorted(assignments.glob(f"*/*/localTests/*/{entry}")):
            if d.parent.name != "_reference":
                found.append((f"assignments_2025/{d.parent.name}", sorted(d.parent.glob("*.py"))))
    for d in sorted(blind.glob(f"U*/{slug}/")):
        found.append((f"blind/{d.parent.name}", sorted(d.glob("*.py"))))
    return [(s, files) for s, files in found if any(f.name == entry for f in files)]


def harness_label(harness_dir: Path, slug: str, files: list, workdir: Path,
                  repo: Path | None = None) -> dict:
    """repo: examples checkout to test against (default: the harness default)."""
    cmd = [str(harness_dir / ".venv-harness" / "bin" / "python"),
           str(harness_dir / "run_local_harness.py"), slug, *map(str, files),
           "--workdir", str(workdir), "--keep", *(["--repo", str(repo)] if repo else [])]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"label": None, "harness_error": "timeout"}
    summary = workdir / "output" / "testSummary.json"
    if not summary.exists():
        return {"label": None, "harness_error": "no testSummary.json"}
    tests = json.loads(summary.read_text()).get("tests", [])
    graphics = [t for t in tests if t.get("type") == "graphics"]
    if not graphics:
        return {"label": None, "harness_error": "no graphics results"}
    failed = [s.get("name") for t in graphics for s in t.get("tests", [])
              if s.get("result") != "PASSED"]
    return {"label": "FAIL" if failed else "PASS",
            "graphics_failed": failed[:10],
            "graphics_total": sum(len(t.get("tests", [])) for t in graphics),
            "overall": json.loads(summary.read_text()).get("result")}


def render_case(ex_dir: Path, files: list, entry: str, case_dir: Path, name: str) -> dict:
    """Copy data files and helpers, then render in a subprocess."""
    work = case_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    for f in ex_dir.iterdir():
        if f.is_file() and f.name not in ("meta.yaml", "test.yaml"):
            shutil.copy(f, work / f.name)
    for f in files:
        shutil.copy(f, work / f.name)
    png, js = case_dir / f"{name}.png", case_dir / f"{name}.json"
    try:
        proc = subprocess.run([sys.executable, "-m", "plot_grader.render", str(work), entry,
                               str(png), str(js)], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"render_error": "timeout"}
    if proc.returncode != 0 or not png.exists():
        return {"render_error": (proc.stderr.strip().splitlines() or ["?"])[-1][:200]}
    return {"png": str(png), "n_figures": json.loads(js.read_text())["n_figures"]}


def main():
    p = argparse.ArgumentParser(description="Build the labelled plot evaluation set")
    p.add_argument("--examples", default=str(HOME / "code/codeability/examples/python"))
    p.add_argument("--assignments", default=os.environ.get("PLOT_GRADER_ASSIGNMENTS", str(REPO / "assignments")),
                   help="assignment repository (env PLOT_GRADER_ASSIGNMENTS)")
    p.add_argument("--blind", default=os.environ.get("PLOT_GRADER_BLIND", str(REPO / "data/blind_solutions")),
                   help="blind LLM solutions (env PLOT_GRADER_BLIND)")
    p.add_argument("--harness", default=os.environ.get("PLOT_GRADER_HARNESS", str(REPO / "data/harness")),
                   help="course test harness scripts (env PLOT_GRADER_HARNESS)")
    p.add_argument("--out", default=str(REPO / "data/eval_set"))
    p.add_argument("--slugs", help="comma list to restrict")
    args = p.parse_args()

    out = Path(args.out).resolve()
    (out / "cases").mkdir(parents=True, exist_ok=True)
    manifest = open(out / "manifest.jsonl", "w")
    counts = {}
    for test_yaml in sorted(Path(args.examples).glob("itpcp.pgph.py.*/test.yaml")):
        ex_dir = test_yaml.parent
        slug = ex_dir.name.removeprefix("itpcp.pgph.py.")
        entry = graphics_entry(test_yaml)
        if not entry or (args.slugs and slug not in args.slugs.split(",")):
            continue
        slug_dir = out / "cases" / slug
        ref = render_case(ex_dir, [ex_dir / entry], entry, slug_dir, "reference")
        if "png" not in ref:
            print(f"{slug}: reference does not render: {ref}")
            continue
        candidates = collect(slug, ex_dir, entry, Path(args.assignments), Path(args.blind))
        for kind, src in mutate((ex_dir / entry).read_text()).items():
            mdir = slug_dir / "mutants" / kind
            mdir.mkdir(parents=True, exist_ok=True)
            (mdir / entry).write_text(src)
            helpers = [f for f in ex_dir.glob("*.py") if f.name != entry]
            candidates.append((f"mutation/{kind}", [mdir / entry, *helpers]))
        seen = set()
        for source, files in candidates:
            digest = hashlib.sha256(b"".join(f.read_bytes() for f in files)).hexdigest()[:16]
            if digest in seen:
                continue
            seen.add(digest)
            case_id = f"{slug}__{source.replace('/', '_')}__{digest[:6]}"
            row = {"id": case_id, "slug": slug, "source": source, "entry": entry,
                   "reference_png": ref["png"]}
            if source.startswith("mutation/"):
                row["mutation_class"] = MUTATION_CLASS[source.split("/", 1)[1]]
            row.update(harness_label(Path(args.harness), slug, files, slug_dir / "harness" / case_id))
            row.update(render_case(ex_dir, files, entry, slug_dir, case_id))
            manifest.write(json.dumps(row) + "\n")
            manifest.flush()
            counts[(row["label"], "png" in row)] = counts.get((row["label"], "png" in row), 0) + 1
            print(f"{slug:24} {source:32} label={row['label']} "
                  f"{'rendered' if 'png' in row else row.get('render_error', '')[:60]}")
    print("counts (label, rendered):", counts)


if __name__ == "__main__":
    main()
