# Matched Betting Risk Engine

## Overview
Short, precise description of what this project actually does.

## Architecture
Brief explanation of:
- engine/
- repo layer
- execution layer
- analytics layer
- Monte Carlo layer
- Streamlit UI

## Core Features
- Pricing engine (qualifying, SNR, SR)
- Partial lay matching
- Settlement with realised PnL
- Ledger + bankroll tracking
- Monte Carlo risk modelling
- Equity / drawdown analytics dashboard

## Risk Model Assumptions
Explicitly state:
- Fill model
- Slippage model
- Void modelling
- Independence assumptions
- VaR computation method

## How to Run
pip install -r requirements.txt
streamlit run streamlit_app.py

## Example Workflow
1. Set bankroll
2. Price bet
3. Place
4. Match
5. Settle
6. Run risk

## Future Improvements
2–3 serious ones only (not fluff)
