"""Embedding service — local bge-small via fastembed (free, no API, no torch).

Vectors are L2-normalized so a FAISS inner-product index is exact cosine similarity. The model is
lazy-loaded (first ``embed`` downloads ~130 MB of ONNX weights), and callers depend on the
``Embedder`` protocol so retrieval can be driven in tests with synthetic vectors and no model.
"""

import logging
from typing import Protocol

import numpy as np

logger = logging.getLogger("blunder.embed")

MODEL = "BAAI/bge-small-en-v1.5"
DIM = 384  # bge-small-en-v1.5 embedding dimension


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization; zero rows are left as zeros (no divide-by-zero)."""
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, 1e-9, None)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an ``(len(texts), DIM)`` float32, L2-normalized array."""
        ...


class FastEmbedder:
    """bge-small via fastembed. The model is constructed once and reused."""

    def __init__(self, model: str = MODEL) -> None:
        try:
            from fastembed import TextEmbedding  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - exercised only without the dep
            raise RuntimeError("fastembed is not installed") from exc
        self._model = TextEmbedding(model_name=model)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        vecs = np.array(list(self._model.embed(texts)), dtype=np.float32)
        return l2_normalize(vecs)
