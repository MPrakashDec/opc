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
    "interval": 5,
    "securityId": 13,
    "instrument": "OPTIDX",
    "expiryFlag": "WEEK",
    "expiryCode": 2,          # 10 March expiry
    "strike": "25500",
    "drvOptionType": "CALL",
    "requiredData": ["close", "spot", "strike", "iv", "timestamp"],
    "fromDate": "2026-02-26",
    "toDate": "2026-02-26",
}
headers = {"access-token": access_token, "Content-Type": "application/json"}
throttle_dhan_data_api()
resp = requests.post(url, json=payload, headers=headers, timeout=60)

if resp.status_code != 200:
    print(f"Error: {resp.status_code} - {resp.text}")
else:
    data = resp.json()
    series = data.get("data", {}).get("ce")
    if not series or not series.get("timestamp"):
        print("No data")
    else:
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(series["timestamp"], unit="s", utc=True).tz_convert(IST),
            "close": series.get("close"),
            "spot": series.get("spot"),
            "strike": series.get("strike"),
            "iv": series.get("iv"),
        })
        # Find row with timestamp exactly 12:45:00
        target = datetime(2026, 2, 26, 12, 45, tzinfo=IST)
        row = df[df["timestamp"] == target]
        if not row.empty:
            print(f"\nCandle at 12:45 IST:")
            print(row.iloc[0])
        else:
            # Show nearest timestamps
            print("\nNo candle at 12:45. Available timestamps around 12:45:")
            print(df[(df["timestamp"].dt.hour == 12) & (df["timestamp"].dt.minute >= 40) & (df["timestamp"].dt.minute <= 50)])