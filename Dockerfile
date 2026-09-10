# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# Слой зависимостей — кешируется, пока не поменялся uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Проект + контент
COPY README.md ./
COPY prompts ./prompts
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --system --create-home app && chown -R app:app /app
USER app

CMD ["bot"]
