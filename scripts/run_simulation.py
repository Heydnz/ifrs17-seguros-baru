"""Generate the synthetic administrative data of Seguros Baru (Phase 1).

    python scripts/run_simulation.py            # writes data/synthetic/*.csv
    python scripts/run_simulation.py --seed 7   # another reproducible world

The files hold the full simulated truth for events up to 31 December 2025; the engine
reads them through ifrs17.data.as_of(closing).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from ifrs17 import assumptions as A
from ifrs17.simulate import simulate_all, write

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=A.SEED)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "synthetic")
    args = parser.parse_args()
    t0 = time.time()
    out = simulate_all(args.seed)
    write(out, args.out)
    for name, df in out.items():
        print(f"{name:24s} {len(df):>8,d} rows")
    print(f"done in {time.time() - t0:.1f}s -> {args.out}")


if __name__ == "__main__":
    main()
