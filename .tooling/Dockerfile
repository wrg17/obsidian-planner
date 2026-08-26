# The planner API and MCP server.
#
# The vault is NOT copied in. It is a directory of markdown that Obsidian edits on the
# host, continuously, and a copy would be a second source of truth that diverges the
# moment either side writes. It is bind-mounted at /vault instead, and the container is
# one more writer alongside Obsidian -- which is the same position the local process is
# in, and why the journal and its conflict handling exist.

FROM python:3.13-slim AS build

# Build deps for anything without a wheel. Dropped from the final image.
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
COPY src ./src

# Install into a virtualenv we can copy wholesale, so the runtime image carries no
# build tooling and no pip cache.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir ".[api,postgres,mcp]"


FROM python:3.13-slim AS runtime

# libpq for psycopg. The binary wheel bundles it, but installing it here means the
# image still works if that ever changes.
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLANNER_VAULT=/vault

# Non-root. The uid is a build arg because a bind-mounted vault on Linux keeps host
# ownership: files the container writes land as this uid, and if it does not match the
# person editing in Obsidian they end up with notes they cannot edit. Docker Desktop on
# macOS maps ownership for you, so the default is only wrong on Linux -- pass
# --build-arg UID=$(id -u) there.
ARG UID=1000
ARG GID=1000
RUN groupadd -g "$GID" planner \
    && useradd -m -u "$UID" -g "$GID" planner
USER planner

WORKDIR /vault

EXPOSE 8000

# Checks the app, not just the port: /health reports whether the vault is reachable,
# which is the failure this container is most likely to have -- a missing or misspelled
# bind mount looks exactly like a healthy server otherwise.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health | grep -q '"status":"ok"' || exit 1

CMD ["uvicorn", "planner.api:app", "--host", "0.0.0.0", "--port", "8000"]
