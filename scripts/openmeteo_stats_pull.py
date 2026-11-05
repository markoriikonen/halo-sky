"""
openmeteo_stats_pull.py  -  ECMWF 9 km cloud cover, 2017 -> yesterday, for all sites

Run:   python openmeteo_stats_pull.py test     (one site, one month: checks key/URL)
       python openmeteo_stats_pull.py          (all sites in locations_current.csv)
       python openmeteo_stats_pull.py Riyadh   (one named site, full period)
       python openmeteo_stats_pull.py locations_new.csv   (sites from another list
                                                in the openmeteo folder)
       python openmeteo_stats_pull.py all      (all four lists; retries anything
                                                missing, logs failures to
                                                openmeteo/stats9km_failures.txt)

Reads   ~/Downloads/grams/openmeteo/apikey.txt          (your Open-Meteo key)
        ~/Downloads/grams/openmeteo/locations_current.csv (name, lat, lon, elev_m)
Writes  ~/Downloads/grams/openmeteo/stats9km/<site>.json.gz

Each site file holds hourly UTC series of cloud_cover, cloud_cover_low,
cloud_cover_mid and cloud_cover_high from model ecmwf_ifs (IFS HRES 9 km),
pulled one calendar year per request. Sites already complete are skipped,
so the run can be stopped and restarted at any time.
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
OUTDIR  = BASE / "stats9km"
URL     = "https://customer-historical-forecast-api.open-meteo.com/v1/forecast"
MODEL   = "ecmwf_ifs"
VARS    = ["cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high"]
START   = dt.date(2017, 1, 1)
PAUSE_S = 0.3


def api_key():
    p = BASE / "apikey.txt"
    if not p.exists():
        sys.exit(f"Put your API key (just the key, one line) in {p}")
    return p.read_text(encoding="utf-8").strip()


def sites(listfile="locations_current.csv"):
    with open(BASE / listfile, encoding="utf-8") as fh:
        return [(r["name"], float(r["lat"]), float(r["lon"]),
                 float(r["elev_m"]) if r.get("elev_m") else None)
                for r in csv.DictReader(fh)]


def safe(name):
    return re.sub(r"[^\w\-]+", "_", name).strip("_")


def fetch(key, lat, lon, elev, d0, d1):
    p = {"latitude": lat, "longitude": lon, "start_date": d0.isoformat(),
         "end_date": d1.isoformat(), "hourly": ",".join(VARS),
         "models": MODEL, "timezone": "GMT", "apikey": key}
    if elev is not None:
        p["elevation"] = elev
    url = URL + "?" + urllib.parse.urlencode(p, safe=",")
    req = urllib.request.Request(url, headers={"User-Agent": "halo-stats-pull"})
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


def pull_site(key, name, lat, lon, elev, d_start, d_end, out):
    series = {v: [] for v in VARS}
    times = []
    meta = None
    y = d_start.year
    while y <= d_end.year:
        a = max(d_start, dt.date(y, 1, 1))
        b = min(d_end, dt.date(y, 12, 31))
        j = fetch(key, lat, lon, elev, a, b)
        h = j["hourly"]
        times += h["time"]
        for v in VARS:
            series[v] += h[v]
        if meta is None:
            meta = {k: j.get(k) for k in ("latitude", "longitude", "elevation")}
        n_ok = sum(x is not None for x in h["cloud_cover_high"])
        print(f"      {y}: {len(h['time'])} h, {n_ok} with data")
        time.sleep(PAUSE_S)
        y += 1
    rec = {"name": name, "lat": lat, "lon": lon, "elev_m": elev, "model": MODEL,
           "grid": meta, "pulled_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
           "time_start": times[0], "time_end": times[-1], "n_hours": len(times),
           "hourly": series}
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(rec, fh)
    tmp.replace(out)


def main():
    key = api_key()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "test":
        name, lat, lon, elev = sites()[0]
        print(f"Test: {name}, one month")
        out = OUTDIR / "_test.json.gz"
        pull_site(key, name, lat, lon, elev, dt.date(2017, 1, 1),
                  dt.date(2017, 1, 31), out)
        print(f"OK -> {out}")
        return

    if arg == "all":
        todo, arg = [], None
        for f in ("locations_current.csv", "locations_new.csv",
                  "locations_admin_100km.csv", "locations_extra.csv", "locations_handpicked.csv"):
            if (BASE / f).exists():
                todo += sites(f)
    elif arg and arg.lower().endswith(".csv"):
        todo, arg = sites(arg), None
    else:
        todo = sites()
    if arg:
        todo = [s for s in todo if s[0].lower() == arg.lower()]
        if not todo:
            sys.exit(f"No site named {arg!r} in locations_current.csv")

    t0 = time.time()
    failures = []
    for i, (name, lat, lon, elev) in enumerate(todo, 1):
        out = OUTDIR / f"{safe(name)}.json.gz"
        if out.exists():
            continue
        print(f"[{i}/{len(todo)}] {name}")
        try:
            pull_site(key, name, lat, lon, elev, START, yesterday, out)
        except Exception as e:
            print(f"    FAILED: {e}")
            failures.append(f"{dt.datetime.now():%Y-%m-%d %H:%M}\t{name}\t{lat}\t{lon}\t{e}")
            if "limit" in str(e).lower():
                sys.exit("Stopped at an API limit; run again later to continue.")
    if failures:
        with open(BASE / "stats9km_failures.txt", "a", encoding="utf-8") as fh:
            fh.write("\n".join(failures) + "\n")
        print(f"\n{len(failures)} site(s) failed; details in {BASE / 'stats9km_failures.txt'}")
    done = len(list(OUTDIR.glob("*.json.gz"))) - (1 if (OUTDIR / "_test.json.gz").exists() else 0)
    print(f"\nFinished pass in {(time.time() - t0) / 60:.1f} min. "
          f"{done} site files in {OUTDIR}")


if __name__ == "__main__":
    main()
