"""Dhan margin calculator (multi-leg) for combined F&O margin."""
from __future__ import annotations

from typing import Any

import requests

from dhan_rate_limit import throttle_dhan_non_trading_api

MARGIN_MULTI_URL = "https://api.dhan.co/v2/margincalculator/multi"

# NRML / carry-forward index options on Dhan typically use MARGIN product
FNO_PRODUCT_TYPE = "MARGIN"


def _parse_total_margin(payload: Any) -> float | None:
    """Extract total margin from multi-calculator JSON (handles key variants)."""
    if payload is None or not isinstance(payload, dict):
        return None
    for key in ("total_margin", "totalMargin"):
        v = payload.get(key)
        if v is not None:
            try:
                x = float(v)
                return x if x > 0 else None
            except (TypeError, ValueError):
                pass
    inner = payload.get("data")
    if isinstance(inner, dict):
        return _parse_total_margin(inner)
    return None


def margin_calculator_multi(
    access_token: str,
    client_id: str,
    scrip_list: list[dict[str, Any]],
    *,
    include_position: bool = False,
    include_order: bool = False,
) -> tuple[float | None, dict[str, Any]]:
    """
    POST /v2/margincalculator/multi.

    Each scrip item: exchangeSegment, transactionType, quantity, productType,
    securityId, price, triggerPrice (optional).

    Returns (total_margin_or_none, raw_json_dict).
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "access-token": access_token,
    }
    body: dict[str, Any] = {
        "includePosition": include_position,
        "includeOrder": include_order,
        "dhanClientId": str(client_id),
        "scripList": scrip_list,
    }
    throttle_dhan_non_trading_api()
    resp = requests.post(
        MARGIN_MULTI_URL,
        json=body,
        headers=headers,
        timeout=60,
    )
    try:
        data = resp.json()
    except ValueError:
        return None, {"error": "non-json", "text": resp.text[:500], "status": resp.status_code}

    if not resp.ok:
        return None, data if isinstance(data, dict) else {"raw": data, "status": resp.status_code}

    total = _parse_total_margin(data)
    return total, data


def build_strategy_scrip_list(
    exchange_segment: str,
    legs: list[tuple[str, str, int, float]],
) -> list[dict[str, Any]]:
    """
    legs: list of (BUY|SELL, security_id, quantity_units, limit_price).
    quantity_units = lots * lot_size for index options.
    """
    out: list[dict[str, Any]] = []
    for side, sec_id, qty, price in legs:
        out.append(
            {
                "exchangeSegment": exchange_segment.upper(),
                "transactionType": side.upper(),
                "quantity": int(qty),
                "productType": FNO_PRODUCT_TYPE,
                "securityId": str(sec_id),
                "price": float(price),
                "triggerPrice": 0.0,
            }
        )
    return out


def fetch_strategy_margin_total(
    access_token: str,
    client_id: str,
    exchange_segment: str,
    legs: list[tuple[str, str, int, float]],
) -> tuple[float | None, dict[str, Any]]:
    """Combined margin for all legs in one request (hedge-aware if API supports it)."""
    scrip = build_strategy_scrip_list(exchange_segment, legs)
    return margin_calculator_multi(access_token, client_id, scrip)
