import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

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

def get_settlement_dt(trade_dt: datetime, trading_days=None) -> datetime:
    """
    HOSE T+2.5 Settlement Availability Rule:
    Shares purchased on day T become eligible for sale at 13:00 PM on T+2.
    Skips non-trading days (weekends and official Vietnamese holidays via trading calendar).
    """
    if trading_days is not None:
        d = trade_dt.date()
        idx = np.searchsorted(trading_days, d)
        s_idx = min(idx + 2, len(trading_days) - 1)
        return datetime.combine(trading_days[s_idx], datetime.strptime("13:00", "%H:%M").time())
    else:
        d = trade_dt.date()
        added = 0
        while added < 2:
            d += timedelta(days=1)
            if d.weekday() < 5:
                added += 1
        return datetime.combine(d, datetime.strptime("13:00", "%H:%M").time())

def build_zero_overlap_whitelist(
    bars_df,
    lookback_days=40,
    rebalance_days=10,
    top_k=4,
    trend_filter="none",
    selection_mode="er_low",
    seed=42,
    use_sma_filter=True
):
    """
    Point-in-Time constituent selection based on Kaufman Efficiency Ratio (ER).
    Evaluates rolling historical window [t - lookback_days, t] with zero forward leakage.
    Implements README §3 Rule 1:
      1. Evaluates 40-day rolling ER.
      2. Filters for stocks within ±3% of 50-bar SMA fair-value anchor.
      3. Ranks qualifying equities by ER and selects top-K constituents.
    """
    daily_records = []
    ticker_history = {}
    for ticker, df in bars_df.groupby("tickersymbol"):
        df = df.sort_values("bar_close").copy()
        if df["close"].max() < 1000:
            for c in ["open", "high", "low", "close"]:
                df[c] *= 1000.0
        df["date"] = df["bar_close"].dt.date
        df["sma50"] = df["close"].rolling(50).mean()
        ticker_history[ticker] = {
            "dates": df["date"].values,
            "close": df["close"].values,
            "sma50": df["sma50"].values
        }
        daily = df.groupby("date").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).reset_index()
        daily["tickersymbol"] = ticker
        daily_records.append(daily)
        
    daily_df = pd.concat(daily_records).sort_values(["date", "tickersymbol"]).reset_index(drop=True)
    all_dates = sorted(daily_df["date"].unique())
    piv_close = daily_df.pivot(index="date", columns="tickersymbol", values="close").ffill()
    
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
            er_val = kaufman_er(c_hist.values)
            
            sma_pass = True
            if use_sma_filter:
                th = ticker_history.get(ticker)
                if th is not None:
                    # Fix lookahead: side="left" - 1 gets the prior trading day's 15:00 close before rebalance day opens
                    mask_idx = np.searchsorted(th["dates"], rebal_date, side="left") - 1
                    if mask_idx >= 50:
                        last_c = th["close"][mask_idx]
                        sma_v = th["sma50"][mask_idx]
                        if not np.isnan(sma_v) and sma_v > 0:
                            sma_pass = (abs(last_c - sma_v) / sma_v <= 0.03)
                        else:
                            sma_pass = False
                    else:
                        sma_pass = False
                else:
                    sma_pass = False
                    
            candidates.append((ticker, er_val, sma_pass))
            
        if use_sma_filter:
            qual = [c for c in candidates if c[2]]
            if len(qual) >= top_k:
                qual_pool = qual
            else:
                rem = [c for c in candidates if not c[2]]
                rem.sort(key=lambda x: x[1])
                qual_pool = qual + rem[:(top_k - len(qual))]
        else:
            qual_pool = candidates
            
        if selection_mode == "er_low":
            qual_pool.sort(key=lambda x: x[1])
            whitelist[rebal_date] = [c[0] for c in qual_pool[:top_k]]
        elif selection_mode == "er_high":
            qual_pool.sort(key=lambda x: x[1], reverse=True)
            whitelist[rebal_date] = [c[0] for c in qual_pool[:top_k]]
        elif selection_mode == "random":
            valid_tickers = [c[0] for c in qual_pool]
            if len(valid_tickers) >= top_k:
                chosen = rng.choice(valid_tickers, size=top_k, replace=False).tolist()
            else:
                chosen = valid_tickers
            whitelist[rebal_date] = chosen
        else:
            qual_pool.sort(key=lambda x: x[1])
            whitelist[rebal_date] = [c[0] for c in qual_pool[:top_k]]
        
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
        selection_mode="er_low",
        seed=42,
        use_sma_filter=True,
        risk_free_rate=0.06,
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
        self.selection_mode = str(selection_mode)
        self.seed = int(seed)
        self.use_sma_filter = bool(use_sma_filter)
        self.risk_free_rate = float(risk_free_rate)
        
        self.trades_df = pd.DataFrame()
        self.equity_series = pd.Series(dtype=float)
        self.log_file = "trade_log.txt"

    def backtest(self, data_bundle):
        bars_df = data_bundle["bars"].copy()
        if bars_df["close"].max() < 1000:
            for c in ["open", "high", "low", "close"]:
                bars_df[c] *= 1000.0
        bars_df = bars_df.sort_values(["bar_close", "tickersymbol"]).reset_index(drop=True)
        
        # Precompute trading days array for institutional settlement calendar (A-12)
        trading_days = np.array(sorted(bars_df["bar_close"].dt.date.unique()))
        
        # 1. Build Whitelist with Rule 1: SMA proximity filter first, then ER ranking (A-8)
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
                
            # PASS 1: EXIT / SELL EVALUATION
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
                    
                    # 1. Position previously hit stop and was awaiting settlement (HOSE T+2.5)
                    if pos.get("pending_floor_stop", False):
                        if can_exit:
                            fill = bar_o  # Sells immediately at Open of settlement bar
                            to_remove.append((lvl, fill, True, "settled_floor_stop"))
                        continue

                    # 2. Floor stop hit during current bar
                    if is_floor_hit:
                        if ticker in grids:
                            grids[ticker]["stop_triggered"] = True
                        if can_exit:
                            fill = min(bar_o, floor_stop)
                            to_remove.append((lvl, fill, True, "floor_stop"))
                        else:
                            # Cannot exit before settlement on HOSE! Mark pending
                            pos["pending_floor_stop"] = True
                        continue

                    # 3. Take-Profit Exit (requires settlement)
                    if bar_h >= pos["tp_price"] and can_exit:
                        to_remove.append((lvl, pos["tp_price"], False, "target"))
                        continue

                    # 4. Rotation Exit (requires settlement, A-7)
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
                        "active_from_ts": ts  # Limit orders active only starting from next bar t+1
                    }
                    positions.setdefault(ticker, {})
                    avail_slots -= 1
                    if avail_slots <= 0:
                        break

            # PASS 3: BUY LIMIT FILL EVALUATION
            for ticker, g in list(grids.items()):
                if ticker not in bar_group.index:
                    continue
                # Rotation discipline: Never place/execute buys on off-whitelist tickers (A-7)
                if ticker not in cur_wl:
                    continue
                # Block new buys if floor stop was triggered (A-10)
                if g.get("stop_triggered", False):
                    continue
                # Order placement lag: Newly deployed grid at close of ts only active from bar t+1
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
                        
                    # Favorable Gap Fill at open (A-14)
                    fill_base = bar_o if bar_o <= buy_px else buy_px
                    actual_fill = fill_base * (1.0 + self.slippage)
                    
                    # Tranche sizing strictly adhering to floor formula (A-13)
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
        bars_per_year = 252.0 * 9.0  # 9 30-minute bars per day on HOSE (A-5)
        rf_per_bar = self.risk_free_rate / bars_per_year
        excess_mean = float(rets.mean() - rf_per_bar)
        sharpe = float(excess_mean / rets.std() * np.sqrt(bars_per_year)) if rets.std() > 0 else 0.0
        downside_rets = rets[rets < rf_per_bar] - rf_per_bar
        sortino = float(excess_mean / downside_rets.std() * np.sqrt(bars_per_year)) if len(downside_rets) > 0 and downside_rets.std() > 0 else 0.0
        
        # Daily resampled Sharpe (institutional quantitative standard)
        eq_daily = eq_series.resample("D").last().dropna()
        daily_rets = eq_daily.pct_change().dropna()
        rf_daily = self.risk_free_rate / 252.0
        daily_excess = daily_rets.mean() - rf_daily
        daily_sharpe = float(daily_excess / daily_rets.std() * np.sqrt(252)) if (len(daily_rets) > 0 and daily_rets.std() > 0) else 0.0
        
        calmar = (cagr / abs(max_dd)) if max_dd != 0 else 0.0  # Preserves sign for losses (A-15)
        
        # Floor-stop trade lots vs distinct liquidation episodes (A-3)
        tp_trades = self.trades_df[self.trades_df["reason"] == "target"] if len(self.trades_df) > 0 else pd.DataFrame()
        rot_trades = self.trades_df[self.trades_df["reason"].str.contains("rotation")] if len(self.trades_df) > 0 else pd.DataFrame()
        stop_trades = self.trades_df[self.trades_df["reason"].str.contains("floor_stop")] if len(self.trades_df) > 0 else pd.DataFrame()
        
        if len(stop_trades) > 0:
            stop_trades_copy = stop_trades.copy()
            stop_trades_copy["exit_date"] = pd.to_datetime(stop_trades_copy["exit_ts"]).dt.date
            stop_episodes = int(len(stop_trades_copy.groupby(["ticker", "exit_date"])))
        else:
            stop_episodes = 0
            
        tp_pnl = float(tp_trades["pnl"].sum()) if len(tp_trades) > 0 else 0.0
        rot_pnl = float(rot_trades["pnl"].sum()) if len(rot_trades) > 0 else 0.0
        stop_pnl = float(stop_trades["pnl"].sum()) if len(stop_trades) > 0 else 0.0
        win_rate = (len(tp_trades) / len(self.trades_df) * 100.0) if len(self.trades_df) > 0 else 0.0
        
        # Period-end open inventory mark-to-market breakdown (A-4)
        open_positions = {}
        open_shares_count = 0
        open_cost_basis = 0.0
        for t, l_dict in positions.items():
            tot_s = sum(p["shares"] for p in l_dict.values())
            if tot_s > 0:
                open_positions[t] = tot_s
                for p in l_dict.values():
                    open_shares_count += p["shares"]
                    open_cost_basis += p["entry_price"] * p["shares"] + p["entry_cost"]
                    
        open_market_val = sum(
            open_positions[t] * float(last_known_close.get(t, 0.0))
            for t in open_positions
        )
        unrealized_pnl = open_market_val - open_cost_basis
        unrealized_pnl_pct = (unrealized_pnl / open_cost_basis * 100.0) if open_cost_basis > 0 else 0.0
        
        # Benchmark VN30 performance metrics & risk comparison (A-1)
        vn30_df = data_bundle.get("vn30d", pd.DataFrame())
        bmk_hpr = 0.0
        bmk_cagr = 0.0
        bmk_mdd = 0.0
        bmk_daily_sharpe = 0.0
        beta = 0.0
        alpha = 0.0
        excess_return = 0.0
        bmk_aligned_series = None
        
        if not vn30_df.empty and "datetime" in vn30_df.columns and "close" in vn30_df.columns:
            vn30_sub = vn30_df.copy()
            vn30_sub["datetime"] = pd.to_datetime(vn30_sub["datetime"])
            min_ts = eq_series.index[0]
            max_ts = eq_series.index[-1]
            vn30_sub = vn30_sub[(vn30_sub["datetime"] >= min_ts.floor("D")) & (vn30_sub["datetime"] <= max_ts.ceil("D"))].sort_values("datetime")
            if len(vn30_sub) >= 2:
                bp0 = float(vn30_sub["close"].iloc[0])
                bp1 = float(vn30_sub["close"].iloc[-1])
                bmk_hpr = (bp1 / bp0 - 1.0) * 100.0
                bmk_days = (vn30_sub["datetime"].iloc[-1] - vn30_sub["datetime"].iloc[0]).total_seconds() / 86400.0
                bmk_years = max(bmk_days / 365.25, 0.01)
                bmk_cagr = (((bp1 / bp0) ** (1.0 / bmk_years)) - 1.0) * 100.0
                
                # Benchmark MDD
                bmk_peaks = vn30_sub["close"].cummax()
                bmk_mdd = float(((vn30_sub["close"] - bmk_peaks) / bmk_peaks).min() * 100.0)
                
                # Benchmark Daily Sharpe
                bmk_rets = vn30_sub["close"].pct_change().dropna()
                bmk_daily_excess = bmk_rets.mean() - rf_daily
                bmk_daily_sharpe = float((bmk_daily_excess / bmk_rets.std()) * np.sqrt(252)) if (len(bmk_rets) > 0 and bmk_rets.std() > 0) else 0.0
                
                # Beta calculation over aligned daily trading sessions
                vn30_sub["date"] = vn30_sub["datetime"].dt.date
                bmk_daily_series = vn30_sub.set_index("date")["close"]
                bmk_aligned_series = vn30_sub.set_index("datetime")["close"]
                
                eq_daily_df = pd.DataFrame({"pv": eq_daily})
                eq_daily_df["date"] = eq_daily_df.index.date
                strat_daily_close = eq_daily_df.groupby("date")["pv"].last()
                
                aligned = pd.DataFrame({
                    "strat": strat_daily_close.pct_change(),
                    "bmk": bmk_daily_series.pct_change()
                }).dropna()
                
                if len(aligned) > 2 and float(np.var(aligned["bmk"])) > 0:
                    cov_mat = np.cov(aligned["strat"], aligned["bmk"])
                    cov_sm = float(cov_mat[0][1])
                    var_m = float(cov_mat[1][1])
                    beta = float(cov_sm / var_m) if var_m > 0 else 0.0
                else:
                    beta = 0.0
                    
                excess_return = hpr - bmk_hpr
                alpha = (cagr - self.risk_free_rate * 100.0) - beta * (bmk_cagr - self.risk_free_rate * 100.0)
        
        return {
            "initial_capital": self.capital,
            "final_capital": final_val,
            "net_profit": net_profit,
            "hpr": hpr,
            "annual_return": cagr,
            "max_drawdown": max_dd,
            "longest_dd_days": longest_dd_days,
            "sharpe_ratio": sharpe,
            "daily_sharpe": daily_sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "total_trades": len(self.trades_df),
            "tp_trades": len(tp_trades),
            "rot_trades": len(rot_trades),
            "stop_trades": len(stop_trades),
            "stop_episodes": stop_episodes,
            "win_rate": win_rate,
            "spot_harvest_pnl": tp_pnl,
            "rotation_pnl": rot_pnl,
            "floor_stop_pnl": stop_pnl,
            "open_positions": open_positions,
            "open_shares_count": open_shares_count,
            "open_cost_basis": open_cost_basis,
            "open_inventory_value": open_market_val,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "cash_balance": cash,
            "benchmark_hpr": bmk_hpr,
            "benchmark_cagr": bmk_cagr,
            "benchmark_mdd": bmk_mdd,
            "benchmark_daily_sharpe": bmk_daily_sharpe,
            "beta": beta,
            "alpha": alpha,
            "excess_return": excess_return,
            "benchmark_series": bmk_aligned_series,
            "equity_series": eq_series
        }

def plot_equity_curve(eq_series: pd.Series, initial_capital: float, title: str, output_path: str, bmk_series: pd.Series = None):
    """
    Plots a dual-panel equity curve and drawdown chart, saved cleanly to output_path.
    Uses dual-axis scaling on Panel 1 so that strategy equity oscillations from active trading
    are clearly resolved and visible to first-time readers, while maintaining benchmark context.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7.5), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
    
    # Panel 1: Strategy Equity (Left Axis)
    color_strat = '#0284c7'
    line_strat = ax1.plot(eq_series.index, eq_series.values / 1e9, label='Strategy Equity (Left Axis)', color=color_strat, lw=2.0)
    ax1.set_ylabel("Strategy Equity (Billion VND)", fontsize=11, fontweight='bold', color=color_strat)
    ax1.tick_params(axis='y', labelcolor=color_strat)
    
    # Dynamic zoom padding on strategy equity to make active trading oscillations vivid
    eq_min = eq_series.min() / 1e9
    eq_max = eq_series.max() / 1e9
    pad = max((eq_max - eq_min) * 0.15, 0.005)
    ax1.set_ylim(eq_min - pad, eq_max + pad * 1.5)
    
    ax1.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax1.grid(True, linestyle=':', alpha=0.6)
    
    # Secondary Right Axis: Normalized Benchmark
    if bmk_series is not None and len(bmk_series) > 0:
        ax1_bmk = ax1.twinx()
        bmk_norm = (initial_capital / 1e9) * (bmk_series / bmk_series.iloc[0])
        color_bmk = '#d97706'
        line_bmk = ax1_bmk.plot(bmk_norm.index, bmk_norm.values, label='VN30 Benchmark (Right Axis)', color=color_bmk, linestyle='--', lw=1.5, alpha=0.85)
        ax1_bmk.set_ylabel("VN30 Benchmark Normalized (Billion VND)", fontsize=11, fontweight='bold', color=color_bmk)
        ax1_bmk.tick_params(axis='y', labelcolor=color_bmk)
        
        lines = line_strat + line_bmk
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc='upper left', framealpha=0.9)
    else:
        ax1.legend(loc='upper left')
        
    # Panel 2: Drawdown
    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak * 100.0
    ax2.fill_between(dd.index, dd.values, 0, color='#ef4444', alpha=0.35)
    ax2.plot(dd.index, dd.values, color='#dc2626', lw=1.2, label='Strategy Drawdown (%)')
    ax2.set_ylabel("Drawdown (%)", fontsize=11, fontweight='bold')
    ax2.set_xlabel("Date", fontsize=11, fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend(loc='lower left')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Equity curve chart saved to: {output_path}")


