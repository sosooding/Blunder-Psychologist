"""The controlled motif tag vocabulary.

Two families, matching DESIGN §5. Detectors emit only these tags and the annotation prompt is
constrained to them, so the tag space is closed and the LLM can't invent motifs. Keeping the
vocabulary in one place lets the schema validator reject anything off-list.
"""

# Tactical — read off engine output + board geometry (see ``tactical.py``).
TACTICAL_TAGS = frozenset(
    {
        "hanging_piece",
        "fork",
        "pin",
        "back_rank",
        "overloaded_defender",  # detector TODO — vocabulary reserved
        "missed_break",  # detector TODO — vocabulary reserved
    }
)

# Positional — read off played-vs-best feature diffs (see ``positional.py``).
POSITIONAL_TAGS = frozenset(
    {
        "structure_damage",
        "tension_release",
        "file_concession",
        "diagonal_concession",
        "king_shield_weakening",
        "bad_trade",
        "outpost_concession",
        "mobility_collapse",
        "wrong_pawn_break",
    }
)

ALL_TAGS = TACTICAL_TAGS | POSITIONAL_TAGS

# Lichess puzzle themes → our tactical tags, used to build the benchmark fixtures from the public
# puzzle database (each puzzle is a real-game blunder with theme labels). Only themes that map
# cleanly onto a tag we actually detect are listed.
LICHESS_THEME_MAP = {
    "fork": "fork",
    "pin": "pin",
    "hangingPiece": "hanging_piece",
    "backRankMate": "back_rank",
}
