"""Lazy, process-wide singletons for the heavy Phase-4 collaborators.

The engine feature extractor and the embedding model are expensive to construct (wheel import /
~130 MB ONNX load), so we build them once per process and reuse. The LLM provider is cheap (just
config), so it is rebuilt per call. Tests never touch these — they inject fakes directly.
"""

from .embed import Embedder
from .engine import FeatureExtractor
from .llm import LLMProvider, build_provider

_extractor: FeatureExtractor | None = None
_embedder: Embedder | None = None


def extractor() -> FeatureExtractor:
    global _extractor
    if _extractor is None:
        from .engine import EngineFeatureExtractor

        _extractor = EngineFeatureExtractor()
    return _extractor


def embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        from .embed import FastEmbedder

        _embedder = FastEmbedder()
    return _embedder


def provider() -> LLMProvider:
    return build_provider()
