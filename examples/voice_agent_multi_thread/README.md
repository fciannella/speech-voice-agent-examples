# Voice Agent WebRTC + LangGraph (Quick Start)

This example launches a complete voice agent stack:
- LangGraph dev server for local agents
- Pipecat-based speech pipeline (WebRTC, ASR, LLM adapter, TTS)
- Static UI you can open in a browser


## 1) Mandatory environment variables
Create `.env` next to this README (or copy from `env.example`) and set at least:

- `NVIDIA_API_KEY` or `RIVA_API_KEY`: required for NVIDIA NIM-hosted Riva ASR/TTS
- `USE_LANGGRAPH=true`: enable LangGraph-backed LLM
- `LANGGRAPH_BASE_URL` (default `http://127.0.0.1:2024`)
- `LANGGRAPH_ASSISTANT` (default `ace-base-agent`)
- `USER_EMAIL` (any email for routing, e.g. `test@example.com`)
- `LANGGRAPH_STREAM_MODE` (default `values`)
- `LANGGRAPH_DEBUG_STREAM` (default `true`)

Optional but commonly used:
- `RIVA_ASR_LANGUAGE` (default `en-US`)
- `RIVA_TTS_LANGUAGE` (default `en-US`)
- `RIVA_TTS_VOICE_ID` (e.g. `Magpie-ZeroShot.Female-1`)
- `RIVA_TTS_MODEL` (e.g. `magpie_tts_ensemble-Magpie-ZeroShot`)
- `ZERO_SHOT_AUDIO_PROMPT` if using Magpie Zero‑shot and a custom voice prompt
- `ZERO_SHOT_AUDIO_PROMPT_URL` to auto-download prompt on startup
- `ENABLE_SPECULATIVE_SPEECH` (default `true`)
- TURN/Twilio for WebRTC if needed: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, or `TURN_SERVER_URL`, `TURN_USERNAME`, `TURN_PASSWORD`


## 2) What it does
- Starts LangGraph dev server to serve local agents from `agents/`.
- Starts the Pipecat pipeline (`pipeline.py`) exposing:
  - HTTP: `http://<host>:7860` (health and RTC config)
  - WebSocket: `ws://<host>:7860/ws` for audio and transcripts
- Serves the built UI at `http://<host>:9000/` (via the container).

By default it uses:
- ASR: NVIDIA Riva (NIM) with `RIVA_API_KEY` and `NVIDIA_ASR_FUNCTION_ID`
- LLM: LangGraph adapter streaming from the selected assistant
- TTS: NVIDIA Riva Magpie (NIM) with `RIVA_API_KEY` and `NVIDIA_TTS_FUNCTION_ID`


## 3) Run

### Option A: Docker (recommended)
From this directory:

```bash
docker compose up --build -d
```

Then open `http://<machine-ip>:9000/`.

Chrome on http origins: enable “Insecure origins treated as secure” at `chrome://flags/` and add `http://<machine-ip>:9000`.

### Option B: Python (local)
Requires Python 3.12 and `uv`.

```bash
uv run pipeline.py
```
Then start the UI from `ui/` (see `ui/README.md`).


## 4) Swap TTS providers (Magpie ⇄ ElevenLabs)
The default TTS in `pipeline.py` is NVIDIA Riva Magpie via NIM:

```startLine:endLine:examples/voice_agent_webrtc_langgraph/pipeline.py
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
1) Ensure `pipecat` ElevenLabs dependency is available (already included via project deps).
2) Set environment:
   - `ELEVENLABS_API_KEY`
   - Optionally `ELEVENLABS_VOICE_ID` and model settings supported by ElevenLabs
3) Change the TTS construction in `pipeline.py` to use `ElevenLabsTTSServiceWithEndOfSpeech`:

```python
from nvidia_pipecat.services.elevenlabs import ElevenLabsTTSServiceWithEndOfSpeech

# Replace RivaTTSService(...) with:
tts = ElevenLabsTTSServiceWithEndOfSpeech(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
    voice_id=os.getenv("ELEVENLABS_VOICE_ID", "Rachel"),
    sample_rate=16000,
    channels=1,
)
```

That’s it. No other pipeline changes are required. The transcript synchronization already supports ElevenLabs end‑of‑speech events.

Notes for Magpie Zero‑shot:
- Provide `RIVA_TTS_VOICE_ID` like `Magpie-ZeroShot.Female-1` and `RIVA_TTS_MODEL` like `magpie_tts_ensemble-Magpie-ZeroShot`.
- If using a custom voice prompt, mount it via `docker-compose.yml` and set `ZERO_SHOT_AUDIO_PROMPT`. You can also set `ZERO_SHOT_AUDIO_PROMPT_URL` to auto-download at startup.


## 5) Troubleshooting
- Healthcheck: `curl -f http://localhost:7860/get_prompt`
- If UI can’t access mic on http, use Chrome flag above or host UI via HTTPS.
- For NAT/firewall issues, configure TURN or Twilio credentials.

