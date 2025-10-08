import os
import json
import time
from typing import Dict, Any

from langchain_core.tools import tool
from langchain_core.runnables.config import ensure_config
from langgraph.config import get_store, get_stream_writer

# Robust logic import that avoids cross-module leakage during hot reloads
try:
    from . import logic as telco_logic  # type: ignore
except Exception:
    import importlib.util as _ilu
    _dir = os.path.dirname(__file__)
    _logic_path = os.path.join(_dir, "logic.py")
    _spec = _ilu.spec_from_file_location("telco_agent_logic", _logic_path)
    telco_logic = _ilu.module_from_spec(_spec)  # type: ignore
    assert _spec and _spec.loader
    _spec.loader.exec_module(telco_logic)  # type: ignore

# Import helper functions (following the working example pattern)
try:
    from ..helper_functions import write_status
except Exception:
    # Fallback inline definition if import fails
    def write_status(tool_name: str, progress: int, status: str, store, namespace, config):
        if not isinstance(namespace, tuple):
            try:
                namespace = tuple(namespace)
            except (TypeError, ValueError):
                namespace = (str(namespace),)
        store.put(namespace, "working-tool-status-update", {
            "tool_name": tool_name,
            "progress": progress,
            "status": status,
        })


# --- Identity tools ---

@tool
def start_login_tool(session_id: str, msisdn: str) -> str:
    """Send a one-time code via SMS to the given mobile number. Returns masked destination and status (JSON)."""
    return json.dumps(telco_logic.start_login(session_id, msisdn))


@tool
def verify_login_tool(session_id: str, msisdn: str, otp: str) -> str:
    """Verify the one-time code sent to the user's phone. Returns {verified, session_id, msisdn}."""
    return json.dumps(telco_logic.verify_login(session_id, msisdn, otp))


# --- Customer/package tools ---

@tool
def get_current_package_tool(msisdn: str) -> str:
    """Get the customer's current package, contract status, and addons (JSON)."""
    return json.dumps(telco_logic.get_current_package(msisdn))


@tool
def get_data_balance_tool(msisdn: str) -> str:
    """Get the customer's current month data usage and remaining allowance (JSON)."""
    return json.dumps(telco_logic.get_data_balance(msisdn))


@tool
def list_available_packages_tool() -> str:
    """List all available mobile packages with fees and features (JSON array)."""
    return json.dumps(telco_logic.list_available_packages())


@tool
def recommend_packages_tool(msisdn: str, preferences_json: str | None = None) -> str:
    """Recommend up to 3 packages based on the customer's usage and optional preferences JSON."""
    prefs: Dict[str, Any] = {}
    try:
        if isinstance(preferences_json, str) and preferences_json.strip():
            prefs = json.loads(preferences_json)
    except Exception:
        prefs = {}
    return json.dumps(telco_logic.recommend_packages(msisdn, prefs))


@tool
def get_roaming_info_tool(msisdn: str, country_code: str) -> str:
    """Get roaming pricing and available passes for a country; indicates if included by current package (JSON)."""
    return json.dumps(telco_logic.get_roaming_info(msisdn, country_code))


@tool
def close_contract_tool(msisdn: str, confirm: bool = False) -> str:
    """Close the customer's contract. Use confirm=true only after explicit user confirmation. Returns summary (JSON)."""
    if not confirm:
        # Just return preview, no long operation
        return json.dumps(telco_logic.close_contract(msisdn, False))
    
    # Long-running operation with progress reporting (following working example pattern)
    writer = get_stream_writer()
    writer("Processing your contract closure request. This may take a moment...")
    
    tool_name = "close_contract_tool"
    steps = 10
    interval_seconds = 5  # 10 steps × 5 seconds = 50 seconds total
    
    config = ensure_config()
    namespace = config["configurable"]["namespace_for_memory"]
    server_store = get_store()
    
    for i in range(1, steps + 1):
        time.sleep(interval_seconds)
        pct = (i * 100) // steps
        status = "running"
        write_status(tool_name, pct, status, server_store, namespace, config)
    
    # Execute actual closure
    result = telco_logic.close_contract(msisdn, True)
    
    write_status(tool_name, 100, "completed", server_store, namespace, config)
    return json.dumps(result)


# --- Extended tools ---

@tool
def list_addons_tool(msisdn: str) -> str:
    """List customer's active addons (e.g., roaming passes)."""
    return json.dumps(telco_logic.list_addons(msisdn))


@tool
def purchase_roaming_pass_tool(msisdn: str, country_code: str, pass_id: str) -> str:
    """Purchase a roaming pass for a country by pass_id. Returns the added addon (JSON)."""
    result = telco_logic.purchase_roaming_pass(msisdn, country_code, pass_id)
    return json.dumps(result)


@tool
def change_package_tool(msisdn: str, package_id: str, effective: str = "next_cycle") -> str:
    """Change customer's package now or next_cycle. Returns status summary (JSON)."""
    result = telco_logic.change_package(msisdn, package_id, effective)
    return json.dumps(result)


@tool
def get_billing_summary_tool(msisdn: str) -> str:
    """Get billing summary including monthly fee and last bill amount (JSON)."""
    result = telco_logic.get_billing_summary(msisdn)
    return json.dumps(result)


@tool
def set_data_alerts_tool(msisdn: str, threshold_percent: int | None = None, threshold_gb: float | None = None) -> str:
    """Set data usage alerts by percent and/or GB. Returns updated alert settings (JSON)."""
    return json.dumps(telco_logic.set_data_alerts(msisdn, threshold_percent, threshold_gb))


# --- Helper tool for secondary thread ---

@tool
def check_status() -> dict:
    """Check the current status and progress of any long-running task."""
    config = ensure_config()
    namespace = config["configurable"]["namespace_for_memory"]
    
    if not isinstance(namespace, tuple):
        try:
            namespace = tuple(namespace)
        except (TypeError, ValueError):
            namespace = (str(namespace),)
    
    server_store = get_store()
    memory_update = server_store.get(namespace, "working-tool-status-update")
    
    if memory_update:
        item_value = memory_update.value
        status = item_value.get("status", "unknown")
        progress = item_value.get("progress", None)
        tool_name = item_value.get("tool_name", "unknown")
        return {
            "status": status,
            "progress": progress,
            "tool_name": tool_name
        }
    else:
        return {
            "status": "idle",
            "progress": None,
            "tool_name": None
        }

