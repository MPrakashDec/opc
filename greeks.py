"""Calculate option Greeks using Black-Scholes model.

For index options (Nifty, Sensex) - European style.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


def _ndf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _ncdf(x: float) -> float:
    """Standard normal cumulative distribution function (approximation)."""
    # Abramowitz and Stegun approximation
    if x < -10:
        return 0.0
    if x > 10:
        return 1.0
    
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911
    
    sign = 1 if x >= 0 else -1
    x = abs(x) / math.sqrt(2.0)
    
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    
    return 0.5 * (1.0 + sign * y)


def _d1_d2(
    spot: float,
    strike: float,
    time_to_expiry: float,  # in years
    risk_free_rate: float,  # annual (e.g., 0.10 for 10%)
    volatility: float,  # annual (e.g., 0.20 for 20%)
) -> tuple[float, float]:
    """Calculate d1 and d2 for Black-Scholes."""
    if spot <= 0 or strike <= 0 or time_to_expiry <= 0 or volatility <= 0:
        return 0.0, 0.0
    
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility * volatility) * time_to_expiry) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    return d1, d2


@dataclass
class Greeks:
    """Option Greeks at a point in time."""
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0  # daily theta (per calendar day)
    vega: float = 0.0   # per 1% change in IV
    iv: float = 0.0     # implied volatility used
    
    def total_delta(self, qty: int, is_sell: bool = False) -> float:
        """Total delta for position quantity."""
        mult = -1 if is_sell else 1
        return self.delta * qty * mult


def calculate_greeks(
    spot: float,
    strike: float,
    time_to_expiry_days: float,
    option_price: float,
    option_type: str = "CE",  # "CE" or "PE"
    risk_free_rate: float = 0.10,  # 10% annual - India typical
    is_sell: bool = False,
) -> Greeks:
    """Calculate Greeks for an option.
    
    For sell positions, Greeks signs are inverted.
    
    Args:
        spot: Underlying spot price
        strike: Option strike price
        time_to_expiry_days: Days to expiry (can be fractional)
        option_price: Current option premium
        option_type: "CE" for Call, "PE" for Put
        risk_free_rate: Risk-free rate (annual)
        is_sell: True if short position (signs inverted)
    
    Returns:
        Greeks object with calculated values
    """
    time_to_expiry = max(time_to_expiry_days / 365.0, 0.0001)  # Convert to years, min 1 hour
    
    # Estimate IV from option price (reverse Black-Scholes approximation)
    # For ATM options, IV ≈ |price| / (0.4 * spot * sqrt(T))
    moneyness = spot / strike
    intrinsic = max(spot - strike, 0) if option_type == "CE" else max(strike - spot, 0)
    time_value = max(option_price - intrinsic, 0.01)
    
    # Rough IV estimate from time value
    iv_estimate = (time_value / (0.4 * spot * math.sqrt(time_to_expiry))) if spot > 0 else 0.2
    iv_estimate = max(min(iv_estimate, 1.0), 0.05)  # Clamp between 5% and 100%
    
    # Calculate d1, d2
    d1, d2 = _d1_d2(spot, strike, time_to_expiry, risk_free_rate, iv_estimate)
    
    sqrt_t = math.sqrt(time_to_expiry)
    ndf_d1 = _ndf(d1)
    
    # Delta
    if option_type == "CE":
        delta = _ncdf(d1)
    else:
        delta = _ncdf(d1) - 1.0
    
    # Gamma (same for calls and puts)
    gamma = ndf_d1 / (spot * iv_estimate * sqrt_t)
    
    # Theta (per year, then convert to daily)
    if option_type == "CE":
        theta_annual = -(spot * ndf_d1 * iv_estimate) / (2 * sqrt_t) - risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * _ncdf(d2)
    else:
        theta_annual = -(spot * ndf_d1 * iv_estimate) / (2 * sqrt_t) + risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * _ncdf(-d2)
    theta = theta_annual / 365.0  # Per calendar day
    
    # Vega (per 1% change in IV)
    vega = (spot * ndf_d1 * sqrt_t) / 100.0  # Per 1% IV change
    
    # Adjust signs for sell positions
    if is_sell:
        delta = -delta
        gamma = -gamma
        theta = -theta
        vega = -vega
    
    return Greeks(
        delta=round(delta, 4),
        gamma=round(gamma, 6),
        theta=round(theta, 2),
        vega=round(vega, 2),
        iv=round(iv_estimate, 4),
    )


def portfolio_greeks(positions: list[tuple[float, Greeks]]) -> Greeks:
    """Calculate portfolio-level Greeks from position list.
    
    Args:
        positions: List of (quantity, Greeks) tuples
    
    Returns:
        Aggregated Greeks
    """
    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    
    for qty, g in positions:
        total_delta += g.delta * qty
        total_gamma += g.gamma * qty
        total_theta += g.theta * qty
        total_vega += g.vega * qty
    
    return Greeks(
        delta=round(total_delta, 4),
        gamma=round(total_gamma, 6),
        theta=round(total_theta, 2),
        vega=round(total_vega, 2),
        iv=0.0,
    )
