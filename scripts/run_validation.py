#!/usr/bin/env python3
"""
Run validation on plot_docstr assignment with stress tests.

Generates visual HTML report showing tier distribution and results.
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from plot_grader.stress_tests import PlotDocstrStressTests
from plot_grader.validator import Validator
from plot_grader.report import generate_html_report
from plot_grader.judges import add_judge_args, tier4_from_args


def main():
    parser = argparse.ArgumentParser(description="Run plot grader validation")
    parser.add_argument("--ai", action="store_true", help="Enable real AI grading (Qwen3-VL)")
    parser.add_argument("--test-mode", action="store_true", help="Run all tiers for comparison")
    parser.add_argument("--reference", help="reference solution plot_docstr.py (default: search ../assignments)")
    add_judge_args(parser)
    args = parser.parse_args()

    print("Plot Grader MVP Validation")
    if args.ai:
        print("AI MODE: Using real Qwen3-VL-4B")
    if args.test_mode:
        print("TEST MODE: All tiers will run")

    # Paths
    repo_root = Path(__file__).parent.parent
    data_dir = repo_root / "data"
    test_variants_dir = data_dir / "test_variants"
    output_dir = data_dir / "validation_results"

    # Reference solution path (allow flexible assignment repos)
    default_ref_path = repo_root.parent / "assignments" / "01_Unit01" / "04_plot_docstr" / \
                       "localTests" / "_reference" / "plot_docstr.py"

    ref_path = Path(args.reference) if args.reference else default_ref_path
    if not ref_path.exists():
        # Fallback: search within ../assignments for any _reference/plot_docstr.py
        assignments_root = repo_root.parent / "assignments"
        matches = list(assignments_root.rglob("_reference/plot_docstr.py")) if assignments_root.exists() else []
        if matches:
            ref_path = matches[0]

    if not ref_path.exists():
        print("\nERROR: Reference solution not found. Searched:")
        print(f" - {default_ref_path}")
        print(" - ../assignments/**/_reference/plot_docstr.py")
        print("Please ensure the assignments repo is available via glab clone.")
        sys.exit(1)

    print(f"\nFound reference solution: {ref_path}")

    # Generate stress test variants
    print("\nGenerating stress test variants...")
    positive_variants = PlotDocstrStressTests.generate_positive_variants(
        test_variants_dir / "positive"
    )
    print(f"  Generated {len(positive_variants)} positive variants")

    negative_variants = PlotDocstrStressTests.generate_negative_variants(
        test_variants_dir / "negative"
    )
    print(f"  Generated {len(negative_variants)} negative variants")

    # Run validation
    print("\nRunning validation...")
    validator = Validator(
        use_real_ai=args.ai,
        test_mode=args.test_mode,
        tier4_grader=tier4_from_args(args),
    )
    validation_run = validator.run_validation(
        reference_path=ref_path,
        positive_variants=positive_variants,
        negative_variants=negative_variants,
    )

    # Print summary
    print("\nVALIDATION SUMMARY")
    print(f"Total submissions: {len(validation_run.submissions)}")
    print(f"Pass rate: {validation_run.pass_rate * 100:.1f}%")
    print(f"False negative rate: {validation_run.false_negative_rate * 100:.1f}%")
    print(f"False positive rate: {validation_run.false_positive_rate * 100:.1f}%")

    print("\nTier Distribution:")
    total = len(validation_run.submissions)
    for tier, count in sorted(validation_run.tier_distribution.items()):
        pct = count / total * 100
        print(f"  {tier}: {count} ({pct:.1f}%)")

    # Generate HTML report
    print("\nGenerating HTML report...")
    report_path = output_dir / "validation_report.html"
    generate_html_report(validation_run.to_dict(), report_path)
    print(f"Report saved to: {report_path}")
    print(f"JSON data saved to: {report_path.with_suffix('.json')}")

    # Open in browser
    print("\nTo view the report:")
    print(f"  open {report_path}")

    # Check hypothesis
    print("\nHYPOTHESIS VALIDATION")

    tier1_count = validation_run.tier_distribution.get("Tier 1: Smart Hardcoded", 0)
    tier2_count = validation_run.tier_distribution.get("Tier 2: Structural Heuristics", 0)
    tier3_count = validation_run.tier_distribution.get("Tier 3: OpenCV Visual", 0)

    tier1_pct = tier1_count / total * 100
    tier2_pct = tier2_count / total * 100
    tier3_pct = tier3_count / total * 100

    print("Expected: Tier 1 >80%, Tier 2 ~15%, Tier 3 ~4%")
    print(f"Actual:   Tier 1 {tier1_pct:.1f}%, Tier 2 {tier2_pct:.1f}%, Tier 3 {tier3_pct:.1f}%")

    if tier1_pct >= 80:
        print("PASS: Tier 1 hypothesis validated (>=80%)")
    else:
        print(f"FAIL: Tier 1 hypothesis failed ({tier1_pct:.1f}% < 80%)")

    if validation_run.false_negative_rate == 0.0:
        print("PASS: No false negatives (all positive variants passed)")
    else:
        print(f"FAIL: {validation_run.false_negative_rate * 100:.1f}% false negatives detected")

    if validation_run.false_positive_rate < 0.001:
        print("PASS: False positive rate <0.1%")
    else:
        print(f"WARN: False positive rate {validation_run.false_positive_rate * 100:.1f}%")


if __name__ == "__main__":
    main()
