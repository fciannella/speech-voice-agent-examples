# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
# OpenAI API key
if [[ -f /secrets/openai_api_key.txt ]]; then
    export OPENAI_API_KEY=$(cat /secrets/openai_api_key.txt)
fi
# NVIDIA API key
if [[ -f /secrets/nvidia_api_key.txt ]]; then
    export NVIDIA_API_KEY=$(cat /secrets/nvidia_api_key.txt)
fi
# ElevenLabs API key
if [[ -f /secrets/elevenlabs_api_key.txt ]]; then
    export ELEVENLABS_API_KEY=$(cat /secrets/elevenlabs_api_key.txt)
fi

if [[ -f /secrets/custom.env ]] ; then
    set -o allexport
    . /secrets/custom.env
    set +o allexport
fi

if [ ! -d "/code" ]; then
    echo "Directory /code not found. Creating it..."
    mkdir -p /code
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create /code directory."
        exit 1
    fi
    chown -R 0:0 /code
fi
# Ensure Python uses the correct module locations
export PYTHONPATH="/code:$PYTHONPATH"
# Access the environment variables
IMAGE_NAME=$IMAGE_NAME
IMAGE_TAG=$IMAGE_TAG
# Combine image name and tag into a sanitized unique identifier
SANITIZED_IMAGE_NAME=$(echo "$IMAGE_NAME" | tr '/' '_')
SANITIZED_IMAGE_TAG=$(echo "$IMAGE_TAG" | tr '/' '_')
IMAGE_IDENTIFIER="${SANITIZED_IMAGE_NAME}_${SANITIZED_IMAGE_TAG}"
INITIALIZED_FILE="/code/.initialized_${IMAGE_IDENTIFIER}"
# Debugging outputs for validation and environment correctness
echo "SANITIZED_IMAGE_NAME: $SANITIZED_IMAGE_NAME"
echo "SANITIZED_IMAGE_TAG: $SANITIZED_IMAGE_TAG"
echo "IMAGE_IDENTIFIER: $IMAGE_IDENTIFIER"
echo "INITIALIZED_FILE: $INITIALIZED_FILE"
echo "PYTHONPATH: $PYTHONPATH"
echo "Running from: $(pwd)"
echo "Contents of /code:"
ls -l /code
# First time setup: Copy files if .initialized for this image and tag doesn't exist
# Check if initialization marker exists
echo "Checking for initialized file: $INITIALIZED_FILE"
if [ ! -f "$INITIALIZED_FILE" ]; then
    echo "First time setup: Copying files..."
    cp -r /app/* /code/
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to copy files from /app to /code."
        exit 1
    fi
    touch "$INITIALIZED_FILE"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create initialized file $INITIALIZED_FILE."
        exit 1
    fi
    # Copy config from mounted volume
    mkdir -p /code/configs
    cp /opt/ext-files/config.yaml /code/configs/config.yaml
    echo "Setup complete for image: $IMAGE_IDENTIFIER"
else
    echo "Setup already initialized for image: $IMAGE_IDENTIFIER"
fi
# Set environment variables for entrypoint
cd /code
export CONFIG_PATH=./configs/config.yaml
export APP_DIR=/code
export PORT=8000

if [ "$DEV" -ne 0 ]; then
    # Avoid to download  the .venv through the ACE Configurator
    rm -rf "$APP_DIR"/.venv
    # launch the command uv sync if a modification is made on the file "pyproject.toml"
    # since the python interpreter launched by uvicorn is under /app/.venv/bin refreshing this venv with uv sync will add the new dependencies available for the interpreter
    # as soon it is restarted by uvicorn
    watchmedo shell-command -R -p "pyproject.toml" -w -c "UV_PROJECT_ENVIRONMENT='/app/.venv' uv sync && touch $APP_DIR/**/*.py 2>/proc/1/fd/2 >/proc/1/fd/2" "$APP_DIR" &
fi
