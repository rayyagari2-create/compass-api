from typing import Dict, Any
import re

def _contains_any(t: str, words) -> bool:
    return any(w in t for w in words)

def route(text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    t = (text or "").lower().strip()
    entities: Dict[str, Any] = {}

    # ----- Proactive insights feed -----
    if t in ("", "insights", "show insights", "insight", "home"):
        return {"domain": "banking", "intent": "bank_insights_feed", "entities": entities}

    # ----- Spend analysis + drilldown -----
    if t.startswith("spend insight"):
        # e.g. "spend insight dining"
        parts = t.split("spend insight", 1)
        cat = parts[1].strip() if len(parts) > 1 else ""
        if cat:
            entities["category"] = cat.title()
        return {"domain": "banking", "intent": "bank_spend_drilldown", "entities": entities}

    if _contains_any(t, ["spend", "spending", "trend", "budget"]):
        return {"domain": "banking", "intent": "bank_spend_analysis", "entities": entities}

    # ----- Recurring charges -----
    if _contains_any(t, ["recurring", "subscription", "subscriptions"]):
        return {"domain": "banking", "intent": "bank_recurring_charges", "entities": entities}

    # ----- Account summary -----
    if "account" in t and _contains_any(t, ["summary", "balance", "balances"]):
        return {"domain": "banking", "intent": "bank_account_summary", "entities": entities}

    # ----- Credit utilization -----
    if _contains_any(t, ["credit utilization", "credit usage", "utilization", "credit card"]):
        return {"domain": "banking", "intent": "bank_credit_utilization", "entities": entities}

    # ----- Bill scheduler -----
    if _contains_any(t, ["bill", "autopay", "schedule bill", "pay bill"]):
        return {"domain": "banking", "intent": "bank_bill_scheduler_nudge", "entities": entities}

    # ----- Auto-sweep -----
    if _contains_any(t, ["auto sweep", "autosweep", "move money automatically", "threshold", "rule"]):
        m = re.search(r"checking\s*<\s*(\d+)", t)
        if m:
            entities["low_threshold"] = float(m.group(1))
        m = re.search(r"checking\s*>\s*(\d+)", t)
        if m:
            entities["high_threshold"] = float(m.group(1))
        return {"domain": "banking", "intent": "bank_auto_sweep", "entities": entities}

    # ----- Handoff -----
    if _contains_any(t, ["agent", "representative", "human", "talk to someone", "handoff"]):
        return {"domain": "banking", "intent": "bank_handoff", "entities": entities}

    # ----- Transfer -----
    if _contains_any(t, ["transfer", "send", "zelle", "move money"]):
        m = re.search(r"(\$?\s*\d[\d,]*(?:\.\d{1,2})?)", t)
        if m:
            raw = m.group(1).replace("$", "").replace(",", "").strip()
            try:
                entities["amount"] = float(raw)
            except:
                pass

        # Direction parse (basic)
        # If user mentions "from savings to checking" or "checking to savings"
        if "savings to checking" in t or "from savings to checking" in t:
            entities["direction"] = "savings_to_checking"
        elif "checking to savings" in t or "from checking to savings" in t:
            entities["direction"] = "checking_to_savings"

        return {"domain": "banking", "intent": "bank_transfer", "entities": entities}

    # ---- Travel ----
    if _contains_any(t, ["travel points", "points available", "rewards points"]):
        return {"domain": "travel", "intent": "travel_points", "entities": entities}

    if _contains_any(t, ["upcoming travel", "my trip", "vacation", "next trip", "upcoming trip"]):
        return {"domain": "travel", "intent": "travel_upcoming", "entities": entities}

    if _contains_any(t, ["points to cash", "convert points", "cash out points"]):
        return {"domain": "travel", "intent": "travel_points_to_cash", "entities": entities}

    # ---- Assets ----
    if _contains_any(t, ["cd maturity", "maturity alert", "matures", "maturing"]):
        return {"domain": "assets", "intent": "assets_cd_maturity_alert", "entities": entities}

    if _contains_any(t, ["cd interest", "move interest", "interest movement"]):
        return {"domain": "assets", "intent": "assets_cd_interest_movement", "entities": entities}

    if _contains_any(t, ["cd", "cds", "certificate of deposit"]):
        if _contains_any(t, ["vs", "compare"]):
            return {"domain": "assets", "intent": "assets_cds_vs_savings", "entities": entities}
        return {"domain": "assets", "intent": "assets_cds_overview", "entities": entities}

    return {"domain": "unknown", "intent": "unknown", "entities": entities}
