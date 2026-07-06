# Stage 1: build the React frontend
FROM node:20-slim AS web-builder
WORKDIR /web
RUN npm install -g pnpm
COPY web/package.json web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY web/ ./
RUN pnpm build

# Stage 2: Python runtime
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 gcc && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./
RUN uv sync --frozen || uv sync
COPY --from=web-builder /web/dist ./static
ENV AGENT_KANBAN_STATIC_DIR=/app/static
EXPOSE 7331
CMD ["sh", "-c", "uv run kanban migrate && uv run kanban serve --host 0.0.0.0 --port 7331"]
