"""
openmeteo_rename_sites.py  -  rename or remove sites without pulling them again

Run:   python openmeteo_rename_sites.py        (only shows what it would do)
       python openmeteo_rename_sites.py go     (does it)

Edit RENAME and REMOVE below. For each renamed site it
  - changes the name in the location list that holds it (the rest of the line is kept as it is),
  - renames the site's files in stats9km/, profiles25km_all/ and climate/, and the name stored inside them.
If a site has already been pulled under its new name, the files under the old name are moved
to openmeteo/removed/ instead.

A removed site is taken out of its location list and its files are moved to openmeteo/removed/.
Nothing is deleted, and the script makes no API calls. Running it twice does no harm.

Afterwards run the build scripts as usual (fingerprint, season_build, season_checks, layer_build).
"""
import sys
import csv
import io
import re
import json
import gzip
import shutil
from pathlib import Path

import numpy as np

BASE = Path.home() / "Downloads" / "grams" / "openmeteo"
LISTS = ["locations_current.csv", "locations_new.csv", "locations_admin_100km.csv",
         "locations_extra.csv", "locations_handpicked.csv", "locations_cities.csv"]
FOLDERS = [("stats9km", ".json.gz"), ("climate", ".json.gz"), ("profiles25km_all", ".npz")]

RENAME = {
    "Dumaquete City": "Dumaguete City",
    "Verkhoyanks": "Verkhoyansk",
    "Norman  Wells": "Norman Wells",                 # two spaces in the old name
    "Mansinloc": "Masinloc",
    "Poblacion IV": "Balabac",                       # Poblacion IV is a barangay of Balabac town, Palawan
    "Tsawwassen": "Vancouver, Tsawwassen",
    "Vancouver": "Vancouver, Washington",            # the site at 45.64 N is Vancouver, WA, USA; delete this line to keep the plain name
    # "Quezon City, Philippines": "Manila",          # 9 km from central Manila: remove the # to rename it instead of pulling Manila
}
REMOVE = ["Godefroy, Canada"]


def safe(name):
    return re.sub(r"[^\w\-]+", "_", name).strip("_")


def split_first(line):
    """A CSV line -> (first field, was it quoted, the rest of the line from the comma on)."""
    if line.startswith('"'):
        i = 1
        while True:
            j = line.index('"', i)
            if line[j + 1:j + 2] == '"':
                i = j + 2
                continue
            return line[1:j].replace('""', '"'), True, line[j + 1:]
    k = line.find(",")
    return line[:k], False, line[k:]


def quote(name, quoted):
    return '"' + name.replace('"', '""') + '"' if quoted or "," in name or '"' in name else name


def edit_lists(go):
    for f in LISTS:
        p = BASE / f
        if not p.exists():
            continue
        lines = p.read_bytes().decode("utf-8").splitlines(keepends=True)   # keeps the line endings as they are
        out, changed = lines[:1], False
        for line in lines[1:]:
            if not line.strip():
                out.append(line)
                continue
            name, quoted, rest = split_first(line)
            if name in REMOVE:
                print(f"  {f}: remove {name!r}")
                changed = True
                continue
            if name in RENAME:
                print(f"  {f}: {name!r} -> {RENAME[name]!r}")
                line = quote(RENAME[name], quoted) + rest
                changed = True
            out.append(line)
        if changed and go:
            p.write_bytes("".join(out).encode("utf-8"))


def rewrite(src, dst, new_name):
    """Copy a site file to dst with the name inside changed, then drop src (if it is a different file)."""
    tmp = dst.with_name(dst.name + ".tmp")
    if src.suffix == ".npz":
        with np.load(src) as z:
            meta = json.loads(str(z["meta"]))
            meta["name"] = new_name
            arrays = {k: z[k] for k in z.files if k != "meta"}
        with open(tmp, "wb") as fh:
            np.savez_compressed(fh, meta=np.array(json.dumps(meta)), **arrays)
    else:
        with gzip.open(src, "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["name"] = new_name
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(rec, fh, separators=(",", ":"))
    tmp.replace(dst)
    if src != dst:
        src.unlink()


def set_aside(src, folder, go):
    dst = BASE / "removed" / folder / src.name
    print(f"  {folder}/{src.name} -> removed/{folder}/")
    if go:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def edit_files(go):
    for folder, ext in FOLDERS:
        d = BASE / folder
        for old, new in RENAME.items():
            src, dst = d / f"{safe(old)}{ext}", d / f"{safe(new)}{ext}"
            if not src.exists():
                continue
            if src != dst and dst.exists():
                print(f"  {folder}: {new!r} is already pulled; the old {old!r} file goes aside")
                set_aside(src, folder, go)
                continue
            print(f"  {folder}/{src.name} -> {dst.name}  (name inside: {new!r})")
            if go:
                rewrite(src, dst, new)
        for name in REMOVE:
            src = d / f"{safe(name)}{ext}"
            if src.exists():
                set_aside(src, folder, go)


def main():
    go = len(sys.argv) > 1 and sys.argv[1] == "go"
    print("Doing it:" if go else "Would do (run with 'go' to do it):")
    edit_lists(go)
    edit_files(go)
    print("Done." if go else "Nothing changed yet.")


if __name__ == "__main__":
    main()
