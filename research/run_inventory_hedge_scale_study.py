#!/usr/bin/env python3
"""
Dynamic Inventory-Proportional Futures Hedge & Capital Scale Optimizer
Directly addresses Advisor Feedback:
  1. "Rổ cổ phiếu của mình là long liên tục, nên lỗ chủ yếu đến từ hàng tồn khi thị trường đi xuống.
      Thay vì đoán lúc thị trường giảm, em thử short phái sinh theo giá trị hàng tồn:
      hàng tồn càng nhiều thì short càng nhiều. Như vậy ảnh hưởng của thị trường giảm đi mà mình vẫn giữ được phần lãi từ dao động."
  2. "Em thử với vốn 500 triệu và 1 tỷ và 5 tỷ ha để xem scale thế nào.
      Với đạt grid tối ưu vốn luôn, có thể nhiều hơn 18 step."
"""

import os
import sys
import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

curr_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(curr_dir)
for p in [curr_dir, project_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.data_fetcher import prepare_data
from src.logic import build_zero_overlap_whitelist, get_settlement_dt

def run_hedged_grid_simulation(
    bundle,
    vn30f_series,
    capital=1_000_000_000,
    top_k=4,
    n_levels=18,
    grid_spacing_pct=0.018,
    stop_buffer_levels=2,
    hedge_ratio=1.0,
    selection_mode="er_low",
    use_sma_filter=True,
    broker_fee=0.0015,
    sell_tax=0.0010,
    slippage=0.0005,
    futures_friction_per_contract=60_000.0,
    risk_free_rate=0.06
):
    bars_df = bundle["bars"].copy()
    if bars_df["close"].max() < 1000:
        for c in ["open", "high", "low", "close"]:
            bars_df[c] *= 1000.0
    bars_df = bars_df.sort_values(["bar_close", "tickersymbol"]).reset_index(drop=True)
    
    # Align futures series with spot timestamps
    spot_all_ts = sorted(bars_df["bar_close"].unique())
    f_series = vn30f_series.reindex(pd.Index(spot_all_ts)).ffill().bfill()
    
    whitelist_by_date = build_zero_overlap_whitelist(
        bars_df,
        lookback_days=40,
        rebalance_days=10,
        top_k=top_k,
        selection_mode=selection_mode,
        seed=42
    )
    
    anchors = {}
    for ticker, df in bars_df.groupby("tickersymbol"):
        anchors[ticker] = df.sort_values("bar_close").set_index("bar_close")["close"].rolling(50).mean()
        
    capital_per_stock = float(capital) / top_k
    capital_per_level = capital_per_stock / n_levels
    
    cash = float(capital)
    grids = {}
    positions = {}
    completed_trades = []
    
    wl_dates = sorted(whitelist_by_date.keys())
    cur_wl = []
    next_wl_idx = 0
    
    # Futures tracking
    cur_short_contracts = 0
    futures_realized_pnl = 0.0
    last_f_px = None
    
    equity_records = []
    lot_size_violations = 0
    total_order_attempts = 0
    
    for ts, bar_group in bars_df.groupby("bar_close", sort=True):
        bar_group = bar_group.set_index("tickersymbol")
        cur_date = ts.date()
        f_px = float(f_series.loc[ts])
        
        if next_wl_idx < len(wl_dates) and cur_date >= wl_dates[next_wl_idx]:
            cur_wl = whitelist_by_date[wl_dates[next_wl_idx]]
            next_wl_idx += 1
            
        # ── 1. SPOT EXITS ──
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
                    
        # ── 2. SPOT GRID INITIALIZATION ──
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
                    
        # ── 3. SPOT BUY LIMIT MATCHING ──
        for ticker, g in list(grids.items()):
            if ticker not in bar_group.index or g.get("stop_triggered", False):
                continue
            if g.get("active_from_ts") == ts:
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
                order_shares = int(round(raw_shares / 100.0)) * 100
                total_order_attempts += 1
                if order_shares < 100:
                    order_shares = 100
                    lot_size_violations += 1
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
                
        # ── 4. DYNAMIC INVENTORY HEDGE (VN30F) ──
        # Calculate real-time spot inventory market value
        spot_inventory_val = sum(
            sum(p["shares"] * float(bar_group.loc[t, "close"]) for p in lvl_dict.values())
            for t, lvl_dict in positions.items() if t in bar_group.index
        )
        
        # Mark to market futures MTM
        if last_f_px is not None and cur_short_contracts > 0:
            # Short position PnL = - Contracts * (Price_now - Price_last) * 100,000
            f_pnl_delta = - cur_short_contracts * (f_px - last_f_px) * 100_000.0
            futures_realized_pnl += f_pnl_delta
            
        # Target contracts proportional to current spot inventory
        if hedge_ratio > 0 and f_px > 0:
            contract_notional = f_px * 100_000.0
            target_short_contracts = int(round((spot_inventory_val * hedge_ratio) / contract_notional))
        else:
            target_short_contracts = 0
            
        # Contract adjustment transaction cost
        if target_short_contracts != cur_short_contracts:
            contract_diff = abs(target_short_contracts - cur_short_contracts)
            trans_friction = contract_diff * futures_friction_per_contract
            futures_realized_pnl -= trans_friction
            cur_short_contracts = target_short_contracts
            
        last_f_px = f_px
        
        # Total portfolio equity = Cash + Spot Inventory Value + Futures Cumulative PnL
        port_val = cash + spot_inventory_val + futures_realized_pnl
        equity_records.append({
            "bar_close": ts,
            "portfolio_value": port_val,
            "spot_inventory": spot_inventory_val,
            "short_contracts": cur_short_contracts,
            "futures_pnl": futures_realized_pnl
        })
        
    eq_df = pd.DataFrame(equity_records).set_index("bar_close")
    eq_s = eq_df["portfolio_value"]
    hpr = (eq_s.iloc[-1] / float(capital) - 1.0) * 100.0
    cummax = eq_s.cummax()
    dd = (eq_s - cummax) / cummax
    max_dd = float(dd.min()) * 100.0
    rets = eq_s.pct_change().dropna()
    rf_per_bar = risk_free_rate / 2016.0
    excess_mean = float(rets.mean() - rf_per_bar)
    sharpe = float(excess_mean / rets.std() * np.sqrt(2016)) if rets.std() > 0 else 0.0
    
    trades_df = pd.DataFrame(completed_trades)
    tp_trades = trades_df[trades_df["reason"] == "target"] if len(trades_df) > 0 else pd.DataFrame()
    harvest_pnl = float(tp_trades["pnl"].sum()) if len(tp_trades) > 0 else 0.0
    
    return {
        "hpr": hpr,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "roundtrips": len(tp_trades),
        "harvest_pnl": harvest_pnl,
        "futures_pnl": futures_realized_pnl,
        "final_capital": eq_s.iloc[-1],
        "equity_series": eq_s,
        "details_df": eq_df,
        "lot_violations_pct": (lot_size_violations / total_order_attempts * 100.0) if total_order_attempts > 0 else 0.0
    }

def main():
    print("=" * 105)
    print("DYNAMIC INVENTORY-PROPORTIONAL FUTURES HEDGE & CAPITAL SCALE OPTIMIZATION")
    print("Testing 500M, 1B, 5B VND and Grid Step Depths (N=18, 24, 30, 36)")
    print("=" * 105)
    
    cfg_path = os.path.join(project_root, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    f_path = os.path.join(project_root, "data/benchmark/vn30f1m_30m.parquet")
    if not os.path.exists(f_path):
        f_path = "/Users/ttt/Final_Projects_v1/data/benchmark/vn30f1m_30m.parquet"
    f_df = pd.read_parquet(f_path)
    f_df["bar_close"] = pd.to_datetime(f_df["bar_close"])
    vn30f_series = f_df.sort_values("bar_close").set_index("bar_close")["close"]
    
    splits = ["in_sample", "out_sample", "holdout"]
    capitals = [500_000_000, 1_000_000_000, 5_000_000_000]
    cap_labels = {500_000_000: "500M VND", 1_000_000_000: "1.0B VND", 5_000_000_000: "5.0B VND"}
    
    # ── Experiment 1: Unhedged vs. Dynamic Inventory Hedge at 1.0B across splits ──
    print("\n[PART 1: UNHEDGED VS. DYNAMIC INVENTORY HEDGE AT 1.0B BASELINE]")
    results_part1 = []
    for split in splits:
        b = prepare_data(config, split)
        # Unhedged
        res_unhedged = run_hedged_grid_simulation(b, vn30f_series, capital=1e9, n_levels=18, grid_spacing_pct=0.018, hedge_ratio=0.0)
        # Hedged (Short proportional to spot inventory)
        res_hedged = run_hedged_grid_simulation(b, vn30f_series, capital=1e9, n_levels=18, grid_spacing_pct=0.018, hedge_ratio=1.0)
        results_part1.append({"split": split, "mode": "Unhedged (Pure Spot Grid)", **res_unhedged})
        results_part1.append({"split": split, "mode": "Dynamic Inventory Hedge (VN30F)", **res_hedged})
        print(f"  Split: {split:<11} | Unhedged Return: {res_unhedged['hpr']:+6.2f}% (DD: {res_unhedged['max_drawdown']:5.1f}%) | Hedged Return: {res_hedged['hpr']:+6.2f}% (DD: {res_hedged['max_drawdown']:5.1f}%) | Futures PnL: {res_hedged['futures_pnl']/1e6:+6.1f}M")
        
    # ── Experiment 2: Capital Scaling Analysis (500M vs 1B vs 5B) in Holdout & In-Sample ──
    print("\n[PART 2: CAPITAL SCALING STUDY (500M, 1B, 5B VND) WITH INVENTORY HEDGE]")
    results_part2 = []
    for cap in capitals:
        for split in ["in_sample", "holdout"]:
            b = prepare_data(config, split)
            res = run_hedged_grid_simulation(b, vn30f_series, capital=cap, n_levels=18, grid_spacing_pct=0.018, hedge_ratio=1.0)
            results_part2.append({
                "capital": cap_labels[cap],
                "split": split,
                "hpr": res["hpr"],
                "max_dd": res["max_drawdown"],
                "sharpe": res["sharpe_ratio"],
                "roundtrips": res["roundtrips"],
                "harvest_pnl": res["harvest_pnl"],
                "futures_pnl": res["futures_pnl"],
                "lot_violation_pct": res["lot_violations_pct"],
                "equity_series": res["equity_series"]
            })
            print(f"  Capital: {cap_labels[cap]:<9} | Split: {split:<10} | Return: {res['hpr']:+6.2f}% | MaxDD: {res['max_drawdown']:5.1f}% | Lot Violations: {res['lot_violations_pct']:4.1f}% | Futures PnL: {res['futures_pnl']/1e6:+7.1f}M")
            
    # ── Experiment 3: Step Depth Optimization (N = 18, 24, 30, 36) on 1B and 5B VND ──
    print("\n[PART 3: GRID LEVEL DEPTH OPTIMIZATION (N = 18, 24, 30, 36) ON 1B & 5B]")
    results_part3 = []
    for cap in [1_000_000_000, 5_000_000_000]:
        for n_lvl in [18, 24, 30, 36]:
            # Adjust spacing so total channel depth is well-calibrated (e.g. 1.2% to 1.8%)
            sp = 0.015 if n_lvl > 18 else 0.018
            b = prepare_data(config, "in_sample")
            res_is = run_hedged_grid_simulation(b, vn30f_series, capital=cap, n_levels=n_lvl, grid_spacing_pct=sp, hedge_ratio=1.0)
            b_ho = prepare_data(config, "holdout")
            res_ho = run_hedged_grid_simulation(b_ho, vn30f_series, capital=cap, n_levels=n_lvl, grid_spacing_pct=sp, hedge_ratio=1.0)
            results_part3.append({
                "capital": cap_labels[cap],
                "n_levels": n_lvl,
                "spacing": f"{sp*100:.1f}%",
                "is_hpr": res_is["hpr"],
                "is_mdd": res_is["max_drawdown"],
                "ho_hpr": res_ho["hpr"],
                "ho_mdd": res_ho["max_drawdown"],
                "ho_roundtrips": res_ho["roundtrips"]
            })
            print(f"  Capital: {cap_labels[cap]:<8} | N={n_lvl:2d} ({sp*100:.1f}%) | IS Ret: {res_is['hpr']:+6.2f}% (DD: {res_is['max_drawdown']:5.1f}%) | Holdout Ret: {res_ho['hpr']:+6.2f}% (DD: {res_ho['max_drawdown']:5.1f}%) | Roundtrips: {res_ho['roundtrips']}")

    # ── Generate Multi-Panel Visualizations ──
    fig, axes = plt.subplots(1, 3, figsize=(21, 6.5), sharey=False)
    split_titles = {
        "in_sample": "In-Sample Secular Bear (2021–2023)",
        "out_sample": "Out-of-Sample Recovery (2024)",
        "holdout": "Forward Blind Holdout (2025–2026)"
    }
    
    for idx, split in enumerate(splits):
        ax = axes[idx]
        b = prepare_data(config, split)
        res_u = run_hedged_grid_simulation(b, vn30f_series, capital=1e9, n_levels=18, grid_spacing_pct=0.018, hedge_ratio=0.0)
        res_h = run_hedged_grid_simulation(b, vn30f_series, capital=1e9, n_levels=18, grid_spacing_pct=0.018, hedge_ratio=1.0)
        
        eq_u = (res_u["equity_series"] / 1e9) * 100.0
        eq_h = (res_h["equity_series"] / 1e9) * 100.0
        
        ax.plot(eq_u.index, eq_u.values, label=f"Unhedged Spot Grid: {res_u['hpr']:+.2f}% (DD {res_u['max_drawdown']:.1f}%)", color="#DC2626", linestyle="--", linewidth=1.8)
        ax.plot(eq_h.index, eq_h.values, label=f"Dynamic Inventory Hedge: {res_h['hpr']:+.2f}% (DD {res_h['max_drawdown']:.1f}%)", color="#059669", linestyle="-", linewidth=2.0)
        
        ax.set_title(split_titles[split], fontsize=12.5, fontweight="bold", pad=10)
        ax.axhline(100.0, color="#9CA3AF", linestyle="--", alpha=0.6, linewidth=1)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.set_ylabel("Portfolio Equity (Normalized Base = 100)", fontsize=10)
        ax.legend(loc="best", fontsize=8.8, framealpha=0.92)
        
    plt.suptitle("Impact of Dynamic Inventory-Proportional Futures Hedging on Portfolio Equity", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    
    os.makedirs(os.path.join(project_root, "images"), exist_ok=True)
    out_img = os.path.join(project_root, "images/inventory_hedge_scale_comparison.png")
    plt.savefig(out_img, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\nSaved inventory hedge comparison chart to: {out_img}")
    
    # Save results to a structured markdown file for review
    report_path = os.path.join(curr_dir, "HEDGE_AND_SCALE_REPORT.md")
    with open(report_path, "w") as f:
        f.write("# Báo cáo Thử nghiệm: Phòng vệ Hàng tồn Phái sinh (VN30F) & Tối ưu Scale Vốn\n\n")
        f.write("Dựa trên phản hồi và gợi ý của Advisor:\n")
        f.write("1. **Short phái sinh theo giá trị hàng tồn:** Tích lũy hàng tồn càng nhiều thì short càng nhiều, không cần đoán đỉnh đáy.\n")
        f.write("2. **Thử nghiệm scale vốn:** 500 triệu, 1 tỷ và 5 tỷ VND.\n")
        f.write("3. **Tối ưu bước grid:** Nâng số cấp grid (N = 18, 24, 30, 36) để tối ưu hiệu suất sử dụng vốn.\n\n")
        f.write("![Inventory Hedge Comparison](images/inventory_hedge_scale_comparison.png)\n\n")
        f.write("## 1. So sánh Hiệu quả Phòng vệ Hàng tồn (Vốn 1.0 Tỷ, N=18)\n\n")
        f.write("| Giai đoạn Thị trường | Chế độ Giao dịch | Lợi nhuận (HPR) | Max Drawdown | Sharpe (Rf=6%) | Roundtrips Khớp | PnL Harvest Cơ sở | PnL Phái sinh VN30F |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for r in results_part1:
            f.write(f"| {r['split']} | {r['mode']} | {r['hpr']:+.2f}% | {r['max_drawdown']:.2f}% | {r['sharpe_ratio']:.3f} | {r['roundtrips']} | {r['harvest_pnl']:+,.0f} VND | {r['futures_pnl']:+,.0f} VND |\n")
            
        f.write("\n## 2. Thử nghiệm Scale Vốn (500M, 1B, 5B VND)\n\n")
        f.write("| Quy mô Vốn | Giai đoạn | Lợi nhuận (HPR) | Max Drawdown | Sharpe (Rf=6%) | Tỷ lệ Vi phạm Lot 100 CP | PnL Harvest | PnL Phái sinh |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for r in results_part2:
            f.write(f"| {r['capital']} | {r['split']} | {r['hpr']:+.2f}% | {r['max_dd']:.2f}% | {r['sharpe']:.3f} | {r['lot_violation_pct']:.1f}% | {r['harvest_pnl']:+,.0f} VND | {r['futures_pnl']:+,.0f} VND |\n")
            
        f.write("\n## 3. Thử nghiệm Tối ưu Số bước Grid (N = 18, 24, 30, 36)\n\n")
        f.write("| Quy mô Vốn | Số bước (N) | Spacing (%) | In-Sample Return | In-Sample MaxDD | Holdout Return | Holdout MaxDD | Holdout Roundtrips |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for r in results_part3:
            f.write(f"| {r['capital']} | {r['n_levels']} | {r['spacing']} | {r['is_hpr']:+.2f}% | {r['is_mdd']:.2f}% | {r['ho_hpr']:+.2f}% | {r['ho_mdd']:.2f}% | {r['ho_roundtrips']} |\n")
            
    print(f"\nWritten full investigation report to: {report_path}")

if __name__ == "__main__":
    main()
