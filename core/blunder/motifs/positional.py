"""Positional motif detectors — thresholded reads of played-vs-best feature diffs.

Each detector compares the position the played move reached against the one the engine's best move
would have reached, both from the mover's perspective (see ``featurediff.FeatureDiff``). We only
detect motifs the current ``Features`` vector grounds honestly — structure damage, king-shield
weakening, mobility collapse. The remaining positional tags in the vocabulary (tension release,
file/diagonal concession, bad trade, outpost concession, wrong pawn break) need richer signals
(pawn tension, diagonal control, material, outpost squares) that the C++ ``Features`` struct does
not yet carry, so they stay reserved rather than fired on a weak proxy — an honest non-tag beats a
false one.
"""

from ..featurediff import FeatureDiff

# Motifs this module fires; other POSITIONAL_TAGS stay reserved (see module docstring).
DETECTED = frozenset({"structure_damage", "king_shield_weakening", "mobility_collapse"})

# Thresholds, in feature units: pawn counts, king-shield files (0..3), mobility in squares.
EXTRA_WEAK_PAWNS = 1  # isolated + doubled + backward pawns beyond what best allowed
SHIELD_DROP = 1  # king-shield files lost relative to best
EXTRA_KING_ATTACKERS = 2  # additional distinct king-zone attackers relative to best
MOBILITY_DROP = 6  # squares of piece mobility lost relative to best


def detect_positional(diff: FeatureDiff) -> set[str]:
    """Positional motif tags implied by how much worse the played move's resulting position is."""
    d = diff.delta
    tags: set[str] = set()

    if d["isolated_pawns"] + d["doubled_pawns"] + d["backward_pawns"] >= EXTRA_WEAK_PAWNS:
        tags.add("structure_damage")

    if d["king_shield"] <= -SHIELD_DROP or d["king_zone_attackers"] >= EXTRA_KING_ATTACKERS:
        tags.add("king_shield_weakening")

    if d["mobility"] <= -MOBILITY_DROP:
        tags.add("mobility_collapse")

    return tags


def detect_positional_for_move(
    fen_before: str,
    played_uci: str,
    best_uci: str,
    *,
    mover_white: bool,
    extractor,
) -> set[str]:
    """Bridge from a candidate to positional tags: diff the played vs best resulting positions."""
    from ..featurediff import feature_diff  # local import avoids a hard featurediff→engine cycle

    diff = feature_diff(
        fen_before, played_uci, best_uci, mover_white=mover_white, extractor=extractor
    )
    return detect_positional(diff)
