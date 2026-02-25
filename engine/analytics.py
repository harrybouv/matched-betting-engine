from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict

from engine.repo import JsonRepo
from engine.monte_carlo import run_monte_carlo

def state_summary(repo: JsonRepo) -> Dict[str, Any]:
    cash = repo.get_available_cash()
    open_bets = repo.load_open_bets()

    locked_total = 0.0
    gp_open_total = 0.0
    liability_total = 0.0
    locked_by_type = defaultdict(float)

    for b in open_bets:
        locked = b.required_capital()
        locked_total += locked
        ot = b.candidate.offer_type
        locked_by_type[ot] += locked

        gp_open_total += float(b.candidate.guaranteed_profit)
        liability_total += float(b.candidate.lay_liability)

    perf = performance_summary(repo)
    realised_profit_total = float(perf["realised_profit_total"])  # already rounded
    initial_bankroll = 0.0

    if hasattr(repo, "load_ledger"):
        ledger = repo.load_ledger()
        initial_entries = [e for e in ledger if getattr(e, "type", None) == "initial"]
        if initial_entries:
            initial_entries.sort(key=lambda e: getattr(e, "timestamp", ""))
            initial_bankroll = float(getattr(initial_entries[0], "amount", 0.0))

    equity = float(cash) + float(locked_total)
    equity_expected = float(initial_bankroll) + float(realised_profit_total)
    recon_error = equity - equity_expected
    is_reconciled = abs(recon_error) <= 1e-6
    # --- end additions ---

    return {
        "available_cash": round(cash, 2),
        "n_open_bets": len(open_bets),
        "locked_total": round(locked_total, 2),
        "locked_by_offer_type": {k: round(v, 2) for k, v in locked_by_type.items()},
        "gp_open_total": round(gp_open_total, 2),
        "liability_total": round(liability_total, 2),

        "initial_bankroll": round(initial_bankroll, 2),
        "realised_profit_total": round(realised_profit_total, 2),
        "equity": round(equity, 2),
        "equity_expected": round(equity_expected, 2),
        "recon_error": round(recon_error, 6),
        "is_reconciled": is_reconciled,
    }
def performance_summary(repo: JsonRepo) -> Dict[str, Any]:
    settled = repo.load_settled()

    n = 0
    realised_total = 0.0
    by_offer = defaultdict(float)
    by_result = defaultdict(int)

    for row in settled:
        s = row["settlement"]
        b = row["bet"]
        cand = b["candidate"]

        profit = float(s["realised_profit"])
        result = s["result"]
        offer_type = cand["offer_type"]

        realised_total += profit
        by_offer[offer_type] += profit
        by_result[result] += 1
        n += 1

    avg = realised_total / n if n > 0 else 0.0

    return {
        "n_settled": n,
        "realised_profit_total": round(realised_total, 2),
        "avg_profit_per_bet": round(avg, 2),
        "profit_by_offer_type": {k: round(v, 2) for k, v in by_offer.items()},
        "count_by_result": dict(by_result),
    }

def risk_snapshot(
        repo: JsonRepo,
        *,
        n: int = 5000,
        fill_min: float = 0.7,
        fill_max: float = 1.0,
        slippage_std: float = 0.05,
        void_prob: float = 0.02,
) -> Dict[str, Any]:
    open_bets = repo.load_open_bets()
    bankroll = float(repo.get_available_cash())

    if not open_bets:
        return {"error": "No open bets available"}

    res = run_monte_carlo(
        bankroll=bankroll,
        open_bets=open_bets,
        n=n,
        fill_min=fill_min,
        fill_max=fill_max,
        slippage_std=slippage_std,
        void_prob=void_prob,
    )

    worst_1pct = float(res["worst_1pct"])
    res["downside_1pct"] = round(bankroll - worst_1pct, 2)

    return {
        "n_sims": n,
        "mean": round(float(res["mean"]), 2),
        "worst_1pct": round(float(res["worst_1pct"]), 2),
        "p_down": round(100 * float(res["p_down"]), 1),  # %
        "downside_1pct": float(res["downside_1pct"]),
    }


