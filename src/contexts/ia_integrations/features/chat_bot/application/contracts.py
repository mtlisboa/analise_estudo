"""Compatibility import; implementation lives in the central RAG module."""
import sys
from contexts.ia_integrations.rag import contracts as _implementation
sys.modules[__name__] = _implementation
