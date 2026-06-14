"""Annotation boundary tests — deterministic parsing/validation/retry, no network."""

import json

import pytest

from blunder.annotation import (
    BATCH_SIZE,
    AnnotationError,
    AnnotationInput,
    annotate_batch,
    build_prompt,
    chunk,
    parse_annotation,
    parse_annotation_array,
    strip_fences,
)


def _obj(desc="left the d-pawn weak", tags=None, counter="best keeps the pawn chain intact"):
    return {
        "description": desc,
        "motif_tags": tags if tags is not None else ["structure_damage"],
        "counterfactual": counter,
    }


def _input(motifs=("structure_damage",)) -> AnnotationInput:
    return AnnotationInput(
        fen="r2q1rk1/pp3ppp/2n1pn2/8/3P4/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1",
        played_san="d5",
        best_line_san=["Re1", "Qc7"],
        delta_cp=180,
        eval_cp=-40,
        detected_motifs=list(motifs),
        archetype="iqp",
        phase="middlegame",
        clock_seconds=160,
    )


class StubProvider:
    """Returns a scripted sequence of completions, one per generate() call."""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]


def test_strip_fences_handles_code_blocks():
    assert strip_fences('```json\n{"a":1}\n```') == '{"a":1}'
    assert strip_fences('```\n[1,2]\n```') == "[1,2]"
    assert strip_fences('{"a":1}') == '{"a":1}'


def test_parse_annotation_valid():
    a = parse_annotation(json.dumps(_obj()))
    assert a.description == "left the d-pawn weak"
    assert a.motif_tags == ["structure_damage"]


def test_parse_rejects_malformed_json():
    with pytest.raises(AnnotationError, match="invalid JSON"):
        parse_annotation("{not json")


def test_parse_rejects_off_vocabulary_tag():
    with pytest.raises(AnnotationError, match="off-vocabulary"):
        parse_annotation(json.dumps(_obj(tags=["structure_damage", "made_up_motif"])))


def test_parse_rejects_missing_fields():
    with pytest.raises(AnnotationError, match="counterfactual"):
        parse_annotation(json.dumps({"description": "x", "motif_tags": []}))


def test_parse_array_validates_count():
    raw = json.dumps([_obj(), _obj()])
    assert len(parse_annotation_array(raw, expected=2)) == 2
    with pytest.raises(AnnotationError, match="expected 3"):
        parse_annotation_array(raw, expected=3)


def test_annotate_batch_happy_path():
    provider = StubProvider("```json\n" + json.dumps([_obj()]) + "\n```")
    out = annotate_batch([_input()], provider)
    assert provider.calls == 1
    assert out[0].motif_tags == ["structure_damage"]


def test_annotate_batch_retries_then_succeeds():
    provider = StubProvider("garbage, not json", json.dumps([_obj(), _obj()]))
    out = annotate_batch([_input(), _input()], provider, retries=1)
    assert provider.calls == 2
    assert len(out) == 2


def test_annotate_batch_raises_after_retries_exhausted():
    provider = StubProvider("nope")
    with pytest.raises(AnnotationError, match="after 2 attempts"):
        annotate_batch([_input()], provider, retries=1)
    assert provider.calls == 2


def test_annotate_batch_empty_is_noop():
    provider = StubProvider("should not be called")
    assert annotate_batch([], provider) == []
    assert provider.calls == 0


def test_build_prompt_grounds_in_data_and_vocabulary():
    prompt = build_prompt([_input(motifs=("structure_damage", "mobility_collapse"))])
    assert "d5" in prompt  # the played move
    assert "structure_damage" in prompt  # detected motif echoed
    assert "back_rank" in prompt  # full controlled vocabulary is listed
    assert "JSON array" in prompt


def test_chunk_splits_by_batch_size():
    items = list(range(BATCH_SIZE * 2 + 3))
    chunks = list(chunk(items))
    assert [len(c) for c in chunks] == [BATCH_SIZE, BATCH_SIZE, 3]
