"""
openmeteo_layer_pull.py  -  cloud in a chosen temperature layer (e.g. -10 to -20 C)

Run:   python openmeteo_layer_pull.py test     (one site, one month: checks key/URL)
       python openmeteo_layer_pull.py          (all sites in the four location lists)
       python openmeteo_layer_pull.py combine  (only rebuild the combined file)

For every site it pulls ECMWF IFS 0.25 deg temperature and cloud cover on the
13 pressure levels (2024 -> yesterday; earlier dates have no pressure levels)
and reduces each daylight hour to three numbers per temperature window:

    layer  = cloud cover inside the window (e.g. between -10 and -20 C)
    below  = cloud cover warmer than the window   (hides the layer from below)
    above  = cloud cover colder than the window   (cirrus above it)

The profile is interpolated in log-pressure between the levels, so a window
always has a value even when no level falls inside it; levels below the
ground are dropped. Only these counts are kept, not the raw hours:

    openmeteo/layer25km/<site>.json.gz        one small file per site
    openmeteo/layer_fingerprints.json.gz      all sites, read by the viewer

Restartable: sites already done are skipped. Pressure-level cloud cover on
Open-Meteo is derived from relative humidity, not taken from the model.
"""
import sys
import csv
import json
import gzip
import re
import time
import datetime as dt
import urllib.request
import urllib.parse
import urllib.error
import socket
from pathlib import Path

import numpy as np

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
OUTDIR = BASE / "layer25km"
COMBINED = BASE / "layer_fingerprints.json.gz"
URL = "https://customer-historical-forecast-api.open-meteo.com/v1/forecast"
MODEL = "ecmwf_ifs025"
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
START = dt.date(2024, 1, 1)
SUN_MIN_DEG = 0.0
WINDOWS = [(-5, -15), (-10, -20), (-15, -25)]      # (warm edge, cold edge), deg C
LISTS = ["locations_current.csv", "locations_new.csv",
         "locations_admin_100km.csv", "locations_extra.csv"]
N_FINE = 80                                        # interpolation points per profile
PAUSE_S = 0.3


def wkey(w):
    return f"{w[0]}..{w[1]}"


def api_key():
    p = BASE / "apikey.txt"
    if not p.exists():
        sys.exit(f"Put your API key in {p}")
    return p.read_text(encoding="utf-8").strip()


def sites():
    out = []
    for f in LISTS:
        p = BASE / f
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    out.append((r["name"], float(r["lat"]), float(r["lon"]),
                                float(r["elev_m"]) if r.get("elev_m") else None))
    return out


def safe(name):
    return re.sub(r"[^\w\-]+", "_", name).strip("_")


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


def fetch(key, lat, lon, elev, d0, d1):
    hourly = ["surface_pressure"] + [f"{v}_{L}hPa" for v in ("temperature", "cloud_cover")
                                     for L in LEVELS]
    p = {"latitude": lat, "longitude": lon, "start_date": d0.isoformat(),
         "end_date": d1.isoformat(), "hourly": ",".join(hourly), "models": MODEL,
         "timezone": "GMT", "apikey": key}
    if elev is not None:
        p["elevation"] = elev
    url = URL + "?" + urllib.parse.urlencode(p, safe=",")
    req = urllib.request.Request(url, headers={"User-Agent": "halo-layer-pull"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as e:
            if attempt < 4:
                print(f"      {type(e).__name__}, retrying in {10 * (attempt + 1)} s")
                time.sleep(10 * (attempt + 1))
                continue
            raise


def reduce_hours(j, lat, lon, elev, counts, stats):
    """Add this chunk's daylight hours to counts[window][month, above, layer, below]."""
    h = j["hourly"]
    times = np.array(h["time"], dtype="datetime64[m]")
    months = times.astype("datetime64[M]").astype(int) % 12
    sun = sun_elevation(lat, lon, times)
    T = np.array([[np.nan if v is None else v for v in h[f"temperature_{L}hPa"]] for L in LEVELS])
    CC = np.array([[np.nan if v is None else v for v in h[f"cloud_cover_{L}hPa"]] for L in LEVELS])
    ps = np.array([np.nan if v is None else v for v in h.get("surface_pressure", [None] * len(times))])
    if np.all(np.isnan(ps)):
        z = elev if elev is not None else float(j.get("elevation", 0) or 0)
        ps[:] = 1013.25 * (1 - 2.25577e-5 * z) ** 5.25588
    lnp = np.log(np.array(LEVELS, float))
    for i in range(len(times)):
        if sun[i] < SUN_MIN_DEG:
            continue
        ok = (~np.isnan(T[:, i])) & (~np.isnan(CC[:, i])) & (np.array(LEVELS) < ps[i])
        if ok.sum() < 3:
            continue
        x = lnp[ok][::-1]                       # increasing ln p (top -> bottom)
        t = T[ok, i][::-1]
        c = CC[ok, i][::-1]
        xf = np.linspace(x[0], x[-1], N_FINE)
        tf = np.interp(xf, x, t)
        cf = np.interp(xf, x, c)
        stats["hours"] += 1
        for w in WINDOWS:
            warm, cold = w
            inside = (tf <= warm) & (tf >= cold)
            layer = cf[inside].max() if inside.any() else 0.0
            below = cf[tf > warm].max() if (tf > warm).any() else 0.0
            above = cf[tf < cold].max() if (tf < cold).any() else 0.0
            b = lambda v: min(5, max(0, int(round(v / 20))))
            counts[wkey(w)][months[i], b(above), b(layer), b(below)] += 1


def pull_site(key, name, lat, lon, elev, d_end, out):
    counts = {wkey(w): np.zeros((12, 6, 6, 6), np.int32) for w in WINDOWS}
    stats = {"hours": 0}
    first = last = None
    chunks = []
    for y in range(START.year, d_end.year + 1):
        for a, b in ((dt.date(y, 1, 1), dt.date(y, 6, 30)), (dt.date(y, 7, 1), dt.date(y, 12, 31))):
            a, b = max(START, a), min(d_end, b)
            if a <= b:
                chunks.append((a, b))
    for a, b in chunks:
        y = f"{a:%Y-%m}"
        j = fetch(key, lat, lon, elev, a, b)
        n0 = stats["hours"]
        reduce_hours(j, lat, lon, elev, counts, stats)
        got = stats["hours"] - n0
        print(f"      {y}: {got} daylight hours with data")
        if got:
            t = j["hourly"]["time"]
            first = first or t[0]
            last = t[-1]
        time.sleep(PAUSE_S)
    rec = {"name": name, "lat": lat, "lon": lon, "elev_m": elev, "model": MODEL,
           "daylight_hours": stats["hours"], "first": first, "last": last,
           "windows": {k: v.reshape(12, -1).tolist() for k, v in counts.items()}}
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(rec, fh)
    tmp.replace(out)


def combine():
    files = sorted(p for p in OUTDIR.glob("*.json.gz") if not p.name.startswith("_"))
    out = {"settings": {"model": MODEL, "start": START.isoformat(), "sun_min_deg": SUN_MIN_DEG,
                        "windows": [wkey(w) for w in WINDOWS],
                        "bins3": "above, layer, below; 0-100 step 20; index (a*6+m)*6+b"},
           "sites": []}
    for p in files:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            r = json.load(fh)
        out["sites"].append({"n": r["name"], "la": r["lat"], "lo": r["lon"],
                             "first": r["first"], "last": r["last"], "w": r["windows"]})
    with gzip.open(COMBINED, "wt", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(files)} sites -> {COMBINED}")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "combine":
        combine()
        return
    key = api_key()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    todo = sites()
    if arg == "test":
        name, lat, lon, elev = todo[0]
        global START
        START = dt.date(2025, 1, 1)
        print(f"Test: {name}, January 2025")
        pull_site(key, name, lat, lon, elev, dt.date(2025, 1, 31), OUTDIR / "_test.json.gz")
        print("OK")
        return
    t0 = time.time()
    for rnd in (1, 2):
        failures = []
        if rnd == 2:
            print("\nSecond pass over the sites that failed")
        for i, (name, lat, lon, elev) in enumerate(todo, 1):
            out = OUTDIR / f"{safe(name)}.json.gz"
            if out.exists():
                continue
            print(f"[{i}/{len(todo)}] {name}")
            try:
                pull_site(key, name, lat, lon, elev, yesterday, out)
            except Exception as e:
                print(f"    FAILED: {e}")
                failures.append(f"{dt.datetime.now():%Y-%m-%d %H:%M}\t{name}\t{e}")
                if "limit" in str(e).lower():
                    break
        if not failures:
            break
    if failures:
        with open(BASE / "layer25km_failures.txt", "a", encoding="utf-8") as fh:
            fh.write("\n".join(failures) + "\n")
        print(f"{len(failures)} failed; see {BASE / 'layer25km_failures.txt'}")
    print(f"Pass took {(time.time() - t0) / 60:.1f} min")
    combine()


if __name__ == "__main__":
    main()
