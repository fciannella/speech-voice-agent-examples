# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD 2-Clause License

"""Riva neural machine translation (NMT) bot.

This bot enables speech-to-speech translation using Riva ASR, NMT and TTS services
with voice activity detection.
"""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TranscriptionFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.sentence import SentenceAggregator
from pipecat.services.nim import NimLLMService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601

from nvidia_pipecat.pipeline.ace_pipeline_runner import ACEPipelineRunner, PipelineMetadata
from nvidia_pipecat.services.riva_nmt import RivaNMTService
from nvidia_pipecat.services.riva_speech import (
    RivaASRService,
    RivaTTSService,
)
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
        PipelineTask: The configured pipeline task for handling speech-to-speech translation.
    """
    transport = ACETransport(
        websocket=pipeline_metadata.websocket,
        params=ACETransportParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    llm = NimLLMService(
        api_key=os.getenv("NVIDIA_API_KEY"),
        model="nvdev/meta/llama-3.1-8b-instruct",
    )

    # Please update the stt and tts language, voice id as needed
    # tts voice id as per the language can be selected from https://docs.nvidia.com/deeplearning/riva/user-guide/docs/tts/tts-overview.html
    language = Language.ES_US
    voice_id = "English-US.Female-1"

    nmt1 = RivaNMTService(source_language=language, target_language=Language.EN_US)
    nmt2 = RivaNMTService(source_language=Language.EN_US, target_language=language)

    stt = RivaASRService(
        server="localhost:50051",
        api_key=os.getenv("NVIDIA_API_KEY"),
        language=language,
        sample_rate=16000,
        model="parakeet-1.1b-en-US-asr-streaming-silero-vad-asr-bls-ensemble",
    )
    tts = RivaTTSService(
        server="localhost:50051",
        api_key=os.getenv("NVIDIA_API_KEY"),
        voice_id=voice_id,
        language=language,
        zero_shot_quality=20,
        sample_rate=16000,
        model="fastpitch-hifigan-tts",
    )

    sentence_aggregator = SentenceAggregator()

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            nmt1,
            llm,
            sentence_aggregator,
            nmt2,
            tts,
            transport.output(),
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
        await task.queue_frames([TranscriptionFrame("Contar una historia.", "", time_now_iso8601)])

    return task


app = FastAPI()
app.include_router(websocket_router)
runner = ACEPipelineRunner.create_instance(pipeline_callback=create_pipeline_task)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../static")), name="static")

if __name__ == "__main__":
    uvicorn.run("bot:app", host="0.0.0.0", port=8100, workers=1)
