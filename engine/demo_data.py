from __future__ import annotations

import inspect
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from engine.repo import JsonRepo
from engine.execution import apply_lay_match, place_open_bet, settle_open_bet
from engine.offers import price_freebet_snr, price_freebet_sr, price_qualifying


# ============================================================
# Signature-safe caller (pricing fn params can drift)
# ============================================================
def _call_kw_only(fn: Callable[..., Any], **kwargs: Any) -> Any:
    sig = inspect.signature(fn)
    allowed = set(sig.parameters.keys())
    return fn(**{k: v for k, v in kwargs.items() if k in allowed})


# ============================================================
# Repo reset (compat-first)
# ============================================================
def _reset_repo(repo: JsonRepo, *, initial_bankroll: float) -> None:
    if hasattr(repo, "reset_ledger_to_cash"):
        repo.reset_ledger_to_cash(float(initial_bankroll))
    else:
        repo.append_ledger("initial", float(initial_bankroll), reference_id=None, note="Demo reset")
        if hasattr(repo, "set_available_cash"):
            repo.set_available_cash(float(initial_bankroll))

    # clear open bets
    if hasattr(repo, "save_open_bets"):
        repo.save_open_bets([])
    else:
        try:
            for b in repo.load_open_bets():
                repo.remove_open_bet(b.bet_id)
        except Exception:
            pass

    # clear settled
    if hasattr(repo, "save_settled_bets"):
        repo.save_settled_bets([])
    elif hasattr(repo, "save_settled"):
        repo.save_settled([])


# ============================================================
# Realistic sampling
# ============================================================
def _clamped_normal(rng: random.Random, mean: float, sd: float, lo: float, hi: float) -> float:
    x = rng.normalvariate(mean, sd)
    return float(max(lo, min(hi, x)))


def _choose_offer_type(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.60:
        return "qualifying"
    if r < 0.90:
        return "freebet_snr"
    return "freebet_sr"   # 10%

def _generate_session_timeline(
    rng: random.Random,
    *,
    n_events: int,
    history_days: int,
    sessions_per_week: int = 3,
    bets_per_session_range: tuple[int, int] = (2, 6),
) -> list[datetime]:
    """
    Produces clustered activity: a few betting sessions per week,
    each session has multiple bets within ~1-2 hours.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=history_days)

    # how many sessions we need
    weeks = max(1, int(history_days / 7))
    n_sessions = max(1, weeks * sessions_per_week)

    # pick session start dates (days), sorted
    session_days = []
    for _ in range(n_sessions):
        d = start + timedelta(days=rng.uniform(0, float(history_days)))
        d0 = d.replace(hour=0, minute=0, second=0, microsecond=0)
        session_days.append(d0)
    session_days.sort()

    times: list[datetime] = []
    for d0 in session_days:
        # evening bias
        if rng.random() < 0.75:
            start_hour = rng.randint(18, 22)
        else:
            start_hour = rng.randint(10, 16)
        session_start = d0.replace(hour=start_hour, minute=rng.randint(0, 45), second=rng.randint(0, 59))

        k = rng.randint(bets_per_session_range[0], bets_per_session_range[1])
        for _ in range(k):
            # bet within next 10–90 mins, small jitter
            dt = session_start + timedelta(minutes=rng.uniform(0, 90))
            times.append(dt)

        if len(times) >= n_events:
            break

    times = times[:n_events]
    times.sort()

    # Ensure strictly increasing timestamps (avoid vertical spikes)
    for i in range(1, len(times)):
        if times[i] <= times[i - 1]:
            times[i] = times[i - 1] + timedelta(seconds=1)

    return times

# ============================================================
# Candidate generation (realistic stakes + odds constraints)
# ============================================================
def _make_candidate(rng: random.Random, offer_type: str):
    team = f"Team {rng.randint(1, 999)}"
    bookmaker = rng.choice(["Bet365", "SkyBet", "WilliamHill", "PaddyPower"])
    commission = 0.02

    # keep odds sane; outliers look fake and create weird pnl
    if offer_type in ("freebet_snr", "freebet_sr"):
        back_odds = rng.uniform(1.8, 4.0)
    else:
        back_odds = rng.uniform(1.6, 3.2)

    lay_odds = back_odds + rng.uniform(0.02, 0.16)

    if offer_type == "qualifying":
        stake = round(_clamped_normal(rng, 10.0, 2.5, 5.0, 15.0), 2)
        return _call_kw_only(
            price_qualifying,
            team=team,
            bookmaker=bookmaker,
            back_odds=back_odds,
            lay_odds=lay_odds,
            back_stake=stake,
            commission=commission,
        )

    free_stake = round(_clamped_normal(rng, 10.0, 4.0, 5.0, 20.0), 2)

    if offer_type == "freebet_snr":
        return _call_kw_only(
            price_freebet_snr,
            team=team,
            bookmaker=bookmaker,
            back_odds=back_odds,
            lay_odds=lay_odds,
            free_stake=free_stake,
            commission=commission,
        )

    if offer_type == "freebet_sr":
        return _call_kw_only(
            price_freebet_sr,
            team=team,
            bookmaker=bookmaker,
            back_odds=back_odds,
            lay_odds=lay_odds,
            free_stake=free_stake,
            commission=commission,
        )

    raise ValueError(f"Unknown offer_type: {offer_type}")


# ============================================================
# Payout model (simple, consistent)
# ============================================================
def _ideal_bookie_payout(bet, result: str) -> float:
    """
    Cash payout used by settle_open_bet.
    This should be plausible, not perfect.
    """
    c = bet.candidate
    BO = float(c.back_odds)
    S = float(c.back_stake)  # freebets store promo here too

    if result == "void":
        return S if c.offer_type == "qualifying" else 0.0

    if result == "lose":
        return 0.0

    # win
    if c.offer_type == "qualifying":
        return BO * S
    if c.offer_type == "freebet_snr":
        return (BO - 1.0) * S  # stake not returned
    return BO * S  # freebet_sr: stake returned


# ============================================================
# Exchange PnL model (MUST satisfy execution.py sanity check)
# ============================================================
def _exchange_pnl_from_match(bet, result: str) -> float:
    """
    Net exchange PnL implied by a fully matched lay.
    This stays within realistic bounds and passes validation.
    """
    c = bet.candidate
    comm = float(getattr(c, "commission", 0.02))
    lay_stake = float(getattr(bet, "matched_lay_stake", 0.0) or getattr(c, "lay_stake", 0.0))
    lay_liab = float(getattr(c, "lay_liability", 0.0))

    if result == "void":
        return 0.0
    if result == "win":
        return -lay_liab
    return lay_stake * (1.0 - comm)


# ============================================================
# Result model (demo: stable profits, especially for freebets)
# ============================================================
def _sample_result(rng: random.Random, bet) -> str:
    ot = bet.candidate.offer_type

    # small void chance overall
    if rng.random() < 0.02:
        return "void"

    if ot in ("freebet_snr", "freebet_sr"):
        # For a demo, bias freebets toward "lose" to keep curve smooth and positive
        # (exchange pnl is +stake*(1-c), bookie payout=0).
        return "lose" if rng.random() < 0.75 else "win"

    # qualifying: approximate implied win probability
    p_win = min(0.90, max(0.05, 1.0 / float(bet.candidate.back_odds)))
    return "win" if rng.random() < p_win else "lose"


# ============================================================
# Timestamp patching: persisted JSON is the source of truth
# ============================================================
def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _find_settled_path(repo: JsonRepo) -> Path | None:
    for attr in ("settled_bets_path", "settled_path"):
        p = getattr(repo, attr, None)
        if p:
            pp = Path(p)
            if pp.exists():
                return pp

    # fallback guesses in same folder as open_path
    base = Path(repo.open_path).parent
    for name in ("settled_bets.json", "settled.json"):
        pp = base / name
        if pp.exists():
            return pp
    return None


def _intraday_time(rng: random.Random, d0: datetime) -> datetime:
    # Bias to evenings; avoid midnight labels.
    if rng.random() < 0.70:
        hour = rng.randint(18, 23)
    else:
        hour = rng.randint(9, 17)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return d0.replace(hour=hour, minute=minute, second=second, microsecond=0)


def _recompute_running_balance(ledger: list[dict]) -> None:
    bal = 0.0
    for i, e in enumerate(ledger):
        amt = float(e.get("amount", 0.0))
        typ = e.get("type")
        if i == 0 and typ in ("initial", "reset"):
            bal = amt
        else:
            bal += amt
        e["running_balance"] = float(bal)


def _patch_persisted_timestamps(
    repo: JsonRepo,
    rng: random.Random,
    *,
    history_days: int,
    open_recent_days: int,
) -> None:
    open_path = Path(repo.open_path)
    ledger_path = Path(getattr(repo, "ledger_path", "")) if hasattr(repo, "ledger_path") else None
    settled_path = _find_settled_path(repo)

    open_bets = _read_json(open_path)
    settled_bets = _read_json(settled_path) if settled_path else []
    ledger = _read_json(ledger_path) if ledger_path and ledger_path.exists() else []

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=history_days)

    # ---- settled: spread across history window with intraday times
    if settled_bets:
        base_dates = []
        for _ in range(len(settled_bets)):
            day = start + timedelta(days=rng.uniform(0, float(history_days)))
            day0 = day.replace(hour=0, minute=0, second=0, microsecond=0)
            base_dates.append(day0)
        base_dates.sort()
        settled_times = _generate_session_timeline(
            rng,
            n_events=len(settled_bets),
            history_days=history_days,
            sessions_per_week=3,
            bets_per_session_range=(2, 6),
        )

        for sb, t_settle in zip(settled_bets, settled_times):
            if not isinstance(sb, dict):
                continue

            # place time before settlement
            t_place = t_settle - timedelta(hours=rng.uniform(1.0, 48.0))
            iso_place = _iso(t_place)
            iso_set = _iso(t_settle)

            settlement = sb.get("settlement")
            if isinstance(settlement, dict):
                settlement["settled_at"] = iso_set

            bet = sb.get("bet")
            if isinstance(bet, dict):
                cand = bet.get("candidate")
                if isinstance(cand, dict):
                    cand["created_at"] = iso_place

    # ---- open: last N days
    if open_bets:
        start_open = now - timedelta(days=open_recent_days)
        base_dates = []
        for _ in range(len(open_bets)):
            day = start_open + timedelta(days=rng.uniform(0, float(open_recent_days)))
            day0 = day.replace(hour=0, minute=0, second=0, microsecond=0)
            base_dates.append(day0)
        base_dates.sort()
        open_times = _generate_session_timeline(
            rng,
            n_events=len(open_bets),
            history_days=open_recent_days,
            sessions_per_week=4,
            bets_per_session_range=(1, 3),
        )

        for ob, t in zip(open_bets, open_times):
            if isinstance(ob, dict) and isinstance(ob.get("candidate"), dict):
                ob["candidate"]["created_at"] = _iso(t)

    # ---- ledger: spread across history; keep order + recompute running_balance
    if ledger:
        base_dates = []
        for _ in range(len(ledger)):
            day = start + timedelta(days=rng.uniform(0, float(history_days)))
            day0 = day.replace(hour=0, minute=0, second=0, microsecond=0)
            base_dates.append(day0)
        base_dates.sort()
        led_times = _generate_session_timeline(
            rng,
            n_events=len(ledger),
            history_days=history_days,
            sessions_per_week=3,
            bets_per_session_range=(3, 10),
        )

        for e, t in zip(ledger, led_times):
            if isinstance(e, dict):
                e["timestamp"] = _iso(t)

        ledger.sort(key=lambda x: x.get("timestamp", ""))
        _recompute_running_balance(ledger)

    _write_json(open_path, open_bets)
    if settled_path:
        _write_json(settled_path, settled_bets)
    if ledger_path and ledger_path.exists():
        _write_json(ledger_path, ledger)


# ============================================================
# Public entry point
# ============================================================
def generate_demo_state(
    repo: JsonRepo,
    *,
    initial_bankroll: float = 300.0,
    n_settled: int = 80,
    n_open: int = 8,
    seed: int = 42,
    history_days: int = 120,
    open_recent_days: int = 10,
) -> None:
    """
    Engine-valid, realistic demo dataset:
      - exchange pnl respects lay economics (passes validation)
      - freebets mostly profitable and stable
      - realistic stake sizes and offer mix
      - timestamps spread across months with intraday times
      - ledger timestamps rewritten + balances recomputed
    """
    rng = random.Random(seed)
    _reset_repo(repo, initial_bankroll=initial_bankroll)

    # ---- settled bets
    for _ in range(n_settled):
        ot = _choose_offer_type(rng)
        cand = _make_candidate(rng, ot)

        bet = place_open_bet(repo, cand)

        # fully match
        apply_lay_match(
            repo,
            bet.bet_id,
            match_stake=float(bet.candidate.lay_stake),
            matched_odds=float(bet.candidate.lay_odds),
        )

        result = _sample_result(rng, bet)
        payout = float(_ideal_bookie_payout(bet, result))
        exchange_pnl = float(_exchange_pnl_from_match(bet, result))

        settle_open_bet(
            repo,
            bet.bet_id,
            result=result,
            actual_bookie_payout=payout,
            actual_exchange_pnl=exchange_pnl,
        )

    # ---- open bets left open (fully matched)
    for _ in range(n_open):
        ot = _choose_offer_type(rng)
        cand = _make_candidate(rng, ot)
        bet = place_open_bet(repo, cand)
        apply_lay_match(
            repo,
            bet.bet_id,
            match_stake=float(bet.candidate.lay_stake),
            matched_odds=float(bet.candidate.lay_odds),
        )

    # ---- patch persisted timestamps (what Streamlit reads)
    _patch_persisted_timestamps(
        repo,
        rng,
        history_days=history_days,
        open_recent_days=open_recent_days,
    )