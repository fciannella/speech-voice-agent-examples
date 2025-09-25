# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD 2-Clause License

"""Riva speech langchain bot."""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantResponseAggregator,
    LLMUserResponseAggregator,
)
from pipecat.processors.frameworks.langchain import LangchainProcessor

from nvidia_pipecat.pipeline.ace_pipeline_runner import ACEPipelineRunner, PipelineMetadata
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

message_store = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """Get the session history."""
    if session_id not in message_store:
        message_store[session_id] = ChatMessageHistory()
    return message_store[session_id]


async def create_pipeline_task(pipeline_metadata: PipelineMetadata):
    """Create the pipeline to be run.

    Args:
        pipeline_metadata (PipelineMetadata): Metadata containing websocket and other pipeline configuration.

    Returns:
        PipelineTask: The configured pipeline task for handling speech-to-speech conversation.
    """
    transport = ACETransport(
        websocket=pipeline_metadata.websocket,
        params=ACETransportParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

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

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Be nice and helpful. Answer very briefly and without special characters like `#` or `*`. "
                "Your response will be synthesized to voice and those characters will create unnatural sounds.",
            ),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )

    chain = prompt | ChatOpenAI(model="gpt-4o", temperature=0.7)
    history_chain = RunnableWithMessageHistory(
        chain,
        get_session_history,
        history_messages_key="chat_history",
        input_messages_key="input",
    )

    lc = LangchainProcessor(history_chain)

    tma_in = LLMUserResponseAggregator()
    tma_out = LLMAssistantResponseAggregator()

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            tma_in,  # User responses
            lc,  # Langchain processor
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            tma_out,  # LLM responses
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
        messages = [({"content": "Please briefly introduce yourself to the user."})]
        await task.queue_frames([LLMMessagesFrame(messages)])

    return task


app = FastAPI()
app.include_router(websocket_router)
runner = ACEPipelineRunner.create_instance(pipeline_callback=create_pipeline_task)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../static")), name="static")

if __name__ == "__main__":
    uvicorn.run("bot:app", host="0.0.0.0", port=8100, workers=1)
