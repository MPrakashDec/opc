"""Backtest options strategy for Nifty 50 and Sensex.

Strategy:
  Entry: Nifty=Thursday 12:45 PM, Sensex=Monday 12:45 PM
    Entry1: Current week expiry ATM CE Buy, 3 lots
    Entry2: Next expiry ATM+6 CE Buy, 6 lots (600 points for Nifty, 300 for Sensex)
    Entry3: Current expiry ATM+2 CE Sell, 9 lots (200 points for Nifty, 100 for Sensex)
  Exit:
    - Close all if profit reaches 2.5% of margin (or SL -2.5%)
    - Close all at 1 day before expiry at 11:45 AM
"""
from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from config import load_credentials
from logger_ist import log, progress, ts_to_csv_display_ist
from data_fetcher import (
    NIFTY_LOT,
    SENSEX_LOT,
    fetch_rolling_options,
    find_profit_target_exit,
    find_sl_exit,
    get_price_at_time,
    get_spot_at_time,
    get_strike_at_time,
    fetch_atm_plus6_fallback,
)
from option_symbol import (
    build_index_option_symbol,
    normalize_strike_for_index,
    strike_from_atm_offset,
    strike_from_spot,
)
from greeks import calculate_greeks, Greeks, portfolio_greeks
from expiry_calendar import (
    get_entry_datetime,
    get_entry_dates,
    get_exit_datetime,
    get_expiry_for_entry,
    get_exit_date_for_expiry,
    get_theoretical_expiry_for_entry,
)


@dataclass
class Position:
    """Single position in the strategy."""
    name: str
    index: str
    expiry_code: int
    strike_offset: int  # 0=ATM, 2=ATM+2, 6=ATM+6
    option_type: str
    side: str  # BUY or SELL
    lots: int
    entry_price: float
    exit_price: float | None = None
    entry_dt: datetime | None = None
    exit_dt: datetime | None = None
    strike: float = 0.0  # Actual strike price
    expiry: date | None = None  # Expiry date
    greeks: Greeks | None = None  # Entry Greeks

    @property
    def lot_size(self) -> int:
        return NIFTY_LOT if self.index.lower() == "nifty" else SENSEX_LOT

    @property
    def quantity(self) -> int:
        return self.lots * self.lot_size

    def pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        if self.side == "BUY":
            return (self.exit_price - self.entry_price) * self.quantity
        return (self.entry_price - self.exit_price) * self.quantity

    def total_delta(self) -> float:
        """Total position delta (quantity * greeks.delta)."""
        if self.greeks is None:
            return 0.0
        is_sell = self.side == "SELL"
        return self.greeks.total_delta(self.quantity, is_sell)


def _progress_after_option_fetch(
    df: pd.DataFrame,
    entry_dt: datetime,
    index: str,
    expiry: date,
    leg_desc: str,
    *,
    atm_norm_for_offsets: int | None = None,
    offset_steps: int | None = None,
) -> int | None:
    """Log trading symbol after a rolling-option fetch; return normalized ATM (leg 1 only)."""
    sk = get_strike_at_time(df, entry_dt)
    spot = get_spot_at_time(df, entry_dt) if sk is None else None
    if sk is None and spot is not None:
        sk = float(strike_from_spot(spot, index))
    if sk is None and atm_norm_for_offsets is not None and offset_steps is not None:
        sk = float(strike_from_atm_offset(atm_norm_for_offsets, offset_steps, index))
    if sk is None:
        progress(f"  ... (no symbol @ entry)  |  {leg_desc}  |  bars={len(df)}")
        return None
    skn = normalize_strike_for_index(sk, index)
    sym = build_index_option_symbol(index, expiry, skn)
    progress(f"  ... {sym}  |  {leg_desc}  |  bars={len(df)}")
    if offset_steps is None:
        return skn
    return None


def run_backtest(
    from_date: str,
    to_date: str,
    index: str = "nifty",
    *,
    use_dhan_margin: bool = True,
) -> dict[str, Any]:
    """Run backtest from given date range.
    
    Args:
        from_date: YYYY-MM-DD
        to_date: YYYY-MM-DD
        index: nifty or sensex
        use_dhan_margin: If True, try Dhan ``/margincalculator/multi`` for combined margin
            as the 25% profit base; falls back to buy-premium if lookup/API fails.
    """
    progress("Loading credentials (token.txt)...")
    client_id, access_token = load_credentials()
    progress("Credentials OK.")

    from_d = date.fromisoformat(from_date)
    to_d = date.fromisoformat(to_date)

    today = date.today()
    if from_d > today or to_d > today:
        log(f"Date range includes future dates. Use dates up to {today}", "WARN")
        return {
            "error": f"Date range {from_date} to {to_date} includes future dates. Dhan API has historical data only (up to 5 years back). Use dates up to {today}.",
            "trades": [],
            "total_pnl": 0,
        }

    entry_dates = get_entry_dates(from_d, to_d, index)
    if not entry_dates:
        return {"error": f"No entry dates in range for {index}", "trades": [], "total_pnl": 0}

    n_cycles = len(entry_dates)
    log(f"Backtest {index.upper()}  {from_date}  ->  {to_date}  |  {n_cycles} cycles...")
    progress(f"Scheduled entry days: {n_cycles} (first {entry_dates[0]}, last {entry_dates[-1]})")

    margin_enabled = bool(use_dhan_margin)
    master_df = None
    if margin_enabled:
        try:
            from fno_security_lookup import get_scrip_master_detailed_df

            master_df = get_scrip_master_detailed_df()
            progress("Scrip master (detailed) ready for Dhan margin calculator.")
        except Exception as e:
            log(f"Dhan scrip CSV unavailable; 25% vs buy-premium only. ({e})", "WARN")
            margin_enabled = False

    positions: list[Position] = []
    all_trades: list[dict] = []

    for i, entry_date in enumerate(entry_dates):
        if entry_date > to_d:
            break

        entry_dt = get_entry_datetime(entry_date)
        exp0 = get_expiry_for_entry(entry_date, 0, index)
        exp1 = get_expiry_for_entry(entry_date, 1, index)
        th0 = get_theoretical_expiry_for_entry(entry_date, 0, index)
        th1 = get_theoretical_expiry_for_entry(entry_date, 1, index)
        if not exp0 or not exp1:
            log(f"Skipping: no expiry for entry {entry_date}", "WARN")
            continue

        exit0 = get_exit_date_for_expiry(exp0, entry_date, th0)
        exit1 = get_exit_date_for_expiry(exp1, entry_date, th1)
        exit_dt0 = get_exit_datetime(exit0)
        exit_dt1 = get_exit_datetime(exit1)

        fd = entry_date.isoformat()
        td = (max(exit0, exit1) + timedelta(days=1)).strftime("%Y-%m-%d")

        progress(
            f"Cycle {i + 1}/{n_cycles} | entry {entry_date} | "
            f"expiries cur={exp0} next={exp1} | exit days {exit0}, {exit1}"
        )
        progress(f"  Fetch 5m bars {fd} -> {td} (Dhan rolling option)...")

        df_e1 = fetch_rolling_options(
            access_token, index, 1, "ATM", "CALL", fd, td, interval="5"
        )
        atm_norm = _progress_after_option_fetch(
            df_e1, entry_dt, index, exp0, "BUY ATM CE, current expiry"
        )

        df_e2 = fetch_rolling_options(
            access_token, index, 2, "ATM+6", "CALL", fd, td, interval="5"
        )
        _progress_after_option_fetch(
            df_e2,
            entry_dt,
            index,
            exp1,
            "BUY ATM+6 CE, next expiry",
            atm_norm_for_offsets=atm_norm,
            offset_steps=6,
        )

        df_e3 = fetch_rolling_options(
            access_token, index, 1, "ATM+2", "CALL", fd, td, interval="5"
        )
        _progress_after_option_fetch(
            df_e3,
            entry_dt,
            index,
            exp0,
            "SELL ATM+2 CE, current expiry",
            atm_norm_for_offsets=atm_norm,
            offset_steps=2,
        )

        progress(
            f"  Bars loaded: ATM={len(df_e1)} ATM+6={len(df_e2)} ATM+2={len(df_e3)}"
        )

        # Get strikes first before trying fallback
        spot = (
            get_spot_at_time(df_e1, entry_dt)
            or get_spot_at_time(df_e2, entry_dt)
            or get_spot_at_time(df_e3, entry_dt)
        )
        sk1 = get_strike_at_time(df_e1, entry_dt)
        sk2 = get_strike_at_time(df_e2, entry_dt)
        sk3 = get_strike_at_time(df_e3, entry_dt)
        if sk1 is None and spot is not None:
            sk1 = float(strike_from_spot(spot, index))
        if sk2 is None and sk1 is not None:
            sk2 = float(strike_from_atm_offset(int(sk1), 6, index))
        if sk3 is None and sk1 is not None:
            sk3 = float(strike_from_atm_offset(int(sk1), 2, index))
        
        sk1 = normalize_strike_for_index(sk1, index) if sk1 is not None else None
        sk2 = normalize_strike_for_index(sk2, index) if sk2 is not None else None
        sk3 = normalize_strike_for_index(sk3, index) if sk3 is not None else None

        # Skip if any strike couldn't be resolved
        if sk1 is None or sk2 is None or sk3 is None:
            log(f"Skip {entry_date}: could not resolve option strikes", "WARN")
            continue

        # Fallback for ATM+6 if Rolling Options returns empty
        if df_e2.empty and sk2 is not None:
            progress("  ATM+6 data empty - trying fallback methods...")
            df_e2, method_used = fetch_atm_plus6_fallback(
                access_token, index, entry_date, entry_dt, sk2, exp1, master_df, "5"
            )
            if not df_e2.empty:
                progress(f"  ATM+6 fallback SUCCESS: {method_used} | bars={len(df_e2)}")
                _progress_after_option_fetch(
                    df_e2,
                    entry_dt,
                    index,
                    exp1,
                    f"BUY ATM+6 CE, next expiry ({method_used})",
                    atm_norm_for_offsets=atm_norm,
                    offset_steps=6,
                )
            else:
                progress(f"  ATM+6 fallback FAILED: {method_used}")

        entry_price_dt = entry_dt
        p1 = get_price_at_time(df_e1, entry_price_dt)
        p2 = get_price_at_time(df_e2, entry_price_dt)
        p3 = get_price_at_time(df_e3, entry_price_dt)

        if df_e1.empty or df_e2.empty or df_e3.empty:
            progress(
                "  One or more legs returned 0 bars — waiting 2s, then refetching empty leg(s)..."
            )
            time.sleep(2)
            if df_e1.empty:
                df_e1 = fetch_rolling_options(
                    access_token, index, 1, "ATM", "CALL", fd, td, interval="5"
                )
                atm_norm = _progress_after_option_fetch(
                    df_e1,
                    entry_dt,
                    index,
                    exp0,
                    "BUY ATM CE, current expiry (refetch)",
                )
            if df_e2.empty:
                df_e2 = fetch_rolling_options(
                    access_token, index, 2, "ATM+6", "CALL", fd, td, interval="5"
                )
                _progress_after_option_fetch(
                    df_e2,
                    entry_dt,
                    index,
                    exp1,
                    "BUY ATM+6 CE, next expiry (refetch)",
                    atm_norm_for_offsets=atm_norm,
                    offset_steps=6,
                )
            if df_e3.empty:
                df_e3 = fetch_rolling_options(
                    access_token, index, 1, "ATM+2", "CALL", fd, td, interval="5"
                )
                _progress_after_option_fetch(
                    df_e3,
                    entry_dt,
                    index,
                    exp0,
                    "SELL ATM+2 CE, current expiry (refetch)",
                    atm_norm_for_offsets=atm_norm,
                    offset_steps=2,
                )
            progress(
                f"  Bars after refetch: ATM={len(df_e1)} ATM+6={len(df_e2)} ATM+2={len(df_e3)}"
            )
            p1 = get_price_at_time(df_e1, entry_price_dt)
            p2 = get_price_at_time(df_e2, entry_price_dt)
            p3 = get_price_at_time(df_e3, entry_price_dt)

        if p1 is None or p2 is None or p3 is None:
            entry_price_dt = entry_dt + timedelta(minutes=5)
            progress(
                f"  Retrying entry prices at {entry_price_dt.strftime('%H:%M')} IST "
                "(1 minute after scheduled entry)..."
            )
            p1 = get_price_at_time(df_e1, entry_price_dt)
            p2 = get_price_at_time(df_e2, entry_price_dt)
            p3 = get_price_at_time(df_e3, entry_price_dt)

        if p1 is None or p2 is None or p3 is None:
            missing: list[str] = []
            if p1 is None:
                missing.append(
                    "ATM CE current: 0 bars"
                    if df_e1.empty
                    else f"ATM CE current: no bar at/before {entry_price_dt.strftime('%H:%M')} IST"
                )
            if p2 is None:
                missing.append(
                    "ATM+6 CE next week: 0 bars (Dhan often empty for this combo)"
                    if df_e2.empty
                    else f"ATM+6 CE next week: no bar at/before {entry_price_dt.strftime('%H:%M')} IST"
                )
            if p3 is None:
                missing.append(
                    "ATM+2 CE current: 0 bars"
                    if df_e3.empty
                    else f"ATM+2 CE current: no bar at/before {entry_price_dt.strftime('%H:%M')} IST"
                )
            log(
                f"Skip {entry_date} entry — {'. '.join(missing)}. "
                f"Counts ATM={len(df_e1)} ATM+6={len(df_e2)} ATM+2={len(df_e3)}.",
                "WARN",
            )
            continue

        progress(
            f"  Entry prices @ {entry_price_dt.strftime('%H:%M')}: "
            f"ATM={p1:.2f} ATM+6={p2:.2f} ATM+2={p3:.2f} | "
            "checking 2.5% profit / -2.5% SL target..."
        )

        # Strikes already calculated above
        progress(f"  Strikes: {sk1} / {sk2} / {sk3} (ATM / ATM+6 / ATM+2)")

        sym1 = build_index_option_symbol(index, exp0, sk1)
        sym2 = build_index_option_symbol(index, exp1, sk2)
        sym3 = build_index_option_symbol(index, exp0, sk3)

        lot_size = NIFTY_LOT if index.lower() == "nifty" else SENSEX_LOT
        pos1 = Position(
            "Entry1_ATM_CE", index, 0, 0, "CALL", "BUY", 3, p1, None, entry_price_dt, None, sk1, exp0
        )
        pos2 = Position(
            "Entry2_ATM+6_CE", index, 1, 6, "CALL", "BUY", 6, p2, None, entry_price_dt, None, sk2, exp1
        )
        pos3 = Position(
            "Entry3_ATM+2_CE", index, 0, 2, "CALL", "SELL", 9, p3, None, entry_price_dt, None, sk3, exp0
        )

        # Calculate Greeks for each position
        time_to_exp0 = (exp0 - entry_date).days
        time_to_exp1 = (exp1 - entry_date).days
        
        pos1.greeks = calculate_greeks(spot or float(sk1), float(sk1), time_to_exp0, p1, "CE", is_sell=False)
        pos2.greeks = calculate_greeks(spot or float(sk2), float(sk2), time_to_exp1, p2, "CE", is_sell=False)
        pos3.greeks = calculate_greeks(spot or float(sk3), float(sk3), time_to_exp0, p3, "CE", is_sell=True)
        
        # Portfolio Greeks
        portfolio_g = portfolio_greeks([
            (pos1.quantity, pos1.greeks),
            (pos2.quantity, pos2.greeks),
            (pos3.quantity, pos3.greeks),
        ])
        
        progress(
            f"  Greeks | Delta: {portfolio_g.delta:.2f}, Gamma: {portfolio_g.gamma:.4f}, "
            f"Theta: {portfolio_g.theta:.0f}/day, Vega: {portfolio_g.vega:.0f}/1%"
        )

        premium_capital = (3 * lot_size * p1) + (6 * lot_size * p2)
        profit_base = premium_capital
        profit_base_label = "buy premium (3 ATM + 6 ATM+6 CE)"
        # BACKTEST: Allow testing without margin for now
        if margin_enabled:
            from dhan_margin import fetch_strategy_margin_total
            from fno_security_lookup import (
                exchange_segment_for_index,
                find_option_security_id,
            )

            seg = exchange_segment_for_index(index)
            id1 = find_option_security_id(master_df, index, exp0, sk1, "CE")
            id2 = find_option_security_id(master_df, index, exp1, sk2, "CE")
            id3 = find_option_security_id(master_df, index, exp0, sk3, "CE")
            if id1 and id2 and id3:
                legs = [
                    ("BUY", id1, 3 * lot_size, p1),
                    ("BUY", id2, 6 * lot_size, p2),
                    ("SELL", id3, 9 * lot_size, p3),
                ]
                mtot, raw = fetch_strategy_margin_total(
                    access_token, client_id, seg, legs
                )
                if mtot is not None and mtot > 0:
                    profit_base = mtot
                    profit_base_label = "Dhan multi-leg margin"
                else:
                    # BACKTEST MUST FAIL - no fallback
                    hint = ""
                    if isinstance(raw, dict):
                        hint = str(
                            raw.get("errorMessage")
                            or raw.get("errorType")
                            or raw.get("remarks")
                            or ""
                        )[:120]
                    err_msg = f"Dhan margin calculation failed for {entry_date}: {hint if hint else 'Invalid margin response'}"
                    log(err_msg, "ERROR")
                    progress(f"  ABORT: {err_msg}")
                    return {
                        "error": err_msg,
                        "trades": all_trades,
                        "total_pnl": sum(p.pnl() for p in positions),
                        "aborted_at_cycle": i + 1,
                    }
            else:
                # BACKTEST MUST FAIL - cannot calculate margin without security IDs
                err_msg = f"Missing security IDs for {entry_date}: id1={id1}, id2={id2}, id3={id3}"
                log(err_msg, "ERROR")
                progress(f"  ABORT: {err_msg}")
                return {
                    "error": err_msg,
                    "trades": all_trades,
                    "total_pnl": sum(p.pnl() for p in positions),
                    "aborted_at_cycle": i + 1,
                }
        else:
            progress(f"  TESTING MODE: Using buy premium base: {profit_base:,.2f}")

        progress(f"  2.5% profit / -2.5% SL target vs {profit_base_label}: {profit_base:,.2f}")

        entry_ts = pd.Timestamp(entry_price_dt)
        max_check_dt = pd.Timestamp(max(exit_dt0, exit_dt1))  # Check until last scheduled exit

        # Check for profit target (2.5%)
        profit_exit_ts = find_profit_target_exit(
            df_e1,
            df_e2,
            df_e3,
            entry_ts,
            p1,
            p2,
            p3,
            lot_size,
            0.025,  # 2.5% profit
            max_check_dt,
            capital=profit_base,
        )

        # Check for stop loss (-2.5%)
        sl_exit_ts = find_sl_exit(
            df_e1,
            df_e2,
            df_e3,
            entry_ts,
            p1,
            p2,
            p3,
            lot_size,
            -0.025,  # -2.5% SL
            max_check_dt,
            capital=profit_base,
        )

        # Determine which exit comes first
        exit_reason = "scheduled"
        exit_dt_used = None
        if profit_exit_ts is not None and sl_exit_ts is not None:
            if profit_exit_ts <= sl_exit_ts:
                exit_reason = "profit"
                exit_dt_used = profit_exit_ts.to_pydatetime()
            else:
                exit_reason = "stop_loss"
                exit_dt_used = sl_exit_ts.to_pydatetime()
        elif profit_exit_ts is not None:
            exit_reason = "profit"
            exit_dt_used = profit_exit_ts.to_pydatetime()
        elif sl_exit_ts is not None:
            exit_reason = "stop_loss"
            exit_dt_used = sl_exit_ts.to_pydatetime()

        if exit_reason == "profit":
            progress(
                f"  Exit: 2.5% profit of {profit_base_label} hit at "
                f"{exit_dt_used.strftime('%Y-%m-%d %H:%M')} IST (all legs)"
            )
            ep1 = get_price_at_time(df_e1, exit_dt_used)
            ep2 = get_price_at_time(df_e2, exit_dt_used)
            ep3 = get_price_at_time(df_e3, exit_dt_used)
            pos1.exit_dt = pos2.exit_dt = pos3.exit_dt = exit_dt_used
        elif exit_reason == "stop_loss":
            progress(
                f"  Exit: -2.5% stop loss of {profit_base_label} hit at "
                f"{exit_dt_used.strftime('%Y-%m-%d %H:%M')} IST (all legs)"
            )
            ep1 = get_price_at_time(df_e1, exit_dt_used)
            ep2 = get_price_at_time(df_e2, exit_dt_used)
            ep3 = get_price_at_time(df_e3, exit_dt_used)
            pos1.exit_dt = pos2.exit_dt = pos3.exit_dt = exit_dt_used
        else:
            progress(
                f"  Exit: scheduled (leg1&3 {exit0} 11:45, leg2 {exit1} 11:45 IST)"
            )
            # Exit at scheduled time: Entry1&3 at exit_dt0, Entry2 at exit_dt1
            ep1 = get_price_at_time(df_e1, exit_dt0)
            ep2 = get_price_at_time(df_e2, exit_dt1)
            ep3 = get_price_at_time(df_e3, exit_dt0)
            pos1.exit_dt = exit_dt0
            pos2.exit_dt = exit_dt1
            pos3.exit_dt = exit_dt0

        if ep1 is None:
            ep1 = df_e1["close"].iloc[-1] if not df_e1.empty else p1
        if ep2 is None:
            ep2 = df_e2["close"].iloc[-1] if not df_e2.empty else p2
        if ep3 is None:
            ep3 = df_e3["close"].iloc[-1] if not df_e3.empty else p3

        pos1.exit_price = ep1
        pos2.exit_price = ep2
        pos3.exit_price = ep3

        cycle_pnl = pos1.pnl() + pos2.pnl() + pos3.pnl()
        progress(
            f"  Cycle PnL: {cycle_pnl:,.0f}  (ATM buy {pos1.pnl():,.0f}, "
            f"ATM+6 buy {pos2.pnl():,.0f}, ATM+2 sell {pos3.pnl():,.0f})"
        )

        leg_meta = (
            (pos1, sym1, sk1),
            (pos2, sym2, sk2),
            (pos3, sym3, sk3),
        )
        for pos, option_sym, strike_val in leg_meta:
            pnl = pos.pnl()
            ep = pos.exit_price if pos.exit_price is not None else ""
            g = pos.greeks
            all_trades.append({
                "symbol": index.upper(),
                "entry_num": i + 1,
                "entry_timestamp": ts_to_csv_display_ist(pos.entry_dt) if pos.entry_dt else "",
                "exit_timestamp": ts_to_csv_display_ist(pos.exit_dt) if pos.exit_dt else "",
                "side": pos.side,
                "option_symbol": option_sym,
                "strike": float(strike_val),
                "qty": pos.quantity,
                "entry_price": pos.entry_price,
                "exit_price": ep,
                "PnL": pnl,
                "delta": g.delta if g else "",
                "gamma": g.gamma if g else "",
                "theta": g.theta if g else "",
                "vega": g.vega if g else "",
                "iv": g.iv if g else "",
            })
        positions.extend([pos1, pos2, pos3])

    total_pnl = sum(p.pnl() for p in positions)

    csv_path = Path(__file__).parent / "backtest_trades.csv"
    if all_trades:
        progress(f"Writing {len(all_trades)} rows -> {csv_path.name}")
        _write_trades_csv(all_trades, csv_path)
    progress(f"Finished. Total PnL {total_pnl:,.0f} | open report below.")

    return {
        "from_date": from_date,
        "to_date": to_date,
        "index": index,
        "num_cycles": len(entry_dates),
        "trades": all_trades,
        "total_pnl": total_pnl,
        "positions": positions,
        "csv_path": str(csv_path) if all_trades else "",
    }


def _write_trades_csv(trades: list[dict], path: Path) -> None:
    """Write trades to CSV in backtest_trades.csv format."""
    cols = ["symbol", "entry_num", "entry_timestamp", "exit_timestamp", "side", "option_symbol", "strike", "qty", "entry_price", "exit_price", "PnL", "delta", "gamma", "theta", "vega", "iv"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for t in trades:
            row = {c: ("" if t.get(c) is None or t.get(c) == "" else t[c]) for c in cols}
            w.writerow(row)


def _short_iso(ts: str) -> str:
    """Display ISO+05:30 as compact local-style (IST)."""
    if not ts:
        return "-"
    s = ts.replace("T", " ").split("+")[0].rstrip("Z")
    return s[:16] if len(s) >= 16 else s


def print_report(result: dict[str, Any]) -> None:
    """Print a compact, readable backtest summary and trade table."""
    if "error" in result:
        print(f"\n[ERROR] {result['error']}\n")
        return
    trades = result.get("trades", [])
    idx = result["index"].upper()
    fd, td = result["from_date"], result["to_date"]

    sep = "=" * 108
    sub = "-" * 108

    if not trades:
        print(f"\n{sep}")
        print(f"  BACKTEST  {idx}   {fd}  ->  {td}")
        print(f"{sep}")
        print("  No trades executed.\n")
        return

    cycles_done = len({t["entry_num"] for t in trades})
    total = result["total_pnl"]
    csv_path = result.get("csv_path", "")
    scheduled = result.get("num_cycles", cycles_done)

    # Calculate total portfolio Greeks from all trades
    total_delta = sum(t.get("delta", 0) * t.get("qty", 0) if t.get("side") == "BUY" else -t.get("delta", 0) * t.get("qty", 0) for t in trades)
    total_gamma = sum(t.get("gamma", 0) * t.get("qty", 0) if t.get("side") == "BUY" else -t.get("gamma", 0) * t.get("qty", 0) for t in trades)
    total_theta = sum(t.get("theta", 0) * t.get("qty", 0) if t.get("side") == "BUY" else -t.get("theta", 0) * t.get("qty", 0) for t in trades)
    total_vega = sum(t.get("vega", 0) * t.get("qty", 0) if t.get("side") == "BUY" else -t.get("vega", 0) * t.get("qty", 0) for t in trades)

    print(f"\n{sep}")
    print("  BACKTEST REPORT")
    print(sub)
    print(f"  Index           {idx}")
    print(f"  Period          {fd}  ->  {td}")
    print(f"  Entry cycles    {cycles_done} executed  (of {scheduled} scheduled)  |  {len(trades)} legs")
    print(f"  Total PnL       {total:,.2f}")
    print(f"  Portfolio Delta {total_delta:,.2f}  Gamma:{total_gamma:,.4f}  Theta:{total_theta:,.0f}/day  Vega:{total_vega:,.0f}/1%")
    if csv_path:
        print(f"  CSV saved       {csv_path}")
    print(f"{sub}")
    print(
        f"  {'#':>3}  {'Contract':<22}  {'Side':<4}  {'Strike':>7}  {'Qty':>4}  {'Delta':>6}  {'Theta':>6}  "
        f"{'Entry @':<16}  {'Exit @':<16}  {'In':>7}  {'Out':>7}  {'PnL':>12}"
    )
    print(f"{sub}")
    for t in trades:
        ep = t.get("exit_price", "")
        if ep == "" or ep is None:
            ep_f: float | None = None
        else:
            ep_f = float(ep)
        pnl = t.get("PnL", 0)
        pnl_f = float(pnl) if isinstance(pnl, (int, float)) else 0.0
        ep_str = f"{ep_f:7.2f}" if ep_f is not None else "      -"
        sk = t.get("strike", "")
        sk_str = f"{int(sk)}" if isinstance(sk, (int, float)) and float(sk) == int(float(sk)) else str(sk)
        sym = str(t.get("option_symbol", ""))[:22]
        g_delta = float(t.get("delta", 0)) if t.get("delta") is not None else 0.0
        g_theta = float(t.get("theta", 0)) if t.get("theta") is not None else 0.0
        print(
            f"  {t.get('entry_num', 0):>3}  {sym:<22}  {t.get('side', ''):<4}  {sk_str:>7}  "
            f"{t.get('qty', 0):>4}  {g_delta:>6.2f}  {g_theta:>6.0f}  "
            f"{_short_iso(str(t.get('entry_timestamp', ''))):<16}  "
            f"{_short_iso(str(t.get('exit_timestamp', ''))):<16}  "
            f"{t.get('entry_price', 0):7.2f}  {ep_str}  {pnl_f:12,.2f}"
        )
    print(f"{sep}\n")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--entry-date", dest="entry_date", required=True, help="Entry date YYYY-MM-DD (runs from this date till today)")
    p.add_argument("--index", default="nifty", choices=["nifty", "sensex"])
    p.add_argument(
        "--no-dhan-margin",
        action="store_true",
        help="Do not call Dhan margin calculator; 2.5%% target vs buy premium only",
    )
    args = p.parse_args()
    to_date = date.today().isoformat()
    r = run_backtest(
        args.entry_date,
        to_date,
        args.index,
        use_dhan_margin=not args.no_dhan_margin,
    )
    print_report(r)
