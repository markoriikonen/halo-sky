"""
build.py  -  assemble the Halo Sky Fingerprints viewer

Run:   python build.py <fingerprints.json.gz> <layer_windows folder> <season.json.gz> <output folder> [koppen folder]

Writes <output folder>/index.html and data/*.js (the gzipped JSON files, base64-encoded
inside small scripts, because the Claude artifact host serves only certain file types).
The output folder can be published as a Claude artifact or on any static web host.
"""
import sys, os, base64, glob
from pathlib import Path

here = Path(__file__).parent
fp, wdir, season, out = sys.argv[1:5]
os.makedirs(os.path.join(out, "data"), exist_ok=True)
t = (here / "template.html").read_text(encoding="utf-8").replace("__LAND__", (here / "land.json").read_text())
t = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
     '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + t + "\n</html>\n")
Path(out, "index.html").write_text(t, encoding="utf-8")

def js(src, name, var):
    Path(out, "data", name).write_text(f'window.{var}="' + base64.b64encode(Path(src).read_bytes()).decode() + '";\n')

js(fp, "fingerprints.js", "FP_DATA")
js(os.path.join(wdir, "index.json.gz"), "layer_index.js", "FP_LINDEX")
for p in sorted(glob.glob(os.path.join(wdir, "w_*.json.gz"))):
    b = os.path.basename(p)[:-8]
    js(p, b + ".js", "FP_W_" + b[2:])
js(season, "season.js", "FP_SEASON")
print("built", out)

# detailed coastline (1:10 million, simplified), loaded by the page only when zoomed in
land10 = here / "land10.json"
if land10.exists():
    Path(out, "data", "land10.js").write_text("window.FP_LAND10=" + land10.read_text() + ";\n")

# Köppen-Geiger layer: legend, tile index and site classes in one small script; images copied as files
kgdir = Path(sys.argv[5]) if len(sys.argv) > 5 else None
if kgdir and kgdir.exists():
    import json, shutil
    leg = json.loads((kgdir / "legend.json").read_text(encoding="utf-8"))
    tiles = {k: json.loads((kgdir / f"{k}.json").read_text()) for k in ("kg1", "kg2")}
    sites = json.loads((kgdir / "koppen_sites.json").read_text(encoding="utf-8"))
    Path(out, "data", "koppen.js").write_text("window.FP_KOPPEN=" + json.dumps({"legend": leg, "tiles": tiles, "sites": sites}, ensure_ascii=False) + ";\n", encoding="utf-8")
    dst = Path(out, "data", "kg"); shutil.rmtree(dst, ignore_errors=True); dst.mkdir(parents=True)
    shutil.copy(kgdir / "kg0.png", dst / "kg0.png")
    for k in ("kg1", "kg2"): shutil.copytree(kgdir / k, dst / k)
