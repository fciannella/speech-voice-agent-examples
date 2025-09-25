# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD 2-Clause License

"""Example bot demonstrating how to use the tracing utilities."""

import asyncio
import logging
import uuid

from fastapi import FastAPI
from opentelemetry import metrics, trace
from pipecat.frames.frames import TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameProcessor

from nvidia_pipecat.utils.tracing import AttachmentStrategy, traceable, traced

app = FastAPI()

tracer = trace.get_tracer("opentelemetry-pipecat-example")

meter = metrics.get_meter("opentelemetry-pipecat-example")

logger = logging.getLogger("opentelemetry")
logger.setLevel(logging.DEBUG)


@traceable
class DummyProcessor(FrameProcessor):
    """Example processor demonstrating how to use the tracing utilities."""

    @traced(attachment_strategy=AttachmentStrategy.NONE)
    async def process_frame(self, frame, direction):
        """Process a frame."""
        await super().process_frame(frame, direction)
        trace.get_current_span().add_event("Before inner")
        with tracer.start_as_current_span("inner") as span:
            span.add_event("inner event")
            await self.child()
            await self.linked()
            await self.none()
        trace.get_current_span().add_event("After inner")
        async for f in self.generator():
            print(f"{f}")
        await super().push_frame(frame, direction)

    @traced
    async def child(self):
        """Example method for the DummyProcessor."""
        # This span is attached as CHILD meaning that it will
        # be attached to the class span if no parent or to its
        # parent otherwise.
        trace.get_current_span().add_event("child")

    @traced(attachment_strategy=AttachmentStrategy.LINK)
    async def linked(self):
        """Example method for the DummyProcessor."""
        # This span is attached as LINK meaning it will be attached
        # to the class span but linked to its parent.
        trace.get_current_span().add_event("linked")

    @traced(attachment_strategy=AttachmentStrategy.NONE)
    async def none(self):
        """Example method for the DummyProcessor."""
        # This span is attached as NONE meaning it will be attached
        # to the class span even if nested under another span.
        trace.get_current_span().add_event("none")

    @traced
    async def generator(self):
        """Example method for the DummyProcessor."""
        yield TextFrame("Hello, ")
        trace.get_current_span().add_event("generated!")
        yield TextFrame("World")


async def main():
    """Main function of the bot."""
    with tracer.start_as_current_span("pipeline-root-span") as span:
        span.set_attribute("stream_id", str(uuid.uuid4()))
        logger.info("Started building pipeline")
        dummy = DummyProcessor()
        logger.info("Built dummy processor")
        pipeline = Pipeline([dummy])
        task = PipelineTask(pipeline)
        await task.queue_frame(TextFrame("Hello, "))
        await task.queue_frame(TextFrame("World"))
        await task.stop_when_done()
        logger.info("Built pipeline task")
        logger.info("Starting pipeline...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
