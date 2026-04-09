import sys
sys.path.append('.')

from datetime import date
from data_fetcher import fetch_rolling_options
from config import load_credentials

client_id, access_token = load_credentials()

entry_date = date(2026, 2, 26)
next_expiry = date(2026, 3, 10)

# Fetch 5‑minute data for 25500 CE (round strike)
df = fetch_rolling_options(
    access_token,
    index='nifty',
    expiry_code=2,          # next expiry (2=next week)
    strike='25500',         # round strike (not ATM+6)
    option_type='CALL',
    from_date=entry_date.isoformat(),
    to_date=next_expiry.isoformat(),
    interval='5'
)

print(f"Data points: {len(df)}")
if not df.empty:
    print(df.head())
else:
    print("No data returned.")