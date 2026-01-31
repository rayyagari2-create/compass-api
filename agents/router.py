import re
from typing import Dict, Any, Tuple


def route(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Very lightweight NLP router (demo).
    Returns: intent + entities
    Replace later with real classifier / LLM router.
    """

    t = (text or "").strip().lower()

    # Banking intents
    if "account summary" in t or "balance" in t or "balances" in t:
        return "bank_account_summary", {}

    if "recurring" in t or "subscriptions" in t:
        return "bank_recurring_charges", {}

    if "transfer" in t or "send money" in t or "move money" in t:
        # amount parsing like "transfer $25" or "transfer 25"
        m = re.search(r"\$?\s*([0-9]+(\.[0-9]+)?)", t)
        amount = float(m.group(1)) if m else 0.0

        # simple direction inference
        frm = "Checking"
        to = "Savings"
        if "savings to checking" in t:
            frm, to = "Savings", "Checking"
        elif "checking to savings" in t:
            frm, to = "Checking", "Savings"

        return "bank_transfer", {"amount": amount, "from": frm, "to": to}

    if "agent" in t or "specialist" in t or "help me" in t:
        return "handoff_agent", {"topic": text.strip()}

    # Travel intents
    if "travel" in t or "points" in t or "vacation" in t:
        return "travel_overview", {}

    # Assets intents
    if "cd" in t or "certificate of deposit" in t:
        return "assets_cd_overview", {}

    return "unknown", {}
