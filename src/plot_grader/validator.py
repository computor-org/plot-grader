"""Validation harness with tier fallthrough tracking."""

from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, field
from collections import Counter
from .grader import PlotGrader
from .executor import execute_plot_code, render_figure_to_bytes


@dataclass
class ValidationRun:
    """Results from validating all submissions."""
    reference_path: Path
    submissions: List[Dict[str, Any]] = field(default_factory=list)
    tier_distribution: Dict[str, int] = field(default_factory=dict)
    pass_rate: float = 0.0
    false_negative_rate: float = 0.0
    false_positive_rate: float = 0.0

    def add_result(self, submission_name: str, submission_path: Path,
                   expected_pass: bool, result, rendered_imgs: Dict[str, bytes]):
        """Add a submission result."""
        self.submissions.append({
            'name': submission_name,
            'path': str(submission_path),
            'expected_pass': expected_pass,
            'actual_pass': result.passed,
            'tier': result.tier.value if result.tier else 'ERROR',
            'confidence': result.confidence,
            'score': result.score,
            'execution_time_ms': result.execution_time_ms,
            'passed_checks': result.passed_checks,
            'failed_checks': result.failed_checks,
            'warnings': result.warnings,
            'error_message': result.error_message,
            'images': rendered_imgs,
        })

    def compute_statistics(self):
        """Compute tier distribution and accuracy metrics."""
        # Tier distribution
        tier_counts = Counter(s['tier'] for s in self.submissions)
        self.tier_distribution = dict(tier_counts)

        # Accuracy metrics
        total = len(self.submissions)
        if total == 0:
            return

        passed = sum(1 for s in self.submissions if s['actual_pass'])
        self.pass_rate = passed / total

        # False negatives: expected pass but failed
        false_negatives = sum(1 for s in self.submissions
                            if s['expected_pass'] and not s['actual_pass'])
        positive_total = sum(1 for s in self.submissions if s['expected_pass'])
        self.false_negative_rate = (false_negatives / positive_total
                                   if positive_total > 0 else 0.0)

        # False positives: expected fail but passed
        false_positives = sum(1 for s in self.submissions
                            if not s['expected_pass'] and s['actual_pass'])
        negative_total = sum(1 for s in self.submissions if not s['expected_pass'])
        self.false_positive_rate = (false_positives / negative_total
                                   if negative_total > 0 else 0.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'reference_path': str(self.reference_path),
            'submissions': self.submissions,
            'tier_distribution': self.tier_distribution,
            'pass_rate': self.pass_rate,
            'false_negative_rate': self.false_negative_rate,
            'false_positive_rate': self.false_positive_rate,
        }


class Validator:
    """Run validation across multiple submissions and track results."""

    def __init__(self, use_real_ai: bool = False, test_mode: bool = False,
                 tier4_grader=None):
        self.grader = PlotGrader(
            use_real_ai=use_real_ai,
            tier4_grader=tier4_grader,
            enable_ai_feedback=use_real_ai,
            test_mode=test_mode
        )

    def run_validation(self,
                      reference_path: Path,
                      positive_variants: List[Path],
                      negative_variants: List[Path]) -> ValidationRun:
        """
        Run validation on stress test variants.

        Args:
            reference_path: Path to reference solution
            positive_variants: Paths to variants that should pass
            negative_variants: Paths to variants that should fail

        Returns:
            ValidationRun with all results and statistics
        """
        validation = ValidationRun(reference_path=reference_path)

        # Render reference once
        ref_exec = execute_plot_code(reference_path)
        ref_img = None
        if ref_exec['success']:
            ref_img = render_figure_to_bytes(ref_exec['figure'])

        # Grade positive variants (should pass)
        for variant_path in positive_variants:
            result = self.grader.grade_submission(variant_path, reference_path)

            # Render student submission
            student_exec = execute_plot_code(variant_path)
            student_img = None
            if student_exec['success']:
                student_img = render_figure_to_bytes(student_exec['figure'])

            rendered_imgs = {
                'reference': ref_img,
                'submission': student_img,
            }

            validation.add_result(
                submission_name=variant_path.name,
                submission_path=variant_path,
                expected_pass=True,
                result=result,
                rendered_imgs=rendered_imgs,
            )

        # Grade negative variants (should fail)
        for variant_path in negative_variants:
            result = self.grader.grade_submission(variant_path, reference_path)

            # Render student submission
            student_exec = execute_plot_code(variant_path)
            student_img = None
            if student_exec['success']:
                student_img = render_figure_to_bytes(student_exec['figure'])

            rendered_imgs = {
                'reference': ref_img,
                'submission': student_img,
            }

            validation.add_result(
                submission_name=variant_path.name,
                submission_path=variant_path,
                expected_pass=False,
                result=result,
                rendered_imgs=rendered_imgs,
            )

        validation.compute_statistics()
        return validation
