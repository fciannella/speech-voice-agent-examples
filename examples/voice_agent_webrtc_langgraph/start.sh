#!/bin/sh
set -eu

# Default to voice_agent_webrtc_langgraph if EXAMPLE_NAME is not set
EXAMPLE_NAME="${EXAMPLE_NAME:-voice_agent_webrtc_langgraph}"
EXAMPLE_PATH="/app/examples/${EXAMPLE_NAME}"

# Optionally load a local .env next to this example if present
if [ -f "${EXAMPLE_PATH}/.env" ]; then
    # shellcheck disable=SC1091
    set -a
    . "${EXAMPLE_PATH}/.env"
    set +a
fi

# If a remote prompt URL is provided, download it and export ZERO_SHOT_AUDIO_PROMPT
if [ -n "${ZERO_SHOT_AUDIO_PROMPT_URL:-}" ]; then
    case "$ZERO_SHOT_AUDIO_PROMPT_URL" in
        *"github.com"*"/blob"*)
            ZERO_SHOT_AUDIO_PROMPT_URL="${ZERO_SHOT_AUDIO_PROMPT_URL}?raw=1"
            ;;
    esac
    PROMPT_TARGET="${ZERO_SHOT_AUDIO_PROMPT:-${EXAMPLE_PATH}/audio_prompt.wav}"
    mkdir -p "$(dirname "$PROMPT_TARGET")"
    if [ ! -f "$PROMPT_TARGET" ]; then
        echo "Downloading ZERO_SHOT_AUDIO_PROMPT from $ZERO_SHOT_AUDIO_PROMPT_URL"
        if ! curl -fsSL "$ZERO_SHOT_AUDIO_PROMPT_URL" -o "$PROMPT_TARGET"; then
            echo "Failed to download audio prompt from URL: $ZERO_SHOT_AUDIO_PROMPT_URL" >&2
        fi
    fi
    export ZERO_SHOT_AUDIO_PROMPT="$PROMPT_TARGET"
fi

# All dependencies and langgraph CLI are installed at build time

# Start langgraph dev from within the internal agents directory (background)
LANGGRAPH_DIR="${EXAMPLE_PATH}/agents"
LANGGRAPH_PID=""
if [ -d "$LANGGRAPH_DIR" ]; then
    LG_HOST="${LANGGRAPH_HOST:-0.0.0.0}"
    LANGGRAPH_PORT="${LANGGRAPH_PORT:-2024}"
    sh -c "cd \"$LANGGRAPH_DIR\" && exec uv run langgraph dev --no-browser --host \"$LG_HOST\" --port \"$LANGGRAPH_PORT\"" &
    LANGGRAPH_PID=$!
fi

# Run the voice agent app in background
cd "${EXAMPLE_PATH}"
uv run pipeline.py &
PIPELINE_PID=$!

# Wait until the pipeline HTTP endpoint is ready
ATTEMPTS=0
MAX_ATTEMPTS=30
until curl -fsS http://127.0.0.1:7860/get_prompt >/dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
        echo "Pipeline failed to become ready in time" >&2
        wait "$PIPELINE_PID" 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

# Ensure children are terminated when this script exits
cleanup() {
    for p in $PIPELINE_PID $LANGGRAPH_PID; do
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
            kill "$p" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT INT TERM

# Monitor background jobs and exit if any of them exits
while :; do
    for p in $PIPELINE_PID $LANGGRAPH_PID; do
        [ -z "$p" ] && continue
        if ! kill -0 "$p" 2>/dev/null; then
            wait "$p" 2>/dev/null || true
            exit 1
        fi
    done
    sleep 1
done


