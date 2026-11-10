"""Compatibility import; implementation lives in the central RAG module."""
import sys
from contexts.ia_integrations.rag import actions as _implementation
sys.modules[__name__] = _implementation
