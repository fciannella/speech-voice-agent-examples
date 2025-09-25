# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD 2-Clause License

"""NVIDIA RAG bot."""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

from nvidia_pipecat.pipeline.ace_pipeline_runner import ACEPipelineRunner, PipelineMetadata
from nvidia_pipecat.processors.nvidia_context_aggregator import (
    # NvidiaTTSResponseCacher, # Uncomment to enable speculative speech processing
    create_nvidia_context_aggregator,
)
from nvidia_pipecat.processors.transcript_synchronization import (
    BotTranscriptSynchronization,
    UserTranscriptSynchronization,
)
from nvidia_pipecat.services.nvidia_rag import NvidiaRAGService
from nvidia_pipecat.services.riva_speech import RivaASRService, RivaTTSService
from nvidia_pipecat.transports.network.ace_fastapi_websocket import (
    ACETransport,
    ACETransportParams,
)
from nvidia_pipecat.transports.services.ace_controller.routers.websocket_router import router as websocket_router
from nvidia_pipecat.utils.logging import setup_default_ace_logging

load_dotenv(override=True)

setup_default_ace_logging(level="INFO")


async def create_pipeline_task(pipeline_metadata: PipelineMetadata):
    """Create the pipeline to be run.

    Args:
        pipeline_metadata (PipelineMetadata): Metadata containing websocket and other pipeline configuration.

    Returns:
        PipelineTask: The configured pipeline task for handling NVIDIA RAG.
    """
    transport = ACETransport(
        websocket=pipeline_metadata.websocket,
        params=ACETransportParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # Please set your nvidia rag collection name here
    rag = NvidiaRAGService(collection_name="nvidia_blogs")

    stt = RivaASRService(
        server="localhost:50051",
        api_key=os.getenv("NVIDIA_API_KEY"),
        language="en-US",
        sample_rate=16000,
        model="parakeet-1.1b-en-US-asr-streaming-silero-vad-asr-bls-ensemble",
    )
    tts = RivaTTSService(
        server="localhost:50051",
        api_key=os.getenv("NVIDIA_API_KEY"),
        voice_id="English-US.Female-1",
        language="en-US",
        zero_shot_quality=20,
        sample_rate=16000,
        model="fastpitch-hifigan-tts",
    )

    messages = [
        {
            "role": "system",
            "content": "You are a helpful Large Language Model. "
            "Your goal is to demonstrate your capabilities in a succinct way. "
            "Your output will be converted to audio so don't include special characters in your answers. "
            "Respond to what the user said in a creative and helpful way.",
        }
    ]

    context = OpenAILLMContext(messages)
    # Required components for Speculative Speech Processing
    # - Nvidia Context aggregator: Handles interim transcripts and early response generation
    # send_interims=False: Only process final transcripts
    # Set send_interims=True to process interim transcripts when enabling speculative speech processing
    nvidia_context_aggregator = create_nvidia_context_aggregator(context, send_interims=False)
    # - TTS response cacher: Manages response timing and delivery for natural conversation flow
    # nvidia_tts_response_cacher = NvidiaTTSResponseCacher() # Uncomment to enable speculative speech processing

    # Used to synchronize the user and bot transcripts in the UI
    stt_transcript_synchronization = UserTranscriptSynchronization()
    tts_transcript_synchronization = BotTranscriptSynchronization()

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            stt_transcript_synchronization,
            nvidia_context_aggregator.user(),
            rag,  # NVIDIA RAG
            tts,  # Text-To-Speech
            # Caches TTS responses for coordinated delivery in speculative
            # speech processing
            # nvidia_tts_response_cacher, # Uncomment to enable speculative speech processing
            tts_transcript_synchronization,
            transport.output(),  # Websocket output to client
            nvidia_context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
            send_initial_empty_metrics=True,
            report_only_initial_ttfb=True,
            start_metadata={"stream_id": pipeline_metadata.stream_id},
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Kick off the conversation.
        messages.append({"role": "user", "content": "Please introduce yourself to the user."})
        await task.queue_frames([LLMMessagesFrame(messages)])

    return task


app = FastAPI()
app.include_router(websocket_router)
runner = ACEPipelineRunner.create_instance(pipeline_callback=create_pipeline_task)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../static")), name="static")

if __name__ == "__main__":
    uvicorn.run("bot:app", host="0.0.0.0", port=8100, workers=1)
