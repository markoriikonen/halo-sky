# Handover: Halo Sky Atlas (haloskyatlas.com)

Written 23 November 2026 at the end of a long working thread, so that a new session can pick up the work. Read this first, then `README.md` for the data pipeline.

Marko Riikonen drives the science and the design; the assistant implements. He decides halo names, codes and what counts as rare or a first. Ask before changing anything scientific; small layout and code fixes can just be done and reported.

## What exists

| Part | Where | Notes |
|---|---|---|
| Halo Sky Gram | `gram/index.html` | Height gram and low/mid/high gram for any place and period; **5-day forecast** (yesterday, today, four days ahead, past hours shaded, red "now" line); **Humidity** style (relative humidity 50–100 %, dashed 70 % line) |
| Halo Sky Atlas (viewer), the front page | `viewer/template.html` → built to the site root | Modes: High cloud, Mid layer, Seasons (together "the Fingerprints"), Displays. 2,630 sites. Opens on the Displays live map (`setMode("displays")` at the end of the script). Header links to the Gram and Methods; credits in the footer, with no personal name (Marko's wish). Intro wording approved by Marko: Displays "maps actual halo displays". The old address `/fingerprints/` is a forwarding page (`viewer/forward.html`) |
| Methods page | `methods/index.html` | Data sources, humidity-derived level cloud (Sundqvist, critical humidity 70 %), why the two grams disagree, IFS upgrades 47r3 (12 Oct 2021) and 50r1 (12 May 2026) |
| Display Log | private Claude artifact `https://claude.ai/artifact/9Fwcbt5GUmJ3oq4N8Lbr9P`; source `displays/entry_template.html` + `displays/forms.json` | Marko enters halo displays here. Data in its database, collection `displays`, document id = running number |
| Old viewer address | Claude artifact `QLgEuMgeaU1XYKTv3nErfs` (public) | A "has moved" page pointing to haloskyatlas.com |

## Hosting and domain

- GitHub Pages serves the **`site`** branch of `markoriikonen/halo-sky`. Code lives on **`main`**.
- `viewer/deploy_site.sh <built viewer folder>` puts the built viewer at the root as the front page, adds the gram, methods, location lists and the `/fingerprints/` forwarding page, writes `CNAME` (haloskyatlas.com) and `.nojekyll`, and force-pushes `site` as a single commit (about 570 MB). Always deploy with this script: a push without the `CNAME` file drops the domain. `DRY=1 sh viewer/deploy_site.sh site` assembles the site in a temporary folder without pushing, for a local test (serve it with `python -m http.server`).
- Domain **haloskyatlas.com** is registered at Porkbun: four A records to GitHub (185.199.108–111.153) and `www` CNAME to `markoriikonen.github.io`. The domain is verified in GitHub (a TXT record `_github-pages-challenge-markoriikonen`; keep it). HTTPS is enforced. The Porkbun MX and SPF records are kept for email forwarding later.

## Getting a working copy in a new session

The built viewer (page plus about 300 MB of data) is not on `main`. Take it from the live site branch:

```
git clone https://github.com/markoriikonen/halo-sky.git halo-sky
git clone --depth 1 -b site https://github.com/markoriikonen/halo-sky.git sitecopy
mkdir site && cp -r sitecopy/index.html sitecopy/data site/   # this "site" folder is the built viewer folder used below
```

For browser tests, Playwright and Chromium are preinstalled; the page loads d3 and topojson from a CDN the sandbox cannot reach, so `npm install d3@7 topojson-client@3` in a scratch folder and route those requests to the local files.

## Common jobs

**Change the viewer page only** (template edits): `python viewer/build_page.py site`, then `sh viewer/deploy_site.sh site`.

**Change the gram, methods or front page**: edit in the repo, commit, then `sh viewer/deploy_site.sh site`.

**Publish new displays from the Log**:
1. Read the Log database (collection `displays`) to JSON files, one per display.
2. Stage any new pictures from Marko's PC folder `~/Downloads/Display images` (through the linked-computer tools) into the container.
3. `python viewer/displays_build.py <displays json folder> displays/forms.json "<images folder>" site` (writes `data/displays.js`, thumbnails in `data/disp/`, flags in `data/flags/`; it lists missing pictures and unknown countries).
4. `sh viewer/deploy_site.sh site`.

**Change the Display Log**: edit `displays/entry_template.html`, make `displays/index.html` by replacing `/*FORMS*/[]` with the contents of `displays/forms.json`, and republish it to the artifact URL above (keep its capabilities: database plus user). Commit both files.

**Update Fingerprints after new pulls** (Marko runs the pulls and builds on his PC, in `~/Downloads/grams`):
1. Stage from `~/Downloads/grams/openmeteo/`: `fingerprints*.json.gz` (6 files), `season.json.gz`, `season_twilight.json.gz`, `season_night.json.gz`, `season_checks.json.gz`, the folders `layer_windows/`, `layer_windows_all/`, `season_years/` (at most 50 files per staging call), and the six `locations_*.csv` lists.
2. Copy the lists into `locations/`.
3. `python koppen/koppen_sites_update.py <staged fingerprints.json.gz> <koppen_geiger_tif.zip, staged from his grams folder> site`.
4. In the staged folder: `python <repo>/viewer/build.py fingerprints.json.gz layer_windows season.json.gz <site>`.
5. Test, commit `locations/` and `koppen/koppen_sites.json`, deploy.

**Rename or remove sites** without pulling again: `scripts/openmeteo_rename_sites.py` (edit its RENAME and REMOVE tables; it shows the plan first and acts with `go`).

## Open-Meteo and the API key

- The paid subscription ended on 20 November 2026. The pull scripts use the customer endpoints with the key in `~/Downloads/grams/openmeteo/apikey.txt`; for further pulls they would need switching to the free endpoints (non-commercial use, 10,000 calls a day) and pacing.
- **Never** put the API key in code, pages, screenshots or posts, and never use it in a public page. `.gitignore` keeps it out of the repo. The public pages use only the free API from the visitor's browser.
- Climate normals (1991–2020 monthly temperature, precipitation, snowfall, sunshine) were pulled for all sites into `~/Downloads/grams/openmeteo/climate/` but are not shown anywhere yet. Marko has not decided whether to use them.

## Displays map: decisions already made

- **Who, where, when** is the core ("the holy trinity"). A single-display pop-up shows: picture, place, date, observer of the picture ("and N others" in grey). No time of day, no halo count.
- **Firsts are about who**: each first is credited to the observers whose items show it (an item with no Shows list shows every halo); observers with the same halos share a line. World first: pink ★ (#d0306a). National first: the country's flag; a **possible** national first has the flag faded with a dashed outline and a small "?". When a display has firsts, the observer line of the trinity is dropped. World-first lines are not bold.
- **Vertical photo credit** beside the picture, except when one observer or one team stands behind every item.
- The text marks R, O, M, E, B are left out of pop-ups and the Log ("O" reads as zero); the hexagons still draw them as symbols. Marko is thinking about a better design.
- **Hexagon**: the number is the count of halos not marked uncertain. Sides clockwise from the top: plate, random, column, Parry, Tricker, Lowitz. A side is black when its orientation had a rare halo, grey when only common ones (Parry, Tricker and Lowitz have no common halos). The fliphelion counts as rare only within 20° of the equator. Fill by light source: sun #ffa500, moon #cd9b9b, artificial #4876ff, mixed #8d99a6.
- **Several displays** show as a dot drawn as a stack of three. If the stack is ever dropped, go back to a single round dot (not a stack of two). Several displays at one place open a pop-up of their hexagons; hovering one shows that display, clicking opens its card; a click on the dot pins the pop-up.
- **Live map**: the last 30 days, but at least the 20 latest displays; an automatic camera counts as one display and brings all its displays. **No marker for the latest display** (the map is a record, not a live feed).
- **Automatic camera**: a Log checkbox (`auto`), a small camera mark at the top left of hexagons and dots, "automatic camera" in pop-ups and cards. Vancouver (Runnan Lin) is the first; more cameras are expected.
- The Log uses **"Uncertain"** for what the data still calls `doubtful`. Cloud types: High, Mid, Low, Ice fog, Contrail.
- **Ice Halo Tracker paste**: copying the halo list from a case page on icehalotracker.com and pasting it into the Log's halo box adds the halos in Marko's translation table (`TRACKER_NAMES` in the Log); the rest are listed for manual entry until the display is saved. Lowitz arcs and Parhelic circle are always entered by hand.

## Open items and plans

- **Rename to "Halo Sky Atlas"**: done on 23 November 2026 (the Atlas is the front page, new intro, credits in the footer, `/fingerprints/` forwards). Still open: whether to invite visitors to send in displays once email forwarding at Porkbun is set up.
- **Numeric halo codes**: Marko will replace the letter codes with numbers before adding alternative nomenclatures, still-theoretical halos, blue-edge effects and halo diffraction features (diffraction needs its own group symbol). When he has the old-to-new list, convert the Log records, `forms.json`, the paste table and the site in one go.
- **Spanish version**: deferred until the Spanish halo names are worked out (possibly with Franklin Fernández).
- **Display places as Fingerprints sites**: done for five places while the subscription lasted; later ones would need the free API.
- Ideas not started: ENSO colouring in the Seasons year-by-year pop-up; Virginia display coordinates awaited from the observer; Marko may reconsider whether some random-orientation halos (such as the 46° halo) count as rare; a GitHub organisation for the repo if someone else takes the site over.
