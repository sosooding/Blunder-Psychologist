"""FAISS retrieval tests — synthetic normalized vectors, no model download, no DB."""

import numpy as np

from blunder.embed import l2_normalize
from blunder.retrieval import UserIndex, index_path


def _vec(*xs) -> np.ndarray:
    return l2_normalize(np.array([xs], dtype=np.float32))[0]


def _index() -> UserIndex:
    idx = UserIndex(dim=3)
    idx.add(
        [10, 20, 30],
        np.stack([_vec(1, 0, 0), _vec(0, 1, 0), _vec(0, 0, 1)]),
    )
    return idx


def test_empty_index_returns_nothing():
    assert UserIndex(dim=3).search(_vec(1, 0, 0), k=5) == []


def test_nearest_neighbour_is_top():
    idx = _index()
    hits = idx.search(_vec(0.9, 0.1, 0.0), k=2)
    assert idx.size == 3
    assert hits[0][0] == 10  # closest to the (1,0,0) vector
    assert hits[0][1] > hits[1][1]  # descending similarity


def test_metadata_prefilter_restricts_ids():
    idx = _index()
    # Query points at id 10, but only 20 and 30 are allowed → 10 is excluded.
    hits = idx.search(_vec(1, 0, 0), k=2, allowed_ids=[20, 30])
    assert {bid for bid, _ in hits} == {20, 30}


def test_k_limits_results():
    assert len(_index().search(_vec(1, 1, 1), k=1)) == 1


def test_save_and_load_round_trip(tmp_path):
    idx = _index()
    path = index_path(str(tmp_path), user_id=7)
    idx.save(path)
    assert path.exists()
    reloaded = UserIndex.load(path, dim=3)
    assert reloaded.size == 3
    assert reloaded.search(_vec(0, 1, 0), k=1)[0][0] == 20


def test_remove_drops_ids():
    idx = _index()
    idx.remove([20])
    assert idx.size == 2
    assert all(bid != 20 for bid, _ in idx.search(_vec(0, 1, 0), k=3))
