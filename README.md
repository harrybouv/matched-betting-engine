# Matched Betting Risk Engine

This is a Python-based matched betting engine with a Streamlit dashboard.  
It prices bets, tracks bankroll and liabilities, records real execution (including partial matches), and runs Monte Carlo simulations to quantify risk on open positions.

It’s built to treat matched betting like a small trading book:
- every bet is a position
- cash is tracked explicitly
- liabilities are real
- risk is modelled, not assumed away

---

## What It Actually Does

You input:
- Offer type (qualifying, SNR, SR)
- Back odds
- Lay odds
- Stake or promo amount
- Exchange commission

The system:
- Calculates optimal lay stake and liability
- Tracks locked cash and exposure
- Records matching (including partial fills)
- Settles bets into realised PnL
- Simulates final bankroll distribution using Monte Carlo
- Shows equity curve and drawdown metrics in the dashboard

It’s not a “find bets” tool. It’s a pricing + execution + risk system.

---

## Architecture

The project is deliberately layered. Logic lives in the engine, not the UI.

### `engine/`
Core domain logic only. No Streamlit, no UI state. Everything here should be testable in isolation.

### Repo Layer (Persistence)
Handles reading and writing:
- bankroll state
- open bets
- settled bets
- configuration

Currently file-based (JSON/CSV-first) so state is transparent and easy to debug.

### Execution Layer
Responsible for:
- Creating new bet positions
- Updating match status (partial → full)
- Storing realised matched prices/stakes
- Settling bets into realised PnL
- Updating bankroll and ledger entries

### Analytics Layer
Builds:
- Performance summaries
- Profit breakdown by offer type
- Equity curve
- Drawdown series
- Risk snapshots

Purely derived from stored state.

### Monte Carlo Layer
Simulates:
- Event outcomes
- Execution uncertainty
- Final bankroll distribution

Reports:
- Mean final bankroll
- Worst X% outcome (quantile-based VaR)
- Probability of finishing below current bankroll

### Streamlit UI
Thin interface layer:
- Takes inputs
- Calls engine functions
- Renders tables and charts

If business logic starts creeping into Streamlit, that’s a design failure.

---

## Core Features

- Pricing engine for:
  - Qualifying bets
  - Stake Not Returned (SNR) free bets
  - Stake Returned (SR) free bets
- Partial lay matching support
- Realised PnL settlement
- Explicit bankroll + liability tracking
- Monte Carlo risk modelling on open bets
- Equity and drawdown dashboard

---

## Risk Model Assumptions

These are explicit so you know what’s being assumed.

### Fill Model
If a bet isn’t fully matched:
- The matched fraction is either taken as observed
- Or sampled from a configurable distribution

Unmatched exposure is real and affects outcomes.

### Slippage Model
Lay odds may deviate from quoted odds:
\[
L_{real} = L_{quote} + \epsilon
\]

\(\epsilon\) is sampled from a small noise model (typically adverse or symmetric).

Execution isn’t assumed perfect.

### Void Modelling
Each bet can be voided with probability \(p_{void}\).

If voided:
- Stakes and liabilities unwind according to defined rules.

### Independence Assumptions
By default:
- Event outcomes are independent
- Execution noise is independent

This is a simplification. If you stack bets on the same event, correlation is not modelled unless explicitly added.

### VaR Method
Monte Carlo produces a distribution of final bankroll.

Downside metrics are computed empirically:
- 1% worst outcome = 1st percentile
- Probability of finishing below current bankroll
- Downside at 1%

This is simulation-based VaR, not parametric.

---

## How to Run

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
