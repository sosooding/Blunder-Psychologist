"""Positional detector tests — pure, over directly-constructed FeatureDiffs and a fake extractor."""

from blunder.featurediff import NUMERIC_FIELDS, FeatureDiff
from blunder.motifs.positional import (
    DETECTED,
    detect_positional,
    detect_positional_for_move,
)
from blunder.motifs.vocab import POSITIONAL_TAGS

# Reuse the fake extractor + FEN from the featurediff test surface.
from tests.test_featurediff import FEN_BLACK_TO_MOVE, FakeExtractor, _feat


def _diff(**delta_over) -> FeatureDiff:
    zero = {k: 0 for k in NUMERIC_FIELDS}
    delta = dict(zero)
    delta.update(delta_over)
    return FeatureDiff(played=dict(zero), best=dict(zero), delta=delta)


def test_structure_damage_fires_on_extra_weak_pawns():
    assert detect_positional(_diff(isolated_pawns=1)) == {"structure_damage"}
    assert detect_positional(_diff(doubled_pawns=2)) == {"structure_damage"}
    assert detect_positional(_diff(backward_pawns=1)) == {"structure_damage"}
    assert detect_positional(_diff(isolated_pawns=0)) == set()


def test_king_shield_weakening():
    assert detect_positional(_diff(king_shield=-1)) == {"king_shield_weakening"}
    assert detect_positional(_diff(king_zone_attackers=2)) == {"king_shield_weakening"}
    assert detect_positional(_diff(king_zone_attackers=1)) == set()  # below threshold


def test_mobility_collapse_threshold():
    assert detect_positional(_diff(mobility=-6)) == {"mobility_collapse"}
    assert detect_positional(_diff(mobility=-5)) == set()


def test_clean_move_fires_nothing_and_stays_in_vocab():
    assert detect_positional(_diff()) == set()
    combined = _diff(isolated_pawns=1, king_shield=-2, mobility=-10)
    got = detect_positional(combined)
    assert got == {"structure_damage", "king_shield_weakening", "mobility_collapse"}
    assert got <= POSITIONAL_TAGS
    assert DETECTED <= POSITIONAL_TAGS


def test_bridge_diffs_played_vs_best_and_fires():
    from blunder.featurediff import push_uci

    played_fen = push_uci(FEN_BLACK_TO_MOVE, "g8f6")
    best_fen = push_uci(FEN_BLACK_TO_MOVE, "g8e7")
    # Played move leaves the mover with collapsed mobility and a wrecked shield vs the best move.
    fake = FakeExtractor(
        {
            played_fen: _feat(mobility=4, king_shield=0),
            best_fen: _feat(mobility=14, king_shield=3),
        }
    )
    got = detect_positional_for_move(
        FEN_BLACK_TO_MOVE, "g8f6", "g8e7", mover_white=False, extractor=fake
    )
    assert got == {"mobility_collapse", "king_shield_weakening"}
    assert all(persp is False for _, persp in fake.calls)
