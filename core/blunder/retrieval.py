"""Per-user FAISS retrieval.

Per-user corpora are 2–10k vectors, so an exact ``IndexFlatIP`` wrapped in ``IndexIDMap2`` (keyed
by blunder id) beats any ANN structure — exact search is cheap below ~100k and the approximation
overhead is unjustified. Vectors are L2-normalized upstream, so inner product is cosine similarity.

Retrieval is hybrid: callers compute a SQL metadata pre-filter (phase × clock bucket × archetype ×
severity) to an allowed set of blunder ids, then this index returns the top-k by semantic
similarity within that set. The on-disk ``{user}.faiss`` file is a cache; the ``embeddings`` table
is the source of truth for rebuilds.
"""

import logging
from pathlib import Path

import faiss
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from .embed import DIM

logger = logging.getLogger("blunder.retrieval")


def index_path(faiss_dir: str, user_id: int) -> Path:
    return Path(faiss_dir) / f"user_{user_id}.faiss"


class UserIndex:
    """A flat inner-product index keyed by blunder id."""

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim
        self.index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))

    @property
    def size(self) -> int:
        return int(self.index.ntotal)

    def add(self, ids: list[int], vectors: np.ndarray) -> None:
        """Add blunder vectors. Ids must be new (callers only embed not-yet-indexed blunders)."""
        if len(ids) == 0:
            return
        vecs = np.ascontiguousarray(vectors, dtype=np.float32)
        self.index.add_with_ids(vecs, np.asarray(ids, dtype=np.int64))

    def remove(self, ids: list[int]) -> None:
        if ids:
            self.index.remove_ids(np.asarray(ids, dtype=np.int64))

    def search(
        self, query: np.ndarray, k: int, *, allowed_ids: list[int] | None = None
    ) -> list[tuple[int, float]]:
        """Top-k ``(blunder_id, cosine)`` for ``query``, restricted to ``allowed_ids`` if given.

        Flat IP returns results in descending-similarity order, so when a filter is present we
        oversearch the whole (small) index and drop disallowed ids — exact and simple.
        """
        n = self.size
        if n == 0:
            return []
        q = np.ascontiguousarray(np.asarray(query, dtype=np.float32).reshape(1, -1))
        topn = n if allowed_ids is not None else min(k, n)
        scores, idx = self.index.search(q, topn)
        allowed = set(allowed_ids) if allowed_ids is not None else None

        out: list[tuple[int, float]] = []
        for score, i in zip(scores[0], idx[0], strict=True):
            if i == -1:
                continue
            bid = int(i)
            if allowed is not None and bid not in allowed:
                continue
            out.append((bid, float(score)))
            if len(out) >= k:
                break
        return out

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(path))

    @classmethod
    def load(cls, path: str | Path, dim: int = DIM) -> "UserIndex":
        idx = cls(dim)
        idx.index = faiss.read_index(str(path))
        return idx


def load_user_index(
    session: Session, faiss_dir: str, user_id: int, *, dim: int = DIM
) -> UserIndex:
    """Load a user's index from its cache file, or rebuild it from the ``embeddings`` table.

    The ``{user}.faiss`` file is a cache; the DB is the source of truth, so a missing or stale file
    is recovered without re-embedding.
    """
    path = index_path(faiss_dir, user_id)
    if path.exists():
        return UserIndex.load(path, dim)

    idx = UserIndex(dim)
    rows = session.execute(
        text(
            "SELECT e.blunder_id, e.vector FROM embeddings e "
            "JOIN blunders b ON b.id = e.blunder_id "
            "JOIN move_analyses m ON m.id = b.move_analysis_id "
            "JOIN games g ON g.id = m.game_id WHERE g.user_id = :uid"
        ),
        {"uid": user_id},
    ).all()
    if rows:
        ids = [int(r.blunder_id) for r in rows]
        vecs = np.stack([np.frombuffer(r.vector, dtype=np.float32) for r in rows])
        idx.add(ids, vecs)
    return idx
