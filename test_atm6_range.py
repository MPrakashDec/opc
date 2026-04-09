import sys
sys.path.append('.')

import pandas as pd
import pytz
from datetime import date, datetime, timedelta
from config import load_credentials
from fno_security_lookup import get_scrip_master_detailed_df, find_option_security_id
from data_fetcher import fetch_intraday_option

IST = pytz.timezone('Asia/Kolkata')

client_id, access_token = load_credentials()

# Get security ID for 10 Mar 26000 CE
master = get_scrip_master_detailed_df()
sec_id = find_option_security_id(master, 'nifty', date(2026, 3, 10), 26000, 'CE')
if not sec_id:
    print("Security ID not found")
    sys.exit(1)

print(f"Security ID: {sec_id}")

# Date range: entry 26 Feb to exit 9 Mar (inclusive)
start = date(2026, 2, 26)
end = date(2026, 3, 9)

all_dfs = []
current = start
while current <= end:
    print(f"Fetching {current}...")
    df = fetch_intraday_option(access_token, sec_id, current.isoformat(), current.isoformat(), interval='1')
    if not df.empty:
        all_dfs.append(df)
        print(f"  -> {len(df)} rows")
    else:
        print(f"  -> No data")
    current += timedelta(days=1)

if not all_dfs:
    print("No data for any day")
    sys.exit(1)

combined = pd.concat(all_dfs)
combined = combined.sort_index()

print(f"\nTotal rows: {len(combined)}")
print(f"Date range: {combined.index.min()} to {combined.index.max()}")
print(f"Columns: {combined.columns.tolist()}")

# Entry time: 12:45 on 26 Feb
target_entry = datetime(2026, 2, 26, 12, 45, tzinfo=IST)
mask = combined.index <= target_entry
if mask.any():
    row = combined.loc[mask].iloc[-1]
    print(f"\nClosest candle to entry time {target_entry.strftime('%Y-%m-%d %H:%M')}:")
    print(row)
else:
    print("No candle before entry time")

# Exit time: 11:45 on 9 Mar
target_exit = datetime(2026, 3, 9, 11, 45, tzinfo=IST)
mask = combined.index <= target_exit
if mask.any():
    row = combined.loc[mask].iloc[-1]
    print(f"\nClosest candle to exit time {target_exit.strftime('%Y-%m-%d %H:%M')}:")
    print(row)
else:
    print("No candle before exit time")