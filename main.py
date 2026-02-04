from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, Tuple
import re
import time
import uuid

app = FastAPI(title="Compass CX Orchestrator", version="1.0")

# -----------------------------
# CORS (add your Vercel URL too)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://compass-ui-blush.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

# -----------------------------
# Models
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
            "pending_action": None,  # transfer wizard state lives here
        }
    return _DEMO_STATE[session_id]

def now_ts() -> int:
    return int(time.time())

# -----------------------------
# NLP helpers
# -----------------------------
AMOUNT_RE = re.compile(r"(\$?\s*\d[\d,]*(?:\.\d{1,2})?)", re.IGNORECASE)

# Examples handled:
# "transfer $25 from savings to checking"
# "transfer 25 savings to checking"
# "from checking to savings"
# "savings to checking"
ACCT = r"(checking|savings)"
DIR_RE_1 = re.compile(rf"from\s+{ACCT}\s+to\s+{ACCT}", re.IGNORECASE)
DIR_RE_2 = re.compile(rf"{ACCT}\s+to\s+{ACCT}", re.IGNORECASE)

def parse_amount(text: str) -> Optional[float]:
    m = AMOUNT_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).replace("$", "").replace(",", "").strip()
    try:
        return float(raw)
    except:
        return None

def parse_direction(text: str) -> Tuple[Optional[str], Optional[str]]:
    t = (text or "").lower()

    m = DIR_RE_1.search(t)
    if m:
        parts = re.findall(ACCT, m.group(0), flags=re.IGNORECASE)
        if len(parts) == 2:
            return parts[0].lower(), parts[1].lower()

    m = DIR_RE_2.search(t)
    if m:
        parts = re.findall(ACCT, m.group(0), flags=re.IGNORECASE)
        if len(parts) == 2:
            return parts[0].lower(), parts[1].lower()

    return None, None

# -----------------------------
# Intent routing (FIXED)
# -----------------------------
def route_intent(text: str) -> str:
    t = (text or "").lower().strip()

    # ✅ Insights (banking)
    # chips: "insights"
    if t == "insights" or "show insights" in t or "my insights" in t:
        return "bank_insights"

    # ✅ CD maturity (assets)
    # chips: "cd maturity alert"
    if "cd" in t and ("maturity" in t or "mature" in t or "alert" in t):
        return "assets_cd_maturity"

    # ✅ Upcoming travel (travel)
    # chips: "upcoming travel"
    if "upcoming travel" in t or "upcoming trip" in t or ("travel" in t and "upcoming" in t) or "vacation" in t:
        return "travel_upcoming"

    # Existing:
    if "recurring" in t or "subscription" in t:
        return "bank_recurring_charges"
    if "spend" in t and ("analysis" in t or "insight" in t):
        return "bank_spend_analysis"
    if "account" in t and ("summary" in t or "balance" in t):
        return "bank_account_summary"
    if "transfer" in t or "send" in t or "move money" in t:
        return "bank_transfer"
    if "transfer money" in t:
        return "bank_transfer"

    return "unknown"

# -----------------------------
# Policy (PIP-lite)
# -----------------------------
def policy_check(intent: str, entities: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Demo PIP gate:
    - Missing amount should NOT block (we clarify).
    - Insufficient funds should block BEFORE confirmation.
    """
    if intent != "bank_transfer":
        return {"allow": True, "risk": "low", "reason": "Allowed"}

    amount = entities.get("amount")
    from_acct = entities.get("from_account")

    # If no amount yet, don’t block — we'll ask a question in the flow.
    if amount is None:
        return {"allow": True, "risk": "medium", "reason": "Needs amount"}

    try:
        amount = float(amount)
    except:
        return {"allow": False, "risk": "low", "reason": "Invalid transfer amount."}

    if amount <= 0:
        return {"allow": False, "risk": "low", "reason": "Transfer amount must be > 0."}

    # If we know the source account, enforce insufficient funds early
    if from_acct in ("checking", "savings"):
        bal = float(state["balances"].get(from_acct, 0))
        if amount > bal:
            return {
                "allow": False,
                "risk": "low",
                "reason": f"Insufficient funds in {from_acct.title()} (demo). Available: ${bal:.2f}",
            }

    # Demo step-up example
    if amount >= 5000:
        return {
            "allow": False,
            "risk": "high",
            "reason": "For safety, transfers above $5,000 require additional verification (demo).",
        }

    return {"allow": True, "risk": "medium", "reason": "Requires confirmation"}

# -----------------------------
# Card builders
# -----------------------------
def card_transfer_choose_direction() -> Dict[str, Any]:
    return {
        "title": "Transfer money between your accounts",
        "subtitle": "Choose a direction (demo)",
        "body": "Where do you want to move money?",
        "actions": [
            {
                "label": "From Checking → Savings",
                "action_name": "transfer_set_direction",
                "params": {"from_account": "checking", "to_account": "savings"},
            },
            {
                "label": "From Savings → Checking",
                "action_name": "transfer_set_direction",
                "params": {"from_account": "savings", "to_account": "checking"},
            },
        ],
    }

def card_transfer_ask_amount(from_acct: str, to_acct: str) -> Dict[str, Any]:
    return {
        "title": "Transfer amount",
        "subtitle": f"{from_acct.title()} → {to_acct.title()} (demo)",
        "body": "How much would you like to transfer?\nExample: “$25” or “transfer $25”.",
        "actions": [],
    }

def card_transfer_confirm(from_acct: str, to_acct: str, amt: float, action_id: str) -> Dict[str, Any]:
    return {
        "title": "Confirm transfer",
        "subtitle": f"{from_acct.title()} → {to_acct.title()} (demo-safe)",
        "body": (
            f"Please confirm:\n"
            f"- Amount: ${amt:.2f}\n"
            f"- From: {from_acct.title()} (demo)\n"
            f"- To: {to_acct.title()} (demo)\n\n"
            f"No real money will move in this demo."
        ),
        "actions": [
            {
                "label": "Confirm transfer",
                "action_name": "confirm_transfer",
                "params": {"action_id": action_id},
            },
            {
                "label": "Cancel",
                "action_name": "cancel_transfer",
                "params": {"action_id": action_id},
            },
        ],
    }

# -----------------------------
# /orchestrate
# -----------------------------
@app.post("/orchestrate")
def orchestrate(req: OrchestrateRequest):
    state = get_state(req.session_id)
    text = (req.text or "").strip()
    intent = route_intent(text)

    # ---- If a transfer wizard is mid-flight, allow user to just type the amount ----
    pending = state.get("pending_action")
    if pending and pending.get("type") == "transfer" and pending.get("stage") == "awaiting_amount":
        amt = parse_amount(text)
        if amt is None:
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": "How much would you like to transfer?"}],
                "card": card_transfer_ask_amount(pending["from_account"], pending["to_account"]),
                "debug": {"intent": "bank_transfer", "entities": {}, "policy": {"allow": True, "risk": "medium", "reason": "Needs amount"}, "ts": now_ts()},
            }

        entities = {
            "amount": float(amt),
            "from_account": pending["from_account"],
            "to_account": pending["to_account"],
        }
        policy = policy_check("bank_transfer", entities, state)
        if not policy["allow"]:
            state["pending_action"] = None
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": f"{policy['reason']}"}],
                "card": {"title": "Transfer blocked", "subtitle": "Policy check", "body": policy["reason"], "actions": []},
                "debug": {"intent": "bank_transfer", "entities": entities, "policy": policy, "ts": now_ts()},
            }

        action_id = str(uuid.uuid4())
        state["pending_action"] = {
            "id": action_id,
            "type": "transfer",
            "stage": "awaiting_confirm",
            "from_account": pending["from_account"],
            "to_account": pending["to_account"],
            "amount": float(amt),
        }
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "For your safety, please confirm this transfer (demo)."}],
            "card": card_transfer_confirm(pending["from_account"], pending["to_account"], float(amt), action_id),
            "debug": {"intent": "bank_transfer", "entities": entities, "policy": policy, "ts": now_ts()},
        }

    # -----------------------------
    # ✅ NEW: Insights
    # -----------------------------
    if intent == "bank_insights":
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Good news — I have new insights ready for you (demo)."}],
            "card": {
                "title": "Insights",
                "subtitle": "New insights — tap a card to view details",
                "body": (
                    "Duplicate Charges\n"
                    "You may have been charged more than once for the same item.\n\n"
                    "Spend Path\n"
                    "You’re trending higher this month (demo).\n\n"
                    "Subscriptions & Recurring Charges\n"
                    "3 charges may be due this week."
                ),
                "actions": [],
            },
            "debug": {"intent": intent, "entities": {}, "policy": {"allow": True, "risk": "low", "reason": "Allowed"}, "ts": now_ts()},
        }

    # -----------------------------
    # ✅ NEW: CD Maturity Alert
    # -----------------------------
    if intent == "assets_cd_maturity":
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here’s your CD maturity alert (demo)."}],
            "card": {
                "title": "CD Maturity Alert",
                "subtitle": "Next 30 days (demo)",
                "body": (
                    "12-month CD — $5,000 — matures in 12 days\n"
                    "6-month CD — $2,500 — matures in 21 days\n\n"
                    "Suggestion (demo): Roll into a new CD ladder or move to Savings if you need liquidity."
                ),
                "actions": [],
            },
            "debug": {"intent": intent, "entities": {}, "policy": {"allow": True, "risk": "low", "reason": "Allowed"}, "ts": now_ts()},
        }

    # -----------------------------
    # ✅ NEW: Upcoming Travel
    # -----------------------------
    if intent == "travel_upcoming":
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here’s your upcoming travel (demo)."}],
            "card": {
                "title": "Upcoming Travel",
                "subtitle": "Next trip (demo)",
                "body": (
                    "Orlando, FL — Feb 28–Mar 3\n"
                    "Flight: Confirmed\n"
                    "Hotel: Reserved\n\n"
                    "Travel points (demo): 42,500"
                ),
                "actions": [],
            },
            "debug": {"intent": intent, "entities": {}, "policy": {"allow": True, "risk": "low", "reason": "Allowed"}, "ts": now_ts()},
        }

    # ---- Existing intents ----
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
            "debug": {"intent": intent, "entities": {}, "policy": {"allow": True, "risk": "low", "reason": "Allowed"}, "ts": now_ts()},
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
            "debug": {"intent": intent, "entities": {}, "policy": {"allow": True, "risk": "low", "reason": "Allowed"}, "ts": now_ts()},
        }

    if intent == "bank_spend_analysis":
        charts = {
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
        }
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here’s a quick spend analysis (demo)."}],
            "card": {
                "title": "Spend Analysis",
                "subtitle": "This month vs last month (demo)",
                "body": "Top categories (demo):\n- Groceries: $420\n- Dining: $260\n- Gas: $110\n- Subscriptions: $35\n\nSuggestion (demo): Dining is trending higher — consider setting a weekly cap.",
                "actions": [],
            },
            "debug": {"intent": intent, "entities": {}, "policy": {"allow": True, "risk": "low", "reason": "Allowed"}, "charts": charts, "ts": now_ts()},
        }

    if intent == "bank_transfer":
        from_acct, to_acct = parse_direction(text)
        amt = parse_amount(text)

        # Case 1: user just says “transfer money” OR “transfer” without enough info → show direction options
        if (from_acct is None or to_acct is None) and amt is None:
            state["pending_action"] = {"type": "transfer", "stage": "awaiting_direction"}
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": "Sure — where do you want to transfer money from and to?"}],
                "card": card_transfer_choose_direction(),
                "debug": {"intent": intent, "entities": {}, "policy": {"allow": True, "risk": "medium", "reason": "Needs direction"}, "ts": now_ts()},
            }

        # Case 2: amount provided but direction missing → ask direction (still show two options)
        if (from_acct is None or to_acct is None) and amt is not None:
            state["pending_action"] = {"type": "transfer", "stage": "awaiting_direction", "amount_hint": float(amt)}
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": f"Got it — you want to transfer ${float(amt):.2f}. Which direction?"}],
                "card": card_transfer_choose_direction(),
                "debug": {"intent": intent, "entities": {"amount": float(amt)}, "policy": {"allow": True, "risk": "medium", "reason": "Needs direction"}, "ts": now_ts()},
            }

        # Case 3: direction provided but amount missing → ask amount
        if from_acct and to_acct and amt is None:
            state["pending_action"] = {"type": "transfer", "stage": "awaiting_amount", "from_account": from_acct, "to_account": to_acct}
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": f"How much would you like to transfer from {from_acct.title()} to {to_acct.title()}?"}],
                "card": card_transfer_ask_amount(from_acct, to_acct),
                "debug": {"intent": intent, "entities": {"from_account": from_acct, "to_account": to_acct}, "policy": {"allow": True, "risk": "medium", "reason": "Needs amount"}, "ts": now_ts()},
            }

        # Case 4: explicit amount + direction provided → go straight to confirm
        entities = {"amount": float(amt or 0), "from_account": from_acct, "to_account": to_acct}
        policy = policy_check(intent, entities, state)
        if not policy["allow"]:
            state["pending_action"] = None
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": policy["reason"]}],
                "card": {"title": "Transfer blocked", "subtitle": "Policy check", "body": policy["reason"], "actions": []},
                "debug": {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
            }

        action_id = str(uuid.uuid4())
        state["pending_action"] = {
            "id": action_id,
            "type": "transfer",
            "stage": "awaiting_confirm",
            "from_account": from_acct,
            "to_account": to_acct,
            "amount": float(amt),
        }
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "For your safety, please confirm this transfer (demo)."}],
            "card": card_transfer_confirm(from_acct, to_acct, float(amt), action_id),
            "debug": {"intent": intent, "entities": entities, "policy": policy, "ts": now_ts()},
        }

    # Fallback
    return {
        "session_id": req.session_id,
        "messages": [{"role": "assistant", "content": "I didn’t catch that. Try: insights, recurring charges, spend analysis, account summary, upcoming travel, cd maturity alert, or transfer money."}],
        "card": {
            "title": "Try something else",
            "subtitle": "Examples",
            "body": "• insights\n• recurring charges\n• spend analysis\n• account summary\n• upcoming travel\n• cd maturity alert\n• transfer money",
            "actions": [],
        },
        "debug": {"intent": intent, "entities": {}, "policy": {"allow": True, "risk": "low", "reason": "Allowed"}, "ts": now_ts()},
    }

# -----------------------------
# /action (button clicks)
# -----------------------------
@app.post("/action")
def action(req: ActionRequest):
    state = get_state(req.session_id)
    pending = state.get("pending_action")

    # Step 1: choose direction
    if req.action_name == "transfer_set_direction":
        from_acct = (req.params or {}).get("from_account")
        to_acct = (req.params or {}).get("to_account")

        if from_acct not in ("checking", "savings") or to_acct not in ("checking", "savings") or from_acct == to_acct:
            return {"ok": False, "messages": [{"role": "assistant", "content": "Invalid direction (demo)."}]}

        # carry amount hint if present
        amount_hint = None
        if pending and pending.get("type") == "transfer" and pending.get("amount_hint") is not None:
            try:
                amount_hint = float(pending.get("amount_hint"))
            except:
                amount_hint = None

        state["pending_action"] = {
            "type": "transfer",
            "stage": "awaiting_amount",
            "from_account": from_acct,
            "to_account": to_acct,
        }

        msg = f"Great — {from_acct.title()} → {to_acct.title()}. How much would you like to transfer?"
        if amount_hint is not None:
            msg = f"Great — {from_acct.title()} → {to_acct.title()}. You mentioned ${amount_hint:.2f}. Confirm the amount or type a new one."

        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": msg}],
            "card": card_transfer_ask_amount(from_acct, to_acct),
            "debug": {"action": req.action_name, "ts": now_ts()},
        }

    # Cancel transfer
    if req.action_name == "cancel_transfer":
        state["pending_action"] = None
        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": "Transfer cancelled (demo)."}],
            "card": {"title": "Cancelled", "subtitle": "No changes made", "body": "Nothing was transferred.", "actions": []},
            "debug": {"action": req.action_name, "ts": now_ts()},
        }

    # Confirm transfer
    if req.action_name == "confirm_transfer":
        if not pending or pending.get("type") != "transfer" or pending.get("stage") != "awaiting_confirm":
            return {"ok": False, "messages": [{"role": "assistant", "content": "No transfer to confirm."}]}

        amount = float(pending["amount"])
        from_acct = pending["from_account"]
        to_acct = pending["to_account"]

        b = state["balances"]
        if amount > float(b.get(from_acct, 0)):
            state["pending_action"] = None
            return {
                "ok": False,
                "messages": [{"role": "assistant", "content": f"Insufficient funds in {from_acct.title()} (demo)."}],
                "card": {"title": "Transfer blocked", "subtitle": "Insufficient funds", "body": "Not enough balance.", "actions": []},
            }

        b[from_acct] -= amount
        b[to_acct] += amount
        state["pending_action"] = None

        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": f"Transfer complete (demo). Moved ${amount:.2f} to {to_acct.title()}."}],
            "card": {
                "title": "Transfer complete",
                "subtitle": "Updated balances (demo)",
                "body": f"Checking: ${b['checking']:.2f}\nSavings: ${b['savings']:.2f}",
                "actions": [],
            },
            "balances": b,
            "debug": {"action": req.action_name, "ts": now_ts()},
        }

    return {"ok": False, "messages": [{"role": "assistant", "content": "Unknown action."}], "debug": {"action": req.action_name, "ts": now_ts()}}
