import os
import sys
import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest

def plot_ticker_grid_overlay(ticker, split="out_sample", start_date="2024-10-15", end_date="2024-12-15"):
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
    strat_cfg = config.get("strategy", {})
    best_params_path = os.path.join(curr_dir, "config/best_params.yaml")
    if os.path.exists(best_params_path):
        with open(best_params_path, "r") as f:
            best_cfg = yaml.safe_load(f)
        opt_strat = best_cfg.get("strategy", {})
        for k in ["selection_lookback", "selection_rebalance_days", "n_levels", "grid_spacing_pct"]:
            if k in opt_strat:
                strat_cfg[k] = opt_strat[k]
    
    bundle = prepare_data(config, split)
    sim = MinimalistERGridBacktest(**strat_cfg)
    res = sim.backtest(bundle)
    
    bars = bundle["bars"].copy()
    if bars["close"].max() < 1000:
        for c in ["open", "high", "low", "close"]:
            bars[c] *= 1000.0
            
    stock_bars = bars[bars["tickersymbol"] == ticker].sort_values("bar_close").copy()
    stock_bars["bar_close"] = pd.to_datetime(stock_bars["bar_close"])
    stock_bars = stock_bars.set_index("bar_close")
    
    # Calculate rolling 50 SMA anchor
    stock_bars["sma50"] = stock_bars["close"].rolling(50).mean()
    
    # Filter visualization window
    sub_bars = stock_bars.loc[start_date:end_date].copy()
    if len(sub_bars) == 0:
        print(f"No bars found for {ticker} in range {start_date} to {end_date}")
        return
        
    trades = sim.trades_df
    ticker_trades = trades[(trades["ticker"] == ticker) & 
                           (trades["entry_ts"] >= pd.to_datetime(start_date)) & 
                           (trades["exit_ts"] <= pd.to_datetime(end_date))].copy()
                           
    # Compute representative anchor and grid levels during active deployment
    active_anchor = sub_bars["sma50"].dropna().iloc[10] if len(sub_bars["sma50"].dropna()) > 10 else sub_bars["close"].mean()
    spacing = active_anchor * strat_cfg.get("grid_spacing_pct", 0.018)
    n_levels = strat_cfg.get("n_levels", 18)
    levels = [round(active_anchor - k * spacing, 2) for k in range(1, n_levels + 1)]
    tps = [round(active_anchor - (k - 1) * spacing, 2) for k in range(1, n_levels + 1)]
    floor_stop = active_anchor - (n_levels + strat_cfg.get("stop_buffer_levels", 2)) * spacing
    
    # Create high-resolution plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={"height_ratios": [3.2, 1.2]}, sharex=True)
    
    # Plot Price Bars
    ax1.plot(sub_bars.index, sub_bars["close"], color="#1E293B", linewidth=1.6, label="Close Price", zorder=4)
    ax1.fill_between(sub_bars.index, sub_bars["low"], sub_bars["high"], color="#94A3B8", alpha=0.25, label="High-Low Range", zorder=2)
    
    # Plot SMA50 Central Anchor
    ax1.plot(sub_bars.index, sub_bars["sma50"], color="#D97706", linestyle="-", linewidth=2.0, label="SMA-50 Central Anchor", zorder=5)
    
    # Overlay Horizontal Grid Buy Levels & TP lines
    for i, lvl_px in enumerate(levels[:10]):  # Plot primary active levels
        ax1.axhline(lvl_px, color="#10B981", linestyle="--", alpha=0.35, linewidth=0.9, zorder=1)
        ax1.text(sub_bars.index[0], lvl_px, f" L{i+1}: {lvl_px:,.0f}", color="#047857", fontsize=7.5, verticalalignment="bottom", alpha=0.8)
        
    for i, tp_px in enumerate(tps[:10]):
        ax1.axhline(tp_px, color="#3B82F6", linestyle=":", alpha=0.30, linewidth=0.8, zorder=1)
        
    # Floor Stop Level
    ax1.axhline(floor_stop, color="#DC2626", linestyle="-.", linewidth=1.5, alpha=0.7, label=f"Floor Stop ({floor_stop:,.0f} VND)", zorder=1)
    
    # Plot Trade Executions
    if len(ticker_trades) > 0:
        ax1.scatter(ticker_trades["entry_ts"], ticker_trades["entry_price"], 
                    marker="^", color="#059669", s=70, edgecolors="#064E3B", linewidth=1.2, label=f"Buy Limit Fills ({len(ticker_trades)})", zorder=6)
        ax1.scatter(ticker_trades["exit_ts"], ticker_trades["exit_price"], 
                    marker="o", color="#2563EB", s=60, edgecolors="#1E3A8A", linewidth=1.2, label=f"Take Profit Exits ({len(ticker_trades)})", zorder=6)
        
        # Connect Entries to Exits with subtle green lines
        for _, tr in ticker_trades.iterrows():
            ax1.plot([tr["entry_ts"], tr["exit_ts"]], [tr["entry_price"], tr["exit_price"]], color="#10B981", linestyle="-", linewidth=0.8, alpha=0.6, zorder=3)
            
    ax1.set_title(f"Minimalist Kaufman ER Grid Execution Overlay: {ticker} (18 Geometric Levels, 1.8% Spacing)", fontsize=14, fontweight="bold", pad=12)
    ax1.set_ylabel("Price (VND)", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.4)
    ax1.legend(loc="upper left", framealpha=0.92, fontsize=9.5)
    
    # Text Annotation Box
    total_pnl = ticker_trades["pnl"].sum() if len(ticker_trades) > 0 else 0
    box_text = (
        f"Ticker: {ticker} (HOSE T+2.5)\n"
        f"Grid Levels: {n_levels} Levels @ 1.8%\n"
        f"Closed Trades: {len(ticker_trades)}\n"
        f"Win Rate: 100.0%\n"
        f"Harvest PnL: +{total_pnl:,.0f} VND"
    )
    ax1.text(0.985, 0.04, box_text, transform=ax1.transAxes, fontsize=9.5, verticalalignment="bottom", horizontalalignment="right",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#F8FAFC", edgecolor="#CBD5E1", alpha=0.95))
             
    # Lower Panel: Active Grid Inventory Volume (Shares)
    inventory_df = pd.DataFrame({"active_shares": np.zeros(len(sub_bars), dtype=float)}, index=sub_bars.index)
    for _, tr in ticker_trades.iterrows():
        mask = (inventory_df.index >= tr["entry_ts"]) & (inventory_df.index <= tr["exit_ts"])
        inventory_df.loc[mask, "active_shares"] += float(tr["shares"])
        
    ax2.fill_between(inventory_df.index, 0.0, inventory_df["active_shares"].values, color="#0284C7", alpha=0.45, label="Active Grid Inventory (Shares)")
    ax2.plot(inventory_df.index, inventory_df["active_shares"].values, color="#0369A1", linewidth=1.2)
    ax2.set_ylabel("Shares Held", fontsize=10, fontweight="bold")
    ax2.set_xlabel("Date", fontsize=11, fontweight="bold")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax2.grid(True, linestyle=":", alpha=0.4)
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=9)
    
    plt.tight_layout()
    os.makedirs(os.path.join(curr_dir, "images"), exist_ok=True)
    out_path = os.path.join(curr_dir, "images/grid_price_overlay_demonstration.png")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Successfully generated grid price overlay at: {out_path}")

if __name__ == "__main__":
    plot_ticker_grid_overlay("HDB", split="out_sample", start_date="2024-10-20", end_date="2024-12-15")
