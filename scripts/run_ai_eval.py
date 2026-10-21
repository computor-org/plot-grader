#!/usr/bin/env python3
"""
Discover real student submissions where Tier 1 fails but a plot exists,
build a manifest, then run full grading with real AI (Qwen3-VL) if available.

Outputs:
- data/ai_eval/cases.json      # manifest of selected cases
- data/ai_eval/results.json    # grading outcomes with AI feedback
- data/ai_eval/report.html     # visual report (reuses existing template)
"""

import sys
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root / "scripts"))

from plot_grader.executor import execute_plot_code, extract_plot_data, render_figure_to_bytes
from plot_grader.tier1 import Tier1Grader
from plot_grader.grader import PlotGrader
from plot_grader.report import generate_html_report
from plot_grader.judges import add_judge_args, tier4_from_args



def find_student_submissions(search_dirs: List[Path]) -> List[Tuple[Path, str]]:
    """
    Find all plot_docstr.py student submissions.

    Returns: List of (file_path, student_name) tuples
    """
    submissions = []

    for search_dir in search_dirs:
        if not search_dir.exists():
            print(f"Skipping non-existent: {search_dir}")
            continue

        print(f"Scanning: {search_dir}")

        # Find all plot_docstr.py files
        for file_path in search_dir.rglob("plot_docstr.py"):
            # Skip our own test variants
            if "test_variants" in str(file_path):
                continue
            # Skip reference/correct solutions (we don't grade those)
            if "_reference" in str(file_path) or "_correctSolution" in str(file_path):
                continue
            if "master" in str(file_path):
                continue

            # Extract student name from path
            # Try to get meaningful name from directory structure
            parts = file_path.parts
            student_name = "unknown"

            # Look for patterns like "studentXXX" or assignment directories
            for i, part in enumerate(parts):
                if "student" in part.lower() or "submission" in part.lower():
                    student_name = part
                    break
                elif i > 0 and ("Unit01" in parts[i-1] or "04_plot_docstr" in parts[i-1]):
                    student_name = part
                    break

            # Use filename's parent as fallback
            if student_name == "unknown":
                student_name = file_path.parent.name

            submissions.append((file_path, student_name))

    # Deduplicate by path
    seen_paths = set()
    deduplicated = []
    for path, name in submissions:
        if path not in seen_paths:
            seen_paths.add(path)
            deduplicated.append((path, name))

    return deduplicated

def find_reference(assignments_root: Path, override: Path | None = None) -> Path:
    """Locate reference solution for plot_docstr assignment.

    If override is provided and exists, it is returned directly.
    """
    if override and override.exists():
        return override

    default = assignments_root / "01_Unit01" / "04_plot_docstr" / "localTests" / "_reference" / "plot_docstr.py"
    if default.exists():
        return default

    matches = list(assignments_root.rglob("_reference/plot_docstr.py")) if assignments_root.exists() else []
    if matches:
        return matches[0]
    raise FileNotFoundError("No reference plot_docstr.py found under assignments root")


def collect_candidates(assignments_root: Path,
                       max_total: int,
                       max_per_assignment: int,
                       sample_images: int,
                       reference_override: Path | None = None) -> Dict[str, Any]:
    """Scan student submissions and keep ones where Tier 1 fails but figure is non-empty."""
    ref_path = find_reference(assignments_root, reference_override)

    # Load reference figure/data once
    ref_exec = execute_plot_code(ref_path)
    if not ref_exec['success']:
        raise RuntimeError(f"Reference execution failed: {ref_exec['error']}")

    ref_fig = ref_exec['figure']
    ref_data = extract_plot_data(ref_fig)
    ref_img = render_figure_to_bytes(ref_fig)

    tier1 = Tier1Grader()

    # Discover student submissions via existing helper
    search_dirs = [assignments_root]
    submissions = find_student_submissions(search_dirs)

    manifest = []
    included_counts = {}
    img_budget = sample_images

    for sub_path, student_name in submissions:
        # Enforce per-assignment cap
        assignment_id = sub_path.parts[-5] if len(sub_path.parts) >= 5 else "unknown"
        if included_counts.get(assignment_id, 0) >= max_per_assignment:
            continue

        exec_res = execute_plot_code(sub_path)
        if not exec_res['success']:
            continue

        fig = exec_res['figure']
        data = extract_plot_data(fig)

        # Skip empty plots
        line_count = sum(len(ax['lines']) for ax in data.get('axes', []))
        if line_count == 0:
            continue

        # Tier 1 grade
        t1_res = tier1.grade(data, ref_data)
        if t1_res.passed:
            continue  # only keep Tier1 failures

        entry: Dict[str, Any] = {
            "path": str(sub_path),
            "student": student_name,
            "assignment": assignment_id,
            "line_count": line_count,
            "tier1_failed_checks": t1_res.failed_checks[:5],
            "tier1_passed_checks": t1_res.passed_checks[:5],
        }

        # Optionally attach images for early cases to help manual review
        if img_budget > 0:
            entry["images"] = {
                "reference": ref_img,
                "submission": render_figure_to_bytes(fig),
            }
            img_budget -= 1

        manifest.append(entry)
        included_counts[assignment_id] = included_counts.get(assignment_id, 0) + 1

        if len(manifest) >= max_total:
            break

    return {
        "reference_path": str(ref_path),
        "cases": manifest,
    }


def run_ai_eval(manifest: Dict[str, Any], use_real_ai: bool, report_dir: Path,
                tier4_grader=None):
    """Run full grading with AI on manifest cases and persist results."""
    report_dir.mkdir(parents=True, exist_ok=True)

    ref_path = Path(manifest["reference_path"])
    grader = PlotGrader(use_real_ai=use_real_ai, tier4_grader=tier4_grader,
                        test_mode=True, enable_ai_feedback=True)

    ref_exec = execute_plot_code(ref_path)
    ref_img = render_figure_to_bytes(ref_exec['figure']) if ref_exec['success'] else None

    submissions_out = []
    tier_counts = {}
    passed = 0

    for idx, case in enumerate(manifest["cases"], 1):
        sub_path = Path(case["path"])
        student_img = None
        try:
            result = grader.grade_submission(sub_path, ref_path)

            # Render submission for first few cases to keep reports informative but small
            if idx <= 50:
                exec_res = execute_plot_code(sub_path)
                if exec_res['success']:
                    student_img = render_figure_to_bytes(exec_res['figure'])

            tier_name = result.tier.value if result.tier else 'ERROR'
            tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1
            if result.passed:
                passed += 1

            submissions_out.append({
                "name": case.get("student", sub_path.name),
                "path": str(sub_path),
                "actual_pass": result.passed,
                "expected_pass": None,
                "tier": tier_name,
                "confidence": result.confidence,
                "score": result.score,
                "execution_time_ms": result.execution_time_ms,
                "passed_checks": result.passed_checks[:10],
                "failed_checks": result.failed_checks[:10],
                "warnings": result.warnings[:10],
                "error_message": result.error_message,
                "images": {
                    "reference": ref_img if idx <= 50 else None,
                    "submission": student_img,
                },
            })

        except Exception as e:
            submissions_out.append({
                "name": sub_path.name,
                "path": str(sub_path),
                "actual_pass": False,
                "expected_pass": None,
                "tier": "ERROR",
                "confidence": 0.0,
                "score": 0.0,
                "execution_time_ms": 0.0,
                "passed_checks": [],
                "failed_checks": [str(e)],
                "warnings": [],
                "error_message": str(e),
                "images": {"reference": None, "submission": None},
            })
            tier_counts['ERROR'] = tier_counts.get('ERROR', 0) + 1

    total = len(submissions_out)
    results = {
        "reference_path": str(ref_path),
        "submissions": submissions_out,
        "tier_distribution": tier_counts,
        "pass_rate": passed / total if total else 0.0,
    }

    # Persist JSON
    (report_dir / "results.json").write_text(json.dumps(results, indent=2, default=str))

    # Build HTML report using existing template
    generate_html_report(results, report_dir / "report.html")

    return results


def main():
    parser = argparse.ArgumentParser(description="AI evaluation on Tier1-fail real submissions")
    parser.add_argument("--assignments-root", default=str(Path(__file__).parent.parent / "../assignments"),
                        help="Path to assignments root (default: ../assignments)")
    parser.add_argument("--max-total", type=int, default=200, help="Max total cases to keep")
    parser.add_argument("--max-per-assignment", type=int, default=50, help="Per-assignment cap")
    parser.add_argument("--sample-images", type=int, default=30, help="Number of cases to embed images for")
    parser.add_argument("--ai", action="store_true", help="Use real AI grader (Qwen3-VL)")
    parser.add_argument("--reference", help="Explicit reference plot_docstr.py path (optional)")
    add_judge_args(parser)
    args = parser.parse_args()

    assignments_root = Path(args.assignments_root).resolve()
    report_dir = Path(__file__).parent.parent / "data" / "ai_eval"

    report_dir.mkdir(parents=True, exist_ok=True)

    print("Discovering Tier1-fail-but-nonempty submissions...")
    manifest = collect_candidates(
        assignments_root,
        max_total=args.max_total,
        max_per_assignment=args.max_per_assignment,
        sample_images=args.sample_images,
        reference_override=Path(args.reference) if args.reference else None,
    )
    (report_dir / "cases.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(f"Collected {len(manifest['cases'])} cases -> {report_dir / 'cases.json'}")

    print("\nRunning AI evaluation (test_mode=True)...")
    results = run_ai_eval(manifest, use_real_ai=args.ai, report_dir=report_dir,
                          tier4_grader=tier4_from_args(args))
    print(f"Results JSON: {report_dir / 'results.json'}")
    print(f"HTML report:  {report_dir / 'report.html'}")
    print(f"Pass rate: {results['pass_rate']*100:.1f}% across {len(results['submissions'])} cases")


if __name__ == "__main__":
    main()
