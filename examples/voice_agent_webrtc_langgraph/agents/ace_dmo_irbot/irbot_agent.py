import os
import logging
import inspect
import asyncio
from typing import Any, Dict, List, Optional

import requests
from pprint import pformat
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_openai import ChatOpenAI
try:
    from .explain_prompt import EXPLAIN_WITH_CONTEXT_PROMPT, TTS_SUMMARY_PROMPT, BACKCHANNEL_PROMPT
except ImportError:
    import sys
    sys.path.append(os.path.dirname(__file__))
    from explain_prompt import EXPLAIN_WITH_CONTEXT_PROMPT, TTS_SUMMARY_PROMPT, BACKCHANNEL_PROMPT
from langgraph.func import entrypoint, task
from langgraph.types import StreamWriter


IRBOT_BASE_URL = os.getenv("IRBOT_BASE_URL", "https://api-prod.nvidia.com")
IRBOT_API_KEY = os.getenv("IRBOT_API_KEY", "")
IRBOT_TIMEOUT = int(os.getenv("IRBOT_TIMEOUT", "20"))

logger = logging.getLogger("ACE_IRBotAgent")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


@task()
def irbot_userquery_task(query: str, session_id: str) -> Dict[str, Any]:
    """Call IRBot userquery endpoint. Output must be JSON-serializable (dict)."""
    if not IRBOT_API_KEY:
        raise RuntimeError("IRBOT_API_KEY is not set")
    url = f"{IRBOT_BASE_URL.rstrip('/')}/chatbot/irbot-app/userquery"
    headers = {"x-irbot-secure": IRBOT_API_KEY}
    payload = {"query": query, "session_id": session_id}
    logger.info(f"POST {url} session_id={session_id} query_len={len(query)}")
    resp = requests.post(url, json=payload, headers=headers, timeout=IRBOT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _extract_text_from_response(data: Dict[str, Any]) -> str:
    # Try common fields where backend may place the textual response
    for key in ("answer", "message", "text", "content", "response", "data"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val
    # Fallback to stringify
    return str(data)


async def _writer_send(writer: Any, payload: Any) -> bool:
    """Best-effort send supporting writer.write(...), async callables, and sync callables."""
    # Case 1: writer object with .write
    try:
        if hasattr(writer, "write"):
            method = getattr(writer, "write")
            try:
                result = method(payload)
                if inspect.isawaitable(result):
                    await result
                return True
            except Exception as e:
                logger.warning(f"Backchannel: writer.write failed: {e}")
    except Exception:
        pass
    # Case 2: writer is callable (async or sync)
    try:
        if callable(writer):
            result = writer(payload)
            if inspect.isawaitable(result):
                await result
            return True
    except Exception as e:
        logger.warning(f"Backchannel: callable writer failed: {e}")
    return False


async def _periodic_backchannel(
    writer: StreamWriter,
    stop_event: asyncio.Event,
    initial_message: str = "Give me a moment, I'm checking that now...",
    followups: Optional[List[str]] = None,
    interval_seconds: float = 8.0,
) -> None:
    """Emit an initial backchannel update and a few periodic follow-ups until stop_event is set.

    This is a best-effort helper. If the runtime hasn't injected a writer, the caller should avoid
    spawning this task. All write failures are logged and ignored so they don't break the run.
    """
    # Send initial message immediately
    try:
        logger.info(f"Backchannel (initial): {initial_message}")
        sent = await _writer_send(writer, {"messages": [AIMessage(content=initial_message)]})
        if not sent:
            await _writer_send(writer, AIMessage(content=initial_message))
    except Exception:
        pass

    # Periodic follow-ups
    idx = 0
    followups = followups or [
        "Still working on it...",
        "Thanks for your patience, almost there...",
    ]
    while not stop_event.is_set():
        try:
            await asyncio.sleep(interval_seconds)
            if stop_event.is_set():
                break
            msg = followups[idx % len(followups)]
            logger.info(f"Backchannel (follow-up): {msg}")
            sent = await _writer_send(writer, {"messages": [AIMessage(content=msg)]})
            if not sent:
                await _writer_send(writer, AIMessage(content=msg))
            idx += 1
        except Exception:
            # Do not crash the loop due to transient issues
            break


@task()
def explain_with_context_task(serialized_messages: list[dict]) -> str:
    """Use the full conversation (last human includes backend JSON) to generate an explanation.
    Accepts a JSON-serializable list of messages: {type: human|ai|system, content: str}.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return ""
    llm = ChatOpenAI(model=os.getenv("EXPLAIN_MODEL", "gpt-4o"), api_key=openai_api_key)
    chain = EXPLAIN_WITH_CONTEXT_PROMPT | llm
    # Reconstruct BaseMessages
    reconstructed: list[BaseMessage] = []
    for m in serialized_messages:
        t = m.get("type")
        c = m.get("content", "")
        if t == "human":
            reconstructed.append(HumanMessage(content=c))
        elif t == "ai":
            reconstructed.append(AIMessage(content=c))
        elif t == "system":
            reconstructed.append(SystemMessage(content=c))
    # Log the reconstructed prompt messages for debugging
    try:
        logger.info("Explain context - prompt messages:\n" + pformat([{"type": type(m).__name__, "content": m.content[:500]} for m in reconstructed]))
    except Exception:
        pass
    result = chain.invoke({"messages": reconstructed})
    try:
        logger.info("Explain context - model response:\n" + str(getattr(result, "content", ""))[:800])
    except Exception:
        pass
    content = getattr(result, "content", None)
    return content if isinstance(content, str) else ""


@task()
def backchannel_task(text: str) -> Dict[str, Any]:
    """Emit a serializable assistant message so updates mode surfaces it.

    Task outputs must be JSON-serializable. We return a minimal 'messages' list
    with an assistant-like dict the client can recognize.
    """
    return {"messages": [{"type": "ai", "content": text}]}


@task()
def tts_summarize_task(original_text: str) -> str:
    """Summarize arbitrary text into a short TTS-friendly paragraph."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return original_text
    llm = ChatOpenAI(model=os.getenv("TTS_SUMMARY_MODEL", "gpt-4o-mini"), api_key=openai_api_key)
    chain = TTS_SUMMARY_PROMPT | llm
    try:
        res = chain.invoke({"original": original_text})
        content = getattr(res, "content", None)
        return content if isinstance(content, str) and content.strip() else original_text
    except Exception:
        return original_text


@task()
def generate_backchannel_task(question: str, history: list[str] | None = None, seed: int | None = None) -> str:
    """Create a varied, context-aware backchannel line using a fast model."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        # Fallback to static
        return "Working on it—this will take just a moment."
    llm = ChatOpenAI(
        model=os.getenv("BACKCHANNEL_MODEL", "gpt-4o-mini"),
        api_key=openai_api_key,
        temperature=float(os.getenv("BACKCHANNEL_TEMPERATURE", "0.9")),
    )
    try:
        history_text = "\n".join(history or [])
        # Some SDKs support seed via kwargs; ignore if unsupported
        if seed is not None and hasattr(llm, "kwargs"):
            llm.kwargs = {**getattr(llm, "kwargs", {}), "seed": seed}
        chain = BACKCHANNEL_PROMPT | llm
        res = chain.invoke({"question": question, "history": history_text})
        content = getattr(res, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
    except Exception:
        pass
    return "Still working—thanks for your patience."


async def _maybe_generate_explanation(backend: Dict[str, Any], question: str, convo_messages: list[BaseMessage]) -> Optional[str]:
    """If backend indicates a table response, call an LLM to produce a short explanation."""
    # Heuristics: look for keys that suggest tabular response
    if not isinstance(backend, dict):
        return None
    response_type = backend.get("responseType") or backend.get("type") or backend.get("format")
    has_table = False
    if isinstance(response_type, str) and response_type.lower() in {"table", "tabular"}:
        has_table = True
    if not has_table:
        # Fallback: presence of typical table fields
        if "columns" in backend and "values" in backend:
            has_table = True

    if not has_table:
        return None

    # Build serializable conversation and append JSON payload as last human message
    serializable: list[dict] = []
    for m in convo_messages:
        if isinstance(m, HumanMessage):
            serializable.append({"type": "human", "content": m.content})
        elif isinstance(m, AIMessage):
            serializable.append({"type": "ai", "content": m.content})
        elif isinstance(m, SystemMessage):
            serializable.append({"type": "system", "content": m.content})
    serializable.append({
        "type": "human",
        "content": str({
            "caption": backend.get("caption"),
            "responseType": backend.get("responseType"),
            "data": backend.get("data") or {"columns": backend.get("columns"), "values": backend.get("values")},
            "query": backend.get("query") or question,
            "chartData": backend.get("chartData", {}),
            "isChartRequired": backend.get("isChartRequired", False),
            "isGuardrailResponse": backend.get("isGuardrailResponse", False),
        })
    })

    # Always use full context prompt
    try:
        content = await explain_with_context_task(serialized_messages=serializable)
        return content or None
    except Exception:
        return None


@entrypoint()
async def agent(
    messages: List[Any],
    previous: Optional[List[Any]],
    config: Optional[Dict[str, Any]] = None,
    writer: StreamWriter = None,
):
    # No accumulation: just proxy the latest human message to IRBot using thread_id as session_id
    if not messages:
        logger.info("IRBot proxy: no incoming messages")
        return entrypoint.final(value=AIMessage(content="No input message received."), save=None)

    # Find the last HumanMessage; if none, just echo empty
    last_user: Optional[Any] = None
    for m in reversed(messages):
        # BaseMessages come through as objects
        if isinstance(m, HumanMessage) or getattr(m, "type", None) == "human":
            last_user = m
            break
        # Fallbacks: dict payloads (different runtimes may serialize messages as dicts)
        if isinstance(m, dict):
            # type-based shape (seen in logs: {"type": "human", "content": "..."})
            if m.get("type") == "human" and m.get("content"):
                last_user = m
                break
            # role-based shape
            if m.get("role") in ("user", "human") and m.get("content"):
                last_user = m
                break

    if last_user is None:
        logger.info(f"IRBot proxy: could not detect a human message. Incoming messages summary: {pformat(messages)}")
        return entrypoint.final(value=AIMessage(content="No user message found."), save=None)

    # Determine session id from config (handle dicts, mappings, and objects)
    cfg = config or {}

    def _get(container: Any, key: str, default: Optional[Any] = None) -> Any:
        try:
            if isinstance(container, dict):
                return container.get(key, default)
            if hasattr(container, "get"):
                return container.get(key, default)  # type: ignore[attr-defined]
            if hasattr(container, key):
                return getattr(container, key, default)
        except Exception:
            return default
        return default

    cfg_conf = _get(cfg, "configurable", {}) or {}
    session_id = (
        _get(cfg, "thread_id")
        or _get(cfg_conf, "thread_id")
        or _get(cfg_conf, "session_id")
        or _get(cfg, "thread")  # some runtimes might use 'thread'
        or _get(cfg_conf, "thread")
        or "unknown"
    )
    logger.info(
        f"IRBot proxy invoked; session_id={session_id} messages_count={len(messages)} "
        f"config_keys={list(cfg.keys()) if isinstance(cfg, dict) else type(cfg).__name__} "
        f"configurable_keys={list(cfg_conf.keys()) if isinstance(cfg_conf, dict) else type(cfg_conf).__name__}"
    )
    logger.info(f"IRBot proxy invoked; session_id={session_id} messages_count={len(messages)}")

    # Call backend
    try:
        user_text = getattr(last_user, "content", None)
        if user_text is None and isinstance(last_user, dict):
            user_text = last_user.get("content", "")
        if not isinstance(user_text, str):
            user_text = str(user_text) if user_text is not None else ""
        # Try to recover session_id from message additional_kwargs if config was empty
        if session_id == "unknown":
            try:
                if hasattr(last_user, "additional_kwargs") and isinstance(last_user.additional_kwargs, dict):
                    session_id = last_user.additional_kwargs.get("session_id") or session_id
                elif isinstance(last_user, dict):
                    ak = last_user.get("additional_kwargs") or {}
                    if isinstance(ak, dict):
                        session_id = ak.get("session_id") or session_id
            except Exception:
                pass
        if not user_text.strip():
            logger.info("IRBot proxy: empty user content; returning empty response")
            return entrypoint.final(value=AIMessage(content=""), save=None)
        # Execute backend call as a task (checkpointed) and emit state-based backchannel updates
        future = irbot_userquery_task(query=user_text or "", session_id=session_id)
        logger.info(f"Backchannel: writer available (ignored): {writer is not None}")

        # Also emit backchannel into graph state so updates mode surfaces it
        try:
            first_bc = await generate_backchannel_task(question=user_text or "", history=[])
            _ = await backchannel_task(text=first_bc)
            backchannel_history: list[str] = [first_bc]
        except Exception as e:
            logger.warning(f"Backchannel task emit failed: {e}")
            backchannel_history = []

        # Periodic follow-up backchannel into graph state while waiting
        try:
            while not future.done():
                await asyncio.sleep(8)
                try:
                    new_bc = await generate_backchannel_task(
                        question=user_text or "",
                        history=backchannel_history,
                    )
                    if isinstance(new_bc, str) and new_bc.strip():
                        backchannel_history.append(new_bc)
                        _ = await backchannel_task(text=new_bc)
                except Exception as e:
                    logger.debug(f"Backchannel follow-up emit skipped: {e}")
        except Exception:
            pass

        backend = await future
        text = _extract_text_from_response(backend)
        # Accumulate short-term memory locally (do not send to backend)
        convo_messages: list[BaseMessage] = []
        if previous:
            for m in previous:
                if isinstance(m, (HumanMessage, AIMessage, SystemMessage)):
                    convo_messages.append(m)
                elif isinstance(m, dict) and m.get("type") in ("human", "ai", "system"):
                    t = m.get("type")
                    c = m.get("content", "")
                    if t == "human":
                        convo_messages.append(HumanMessage(content=c))
                    elif t == "ai":
                        convo_messages.append(AIMessage(content=c))
                    elif t == "system":
                        convo_messages.append(SystemMessage(content=c))
        # add current
        convo_messages.append(HumanMessage(content=user_text or ""))
        # Decide response shape
        resp_type = None
        if isinstance(backend, dict):
            resp_type = backend.get("responseType") or backend.get("type") or backend.get("format")
            if isinstance(resp_type, str):
                resp_type = resp_type.lower()

        if resp_type == "table" or (isinstance(backend, dict) and ("columns" in backend and "values" in backend)):
            # Always use context-based explanation and attach full backend JSON as metadata
            expl = await _maybe_generate_explanation(backend, question=user_text or "", convo_messages=convo_messages)
            content_out = expl if expl else text
            ai = AIMessage(content=content_out, response_metadata={"irbot": backend})
        else:
            # String or other response types: produce a TTS-friendly summary as content; return raw backend text in metadata
            try:
                tts_text = await tts_summarize_task(original_text=text)
            except Exception:
                tts_text = text
            ai = AIMessage(content=tts_text, response_metadata={"irbot": backend, "raw_text": text})
        # Note: We intentionally do not use writer here; updates mode will include final agent value
        # Accumulate final short-term memory for next turn
        final_messages = (previous or []) + [HumanMessage(content=user_text or ""), ai]
        return entrypoint.final(value=ai, save=final_messages)
    except Exception as exc:
        logger.error(f"IRBot backend error: {exc}")
        err = AIMessage(content=f"Backend error: {exc}")
        return entrypoint.final(value=err, save=None)


