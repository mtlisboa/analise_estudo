"""Compatibility import for persisted chat history."""
import sys
from features.rag.infrastructure import history as _implementation
sys.modules[__name__] = _implementation
