"""
openmeteo_profile_pull.py  -  keep the temperature/cloud profile of every daylight hour

Run:   python openmeteo_profile_pull.py test   (one site, January 2025: checks key/URL)
       python openmeteo_profile_pull.py        (all sites in the four location lists)

Pulls ECMWF IFS 0.25 deg surface pressure, temperature and cloud cover on the
13 pressure levels (2024 -> yesterday) and saves, for every hour with the sun
above the horizon, the raw profile in a compact file:

    openmeteo/profiles25km/<site>.npz      (about 0.1-0.3 MB per site)

Temperature windows are then counted from these files by
openmeteo_layer_build.py, any number of times, with no new pull.
Restartable: sites already done are skipped. Timeouts are retried, and the
sites that still fail get a second pass at the end.
"""
import sys
import csv
import json
import re
import time
import socket
import datetime as dt
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

import numpy as np

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
OUTDIR = BASE / "profiles25km"
URL = "https://customer-historical-forecast-api.open-meteo.com/v1/forecast"
MODEL = "ecmwf_ifs025"
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
START = dt.date(2024, 1, 1)
SUN_KEEP_DEG = 0.0                 # hours with the sun at least this high are kept
LISTS = ["locations_current.csv", "locations_new.csv",
         "locations_admin_100km.csv", "locations_extra.csv", "locations_handpicked.csv"]
PAUSE_S = 0.3


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
    req = urllib.request.Request(url, headers={"User-Agent": "halo-profile-pull"})
    waits = [15, 30, 60, 120, 240]
    for attempt in range(len(waits) + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:120].replace("\n", " ")
            if e.code in (429, 500, 502, 503, 504) and attempt < len(waits):
                print(f"      HTTP {e.code}, retrying in {waits[attempt]} s")
                time.sleep(waits[attempt])
                continue
            raise RuntimeError(f"HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError, ValueError) as e:
            # ValueError: an empty or cut-off answer that is not valid JSON
            if attempt < len(waits):
                print(f"      {type(e).__name__}, retrying in {waits[attempt]} s")
                time.sleep(waits[attempt])
                continue
            raise


def col(h, k, n):
    return np.array([np.nan if v is None else v for v in h.get(k, [None] * n)], float)


def pull_site(key, name, lat, lon, elev, d_end, out):
    parts = []
    first = last = None
    chunks = []
    for y in range(START.year, d_end.year + 1):
        for a, b in ((dt.date(y, 1, 1), dt.date(y, 6, 30)), (dt.date(y, 7, 1), dt.date(y, 12, 31))):
            a, b = max(START, a), min(d_end, b)
            if a <= b:
                chunks.append((a, b))
    partdir = out.parent / "_parts"
    partdir.mkdir(exist_ok=True)
    for a, b in chunks:
        part = partdir / f"{out.stem}_{a:%Y%m}.json"
        if part.exists():
            j = json.loads(part.read_text(encoding="utf-8"))
        else:
            j = fetch(key, lat, lon, elev, a, b)
            if b < d_end:
                part.write_text(json.dumps(j), encoding="utf-8")      # finished half-year: keep for a restart
        h = j["hourly"]
        times = np.array(h["time"], dtype="datetime64[m]")
        n = len(times)
        sun = sun_elevation(lat, lon, times)
        keep = sun >= SUN_KEEP_DEG
        T = np.array([col(h, f"temperature_{L}hPa", n) for L in LEVELS]).T[keep]
        C = np.array([col(h, f"cloud_cover_{L}hPa", n) for L in LEVELS]).T[keep]
        ps = col(h, "surface_pressure", n)[keep]
        parts.append({
            "time": times[keep].astype("datetime64[m]").astype(np.int64),     # minutes since 1970, UTC
            "sun": np.rint(sun[keep]).astype(np.int8),
            "ps": np.where(np.isnan(ps), 0, np.rint(ps * 10)).astype(np.uint16),   # 0.1 hPa; 0 = missing
            "T": np.where(np.isnan(T), -128, np.clip(np.rint(T), -127, 127)).astype(np.int8),  # deg C
            "C": np.where(np.isnan(C), 255, np.clip(np.rint(C), 0, 100)).astype(np.uint8),     # %
        })
        print(f"      {a:%Y-%m}: {int(keep.sum())} daylight hours")
        if n:
            first = first or h["time"][0]
            last = h["time"][-1]
        time.sleep(PAUSE_S)
    data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    meta = {"name": name, "lat": lat, "lon": lon, "elev_m": elev, "model": MODEL,
            "levels": LEVELS, "first": first, "last": last, "sun_keep_deg": SUN_KEEP_DEG}
    tmp = out.with_name(out.stem + "_tmp.npz")
    np.savez_compressed(tmp, meta=np.array(json.dumps(meta)), **data)
    tmp.replace(out)
    for q in partdir.glob(f"{out.stem}_*.json"):
        q.unlink()


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    key = api_key()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    todo = sites()
    if arg == "test":
        global START
        name, lat, lon, elev = todo[0]
        START = dt.date(2025, 1, 1)
        print(f"Test: {name}, January 2025")
        out = OUTDIR / "_test.npz"
        pull_site(key, name, lat, lon, elev, dt.date(2025, 1, 31), out)
        z = np.load(out)
        print(f"OK: {len(z['ps'])} hours saved, temperatures {z['T'][0].tolist()}")
        return
    t0 = time.time()
    for rnd in (1, 2):
        failures = []
        if rnd == 2:
            print("\nSecond pass over the sites that failed")
        in_a_row = 0
        for i, (name, lat, lon, elev) in enumerate(todo, 1):
            out = OUTDIR / f"{safe(name)}.npz"
            if out.exists():
                continue
            print(f"[{i}/{len(todo)}] {name}")
            try:
                pull_site(key, name, lat, lon, elev, yesterday, out)
                in_a_row = 0
            except Exception as e:
                print(f"    FAILED: {e}")
                failures.append(f"{dt.datetime.now():%Y-%m-%d %H:%M}\t{name}\t{e}")
                if "limit" in str(e).lower():
                    break
                in_a_row += 1
                if in_a_row >= 3:
                    print(f"    {in_a_row} sites failed in a row: the server seems to be struggling, pausing 20 min "
                          f"({dt.datetime.now() + dt.timedelta(minutes=20):%H:%M})")
                    time.sleep(1200)
                    in_a_row = 0
        if not failures:
            break
    if failures:
        with open(BASE / "profiles25km_failures.txt", "a", encoding="utf-8") as fh:
            fh.write("\n".join(failures) + "\n")
        print(f"{len(failures)} failed; see {BASE / 'profiles25km_failures.txt'}")
    print(f"Pass took {(time.time() - t0) / 60:.1f} min. Next: python openmeteo_layer_build.py")


if __name__ == "__main__":
    main()
