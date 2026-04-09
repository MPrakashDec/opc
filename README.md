# Dhan Options Backtest - Nifty 50 & Sensex

Backtest options strategy for [Dhan](https://dhan.co) using historical data from the Rolling Options API.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Add credentials to `token.txt`**
   ```
   client_id=your_client_id
   access_token=your_access_token
   ```
   Get these from [web.dhan.co](https://web.dhan.co). Access token is valid for 24 hours.

## Usage

```bash
python backtest.py --entry-date 2024-01-01 --index nifty
python backtest.py --entry-date 2024-06-01 --index sensex
```

Runs from `--entry-date` through **today**. Use `--no-dhan-margin` to skip the margin API and keep the 25% target vs **buy premium** only.

**Strategy:**
- **Entry**: Nifty 50 = Thursday 12:45 PM, Sensex = Monday 12:45 PM
- **Positions**: Entry1 = Current week ATM CE Buy 3 lots; Entry2 = Next expiry ATM+6 CE Buy 6 lots; Entry3 = Current expiry ATM+2 CE Sell 9 lots
- **Exit**: (1) Close all if PnL reaches **25% of Dhan [multi-leg margin](https://dhanhq.co/docs/v2/funds/)** when available, else 25% of buy premium; (2) Close all at 1 day before expiry at 11:45 AM
- **Expiry**: Nifty 50 = Tuesday, Sensex = Thursday. When expiry falls on holiday (e.g. 2026-03-03 Holi), it moves to previous trading day (2026-03-02).

Uses Dhan's [Rolling Options API](https://dhanhq.co/docs/v2/expired-options-data/) for historical data (up to 5 years).

**API rate limits:** Outbound calls to `api.dhan.co` are throttled to stay within Dhan’s published caps (Data ~10/s, Non-Trading ~20/s). See [Dhan API rate limits](https://dhan.co/support/platforms/dhanhq-api/what-are-the-api-rate-limits-for-dhan/).

**Troubleshooting:**
- Use **historical dates only** (e.g. 2024-01-01 to 2024-03-01). Future dates will fail.
- Access token expires in 24 hours – regenerate from [web.dhan.co](https://web.dhan.co).
- 400 error: Ensure Data API subscription is active on your Dhan account.
