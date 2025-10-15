# Build argument to specify which example to use
ARG EXAMPLE_NAME=voice_agent_webrtc_langgraph

# Build UI assets
FROM node:18-alpine AS ui-builder
ARG EXAMPLE_NAME

WORKDIR /ui
# Install UI dependencies
COPY examples/${EXAMPLE_NAME}/ui/package*.json ./
RUN npm ci --no-audit --no-fund && npm cache clean --force
# Build UI
COPY examples/${EXAMPLE_NAME}/ui/ .
RUN npm run build

# Base image
FROM python:3.12-slim

# Build argument needs to be repeated in this stage
ARG EXAMPLE_NAME=voice_agent_webrtc_langgraph

# Environment setup
ENV PYTHONUNBUFFERED=1
ENV UV_NO_TRACKED_CACHE=1
ENV EXAMPLE_NAME=${EXAMPLE_NAME}

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglx-mesa0 \
    curl \
    wget \
    ca-certificates \
    ffmpeg \
    git \
    net-tools \
    procps \
    vim \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip uv

# Create non-root user (UID 1000) for provider runtime (container will run as UID 1000 on provider)
RUN useradd -m -u 1000 user
ENV HOME=/home/user
ENV PATH=$HOME/.local/bin:$PATH
ENV XDG_CACHE_HOME=$HOME/.cache

# App directory setup
WORKDIR /app

# App files
COPY --chown=user pyproject.toml uv.lock \
     LICENSE README.md \
     ./
COPY --chown=user src/ ./src/
COPY --chown=user examples/${EXAMPLE_NAME} ./examples/${EXAMPLE_NAME}

# Copy built UI into example directory so FastAPI can serve it
COPY --from=ui-builder --chown=user /ui/dist /app/examples/${EXAMPLE_NAME}/ui/dist

# Example app directory
WORKDIR /app/examples/${EXAMPLE_NAME}

# Dependencies
RUN uv sync --frozen
RUN uv pip install -r agents/requirements.txt
# Ensure langgraph CLI is available at build time
RUN uv pip install -U langgraph
RUN chmod +x start.sh

# Fix ownership so runtime user can read caches and virtualenv
RUN mkdir -p /home/user/.cache/uv \
    && chown -R 1000:1000 /home/user/.cache \
    && if [ -d /app/examples/${EXAMPLE_NAME}/.venv ]; then chown -R 1000:1000 /app/examples/${EXAMPLE_NAME}/.venv; fi

# Port configuration (single external port for app)
EXPOSE 7860

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s CMD curl -f http://localhost:7860/get_prompt || exit 1

# Start command (using sh to expand EXAMPLE_NAME variable)
CMD sh -c "/app/examples/${EXAMPLE_NAME}/start.sh"


