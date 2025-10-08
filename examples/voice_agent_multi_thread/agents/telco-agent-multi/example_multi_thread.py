#!/usr/bin/env python3
"""
Example script demonstrating multi-threaded telco agent usage.

This script shows how to:
1. Start a long-running operation (main thread)
2. Handle interim queries (secondary thread) while the operation runs
3. Let the agent synthesize the final response

Usage:
    python example_multi_thread.py
"""

import os
import sys
import time
import uuid
import threading
import queue
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.store.memory import InMemoryStore

# Import the agent
from react_agent import agent

# Setup
store = InMemoryStore()
thread_id_main = str(uuid.uuid4())
thread_id_secondary = str(uuid.uuid4())

user_id = "demo_user"
namespace_for_memory = (user_id, "telco_operations")

config_main = {
    "configurable": {
        "thread_id": thread_id_main,
        "namespace_for_memory": namespace_for_memory
    }
}

config_secondary = {
    "configurable": {
        "thread_id": thread_id_secondary,
        "namespace_for_memory": namespace_for_memory
    }
}

print("=" * 60)
print("Multi-Threaded Telco Agent Demo")
print("=" * 60)
print(f"Main Thread ID: {thread_id_main}")
print(f"Secondary Thread ID: {thread_id_secondary}")
print(f"Namespace: {namespace_for_memory}")
print("=" * 60)
print()

# Thread-safe printing
print_lock = threading.Lock()

def safe_print(text: str) -> None:
    with print_lock:
        print(text)

def run_agent_stream(user_text: str, thread_type: str, config: dict, interim_reset: bool) -> None:
    """Run agent and print results."""
    messages = [HumanMessage(content=user_text)]
    try:
        for mode, chunk in agent.stream(
            {
                "messages": messages,
                "thread_type": thread_type,
                "interim_messages_reset": interim_reset
            },
            stream_mode=["custom", "values"],
            config=config,
            store=store
        ):
            if isinstance(chunk, list) and chunk:
                ai_messages = [m for m in chunk if isinstance(m, AIMessage)]
                if ai_messages:
                    safe_print(f"[{thread_type}] {ai_messages[-1].content}")
            elif isinstance(chunk, str):
                safe_print(f"[{thread_type}] {chunk}")
    except Exception as e:
        safe_print(f"[{thread_type} ERROR] {e!r}")

# ============================================================================
# Demo Scenario 1: Long operation with status checks
# ============================================================================

print("SCENARIO 1: Long operation with interim status checks")
print("-" * 60)

# Start a long-running operation in the background
print("\n>>> User: 'Change my package to Premium Plus'")
print(">>> (Starting main thread in background...)")
print()

main_job = threading.Thread(
    target=run_agent_stream,
    args=("Change my package to Premium Plus", "main", config_main, True),
    daemon=True
)
main_job.start()

# Wait a bit for the operation to start
time.sleep(3)

# Now user asks about status (secondary thread)
print("\n>>> User: 'What's the status of my request?'")
print(">>> (Handled by secondary thread...)")
print()
run_agent_stream("What's the status of my request?", "secondary", config_secondary, False)

# Another query while main is still running
time.sleep(2)
print("\n>>> User: 'How much data do I have left?'")
print(">>> (Handled by secondary thread...)")
print()
run_agent_stream("How much data do I have left?", "secondary", config_secondary, False)

# Wait for main operation to complete
main_job.join()

print("\n" + "=" * 60)
print("Main operation completed and synthesized with interim conversation!")
print("=" * 60)

# ============================================================================
# Demo Scenario 2: Quick query (no multi-threading needed)
# ============================================================================

print("\n\nSCENARIO 2: Quick query (synchronous)")
print("-" * 60)

print("\n>>> User: 'What's my current package?'")
print(">>> (Quick query, handled synchronously...)")
print()
run_agent_stream("What's my current package?", "main", config_main, True)

# ============================================================================
# Demo Scenario 3: Interactive mode
# ============================================================================

print("\n\nSCENARIO 3: Interactive mode")
print("-" * 60)
print("Type your messages. Long operations will run in background.")
print("Type 'exit' to quit.")
print("-" * 60)

input_queue: "queue.Queue[str]" = queue.Queue()
stop_event = threading.Event()
main_job_active = None
interim_reset = True

def input_reader() -> None:
    try:
        while not stop_event.is_set():
            try:
                user_text = input("\nYou: ").strip()
            except (KeyboardInterrupt, EOFError):
                user_text = "exit"
            if not user_text:
                continue
            input_queue.put(user_text)
            if user_text.lower() in {"exit", "quit"}:
                break
    finally:
        pass

reader_thread = threading.Thread(target=input_reader, daemon=True)
reader_thread.start()

try:
    while True:
        try:
            user_text = input_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        if not user_text:
            continue

        if user_text.lower() in {"exit", "quit"}:
            stop_event.set()
            break

        # Check if main thread is active
        main_active = main_job_active is not None and main_job_active.is_alive()
        
        # Check store for running status
        memories = store.search(namespace_for_memory)
        current_status = None
        if memories:
            try:
                md = list(memories)[-1].value
                current_status = md.get("status")
            except Exception:
                pass

        if current_status == "running" or main_active:
            # Secondary thread (synchronous)
            safe_print("\n>>> (Long operation in progress, using secondary thread...)")
            run_agent_stream(user_text, "secondary", config_secondary, False)
            interim_reset = False
        else:
            # Main thread (background)
            safe_print("\n>>> (Starting operation in background...)")
            interim_reset = True
            t = threading.Thread(
                target=run_agent_stream,
                args=(user_text, "main", config_main, interim_reset),
                daemon=True
            )
            main_job_active = t
            t.start()

except Exception as e:
    safe_print(f"\n[FATAL ERROR] {e!r}")
finally:
    stop_event.set()
    if main_job_active is not None:
        main_job_active.join(timeout=5)

print("\n\nDemo completed!")



