from __future__ import annotations

"""Utility helpers for constructing instrument ids and bar_type strings.

Centralizes logic for formatting auxiliary instrument ids (e.g. deriving BTC instrument
id from a simplified `btc_symbol` and a template instrument id) and for building
bar_type strings from timeframe specifications.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Known instrument type tokens that may appear in instrument ids
KNOWN_INST_TYPES = {"PERP", "SWAP", "FUTURE", "CASH", "SPOT", "LINEAR"}


def _parse_inst_type_from_template(template_inst_id: str) -> str:
    """
    Parse the contract/instrument type from a template instrument id.

    Examples:
      - "AVAX-USDT-PERP.OKX" -> "PERP"
      - "BTC-USDT-SWAP.BINANCE" -> "SWAP"
      - "ETH-USDT.OKX" -> fallback "PERP"

    Returns an uppercase instrument type. Falls back to "PERP" if not detectable.
    """
    if not template_inst_id:
        return "PERP"

    base = template_inst_id.split(".")[0]
    parts = [p.strip().upper() for p in base.split("-") if p.strip()]
    if parts and parts[-1] in KNOWN_INST_TYPES:
        return parts[-1]
    return "PERP"


def _parse_venue_from_template(template_inst_id: str) -> Optional[str]:
    """
    Extract venue (exchange) token from a template instrument id, if present.

    Example:
      - "AVAX-USDT-PERP.OKX" -> "OKX"
      - "BTC-USDT-PERP" -> None
    """
    if not template_inst_id:
        return None
    if "." in template_inst_id:
        return template_inst_id.split(".")[-1]
    return None


def _strip_inst_type_from_symbol(symbol: str) -> str:
    """
    If the given symbol contains a trailing instrument type token (e.g. "-PERP"),
    strip that part and return the remaining core symbol.

    Examples:
      - "BTC-USDT-PERP" -> "BTC-USDT"
      - "ETH-USDT" -> "ETH-USDT"
    """
    parts = [p.strip() for p in symbol.split("-") if p.strip()]
    if parts and parts[-1].upper() in KNOWN_INST_TYPES:
        return "-".join(parts[:-1])
    return "-".join(parts)


def _normalize_aux_symbol(aux_symbol: str) -> str:
    """
    Normalize auxiliary symbol representations into the canonical 'BASE-USDT' form when possible.

    Rules:
      - If aux_symbol contains a '.' (already an instrument id), return the left-side (without venue).
      - If aux_symbol contains '-' and already includes 'USDT', return uppercase and stripped form.
      - If aux_symbol contains '-' but not USDT, return uppercased form (assume user provided hyphenated symbol).
      - If aux_symbol contains no '-' and ends with 'USDT' (e.g. 'BTCUSDT'), convert to 'BTC-USDT'.
      - If aux_symbol is a short base like 'BTC', convert to 'BTC-USDT' (common default).
    """
    if not aux_symbol:
        raise ValueError("aux_symbol must be a non-empty string")

    s = aux_symbol.strip().upper()

    # If it's already an instrument-like string with venue, strip venue part
    if "." in s:
        s = s.split(".")[0]

    # Remove any trailing known inst type, e.g. "BTC-USDT-PERP" -> "BTC-USDT"
    s = _strip_inst_type_from_symbol(s)

    # If already hyphenated, make sure it's uppercased
    if "-" in s:
        return s

    # If endswith USDT, split into base-USDT
    if s.endswith("USDT"):
        base = s[:-4]
        if not base:
            raise ValueError(f"Invalid aux_symbol: {aux_symbol}")
        return f"{base}-USDT"

    # Fallback: assume it's a base asset (e.g., 'BTC') -> 'BTC-USDT'
    return f"{s}-USDT"


def format_aux_instrument_id(
    aux_symbol: str,
    template_inst_id: Optional[str] = None,
    venue: Optional[str] = None,
    inst_type: Optional[str] = None,
) -> str:
    """
    Format an auxiliary symbol (like BTCUSDT, BTC-USDT, BTC) into a full instrument_id.

    Behavior / precedence:
      1. If `inst_type` is provided, it is used (uppercased) as the contract type.
      2. Else if `template_inst_id` is provided, the contract type is parsed from it.
      3. Otherwise the default contract type is "PERP".

    Venue resolution:
      - If `template_inst_id` contains a venue (e.g. '.OKX'), it takes precedence.
      - Otherwise the `venue` argument must be provided when no template venue exists.

    Examples:
      - format_aux_instrument_id("BTCUSDT", "AVAX-USDT-PERP.OKX") -> "BTC-USDT-PERP.OKX"
      - format_aux_instrument_id("btc", None, venue="OKX") -> "BTC-USDT-PERP.OKX"
      - format_aux_instrument_id("BTCUSDT", inst_type="SWAP", venue="BINANCE") -> "BTC-USDT-SWAP.BINANCE"

    Returns: instrument_id string like 'BTC-USDT-PERP.OKX'
    """
    formatted_symbol = _normalize_aux_symbol(aux_symbol)

    # Determine instrument type: explicit param > template-derived > default
    if inst_type:
        resolved_inst_type = inst_type.strip().upper()
    else:
        resolved_inst_type = "PERP"
        if template_inst_id:
            resolved_inst_type = _parse_inst_type_from_template(template_inst_id)

    tmpl_venue = None
    if template_inst_id:
        tmpl_venue = _parse_venue_from_template(template_inst_id)

    # Decide venue: template venue takes precedence over explicit venue argument
    resolved_venue = tmpl_venue or (venue and venue.strip().upper())
    if not resolved_venue:
        raise ValueError("venue is required when template_inst_id does not specify a venue")

    # Venue-specific type normalization: BINANCE uses PERP for perpetual contracts
    if resolved_venue == "BINANCE" and resolved_inst_type in ("SWAP", "PERP"):
        resolved_inst_type = "PERP"

    instrument_id = f"{formatted_symbol}-{resolved_inst_type}.{resolved_venue}"
    return instrument_id


def build_bar_type_from_timeframe(
    instrument_id: str,
    timeframe: str = "1d",
    price_type: str = "LAST",
    origination: str = "EXTERNAL",
) -> str:
    """
    Build a bar_type string from an instrument_id and timeframe.

    Example:
      build_bar_type_from_timeframe("BTC-USDT-PERP.OKX", "1d") ->
         "BTC-USDT-PERP.OKX-1-DAY-LAST-EXTERNAL"

    Note: This follows the project's convention: {instrument_id}-{period}-{UNIT}-{PRICE}-{ORIG}
    """
    tf = (timeframe or "1d").strip().lower()

    if tf.endswith("d"):
        period = tf[:-1] or "1"
        unit = "DAY"
    elif tf.endswith("h"):
        period = tf[:-1] or "1"
        unit = "HOUR"
    elif tf.endswith("m"):
        period = tf[:-1] or "1"
        unit = "MINUTE"
    else:
        # Unknown format, fallback to 1 day
        period = "1"
        unit = "DAY"

    return f"{instrument_id}-{period}-{unit}-{price_type.upper()}-{origination.upper()}"


def parse_instrument_id(instrument_id: str) -> Tuple[str, str, Optional[str]]:
    """
    Parse an instrument_id into components: (symbol, inst_type, venue)

    Example:
      parse_instrument_id("AVAX-USDT-PERP.OKX") -> ("AVAX-USDT", "PERP", "OKX")
      parse_instrument_id("BTC-USDT-PERP") -> ("BTC-USDT", "PERP", None)
    """
    if not instrument_id:
        raise ValueError("instrument_id must be non-empty")

    venue = None
    if "." in instrument_id:
        left, venue = instrument_id.split(".", 1)
        venue = venue.strip().upper()
    else:
        left = instrument_id

    parts = [p.strip() for p in left.split("-") if p.strip()]
    if parts and parts[-1].upper() in KNOWN_INST_TYPES:
        inst_type = parts[-1].upper()
        symbol = "-".join(parts[:-1])
    else:
        inst_type = "PERP"
        symbol = "-".join(parts)

    return symbol, inst_type, venue


__all__ = [
    "format_aux_instrument_id",
    "build_bar_type_from_timeframe",
    "parse_instrument_id",
]
