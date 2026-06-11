FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STOCKFISH_PATH=/usr/local/bin/stockfish

WORKDIR /app

# Toolchain for the native engine module (scikit-build-core + pybind11 compile it from source)
# plus curl/tar for fetching the pinned Stockfish.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned official Stockfish binary — the generic x86-64 build (runs on any 64-bit CPU) with its
# NNUE net embedded. A fixed binary + net is what makes evals reproducible across machines, so
# Phase 1's determinism guarantee holds in CI, in this image, and on the dev host alike.
ARG STOCKFISH_VERSION=sf_18
RUN curl -sSL -o /tmp/sf.tar \
        "https://github.com/official-stockfish/Stockfish/releases/download/${STOCKFISH_VERSION}/stockfish-ubuntu-x86-64.tar" \
    && tar -xf /tmp/sf.tar -C /tmp \
    && install -m 0755 /tmp/stockfish/stockfish-ubuntu-x86-64 /usr/local/bin/stockfish \
    && rm -rf /tmp/sf.tar /tmp/stockfish

# Native analysis engine (blunder_engine). Build it first so this layer caches independently of
# the Python core, and verify it imports inside the image.
COPY engine/ /engine/
RUN pip install --no-cache-dir /engine \
    && python -c "import blunder_engine; print('blunder_engine import OK')"

# Python core (api, worker, job queue, models).
COPY core/ /app/
RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "blunder.worker"]
