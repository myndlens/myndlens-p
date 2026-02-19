"""ONNX Embedding Engine — Digital Self semantic layer.

Uses fastembed (ONNX Runtime) for fast, dependency-light embeddings.
Model: BAAI/bge-small-en-v1.5 (33M params, 384-dim, quantized ONNX).
No PyTorch. No TensorFlow. Downloads and caches model on first use.

Why ONNX over ChromaDB default:
- Deterministic: same text → same vector always
- Persistent: vectors can be stored + reloaded without re-embedding
- Fast: ONNX Runtime is significantly faster than sentence-transformers
- Portable: same model runs on any platform with onnxruntime
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

_model = None
MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384-dim, quantized, fast


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        logger.info("[ONNX Embedder] Loading model: %s", MODEL_NAME)
        _model = TextEmbedding(model_name=MODEL_NAME)
        logger.info("[ONNX Embedder] Model ready: %s", MODEL_NAME)
    return _model


def embed(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts.

    Returns list of 384-dim float vectors.
    Caches model on first call (~30s download, then instant).
    """
    model = _get_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


def embed_one(text: str) -> List[float]:
    """Generate embedding for a single text."""
    return embed([text])[0]


def dimension() -> int:
    """Return embedding dimension (384 for bge-small-en-v1.5)."""
    return 384
