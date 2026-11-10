"""Compatibility import; implementation lives in the central RAG module."""
import sys
from features.rag.infrastructure import actions as _implementation
sys.modules[__name__] = _implementation
