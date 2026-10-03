"""Mortality: 1980 CSO base table, experience factor and improvement (IFRS 17 par. 33, B49-B58).

Best-estimate annual mortality for a life aged x in calendar year y:

    q_BE(x, y) = min(1, CSO80(x) x experience_factor x (1 - improvement) ** (y - BASE_YEAR))

The 1980 CSO is the pricing and statutory base used in many Latin American
markets; it carries margins and is old, so the experience factor brings it to
the insured population and the improvement reflects the mortality trend (B58).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data" / "raw" / "mortality" / "cso1980_anb.csv"
BASE_YEAR = 2023
MAX_AGE = 99  # the table closes with q = 1 at 99


@lru_cache(maxsize=1)
def cso1980() -> pd.DataFrame:
    """1980 CSO aggregate, ANB, ages 0-99: columns 'M' and 'F'."""
    df = pd.read_csv(DATA, comment="#").set_index("age")
    return df.rename(columns={"qx_male": "M", "qx_female": "F"})


def qx(sex: str, ages, factor=1.0, improvement: float = 0.0, years_from_base=0) -> np.ndarray:
    """Annual mortality rates for integer ages (array-friendly). Ages above 99 get q = 1."""
    ages = np.atleast_1d(np.asarray(ages, dtype=int))
    table = cso1980()[sex].to_numpy()
    base = np.where(ages > MAX_AGE, 1.0, table[np.clip(ages, 0, MAX_AGE)])
    scaled = base * np.asarray(factor) * (1.0 - improvement) ** np.asarray(years_from_base)
    return np.where(ages >= MAX_AGE, 1.0, np.clip(scaled, 0.0, 1.0))


def monthly_rate(annual) -> np.ndarray:
    """Monthly probability consistent with an annual one under a constant force: 1 - (1 - q) ** (1/12)."""
    annual = np.clip(np.asarray(annual, dtype=float), 0.0, 1.0)
    return 1.0 - (1.0 - annual) ** (1.0 / 12.0)
