#!/usr/bin/env python3
"""
Model B Implementation & Empirical Validation: Dual-Horizon Selection
Macro Trend Direction (Close > SMA_trend) + Micro Mean-Reverting Oscillation (Lowest ER)

Compares:
  - Model A: Pure Low ER (Baseline)
  - Model B1: Dual-Horizon (Close > SMA100 + Lowest ER)
  - Model B2: Dual-Horizon (Close > SMA200 + Lowest ER)
  - Model B + Dynamic Inventory Hedge (VN30F)
Across In-Sample (2021-2023), Out-of-Sample (2024), and Forward Holdout (2025-2026).
"""

import os
import sys
import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.data_fetcher import prepare_data
from src.logic import kaufman_er, get_settlement_dt

def build_dual_horizon_whitelist(
    bars_df,
    lookback_days=40,
    rebalance_days=10,
    top_k=4,
    trend_filter="none",  # "none", "sma100", "sma200"
    selection_mode="er_low",
    seed=42
):
    daily_records = []
    for ticker, df in bars_df.groupby("tickersymbol"):
        df = df.sort_values("bar_close").copy()
        if df["close"].max() < 1000:
            for c in ["open", "high", "low", "close"]:
                df[c] *= 1000.0
        df["date"] = df["bar_close"].dt.date
        daily = df.groupby("date").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).reset_index()
        daily["tickersymbol"] = ticker
        daily_records.append(daily)
        
    daily_df = pd.concat(daily_records).sort_values(["date", "tickersymbol"]).reset_index(drop=True)
    all_dates = sorted(daily_df["date"].unique())
    piv_close = daily_df.pivot(index="date", columns="tickersymbol", values="close").ffill()
    
    # Compute Trend Moving Averages on Daily Bars
    if trend_filter == "sma100":
        trend_ma = piv_close.rolling(100, min_periods=30).mean()
    elif trend_filter == "sma200":
        trend_ma = piv_close.rolling(200, min_periods=40).mean()
    else:
        trend_ma = None
        
    rng = np.random.RandomState(seed)
    whitelist = {}
    
    for i in range(lookback_days, len(all_dates), rebalance_days):
        rebal_date = all_dates[i]
        hist_dates = all_dates[i - lookback_days : i]
        candidates = []
        
        for ticker in piv_close.columns:
            c_hist = piv_close.loc[hist_dates, ticker].dropna()
            if len(c_hist) < lookback_days * 0.8:
                continue
            cur_price = piv_close.loc[rebal_date, ticker]
            
            # Macro Trend Condition
            is_uptrend = True
            if trend_ma is not None:
                ma_val = trend_ma.loc[rebal_date, ticker]
                if not np.isnan(ma_val):
                    is_uptrend = (cur_price >= ma_val)
                    
            er_val = kaufman_er(c_hist.values)
            candidates.append({
                "ticker": ticker,
                "er": er_val,
                "is_uptrend": is_uptrend
            })
            
        if trend_filter in ["sma100", "sma200"]:
            # Prioritize candidates in a macro uptrend, then sort by lowest ER
            uptrend_candidates = [c for c in candidates if c["is_uptrend"]]
            if len(uptrend_candidates) >= top_k:
                uptrend_candidates.sort(key=lambda x: x["er"])
                chosen = [c["ticker"] for c in uptrend_candidates[:top_k]]
            else:
                # If fewer than top_k stocks in uptrend, fill remainder with lowest ER
                uptrend_candidates.sort(key=lambda x: x["er"])
                chosen = [c["ticker"] for c in uptrend_candidates]
                remaining = [c for c in candidates if c["ticker"] not in chosen]
                remaining.sort(key=lambda x: x["er"])
                chosen += [c["ticker"] for c in remaining[:(top_k - len(chosen))]]
            whitelist[rebal_date] = chosen
        else:
            # Baseline: Pure ER Low
            candidates.sort(key=lambda x: x["er"])
            whitelist[rebal_date] = [c["ticker"] for c in candidates[:top_k]]
            
    return whitelist

def backtest_dual_horizon(
    bundle,
    trend_filter="none",
    capital=1_000_000_000,
    top_k=4,
    n_levels=18,
    grid_spacing_pct=0.018,
    stop_buffer_levels=2,
    use_sma_filter=True,
    hedge_ratio=0.0,
    vn30f_series=None
):
    bars_df = bundle["bars"].copy()
    if bars_df["close"].max() < 1000:
        for c in ["open", "high", "low", "close"]:
            bars_df[c] *= 1000.0
    bars_df = bars_df.sort_values(["bar_close", "tickersymbol"]).reset_index(drop=True)
    
    spot_all_ts = sorted(bars_df["bar_close"].unique())
    f_series = vn30f_series.reindex(pd.Index(spot_all_ts)).ffill().bfill() if vn30f_series is not None else None
    
    whitelist_by_date = build_dual_horizon_whitelist(
        bars_df,
        lookback_days=40,
        rebalance_days=10,
        top_k=top_k,
        trend_filter=trend_filter,
        selection_mode="er_low"
    )
    
    anchors = {}
    for ticker, df in bars_df.groupby("tickersymbol"):
        anchors[ticker] = df.sort_values("bar_close").set_index("bar_close")["close"].rolling(50).mean()
        
    capital_per_stock = float(capital) / top_k
    capital_per_level = capital_per_stock / n_levels
    broker_fee = 0.0015
    sell_tax = 0.0010
    slippage = 0.0005
    
    cash = float(capital)
    grids = {}
    positions = {}
    completed_trades = []
    
    wl_dates = sorted(whitelist_by_date.keys())
    cur_wl = []
    next_wl_idx = 0
    
    cur_short_contracts = 0
    futures_realized_pnl = 0.0
    last_f_px = None
    equity_records = []
    
    for ts, bar_group in bars_df.groupby("bar_close", sort=True):
        bar_group = bar_group.set_index("tickersymbol")
        cur_date = ts.date()
        f_px = float(f_series.loc[ts]) if f_series is not None else 0.0
        
        if next_wl_idx < len(wl_dates) and cur_date >= wl_dates[next_wl_idx]:
            cur_wl = whitelist_by_date[wl_dates[next_wl_idx]]
            next_wl_idx += 1
            
        # 1. EXITS
        for ticker in list(positions.keys()):
            if ticker not in bar_group.index:
                continue
            bar = bar_group.loc[ticker]
            bar_o, bar_h, bar_l, bar_c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            grid_info = grids.get(ticker)
            floor_stop = grid_info["stop"] if grid_info else 0.0
            is_floor_hit = (bar_l <= floor_stop) and (floor_stop > 0)
            
            to_remove = []
            lvl_dict = positions[ticker]
            for lvl, pos in list(lvl_dict.items()):
                can_exit = (ts >= pos["settlement"])
                if pos.get("pending_floor_stop", False):
                    if can_exit:
                        to_remove.append((lvl, bar_o, True, "settled_floor_stop"))
                    continue
                if is_floor_hit:
                    if can_exit:
                        fill = max(min(bar_o, floor_stop), floor_stop * 0.93)
                        to_remove.append((lvl, fill, True, "floor_stop"))
                    else:
                        pos["pending_floor_stop"] = True
                        if ticker in grids:
                            grids[ticker]["stop_triggered"] = True
                    continue
                if bar_h >= pos["tp_price"] and can_exit:
                    to_remove.append((lvl, pos["tp_price"], False, "target"))
                    continue
                if ticker not in cur_wl and can_exit and (grid_info is None):
                    to_remove.append((lvl, bar_c, True, "rotation_exit"))
                    continue
                    
            for (lvl, fill_px, is_stop, reason) in to_remove:
                pos = lvl_dict.pop(lvl)
                actual_fill = fill_px * (1.0 - slippage)
                exit_cost = actual_fill * pos["shares"] * (broker_fee + sell_tax)
                proceeds = actual_fill * pos["shares"] - exit_cost
                cash += proceeds
                pnl = proceeds - (pos["entry_price"] * pos["shares"] + pos["entry_cost"])
                completed_trades.append({
                    "ticker": ticker, "level": lvl, "reason": reason,
                    "pnl": pnl, "entry_ts": pos["entry_ts"], "exit_ts": ts
                })
                
            if len(lvl_dict) == 0:
                positions.pop(ticker, None)
                if ticker in grids and (grids[ticker].get("stop_triggered", False) or ticker not in cur_wl):
                    del grids[ticker]
                    
        # 2. GRID ACTIVATION
        for ticker in list(grids.keys()):
            if ticker not in cur_wl and (ticker not in positions or len(positions[ticker]) == 0):
                del grids[ticker]
                
        avail_slots = top_k - len(grids)
        if avail_slots > 0 and len(cur_wl) > 0:
            for ticker in cur_wl:
                if ticker in grids or ticker not in bar_group.index:
                    continue
                bar = bar_group.loc[ticker]
                sma_val = anchors[ticker].get(ts, np.nan)
                if np.isnan(sma_val):
                    continue
                if use_sma_filter and (abs(float(bar["close"]) - sma_val) / sma_val > 0.03):
                    continue
                spacing = sma_val * grid_spacing_pct
                levels = [round(sma_val - k * spacing, 2) for k in range(1, n_levels + 1)]
                tps = [round(sma_val - (k - 1) * spacing, 2) for k in range(1, n_levels + 1)]
                stop_px = sma_val - (n_levels + stop_buffer_levels) * spacing
                grids[ticker] = {
                    "anchor": sma_val, "levels": levels, "tps": tps, "stop": stop_px,
                    "active_from_ts": ts
                }
                positions.setdefault(ticker, {})
                avail_slots -= 1
                if avail_slots <= 0:
                    break
                    
        # 3. BUY MATCHING
        for ticker, g in list(grids.items()):
            if ticker not in bar_group.index or g.get("stop_triggered", False) or g.get("active_from_ts") == ts:
                continue
            bar_o = float(bar_group.loc[ticker, "open"])
            bar_l = float(bar_group.loc[ticker, "low"])
            lvl_dict = positions.setdefault(ticker, {})
            
            for lvl_idx in range(1, n_levels + 1):
                if lvl_idx in lvl_dict:
                    continue
                limit_px = g["levels"][lvl_idx - 1]
                if bar_l > limit_px:
                    continue
                fill_px = (bar_o * (1.0 + slippage)) if (bar_o <= limit_px) else (limit_px * (1.0 + slippage))
                raw_shares = capital_per_level / fill_px
                order_shares = max(100, int(round(raw_shares / 100.0)) * 100)
                entry_cost = fill_px * order_shares * broker_fee
                req_cash = fill_px * order_shares + entry_cost
                if cash < req_cash:
                    continue
                cash -= req_cash
                lvl_dict[lvl_idx] = {
                    "shares": order_shares, "entry_price": fill_px,
                    "tp_price": g["tps"][lvl_idx - 1], "entry_cost": entry_cost,
                    "entry_ts": ts, "settlement": get_settlement_dt(ts)
                }
                
        # 4. HEDGING (IF ENABLED)
        spot_inventory_val = sum(
            sum(p["shares"] * float(bar_group.loc[t, "close"]) for p in lvl_dict.values())
            for t, lvl_dict in positions.items() if t in bar_group.index
        )
        
        if hedge_ratio > 0 and f_series is not None:
            if last_f_px is not None and cur_short_contracts > 0:
                f_pnl_delta = - cur_short_contracts * (f_px - last_f_px) * 100_000.0
                futures_realized_pnl += f_pnl_delta
            target_short = int(round((spot_inventory_val * hedge_ratio) / (f_px * 100_000.0))) if f_px > 0 else 0
            if target_short != cur_short_contracts:
                diff = abs(target_short - cur_short_contracts)
                futures_realized_pnl -= diff * 60_000.0
                cur_short_contracts = target_short
            last_f_px = f_px
            
        port_val = cash + spot_inventory_val + futures_realized_pnl
        equity_records.append({"bar_close": ts, "portfolio_value": port_val})
        
    eq_df = pd.DataFrame(equity_records).set_index("bar_close")
    eq_s = eq_df["portfolio_value"]
    hpr = (eq_s.iloc[-1] / float(capital) - 1.0) * 100.0
    cummax = eq_s.cummax()
    dd = (eq_s - cummax) / cummax
    max_dd = float(dd.min()) * 100.0
    rets = eq_s.pct_change().dropna()
    rf_per_bar = 0.06 / 2016.0
    excess_mean = float(rets.mean() - rf_per_bar)
    sharpe = float(excess_mean / rets.std() * np.sqrt(2016)) if rets.std() > 0 else 0.0
    
    trades_df = pd.DataFrame(completed_trades)
    tp_trades = trades_df[trades_df["reason"] == "target"] if len(trades_df) > 0 else pd.DataFrame()
    stop_trades = trades_df[trades_df["reason"] != "target"] if len(trades_df) > 0 else pd.DataFrame()
    harvest_pnl = float(tp_trades["pnl"].sum()) if len(tp_trades) > 0 else 0.0
    drag_pnl = float(stop_trades["pnl"].sum()) if len(stop_trades) > 0 else 0.0
    
    return {
        "hpr": hpr,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "roundtrips": len(tp_trades),
        "stops": len(stop_trades),
        "harvest_pnl": harvest_pnl,
        "drag_pnl": drag_pnl,
        "equity_series": eq_s
    }

def main():
    print("=" * 105)
    print("MODEL B (DUAL-HORIZON) EMPIRICAL VALIDATION")
    print("Macro Trend Direction (Close > SMA_trend) + Micro Mean-Reverting Oscillation (Lowest ER)")
    print("=" * 105)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    f_path = "/Users/ttt/Final_Projects_v1/data/benchmark/vn30f1m_30m.parquet"
    f_df = pd.read_parquet(f_path)
    f_df["bar_close"] = pd.to_datetime(f_df["bar_close"])
    vn30f_series = f_df.sort_values("bar_close").set_index("bar_close")["close"]
    
    splits = ["in_sample", "out_sample", "holdout"]
    models = [
        ("Model A: Pure Low ER (Baseline)", "none", 0.0),
        ("Model B1: Dual-Horizon (Close > SMA100 + Low ER)", "sma100", 0.0),
        ("Model B2: Dual-Horizon (Close > SMA200 + Low ER)", "sma200", 0.0),
        ("Model B2 + Dynamic Inventory Hedge", "sma200", 1.0),
    ]
    
    all_results = []
    
    for split in splits:
        print(f"\n[EVALUATING SPLIT: {split.upper()}] ...")
        b = prepare_data(config, split)
        for label, tf, hedge in models:
            res = backtest_dual_horizon(
                b,
                trend_filter=tf,
                capital=1e9,
                hedge_ratio=hedge,
                vn30f_series=vn30f_series
            )
            all_results.append({
                "split": split,
                "model": label,
                "hpr": res["hpr"],
                "max_dd": res["max_drawdown"],
                "sharpe": res["sharpe_ratio"],
                "roundtrips": res["roundtrips"],
                "stops": res["stops"],
                "harvest_pnl": res["harvest_pnl"],
                "drag_pnl": res["drag_pnl"],
                "equity_series": res["equity_series"]
            })
            print(f"  {label:<50} | Return: {res['hpr']:+6.2f}% | MaxDD: {res['max_drawdown']:5.1f}% | Sharpe: {res['sharpe_ratio']:5.3f} | Stops: {res['stops']:>2} | Roundtrips: {res['roundtrips']}")
            
    df_summary = pd.DataFrame(all_results)
    
    # Generate Multi-Panel Comparison Visualization
    fig, axes = plt.subplots(1, 3, figsize=(21, 6.5), sharey=False)
    split_titles = {
        "in_sample": "In-Sample Secular Bear (2021–2023)",
        "out_sample": "Out-of-Sample Recovery (2024)",
        "holdout": "Forward Blind Holdout (2025–2026)"
    }
    
    colors = {
        "Model A: Pure Low ER (Baseline)": "#4B5563",
        "Model B1: Dual-Horizon (Close > SMA100 + Low ER)": "#2563EB",
        "Model B2: Dual-Horizon (Close > SMA200 + Low ER)": "#D97706",
        "Model B2 + Dynamic Inventory Hedge": "#059669"
    }
    styles = {
        "Model A: Pure Low ER (Baseline)": ":",
        "Model B1: Dual-Horizon (Close > SMA100 + Low ER)": "--",
        "Model B2: Dual-Horizon (Close > SMA200 + Low ER)": "-.",
        "Model B2 + Dynamic Inventory Hedge": "-"
    }
    
    for idx, split in enumerate(splits):
        ax = axes[idx]
        sub = df_summary[df_summary["split"] == split]
        for _, row in sub.iterrows():
            m_name = row["model"]
            eq = (row["equity_series"] / 1e9) * 100.0
            label_text = f"{m_name.split(':')[0]}: {row['hpr']:+.2f}% (DD {row['max_dd']:.1f}%)"
            ax.plot(eq.index, eq.values, label=label_text, color=colors[m_name], linestyle=styles[m_name], linewidth=1.9)
            
        ax.set_title(split_titles[split], fontsize=12.5, fontweight="bold", pad=10)
        ax.axhline(100.0, color="#9CA3AF", linestyle="--", alpha=0.6, linewidth=1)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.set_ylabel("Portfolio Equity (Normalized Base = 100)", fontsize=10)
        ax.legend(loc="best", fontsize=8.2, framealpha=0.92)
        
    plt.suptitle("Model B Evaluation: Dual-Horizon Selection (Macro Trend + Micro Low ER)", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    
    out_img = os.path.join(curr_dir, "images/model_b_dual_horizon_comparison.png")
    plt.savefig(out_img, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\nSaved Model B comparison chart to: {out_img}")
    
    print("\n" + "=" * 115)
    print("MODEL B (DUAL-HORIZON) PERFORMANCE COMPARISON TABLE:")
    print("=" * 115)
    print(f"{'Split':<12} | {'Model Configuration':<50} | {'Return':<8} | {'MaxDD':<7} | {'Sharpe':<6} | {'Roundtrips':<10} | {'Stops'}")
    print("-" * 115)
    for _, r in df_summary.iterrows():
        print(f"{r['split']:<12} | {r['model']:<50} | {r['hpr']:+6.2f}%  | {r['max_dd']:5.1f}% | {r['sharpe']:6.3f} | {r['roundtrips']:>10} | {r['stops']:>5}")
    print("=" * 115)

if __name__ == "__main__":
    main()
