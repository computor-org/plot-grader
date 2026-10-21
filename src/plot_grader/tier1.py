"""Tier 1: Smart hardcoded checks with normalization."""

import numpy as np
import matplotlib.colors as mcolors
from typing import Tuple, Dict, Any
from .models import GradingResult, Tier, ResultStatus


# Color normalization mappings
COLOR_ALIASES = {
    'r': 'red',
    'g': 'green',
    'b': 'blue',
    'c': 'cyan',
    'm': 'magenta',
    'y': 'yellow',
    'k': 'black',
    'w': 'white',
}

# Linestyle normalization
LINESTYLE_ALIASES = {
    '-': 'solid',
    '--': 'dashed',
    '-.': 'dashdot',
    ':': 'dotted',
    'solid': 'solid',
    'dashed': 'dashed',
    'dashdot': 'dashdot',
    'dotted': 'dotted',
}


def normalize_color(color: Any) -> Tuple[float, float, float]:
    """
    Normalize color to RGB tuple (0-1 range).

    Handles:
    - Single letter: 'r' -> (1.0, 0, 0)
    - Named colors: 'red' -> (1.0, 0, 0)
    - Hex: '#FF0000' -> (1.0, 0, 0)
    - RGB tuple: (255, 0, 0) -> (1.0, 0, 0)
    - RGB float: (1.0, 0.0, 0.0) -> (1.0, 0, 0)
    """
    if isinstance(color, str):
        # Handle single-letter aliases
        if color in COLOR_ALIASES:
            color = COLOR_ALIASES[color]

        # Convert named color or hex to RGB
        try:
            rgb = mcolors.to_rgb(color)
            return tuple(float(c) for c in rgb)
        except ValueError:
            return (0.0, 0.0, 0.0)  # Default to black if invalid

    elif isinstance(color, (tuple, list)):
        # Already RGB/RGBA
        rgb = tuple(color[:3])
        # Normalize to 0-1 range if needed
        if any(c > 1.0 for c in rgb):
            return tuple(c / 255.0 for c in rgb)
        return tuple(float(c) for c in rgb)

    # Fallback
    return (0.0, 0.0, 0.0)


def normalize_linestyle(linestyle: Any) -> str:
    """
    Normalize linestyle to canonical name.

    Returns: 'solid', 'dashed', 'dashdot', or 'dotted'
    """
    if isinstance(linestyle, str):
        return LINESTYLE_ALIASES.get(linestyle, linestyle)

    # Matplotlib also accepts tuples like (0, (5, 5)) for dashed
    if isinstance(linestyle, tuple):
        offset, onoffseq = linestyle
        if not onoffseq:
            return 'solid'
        # Heuristic mapping based on pattern
        if len(onoffseq) == 2:
            if onoffseq[0] > onoffseq[1]:
                return 'dashed'
            else:
                return 'dotted'
        return 'dashdot'

    return 'solid'  # Default


def colors_match(color1: Tuple[float, float, float],
                 color2: Tuple[float, float, float],
                 tolerance: float = 0.01) -> bool:
    """Check if two RGB colors match within tolerance."""
    return all(abs(c1 - c2) < tolerance for c1, c2 in zip(color1, color2))


def arrays_match(arr1: np.ndarray, arr2: np.ndarray,
                 rtol: float = 1e-12, atol: float = 0.0001) -> bool:
    """Check if two numpy arrays match within tolerance."""
    try:
        np.testing.assert_allclose(arr1, arr2, rtol=rtol, atol=atol)
        return True
    except AssertionError:
        return False


class Tier1Grader:
    """Tier 1: Smart hardcoded checks with order-independent normalization."""

    def __init__(self, rtol: float = 1e-12, atol: float = 0.0001):
        self.rtol = rtol
        self.atol = atol

    def grade(self, student_data: Dict[str, Any],
             reference_data: Dict[str, Any]) -> GradingResult:
        """
        Grade submission using Tier 1 normalized hardcoded checks.

        Args:
            student_data: Extracted plot data from student submission
            reference_data: Extracted plot data from reference solution

        Returns:
            GradingResult with tier=TIER_1
        """
        passed_checks = []
        failed_checks = []
        details = {}

        # Check number of axes
        if len(student_data['axes']) != len(reference_data['axes']):
            return GradingResult(
                status=ResultStatus.FAIL,
                tier=Tier.TIER_1,
                confidence=1.0,
                score=0.0,
                failed_checks=[f"Expected {len(reference_data['axes'])} axes, "
                             f"got {len(student_data['axes'])}"],
                tier_1_details=details,
            )

        # For each axis
        for ax_idx, (student_ax, ref_ax) in enumerate(
            zip(student_data['axes'], reference_data['axes'])
        ):
            # Check number of lines
            n_student_lines = len(student_ax['lines'])
            n_ref_lines = len(ref_ax['lines'])

            if n_student_lines != n_ref_lines:
                failed_checks.append(
                    f"Axis {ax_idx}: Expected {n_ref_lines} lines, got {n_student_lines}"
                )
                continue

            passed_checks.append(f"Axis {ax_idx}: Correct number of lines ({n_ref_lines})")

            # Extract and normalize all lines
            student_lines_norm = []
            for line in student_ax['lines']:
                student_lines_norm.append({
                    'color': normalize_color(line['color']),
                    'linestyle': normalize_linestyle(line['linestyle']),
                    'xdata': np.array(line['xdata']),
                    'ydata': np.array(line['ydata']),
                })

            ref_lines_norm = []
            for line in ref_ax['lines']:
                ref_lines_norm.append({
                    'color': normalize_color(line['color']),
                    'linestyle': normalize_linestyle(line['linestyle']),
                    'xdata': np.array(line['xdata']),
                    'ydata': np.array(line['ydata']),
                })

            # Sort lines by canonical property (mean y-value) for order-independence
            student_lines_sorted = sorted(student_lines_norm,
                                         key=lambda line: float(line['ydata'].mean()))
            ref_lines_sorted = sorted(ref_lines_norm,
                                     key=lambda line: float(line['ydata'].mean()))

            # Compare sorted lines
            for line_idx, (s_line, r_line) in enumerate(
                zip(student_lines_sorted, ref_lines_sorted)
            ):
                # Color check
                if not colors_match(s_line['color'], r_line['color']):
                    failed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Color mismatch "
                        f"({s_line['color']} vs {r_line['color']})"
                    )
                else:
                    passed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Color match"
                    )

                # Linestyle check
                if s_line['linestyle'] != r_line['linestyle']:
                    failed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Linestyle mismatch "
                        f"({s_line['linestyle']} vs {r_line['linestyle']})"
                    )
                else:
                    passed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Linestyle match"
                    )

                # Data check
                if not (arrays_match(s_line['xdata'], r_line['xdata'], self.rtol, self.atol) and
                       arrays_match(s_line['ydata'], r_line['ydata'], self.rtol, self.atol)):
                    failed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Data mismatch"
                    )
                else:
                    passed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Data match"
                    )

            # Check labels and title
            if student_ax['xlabel'] != ref_ax['xlabel']:
                failed_checks.append(f"Axis {ax_idx}: xlabel mismatch "
                                   f"({student_ax['xlabel']!r} vs {ref_ax['xlabel']!r})")
            else:
                passed_checks.append(f"Axis {ax_idx}: xlabel match")

            if student_ax['ylabel'] != ref_ax['ylabel']:
                failed_checks.append(f"Axis {ax_idx}: ylabel mismatch "
                                   f"({student_ax['ylabel']!r} vs {ref_ax['ylabel']!r})")
            else:
                passed_checks.append(f"Axis {ax_idx}: ylabel match")

            if student_ax['title'] != ref_ax['title']:
                failed_checks.append(f"Axis {ax_idx}: title mismatch "
                                   f"({student_ax['title']!r} vs {ref_ax['title']!r})")
            else:
                passed_checks.append(f"Axis {ax_idx}: title match")

        # Determine overall result
        if failed_checks:
            status = ResultStatus.FAIL
            score = 0.0
        else:
            status = ResultStatus.PASS
            score = 100.0

        details['passed_checks_count'] = len(passed_checks)
        details['failed_checks_count'] = len(failed_checks)

        return GradingResult(
            status=status,
            tier=Tier.TIER_1,
            confidence=1.0,  # Tier 1 is deterministic
            score=score,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            tier_1_details=details,
        )
