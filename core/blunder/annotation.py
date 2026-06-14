"""Grounded blunder annotation.

The motif detectors already say *what* went wrong (a controlled set of tags). The LLM writes only
what code can't: a one-line *why* and the *counterfactual* (what the better move achieves), as
strict JSON over the same closed tag vocabulary. This is the eval-driven boundary, so the parser is
the part that gets deterministic tests — fence-stripping, malformed output, off-vocabulary tags,
and the retry path — while annotation *quality* is spot-checked, not exact-match tested.

Annotations are batched (one model call per N blunders, for free-tier rate limits) and, once
written, immutable.
"""

import json
import logging
import re
from dataclasses import dataclass

from .motifs.vocab import ALL_TAGS

logger = logging.getLogger("blunder.annotation")

BATCH_SIZE = 8  # blunders per model call — within free-tier limits, see DESIGN §5

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class AnnotationError(ValueError):
    """The model output could not be parsed into a valid annotation."""


@dataclass
class AnnotationInput:
    fen: str
    played_san: str
    best_line_san: list[str]
    delta_cp: int
    eval_cp: int
    detected_motifs: list[str]  # tags the deterministic detectors already fired
    archetype: str
    phase: str
    clock_seconds: int | None = None


@dataclass
class Annotation:
    description: str
    motif_tags: list[str]
    counterfactual: str


def strip_fences(raw: str) -> str:
    """Remove a leading ```/```json and a trailing ``` fence the model may wrap JSON in."""
    out = _FENCE.sub("", raw.strip())
    return _FENCE.sub("", out).strip()


def _validate(obj: object) -> Annotation:
    if not isinstance(obj, dict):
        raise AnnotationError(f"expected a JSON object, got {type(obj).__name__}")
    desc = obj.get("description")
    tags = obj.get("motif_tags")
    counter = obj.get("counterfactual")
    if not isinstance(desc, str) or not desc.strip():
        raise AnnotationError("missing/empty 'description'")
    if not isinstance(counter, str) or not counter.strip():
        raise AnnotationError("missing/empty 'counterfactual'")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise AnnotationError("'motif_tags' must be a list of strings")
    unknown = [t for t in tags if t not in ALL_TAGS]
    if unknown:
        raise AnnotationError(f"off-vocabulary motif tags: {unknown}")
    return Annotation(description=desc.strip(), motif_tags=tags, counterfactual=counter.strip())


def parse_annotation(raw: str) -> Annotation:
    """Parse one model completion into a validated ``Annotation`` (raises ``AnnotationError``)."""
    text = strip_fences(raw)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnnotationError(f"invalid JSON: {exc}") from exc
    return _validate(obj)


def parse_annotation_array(raw: str, expected: int) -> list[Annotation]:
    """Parse a JSON array of annotations (the batched form), validating count and each item."""
    text = strip_fences(raw)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnnotationError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, list):
        raise AnnotationError(f"expected a JSON array, got {type(obj).__name__}")
    if len(obj) != expected:
        raise AnnotationError(f"expected {expected} annotations, got {len(obj)}")
    return [_validate(item) for item in obj]


def _format_blunder(i: int, b: AnnotationInput) -> str:
    line = " ".join(b.best_line_san) or "(none)"
    clock = f"{b.clock_seconds}s" if b.clock_seconds is not None else "n/a"
    return (
        f"[{i}] fen={b.fen} phase={b.phase} archetype={b.archetype}\n"
        f"    played={b.played_san} eval_after={b.eval_cp}cp lost={b.delta_cp}cp clock={clock}\n"
        f"    best_line={line}\n"
        f"    detected_motifs={b.detected_motifs or '[]'}"
    )


def build_prompt(batch: list[AnnotationInput]) -> str:
    """Build the batched prompt — strict JSON-array out, tags from the closed vocabulary."""
    vocab = ", ".join(sorted(ALL_TAGS))
    blunders = "\n".join(_format_blunder(i, b) for i, b in enumerate(batch))
    return (
        "You are a chess analyst. For each numbered blunder below, write a terse, factual "
        "annotation grounded ONLY in the given data (do not invent lines or evaluations).\n\n"
        "Return a JSON array with one object per blunder, in order, each exactly:\n"
        '  {"description": str, "motif_tags": [str], "counterfactual": str}\n'
        "- description: one sentence on why the played move is worse than the best line.\n"
        "- counterfactual: one sentence on what the best line achieves instead.\n"
        f"- motif_tags: choose ONLY from this fixed vocabulary: {vocab}. Include the "
        "detected_motifs and add any others clearly supported by the data.\n"
        "Output the JSON array and nothing else.\n\n"
        f"{blunders}"
    )


def annotate_batch(
    batch: list[AnnotationInput],
    provider,
    *,
    retries: int = 1,
) -> list[Annotation]:
    """Annotate a batch in one model call; on a parse failure, retry with a stricter nudge."""
    if not batch:
        return []
    base = build_prompt(batch)
    strict = base + "\n\nReturn ONLY the JSON array, no prose."
    last_error: AnnotationError | None = None
    for attempt in range(retries + 1):
        text = provider.generate(base if attempt == 0 else strict)
        try:
            return parse_annotation_array(text, len(batch))
        except AnnotationError as exc:
            last_error = exc
            logger.warning("annotation parse failed (attempt %d): %s", attempt + 1, exc)
    raise AnnotationError(f"annotation failed after {retries + 1} attempts: {last_error}")


def chunk(items: list, size: int = BATCH_SIZE):
    """Yield successive ``size``-length chunks (one model call each)."""
    for i in range(0, len(items), size):
        yield items[i : i + size]
