"""Render a plotting script to one PNG in a subprocess-safe way.

Usage: python -m plot_grader.render WORKDIR ENTRY.py OUT.png OUT.json

Runs ENTRY.py inside WORKDIR (so data files and helper modules resolve), with
plt.show/plt.pause/input disabled. All open figures are rendered and stacked
vertically into OUT.png. OUT.json gets the extracted data of figure 1 (for
Tier 1) and the number of figures.
"""

import builtins
import io
import json
import os
import random
import runpy
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

from plot_grader.executor import extract_plot_data, render_figure_to_bytes  # noqa: E402


def _jsonable(obj):
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return str(obj)


def render(workdir: Path, entry: str, out_png: Path, out_json: Path) -> int:
    os.chdir(workdir)
    sys.path.insert(0, str(workdir))
    plt.show = lambda *a, **k: None
    plt.pause = lambda *a, **k: None
    builtins.input = lambda *a, **k: ""
    random.seed(1)  # as the Computor harness (python/test_class.py)
    np.random.seed(1)
    runpy.run_path(entry, run_name="__main__")
    figs = [plt.figure(n) for n in plt.get_fignums()]
    if not figs:
        raise RuntimeError("no matplotlib figure created")
    images = [Image.open(io.BytesIO(render_figure_to_bytes(f))).convert("RGB") for f in figs]
    width = max(im.width for im in images)
    canvas = Image.new("RGB", (width, sum(im.height for im in images)), "white")
    y = 0
    for im in images:
        canvas.paste(im, (0, y))
        y += im.height
    canvas.save(out_png)
    data = extract_plot_data(figs[0])
    out_json.write_text(json.dumps({"n_figures": len(figs), "plot_data": data},
                                   default=_jsonable))
    return len(figs)


if __name__ == "__main__":
    wd, entry, png, js = sys.argv[1:5]
    render(Path(wd), entry, Path(png).resolve(), Path(js).resolve())
