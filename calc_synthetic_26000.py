import math
from scipy.stats import norm

def black_scholes_call(spot, strike, time_to_expiry_years, risk_free_rate, volatility):
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry_years) / (volatility * math.sqrt(time_to_expiry_years))
    d2 = d1 - volatility * math.sqrt(time_to_expiry_years)
    price = spot * norm.cdf(d1) - strike * math.exp(-risk_free_rate * time_to_expiry_years) * norm.cdf(d2)
    return price

# Data from 12:45 candle (10-Mar expiry)
spot = 25452.60
atm_strike = 25450.0
atm_price = 253.20
iv = 0.11049138  # 11.049138%

# Target strike
target_strike = 26000.0

# Time to expiry: from 26-Feb 12:45 to 10-Mar expiry (Tuesday). We'll use 12 days (approx) but you can adjust.
# Let's calculate exact days including hours: from 26-Feb 12:45 to 10-Mar 15:30 (typical expiry time) is 12 days + 2h45m = ~12.115 days.
# For simplicity, use 12.0 days for now.
time_to_expiry_years = 12.0 / 365.0
risk_free_rate = 0.10  # 10% as in greeks.py

synthetic_price = black_scholes_call(spot, target_strike, time_to_expiry_years, risk_free_rate, iv)

print(f"Spot: {spot}")
print(f"ATM Strike: {atm_strike}, ATM Price: {atm_price}, IV: {iv:.4%}")
print(f"Target Strike: {target_strike}")
print(f"Synthetic Price: {synthetic_price:.2f}")