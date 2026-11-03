"""
build.py  -  assemble the Halo Sky Fingerprints viewer

Run:   python build.py <fingerprints.json.gz> <layer_windows folder> <season.json.gz> <output folder>

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
