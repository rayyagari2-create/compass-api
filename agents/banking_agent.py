from typing import Dict, Any

def _balances_card(state: Dict[str, Any]) -> Dict[str, Any]:
    b = state["balances"]
    return {
        "title": "Account Summary",
        "subtitle": "Balances overview (demo)",
        "body": f"Checking: ${b['checking']:.2f}\nSavings: ${b['savings']:.2f}",
        "actions": [],
    }

def _agent_notes(state: Dict[str, Any], note: str) -> None:
    state.setdefault("agent_notes", [])
    state["agent_notes"].append(note)

def _demo_spend_payload() -> Dict[str, Any]:
    spend_by_category = {
        "Groceries": 620,
        "Dining": 310,
        "Gas": 180,
        "Shopping": 540,
        "Bills": 890,
    }
    trend = [
        {"week": "W1", "amount": 520},
        {"week": "W2", "amount": 610},
        {"week": "W3", "amount": 720},
        {"week": "W4", "amount": 690},
    ]

    mtd_total = sum(spend_by_category.values())
    summary = {
        "mtd_total": mtd_total,
        "mom_delta_pct": 18,          # demo
        "top_driver": "Shopping",     # demo
        "message": "Shopping + Dining are trending higher than last month (demo)."
    }

    return {"pie": spend_by_category, "line": trend, "summary": summary}

def handle(intent: str, entities: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    # ---------------------------
    # C) Insights feed (home)
    # ---------------------------
    if intent == "bank_insights_feed":
        _agent_notes(state, "User viewed Insights feed.")
        return {
            "messages": [{"role": "assistant", "content": "Good morning — I have new insights ready for you (demo)."}],
            "card": {
                "title": "Insights",
                "subtitle": "Tap a card to view details",
                "body": (
                    "• Duplicate Charges — you may have been charged more than once\n"
                    "• Spend Path — see your monthly spending trend\n"
                    "• Subscriptions — upcoming recurring charges\n"
                    "• Quick Transfer — send money with confirmation\n"
                ),
                "actions": [
                    {"label": "Duplicate Charges", "action_name": "open_insight", "params": {"kind": "duplicate_charges"}},
                    {"label": "Spend Path", "action_name": "open_insight", "params": {"kind": "spend_path"}},
                    {"label": "Subscriptions", "action_name": "open_insight", "params": {"kind": "subscriptions"}},
                    {"label": "Quick Transfer", "action_name": "open_insight", "params": {"kind": "quick_transfer"}},
                ],
            },
        }

    # ---------------------------
    # Existing: recurring charges
    # ---------------------------
    if intent == "bank_recurring_charges":
        _agent_notes(state, "User asked about recurring charges/subscriptions.")
        return {
            "messages": [{"role": "assistant", "content": "Here are your upcoming subscriptions (demo)."}],
            "card": {
                "title": "Subscriptions & Recurring Charges",
                "subtitle": "Upcoming charges (demo)",
                "body": "Spotify — $11.99 • due in 3 days\nNetflix — $15.49 • due in 5 days\niCloud — $2.99 • due in 6 days\n\nDemo subscriptions only.",
                "actions": [],
            },
        }

    # ---------------------------
    # Existing: account summary
    # ---------------------------
    if intent == "bank_account_summary":
        _agent_notes(state, "User requested balances overview.")
        return {
            "messages": [{"role": "assistant", "content": "Here’s your balances overview (demo)."}],
            "card": _balances_card(state),
        }

    # ---------------------------
    # A) Spend analysis w/ visuals.summary
    # ---------------------------
    if intent == "bank_spend_analysis":
        _agent_notes(state, "User asked for spend analysis/trends.")
        visuals = _demo_spend_payload()
        summary = visuals["summary"]

        return {
            "messages": [{"role": "assistant", "content": "Here’s your spending view for the month (demo)."}],
            "card": {
                "title": "Spend Analysis",
                "subtitle": "Month-to-date overview (demo)",
                "body": (
                    f"{summary['message']}\n\n"
                    "Tip: Tap a category on the pie chart to drill into it."
                ),
                "actions": [
                    {"label": "Drill into Shopping", "action_name": "spend_drilldown", "params": {"category": "Shopping"}},
                    {"label": "View Subscriptions", "action_name": "open_insight", "params": {"kind": "subscriptions"}},
                ],
            },
            "visuals": visuals,
        }

    # ---------------------------
    # B) Spend drilldown (category)
    # ---------------------------
    if intent == "bank_spend_drilldown":
        cat = (entities.get("category") or "Shopping").title()
        _agent_notes(state, f"User drilled into spend category: {cat}")

        # demo “why” + top merchants (fake)
        why = f"{cat} is up ~22% vs last month (demo)."
        merchants = "Top merchants (demo):\n• Merchant A — $120\n• Merchant B — $85\n• Merchant C — $60"

        return {
            "messages": [{"role": "assistant", "content": f"Here’s a quick breakdown for {cat} (demo)."}],
            "card": {
                "title": f"{cat} Insights",
                "subtitle": "Category drilldown (demo)",
                "body": f"{why}\n\n{merchants}\n\nSuggestion (demo): set a soft weekly cap for {cat}.",
                "actions": [
                    {"label": "Set a cap (demo)", "action_name": "bank_set_budget_nudge", "params": {"category": cat}},
                    {"label": "Back to Spend Analysis", "action_name": "open_insight", "params": {"kind": "spend_path"}},
                ],
            },
        }

    # ---------------------------
    # Bill scheduler nudge
    # ---------------------------
    if intent == "bank_bill_scheduler_nudge":
        _agent_notes(state, "User asked about bills/autopay/scheduling.")
        return {
            "messages": [{"role": "assistant", "content": "I can help schedule bills to reduce manual payments (demo)."}],
            "card": {
                "title": "Bill Scheduler",
                "subtitle": "Suggested automation (demo)",
                "body": (
                    "I noticed a bill that looks manually paid each month (demo).\n\n"
                    "Suggestion: schedule it to reduce late-fee risk.\n"
                    "Example: Electric bill — due around the 15th.\n\n"
                    "Demo-safe: No real autopay setup."
                ),
                "actions": [
                    {"label": "Set autopay (demo)", "action_name": "bank_setup_autopay", "params": {"payee": "Electric"}},
                    {"label": "Remind me monthly (demo)", "action_name": "bank_bill_reminder", "params": {"payee": "Electric"}},
                ],
            },
        }

    # ---------------------------
    # Auto-sweep setup
    # ---------------------------
    if intent == "bank_auto_sweep":
        low = float(entities.get("low_threshold", 500) or 500)
        high = float(entities.get("high_threshold", 3000) or 3000)
        _agent_notes(state, f"User asked about auto-sweep rules. Proposed: <{low}, >{high}")
        return {
            "messages": [{"role": "assistant", "content": "Here’s a simple auto-sweep rule setup (demo)."}],
            "card": {
                "title": "Auto-Sweep Rules",
                "subtitle": "Automate money movement (demo)",
                "body": (
                    f"Rule A: If Checking < ${low:.0f}, move money from Savings to Checking.\n"
                    f"Rule B: If Checking > ${high:.0f}, move extra money to Savings.\n\n"
                    "Demo-safe: no real rule created."
                ),
                "actions": [
                    {"label": "Enable rules (demo)", "action_name": "bank_enable_autosweep", "params": {"low": low, "high": high}},
                    {"label": "Edit thresholds (demo)", "action_name": "bank_edit_autosweep", "params": {}},
                ],
            },
        }

    # ---------------------------
    # Credit utilization
    # ---------------------------
    if intent == "bank_credit_utilization":
        _agent_notes(state, "User asked about credit utilization.")
        limit_amt = 8000
        current_bal = 2450
        util = int((current_bal / limit_amt) * 100)
        suggestion = "Suggestion (demo): keeping utilization under ~30% can help reduce score-impact risk."
        return {
            "messages": [{"role": "assistant", "content": "Here’s your credit usage snapshot (demo)."}],
            "card": {
                "title": "Credit Usage",
                "subtitle": "Utilization (demo)",
                "body": f"Card limit: ${limit_amt}\nCurrent balance: ${current_bal}\nUtilization: {util}%\n\n{suggestion}",
                "actions": [
                    {"label": "Set utilization alert (demo)", "action_name": "bank_set_util_alert", "params": {"threshold": 30}},
                ],
            },
        }

    # ---------------------------
    # Handoff
    # ---------------------------
    if intent == "bank_handoff":
        notes = state.get("agent_notes", [])
        notes_text = "\n".join([f"- {n}" for n in notes[-6:]]) if notes else "- (no notes yet)"
        return {
            "messages": [{"role": "assistant", "content": "Okay — I can hand this off to a human agent (demo)."}],
            "card": {
                "title": "Handoff to Agent",
                "subtitle": "Agent-ready notes (demo)",
                "body": (
                    "What I’ll send to the agent:\n"
                    f"{notes_text}\n\n"
                    "In a real flow, this would open secure chat/call scheduling."
                ),
                "actions": [
                    {"label": "Confirm handoff (demo)", "action_name": "bank_confirm_handoff", "params": {}},
                    {"label": "Cancel", "action_name": "bank_cancel_handoff", "params": {}},
                ],
            },
        }

    # Default
    return {
        "messages": [{"role": "assistant", "content": "Try: insights, spend analysis, recurring charges, account summary, transfer $25…"}],
        "card": {
            "title": "Banking",
            "subtitle": "Examples",
            "body": "• insights\n• spend analysis\n• recurring charges\n• account summary\n• transfer $25 from savings to checking",
            "actions": [],
        },
    }
