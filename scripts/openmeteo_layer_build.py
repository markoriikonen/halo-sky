"""
openmeteo_layer_build.py  -  count temperature windows from the saved profiles

Run:   python openmeteo_layer_build.py

Reads openmeteo/profiles25km/*.npz (from openmeteo_profile_pull.py) and, for
every temperature window in WINDOWS, counts the daylight hours per month by

    layer  = cloud cover inside the window      (e.g. between -10 and -20 C)
    below  = cloud cover warmer than the window
    above  = cloud cover colder than the window

in 20 % steps, as before. Writes the files the viewer reads:

    openmeteo/layer_windows/index.json.gz         settings and site list
    openmeteo/layer_windows/w_<warm>_<cold>.json.gz   one file per window

ALOFT_ONLY: a window that reaches the ground (the air at the surface is no
warmer than the window's warm edge, as in a Siberian winter) does not count
as a cloud layer: that hour is counted with layer = 0. Set it to False to
count surface layers too.
"""
import json
import gzip
import time
from pathlib import Path

import numpy as np

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
SRC = BASE / "profiles25km"
OUT = BASE / "layer_windows"
SUN_MIN_DEG = 0.0
ALOFT_ONLY = True
EDGES = list(range(0, -45, -5))                     # 0, -5, ... -40 C
WIDTHS = (5, 10, 15, 20)
WINDOWS = [(w, w - d) for w in EDGES for d in WIDTHS if w - d >= EDGES[-1]]
N_FINE = 80


def wkey(w):
    return f"{w[0]}..{w[1]}"


def fine_weights(levels):
    """Linear-in-ln(p) weights from the levels to N_FINE points (top -> bottom)."""
    lv = np.array(sorted(levels), float)              # 50 ... 1000 hPa
    x = np.log(lv)
    xf = np.linspace(x[0], x[-1], N_FINE)
    W = np.zeros((N_FINE, len(lv)))
    for i, v in enumerate(xf):
        k = min(np.searchsorted(x, v, side="right") - 1, len(lv) - 2)
        f = (v - x[k]) / (x[k + 1] - x[k])
        W[i, k], W[i, k + 1] = 1 - f, f
    return lv, np.exp(xf), W


def site_counts(z):
    meta = json.loads(str(z["meta"]))
    levels = meta["levels"]
    order = np.argsort(levels)                        # columns sorted 50 ... 1000 hPa
    lv, pf, W = fine_weights(levels)
    keep = z["sun"] >= SUN_MIN_DEG
    T = z["T"][keep][:, order].astype(float)
    C = z["C"][keep][:, order].astype(float)
    ps = z["ps"][keep] / 10.0
    months = z["time"][keep].astype("datetime64[m]").astype("datetime64[M]").astype(int) % 12
    miss = (T == -128) | (C == 255)
    T[miss] = 0
    C[miss] = 0
    tf = T @ W.T
    cf = C @ W.T
    bad_f = (miss.astype(float) @ (W.T > 0)) > 0      # fine point touches a missing level
    valid = (~bad_f) & (pf[None, :] < ps[:, None]) & (ps[:, None] > 0)
    good = valid.sum(1) >= 10
    tf, cf, valid, months = tf[good], cf[good], valid[good], months[good]
    last = N_FINE - 1 - np.argmax(valid[:, ::-1], axis=1)      # lowest point above ground
    t_sfc = tf[np.arange(len(tf)), last]
    b = lambda v: np.clip(np.rint(v / 20), 0, 5).astype(int)
    out = {}
    for w in WINDOWS:
        warm, cold = w
        inside = valid & (tf <= warm) & (tf >= cold)
        layer = np.where(inside, cf, 0).max(1)
        below = np.where(valid & (tf > warm), cf, 0).max(1)
        above = np.where(valid & (tf < cold), cf, 0).max(1)
        if ALOFT_ONLY:
            layer = np.where(t_sfc <= warm, 0, layer)
        cnt = np.zeros((12, 6, 6, 6), np.int32)
        np.add.at(cnt, (months, b(above), b(layer), b(below)), 1)
        out[wkey(w)] = cnt.reshape(-1)
    return meta, out


def main():
    files = sorted(p for p in SRC.glob("*.npz") if not p.name.startswith("_"))
    OUT.mkdir(parents=True, exist_ok=True)
    sites, per_win = [], {wkey(w): [] for w in WINDOWS}
    start = None
    t0 = time.time()
    for i, p in enumerate(files, 1):
        z = np.load(p)
        meta, cnt = site_counts(z)
        sites.append({"n": meta["name"], "la": meta["lat"], "lo": meta["lon"],
                      "first": meta["first"], "last": meta["last"]})
        start = min(start or meta["first"], meta["first"])
        for k, v in cnt.items():
            per_win[k].append(v.tolist())
        if i % 100 == 0:
            print(f"  {i}/{len(files)}  ({(time.time() - t0) / 60:.1f} min)")
    index = {"settings": {"model": "ecmwf_ifs025", "start": start[:10], "sun_min_deg": SUN_MIN_DEG,
                          "aloft_only": ALOFT_ONLY, "windows": [wkey(w) for w in WINDOWS],
                          "bins3": "above, layer, below; 0-100 step 20; index (a*6+m)*6+b; 12 months"},
             "sites": sites}
    with gzip.open(OUT / "index.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(index, fh, separators=(",", ":"))
    for w in WINDOWS:
        with gzip.open(OUT / f"w_{-w[0]}_{-w[1]}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump({"key": wkey(w), "c": per_win[wkey(w)]}, fh, separators=(",", ":"))
    print(f"{len(files)} sites, {len(WINDOWS)} windows -> {OUT}")


if __name__ == "__main__":
    main()
