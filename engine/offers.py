from __future__ import annotations

from .models import Candidate


def price_qualifying(
    *,
    team: str,
    bookmaker: str,
    back_odds: float,
    lay_odds: float,
    back_stake: float,
    commission: float,
    lay_size: float = 0.0,
) -> Candidate:

    lay_stake = (back_stake * back_odds) / (lay_odds - commission)
    lay_liability = lay_stake * (lay_odds - 1)

    # Profit if bookie wins:
    bookie_profit = (back_odds * back_stake) - back_stake - lay_liability
    # Profit if bookie loses (exchange wins less commission):
    lay_profit = lay_stake * (1 - commission) - back_stake

    guaranteed_profit = min(bookie_profit, lay_profit)
    roi = guaranteed_profit / back_stake if back_stake else 0.0

    return Candidate(
        team=team,
        bookmaker=bookmaker,
        offer_type="qualifying",
        back_odds=float(back_odds),
        back_stake=float(back_stake),
        commission=float(commission),
        lay_odds=float(lay_odds),
        lay_size=float(lay_size),
        lay_stake=float(lay_stake),
        lay_liability=float(lay_liability),
        guaranteed_profit=float(guaranteed_profit),
        roi=float(roi),
    )

def price_freebet_snr(
    *,
    team: str,
    bookmaker: str,
    back_odds: float,
    lay_odds: float,
    free_stake: float,
    commission: float,
    lay_size: float = 0.0,
) -> Candidate:


    BO = float(back_odds)
    LO = float(lay_odds)
    FS = float(free_stake)
    c = float(commission)

    # Lay stake: hedge the "winnings only" part
    LS = (FS * (BO - 1)) / (LO - c)
    LL = LS * (LO - 1)

    # Profit if bookie wins: winnings - lay loss
    win_profit = (BO - 1) * FS - LL

    # Profit if bookie loses: you just win on exchange
    lose_profit = LS * (1 - c)

    GP = min(win_profit, lose_profit)
    R = GP / FS if FS else 0.0

    return Candidate(
        team=team,
        bookmaker=bookmaker,
        offer_type="freebet_snr",
        back_odds=BO,
        back_stake=FS,
        commission=c,
        lay_odds=LO,
        lay_size=float(lay_size),
        lay_stake=float(LS),
        lay_liability=float(LL),
        guaranteed_profit=float(GP),
        roi=float(R),
    )


def price_freebet_sr(
    *,
    team: str,
    bookmaker: str,
    back_odds: float,
    lay_odds: float,
    free_stake: float,
    commission: float,
    lay_size: float = 0.0,
) -> Candidate:


    BO = float(back_odds)
    LO = float(lay_odds)
    FS = float(free_stake)
    c = float(commission)

    # Lay stake: hedge the full return (stake + winnings)
    LS = (FS * BO) / (LO - c)
    LL = LS * (LO - 1)

    # Profit if bookie wins: full return - lay loss
    win_profit = BO * FS - LL

    # Profit if bookie loses: exchange win (no back stake lost)
    lose_profit = LS * (1 - c)

    GP = min(win_profit, lose_profit)
    R = GP / FS if FS else 0.0

    return Candidate(
        team=team,
        bookmaker=bookmaker,
        offer_type="freebet_sr",
        back_odds=BO,
        back_stake=FS,          # store promo amount here for now
        commission=c,
        lay_odds=LO,
        lay_size=float(lay_size),
        lay_stake=float(LS),
        lay_liability=float(LL),
        guaranteed_profit=float(GP),
        roi=float(R),
    )