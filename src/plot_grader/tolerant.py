"""Tolerant deterministic checks on extracted plot data (docs/criteria.md).

Checks only content, never style: panels exist (M6), labelled axes stay
labelled (M4, any wording), every reference curve has a student curve with
the same values in any order and at any sampling (M1, M2), and the x range
still shows the reference data (M3). Returns the violated criteria.

Random data (T6): when the reference solution draws unseeded random numbers,
no student draw can match its values, so M1/M2 are left to the model.
"""

import re
from typing import Any, Dict, List

import numpy as np

DATA_TOL = 0.05  # max deviation as a share of the reference curve's y range
XRANGE_COVER = 0.8  # share of the reference x data range that must stay visible


def _real(values) -> np.ndarray:
    """Floats; complex values (also as strings like "(1+0j)") give their real
    part, as matplotlib plots them."""
    try:
        return np.asarray(values, float).ravel()
    except (TypeError, ValueError):
        return np.real(np.array([complex(v) for v in np.ravel(values)]))


def _xy(line: Dict[str, Any]):
    try:
        x, y = _real(line["xdata"]), _real(line["ydata"])
    except (TypeError, ValueError):
        return None
    ok = np.isfinite(x) & np.isfinite(y)
    return (x[ok], y[ok]) if ok.sum() >= 2 and len(x) == len(y) else None


def _same_curve(ref, stu) -> bool:
    (rx, ry), (sx, sy) = ref, stu
    lo, hi = max(rx.min(), sx.min()), min(rx.max(), sx.max())
    span = rx.max() - rx.min()
    if span > 0 and hi - lo < 0.5 * span:
        return False
    order = np.argsort(sx)
    sx, sy = sx[order], sy[order]
    inside = (rx >= lo) & (rx <= hi)
    if inside.sum() < 2:
        return False
    if len(np.unique(sx)) < len(sx):  # not a function of x: compare point sets
        pts = np.column_stack([sx, sy])
        dist = [np.min(np.hypot(*(pts - p).T)) for p in np.column_stack([rx, ry])[inside]]
        scale = np.hypot(np.ptp(rx), np.ptp(ry)) or 1.0
        return max(dist) <= DATA_TOL * scale
    yi = np.interp(rx[inside], sx, sy)
    scale = np.ptp(ry) or abs(ry).max() or 1.0
    return float(np.max(np.abs(yi - ry[inside]))) <= DATA_TOL * scale


_RANDOM = re.compile(r"\brandom\b|\brng\b|default_rng")
_SEED = re.compile(r"\bseed\s*\(|default_rng\s*\(\s*(seed\s*=\s*)?\d")


def unseeded_random(source: str) -> bool:
    """True if the (reference) source draws random numbers without fixing a seed."""
    code = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
    return bool(_RANDOM.search(code)) and not _SEED.search(code)


def tolerant_check(student: Dict[str, Any], reference: Dict[str, Any],
                   random_data: bool = False) -> List[str]:
    """Violated criteria, e.g. ["M4 axis 0 ylabel missing"]; [] means content OK.

    `random_data`: the reference draws unseeded random data (T6), skip M1/M2.
    """
    problems = []
    raxes, saxes = reference.get("axes", []), student.get("axes", [])
    if len(saxes) < len(raxes):
        problems.append(f"M6 {len(saxes)} panels instead of {len(raxes)}")
    for ra, sa in zip(raxes, saxes):
        k = ra["index"]
        for lab in ("xlabel", "ylabel"):
            if (ra.get(lab) or "").strip() and not (sa.get(lab) or "").strip():
                problems.append(f"M4 axis {k} {lab} missing")
        scurves = [c for c in map(_xy, sa.get("lines", [])) if c is not None]
        rcurves = [c for c in map(_xy, ra.get("lines", [])) if c is not None]
        for j, rc in enumerate([] if random_data else rcurves):
            if not any(_same_curve(rc, sc) for sc in scurves):
                problems.append(f"M1/M2 axis {k} curve {j} not found in the student plot")
        if rcurves and sa.get("xlim"):
            dlo = min(c[0].min() for c in rcurves)
            dhi = max(c[0].max() for c in rcurves)
            lo, hi = sa["xlim"]
            if dhi > dlo and (min(hi, dhi) - max(lo, dlo)) < XRANGE_COVER * (dhi - dlo):
                problems.append(f"M3 axis {k} x range hides the data")
    return problems
