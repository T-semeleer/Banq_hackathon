"""
LLM Judge for OCR correction and validation.
Uses LM Studio's OpenAI-compatible API for local LLM inference.
"""
from __future__ import annotations
import json
import time
import hashlib
from typing import Dict, Any, List, Optional
import requests
from dataclasses import dataclass, field
from core.logger import get_logger
from core.exceptions import LLMJudgeError
from config.settings import settings
from core.processing_types import DocumentChunk
logger = get_logger(__name__)

@dataclass
class JudgeResult:
    corrected_text: str
    confidence: float
    corrections: List[str]
    reasoning: str
    processing_time: float = 0.0


class LLMJudge:
    """LLM-based OCR judge that corrects and validates OCR output."""
    
    def __init__(self):
        self.enabled = getattr(settings, 'llm_judge_enabled', False)
        self.base_url = getattr(settings, 'lm_studio_base_url', "http://localhost:1234/v1")
        self.model = getattr(settings, 'lm_studio_model', None)
        self.timeout = getattr(settings, 'llm_judge_timeout', 30)
        self.threshold = getattr(settings, 'llm_judge_threshold', 0.7)
        
        # Cache for similar text patterns
        self.cache: Dict[str, JudgeResult] = {}
    
    def judge_chunk(self, chunk: DocumentChunk, page_context: str = "", 
                   surrounding_chunks: List[DocumentChunk] = None) -> JudgeResult:
        """
        Judge and correct OCR output for a single chunk.
        
        Args:
            chunk: The document chunk with OCR results
            page_context: Text from the same page for context
            surrounding_chunks: Nearby chunks for spatial context
            
        Returns:
            JudgeResult with corrections and confidence
        """
        if not self.enabled or not chunk.final_text.strip():
            return JudgeResult(
                corrected_text=chunk.final_text,
                confidence=chunk.confidence.ocr_average,
                corrections=[],
                reasoning="Judge disabled or empty text"
            )
        
        start_time = time.time()
        
        # Create cache key based on text hash and chunk type
        text_hash = hashlib.md5(chunk.final_text.encode()).hexdigest()[:8]
        cache_key = f"{text_hash}_{chunk.chunk_type.value}"
        
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            # Return cached but update processing time
            return JudgeResult(
                corrected_text=cached.corrected_text,
                confidence=cached.confidence,
                corrections=cached.corrections,
                reasoning=cached.reasoning + " (cached)",
                processing_time=time.time() - start_time
            )
        
        # Prepare context from surrounding chunks
        context_text = ""
        if surrounding_chunks:
            # Get text from nearby chunks (within 100 pixels vertically)
            nearby_texts = []
            for other in surrounding_chunks:
                if other is not chunk and other.bbox and chunk.bbox:
                    if abs(other.bbox.y - chunk.bbox.y) < 100:
                        nearby_texts.append(other.final_text)
            if nearby_texts:
                context_text = "Nearby text: " + " | ".join(nearby_texts[:3])
        
        # Build the prompt for the LLM
        prompt = self._build_judge_prompt(
            ocr_text=chunk.final_text,
            chunk_type=chunk.chunk_type,
            ocr_confidence=chunk.confidence.ocr_average,
            page_context=page_context,
            surrounding_context=context_text,
            surya_label=getattr(chunk, 'surya_label', 'Text')
        )
        
        try:
            # Call LM Studio API
            response = self._call_lm_studio(prompt)
            result = self._parse_llm_response(response)
            
            # Calculate processing time
            result.processing_time = time.time() - start_time
            
            # Cache the result (limit cache size)
            if len(self.cache) < 100:
                self.cache[cache_key] = result
            
            return result
            
        except Exception as e:
            # Fallback to original OCR text if LLM fails
            logger.error(f"LLM Judge error: {e}")
            return JudgeResult(
                corrected_text=chunk.final_text,
                confidence=chunk.confidence.ocr_average * 0.8,  # Penalize for failure
                corrections=[],
                reasoning=f"Judge failed: {str(e)[:100]}",
                processing_time=time.time() - start_time
            )
    
    def judge_batch(self, chunks: List[DocumentChunk], 
                   page_context: Dict[int, str] = None) -> List[JudgeResult]:
        """
        Judge multiple chunks in a batch for efficiency.
        """
        results = []
        for i, chunk in enumerate(chunks):
            context = page_context.get(chunk.page_number, "") if page_context else ""
            
            # Get nearby chunks (previous and next)
            surrounding = []
            if i > 0:
                surrounding.append(chunks[i-1])
            if i < len(chunks) - 1:
                surrounding.append(chunks[i+1])
            
            result = self.judge_chunk(chunk, context, surrounding)
            results.append(result)
        
        return results
    
    def _build_judge_prompt(self, ocr_text: str, chunk_type, ocr_confidence: float,
                          page_context: str, surrounding_context: str, surya_label: str) -> str:
        """Build the prompt for the LLM judge."""
        
        chunk_type_desc = {
            "text": "body text paragraph",
            "title": "document title or heading",
            "section_header": "section heading",
            "list_item": "list item or bullet point",
            "table": "table cell content",
            "caption": "image or figure caption",
            "footnote": "footnote or annotation",
            "page_header": "page header",
            "page_footer": "page footer",
            "formula": "mathematical formula",
            "handwriting": "handwritten text",
            "signature": "signature or handwritten name",
            "stamp": "official stamp or seal",
            "logo": "company logo or emblem",
        }.get(chunk_type.value, "text element")
        
        return f"""You are an expert document OCR corrector and validator.

TASK: Correct OCR errors in the following text. The text comes from a document chunk identified as: {surya_label} ({chunk_type_desc}).

OCR CONFIDENCE: {ocr_confidence:.2f}

ORIGINAL OCR TEXT:
```text
{ocr_text}"""