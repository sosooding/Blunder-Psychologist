FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps: the Stockfish engine + a C++ toolchain for the future native module (Phase 1).
# NOTE: Phase 1 replaces the apt Stockfish with a pinned official binary + NNUE net for
#       cross-machine determinism. apt is fine here because Phase 0 never invokes the engine.
RUN apt-get update && apt-get install -y --no-install-recommends \
        stockfish \
        build-essential \
        cmake \
        git \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY core/ /app/
RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "blunder.worker"]
