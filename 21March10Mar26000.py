# filename: check_dhan_data_v2.py
import pandas as pd
import requests
from datetime import datetime, date
import pytz
from config import load_credentials
from dhan_rate_limit import throttle_dhan_data_api
from fno_security_lookup import get_scrip_master_detailed_df, find_option_security_id

IST = pytz.timezone("Asia/Kolkata")

def fetch_backtest_missing_leg():
    """
    Diagnostic: Fetches data using the specific Security ID for 10-MAR-26 26000 CE.
    This bypasses the DH-905 error by being explicit.
    """
    client_id, access_token = load_credentials()
    url = "https://api.dhan.co/v2/charts/option/intraday" # Using intraday for specific ID
    
    # 1. Get the actual Security ID for the contract
    master_df = get_scrip_master_detailed_df()
    sec_id = find_option_security_id(
        master_df, 
        index="nifty", 
        expiry=date(2026, 3, 10), 
        strike=26000, 
        option_type="CE"
    )

    if not sec_id:
        print("Could not find Security ID for NIFTY 10-MAR-26 26000 CE in master list.")
        return

    print(f"Found Security ID: {sec_id}")

    # 2. Build payload for specific security
    payload = {
        "securityId": str(sec_id),
        "exchangeSegment": "NSE_FNO",
        "instrumentType": "OPTIDX",
        "interval": "1",
        "fromDate": "2026-02-26",
        "toDate": "2026-02-26"
    }

    headers = {
        "access-token": access_token,
        "Content-Type": "application/json",
    }

    print("Connecting to Dhan Intraday Chart API...")
    throttle_dhan_data_api()
    
    try:
        # Note: Using POST for charts as per Dhan docs
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            print(f"Error: {resp.status_code} - {resp.text}")
            return

        data = resp.json().get("data", {})
        if not data or "start_Time" not in data:
            print("No candle data returned for this Security ID on Feb 26.")
            return

        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["start_Time"], unit="s").dt.tz_localize("UTC").dt.astimezone(IST)
        df.set_index("timestamp", inplace=True)

        # Target our backtest entry window
        target_start = IST.localize(datetime(2026, 2, 26, 12, 45))
        target_end = IST.localize(datetime(2026, 2, 26, 12, 50))
        
        snapshot = df.loc[target_start:target_end]

        if snapshot.empty:
            print("Strike found, but no candles exist for the 12:45-12:50 window.")
        else:
            print("\n--- NIFTY 10-MAR-26 26000 CE | Verified Data ---")
            print(snapshot[['open', 'high', 'low', 'close', 'volume']])
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    fetch_backtest_missing_leg()