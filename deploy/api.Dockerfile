FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY backend/requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 infdrawing \
    && useradd --system --uid 10001 --gid infdrawing --home /app infdrawing

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=infdrawing:infdrawing backend/app ./app
COPY --chown=infdrawing:infdrawing backend/migrations ./migrations
COPY --chown=infdrawing:infdrawing backend/alembic.ini ./alembic.ini
COPY --chown=infdrawing:infdrawing scripts/bootstrap_api_key.py ./scripts/bootstrap_api_key.py
COPY --chown=root:root deploy/container_entrypoint.py /usr/local/bin/infdrawing-entrypoint
RUN mkdir -p /app/data/uploads /app/data/outputs /app/data/logs \
    && chown -R infdrawing:infdrawing /app

USER infdrawing
EXPOSE 8000
ENTRYPOINT ["python", "/usr/local/bin/infdrawing-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
