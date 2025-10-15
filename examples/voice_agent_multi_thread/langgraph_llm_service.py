"""LangGraph-backed LLM service for Pipecat pipelines.

This service adapts a running LangGraph agent (accessed via langgraph-sdk)
to Pipecat's frame-based processing model. It consumes `OpenAILLMContextFrame`
or `LLMMessagesFrame` inputs, extracts the latest user message (using the
LangGraph server's thread to persist history), and streams assistant tokens
back as `LLMTextFrame` until completion.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional
import os
from dotenv import load_dotenv

from langgraph_sdk import get_client
from langchain_core.messages import HumanMessage
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesFrame,
    LLMTextFrame,
    StartInterruptionFrame,
    VisionImageRawFrame,
)
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext, OpenAILLMContextFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.openai.llm import OpenAILLMService


load_dotenv()

# TTS sanitize helper: normalize curly quotes/dashes and non-breaking spaces to ASCII
def _tts_sanitize(text: str) -> str:
    try:
        if not isinstance(text, str):
            text = str(text)
        replacements = {
            "\u2018": "'",  # left single quote
            "\u2019": "'",  # right single quote / apostrophe
            "\u201C": '"',   # left double quote
            "\u201D": '"',   # right double quote
            "\u00AB": '"',   # left angle quote
            "\u00BB": '"',   # right angle quote
            "\u2013": "-",  # en dash
            "\u2014": "-",  # em dash
            "\u2026": "...",# ellipsis
            "\u00A0": " ",  # non-breaking space
            "\u202F": " ",  # narrow no-break space
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text
    except Exception:
        return text

class LangGraphLLMService(OpenAILLMService):
    """Pipecat LLM service that delegates responses to a LangGraph agent.

    Attributes:
        base_url: LangGraph API base URL, e.g. "http://127.0.0.1:2024".
        assistant: Assistant name or id registered with the LangGraph server.
        user_email: Value for `configurable.user_email` (routing / personalization).
        stream_mode: SDK stream mode ("updates", "values", "messages", "events").
        debug_stream: When True, logs raw stream events for troubleshooting.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:2024",
        assistant: str = "ace-base-agent",
        user_email: str = "test@example.com",
        stream_mode: Optional[list] = None,
        debug_stream: bool = False,
        thread_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        enable_multi_threading: bool = True,  # Enable multi-threaded routing
        **kwargs: Any,
    ) -> None:
        # Initialize base class; OpenAI settings unused but required by parent
        super().__init__(api_key="", **kwargs)
        self.base_url = base_url
        self.assistant = assistant
        self.user_email = user_email
        # Match working text client: use ["values", "custom"] for multi-threading
        self.stream_mode = stream_mode if stream_mode is not None else (["values", "custom"] if enable_multi_threading else "values")
        self.debug_stream = debug_stream
        self.enable_multi_threading = enable_multi_threading
        logger.info(f"🎛️  LangGraphLLMService initialized: enable_multi_threading={enable_multi_threading}, stream_mode={self.stream_mode}, type={type(self.stream_mode)}")

        # Optional auth header
        token = (
            auth_token
            or os.getenv("LANGGRAPH_AUTH_TOKEN")
            or os.getenv("AUTH0_ACCESS_TOKEN")
            or os.getenv("AUTH_BEARER_TOKEN")
        )

        headers = {"Authorization": f"Bearer {token}"} if isinstance(token, str) and token else None
        self._client = get_client(url=self.base_url, headers=headers) if headers else get_client(url=self.base_url)
        
        # Multi-threading: maintain separate threads for main and secondary
        self._thread_id_main: Optional[str] = thread_id
        self._thread_id_secondary: Optional[str] = None
        self._thread_id: Optional[str] = thread_id  # Backward compatibility
        
        # Namespace for store coordination - sanitize email (periods not allowed)
        sanitized_email = self.user_email.replace(".", "_").replace("@", "_at_")
        self._namespace_for_memory: tuple[str, str] = (sanitized_email, "tools_updates")
        
        # Track interim message reset state
        self._interim_messages_reset: bool = True
        self._last_was_long_operation: bool = False
        
        self._current_task: Optional[asyncio.Task] = None
        self._outer_open: bool = False
        self._emitted_texts: set[str] = set()
        
        # Background task for main thread long operations
        self._background_main_task: Optional[asyncio.Task] = None
        self._background_final_message: Optional[str] = None
        self._background_monitor_task: Optional[asyncio.Task] = None
        self._background_task_is_long_operation: bool = False  # Track if current background task is a long operation

    async def _ensure_thread(self, thread_type: str = "main") -> Optional[str]:
        """Ensure thread exists for the given type (main or secondary)."""
        if thread_type == "main":
            if self._thread_id_main:
                return self._thread_id_main
        else:
            if self._thread_id_secondary:
                return self._thread_id_secondary
        
        try:
            thread = await self._client.threads.create()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"LangGraph: failed to create {thread_type} thread; proceeding threadless. Error: {exc}")
            return None

        thread_id = getattr(thread, "thread_id", None)
        if thread_id is None and isinstance(thread, dict):
            thread_id = thread.get("thread_id") or thread.get("id")
        if thread_id is None:
            thread_id = getattr(thread, "id", None)
        
        if isinstance(thread_id, str) and thread_id:
            if thread_type == "main":
                self._thread_id_main = thread_id
                self._thread_id = thread_id  # Backward compatibility
            else:
                self._thread_id_secondary = thread_id
            logger.info(f"Created {thread_type} thread: {thread_id}")
            return thread_id
        else:
            logger.warning(f"LangGraph: could not determine {thread_type} thread id; proceeding threadless.")
            return None

    async def _monitor_background_task(self) -> None:
        """Monitor background main task and proactively inject final message when complete."""
        if not self._background_main_task:
            return
        
        try:
            # Wait for the background task to complete
            await self._background_main_task
            logger.info("🏁 Background main task completed, checking for final message")
            
            # Give a VERY brief moment for the final message to be captured (minimize race window)
            await asyncio.sleep(0.1)
            
            # If we captured a final message, inject it as a new bot-initiated turn
            if self._background_final_message:
                logger.info("📢 Injecting final synthesized message from background task")
                logger.info(f"Message to inject: {self._background_final_message}")
                
                # Simply push the frames directly - they should flow through TTS
                await self.push_frame(LLMFullResponseStartFrame())
                logger.info("✅ Pushed LLMFullResponseStartFrame")
                
                await self.push_frame(LLMTextFrame(_tts_sanitize(self._background_final_message)))
                logger.info(f"✅ Pushed LLMTextFrame with content")
                
                await self.push_frame(LLMFullResponseEndFrame())
                logger.info("✅ Pushed LLMFullResponseEndFrame")
                
                # Clear the captured message
                self._background_final_message = None
                logger.info("✨ Final message injection complete")
            else:
                logger.info("ℹ️ Background task completed but no final message to inject")
        except asyncio.CancelledError:
            logger.info("🚫 Background task monitor cancelled")
        except Exception as exc:
            logger.error(f"❌ Background task monitor error: {exc}", exc_info=True)
        finally:
            self._background_main_task = None
            self._background_monitor_task = None

    async def _check_long_operation_running(self) -> bool:
        """Check if a long operation is currently running via the store."""
        if not self.enable_multi_threading:
            logger.info("Multi-threading disabled, returning False")
            return False
        
        try:
            ns_list = list(self._namespace_for_memory)
            logger.info(f"Checking store with namespace: {ns_list}")
            
            # Use search_items() like the working client code does
            items = await self._client.store.search_items(ns_list)
            logger.info(f"🔎 search_items returned: type={type(items)}")
            
            # Normalize return shape: SDK may return a dict with 'items' or a bare list (matching text client)
            items_list = None
            if isinstance(items, dict):
                inner = items.get("items")
                if isinstance(inner, list):
                    items_list = inner
                    logger.info(f"📦 Extracted {len(inner)} items from dict wrapper")
            elif isinstance(items, list):
                items_list = items
                logger.info(f"📦 Got {len(items)} items as bare list")
            
            if not items_list:
                logger.info("No items found in store, returning False")
                return False
            
            logger.info(f"📦 Total items in store: {len(items_list)}")
            
            # Walk from the end to find the most recent item that has a 'status' (EXACTLY like text client)
            for idx, item in enumerate(reversed(items_list)):
                item_key = getattr(item, "key", None) or (item.get("key") if isinstance(item, dict) else None)
                value = getattr(item, "value", None)
                if value is None and isinstance(item, dict):
                    value = item.get("value")
                
                value_keys = list(value.keys()) if isinstance(value, dict) else "N/A"
                logger.info(f"📦 Item {idx} (from end): key={item_key}, value_keys={value_keys}")
                
                if isinstance(value, dict) and "status" in value:
                    status = value.get("status")
                    logger.info(f"🔍 Long operation check: status={status}, tool={value.get('tool_name')}, progress={value.get('progress')}")
                    return status == "running"
            
            logger.info("No status items found in store")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error(f"❌ Failed to check operation status: {exc}", exc_info=True)
            return False

    @staticmethod
    def _extract_latest_user_text(context: OpenAILLMContext) -> str:
        """Return the latest user (or fallback system) message content.

        The LangGraph server maintains history via threads, so we only need to
        send the current turn text. Prefer the latest user message; if absent,
        fall back to the latest system message so system-only kickoffs can work.
        """
        messages = context.get_messages() or []
        for msg in reversed(messages):
            try:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    return content if isinstance(content, str) else str(content)
            except Exception:  # Defensive against unexpected shapes
                continue
        # Fallback: use the most recent system message if no user message exists
        for msg in reversed(messages):
            try:
                if msg.get("role") == "system":
                    content = msg.get("content", "")
                    return content if isinstance(content, str) else str(content)
            except Exception:
                continue
        return ""

    async def _stream_langgraph_impl(self, text: str, thread_type: str, thread_id: Optional[str], config: dict, input_payload: Any, is_background: bool = False) -> None:
        """Internal implementation of LangGraph streaming."""
        try:
            logger.info(f"🎬 Starting stream with mode: {self.stream_mode} (type: {type(self.stream_mode)})")
            async for chunk in self._client.runs.stream(
                thread_id,
                self.assistant,
                input=input_payload,
                stream_mode=self.stream_mode,
                config=config,
            ):
                data = getattr(chunk, "data", None)
                event = getattr(chunk, "event", "") or ""

                if self.debug_stream:
                    try:
                        # Short, structured debugging output
                        dtype = type(data).__name__
                        preview = ""
                        if hasattr(data, "content") and isinstance(getattr(data, "content"), str):
                            c = getattr(data, "content")
                            preview = c[:120]
                        elif isinstance(data, dict):
                            preview = ",".join(list(data.keys())[:6])
                        logger.debug(f"[LangGraph stream] event={event} data={dtype}:{preview}")
                    except Exception:  # noqa: BLE001
                        logger.debug(f"[LangGraph stream] event={event}")

                # Token streaming events (LangChain chat model streaming)
                if "on_chat_model_stream" in event or event.endswith(".on_chat_model_stream"):
                    part_text = ""
                    d = data
                    if isinstance(d, dict):
                        if "chunk" in d:
                            ch = d["chunk"]
                            part_text = getattr(ch, "content", None) or ""
                            if not isinstance(part_text, str):
                                part_text = str(part_text)
                        elif "delta" in d:
                            delta = d["delta"]
                            part_text = getattr(delta, "content", None) or ""
                            if not isinstance(part_text, str):
                                part_text = str(part_text)
                        elif "content" in d and isinstance(d["content"], str):
                            part_text = d["content"]
                    else:
                        part_text = getattr(d, "content", "")

                    if part_text:
                        if not self._outer_open:
                            await self.push_frame(LLMFullResponseStartFrame())
                            self._outer_open = True
                            self._emitted_texts.clear()
                        if part_text not in self._emitted_texts:
                            self._emitted_texts.add(part_text)
                            await self.push_frame(LLMTextFrame(_tts_sanitize(part_text)))
                
                # Custom events from get_stream_writer() - tool progress messages
                if event == "custom":
                    custom_text = ""
                    if isinstance(data, str):
                        custom_text = data
                    elif isinstance(data, dict):
                        # Try to extract text from custom event data
                        custom_text = data.get("content") or data.get("text") or ""
                    elif hasattr(data, "content"):
                        custom_text = getattr(data, "content", "")
                    
                    if custom_text and isinstance(custom_text, str) and custom_text not in self._emitted_texts:
                        logger.info(f"📢 Custom event (tool message): {custom_text[:100]}")
                        self._emitted_texts.add(custom_text)
                        # Emit as its own turn
                        if self._outer_open:
                            await self.push_frame(LLMFullResponseEndFrame())
                            self._outer_open = False
                        await self.push_frame(LLMFullResponseStartFrame())
                        await self.push_frame(LLMTextFrame(_tts_sanitize(custom_text)))
                        await self.push_frame(LLMFullResponseEndFrame())

                # Final value-style events (values mode)
                if event == "values":
                    # Some dev servers send final AI message content here
                    final_text = ""
                    logger.info(f"📊 Processing values event: data_type={type(data)}, is_background={is_background}")
                    
                    # Handle list of messages (most common case)
                    if isinstance(data, list) and data:
                        logger.info(f"📊 Data is list with {len(data)} items")
                        # Find the last AI message in the list
                        for msg in reversed(data):
                            if isinstance(msg, dict):
                                if msg.get("type") == "ai" and isinstance(msg.get("content"), str):
                                    final_text = msg["content"]
                                    logger.info(f"✅ Found AI message in dict: {final_text[:100]}")
                                    break
                            elif hasattr(msg, "type") and getattr(msg, "type") == "ai":
                                content = getattr(msg, "content", None)
                                if isinstance(content, str):
                                    final_text = content
                                    logger.info(f"✅ Found AI message in object: {final_text[:100]}")
                                    break
                    # Handle single message object
                    elif hasattr(data, "content") and isinstance(getattr(data, "content"), str):
                        final_text = getattr(data, "content")
                        logger.info(f"✅ Found content in object: {final_text[:100]}")
                    # Handle single message dict
                    elif isinstance(data, dict):
                        c = data.get("content")
                        if isinstance(c, str):
                            final_text = c
                            logger.info(f"✅ Found content in dict: {final_text[:100]}")
                    
                    if final_text and final_text not in self._emitted_texts:
                        if is_background:
                            # Running in background - capture for later injection
                            # Only capture if there's no pending message waiting to be injected
                            if not self._background_final_message:
                                logger.info("💾 Capturing final message from background task")
                                self._background_final_message = final_text
                                self._emitted_texts.add(final_text)
                            else:
                                logger.info(f"⚠️  Skipping capture - pending message already exists: {self._background_final_message[:50]}...")
                            # Close any open utterance
                            if self._outer_open:
                                await self.push_frame(LLMFullResponseEndFrame())
                                self._outer_open = False
                        else:
                            # Normal foreground - push immediately
                            # Close backchannel utterance if open
                            if self._outer_open:
                                await self.push_frame(LLMFullResponseEndFrame())
                                self._outer_open = False
                            # Emit final explanation as its own message
                            self._emitted_texts.add(final_text)
                            await self.push_frame(LLMFullResponseStartFrame())
                            await self.push_frame(LLMTextFrame(_tts_sanitize(final_text)))
                            await self.push_frame(LLMFullResponseEndFrame())

                # Messages mode: look for an array of messages
                if event == "messages" or event.endswith(":messages"):
                    try:
                        msgs = None
                        if isinstance(data, dict):
                            msgs = data.get("messages") or data.get("result") or data.get("value")
                        elif hasattr(data, "messages"):
                            msgs = getattr(data, "messages")
                        if isinstance(msgs, list) and msgs:
                            last = msgs[-1]
                            content = getattr(last, "content", None)
                            if content is None and isinstance(last, dict):
                                content = last.get("content")
                            if isinstance(content, str) and content:
                                if not self._outer_open:
                                    await self.push_frame(LLMFullResponseStartFrame())
                                    self._outer_open = True
                                    self._emitted_texts.clear()
                                if content not in self._emitted_texts:
                                    self._emitted_texts.add(content)
                                    await self.push_frame(LLMTextFrame(_tts_sanitize(content)))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(f"LangGraph messages parsing error: {exc}")
                # If payload is a plain string, emit it
                if isinstance(data, str):
                    txt = data.strip()
                    if txt:
                        if not self._outer_open:
                            await self.push_frame(LLMFullResponseStartFrame())
                            self._outer_open = True
                            self._emitted_texts.clear()
                        if txt not in self._emitted_texts:
                            self._emitted_texts.add(txt)
                            await self.push_frame(LLMTextFrame(_tts_sanitize(txt)))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"LangGraph stream error: {exc}")
        finally:
            # Mark operation complete if this was a main thread
            if thread_type == "main":
                self._last_was_long_operation = True
                logger.info("✅ Main thread operation completed")

    async def _stream_langgraph(self, text: str) -> None:
        """Route to main or secondary thread, running main operations in background."""
        # Determine thread type based on whether a long operation is running
        logger.info(f"🎯 _stream_langgraph called: enable_multi_threading={self.enable_multi_threading}")
        thread_type = "main"
        if self.enable_multi_threading:
            long_operation_running = await self._check_long_operation_running()
            if long_operation_running:
                thread_type = "secondary"
                self._interim_messages_reset = False
                logger.info("🔀 Long operation detected, routing to secondary thread")
            else:
                # Starting new main operation
                if self._last_was_long_operation:
                    self._interim_messages_reset = True
                    self._last_was_long_operation = False
                else:
                    self._interim_messages_reset = True
                logger.info("▶️  No long operation, routing to main thread")
        
        # Ensure appropriate thread
        thread_id = await self._ensure_thread(thread_type)
        
        # Build config with namespace for store coordination
        config = {
            "configurable": {
                "user_email": self.user_email,
                "thread_id": thread_id,
                "namespace_for_memory": list(self._namespace_for_memory),
            }
        }
        
        # Build input dict for multi-threaded agent
        if self.enable_multi_threading:
            input_payload = {
                "messages": [{"type": "human", "content": text}],
                "thread_type": thread_type,
                "interim_messages_reset": self._interim_messages_reset,
            }
        else:
            # Backward compatible: simple message input
            input_payload = [HumanMessage(content=text)]

        # For main thread operations, run in background to allow subsequent messages
        if self.enable_multi_threading and thread_type == "main":
            logger.info("🚀 Starting main thread operation in background")
            
            # Cancel any existing background main task and monitor
            if self._background_main_task is not None and not self._background_main_task.done():
                logger.info("⚠️  Canceling previous background main task")
                self._background_main_task.cancel()
                try:
                    await self._background_main_task
                except asyncio.CancelledError:
                    pass
            if self._background_monitor_task is not None and not self._background_monitor_task.done():
                self._background_monitor_task.cancel()
                try:
                    await self._background_monitor_task
                except asyncio.CancelledError:
                    pass
            
            # Start new background task (with is_background=True to capture final message)
            self._background_main_task = asyncio.create_task(
                self._stream_langgraph_impl(text, thread_type, thread_id, config, input_payload, is_background=True)
            )
            
            # Start monitor to inject final message when background task completes
            self._background_monitor_task = asyncio.create_task(self._monitor_background_task())
            
            # Don't await - return immediately to allow pipeline to process next message
            logger.info("✨ Main thread operation dispatched, pipeline is now free")
        else:
            # Secondary thread or non-multi-threaded: run synchronously (should be fast)
            logger.info(f"⚡ Running {thread_type} thread operation synchronously")
            await self._stream_langgraph_impl(text, thread_type, thread_id, config, input_payload, is_background=False)

    async def _process_context_and_frames(self, context: OpenAILLMContext) -> None:
        """Adapter entrypoint: push start/end frames and stream tokens."""
        try:
            # Defer opening until backchannels arrive; final will be emitted separately
            user_text = self._extract_latest_user_text(context)
            if not user_text:
                logger.debug("LangGraph: no user text in context; skipping run.")
                return
            self._outer_open = False
            self._emitted_texts.clear()
            await self._stream_langgraph(user_text)
        finally:
            if self._outer_open:
                await self.push_frame(LLMFullResponseEndFrame())
                self._outer_open = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process pipeline frames, handling interruptions and context inputs."""
        context: Optional[OpenAILLMContext] = None

        if isinstance(frame, OpenAILLMContextFrame):
            context = frame.context
        elif isinstance(frame, LLMMessagesFrame):
            context = OpenAILLMContext.from_messages(frame.messages)
        elif isinstance(frame, VisionImageRawFrame):
            # Not implemented for LangGraph adapter; ignore images
            context = None
        elif isinstance(frame, StartInterruptionFrame):
            # Relay interruption downstream and cancel any active run
            await self._start_interruption()
            await self.stop_all_metrics()
            await self.push_frame(frame, direction)
            if self._current_task is not None and not self._current_task.done():
                await self.cancel_task(self._current_task)
                self._current_task = None
            # For multi-threading: check if a long operation is running before cancelling
            long_op_running = False
            if self.enable_multi_threading:
                long_op_running = await self._check_long_operation_running()
            
            # Only cancel background tasks if NOT in a long operation (which should continue)
            if not long_op_running:
                if self._background_main_task is not None and not self._background_main_task.done():
                    logger.info("🛑 Canceling background main task due to interruption")
                    self._background_main_task.cancel()
                    try:
                        await self._background_main_task
                    except asyncio.CancelledError:
                        pass
                    self._background_main_task = None
                if self._background_monitor_task is not None and not self._background_monitor_task.done():
                    logger.info("🛑 Canceling background monitor task due to interruption")
                    self._background_monitor_task.cancel()
                    try:
                        await self._background_monitor_task
                    except asyncio.CancelledError:
                        pass
                    self._background_monitor_task = None
            else:
                logger.info("🔄 Long operation running - keeping background tasks alive, secondary will handle interruption")
            return
        else:
            await super().process_frame(frame, direction)

        if context is not None:
            if self._current_task is not None and not self._current_task.done():
                await self.cancel_task(self._current_task)
                self._current_task = None
                logger.debug("LangGraph LLM: canceled previous task")

            self._current_task = self.create_task(self._process_context_and_frames(context))
            self._current_task.add_done_callback(lambda _: setattr(self, "_current_task", None))


