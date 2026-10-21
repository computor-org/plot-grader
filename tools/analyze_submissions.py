#!/usr/bin/env python3
"""
Analyze student submissions to understand variation patterns.

This helps identify what types of variations students actually produce,
informing stress test generation.

Usage:
    python tools/analyze_submissions.py
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend


def extract_plot_attributes(py_file: Path) -> Dict:
    """Extract plotting attributes from a Python file without executing it."""
    content = py_file.read_text(errors='ignore')

    attributes = {
        'file': str(py_file),
        'has_plot': 'plt.plot' in content or '.plot(' in content,
        'has_subplot': 'plt.subplot' in content or 'plt.subplots' in content,
        'has_errorbar': 'plt.errorbar' in content,
        'has_animation': 'FuncAnimation' in content,
        'color_styles': [],
        'linestyles': [],
        'markers': [],
        'plot_commands': [],
    }

    # Extract plot commands (simple regex-like search)
    lines = content.split('\n')
    for line in lines:
        if 'plt.plot(' in line or '.plot(' in line:
            attributes['plot_commands'].append(line.strip())

            # Look for color specifiers
            if any(c in line for c in ["'r'", '"r"', "'red'", '"red"', '#FF0000']):
                attributes['color_styles'].append('red')
            if any(c in line for c in ["'b'", '"b"', "'blue'", '"blue"', '#0000FF']):
                attributes['color_styles'].append('blue')
            if any(c in line for c in ["'k'", '"k"', "'black'", '"black"', '#000000']):
                attributes['color_styles'].append('black')

            # Look for linestyles
            if '--' in line or 'dashed' in line:
                attributes['linestyles'].append('dashed')
            if ':' in line or 'dotted' in line:
                attributes['linestyles'].append('dotted')
            if "'-'" in line or '"solid"' in line:
                attributes['linestyles'].append('solid')

    return attributes


def analyze_assignment(assignment_name: str, submissions_dir: Path):
    """Analyze all submissions for a specific assignment."""
    print(f"\nAnalyzing: {assignment_name}\n")

    # Find all files for this assignment
    pattern = f"**/{assignment_name}.py"
    files = list(submissions_dir.glob(pattern))

    if not files:
        print(f"No submissions found for {assignment_name}")
        return

    print(f"Found {len(files)} submissions")

    # Analyze each submission
    analyses = []
    for f in files:
        try:
            analysis = extract_plot_attributes(f)
            analyses.append(analysis)
        except Exception as e:
            print(f"Error analyzing {f}: {e}")

    # Aggregate statistics
    total = len(analyses)
    has_plot = sum(1 for a in analyses if a['has_plot'])
    has_subplot = sum(1 for a in analyses if a['has_subplot'])

    print("\nStatistics:")
    print(f"  Total submissions: {total}")
    print(f"  With plot calls: {has_plot} ({100*has_plot/total:.1f}%)")
    print(f"  With subplots: {has_subplot} ({100*has_subplot/total:.1f}%)")

    # Color variations
    all_colors = [c for a in analyses for c in a['color_styles']]
    color_counts = Counter(all_colors)
    print("\n  Color usage:")
    for color, count in color_counts.most_common():
        print(f"    {color}: {count}")

    # Linestyle variations
    all_linestyles = [ls for a in analyses for ls in a['linestyles']]
    linestyle_counts = Counter(all_linestyles)
    print("\n  Linestyle usage:")
    for ls, count in linestyle_counts.most_common():
        print(f"    {ls}: {count}")

    # Unique implementations
    unique_plots = set(tuple(a['plot_commands']) for a in analyses)
    print(f"\n  Unique implementations: {len(unique_plots)}")

    # Show examples of variations
    if len(unique_plots) > 1:
        print("\n  Sample variations:")
        for i, plot_cmds in enumerate(list(unique_plots)[:3], 1):
            print(f"\n    Variant {i}:")
            for cmd in plot_cmds[:3]:  # First 3 plot commands
                print(f"      {cmd}")
            if len(plot_cmds) > 3:
                print(f"      ... ({len(plot_cmds) - 3} more)")

    return {
        'assignment': assignment_name,
        'total': total,
        'has_plot': has_plot,
        'unique_implementations': len(unique_plots),
        'color_counts': dict(color_counts),
        'linestyle_counts': dict(linestyle_counts),
    }


def main():
    submissions_dir = Path('./data/student_submissions')

    if not submissions_dir.exists():
        print(f"Error: {submissions_dir} not found")
        print("Run ./tools/fetch_student_submissions.sh first")
        sys.exit(1)

    # Assignments to analyze
    assignments = [
        'plot_docstr',
        'simple_taylor',
        'kerrzelle',
        'einfache_animation',
    ]

    results = []
    for assignment in assignments:
        result = analyze_assignment(assignment, submissions_dir)
        if result:
            results.append(result)

    # Save results
    output_file = submissions_dir / 'analysis_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nAnalysis complete. Results saved to: {output_file}")


if __name__ == '__main__':
    main()
