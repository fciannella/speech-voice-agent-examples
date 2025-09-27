import os
import sys
import json
from typing import Any, Dict, Optional

from langchain_core.tools import tool

# Robust logic import isolated to this agent
try:
    from . import logic as hc_logic  # type: ignore
except Exception:
    import importlib.util as _ilu
    _dir = os.path.dirname(__file__)
    _logic_path = os.path.join(_dir, "logic.py")
    _spec = _ilu.spec_from_file_location("healthcare_agent_logic", _logic_path)
    hc_logic = _ilu.module_from_spec(_spec)  # type: ignore
    assert _spec and _spec.loader
    _spec.loader.exec_module(hc_logic)  # type: ignore

find_patient_by_name = hc_logic.find_patient_by_name
find_patient_by_full_name = hc_logic.find_patient_by_full_name
get_patient_profile = hc_logic.get_patient_profile
authenticate_patient = hc_logic.authenticate_patient
get_preferred_pharmacy = hc_logic.get_preferred_pharmacy
list_providers = hc_logic.list_providers
get_provider_slots = hc_logic.get_provider_slots
schedule_appointment = hc_logic.schedule_appointment
triage_symptoms = hc_logic.triage_symptoms
log_call = hc_logic.log_call


@tool
def find_patient(first_name: str | None = None, last_name: str | None = None, full_name: str | None = None) -> str:
    """Find a patient_id by name. Prefer full_name; otherwise use first+last. Returns JSON with patient_id or {}."""
    if isinstance(full_name, str) and full_name.strip():
        return json.dumps(find_patient_by_full_name(full_name))
    return json.dumps(find_patient_by_name(first_name or "", last_name or ""))


@tool
def get_patient_profile_tool(patient_id: str) -> str:
    """Fetch patient profile, allergies, meds, visits, and vitals. Returns JSON string."""
    return json.dumps(get_patient_profile(patient_id))


@tool
def verify_identity(session_id: str, patient_id: str | None = None, full_name: str | None = None, dob_yyyy_mm_dd: str | None = None, mrn_last4: str | None = None, secret_answer: str | None = None) -> str:
    """Verify identity before accessing records. Provide any of: full_name, dob (YYYY-MM-DD or free-form), MRN last-4, secret answer. Returns JSON with verified flag, needed fields, and optional secret question."""
    res = authenticate_patient(session_id, patient_id, full_name, dob_yyyy_mm_dd, mrn_last4, secret_answer)
    return json.dumps(res)


@tool
def get_preferred_pharmacy_tool(patient_id: str) -> str:
    """Get the patient's preferred pharmacy details. Returns JSON."""
    return json.dumps(get_preferred_pharmacy(patient_id))


@tool
def list_providers_tool(specialty: str | None = None) -> str:
    """List available providers. Optional filter by specialty. Returns JSON array."""
    return json.dumps(list_providers(specialty))


@tool
def get_provider_slots_tool(provider_id: str, count: int = 3) -> str:
    """Get upcoming appointment slots for a provider. Returns JSON array of ISO datetimes."""
    return json.dumps(get_provider_slots(provider_id, count))


@tool
def schedule_appointment_tool(provider_id: str, slot_iso: str, patient_id: str | None = None) -> str:
    """Schedule an appointment slot with a provider for a patient. Returns JSON with appointment_id."""
    return json.dumps(schedule_appointment(provider_id, slot_iso, patient_id))


@tool
def triage_symptoms_tool(patient_id: str | None, symptoms_text: str) -> str:
    """Run symptoms through triage rules. Returns {risk, advice, red_flags, rule}."""
    return json.dumps(triage_symptoms(patient_id, symptoms_text))


@tool
def log_call_tool(session_id: str, patient_id: str | None = None, notes: str | None = None, triage_json: str | None = None) -> str:
    """Log the call details and triage outcome. triage_json is a JSON dict string. Returns {logged, log_id}."""
    triage: Dict[str, Any] | None
    try:
        triage = json.loads(triage_json or "null") if triage_json else None
    except Exception:
        triage = None
    return json.dumps(log_call(session_id, patient_id, notes, triage))


