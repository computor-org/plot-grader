"""Main grader orchestrating multi-tier validation."""

import time
from pathlib import Path
from typing import List
from .executor import execute_plot_code, extract_plot_data, render_figure_to_bytes
from .tier1 import Tier1Grader
from .tier2 import Tier2Grader
from .tier3 import Tier3Grader
from .models import GradingResult, ResultStatus

# Try to import real AI grader (optional)
try:
    from .tier4_real import Qwen3VLGrader
    REAL_AI_AVAILABLE = True
except ImportError:
    REAL_AI_AVAILABLE = False
    Qwen3VLGrader = None


class PlotGrader:
    """
    Multi-tier plot grader.

    Attempts tiers in order until confident result:
    1. Tier 1: Smart hardcoded (order-independent, normalized)
    2. Tier 2: Structural heuristics (set-based matching)
    3. Tier 3: Visual similarity (SSIM, histograms)
    4. Tier 4: vision-language model (optional)
    """

    def __init__(self,
                 tier1_enabled: bool = True,
                 tier2_enabled: bool = True,
                 tier3_enabled: bool = True,
                 tier4_enabled: bool = True,
                 use_real_ai: bool = False,
                 tier4_grader=None,
                 confidence_threshold: float = 0.90,
                 enable_ai_feedback: bool = True,
                 test_mode: bool = False):
        """
        Initialize multi-tier grader.

        Args:
            tier1_enabled: Enable Tier 1 (smart hardcoded)
            tier2_enabled: Enable Tier 2 (structural heuristics)
            tier3_enabled: Enable Tier 3 (OpenCV visual)
            tier4_enabled: Enable Tier 4 (AI feedback)
            use_real_ai: Enable Tier 4 with the Qwen3-VL model (mlx-vlm)
            tier4_grader: Tier 4 object with a grade() method, e.g.
                judges.JudgeTier4; takes precedence over use_real_ai
            confidence_threshold: Minimum confidence to stop tier fallthrough
            enable_ai_feedback: Add AI feedback even when early tier resolves
            test_mode: Run ALL tiers regardless of confidence (for testing/comparison)
        """
        self.tier1_grader = Tier1Grader() if tier1_enabled else None
        self.tier2_grader = Tier2Grader() if tier2_enabled else None
        self.tier3_grader = Tier3Grader() if tier3_enabled else None

        # Tier 4 runs only with a real vision model; there is no mock.
        self.tier4_grader = tier4_grader if tier4_enabled else None
        if tier4_enabled and tier4_grader is None and use_real_ai:
            if not REAL_AI_AVAILABLE:
                raise RuntimeError(
                    "Real AI grader requested but not available. "
                    "Install mlx-vlm: uv sync --extra mlx"
                )
            self.tier4_grader = Qwen3VLGrader()

        self.confidence_threshold = confidence_threshold
        self.enable_ai_feedback = enable_ai_feedback
        self.use_real_ai = use_real_ai
        self.test_mode = test_mode

        if test_mode:
            print("TEST MODE: All tiers will run regardless of confidence")

    def _add_ai_feedback(self, base_result, student_data, reference_data, tier_results):
        """Attach AI feedback warnings using configured AI grader.

        Returns the base_result potentially augmented with AI-generated
        context. The AI grader itself is invoked only when enabled.
        """
        if not (self.enable_ai_feedback and self.tier4_grader):
            return base_result

        ai_result = self.tier4_grader.grade(
            student_data,
            reference_data,
            tier_results=tier_results,
            assignment_requirements=None,
        )

        if ai_result.passed_checks:
            base_result.warnings.extend(["AI: " + c for c in ai_result.passed_checks])
        if ai_result.failed_checks:
            base_result.warnings.extend(["AI: " + c for c in ai_result.failed_checks])

        return base_result

    def grade_submission(self,
                        submission_path: Path,
                        reference_path: Path) -> GradingResult:
        """
        Grade a student submission against reference solution.

        Args:
            submission_path: Path to student's Python file
            reference_path: Path to reference Python file

        Returns:
            GradingResult indicating which tier resolved and outcome
        """
        start_time = time.time()

        # Execute both codes
        student_exec = execute_plot_code(submission_path)
        if not student_exec['success']:
            return GradingResult(
                status=ResultStatus.ERROR,
                tier=None,
                confidence=0.0,
                score=0.0,
                error_message=f"Student code execution failed: {student_exec['error']}",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        reference_exec = execute_plot_code(reference_path)
        if not reference_exec['success']:
            return GradingResult(
                status=ResultStatus.ERROR,
                tier=None,
                confidence=0.0,
                score=0.0,
                error_message=f"Reference code execution failed: {reference_exec['error']}",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        # Extract plot data
        student_data = extract_plot_data(student_exec['figure'])
        reference_data = extract_plot_data(reference_exec['figure'])

        # Store references for AI tier
        student_data['execution'] = student_exec
        reference_data['execution'] = reference_exec

        # Collect tier results for AI context
        tier_results: List[GradingResult] = []

        # Tier 1: Smart hardcoded checks
        if self.tier1_grader:
            result = self.tier1_grader.grade(student_data, reference_data)
            result.execution_time_ms = (time.time() - start_time) * 1000
            tier_results.append(result)

            if result.passed and result.confidence >= self.confidence_threshold and not self.test_mode:
                return self._add_ai_feedback(result, student_data, reference_data, tier_results)

        # Tier 2: Structural heuristics
        if self.tier2_grader:
            result = self.tier2_grader.grade(student_data, reference_data)
            result.execution_time_ms = (time.time() - start_time) * 1000
            tier_results.append(result)

            if result.passed and result.confidence >= self.confidence_threshold and not self.test_mode:
                return self._add_ai_feedback(result, student_data, reference_data, tier_results)

        # Tier 3: Visual similarity
        if self.tier3_grader:
            # Render both figures to images
            student_img = render_figure_to_bytes(student_exec['figure'])
            reference_img = render_figure_to_bytes(reference_exec['figure'])

            result = self.tier3_grader.grade(student_img, reference_img)
            result.execution_time_ms = (time.time() - start_time) * 1000
            tier_results.append(result)

            # Don't return yet - let AI tier have final say
            if result.passed and result.confidence >= self.confidence_threshold and not self.tier4_grader and not self.test_mode:
                return result

        # Tier 4: AI assessment with full context
        if self.tier4_grader:
            ai_result = self.tier4_grader.grade(
                student_data,
                reference_data,
                tier_results=tier_results if tier_results else None,
                assignment_requirements=None
            )
            ai_result.execution_time_ms = (time.time() - start_time) * 1000

            # In test mode, attach all tier results for comparison
            if self.test_mode and tier_results:
                ai_result.warnings.insert(0, f"TEST MODE: Collected {len(tier_results)} tier results for comparison")
                for i, tr in enumerate(tier_results, 1):
                    tier_name = tr.tier.value if tr.tier else f"Tier {i}"
                    ai_result.warnings.append(
                        f"{tier_name}: {'PASS' if tr.passed else 'FAIL'} "
                        f"(confidence: {tr.confidence:.2f}, score: {tr.score:.0f})"
                    )

            return ai_result

        # Fallback: return best tier result
        if tier_results:
            best = tier_results[-1]
            if self.test_mode:
                best.warnings.insert(0, f"TEST MODE: Collected {len(tier_results)} tier results")
            return best

        # No tiers enabled
        return GradingResult(
            status=ResultStatus.ERROR,
            tier=None,
            confidence=0.0,
            score=0.0,
            error_message="No grading tiers enabled",
            execution_time_ms=(time.time() - start_time) * 1000,
        )
