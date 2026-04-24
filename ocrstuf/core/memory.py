from __future__ import annotations
from pathlib import Path
import json
import gc
import time
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional
from pdf2image import convert_from_path, pdfinfo_from_path
import cv2
from PIL import Image
from .processing_types import PageReference  # define small dataclass shared types
from config.settings import settings


def get_page_count(document_path: Path) -> int:
    if document_path.suffix.lower() == ".pdf":
        info = pdfinfo_from_path(str(document_path), poppler_path=str(settings.poppler_path) if settings.poppler_path else None)
        return info.get("Pages", 0)
    return 1


def stream_pdf_pages(pdf_path: Path, progress: Callable[[int, int], None] | None) -> Iterator[PageReference]:
    total = get_page_count(pdf_path)
    for page_num in range(1, total + 1):
        if progress:
            progress(page_num, total)
        images = convert_from_path(
            str(pdf_path),
            dpi=settings.dpi,
            first_page=page_num,
            last_page=page_num,
            poppler_path=str(settings.poppler_path) if settings.poppler_path else None,
        )
        pil_image = images[0]
        ref = _save_page(pil_image, page_num - 1)
        del pil_image
        gc.collect()
        yield ref


def stream_image_page(image_path: Path) -> Iterator[PageReference]:
    pil_image = Image.open(image_path).convert("RGB")
    ref = _save_page(pil_image, 0)
    del pil_image
    gc.collect()
    yield ref


def _save_page(pil_image: Image.Image, page_number: int) -> PageReference:
    pages_dir = settings.temp_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    img_path = pages_dir / f"page_{page_number:04d}.png"
    pil_image.save(img_path, "PNG")
    width, height = pil_image.size
    return PageReference(
        page_number=page_number,
        image_path=img_path,
        json_path=pages_dir / f"page_{page_number:04d}.json",
        width=width,
        height=height,
        is_processed=False,
    )