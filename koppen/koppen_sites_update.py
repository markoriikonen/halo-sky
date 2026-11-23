"""
koppen_sites_update.py  -  Köppen-Geiger class for every Fingerprints site, kept in step with the site list

Run:   python koppen_sites_update.py <fingerprints.json.gz> <koppen_geiger_tif.zip> <built viewer folder>

Reads the site list from fingerprints.json.gz, gives each site not yet in koppen_sites.json its class from the
1991-2020 map at 1 km (Beck et al. 2023: the zip as downloaded), drops sites that are gone (renamed or removed),
and writes koppen_sites.json here and data/koppen.js in the built viewer. A site on a water pixel takes the
commonest class within about 12 km; 0 means none was found.
"""
import sys, json, gzip, zipfile, tempfile
from pathlib import Path
import numpy as np
import tifffile

here = Path(__file__).resolve().parent
fp_path, zip_path, site = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])

with zipfile.ZipFile(zip_path) as z, tempfile.TemporaryDirectory() as tmp:
    name = next(n for n in z.namelist() if n.startswith("1991_2020") and "0p00833333" in n)
    R = tifffile.imread(z.extract(name, tmp))
step = 180 / R.shape[0]

def cls(la, lo, rad=12):
    r = min(max(int((90 - la) / step), 0), R.shape[0] - 1); c = int((lo + 180) / step) % R.shape[1]
    v = int(R[r, c])
    if v:
        return v
    for d in range(1, rad + 1):
        w = R[max(r - d, 0):r + d + 1, [(c + k) % R.shape[1] for k in range(-d, d + 1)]]; nz = w[w > 0]
        if nz.size:
            vals, n = np.unique(nz, return_counts=True); return int(vals[n.argmax()])
    return 0

sites = {s["n"]: (s["la"], s["lo"]) for s in json.load(gzip.open(fp_path, "rt"))["sites"]}
ks = json.load(open(here / "koppen_sites.json", encoding="utf-8"))
new = {n: cls(*sites[n]) for n in sites if n not in ks}
ks = {n: v for n, v in ks.items() if n in sites}; ks.update(new)
json.dump(ks, open(here / "koppen_sites.json", "w", encoding="utf-8"), ensure_ascii=False)
p = site / "data" / "koppen.js"
s = p.read_text(encoding="utf-8"); kj = json.loads(s[s.index("=") + 1:].rstrip().rstrip(";")); kj["sites"] = ks
p.write_text("window.FP_KOPPEN=" + json.dumps(kj, ensure_ascii=False) + ";\n", encoding="utf-8")
print(f"{len(new)} new classes, {len(ks)} sites")
