#!/usr/bin/env python3
"""Test synthetic ATM+6 data generation with real Dhan API data."""

import sys
sys.path.append('.')

from data_fetcher import fetch_rolling_options, get_price_at_time, get_spot_at_time, get_strike_at_time
from greeks import calculate_greeks
from datetime import date, datetime
import pytz
import pandas as pd

IST = pytz.timezone('Asia/Kolkata')

# Read token
token_data = open('token.txt').read().strip().split('\n')
access_token = [line.split('=')[1].strip() for line in token_data if 'access_token' in line][0]

# Test date: Feb 26, 2026 (expired contract)
entry_date = date(2026, 2, 26)
entry_dt = datetime(2026, 2, 26, 12, 45, tzinfo=IST)

# Expiries
current_expiry = date(2026, 2, 26)  # Current week
next_expiry = date(2026, 3, 3)      # Next week (Tuesday)

print("=" * 60)
print("SYNTHETIC ATM+6 DATA GENERATION TEST")
print("=" * 60)
print(f"Entry Date: {entry_date}")
print(f"Entry Time: 12:45 PM IST")
print(f"Current Expiry: {current_expiry}")
print(f"Next Expiry: {next_expiry}")
print()

# Step 1: Get current week ATM data (expired)
print("STEP 1: Fetching CURRENT WEEK ATM (expired)...")
current_atm_df = fetch_rolling_options(
    access_token, 'nifty', 0, 'ATM', 'CALL',
    entry_date.isoformat(), current_expiry.isoformat(), '5'
)

if current_atm_df.empty:
    print("ERROR: Could not fetch current week ATM data")
    sys.exit(1)

current_atm_price = get_price_at_time(current_atm_df, entry_dt)
current_atm_strike = get_strike_at_time(current_atm_df, entry_dt)
current_spot = get_spot_at_time(current_atm_df, entry_dt)

print(f"  Current ATM Strike: {current_atm_strike}")
print(f"  Current ATM Price @ 12:45: {current_atm_price}")
print(f"  Spot Price: {current_spot}")
print(f"  Data points: {len(current_atm_df)}")
print()

# Step 2: Calculate normalized 100-point strike
if current_atm_strike:
    normalized_strike = round(current_atm_strike / 100) * 100
    print(f"STEP 2: Normalized 100-point strike: {normalized_strike}")
else:
    print("ERROR: Could not determine ATM strike")
    sys.exit(1)

# Step 3: Get next week ATM data (using normalized strike)
print(f"\nSTEP 3: Fetching NEXT WEEK ATM ({normalized_strike})...")
next_atm_df = fetch_rolling_options(
    access_token, 'nifty', 1, 'ATM', 'CALL',
    entry_date.isoformat(), next_expiry.isoformat(), '5'
)

if next_atm_df.empty:
    print("ERROR: Could not fetch next week ATM data")
    sys.exit(1)

next_atm_price = get_price_at_time(next_atm_df, entry_dt)
next_atm_strike = get_strike_at_time(next_atm_df, entry_dt)
next_spot = get_spot_at_time(next_atm_df, entry_dt)

print(f"  Next Week ATM Strike: {next_atm_strike}")
print(f"  Next Week ATM Price @ 12:45: {next_atm_price}")
print(f"  Spot Price: {next_spot}")
print(f"  Data points: {len(next_atm_df)}")
print()

# Step 4: Calculate target strike (+600 from normalized)
target_strike = normalized_strike + 600
print(f"STEP 4: Target ATM+6 Strike: {target_strike}")
print()

# Step 5: Calculate Greeks for next week ATM
print("STEP 5: Calculating Greeks for next week ATM...")
days_to_expiry = 5.0  # Feb 26 to Mar 3 is about 5 days

if next_atm_price and next_spot and next_atm_strike:
    next_greeks = calculate_greeks(
        spot=next_spot,
        strike=next_atm_strike,
        time_to_expiry_days=days_to_expiry,
        option_price=next_atm_price,
        option_type="CE",
        is_sell=False
    )
    
    print(f"  Delta: {next_greeks.delta}")
    print(f"  Gamma: {next_greeks.gamma}")
    print(f"  Theta: {next_greeks.theta}")
    print(f"  Vega: {next_greeks.vega}")
    print(f"  IV: {next_greeks.iv}")
    print()
else:
    print("ERROR: Missing data for Greeks calculation")
    sys.exit(1)

# Step 6: Generate synthetic ATM+6 price
print(f"STEP 6: Generating synthetic ATM+6 ({target_strike})...")

strike_diff = target_strike - next_atm_strike
print(f"  Strike difference: {strike_diff} points")
print(f"  Using Delta: {next_greeks.delta}")

# Price adjustment using Delta
# For OTM calls, price decreases as strike increases
delta_adjustment = next_greeks.delta * strike_diff * -1
print(f"  Delta adjustment: {delta_adjustment:.2f}")

# Gamma adjustment for convexity
gamma_adjustment = 0.5 * next_greeks.gamma * (strike_diff ** 2) * 0.01
print(f"  Gamma adjustment: {gamma_adjustment:.2f}")

# Synthetic price
synthetic_price = next_atm_price + delta_adjustment - gamma_adjustment
synthetic_price = max(synthetic_price, 0.5)  # Floor at 0.5

print(f"\n  SYNTHETIC ATM+6 PRICE: {synthetic_price:.2f}")
print(f"  (Base: {next_atm_price:.2f} - Adjustment: {abs(delta_adjustment):.2f})")
print()

# Step 7: Create synthetic data frame
print("STEP 7: Synthetic data preview...")
if len(next_atm_df) >= 3:
    base_times = next_atm_df.index[:3]
    data = []
    for i, ts in enumerate(base_times):
        base_val = next_atm_df.iloc[i]['close']
        variation = (base_val - next_atm_price) / next_atm_price if next_atm_price > 0 else 0
        synth_price = synthetic_price * (1 + variation)
        
        data.append({
            'timestamp': ts,
            'open': round(next_atm_df.iloc[i]['open'] * (synthetic_price / next_atm_price), 2),
            'high': round(next_atm_df.iloc[i]['high'] * (synthetic_price / next_atm_price), 2),
            'low': round(next_atm_df.iloc[i]['low'] * (synthetic_price / next_atm_price), 2),
            'close': round(synth_price, 2),
            'volume': next_atm_df.iloc[i].get('volume', 100),
            'spot': next_spot,
            'strike': target_strike,
        })
    
    synth_df = pd.DataFrame(data)
    print(synth_df.to_string(index=False))

print()
print("=" * 60)
print("SUMMARY FOR CROSS-VERIFICATION")
print("=" * 60)
print(f"Current Week ATM: {current_atm_strike} @ {current_atm_price:.2f}")
print(f"Next Week ATM: {next_atm_strike} @ {next_atm_price:.2f}")
print(f"Next Week IV: {next_greeks.iv:.4f}")
print(f"Synthetic ATM+6 ({target_strike}): {synthetic_price:.2f}")
print()
print("Compare with your StockMojo manual data for validation.")
