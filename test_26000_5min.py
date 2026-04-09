import requests
import pandas as pd
from config import load_credentials
from dhan_rate_limit import throttle_dhan_data_api

client_id, access_token = load_credentials()
url = "https://api.dhan.co/v2/charts/rollingoption"
payload = {
    "exchangeSegment": "NSE_FNO",
    "interval": 5,
    "securityId": 13,
    "instrument": "OPTIDX",
    "expiryFlag": "WEEK",
    "expiryCode": 1,
    "strike": "26000",
    "drvOptionType": "CALL",
    "requiredData": ["open", "high", "low", "close", "volume", "spot", "strike", "iv"],
    "fromDate": "2026-02-26",
    "toDate": "2026-03-10",
}
headers = {"access-token": access_token, "Content-Type": "application/json"}
throttle_dhan_data_api()
resp = requests.post(url, json=payload, headers=headers, timeout=60)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    series = data.get("data", {}).get("ce")
    if series and series.get("timestamp"):
        df = pd.DataFrame({
            "close": series.get("close"),
            "strike": series.get("strike"),
            "iv": series.get("iv"),
        })
        print(f"Rows: {len(df)}")
        print("First 3 rows:")
        print(df.head(3))
    else:
        print("No data in response")
else:
    print(resp.text[:500])