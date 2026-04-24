"""
Custom exceptions for the OCR Engine.
Keeps error handling consistent across all modules.
"""


class OCREngineError(Exception):
    """Base exception for all OCR engine errors."""
    pass


class DocumentProcessingError(OCREngineError):
    """Raised when the overall document processing pipeline fails."""
    pass


class TesseractError(OCREngineError):
    """Raised when Tesseract OCR fails."""
    pass


class EasyOCRError(OCREngineError):
    """Raised when EasyOCR fails."""
    pass


class LLMJudgeError(OCREngineError):
    """Raised when the LLM Judge correction fails."""
    pass


class HandwritingError(OCREngineError):
    """Raised when handwriting recognition fails."""
    pass


class LayoutDetectionError(OCREngineError):
    """Raised when layout detection fails."""
    pass


class ExportError(OCREngineError):
    """Raised when document export fails."""
    pass