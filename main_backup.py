from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import re
import time
import uuid

app = FastAPI(title="Compass CX Orchestrator", version="1.0")

# Allow UI (Next.js) to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Request/Response Models
# -----------------------------
class OrchestrateRequest(BaseModel):
    session_id: str
    user_id: str
    channel: str
    text: str
    context: Optional[Dict[str, Any]] = {}

class ActionRequest(BaseModel):
    session_id: str
    user_id: str
    action_name: str
    params: Dict[str, Any] = {}

# -----------------------------
# Demo state (balances, etc.)
# -----------------------------
_DEMO_STATE: Dict[str, Dict[str, Any]] = {}

def get_state(session_id: str) -> Dict[str, Any]:
    if session_id not in _DEMO_STATE:
        _DEMO_STATE[session_id] = {
            "balances": {"checking": 2450.12, "savings": 8900.00},
            "last_intent": None,
            "pending_action": None,
        }
    return _DEMO_STATE[session_id]

def now_ts() -> int:
    return int(time.time())

# -----------------------------
# Simple NLP / intent routing
# -----------------------------
AMOUNT_RE = re.compile(r"(\$?\s*\d[\d,]*(?:\.\d{1,2})?)", re.IGNORECASE)

def parse_amount(text: str) -> Optional[float]:
    m = AMOUNT_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace("$", "").replace(",", "").strip()
    try:
        return float(raw)
    except:
        return None

def route_intent(text: str) -> str:
    t = text.lower().strip()
    if "recurring" in t or "subscription" in t:
        return "bank_recurring_charges"
    if "account" in t and ("summary" in t or "balance" in t):
        return "bank_account_summary"
    if "transfer" in t or "send" in t or "zelle" in t:
        return "bank_transfer"
    return "unknown"

# -----------------------------
# Policy gate (demo)
# -----------------------------
def policy_check(intent: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    # Demo rules:
    # - transfers must be > 0
    if intent == "bank_transfer":
        amount = entities.get("amount")
        if amount is None:
            return {"allow": True, "risk": "medium", "reason": "Needs confirmation"}
        if amount <= 0:
            return {"allow": False, "risk": "low", "reason": "Transfer amount must be > 0"}
        return {"allow": True, "risk": "medium", "reason": "Requires confirmation"}
    return {"allow": True, "risk": "low", "reason": "Allowed"}

# -----------------------------
# API: Orchestrate
# -----------------------------
@app.post("/orchestrate")
def orchestrate(req: OrchestrateRequest):
    state = get_state(req.session_id)

    intent = route_intent(req.text)
    entities: Dict[str, Any] = {}

    if intent == "bank_transfer":
        amt = parse_amount(req.text)
        if amt is not None:
            entities["amount"] = amt

    policy = policy_check(intent, entities)

    # Blocked card
    if not policy["allow"]:
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": f"Blocked: {policy['reason']}"}],
            "card": {
                "title": "Action blocked",
                "subtitle": "Policy / safety check",
                "body": policy["reason"],
                "actions": [],
            },
            "debug": {"intent": intent, "entities": entities, "policy": policy},
        }

    # Intent handlers
    if intent == "bank_recurring_charges":
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here are your upcoming subscriptions (demo)."}],
            "card": {
                "title": "Subscriptions & Recurring Charges",
                "subtitle": "Upcoming charges (demo)",
                "body": "Spotify — $11.99 • due in 3 days\nNetflix — $15.49 • due in 5 days\niCloud — $2.99 • due in 6 days\n\nDemo subscriptions only.",
                "actions": [],
            },
            "debug": {"intent": intent, "entities": entities, "policy": policy},
        }

    if intent == "bank_account_summary":
        b = state["balances"]
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here’s your balances overview (demo)."}],
            "card": {
                "title": "Account Summary",
                "subtitle": "Balances overview (demo)",
                "body": f"Checking: ${b['checking']:.2f}\nSavings: ${b['savings']:.2f}",
                "actions": [],
            },
            "debug": {"intent": intent, "entities": entities, "policy": policy},
        }

    if intent == "bank_transfer":
        amt = entities.get("amount")
        if amt is None:
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": "How much would you like to transfer?"}],
                "card": {
                    "title": "Transfer Money",
                    "subtitle": "Amount needed",
                    "body": "Example: “transfer $25”",
                    "actions": [],
                },
                "debug": {"intent": intent, "entities": entities, "policy": policy},
            }

        # Create a pending transfer for confirmation
        action_id = str(uuid.uuid4())
        state["pending_action"] = {"id": action_id, "type": "transfer", "amount": float(amt)}

        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "For your safety, please confirm this transfer (demo)."}],
            "card": {
                "title": "Transfer Funds",
                "subtitle": "Confirmation (demo-safe)",
                "body": f"Please confirm:\n- Amount: ${amt:.2f}\n- From: Checking (demo)\n- To: Savings (demo)\n\nNo real money will move in this demo.",
                "actions": [
                    {"label": "Confirm transfer", "action_name": "confirm_transfer", "params": {"action_id": action_id}},
                    {"label": "Cancel", "action_name": "cancel_transfer", "params": {"action_id": action_id}},
                ],
            },
            "debug": {"intent": intent, "entities": entities, "policy": policy},
        }

    # Fallback
    return {
        "session_id": req.session_id,
        "messages": [{"role": "assistant", "content": "I didn’t catch that. Try: recurring charges, account summary, or transfer $25."}],
        "card": {
            "title": "Try something else",
            "subtitle": "Examples",
            "body": "• recurring charges\n• account summary\n• transfer $25",
            "actions": [],
        },
        "debug": {"intent": intent, "entities": entities, "policy": policy},
    }

# -----------------------------
# API: Action (button clicks)
# -----------------------------
@app.post("/action")
def action(req: ActionRequest):
    state = get_state(req.session_id)
    pending = state.get("pending_action")

    if req.action_name == "cancel_transfer":
        state["pending_action"] = None
        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": "Transfer cancelled (demo)."}],
            "card": {"title": "Cancelled", "subtitle": "No changes made", "body": "Nothing was transferred.", "actions": []},
            "debug": {"action": req.action_name},
        }

    if req.action_name == "confirm_transfer":
        if not pending or pending.get("type") != "transfer":
            return {"ok": False, "messages": [{"role": "assistant", "content": "No transfer to confirm."}]}

        amount = float(pending["amount"])
        if amount <= 0:
            return {"ok": False, "messages": [{"role": "assistant", "content": "Transfer amount must be greater than $0."}]}

        b = state["balances"]
        b["checking"] -= amount
        b["savings"] += amount
        state["pending_action"] = None

        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": f"Transfer complete (demo). Moved ${amount:.2f} to Savings."}],
            "card": {
                "title": "Transfer Complete",
                "subtitle": "Updated balances (demo)",
                "body": f"Checking: ${b['checking']:.2f}\nSavings: ${b['savings']:.2f}",
                "actions": [],
            },
            "balances": b,
            "debug": {"action": req.action_name},
        }

    return {"ok": False, "messages": [{"role": "assistant", "content": "Unknown action."}], "debug": {"action": req.action_name}}
