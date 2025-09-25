# Base image
FROM python:3.12-slim

# Image metadata
LABEL maintainer="NVIDIA"
LABEL description="Speech Planner example"
LABEL version="1.0"

# Environment setup
ENV PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
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
COPY examples/static/ ./examples/static/
COPY examples/speech_planner/ ./examples/speech_planner/

# Example app directory
WORKDIR /app/examples/speech_planner

# Dependencies
RUN uv sync --frozen

# Port configuration
EXPOSE 8100

# Start command
CMD ["uv", "run", "bot.py"]