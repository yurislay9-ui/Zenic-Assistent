"""
Unit tests for src/core/semantic_engine.py - SemanticEngine

Tests:
- SemanticEngine initialization (auto_load=False to avoid real model)
- load_model() / unload_model() lifecycle
- is_loaded property
- stats property
- embed() with mocked model
- embed_batch() with mocked model
- similarity() static method
- similarity_text() with mocked embed
- classify_intent() with mocked embeddings
- classify_intent() fallback path
- search() with mocked embeddings
- find_similar_intents() with mocked embeddings
"""

from .test_semantic_parts import *
