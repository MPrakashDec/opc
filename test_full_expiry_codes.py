import requests
import pandas as pd
import pytz
from config import load_credentials
from dhan_rate_limit import throttle_dhan_data_api

IST = pytz.timezone('Asia/Kolkata')
client_id, access_token = load_credentials()
url = "https://api.dhan.co/v2/charts/rollingoption"

for code in range(5):
    payload = {
        "exchangeSegment": "NSE_FNO",
        "interval": 5,
        "securityId": 13,
        "instrument": "OPTIDX",
        "expiryFlag": "WEEK",
        "expiryCode": code,
        "strike": "26000",
        "drvOptionType": "CALL",
        "requiredData": ["open", "high", "low", "close", "volume", "spot", "strike", "iv"],
        "fromDate": "2026-02-26",
        "toDate": "2026-03-10",
    }
    headers = {"access-token": access_token, "Content-Type": "application/json"}
    throttle_dhan_data_api()
    resp = requests.post(url, json=payload, headers=headers, timeout=60)

    print(f"\n{'='*50}")
    print(f"ExpiryCode = {code}")
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Error: {resp.text[:300]}")
        continue

    data = resp.json()
    series = data.get("data", {}).get("ce")
    if not series or not series.get("timestamp"):
        print("No data in response")
        continue

    # Build DataFrame with all fields
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(series["timestamp"], unit="s", utc=True).tz_convert(IST),
        "open": series.get("open"),
        "high": series.get("high"),
        "low": series.get("low"),
        "close": series.get("close"),
        "volume": series.get("volume"),
        "spot": series.get("spot"),
        "strike": series.get("strike"),
        "iv": series.get("iv"),
    })
    print(f"Rows: {len(df)}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print("\nFirst 5 rows (all columns):")
    print(df.head(5).to_string())