#!/usr/bin/env python3
"""
Client for multi-threaded telco agent.

This client handles routing between main and secondary threads:
- Main thread: Handles long-running operations (package changes, contract closures, etc.)
- Secondary thread: Handles interim queries while main thread is busy

Usage:
    # Interactive mode
    python telco_client.py --interactive
    
    # Single message
    python telco_client.py
    
    # Custom server URL
    python telco_client.py --url http://localhost:2024 --interactive
"""

import argparse
import asyncio
import sys
import time
import uuid
from pathlib import Path
import contextlib

from langgraph_sdk import get_client
from langgraph_sdk.schema import StreamPart
import httpx
from typing import Any, Optional


# Terminal colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
FG_BLUE = "\033[34m"
FG_GREEN = "\033[32m"
FG_CYAN = "\033[36m"
FG_YELLOW = "\033[33m"
FG_MAGENTA = "\033[35m"
FG_GRAY = "\033[90m"
PROMPT_STR = f"{BOLD}> {RESET}"


def _show_prompt() -> None:
    sys.stdout.write(PROMPT_STR)
    sys.stdout.flush()


def _write_line(s: str) -> None:
    sys.stdout.write("\r\x1b[2K" + s + "\n")
    sys.stdout.flush()
    _show_prompt()


def _write_line_no_prompt(s: str) -> None:
    sys.stdout.write("\r\x1b[2K" + s + "\n")
    sys.stdout.flush()


def _log(msg: str) -> None:
    _write_line(f"{FG_GRAY}{msg}{RESET}")


def _user(msg: str) -> None:
    _write_line_no_prompt(f"{FG_BLUE}User{RESET}: {msg}")


def _assistant(msg: str) -> None:
    _write_line(f"{FG_GREEN}Assistant{RESET}: {msg}")


def _event(label: str, text: str) -> None:
    _write_line(f"{FG_YELLOW}[{label}]{RESET} {DIM}{text}{RESET}")


def _extract_text_from_messages(messages: list[Any]) -> Optional[str]:
    """Extract text from a list of message objects."""
    if not isinstance(messages, list) or not messages:
        return None
    last = messages[-1]
    if isinstance(last, dict):
        content = last.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            pieces: list[str] = []
            for seg in content:
                if isinstance(seg, dict):
                    t = seg.get("text") or seg.get("content") or ""
                    if isinstance(t, str) and t:
                        pieces.append(t)
            if pieces:
                return "\n".join(pieces)
    return None


def _extract_text(payload: Any, *, graph_key: str | None = None) -> Optional[str]:
    """Extract assistant text from various payload shapes."""
    # Direct string
    if isinstance(payload, str):
        return payload
    # List of messages or mixed
    if isinstance(payload, list):
        text = _extract_text_from_messages(payload)
        if text:
            return text
        # Fallback: any string entries
        for v in payload:
            t = _extract_text(v, graph_key=graph_key)
            if t:
                return t
        return None
    # Dict payloads
    if isinstance(payload, dict):
        # Graph-level direct string
        if graph_key and isinstance(payload.get(graph_key), str):
            return payload[graph_key]
        # Common shapes
        if isinstance(payload.get("value"), (str, list, dict)):
            t = _extract_text(payload.get("value"), graph_key=graph_key)
            if t:
                return t
        if isinstance(payload.get("messages"), list):
            t = _extract_text_from_messages(payload.get("messages", []))
            if t:
                return t
        if isinstance(payload.get("content"), str):
            return payload.get("content")
        # Search nested values
        for v in payload.values():
            t = _extract_text(v, graph_key=graph_key)
            if t:
                return t
    return None


async def stream_run(
    client,
    thread_id: str,
    graph: str,
    message: dict,
    label: str,
    *,
    namespace_for_memory: tuple[str, ...],
    global_last_text: dict[str, str],  # Shared across runs for deduplication
) -> int:
    """Stream a run and print output."""
    printed_once = False
    command: dict[str, Any] | None = None

    config = {
        "configurable": {
            "thread_id": thread_id,
            "namespace_for_memory": list(namespace_for_memory),
        }
    }

    while True:
        last_text: Optional[str] = global_last_text.get("last", None)  # Global de-dupe
        stream = client.runs.stream(
            thread_id=thread_id,
            assistant_id=graph,
            input=message if command is None else None,
            command=command,
            stream_mode=["values", "custom"],
            config=config,
        )

        saw_interrupt = False
        async for part in stream:
            assert isinstance(part, StreamPart)
            if part.event == "metadata":
                data = part.data or {}
                run_id = (data.get("run_id") if isinstance(data, dict) else None) or "?"
                _event(label, f"run started (run_id={run_id}, thread_id={thread_id})")
                continue
            if part.event == "custom":
                data = part.data
                text = _extract_text(data, graph_key=graph)
                if text and text != last_text:
                    _assistant(text)
                    last_text = text
                    global_last_text["last"] = text
                continue
            if part.event == "values":
                data = part.data
                text = _extract_text(data, graph_key=graph)
                if text and text != last_text:
                    _assistant(text)
                    last_text = text
                    global_last_text["last"] = text
                continue
            # Uncomment for debug info
            # if part.event:
            #     _event(label, f"{part.event} {part.data}")
            if part.event == "end":
                return 0

        if saw_interrupt:
            command = {"resume": None}
            continue
        return 0


async def ainput(prompt: str = "") -> str:
    """Async input wrapper."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def read_latest_status(client, namespace_for_memory: tuple[str, ...]) -> dict:
    """Read the latest tool status from the store."""
    ns_list = list(namespace_for_memory)
    try:
        items = await client.store.search_items(ns_list)
    except Exception:
        return {}
    
    # Normalize return shape: SDK may return a dict with 'items' or a bare list
    items_list: list[Any] | None = None
    if isinstance(items, dict):
        inner = items.get("items")
        if isinstance(inner, list):
            items_list = inner
    elif isinstance(items, list):
        items_list = items
    
    if not items_list:
        return {}
    
    # Walk from the end to find the most recent item that has a 'status'
    for item in reversed(items_list):
        value = getattr(item, "value", None)
        if value is None and isinstance(item, dict):
            value = item.get("value")
        if isinstance(value, dict) and "status" in value:
            return value
    
    # Fallback to last value if present
    last = items_list[-1]
    value = getattr(last, "value", None)
    if value is None and isinstance(last, dict):
        value = last.get("value")
    return value if isinstance(value, dict) else {}


async def check_completion_flag(client, namespace_for_memory: tuple[str, ...]) -> bool:
    """Check if main operation has completed recently."""
    ns_list = list(namespace_for_memory)
    try:
        items = await client.store.search_items(ns_list)
    except Exception:
        return False
    
    # Normalize return shape
    items_list: list[Any] | None = None
    if isinstance(items, dict):
        inner = items.get("items")
        if isinstance(inner, list):
            items_list = inner
    elif isinstance(items, list):
        items_list = items
    
    if not items_list:
        return False
    
    # Look for completion flag
    for item in reversed(items_list):
        key = getattr(item, "key", None) or (item.get("key") if isinstance(item, dict) else None)
        if key == "main_operation_complete":
            value = getattr(item, "value", None)
            if value is None and isinstance(item, dict):
                value = item.get("value")
            if isinstance(value, dict) and value.get("ready_for_new_operation"):
                return True
    
    return False


async def run_client(
    base_url: str,
    graph: str,
    user_id: str,
    interactive: bool,
    thread_file: str | None,
    initial_message: str | None,
) -> int:
    """Main client logic."""
    client = get_client(url=base_url)

    # Primary and secondary thread ids
    thread_path = Path(thread_file) if thread_file else None
    
    # Main thread: load from file if present; otherwise create on server and persist
    if thread_path and thread_path.exists():
        try:
            loaded = thread_path.read_text().strip().splitlines()
            thread_id_main = loaded[0] if loaded else None
        except Exception:
            thread_id_main = None
        
        if not thread_id_main:
            t = await client.threads.create()
            thread_id_main = getattr(t, "thread_id", None) or (
                t["thread_id"] if isinstance(t, dict) else str(uuid.uuid4())
            )
            try:
                thread_path.write_text(thread_id_main + "\n")
            except Exception:
                pass
        else:
            try:
                await client.threads.create(thread_id=thread_id_main, if_exists="do_nothing")
            except httpx.HTTPStatusError as e:
                if getattr(e, "response", None) is not None and e.response.status_code == 409:
                    pass
                else:
                    raise
    else:
        t = await client.threads.create()
        thread_id_main = getattr(t, "thread_id", None) or (
            t["thread_id"] if isinstance(t, dict) else str(uuid.uuid4())
        )
        if thread_path:
            try:
                thread_path.write_text(thread_id_main + "\n")
            except Exception:
                pass

    # Secondary thread: always create on server (ephemeral)
    t2 = await client.threads.create()
    thread_id_updates = getattr(t2, "thread_id", None) or (
        t2["thread_id"] if isinstance(t2, dict) else str(uuid.uuid4())
    )

    # Shared namespace used by server agent's tools
    namespace_for_memory = (user_id, "tools_updates")

    print(f"{FG_MAGENTA}Telco Agent Multi-Threaded Client{RESET}")
    print(f"Main Thread ID: {FG_CYAN}{thread_id_main}{RESET}")
    print(f"Secondary Thread ID: {FG_CYAN}{thread_id_updates}{RESET}")
    print(f"Namespace: {FG_CYAN}{namespace_for_memory}{RESET}")
    print()

    # Interactive loop
    if interactive:
        print(f"{FG_CYAN}Interactive Mode: Type your message. Use /exit to quit.{RESET}")
        print(f"{FG_GRAY}Long operations will run in background. You can ask questions while they run.{RESET}")
        print()
        
        # Clear any stale flags from previous sessions
        try:
            ns_list = list(namespace_for_memory)
            await client.store.delete_item(ns_list, "main_operation_complete")
            await client.store.delete_item(ns_list, "working-tool-status-update")
            await client.store.delete_item(ns_list, "secondary_status")
            await client.store.delete_item(ns_list, "secondary_abort")
            await client.store.delete_item(ns_list, "secondary_interim_messages")
        except Exception:
            pass  # Flags might not exist, that's okay
        
        _show_prompt()
        
        # Track background task and state
        main_job: asyncio.Task[int] | None = None
        interim_messages_reset = True
        global_last_text: dict[str, str] = {}  # Global deduplication
        cooldown_until: float = 0  # Cooldown timestamp
        last_operation_complete_time: float = 0

        while True:
            try:
                user_text = await ainput("")
            except (KeyboardInterrupt, EOFError):
                user_text = "/exit"
            
            user_text = (user_text or "").strip()
            if not user_text:
                continue
            
            if user_text.lower() in {"exit", "quit", "/exit"}:
                break
            
            _user(user_text)

            # Check if we're in cooldown period
            current_time = time.time()
            if current_time < cooldown_until:
                wait_time = int(cooldown_until - current_time)
                _event("cooldown", f"Operation just completed, waiting {wait_time}s before starting new operation...")
                await asyncio.sleep(cooldown_until - current_time)
                cooldown_until = 0
                # Clear completion flag after cooldown
                try:
                    ns_list = list(namespace_for_memory)
                    # Try to delete completion flag (may not exist)
                    try:
                        await client.store.delete_item(ns_list, "main_operation_complete")
                    except Exception:
                        pass
                except Exception:
                    pass

            # Determine current status based ONLY on server-side store
            # Don't use main_job.done() because the client task finishes quickly
            # even though the server operation continues
            long_info = await read_latest_status(client, namespace_for_memory)
            long_running = bool(long_info.get("status") == "running")
            just_completed = await check_completion_flag(client, namespace_for_memory)
            
            # If operation just completed, set cooldown but don't skip the message
            if just_completed and last_operation_complete_time != current_time:
                _event("status", f"{FG_MAGENTA}Operation complete! Ready for new requests.{RESET}")
                cooldown_until = time.time() + 2.0  # 2 second cooldown
                last_operation_complete_time = current_time
                global_last_text.clear()  # Clear dedup cache
                main_job = None
                # Clear completion flag
                try:
                    ns_list = list(namespace_for_memory)
                    await client.store.delete_item(ns_list, "main_operation_complete")
                except Exception:
                    pass
                # Don't continue - let the message be processed after cooldown
                # The cooldown check above will handle waiting if needed

            # Routing logic: Use ONLY server-side status, not client task status
            if long_running and not just_completed:
                # Secondary thread: handle queries during long operation
                progress = long_info.get("progress", "?")
                tool_name = long_info.get("tool_name", "operation")
                _event("routing", f"Operation in progress ({progress}%), routing to secondary thread")
                payload = {
                    "messages": [{"type": "human", "content": user_text}],
                    "thread_type": "secondary",
                    "interim_messages_reset": False,
                }
                await stream_run(
                    client,
                    thread_id_updates,
                    graph,
                    payload,
                    label=f"secondary [{progress}%]",
                    namespace_for_memory=namespace_for_memory,
                    global_last_text=global_last_text,
                )
                interim_messages_reset = False
            else:
                # Main thread: start new operation
                _event("routing", "Starting new operation on main thread (background)")
                interim_messages_reset = True
                global_last_text.clear()  # Clear for new operation
                payload = {
                    "messages": [{"type": "human", "content": user_text}],
                    "thread_type": "main",
                    "interim_messages_reset": interim_messages_reset,
                }

                async def run_main() -> int:
                    result = await stream_run(
                        client,
                        thread_id_main,
                        graph,
                        payload,
                        label="main",
                        namespace_for_memory=namespace_for_memory,
                        global_last_text=global_last_text,
                    )
                    # After completion, signal cooldown
                    return result

                main_job = asyncio.create_task(run_main())
                # Do not await; allow user to type while long task runs

        # On exit, best-effort wait for background
        if main_job is not None:
            print(f"\n{FG_GRAY}Waiting for background task to complete...{RESET}")
            with contextlib.suppress(Exception):
                await asyncio.wait_for(main_job, timeout=10)
        return 0
    else:
        # Non-interactive: single message to main thread
        msg = initial_message or "Hello, I need help with my mobile account"
        print(f"{FG_BLUE}Sending:{RESET} {msg}\n")
        payload = {
            "messages": [{"type": "human", "content": msg}],
            "thread_type": "main",
            "interim_messages_reset": True,
        }
        global_last_text: dict[str, str] = {}
        return await stream_run(
            client,
            thread_id_main,
            graph,
            payload,
            label="single",
            namespace_for_memory=namespace_for_memory,
            global_last_text=global_last_text,
        )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Client for multi-threaded telco agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (recommended)
  python telco_client.py --interactive
  
  # Single message
  python telco_client.py --message "What's my current package?"
  
  # Custom server and user
  python telco_client.py --url http://localhost:8000 --user john_doe --interactive
  
  # Use different thread file
  python telco_client.py --thread-file .telco_thread --interactive
        """
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:2024",
        help="LangGraph server base URL (default: http://127.0.0.1:2024)"
    )
    parser.add_argument(
        "--graph",
        default="telco-agent",
        help="Graph name as defined in langgraph.json (default: telco-agent)"
    )
    parser.add_argument(
        "--user",
        default="fciannella",
        help="User ID for namespace (default: fciannella)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode (chat continuously)"
    )
    parser.add_argument(
        "--thread-file",
        default=".telco_thread_id",
        help="Path to persist/load main thread ID (default: .telco_thread_id)"
    )
    parser.add_argument(
        "--message",
        "-m",
        help="Single message to send (non-interactive mode)"
    )
    args = parser.parse_args(argv)

    return asyncio.run(
        run_client(
            base_url=args.url,
            graph=args.graph,
            user_id=args.user,
            interactive=args.interactive,
            thread_file=args.thread_file,
            initial_message=args.message,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

