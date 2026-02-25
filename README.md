# Matched Betting Risk Engine

A Python engine + Streamlit dashboard for **pricing**, **tracking**, and **risk-modelling** matched betting positions across bookmakers and an exchange (e.g., Betfair).

It’s not a “tips” app. It’s a **position + cashflow system**:
- you input/ingest offers and odds
- the engine computes optimal stakes + liabilities
- you record execution (including imperfect fills)
- you settle outcomes into realised PnL
- you run Monte Carlo to quantify bankroll risk (VaR-style) on the open book
- the UI visualises equity and drawdown

---

## Overview (what it actually does)

**Inputs:** offers, back odds, lay odds, commission, stake limits, bankroll constraints, (optional) execution fill information.  
**Outputs:** recommended staking, locked cash/liability, expected profit, realised profit after settlement, and a risk distribution for final bankroll given open bets.

The key idea: the system treats each bet as a **financial position** with:
- cash outflows/inflows
- liabilities
- settlement rules
- execution uncertainty (partial matches, slippage, voids)

---

## Architecture

High-level layering (keep this separation — it’s the whole point):

### `engine/`
Core domain logic. No Streamlit, no UI state. Pure Python.

### Repo layer (persistence)
Responsible for reading/writing the system state:
- bankroll / available cash
- open bets
- settled bets
- configuration (commission, assumptions, etc.)

Typically JSON/CSV-first so you can inspect and debug without a database.

### Execution layer
Turns priced opportunities into *positions* and updates them as reality happens:
- place a bet (creates an open position)
- update matching (partial/full)
- record the actual matched prices/stakes
- settle into realised PnL
- maintain a ledger-like record of changes

### Analytics layer
Computes reporting tables and derived metrics from repo state:
- performance summaries (by offer type, by result, totals)
- equity curve and drawdowns
- exposure/locked cash/liability snapshots
- quality checks / data validation summaries

### Monte Carlo layer
Simulates bankroll outcomes under uncertainty for the current set of open bets:
- samples outcomes + execution noise (fill/slippage/void)
- produces distribution of final bankroll
- reports downside risk metrics (VaR-style, probability of drawdown)

### Streamlit UI
A thin shell:
- collects inputs
- calls engine/execution/analytics functions
- renders tables and charts
- never contains “business logic” that you can’t unit-test

If your logic lives in Streamlit, you’ve already lost.

---

## Core Features

- **Pricing engine** for:
  - Qualifying bets
  - SNR (stake-not-returned free bets)
  - SR (stake-returned free bets)
- **Partial lay matching**:
  - supports incomplete exchange fills and updates liabilities correctly
- **Settlement with realised PnL**:
  - closes positions into the ledger/state
- **Ledger + bankroll tracking**:
  - tracks available cash, locked funds, liabilities, and realised profit
- **Monte Carlo risk modelling**:
  - simulates final bankroll distribution on the open book
- **Equity / drawdown analytics dashboard**:
  - equity curve, drawdown series, performance breakdowns, and risk snapshots

---

## Risk Model Assumptions (explicit)

These assumptions matter. If you don’t like them, change them — but don’t pretend they don’t exist.

### Fill model
- Each open bet has a **fill fraction** on the exchange leg:  
  \[
  f \sim \text{FillDistribution}(\cdot)
  \]
- Default: treat `f` as fixed at the currently observed match status when available (fully matched = 1, partial = current fraction), otherwise sample `f` from a configured distribution (e.g., Beta or a simple discrete model).

**Interpretation:** liquidity is not guaranteed; some exposure can remain unmatched.

### Slippage model
- The realised lay odds are perturbed from the quoted lay odds:
  \[
  L_{\text{real}} = L_{\text{quote}} + \epsilon
  \]
- Default: \(\epsilon\) is sampled from a small symmetric noise model (or a conservative one-sided model if you want to penalise adverse fills).

**Interpretation:** your execution price is uncertain; worse fills increase liability / reduce edge.

### Void modelling
- Each bet has an independent probability of void:
  \[
  v \sim \text{Bernoulli}(p_{\text{void}})
  \]
- If voided: stake and exchange exposure are unwound according to rules you define (bookmaker void, exchange cancellation, etc.).

**Interpretation:** cancellations happen; modelling it stops you overstating certainty.

### Independence assumptions
- Base model assumes:
  - event outcomes are independent across bets **unless** you explicitly model correlation
  - execution noise (fill/slippage/void) is independent across bets

**Reality check:** independence is false when you stack bets on the same match/market/day or face shared liquidity conditions. If you frequently have clustered exposure, you should implement correlation (see Future Improvements).

### VaR computation method
- Monte Carlo produces a distribution of **final bankroll** \(B_T\).
- Report downside via quantiles (empirical):
  - “Worst 1% outcome” = 1st percentile of \(B_T\)
  - “Downside 1%” = \(\max(0, B_0 - \text{VaR}_{1\%})\)
  - \(P(B_T < B_0)\) as probability of finishing below current bankroll

This is **simulation VaR** (quantile-based), not parametric VaR.

---

