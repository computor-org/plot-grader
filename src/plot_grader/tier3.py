"""Tier 3: OpenCV visual similarity comparison."""

import cv2
import numpy as np
from PIL import Image
import io
from skimage.metrics import structural_similarity as ssim
from .models import GradingResult, Tier, ResultStatus


class Tier3Grader:
    """Tier 3: Computer vision similarity (SSIM, histograms, edges)."""

    def __init__(self, ssim_threshold: float = 0.85):
        self.ssim_threshold = ssim_threshold

    def grade(self, student_img_bytes: bytes,
             reference_img_bytes: bytes) -> GradingResult:
        """
        Grade using visual similarity metrics.

        Args:
            student_img_bytes: PNG bytes of student plot
            reference_img_bytes: PNG bytes of reference plot

        Returns:
            GradingResult with tier=TIER_3
        """
        passed_checks = []
        failed_checks = []
        details = {}

        try:
            # Load images
            student_img = self._load_image(student_img_bytes)
            reference_img = self._load_image(reference_img_bytes)

            # Ensure same size
            if student_img.shape != reference_img.shape:
                # Resize student to match reference
                student_img = cv2.resize(student_img,
                                        (reference_img.shape[1], reference_img.shape[0]))

            # 1. SSIM (Structural Similarity Index)
            ssim_score = ssim(reference_img, student_img, channel_axis=2)
            details['ssim'] = float(ssim_score)

            if ssim_score >= self.ssim_threshold:
                passed_checks.append(f"SSIM: {ssim_score:.3f} (>= {self.ssim_threshold})")
            else:
                failed_checks.append(f"SSIM: {ssim_score:.3f} (< {self.ssim_threshold})")

            # 2. Color histogram comparison
            hist_similarity = self._compare_histograms(student_img, reference_img)
            details['histogram_similarity'] = float(hist_similarity)

            if hist_similarity >= 0.8:
                passed_checks.append(f"Histogram similarity: {hist_similarity:.3f}")
            else:
                failed_checks.append(f"Histogram similarity: {hist_similarity:.3f} (low)")

            # 3. Edge detection similarity
            edge_similarity = self._compare_edges(student_img, reference_img)
            details['edge_similarity'] = float(edge_similarity)

            if edge_similarity >= 0.7:
                passed_checks.append(f"Edge similarity: {edge_similarity:.3f}")
            else:
                failed_checks.append(f"Edge similarity: {edge_similarity:.3f} (low)")

            # Calculate overall score
            # Weighted combination
            score = (
                ssim_score * 50 +          # SSIM is most important
                hist_similarity * 30 +     # Color distribution
                edge_similarity * 20       # Shape similarity
            )

            # Confidence based on SSIM
            if ssim_score >= 0.95:
                confidence = 0.90
            elif ssim_score >= 0.85:
                confidence = 0.80
            else:
                confidence = 0.60

            # Pass if overall score >= 70
            status = ResultStatus.PASS if score >= 70 else ResultStatus.FAIL

            return GradingResult(
                status=status,
                tier=Tier.TIER_3,
                confidence=confidence,
                score=score,
                passed_checks=passed_checks,
                failed_checks=failed_checks,
                tier_3_details=details,
            )

        except Exception as e:
            return GradingResult(
                status=ResultStatus.ERROR,
                tier=Tier.TIER_3,
                confidence=0.0,
                score=0.0,
                failed_checks=[f"Visual comparison error: {str(e)}"],
                tier_3_details=details,
                error_message=str(e),
            )

    def _load_image(self, img_bytes: bytes) -> np.ndarray:
        """Load image from bytes to RGB numpy array."""
        img = Image.open(io.BytesIO(img_bytes))
        return np.array(img.convert('RGB'))

    def _compare_histograms(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Compare color histograms of two images."""
        # Calculate histograms for each channel
        similarity_scores = []

        for channel in range(3):  # RGB
            hist1 = cv2.calcHist([img1], [channel], None, [256], [0, 256])
            hist2 = cv2.calcHist([img2], [channel], None, [256], [0, 256])

            # Normalize
            hist1 = cv2.normalize(hist1, hist1).flatten()
            hist2 = cv2.normalize(hist2, hist2).flatten()

            # Compare using correlation
            similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            similarity_scores.append(similarity)

        return float(np.mean(similarity_scores))

    def _compare_edges(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Compare edge maps of two images."""
        # Convert to grayscale
        gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)

        # Detect edges
        edges1 = cv2.Canny(gray1, 50, 150)
        edges2 = cv2.Canny(gray2, 50, 150)

        # Calculate similarity (intersection over union)
        intersection = np.logical_and(edges1, edges2).sum()
        union = np.logical_or(edges1, edges2).sum()

        if union == 0:
            return 1.0  # Both empty

        return float(intersection / union)
