"""
openmeteo_climate_pull.py  -  monthly climate (temperature, precipitation, sunshine) for every site

Run:   python openmeteo_climate_pull.py test   (one site; check the call counter on your
                                                Open-Meteo dashboard before and after)
       python openmeteo_climate_pull.py        (all sites in the location lists)

Pulls from Open-Meteo's historical weather archive (ERA5 reanalysis, refined with
ERA5-Land where available) the daily mean, maximum and minimum 2 m temperature,
precipitation, snowfall and sunshine duration for the climate normal period
1991-2020, and keeps for each site the monthly values of every year:

    openmeteo/climate/<site>.json.gz      (a few kB per site)

    months[year][month] = [tmean, tmax, tmin (deg C, monthly means of the daily values),
                           precipitation (mm), snowfall (cm), sunshine (h)]  (monthly totals)

Sites already pulled are skipped, so the run can be stopped and restarted at any time.
One request per site, six variables, 30 years of daily values.
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

BASE    = Path.home() / "Downloads" / "grams" / "openmeteo"
OUTDIR  = BASE / "climate"
URL     = "https://customer-archive-api.open-meteo.com/v1/archive"
DAILY   = ["temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
           "precipitation_sum", "snowfall_sum", "sunshine_duration"]
YEAR_FROM, YEAR_TO = 1991, 2020
PAUSE_S = 0.3
LISTS   = ["locations_current.csv", "locations_new.csv", "locations_admin_100km.csv",
           "locations_extra.csv", "locations_handpicked.csv", "locations_cities.csv"]


def api_key():
    p = BASE / "apikey.txt"
    if not p.exists():
        sys.exit(f"Put your API key (just the key, one line) in {p}")
    return p.read_text(encoding="utf-8").strip()


def sites():
    seen, out = set(), []
    for f in LISTS:
        p = BASE / f
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["name"] in seen:
                    continue
                seen.add(r["name"])
                out.append((r["name"], float(r["lat"]), float(r["lon"]),
                            float(r["elev_m"]) if (r.get("elev_m") or "").strip() else None))
    return out


def safe(name):
    return re.sub(r"[^\w\-]+", "_", name).strip("_")


def fetch(key, lat, lon, elev):
    p = {"latitude": lat, "longitude": lon, "start_date": f"{YEAR_FROM}-01-01",
         "end_date": f"{YEAR_TO}-12-31", "daily": ",".join(DAILY), "timezone": "auto", "apikey": key}
    if elev is not None:
        p["elevation"] = elev
    url = URL + "?" + urllib.parse.urlencode(p, safe=",")
    req = urllib.request.Request(url, headers={"User-Agent": "halo-climate-pull"})
    waits = [15, 30, 60, 120, 240]
    for attempt in range(len(waits) + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:160].replace("\n", " ")
            if e.code in (429, 500, 502, 503, 504) and attempt < len(waits):
                print(f"      HTTP {e.code}, retrying in {waits[attempt]} s")
                time.sleep(waits[attempt])
                continue
            raise RuntimeError(f"HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError, ValueError) as e:
            if attempt < len(waits):
                print(f"      {type(e).__name__}, retrying in {waits[attempt]} s")
                time.sleep(waits[attempt])
                continue
            raise


def monthly(j):
    """Daily series -> {year: [[tmean, tmax, tmin, prec, snow, sun_h] x 12]}; None where a month lacks data."""
    d = j["daily"]
    acc = {}
    for i, day in enumerate(d["time"]):
        y, m = int(day[:4]), int(day[5:7])
        a = acc.setdefault((y, m), {"n": 0, "v": [[] for _ in DAILY]})
        a["n"] += 1
        for k, v in enumerate(DAILY):
            x = d[v][i]
            if x is not None:
                a["v"][k].append(x)
    out = {}
    for (y, m), a in sorted(acc.items()):
        row = []
        for k, v in enumerate(DAILY):
            xs = a["v"][k]
            if len(xs) < 0.8 * a["n"]:
                row.append(None)
            elif k < 3:                                           # temperatures: monthly mean
                row.append(round(sum(xs) / len(xs), 2))
            elif v == "sunshine_duration":                        # seconds -> hours, monthly total
                row.append(round(sum(xs) / len(xs) * a["n"] / 3600, 1))
            else:                                                 # precipitation mm, snowfall cm: monthly total
                row.append(round(sum(xs) / len(xs) * a["n"], 1))
        out.setdefault(str(y), [None] * 12)[m - 1] = row
    return out


def pull_site(key, name, lat, lon, elev, out):
    j = fetch(key, lat, lon, elev)
    rec = {"name": name, "lat": lat, "lon": lon, "elev_m": elev,
           "grid": {k: j.get(k) for k in ("latitude", "longitude", "elevation")},
           "source": "Open-Meteo historical weather API (ERA5 / ERA5-Land)", "years": [YEAR_FROM, YEAR_TO],
           "fields": ["tmean_C", "tmax_C", "tmin_C", "precip_mm", "snow_cm", "sunshine_h"],
           "pulled_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "months": monthly(j)}
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(rec, fh, separators=(",", ":"))
    tmp.replace(out)
    return rec


def normals(rec):
    """Mean over the years, per month: for a quick look in the test."""
    rows = []
    for m in range(12):
        vals = [rec["months"][y][m] for y in rec["months"] if rec["months"][y][m]]
        rows.append([round(sum(v[k] for v in vals if v[k] is not None) / max(1, sum(v[k] is not None for v in vals)), 1)
                     for k in range(len(DAILY))])
    return rows


def main():
    key = api_key()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    todo = sites()
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        name, lat, lon, elev = next((s for s in todo if s[0].startswith("Tampere")), todo[0])
        print(f"Test: {name}, {YEAR_FROM}-{YEAR_TO}")
        rec = pull_site(key, name, lat, lon, elev, OUTDIR / "_test.json.gz")
        print("month  tmean  tmax  tmin  precip  snow  sunshine")
        for m, r in enumerate(normals(rec), 1):
            print(f"{m:5d} {r[0]:6.1f} {r[1]:5.1f} {r[2]:5.1f} {r[3]:7.1f} {r[4]:5.1f} {r[5]:8.1f}")
        print("\nNow look at the call counter on your Open-Meteo dashboard: the difference is the cost of one site.")
        return
    failed, t0 = [], time.time()
    left = [s for s in todo if not (OUTDIR / f"{safe(s[0])}.json.gz").exists()]
    print(f"{len(todo)} sites, {len(todo) - len(left)} already pulled, {len(left)} to go")
    for i, (name, lat, lon, elev) in enumerate(left, 1):
        out = OUTDIR / f"{safe(name)}.json.gz"
        try:
            pull_site(key, name, lat, lon, elev, out)
            print(f"[{i}/{len(left)}] {name}  ({(time.time() - t0) / 60:.1f} min)")
        except Exception as e:
            print(f"[{i}/{len(left)}] {name}: FAILED {e}")
            failed.append(name)
            if len(failed) >= 3 and len(failed) == i:
                sys.exit("The first three sites all failed: check the key and the connection.")
        time.sleep(PAUSE_S)
    if failed:
        (BASE / "climate_failures.txt").write_text("\n".join(failed), encoding="utf-8")
        print(f"{len(failed)} failed, listed in {BASE / 'climate_failures.txt'}; run again to retry them")
    print(f"Done -> {OUTDIR}")


if __name__ == "__main__":
    main()
