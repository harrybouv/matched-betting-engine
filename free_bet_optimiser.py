# free_bet_optimiser.py
# Robust, alignment-safe optimiser for free-bet conversions.

from __future__ import annotations
import csv
import os
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import match_calc  # uses your calc_free(BO, BS, LO, E) returning a dict

# ---------- CONFIG ----------
CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CSV Files")

BOOKIE_FILE   = os.path.join(CSV_DIR, "skybet_scraper.csv")
SMARKETS_FILE = os.path.join(CSV_DIR, "smarkets_exchange_scraper.csv")
BETFAIR_FILE  = os.path.join(CSV_DIR, "betfair_exchange_scraper.csv")

EXCHANGE_COMMISSION = {
    "Smarkets": 2.0,   # %
    "Betfair":  5.0,   # %
}

FREE_BET_STAKE = 10.0
MIN_EXTRACTION_PCT = 0.0
TOP_N = 10

OUT_RANKED   = os.path.join(CSV_DIR, "ranked_free_bets.csv")
OUT_SUSPECTS = os.path.join(CSV_DIR, "suspect_pairs.csv")
# ----------------------------


# ========== UTILITIES ==========
def must_exist(path: str) -> str:
    if not os.path.exists(path):
        all_csvs = [os.path.join(CSV_DIR, f) for f in os.listdir(CSV_DIR) if f.lower().endswith(".csv")]
        msg = ["Could not find:", path,
               f"Working dir: {os.getcwd()}",
               f"Expected in: {CSV_DIR}",
               "Available CSVs:"]
        for p in all_csvs:
            msg.append("  - " + p)
        raise FileNotFoundError("\n".join(msg))
    return path


def read_csv(path: str) -> List[Dict[str, str]]:
    rows = []
    with open(must_exist(path), newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()})
    return rows


def norm_team(s: str) -> str:
    # Lowercase, collapse spaces, strip punctuation-ish separators
    import re
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = " ".join(s.split())
    return s


def to_float_safe(v: str) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None
# ===============================


# ========== DATA MODELS ==========
@dataclass
class BookieRow:
    home: str
    away: str
    sel: str  # "Home" | "Draw" | "Away"
    BO: float


@dataclass
class ExchangeRow:
    home: str
    away: str
    sel: str  # "Home" | "Draw" | "Away"
    LO: float
    exch: str
    E: float  # commission %
# =================================


# ========== LOAD & LONGIFY ==========
def longify_bookie(rows: List[Dict[str, str]]) -> List[BookieRow]:
    out: List[BookieRow] = []
    for r in rows:
        h, a = r.get("Home Team"), r.get("Away Team")
        hb = to_float_safe(r.get("Home Back Odds", ""))
        db = to_float_safe(r.get("Draw Back Odds", ""))
        ab = to_float_safe(r.get("Away Back Odds", ""))

        if not (h and a):
            continue

        if hb is not None:
            out.append(BookieRow(h, a, "Home", hb))
        if db is not None:
            out.append(BookieRow(h, a, "Draw", db))
        if ab is not None:
            out.append(BookieRow(h, a, "Away", ab))
    return out


def longify_exchange(rows: List[Dict[str, str]], exchange_name: str) -> List[ExchangeRow]:
    out: List[ExchangeRow] = []
    E = EXCHANGE_COMMISSION.get(exchange_name, 0.0)
    for r in rows:
        h, a = r.get("Home Team"), r.get("Away Team")
        hL = to_float_safe(r.get("Home Lay Odds", ""))
        dL = to_float_safe(r.get("Draw Lay Odds", ""))
        aL = to_float_safe(r.get("Away Lay Odds", ""))

        if not (h and a):
            continue

        if hL is not None:
            out.append(ExchangeRow(h, a, "Home", hL, exchange_name, E))
        if dL is not None:
            out.append(ExchangeRow(h, a, "Draw", dL, exchange_name, E))
        if aL is not None:
            out.append(ExchangeRow(h, a, "Away", aL, exchange_name, E))
    return out
# ====================================


# ========== MATCHING & MERGE ==========
def key_tuple(home: str, away: str) -> Tuple[str, str]:
    return (norm_team(home), norm_team(away))


def flip_selection(sel: str) -> str:
    if sel == "Home":
        return "Away"
    if sel == "Away":
        return "Home"
    return "Draw"


def index_exchange_by_key(ex_rows: List[ExchangeRow]) -> Dict[Tuple[str, str], List[ExchangeRow]]:
    idx: Dict[Tuple[str, str], List[ExchangeRow]] = {}
    for r in ex_rows:
        k = key_tuple(r.home, r.away)
        idx.setdefault(k, []).append(r)
    return idx


def best_lay_per_market(ex_rows: List[ExchangeRow]) -> Dict[Tuple[str, str, str], ExchangeRow]:
    """
    Returns the *best* (lowest LO) row for each (home, away, selection), keyed by normalized names.
    """
    best: Dict[Tuple[str, str, str], ExchangeRow] = {}
    for r in ex_rows:
        k = (*key_tuple(r.home, r.away), r.sel)
        cur = best.get(k)
        if (cur is None) or (r.LO < cur.LO):
            best[k] = r
    return best


def join_bookie_with_exchanges(bo_rows: List[BookieRow],
                               best_ex: Dict[Tuple[str, str, str], ExchangeRow]) -> List[Dict]:
    """
    Robust join that handles potential home/away flips between files:
    1) Try exact key (home, away)
    2) If not found, try flipped (away, home) and flip the selection mapping accordingly
    """
    out: List[Dict] = []
    for b in bo_rows:
        k_exact = (*key_tuple(b.home, b.away), b.sel)
        ex = best_ex.get(k_exact)
        if ex is not None:
            out.append({
                "match": f"{b.home} vs {b.away}",
                "selection": b.sel,
                "BO": b.BO,
                "LO": ex.LO,
                "exchange": ex.exch,
                "E": ex.E,
            })
            continue

        # Try flipped
        k_flip = (*key_tuple(b.away, b.home), flip_selection(b.sel))
        ex2 = best_ex.get(k_flip)
        if ex2 is not None:
            out.append({
                "match": f"{b.home} vs {b.away}",
                "selection": b.sel,
                "BO": b.BO,
                "LO": ex2.LO,
                "exchange": ex2.exch,
                "E": ex2.E,
            })
            continue

        # If neither found, skip (no matching exchange market)
    return out
# =====================================


# ========== SANITY / PLAUSIBILITY ==========
def is_plausible_pair(BO: float, LO: float) -> bool:
    """
    Heuristic: in the same market at the same moment, back vs lay for the *same* selection
    should be reasonably close. We flag pairs where they differ massively.

    We accept LO in [BO / 1.6, BO * 1.6] roughly. (Tunable.)
    """
    if BO <= 1.01 or LO <= 1.01:
        # odds this low are rarely valid for full-time 1X2 (except heavy favorites),
        # but still allow heavy favs—just don't outright reject here.
        pass
    ratio = LO / BO if BO > 0 else float("inf")
    return 0.625 <= ratio <= 1.6


def split_plausible(joined: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    good, bad = [], []
    for r in joined:
        (good if is_plausible_pair(r["BO"], r["LO"]) else bad).append(r)
    return good, bad
# ==========================================


# ========== EVALUATE & OUTPUT ==========
def evaluate(rows: List[Dict], free_bet_stake: float) -> List[Dict]:
    out = []
    for r in rows:
        calc = match_calc.calc_free(
            BO=float(r["BO"]),
            BS=float(free_bet_stake),
            LO=float(r["LO"]),
            E=float(r["E"])
        )
        out.append({
            **r,
            "lay_stake": float(calc["lay_stake"]),
            "liability": float(calc["liability"]),
            "guaranteed_profit": float(calc["guaranteed_profit"]),
            "extraction_%": float(calc["extraction_rate"]) * 100.0
        })
    return out


def write_csv(path: str, rows: List[Dict], fieldnames: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    # 1) Load CSVs
    bookie_raw   = read_csv(BOOKIE_FILE)
    smarkets_raw = read_csv(SMARKETS_FILE)
    betfair_raw  = read_csv(BETFAIR_FILE)

    # 2) Longify
    bo_long = longify_bookie(bookie_raw)
    ex_long = longify_exchange(smarkets_raw, "Smarkets") + \
              longify_exchange(betfair_raw,  "Betfair")

    # 3) Best lay per (home, away, selection)
    best_by_market = best_lay_per_market(ex_long)

    # 4) Join bookie with exchanges (auto-detect swapped home/away)
    joined = join_bookie_with_exchanges(bo_long, best_by_market)

    # 5) Split plausible vs suspect (to *surface* alignment problems)
    plausible, suspects = split_plausible(joined)

    # 6) Evaluate
    evaluated = evaluate(plausible, FREE_BET_STAKE)

    # 7) Rank & trim
    evaluated = [r for r in evaluated if r["extraction_%"] >= MIN_EXTRACTION_PCT]
    evaluated.sort(key=lambda r: r["extraction_%"], reverse=True)
    top = evaluated[:TOP_N]

    # 8) Output ranked + suspects
    ranked_fields = [
        "match", "selection", "exchange",
        "BO", "LO", "E",
        "lay_stake", "liability", "guaranteed_profit", "extraction_%"
    ]
    write_csv(OUT_RANKED, top, ranked_fields)

    if suspects:
        write_csv(OUT_SUSPECTS, suspects, ["match", "selection", "BO", "LO", "exchange", "E"])

    # 9) Console summary
    print(f"Loaded: bookie={len(bookie_raw)} rows, exchanges={len(smarkets_raw)+len(betfair_raw)} rows")
    print(f"Bookie markets (long): {len(bo_long)}   Exchange markets (long): {len(ex_long)}")
    print(f"Joined (all): {len(joined)}   Plausible: {len(plausible)}   Suspect: {len(suspects)}")
    if suspects:
        print(f"⚠ Wrote {len(suspects)} suspect pairs to: {OUT_SUSPECTS}")
    print(f"✅ Wrote ranked top {len(top)} to: {OUT_RANKED}")

    # Optional: pretty print top table
    if top:
        header = (
            f"{'Match':<34} {'Sel':<6} {'Exch':<9} "
            f"{'Extract%':>9} {'£Profit':>8} {'Lay':>8} {'Liab':>8} "
            f"{'BO':>6} {'LO':>6}"
        )
        print("\n=== TOP FREE BET CONVERSIONS ===\n")
        print(header)
        print("-" * len(header))
        for r in top:
            print(
                f"{r['match']:<34.34} {r['selection']:<6} {r['exchange']:<9} "
                f"{r['extraction_%']:>8.1f}% {r['guaranteed_profit']:>8.2f} "
                f"{r['lay_stake']:>8.2f} {r['liability']:>8.2f} "
                f"{float(r['BO']):>6.2f} {float(r['LO']):>6.2f}"
            )
    else:
        print("No opportunities met the threshold.")


if __name__ == "__main__":
    main()
