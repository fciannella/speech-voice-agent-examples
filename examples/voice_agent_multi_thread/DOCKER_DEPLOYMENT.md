# Docker Deployment - Multi-Threaded Voice Agent

## Overview

This Docker container runs the complete multi-threaded telco voice agent stack:
- **LangGraph Server** (`langgraph dev`) on port 2024
- **Pipecat Pipeline** (FastAPI + WebRTC) on port 7860
- **React UI** served at `http://localhost:7860`

## Quick Start

### Build the Image

```bash
# From project root
docker build -t voice-agent-multi-thread .
```

### Run the Container

```bash
docker run -p 7860:7860 \
  -e RIVA_API_KEY=your_nvidia_api_key \
  -e NVIDIA_ASR_FUNCTION_ID=52b117d2-6c15-4cfa-a905-a67013bee409 \
  -e NVIDIA_TTS_FUNCTION_ID=4e813649-d5e4-4020-b2be-2b918396d19d \
  voice-agent-multi-thread
```

### Access the UI

Open your browser to: **http://localhost:7860**

## What Happens Inside the Container

The `start.sh` script orchestrates two processes:

### 1. LangGraph Server (Port 2024)
```bash
cd /app/examples/voice_agent_multi_thread/agents
uv run langgraph dev --no-browser --host 0.0.0.0 --port 2024
```

This runs the multi-threaded telco agent with:
- Main thread for long operations
- Secondary thread for interim queries
- Store-based coordination

### 2. Pipecat Pipeline (Port 7860)
```bash
cd /app/examples/voice_agent_multi_thread
uv run pipeline.py
```

This runs the voice pipeline with:
- WebRTC transport
- RIVA ASR (speech-to-text)
- LangGraphLLMService (multi-threaded routing)
- RIVA TTS (text-to-speech)
- React UI

## Environment Variables

### Required

```bash
# NVIDIA API Key for RIVA services
RIVA_API_KEY=nvapi-xxxxx
```

### Optional

```bash
# LangGraph Configuration
LANGGRAPH_HOST=0.0.0.0
LANGGRAPH_PORT=2024
LANGGRAPH_ASSISTANT=telco-agent

# User Configuration
USER_EMAIL=user@example.com

# ASR Configuration
NVIDIA_ASR_FUNCTION_ID=52b117d2-6c15-4cfa-a905-a67013bee409
RIVA_ASR_LANGUAGE=en-US
RIVA_ASR_MODEL=parakeet-1.1b-en-US-asr-streaming-silero-vad-asr-bls-ensemble

# TTS Configuration
NVIDIA_TTS_FUNCTION_ID=4e813649-d5e4-4020-b2be-2b918396d19d
RIVA_TTS_VOICE_ID=Magpie-ZeroShot.Female-1
RIVA_TTS_MODEL=magpie_tts_ensemble-Magpie-ZeroShot
RIVA_TTS_LANGUAGE=en-US

# Zero-shot audio prompt (optional)
ZERO_SHOT_AUDIO_PROMPT_URL=https://github.com/your-repo/audio-prompt.wav

# Multi-threading (default: true)
ENABLE_MULTI_THREADING=true

# Debug
LANGGRAPH_DEBUG_STREAM=false
```

## Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  voice-agent:
    build: .
    ports:
      - "7860:7860"
    environment:
      - RIVA_API_KEY=${RIVA_API_KEY}
      - NVIDIA_ASR_FUNCTION_ID=52b117d2-6c15-4cfa-a905-a67013bee409
      - NVIDIA_TTS_FUNCTION_ID=4e813649-d5e4-4020-b2be-2b918396d19d
      - USER_EMAIL=user@example.com
      - LANGGRAPH_ASSISTANT=telco-agent
      - ENABLE_MULTI_THREADING=true
    volumes:
      # Optional: mount .env file
      - ./examples/voice_agent_multi_thread/.env:/app/examples/voice_agent_multi_thread/.env:ro
      # Optional: persist audio recordings
      - ./audio_dumps:/app/examples/voice_agent_multi_thread/audio_dumps
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7860/get_prompt"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

Run with:
```bash
docker-compose up
```

## Using .env File

Create `.env` in `examples/voice_agent_multi_thread/`:

```bash
# NVIDIA API Keys
RIVA_API_KEY=nvapi-xxxxx

# LangGraph
LANGGRAPH_ASSISTANT=telco-agent
LANGGRAPH_BASE_URL=http://127.0.0.1:2024

# User
USER_EMAIL=test@example.com

# ASR
NVIDIA_ASR_FUNCTION_ID=52b117d2-6c15-4cfa-a905-a67013bee409

# TTS
NVIDIA_TTS_FUNCTION_ID=4e813649-d5e4-4020-b2be-2b918396d19d
RIVA_TTS_VOICE_ID=Magpie-ZeroShot.Female-1
```

The `start.sh` script automatically loads this file.

## Ports

| Service | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------|
| LangGraph Server | 2024 | - | Agent runtime (internal only) |
| Pipecat Pipeline | 7860 | 7860 | WebRTC + HTTP API |
| React UI | - | 7860 | Served by pipeline |

**Note**: Only port 7860 is exposed externally. LangGraph runs internally on 2024.

## Healthcheck

The container includes a healthcheck that verifies the pipeline is responding:

```bash
curl -f http://localhost:7860/get_prompt
```

Check health status:
```bash
docker ps
# Look for "(healthy)" in STATUS column
```

## Logs

View all logs:
```bash
docker logs -f <container-id>
```

You'll see both:
- LangGraph server startup and agent logs
- Pipeline startup and WebRTC connection logs

## Testing Multi-Threading

1. **Open UI**: http://localhost:7860
2. **Select Agent**: Choose "Telco Agent"
3. **Test Long Operation**:
   - Say: *"Close my contract"*
   - Confirm: *"Yes"*
   - Operation starts (50 seconds)
4. **Test Secondary Thread**:
   - While waiting, say: *"What's the status?"*
   - Agent responds with progress
   - Say: *"How much data do I have left?"*
   - Agent answers while main operation continues

## Troubleshooting

### Container won't start
```bash
# Check logs
docker logs <container-id>

# Common issues:
# 1. Missing RIVA_API_KEY
# 2. Port 7860 already in use
# 3. Insufficient memory
```

### LangGraph not starting
```bash
# Check if agents directory exists
docker exec <container-id> ls -la /app/examples/voice_agent_multi_thread/agents

# Check langgraph.json
docker exec <container-id> cat /app/examples/voice_agent_multi_thread/agents/langgraph.json
```

### Pipeline not responding
```bash
# Check pipeline logs
docker logs <container-id> 2>&1 | grep pipeline

# Check if port is accessible
curl http://localhost:7860/get_prompt
```

### Multi-threading not working
```bash
# Verify env var
docker exec <container-id> env | grep MULTI_THREADING

# Check LangGraph server
docker exec <container-id> curl http://localhost:2024/assistants
```

## Development Mode

To develop inside the container:

```bash
# Run with shell
docker run -it -p 7860:7860 \
  -v $(pwd)/examples/voice_agent_multi_thread:/app/examples/voice_agent_multi_thread \
  voice-agent-multi-thread /bin/bash

# Inside container:
cd /app/examples/voice_agent_multi_thread

# Start services manually
cd agents && uv run langgraph dev &
cd .. && uv run pipeline.py
```

## Building for Production

### Multi-stage optimization
The Dockerfile uses a multi-stage build:
1. **ui-builder**: Compiles React UI
2. **python base**: Installs Python dependencies
3. **Final image**: ~2GB (UI + Python + agents)

### Reducing image size
```dockerfile
# Use slim Python base (already done)
FROM python:3.12-slim

# Clean up build artifacts (already done)
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Use uv for faster installs (already done)
RUN pip install uv
```

## Security Considerations

1. **Non-root user**: Container runs as UID 1000
2. **No secrets in image**: Use environment variables or mount secrets
3. **Read-only filesystem**: UI dist is built at image time
4. **Health checks**: Automatic restart on failure

## Performance

- **Startup time**: ~30-60 seconds
- **Memory**: ~2GB recommended
- **CPU**: 2 cores minimum
- **Storage**: ~3GB for image + runtime

## Related Files

- `Dockerfile` - Container definition
- `start.sh` - Startup orchestration
- `agents/langgraph.json` - Agent configuration
- `pipeline.py` - Pipecat pipeline
- `langgraph_llm_service.py` - Multi-threaded LLM service

## Support

For issues:
1. Check logs: `docker logs <container-id>`
2. Verify environment variables
3. Test components individually (LangGraph, Pipeline)
4. Review `PIPECAT_MULTI_THREADING.md` for architecture details



