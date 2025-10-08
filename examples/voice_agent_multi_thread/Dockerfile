# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD 2-Clause License

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

# Image metadata
LABEL maintainer="NVIDIA"
LABEL description="Voice Agent WebRTC using Langgraph"
LABEL version="1.0"

# Environment setup
ENV PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglx-mesa0 \
    curl \
    ffmpeg \
    git \
    net-tools \
    procps \
    vim \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip uv

# App directory setup
WORKDIR /app

# App files
COPY pyproject.toml uv.lock \
     LICENSE README.md NVIDIA_PIPECAT.md \
     ./
COPY src/ ./src/
COPY examples/voice_agent_webrtc_langgraph/ ./examples/voice_agent_webrtc_langgraph/

# Copy built UI into example directory
COPY --from=ui-builder /ui/dist /app/examples/voice_agent_webrtc_langgraph/ui/dist

# Example app directory
WORKDIR /app/examples/voice_agent_webrtc_langgraph

# Dependencies
RUN uv sync --frozen
# RUN uv sync
# Install all agent requirements recursively into the project's virtual environment
# RUN if [ -d "agents" ]; then \
#     find agents -type f -name "requirements.txt" -print0 | xargs -0 -I {} uv pip install -r "{}"; \
#   fi

RUN uv pip install -r agents/requirements.txt
# Ensure langgraph CLI is available at build time
RUN uv pip install -U langgraph
RUN chmod +x start.sh

# Port configuration
EXPOSE 7860
EXPOSE 9000
EXPOSE 2024

# Healthcheck similar to docker-compose
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s CMD curl -f http://localhost:7860/get_prompt || exit 1

# Start command
CMD ["/app/examples/voice_agent_webrtc_langgraph/start.sh"]