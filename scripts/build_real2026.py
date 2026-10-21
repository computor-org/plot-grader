#!/usr/bin/env python3
"""Real 2026 PiP submissions for the plot judge (round 5).

Two steps:

  fetch  Read-only download of the latest submitted artifact per student for
         every exercise with a graphics test (Computor API, course
         "Programmieren in der Physik 2026 PYTHON"). Students are keyed by a
         random pseudonym immediately; the pseudonym -> course member mapping
         lives only in data/real2026/private/ (mode 600). No names or emails
         are requested or stored.
  build  Label every submission with the official harness and render it,
         reusing scripts/build_eval_set.py. Writes data/real2026/manifest.jsonl
         in the eval-set schema (source="real2026").

Everything is written under data/real2026/ (gitignored). fetch needs read
access to a Computor API (COMPUTOR_URL), the course id in COMPUTOR_COURSE_ID,
and the course test harness scripts (with computor_client) in
PLOT_GRADER_HARNESS.
"""

import argparse
import base64
import io
import json
import os
import re
import secrets
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_eval_set import HOME, REPO, graphics_entry, harness_label, render_case  # noqa: E402

COURSE = os.environ.get("COMPUTOR_COURSE_ID", "")  # Computor course to fetch from
OUT = REPO / "data/real2026"
PRIVATE = OUT / "private"
EXAMPLES = HOME / "code/codeability/examples/python"
HARNESS = Path(os.environ.get("PLOT_GRADER_HARNESS", str(REPO / "data/harness")))
DEPLOYED = OUT / "examples_deployed"  # exercises as deployed in the 2026 course


def graphics_exercises() -> dict:
    """slug -> entry point for every exercise with a graphics test collection."""
    found = {}
    for test_yaml in sorted(EXAMPLES.glob("itpcp.pgph.py.*/test.yaml")):
        entry = graphics_entry(test_yaml)
        if entry:
            found[test_yaml.parent.name.removeprefix("itpcp.pgph.py.")] = entry
    return found


def private_json(name: str, data=None):
    """Read (data=None) or write a JSON file in the private directory, mode 600."""
    PRIVATE.mkdir(parents=True, exist_ok=True)
    PRIVATE.chmod(0o700)
    path = PRIVATE / name
    if data is None:
        return json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps(data, indent=1))
    path.chmod(0o600)


def fetch(args):
    if not COURSE:
        sys.exit("set COMPUTOR_COURSE_ID to the Computor course id")
    sys.path.insert(0, str(HARNESS))
    from computor_client import api_get, api_get_binary  # read-only GET helpers

    exercises = graphics_exercises()
    contents, deployments = {}, {}
    for c in api_get("/course-contents", params={"course_id": COURSE, "limit": "500"}):
        slug = ((c.get("deployment") or {}).get("example_identifier") or "")
        slug = slug.removeprefix("itpcp.pgph.py.")
        if slug in exercises:
            contents[slug] = c["id"]
            dep = c["deployment"]
            deployments[slug] = {k: dep.get(k) for k in ("example_version_id", "version_tag",
                                                         "deployed_at", "has_newer_version")}
    (OUT / "deployments.json").write_text(json.dumps(deployments, indent=1))
    for slug, dep in deployments.items():  # the exercise exactly as deployed
        ex = DEPLOYED / "python" / f"itpcp.pgph.py.{slug}"
        for name, text in api_get(f"/examples/download/{dep['example_version_id']}")["files"].items():
            (ex / name).parent.mkdir(parents=True, exist_ok=True)
            if text.startswith("data:") and ";base64," in text[:100]:  # binary files
                (ex / name).write_bytes(base64.b64decode(text.split(",", 1)[1]))
            else:
                (ex / name).write_text(text)
    if args.examples_only:
        return
    pseudo = private_json("pseudonyms.json")  # course member id -> pseudonym
    taken = set(pseudo.values())
    provenance = private_json("artifacts.json")  # slug/pseudonym -> artifact id
    stats = {}
    for slug in sorted(exercises):
        if slug not in contents:
            print(f"{slug}: not deployed in the course")
            continue
        arts, skip = [], 0
        while True:
            page = api_get("/submissions/artifacts", params={
                "course_content_id": contents[slug], "limit": "500", "skip": str(skip)})
            arts += page
            skip += len(page)
            if len(page) < 500:
                break
        latest = {}
        for a in arts:
            if not a.get("submit"):
                continue
            member = a["uploaded_by_course_member_id"]
            if member not in latest or a["created_at"] > latest[member]["created_at"]:
                latest[member] = a
        for member, a in latest.items():
            if member not in pseudo:
                p = "s" + secrets.token_hex(4)
                while p in taken:
                    p = "s" + secrets.token_hex(4)
                pseudo[member] = p
                taken.add(p)
            target = OUT / "subs" / slug / pseudo[member]
            if target.exists() and any(target.iterdir()):
                continue
            target.mkdir(parents=True, exist_ok=True)
            data = api_get_binary(f"/submissions/artifacts/{a['id']}/download")
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    name = Path(info.filename).name
                    if not info.is_dir() and name and not name.startswith("."):
                        (target / name).write_bytes(z.read(info))
            provenance[f"{slug}/{pseudo[member]}"] = {"artifact": a["id"],
                                                     "created_at": a["created_at"]}
        stats[slug] = {"artifacts": len(arts), "submitted": sum(bool(a.get("submit")) for a in arts),
                       "students": len(latest)}
        print(f"{slug:24} artifacts={len(arts):5} submitted={stats[slug]['submitted']:5} "
              f"students={len(latest)}", flush=True)
        private_json("pseudonyms.json", pseudo)
        private_json("artifacts.json", provenance)
    (OUT / "fetch_stats.json").write_text(json.dumps(stats, indent=1))


def build(args):
    exercises = graphics_exercises()
    jobs, refs = [], {}
    roots = {}
    only = set(args.slugs.split(",")) if args.slugs else None
    for slug, entry in sorted(exercises.items()):
        if only and slug not in only:
            continue
        subs = sorted((OUT / "subs" / slug).glob("s*/"))
        if not subs:
            continue
        roots[slug] = DEPLOYED if args.deployed else EXAMPLES.parent
        ex_dir = roots[slug] / "python" / f"itpcp.pgph.py.{slug}"
        entry = graphics_entry(ex_dir / "test.yaml") or entry
        ref = render_case(ex_dir, [ex_dir / entry], entry, OUT / "cases" / slug, "reference")
        if "png" not in ref:
            print(f"{slug}: reference does not render: {ref}")
            continue
        refs[slug] = ref["png"]
        jobs += [(slug, entry, ex_dir, d) for d in subs]

    def one(job):
        slug, entry, ex_dir, d = job
        case_id = f"{slug}__real2026__{d.name}"
        row = {"id": case_id, "slug": slug, "source": "real2026", "entry": entry,
               "reference_png": refs[slug]}
        # Like the test engine, the exercise's additionalFiles (data files) win
        # over copies the student submitted.
        meta = (ex_dir / "meta.yaml").read_text()
        extra = set(re.findall(r"^\s*-\s*(\S+)", meta.split("additionalFiles:", 1)[1]
                               .split("testFiles:", 1)[0], re.M)) if "additionalFiles:" in meta else set()
        files = sorted(f for f in d.iterdir() if f.is_file() and f.name not in extra)
        renamed = [f for f in files if f.name != entry and f.name.replace("skript", "script") == entry]
        if renamed and not any(f.name == entry for f in files):
            # The deployed 2026 version used the German file name (pskript.py,
            # gauss1d_skript.py); the current repo and tests use "script".
            alias = OUT / "alias" / slug / d.name
            alias.mkdir(parents=True, exist_ok=True)
            for f in files:
                (alias / f.name.replace("skript", "script")).write_bytes(f.read_bytes())
            files = sorted(alias.iterdir())
        if not any(f.name == entry for f in files):
            row.update({"label": None, "harness_error": f"no {entry} in submission"})
            return row
        slug_dir = OUT / "cases" / slug
        row.update(harness_label(HARNESS, slug, files, slug_dir / "harness" / case_id,
                                 repo=roots[slug]))
        if args.deployed:
            row["examples"] = "deployed2026"
        row.update(render_case(ex_dir, files, entry, slug_dir, case_id))
        return row

    counts = {}
    kept = []  # with --slugs, rows of the other exercises stay in the manifest
    if only and (OUT / "manifest.jsonl").exists():
        kept = [line for line in open(OUT / "manifest.jsonl")
                if json.loads(line)["slug"] not in only]
    with open(OUT / "manifest.jsonl", "w") as fh, ThreadPoolExecutor(args.workers) as pool:
        fh.writelines(kept)
        for row in pool.map(one, jobs):
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            key = (row["label"], "png" in row)
            counts[key] = counts.get(key, 0) + 1
            print(f"{row['id']:48} label={row['label']} "
                  f"{'rendered' if 'png' in row else row.get('render_error', row.get('harness_error', ''))[:50]}",
                  flush=True)
    print("counts (label, rendered):", counts)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("step", choices=["fetch", "build"])
    p.add_argument("--slugs", help="build: comma list; rebuild only these exercises")
    p.add_argument("--deployed", action="store_true",
                   help="build: test and render against the exercises as deployed in 2026 "
                   "(downloaded by fetch; the repo was cleaned up after the semester)")
    p.add_argument("--examples-only", action="store_true",
                   help="fetch: only the deployed exercise versions, no submissions")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {"fetch": fetch, "build": build}[args.step](args)


if __name__ == "__main__":
    main()
