"""
openmeteo_boundary_check.py  -  at what temperature does ECMWF's "high" cloud sit?

Run:   python openmeteo_boundary_check.py                 (Tbilisi)
       python openmeteo_boundary_check.py Tbilisi Hotan   (any sites in the location lists)

For June-September 2024, 2025 and 2026 it pulls, for each daylight hour:
  - ECMWF IFS 9 km   low / mid / high cloud cover        (the bands in the fingerprints)
  - ECMWF IFS 25 km  low / mid / high cloud cover, surface pressure, and temperature,
                     cloud cover and height on the 13 pressure levels
and works out
  - the temperature and height of the band boundaries (0.8 and 0.45 x surface pressure)
  - for hours the model calls "high" cloud: the temperature of that cloud on the levels
  - for hours it calls "mid" cloud: the same

Prints a summary and writes openmeteo/boundary_<site>.json (hour by hour) for plotting.
A few calls per site. Reads the key from openmeteo/apikey.txt.
"""
import sys
import csv
import json
import time
import socket
import datetime as dt
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

import numpy as np

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
URL = "https://customer-historical-forecast-api.open-meteo.com/v1/forecast"
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
YEARS = [2024, 2025, 2026]
MONTHS = (6, 9)                    # June .. September
SUN_MIN_DEG = 0.0
CLOUDY = 40                        # a band counts as cloudy at >= this %
CLEAR = 20                         # ... and as clear at <= this %
LEVEL_CLOUD = 30                   # cloud on the level profile counts at >= this %
LISTS = ["locations_current.csv", "locations_new.csv",
         "locations_admin_100km.csv", "locations_extra.csv"]


def api_key():
    return (BASE / "apikey.txt").read_text(encoding="utf-8").strip()


def find_site(name):
    for f in LISTS:
        p = BASE / f
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if r["name"].lower() == name.lower() or r["name"].lower().startswith(name.lower() + ","):
                        return r["name"], float(r["lat"]), float(r["lon"])
    sys.exit(f"No site {name!r} in the location lists")


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


def fetch(key, lat, lon, d0, d1, model, hourly):
    p = {"latitude": lat, "longitude": lon, "start_date": d0.isoformat(),
         "end_date": d1.isoformat(), "hourly": ",".join(hourly), "models": model,
         "timezone": "GMT", "apikey": key}
    url = URL + "?" + urllib.parse.urlencode(p, safe=",")
    req = urllib.request.Request(url, headers={"User-Agent": "halo-boundary-check"})
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
                print(f"    {type(e).__name__}, retrying")
                time.sleep(10 * (attempt + 1))
                continue
            raise


def arr(h, k):
    return np.array([np.nan if v is None else v for v in h.get(k, [])], float)


def pull(key, lat, lon, y):
    d0, d1 = dt.date(y, MONTHS[0], 1), dt.date(y, MONTHS[1], 30)
    d1 = min(d1, dt.date.today() - dt.timedelta(days=1))
    if d1 < d0:
        return None
    bands = ["cloud_cover_low", "cloud_cover_mid", "cloud_cover_high"]
    j9 = fetch(key, lat, lon, d0, d1, "ecmwf_ifs", bands)
    lev = ["surface_pressure"] + bands + [f"{v}_{L}hPa" for v in
                                          ("temperature", "cloud_cover", "geopotential_height") for L in LEVELS]
    j25 = fetch(key, lat, lon, d0, d1, "ecmwf_ifs025", lev)
    return j9, j25


def analyse(name, lat, lon, j9, j25):
    h9, h = j9["hourly"], j25["hourly"]
    t = np.array(h["time"], dtype="datetime64[m]")
    t9 = np.array(h9["time"], dtype="datetime64[m]")
    idx9 = {v: i for i, v in enumerate(t9)}
    sun = sun_elevation(lat, lon, t)
    T = np.array([arr(h, f"temperature_{L}hPa") for L in LEVELS])
    C = np.array([arr(h, f"cloud_cover_{L}hPa") for L in LEVELS])
    Z = np.array([arr(h, f"geopotential_height_{L}hPa") for L in LEVELS])
    ps = arr(h, "surface_pressure")
    lnp = np.log(np.array(LEVELS, float))
    rows = []
    for i in range(len(t)):
        if sun[i] < SUN_MIN_DEG or np.isnan(ps[i]) or t[i] not in idx9:
            continue
        ok = ~np.isnan(T[:, i]) & ~np.isnan(C[:, i]) & (np.array(LEVELS) < ps[i])
        if ok.sum() < 4:
            continue
        x = lnp[ok][::-1]                                   # top -> bottom, increasing ln p
        tt, cc, zz = T[ok, i][::-1], C[ok, i][::-1], Z[ok, i][::-1]
        xf = np.linspace(x[0], x[-1], 120)
        tf, cf = np.interp(xf, x, tt), np.interp(xf, x, cc)
        zf = np.interp(xf, x, zz) if not np.isnan(zz).any() else np.full_like(xf, np.nan)
        pf = np.exp(xf)
        p_mh, p_lm = 0.45 * ps[i], 0.8 * ps[i]

        def at(p):                                          # T and z at pressure p
            xp = np.log(p)
            return float(np.interp(xp, x, tt)), (float(np.interp(xp, x, zz)) if not np.isnan(zz).any() else None)

        def cloud_temps(sel):                               # warmest (base) and cloudiest T in a band
            s = sel & (cf >= LEVEL_CLOUD)
            if not s.any():
                return None, None
            return float(tf[s].max()), float(tf[s][np.argmax(cf[s])])

        T_mh, z_mh = at(p_mh)
        T_lm, z_lm = at(p_lm)
        j = idx9[t[i]]
        rows.append({
            "time": str(t[i]),
            "l9": h9["cloud_cover_low"][j], "m9": h9["cloud_cover_mid"][j], "h9": h9["cloud_cover_high"][j],
            "l25": h["cloud_cover_low"][i], "m25": h["cloud_cover_mid"][i], "h25": h["cloud_cover_high"][i],
            "ps": float(ps[i]), "T_mh": T_mh, "z_mh": z_mh, "T_lm": T_lm, "z_lm": z_lm,
            "high_base_T": cloud_temps(pf < p_mh)[0], "high_peak_T": cloud_temps(pf < p_mh)[1],
            "mid_base_T": cloud_temps((pf >= p_mh) & (pf < p_lm))[0],
            "mid_peak_T": cloud_temps((pf >= p_mh) & (pf < p_lm))[1],
            "profile_T": [round(float(v), 1) for v in tt], "profile_C": [round(float(v)) for v in cc],
            "profile_p": [int(round(float(np.exp(v)))) for v in x],
        })
    return rows


def pct(a, f):
    a = np.array([v for v in a if v is not None], float)
    return (100 * f(a).mean() if len(a) else float("nan")), len(a)


def summary(name, rows):
    print(f"\n=== {name}: {len(rows)} daylight hours, June-September {YEARS[0]}-{YEARS[-1]} ===")
    Tmh = np.array([r["T_mh"] for r in rows])
    zmh = np.array([r["z_mh"] for r in rows if r["z_mh"] is not None])
    print(f"Mid/high boundary (0.45 x surface pressure): median {np.median(Tmh):.1f} C "
          f"(10-90 %: {np.percentile(Tmh, 10):.1f} .. {np.percentile(Tmh, 90):.1f} C)"
          + (f", height median {np.median(zmh):.0f} m" if len(zmh) else ""))
    Tlm = np.array([r["T_lm"] for r in rows])
    print(f"Low/mid boundary  (0.8 x surface pressure):  median {np.median(Tlm):.1f} C")
    print(f"Model surface pressure median {np.median([r['ps'] for r in rows]):.0f} hPa")
    for grid in ("9", "25"):
        for band, other in (("h", "m"), ("m", "h")):
            sel = [r for r in rows if (r[band + grid] or 0) >= CLOUDY and (r["l" + grid] or 0) <= CLEAR]
            key = "high" if band == "h" else "mid"
            base = [r[f"{key}_base_T"] for r in sel]
            peak = [r[f"{key}_peak_T"] for r in sel]
            print(f"\n{grid} km hours with {key} >= {CLOUDY}% and low <= {CLEAR}%: {len(sel)}")
            if not sel:
                continue
            n_none = sum(b is None for b in base)
            print(f"  level profile shows no cloud >= {LEVEL_CLOUD}% in that band: {n_none}")
            b = np.array([v for v in base if v is not None])
            p = np.array([v for v in peak if v is not None])
            if len(b):
                print(f"  cloud base temperature: median {np.median(b):.1f} C; "
                      f"warmer than -20: {100 * (b > -20).mean():.0f} %, warmer than -25: {100 * (b > -25).mean():.0f} %, "
                      f"warmer than -30: {100 * (b > -30).mean():.0f} %")
                print(f"  temperature of the cloudiest level: median {np.median(p):.1f} C; "
                      f"warmer than -25: {100 * (p > -25).mean():.0f} %")


def main():
    names = sys.argv[1:] or ["Tbilisi"]
    key = api_key()
    for nm in names:
        name, lat, lon = find_site(nm)
        print(f"{name} ({lat}, {lon})")
        rows = []
        for y in YEARS:
            r = pull(key, lat, lon, y)
            if r is None:
                continue
            got = analyse(name, lat, lon, *r)
            print(f"  {y}: {len(got)} daylight hours")
            rows += got
            time.sleep(0.5)
        out = BASE / f"boundary_{name.split(',')[0].replace(' ', '_')}.json"
        out.write_text(json.dumps({"name": name, "lat": lat, "lon": lon, "rows": rows}), encoding="utf-8")
        summary(name, rows)
        print(f"\nHour-by-hour data -> {out}")


if __name__ == "__main__":
    main()
