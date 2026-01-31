from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class PolicyDecision:
    allow: bool
    reason: str = ""
    risk: str = "low"  # low | medium | high


def evaluate_policy(intent: str, entities: Dict[str, Any], balances: Optional[Dict[str, float]] = None) -> PolicyDecision:
    """
    PIP = Policy / Identity / Permissions gate (demo version).
    This is where real systems would check authN/authZ, limits, step-up, consent, etc.

    Rules we want:
      - Unknown intent => blocked
      - Transfers:
          * missing amount => allow (so orchestrator can ask clarifying question)
          * amount <= 0 => block
          * amount >= 5000 => block (demo "step-up")
          * insufficient funds in FROM account => block BEFORE confirmation
    """

    if not intent or intent in ("unknown",):
        return PolicyDecision(False, "I didn’t understand that request.", "low")

    if intent == "bank_transfer":
        amount_raw = entities.get("amount", None)

        # ✅ Missing amount should NOT be blocked (let orchestrator ask "How much?")
        if amount_raw is None:
            return PolicyDecision(True, "Amount required (clarify)", "low")

        try:
            amt = float(amount_raw or 0)
        except Exception:
            return PolicyDecision(False, "Transfer amount is invalid.", "low")

        if amt <= 0:
            return PolicyDecision(False, "Transfer amount must be greater than $0.", "low")

        if amt >= 5000:
            return PolicyDecision(
                False,
                "For safety, transfers above $5,000 require additional verification (demo).",
                "high",
            )

        # ✅ Insufficient funds check happens here (before confirmation card)
        from_acct = (entities.get("from_account") or "checking").lower().strip()
        if balances is not None:
            available = float(balances.get(from_acct, 0) or 0)
            if available < amt:
                return PolicyDecision(
                    False,
                    f"Insufficient funds in {from_acct.title()} (demo). Available: ${available:.2f}",
                    "low",
                )

    return PolicyDecision(True, "Allowed", "low")
