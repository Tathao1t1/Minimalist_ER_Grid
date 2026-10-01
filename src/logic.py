import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def kaufman_er(prices: np.ndarray) -> float:
    """
    Kaufman Efficiency Ratio (ER) = Direction / Volatility
    Direction = |Price_t - Price_0|
    Volatility = Sum(|Price_i - Price_{i-1}|)
    Returns value in [0.0, 1.0]. Lower values indicate oscillating mean-reverting regimes.
    """
    if len(prices) < 2:
        return 1.0
    direction = abs(float(prices[-1]) - float(prices[0]))
    volatility = float(np.sum(np.abs(np.diff(prices))))
    return direction / volatility if volatility > 0 else 1.0

def get_settlement_dt(trade_dt: datetime) -> datetime:
    """
    HOSE T+2.5 Settlement Availability Rule:
    Shares purchased on day T become eligible for sale at 13:00 PM on T+2.
    Skips non-trading weekend days.
    """
    d = trade_dt.date()
    added = 0
    while added < 2:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return datetime.combine(d, datetime.strptime("13:00", "%H:%M").time())

def build_zero_overlap_whitelist(bars_df, lookback_days=40, rebalance_days=10, top_k=4, trend_filter="none"):
    """
    Point-in-Time constituent selection based on Kaufman Efficiency Ratio (ER).
    Evaluates rolling historical window [t - lookback_days, t] with zero forward leakage.
    """
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
    
    whitelist = {}
    for i in range(lookback_days, len(all_dates), rebalance_days):
        rebal_date = all_dates[i]
        hist_dates = all_dates[i - lookback_days : i]
        candidates = []
        for ticker in piv_close.columns:
            c_hist = piv_close.loc[hist_dates, ticker].dropna()
            if len(c_hist) < lookback_days * 0.8:
                continue
            er_val = kaufman_er(c_hist.values)
            candidates.append((ticker, er_val))
            
        # Select lowest ER (most mean-reverting oscillating stocks)
        candidates.sort(key=lambda x: x[1])
        whitelist[rebal_date] = [c[0] for c in candidates[:top_k]]
        
    return whitelist

class MinimalistERGridBacktest:
    """
    Pure Minimalist Kaufman ER Grid Trading Engine.
    Executes true geometric grid recycling with strict T+2.5 settlement enforcement.
    """
    def __init__(
        self,
        capital=1_000_000_000,
        initial_spot_capital=1_000_000_000,
        broker_fee=0.0015,
        sell_tax=0.0010,
        slippage=0.0005,
        selection_lookback=40,
        selection_rebalance_days=10,
        top_k=4,
        n_levels=18,
        grid_spacing_pct=0.018,
        stop_buffer_levels=2,
        trend_filter="none",
        **kwargs
    ):
        self.capital = float(capital)
        self.initial_spot_capital = float(initial_spot_capital)
        self.broker_fee = float(broker_fee)
        self.sell_tax = float(sell_tax)
        self.slippage = float(slippage)
        self.selection_lookback = int(selection_lookback)
        self.selection_rebalance_days = int(selection_rebalance_days)
        self.top_k = int(top_k)
        self.n_levels = int(n_levels)
        self.grid_spacing_pct = float(grid_spacing_pct)
        self.stop_buffer_levels = int(stop_buffer_levels)
        self.trend_filter = str(trend_filter)
        
        self.trades_df = pd.DataFrame()
        self.equity_series = pd.Series(dtype=float)
        self.log_file = "trade_log.txt"

    def backtest(self, data_bundle):
        bars_df = data_bundle["bars"].copy()
        if bars_df["close"].max() < 1000:
            for c in ["open", "high", "low", "close"]:
                bars_df[c] *= 1000.0
        bars_df = bars_df.sort_values(["bar_close", "tickersymbol"]).reset_index(drop=True)
        
        # 1. Build Whitelist
        whitelist_by_date = build_zero_overlap_whitelist(
            bars_df,
            lookback_days=self.selection_lookback,
            rebalance_days=self.selection_rebalance_days,
            top_k=self.top_k,
            trend_filter=self.trend_filter
        )
        
        # 2. Compute 50-period SMA anchor per ticker
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
        
        wl_dates = sorted(whitelist_by_date.keys())
        cur_wl = []
        next_wl_idx = 0
        
        for ts, bar_group in bars_df.groupby("bar_close", sort=True):
            bar_group = bar_group.set_index("tickersymbol")
            cur_date = ts.date()
            
            if next_wl_idx < len(wl_dates) and cur_date >= wl_dates[next_wl_idx]:
                cur_wl = whitelist_by_date[wl_dates[next_wl_idx]]
                next_wl_idx += 1
                
            # PASS 1: EXIT / SELL EVALUATION
            for ticker in list(positions.keys()):
                if ticker not in bar_group.index:
                    continue
                bar = bar_group.loc[ticker]
                bar_h, bar_l, bar_c = float(bar["high"]), float(bar["low"]), float(bar["close"])
                grid_info = grids.get(ticker)
                floor_stop = grid_info["stop"] if grid_info else 0.0
                is_floor_hit = (bar_l <= floor_stop) and (floor_stop > 0)
                
                to_remove = []
                lvl_dict = positions[ticker]
                for lvl, pos in lvl_dict.items():
                    can_exit = (ts >= pos["settlement"])
                    if is_floor_hit:
                        fill = max(min(float(bar["open"]), floor_stop), floor_stop * 0.93)
                        to_remove.append((lvl, fill, True, "floor_stop"))
                        continue
                    if bar_h >= pos["tp_price"] and can_exit:
                        to_remove.append((lvl, pos["tp_price"], False, "target"))
                        continue
                    if ticker not in cur_wl and can_exit and (grid_info is None):
                        to_remove.append((lvl, bar_c, True, "rotation_exit"))
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
                    
                if is_floor_hit:
                    positions.pop(ticker, None)
                    if ticker in grids:
                        del grids[ticker]
                elif len(lvl_dict) == 0 and ticker not in cur_wl:
                    positions.pop(ticker, None)
                    if ticker in grids:
                        del grids[ticker]

            # PASS 2: GRID INITIALIZATION
            for ticker in list(grids.keys()):
                if ticker not in cur_wl and (ticker not in positions or len(positions[ticker]) == 0):
                    del grids[ticker]
                    
            avail_slots = self.top_k - len(grids)
            if avail_slots > 0 and len(cur_wl) > 0:
                for ticker in cur_wl:
                    if ticker in grids or ticker not in bar_group.index:
                        continue
                    bar = bar_group.loc[ticker]
                    sma_val = anchors[ticker].get(ts, np.nan)
                    if np.isnan(sma_val) or abs(float(bar["close"]) - sma_val) / sma_val > 0.03:
                        continue
                    spacing = sma_val * self.grid_spacing_pct
                    levels = [round(sma_val - k * spacing, 2) for k in range(1, self.n_levels + 1)]
                    tps = [round(sma_val - (k - 1) * spacing, 2) for k in range(1, self.n_levels + 1)]
                    stop_px = sma_val - (self.n_levels + self.stop_buffer_levels) * spacing
                    grids[ticker] = {"anchor": sma_val, "levels": levels, "tps": tps, "stop": stop_px}
                    positions.setdefault(ticker, {})
                    avail_slots -= 1
                    if avail_slots <= 0:
                        break

            # PASS 3: BUY LIMIT FILL EVALUATION
            for ticker, g in grids.items():
                if ticker not in bar_group.index:
                    continue
                bar_l = float(bar_group.loc[ticker, "low"])
                lvl_dict = positions.setdefault(ticker, {})
                for lvl_idx in range(1, self.n_levels + 1):
                    if lvl_idx in lvl_dict:
                        continue
                    buy_px = g["levels"][lvl_idx - 1]
                    if bar_l > buy_px:
                        continue
                    actual_fill = buy_px * (1.0 + self.slippage)
                    order_shares = max(100, int(round(capital_per_level / actual_fill / 100.0)) * 100)
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
                        "settlement": get_settlement_dt(ts)
                    }
                    
            pos_val = sum(
                sum(p["shares"] * float(bar_group.loc[t]["close"]) for p in lvl_dict.values())
                for t, lvl_dict in positions.items() if t in bar_group.index
            )
            equity_curve.append({"bar_close": ts, "portfolio_value": cash + pos_val})
            
        self.trades_df = pd.DataFrame(completed_trades)
        eq_df = pd.DataFrame(equity_curve)
        eq_series = eq_df.set_index(pd.to_datetime(eq_df["bar_close"]))["portfolio_value"]
        self.equity_series = eq_series
        
        final_val = float(eq_series.iloc[-1])
        net_profit = final_val - self.capital
        hpr = (final_val / self.capital - 1.0) * 100.0
        days = (eq_series.index[-1] - eq_series.index[0]).total_seconds() / 86400.0
        years = max(days / 365.25, 0.01)
        cagr = (((final_val / self.capital) ** (1.0 / years)) - 1.0) * 100.0
        
        dd = (eq_series - eq_series.cummax()) / eq_series.cummax() * 100.0
        max_dd = float(dd.min())
        
        # Drawdown duration in days
        is_in_dd = dd < 0
        dd_starts = is_in_dd & (~is_in_dd.shift(1).fillna(False))
        longest_dd_days = 0
        if is_in_dd.any():
            peaks = eq_series.cummax()
            underwater = (eq_series < peaks)
            cur_days = 0
            max_days = 0
            last_ts = None
            for idx_t, uw in underwater.items():
                if uw:
                    if last_ts is not None:
                        cur_days += (idx_t - last_ts).total_seconds() / 86400.0
                        if cur_days > max_days: max_days = cur_days
                else:
                    cur_days = 0
                last_ts = idx_t
            longest_dd_days = int(round(max_days))
            
        rets = eq_series.pct_change().dropna()
        sharpe = float(rets.mean() / rets.std() * np.sqrt(2016)) if rets.std() > 0 else 0.0
        downside_rets = rets[rets < 0]
        sortino = float(rets.mean() / downside_rets.std() * np.sqrt(2016)) if len(downside_rets) > 0 and downside_rets.std() > 0 else 0.0
        calmar = abs(cagr / max_dd) if max_dd != 0 else 0.0
        
        tp_trades = self.trades_df[self.trades_df["reason"] == "target"] if len(self.trades_df) > 0 else pd.DataFrame()
        drag_trades = self.trades_df[self.trades_df["reason"] != "target"] if len(self.trades_df) > 0 else pd.DataFrame()
        
        tp_pnl = float(tp_trades["pnl"].sum()) if len(tp_trades) > 0 else 0.0
        drag_pnl = float(drag_trades["pnl"].sum()) if len(drag_trades) > 0 else 0.0
        win_rate = (len(tp_trades) / len(self.trades_df) * 100.0) if len(self.trades_df) > 0 else 0.0
        
        return {
            "initial_capital": self.capital,
            "final_capital": final_val,
            "net_profit": net_profit,
            "hpr": hpr,
            "annual_return": cagr,
            "max_drawdown": max_dd,
            "longest_dd_days": longest_dd_days,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "total_trades": len(self.trades_df),
            "tp_trades": len(tp_trades),
            "drag_trades": len(drag_trades),
            "win_rate": win_rate,
            "spot_harvest_pnl": tp_pnl,
            "spot_drag_pnl": drag_pnl,
            "equity_series": eq_series
        }
