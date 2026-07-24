"""Field classification and column contract for the derived annual table.

Follows the Buffett design spec section 6.1 annualization rules. Every Stage 1
raw field is a flow (sum of the 4 fiscal quarters), a stock (fiscal-Q4 value),
or a ytd-annual figure (Q4 full-year cumulative). This module is the single
source of the annual column names the warehouse and the metrics layer use.
"""

from __future__ import annotations

FLOW_FIELDS: tuple[str, ...] = (
    "saleq",
    "niq",
    "oiadpq",
    "xintq",
    "txtq",
    "epspxq",
    "oancfq",
    "prstkcq",
    "capxq",
    "dvpq",
    "cogsq",
    "xsgaq",
    "xrdq",
    "dpq",
)
YTD_ANNUAL_FIELDS: tuple[str, ...] = ("oancfy", "capxy", "prstkcy", "dvy")
STOCK_FIELDS: tuple[str, ...] = (
    "actq",
    "lctq",
    "ppentq",
    "gdwlq",
    "ivltq",
    "atq",
    "ceqq",
    "dlcq",
    "dlttq",
    "req",
    "tstkq",
    "cheq",
    "cshfdq",
    "cshopq",
    "cshoq",
    "ltq",
    "invtq",
    "rectq",
)

ANNUAL_KEY_COLUMNS: tuple[str, ...] = ("ticker", "fiscal_year")
ANNUAL_COMPLETENESS_COLUMNS: tuple[str, ...] = ("quarters_present", "has_q4")

# Ordered annual value columns: flow `_annual`, then ytd `_annual`, then stock `_q4`.
ANNUAL_VALUE_COLUMNS: tuple[str, ...] = (
    *(f"{field}_annual" for field in FLOW_FIELDS),
    *(f"{field}_annual" for field in YTD_ANNUAL_FIELDS),
    *(f"{field}_q4" for field in STOCK_FIELDS),
)
