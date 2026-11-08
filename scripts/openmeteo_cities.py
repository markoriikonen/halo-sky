"""
openmeteo_cities.py  -  add the big cities of every country to the site lists

Run:   python openmeteo_cities.py

Needs two free GeoNames files (CC BY 4.0) in ~/Downloads/grams/openmeteo/:
    cities15000.txt    unzipped from https://download.geonames.org/export/dump/cities15000.zip
    countryInfo.txt    https://download.geonames.org/export/dump/countryInfo.txt

A city is taken if, in its country (GeoNames country code, so Greenland, Puerto
Rico etc. count on their own), it is
    1. the largest city, or
    2. at least SHARE of the largest city's population, or
    3. at least MILLION people,
and it lies more than SKIP_KM from every site already in the lists (and from any
bigger city already taken). Populations are GeoNames' city-proper figures.

Writes  openmeteo/locations_cities.csv          (the new sites, for the pulls)
        openmeteo/locations_cities_skipped.csv  (cities left out as too close, for checking)
No API calls.
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
SHARE = 0.25
MILLION = 1_000_000
SKIP_KM = 28
EXISTING = ["locations_current.csv", "locations_new.csv", "locations_admin_100km.csv",
            "locations_extra.csv", "locations_handpicked.csv"]
NOT_CITIES = {"PPLX", "PPLH", "PPLQ", "PPLW", "PPLCH"}     # city sections, historical, abandoned, destroyed


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1, h)))


def main():
    for f in ("cities15000.txt", "countryInfo.txt"):
        if not (BASE / f).exists():
            raise SystemExit(f"Missing {BASE / f}; see the instructions at the top of this script.")
    country = {}
    with open(BASE / "countryInfo.txt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            country[p[0]] = p[4]
    existing, names = [], set()
    for f in EXISTING:
        if (BASE / f).exists():
            with open(BASE / f, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    existing.append((float(r["lat"]), float(r["lon"]), r["name"]))
                    names.add(r["name"].lower())
    by_cc = defaultdict(list)
    with open(BASE / "cities15000.txt", encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) < 15 or p[6] != "P" or p[7] in NOT_CITIES:
                continue
            by_cc[p[8]].append({"name": p[1], "lat": float(p[4]), "lon": float(p[5]), "cc": p[8], "pop": int(p[14] or 0)})

    cand = []
    for cc, cities in by_cc.items():
        top = max(c["pop"] for c in cities)
        for c in cities:
            rule = ("largest" if c["pop"] == top else f"≥{int(SHARE * 100)}% of largest" if c["pop"] >= SHARE * top
                    else "≥1 million" if c["pop"] >= MILLION else None)
            if rule:
                cand.append({**c, "rule": rule, "country": country.get(cc, cc)})
    cand.sort(key=lambda c: -c["pop"])

    taken, skipped, pts = [], [], list(existing)
    for c in cand:
        near = min(pts, key=lambda q: km((c["lat"], c["lon"]), q)) if pts else None
        d = km((c["lat"], c["lon"]), near) if near else 1e9
        if d <= SKIP_KM:
            skipped.append({**c, "near": near[2], "km": round(d)})
            continue
        name = f"{c['name']}, {c['country']}"
        if name.lower() in names:
            name = f"{c['name']} ({c['lat']:.2f}, {c['lon']:.2f}), {c['country']}"
        names.add(name.lower())
        taken.append({**c, "site": name, "near": near[2] if near else "", "km": round(d)})
        pts.append((c["lat"], c["lon"], name))

    with open(BASE / "locations_cities.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "lat", "lon", "elev_m", "country", "population", "rule", "nearest_site", "nearest_km"])
        for c in taken:
            w.writerow([c["site"], round(c["lat"], 4), round(c["lon"], 4), "", c["country"], c["pop"], c["rule"], c["near"], c["km"]])
    with open(BASE / "locations_cities_skipped.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["city", "country", "population", "rule", "too_close_to", "km"])
        for c in skipped:
            w.writerow([c["name"], c["country"], c["pop"], c["rule"], c["near"], c["km"]])

    rules = defaultdict(int)
    per = defaultdict(int)
    for c in taken:
        rules[c["rule"]] += 1
        per[c["country"]] += 1
    print(f"Candidates {len(cand)}: {len(taken)} new sites, {len(skipped)} skipped as within {SKIP_KM} km of a site")
    for r, n in sorted(rules.items(), key=lambda x: -x[1]):
        print(f"   {r:18s} {n}")
    print("Most new sites:", ", ".join(f"{k} {v}" for k, v in sorted(per.items(), key=lambda x: -x[1])[:15]))
    print(f"Estimated API calls: about {len(taken) * 560:,} (9 km cloud 2017- and profiles 2024-)")
    print(f"-> {BASE / 'locations_cities.csv'}")


if __name__ == "__main__":
    main()
