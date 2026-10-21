#!/usr/bin/env python3
"""Side-by-side sheets (reference | student) for labelling by eye.

Usage: make_label_sheets.py [MANIFEST] [OUT_DIR]
Writes OUT_DIR/NNN.png for every rendered case and OUT_DIR/index.tsv
(number, case id). Sheets are numbered so the labeller does not see the
source or mutation kind. Visual labels against docs/criteria.md go to
data/eval_set/visual_labels.jsonl as {"id", "visual": PASS|FAIL,
"criterion": "M1".."M6" or "", "note"}.
"""

import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HEIGHT = 520


def fit(path: str) -> Image.Image:
    im = Image.open(path).convert("RGB")
    return im.resize((max(1, im.width * HEIGHT // im.height), HEIGHT))


def main():
    manifest = Path(sys.argv[1] if len(sys.argv) > 1 else "data/eval_set/manifest.jsonl")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/eval_set/label_sheets")
    out.mkdir(parents=True, exist_ok=True)
    ids = []
    rows = [json.loads(line) for line in open(manifest)]
    random.Random(4).shuffle(rows)  # mix exercises and sources
    for row in rows:
        if "png" not in row or row.get("label") is None:
            continue
        ref, stu = fit(row["reference_png"]), fit(row["png"])
        sheet = Image.new("RGB", (ref.width + stu.width + 20, HEIGHT + 30), "white")
        sheet.paste(ref, (0, 30))
        sheet.paste(stu, (ref.width + 20, 30))
        draw = ImageDraw.Draw(sheet)
        draw.text((5, 8), "REFERENCE", fill="black")
        draw.text((ref.width + 25, 8), "STUDENT", fill="black")
        draw.line([(ref.width + 10, 0), (ref.width + 10, HEIGHT + 30)], fill="gray", width=2)
        sheet.save(out / f"{len(ids):03d}.png")
        ids.append(row["id"])
    (out / "index.tsv").write_text("".join(f"{n:03d}\t{i}\n" for n, i in enumerate(ids)))
    print(f"{len(ids)} sheets in {out}")


if __name__ == "__main__":
    main()
