import os
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from langgraph.func import entrypoint, task
from langgraph.graph import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    BaseMessage,
    ToolCall,
    ToolMessage,
)
from langchain_core.prompts import ChatPromptTemplate
from langgraph.store.base import BaseStore
from langgraph.config import RunnableConfig
from langchain_core.runnables.config import ensure_config
from langgraph.config import get_store


# ---- Tools (telco) ----

try:
    from . import tools as telco_tools  # type: ignore
except Exception:
    import importlib.util as _ilu
    _dir = os.path.dirname(__file__)
    _tools_path = os.path.join(_dir, "tools.py")
    _spec = _ilu.spec_from_file_location("telco_agent_tools", _tools_path)
    telco_tools = _ilu.module_from_spec(_spec)  # type: ignore
    assert _spec and _spec.loader
    _spec.loader.exec_module(telco_tools)  # type: ignore

# Aliases for tool functions
start_login_tool = telco_tools.start_login_tool
verify_login_tool = telco_tools.verify_login_tool
get_current_package_tool = telco_tools.get_current_package_tool
get_data_balance_tool = telco_tools.get_data_balance_tool
list_available_packages_tool = telco_tools.list_available_packages_tool
recommend_packages_tool = telco_tools.recommend_packages_tool
get_roaming_info_tool = telco_tools.get_roaming_info_tool
close_contract_tool = telco_tools.close_contract_tool
list_addons_tool = telco_tools.list_addons_tool
purchase_roaming_pass_tool = telco_tools.purchase_roaming_pass_tool
change_package_tool = telco_tools.change_package_tool
get_billing_summary_tool = telco_tools.get_billing_summary_tool
set_data_alerts_tool = telco_tools.set_data_alerts_tool
check_status = telco_tools.check_status

# Import helper functions
try:
    from ..helper_functions import write_status, reset_status
except Exception:
    import importlib.util as _ilu
    _dir = os.path.dirname(os.path.dirname(__file__))
    _helper_path = os.path.join(_dir, "helper_functions.py")
    _spec = _ilu.spec_from_file_location("helper_functions", _helper_path)
    _helper_module = _ilu.module_from_spec(_spec)  # type: ignore
    assert _spec and _spec.loader
    _spec.loader.exec_module(_helper_module)  # type: ignore
    write_status = _helper_module.write_status
    reset_status = _helper_module.reset_status


"""ReAct agent entrypoint and system prompt for Telco assistant."""


SYSTEM_PROMPT = (
    "You are a warm, helpful mobile operator assistant. Greet briefly, then ask for the caller's mobile number (MSISDN). "
    "IDENTITY IS MANDATORY: After collecting the number, call start_login_tool to send a one-time code via SMS, then ask for the 6-digit code. "
    "Call verify_login_tool with the code. Do NOT proceed unless verified=true. If not verified, ask ONLY for the next missing item and retry. "
    "AFTER VERIFIED: Support these tasks and ask one question per turn: "
    "(1) Show current package and contract; (2) Check current data balance; (3) Explain roaming in a country and available passes; (4) Recommend packages with costs based on usage/preferences; (5) Close contract (require explicit yes/no confirmation). "
    "When recommending, include monthly fees and key features, and keep answers concise. When closing contracts, summarize any early termination fee before asking for confirmation. "
    "STYLE: Concise (1–2 sentences), friendly, and action-oriented. "
    "TTS SAFETY: Output must be plain text suitable for text-to-speech. Do not use markdown, bullets, asterisks, emojis, or special typography. Use only ASCII punctuation and straight quotes."
)

SECONDARY_SYSTEM_PROMPT = (
    "You are a lively, personable mobile operator assistant keeping customers entertained while their request processes in the background. "
    "Your goal is to make the wait enjoyable - be playful, share interesting facts, tell brief jokes, or engage in light conversation. "
    "If they ask about status, check using check_status tool and present it in an upbeat way. "
    "If they're bored or impatient, sympathize warmly and distract them with something fun - ask about their day, share a quick tech tip, or make them smile. "
    "For small talk (weather, location, hobbies, sports, random questions), engage enthusiastically and naturally - show genuine interest! "
    "You can answer quick questions about their package, data balance, or roaming options. "
    "DO NOT start new long operations (changing packages, closing contracts, purchasing passes) - playfully explain you're juggling their current request and can help with that next. "
    "PERSONALITY: Friendly, upbeat, conversational, and entertaining - like a fun colleague who makes waiting time fly by! "
    "STYLE: Natural (2-3 sentences), warm, and engaging. Mix status updates with personality - don't just recite percentages robotically. "
    "TTS SAFETY: Plain text only - no markdown, bullets, asterisks, emojis, or special formatting. Use ASCII punctuation and straight quotes."
)


_MODEL_NAME = os.getenv("REACT_MODEL", os.getenv("CLARIFY_MODEL", "gpt-4o"))
_LLM = ChatOpenAI(model=_MODEL_NAME, temperature=0.3)
_HELPER_LLM = ChatOpenAI(model=_MODEL_NAME, temperature=0.7)

# Main thread tools (all tools)
_MAIN_TOOLS = [
    start_login_tool,
    verify_login_tool,
    get_current_package_tool,
    get_data_balance_tool,
    list_available_packages_tool,
    recommend_packages_tool,
    get_roaming_info_tool,
    close_contract_tool,
    list_addons_tool,
    purchase_roaming_pass_tool,
    change_package_tool,
    get_billing_summary_tool,
    set_data_alerts_tool,
]

# Secondary thread tools (limited to safe, quick operations)
_SECONDARY_TOOLS = [
    check_status,
    get_current_package_tool,
    get_data_balance_tool,
    list_available_packages_tool,
    get_roaming_info_tool,
    list_addons_tool,
]

_LLM_WITH_TOOLS = _LLM.bind_tools(_MAIN_TOOLS)
_HELPER_LLM_WITH_TOOLS = _HELPER_LLM.bind_tools(_SECONDARY_TOOLS)
_ALL_TOOLS_BY_NAME = {t.name: t for t in (_MAIN_TOOLS + [check_status])}

# Synthesis chain for merging tool results with interim conversation
_SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful mobile operator assistant. A long-running operation you were executing has just finished. Your goal is to synthesize the result with the conversation that happened while the operation was running.",
        ),
        ("user", "Here is the result from the operation:\n\n{tool_result}"),
        (
            "user",
            "While the operation was running, we had this conversation:\n\n{interim_conversation}",
        ),
        (
            "user",
            "Now, please craft a single, natural-sounding response that seamlessly continues the conversation. Start by acknowledging the last message if appropriate, and then present the operation result. The response should feel like a direct and fluid continuation of the chat, smoothly integrating the outcome. Keep it brief (1-2 sentences) and TTS-safe (no markdown or special formatting).",
        ),
    ]
)
_SYNTHESIS_LLM = ChatOpenAI(model=_MODEL_NAME, temperature=0.7)
_SYNTHESIS_CHAIN = _SYNTHESIS_PROMPT | _SYNTHESIS_LLM

# Simple per-run context storage (thread-safe enough for local dev worker)
_CURRENT_THREAD_ID: str | None = None
_CURRENT_MSISDN: str | None = None

# ---- Logger ----
logger = logging.getLogger("TelcoAgent")
if not logger.handlers:
    _stream = logging.StreamHandler()
    _stream.setLevel(logging.INFO)
    _fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    _stream.setFormatter(_fmt)
    logger.addHandler(_stream)
    try:
        _file = logging.FileHandler(str(Path(__file__).resolve().parents[2] / "app.log"))
        _file.setLevel(logging.INFO)
        _file.setFormatter(_fmt)
        logger.addHandler(_file)
    except Exception:
        pass
logger.setLevel(logging.INFO)
_DEBUG = os.getenv("TELCO_DEBUG", "0") not in ("", "0", "false", "False")

def _get_thread_id(config: Dict[str, Any] | None, messages: List[BaseMessage]) -> str:
    cfg = config or {}
    # Try dict-like and attribute-like access
    def _safe_get(container: Any, key: str, default: Any = None) -> Any:
        try:
            if isinstance(container, dict):
                return container.get(key, default)
            if hasattr(container, "get"):
                return container.get(key, default)
            if hasattr(container, key):
                return getattr(container, key, default)
        except Exception:
            return default
        return default

    try:
        conf = _safe_get(cfg, "configurable", {}) or {}
        for key in ("thread_id", "session_id", "thread"):
            val = _safe_get(conf, key)
            if isinstance(val, str) and val:
                return val
    except Exception:
        pass

    # Fallback: look for session_id on the latest human message additional_kwargs
    try:
        for m in reversed(messages or []):
            addl = getattr(m, "additional_kwargs", None)
            if isinstance(addl, dict) and isinstance(addl.get("session_id"), str) and addl.get("session_id"):
                return addl.get("session_id")
            if isinstance(m, dict):
                ak = m.get("additional_kwargs") or {}
                if isinstance(ak, dict) and isinstance(ak.get("session_id"), str) and ak.get("session_id"):
                    return ak.get("session_id")
    except Exception:
        pass
    return "unknown"


def _trim_messages(messages: List[BaseMessage], max_messages: int = 40) -> List[BaseMessage]:
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


def _sanitize_conversation(messages: List[BaseMessage]) -> List[BaseMessage]:
    """Ensure tool messages only follow an assistant message with tool_calls.

    Drops orphan tool messages that could cause OpenAI 400 errors.
    """
    sanitized: List[BaseMessage] = []
    pending_tool_ids: set[str] | None = None
    for m in messages:
        try:
            if isinstance(m, AIMessage):
                sanitized.append(m)
                tool_calls = getattr(m, "tool_calls", None) or []
                ids: set[str] = set()
                for tc in tool_calls:
                    # ToolCall can be mapping-like or object-like
                    if isinstance(tc, dict):
                        _id = tc.get("id") or tc.get("tool_call_id")
                    else:
                        _id = getattr(tc, "id", None) or getattr(tc, "tool_call_id", None)
                    if isinstance(_id, str):
                        ids.add(_id)
                pending_tool_ids = ids if ids else None
                continue
            if isinstance(m, ToolMessage):
                if pending_tool_ids and isinstance(getattr(m, "tool_call_id", None), str) and m.tool_call_id in pending_tool_ids:
                    sanitized.append(m)
                    # keep accepting subsequent tool messages for the same assistant turn
                    continue
                # Orphan tool message: drop
                continue
            # Any other message resets expectation
            sanitized.append(m)
            pending_tool_ids = None
        except Exception:
            # On any unexpected shape, include as-is but reset to avoid pairing issues
            sanitized.append(m)
            pending_tool_ids = None
    # Ensure the conversation doesn't start with a ToolMessage
    while sanitized and isinstance(sanitized[0], ToolMessage):
        sanitized.pop(0)
    return sanitized


def _today_string() -> str:
    override = os.getenv("RBC_FEES_TODAY_OVERRIDE")
    if isinstance(override, str) and override.strip():
        try:
            datetime.strptime(override.strip(), "%Y-%m-%d")
            return override.strip()
        except Exception:
            pass
    return datetime.utcnow().strftime("%Y-%m-%d")


def _system_messages() -> List[BaseMessage]:
    today = _today_string()
    return [SystemMessage(content=SYSTEM_PROMPT)]


@task()
def call_llm(messages: List[BaseMessage]) -> AIMessage:
    """LLM decides whether to call a tool or not."""
    if _DEBUG:
        try:
            preview = [f"{getattr(m,'type', getattr(m,'role',''))}:{str(getattr(m,'content', m))[:80]}" for m in messages[-6:]]
            logger.info("call_llm: messages_count=%s preview=%s", len(messages), preview)
        except Exception:
            logger.info("call_llm: messages_count=%s", len(messages))
    resp = _LLM_WITH_TOOLS.invoke(_system_messages() + messages)
    try:
        # Log assistant content or tool calls for visibility
        tool_calls = getattr(resp, "tool_calls", None) or []
        if tool_calls:
            names = []
            for tc in tool_calls:
                n = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if isinstance(n, str):
                    names.append(n)
            logger.info("LLM tool_calls: %s", names)
        else:
            txt = getattr(resp, "content", "") or ""
            if isinstance(txt, str) and txt.strip():
                logger.info("LLM content: %s", (txt if len(txt) <= 500 else (txt[:500] + "…")))
    except Exception:
        pass
    return resp


@task()
def call_tool(tool_call: ToolCall) -> ToolMessage:
    """Execute a tool call and wrap result in a ToolMessage."""
    global _CURRENT_MSISDN
    tool = _ALL_TOOLS_BY_NAME[tool_call["name"]]
    args = tool_call.get("args") or {}
    # Auto-inject session context and remembered msisdn
    if tool.name in ("start_login_tool", "verify_login_tool"):
        if "session_id" not in args and _CURRENT_THREAD_ID:
            args["session_id"] = _CURRENT_THREAD_ID
    if "msisdn" not in args and _CURRENT_MSISDN:
        args["msisdn"] = _CURRENT_MSISDN
    # If the LLM passes msisdn, remember it for subsequent calls
    try:
        if isinstance(args.get("msisdn"), str) and args.get("msisdn").strip():
            _CURRENT_MSISDN = args.get("msisdn")
    except Exception:
        pass
    if _DEBUG:
        try:
            logger.info("call_tool: name=%s args_keys=%s", tool.name, list(args.keys()))
        except Exception:
            logger.info("call_tool: name=%s", tool.name)
    result = tool.invoke(args)
    # Ensure string content
    content = result if isinstance(result, str) else json.dumps(result)
    try:
        # Log tool result previews and OTP debug_code when present
        if tool.name == "verify_login_tool":
            try:
                data = json.loads(content)
                logger.info("verify_login: verified=%s", data.get("verified"))
            except Exception:
                logger.info("verify_login result: %s", content[:300])
        elif tool.name == "start_login_tool":
            try:
                data = json.loads(content)
                logger.info("start_login_tool: sent=%s", data.get("sent"))
            except Exception:
                logger.info("start_login_tool: %s", content[:300])
        else:
            # Generic preview
            logger.info("tool %s result: %s", tool.name, (content[:300] if isinstance(content, str) else str(content)[:300]))
    except Exception:
        pass
    # Never expose OTP debug_code to the LLM
    try:
        if tool.name == "start_login_tool":
            data = json.loads(content)
            if isinstance(data, dict) and "debug_code" in data:
                data.pop("debug_code", None)
                content = json.dumps(data)
    except Exception:
        pass
    return ToolMessage(content=content, tool_call_id=tool_call["id"], name=tool.name)


@entrypoint()
def agent(input_dict: dict, previous: Any = None, config: RunnableConfig | None = None, store: BaseStore | None = None):
    """Multi-threaded telco agent supporting concurrent conversations during long operations.
    
    Args:
        input_dict: Must contain:
            - messages: List of new messages
            - thread_type: "main" or "secondary"
            - interim_messages_reset: bool (reset interim conversation)
        previous: Previous state dict with {messages, interim_messages}
        config: Runtime configuration
        store: LangGraph store for coordination
    """
    # Extract input parameters - handle both dict and list formats
    if isinstance(input_dict, dict):
        messages = input_dict.get("messages", [])
        thread_type = input_dict.get("thread_type", "main")
        interim_messages_reset = input_dict.get("interim_messages_reset", True)
    else:
        # input_dict is actually a list of messages (legacy format)
        messages = input_dict if isinstance(input_dict, list) else []
        thread_type = "main"
        interim_messages_reset = True
    
    # Get store (from parameter or global context)
    if store is None:
        store = get_store()
    
    # Get namespace for coordination
    cfg = ensure_config() if config is None else config
    conf = cfg.get("configurable", {}) if isinstance(cfg, dict) else {}
    namespace = conf.get("namespace_for_memory")
    if namespace and not isinstance(namespace, tuple):
        try:
            namespace = tuple(namespace)
        except (TypeError, ValueError):
            namespace = (str(namespace),)
    
    # Merge with previous state
    interim_messages = []
    if previous:
        if isinstance(previous, dict):
            previous_messages = previous.get("messages", [])
            previous_interim_messages = previous.get("interim_messages", [])
        else:
            # Fallback: previous might be a list of messages (old format)
            previous_messages = list(previous) if isinstance(previous, list) else []
            previous_interim_messages = []
        
        messages = add_messages(previous_messages, messages)
        interim_messages = add_messages(messages, previous_interim_messages)
    
    # Trim and sanitize
    messages = _trim_messages(messages, max_messages=int(os.getenv("RBC_FEES_MAX_MSGS", "40")))
    messages = _sanitize_conversation(messages)
    
    # Get thread ID and session context
    thread_id = _get_thread_id(cfg, messages)
    default_msisdn = conf.get("msisdn") or conf.get("phone_number")
    
    # Update module context
    global _CURRENT_THREAD_ID, _CURRENT_MSISDN
    _CURRENT_THREAD_ID = thread_id
    _CURRENT_MSISDN = default_msisdn
    
    logger.info("agent start: thread_id=%s thread_type=%s total_in=%s", thread_id, thread_type, len(messages))
    
    # Secondary thread: Set processing lock at start
    if thread_type != "main" and namespace:
        store.put(namespace, "secondary_status", {
            "processing": True,
            "started_at": time.time()
        })
        
        # Check abort flag before starting
        abort_signal = store.get(namespace, "secondary_abort")
        if abort_signal and abort_signal.value.get("abort"):
            # Clean up and exit silently
            store.put(namespace, "secondary_status", {"processing": False, "aborted": True})
            store.delete(namespace, "secondary_abort")
            prev_state = previous if isinstance(previous, dict) else {"messages": [], "interim_messages": []}
            return entrypoint.final(value=[], save=prev_state)
    
    # Choose LLM and system prompt based on thread type
    if thread_type == "main":
        active_llm_with_tools = _LLM_WITH_TOOLS
        system_prompt = SYSTEM_PROMPT
    else:
        active_llm_with_tools = _HELPER_LLM_WITH_TOOLS
        system_prompt = SECONDARY_SYSTEM_PROMPT
    
    # Build system messages
    sys_messages = [SystemMessage(content=system_prompt)]
    
    # First LLM call
    llm_response = active_llm_with_tools.invoke(sys_messages + messages)
    
    # Tool execution loop
    while True:
        tool_calls = getattr(llm_response, "tool_calls", None) or []
        if not tool_calls:
            break
        
        # Execute tools in parallel
        futures = [call_tool(tc) for tc in tool_calls]
        tool_results = [f.result() for f in futures]
        
        if _DEBUG:
            try:
                logger.info("tool_results: count=%s names=%s", len(tool_results), [tr.name for tr in tool_results])
            except Exception:
                pass
        
        messages = add_messages(messages, [llm_response, *tool_results])
        llm_response = active_llm_with_tools.invoke(sys_messages + messages)
    
    # Append final assistant turn
    messages = add_messages(messages, [llm_response])
    
    # Update interim messages
    if interim_messages_reset:
        interim_messages = add_messages([], [llm_response])
    else:
        interim_messages = add_messages(interim_messages, [llm_response])
    
    # Main thread: Reset status after completion and signal completion
    if thread_type == "main" and namespace:
        reset_status(store, namespace)
        # Signal that main operation is complete
        store.put(namespace, "main_operation_complete", {
            "completed": True,
            "timestamp": time.time()
        })
    
    # Secondary thread: Handle abort and release lock
    if thread_type != "main" and namespace:
        # Check abort flag before writing results
        abort_signal = store.get(namespace, "secondary_abort")
        if abort_signal and abort_signal.value.get("abort"):
            # Clean up and exit without saving
            store.put(namespace, "secondary_status", {"processing": False, "aborted": True})
            store.delete(namespace, "secondary_abort")
            prev_state = previous if isinstance(previous, dict) else {"messages": [], "interim_messages": []}
            return entrypoint.final(value=[], save=prev_state)
        
        # Safe to proceed - write results and release lock
        store.put(namespace, "secondary_interim_messages", {"messages": interim_messages})
        store.put(namespace, "secondary_status", {
            "processing": False,
            "completed_at": time.time()
        })
    
    # Main thread: Wait for secondary and synthesize if needed
    if thread_type == "main" and namespace:
        # Wait for secondary thread to finish processing (with timeout)
        MAX_WAIT_SECONDS = 15
        CHECK_INTERVAL = 0.5
        elapsed = 0
        
        while elapsed < MAX_WAIT_SECONDS:
            secondary_status = store.get(namespace, "secondary_status")
            if not secondary_status or not secondary_status.value.get("processing", False):
                break
            time.sleep(CHECK_INTERVAL)
            elapsed += CHECK_INTERVAL
        
        # If timed out, set abort flag
        if elapsed >= MAX_WAIT_SECONDS:
            store.put(namespace, "secondary_abort", {
                "abort": True,
                "reason": "main_thread_timeout",
                "timestamp": time.time()
            })
            time.sleep(0.2)  # Brief moment for secondary to see abort
        
        # Read and synthesize interim messages (only if meaningful)
        interim_messages_from_store = store.get(namespace, "secondary_interim_messages")
        if interim_messages_from_store:
            interim_conv = interim_messages_from_store.value.get("messages")
            if interim_conv and len(interim_conv) > 0:
                # Filter out status-only messages for synthesis
                meaningful_messages = []
                for m in interim_conv:
                    content = getattr(m, 'content', '').lower()
                    # Skip if it's just about status/progress
                    if not any(word in content for word in ['processing', 'complete', 'running', 'percent', 'status']):
                        meaningful_messages.append(m)
                
                # Only synthesize if there were non-status conversations
                if meaningful_messages:
                    tool_result_content = messages[-1].content if messages else ""
                    interim_conv_str = "\n".join(
                        [f"{getattr(m, 'type', 'message')}: {getattr(m, 'content', '')}" for m in meaningful_messages]
                    )
                    try:
                        final_answer = _SYNTHESIS_CHAIN.invoke({
                            "tool_result": tool_result_content,
                            "interim_conversation": interim_conv_str,
                        })
                        # Add visual marker for synthesis
                        synthesized_content = f"{final_answer.content}"
                        messages[-1] = AIMessage(content=synthesized_content)
                        logger.info("Synthesized response with %d meaningful interim messages", len(meaningful_messages))
                    except Exception as e:
                        logger.warning("Synthesis failed: %s", e)
                else:
                    logger.info("No meaningful interim messages to synthesize (only status checks)")
                
                store.delete(namespace, "secondary_interim_messages")
        
        # Clean up coordination state
        reset_status(store, namespace)
        store.delete(namespace, "secondary_status")
        store.delete(namespace, "secondary_abort")
        # Keep completion flag briefly for client to see
        store.put(namespace, "main_operation_complete", {
            "completed": True,
            "timestamp": time.time(),
            "ready_for_new_operation": True
        })
    
    # Prepare final state
    current_state = {
        "messages": messages,
        "interim_messages": interim_messages,
    }
    
    final_text = getattr(messages[-1], "content", "") if messages else ""
    try:
        if isinstance(final_text, str) and final_text.strip():
            logger.info("final content: %s", (final_text if len(final_text) <= 500 else (final_text[:500] + "…")))
    except Exception:
        pass
    
    logger.info("agent done: thread_id=%s thread_type=%s total_messages=%s", thread_id, thread_type, len(messages))
    
    return entrypoint.final(value=messages, save=current_state)


