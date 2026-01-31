from typing import Dict, Any

def handle(intent: str, entities: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    if intent == "travel_points":
        pts = 48250
        cash = round(pts * 0.0125, 2)
        return {
            "messages": [{"role": "assistant", "content": "Here are your travel points (demo)."}],
            "card": {
                "title": "Travel Rewards",
                "subtitle": "Points available (demo)",
                "body": f"Available points: {pts:,}\nEstimated cash value: ${cash:.2f}\n\nDemo data only.",
                "actions": [
                    {"label": "Points → cash (estimate)", "action_name": "travel_points_to_cash", "params": {}},
                ],
            },
        }

    if intent == "travel_upcoming":
        return {
            "messages": [{"role": "assistant", "content": "Here’s your upcoming travel (demo)."}],
            "card": {
                "title": "Upcoming Trip",
                "subtitle": "Vacation preview (demo)",
                "body": (
                    "Destination: Orlando\n"
                    "Dates: Mar 12–Mar 17\n"
                    "Vibe: Family + theme parks\n\n"
                    "Suggestion (demo): Want me to estimate how many points you could apply?"
                ),
                "actions": [
                    {"label": "View travel points", "action_name": "travel_points", "params": {}},
                    {"label": "Points → cash (estimate)", "action_name": "travel_points_to_cash", "params": {}},
                ],
            },
        }

    if intent == "travel_points_to_cash":
        pts = 48250
        cash = round(pts * 0.0125, 2)
        return {
            "messages": [{"role": "assistant", "content": "Here’s an estimate of your points converted to cash (demo)."}],
            "card": {
                "title": "Points → Cash (Estimate)",
                "subtitle": "Conversion estimate (demo)",
                "body": f"{pts:,} points ≈ ${cash:.2f}\n\nRates vary by program. Demo estimate only.",
                "actions": [],
            },
        }

    return {
        "messages": [{"role": "assistant", "content": "Travel agent couldn’t match that (demo)."}],
        "card": {
            "title": "Travel",
            "subtitle": "Try one of these",
            "body": "• travel points\n• upcoming travel\n• points to cash",
            "actions": [],
        },
    }
