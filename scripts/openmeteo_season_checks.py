"""
openmeteo_season_checks.py  -  is each site's average high-cloud season really there?

Run:   python openmeteo_season_checks.py

Reads openmeteo/season_years/ (from openmeteo_season_build.py) and, for every site,
light setting (daylight / + twilight / all hours), measure (high cloud present /
halo window with low cloud <= 40 %) and high-cloud threshold (10 ... 100 %), works
out from the whole years 2017-2025 (30-day averages):

  agree        how well the average curves of the odd and the even years match
               (correlation, -1 ... 1): does the seasonal shape repeat?
  luck         chance that a swing as large as the average curve's comes from
               weather alone: each year is shifted by a random number of days,
               destroying any common season but keeping the weather (300 tries)
  reliability  share of each year's ups and downs that the average seasonal
               shape accounts for (0 ... 1): will the season be there in a given year?

Writes openmeteo/season_checks.json.gz, read by the viewer. No API calls.
"""
import gzip
import json
from pathlib import Path

import numpy as np

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
SRC = BASE / "season_years"
OUT = BASE / "season_checks.json.gz"
LAST_WHOLE_YEAR = 2025
LIGHT_SETS = {"day": [0], "twilight": [0, 1], "all": [0, 1, 2]}
MEASURES = ("pres", "win")
THRESHOLDS = list(range(10, 101, 10))
N_SHUFFLE = 300
NP = 73
rng = np.random.default_rng(1)


def smooth(tot, m):
    """Centred 30-day (6-pentad) average, wrapping within each year."""
    k = np.arange(NP)[:, None] + np.arange(-3, 3)[None, :]
    k %= NP
    T = tot[:, k].sum(2)
    M = m[:, k].sum(2)
    return np.where(T > 0, M / np.maximum(T, 1), np.nan)


def checks(y):
    """y: years x valid pentads (30-day shares). Returns agree, luck, reliability."""
    if y.shape[0] < 4 or y.shape[1] < 20 or np.isnan(y).any():
        return np.nan, np.nan, np.nan
    avg = y.mean(0)
    swing = avg.max() - avg.min()
    a, b = y[0::2].mean(0), y[1::2].mean(0)
    agree = np.corrcoef(a, b)[0, 1] if a.std() > 0 and b.std() > 0 else np.nan
    V = y.shape[1]
    sh = rng.integers(0, V, size=(N_SHUFFLE, y.shape[0]))
    idx = (np.arange(V)[None, None, :] + sh[:, :, None]) % V
    shuffled = y[np.arange(y.shape[0])[None, :, None], idx].mean(1)
    luck = float((shuffled.max(1) - shuffled.min(1) >= swing).mean())
    d = y - y.mean(1, keepdims=True)
    c = avg - avg.mean()
    den = (d ** 2).sum()
    rel = 1 - ((d - c) ** 2).sum() / den if den > 0 else np.nan
    return agree, luck, rel


def main():
    idx = json.load(gzip.open(SRC / "index.json.gz", "rt"))
    years, chunk, names = idx["years"], idx["chunk"], idx["sites"]
    whole = [k for k, yr in enumerate(years) if yr <= LAST_WHOLE_YEAR]
    ny, size = len(years), 3 * len(years) * NP * 22
    out = {"settings": {"years": [years[whole[0]], years[whole[-1]]], "light": list(LIGHT_SETS), "measures": list(MEASURES),
                        "thresholds": THRESHOLDS, "shuffles": N_SHUFFLE,
                        "encoding": "per site [light][measure][threshold][agree, luck, reliability]; agree and reliability as (x+1)*100, luck as x*200; 255 = none"},
           "sites": {}}
    for c0 in range(0, len(names), chunk):
        raw = np.frombuffer(gzip.decompress((SRC / f"y_{c0 // chunk:03d}.bin").read_bytes()), np.uint8)
        for j, name in enumerate(names[c0:c0 + chunk]):
            blk = raw[j * size:(j + 1) * size].reshape(3, ny, NP, 2, 11).astype(float)[:, whole]
            vals = []
            for light, cls in LIGHT_SETS.items():
                b = blk[cls].sum(0)                                   # year, pentad, low class, high bin
                tot = b.sum((2, 3))
                allyrs = tot.sum(0)
                valid = allyrs >= 0.25 * allyrs.max() if allyrs.max() > 0 else np.zeros(NP, bool)
                for meas in MEASURES:
                    for thr in THRESHOLDS:
                        tb = thr // 10
                        m = b[:, :, :, tb:].sum((2, 3)) if meas == "pres" else b[:, :, 0, tb:].sum(2)
                        y = smooth(tot, m)[:, valid]
                        ag, lu, re = checks(y)
                        vals += [255 if np.isnan(ag) else int(round((ag + 1) * 100)),
                                 255 if np.isnan(lu) else int(round(lu * 200)),
                                 255 if np.isnan(re) else int(round((max(-1, re) + 1) * 100))]
            out["sites"][name] = vals
        print(f"  {min(c0 + chunk, len(names))}/{len(names)}")
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"{len(names)} sites -> {OUT}")


if __name__ == "__main__":
    main()
