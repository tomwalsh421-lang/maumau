FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql
COPY data ./data
COPY docs/results ./docs/results
COPY artifacts/models ./artifacts/models

RUN python -m pip install --upgrade pip \
    && python -m pip install -e . \
    && mkdir -p artifacts/models backups docs/results/history \
    && groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser \
    && chown -R 1000:1000 /app

USER 1000:1000

ENTRYPOINT ["cbb"]
CMD ["--help"]
