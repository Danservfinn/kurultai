#!/usr/bin/env python3
"""
Embedding Generator — Local embeddings via Ollama nomic-embed-text (768d).

Provides synchronous embedding generation for the ingestion pipeline.
Falls back to zero-vector if Ollama is unavailable.

Usage:
    from embedding_generator import generate_embedding, generate_embeddings

    embedding = generate_embedding("Hello, world!")
    # Returns list of 768 floats

    embeddings = generate_embeddings(["Hello", "World"])
    # Returns list of 2 embedding vectors
"""

import json
import logging
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768
OLLAMA_BASE_URL = "http://localhost:11434"

# Cache for model availability check
_model_available: Optional[bool] = None


def _check_model_available() -> bool:
    """Check if the embedding model is available in Ollama."""
    global _model_available
    if _model_available is not None:
        return _model_available

    try:
        import requests
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            _model_available = any(
                EMBEDDING_MODEL in m.get("name", "")
                for m in models
            )
        else:
            _model_available = False
    except Exception:
        # Try subprocess fallback
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True, text=True, timeout=10
            )
            _model_available = EMBEDDING_MODEL in result.stdout
        except Exception:
            _model_available = False

    if not _model_available:
        logger.warning(f"Embedding model '{EMBEDDING_MODEL}' not available in Ollama")
    return _model_available


def generate_embedding(text: str) -> List[float]:
    """Generate a 768-dimensional embedding for a text string.

    Args:
        text: Input text to embed

    Returns:
        List of 768 floats. Returns zero-vector if Ollama is unavailable.
    """
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM

    if not _check_model_available():
        return [0.0] * EMBEDDING_DIM

    try:
        import requests
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBEDDING_MODEL, "input": text},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                emb = embeddings[0]
                if len(emb) == EMBEDDING_DIM:
                    return emb
                logger.warning(
                    f"Unexpected embedding dimension: {len(emb)}, expected {EMBEDDING_DIM}"
                )
        else:
            logger.error(f"Ollama embedding request failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")

    return [0.0] * EMBEDDING_DIM


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts.

    Args:
        texts: List of input texts

    Returns:
        List of embedding vectors (one per input text)
    """
    if not texts:
        return []

    if not _check_model_available():
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    try:
        import requests
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBEDDING_MODEL, "input": texts},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if len(embeddings) == len(texts):
                return embeddings
    except Exception as e:
        logger.error(f"Batch embedding generation failed: {e}")

    # Fallback: generate one at a time
    return [generate_embedding(text) for text in texts]


def embedding_is_zero(embedding: List[float]) -> bool:
    """Check if an embedding is a zero-vector (failed generation)."""
    if not embedding:
        return True
    return all(v == 0.0 for v in embedding[:10])


if __name__ == "__main__":
    print("Embedding generator self-test:")

    if not _check_model_available():
        print(f"  WARNING: {EMBEDDING_MODEL} not available. Run: ollama pull {EMBEDDING_MODEL}")
        print("  Generating zero-vector fallback...")

    emb = generate_embedding("Hello from Kublai!")
    print(f"  Dimension: {len(emb)}")
    print(f"  First 5 values: {emb[:5]}")
    print(f"  Is zero: {embedding_is_zero(emb)}")

    # Batch test
    batch = generate_embeddings(["Hello", "World", "Test"])
    print(f"  Batch: {len(batch)} embeddings of dim {len(batch[0]) if batch else 0}")

    print("\nDone.")
