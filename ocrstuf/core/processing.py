from __future__ import annotations
from pathlib import Path
import time
from typing import Callable, Optional
import cv2
from PIL import Image

from config.settings import settings
from engines.ocr import OCRManager
from engines.layout import LayoutDetector
from utils.image import preprocess_image
from utils.export import Exporter
from .memory import get_page_count, stream_pdf_pages, stream_image_page
from .processing_types import ProcessedDocument, ProcessedPage, ChunkType
from core.logger import get_logger
from core.exceptions import OCREngineError, DocumentProcessingError

logger = get_logger(__name__)


class DocumentProcessor:
    def __init__(self):
        self.ocr = OCRManager()                     # ← no settings param
        self.layout = LayoutDetector()               # ← no settings param
        self.exporter = Exporter()                   # ← no settings param
        self.llm_judge_enabled = settings.llm_judge_enabled
        if self.llm_judge_enabled:
            logger.info("🤖 LLM Judge is ENABLED for OCR correction")

    def process(self, file_path: Path, output_format: str = "pdf", output_path: Path | None = None,
                progress: Callable[[str, int, int], None] | None = None) -> ProcessedDocument:
        file_path = Path(file_path)
        total_pages = get_page_count(file_path)
        use_streaming = settings.stream_large_docs and total_pages >= settings.large_doc_threshold

        doc = ProcessedDocument(
            document_id=f"doc_{int(time.time())}",
            source_filename=file_path.name,
            source_path=str(file_path),
        )

        try:
            # Determine page iterator
            if use_streaming and file_path.suffix.lower() == ".pdf":
                page_iter = stream_pdf_pages(file_path, lambda c, t: progress and progress(f"Page {c}/{t}", c, t))
            elif file_path.suffix.lower() == ".pdf":
                page_iter = stream_pdf_pages(file_path, lambda c, t: progress and progress(f"Page {c}/{t}", c, t))
            else:
                page_iter = stream_image_page(file_path)

            for ref in page_iter:
                # Load and preprocess image
                img_bgr = cv2.imread(str(ref.image_path))
                pil = Image.open(ref.image_path).convert("RGB")
                cv2_proc, pil_proc = preprocess_image(pil)

                # Detect layout (now includes handwriting classification)
                chunks = self.layout.detect(cv2_proc, ref.page_number)

                # First pass: Basic OCR on all chunks (collect page context)
                page_text_context = ""
                for i, ch in enumerate(chunks):
                    if ch.chunk_type.requires_ocr():
                        # Run OCR — routing to handwriting or typed happens inside OCRManager
                        self.ocr.run_ocr(ch, page_context="")
                        page_text_context += ch.final_text + " "
                    else:
                        ch.final_text = f"[{ch.chunk_type.value.upper()}]"

                # Second pass: Apply LLM Judge to low‑confidence chunks if enabled
                                # Second pass: Apply LLM Judge to low‑confidence chunks if enabled
                # Skip HANDWRITING chunks — they already went through TrOCR + LLM Judge
                if self.llm_judge_enabled:
                    low_confidence_chunks = [
                        ch for ch in chunks
                        if ch.chunk_type.requires_ocr()
                        and ch.chunk_type != ChunkType.HANDWRITING
                        and ch.confidence.ocr_average < settings.llm_judge_threshold
                    ]
                    if low_confidence_chunks:
                        logger.info(f"Page {ref.page_number + 1}: {len(low_confidence_chunks)} chunks need LLM judgment")
                        for ch in low_confidence_chunks:
                            # Re‑run OCR with page context for better correction
                            self.ocr.run_ocr(ch, page_context=page_text_context)

                # Create processed page
                page = ProcessedPage(
                    page_number=ref.page_number,
                    document_id=doc.document_id,
                    original_width=ref.width,
                    original_height=ref.height,
                    chunks=chunks,
                )
                page.update_statistics()
                doc.pages.append(page)

                # Progress update
                if progress:
                    progress(f"Processed page {ref.page_number + 1}/{total_pages}", ref.page_number + 1, total_pages)

            doc.update_statistics()

            # Determine output path
            if output_path:
                output_path = Path(output_path)
            else:
                output_path = settings.output_dir / f"{file_path.stem}.{output_format}"

            # Export
            self.exporter.export(doc, output_path, output_format)

            # Print summary
            self._print_summary(doc)

            return doc

        except OCREngineError as e:
            logger.exception(f"Document processing failed: {e}")
            raise DocumentProcessingError(f"Failed to process {file_path}: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error during document processing: {e}")
            raise

    def _print_summary(self, doc: ProcessedDocument):
        """Print processing summary."""
        print("\n" + "=" * 50)
        print("📊 PROCESSING SUMMARY")
        print("=" * 50)
        print(f"Document: {doc.source_filename}")
        print(f"Pages: {doc.total_pages}")
        print(f"Total chunks: {doc.total_chunks}")
        print(f"Chunks needing review: {doc.total_chunks_needing_review}")

        # Count LLM‑judged chunks
        llm_judged = 0
        handwriting_chunks = 0
        for page in doc.pages:
            for chunk in page.chunks:
                if "llm_judge" in chunk.ocr_results:
                    llm_judged += 1
                if chunk.chunk_type == ChunkType.HANDWRITING:
                    handwriting_chunks += 1

        if llm_judged > 0:
            print(f"LLM-judged chunks: {llm_judged}")
        if handwriting_chunks > 0:
            print(f"✍️  Handwriting chunks: {handwriting_chunks}")
        print("=" * 50)