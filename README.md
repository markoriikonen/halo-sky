# Halo Sky

Tools for finding where and when the sky favours ice-crystal halos, from ECMWF model data served by [Open-Meteo](https://open-meteo.com/).

- **Halo Sky Gram** (`gram/`): a web page that draws a cloud-by-height gram (with the 0, −15 and −40 °C isotherms) or a low/mid/high cloud gram for any place and period. It runs in the visitor's browser and fetches from Open-Meteo's free, non-commercial API; no key is involved. Live at <https://markoriikonen.github.io/halo-sky/gram/>.
- **Halo Sky Fingerprints** (`viewer/`): a world map of about 2,000 sites showing how often each combination of cloud layers occurs in daylight, the elliptical-halo "mid layer" search, and high-cloud seasons. Built from a multi-year pull of hourly data (see below).
- **Scripts** (`scripts/`): the Python pipeline that pulls the data and builds the viewer's files.
- **Locations** (`locations/`): the site lists (name, latitude, longitude, elevation).

## The pipeline

The scripts expect a folder `~/Downloads/grams/openmeteo/` holding the location lists and a file `apikey.txt` with an Open-Meteo API key (the historical-forecast customer endpoint). **Never commit `apikey.txt`**; `.gitignore` keeps it out.

| Step | Script | Model | What it does |
|---|---|---|---|
| 1 | `openmeteo_stats_pull.py all` | IFS HRES 9 km | Hourly low/mid/high cloud, 2017 → yesterday, per site |
| 2 | `openmeteo_fingerprint.py` | – | Monthly daylight counts of low × high (10 % steps) and high × mid × low (20 %) → `fingerprints.json.gz` |
| 3 | `openmeteo_season_build.py` | – | High-cloud counts per five-day period in daylight, twilight and night, plus every year separately → `season*.json.gz`, `season_years/` |
| 4 | `openmeteo_profile_pull.py` | IFS 0.25° | Temperature and cloud cover on 13 pressure levels, 2024 → yesterday, every daylight hour, per site |
| 5 | `openmeteo_layer_build.py` | – | Daylight counts of cloud inside / warmer than / colder than each temperature window → `layer_windows/` |
| 6 | `openmeteo_season_checks.py` | – | Per site: do the odd- and even-year halves agree, could the swing be weather alone, how reliable is the season → `season_checks.json.gz` |
| 7 | `viewer/build.py` | – | Assembles the viewer page and its data files |

Other scripts: `openmeteo_boundary_check.py` (where ECMWF's mid/high split falls in temperature at chosen sites), `openmeteo_gram.py` and `openmeteo_quick.py` (PNG grams with matplotlib), `openmeteo_layer_pull.py` (earlier fixed-window version of steps 4–5).

## Things to know about the data

- ECMWF's low/mid/high bands are split by pressure, at 0.8 and 0.45 of surface pressure, not by cloud type or temperature. In a summer subtropical atmosphere the mid/high split lies near −17 °C.
- Cloud cover is the fraction of the model's grid box (about 9 × 9 km for the HRES bands) covered by cloud. Seen from the ground that box is roughly the sky above 65° elevation for cirrus at 10 km.
- Cloud cover on pressure levels is derived from relative humidity, not taken from the model's cloud scheme.
- Daylight means the sun above the horizon (NOAA solar position approximation).

## Licence and attribution

Data: ECMWF IFS via Open-Meteo, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The gram page uses Open-Meteo's free API, which is for non-commercial use only.
