from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, Tuple
import re
import time
import uuid

app = FastAPI(title="Compass CX Orchestrator", version="1.0")

# -----------------------------
# CORS
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
# Intent routing
# -----------------------------
def route_intent(text: str) -> str:
    t = (text or "").lower().strip()

    # Insights
    if t == "insights" or "show insights" in t or "my insights" in t:
        return "bank_insights"

    # ✅ Manage CD (chip rename support) + existing CD maturity
    if t == "manage cd" or "manage cd" in t:
        return "assets_cd_maturity"
    if "cd" in t and ("maturity" in t or "mature" in t or "alert" in t):
        return "assets_cd_maturity"

    # ✅ Travel (chip rename support) + existing upcoming travel logic
    if t == "travel" or "travel" in t:
        return "travel_upcoming"
    if "upcoming travel" in t or "upcoming trip" in t or ("travel" in t and "upcoming" in t) or "vacation" in t:
        return "travel_upcoming"

    # Agent handoff
    if "agent" in t or "representative" in t or "human" in t or "talk to" in t:
        return "agent_handoff"

    # Existing
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

    # Missing amount -> clarify later
    if amount is None:
        return {"allow": True, "risk": "medium", "reason": "Needs amount"}

    try:
        amount = float(amount)
    except:
        return {"allow": False, "risk": "low", "reason": "Invalid transfer amount."}

    if amount <= 0:
        return {"allow": False, "risk": "low", "reason": "Transfer amount must be > 0."}

    # Enforce insufficient funds early (only if source known)
    if from_acct in ("checking", "savings"):
        bal = float(state["balances"].get(from_acct, 0))
        if amount > bal:
            return {
                "allow": False,
                "risk": "low",
                "reason": f"Insufficient funds in {from_acct.title()}. Available: ${bal:.2f}",
            }

    if amount >= 5000:
        return {
            "allow": False,
            "risk": "high",
            "reason": "For safety, transfers above $5,000 require additional verification.",
        }

    return {"allow": True, "risk": "medium", "reason": "Requires confirmation"}

# -----------------------------
# Trace helper (Planner → Delegate → Act)
# -----------------------------
def make_trace(
    decision: str,
    reason: str,
    agent: str,
    capability: str,
    result: str,
    confidence: str = "high",
) -> Dict[str, Any]:
    return {
        "planner": {"decision": decision, "reason": reason},
        "delegate": {"agent": agent, "capability": capability},
        "act": {"result": result, "confidence": confidence},
    }

# -----------------------------
# Insights data (what the UI will show in the Insights drawer)
# -----------------------------
INSIGHTS = [
    {
        "id": "spend_path",
        "title": "Spend Path",
        "subtitle": "You’re trending higher this month.",
    },
    {
        "id": "upcoming_cd_maturity",
        "title": "Upcoming CD maturity",
        "subtitle": "Two CDs are maturing soon.",
    },
    {
        "id": "travel",
        "title": "Travel",
        "subtitle": "Next trip is coming up.",
    },
    {
        "id": "subscriptions",
        "title": "Subscriptions & Recurring Charges",
        "subtitle": "3 charges may be due this week.",
    },
]

def get_insight_detail(insight_id: str) -> Dict[str, Any]:
    """
    Only used for items that aren't routed to an existing "real" experience.
    We removed Duplicate Charges and Quarterly Life Plan from Insights.
    """
    iid = (insight_id or "").strip().lower()

    if iid == "subscriptions":
        return {
            "card": {
                "title": "Subscriptions & Recurring Charges",
                "subtitle": "Upcoming charges",
                "body": (
                    "Spotify — $11.99 • due in 3 days\n"
                    "Netflix — $15.49 • due in 5 days\n"
                    "iCloud — $2.99 • due in 6 days"
                ),
                "actions": [],
            }
        }

    # Fallback
    return {
        "card": {
            "title": "Insight",
            "subtitle": "Details",
            "body": "No details available.",
            "actions": [],
        }
    }

# -----------------------------
# Card builders
# -----------------------------
def card_transfer_choose_direction() -> Dict[str, Any]:
    return {
        "title": "Transfer money between your accounts",
        "subtitle": "Choose a direction",
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
        "subtitle": f"{from_acct.title()} → {to_acct.title()}",
        "body": "How much would you like to transfer?\nExample: “$25” or “transfer $25”.",
        "actions": [],
    }

def card_transfer_confirm(from_acct: str, to_acct: str, amt: float, action_id: str) -> Dict[str, Any]:
    return {
        "title": "Confirm transfer",
        "subtitle": f"{from_acct.title()} → {to_acct.title()}",
        "body": (
            f"Please confirm:\n"
            f"- Amount: ${amt:.2f}\n"
            f"- From: {from_acct.title()}\n"
            f"- To: {to_acct.title()}\n"
        ),
        "actions": [
            {"label": "Confirm transfer", "action_name": "confirm_transfer", "params": {"action_id": action_id}},
            {"label": "Cancel", "action_name": "cancel_transfer", "params": {"action_id": action_id}},
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
            trace = make_trace(
                decision="Continue transfer workflow",
                reason="Wizard awaiting amount",
                agent="BankingAgent",
                capability="Transfers",
                result="Asked user for amount",
                confidence="medium",
            )
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": "How much would you like to transfer?"}],
                "card": card_transfer_ask_amount(pending["from_account"], pending["to_account"]),
                "debug": {
                    "intent": "bank_transfer",
                    "entities": {},
                    "policy": {"allow": True, "risk": "medium", "reason": "Needs amount"},
                    "agent_trace": trace,
                    "ts": now_ts(),
                },
            }

        entities = {"amount": float(amt), "from_account": pending["from_account"], "to_account": pending["to_account"]}
        policy = policy_check("bank_transfer", entities, state)

        if not policy["allow"]:
            state["pending_action"] = None
            trace = make_trace(
                decision="Block transfer before confirmation",
                reason=policy["reason"],
                agent="PIP",
                capability="Policy check",
                result="Blocked unsafe transfer",
                confidence="high",
            )
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": f"{policy['reason']}"}],
                "card": {"title": "Transfer blocked", "subtitle": "Policy check", "body": policy["reason"], "actions": []},
                "debug": {
                    "intent": "bank_transfer",
                    "entities": entities,
                    "policy": policy,
                    "agent_trace": trace,
                    "ts": now_ts(),
                },
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

        trace = make_trace(
            decision="Require confirmation for transfer",
            reason="High-sensitivity action",
            agent="BankingAgent",
            capability="Transfers",
            result="Returned confirmation card",
            confidence="high",
        )
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "For your safety, please confirm this transfer."}],
            "card": card_transfer_confirm(pending["from_account"], pending["to_account"], float(amt), action_id),
            "debug": {
                "intent": "bank_transfer",
                "entities": entities,
                "policy": policy,
                "agent_trace": trace,
                "ts": now_ts(),
            },
        }

    # -----------------------------
    # Insights
    # -----------------------------
    if intent == "bank_insights":
        trace = make_trace(
            decision="Surface proactive insights",
            reason="User requested insights",
            agent="BankingAgent",
            capability="Insights",
            result="Returned insight list",
            confidence="high",
        )
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here are your latest insights."}],
            "card": {
                "title": "Insights",
                "subtitle": "Tap an insight to view details",
                "body": "Use the Insights button to view and open insights.",
                "actions": [],
            },
            "debug": {
                "intent": intent,
                "entities": {},
                "policy": {"allow": True, "risk": "low", "reason": "Allowed"},
                "agent_trace": trace,
                "insights": INSIGHTS,
                "ts": now_ts(),
            },
        }

    # -----------------------------
    # CD Maturity (renamed card: Manage CD)
    # -----------------------------
    if intent == "assets_cd_maturity":
        trace = make_trace(
            decision="Notify CD maturity timeline",
            reason="User asked about CD maturity",
            agent="AssetsAgent",
            capability="CD alerts",
            result="Returned Manage CD card",
            confidence="high",
        )
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here’s your CD maturity details."}],
            "card": {
                "title": "Manage CD",
                "subtitle": "Upcoming maturity (next 30 days)",
                "body": (
                    "12-month CD — $5,000 — matures in 12 days\n"
                    "6-month CD — $2,500 — matures in 21 days\n\n"
                    "Suggestion: roll into a ladder or move to Savings if you need liquidity."
                ),
                "actions": [],
            },
            "debug": {
                "intent": intent,
                "entities": {},
                "policy": {"allow": True, "risk": "low", "reason": "Allowed"},
                "agent_trace": trace,
                "ts": now_ts(),
            },
        }

    # -----------------------------
    # Travel upcoming (rename card title: Travel) + ✅ enrich details
    # -----------------------------
    if intent == "travel_upcoming":
        trace = make_trace(
            decision="Show upcoming trip summary",
            reason="User requested travel details",
            agent="TravelAgent",
            capability="Upcoming travel",
            result="Returned Travel card",
            confidence="high",
        )
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here’s your travel details."}],
            "card": {
                "title": "Travel",
                "subtitle": "Next trip",
                "body": (
                    "Destination: Orlando, FL\n"
                    "Dates: Feb 28–Mar 3\n\n"
                    "Flight: JetBlue B6 417\n"
                    "Depart: CMH 9:10 AM → MCO 11:38 AM\n"
                    "Return: MCO 6:25 PM → CMH 8:52 PM\n\n"
                    "Hotel: Hyatt Regency Orlando\n"
                    "Address: 9801 International Dr, Orlando, FL\n"
                    "Check-in: 4:00 PM • Check-out: 11:00 AM\n"
                    "Confirmation: HY-82K19\n\n"
                    "Travel points: 42,500"
                ),
                "actions": [],
            },
            "debug": {
                "intent": intent,
                "entities": {},
                "policy": {"allow": True, "risk": "low", "reason": "Allowed"},
                "agent_trace": trace,
                "ts": now_ts(),
            },
        }

    # -----------------------------
    # Agent handoff
    # -----------------------------
    if intent == "agent_handoff":
        agent_notes = (
            "Agent Notes:\n"
            f"- User: {req.user_id}\n"
            f"- Request: {text}\n"
            "- Suggested next step: verify identity + confirm issue category\n"
            "- Context: demo environment, no real transactions\n"
        )

        trace = make_trace(
            decision="Initiate human handoff",
            reason="User asked for an agent",
            agent="HandoffAgent",
            capability="Agent handoff",
            result="Prepared handoff package + asked for confirmation",
            confidence="high",
        )

        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "I can connect you to an agent. Want to proceed?"}],
            "card": {
                "title": "Talk to an Agent",
                "subtitle": "Secure handoff",
                "body": "If you confirm, I’ll create an agent handoff package (notes + context) and connect you.",
                "actions": [
                    {"label": "Connect me to an agent", "action_name": "agent_connect", "params": {"agent_notes": agent_notes}},
                    {"label": "Not now", "action_name": "agent_cancel", "params": {}},
                ],
            },
            "debug": {
                "intent": intent,
                "entities": {},
                "policy": {"allow": True, "risk": "low", "reason": "Allowed"},
                "agent_trace": trace,
                "ts": now_ts(),
            },
        }

    # -----------------------------
    # Recurring
    # -----------------------------
    if intent == "bank_recurring_charges":
        trace = make_trace(
            decision="Show recurring charges",
            reason="User asked for subscriptions/recurring",
            agent="BankingAgent",
            capability="Recurring charges",
            result="Returned subscriptions list",
            confidence="high",
        )
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here are your upcoming subscriptions."}],
            "card": {
                "title": "Subscriptions & Recurring Charges",
                "subtitle": "Upcoming charges",
                "body": (
                    "Spotify — $11.99 • due in 3 days\n"
                    "Netflix — $15.49 • due in 5 days\n"
                    "iCloud — $2.99 • due in 6 days"
                ),
                "actions": [],
            },
            "debug": {
                "intent": intent,
                "entities": {},
                "policy": {"allow": True, "risk": "low", "reason": "Allowed"},
                "agent_trace": trace,
                "ts": now_ts(),
            },
        }

    # -----------------------------
    # Account summary
    # -----------------------------
    if intent == "bank_account_summary":
        b = state["balances"]
        trace = make_trace(
            decision="Show balances",
            reason="User asked for account summary",
            agent="BankingAgent",
            capability="Balances",
            result="Returned balances card",
            confidence="high",
        )
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here’s your balances overview."}],
            "card": {
                "title": "Account Summary",
                "subtitle": "Balances overview",
                "body": f"Checking: ${b['checking']:.2f}\nSavings: ${b['savings']:.2f}",
                "actions": [],
            },
            "debug": {
                "intent": intent,
                "entities": {},
                "policy": {"allow": True, "risk": "low", "reason": "Allowed"},
                "agent_trace": trace,
                "ts": now_ts(),
            },
        }

    # -----------------------------
    # Spend analysis
    # -----------------------------
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

        trace = make_trace(
            decision="Generate spend insights",
            reason="User asked for spend analysis",
            agent="BankingAgent",
            capability="Spend analysis",
            result="Returned spend summary + charts payload",
            confidence="high",
        )

        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "Here’s your spend analysis."}],
            "card": {
                "title": "Spend Analysis",
                "subtitle": "This month vs last month",
                "body": (
                    "Top categories:\n"
                    "- Groceries: $420\n"
                    "- Dining: $260\n"
                    "- Gas: $110\n"
                    "- Subscriptions: $35\n\n"
                    "Suggestion: Dining is trending higher — consider setting a weekly cap."
                ),
                "actions": [],
            },
            "debug": {
                "intent": intent,
                "entities": {},
                "policy": {"allow": True, "risk": "low", "reason": "Allowed"},
                "charts": charts,
                "agent_trace": trace,
                "ts": now_ts(),
            },
        }

    # -----------------------------
    # Transfer
    # -----------------------------
    if intent == "bank_transfer":
        from_acct, to_acct = parse_direction(text)
        amt = parse_amount(text)

        # Case 1: transfer with no info -> choose direction
        if (from_acct is None or to_acct is None) and amt is None:
            state["pending_action"] = {"type": "transfer", "stage": "awaiting_direction"}
            trace = make_trace(
                decision="Start transfer workflow",
                reason="Transfer requested without direction/amount",
                agent="BankingAgent",
                capability="Transfers",
                result="Asked user to choose direction",
                confidence="medium",
            )
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": "Sure — where do you want to transfer money from and to?"}],
                "card": card_transfer_choose_direction(),
                "debug": {
                    "intent": intent,
                    "entities": {},
                    "policy": {"allow": True, "risk": "medium", "reason": "Needs direction"},
                    "agent_trace": trace,
                    "ts": now_ts(),
                },
            }

        # Case 2: amount but no direction
        if (from_acct is None or to_acct is None) and amt is not None:
            state["pending_action"] = {"type": "transfer", "stage": "awaiting_direction", "amount_hint": float(amt)}
            trace = make_trace(
                decision="Collect transfer direction",
                reason="Amount provided, direction missing",
                agent="BankingAgent",
                capability="Transfers",
                result="Asked user to choose direction (kept amount as hint)",
                confidence="medium",
            )
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": f"Got it — you want to transfer ${float(amt):.2f}. Which direction?"}],
                "card": card_transfer_choose_direction(),
                "debug": {
                    "intent": intent,
                    "entities": {"amount": float(amt)},
                    "policy": {"allow": True, "risk": "medium", "reason": "Needs direction"},
                    "agent_trace": trace,
                    "ts": now_ts(),
                },
            }

        # Case 3: direction but no amount
        if from_acct and to_acct and amt is None:
            state["pending_action"] = {"type": "transfer", "stage": "awaiting_amount", "from_account": from_acct, "to_account": to_acct}
            trace = make_trace(
                decision="Collect transfer amount",
                reason="Direction provided, amount missing",
                agent="BankingAgent",
                capability="Transfers",
                result="Asked user for amount",
                confidence="medium",
            )
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": f"How much would you like to transfer from {from_acct.title()} to {to_acct.title()}?"}],
                "card": card_transfer_ask_amount(from_acct, to_acct),
                "debug": {
                    "intent": intent,
                    "entities": {"from_account": from_acct, "to_account": to_acct},
                    "policy": {"allow": True, "risk": "medium", "reason": "Needs amount"},
                    "agent_trace": trace,
                    "ts": now_ts(),
                },
            }

        # Case 4: explicit direction + amount -> confirm
        entities = {"amount": float(amt or 0), "from_account": from_acct, "to_account": to_acct}
        policy = policy_check(intent, entities, state)

        if not policy["allow"]:
            state["pending_action"] = None
            trace = make_trace(
                decision="Block transfer before confirmation",
                reason=policy["reason"],
                agent="PIP",
                capability="Policy check",
                result="Blocked unsafe transfer",
                confidence="high",
            )
            return {
                "session_id": req.session_id,
                "messages": [{"role": "assistant", "content": policy["reason"]}],
                "card": {"title": "Transfer blocked", "subtitle": "Policy check", "body": policy["reason"], "actions": []},
                "debug": {
                    "intent": intent,
                    "entities": entities,
                    "policy": policy,
                    "agent_trace": trace,
                    "ts": now_ts(),
                },
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

        trace = make_trace(
            decision="Require confirmation for transfer",
            reason="High-sensitivity action",
            agent="BankingAgent",
            capability="Transfers",
            result="Returned confirmation card",
            confidence="high",
        )
        return {
            "session_id": req.session_id,
            "messages": [{"role": "assistant", "content": "For your safety, please confirm this transfer."}],
            "card": card_transfer_confirm(from_acct, to_acct, float(amt), action_id),
            "debug": {
                "intent": intent,
                "entities": entities,
                "policy": policy,
                "agent_trace": trace,
                "ts": now_ts(),
            },
        }

    # Fallback
    trace = make_trace(
        decision="Ask user to rephrase",
        reason="Unknown intent",
        agent="Planner",
        capability="Routing",
        result="Returned suggestions",
        confidence="low",
    )
    return {
        "session_id": req.session_id,
        "messages": [{"role": "assistant", "content": "I didn’t catch that. Try: insights, recurring charges, spend analysis, account summary, upcoming travel, cd maturity alert, talk to an agent, or transfer money."}],
        "card": {
            "title": "Try something else",
            "subtitle": "Examples",
            "body": "• insights\n• recurring charges\n• spend analysis\n• account summary\n• upcoming travel\n• cd maturity alert\n• talk to an agent\n• transfer money",
            "actions": [],
        },
        "debug": {
            "intent": intent,
            "entities": {},
            "policy": {"allow": True, "risk": "low", "reason": "Allowed"},
            "agent_trace": trace,
            "ts": now_ts(),
        },
    }

# -----------------------------
# /action
# -----------------------------
@app.post("/action")
def action(req: ActionRequest):
    state = get_state(req.session_id)
    pending = state.get("pending_action")

    # -----------------------------
    # Insights "VIEW" handler
    # -----------------------------
    if req.action_name == "insight_view":
        insight_id = (req.params or {}).get("insight_id", "")
        iid = (insight_id or "").strip().lower()

        # Route to existing experiences so VIEW always shows something real
        if iid == "spend_path":
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

            trace = make_trace(
                decision="Open Spend Path insight",
                reason="User tapped VIEW",
                agent="InsightsAgent",
                capability="Spend analysis",
                result="Returned Spend Analysis card + charts",
                confidence="high",
            )
            return {
                "ok": True,
                "messages": [{"role": "assistant", "content": "Opening Spend Path."}],
                "card": {
                    "title": "Spend Analysis",
                    "subtitle": "This month vs last month",
                    "body": (
                        "Top categories:\n"
                        "- Groceries: $420\n"
                        "- Dining: $260\n"
                        "- Gas: $110\n"
                        "- Subscriptions: $35\n\n"
                        "Suggestion: Dining is trending higher — consider setting a weekly cap."
                    ),
                    "actions": [],
                },
                "debug": {"action": req.action_name, "agent_trace": trace, "charts": charts, "ts": now_ts()},
            }

        if iid == "upcoming_cd_maturity":
            trace = make_trace(
                decision="Open Upcoming CD maturity insight",
                reason="User tapped VIEW",
                agent="InsightsAgent",
                capability="CD alerts",
                result="Returned Manage CD card",
                confidence="high",
            )
            return {
                "ok": True,
                "messages": [{"role": "assistant", "content": "Opening Manage CD."}],
                "card": {
                    "title": "Manage CD",
                    "subtitle": "Upcoming maturity (next 30 days)",
                    "body": (
                        "12-month CD — $5,000 — matures in 12 days\n"
                        "6-month CD — $2,500 — matures in 21 days\n\n"
                        "Suggestion: roll into a ladder or move to Savings if you need liquidity."
                    ),
                    "actions": [],
                },
                "debug": {"action": req.action_name, "agent_trace": trace, "ts": now_ts()},
            }

        if iid == "travel":
            trace = make_trace(
                decision="Open Travel insight",
                reason="User tapped VIEW",
                agent="InsightsAgent",
                capability="Travel",
                result="Returned Travel card",
                confidence="high",
            )
            return {
                "ok": True,
                "messages": [{"role": "assistant", "content": "Opening Travel."}],
                "card": {
                    "title": "Travel",
                    "subtitle": "Next trip",
                    "body": (
                        "Destination: Orlando, FL\n"
                        "Dates: Feb 28–Mar 3\n\n"
                        "Flight: JetBlue B6 417\n"
                        "Depart: CMH 9:10 AM → MCO 11:38 AM\n"
                        "Return: MCO 6:25 PM → CMH 8:52 PM\n\n"
                        "Hotel: Hyatt Regency Orlando\n"
                        "Address: 9801 International Dr, Orlando, FL\n"
                        "Check-in: 4:00 PM • Check-out: 11:00 AM\n"
                        "Confirmation: HY-82K19\n\n"
                        "Travel points: 42,500"
                    ),
                    "actions": [],
                },
                "debug": {"action": req.action_name, "agent_trace": trace, "ts": now_ts()},
            }

        # Remaining items: simple detail cards (subscriptions, etc.)
        detail = get_insight_detail(iid)
        trace = make_trace(
            decision="Open selected insight",
            reason=f"User tapped VIEW for {iid}",
            agent="InsightsAgent",
            capability="Insight detail",
            result="Returned insight detail card",
            confidence="high",
        )
        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": "Opening that insight."}],
            "card": detail.get("card"),
            "debug": {"action": req.action_name, "agent_trace": trace, "ts": now_ts()},
        }

    # -----------------------------
    # Transfer direction
    # -----------------------------
    if req.action_name == "transfer_set_direction":
        from_acct = (req.params or {}).get("from_account")
        to_acct = (req.params or {}).get("to_account")

        if from_acct not in ("checking", "savings") or to_acct not in ("checking", "savings") or from_acct == to_acct:
            return {"ok": False, "messages": [{"role": "assistant", "content": "Invalid direction."}]}

        amount_hint = None
        if pending and pending.get("type") == "transfer" and pending.get("amount_hint") is not None:
            try:
                amount_hint = float(pending.get("amount_hint"))
            except:
                amount_hint = None

        state["pending_action"] = {"type": "transfer", "stage": "awaiting_amount", "from_account": from_acct, "to_account": to_acct}

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
            "messages": [{"role": "assistant", "content": "Transfer cancelled."}],
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
                "messages": [{"role": "assistant", "content": f"Insufficient funds in {from_acct.title()}."}],
                "card": {"title": "Transfer blocked", "subtitle": "Insufficient funds", "body": "Not enough balance.", "actions": []},
            }

        b[from_acct] -= amount
        b[to_acct] += amount
        state["pending_action"] = None

        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": f"Transfer complete. Moved ${amount:.2f} to {to_acct.title()}."}],
            "card": {
                "title": "Transfer complete",
                "subtitle": "Updated balances",
                "body": f"Checking: ${b['checking']:.2f}\nSavings: ${b['savings']:.2f}",
                "actions": [],
            },
            "balances": b,
            "debug": {"action": req.action_name, "ts": now_ts()},
        }

    # Agent connect/cancel
    if req.action_name == "agent_connect":
        notes = (req.params or {}).get("agent_notes", "")
        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": "Connected. An agent has your context."}],
            "card": {"title": "Agent Connected", "subtitle": "Handoff packet", "body": notes, "actions": []},
            "debug": {"action": req.action_name, "ts": now_ts()},
        }

    if req.action_name == "agent_cancel":
        return {
            "ok": True,
            "messages": [{"role": "assistant", "content": "No problem — I’m here if you need me."}],
            "card": {"title": "Stayed in chat", "subtitle": "No handoff", "body": "Tell me what you’d like to do next.", "actions": []},
            "debug": {"action": req.action_name, "ts": now_ts()},
        }

    return {"ok": False, "messages": [{"role": "assistant", "content": "Unknown action."}], "debug": {"action": req.action_name, "ts": now_ts()}}
