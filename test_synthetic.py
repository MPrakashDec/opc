#!/usr/bin/env python3
"""Test synthetic ATM+6 data generator."""

import sys
sys.path.append('.')

from data_fetcher import fetch_atm_plus6_fallback
from datetime import date, datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')

# Read token
token_data = open('token.txt').read().strip().split('\n')
access_token = [line.split('=')[1].strip() for line in token_data if 'access_token' in line][0]

entry_date = date(2026, 2, 26)
entry_dt = datetime(2026, 2, 26, 12, 45, tzinfo=IST)
strike = 26000.0
expiry = date(2026, 3, 10)

print(f"Testing synthetic ATM+6 generation:")
print(f"  Entry date: {entry_date}")
print(f"  Target strike: {strike}")
print(f"  Next expiry: {expiry}")
print()

df, method = fetch_atm_plus6_fallback(access_token, 'nifty', entry_date, entry_dt, strike, expiry)

print(f"Method used: {method}")
print(f"Data shape: {df.shape if not df.empty else 'Empty'}")

if not df.empty:
    print("\nFirst few rows:")
    print(df.head())
    print(f"\nColumns: {df.columns.tolist()}")
else:
    print("No data generated")
