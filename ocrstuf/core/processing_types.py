from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import time


@dataclass
class PageReference:
    page_number: int
    image_path: Any
    json_path: Any
    width: int
    height: int
    is_processed: bool = False


class ChunkType(Enum):
    TEXT = "text"
    TITLE = "title"
    SECTION_HEADER = "section_header"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    IMAGE = "image"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    HANDWRITING = "handwriting"
    STAMP = "stamp"
    LOGO = "logo"
    SIGNATURE = "signature"
    FORMULA = "formula"
    UNKNOWN = "unknown"

    @classmethod
    def from_surya_label(cls, label: str) -> "ChunkType":
        mapping = {
            "Text": cls.TEXT,
            "Title": cls.TITLE,
            "Section-header": cls.SECTION_HEADER,
            "List-item": cls.LIST_ITEM,
            "Table": cls.TABLE,
            "Figure": cls.FIGURE,
            "Caption": cls.CAPTION,
            "Footnote": cls.FOOTNOTE,
            "Page-header": cls.PAGE_HEADER,
            "Page-footer": cls.PAGE_FOOTER,
            "Picture": cls.IMAGE,
            "Formula": cls.FORMULA,
        }
        return mapping.get(label, cls.UNKNOWN)

    def requires_ocr(self) -> bool:
        return self not in {self.FIGURE, self.IMAGE, self.STAMP, self.LOGO, self.SIGNATURE}


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    @classmethod
    def from_xyxy(cls, x1: int, y1: int, x2: int, y2: int) -> "BoundingBox":
        return cls(x=x1, y=y1, width=x2 - x1, height=y2 - y1)


@dataclass
class ConfidenceScores:
    layout: float = 0.0
    ocr_tesseract: float = 0.0
    ocr_easyocr: float = 0.0
    ocr_handwriting: float = 0.0   # ← NEW: TrOCR handwriting confidence
    judge: float = 0.0

    @property
    def ocr_average(self) -> float:
        scores = [s for s in (self.ocr_tesseract, self.ocr_easyocr, self.ocr_handwriting) if s > 0]
        return sum(scores) / len(scores) if scores else 0.0

    @property
    def overall(self) -> float:
        return (self.layout * 0.2) + (self.ocr_average * 0.5) + (self.judge * 0.3)


@dataclass
class DocumentChunk:
    chunk_id: int
    page_number: int = 0
    chunk_type: ChunkType = ChunkType.UNKNOWN
    surya_label: str = ""
    bbox: BoundingBox | None = None
    image: Any = None
    ocr_results: Dict[str, Any] = field(default_factory=dict)
    final_text: str = ""
    confidence: ConfidenceScores = field(default_factory=ConfidenceScores)
    review_flag: str = "none"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    reading_order: Optional[int] = None  # VLM-determined position, does NOT replace chunk_id
    handwriting_classification: Optional[Dict[str, Any]] = None  # ← NEW: classifier features

    def update_review_flag(self):
        if self.confidence.layout < 0.7 or self.confidence.ocr_average < 0.6 or self.confidence.judge < 0.8:
            self.review_flag = "needs_review"


@dataclass
class ProcessedPage:
    page_number: int
    document_id: str = ""
    original_width: int = 0
    original_height: int = 0
    chunks: List[DocumentChunk] = field(default_factory=list)
    total_chunks: int = 0
    chunks_needing_review: int = 0
    processing_time: float = 0.0

    def update_statistics(self):
        self.total_chunks = len(self.chunks)
        self.chunks_needing_review = len([c for c in self.chunks if c.review_flag != "none"])

    def get_full_text(self) -> str:
        from utils.sorting import sort_chunks  # local import to avoid circular
        ordered = sort_chunks(self.chunks)
        return "\n\n".join([c.final_text for c in ordered if c.final_text and c.chunk_type.requires_ocr()])


@dataclass
class ProcessedDocument:
    document_id: str
    source_filename: str
    source_path: str
    pages: List[ProcessedPage] = field(default_factory=list)
    total_pages: int = 0
    total_chunks: int = 0
    total_chunks_needing_review: int = 0

    def update_statistics(self):
        self.total_pages = len(self.pages)
        self.total_chunks = sum(len(p.chunks) for p in self.pages)
        self.total_chunks_needing_review = sum(p.chunks_needing_review for p in self.pages)

    def get_full_text(self) -> str:
        return "\n\n--- PAGE BREAK ---\n\n".join(p.get_full_text() for p in self.pages)

    def to_dict(self):
        return {
            "document_id": self.document_id,
            "source_filename": self.source_filename,
            "total_pages": self.total_pages,
            "total_chunks": self.total_chunks,
            "total_chunks_needing_review": self.total_chunks_needing_review,
            "pages": [
                {
                    "page_number": p.page_number,
                    "document_id": p.document_id,
                    "original_width": p.original_width,
                    "original_height": p.original_height,
                    "total_chunks": p.total_chunks,
                    "chunks_needing_review": p.chunks_needing_review,
                    "processing_time": p.processing_time,
                    "chunks": [
                        {
                            "chunk_id": c.chunk_id,
                            "page_number": c.page_number,
                            "chunk_type": c.chunk_type.value,
                            "surya_label": c.surya_label,
                            "bbox": c.bbox.to_tuple() if c.bbox else None,
                            "final_text": c.final_text,
                            "confidence": {
                                "layout": c.confidence.layout,
                                "ocr_average": c.confidence.ocr_average,
                                "ocr_handwriting": c.confidence.ocr_handwriting,  # ← NEW
                                "judge": c.confidence.judge,
                                "overall": c.confidence.overall,
                            },
                            "review_flag": c.review_flag,
                            "created_at": c.created_at,
                            "reading_order": c.reading_order,
                            "handwriting_classification": c.handwriting_classification,  # ← NEW
                        }
                        for c in p.chunks
                    ],
                }
                for p in self.pages
            ],
        }


class OutputFormat(Enum):
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    JSON = "json"
    TXT = "txt"