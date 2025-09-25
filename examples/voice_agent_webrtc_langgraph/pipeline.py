# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD 2-Clause License

"""Voice Agent WebRTC Pipeline.

This module implements a voice agent pipeline using WebRTC for real-time
speech-to-speech communication with dynamic prompt support.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import InputAudioRawFrame, LLMMessagesFrame, TTSAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport
from pipecat.transports.network.webrtc_connection import (
    IceServer,
    SmallWebRTCConnection,
)
from websocket_transcript_output import WebsocketTranscriptOutput

from nvidia_pipecat.processors.audio_util import AudioRecorder
from nvidia_pipecat.processors.nvidia_context_aggregator import (
    NvidiaTTSResponseCacher,
    create_nvidia_context_aggregator,
)
from nvidia_pipecat.processors.transcript_synchronization import (
    BotTranscriptSynchronization,
    UserTranscriptSynchronization,
)
from nvidia_pipecat.services.riva_speech import RivaASRService, RivaTTSService
from langgraph_llm_service import LangGraphLLMService

load_dotenv(override=True)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store connections by pc_id
pcs_map: dict[str, SmallWebRTCConnection] = {}
contexts_map: dict[str, OpenAILLMContext] = {}


ice_servers = (
    [
        IceServer(
            urls=os.getenv("TURN_SERVER_URL", ""),
            username=os.getenv("TURN_USERNAME", ""),
            credential=os.getenv("TURN_PASSWORD", ""),
        )
    ]
    if os.getenv("TURN_SERVER_URL")
    else []
)


@app.get("/assistants")
async def list_assistants(request: Request):
    """Return a list of assistants from LangGraph, with robust fallbacks.

    Output: List of {assistant_id, graph_id?, name?, description?, display_name}.
    """
    import requests

    base_url = os.getenv("LANGGRAPH_BASE_URL", "http://127.0.0.1:2024").rstrip("/")

    inbound_auth = request.headers.get("authorization")
    token = os.getenv("LANGGRAPH_AUTH_TOKEN") or os.getenv("AUTH0_ACCESS_TOKEN") or os.getenv("AUTH_BEARER_TOKEN")
    headers = {"Authorization": inbound_auth} if inbound_auth else ({"Authorization": f"Bearer {token}"} if token else None)

    def normalize_entries(raw_items: list) -> list[dict]:
        results: list[dict] = []
        for entry in raw_items:
            assistant_id = None
            if isinstance(entry, dict):
                assistant_id = entry.get("assistant_id") or entry.get("id") or entry.get("name")
            elif isinstance(entry, str):
                assistant_id = entry
            if not assistant_id:
                continue
            results.append({"assistant_id": assistant_id, **(entry if isinstance(entry, dict) else {})})
        return results

    # Try GET /assistants first (newer servers)
    items: list[dict] = []
    try:
        get_resp = requests.get(f"{base_url}/assistants", params={"limit": 100}, timeout=8, headers=headers)
        if get_resp.ok:
            data = get_resp.json() or []
            if isinstance(data, dict):
                data = data.get("items") or data.get("results") or data.get("assistants") or []
            items = normalize_entries(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"GET /assistants failed: {exc}")

    # Fallback: POST /assistants/search (older servers)
    if not items:
        try:
            search_resp = requests.post(
                f"{base_url}/assistants/search",
                json={
                    "metadata": {},
                    "limit": 100,
                    "offset": 0,
                    "sort_by": "assistant_id",
                    "sort_order": "asc",
                    "select": ["assistant_id"],
                },
                timeout=10,
                headers=headers,
            )
            if search_resp.ok:
                data = search_resp.json() or []
                if isinstance(data, dict):
                    data = data.get("items") or data.get("results") or []
                items = normalize_entries(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"POST /assistants/search failed: {exc}")

    # Best-effort: enrich with details when possible
    enriched: list[dict] = []
    for item in items:
        detail = dict(item)
        assistant_id = detail.get("assistant_id")
        if assistant_id:
            try:
                detail_resp = requests.get(f"{base_url}/assistants/{assistant_id}", timeout=5, headers=headers)
                if detail_resp.ok:
                    d = detail_resp.json() or {}
                    detail.update(
                        {
                            "graph_id": d.get("graph_id"),
                            "name": d.get("name"),
                            "description": d.get("description"),
                            "metadata": d.get("metadata") or {},
                        }
                    )
            except Exception:
                pass
        md = (detail.get("metadata") or {}) if isinstance(detail.get("metadata"), dict) else {}
        display_name = (
            detail.get("name")
            or md.get("display_name")
            or md.get("friendly_name")
            or detail.get("graph_id")
            or detail.get("assistant_id")
        )
        detail["display_name"] = display_name
        enriched.append(detail)

    # Final fallback: read local graphs from agents/langgraph.json
    if not enriched:
        try:
            config_path = Path(__file__).parent / "agents" / "langgraph.json"
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f) or {}
            graphs = (cfg.get("graphs") or {}) if isinstance(cfg, dict) else {}
            for graph_id in graphs.keys():
                enriched.append({
                    "assistant_id": graph_id,
                    "graph_id": graph_id,
                    "display_name": graph_id,
                })
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to read local agents/langgraph.json: {exc}")

    return enriched

async def run_bot(webrtc_connection, ws: WebSocket, assistant_override: str | None = None):
    """Run the voice agent bot with WebRTC connection and WebSocket.

    Args:
        webrtc_connection: The WebRTC connection for audio streaming
        ws: WebSocket connection for communication
    """
    stream_id = uuid.uuid4()
    transport_params = TransportParams(
        audio_in_enabled=True,
        audio_in_sample_rate=16000,
        audio_out_sample_rate=16000,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
        audio_out_10ms_chunks=5,
    )

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=transport_params,
    )

    selected_assistant = assistant_override or os.getenv("LANGGRAPH_ASSISTANT", "ace-base-agent")
    logger.info(f"Using LangGraph assistant: {selected_assistant}")

    llm = LangGraphLLMService(
        base_url=os.getenv("LANGGRAPH_BASE_URL", "http://127.0.0.1:2024"),
        assistant=selected_assistant,
        user_email=os.getenv("USER_EMAIL", "test@example.com"),
        stream_mode=os.getenv("LANGGRAPH_STREAM_MODE", "values"),
        debug_stream=os.getenv("LANGGRAPH_DEBUG_STREAM", "false").lower() == "true",
    )



    # stt = RivaASRService(
    #     server=os.getenv("RIVA_ASR_URL", "localhost:50051"),
    #     api_key=os.getenv("NVIDIA_API_KEY"),
    #     language=os.getenv("RIVA_ASR_LANGUAGE", "en-US"),
    #     sample_rate=16000,
    #     model=os.getenv("RIVA_ASR_MODEL", "parakeet-1.1b-en-US-asr-streaming-silero-vad-asr-bls-ensemble"),
    # )

    stt = RivaASRService(
        # server=os.getenv("RIVA_ASR_URL", "localhost:50051"), # default url is grpc.nvcf.nvidia.com:443
        api_key=os.getenv("RIVA_API_KEY"),
        function_id=os.getenv("NVIDIA_ASR_FUNCTION_ID", "52b117d2-6c15-4cfa-a905-a67013bee409"),
        language=os.getenv("RIVA_ASR_LANGUAGE", "en-US"),
        sample_rate=16000,
        model=os.getenv("RIVA_ASR_MODEL", "parakeet-1.1b-en-US-asr-streaming-silero-vad-asr-bls-ensemble"),
    )

    # stt = RivaASRService(
    #     server=os.getenv("RIVA_ASR_URL", "localhost:50051"),
    #     api_key=os.getenv("NVIDIA_API_KEY"),
    #     language=os.getenv("RIVA_ASR_LANGUAGE", "en-US"),
    #     sample_rate=16000,
    #     model=os.getenv("RIVA_ASR_MODEL", "parakeet-1.1b-en-US-asr-streaming-silero-vad-asr-bls-ensemble"),
    # )

    # Load IPA dictionary with error handling
    ipa_file = Path(__file__).parent / "ipa.json"
    try:
        with open(ipa_file, encoding="utf-8") as f:
            ipa_dict = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"IPA dictionary file not found at {ipa_file}")
        raise FileNotFoundError(f"IPA dictionary file not found at {ipa_file}") from e
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in IPA dictionary file: {e}")
        raise ValueError(f"Invalid JSON in IPA dictionary file: {e}") from e
    except Exception as e:
        logger.error(f"Error loading IPA dictionary: {e}")
        raise

    tts = RivaTTSService(
        # server=os.getenv("RIVA_TTS_URL", "localhost:50051"), # default url is grpc.nvcf.nvidia.com:443
        api_key=os.getenv("RIVA_API_KEY"),
        function_id=os.getenv("NVIDIA_TTS_FUNCTION_ID", "4e813649-d5e4-4020-b2be-2b918396d19d"),
        voice_id=os.getenv("RIVA_TTS_VOICE_ID", "Magpie-ZeroShot.Female-1"),
        model=os.getenv("RIVA_TTS_MODEL", "magpie_tts_ensemble-Magpie-ZeroShot"),
        language=os.getenv("RIVA_TTS_LANGUAGE", "en-US"),
        zero_shot_audio_prompt_file=(
            Path(os.getenv("ZERO_SHOT_AUDIO_PROMPT")) if os.getenv("ZERO_SHOT_AUDIO_PROMPT") else None
        ),
    )

    # tts = RivaTTSService(
    #     server=os.getenv("RIVA_TTS_URL", "localhost:50051"),
    #     api_key=os.getenv("NVIDIA_API_KEY"),
    #     voice_id=os.getenv("RIVA_TTS_VOICE_ID", "Magpie-ZeroShot.Female-1"),
    #     model=os.getenv("RIVA_TTS_MODEL", "magpie_tts_ensemble-Magpie-ZeroShot"),
    #     language=os.getenv("RIVA_TTS_LANGUAGE", "en-US"),
    #     zero_shot_audio_prompt_file=(
    #         Path(os.getenv("ZERO_SHOT_AUDIO_PROMPT", str(Path(__file__).parent / "model-em_sample-02.wav")))
    #         if os.getenv("ZERO_SHOT_AUDIO_PROMPT")
    #         else None
    #     ),
    #     ipa_dict=ipa_dict,
    # )

    # Create audio_dumps directory if it doesn't exist
    audio_dumps_dir = Path(__file__).parent / "audio_dumps"
    audio_dumps_dir.mkdir(exist_ok=True)

    asr_recorder = AudioRecorder(
        output_file=str(audio_dumps_dir / f"asr_recording_{stream_id}.wav"),
        params=transport_params,
        frame_type=InputAudioRawFrame,
    )

    tts_recorder = AudioRecorder(
        output_file=str(audio_dumps_dir / f"tts_recording_{stream_id}.wav"),
        params=transport_params,
        frame_type=TTSAudioRawFrame,
    )

    # Used to synchronize the user and bot transcripts in the UI
    stt_transcript_synchronization = UserTranscriptSynchronization()
    tts_transcript_synchronization = BotTranscriptSynchronization()

    # Start with empty context; LangGraph agent manages prompts and policy
    context = OpenAILLMContext([])

    # Store context globally so WebSocket can access it
    pc_id = webrtc_connection.pc_id
    contexts_map[pc_id] = context

    # Configure speculative speech processing based on environment variable
    enable_speculative_speech = os.getenv("ENABLE_SPECULATIVE_SPEECH", "true").lower() == "true"

    if enable_speculative_speech:
        context_aggregator = create_nvidia_context_aggregator(context, send_interims=True)
        tts_response_cacher = NvidiaTTSResponseCacher()
    else:
        context_aggregator = llm.create_context_aggregator(context)
        tts_response_cacher = None

    transcript_processor_output = WebsocketTranscriptOutput(ws)

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            asr_recorder,
            stt,  # Speech-To-Text
            stt_transcript_synchronization,
            context_aggregator.user(),
            llm,  # LLM
            tts,  # Text-To-Speech
            tts_recorder,
            *([tts_response_cacher] if tts_response_cacher else []),  # Include cacher only if enabled
            tts_transcript_synchronization,
            transcript_processor_output,
            transport.output(),  # Websocket output to client
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
            send_initial_empty_metrics=True,
            start_metadata={"stream_id": stream_id},
        ),
    )

    # No auto-kickoff; LangGraph determines when/how to greet

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for handling voice agent connections.

    Args:
        websocket: The WebSocket connection to handle
    """
    await websocket.accept()
    try:
        request = await websocket.receive_json()
        pc_id = request.get("pc_id")
        assistant_from_client = request.get("assistant")

        if pc_id and pc_id in pcs_map:
            pipecat_connection = pcs_map[pc_id]
            logger.info(f"Reusing existing connection for pc_id: {pc_id}")
            await pipecat_connection.renegotiate(sdp=request["sdp"], type=request["type"])
        else:
            pipecat_connection = SmallWebRTCConnection(ice_servers)
            await pipecat_connection.initialize(sdp=request["sdp"], type=request["type"])

            @pipecat_connection.event_handler("closed")
            async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
                logger.info(f"Discarding peer connection for pc_id: {webrtc_connection.pc_id}")
                pcs_map.pop(webrtc_connection.pc_id, None)  # Remove connection reference
                contexts_map.pop(webrtc_connection.pc_id, None)  # Remove context reference

            asyncio.create_task(run_bot(pipecat_connection, websocket, assistant_from_client))

        answer = pipecat_connection.get_answer()
        pcs_map[answer["pc_id"]] = pipecat_connection

        await websocket.send_json(answer)

        # Keep the connection open and print text messages
        while True:
            try:
                message = await websocket.receive_text()
                # Parse JSON message from UI
                try:
                    data = json.loads(message)
                    message = data.get("message", "").strip()
                    if data.get("type") == "context_reset" and message:
                        print(f"Received context reset from UI: {message}")
                        logger.info(f"Context reset from UI: {message}")

                        # Forward context reset as a user message to LangGraph on next turn
                        pc_id = pipecat_connection.pc_id
                        if pc_id in contexts_map:
                            context = contexts_map[pc_id]
                            context.add_message({"role": "user", "content": message})
                        else:
                            print(f"No context found for pc_id: {pc_id}")

                except json.JSONDecodeError:
                    print(f"Non-JSON message: {message}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                break

    except WebSocketDisconnect:
        logger.info("Client disconnected from websocket")


@app.get("/get_prompt")
async def get_prompt():
    """Report that the LangGraph agent owns the prompt/policy."""
    return {
        "prompt": "",
        "name": "LangGraph-managed",
        "description": "Prompt and persona are managed by the LangGraph agent.",
    }

# Serve static UI (if bundled) after API/WebSocket routes so they still take precedence
UI_DIST_DIR = Path(__file__).parent / "ui" / "dist"
if UI_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIST_DIR), html=True), name="static")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC demo")
    parser.add_argument("--host", default="0.0.0.0", help="Host for HTTP server (default: localhost)")
    parser.add_argument("--port", type=int, default=7860, help="Port for HTTP server (default: 7860)")
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    logger.remove(0)
    if args.verbose:
        logger.add(sys.stderr, level="TRACE")
    else:
        logger.add(sys.stderr, level="DEBUG")

    uvicorn.run(app, host=args.host, port=args.port)
