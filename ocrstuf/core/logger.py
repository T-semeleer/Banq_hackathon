"""
Centralized logging for the OCR Engine.
Every module calls: from core.logger import get_logger
"""
import logging
import sys

# Create a single shared formatter
_formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

# Single stream handler (console output), attached to root OCR logger
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_formatter)

# Root logger for the entire OCR engine
_root_logger = logging.getLogger("ocrengine")
_root_logger.setLevel(logging.DEBUG)
_root_logger.addHandler(_handler)
_root_logger.propagate = False  # Don't duplicate into Python's root logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger under the ocrengine namespace.
    Usage: logger = get_logger(__name__)
    """
    return _root_logger.getChild(name)