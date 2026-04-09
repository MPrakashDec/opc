import requests
import pandas as pd
import pytz
from datetime import datetime
from config import load_credentials
from dhan_rate_limit import throttle_dhan_data_api

IST = pytz.timezone('Asia/Kolkata')
client_id, access_token = load_credentials()

url = "https://api.dhan.co/v2/charts/rollingoption"

payload = {
    "exchangeSegment": "NSE_FNO",
    "interval": 1,                     # 1‑minute candles
    "securityId": 13,
    "instrument": "OPTIDX",
    "expiryFlag": "WEEK",
    "expiryCode": 1,
    "strike": "25500",
    "drvOptionType": "CALL",
    "requiredData": ["open", "high", "low", "close", "volume", "spot", "strike", "iv"],
    "fromDate": "2026-02-26",
    "toDate": "2026-02-26",            # only one day
}

headers = {"access-token": access_token, "Content-Type": "application/json"}
throttle_dhan_data_api()
resp = requests.post(url, json=payload, headers=headers, timeout=60)

if resp.status_code != 200:
    print(f"Error: {resp.status_code} - {resp.text}")
else:
    data = resp.json()
    series = data.get("data", {}).get("ce")
    if not series:
        print("No data")
    else:
        ts = series.get("timestamp", [])
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
        df.set_index("timestamp", inplace=True)

        print(f"Columns: {df.columns.tolist()}")
        print(f"Data points: {len(df)}")
        
        target = datetime(2026, 2, 26, 12, 45, tzinfo=IST)
        mask = df.index <= target
        if mask.any():
            row = df.loc[mask].iloc[-1]
            print("\nRow at or before 12:45 IST:")
            print(row)
        else:
            print("No candle before 12:45")