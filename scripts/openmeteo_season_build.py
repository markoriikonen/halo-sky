"""
openmeteo_season_build.py  -  high-cloud seasons, coverage and persistence

Run:   python openmeteo_season_build.py             (all sites, writes season.json.gz)
       python openmeteo_season_build.py test        (only prints the test sites)

Reads the hourly 9 km files in ~/Downloads/grams/openmeteo/stats9km/ (no new pull)
and counts, for every site, by five-day period ("pentad", 73 per year):

  h: daylight hours by high cloud cover (0, 10, ... 100 %) separately for
     low cloud <= LOW_MAX and low cloud > LOW_MAX           -> 22 numbers per pentad
  p: high-cloud hours (high >= PRESENT, day and night) by the length of the
     unbroken episode they belong to: 1, 2-3, 4-6, 7-12, 13-24, >24 hours
                                                            ->  6 numbers per pentad

From these the viewer gets presence (how often), coverage (thin vs sheet) and
persistence (wisps vs long sheets) for any season. Writes
~/Downloads/grams/openmeteo/season.json.gz and prints the test sites.
"""
import sys
import json
import gzip
from pathlib import Path

import numpy as np

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
SRC = BASE / "stats9km"
OUT = BASE / "season.json.gz"

YEAR_FROM, YEAR_TO = 2017, 2025      # whole years only
SUN_MIN_DEG = 0.0                    # daylight for the coverage counts
LOW_MAX = 40                         # low cloud split for the halo window
PRESENT = 20                         # high cloud counts as present at >= this %
EPISODE_BINS = [1, 2, 4, 7, 13, 25]  # lower edges of the episode-length classes, hours
TEST_SITES = [("Hurghada", [1, 2, 3, 4]), ("Chiang Mai", [2]), ("Chiang Mai", [4]), ("Chiang Mai", [7]),
              ("Darwin", [1]), ("Darwin", [7]), ("Siquijor", list(range(1, 13))), ("Riyadh", [1, 2, 3, 4])]


def sun_elevation(lat, lon, utc):
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


def series(rec, key):
    return np.array([np.nan if v is None else v for v in rec["hourly"][key]], float)


def pentad_of(times):
    """0..72; day 366 of a leap year goes into the last pentad."""
    doy = (times.astype("datetime64[D]") - times.astype("datetime64[Y]")).astype(int)   # 0..365
    return np.minimum(doy // 5, 72)


def episodes(present):
    """Length of the unbroken run each hour belongs to (0 where not present)."""
    p = present.astype(np.int8)
    d = np.diff(np.concatenate([[0], p, [0]]))
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    run = np.zeros(len(p), int)
    for s, e in zip(starts, ends):
        run[s:e] = e - s
    return run


def site_counts(rec):
    t0 = np.datetime64(rec["time_start"])
    times = t0 + np.arange(rec["n_hours"]).astype("timedelta64[h]")
    years = times.astype("datetime64[Y]").astype(int) + 1970
    inyr = (years >= YEAR_FROM) & (years <= YEAR_TO)
    pent = pentad_of(times)
    low, high = series(rec, "cloud_cover_low"), series(rec, "cloud_cover_high")
    sun = sun_elevation(rec["lat"], rec["lon"], times)

    # coverage, daylight
    ok = inyr & (sun >= SUN_MIN_DEG) & ~np.isnan(low) & ~np.isnan(high)
    hb = np.clip(np.rint(high[ok] / 10).astype(int), 0, 10)
    lc = (np.rint(low[ok] / 10) * 10 > LOW_MAX).astype(int)          # 0: low <= LOW_MAX, 1: more
    h = np.zeros((73, 2, 11), np.int32)
    np.add.at(h, (pent[ok], lc, hb), 1)

    # persistence, all hours (an episode does not stop at sunset); missing values break a run
    present = (high >= PRESENT) & ~np.isnan(high)
    run = episodes(present)
    sel = inyr & present
    eb = np.searchsorted(EPISODE_BINS, run[sel], side="right") - 1
    p = np.zeros((73, len(EPISODE_BINS)), np.int32)
    np.add.at(p, (pent[sel], eb), 1)
    return h, p


def months_to_pentads(months):
    """Calendar months (1-12) -> pentads whose middle day falls in them."""
    mid = np.datetime64("2023-01-01") + (np.arange(73) * 5 + 2).astype("timedelta64[D]")
    m = mid.astype("datetime64[M]").astype(int) % 12 + 1
    return [i for i in range(73) if m[i] in months]


def describe(name, h, p, months):
    ps = months_to_pentads(months)
    hh = h[ps].sum(0)                      # (2, 11)
    allh = hh.sum(0)                       # by high bin
    tot = allh.sum()
    pres = allh[2:].sum()                  # high >= 20 %
    thin = allh[2:5].sum() / pres if pres else np.nan      # 20-40 %
    midc = allh[5:8].sum() / pres if pres else np.nan      # 50-70 %
    sheet = allh[8:].sum() / pres if pres else np.nan      # 80-100 %
    win = hh[0, 5:].sum() / tot if tot else np.nan          # high >= 50, low <= LOW_MAX
    pp = p[ps].sum(0)
    ph = pp.sum()
    # mean episode length, weighted by hours (the length of the episode a random high-cloud hour is in)
    mids = np.array([1, 2.5, 5, 9.5, 18.5, 36])
    wlen = (pp * mids).sum() / ph if ph else np.nan
    long12 = pp[4:].sum() / ph if ph else np.nan
    short3 = pp[:2].sum() / ph if ph else np.nan
    mlab = "year" if len(months) == 12 else "+".join(str(m) for m in months)
    print(f"{name[:18]:18s} {mlab:8s} present {100 * pres / tot:3.0f}% | window {100 * win:3.0f}% | "
          f"of present: thin {100 * thin:3.0f} mid {100 * midc:3.0f} sheet {100 * sheet:3.0f} | "
          f"episodes: in <=3 h runs {100 * short3:3.0f}%, in >12 h runs {100 * long12:3.0f}%, typical {wlen:4.1f} h")


def main():
    test = len(sys.argv) > 1 and sys.argv[1] == "test"
    files = sorted(q for q in SRC.glob("*.json.gz") if not q.name.startswith("_"))
    if test:
        want = {n for n, _ in TEST_SITES}
        files = [q for q in files if any(q.name.startswith(w.replace(" ", "_")) for w in want)]
    out = {"settings": {"years": [YEAR_FROM, YEAR_TO], "sun_min_deg": SUN_MIN_DEG, "low_max": LOW_MAX,
                        "present": PRESENT, "episode_bins": EPISODE_BINS, "pentads": 73,
                        "h": "per pentad: [low<=low_max: high 0..100 step 10] + [low>low_max: same], daylight hours",
                        "p": "per pentad: high-cloud hours (all hours) by episode length class"},
           "sites": []}
    res = {}
    for i, q in enumerate(files, 1):
        with gzip.open(q, "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        h, p = site_counts(rec)
        res[rec["name"]] = (h, p)
        el = (rec.get("grid") or {}).get("elevation", rec.get("elev_m"))
        out["sites"].append({"n": rec["name"], "la": rec["lat"], "lo": rec["lon"],
                             "el": None if el is None else round(float(el)),
                             "h": h.reshape(73, -1).tolist(), "p": p.tolist()})
        if i % 100 == 0:
            print(f"  {i}/{len(files)}")
    print()
    for nm, months in TEST_SITES:
        hit = [k for k in res if k == nm or k.startswith(nm + ",")]
        if hit:
            describe(hit[0], *res[hit[0]], months)
        else:
            print(f"{nm}: not found")
    if not test:
        with gzip.open(OUT, "wt", encoding="utf-8") as fh:
            json.dump(out, fh, separators=(",", ":"))
        print(f"\n{len(files)} sites -> {OUT}")


if __name__ == "__main__":
    main()
