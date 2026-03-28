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

RUN python -m pip install --upgrade pip \
    && python -m pip install -e . \
    && mkdir -p artifacts/models backups docs/results/history \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["cbb"]
CMD ["--help"]
