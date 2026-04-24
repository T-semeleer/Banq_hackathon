from __future__ import annotations
import cv2
import numpy as np
from typing import List
from config.settings import settings
from core.processing_types import DocumentChunk, ChunkType, BoundingBox, ConfidenceScores
from core.logger import get_logger
from utils.sorting import sort_chunks

try:
    from surya.detection import DetectionPredictor
    from surya.layout import LayoutPredictor
    SURYA_AVAILABLE = True
except ImportError:
    SURYA_AVAILABLE = False

# Try to import VLM Layout Analyzer
try:
    from engines.vlm_layout_analyzer import VLMStructureAnalyzer
    VLM_AVAILABLE = True
except ImportError:
    VLM_AVAILABLE = False

# ── Try to import Handwriting Classifier ───────────────────────────────────────
try:
    from engines.handwriting import HandwritingClassifier
    HANDWRITING_AVAILABLE = True
except ImportError:
    HANDWRITING_AVAILABLE = False

logger = get_logger(__name__)


class LayoutDetector:
    def __init__(self):
        self.use_surya = SURYA_AVAILABLE

        # Initialize VLM if available and enabled
        self.vlm_analyzer = None
        if VLM_AVAILABLE and settings.vlm_enabled:
            self.vlm_analyzer = VLMStructureAnalyzer()
            logger.info(f"VLM Layout Analyzer initialized (model: {settings.vlm_model})")
        else:
            if VLM_AVAILABLE and not settings.vlm_enabled:
                logger.info("VLM Layout Analyzer available but not enabled. Set VLM_ENABLED=True in .env")

        # ── Initialize Handwriting Classifier ──────────────────────────────────
        self.handwriting_classifier = None
        if HANDWRITING_AVAILABLE and settings.handwriting_enabled:
            self.handwriting_classifier = HandwritingClassifier()
            logger.info(f"Handwriting classifier initialized "
                        f"(threshold: {settings.handwriting_classifier_threshold})")
        else:
            if HANDWRITING_AVAILABLE and not settings.handwriting_enabled:
                logger.info("Handwriting classifier available but not enabled. "
                            "Set HANDWRITING_ENABLED=True in .env")

        if self.use_surya:
            try:
                self.layout_predictor = LayoutPredictor()
                self.detection_predictor = DetectionPredictor()
                logger.info("Surya Layout Detector initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Surya: {e}")
                self.use_surya = False

    def detect(self, image_bgr: np.ndarray, page_number: int) -> List[DocumentChunk]:
        if self.use_surya:
            chunks = self._detect_surya(image_bgr, page_number)
        else:
            chunks = self._detect_opencv(image_bgr, page_number)

        if not chunks:
            return chunks

        # ── Handwriting classification (before VLM, after layout detection) ────
        chunks = self._classify_handwriting(chunks, page_number)

        chunks = self._apply_vlm_analysis(image_bgr, page_number, chunks)

        # Final sort: reading_order if set, else (y,x)
        return sort_chunks(chunks)

    def _classify_handwriting(self, chunks: List[DocumentChunk],
                              page_number: int) -> List[DocumentChunk]:
        """Run handwriting classifier on eligible chunks and reclassify if needed."""
        if not self.handwriting_classifier:
            return chunks

        classifiable_types = {
            ChunkType(t) for t in settings.handwriting_classify_chunk_types
        }

        reclassified_count = 0
        for chunk in chunks:
            # Only classify chunk types that could be handwriting
            if chunk.chunk_type not in classifiable_types:
                continue
            # Need an image to classify
            if chunk.image is None or chunk.image.size == 0:
                continue

            result = self.handwriting_classifier.classify(chunk.image)

            # Store classification features for debugging/export
            chunk.handwriting_classification = {
                "is_handwritten": result.is_handwritten,
                "confidence": result.confidence,
                "features": result.features,
            }

            if result.is_handwritten:
                chunk.chunk_type = ChunkType.HANDWRITING
                chunk.surya_label = "Handwriting"
                reclassified_count += 1
                logger.debug(
                    f"Page {page_number + 1}, chunk {chunk.chunk_id}: "
                    f"reclassified as HANDWRITING (score: {result.confidence:.2f})"
                )

        if reclassified_count > 0:
            logger.info(
                f"Page {page_number + 1}: {reclassified_count} chunk(s) "
                f"reclassified as handwriting"
            )

        return chunks

    def _apply_vlm_analysis(self, image_bgr: np.ndarray, page_number: int,
                           chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        if self.vlm_analyzer and len(chunks) >= settings.vlm_analyze_threshold:

            try:
                from PIL import Image
                rgb_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_image)

                structure_result = self.vlm_analyzer.analyze_structure_sync(pil_image, chunks)

                if structure_result.confidence > settings.vlm_min_confidence:

                    enhanced_chunks = self.vlm_analyzer.apply_structure_to_chunks(chunks, structure_result)

                    logger.info(f"Page {page_number + 1}: VLM enhanced {len(enhanced_chunks)} chunks "
                                f"(confidence: {structure_result.confidence:.2f})")

                    if structure_result.anomalies:
                        for anomaly in structure_result.anomalies[:3]:
                            logger.warning(f"Layout anomaly: {anomaly}")
                        if len(structure_result.anomalies) > 3:
                            logger.debug(f"... and {len(structure_result.anomalies) - 3} more anomalies")

                    if structure_result.reading_order:
                        chunk_dict = {chunk.chunk_id: chunk for chunk in enhanced_chunks}
                        for position, chunk_id in enumerate(structure_result.reading_order):
                            if chunk_id in chunk_dict:
                                chunk_dict[chunk_id].reading_order = position

                        ordered_chunks = []
                        for chunk_id in structure_result.reading_order:
                            if chunk_id in chunk_dict:
                                ordered_chunks.append(chunk_dict[chunk_id])
                        remaining = [chunk for chunk in enhanced_chunks if chunk.reading_order is None]
                        ordered_chunks.extend(remaining)
                        chunks = ordered_chunks
                    else:
                        chunks = enhanced_chunks

                    for chunk in chunks:
                        chunk.confidence.layout = (chunk.confidence.layout + structure_result.confidence) / 2

                else:
                    logger.debug(f"Page {page_number + 1}: VLM analysis low confidence "
                                 f"({structure_result.confidence:.2f}), using original layout")

            except Exception as e:
                logger.error(f"VLM analysis failed for page {page_number + 1}: {e}")

        return chunks

    def _detect_surya(self, image_bgr, page_number):
        from PIL import Image as PILImage
        pil = PILImage.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))

        try:
            results = self.layout_predictor([pil])
            chunks = []
            if not results:
                return chunks

            page_layout = results[0]
            for idx, bbox_data in enumerate(page_layout.bboxes):
                x1, y1, x2, y2 = map(int, bbox_data.bbox)
                bbox = BoundingBox.from_xyxy(x1, y1, x2, y2)
                if bbox.area < settings.min_chunk_area:
                    continue
                label = bbox_data.label if hasattr(bbox_data, "label") else "Text"
                confidence = getattr(bbox_data, "confidence", 0.9)
                chunk_type = ChunkType.from_surya_label(label)
                chunk_img = image_bgr[y1:y2, x1:x2].copy()
                chunks.append(DocumentChunk(
                    chunk_id=idx,
                    page_number=page_number,
                    chunk_type=chunk_type,
                    surya_label=label,
                    bbox=bbox,
                    image=chunk_img,
                    confidence=ConfidenceScores(layout=confidence),
                ))
            return chunks

        except Exception as e:
            logger.warning(f"Surya detection failed: {e}, falling back to OpenCV")
            return self._detect_opencv(image_bgr, page_number)

    def _detect_opencv(self, image_bgr, page_number):
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 11, 2)
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
        horizontal = cv2.dilate(binary, kernel_h, iterations=2)
        dilated = cv2.dilate(horizontal, kernel_v, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        chunks = []
        for idx, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            if area < settings.min_chunk_area:
                continue

            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio > 50 or (aspect_ratio < 0.02 and h > 100):
                continue

            bbox = BoundingBox(x, y, w, h)
            chunk_img = image_bgr[y:y+h, x:x+w].copy()

            if aspect_ratio > 3 and h < 50:
                chunk_type = ChunkType.TITLE
            elif w > h * 2:
                chunk_type = ChunkType.TEXT
            else:
                chunk_type = ChunkType.TEXT

            chunks.append(DocumentChunk(
                chunk_id=idx,
                page_number=page_number,
                chunk_type=chunk_type,
                surya_label="Text",
                bbox=bbox,
                image=chunk_img,
                confidence=ConfidenceScores(layout=0.7),
            ))

        logger.info(f"Page {page_number + 1}: OpenCV detected {len(chunks)} chunks")
        return chunks