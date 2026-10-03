"""Download US Treasury par yield curves and rebuild the month-end snapshot.

Run from the repository root on a machine with internet access:

    python scripts/download_treasury.py

It writes the full daily files to data/raw/treasury/par_<year>.csv and compares
the last business day of every month with data/raw/treasury/par_month_end_2023_2025.csv,
which was captured from the Treasury website on 2026-10-02. Any difference is
printed so the snapshot can be corrected before it is used.
"""

from __future__ import annotations

import io
import sys
import urllib.request
from pathlib import Path

import pandas as pd

URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
COLUMNS = {
    "1 Mo": "1M", "2 Mo": "2M", "3 Mo": "3M", "4 Mo": "4M", "6 Mo": "6M",
    "1 Yr": "1Y", "2 Yr": "2Y", "3 Yr": "3Y", "5 Yr": "5Y", "7 Yr": "7Y",
    "10 Yr": "10Y", "20 Yr": "20Y", "30 Yr": "30Y",
}
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "treasury"


def download(year: int) -> pd.DataFrame:
    with urllib.request.urlopen(URL.format(year=year), timeout=60) as resp:
        text = resp.read().decode("utf-8")
    (RAW / f"par_{year}.csv").write_text(text, encoding="utf-8")
    df = pd.read_csv(io.StringIO(text), parse_dates=["Date"])
    return df.rename(columns={"Date": "date", **COLUMNS})[["date", *COLUMNS.values()]]


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    daily = pd.concat([download(y) for y in (2023, 2024, 2025)]).sort_values("date")
    month_end = daily.groupby(daily["date"].dt.to_period("M")).tail(1).set_index("date")
    snapshot = pd.read_csv(RAW / "par_month_end_2023_2025.csv", parse_dates=["date"]).set_index("date")
    diff = (month_end.round(2) - snapshot.round(2)).abs()
    bad = diff[(diff > 1e-9).any(axis=1)]
    if bad.empty and month_end.index.equals(snapshot.index):
        print("Snapshot matches the Treasury files for all 36 month-ends.")
        return 0
    print("Differences found (percentage points):")
    print(bad if not bad.empty else "Dates differ:\n" + str(month_end.index.difference(snapshot.index)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
