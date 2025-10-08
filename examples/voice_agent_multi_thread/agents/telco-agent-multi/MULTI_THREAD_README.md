# Multi-Threaded Telco Agent

## Overview

This telco agent now supports **non-blocking multi-threaded execution**, allowing users to continue conversing while long-running operations (like package changes, contract closures, or billing queries) are in progress.

## Key Features

### 1. **Dual Thread Architecture**

- **Main Thread**: Handles primary requests and long-running operations
- **Secondary Thread**: Handles interim conversations while main thread is busy

### 2. **Long-Running Tools**

The following tools are marked as long-running and will trigger multi-threaded behavior:

- `close_contract_tool` (10 seconds)
- `purchase_roaming_pass_tool` (8 seconds)
- `change_package_tool` (10 seconds)
- `get_billing_summary_tool` (6 seconds)

### 3. **Quick Tools** (for secondary thread)

These tools are available during long operations:

- `check_status` - Query progress of ongoing operation
- `get_current_package_tool` - Quick lookups
- `get_data_balance_tool` - Quick queries
- `list_available_packages_tool` - Browse packages
- `get_roaming_info_tool` - Roaming information
- `list_addons_tool` - List addons

### 4. **Progress Tracking**

Long-running tools report progress that can be queried via `check_status` tool during execution.

### 5. **Conversation Synthesis**

When a long operation completes, the agent synthesizes the result with any interim conversation that occurred, providing a natural, coherent response.

## Usage

### Input Format

The agent now expects an `input_dict` instead of a simple message list:

```python
input_dict = {
    "messages": [HumanMessage(content="Close my contract")],
    "thread_type": "main",  # or "secondary"
    "interim_messages_reset": True  # Reset interim conversation tracking
}
```

### Configuration

The agent requires a `namespace_for_memory` in the config for coordination:

```python
config = {
    "configurable": {
        "thread_id": "main-thread-123",
        "namespace_for_memory": ("user_id", "tools_updates")
    }
}
```

### Example Client Usage

```python
import uuid
import threading
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.store.memory import InMemoryStore

# Initialize
store = InMemoryStore()
thread_id_main = str(uuid.uuid4())
thread_id_secondary = str(uuid.uuid4())
namespace = ("user_123", "telco_ops")

config_main = {
    "configurable": {
        "thread_id": thread_id_main,
        "namespace_for_memory": namespace
    }
}

config_secondary = {
    "configurable": {
        "thread_id": thread_id_secondary,
        "namespace_for_memory": namespace
    }
}

# Main thread (long operation - non-blocking)
def run_main_operation():
    result = agent.invoke(
        {
            "messages": [HumanMessage(content="Change my package to Premium")],
            "thread_type": "main",
            "interim_messages_reset": True
        },
        config=config_main,
        store=store
    )
    print(f"Main: {result[-1].content}")

# Start long operation in background
main_thread = threading.Thread(target=run_main_operation)
main_thread.start()

# While main is running, handle secondary queries
time.sleep(2)  # Let main operation start

result = agent.invoke(
    {
        "messages": [HumanMessage(content="What's the status?")],
        "thread_type": "secondary",
        "interim_messages_reset": False
    },
    config=config_secondary,
    store=store
)
print(f"Secondary: {result[-1].content}")

# Wait for main to complete
main_thread.join()
```

## Coordination Mechanism

The agent uses the LangGraph store for thread coordination:

### Store Keys

- `working-tool-status-update`: Current tool progress and status
- `secondary_status`: Lock indicating secondary thread processing state
- `secondary_abort`: Abort signal for terminating secondary thread
- `secondary_interim_messages`: Interim conversation to be synthesized

### State Management

The agent maintains two message lists:

1. `messages`: Full conversation history
2. `interim_messages`: Messages exchanged during long operations (for synthesis)

## Architecture

```
User Request
     │
     ├─ Long Operation? ───► Main Thread
     │                        │
     │                        ├─ Execute Tool (with progress reporting)
     │                        │
     │                        └─ Wait for Secondary + Synthesize
     │
     └─ Quick Query? ──────► Secondary Thread
                              │
                              ├─ Handle query (limited tools)
                              │
                              └─ Store interim messages
```

## Safety Features

1. **Processing Locks**: Prevent race conditions during state updates
2. **Abort Signals**: Gracefully terminate secondary thread if main completes
3. **Timeouts**: Main thread waits max 15 seconds for secondary to finish
4. **Message Sanitization**: Removes orphan tool messages to prevent API errors

## Testing

To test the multi-threaded behavior, you can simulate long operations:

```python
# Test 1: Long operation without interruption
response = agent.invoke({
    "messages": [HumanMessage(content="Close my contract")],
    "thread_type": "main",
    "interim_messages_reset": True
}, config=config_main, store=store)

# Test 2: Long operation with status check
# (Start main in background, then query status)

# Test 3: Multiple secondary queries during long operation
```

## Environment Variables

- `REACT_MODEL`: Model for main thread (default: gpt-4o)
- `RBC_FEES_MAX_MSGS`: Max messages to keep in context (default: 40)
- `TELCO_DEBUG`: Enable debug logging (default: 0)

## Migration Notes

If you have existing code using the old agent format:

**Before:**
```python
result = agent.invoke(
    [HumanMessage(content="Hello")],
    config=config
)
```

**After:**
```python
result = agent.invoke(
    {
        "messages": [HumanMessage(content="Hello")],
        "thread_type": "main",
        "interim_messages_reset": True
    },
    config=config,
    store=store
)
```

The state format has also changed from `List[BaseMessage]` to `Dict[str, List[BaseMessage]]` with keys `messages` and `interim_messages`.



