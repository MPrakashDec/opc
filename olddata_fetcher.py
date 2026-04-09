"""Fetch historical options data from Dhan API for backtesting."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd
import pytz
import requests

from dhan_rate_limit import throttle_dhan_data_api

IST = pytz.timezone("Asia/Kolkata")

# Dhan API
ROLLING_OPTION_URL = "https://api.dhan.co/v2/charts/rollingoption"

# Underlying security IDs (from Dhan instrument list)
NIFTY_UNDERLYING_ID = "13"
SENSEX_UNDERLYING_ID = "23"  # BSE Sensex - verify from instrument list

# Lot sizes
NIFTY_LOT = 65
SENSEX_LOT = 20  # Sensex lot size - verify


def fetch_rolling_options(
    access_token: str,
    index: str,
    expiry_code: int,
    strike: str,
    option_type: str,
    from_date: str,
    to_date: str,
    interval: str = "5",
    expiry_flag: str = "WEEK",
) -> pd.DataFrame:
    """Fetch expired options OHLC from Dhan rolling option API.
    
    Args:
        access_token: Dhan API token
        index: 'nifty' or 'sensex'
        expiry_code: 0=current, 1=next, 2=far
        strike: ATM, ATM+1, ATM+2, ... ATM+10, ATM-1, etc.
        option_type: CALL or PUT
        from_date: YYYY-MM-DD
        to_date: YYYY-MM-DD (non-inclusive)
        interval: 1, 5, 15, 25, 60 minutes
        expiry_flag: WEEK or MONTH
    """
    seg = "NSE_FNO" if index.lower() == "nifty" else "BSE_FNO"
    sec_id = NIFTY_UNDERLYING_ID if index.lower() == "nifty" else SENSEX_UNDERLYING_ID
    
    payload = {
        "exchangeSegment": seg,
        "interval": int(interval),
        "securityId": int(sec_id),
        "instrument": "OPTIDX",
        "expiryFlag": expiry_flag,
        # WEEK: expiryCode 0 fails on Dhan API; use 1=current, 2=next
        "expiryCode": int(expiry_code) + (1 if expiry_flag == "WEEK" else 0),
        "strike": strike,
        "drvOptionType": option_type.upper(),
        "requiredData": ["open", "high", "low", "close", "volume", "spot", "strike"],
        "fromDate": from_date,
        "toDate": to_date,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "access-token": access_token,
    }
    time.sleep(1)
    throttle_dhan_data_api()
    resp = requests.post(ROLLING_OPTION_URL, json=payload, headers=headers, timeout=60)
    # Some builds reject "strike" in requiredData; retry without it (spot-based fallback in backtest).
    if not resp.ok and resp.status_code == 400 and "strike" in payload.get("requiredData", []):
        payload = {**payload, "requiredData": ["open", "high", "low", "close", "volume", "spot"]}
        time.sleep(1)
        throttle_dhan_data_api()
        resp = requests.post(ROLLING_OPTION_URL, json=payload, headers=headers, timeout=60)
    if not resp.ok:
        try:
            err_body = resp.json()
            msg = (
                err_body.get("errorMessage")
                or err_body.get("message")
                or err_body.get("errorCode")
                or str(err_body)
            )
        except ValueError:
            msg = resp.text[:500]
        raise RuntimeError(f"Dhan API {resp.status_code}: {msg}") from None
    data = resp.json()

    # Parse response - structure: data.ce or data.pe
    opt_key = "ce" if option_type.upper() == "CALL" else "pe"
    series = data.get("data", {}).get(opt_key)
    if not series:
        return pd.DataFrame()
    
    ts = series.get("timestamp", [])
    if not ts:
        return pd.DataFrame()

    n = len(ts)
    def to_list(arr, default=0):
        a = list(arr or [])
        if len(a) < n:
            a = a + [a[-1] if a else default] * (n - len(a))
        return a[:n]

    df = pd.DataFrame({
        "open": to_list(series.get("open")),
        "high": to_list(series.get("high")),
        "low": to_list(series.get("low")),
        "close": to_list(series.get("close")),
        "volume": to_list(series.get("volume"), 0),
        "spot": to_list(series.get("spot")),
        "strike": to_list(series.get("strike")),
    })
    # Convert epoch to IST (like newDhan1_with_fut.py)
    dt_index = pd.to_datetime(ts, unit="s", utc=True).tz_convert(IST)
    df["timestamp"] = dt_index
    df = df.set_index("timestamp")
    return df


def _row_at_or_before(df: pd.DataFrame, dt: datetime) -> pd.Series | None:
    """Last row at or before dt (IST)."""
    if df.empty:
        return None
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    ts = pd.Timestamp(dt)
    if df.index.tz is not None:
        ts = ts.tz_localize(IST) if ts.tz is None else ts.tz_convert(IST)
    mask = df.index <= ts
    if not mask.any():
        return None
    return df.loc[mask].iloc[-1]


def get_price_at_time(df: pd.DataFrame, dt: datetime) -> float | None:
    """Get close price at or just before given datetime (dt assumed IST if naive)."""
    row = _row_at_or_before(df, dt)
    if row is None:
        return None
    return float(row["close"])


def get_spot_at_time(df: pd.DataFrame, dt: datetime) -> float | None:
    """Underlying spot/index at or just before dt."""
    row = _row_at_or_before(df, dt)
    if row is None or "spot" not in row.index:
        return None
    v = row["spot"]
    if pd.isna(v) or float(v) <= 0:
        return None
    return float(v)


def get_strike_at_time(df: pd.DataFrame, dt: datetime) -> float | None:
    """Option strike from API series at or just before dt."""
    row = _row_at_or_before(df, dt)
    if row is None or "strike" not in row.index:
        return None
    v = row["strike"]
    if pd.isna(v) or float(v) <= 0:
        return None
    return float(v)


def find_profit_target_exit(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    df3: pd.DataFrame,
    entry_dt: pd.Timestamp,
    p1: float,
    p2: float,
    p3: float,
    lot_size: int,
    profit_pct: float = 0.25,
    max_dt: pd.Timestamp | None = None,
    capital: float | None = None,
) -> pd.Timestamp | None:
    """Find first timestamp when total PnL reaches profit_pct of capital.

    If ``capital`` is None or <= 0, uses premium paid on buys:
    (3*lot*p1 + 6*lot*p2). Otherwise uses the given value (e.g. Dhan multi margin).
    """
    if capital is not None and float(capital) > 0:
        cap = float(capital)
    else:
        cap = (3 * lot_size * p1) + (6 * lot_size * p2)
    if cap <= 0:
        return None
    if df1.empty or df2.empty or df3.empty:
        return None

    # Ensure timezone-aware for comparison (assumed IST if naive)
    if entry_dt.tzinfo is None:
        entry_dt = pd.Timestamp(entry_dt).tz_localize(IST)
    if max_dt is not None and max_dt.tzinfo is None:
        max_dt = pd.Timestamp(max_dt).tz_localize(IST)

    # Reindex to union of timestamps, forward-fill
    all_idx = df1.index.union(df2.index).union(df3.index)
    all_idx = all_idx[all_idx >= entry_dt]
    if max_dt is not None:
        all_idx = all_idx[all_idx <= max_dt]
    all_idx = sorted(all_idx.unique())

    s1 = df1["close"].reindex(all_idx).ffill()
    s2 = df2["close"].reindex(all_idx).ffill()
    s3 = df3["close"].reindex(all_idx).ffill()

    for ts in all_idx:
        c1, c2, c3 = s1.get(ts), s2.get(ts), s3.get(ts)
        if pd.isna(c1) or pd.isna(c2) or pd.isna(c3):
            continue
        pnl = (float(c1) - p1) * 3 * lot_size + (float(c2) - p2) * 6 * lot_size + (p3 - float(c3)) * 9 * lot_size
        if pnl / cap >= profit_pct:
            return ts
    return None


def find_sl_exit(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    df3: pd.DataFrame,
    entry_dt: pd.Timestamp,
    p1: float,
    p2: float,
    p3: float,
    lot_size: int,
    sl_pct: float = -0.025,
    max_dt: pd.Timestamp | None = None,
    capital: float | None = None,
) -> pd.Timestamp | None:
    """Find first timestamp when total PnL hits stop loss (negative) pct of capital.

    If ``capital`` is None or <= 0, uses premium paid on buys:
    (3*lot*p1 + 6*lot*p2). Otherwise uses the given value (e.g. Dhan multi margin).
    """
    if capital is not None and float(capital) > 0:
        cap = float(capital)
    else:
        cap = (3 * lot_size * p1) + (6 * lot_size * p2)
    if cap <= 0:
        return None
    if df1.empty or df2.empty or df3.empty:
        return None

    # Ensure timezone-aware for comparison (assumed IST if naive)
    if entry_dt.tzinfo is None:
        entry_dt = pd.Timestamp(entry_dt).tz_localize(IST)
    if max_dt is not None and max_dt.tzinfo is None:
        max_dt = pd.Timestamp(max_dt).tz_localize(IST)

    # Reindex to union of timestamps, forward-fill
    all_idx = df1.index.union(df2.index).union(df3.index)
    all_idx = all_idx[all_idx >= entry_dt]
    if max_dt is not None:
        all_idx = all_idx[all_idx <= max_dt]
    all_idx = sorted(all_idx.unique())

    s1 = df1["close"].reindex(all_idx).ffill()
    s2 = df2["close"].reindex(all_idx).ffill()
    s3 = df3["close"].reindex(all_idx).ffill()

    for ts in all_idx:
        c1, c2, c3 = s1.get(ts), s2.get(ts), s3.get(ts)
        if pd.isna(c1) or pd.isna(c2) or pd.isna(c3):
            continue
        pnl = (float(c1) - p1) * 3 * lot_size + (float(c2) - p2) * 6 * lot_size + (p3 - float(c3)) * 9 * lot_size
        if pnl / cap <= sl_pct:  # SL is negative
            return ts
    return None


def fetch_intraday_option(
    access_token: str,
    security_id: str,
    from_date: str,
    to_date: str | None = None,
    interval: str = "5",
) -> pd.DataFrame:
    """Fetch intraday data using specific security ID."""
    if to_date is None:
        to_date = from_date
    
    url = "https://api.dhan.co/v2/charts/option/intraday"
    
    payload = {
        "securityId": str(security_id),
        "exchangeSegment": "NSE_FNO",
        "instrumentType": "OPTIDX",
        "interval": int(interval),
        "fromDate": from_date,
        "toDate": to_date,
    }
    
    headers = {
        "access-token": access_token,
        "Content-Type": "application/json",
    }
    
    throttle_dhan_data_api()
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    
    if not resp.ok:
        raise RuntimeError(f"Intraday API {resp.status_code}: {resp.text}")
    
    data = resp.json().get("data", {})
    if not data or "start_Time" not in data:
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["start_Time"], unit="s", utc=True).tz_convert(IST)
    df = df.rename(columns={
        "open": "open",
        "high": "high", 
        "low": "low",
        "close": "close",
        "volume": "volume"
    })
    df = df.set_index("timestamp")
    
    # Add dummy spot and strike columns for compatibility
    df["spot"] = 0.0
    df["strike"] = 0.0
    
    return df


def estimate_atm_plus6_price(
    current_week_df: pd.DataFrame,
    entry_dt: datetime,
    strike_offset: int = 600,
) -> pd.DataFrame:
    """Estimate ATM+6 price using current week data with adjustments."""
    if current_week_df.empty:
        return pd.DataFrame()
    
    # Get current week ATM price at entry time
    atm_price = get_price_at_time(current_week_df, entry_dt)
    if atm_price is None:
        return pd.DataFrame()
    
    # Estimate next week price (rough approximation)
    # Next week options have more time value, typically 20-40% higher
    time_multiplier = 1.3  # 30% higher due to extra time to expiry
    
    estimated_price = atm_price * time_multiplier
    
    # Create synthetic DataFrame with same structure
    entry_ts = pd.Timestamp(entry_dt).tz_localize(IST) if entry_dt.tzinfo is None else pd.Timestamp(entry_dt)
    
    # Create a few price points around entry time
    times = [entry_ts - pd.Timedelta(minutes=10), entry_ts, entry_ts + pd.Timedelta(minutes=10)]
    base_price = estimated_price
    
    data = []
    for i, ts in enumerate(times):
        # Add small variation to make it realistic
        variation = 1.0 + (i - 1) * 0.01  # -1%, 0%, +1%
        price = base_price * variation
        
        data.append({
            "open": price,
            "high": price * 1.02,
            "low": price * 0.98,
            "close": price,
            "volume": 100,
            "timestamp": ts
        })
    
    df = pd.DataFrame(data)
    df = df.set_index("timestamp")
    df["spot"] = 0.0
    df["strike"] = 0.0
    
    return df


def generate_synthetic_atm_plus6(
    next_week_atm_df: pd.DataFrame,
    target_strike: float,
    base_strike: float,
    entry_dt: datetime,
) -> pd.DataFrame:
    """Generate synthetic ATM+6 data using next week ATM data and Greeks.
    
    Uses the next week ATM strike (e.g., 25400) to synthesize ATM+6 (26000)
    by calculating the Greeks-adjusted price difference.
    
    Args:
        next_week_atm_df: DataFrame with next week ATM data
        target_strike: Target strike (e.g., 26000 for ATM+6)
        base_strike: Base strike from which to synthesize (e.g., 25400)
        entry_dt: Entry datetime
    
    Returns:
        DataFrame with synthetic ATM+6 data
    """
    if next_week_atm_df.empty:
        return pd.DataFrame()
    
    from greeks import calculate_greeks
    
    # Get base price at entry time
    base_price = get_price_at_time(next_week_atm_df, entry_dt)
    if base_price is None:
        return pd.DataFrame()
    
    # Get spot price from the data
    spot = get_spot_at_time(next_week_atm_df, entry_dt)
    if spot is None:
        spot = base_strike  # Fallback to strike if spot not available
    
    # Estimate time to expiry (next week expiry, typically 7-9 days)
    days_to_expiry = 7.0
    
    # Calculate Greeks for base strike
    base_greeks = calculate_greeks(
        spot=spot,
        strike=base_strike,
        time_to_expiry_days=days_to_expiry,
        option_price=base_price,
        option_type="CE",
        is_sell=False
    )
    
    # Calculate price adjustment for target strike using Delta
    # Price change ≈ Delta * (target_strike - base_strike)
    # For OTM calls, Delta decreases, so price decreases
    strike_diff = target_strike - base_strike
    price_adjustment = base_greeks.delta * strike_diff * -1  # Negative because OTM has lower value
    
    # Apply Gamma correction for large strike differences
    gamma_adjustment = 0.5 * base_greeks.gamma * (strike_diff ** 2) * 0.01
    
    target_price = base_price + price_adjustment - gamma_adjustment
    target_price = max(target_price, 0.5)  # Minimum price floor
    
    # Create synthetic DataFrame with same timestamps as base
    entry_ts = pd.Timestamp(entry_dt).tz_localize(IST) if entry_dt.tzinfo is None else pd.Timestamp(entry_dt)
    
    # Get the timeframe from the base DataFrame
    if len(next_week_atm_df) >= 3:
        # Use actual timestamps from base data
        base_times = next_week_atm_df.index[:3]
        data = []
        for i, ts in enumerate(base_times):
            base_val = next_week_atm_df.iloc[i]['close']
            variation = (base_val - base_price) / base_price if base_price > 0 else 0
            synth_price = target_price * (1 + variation)
            
            data.append({
                'open': next_week_atm_df.iloc[i]['open'] * (target_price / base_price),
                'high': next_week_atm_df.iloc[i]['high'] * (target_price / base_price),
                'low': next_week_atm_df.iloc[i]['low'] * (target_price / base_price),
                'close': synth_price,
                'volume': next_week_atm_df.iloc[i].get('volume', 100),
            })
        
        df = pd.DataFrame(data, index=base_times)
    else:
        # Minimal fallback with just entry time
        times = [
            entry_ts - pd.Timedelta(minutes=10),
            entry_ts,
            entry_ts + pd.Timedelta(minutes=10)
        ]
        data = []
        for i, ts in enumerate(times):
            variation = 1.0 + (i - 1) * 0.005
            price = target_price * variation
            data.append({
                'open': price,
                'high': price * 1.01,
                'low': price * 0.99,
                'close': price,
                'volume': 100,
            })
        df = pd.DataFrame(data)
        df.index = times
    
    # Add metadata columns
    df['spot'] = spot
    df['strike'] = target_strike
    
    return df


def fetch_atm_plus6_fallback(
    access_token: str,
    index: str,
    entry_date: date,
    entry_dt: datetime,
    strike: float,
    expiry: date,
    master_df: pd.DataFrame | None = None,
    interval: str = "5",
) -> tuple[pd.DataFrame, str]:
    """Try multiple methods to get ATM+6 next-week data.
    
    Returns:
        (DataFrame, method_description)
    """
    
    # Method 1: Intraday Chart API with specific security ID
    if master_df is not None:
        try:
            from fno_security_lookup import find_option_security_id
            sec_id = find_option_security_id(master_df, index, expiry, int(strike), "CE")
            if sec_id:
                df = fetch_intraday_option(access_token, str(sec_id), entry_date.isoformat(), entry_date.isoformat(), interval)
                if not df.empty:
                    return df, "Intraday API (Security ID)"
        except Exception as e:
            pass
    
    # Method 2: Different intervals with Rolling Options
    for intv in ["15", "60", "1"]:
        try:
            df = fetch_rolling_options(
                access_token, index, 1, "ATM+6", "CALL", 
                entry_date.isoformat(), expiry.isoformat(), intv
            )
            if not df.empty:
                return df, f"Rolling Options ({intv}m)"
        except:
            continue
    
    # Method 3: Synthetic data using next week ATM strike
    try:
        # Find next week ATM strike (e.g., if target is 26000, use 25400 or 25500)
        # Use 100-point increments only
        base_strike = round(strike / 100) * 100 - 600  # Go back 6 strikes from target
        
        # Try multiple base strikes if needed
        for offset in [0, 100, -100]:
            try_strike = base_strike + offset
            if try_strike <= 0:
                continue
                
            # Fetch next week ATM data
            base_df = fetch_rolling_options(
                access_token, index, 1, "ATM", "CALL",
                entry_date.isoformat(), expiry.isoformat(), interval
            )
            
            if not base_df.empty:
                # Get actual strike from data
                actual_base_strike = get_strike_at_time(base_df, entry_dt)
                if actual_base_strike:
                    try_strike = actual_base_strike
                
                # Generate synthetic ATM+6
                synthetic_df = generate_synthetic_atm_plus6(
                    base_df, strike, try_strike, entry_dt
                )
                if not synthetic_df.empty:
                    return synthetic_df, f"Synthetic ({try_strike} to {strike})"
    except:
        pass
    
    # Method 4: Price estimation (last resort)
    try:
        # Get current week ATM data for estimation
        current_week_df = fetch_rolling_options(
            access_token, index, 0, "ATM", "CALL",
            entry_date.isoformat(), expiry.isoformat(), interval
        )
        if not current_week_df.empty:
            estimated_df = estimate_atm_plus6_price(current_week_df, entry_dt)
            if not estimated_df.empty:
                return estimated_df, "Price Estimation"
    except:
        pass
    
    # All methods failed
    return pd.DataFrame(), "All methods failed"
