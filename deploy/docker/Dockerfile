# Use an official Python runtime as a parent image
FROM python:3.12 AS builder
RUN apt update && apt install -y libgl1-mesa-glx ffmpeg
# RUN apt install gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gobject-introspection libgirepository1.0-dev libgstreamer1.0-dev gstreamer1.0-plugins-base ffmpeg

# Install uv
RUN pip install uv

# Create and set the working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev


# Copy the nvidia_pipecat source code
COPY pyproject.toml uv.lock* README.md ./
COPY ./src/nvidia_pipecat ./src/nvidia_pipecat

# Install dependencies without dev packages and without creating a virtual environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Set environment path to use uv's installed Python packages
ENV PATH="/app/.venv/bin:$PATH"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

