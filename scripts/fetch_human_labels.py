#!/usr/bin/env python3
"""Download the human judge's answers from plotcheck into data/human_labels/.

Usage: fetch_human_labels.py --base https://<plotcheck-host>
                             [--tokens data/judge_package/private/tokens.json]
                             [--out data/human_labels]

Writes answers.jsonl (current answer per judge and case) and events.jsonl
(every click), plus timestamped copies. The admin token is read from the
private tokens file and sent as a Bearer header.
"""

import argparse
import json
import urllib.request
from datetime import datetime
from pathlib import Path


def fetch(base: str, admin: str, what: str) -> bytes:
    req = urllib.request.Request(f"{base.rstrip('/')}/admin/export?what={what}",
                                 headers={"Authorization": f"Bearer {admin}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="URL of the webjudge host")
    ap.add_argument("--tokens", default="data/judge_package/private/tokens.json")
    ap.add_argument("--out", default="data/human_labels")
    a = ap.parse_args()
    admin = json.loads(Path(a.tokens).read_text())["admin"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for what in ("answers", "events"):
        data = fetch(a.base, admin, what)
        for name in (f"{what}.jsonl", f"{what}_{stamp}.jsonl"):
            (out / name).write_bytes(data)
        rows = [json.loads(x) for x in data.decode().splitlines() if x.strip()]
        judges = sorted({r["judge"] for r in rows})
        print(f"{what}: {len(rows)} rows, judges {judges} -> {out / (what + '.jsonl')}")


if __name__ == "__main__":
    main()
