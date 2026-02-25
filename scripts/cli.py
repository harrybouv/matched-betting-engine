from __future__ import annotations

from engine.repo import JsonRepo
from engine.offers import price_qualifying, price_freebet_snr, price_freebet_sr
from engine.execution import place_open_bet, settle_open_bet
from engine.execution import expected_exchange_pnl_from_matches
from engine.monte_carlo import run_monte_carlo
from engine.execution import apply_lay_match
from engine.analytics import state_summary, performance_summary, risk_snapshot

def set_bankroll(repo: JsonRepo) -> None:
    x = float(input("Set available cash to: "))
    repo.reset_ledger_to_cash(x)
    print(f"Available cash = {repo.get_available_cash():.2f}")


def place(repo: JsonRepo) -> None:
    bet_type = input("Type (qualifying / freebet_snr / freebet_sr): ").strip().lower()
    if bet_type not in ("qualifying", "freebet_snr", "freebet_sr"):
        print("Invalid type.")
        return

    team = input("Team: ").strip().lower()
    bookmaker = input("Bookmaker: ").strip()
    bo = float(input("Back odds: "))
    lo = float(input("Lay odds: "))

    amount = float(input("Stake / Free stake: "))

    c = float(input("Commission (e.g. 0.02 or 2): "))
    if c >= 1:
        c = c / 100.0

    if bet_type == "qualifying":
        cand = price_qualifying(
            team=team,
            bookmaker=bookmaker,
            back_odds=bo,
            lay_odds=lo,
            back_stake=amount,
            commission=c,
        )
    elif bet_type == "freebet_snr":
        cand = price_freebet_snr(
            team=team,
            bookmaker=bookmaker,
            back_odds=bo,
            lay_odds=lo,
            free_stake=amount,
            commission=c,
        )
    else:  # freebet_sr
        cand = price_freebet_sr(
            team=team,
            bookmaker=bookmaker,
            back_odds=bo,
            lay_odds=lo,
            free_stake=amount,
            commission=c,
        )

    print("\nCandidate priced:")
    print(f"Lay stake: {cand.lay_stake:.2f}")
    print(f"Liability: {cand.lay_liability:.2f}")
    print(f"GP:        {cand.guaranteed_profit:.2f}")
    print(f"ROI:       {cand.roi:.4f}")

    ok = input("Place bet? (y/n): ").strip().lower()
    if ok != "y":
        return

    bet = place_open_bet(repo, cand)
    print(f"PLACED bet_id={bet.bet_id} locked={bet.required_capital():.2f}")
    print(f"Available cash now: {repo.get_available_cash():.2f}")


def list_open(repo: JsonRepo) -> None:
    bets = repo.load_open_bets()
    if not bets:
        print("No open bets.")
        return
    for b in bets:
        print(f"- id={b.bet_id} team={b.candidate.team} locked={b.required_capital():.2f} GP={b.candidate.guaranteed_profit:.2f}")


def settle(repo: JsonRepo) -> None:
    list_open(repo)
    bet_id = input("Enter bet_id to settle: ").strip()
    result = input("Result (win/lose/void): ").strip().lower()
    if result not in ("win", "lose", "void"):
        print("Invalid result.")
        return

    # Defaults (expected) for qualifying bets
    open_bets = repo.load_open_bets()
    bet = next((b for b in open_bets if b.bet_id == bet_id), None)
    if bet is None:
        print("bet_id not found.")
        return
    if result == "win":
        expected_bookie = bet.candidate.back_odds * bet.candidate.back_stake
    elif result == "lose":
        expected_bookie = 0.0
    else:
        expected_bookie = bet.candidate.back_stake  # void -> stake back

    expected_exch = expected_exchange_pnl_from_matches(bet, result)

    if result == "win":
        expected_bookie = bet.candidate.back_odds * bet.candidate.back_stake
        expected_exch = -bet.candidate.lay_liability
    elif result == "lose":
        expected_bookie = 0.0
        expected_exch = bet.candidate.lay_stake * (1 - bet.candidate.commission)
    else:  # void (rough v1 default)
        expected_bookie = bet.candidate.back_stake
        expected_exch = 0.0

    bi = input(f"Actual bookie payout (Enter={expected_bookie:.2f}): ").strip()
    ei = input(f"Actual exchange P/L (Enter={expected_exch:.2f}): ").strip()
    bookie = expected_bookie if bi == "" else float(bi)
    exch = expected_exch if ei == "" else float(ei)

    s = settle_open_bet(repo, bet_id, result=result, actual_bookie_payout=bookie, actual_exchange_pnl=exch)
    print(f"SETTLED id={bet_id} profit={s.realised_profit:.2f}")
    print(f"Available cash now: {repo.get_available_cash():.2f}")


def monte(repo: JsonRepo) -> None:
    open_bets = repo.load_open_bets()
    if not open_bets:
        print("No open bets.")
        return

    bankroll = repo.get_available_cash()

    try:
        n = int(input("Simulations (e.g. 5000): ").strip())
    except ValueError:
        n = 5000

    result = run_monte_carlo(
        bankroll=bankroll,
        open_bets=open_bets,
        n=n,
        fill_min=0.7,
        fill_max=1.0,
        slippage_std=0.05,
        void_prob=0.02,
    )

    print(f"\nOpen bets:           {len(open_bets)}")
    print(f"Current bankroll:    {bankroll:.2f}")
    print(f"Mean final bankroll: {result['mean']:.2f}")
    print(f"Worst 1% outcome:    {result['worst_1pct']:.2f}")
    print(f"P(final < now):      {100*result['p_down']:.1f}%")

def match_lay(repo: JsonRepo) -> None:
    list_open(repo)
    bet_id = input("Enter bet_id: ").strip()

    open_bets = repo.load_open_bets()
    bet = next((b for b in open_bets if b.bet_id == bet_id), None)
    if bet is None:
        print("bet_id not found.")
        return

    remaining = float(bet.candidate.lay_stake) - float(bet.matched_lay_stake)
    remaining = max(0.0, remaining)
    print(f"Remaining lay stake: {remaining:.2f} (target {bet.candidate.lay_stake:.2f})")

    ms_in = input(f"Match stake (Enter={remaining:.2f}): ").strip()
    ms = remaining if ms_in == "" else float(ms_in)
    mo_in = input(f"Match odds (Enter={bet.candidate.lay_odds:.2f}): ").strip()
    mo = float(bet.candidate.lay_odds) if mo_in == "" else float(mo_in)

    b2 = apply_lay_match(repo, bet_id, match_stake=ms, matched_odds=mo)
    print(f"UPDATED status={b2.status} matched={b2.matched_lay_stake:.2f}/{b2.candidate.lay_stake:.2f} avg_odds={b2.avg_lay_odds:.3f}")

def main():
    repo = JsonRepo("data")

    while True:
        print("\n1) Set bankroll")
        print("2) Place qualifying bet")
        print("3) List open bets")
        print("4) Settle bet")
        print("5) Exit")
        print("6) Monte Carlo")
        print("7) Match Lay")
        print("8) Summary")
        choice = input("Choose: ").strip()

        if choice == "1":
            set_bankroll(repo)
        elif choice == "2":
            place(repo)
        elif choice == "3":
            list_open(repo)
        elif choice == "4":
            settle(repo)
        elif choice == "5":
            break
        elif choice == "6":
            monte(repo)
        elif choice == "7":
            match_lay(repo)
        elif choice == "8":
            print("\nSTATE")
            print(state_summary(repo))
            print("\nPERFORMANCE")
            print(performance_summary(repo))
            print("\nRISK (open bets)")
            print(risk_snapshot(repo, n=5000))


if __name__ == "__main__":
    main()