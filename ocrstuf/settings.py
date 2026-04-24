from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    # Paths
    temp_dir: Path = Field(default=Path("temp_processing"))
    output_dir: Path = Field(default=Path("output"))
    assets_dir: Path = Field(default=Path("assets"))
    cache_dir: Path = Field(default=Path("model_cache"))
    
    #LLM judge
    llm_judge_enabled: bool = True  # Set to True to enable the feature
    lm_studio_base_url: str = "http://localhost:1234/v1" 
    lm_studio_model: str | None = None  
    llm_judge_timeout: int = 30 
    llm_judge_threshold: float = 0.7 
    llm_judge_batch_size: int = 5 
    llm_judge_context_window: int = 3

    # Tools
    poppler_path: Path | None = None
    tesseract_cmd: Path | None = None

    # OCR / layout
    dpi: int = 300
    max_image_dim: int = 4096
    supported_formats: tuple[str, ...] = (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp")

    # OCR options
    tesseract_lang: str = "eng"
    tesseract_psm: int = 3
    easyocr_langs: tuple[str, ...] = ("en",)

    # Layout
    min_chunk_area: int = 500
    merge_distance: int = 20
    layout_confidence_threshold: float = 0.7
    ocr_confidence_threshold: float = 0.6
    judge_confidence_threshold: float = 0.8

    # Streaming
    stream_large_docs: bool = True
    large_doc_threshold: int = 20
    cleanup_temp_files: bool = True

    # LLM Judge (optional)
    ollama_model: str = "qwen2.5-vl:7b-instruct"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

   # VLM Layout Analysis
    vlm_enabled: bool = Field(default=False)
    vlm_provider: str = Field(default="lm_studio")  
    vlm_base_url: str = Field(default="http://localhost:1234/v1")
    vlm_model: str = Field(default="llava-llama-3-8b-v1_1")  # Your loaded model
    vlm_timeout: int = Field(default=60)
    vlm_min_confidence: float = Field(default=0.6)
    vlm_analyze_threshold: int = Field(default=5)  # Min chunks to trigger VLM
    
    # Cache settings
    cache_ttl: int = Field(default=86400)  # 1 day in seconds
    vlm_cache_size: int = Field(default=100)  # max items (for memory cache, but we now use disk)

    # ── Handwriting Recognition ────────────────────────────────────────────────
    handwriting_enabled: bool = Field(default=True)
    handwriting_use_gpu: bool = Field(default=True)  # Use RTX 4060; set False for RPi5
    handwriting_model: str = Field(default="microsoft/trocr-base-handwritten")
    handwriting_classifier_threshold: float = Field(default=0.55)  # Score above this → handwritten
    handwriting_confidence_threshold: float = Field(default=0.3)  # TrOCR conf below this → discard
    handwriting_max_tokens: int = Field(default=128)  # Max tokens per line
    handwriting_num_beams: int = Field(default=4)  # Beam search width (higher = better but slower)
    handwriting_classify_chunk_types: tuple[str, ...] = Field(
        default=("text", "unknown")  # Only classify these chunk types for handwriting
    )

settings = Settings()
for d in (settings.temp_dir, settings.output_dir, settings.assets_dir, settings.cache_dir):
    d.mkdir(parents=True, exist_ok=True)