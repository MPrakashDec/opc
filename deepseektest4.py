import requests
import pandas as pd
import pytz
from datetime import datetime
from config import load_credentials
from dhan_rate_limit import throttle_dhan_data_api
from fno_security_lookup import get_scrip_master_detailed_df, find_option_security_id

IST = pytz.timezone('Asia/Kolkata')
client_id, access_token = load_credentials()

# Find security ID for 10 Mar 26000 CE
master = get_scrip_master_detailed_df()
sec_id = find_option_security_id(master, "nifty", date(2026, 3, 10), 26000, "CE")
if not sec_id:
    print("Security ID not found")
    exit(1)

print(f"Security ID: {sec_id}")

url = "https://api.dhan.co/v2/charts/option/intraday"
payload = {
    "securityId": str(sec_id),
    "exchangeSegment": "NSE_FNO",
    "instrumentType": "OPTIDX",
    "interval": 1,
    "fromDate": "2026-02-26",
    "toDate": "2026-02-26"
}
headers = {"access-token": access_token, "Content-Type": "application/json"}
throttle_dhan_data_api()
resp = requests.post(url, json=payload, headers=headers, timeout=60)

if resp.status_code != 200:
    print(f"Error: {resp.status_code} - {resp.text}")
else:
    data = resp.json().get("data", {})
    if not data or "start_Time" not in data:
        print("No data")
    else:
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["start_Time"], unit="s", utc=True).tz_convert(IST)
        df.set_index("timestamp", inplace=True)
        print(f"Data points: {len(df)}")
        target = datetime(2026, 2, 26, 12, 45, tzinfo=IST)
        mask = df.index <= target
        if mask.any():
            row = df.loc[mask].iloc[-1]
            print("\nRow at or before 12:45 IST:")
            print(row)
        else:
            print("No candle before 12:45")