import random
import statistics


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def implied_win_prob(back_odds):
    # crude: implied probability from decimal odds
    if back_odds <= 1:
        return 0.5
    return clamp(1.0 / back_odds, 0.01, 0.99)


def sample_fill_pct(fill_min, fill_max):
    return random.uniform(fill_min, fill_max)


def sample_lay_odds(expected_lay_odds, slippage_std):
    x = expected_lay_odds + random.gauss(0, slippage_std)
    return max(1.01, x)


def simulate_bet_profit(cand, *, fill_min, fill_max, slippage_std, void_prob):
    # Void?
    if random.random() < void_prob:
        return 0.0

    # Fill + slippage
    fill_pct = sample_fill_pct(fill_min, fill_max)
    matched_lay_stake = cand.lay_stake * fill_pct
    lay_odds = sample_lay_odds(cand.lay_odds, slippage_std)

    # Outcome
    p_win = implied_win_prob(cand.back_odds)
    win = random.random() < p_win

    # Exchange P/L from matched part only
    if win:
        exchange_pnl = -matched_lay_stake * (lay_odds - 1)
    else:
        exchange_pnl = matched_lay_stake * (1 - cand.commission)

    # Bookie payout depends on offer type
    if cand.offer_type == "qualifying":
        if win:
            bookie_payout = cand.back_odds * cand.back_stake
        else:
            bookie_payout = 0.0
        profit = (bookie_payout - cand.back_stake) + exchange_pnl

    elif cand.offer_type == "freebet_snr":
        # stake not returned; store promo amount in back_stake
        FS = cand.back_stake
        if win:
            bookie_profit = (cand.back_odds - 1) * FS
        else:
            bookie_profit = 0.0
        profit = bookie_profit + exchange_pnl

    elif cand.offer_type == "freebet_sr":
        # stake returned on win; store promo amount in back_stake
        FS = cand.back_stake
        if win:
            bookie_profit = cand.back_odds * FS
        else:
            bookie_profit = 0.0
        profit = bookie_profit + exchange_pnl

    else:
        # unknown type: treat as qualifying
        if win:
            bookie_payout = cand.back_odds * cand.back_stake
        else:
            bookie_payout = 0.0
        profit = (bookie_payout - cand.back_stake) + exchange_pnl

    return profit


def run_monte_carlo(
    *,
    bankroll,
    open_bets,
    n=2000,
    fill_min=0.8,
    fill_max=1.0,
    slippage_std=0.02,
    void_prob=0.01,
):
    results = []

    for _ in range(n):
        cash = float(bankroll)

        for bet in open_bets:
            cand = bet.candidate
            cash += simulate_bet_profit(
                cand,
                fill_min=fill_min,
                fill_max=fill_max,
                slippage_std=slippage_std,
                void_prob=void_prob,
            )

        results.append(cash)

    results_sorted = sorted(results)
    mean = statistics.mean(results)
    worst_1pct = results_sorted[int(0.01 * n)]
    p_down = sum(1 for x in results if x < bankroll) / n

    return {
        "mean": mean,
        "worst_1pct": worst_1pct,
        "p_down": p_down,
        "results": results,
    }