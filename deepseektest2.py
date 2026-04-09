import requests
import pandas as pd
import pytz
from datetime import datetime
from config import load_credentials
from dhan_rate_limit import throttle_dhan_data_api

IST = pytz.timezone('Asia/Kolkata')

# Load token
client_id, access_token = load_credentials()

# API endpoint
url = "https://api.dhan.co/v2/charts/rollingoption"

payload = {
    "exchangeSegment": "NSE_FNO",
    "interval": 5,
    "securityId": 13,               # Nifty underlying
    "instrument": "OPTIDX",
    "expiryFlag": "WEEK",
    "expiryCode": 1,                # next expiry (index 1 for WEEK)
    "strike": "25500",
    "drvOptionType": "CALL",
    "requiredData": ["open", "high", "low", "close", "volume", "spot", "strike", "iv"],
    "fromDate": "2026-02-26",
    "toDate": "2026-03-10",
}

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "access-token": access_token,
}

throttle_dhan_data_api()
resp = requests.post(url, json=payload, headers=headers, timeout=60)

if resp.status_code != 200:
    print(f"Error: {resp.status_code} - {resp.text}")
else:
    data = resp.json()
    opt_key = "ce"
    series = data.get("data", {}).get(opt_key)
    if not series:
        print("No data in response")
    else:
        # Build DataFrame
        ts = series.get("timestamp", [])
        if not ts:
            print("No timestamps")
        else:
            df = pd.DataFrame({
                "open": series.get("open"),
                "high": series.get("high"),
                "low": series.get("low"),
                "close": series.get("close"),
                "volume": series.get("volume"),
                "spot": series.get("spot"),
                "strike": series.get("strike"),
                "iv": series.get("iv"),
            })
            dt_index = pd.to_datetime(ts, unit="s", utc=True).tz_convert(IST)
            df["timestamp"] = dt_index
            df = df.set_index("timestamp")

            print(f"Columns: {df.columns.tolist()}")
            print(f"Total data points: {len(df)}")
            print()

            # Find row at or before 12:55 IST
            target_dt = datetime(2026, 2, 26, 12, 55, tzinfo=IST)
            ts_target = pd.Timestamp(target_dt)
            mask = df.index <= ts_target
            if mask.any():
                row = df.loc[mask].iloc[-1]
                print(f"Closest candle to {target_dt.strftime('%Y-%m-%d %H:%M')} IST:")
                print(row)
                print()
                # Check if iv is present
                if 'iv' in row.index:
                    print(f"IV value: {row['iv']}")
                else:
                    print("No IV column in the row.")
            else:
                print(f"No candle at or before {target_dt}")