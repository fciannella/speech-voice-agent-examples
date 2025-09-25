# Build UI assets
FROM node:18-alpine AS ui-builder

WORKDIR /ui
# Install UI dependencies
COPY examples/voice_agent_webrtc_langgraph/ui/package*.json ./
RUN npm ci --no-audit --no-fund && npm cache clean --force
# Build UI
COPY examples/voice_agent_webrtc_langgraph/ui/ .
RUN npm run build

# Base image
FROM python:3.12-slim

# Environment setup
ENV PYTHONUNBUFFERED=1

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
     LICENSE README.md NVIDIA_PIPECAT.md \
     ./
COPY --chown=user src/ ./src/
COPY --chown=user examples/voice_agent_webrtc_langgraph/ ./examples/voice_agent_webrtc_langgraph/

# Copy built UI into example directory so FastAPI can serve it
COPY --from=ui-builder --chown=user /ui/dist /app/examples/voice_agent_webrtc_langgraph/ui/dist

# Example app directory
WORKDIR /app/examples/voice_agent_webrtc_langgraph

# Dependencies
RUN uv sync --frozen
RUN uv pip install -r agents/requirements.txt
# Ensure langgraph CLI is available at build time
RUN uv pip install -U langgraph
RUN chmod +x start.sh

# Port configuration (single external port for app)
EXPOSE 7860

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s CMD curl -f http://localhost:7860/get_prompt || exit 1

# Start command
CMD ["/app/examples/voice_agent_webrtc_langgraph/start.sh"]


