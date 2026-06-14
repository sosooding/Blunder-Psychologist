"""Annotation orchestration — turn stored blunders into grounded, embedded annotations.

The pure assembly here (DB row → detected motifs → ``AnnotationInput``, and the text we embed) is
unit-tested with fakes; the DB-coupled ``run_annotate`` (query rows, set-once write, embedding +
FAISS upsert) lands with the worker wiring once a database is available, and reuses these helpers.
"""

import logging

import chess
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from .annotation import AnnotationInput, annotate_batch, chunk
from .embed import Embedder
from .engine import FeatureExtractor, classify_phase
from .llm import LLMProvider
from .motifs.positional import detect_positional_for_move
from .motifs.tactical import detect_tactical_for_move
from .retrieval import index_path, load_user_index

logger = logging.getLogger("blunder.annotate_flow")

# A stored blunder, flattened from the blunders ⋈ move_analyses join.
BlunderRow = dict


def uci_line_to_san(fen: str, uci_line: list[str], max_plies: int = 6) -> list[str]:
    """Render the first ``max_plies`` of a UCI line as SAN from ``fen`` (for the prompt)."""
    board = chess.Board(fen)
    out: list[str] = []
    for u in uci_line[:max_plies]:
        try:
            move = chess.Move.from_uci(u)
        except ValueError:
            break
        if not board.is_legal(move):
            break
        out.append(board.san(move))
        board.push(move)
    return out


def signature_text(
    phase: str, archetype: str, motif_tags: list[str], description: str = ""
) -> str:
    """A compact, embeddable signature of a blunder, used for BOTH the stored vector and a query
    position so they share one embedding space (a raw FEN would not match annotation prose)."""
    tags = ", ".join(sorted(motif_tags)) if motif_tags else "none"
    sig = f"{phase} {archetype}; motifs: {tags}"
    return f"{sig}; {description}".strip().rstrip(";").strip() if description else sig


def detect_motifs(row: BlunderRow, extractor: FeatureExtractor) -> list[str]:
    """Run both detector families on one stored blunder; returns sorted, de-duplicated tags."""
    fen = row["fen"]
    board = chess.Board(fen)
    played_uci = board.parse_san(row["move"]).uci()
    best_pv = row.get("best_pv") or []
    best_uci = best_pv[0] if best_pv else None
    mover_white = board.turn == chess.WHITE

    tags = detect_tactical_for_move(fen, played_uci)
    if best_uci is not None:
        tags = tags | detect_positional_for_move(
            fen, played_uci, best_uci, mover_white=mover_white, extractor=extractor
        )
    return sorted(tags)


def build_annotation_inputs(
    rows: list[BlunderRow], extractor: FeatureExtractor
) -> tuple[list[AnnotationInput], list[list[str]], list[int]]:
    """Assemble ``(inputs, detected_motifs, blunder_ids)`` from stored blunder rows."""
    inputs: list[AnnotationInput] = []
    detected: list[list[str]] = []
    bids: list[int] = []
    for row in rows:
        motifs = detect_motifs(row, extractor)
        best_pv = row.get("best_pv") or []
        inputs.append(
            AnnotationInput(
                fen=row["fen"],
                played_san=row["move"],
                best_line_san=uci_line_to_san(row["fen"], best_pv),
                delta_cp=row.get("delta_cp") or 0,
                eval_cp=row.get("eval_cp") or 0,
                detected_motifs=motifs,
                archetype=row.get("archetype") or "unknown",
                phase=row.get("phase") or "unknown",
                clock_seconds=row.get("clock_seconds"),
            )
        )
        detected.append(motifs)
        bids.append(row["id"])
    return inputs, detected, bids


# -- DB orchestration --------------------------------------------------------------------

# Motif tags are a closed [a-z_] vocabulary, so a Postgres array literal needs no escaping. This
# sidesteps psycopg2's "cannot determine type of empty array" on an empty Python list.
def _pg_text_array(values: list[str]) -> str:
    return "{" + ",".join(values) + "}"


_BLUNDER_ROWS = text(
    "SELECT b.id AS id, m.fen AS fen, m.move AS move, m.best_pv AS best_pv, "
    "m.eval_cp AS eval_cp, m.delta_cp AS delta_cp, m.phase AS phase, "
    "m.pawn_archetype AS archetype, m.clock_seconds AS clock_seconds "
    "FROM blunders b JOIN move_analyses m ON m.id = b.move_analysis_id "
    "WHERE m.game_id = :gid AND b.annotation IS NULL ORDER BY b.id"
)


def run_annotate(
    session: Session,
    game_id: int,
    *,
    extractor: FeatureExtractor,
    provider: LLMProvider,
    embedder: Embedder,
    faiss_dir: str,
) -> dict[str, int]:
    """Annotate a game's un-annotated blunders: detect motifs, write the LLM annotation + tags
    (set-once), embed, and upsert the user's FAISS index. Idempotent — re-runs annotate nothing."""
    user_id = session.execute(
        text("SELECT user_id FROM games WHERE id = :gid"), {"gid": game_id}
    ).scalar_one()
    rows = [dict(r) for r in session.execute(_BLUNDER_ROWS, {"gid": game_id}).mappings().all()]
    if not rows:
        return {"annotated": 0}

    inputs, detected, bids = build_annotation_inputs(rows, extractor)

    annotations = []
    for batch in chunk(inputs):
        annotations.extend(annotate_batch(batch, provider))

    signatures = [
        signature_text(inp.phase, inp.archetype, ann.motif_tags, ann.description)
        for inp, ann in zip(inputs, annotations, strict=True)
    ]
    vectors = embedder.embed(signatures)

    # Load (or rebuild-from-DB) the index BEFORE persisting this batch's embeddings. The rebuild
    # path reads the ``embeddings`` table, so loading after the commit below would make the first
    # annotate of a user (no cache file yet) rebuild from the just-inserted rows AND then re-add
    # them via ``idx.add``, double-counting the batch in the index.
    idx = load_user_index(session, faiss_dir, user_id)

    new_ids: list[int] = []
    new_vecs: list[np.ndarray] = []
    for bid, ann, det, vec in zip(bids, annotations, detected, vectors, strict=True):
        tags = sorted(set(ann.motif_tags) | set(det))
        written = session.execute(
            text(
                "UPDATE blunders SET annotation = :a, motif_tags = cast(:t as text[]) "
                "WHERE id = :bid AND annotation IS NULL RETURNING id"
            ),
            {"a": ann.description, "t": _pg_text_array(tags), "bid": bid},
        ).fetchone()
        if written is None:
            continue  # already annotated by an earlier run — annotations are immutable
        v = np.asarray(vec, dtype=np.float32)
        session.execute(
            text(
                "INSERT INTO embeddings (blunder_id, dim, vector) VALUES (:bid, :dim, :v) "
                "ON CONFLICT (blunder_id) DO NOTHING"
            ),
            {"bid": bid, "dim": int(v.shape[0]), "v": v.tobytes()},
        )
        new_ids.append(bid)
        new_vecs.append(v)
    session.commit()

    if new_ids:
        idx.add(new_ids, np.stack(new_vecs))
        idx.save(index_path(faiss_dir, user_id))

    logger.info("annotate game=%d: annotated=%d", game_id, len(new_ids))
    return {"annotated": len(new_ids)}


def position_signature(fen: str, extractor: FeatureExtractor) -> str:
    """Build a query signature for a bare position (phase + archetype), to embed against the stored
    blunder signatures — a raw FEN would not live in the same embedding space."""
    board = chess.Board(fen)
    feats = extractor.extract(fen, white_perspective=(board.turn == chess.WHITE))
    return signature_text(classify_phase(fen), feats.get("archetype", "unknown"), [])


def _filter_blunder_ids(
    session: Session,
    user_id: int,
    *,
    phase: str | None,
    archetype: str | None,
    severity: str | None,
) -> list[int]:
    """The SQL metadata pre-filter: the user's blunder ids narrowed by phase/archetype/severity."""
    clauses = ["g.user_id = :uid"]
    params: dict = {"uid": user_id}
    if phase:
        clauses.append("m.phase = :phase")
        params["phase"] = phase
    if archetype:
        clauses.append("m.pawn_archetype = :arch")
        params["arch"] = archetype
    if severity:
        clauses.append("b.severity = :sev")
        params["sev"] = severity
    sql = (
        "SELECT b.id FROM blunders b JOIN move_analyses m ON m.id = b.move_analysis_id "
        "JOIN games g ON g.id = m.game_id WHERE " + " AND ".join(clauses)
    )
    return [int(r[0]) for r in session.execute(text(sql), params).all()]


def find_similar_blunders(
    session: Session,
    username: str,
    fen: str,
    *,
    extractor: FeatureExtractor,
    embedder: Embedder,
    faiss_dir: str,
    k: int = 5,
    phase: str | None = None,
    archetype: str | None = None,
    severity: str | None = None,
) -> list[dict]:
    """Hybrid retrieval: SQL metadata pre-filter → FAISS top-k for a query position, scoped to one
    user. Returns the neighbour blunders' details with a cosine score."""
    user_id = session.execute(
        text("SELECT id FROM users WHERE lichess_username = :u"), {"u": username}
    ).scalar_one_or_none()
    if user_id is None:
        return []

    idx = load_user_index(session, faiss_dir, user_id)
    if idx.size == 0:
        return []

    allowed = _filter_blunder_ids(
        session, user_id, phase=phase, archetype=archetype, severity=severity
    )
    if not allowed:
        return []

    query_vec = embedder.embed([position_signature(fen, extractor)])[0]
    hits = idx.search(np.asarray(query_vec, dtype=np.float32), k, allowed_ids=allowed)
    if not hits:
        return []

    ids = [bid for bid, _ in hits]
    details = session.execute(
        text(
            "SELECT b.id AS id, m.fen AS fen, m.move AS move, b.severity AS severity, "
            "b.motif_tags AS motif_tags, b.annotation AS annotation, m.phase AS phase, "
            "m.pawn_archetype AS archetype FROM blunders b "
            "JOIN move_analyses m ON m.id = b.move_analysis_id WHERE b.id = ANY(:ids)"
        ),
        {"ids": ids},
    ).mappings().all()
    by_id = {d["id"]: dict(d) for d in details}

    out = []
    for bid, score in hits:
        detail = by_id.get(bid)
        if detail is not None:
            out.append({**detail, "score": score})
    return out
