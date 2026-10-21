"""Tier 4: AI Visual Assessment with Qwen3-VL-4B (Real Implementation)."""

import io
import json
from typing import Dict, Any, List, Optional
from PIL import Image

from .models import GradingResult, Tier, ResultStatus


class Qwen3VLGrader:
    """
    Real AI grader using Qwen3-VL-4B-8bit with MLX.

    Uses vision-language model to:
    1. Compare reference and student plots visually
    2. Identify specific differences
    3. Generate detailed feedback with coding hints
    """

    def __init__(self, model_path: str = "lmstudio-community/Qwen3-VL-4B-Instruct-MLX-8bit"):
        """
        Initialize Qwen3-VL grader.

        Args:
            model_path: Hugging Face model path for Qwen3-VL MLX variant
        """
        self.model_path = model_path
        self.model = None
        self.processor = None
        self.config = None
        self.call_count = 0
        self._load_model()

    def _load_model(self):
        """Load the Qwen3-VL model using mlx-vlm."""
        try:
            from mlx_vlm import load, generate
            from mlx_vlm.prompt_utils import apply_chat_template
            from mlx_vlm.utils import load_config

            print(f"Loading Qwen3-VL model: {self.model_path}")
            print("(First run may take time to download ~2.5GB)")

            self.model, self.processor = load(self.model_path)
            self.config = load_config(self.model_path)

            # Store generate function
            self._generate = generate
            self._apply_chat_template = apply_chat_template

            print("Qwen3-VL model loaded successfully")

        except ImportError as e:
            raise ImportError(
                "mlx-vlm not installed. Install with: pip install mlx-vlm"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load Qwen3-VL model: {e}") from e

    def grade(
        self,
        student_data: Dict[str, Any],
        reference_data: Dict[str, Any],
        tier_results: Optional[List[GradingResult]] = None,
        assignment_requirements: Optional[str] = None,
    ) -> GradingResult:
        """
        Grade submission using Qwen3-VL visual analysis.

        Args:
            student_data: Student plot data (must include 'execution' with figure)
            reference_data: Reference plot data (must include 'execution' with figure)
            tier_results: Results from previous tiers (for context)
            assignment_requirements: Text description of assignment

        Returns:
            GradingResult with AI-generated feedback
        """
        self.call_count += 1

        # Get images from execution data
        from plot_grader.executor import render_figure_to_bytes

        student_fig = student_data.get('execution', {}).get('figure')
        reference_fig = reference_data.get('execution', {}).get('figure')

        if not student_fig or not reference_fig:
            return GradingResult(
                status=ResultStatus.ERROR,
                tier=Tier.TIER_4,
                confidence=0.0,
                score=0.0,
                error_message="Missing figure data for AI grading",
                execution_time_ms=0.0,
            )

        # Render to images
        student_img_bytes = render_figure_to_bytes(student_fig)
        reference_img_bytes = render_figure_to_bytes(reference_fig)

        student_img = Image.open(io.BytesIO(student_img_bytes))
        reference_img = Image.open(io.BytesIO(reference_img_bytes))

        # Grade using tier context if available
        result = self._grade_plots(student_img, reference_img, tier_results)
        return result

    def _grade_plots(
        self,
        student_img: Image.Image,
        reference_img: Image.Image,
        tier_results: Optional[List[GradingResult]] = None,
    ) -> GradingResult:
        """
        Generate AI feedback using tier context.

        If tier_results provided: Use tier findings + images to generate helpful hints
        Otherwise: Do independent visual comparison (fallback)
        """
        import time
        start_time = time.time()

        # If we have tier results, use them to guide AI feedback
        if tier_results and len(tier_results) > 0:
            latest_tier = tier_results[-1]

            # Build context from tier findings
            context_parts = []
            if latest_tier.passed_checks:
                context_parts.append("PASSED CHECKS:")
                for check in latest_tier.passed_checks:
                    context_parts.append(f"  PASS: {check}")

            if latest_tier.failed_checks:
                context_parts.append("\nFAILED CHECKS:")
                for check in latest_tier.failed_checks:
                    context_parts.append(f"  FAIL: {check}")

            context = "\n".join(context_parts)

            # Ask AI to provide helpful feedback based on tier findings
            prompt = f"""You are helping a student fix their matplotlib plot.

AUTOMATED TEST RESULTS:
{context}

The student's plot has issues. Looking at their plot, provide helpful feedback in JSON format.

Respond with JSON ONLY. No other text.

JSON format:
{{
  "visual_assessment": "what you see in the plot",
  "issues": ["specific issue 1", "specific issue 2"],
  "hint": "How to fix using matplotlib (code examples if helpful)"
}}"""

            response = self._query_model(prompt, [student_img])

            # Parse AI feedback
            try:
                json_str = response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0].strip()

                data = json.loads(json_str)
                visual = data.get("visual_assessment", "")
                issues = data.get("issues", [])
                hint = data.get("hint", "")

            except (json.JSONDecodeError, IndexError):
                visual = response[:200]
                issues = []
                hint = ""

            # Use tier result's pass/fail, just add AI feedback
            feedback_parts = ["AI Visual Feedback:"]
            if visual:
                feedback_parts.append(f"What AI sees: {visual}")
            if issues:
                feedback_parts.append("\nAI identified issues:")
                for issue in issues:
                    feedback_parts.append(f"- {issue}")
            if hint:
                feedback_parts.append(f"\nAI Hint:\n{hint}")

            feedback = "\n".join(feedback_parts)
            execution_time_ms = (time.time() - start_time) * 1000

            # Return tier result with AI feedback added
            return GradingResult(
                status=latest_tier.status,
                tier=latest_tier.tier,
                confidence=latest_tier.confidence,
                score=latest_tier.score,
                passed_checks=latest_tier.passed_checks + ([feedback] if latest_tier.passed else []),
                failed_checks=latest_tier.failed_checks + ([feedback] if not latest_tier.passed else []),
                warnings=latest_tier.warnings + [f"AI feedback generated (call #{self.call_count})"],
                error_message=latest_tier.error_message,
                execution_time_ms=latest_tier.execution_time_ms + execution_time_ms,
            )

        else:
            # Fallback: Independent visual assessment (when no tier context)
            ref_desc = self._query_model(
                "Describe this matplotlib plot: curves, colors, linestyles, labels, title.",
                [reference_img]
            )
            student_desc = self._query_model(
                "Describe this matplotlib plot: curves, colors, linestyles, labels, title.",
                [student_img]
            )

            passed = ref_desc.lower() == student_desc.lower()
            feedback = f"AI Visual: Ref={ref_desc[:100]}... Student={student_desc[:100]}..."
            execution_time_ms = (time.time() - start_time) * 1000

            return GradingResult(
                status=ResultStatus.PASS if passed else ResultStatus.FAIL,
                tier=Tier.TIER_4,
                confidence=0.60,
                score=100 if passed else 0,
                passed_checks=[feedback] if passed else [],
                failed_checks=[] if passed else [feedback],
                warnings=[f"AI independent assessment (call #{self.call_count})"],
                error_message=None,
                execution_time_ms=execution_time_ms,
            )

    def _query_model(self, prompt: str, images: List[Image.Image]) -> str:
        """
        Query Qwen3-VL model with prompt and images.

        Args:
            prompt: Text prompt
            images: List of PIL Images

        Returns:
            Model response text
        """
        try:
            # Apply chat template
            formatted_prompt = self._apply_chat_template(
                self.processor,
                self.config,
                prompt,
                num_images=len(images)
            )

            # Generate response (conservative settings to avoid GPU timeout)
            output = self._generate(
                self.model,
                self.processor,
                formatted_prompt,
                images,
                max_tokens=250,  # Enough for JSON response
                temperature=0.1,  # Low temperature for deterministic JSON
                verbose=False
            )

            # Extract text from GenerationResult
            if hasattr(output, 'text'):
                return output.text
            else:
                return str(output)

        except Exception as e:
            return f"Error querying model: {e}"

    def get_stats(self) -> Dict[str, Any]:
        """Get AI grader statistics."""
        return {
            "total_calls": self.call_count,
            "mode": "real",
            "model": self.model_path,
            "backend": "MLX (Apple Silicon optimized)",
        }
