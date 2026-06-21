"""Variance Risk Premium & Variance-Swap Replication — Streamlit dashboard.

Run: streamlit run app.py

Sidebar controls that only touch the small VRP/strategy series (cost bps,
position sizing/tail-stop, realized-vol estimator, gross/net) recompute
live — they're cheap (a few thousand rows). The option-chain replication
itself is NOT recomputed live: it's the expensive, validated part of this
project (see RESULTS.md), so the dashboard reads its cached output.
Target tenor is fixed at 30 days for the same reason — re-deriving the
chain for a different tenor would mean re-running the full historical
replication, not a dashboard-speed operation.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import DATA_RAW_DIR, FIGURES_DIR
from src.vrp import backtest, data_access, smile, strategy
from src.vrp.ingest import cboe_vix, fred, underlying

st.set_page_config(page_title="VRP & Variance-Swap Replication", layout="wide")

CACHE_DIR = DATA_RAW_DIR.parent / "cache"
ESTIMATORS = ["close_to_close", "parkinson", "garman_klass"]


@st.cache_data
def load_implied_vs_vix() -> pd.DataFrame:
    return pd.read_parquet(CACHE_DIR / "synthetic_vs_vix_2017_2023.parquet")


@st.cache_data
def load_vrp(estimator: str) -> pd.DataFrame:
    return pd.read_parquet(CACHE_DIR / f"vrp_2017_2023_{estimator}.parquet")


@st.cache_data
def load_trailing_vol() -> pd.Series:
    df = pd.read_parquet(CACHE_DIR / "trailing_realized_variance.parquet")
    return 100 * df["trailing_realized_variance"] ** 0.5


@st.cache_data
def load_spx() -> pd.DataFrame:
    return underlying.fetch_underlying_history()


@st.cache_data
def load_vix() -> pd.DataFrame:
    return cboe_vix.fetch_vix_history()


@st.cache_data
def load_rate() -> pd.Series:
    rate = fred.fetch_fred_series()["DGS3MO"] / 100.0
    return rate.reindex(pd.date_range(rate.index.min(), rate.index.max())).ffill()


@st.cache_data
def run_strategy(estimator: str, vega_notional: float, tail_stop_pct: float, txn_bps: float, spread_bps: float) -> pd.DataFrame:
    vrp_df = load_vrp(estimator)
    trailing_vol = load_trailing_vol()
    spx = load_spx()
    # costs.entry_cost_usd reads bps from config by default; override via direct calc here
    pnl = strategy.daily_pnl_series(vrp_df, trailing_vol, spx.index, vega_notional, tail_stop_pct)
    if (txn_bps, spread_bps) != (5.0, 2.5):
        total_bps = txn_bps + 2 * spread_bps
        pnl["cost_usd"] = pnl["notional_usd"] * total_bps / 10_000.0
        pnl["net_pnl_usd"] = pnl["gross_pnl_usd"] - pnl["cost_usd"]
    return pnl


# --- Sidebar -----------------------------------------------------------
st.sidebar.title("Controls")

implied_vix = load_implied_vs_vix()
min_date, max_date = implied_vix.index.min().date(), implied_vix.index.max().date()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (min_date, max_date))

st.sidebar.selectbox("Target tenor (DTE)", options=["30 (fixed)"], disabled=True,
                      help="Fixed at 30 days — this is the validated replication (RESULTS.md). "
                           "Other tenors would require re-running the full historical option-chain pull.")

txn_bps = st.sidebar.slider("Transaction cost (bps)", 0.0, 30.0, 5.0, 0.5)
spread_bps = st.sidebar.slider("Bid-ask half-spread (bps)", 0.0, 30.0, 2.5, 0.5)
tail_stop_pct = st.sidebar.slider("Tail-stop trigger: trailing realized vol (%)", 15.0, 80.0, 35.0, 1.0,
                                   help="Pause new short-variance entries when trailing 10-day realized vol exceeds this.")
vega_notional = st.sidebar.number_input("Vega notional (risk-sizing base, $)", value=1.0, min_value=0.01, step=0.5)
estimator = st.sidebar.selectbox("Realized-vol estimator", ESTIMATORS, index=0)
gross_or_net = st.sidebar.radio("Strategy view", ["Net", "Gross"], horizontal=True)

# --- Data, filtered to the selected date range --------------------------
vrp_df = load_vrp(estimator)
mask = (vrp_df.index.date >= start_date) & (vrp_df.index.date <= end_date)
vrp_view = vrp_df[mask]

pnl = run_strategy(estimator, vega_notional, tail_stop_pct, txn_bps, spread_bps)
gross_ret = backtest.daily_returns(pnl["gross_pnl_usd"], vega_notional)
net_ret = backtest.daily_returns(pnl["net_pnl_usd"], vega_notional)
ret_mask = (pnl.index.date >= start_date) & (pnl.index.date <= end_date)
chosen_ret = (net_ret if gross_or_net == "Net" else gross_ret)[ret_mask]
strat_stats = backtest.performance_stats(chosen_ret)

# --- Overview ------------------------------------------------------------
st.title("Variance Risk Premium & Variance-Swap Replication — SPX")
st.caption("All numbers reproducible from RESULTS.md / scripts in this repo. See sidebar for live-adjustable assumptions.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Average VRP (vol pts)", f"{vrp_view['vrp_vol_pts'].mean():.2f}")
c2.metric("% days VRP > 0", f"{(vrp_view['vrp'] > 0).mean()*100:.1f}%")
c3.metric(f"Strategy {gross_or_net.lower()} Sharpe", f"{strat_stats['sharpe']:.2f}")
c4.metric(f"Strategy {gross_or_net.lower()} max drawdown", f"{strat_stats['max_drawdown']*100:.1f}%")

st.divider()

# --- Implied vs Realized --------------------------------------------------
st.header("Implied vs. Realized Volatility")
fig = go.Figure()
fig.add_trace(go.Scatter(x=vrp_view.index, y=vrp_view["implied_vol_pct"], name="Implied (30d, synthetic)", line=dict(color="#1f77b4")))
fig.add_trace(go.Scatter(x=vrp_view.index, y=vrp_view["realized_vol_pct"], name="Realized (next 30d)", line=dict(color="#ff7f0e")))
fig.add_vrect(x0="2020-01-01", x1="2020-12-31", fillcolor="red", opacity=0.08, line_width=0, annotation_text="2020")
fig.add_vrect(x0="2022-01-01", x1="2022-12-31", fillcolor="orange", opacity=0.08, line_width=0, annotation_text="2022")
fig.update_layout(yaxis_title="Annualized vol (%)", height=420, legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, width='stretch')

# --- VRP -------------------------------------------------------------------
st.header("Variance Risk Premium")
col1, col2 = st.columns([2, 1])
with col1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=vrp_view.index, y=vrp_view["vrp_vol_pts"], name="VRP (vol pts)", line=dict(color="#2ca02c")))
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(yaxis_title="VRP (vol pts)", height=380)
    st.plotly_chart(fig, width='stretch')
with col2:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=vrp_view["vrp_vol_pts"], nbinsx=40, marker_color="#2ca02c"))
    fig.add_vline(x=0, line_dash="dot", line_color="gray")
    fig.update_layout(xaxis_title="VRP (vol pts)", height=380, showlegend=False)
    st.plotly_chart(fig, width='stretch')

# --- Replication validation ------------------------------------------------
st.header("Replication Validation: Synthetic 30-Day Implied Vol vs. Real VIX")
val_view = implied_vix[mask]
err = (val_view["vol_30d_pct"] - val_view["vix_close"]).abs()
v1, v2, v3 = st.columns(3)
v1.metric("Mean abs error (vol pts)", f"{err.mean():.3f}")
v2.metric("RMSE (vol pts)", f"{(err**2).mean()**0.5:.3f}")
v3.metric("Correlation", f"{val_view['vol_30d_pct'].corr(val_view['vix_close']):.4f}")

fig = go.Figure()
fig.add_trace(go.Scatter(x=val_view.index, y=val_view["vol_30d_pct"], name="Synthetic 30d implied vol", line=dict(color="#1f77b4")))
fig.add_trace(go.Scatter(x=val_view.index, y=val_view["vix_close"], name="Real VIX", line=dict(color="#d62728", dash="dot")))
fig.update_layout(yaxis_title="Vol (%)", height=400, legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, width='stretch')

# --- Snapshot ---------------------------------------------------------------
st.header("Snapshot: Option Smile for a Selected Date")
snap_date = st.date_input("Snapshot date", value=pd.Timestamp("2020-03-16").date(), min_value=min_date, max_value=max_date)
snap_ts = pd.Timestamp(snap_date)

day_chain = data_access.load_chain_for_date(snap_ts)
if day_chain.empty:
    st.info("No option data cached for this date (non-trading day or outside the pulled window).")
else:
    grid = data_access.full_strike_grid_for_date(snap_ts)
    grids_by_expiry = {e: np.sort(g.strike.unique()) for e, g in grid.groupby("expiry")}
    rate = load_rate().asof(snap_ts)
    dtes = sorted(int(d) for d in day_chain["dte"].unique() if d > 0)[:2]

    fig = go.Figure()
    for dte in dtes:
        expiry = snap_ts + pd.Timedelta(days=dte)
        fg = grids_by_expiry.get(expiry)
        if fg is None:
            continue
        sm = smile.smile_for_expiry(day_chain, dte, rate, fg)
        if sm.empty:
            continue
        fig.add_trace(go.Scatter(x=sm["moneyness"], y=100 * sm["iv"], mode="markers",
                                  name=f"{dte}d (exp {expiry.date()})"))
    fig.update_layout(xaxis_title="Moneyness (K/F)", yaxis_title="Black-76 implied vol (%)", height=420,
                       legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width='stretch')
    st.caption("Implied vol per strike via Black-76 inversion against the same put-call-parity forward used in "
               "the replication — a display convenience; the headline implied-variance numbers never use this.")

# --- Strategy ----------------------------------------------------------------
st.header("Strategy: Cost-Aware Short-Variance Carry")

eq_gross = (1 + gross_ret[ret_mask]).cumprod()
eq_net = (1 + net_ret[ret_mask]).cumprod()
fig = go.Figure()
fig.add_trace(go.Scatter(x=eq_gross.index, y=eq_gross, name="Gross", line=dict(color="#1f77b4")))
fig.add_trace(go.Scatter(x=eq_net.index, y=eq_net, name="Net", line=dict(color="#d62728")))
fig.update_layout(yaxis_title="NAV (start = 1.0)", height=400, legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, width='stretch')

nav = backtest._nav_with_liquidation_floor(chosen_ret.dropna())
dd = nav / nav.cummax() - 1
fig = go.Figure()
fig.add_trace(go.Scatter(x=dd.index, y=dd * 100, fill="tozeroy", line=dict(color="#d62728"), name="Drawdown"))
fig.update_layout(yaxis_title="Drawdown (%)", height=300)
st.plotly_chart(fig, width='stretch')

monthly = chosen_ret.resample("ME").apply(lambda r: (1 + r).prod() - 1) * 100
heat = monthly.to_frame("ret")
heat["year"], heat["month"] = heat.index.year, heat.index.month
pivot = heat.pivot(index="year", columns="month", values="ret")
fig = go.Figure(data=go.Heatmap(z=pivot.values, x=[f"{m:02d}" for m in pivot.columns], y=pivot.index.astype(str),
                                 colorscale="RdYlGn", zmid=0, text=np.round(pivot.values, 1), texttemplate="%{text}"))
fig.update_layout(height=320, xaxis_title="Month", yaxis_title="Year")
st.plotly_chart(fig, width='stretch')

metrics_df = pd.DataFrame({"Gross": backtest.performance_stats(gross_ret[ret_mask]), "Net": backtest.performance_stats(net_ret[ret_mask])}).T
st.dataframe(metrics_df.style.format("{:.4f}"), width='stretch')
