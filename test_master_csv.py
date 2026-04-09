import sys
sys.path.append('.')

from fno_security_lookup import get_scrip_master_detailed_df
from datetime import date

# Force refresh to ensure latest data
df = get_scrip_master_detailed_df(force_refresh=True)

print(f"Total rows: {len(df)}")
print("Columns:", df.columns.tolist())
print("\nFirst 3 rows:")
print(df.head(3))

# Search for NIFTY 10 Mar 26 26000 CE
mask = (
    (df['INSTRUMENT'] == 'OPTIDX') &
    (df['UNDERLYING_SYMBOL'] == 'NIFTY') &
    (df['OPTION_TYPE'] == 'CE') &
    (df['STRIKE_PRICE'] == 26000.0)
)
result = df.loc[mask]
print(f"\nFound {len(result)} rows for NIFTY 10 Mar 26 26000 CE")
if not result.empty:
    print(result[['SECURITY_ID', 'SM_EXPIRY_DATE', 'STRIKE_PRICE']].head())
else:
    # Also check for 10-Mar-26 expiry specifically
    # The expiry date column might be in a different format; try converting
    df['expiry_date'] = pd.to_datetime(df['SM_EXPIRY_DATE'], errors='coerce').dt.date
    mask2 = (
        (df['INSTRUMENT'] == 'OPTIDX') &
        (df['UNDERLYING_SYMBOL'] == 'NIFTY') &
        (df['OPTION_TYPE'] == 'CE') &
        (df['STRIKE_PRICE'] == 26000.0) &
        (df['expiry_date'] == date(2026, 3, 10))
    )
    result2 = df.loc[mask2]
    print(f"\nWith expiry date filter: found {len(result2)} rows")
    if not result2.empty:
        print(result2[['SECURITY_ID', 'SM_EXPIRY_DATE', 'STRIKE_PRICE']].head())