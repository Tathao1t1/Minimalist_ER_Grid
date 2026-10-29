#!/usr/bin/env python3
"""
High-Frequency & Capital Utilization Experiment
Evaluates levers to force more trade frequency and increase capital utilization:
1. Spacing Compression (Delta: 2.0% -> 1.5% -> 1.2% -> 1.0% -> 0.8%)
2. Portfolio Breadth Expansion (Top-K: 4 -> 6 -> 8 stocks)
3. Dynamic Trailing Anchor (Trailing 50-SMA baseline vs Static Rebalance Anchor)
"""

import os
import sys
import yaml
import pandas as pd
import numpy as np

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest, build_zero_overlap_whitelist, get_settlement_dt

class HighFrequencyERGridBacktest(MinimalistERGridBacktest):
    def __init__(self, trailing_anchor=False, **kwargs):
        super().__init__(**kwargs)
        self.trailing_anchor = trailing_anchor

    def backtest(self, data_bundle):
        if not self.trailing_anchor:
            r = super().backtest(data_bundle)
            r["avg_invested_pct"] = r.get("avg_capital_invested_pct", 0.0)
            return r

        # Dynamic Trailing Anchor Logic:
        # Re-evaluates grid levels dynamically whenever rolling 50-SMA shifts upward
        bars_df = data_bundle["bars"].copy()
        trading_days = np.array(sorted(bars_df["bar_close"].dt.date.unique()))

        whitelist_by_date = build_zero_overlap_whitelist(
            bars_df,
            lookback_days=self.selection_lookback,
            rebalance_days=self.selection_rebalance_days,
            top_k=self.top_k,
            trend_filter=self.trend_filter,
            selection_mode=self.selection_mode,
            seed=self.seed,
            use_sma_filter=self.use_sma_filter
        )

        anchors = {}
        for ticker, df in bars_df.groupby("tickersymbol"):
            df = df.sort_values("bar_close")
            anchors[ticker] = df.set_index("bar_close")["close"].rolling(50).mean()

        capital_per_stock = self.initial_spot_capital / self.top_k
        capital_per_level = capital_per_stock / self.n_levels

        cash = float(self.initial_spot_capital)
        grids = {}
        positions = {}
        completed_trades = []
        equity_curve = []
        last_known_close = {}

        wl_dates = sorted(whitelist_by_date.keys())
        cur_wl = []
        next_wl_idx = 0

        for ts, bar_group in bars_df.groupby("bar_close", sort=True):
            bar_group = bar_group.set_index("tickersymbol")
            cur_date = ts.date()
            is_warmup_bar = bool(bar_group["is_warmup"].iloc[0]) if "is_warmup" in bar_group.columns else False

            for t, row in bar_group.iterrows():
                last_known_close[t] = float(row["close"])

            if next_wl_idx < len(wl_dates) and cur_date >= wl_dates[next_wl_idx]:
                cur_wl = whitelist_by_date[wl_dates[next_wl_idx]]
                next_wl_idx += 1

            if is_warmup_bar:
                continue

            # PASS 1: EXITS
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
                            fill = bar_o
                            to_remove.append((lvl, fill, True, "settled_floor_stop"))
                        continue

                    if is_floor_hit:
                        if ticker in grids:
                            grids[ticker]["stop_triggered"] = True
                        if can_exit:
                            fill = min(bar_o, floor_stop)
                            to_remove.append((lvl, fill, True, "floor_stop"))
                        else:
                            pos["pending_floor_stop"] = True
                        continue

                    if bar_h >= pos["tp_price"] and can_exit:
                        to_remove.append((lvl, pos["tp_price"], False, "target"))
                        continue

                    if ticker not in cur_wl:
                        if pos.get("pending_rotation_exit", False):
                            if can_exit:
                                fill = bar_o
                                to_remove.append((lvl, fill, True, "settled_rotation_exit"))
                            continue
                        if can_exit:
                            fill = bar_c
                            to_remove.append((lvl, fill, True, "rotation_exit"))
                        else:
                            pos["pending_rotation_exit"] = True
                        continue

                for (lvl, fill_px, is_stop, reason) in to_remove:
                    pos = lvl_dict.pop(lvl)
                    actual_fill = fill_px * (1.0 - self.slippage)
                    exit_cost = actual_fill * pos["shares"] * (self.broker_fee + self.sell_tax)
                    proceeds = actual_fill * pos["shares"] - exit_cost
                    cash += proceeds
                    pnl = proceeds - (pos["entry_price"] * pos["shares"] + pos["entry_cost"])
                    completed_trades.append({
                        "ticker": ticker,
                        "level_idx": lvl,
                        "reason": reason,
                        "entry_ts": pos["entry_ts"],
                        "entry_price": pos["entry_price"],
                        "exit_ts": ts,
                        "exit_price": actual_fill,
                        "tp_price": pos["tp_price"],
                        "shares": pos["shares"],
                        "pnl": pnl,
                        "pnl_pct": pnl / (pos["entry_price"] * pos["shares"] + pos["entry_cost"]) * 100.0,
                        "holding_days": (ts - pos["entry_ts"]).total_seconds() / 86400.0
                    })

                if len(lvl_dict) == 0:
                    positions.pop(ticker, None)
                    if ticker in grids and (grids[ticker].get("stop_triggered", False) or ticker not in cur_wl):
                        del grids[ticker]

            # PASS 2: GRID INITIALIZATION & DYNAMIC TRAILING ANCHOR
            for ticker in list(grids.keys()):
                if ticker not in cur_wl and (ticker not in positions or len(positions[ticker]) == 0):
                    del grids[ticker]

            # If trailing anchor is active, update empty grid levels when SMA moves up
            for ticker in list(grids.keys()):
                if ticker in cur_wl and ticker in bar_group.index:
                    cur_sma = anchors[ticker].get(ts, np.nan)
                    if not np.isnan(cur_sma) and cur_sma > grids[ticker]["anchor"] * 1.01:
                        # Shift anchor up only if uninvested or re-anchoring open levels
                        if ticker not in positions or len(positions[ticker]) == 0:
                            spacing = cur_sma * self.grid_spacing_pct
                            grids[ticker]["anchor"] = cur_sma
                            grids[ticker]["levels"] = [round(cur_sma - k * spacing, 2) for k in range(1, self.n_levels + 1)]
                            grids[ticker]["tps"] = [round(cur_sma - (k - 1) * spacing, 2) for k in range(1, self.n_levels + 1)]
                            grids[ticker]["stop"] = cur_sma - (self.n_levels + self.stop_buffer_levels) * spacing

            avail_slots = self.top_k - len(grids)
            if avail_slots > 0 and len(cur_wl) > 0:
                for ticker in cur_wl:
                    if ticker in grids or ticker not in bar_group.index:
                        continue
                    sma_val = anchors[ticker].get(ts, np.nan)
                    if np.isnan(sma_val):
                        continue
                    spacing = sma_val * self.grid_spacing_pct
                    levels = [round(sma_val - k * spacing, 2) for k in range(1, self.n_levels + 1)]
                    tps = [round(sma_val - (k - 1) * spacing, 2) for k in range(1, self.n_levels + 1)]
                    stop_px = sma_val - (self.n_levels + self.stop_buffer_levels) * spacing
                    grids[ticker] = {
                        "anchor": sma_val,
                        "levels": levels,
                        "tps": tps,
                        "stop": stop_px,
                        "active_from_ts": ts
                    }
                    positions.setdefault(ticker, {})
                    avail_slots -= 1
                    if avail_slots <= 0:
                        break

            # PASS 3: BUY LIMIT FILLS
            for ticker, g in list(grids.items()):
                if ticker not in bar_group.index or ticker not in cur_wl or g.get("stop_triggered", False):
                    continue
                if g.get("active_from_ts") == ts:
                    continue

                bar_o = float(bar_group.loc[ticker, "open"])
                bar_l = float(bar_group.loc[ticker, "low"])
                lvl_dict = positions.setdefault(ticker, {})
                for lvl_idx in range(1, self.n_levels + 1):
                    if lvl_idx in lvl_dict:
                        continue
                    buy_px = g["levels"][lvl_idx - 1]
                    if bar_l > buy_px:
                        continue

                    fill_base = bar_o if bar_o <= buy_px else buy_px
                    actual_fill = fill_base * (1.0 + self.slippage)
                    order_shares = max(100, int(np.floor(capital_per_level / actual_fill / 100.0)) * 100)
                    entry_cost = actual_fill * order_shares * self.broker_fee
                    total_cost = actual_fill * order_shares + entry_cost
                    if cash < total_cost:
                        continue
                    cash -= total_cost
                    lvl_dict[lvl_idx] = {
                        "shares": order_shares,
                        "entry_price": actual_fill,
                        "tp_price": g["tps"][lvl_idx - 1],
                        "entry_cost": entry_cost,
                        "entry_ts": ts,
                        "settlement": get_settlement_dt(ts, trading_days),
                        "pending_floor_stop": False,
                        "pending_rotation_exit": False
                    }

            pos_val = 0.0
            for t, lvl_dict in positions.items():
                tot_shares = sum(p["shares"] for p in lvl_dict.values())
                if tot_shares > 0:
                    px = float(bar_group.loc[t]["close"]) if t in bar_group.index else last_known_close.get(t, 0.0)
                    pos_val += tot_shares * px
            if len(cur_wl) > 0 or len(positions) > 0:
                equity_curve.append({"bar_close": ts, "portfolio_value": cash + pos_val, "invested_val": pos_val})

        self.trades_df = pd.DataFrame(completed_trades)
        eq_df = pd.DataFrame(equity_curve)
        eq_series = eq_df.set_index(pd.to_datetime(eq_df["bar_close"]))["portfolio_value"]
        self.equity_series = eq_series
        avg_invested_pct = float((eq_df["invested_val"] / eq_df["portfolio_value"]).mean() * 100.0) if len(eq_df) > 0 else 0.0

        final_val = float(eq_series.iloc[-1])
        net_profit = final_val - self.capital
        hpr = (final_val / self.capital - 1.0) * 100.0

        days = (eq_series.index[-1] - eq_series.index[0]).days
        years = max(days / 365.25, 0.1)
        cagr = ((final_val / self.capital) ** (1.0 / years) - 1.0) * 100.0 if final_val > 0 else -100.0

        cummax = eq_series.cummax()
        drawdown = (eq_series - cummax) / cummax
        max_dd = float(drawdown.min() * 100.0)

        daily_returns = eq_series.resample("1D").last().dropna().pct_change().dropna()
        daily_rf = (1.0 + self.risk_free_rate) ** (1.0 / 252.0) - 1.0
        daily_sharpe = float((daily_returns.mean() - daily_rf) / daily_returns.std() * np.sqrt(252.0)) if len(daily_returns) > 1 and daily_returns.std() > 0 else 0.0
        calmar = float(cagr / abs(max_dd)) if abs(max_dd) > 0 else 0.0

        tp_count = len(self.trades_df[self.trades_df["reason"] == "target"]) if len(self.trades_df) > 0 else 0
        rot_count = len(self.trades_df[self.trades_df["reason"].str.contains("rotation", na=False)]) if len(self.trades_df) > 0 else 0
        stop_count = len(self.trades_df[self.trades_df["reason"].str.contains("floor", na=False)]) if len(self.trades_df) > 0 else 0

        win_rate = (tp_count / len(self.trades_df) * 100.0) if len(self.trades_df) > 0 else 0.0
        harvest_pnl = self.trades_df[self.trades_df["reason"] == "target"]["pnl"].sum() if tp_count > 0 else 0.0

        return {
            "total_trades": len(self.trades_df),
            "tp_trades": tp_count,
            "rot_trades": rot_count,
            "stop_trades": stop_count,
            "win_rate": win_rate,
            "hpr": hpr,
            "cagr": cagr,
            "max_drawdown": max_dd,
            "daily_sharpe": daily_sharpe,
            "calmar": calmar,
            "avg_invested_pct": avg_invested_pct,
            "harvest_pnl": harvest_pnl,
            "net_profit": net_profit
        }

def run_experiment_suite():
    cfg_path = os.path.join(repo_root, "config/config.yaml")
    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f)

    print("Loading data bundles...")
    is_bundle = prepare_data(cfg, "in_sample", include_warmup=False)
    oos_bundle = prepare_data(cfg, "out_sample", include_warmup=False)
    holdout_bundle = prepare_data(cfg, "holdout", include_warmup=False)

    print("\n" + "=" * 95)
    print("EXPERIMENT 1: SPACING COMPRESSION (Delta = 2.0% -> 1.5% -> 1.2% -> 1.0% -> 0.8%)")
    print("Baseline: k=4 stocks, N=16 levels, Lookback=30d, Rebalance=15d")
    print("=" * 95)
    print(f"{'Split':<10} | {'Spacing':<8} | {'Trades':<8} | {'TPs':<6} | {'WinRate':<8} | {'HPR (%)':<9} | {'MaxDD (%)':<10} | {'Sharpe':<7} | {'Avg Inv %':<10}")
    print("-" * 95)

    spacings = [0.020, 0.015, 0.012, 0.010, 0.008]
    splits = [("In-Sample", is_bundle), ("Out-Sample", oos_bundle), ("Holdout", holdout_bundle)]

    exp1_results = []
    for split_name, bundle in splits:
        for sp in spacings:
            sim = HighFrequencyERGridBacktest(
                capital=1_000_000_000,
                initial_spot_capital=1_000_000_000,
                broker_fee=0.0015,
                sell_tax=0.0010,
                slippage=0.0005,
                selection_lookback=30,
                selection_rebalance_days=15,
                top_k=4,
                n_levels=16,
                grid_spacing_pct=sp,
                stop_buffer_levels=2,
                trend_filter="none",
                use_sma_filter=True,
                trailing_anchor=False
            )
            res = sim.backtest(bundle)
            print(f"{split_name:<10} | {sp*100:4.1f}%   | {res['total_trades']:<8} | {res['tp_trades']:<6} | {res['win_rate']:5.1f}%   | {res['hpr']:+7.2f}%  | {res['max_drawdown']:7.2f}%   | {res['daily_sharpe']:6.2f} | {res['avg_invested_pct']:5.1f}%")
            exp1_results.append({"split": split_name, "spacing": sp, **res})

    print("\n" + "=" * 95)
    print("EXPERIMENT 2: PORTFOLIO BREADTH EXPANSION (k = 4 -> 6 -> 8 -> 10 stocks)")
    print("Fixed Spacing = 1.2%, N = 16 levels, Lookback = 30d, Rebalance = 15d")
    print("=" * 95)
    print(f"{'Split':<10} | {'k stocks':<8} | {'Trades':<8} | {'TPs':<6} | {'WinRate':<8} | {'HPR (%)':<9} | {'MaxDD (%)':<10} | {'Sharpe':<7} | {'Avg Inv %':<10}")
    print("-" * 95)

    k_list = [4, 6, 8, 10]
    for split_name, bundle in splits:
        for k_val in k_list:
            sim = HighFrequencyERGridBacktest(
                capital=1_000_000_000,
                initial_spot_capital=1_000_000_000,
                broker_fee=0.0015,
                sell_tax=0.0010,
                slippage=0.0005,
                selection_lookback=30,
                selection_rebalance_days=15,
                top_k=k_val,
                n_levels=16,
                grid_spacing_pct=0.012,
                stop_buffer_levels=2,
                trend_filter="none",
                use_sma_filter=True,
                trailing_anchor=False
            )
            res = sim.backtest(bundle)
            print(f"{split_name:<10} | {k_val:<8} | {res['total_trades']:<8} | {res['tp_trades']:<6} | {res['win_rate']:5.1f}%   | {res['hpr']:+7.2f}%  | {res['max_drawdown']:7.2f}%   | {res['daily_sharpe']:6.2f} | {res['avg_invested_pct']:5.1f}%")

    print("\n" + "=" * 95)
    print("EXPERIMENT 3: DYNAMIC TRAILING ANCHOR vs STATIC REBALANCE ANCHOR")
    print("Evaluating whether dynamic trailing anchor increases trades during trend shifts")
    print("=" * 95)
    print(f"{'Split':<10} | {'Anchor Mode':<15} | {'Trades':<8} | {'TPs':<6} | {'WinRate':<8} | {'HPR (%)':<9} | {'MaxDD (%)':<10} | {'Sharpe':<7} | {'Avg Inv %':<10}")
    print("-" * 95)

    for split_name, bundle in splits:
        for trailing in [False, True]:
            mode_lbl = "Dynamic Trailing" if trailing else "Static Rebalance"
            sim = HighFrequencyERGridBacktest(
                capital=1_000_000_000,
                initial_spot_capital=1_000_000_000,
                broker_fee=0.0015,
                sell_tax=0.0010,
                slippage=0.0005,
                selection_lookback=30,
                selection_rebalance_days=15,
                top_k=4,
                n_levels=16,
                grid_spacing_pct=0.015,
                stop_buffer_levels=2,
                trend_filter="none",
                use_sma_filter=True,
                trailing_anchor=trailing
            )
            res = sim.backtest(bundle)
            print(f"{split_name:<10} | {mode_lbl:<15} | {res['total_trades']:<8} | {res['tp_trades']:<6} | {res['win_rate']:5.1f}%   | {res['hpr']:+7.2f}%  | {res['max_drawdown']:7.2f}%   | {res['daily_sharpe']:6.2f} | {res['avg_invested_pct']:5.1f}%")

if __name__ == "__main__":
    run_experiment_suite()
