from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import re
import time
import uuid

app = FastAPI(title="Compass CX Orchestrator", version="1.0")

@app.get("/health")
def health():
    return {"ok": True}


# Allow UI (Next.js) to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        allow_origins=[
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "https://compass-ui-blush.vercel.app",
],

    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Request Models
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
# Demo state
# -----------------------------
_DEMO_STATE: Dict[str, Dict[str, Any]] = {}

def get_state(session_id: str) -> Dict[str, Any]:
    if session_id not in _DEMO_STATE:
        _DEMO_STATE[session_id] = {
            "balances": {"checking": 2450.12, "savings": 8900.00},
            "pending_action": None,
            "memory": {
                "last_domain": None,
                "last_intent": None,
                "last_entities": {},
            },
        }
    return _DEMO_STATE[session_id]

def now_ts() -> int:
    return int(time.time())

# -----------------------------
# NLP: amount + direction
# -----------------------------
AMOUNT_RE = re.compile(r"(\$?\s*\d[\d,]*(?:\.\d{1,2})?)", re.IGNORECASE)

def parse_amount(text: str) -> Optional[float]:
    m = AMOUNT_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).replace("$", "").replace(",", "").strip()
    try:
        return float(raw)
    except:
        return None

def parse_transfer_direction(text: str) -> Dict[str, str]:
    """
    Default: checking -> savings
    If user says "from savings to checking", respect it.
    """
    t = (text or "").lower()

    # Strong patterns: "from X to Y"
    if "from savings" in t and "to checking" in t:
        return {"from": "savings", "to": "checking"}
    if "from checking" in t and "to savings" in t:
        return {"from": "checking", "to": "savings"}

    # weaker cues
    if "to checking" in t:
        return {"from": "savings", "to": "checking"}
    if "to savings" in t:
        return {"from": "checking", "to": "savings"}

    return {"from": "checking", "to": "savings"}

# -----------------------------
# Routing (domains/intents)
# -----------------------------
def route_intent(text: str) -> str:
    t = (text or "").lower().strip()

    # Insights / home
    if t in ("insights", "show insights", "my insights"):
        return "home_insights"

    # Banking
    if "spend" in t or "spending" in t or "analysis" in t:
        return "bank_spend_analysis"
    if "recurring" in t or "subscription" in t:
        return "bank_recurring_charges"
    if "account" in t and ("summary" in t or "balance" in t or "balances" in t):
        return "bank_account_summary"
    if "transfer" in t or "send" in t or "zelle" in t or "move money" in t or "transfer money" in t:
        return "bank_transfer"

    # Travel
    if "travel" in t or "upcoming trip" in t or "upcoming travel" in t or "points" in t:
        return "travel_upcoming"

    # Assets
    if "cd" in t or "maturity" in t or "certificate of deposit" in t:
        return "assets_cd_maturity"

    # Agent handoff
    if "agent" in t or "representative" in t or "specialist" in t or "talk to a" in t:
        return "handoff_agent"

    return "unknown"

# -----------------------------
# PIP (Policy / Identity / Permissions)
# -----------------------------
def pip_decision(intent: str, entities: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    - Missing amount for transfers => allow (clarify), NOT blocked
    - Insufficient funds check happens BEFORE confirmation card
    """
    if intent in ("unknown", "", None):
        return {"allow": True, "risk": "low", "reason": "No match"}  # let orchestrator respond with helpful fallback

    if intent == "bank_transfer":
        amt = entities.get("amount")
        # Missing amount => clarification path (allowed)
        if amt is None:
            return {"allow": True, "risk": "low", "reason": "Needs amount clarification"}

        amt = float(amt)
        if amt <= 0:
            return {"allow": False, "risk": "low", "reason": "Transfer amount must be greater than $0."}

        # direction-aware funds check
        frm = entities.get("from_account", "checking")
        balances = state["balances"]
        if balances.get(frm, 0) < amt:
            return {
                "allow": False,
                "risk": "low",
                "reason": f"Insufficient funds in {frm.title()} (demo). Available: ${balances.get(frm,0):.2f}"
            }

        # Optional demo cap rule
        if amt >= 5000:
            return {"allow": False, "risk": "high", "reason": "Transfers above $5,000 require additional verification (demo)."}

        return {"allow": True, "risk": "medium", "reason": "Requires confirmation"}

    return {"allow": True, "risk": "low", "reason": "Allowed"}

# -----------------------------
# Card helpers
# -----------------------------
def make_card(title: str, subtitle: str = "", body: str = "", actions=None):
    return {
        "title": title,
        "subtitle": subtitle,
        "body": body,
        "actions": actions or [],
    }

def response(session_id: str, messages, card, debug):
    return {
        "session_id": session_id,
        "messages": messages,
        "card": card,
        "debug": debug,
    }

# -----------------------------
# API: Orchestrate
# -----------------------------
@app.post("/orchestrate")
def orchestrate(req: OrchestrateRequest):
    state = get_state(req.session_id)
    text = (req.text or "").strip()

    intent = route_intent(text)
    entities: Dict[str, Any] = {}

    # Extract entities where relevant
    if intent == "bank_transfer":
        amt = parse_amount(text)
        if amt is not None:
            entities["amount"] = amt
        direction = parse_transfer_direction(text)
        entities["from_account"] = direction["from"]
        entities["to_account"] = direction["to"]

    # Remember last routing (agentic “memory-lite”)
    state["memory"]["last_intent"] = intent
    state["memory"]["last_entities"] = entities

    policy = pip_decision(intent, entities, state)

    # If blocked: show blocked card
    if not policy["allow"]:
        return response(
            req.session_id,
            [{"role": "assistant", "content": f"{policy['reason']}"}],
            make_card("Action blocked", "Policy / safety check", policy["reason"], []),
            {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        )

    # ---- Handlers ----

    if intent == "home_insights":
        body = (
            "New insights — tap a card to view details.\n\n"
            "• Duplicate Charges — You may have been charged more than once for the same item.\n"
            "• Spend Path — See your current monthly spending (demo).\n"
            "• Subscriptions & Recurring Charges — 3 charges may be due this week.\n"
            "• Quick Transfer — Send money with confirmation (demo-safe)."
        )
        return response(
            req.session_id,
            [{"role": "assistant", "content": "Loaded your insights (demo)."}],
            make_card("Insights", "Highlights (demo)", body, []),
            {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        )

    if intent == "bank_spend_analysis":
        # Keep it simple + demo-friendly; your UI can render charts from debug later
        body = (
            "Top categories (demo):\n"
            "- Groceries: $420\n"
            "- Dining: $260\n"
            "- Gas: $110\n"
            "- Subscriptions: $35\n\n"
            "Suggestion (demo): Dining is trending higher — consider setting a weekly cap."
        )
        debug = {
            "intent": intent,
            "entities": entities,
            "policy": policy,
            "ts": now_ts(),
            # Chart payload (optional: your UI can read this and render charts)
            "charts": {
                "pie": [
                    {"name": "Groceries", "value": 420},
                    {"name": "Dining", "value": 260},
                    {"name": "Gas", "value": 110},
                    {"name": "Subscriptions", "value": 35},
                ],
                "trend": [
                    {"day": "W1", "value": 820},
                    {"day": "W2", "value": 910},
                    {"day": "W3", "value": 980},
                    {"day": "W4", "value": 1045},
                ],
            },
        }
        return response(
            req.session_id,
            [{"role": "assistant", "content": "Here’s a quick spend analysis (demo)."}],
            make_card("Spend Analysis", "This month vs last month (demo)", body, []),
            debug,
        )

    if intent == "bank_recurring_charges":
        return response(
            req.session_id,
            [{"role": "assistant", "content": "Here are your upcoming subscriptions (demo)."}],
            make_card(
                "Subscriptions & Recurring Charges",
                "Upcoming charges (demo)",
                "Spotify — $11.99 • due in 3 days\n"
                "Netflix — $15.49 • due in 5 days\n"
                "iCloud — $2.99 • due in 6 days\n\n"
                "Demo subscriptions only.",
                [],
            ),
            {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        )

    if intent == "bank_account_summary":
        b = state["balances"]
        return response(
            req.session_id,
            [{"role": "assistant", "content": "Here’s your balances overview (demo)."}],
            make_card(
                "Account Summary",
                "Balances overview (demo)",
                f"Checking: ${b['checking']:.2f}\nSavings:  ${b['savings']:.2f}",
                [],
            ),
            {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        )

    if intent == "bank_transfer":
        amt = entities.get("amount")

        # Clarify amount (NOT blocked)
        if amt is None:
            return response(
                req.session_id,
                [{"role": "assistant", "content": "How much would you like to transfer?"}],
                make_card("Transfer Money", "Amount needed", "Example: “transfer $25 from savings to checking”", []),
                {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
            )

        frm = entities.get("from_account", "checking")
        to = entities.get("to_account", "savings")

        # Create pending transfer for confirmation
        action_id = str(uuid.uuid4())
        state["pending_action"] = {"id": action_id, "type": "transfer", "amount": float(amt), "from": frm, "to": to}

        return response(
            req.session_id,
            [{"role": "assistant", "content": "For your safety, please confirm this transfer (demo)."}],
            make_card(
                "Transfer Funds",
                "Confirmation (demo-safe)",
                f"Please confirm:\n"
                f"- Amount: ${float(amt):.2f}\n"
                f"- From: {frm.title()} (demo)\n"
                f"- To:   {to.title()} (demo)\n\n"
                f"No real money will move in this demo.",
                actions=[
                    {"label": "Confirm transfer", "action_name": "confirm_transfer", "params": {"action_id": action_id}},
                    {"label": "Cancel", "action_name": "cancel_transfer", "params": {"action_id": action_id}},
                ],
            ),
            {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        )

    if intent == "travel_upcoming":
        body = (
            "Upcoming trip (demo):\n"
            "• Orlando — Feb 18–22\n"
            "• Hotel + flight: booked\n\n"
            "Travel points (demo): 42,500"
        )
        return response(
            req.session_id,
            [{"role": "assistant", "content": "Here’s your upcoming travel (demo)."}],
            make_card("Travel", "Upcoming travel + points (demo)", body, []),
            {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        )

    if intent == "assets_cd_maturity":
        body = (
            "CD Maturity Alert (demo):\n"
            "• 12-month CD — matures in 14 days\n"
            "• Current rate: 4.35% (demo)\n\n"
            "Suggestion (demo): Review renew vs move funds to savings/investments."
        )
        return response(
            req.session_id,
            [{"role": "assistant", "content": "Here’s your CD maturity alert (demo)."}],
            make_card("CD Maturity Alert", "Assets overview (demo)", body, []),
            {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        )

    if intent == "handoff_agent":
        # Agentic: create a demo “handoff packet”
        handoff = (
            "Handoff packet (demo):\n"
            f"- User: {req.user_id}\n"
            f"- Last intent: {state['memory']['last_intent']}\n"
            f"- Last request: {req.text}\n"
            f"- Balances snapshot: Checking ${state['balances']['checking']:.2f}, Savings ${state['balances']['savings']:.2f}\n"
            "\nAgent note (demo): Keep user in same context; do not ask them to repeat details."
        )
        return response(
            req.session_id,
            [{"role": "assistant", "content": "Connecting you to a specialist (demo). I’ll share context so you don’t repeat yourself."}],
            make_card("Agent Handoff", "Connecting (demo)", handoff, []),
            {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        )

    # Fallback
    return response(
        req.session_id,
        [{"role": "assistant", "content": "I didn’t catch that. Try: insights, spend analysis, recurring charges, account summary, transfer $25, or talk to an agent."}],
        make_card(
            "Try something else",
            "Examples",
            "• insights\n• spend analysis\n• recurring charges\n• account summary\n• transfer $25 from savings to checking\n• talk to an agent",
            [],
        ),
        {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
    )

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
            "card": make_card("Cancelled", "No changes made", "Nothing was transferred.", []),
            "debug": {"action": req.action_name, "ts": now_ts()},
        }

    if req.action_name == "confirm_transfer":
        if not pending or pending.get("type") != "transfer":
            return {"ok": False, "messages": [{"role": "assistant", "content": "No transfer to confirm."}]}

        amount = float(pending["amount"])
        frm = pending.get("from", "checking")
        to = pending.get("to", "savings")

        # Guardrails (prevents negative balances)
        if amount <= 0:
            return {"ok": False, "messages": [{"role": "assistant", "content": "Transfer amount must be greater than $0."}]}

        b = state["balances"]
        if b.get(frm, 0) < amount:
            state["pending_action"] = None
            return {
                "ok": False,
                "messages": [{"role": "assistant", "content": f"Insufficient funds in {frm.title()} (demo)."}],
                "card": make_card("Action blocked", "Insufficient funds", f"{frm.title()} available: ${b.get(frm,0):.2f}", []),
                "debug": {"action": req.action_name, "ts": now_ts()},
            }

        # Execute (demo)
        b[frm] -= amount
        b[to] += amount
        state["pending_action"] = None

        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": f"Transfer complete (demo). Moved ${amount:.2f} from {frm.title()} to {to.title()}."}],
            "card": make_card(
                "Transfer Complete",
                "Updated balances (demo)",
                f"Checking: ${b['checking']:.2f}\nSavings:  ${b['savings']:.2f}",
                [],
            ),
            "balances": b,
            "debug": {"action": req.action_name, "from": frm, "to": to, "amount": amount, "ts": now_ts()},
        }

    return {
        "ok": False,
        "messages": [{"role": "assistant", "content": "Unknown action."}],
        "debug": {"action": req.action_name, "ts": now_ts()},
    }
