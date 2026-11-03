"""
openmeteo_quick.py  -  quick ECMWF gram for any place, right now

Run:   python openmeteo_quick.py "Puerto La Cruz" 10.21 -64.63
       python openmeteo_quick.py "Puerto La Cruz" 10.21 -64.63 3 2
                                  name           lat    lon  past next (days)
       python openmeteo_quick.py Riyadh 24.69 46.72 2026-07-27 2026-09-13
                                  name   lat   lon   from       to   (archive)

Pulls ECMWF IFS 0.25 (pressure levels) from the Open-Meteo forecast API:
the last few days (as already analysed) plus the next days, saves the data
as quick_<name>.json in ~/Downloads/grams/openmeteo/ and draws
quick_<name>.png next to it with openmeteo_gram.py (same folder as this
script). Needs numpy and matplotlib for the drawing step; if they are
missing the JSON is still saved.
"""

import sys
import json
import re
import datetime as dt
import urllib.request
import urllib.parse
from pathlib import Path

URL    = "https://api.open-meteo.com/v1/forecast"
ARCH   = "https://historical-forecast-api.open-meteo.com/v1/forecast"
MODEL  = "ecmwf_ifs025"
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
PL     = ["temperature", "relative_humidity", "cloud_cover", "geopotential_height"]
SURF   = ["temperature_2m", "cloud_cover", "cloud_cover_low", "cloud_cover_mid",
          "cloud_cover_high", "precipitation", "cape", "is_day", "surface_pressure"]
OUT    = Path.home() / "Downloads" / "grams" / "openmeteo"


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    name, lat, lon = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": ",".join(SURF + [f"{v}_{L}hPa" for v in PL for L in LEVELS]),
        "models": MODEL, "timezone": "auto",
    }
    rest = sys.argv[4:6]
    suffix = ""
    if rest and "-" in rest[0]:                     # date range -> archive
        start = dt.date.fromisoformat(rest[0])
        end   = dt.date.fromisoformat(rest[1]) if len(rest) > 1 else start
        params.update(start_date=start.isoformat(), end_date=end.isoformat())
        base, suffix = ARCH, f"_{start:%Y%m%d}-{end:%Y%m%d}"
    else:
        params.update(past_days=int(rest[0]) if rest else 2,
                      forecast_days=int(rest[1]) if len(rest) > 1 else 2)
        base = URL
    url = base + "?" + urllib.parse.urlencode(params, safe=",")
    req = urllib.request.Request(url, headers={"User-Agent": "halo-gram-quick"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read().decode("utf-8"))
    j["_pilot"] = {"name": name, "lat": lat, "lon": lon, "model": MODEL,
                   "pulled_utc": dt.datetime.now(dt.timezone.utc).isoformat()}

    OUT.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]+", "_", name)
    jpath = OUT / f"quick_{safe}{suffix}.json"
    jpath.write_text(json.dumps(j), encoding="utf-8")
    print(f"  data: {jpath}")

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from openmeteo_gram import load, render
        png = jpath.with_suffix(".png")
        render(load(jpath), png)
        print(f"  gram: {png}")
    except ImportError as e:
        print(f"  (no drawing: {e})")


if __name__ == "__main__":
    main()
