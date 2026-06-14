"""Programmatic motif detection — tactical (engine/board geometry) and positional (feature diffs).

Motifs are detected in code first; the annotation LLM only ever writes the *why* and the
counterfactual, choosing tags from this controlled vocabulary. See ``vocab`` for the tag set.
"""

from .vocab import ALL_TAGS, POSITIONAL_TAGS, TACTICAL_TAGS

__all__ = ["ALL_TAGS", "POSITIONAL_TAGS", "TACTICAL_TAGS"]
