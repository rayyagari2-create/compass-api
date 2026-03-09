# Compass API — Project Guide

## Overview
Compass is a **CX orchestrator demo** for digital banking. It powers a chat-based assistant that handles banking, travel, and asset management intents through an agentic routing pipeline (Planner → Delegate → Act).

**Target audience:** Managing Director-level demo at Chase.

## Tech Stack
- **Framework:** FastAPI + Uvicorn
- **Language:** Python 3.11+
- **Validation:** Pydantic
- **Deployment:** Local dev (uvicorn main:app --reload)

## Project Structure
```
compass-api/
├── main.py              # Orchestrator: endpoints, intent routing, policy, card builders
├── agents/
│   ├── router.py        # Agent-level router (unused — logic lives in main.py)
│   ├── banking_agent.py # Banking agent handler (unused — inlined in main.py)
│   ├── travel_agent.py  # Travel agent handler (unused — inlined in main.py)
│   └── assets_agent.py  # Assets/CD agent handler (unused — inlined in main.py)
├── core/
│   ├── router.py        # Core NLP router (unused — inlined in main.py)
│   ├── nlp.py           # Empty placeholder
│   ├── models.py        # Empty placeholder
│   └── state.py         # Empty placeholder
├── memory/
│   └── aom.py           # Agent Operating Memory (unused — state in main.py)
├── policy/
│   └── pip.py           # Policy engine (unused — inlined in main.py)
├── requirements.txt     # fastapi, uvicorn, pydantic
└── .gitignore
```

> **Note:** The modular files under agents/, core/, memory/, policy/ are an earlier architecture.
> All live logic currently runs through main.py. Future refactor should reconcile these.

## Key Endpoints
- `GET /health` — Health check
- `POST /orchestrate` — Main chat endpoint (text → intent → policy → response)
- `POST /action` — Button/action handler (transfer confirm, insight view, etc.)

## Intent Routing
Intent is resolved via keyword matching in `route_intent()`. Supported intents:
- `bank_insights`, `bank_recurring_charges`, `bank_spend_analysis`
- `bank_account_summary`, `bank_transfer`
- `assets_cd_maturity`, `travel_upcoming`
- `agent_handoff`

## Transfer Wizard Flow
Multi-step stateful flow: direction → amount → policy check → confirmation → execute.
State stored in `_DEMO_STATE[session_id]["pending_action"]`.

**Intent-first escape hatch:** If the user types a recognized non-transfer intent while
the wizard is awaiting an amount (e.g. "account summary"), the pending transfer is
silently abandoned and the new intent is handled normally. This prevents the wizard
from trapping users who change their mind.

## Policy Engine
`policy_check()` gates transfers: validates amount > 0, < $5000, sufficient funds.

## Insights Feed
`INSIGHTS` list drives the proactive insights UI. Each insight includes:
- `id`, `title`, `subtitle` — display fields
- `metric` — bold callout (e.g. "+18% vs last month", "$30.47 due this week")
- `category` — drives UI color coding: `spend` (amber), `assets` (yellow), `travel` (sky), `recurring` (gray)
- `priority` — `high`, `medium`, `low`
- `is_new` — shows a "New" badge in the UI

## Agent Trace Names
Traces use professional names for the MD demo:
- `Financial Services Agent` — banking intents (transfers, balances, spend, recurring)
- `Asset Management Agent` — CD maturity, asset management
- `Travel Services Agent` — upcoming travel
- `Client Services Agent` — human agent handoff
- `Insights Agent` — insight detail views
- `Policy Engine` — transfer policy gating
- `Planner` — fallback/routing

## Conventions
- All API responses include a `debug` payload with `agent_trace` (Planner/Delegate/Act)
- Card responses follow: `{ title, subtitle, body, actions[] }`
- No real banking actions — all data is hardcoded demo data
- CORS allows localhost:3000/3001 and Vercel deployment
- No "(demo)" text in any API response — UI should not need to strip it

## Running Locally
```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Companion UI
- Repo: compass-ui (Next.js 16 / React 19 / Tailwind 4)
- Deployed: https://compass-ui-blush.vercel.app/
- Env var: `NEXT_PUBLIC_API_BASE` (defaults to http://127.0.0.1:8000)

## Changelog
- **v1.1** — Enriched insights with metric/category/priority/is_new fields; intent-first
  escape hatch for transfer wizard; professional agent trace names; bare except cleanup
- **v1.0** — Initial orchestrator with transfer wizard, insights, travel, CD, handoff
