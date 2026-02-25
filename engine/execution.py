from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from .models import OpenBet, Settlement, now_iso
from .repo import JsonRepo


def new_bet_id() -> str:
    return uuid4().hex[:10]


def place_open_bet(repo: JsonRepo, candidate) -> OpenBet:

    bet = OpenBet(
        bet_id=new_bet_id(),
        candidate=candidate,
        status="open",
        expected_lay_odds=candidate.lay_odds,
        matched_lay_stake=0.0,
        avg_lay_odds=0.0,
    )

    required = bet.required_capital()
    available = repo.get_available_cash()
    if required > available:
        raise ValueError(f"Insufficient cash: need {required:.2f}, have {available:.2f}")

    # Lock funds (ledger-driven)
    repo.append_ledger("lock", -required, reference_id=bet.bet_id, note="Lock capital for open bet")
    repo.add_open_bet(bet)
    return bet

def refresh_lay_quote(repo: JsonRepo, bet_id: str, *, lay_odds: float, lay_size: float) -> OpenBet:

    bets = repo.load_open_bets()
    for i, b in enumerate(bets):
        if b.bet_id == bet_id:
            # update candidate quote (latest)
            b.candidate.lay_odds = float(lay_odds)
            b.candidate.lay_size = float(lay_size)
            bets[i] = b
            repo.save_open_bets(bets)
            return b
    raise KeyError(f"Open bet not found: {bet_id}")


def apply_lay_match(repo: JsonRepo, bet_id: str, *, match_stake: float, matched_odds: float) -> OpenBet:

    bets = repo.load_open_bets()
    for i, b in enumerate(bets):
        if b.bet_id != bet_id:
            continue

        if b.status == "settled":
            raise ValueError("Bet already settled")

        remaining = b.remaining_lay_stake()
        if remaining <= 0:
            b.status = "fully_matched"
            bets[i] = b
            repo.save_open_bets(bets)
            return b

        m = float(match_stake)
        if m <= 0:
            raise ValueError("match_stake must be > 0")

        # cannot match more than remaining
        m = min(m, remaining)

        # update weighted average odds
        old_m = b.matched_lay_stake
        old_avg = b.avg_lay_odds

        new_m = old_m + m
        if old_m == 0:
            new_avg = float(matched_odds)
        else:
            new_avg = (old_m * old_avg + m * float(matched_odds)) / new_m

        b.matched_lay_stake = new_m
        b.avg_lay_odds = new_avg

        # status
        target = float(b.candidate.lay_stake)
        matched = float(b.matched_lay_stake)

        if matched >= target - 1e-6:
            b.matched_lay_stake = target  # snap to target
            b.status = "fully_matched"
        else:
            b.status = "partially_matched"

        bets[i] = b
        repo.save_open_bets(bets)

        # ledger note only (no cash movement — liability is “potential”, not paid up front)
        repo.append_ledger("fee", 0.0, reference_id=bet_id, note=f"Lay matched {m:.2f} @ {matched_odds:.2f} (avg {b.avg_lay_odds:.3f})")

        return b

    raise KeyError(f"Open bet not found: {bet_id}")

def expected_exchange_pnl_from_matches(bet: OpenBet, result: str) -> float:

    m = float(bet.matched_lay_stake)
    if m <= 0:
        return 0.0

    avg = float(bet.avg_lay_odds) if bet.avg_lay_odds > 0 else float(bet.expected_lay_odds)
    c = float(bet.candidate.commission)

    if result == "win":
        # you lose on the exchange: liability on matched part
        return -m * (avg - 1)
    elif result == "lose":
        # you win on the exchange (less commission)
        return m * (1 - c)
    elif result == "void":
        return 0.0
    else:
        raise ValueError("result must be win/lose/void")

def settle_open_bet(

    repo: JsonRepo,
    bet_id: str,
    *,
    result: str,
    actual_bookie_payout: float,
    actual_exchange_pnl: float,
) -> Settlement:

    bet = repo.remove_open_bet(bet_id)
    if bet.status != "fully_matched":
        raise ValueError(f"Cannot settle: bet is {bet.status}. Match lay fully first.")
    locked = bet.required_capital()

    # --- Minimal sanity checks to prevent corrupt settlement ---
    if result not in {"win", "lose", "void"}:
        raise ValueError("result must be 'win', 'lose', or 'void'")

    abp = float(actual_bookie_payout)
    aep = float(actual_exchange_pnl)

    if abp < 0:
        raise ValueError(f"actual_bookie_payout must be >= 0, got {abp}")

    # Loose bound to catch passing gross exchange returns or wrong sign.
    ll = float(bet.candidate.lay_liability)
    ls = float(bet.candidate.lay_stake)
    bound = max(5.0, ll + ls)  # loose to avoid false positives on small bets
    if abs(aep) > bound * 1.2:
        raise ValueError(
            f"actual_exchange_pnl looks unrealistic (must be signed NET PnL). "
            f"pnl={aep}, lay_liability={ll}, lay_stake={ls}"
        )

    # Only qualifying bets pay a real back stake from your bankroll
    stake_cost = bet.candidate.back_stake if bet.candidate.offer_type == "qualifying" else 0.0

    realised_profit = float(actual_bookie_payout) + float(actual_exchange_pnl) - float(stake_cost)
    settled_at = now_iso()

    settlement = Settlement(
        bet_id=bet_id,
        result=result,  # "win"/"lose"/"void"
        actual_bookie_payout=float(actual_bookie_payout),
        actual_exchange_pnl=float(actual_exchange_pnl),
        realised_profit=float(realised_profit),
        settled_at=settled_at,
    )

    # Unlock locked capital
    repo.append_ledger("unlock", +locked, reference_id=bet_id, note="Unlock capital after settlement")
    # Record realised profit separately (clean audit trail)
    repo.append_ledger("profit", +realised_profit, reference_id=bet_id, note=f"Result={result}")

    # Persist settlement + bet snapshot
    repo.append_settlement(settlement, bet)
    return settlement