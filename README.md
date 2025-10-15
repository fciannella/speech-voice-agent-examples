---
title: Voice Agent WebRTC + LangGraph
emoji: 🎙️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
suggested_hardware: t4-small
short_description: Complete voice agent stack with LangGraph, Pipecat, WebRTC, ASR, and TTS
---

# Voice Agent WebRTC + LangGraph (Quick Start)

This repository includes a complete voice agent stack:
- LangGraph dev server for local agents
- Pipecat-based speech pipeline (WebRTC, ASR, LangGraph LLM adapter, TTS)
- Static UI you can open in a browser

Primary example: `examples/voice_agent_webrtc_langgraph/`


## 1) Mandatory environment variables
Create `.env` in `examples/voice_agent_webrtc_langgraph/` (copy from `env.example`) and set at least:

- `RIVA_API_KEY` or `NVIDIA_API_KEY`: required for NVIDIA NIM-hosted Riva ASR/TTS
- `LANGGRAPH_BASE_URL` (default `http://127.0.0.1:2024`)
- `LANGGRAPH_ASSISTANT` (default `ace-base-agent`)
- `USER_EMAIL` (e.g. `test@example.com`)
- `LANGGRAPH_STREAM_MODE` (default `values`)
- `LANGGRAPH_DEBUG_STREAM` (default `true`)

Optional but useful:
- `RIVA_ASR_LANGUAGE` (default `en-US`)
- `RIVA_TTS_LANGUAGE` (default `en-US`)
- `RIVA_TTS_VOICE_ID` (e.g. `Magpie-ZeroShot.Female-1`)
- `RIVA_TTS_MODEL` (e.g. `magpie_tts_ensemble-Magpie-ZeroShot`)
- `ZERO_SHOT_AUDIO_PROMPT` if using Magpie Zero‑shot with a custom audio prompt
- `ZERO_SHOT_AUDIO_PROMPT_URL` to auto-download prompt on startup
- `ENABLE_SPECULATIVE_SPEECH` (default `true`)
- `LANGGRAPH_AUTH_TOKEN` (or `AUTH0_ACCESS_TOKEN`/`AUTH_BEARER_TOKEN`) if your LangGraph server requires auth
- TURN/Twilio for WebRTC if needed: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, or `TURN_SERVER_URL`, `TURN_USERNAME`, `TURN_PASSWORD`


## 2) What it does
- Starts LangGraph dev server serving agents from `examples/voice_agent_webrtc_langgraph/agents/`.
- Starts the Pipecat pipeline (`pipeline.py`) exposing:
  - HTTP: `http://<host>:7860` (health, RTC config)
  - WebSocket: `ws://<host>:7860/ws` (audio + transcripts)
  - Static UI: `http://<host>:7860/` (served by FastAPI)

Defaults:
- ASR: NVIDIA Riva (NIM) via `RIVA_API_KEY` and built-in `NVIDIA_ASR_FUNCTION_ID`
- LLM: LangGraph adapter, streaming from the selected assistant
- TTS: NVIDIA Riva Magpie (NIM) via `RIVA_API_KEY` and built-in `NVIDIA_TTS_FUNCTION_ID`


## 3) Run

### Option A: Docker (recommended)
From `examples/voice_agent_webrtc_langgraph/`:

```bash
docker compose up --build -d
```

Then open `http://<machine-ip>:7860/`.

Chrome on http origins: enable "Insecure origins treated as secure" at `chrome://flags/` and add `http://<machine-ip>:7860`.

#### Building for Different Examples
The Dockerfile in the repository root is generalized to work with any example. Use the `EXAMPLE_NAME` build argument to specify which example to use:

**For voice_agent_webrtc_langgraph (default):**
```bash
docker build --build-arg EXAMPLE_NAME=voice_agent_webrtc_langgraph -t my-voice-agent .
docker run -p 7860:7860 --env-file examples/voice_agent_webrtc_langgraph/.env my-voice-agent
```

**For voice_agent_multi_thread:**
```bash
docker build --build-arg EXAMPLE_NAME=voice_agent_multi_thread -t my-voice-agent .
docker run -p 7860:7860 --env-file examples/voice_agent_multi_thread/.env my-voice-agent
```

The Dockerfile will automatically:
- Build the UI for the specified example
- Copy only the files for that example
- Set up the correct working directory
- Configure the start script to run the correct example

**Note:** The UI is served on the same port as the API (7860). The FastAPI app serves both the WebSocket/HTTP endpoints and the static UI files.

### Option B: Python (local)
Requires Python 3.12 and `uv`.

```bash
cd examples/voice_agent_webrtc_langgraph
uv run pipeline.py
```
Then start the UI from `ui/` (see `examples/voice_agent_webrtc_langgraph/ui/README.md`).


## 4) Swap TTS providers (Magpie ⇄ ElevenLabs)
The default TTS in `examples/voice_agent_webrtc_langgraph/pipeline.py` is NVIDIA Riva Magpie via NIM:

```python
from nvidia_pipecat.services.riva_speech import RivaTTSService

tts = RivaTTSService(
    api_key=os.getenv("RIVA_API_KEY"),
    function_id=os.getenv("NVIDIA_TTS_FUNCTION_ID", "4e813649-d5e4-4020-b2be-2b918396d19d"),
    voice_id=os.getenv("RIVA_TTS_VOICE_ID", "Magpie-ZeroShot.Female-1"),
    model=os.getenv("RIVA_TTS_MODEL", "magpie_tts_ensemble-Magpie-ZeroShot"),
    language=os.getenv("RIVA_TTS_LANGUAGE", "en-US"),
    zero_shot_audio_prompt_file=(
        Path(os.getenv("ZERO_SHOT_AUDIO_PROMPT")) if os.getenv("ZERO_SHOT_AUDIO_PROMPT") else None
    ),
)
```

To use ElevenLabs instead:
1) Ensure ElevenLabs support is available (included via project deps).
2) Set environment:
   - `ELEVENLABS_API_KEY`
   - Optionally `ELEVENLABS_VOICE_ID` and any model-specific settings
3) Edit `examples/voice_agent_webrtc_langgraph/pipeline.py` to import and construct ElevenLabs TTS:

```python
from nvidia_pipecat.services.elevenlabs import ElevenLabsTTSServiceWithEndOfSpeech

# Replace the RivaTTSService(...) block with:
tts = ElevenLabsTTSServiceWithEndOfSpeech(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
    voice_id=os.getenv("ELEVENLABS_VOICE_ID", "Rachel"),
    sample_rate=16000,
    channels=1,
)
```

No other pipeline changes are required; transcript synchronization supports ElevenLabs end‑of‑speech events.

Notes for Magpie Zero‑shot:
- Set `RIVA_TTS_VOICE_ID` like `Magpie-ZeroShot.Female-1` and `RIVA_TTS_MODEL` like `magpie_tts_ensemble-Magpie-ZeroShot`.
- If using a custom voice prompt, mount it via `docker-compose.yml` and set `ZERO_SHOT_AUDIO_PROMPT`, or set `ZERO_SHOT_AUDIO_PROMPT_URL` to auto-download on startup.


## 5) Troubleshooting
- Healthcheck: `curl -f http://localhost:7860/get_prompt`
- If the UI can't access the mic on http, use the Chrome flag above or host the UI via HTTPS.
- For NAT/firewall issues, configure TURN or provide Twilio credentials.


## 6) Multi-threaded Voice Agent (voice_agent_multi_thread)

The `voice_agent_multi_thread` example includes a non-blocking multi-threaded agent implementation that allows users to continue conversing while long-running operations execute in the background.

### Build the Docker image:
```bash
docker build --build-arg EXAMPLE_NAME=voice_agent_multi_thread -t voice-agent-multi-thread .
```

### Run the container:
```bash
docker run -d --name voice-agent-multi-thread \
  -p 2024:2024 \
  -p 7862:7860 \
  --env-file examples/voice_agent_multi_thread/.env \
  voice-agent-multi-thread
```

Then access:
- **LangGraph API**: `http://localhost:2024`
- **Web UI**: `http://localhost:7862`
- **Pipeline WebSocket**: `ws://localhost:7862/ws`

The multi-threaded agent automatically enables for `telco-agent` and `wire-transfer-agent`, allowing the secondary thread to handle status checks and interim conversations while the main thread processes long-running tools.

### Stop and remove the container:
```bash
docker stop voice-agent-multi-thread && docker rm voice-agent-multi-thread
```


## 7) Manual Docker Commands (voice_agent_webrtc_langgraph)

If you prefer manual Docker commands instead of docker-compose:

```bash
docker build -t ace-voice-webrtc:latest \
  -f examples/voice_agent_webrtc_langgraph/Dockerfile \
  .

docker run --name ace-voice-webrtc -d \
  -p 7860:7860 \
  -p 2024:2024 \
  --env-file examples/voice_agent_webrtc_langgraph/.env \
  -e LANGGRAPH_ASSISTANT=healthcare-agent \
  ace-voice-webrtc:latest
```