from typing import Dict, Any

def handle(intent: str, entities: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    cds = [
        {"name": "12-mo CD", "apr": 5.10, "balance": 10000.00, "matures_in_days": 112},
        {"name": "6-mo CD", "apr": 4.60, "balance": 5000.00, "matures_in_days": 29},
    ]

    if intent == "assets_cds_overview":
        lines = []
        total = 0.0
        for cd in cds:
            total += cd["balance"]
            lines.append(
                f"{cd['name']} — ${cd['balance']:.2f} @ {cd['apr']:.2f}% • matures in {cd['matures_in_days']} days"
            )
        return {
            "messages": [{"role": "assistant", "content": "Here’s your CD overview (demo)."}],
            "card": {
                "title": "Certificates of Deposit",
                "subtitle": "CDs overview (demo)",
                "body": "\n".join(lines) + f"\n\nTotal in CDs: ${total:.2f}\n\nDemo data only.",
                "actions": [
                    {"label": "Maturity alerts (demo)", "action_name": "assets_cd_maturity_alert", "params": {}},
                ],
            },
        }

    if intent == "assets_cd_maturity_alert":
        soon = [c for c in cds if c["matures_in_days"] <= 30]
        if not soon:
            body = "No CDs maturing within 30 days (demo)."
        else:
            body = "\n".join([f"{c['name']} matures in {c['matures_in_days']} days — ${c['balance']:.2f}" for c in soon])
        return {
            "messages": [{"role": "assistant", "content": "Here are your CD maturity alerts (demo)."}],
            "card": {
                "title": "CD Maturity Alerts",
                "subtitle": "Maturing soon (demo)",
                "body": body + "\n\nSuggestion (demo): decide whether to renew, ladder, or move to savings.",
                "actions": [],
            },
        }

    if intent == "assets_cds_vs_savings":
        return {
            "messages": [{"role": "assistant", "content": "Here’s a quick CD vs Savings view (demo)."}],
            "card": {
                "title": "CDs vs Savings",
                "subtitle": "At-a-glance (demo)",
                "body": (
                    "CDs: Higher rate, less flexible until maturity.\n"
                    "Savings: Lower rate, high flexibility.\n\n"
                    "If you won’t need the money soon, CDs may be better.\n"
                    "If you need liquidity, keep it in Savings.\n\nDemo guidance only."
                ),
                "actions": [],
            },
        }

    if intent == "assets_cd_interest_movement":
        return {
            "messages": [{"role": "assistant", "content": "I can help route CD interest when it posts (demo)."}],
            "card": {
                "title": "CD Interest Movement",
                "subtitle": "Setup (demo-safe)",
                "body": (
                    "In a real flow, we’d ask:\n"
                    "• Which CD?\n"
                    "• Move interest to Savings or Checking?\n"
                    "• One-time or recurring?\n\n"
                    "Demo: No real setup performed."
                ),
                "actions": [],
            },
        }

    return {
        "messages": [{"role": "assistant", "content": "Assets agent couldn’t match that (demo)."}],
        "card": {
            "title": "Assets",
            "subtitle": "Try one of these",
            "body": "• CDs overview\n• CD maturity alert\n• CDs vs savings\n• CD interest movement",
            "actions": [],
        },
    }
