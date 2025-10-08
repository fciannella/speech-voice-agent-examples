"""Helper functions for multi-threaded agent coordination and progress tracking."""

from typing import Any, Dict
from langgraph.store.base import BaseStore


def write_status(
    tool_name: str,
    progress: int,
    status: str,
    store: BaseStore,
    namespace: tuple | list,
    config: Dict[str, Any] | None = None
) -> None:
    """Write tool execution status and progress to the store.
    
    Args:
        tool_name: Name of the tool being executed
        progress: Progress percentage (0-100)
        status: Status string ("running", "completed", "failed")
        store: LangGraph store instance
        namespace: Namespace tuple for store isolation
        config: Optional runtime config
    """
    if not isinstance(namespace, tuple):
        try:
            namespace = tuple(namespace)
        except (TypeError, ValueError):
            namespace = (str(namespace),)
    
    store.put(
        namespace,
        "working-tool-status-update",
        {
            "tool_name": tool_name,
            "progress": progress,
            "status": status,
        }
    )


def reset_status(store: BaseStore, namespace: tuple | list) -> None:
    """Reset/clear tool execution status from the store.
    
    Args:
        store: LangGraph store instance
        namespace: Namespace tuple for store isolation
    """
    if not isinstance(namespace, tuple):
        try:
            namespace = tuple(namespace)
        except (TypeError, ValueError):
            namespace = (str(namespace),)
    
    try:
        store.delete(namespace, "working-tool-status-update")
    except Exception:
        # If key doesn't exist, that's fine
        pass



