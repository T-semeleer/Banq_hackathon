from __future__ import annotations
import cv2
import pytesseract
import easyocr
from config.settings import settings
from core.processing_types import DocumentChunk, ChunkType
from utils.types import OCRResult
from engines.llm_judge import LLMJudge
from core.logger import get_logger
from core.exceptions import TesseractError, EasyOCRError, LLMJudgeError

# ── Try to import Handwriting Engine ───────────────────────────────────────────
try:
    from engines.handwriting import HandwritingEngine
    HANDWRITING_ENGINE_AVAILABLE = True
except ImportError:
    HANDWRITING_ENGINE_AVAILABLE = False

logger = get_logger(__name__)


class OCRManager:
    def __init__(self):
        pytesseract.pytesseract.tesseract_cmd = str(settings.tesseract_cmd) if settings.tesseract_cmd else pytesseract.pytesseract.tesseract_cmd
        self.easy_reader = easyocr.Reader(settings.easyocr_langs, gpu=False, verbose=False)
        self.llm_judge = LLMJudge() if settings.llm_judge_enabled else None

        # ── Initialize Handwriting Engine ──────────────────────────────────────
        self.handwriting_engine = None
        if HANDWRITING_ENGINE_AVAILABLE and settings.handwriting_enabled:
            self.handwriting_engine = HandwritingEngine()
            logger.info("Handwriting recognition engine enabled")

    def _tesseract(self, image):
        try:
            data = pytesseract.image_to_data(image, lang=settings.tesseract_lang, config=f"--psm {settings.tesseract_psm}", output_type=pytesseract.Output.DICT)
            text = " ".join([data["text"][i] for i in range(len(data["text"])) if int(data["conf"][i]) > 0])
            confs = [int(data["conf"][i]) for i in range(len(data["text"])) if int(data["conf"][i]) > 0]
            conf = sum(confs) / len(confs) / 100.0 if confs else 0.0
            return OCRResult(text, conf)
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            raise TesseractError(f"Tesseract failed: {e}") from e

    def _easyocr(self, image):
        try:
            result = self.easy_reader.readtext(image, paragraph=True)
            text = " ".join([item[1] for item in result])
            conf = sum([item[2] for item in result]) / len(result) if result else 0.0
            return OCRResult(text, conf)
        except Exception as e:
            logger.error(f"EasyOCR failed: {e}")
            raise EasyOCRError(f"EasyOCR failed: {e}") from e

    def _handwriting_ocr(self, chunk: DocumentChunk) -> OCRResult:
        """Run TrOCR handwriting recognition on a chunk."""
        try:
            result = self.handwriting_engine.recognize(chunk.image)
            logger.debug(
                f"Handwriting OCR chunk {chunk.chunk_id}: "
                f"'{result.text[:50]}...' (conf: {result.confidence:.2f})"
                if len(result.text) > 50 else
                f"Handwriting OCR chunk {chunk.chunk_id}: "
                f"'{result.text}' (conf: {result.confidence:.2f})"
            )
            return result
        except Exception as e:
            logger.error(f"Handwriting OCR failed for chunk {chunk.chunk_id}: {e}")
            return OCRResult(text="", confidence=0.0, error=str(e))

    def run_ocr(self, chunk: DocumentChunk, page_context: str = "") -> DocumentChunk:
        # ── HANDWRITING PATH ──────────────────────────────────────────────────
        if chunk.chunk_type == ChunkType.HANDWRITING and self.handwriting_engine:
            hw_result = self._handwriting_ocr(chunk)
            chunk.ocr_results["handwriting_trocr"] = hw_result
            chunk.confidence.ocr_handwriting = hw_result.confidence

            # If TrOCR confidence is very low, also try Tesseract as a backup
            # (some "handwriting" might actually be stylized typed text)
            if hw_result.confidence < settings.handwriting_confidence_threshold:
                logger.info(
                    f"Chunk {chunk.chunk_id}: TrOCR low confidence "
                    f"({hw_result.confidence:.2f}), trying Tesseract as backup"
                )
                try:
                    tess = self._tesseract(chunk.image)
                    chunk.ocr_results["tesseract"] = tess
                    chunk.confidence.ocr_tesseract = tess.confidence
                    # Use whichever result is better
                    if tess.confidence > hw_result.confidence:
                        best = tess
                    else:
                        best = hw_result
                except TesseractError:
                    best = hw_result
            else:
                best = hw_result

            chunk.final_text = best.text

            # LLM Judge still applies for low-confidence handwriting
            self._apply_llm_judge(chunk, page_context)
            chunk.update_review_flag()
            return chunk

        # ── STANDARD PATH (typed text — unchanged logic) ──────────────────────
        try:
            tess = self._tesseract(chunk.image)
            chunk.ocr_results["tesseract"] = tess
        except TesseractError as e:
            logger.warning(f"Tesseract failed for chunk {chunk.chunk_id}: {e}, falling back to EasyOCR")
            tess = OCRResult("", 0.0)
            chunk.ocr_results["tesseract"] = tess

        if tess.confidence < settings.ocr_confidence_threshold:
            try:
                ez = self._easyocr(chunk.image)
                chunk.ocr_results["easyocr"] = ez
                best = ez if ez.confidence > tess.confidence else tess
            except EasyOCRError as e:
                logger.warning(f"EasyOCR failed for chunk {chunk.chunk_id}: {e}, using Tesseract only")
                best = tess
        else:
            best = tess

        chunk.final_text = best.text
        chunk.confidence.ocr_tesseract = chunk.ocr_results["tesseract"].confidence
        chunk.confidence.ocr_easyocr = chunk.ocr_results.get("easyocr", OCRResult("", 0)).confidence

        # LLM Judge
        self._apply_llm_judge(chunk, page_context)
        chunk.update_review_flag()
        return chunk

    def _apply_llm_judge(self, chunk: DocumentChunk, page_context: str):
        """Apply LLM Judge to low-confidence chunks (works for both typed and handwritten)."""
        if (self.llm_judge and
            chunk.final_text.strip() and
            chunk.chunk_type.requires_ocr() and
            chunk.confidence.ocr_average < settings.llm_judge_threshold):

            try:
                judge_result = self.llm_judge.judge_chunk(chunk, page_context)

                if judge_result.confidence > chunk.confidence.ocr_average:
                    chunk.final_text = judge_result.corrected_text
                    chunk.confidence.judge = judge_result.confidence
                    chunk.ocr_results["llm_judge"] = {
                        "original": chunk.final_text,
                        "corrected": judge_result.corrected_text,
                        "corrections": judge_result.corrections,
                        "reasoning": judge_result.reasoning,
                        "processing_time": judge_result.processing_time
                    }
                else:
                    chunk.confidence.judge = chunk.confidence.ocr_average

            except LLMJudgeError as e:
                logger.error(f"LLM Judge failed for chunk {chunk.chunk_id}: {e}")
                chunk.confidence.judge = chunk.confidence.ocr_average * 0.9
            except Exception as e:
                logger.exception(f"Unexpected error in LLM Judge for chunk {chunk.chunk_id}: {e}")
                chunk.confidence.judge = chunk.confidence.ocr_average * 0.9
        else:
            chunk.confidence.judge = chunk.confidence.ocr_average