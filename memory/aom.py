from typing import Dict, Any, List


# super simple in-memory "Agent Operating Memory" (demo)
AOM: Dict[str, Dict[str, Any]] = {}


def get_state(session_id: str) -> Dict[str, Any]:
    return AOM.setdefault(session_id, {"last_intent": None, "last_entities": {}, "handoff_notes": []})


def set_last(session_id: str, intent: str, entities: Dict[str, Any]) -> None:
    s = get_state(session_id)
    s["last_intent"] = intent
    s["last_entities"] = entities


def add_handoff_note(session_id: str, note: str) -> None:
    s = get_state(session_id)
    s["handoff_notes"].append(note)


def get_handoff_notes(session_id: str) -> List[str]:
    return get_state(session_id)["handoff_notes"]
