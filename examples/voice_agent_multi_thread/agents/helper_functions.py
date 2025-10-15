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
    import logging
    logger = logging.getLogger(__name__)
    
    if not isinstance(namespace, tuple):
        try:
            namespace = tuple(namespace)
        except (TypeError, ValueError):
            namespace = (str(namespace),)
    
    try:
        logger.info(f"📝 write_status: Attempting to write to store: namespace={namespace}, key='working-tool-status-update'")
        store.put(
            namespace,
            "working-tool-status-update",
            {
                "tool_name": tool_name,
                "progress": progress,
                "status": status,
            }
        )
        logger.info(f"📝 write_status: Successfully called store.put() for {tool_name} at {progress}%")
    except Exception as e:
        logger.error(f"❌ write_status FAILED: {e}", exc_info=True)


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



