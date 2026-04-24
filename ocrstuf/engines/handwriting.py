"""
Handwriting Detection & Recognition Engine
- Classifier: determines if a chunk image is handwritten vs typed
- Recognizer: TrOCR-based handwriting OCR with line segmentation
"""
from __future__ import annotations

import cv2
import numpy as np
import torch
from PIL import Image
from typing import List, Tuple, Optional
from dataclasses import dataclass
from config.settings import settings
from utils.types import OCRResult
from core.logger import get_logger

logger = get_logger(__name__)

# ── Lazy model loading ─────────────────────────────────────────────────────────
_trocr_processor = None
_trocr_model = None
_device = None


def _get_device() -> torch.device:
    global _device
    if _device is None:
        if settings.handwriting_use_gpu and torch.cuda.is_available():
            _device = torch.device("cuda")
            logger.info("Handwriting engine using GPU (CUDA)")
        else:
            _device = torch.device("cpu")
            logger.info("Handwriting engine using CPU")
    return _device


def _load_trocr():
    """Lazy-load TrOCR model and processor (only on first use)."""
    global _trocr_processor, _trocr_model
    if _trocr_processor is not None:
        return _trocr_processor, _trocr_model

    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    model_name = settings.handwriting_model
    cache_dir = str(settings.cache_dir / "handwriting")
    logger.info(f"Loading TrOCR model: {model_name}")

    _trocr_processor = TrOCRProcessor.from_pretrained(model_name, cache_dir=cache_dir)
    _trocr_model = VisionEncoderDecoderModel.from_pretrained(model_name, cache_dir=cache_dir)
    _trocr_model.to(_get_device())
    _trocr_model.eval()

    logger.info(f"TrOCR model loaded on {_get_device()}")
    return _trocr_processor, _trocr_model


# ── Handwriting Classifier ─────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    is_handwritten: bool
    confidence: float
    features: dict


class HandwritingClassifier:
    """
    Lightweight heuristic classifier that distinguishes handwritten from typed text.
    Uses stroke width variance, contour irregularity, and spacing analysis.
    Fast enough for RPi5 — no ML model required.
    """

    def __init__(self):
        self.min_confidence = settings.handwriting_classifier_threshold

    def classify(self, image_bgr: np.ndarray) -> ClassificationResult:
        """Analyze a chunk image and classify as handwritten or typed."""
        try:
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

            stroke_score = self._stroke_width_variance(gray)
            contour_score = self._contour_irregularity(gray)
            spacing_score = self._spacing_irregularity(gray)
            baseline_score = self._baseline_variation(gray)
            angle_score = self._stroke_angle_diversity(gray)

            # Weighted combination
            # Handwriting: high variance in all metrics
            # Typed text: low variance, regular patterns
            handwriting_score = (
                stroke_score * 0.25 +
                contour_score * 0.20 +
                spacing_score * 0.20 +
                baseline_score * 0.20 +
                angle_score * 0.15
            )

            is_handwritten = handwriting_score >= self.min_confidence
            features = {
                "stroke_width_variance": round(stroke_score, 3),
                "contour_irregularity": round(contour_score, 3),
                "spacing_irregularity": round(spacing_score, 3),
                "baseline_variation": round(baseline_score, 3),
                "stroke_angle_diversity": round(angle_score, 3),
                "combined_score": round(handwriting_score, 3),
            }

            return ClassificationResult(
                is_handwritten=is_handwritten,
                confidence=handwriting_score,
                features=features,
            )

        except Exception as e:
            logger.warning(f"Handwriting classification failed: {e}")
            return ClassificationResult(is_handwritten=False, confidence=0.0, features={})

    def _stroke_width_variance(self, gray: np.ndarray) -> float:
        """Handwriting has more variable stroke widths than typed text."""
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
        )
        dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
        stroke_widths = dist_transform[dist_transform > 0]
        if len(stroke_widths) < 10:
            return 0.0

        variance = float(np.std(stroke_widths) / (np.mean(stroke_widths) + 1e-6))
        # Normalize: typed text ~0.2-0.4, handwriting ~0.5-1.0+
        return min(variance / 1.0, 1.0)

    def _contour_irregularity(self, gray: np.ndarray) -> float:
        """Handwritten characters have more irregular contours."""
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
        )
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) < 3:
            return 0.0

        irregularities = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 20:
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue
            # Circularity: perfect circle = 1.0, irregular shapes < 1.0
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            irregularities.append(1.0 - circularity)

        if not irregularities:
            return 0.0

        # Higher variance in irregularity → more likely handwritten
        mean_irreg = float(np.mean(irregularities))
        std_irreg = float(np.std(irregularities))
        score = (mean_irreg * 0.5 + std_irreg * 0.5)
        return min(score / 0.5, 1.0)

    def _spacing_irregularity(self, gray: np.ndarray) -> float:
        """Handwriting has less regular character/word spacing."""
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
        )
        # Project vertically to find gaps
        projection = np.sum(binary, axis=0)
        threshold = np.max(projection) * 0.05

        # Find gap widths (spaces between characters)
        in_gap = False
        gap_widths = []
        current_gap = 0
        for val in projection:
            if val < threshold:
                current_gap += 1
                in_gap = True
            else:
                if in_gap and current_gap > 2:
                    gap_widths.append(current_gap)
                current_gap = 0
                in_gap = False

        if len(gap_widths) < 3:
            return 0.0

        gap_cv = float(np.std(gap_widths) / (np.mean(gap_widths) + 1e-6))
        # Typed text: CV ~0.1-0.3, Handwriting: CV ~0.4-1.0+
        return min(gap_cv / 1.0, 1.0)

    def _baseline_variation(self, gray: np.ndarray) -> float:
        """Handwriting drifts from the baseline; typed text stays straight."""
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
        )
        h, w = binary.shape
        if w < 20:
            return 0.0

        # Split image into vertical strips and find the baseline (lowest ink) in each
        num_strips = min(20, w // 10)
        strip_width = w // num_strips
        baselines = []

        for i in range(num_strips):
            strip = binary[:, i * strip_width:(i + 1) * strip_width]
            projection = np.sum(strip, axis=1)
            ink_rows = np.where(projection > 0)[0]
            if len(ink_rows) > 0:
                baselines.append(float(ink_rows[-1]))  # Bottom of ink

        if len(baselines) < 5:
            return 0.0

        baseline_cv = float(np.std(baselines) / (np.mean(baselines) + 1e-6))
        # Typed: CV ~0.01-0.05, Handwriting: CV ~0.05-0.20+
        return min(baseline_cv / 0.15, 1.0)

    def _stroke_angle_diversity(self, gray: np.ndarray) -> float:
        """Handwriting has more diverse stroke angles than typed text."""
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=20,
                                minLineLength=10, maxLineGap=5)
        if lines is None or len(lines) < 5:
            return 0.0

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
            angles.append(angle)

        # Typed text: mostly 0° and 90° angles
        # Handwriting: angles spread across many directions
        angle_std = float(np.std(angles))
        # Normalize: typed ~5-15°, handwriting ~20-50°
        return min(angle_std / 45.0, 1.0)


# ── Line Segmentation ──────────────────────────────────────────────────────────

def segment_lines(image_bgr: np.ndarray, min_line_height: int = 15) -> List[np.ndarray]:
    """
    Segment a handwriting chunk into individual text lines.
    TrOCR works best on single-line images.
    Returns a list of line images (BGR).
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
    )

    # Horizontal projection to find line boundaries
    h_projection = np.sum(binary, axis=1)
    threshold = np.max(h_projection) * 0.05 if np.max(h_projection) > 0 else 0

    # Find line regions (runs of ink rows)
    in_line = False
    line_start = 0
    line_regions: List[Tuple[int, int]] = []

    for y, val in enumerate(h_projection):
        if val > threshold and not in_line:
            line_start = y
            in_line = True
        elif val <= threshold and in_line:
            if y - line_start >= min_line_height:
                line_regions.append((line_start, y))
            in_line = False

    # Handle last line if image ends mid-line
    if in_line and (len(h_projection) - line_start) >= min_line_height:
        line_regions.append((line_start, len(h_projection)))

    # If no lines found, treat the whole image as one line
    if not line_regions:
        return [image_bgr]

    # Add padding around each line
    padding = 5
    h, w = image_bgr.shape[:2]
    line_images = []
    for start, end in line_regions:
        y1 = max(0, start - padding)
        y2 = min(h, end + padding)
        line_img = image_bgr[y1:y2, :].copy()
        line_images.append(line_img)

    return line_images


# ── TrOCR Recognition ──────────────────────────────────────────────────────────

def recognize_line(line_image_bgr: np.ndarray) -> OCRResult:
    """Recognize a single text line using TrOCR."""
    processor, model = _load_trocr()
    device = _get_device()

    try:
        # Convert BGR → RGB → PIL
        rgb = cv2.cvtColor(line_image_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb).convert("RGB")

        # Preprocess for TrOCR
        pixel_values = processor(images=pil_image, return_tensors="pt").pixel_values
        pixel_values = pixel_values.to(device)

        # Generate text
        with torch.no_grad():
            generated_ids = model.generate(
                pixel_values,
                max_new_tokens=settings.handwriting_max_tokens,
                num_beams=settings.handwriting_num_beams,
                early_stopping=True,
                return_dict_in_generate=True,
                output_scores=True,
            )

        # Decode text
        text = processor.batch_decode(generated_ids.sequences, skip_special_tokens=True)[0]
        text = text.strip()

        # Compute confidence from sequence scores
        if hasattr(generated_ids, "sequences_scores") and generated_ids.sequences_scores is not None:
            log_prob = generated_ids.sequences_scores[0].item()
            confidence = min(max(np.exp(log_prob), 0.0), 1.0)
        else:
            # Fallback: estimate from token probabilities
            confidence = _estimate_confidence(generated_ids, model)

        return OCRResult(text=text, confidence=confidence)

    except Exception as e:
        logger.error(f"TrOCR recognition failed: {e}")
        return OCRResult(text="", confidence=0.0, error=str(e))


def _estimate_confidence(generated_ids, model) -> float:
    """Estimate confidence when sequences_scores is not available."""
    try:
        if hasattr(generated_ids, "scores") and generated_ids.scores:
            probs = []
            for score in generated_ids.scores:
                token_probs = torch.softmax(score, dim=-1)
                max_prob = torch.max(token_probs).item()
                probs.append(max_prob)
            return float(np.mean(probs)) if probs else 0.5
    except Exception:
        pass
    return 0.5


# ── Main Engine Class ──────────────────────────────────────────────────────────

class HandwritingEngine:
    """
    Complete handwriting processing: classification + line segmentation + TrOCR recognition.
    """

    def __init__(self):
        self.classifier = HandwritingClassifier()
        self._model_loaded = False
        logger.info("Handwriting engine initialized (model loads on first use)")

    def classify(self, image_bgr: np.ndarray) -> ClassificationResult:
        """Classify whether a chunk image contains handwriting."""
        return self.classifier.classify(image_bgr)

    def recognize(self, image_bgr: np.ndarray) -> OCRResult:
        """
        Recognize handwritten text in an image.
        Segments into lines, runs TrOCR on each, combines results.
        """
        if image_bgr is None or image_bgr.size == 0:
            return OCRResult(text="", confidence=0.0)

        self._model_loaded = True

        # Segment into lines
        lines = segment_lines(image_bgr)
        logger.debug(f"Handwriting: segmented into {len(lines)} lines")

        # Recognize each line
        line_results: List[OCRResult] = []
        for i, line_img in enumerate(lines):
            result = recognize_line(line_img)
            if result.text.strip():
                line_results.append(result)
                logger.debug(f"  Line {i + 1}: '{result.text}' (conf: {result.confidence:.2f})")

        if not line_results:
            return OCRResult(text="", confidence=0.0)

        # Combine lines
        full_text = "\n".join(r.text for r in line_results)
        avg_confidence = sum(r.confidence for r in line_results) / len(line_results)

        return OCRResult(text=full_text, confidence=avg_confidence)