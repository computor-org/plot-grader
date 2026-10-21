"""Tier 2: Structural heuristics with set-based matching and loose pairing."""

import numpy as np
from typing import Dict, Any
from .models import GradingResult, Tier, ResultStatus
from .tier1 import normalize_color, normalize_linestyle


class Tier2Grader:
    """Tier 2: Structural heuristics (order-independent set matching)."""

    def grade(self, student_data: Dict[str, Any],
             reference_data: Dict[str, Any]) -> GradingResult:
        """
        Grade using structural heuristics.

        Checks:
        - Curve count (exact)
        - Color set matching (order-independent)
        - Linestyle set matching (order-independent)
        - Label/title presence (fuzzy)

        Args:
            student_data: Extracted plot data
            reference_data: Extracted reference data

        Returns:
            GradingResult with tier=TIER_2
        """
        passed_checks = []
        failed_checks = []
        warnings = []
        details = {}

        total_score = 0
        max_score = 0

        # Axis count must match; otherwise structural comparison is meaningless
        if len(student_data['axes']) != len(reference_data['axes']):
            return GradingResult(
                status=ResultStatus.FAIL,
                tier=Tier.TIER_2,
                confidence=0.95,
                score=0.0,
                failed_checks=[
                    f"Expected {len(reference_data['axes'])} axes, got {len(student_data['axes'])}"
                ],
                warnings=warnings,
                tier_2_details={'reason': 'axis_count_mismatch'},
            )

        # Check each axis
        for ax_idx, (student_ax, ref_ax) in enumerate(
            zip(student_data['axes'], reference_data['axes'])
        ):
            # Line count (exact)
            max_score += 10
            if len(student_ax['lines']) == len(ref_ax['lines']):
                total_score += 10
                passed_checks.append(f"Axis {ax_idx}: Correct line count")
            else:
                failed_checks.append(
                    f"Axis {ax_idx}: Expected {len(ref_ax['lines'])} lines, "
                    f"got {len(student_ax['lines'])}"
                )

            # Color set matching (order-independent)
            student_colors = {normalize_color(line['color'])
                            for line in student_ax['lines']}
            ref_colors = {normalize_color(line['color'])
                        for line in ref_ax['lines']}

            max_score += 15
            if student_colors == ref_colors:
                total_score += 15
                passed_checks.append(f"Axis {ax_idx}: Color set matches")
            else:
                missing = ref_colors - student_colors
                extra = student_colors - ref_colors
                failed_checks.append(
                    f"Axis {ax_idx}: Color set mismatch "
                    f"(missing: {missing}, extra: {extra})"
                )

            # Linestyle set matching
            student_styles = {normalize_linestyle(line['linestyle'])
                            for line in student_ax['lines']}
            ref_styles = {normalize_linestyle(line['linestyle'])
                        for line in ref_ax['lines']}

            max_score += 15
            if student_styles == ref_styles:
                total_score += 15
                passed_checks.append(f"Axis {ax_idx}: Linestyle set matches")
            else:
                failed_checks.append(
                    f"Axis {ax_idx}: Linestyle set mismatch"
                )

            # Pairwise loose matching (sorted by mean y) to catch swapped colors/styles/data
            max_score += 60  # 20 color, 20 style, 20 data range
            student_sorted = sorted(student_ax['lines'], key=lambda line: np.mean(line['ydata']))
            ref_sorted = sorted(ref_ax['lines'], key=lambda line: np.mean(line['ydata']))

            pair_color_matches = 0
            pair_style_matches = 0
            pair_data_matches = 0
            for line_idx, (s_line, r_line) in enumerate(zip(student_sorted, ref_sorted)):
                s_color = normalize_color(s_line['color'])
                r_color = normalize_color(r_line['color'])
                s_style = normalize_linestyle(s_line['linestyle'])
                r_style = normalize_linestyle(r_line['linestyle'])
                s_y = np.array(s_line['ydata'])
                r_y = np.array(r_line['ydata'])

                if s_color == r_color:
                    pair_color_matches += 1
                else:
                    failed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Color pairing mismatch ({s_color} vs {r_color})"
                    )

                if s_style == r_style:
                    pair_style_matches += 1
                else:
                    failed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Linestyle pairing mismatch ({s_style} vs {r_style})"
                    )

                # Data range similarity (loose tolerance, structural only)
                if np.allclose([s_y.min(), s_y.max()], [r_y.min(), r_y.max()], rtol=0.05, atol=0.05):
                    pair_data_matches += 1
                else:
                    failed_checks.append(
                        f"Axis {ax_idx}, Line {line_idx}: Data range mismatch"
                    )

            total_score += pair_color_matches * 20 / max(len(ref_sorted), 1)
            total_score += pair_style_matches * 20 / max(len(ref_sorted), 1)
            total_score += pair_data_matches * 20 / max(len(ref_sorted), 1)

            # Labels (presence required)
            max_score += 20  # 10 each label
            if student_ax['xlabel']:
                total_score += 10
                passed_checks.append(f"Axis {ax_idx}: Has xlabel")
            else:
                failed_checks.append(f"Axis {ax_idx}: Missing xlabel")

            if student_ax['ylabel']:
                total_score += 10
                passed_checks.append(f"Axis {ax_idx}: Has ylabel")
            else:
                failed_checks.append(f"Axis {ax_idx}: Missing ylabel")

            # Title (presence required)
            max_score += 10
            if student_ax['title']:
                total_score += 10
                passed_checks.append(f"Axis {ax_idx}: Has title")
            else:
                failed_checks.append(f"Axis {ax_idx}: Missing title")

        # Calculate score and confidence
        score = (total_score / max_score * 100) if max_score > 0 else 0.0

        # Confidence based on score
        if score >= 90:
            confidence = 0.95
        elif score >= 70:
            confidence = 0.85
        else:
            confidence = 0.70

        # Pass only if score is good AND no failed checks (structural heuristics should be conservative)
        status = ResultStatus.PASS if (score >= 70 and not failed_checks) else ResultStatus.FAIL

        details['total_score'] = total_score
        details['max_score'] = max_score
        details['score_percent'] = score

        return GradingResult(
            status=status,
            tier=Tier.TIER_2,
            confidence=confidence,
            score=score,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            warnings=warnings,
            tier_2_details=details,
        )
