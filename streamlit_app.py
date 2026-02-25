import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from pathlib import Path

from engine.repo import JsonRepo
from engine.analytics import state_summary, performance_summary, risk_snapshot
from engine.offers import price_qualifying, price_freebet_snr, price_freebet_sr
from engine.execution import (
    place_open_bet,
    apply_lay_match,
    settle_open_bet,
    expected_exchange_pnl_from_matches,
)
from engine.demo_data import generate_demo_state

# Optional histogram (engine function, not reimplementation)
try:
    from engine.monte_carlo import run_monte_carlo
    HAS_MC = True
except Exception:
    HAS_MC = False


# ============================
# Page config
# ============================
st.set_page_config(
    page_title="Matched Betting Risk Engine (v1)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

alt.data_transformers.disable_max_rows()


# ============================
# Helpers
# ============================
def money(x) -> str:
    try:
        return f"£{float(x):,.2f}"
    except Exception:
        return "—"


def pct(x) -> str:
    try:
        return f"{100.0 * float(x):.1f}%"
    except Exception:
        return "—"


def norm_commission(x: float) -> float:
    x = float(x)
    return x / 100.0 if x >= 1.0 else x


def default_bookie_payout(bet, result: str) -> float:
    """
    Default payout model used to prefill settlement inputs.
    (Keeps existing behaviour.)
    """
    c = bet.candidate
    bo = float(c.back_odds)
    bs = float(c.back_stake)

    if c.offer_type == "qualifying":
        if result == "win":
            return bo * bs
        if result == "lose":
            return 0.0
        return bs  # void => stake returned

    if c.offer_type == "freebet_snr":
        if result == "win":
            return (bo - 1) * bs
        if result == "lose":
            return 0.0
        return 0.0

    # freebet_sr
    if result == "win":
        return bo * bs
    if result == "lose":
        return 0.0
    return 0.0


def build_open_df(open_bets) -> pd.DataFrame:
    rows = []
    for b in open_bets:
        c = b.candidate
        rows.append(
            dict(
                bet_id=b.bet_id,
                status=b.status,
                offer_type=c.offer_type,
                team=c.team,
                bookmaker=c.bookmaker,
                back_odds=float(c.back_odds),
                lay_odds=float(c.lay_odds),
                stake=float(c.back_stake),
                lay_stake_target=float(c.lay_stake),
                matched_lay_stake=float(b.matched_lay_stake),
                remaining_lay=float(b.remaining_lay_stake()),
                avg_lay_odds=float(b.avg_lay_odds),
                lay_liability=float(c.lay_liability),
                gp=float(c.guaranteed_profit),
                required_capital=float(b.required_capital()),
            )
        )
    return pd.DataFrame(rows)


def build_settled_df(repo: JsonRepo) -> pd.DataFrame:
    """
    Must match analytics.py storage expectations:
      settled = repo.load_settled()
      each row: {"settlement": {...}, "bet": {...}}
    """
    raw = repo.load_settled() or []
    rows = []

    for row in raw:
        # Defensive: row could be dict-like, but analytics.py assumes dict access.
        if not isinstance(row, dict):
            row = getattr(row, "__dict__", {}) or {}

        s = row.get("settlement", {}) or {}
        b = row.get("bet", {}) or {}
        cand = (b.get("candidate", {}) or {})

        rows.append(
            dict(
                settled_at=s.get("settled_at"),
                bet_id=s.get("bet_id"),
                result=s.get("result"),
                realised_profit=float(s.get("realised_profit", 0.0) or 0.0),
                bookie_payout=float(s.get("actual_bookie_payout", 0.0) or 0.0),
                exchange_pnl=float(s.get("actual_exchange_pnl", 0.0) or 0.0),
                offer_type=cand.get("offer_type"),
                team=cand.get("team"),
                bookmaker=cand.get("bookmaker"),
            )
        )

    df = pd.DataFrame(rows)

    # Guarantee columns always exist (prevents KeyError no matter what)
    for col in [
        "settled_at", "bet_id", "result", "realised_profit",
        "bookie_payout", "exchange_pnl", "offer_type", "team", "bookmaker"
    ]:
        if col not in df.columns:
            df[col] = np.nan

    return df


# ============================
# Repo + state
# ============================
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent  # MatchedBetting2/
DATA_DIR = PROJECT_ROOT / "data"

repo = JsonRepo(str(DATA_DIR))

# session state
if "candidate" not in st.session_state:
    st.session_state["candidate"] = None
if "risk_snap" not in st.session_state:
    st.session_state["risk_snap"] = None
if "risk_results" not in st.session_state:
    st.session_state["risk_results"] = None

# recompute summaries each run (simple + correct)
state = state_summary(repo)
perf = performance_summary(repo)
open_bets = repo.load_open_bets()


# ============================
# Sidebar controls
# ============================
with st.sidebar:
    st.markdown("## Command Center")

    c1, c2 = st.columns(2)
    if c1.button("Refresh", use_container_width=True):
        st.rerun()
    if c2.button("Generate demo", use_container_width=True):
        generate_demo_state(repo, initial_bankroll=300.0, n_settled=30, n_open=8, seed=42)
        st.success("Demo data generated")
        st.rerun()

    st.divider()

    st.markdown("### Live status")
    st.metric("Available cash", money(state["available_cash"]))
    st.metric("Open bets", int(state["n_open_bets"]))
    st.metric("Locked total", money(state["locked_total"]))

    st.divider()

    st.markdown("### Bankroll")
    with st.form("bankroll_form"):
        cash = st.number_input("Cash (£)", min_value=0.0, value=float(state["available_cash"]), step=50.0)
        confirm = st.checkbox("Confirm reset", value=False)
        ok = st.form_submit_button("Set bankroll", use_container_width=True)
    if ok:
        if not confirm:
            st.error("Confirmation required.")
        else:
            repo.reset_ledger_to_cash(float(cash))
            st.success(f"Bankroll set to {money(cash)}")
            st.rerun()

    st.divider()

    st.markdown("### Price + Place")
    with st.form("price_place_form"):
        bet_type = st.selectbox("Bet type", ["qualifying", "freebet_snr", "freebet_sr"])
        team = st.text_input("Team", value="")
        bookmaker = st.text_input("Bookmaker", value="")
        back_odds = st.number_input("Back odds", min_value=1.01, value=2.0, step=0.01)
        lay_odds = st.number_input("Lay odds", min_value=1.01, value=2.0, step=0.01)
        stake_label = "Back stake (£)" if bet_type == "qualifying" else "Free stake (£)"
        stake = st.number_input(stake_label, min_value=0.0, value=10.0, step=1.0)
        commission_in = st.number_input("Commission (0.02 or 2)", min_value=0.0, value=0.02, step=0.01)

        pc1, pc2 = st.columns(2)
        do_price = pc1.form_submit_button("Price", use_container_width=True)
        do_place = pc2.form_submit_button("Place", use_container_width=True)

    if do_price:
        comm = norm_commission(float(commission_in))
        if bet_type == "qualifying":
            cand = price_qualifying(team, bookmaker, float(back_odds), float(lay_odds), float(stake), comm)
        elif bet_type == "freebet_snr":
            cand = price_freebet_snr(team, bookmaker, float(back_odds), float(lay_odds), float(stake), comm)
        else:
            cand = price_freebet_sr(team, bookmaker, float(back_odds), float(lay_odds), float(stake), comm)
        st.session_state["candidate"] = cand

    cand = st.session_state.get("candidate")
    if cand is not None:
        st.info(
            f"Priced: {cand.offer_type} • {cand.team} • {cand.bookmaker}\n\n"
            f"Lay stake: {money(cand.lay_stake)} | Liability: {money(cand.lay_liability)} | "
            f"GP: {money(cand.guaranteed_profit)} | ROI: {pct(cand.roi)}"
        )

    if do_place:
        cand = st.session_state.get("candidate")
        if cand is None:
            st.error("Price first.")
        else:
            bet = place_open_bet(repo, cand)
            st.success(f"Placed bet_id: {bet.bet_id}")
            st.rerun()

    st.divider()

    st.markdown("### Match lay")
    obs = repo.load_open_bets()
    ids = [b.bet_id for b in obs]
    if not ids:
        st.caption("No open bets.")
    else:
        bet_map = {b.bet_id: b for b in obs}
        with st.form("match_form"):
            bet_id = st.selectbox("bet_id", ids)
            bet = bet_map[bet_id]
            default_stake = float(bet.remaining_lay_stake())
            matched_odds = st.number_input(
                "Matched lay odds", min_value=1.01, value=float(bet.expected_lay_odds), step=0.01
            )
            match_stake = st.number_input("Match stake", min_value=0.0, value=default_stake, step=0.5)
            ok = st.form_submit_button("Apply match", use_container_width=True)

        if ok:
            updated = apply_lay_match(repo, bet_id, match_stake=float(match_stake), matched_odds=float(matched_odds))
            st.success(f"{updated.status} • matched {updated.matched_lay_stake:.4f}/{updated.candidate.lay_stake:.4f}")
            st.rerun()

    st.divider()

    st.markdown("### Settle")
    obs = repo.load_open_bets()
    ids = [b.bet_id for b in obs]
    if not ids:
        st.caption("No open bets.")
    else:
        bet_map = {b.bet_id: b for b in obs}
        with st.form("settle_form"):
            bet_id = st.selectbox("bet_id", ids)
            bet = bet_map[bet_id]
            result = st.selectbox("Result", ["win", "lose", "void"])

            exp_exch = float(expected_exchange_pnl_from_matches(bet, result))
            exp_bookie = float(default_bookie_payout(bet, result))

            actual_bookie_payout = st.number_input("Actual bookie payout (£)", value=exp_bookie, step=0.5)
            actual_exchange_pnl = st.number_input("Actual exchange PnL (£)", value=exp_exch, step=0.5)

            ok = st.form_submit_button("Settle bet", use_container_width=True)

        if ok:
            try:
                s = settle_open_bet(
                    repo,
                    bet_id,
                    result=result,
                    actual_bookie_payout=float(actual_bookie_payout),
                    actual_exchange_pnl=float(actual_exchange_pnl),
                )
                st.success(f"Realised profit: {money(s.realised_profit)}")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.divider()

    st.markdown("### Risk (Monte Carlo)")
    with st.form("risk_form"):
        n = st.number_input("Simulations", min_value=200, value=5000, step=500)
        fill_min = st.number_input("Fill min", min_value=0.0, max_value=1.0, value=0.95, step=0.01)
        fill_max = st.number_input("Fill max", min_value=0.0, max_value=1.0, value=1.00, step=0.01)
        slippage_std = st.number_input("Slippage std (odds)", min_value=0.0, value=0.01, step=0.01)
        void_prob = st.number_input("Void prob", min_value=0.0, max_value=1.0, value=0.00, step=0.01)
        want_hist = st.checkbox("Also compute distribution histogram", value=False, disabled=not HAS_MC)
        ok = st.form_submit_button("Run risk", use_container_width=True)

    if ok:
        snap = risk_snapshot(
            repo,
            n=int(n),
            fill_min=float(fill_min),
            fill_max=float(fill_max),
            slippage_std=float(slippage_std),
            void_prob=float(void_prob),
        )
        st.session_state["risk_snap"] = snap
        st.session_state["risk_results"] = None

        if want_hist and HAS_MC:
            bank = float(state_summary(repo)["available_cash"])
            obs = repo.load_open_bets()
            out = run_monte_carlo(
                bankroll=bank,
                open_bets=obs,
                n=int(n),
                fill_min=float(fill_min),
                fill_max=float(fill_max),
                slippage_std=float(slippage_std),
                void_prob=float(void_prob),
            )
            st.session_state["risk_results"] = out.get("results", None)

        st.success("Risk snapshot updated")
        st.rerun()


# ============================
# Main layout
# ============================
st.title("Matched Betting Risk Engine")
st.caption("v1 • data/")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Available cash", money(state["available_cash"]))
m2.metric("Open bets", int(state["n_open_bets"]))
m3.metric("Locked total", money(state["locked_total"]))
m4.metric("GP (open) total", money(state["gp_open_total"]))
m5.metric("Liability total", money(state["liability_total"]))

tabs = st.tabs(["Operations", "Analytics", "Risk"])


# ============================
# Operations tab
# ============================
with tabs[0]:
    st.subheader("Open bets")
    open_df = build_open_df(open_bets)

    if open_df.empty:
        st.info("No open bets.")
    else:
        q = st.text_input("Search open bets", value="", placeholder="team / bookmaker / bet_id")
        if q.strip():
            qq = q.strip().lower()
            mask = (
                open_df["bet_id"].astype(str).str.lower().str.contains(qq)
                | open_df["team"].astype(str).str.lower().str.contains(qq)
                | open_df["bookmaker"].astype(str).str.lower().str.contains(qq)
            )
            open_df = open_df[mask]

        st.dataframe(open_df, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Settled bets (raw)")
    settled_df = build_settled_df(repo)
    if settled_df.empty:
        st.info("No settled bets yet.")
    else:
        st.dataframe(
            settled_df.sort_values("settled_at", ascending=False, na_position="last"),
            use_container_width=True,
            hide_index=True,
        )


# ============================
# Analytics tab
# ============================
with tabs[1]:
    st.markdown("## Analytics")

    a1, a2, a3 = st.columns(3)
    a1.metric("Settled bets", int(perf.get("n_settled", 0)))
    a2.metric("Realised profit total", money(perf.get("realised_profit_total", 0.0)))
    a3.metric("Avg profit / bet", money(perf.get("avg_profit_per_bet", 0.0)))

    settled_df = build_settled_df(repo)

    if settled_df.empty:
        st.info("No settled bets yet. Settle a few bets to populate analytics.")
        st.stop()

    if "settled_at" not in settled_df.columns:
        st.error(f"Settled dataframe missing 'settled_at'. Columns: {list(settled_df.columns)}")
        st.stop()

    df = settled_df.copy()
    df["settled_at"] = pd.to_datetime(df["settled_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["settled_at"])
    if df.empty:
        st.error("Settled bets exist but none have valid timestamps.")
        st.stop()

    # Reduce overplotting if many events share same second
    df["settled_at"] = df["settled_at"].dt.floor("min")

    for col in ["realised_profit", "bookie_payout", "exchange_pnl"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df = df.sort_values("settled_at").reset_index(drop=True)
    df["cum_profit"] = df["realised_profit"].cumsum()

    # Baseline bankroll from ledger (best-effort)
    initial_bankroll = 0.0
    if hasattr(repo, "load_ledger"):
        ledger = repo.load_ledger() or []
        if ledger:
            initial_entries = [l for l in ledger if getattr(l, "type", None) in ("initial", "reset")]
            if initial_entries:
                initial_bankroll = float(initial_entries[0].amount)
            else:
                positives = [float(l.amount) for l in ledger if float(l.amount) > 0]
                initial_bankroll = positives[0] if positives else 0.0

    df["equity"] = df["cum_profit"] + float(initial_bankroll)
    df["peak"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] - df["peak"]

    st.divider()
    mm1, mm2, mm3 = st.columns(3)
    mm1.metric("Max drawdown", money(float(df["drawdown"].min())))
    mm2.metric("Best bet", money(float(df["realised_profit"].max())))
    mm3.metric("Worst bet", money(float(df["realised_profit"].min())))
    st.divider()

    # x-axis formatting (keep your existing logic)
    min_date = df["settled_at"].min()
    max_date = df["settled_at"].max()
    span_days = (max_date - min_date).days

    if span_days <= 7:
        fmt = "%d %b %H:%M"
    elif span_days <= 60:
        fmt = "%d %b"
    elif span_days <= 365:
        fmt = "%b %Y"
    else:
        fmt = "%Y"

    x_time = alt.X(
        "settled_at:T",
        title=None,
        axis=alt.Axis(format=fmt, labelAngle=-25, tickCount=8),
    )

    y_money = lambda field, title: alt.Y(
        field,
        title=title,
        axis=alt.Axis(format=",.0f"),
    )

    tt_time = alt.Tooltip("settled_at:T", title="Time", format="%Y-%m-%d %H:%M")

    st.markdown("### Cumulative profit")

    line = (
        alt.Chart(df)
        .mark_line(strokeWidth=3)
        .encode(
            x=x_time,
            y=y_money("cum_profit:Q", "Cum profit (£)"),
            tooltip=[
                tt_time,
                alt.Tooltip("cum_profit:Q", title="Cum profit (£)", format=",.2f"),
                alt.Tooltip("realised_profit:Q", title="Bet profit (£)", format=",.2f"),
                alt.Tooltip("offer_type:N", title="Offer"),
                alt.Tooltip("result:N", title="Result"),
                alt.Tooltip("bookmaker:N", title="Bookmaker"),
                alt.Tooltip("team:N", title="Team"),
            ],
        )
    )

    pts = (
        alt.Chart(df)
        .mark_point(size=55, filled=True)
        .encode(
            x=x_time,
            y="cum_profit:Q",
            tooltip=[
                tt_time,
                alt.Tooltip("cum_profit:Q", title="Cum profit (£)", format=",.2f"),
                alt.Tooltip("realised_profit:Q", title="Bet profit (£)", format=",.2f"),
                alt.Tooltip("offer_type:N", title="Offer"),
                alt.Tooltip("result:N", title="Result"),
            ],
        )
    )

    profit_chart = (line + pts).properties(height=340).configure_view(strokeOpacity=0)
    st.altair_chart(profit_chart, use_container_width=True)

    st.markdown("### Equity + drawdown")
    c1, c2 = st.columns(2)

    equity_chart = (
        alt.Chart(df)
        .mark_line(strokeWidth=3)
        .encode(
            x=x_time,
            y=y_money("equity:Q", "Equity (£)"),
            tooltip=[tt_time, alt.Tooltip("equity:Q", title="Equity (£)", format=",.2f")],
        )
        .properties(height=260)
        .configure_view(strokeOpacity=0)
    )

    drawdown_chart = (
        alt.Chart(df)
        .mark_area(opacity=0.25)
        .encode(
            x=x_time,
            y=y_money("drawdown:Q", "Drawdown (£)"),
            tooltip=[tt_time, alt.Tooltip("drawdown:Q", title="Drawdown (£)", format=",.2f")],
        )
        .properties(height=260)
        .configure_view(strokeOpacity=0)
    )

    with c1:
        st.altair_chart(equity_chart, use_container_width=True)
    with c2:
        st.altair_chart(drawdown_chart, use_container_width=True)

    st.markdown("### Breakdown")
    b1, b2 = st.columns(2)

    pot = perf.get("profit_by_offer_type", {}) or {}
    df_offer = pd.DataFrame([{"offer_type": k, "profit": float(v)} for k, v in pot.items()])
    df_offer = df_offer.sort_values("profit", ascending=False) if not df_offer.empty else df_offer

    if df_offer.empty:
        with b1:
            st.info("No offer breakdown yet.")
    else:
        offer_chart = (
            alt.Chart(df_offer)
            .mark_bar()
            .encode(
                x=alt.X("offer_type:N", title=None, sort="-y"),
                y=alt.Y("profit:Q", title="Profit (£)", axis=alt.Axis(format=",.0f")),
                tooltip=[
                    alt.Tooltip("offer_type:N", title="Offer"),
                    alt.Tooltip("profit:Q", title="Profit (£)", format=",.2f"),
                ],
            )
            .properties(height=260)
            .configure_view(strokeOpacity=0)
        )
        with b1:
            st.altair_chart(offer_chart, use_container_width=True)

    cbr = perf.get("count_by_result", {}) or {}
    df_res = pd.DataFrame([{"result": k, "count": int(v)} for k, v in cbr.items()])
    df_res = df_res.sort_values("count", ascending=False) if not df_res.empty else df_res

    if df_res.empty:
        with b2:
            st.info("No result breakdown yet.")
    else:
        res_chart = (
            alt.Chart(df_res)
            .mark_bar()
            .encode(
                x=alt.X("result:N", title=None, sort="-y"),
                y=alt.Y("count:Q", title="Count"),
                tooltip=[
                    alt.Tooltip("result:N", title="Result"),
                    alt.Tooltip("count:Q", title="Count"),
                ],
            )
            .properties(height=260)
            .configure_view(strokeOpacity=0)
        )
        with b2:
            st.altair_chart(res_chart, use_container_width=True)

    with st.expander("Show chart data", expanded=False):
        st.dataframe(df.sort_values("settled_at", ascending=False), use_container_width=True, hide_index=True)


# ============================
# Risk tab
# ============================
with tabs[2]:
    st.subheader("Risk snapshot")

    snap = st.session_state.get("risk_snap")
    if not snap:
        st.info("Run Monte Carlo from the sidebar to populate this.")
        st.stop()

    if "error" in snap:
        st.error(snap["error"])
        st.stop()

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Mean", money(snap["mean"]))
    r2.metric("Worst 1%", money(snap["worst_1pct"]))
    r3.metric("P(down)", f"{snap['p_down']}%")
    r4.metric("Downside 1%", money(snap["downside_1pct"]))

    if st.session_state.get("risk_results") is not None:
        st.divider()
        st.subheader("Profit distribution")

        results = st.session_state["risk_results"]
        if results:
            current_bankroll = float(state_summary(repo)["available_cash"])
            series = pd.Series(results, dtype="float64") - current_bankroll

            bins = 30
            counts, edges = np.histogram(series, bins=bins)
            centers = 0.5 * (edges[:-1] + edges[1:])
            hist_df = pd.DataFrame({"Profit (£)": np.round(centers, 2), "Frequency": counts})

            st.bar_chart(hist_df.set_index("Profit (£)"))
        else:
            st.info("No results to plot.")