"""
openmeteo_fingerprint.py  -  low/high cloud "fingerprint" for every site

Run:   python openmeteo_fingerprint.py

For every site file in ~/Downloads/grams/openmeteo/stats9km/ it counts the
daylight hours in each cell of an 11 x 11 table:
    low cloud cover  rounded to 0, 10, ... 100 %
    high cloud cover rounded to 0, 10, ... 100 %
separately for each calendar month. Writes one compact file,
~/Downloads/grams/openmeteo/fingerprints.json.gz, that the viewer reads.

Settings below: the years used, the sun elevation that counts as daylight,
and whether mid cloud counts as obstructing (added to low) or is ignored.
"""
import json
import gzip
import datetime as dt
from pathlib import Path

import numpy as np

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
SRC = BASE / "stats9km"
OUT = BASE / "fingerprints.json.gz"

YEAR_FROM, YEAR_TO = 2017, 2025      # whole years only, so every month counts equally
SUN_MIN_DEG = 0.0                    # daylight = sun at least this high (degrees)
OBSTRUCTION = "low"                  # "low", or "low+mid" (mid cloud added to low, capped at 100)


def sun_elevation(lat, lon, utc):
    """Solar elevation in degrees (NOAA approximation). utc: datetime64 array."""
    t = (utc - np.datetime64("2000-01-01T12:00")) / np.timedelta64(1, "D")
    g = np.radians((357.529 + 0.98560028 * t) % 360)
    q = (280.459 + 0.98564736 * t) % 360
    L = np.radians((q + 1.915 * np.sin(g) + 0.020 * np.sin(2 * g)) % 360)
    e = np.radians(23.439 - 0.00000036 * t)
    ra = np.arctan2(np.cos(e) * np.sin(L), np.cos(L))
    dec = np.arcsin(np.sin(e) * np.sin(L))
    gmst = (18.697374558 + 24.06570982441908 * t) % 24
    ha = np.radians(gmst * 15 + lon) - ra
    la = np.radians(lat)
    return np.degrees(np.arcsin(np.sin(la) * np.sin(dec) +
                                np.cos(la) * np.cos(dec) * np.cos(ha)))


def fingerprint(rec):
    """Return (counts[12, 11, 11], counts3[12, 6, 6, 6]).
    counts:  daylight hours per month by (high, low) in 10 % steps.
    counts3: daylight hours per month by (high, mid, low) in 20 % steps."""
    h = rec["hourly"]
    t0 = np.datetime64(rec["time_start"])
    n = rec["n_hours"]
    times = t0 + np.arange(n).astype("timedelta64[h]")
    years = times.astype("datetime64[Y]").astype(int) + 1970
    months = times.astype("datetime64[M]").astype(int) % 12
    low = np.array([np.nan if v is None else v for v in h["cloud_cover_low"]], float)
    high = np.array([np.nan if v is None else v for v in h["cloud_cover_high"]], float)
    if OBSTRUCTION == "low+mid":
        mid = np.array([np.nan if v is None else v for v in h["cloud_cover_mid"]], float)
        low = np.minimum(100.0, low + mid)
    # instantaneous values at the full hour; sun taken at the same moment
    sun = sun_elevation(rec["lat"], rec["lon"], times)
    ok = ((years >= YEAR_FROM) & (years <= YEAR_TO) & (sun >= SUN_MIN_DEG)
          & ~np.isnan(low) & ~np.isnan(high))
    lb = np.clip(np.rint(low[ok] / 10).astype(int), 0, 10)
    hb = np.clip(np.rint(high[ok] / 10).astype(int), 0, 10)
    counts = np.zeros((12, 11, 11), np.int32)
    np.add.at(counts, (months[ok], hb, lb), 1)

    # low : mid : high, always with the plain low (no mid added), 20 % steps
    low0 = np.array([np.nan if v is None else v for v in h["cloud_cover_low"]], float)
    mid0 = np.array([np.nan if v is None else v for v in h["cloud_cover_mid"]], float)
    ok3 = ok & ~np.isnan(low0) & ~np.isnan(mid0)
    l3 = np.clip(np.rint(low0[ok3] / 20).astype(int), 0, 5)
    m3 = np.clip(np.rint(mid0[ok3] / 20).astype(int), 0, 5)
    h3 = np.clip(np.rint(high[ok3] / 20).astype(int), 0, 5)
    counts3 = np.zeros((12, 6, 6, 6), np.int32)
    np.add.at(counts3, (months[ok3], h3, m3, l3), 1)
    return counts, counts3


def main():
    files = sorted(p for p in SRC.glob("*.json.gz") if not p.name.startswith("_"))
    out = {"settings": {"years": [YEAR_FROM, YEAR_TO], "sun_min_deg": SUN_MIN_DEG,
                        "obstruction": OBSTRUCTION, "bins": "0-100 step 10, rounded",
                        "bins3": "high, mid, low; 0-100 step 20, rounded; index (h*6+m)*6+l"},
           "sites": []}
    for i, p in enumerate(files, 1):
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        c, c3 = fingerprint(rec)
        el = (rec.get("grid") or {}).get("elevation")
        if el is None:
            el = rec.get("elev_m")
        out["sites"].append({"n": rec["name"], "la": rec["lat"], "lo": rec["lon"],
                             "el": None if el is None else round(float(el)),
                             "c": c.reshape(12, -1).tolist(),
                             "c3": c3.reshape(12, -1).tolist()})
        if i % 100 == 0:
            print(f"  {i}/{len(files)}")
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(files)} sites -> {OUT}")


if __name__ == "__main__":
    main()
