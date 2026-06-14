"""End-to-end annotate flow + retrieval against a real Postgres, with fakes for the engine
extractor, the LLM provider, and the embedding model (no wheel, no network, no model download)."""

import json

import numpy as np
import pytest
from sqlalchemy import text

from blunder.annotate_flow import find_similar_blunders, run_annotate
from blunder.embed import DIM, l2_normalize
from blunder.featurediff import NUMERIC_FIELDS
from blunder.retrieval import UserIndex, index_path

# Black to move, knight on d2: ...Ne4 hangs it to Re1 and pins it to the e8 king.
BLUNDER_FEN = "4k3/8/8/8/8/8/3n4/4R1K1 b - - 0 1"


def _feat() -> dict:
    f = {k: 0 for k in NUMERIC_FIELDS}
    f["archetype"] = "endgame_simplified"
    return f


class ConstExtractor:
    """Returns the same features for any position → positional diff is always zero."""

    def extract(self, fen: str, *, white_perspective: bool) -> dict:
        return _feat()


class FakeProvider:
    """Returns a valid JSON array of ``n`` annotations per call (n = the batch size)."""

    def __init__(self, n: int) -> None:
        self.n = n

    def generate(self, prompt: str) -> str:
        return json.dumps(
            [
                {
                    "description": f"weak square conceded ({i})",
                    "motif_tags": ["hanging_piece"],
                    "counterfactual": "the retreat keeps the knight active",
                }
                for i in range(self.n)
            ]
        )


class FakeEmbedder:
    """Deterministic per-text unit vectors — reproducible, no model."""

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        rows = [
            np.random.default_rng(abs(hash(t)) % (2**32)).standard_normal(DIM).astype(np.float32)
            for t in texts
        ]
        return l2_normalize(np.stack(rows))


@pytest.fixture
def clean(session):
    session.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
    session.commit()
    return session


def _seed_user(session, username: str) -> int:
    return session.execute(
        text("INSERT INTO users (lichess_username) VALUES (:u) RETURNING id"), {"u": username}
    ).scalar_one()


def _seed_game(session, user_id: int) -> int:
    return session.execute(
        text("INSERT INTO games (user_id, pgn) VALUES (:u, '') RETURNING id"), {"u": user_id}
    ).scalar_one()


def _seed_blunder(session, game_id: int, ply: int, *, severity: str) -> int:
    ma_id = session.execute(
        text(
            "INSERT INTO move_analyses "
            "(game_id, ply, fen, move, eval_cp, best_eval_cp, delta_cp, phase, pawn_archetype, "
            " best_pv) "
            "VALUES (:g, :p, :fen, 'Ne4', -300, 50, 350, 'endgame', 'endgame_simplified', "
            " cast(:bp as jsonb)) RETURNING id"
        ),
        {"g": game_id, "p": ply, "fen": BLUNDER_FEN, "bp": json.dumps(["d2c4"])},
    ).scalar_one()
    return session.execute(
        text("INSERT INTO blunders (move_analysis_id, severity) VALUES (:m, :s) RETURNING id"),
        {"m": ma_id, "s": severity},
    ).scalar_one()


def _annotate(session, game_id, faiss_dir, n):
    return run_annotate(
        session,
        game_id,
        extractor=ConstExtractor(),
        provider=FakeProvider(n),
        embedder=FakeEmbedder(),
        faiss_dir=str(faiss_dir),
    )


def test_run_annotate_writes_annotations_embeddings_and_index(clean, tmp_path):
    session = clean
    user_id = _seed_user(session, "alice")
    game_id = _seed_game(session, user_id)
    b1 = _seed_blunder(session, game_id, 10, severity="blunder")
    b2 = _seed_blunder(session, game_id, 12, severity="mistake")
    session.commit()

    result = _annotate(session, game_id, tmp_path, n=2)
    assert result["annotated"] == 2

    rows = session.execute(
        text("SELECT id, annotation, motif_tags FROM blunders ORDER BY id")
    ).all()
    for _id, annotation, tags in rows:
        assert annotation  # set
        # detector tags (hanging_piece + pin) are unioned with the LLM's
        assert "hanging_piece" in tags and "pin" in tags

    embs = session.execute(text("SELECT count(*) FROM embeddings")).scalar_one()
    assert embs == 2
    assert index_path(str(tmp_path), user_id).exists()
    assert {b1, b2} == {r[0] for r in rows}


def test_run_annotate_does_not_double_index_on_first_batch(clean, tmp_path):
    """Regression: with no cache file yet, ``load_user_index`` rebuilds from the embeddings table.
    When that load happened *after* the batch's embeddings were committed, the rebuild already held
    the new rows and ``idx.add`` re-added them — doubling the first game's vectors in the index."""
    session = clean
    user_id = _seed_user(session, "alice")
    game_id = _seed_game(session, user_id)
    _seed_blunder(session, game_id, 10, severity="blunder")
    _seed_blunder(session, game_id, 12, severity="mistake")
    session.commit()

    assert _annotate(session, game_id, tmp_path, n=2)["annotated"] == 2

    # Exactly one vector per blunder on disk — not four.
    idx = UserIndex.load(index_path(str(tmp_path), user_id))
    assert idx.size == 2

    # And retrieval never returns the same blunder twice.
    hits = find_similar_blunders(
        session,
        "alice",
        BLUNDER_FEN,
        k=10,
        extractor=ConstExtractor(),
        embedder=FakeEmbedder(),
        faiss_dir=str(tmp_path),
    )
    ids = [h["id"] for h in hits]
    assert len(ids) == len(set(ids))


def test_run_annotate_is_idempotent(clean, tmp_path):
    session = clean
    user_id = _seed_user(session, "alice")
    game_id = _seed_game(session, user_id)
    _seed_blunder(session, game_id, 10, severity="blunder")
    session.commit()

    assert _annotate(session, game_id, tmp_path, n=1)["annotated"] == 1
    # second run finds nothing un-annotated (annotations are immutable, set-once)
    assert _annotate(session, game_id, tmp_path, n=1)["annotated"] == 0
    assert session.execute(text("SELECT count(*) FROM embeddings")).scalar_one() == 1


def test_find_similar_is_user_scoped_and_filterable(clean, tmp_path):
    session = clean
    alice = _seed_user(session, "alice")
    alice_game = _seed_game(session, alice)
    _seed_blunder(session, alice_game, 10, severity="blunder")
    _seed_blunder(session, alice_game, 12, severity="mistake")
    bob = _seed_user(session, "bob")
    bob_game = _seed_game(session, bob)
    _seed_blunder(session, bob_game, 10, severity="blunder")
    session.commit()

    _annotate(session, alice_game, tmp_path, n=2)
    _annotate(session, bob_game, tmp_path, n=1)

    common = dict(
        extractor=ConstExtractor(),
        embedder=FakeEmbedder(),
        faiss_dir=str(tmp_path),
    )
    hits = find_similar_blunders(session, "alice", BLUNDER_FEN, k=5, **common)
    assert hits  # non-empty
    alice_ids = {
        r[0]
        for r in session.execute(
            text(
                "SELECT b.id FROM blunders b JOIN move_analyses m ON m.id=b.move_analysis_id "
                "JOIN games g ON g.id=m.game_id WHERE g.user_id=:u"
            ),
            {"u": alice},
        ).all()
    }
    assert {h["id"] for h in hits} <= alice_ids  # never returns bob's blunders
    assert all(-1.0001 <= h["score"] <= 1.0001 for h in hits)

    # severity metadata pre-filter narrows the candidate set
    only_blunders = find_similar_blunders(
        session, "alice", BLUNDER_FEN, k=5, severity="blunder", **common
    )
    sevs = {
        session.execute(
            text("SELECT severity FROM blunders WHERE id=:i"), {"i": h["id"]}
        ).scalar_one()
        for h in only_blunders
    }
    assert sevs == {"blunder"}


def test_find_similar_unknown_user_is_empty(clean, tmp_path):
    assert (
        find_similar_blunders(
            clean,
            "nobody",
            BLUNDER_FEN,
            extractor=ConstExtractor(),
            embedder=FakeEmbedder(),
            faiss_dir=str(tmp_path),
        )
        == []
    )
