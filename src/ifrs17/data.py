"""Read the synthetic administrative data as it was known at a closing date.

The simulator writes the full truth for events up to 31 December 2025 (including
reports and payments made later). Every valuation reads it through ``as_of`` so that
it only uses information available at the reporting date (IFRS 17 par. 33(c), B54).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC = ROOT / "data" / "synthetic"

DATE_COLUMNS = ("issue_date", "exit_date", "expiry_date", "date", "occurrence_date", "report_date",
                "payment_date", "closing", "month_start")


@lru_cache(maxsize=None)
def load(name: str, folder: Path = SYNTHETIC) -> pd.DataFrame:
    path = folder / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run scripts/run_simulation.py first")
    df = pd.read_csv(path)
    for col in DATE_COLUMNS:
        if col in df:
            df[col] = pd.to_datetime(df[col])
    return df


def as_of(name: str, closing, folder: Path = SYNTHETIC) -> pd.DataFrame:
    """Rows of a table that the entity knew at ``closing`` (inclusive)."""
    c = pd.Timestamp(closing)
    df = load(name, folder)
    if name.endswith("_policies"):
        out = df[df["issue_date"] <= c].copy()
        if "exit_date" in out:
            # an exit after the closing date is not known yet
            future = out["exit_date"] > c
            out.loc[future, "exit_date"] = pd.NaT
            out.loc[future, "exit_reason"] = "inforce"
        return out
    if name.endswith("_claims"):
        return df[df["report_date"] <= c].copy()
    if name.endswith("_payments"):
        return df[df["payment_date"] <= c].copy()
    if name.endswith("_case_reserves"):
        return df[df["closing"] == c].copy()
    if name.endswith("_transactions") or name.endswith("_premiums"):
        return df[df["date"] <= c].copy()
    if name == "va_account_values":
        return df[df["closing"] == c].copy()
    if name == "va_account_ledger":
        return df[df["month_start"] <= c].copy()
    if name == "expenses":
        return df[pd.PeriodIndex(df["month"], freq="M").end_time <= c + pd.Timedelta(days=1)].copy()
    raise KeyError(name)


def life_inforce(product: str, closing) -> pd.DataFrame:
    """Life policies the entity treats as in force at ``closing``.

    A death that occurred but was not yet reported keeps the policy in force in the
    records; its claim is part of the IBNR in the liability for incurred claims.
    """
    c = pd.Timestamp(closing)
    pol = load(f"{product}_policies")
    pol = pol[pol["issue_date"] <= c].copy()
    claims = load(f"{product}_claims")
    reported = set(claims.loc[claims["report_date"] <= c, "policy_id"])
    lapsed = (pol["exit_reason"].isin(["lapse", "surrender"])) & (pol["exit_date"] <= c)
    dead_known = pol["policy_id"].isin(reported)
    return pol[~lapsed & ~dead_known].copy()


def elapsed_months(policies: pd.DataFrame, closing) -> pd.Series:
    """Whole months run from issue (first of the month) to the closing (month end)."""
    c = pd.Timestamp(closing)
    return (c.year - policies["issue_date"].dt.year) * 12 + (c.month - policies["issue_date"].dt.month) + 1
