"""
Enhanced Vision-Language Model (VLM) for document structure analysis.
Supports multiple VLM providers (LM Studio, Ollama, OpenAI, Claude) with fallback strategies.
"""
from __future__ import annotations
import base64
import json
import time
import asyncio
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import aiohttp
from PIL import Image
import io
from utils.cache import DiskCache
from config.settings import settings, Settings  # <-- direct import
from core.processing_types import DocumentChunk, BoundingBox, ChunkType

# Configure logging
logger = logging.getLogger(__name__)


class VLMProvider(Enum):
    """Supported VLM providers."""
    LM_STUDIO = "lm_studio"
    OLLAMA = "ollama"
    OPENAI = "openai"
    CLAUDE = "claude"
    LOCAL = "local"


class VLMError(Exception):
    """Custom exception for VLM-related errors."""
    pass


@dataclass
class VLMStructureResult:
    """Results from VLM structure analysis with enhanced metadata."""
    reading_order: List[int] = field(default_factory=list)
    groups: List[List[int]] = field(default_factory=list)
    hierarchies: List[Dict[str, Any]] = field(default_factory=list)
    anomalies: List[Dict[str, Any]] = field(default_factory=list)  # Enhanced with type and severity
    table_structures: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    confidence: float = 0.0
    processing_time: float = 0.0
    model_used: Optional[str] = None
    provider: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkRelationship:
    """Enhanced relationships between chunks."""
    source_id: int
    target_ids: List[int]
    relationship_type: str  # "caption_to_image", "title_to_table", "list_items", "figure_reference", etc.
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VLMPromptTemplate:
    """Configurable prompt templates for different document types."""
    name: str
    system_prompt: str
    user_prompt: str
    response_format: Dict[str, Any]
    temperature: float = 0.1
    max_tokens: int = 2000


class VLMBaseClient:
    """Base class for VLM clients with common functionality."""
    
    def __init__(self, base_url: str, model: str, timeout: int = 60):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
    
    async def ensure_session(self):
        """Ensure a session exists (thread-safe)."""
        async with self._session_lock:
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def __aenter__(self):
        await self.ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def analyze_image(self, image_base64: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Base method to analyze image with VLM (to be implemented by subclasses)."""
        raise NotImplementedError


class LMStudioClient(VLMBaseClient):
    """Client for LM Studio VLM API."""
    
    async def analyze_image(self, image_base64: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Analyze image using LM Studio API."""
        await self.ensure_session()
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 2000),
            "stream": False
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=self.timeout
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                content = data["choices"][0]["message"]["content"]
                return self._extract_json_response(content)
                
        except aiohttp.ClientError as e:
            logger.error(f"LM Studio API error: {e}")
            raise VLMError(f"LM Studio API call failed: {e}")
    
    def _extract_json_response(self, content: str) -> Dict[str, Any]:
        """Extract JSON from response text."""
        # Remove markdown code blocks if present
        import re
        
        # Try to find JSON in code blocks
        json_pattern = r'```(?:json)?\s*(.*?)\s*```'
        match = re.search(json_pattern, content, re.DOTALL)
        
        if match:
            json_str = match.group(1)
        else:
            # If no code blocks, try to find JSON directly
            json_str = content.strip()
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            # Try to extract JSON-like structure
            try:
                # Find content between { and }
                json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except:
                pass
            raise VLMError(f"Invalid JSON response from VLM: {content[:200]}...")


class OllamaClient(VLMBaseClient):
    """Client for Ollama VLM API."""
    
    async def analyze_image(self, image_base64: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Analyze image using Ollama API."""
        await self.ensure_session()
        
        # Ollama expects image data as raw bytes in the images array
        image_bytes = base64.b64decode(image_base64)
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_bytes],
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.1),
                "num_predict": kwargs.get("max_tokens", 2000)
            }
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                return self._extract_json_response(data.get("response", ""))
                
        except aiohttp.ClientError as e:
            logger.error(f"Ollama API error: {e}")
            raise VLMError(f"Ollama API call failed: {e}")


class VLMStructureAnalyzer:
    """Enhanced VLM for document structure understanding with multi-provider support."""
    
    # Default prompt templates
    DEFAULT_TEMPLATES = {
        "general": VLMPromptTemplate(
            name="general",
            system_prompt="You are an expert document layout analyst. Analyze the document image and provide structural information.",
            user_prompt="""Analyze this document image and the detected chunks:

DETECTED CHUNKS:
{chunks_preview}

TASKS:
1. READING ORDER: Determine correct reading order (considering columns, flow).
2. GROUPING: Identify chunks that belong together (captions, lists, related sections).
3. HIERARCHY: Detect heading levels and parent-child relationships.
4. ANOMALIES: Flag layout issues with type and severity (low/medium/high).
5. TABLES: For table chunks, describe structure including merged cells.

RESPONSE FORMAT (JSON):
{response_format_example}

IMPORTANT: Use 0-based chunk indices from the DETECTED CHUNKS list.""",
            response_format={
                "reading_order": [0, 1, 2],
                "groups": [[0, 1], [2, 3]],
                "hierarchies": [
                    {"chunk_id": 0, "level": "title", "children": [1, 2]},
                    {"chunk_id": 1, "level": "h1", "parent": 0}
                ],
                "anomalies": [
                    {"chunk_id": 3, "type": "overlap", "description": "Text overlaps image", "severity": "medium"}
                ],
                "tables": {
                    "4": {"rows": 3, "columns": 2, "has_headers": True, "merged_cells": []}
                },
                "confidence": 0.95
            }
        ),
        "academic": VLMPromptTemplate(
            name="academic",
            system_prompt="You are an expert academic paper analyst. Focus on sections, references, figures, and equations.",
            user_prompt="""Analyze this academic paper image:

DETECTED CHUNKS:
{chunks_preview}

Special attention to:
- Abstract, Introduction, Methods, Results, Discussion sections
- Figure and table captions
- References and citations
- Equations and special notations

{response_format_example}""",
            response_format={
                "reading_order": [],
                "groups": [],
                "hierarchies": [],
                "anomalies": [],
                "tables": {},
                "confidence": 0.0,
                "sections": {}  # Additional field for academic papers
            }
        )
    }
    
    def __init__(self, settings_override: Optional[Settings] = None):
        """
        Args:
            settings_override: Optional Settings instance with overridden values.
                               If None, uses the global `settings` from config.
        """
        self._settings = settings_override or settings
        
        self.enabled = self._settings.vlm_enabled
        self.provider = VLMProvider(self._settings.vlm_provider)
        self.base_url = self._settings.vlm_base_url
        self.model = self._settings.vlm_model
        self.timeout = self._settings.vlm_timeout
        self.min_confidence = self._settings.vlm_min_confidence
        
    
        cache_dir = self._settings.cache_dir / "vlm"
        self.cache = DiskCache(cache_dir, ttl=self._settings.cache_ttl)

        
        # Statistics
        self.stats = {
            "requests": 0,
            "cache_hits": 0,
            "errors": 0,
            "total_processing_time": 0.0
        }
        
        # Prompt template management
        self.templates = self.DEFAULT_TEMPLATES.copy()
        self.current_template = "general"
        
        # Initialize client
        self.client = self._create_client()
    
    def _create_client(self) -> VLMBaseClient:
        """Create appropriate VLM client based on provider."""
        if self.provider == VLMProvider.LM_STUDIO:
            return LMStudioClient(self.base_url, self.model, self.timeout)
        elif self.provider == VLMProvider.OLLAMA:
            ollama_url = getattr(self._settings, 'ollama_url', 'http://localhost:11434')
            return OllamaClient(ollama_url, self.model, self.timeout)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    async def analyze_page_structure(
        self,
        page_image: Image.Image,
        detected_chunks: List[DocumentChunk],
        template_name: str = "general",
        use_cache: bool = True
    ) -> VLMStructureResult:
        """
        Analyze document structure using VLM.
        
        Args:
            page_image: PIL Image of the page
            detected_chunks: List of chunks from initial layout detection
            template_name: Name of prompt template to use
            use_cache: Whether to use cached results
            
        Returns:
            VLMStructureResult with enhanced structure information
        """
        if not self.enabled or not detected_chunks:
            return self._create_empty_result()
        
        start_time = time.time()
        self.stats["requests"] += 1
        
        # Create cache key
        cache_key = self._generate_cache_key(page_image, detected_chunks)
        
        if use_cache:
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                self.stats["cache_hits"] += 1
                cached_result.processing_time = time.time() - start_time
                logger.debug(f"Cache hit for key: {cache_key[:20]}...")
                return cached_result
        
        try:
            # Select template
            template = self.templates.get(template_name, self.templates["general"])
            self.current_template = template_name
            
            # Prepare chunks preview
            chunks_preview = self._create_chunks_preview(detected_chunks)
            
            # Convert image to base64
            img_base64 = self._pil_to_base64(page_image)
            
            # Build prompt
            prompt = self._build_prompt(template, chunks_preview)
            
            # Call VLM
            result_json = await self._call_vlm_with_retry(
                img_base64, prompt, template
            )
            
            # Parse and validate response
            result = self._parse_and_validate_response(
                result_json, detected_chunks, template
            )
            
            # Add metadata
            result.processing_time = time.time() - start_time
            result.model_used = self.model
            result.provider = self.provider.value
            result.metadata = {
                "template_used": template_name,
                "chunks_analyzed": len(detected_chunks),
                "timestamp": time.time()
            }
            
            # Update statistics
            self.stats["total_processing_time"] += result.processing_time
            
            # Cache the result
            self.cache.set(cache_key, result)
            
            logger.info(
                f"VLM analysis completed: {len(result.reading_order)} chunks ordered, "
                f"confidence: {result.confidence:.2f}, "
                f"time: {result.processing_time:.2f}s"
            )
            
            return result
            
        except VLMError as e:
            self.stats["errors"] += 1
            logger.error(f"VLM analysis failed: {e}")
            return self._create_empty_result(
                processing_time=time.time() - start_time,
                error=str(e)
            )
        except Exception as e:
            self.stats["errors"] += 1
            logger.exception(f"Unexpected error in VLM analysis: {e}")
            return self._create_empty_result(
                processing_time=time.time() - start_time,
                error=str(e)
            )
    
    async def _call_vlm_with_retry(
        self,
        image_base64: str,
        prompt: str,
        template: VLMPromptTemplate,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Call VLM with retry logic and exponential backoff."""
        for attempt in range(max_retries):
            try:
                return await self.client.analyze_image(
                    image_base64,
                    prompt,
                    temperature=template.temperature,
                    max_tokens=template.max_tokens
                )
            except (aiohttp.ClientError, VLMError) as e:
                if attempt == max_retries - 1:
                    raise
                
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(
                    f"VLM call failed (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
        
        raise VLMError(f"VLM call failed after {max_retries} attempts")
    
    def _generate_cache_key(
        self,
        page_image: Image.Image,
        chunks: List[DocumentChunk]
    ) -> str:
        """Generate cache key from image and chunk data."""
        # Image hash
        img_bytes = page_image.tobytes()
        img_hash = hashlib.md5(img_bytes).hexdigest()[:16]
        
        # Chunk signature (type, position, text hash)
        chunk_signatures = []
        for chunk in chunks[:50]:  # Limit to first 50 chunks
            chunk_sig = f"{chunk.chunk_type.value}_{chunk.bbox.x}_{chunk.bbox.y}"
            if chunk.final_text:
                text_hash = hashlib.md5(chunk.final_text.encode()).hexdigest()[:8]
                chunk_sig += f"_{text_hash}"
            chunk_signatures.append(chunk_sig)
        
        chunks_hash = hashlib.md5("_".join(chunk_signatures).encode()).hexdigest()[:16]
        
        return f"{img_hash}_{chunks_hash}_{self.current_template}"
    
    def _build_prompt(self, template: VLMPromptTemplate, chunks_preview: str) -> str:
        """Build complete prompt from template."""
        # Format response format as pretty JSON for the prompt
        import json as json_module
        response_format_example = json_module.dumps(
            template.response_format,
            indent=2
        )
        
        # Build complete prompt
        prompt_parts = [
            template.system_prompt,
            "\n" + "="*50 + "\n",
            template.user_prompt.format(
                chunks_preview=chunks_preview,
                response_format_example=response_format_example
            )
        ]
        
        return "\n".join(prompt_parts)
    
    def _parse_and_validate_response(
        self,
        response_data: Dict[str, Any],
        chunks: List[DocumentChunk],
        template: VLMPromptTemplate
    ) -> VLMStructureResult:
        """Parse and validate VLM response against expected format."""
        
        # Validate required fields
        required_fields = ["reading_order", "groups", "hierarchies", "anomalies", "tables", "confidence"]
        for field in required_fields:
            if field not in response_data:
                logger.warning(f"Missing field in VLM response: {field}")
                response_data[field] = template.response_format.get(field, [])
        
        # Validate chunk indices are within bounds
        def validate_indices(indices: List[int], context: str) -> List[int]:
            valid = []
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(chunks):
                    valid.append(idx)
                else:
                    logger.warning(f"Invalid chunk index {idx} in {context}")
            return valid
        
        # Validate reading order
        reading_order = validate_indices(response_data.get("reading_order", []), "reading_order")
        
        # Validate groups
        validated_groups = []
        for group in response_data.get("groups", []):
            if isinstance(group, list):
                validated_group = validate_indices(group, "group")
                if validated_group:
                    validated_groups.append(validated_group)
        
        # Validate hierarchies
        validated_hierarchies = []
        for hierarchy in response_data.get("hierarchies", []):
            if isinstance(hierarchy, dict):
                chunk_id = hierarchy.get("chunk_id")
                if isinstance(chunk_id, int) and 0 <= chunk_id < len(chunks):
                    # Validate parent and children indices if present
                    if "parent" in hierarchy:
                        parent = hierarchy["parent"]
                        if parent is not None and not (isinstance(parent, int) and 0 <= parent < len(chunks)):
                            hierarchy["parent"] = None
                    
                    if "children" in hierarchy:
                        hierarchy["children"] = validate_indices(hierarchy["children"], "hierarchy_children")
                    
                    validated_hierarchies.append(hierarchy)
        
        # Validate anomalies
        validated_anomalies = []
        for anomaly in response_data.get("anomalies", []):
            if isinstance(anomaly, dict):
                if "chunk_id" in anomaly:
                    chunk_id = anomaly["chunk_id"]
                    if not (isinstance(chunk_id, int) and 0 <= chunk_id < len(chunks)):
                        continue
                validated_anomalies.append(anomaly)
            elif isinstance(anomaly, str):
                # Convert string anomalies to dict format
                validated_anomalies.append({
                    "description": anomaly,
                    "severity": "medium",
                    "type": "general"
                })
        
        # Validate tables
        validated_tables = {}
        for chunk_id_str, table_info in response_data.get("tables", {}).items():
            try:
                chunk_id = int(chunk_id_str)
                if 0 <= chunk_id < len(chunks) and isinstance(table_info, dict):
                    validated_tables[chunk_id] = table_info
            except (ValueError, TypeError):
                continue
        
        # Validate confidence
        confidence = float(response_data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        
        return VLMStructureResult(
            reading_order=reading_order,
            groups=validated_groups,
            hierarchies=validated_hierarchies,
            anomalies=validated_anomalies,
            table_structures=validated_tables,
            confidence=confidence
        )
    
    def _create_empty_result(
        self,
        processing_time: float = 0.0,
        error: Optional[str] = None
    ) -> VLMStructureResult:
        """Create an empty result with optional error information."""
        metadata = {}
        if error:
            metadata["error"] = error
        
        return VLMStructureResult(
            processing_time=processing_time,
            metadata=metadata
        )
    
    def apply_structure_to_chunks(
        self,
        chunks: List[DocumentChunk],
        structure: VLMStructureResult
    ) -> List[DocumentChunk]:
        """
        Apply VLM structure analysis results back onto document chunks.
        
        Updates:
        - reading_order from structure.reading_order
        - group metadata from structure.groups
        - hierarchy (parent/children) from structure.hierarchies
        - anomaly flags from structure.anomalies
        - table structure from structure.table_structures
        
        Args:
            chunks: Original document chunks
            structure: VLM analysis result
            
        Returns:
            Enhanced chunks with structure information applied
        """
        if not chunks or structure.confidence <= 0:
            return chunks

        # Build index for fast lookup
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        # Also build by position index (VLM returns 0-based indices, not chunk_ids)
        chunk_by_index = {i: chunk for i, chunk in enumerate(chunks)}

        # ── Apply reading order ────────────────────────────────────────────
        if structure.reading_order:
            for position, idx in enumerate(structure.reading_order):
                if idx in chunk_by_index:
                    chunk_by_index[idx].reading_order = position

        # ── Apply group metadata ───────────────────────────────────────────
        for group_idx, group in enumerate(structure.groups):
            for idx in group:
                if idx in chunk_by_index:
                    # Store group info in the chunk's ocr_results dict
                    # (reusing existing dict to avoid adding new fields)
                    if "vlm_metadata" not in chunk_by_index[idx].ocr_results:
                        chunk_by_index[idx].ocr_results["vlm_metadata"] = {}
                    chunk_by_index[idx].ocr_results["vlm_metadata"]["group_id"] = group_idx
                    chunk_by_index[idx].ocr_results["vlm_metadata"]["group_members"] = group

        # ── Apply hierarchy ────────────────────────────────────────────────
        for hierarchy in structure.hierarchies:
            chunk_idx = hierarchy.get("chunk_id")
            if chunk_idx is not None and chunk_idx in chunk_by_index:
                chunk = chunk_by_index[chunk_idx]
                if "vlm_metadata" not in chunk.ocr_results:
                    chunk.ocr_results["vlm_metadata"] = {}

                chunk.ocr_results["vlm_metadata"]["hierarchy_level"] = hierarchy.get("level", "unknown")

                if "parent" in hierarchy and hierarchy["parent"] is not None:
                    chunk.ocr_results["vlm_metadata"]["parent_index"] = hierarchy["parent"]

                if "children" in hierarchy:
                    chunk.ocr_results["vlm_metadata"]["children_indices"] = hierarchy["children"]

        # ── Apply anomaly flags ────────────────────────────────────────────
        for anomaly in structure.anomalies:
            if isinstance(anomaly, dict) and "chunk_id" in anomaly:
                idx = anomaly["chunk_id"]
                if idx in chunk_by_index:
                    chunk = chunk_by_index[idx]
                    if "vlm_metadata" not in chunk.ocr_results:
                        chunk.ocr_results["vlm_metadata"] = {}
                    chunk.ocr_results["vlm_metadata"]["anomaly"] = {
                        "type": anomaly.get("type", "unknown"),
                        "description": anomaly.get("description", ""),
                        "severity": anomaly.get("severity", "medium"),
                    }
                    # Flag for review if severity is high
                    if anomaly.get("severity") == "high":
                        chunk.review_flag = "needs_review"

        # ── Apply table structures ─────────────────────────────────────────
        for chunk_idx, table_info in structure.table_structures.items():
            idx = int(chunk_idx) if isinstance(chunk_idx, str) else chunk_idx
            if idx in chunk_by_index:
                chunk = chunk_by_index[idx]
                if "vlm_metadata" not in chunk.ocr_results:
                    chunk.ocr_results["vlm_metadata"] = {}
                chunk.ocr_results["vlm_metadata"]["table_structure"] = table_info
                # Ensure chunk is typed as TABLE
                if chunk.chunk_type != ChunkType.TABLE:
                    logger.info(
                        f"Chunk {chunk.chunk_id} reclassified as TABLE by VLM "
                        f"(was {chunk.chunk_type.value})"
                    )
                    chunk.chunk_type = ChunkType.TABLE

        logger.debug(
            f"Applied VLM structure: {len(structure.reading_order)} ordered, "
            f"{len(structure.groups)} groups, {len(structure.hierarchies)} hierarchies, "
            f"{len(structure.anomalies)} anomalies, {len(structure.table_structures)} tables"
        )

        return chunks
    
    def _create_chunks_preview(self, chunks: List[DocumentChunk], max_chunks: int = 30) -> str:
        """Create a text preview of detected chunks."""
        preview_lines = []
        
        for i, chunk in enumerate(chunks[:max_chunks]):
            preview = f"[{i}] Type: {chunk.chunk_type.value}"
            
            if chunk.surya_label:
                preview += f", Label: {chunk.surya_label}"
            
            if chunk.bbox:
                preview += f", Pos: ({chunk.bbox.x:.0f},{chunk.bbox.y:.0f})-({chunk.bbox.x2:.0f},{chunk.bbox.y2:.0f})"
            
            if chunk.final_text:
                text_preview = chunk.final_text.replace('\n', ' ').strip()
                if len(text_preview) > 60:
                    text_preview = text_preview[:57] + "..."
                preview += f", Text: '{text_preview}'"
            
            preview_lines.append(preview)
        
        if len(chunks) > max_chunks:
            preview_lines.append(f"... and {len(chunks) - max_chunks} more chunks")
        
        return "\n".join(preview_lines)
    
    def _pil_to_base64(self, image: Image.Image, format: str = "JPEG", quality: int = 85) -> str:
        """Convert PIL Image to base64 string with compression."""
        buffered = io.BytesIO()
        
        # Convert to RGB if necessary (for JPEG)
        if format == "JPEG" and image.mode != "RGB":
            image = image.convert("RGB")
        
        image.save(buffered, format=format, quality=quality, optimize=True)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current statistics."""
        avg_time = 0
        if self.stats["requests"] > 0:
            avg_time = self.stats["total_processing_time"] / self.stats["requests"]
        
        cache_hit_rate = 0
        if self.stats["requests"] > 0:
            cache_hit_rate = self.stats["cache_hits"] / self.stats["requests"]
        
        return {
            **self.stats,
            "cache_hit_rate": cache_hit_rate,
            "avg_processing_time": avg_time,
            "provider": self.provider.value,
            "model": self.model
        }
    
    def clear_cache(self):
        """Clear the VLM cache."""
        self.cache.clear()
        logger.info("VLM cache cleared")
    
    # Synchronous wrapper for async methods
    def analyze_structure_sync(
        self,
        page_image: Image.Image,
        detected_chunks: List[DocumentChunk],
        **kwargs
    ) -> VLMStructureResult:
        """Synchronous wrapper for async analysis."""
        if not self.enabled:
            return self._create_empty_result()
        
        try:
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're in a running loop, we need to run in a separate thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.analyze_page_structure(page_image, detected_chunks, **kwargs)
                    )
                    return future.result()
            except RuntimeError:
                # No running loop, we can create one
                return asyncio.run(self.analyze_page_structure(page_image, detected_chunks, **kwargs))
                
        except Exception as e:
            logger.error(f"Sync analysis failed: {e}")
            return self._create_empty_result(error=str(e))
    
    def __del__(self):
        if hasattr(self, 'cache'):
            self.cache.close()

# =============================================================================
# Factory function (simplified, uses settings.model_copy)
# =============================================================================
def create_vlm_analyzer(**kwargs) -> VLMStructureAnalyzer:
    """
    Create a VLMStructureAnalyzer with optional settings overrides.

    Args:
        **kwargs: Any setting from `Settings` to override (e.g., vlm_model="llava-13b").

    Returns:
        Configured VLMStructureAnalyzer instance.
    """
    if not kwargs:
        return VLMStructureAnalyzer()
    
    # Create a copy of the global settings with the provided overrides
    from config.settings import settings
    overridden = settings.model_copy(update=kwargs)
    return VLMStructureAnalyzer(settings_override=overridden)