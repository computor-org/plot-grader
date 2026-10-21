"""Round-4 plot verdict: tolerant model and tolerant data checks (docs/criteria.md).

A student plot PASSES if it is pixel-identical to the reference (no model
call), or if Flash-Next with the tolerant prompt (`view="pair_tolerant"`,
chat mode, images at 75 %) says PASS and `tolerant_check` finds no content
problem in the extracted plot data. Everything else is FAIL, or ERROR when
the model reply is unusable and the data checks found nothing.

CLI: python -m plot_grader.tolerant_judge STUDENT_DIR ENTRY REFERENCE_DIR
renders both scripts with plot_grader.render and prints the verdict as JSON.
REFERENCE_DIR may hold the reference under another file name (--ref-entry).
"""

import argparse
import io
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from plot_grader.judges import DEFAULT_ENDPOINTS, load_endpoints, make_judge
from plot_grader.tolerant import tolerant_check, unseeded_random

MODEL = "flash-next"
SCALE = 0.75
VIEW = "pair_tolerant"
_CODE = re.compile(r"\bM[1-6]\b")


@dataclass
class TolerantVerdict:
    verdict: str  # "PASS", "FAIL" or "ERROR"
    criteria: List[str] = field(default_factory=list)  # violated, e.g. ["M4"]
    problems: List[str] = field(default_factory=list)  # from tolerant_check
    differences: List[str] = field(default_factory=list)  # from the model
    hint: str = ""
    pixel_identical: bool = False
    model_verdict: Optional[str] = None
    latency_s: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def scale_png(png: bytes, scale: float = SCALE) -> bytes:
    """Resize a PNG by `scale` (LANCZOS), as in the round-3/4 evaluation."""
    if scale == 1.0:
        return png
    im = Image.open(io.BytesIO(png))
    size = (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
    buf = io.BytesIO()
    im.resize(size, Image.LANCZOS).save(buf, format="PNG")
    return buf.getvalue()


def pixel_identical(a: bytes, b: bytes) -> bool:
    """Same size and no visibly differing pixel (a colour channel differs by > 10).

    RGB, not grey levels as in scripts/report_round4.py: red and matplotlib's
    green have almost the same grey level.
    """
    A = np.asarray(Image.open(io.BytesIO(a)).convert("RGB"), float)
    B = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"), float)
    return A.shape == B.shape and not bool((np.abs(A - B) > 10).any())


def _plot_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Accept render.py's JSON ({"plot_data": ...}) or the plot data itself."""
    return data.get("plot_data", data)


def default_judge(endpoints: Path = DEFAULT_ENDPOINTS):
    return make_judge(load_endpoints(Path(endpoints)), MODEL, "chat")


def judge_plot(student_png: bytes, reference_png: bytes,
               student_data: Dict[str, Any], reference_data: Dict[str, Any],
               judge=None, scale: float = SCALE,
               random_data: bool = False) -> TolerantVerdict:
    """Round-4 verdict for one student plot against its reference.

    `judge` is anything with judges.CompletionsJudge's `judge()` signature;
    by default Flash-Next in chat mode from configs/vlm_endpoints.json.
    The model is asked even when the data checks fail, for differences and
    a hint to show the student. `random_data`: the reference draws unseeded
    random numbers (see tolerant.unseeded_random); the data checks then skip
    the curve comparison.
    """
    if pixel_identical(student_png, reference_png):
        return TolerantVerdict("PASS", pixel_identical=True)
    problems = tolerant_check(_plot_data(student_data), _plot_data(reference_data),
                              random_data)
    judge = judge or default_judge()
    res = judge.judge(scale_png(student_png, scale), scale_png(reference_png, scale),
                      view=VIEW)
    codes = {c for p in problems for c in p.split()[0].split("/")}
    if res.verdict == "FAIL":
        codes |= {c for d in res.differences for c in _CODE.findall(d)}
    if problems or res.verdict == "FAIL":
        verdict = "FAIL"
    elif res.verdict == "PASS":
        verdict = "PASS"
    else:
        verdict = "ERROR"
    return TolerantVerdict(
        verdict, criteria=sorted(codes), problems=problems,
        differences=list(res.differences) if res.verdict == "FAIL" else [],
        hint=res.hint if verdict != "PASS" else "", model_verdict=res.verdict,
        latency_s=res.latency_s, error=res.error)


def render_script(workdir: Path, entry: str, out_png: Path,
                  timeout: float = 120) -> Dict[str, Any]:
    """Render WORKDIR/ENTRY in a subprocess; return render.py's JSON."""
    out_json = out_png.with_suffix(".json")
    proc = subprocess.run(
        [sys.executable, "-m", "plot_grader.render", str(workdir), entry,
         str(out_png), str(out_json)],
        capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or not out_png.exists():
        last = (proc.stderr.strip().splitlines() or ["render failed"])[-1]
        raise RuntimeError(f"{workdir / entry}: {last}")
    return json.loads(out_json.read_text())


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("student_dir")
    p.add_argument("entry")
    p.add_argument("reference_dir")
    p.add_argument("--ref-entry", help="reference file name (default: ENTRY)")
    p.add_argument("--endpoints", default=str(DEFAULT_ENDPOINTS))
    args = p.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        s_png, r_png = Path(tmp, "student.png"), Path(tmp, "reference.png")
        s_data = render_script(Path(args.student_dir).resolve(), args.entry, s_png)
        r_data = render_script(Path(args.reference_dir).resolve(),
                               args.ref_entry or args.entry, r_png)
        ref_src = Path(args.reference_dir, args.ref_entry or args.entry).read_text()
        v = judge_plot(s_png.read_bytes(), r_png.read_bytes(), s_data, r_data,
                       judge=default_judge(Path(args.endpoints)),
                       random_data=unseeded_random(ref_src))
    print(json.dumps(v.to_dict(), ensure_ascii=False, indent=2))
    return 0 if v.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
