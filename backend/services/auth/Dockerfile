FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM python:3.13.16-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY libs ./libs
COPY services/auth ./services/auth
RUN uv sync --frozen --no-dev --no-editable --package ecommerce-auth-service

FROM python:3.13.16-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /keys \
    && chown app:app /keys
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv/auth
COPY services/auth/alembic.ini ./alembic.ini
COPY services/auth/migrations ./migrations
USER app
EXPOSE 8000
CMD ["python", "-m", "auth"]
