"""
displays_build.py  -  halo displays for the Fingerprints viewer's Displays mode

Run:   python displays_build.py <displays folder> <forms.json> <images folder> <site folder>

<displays folder>  one JSON file per display, as read from the Halo Display Log
<forms.json>       the halo forms list the Display Log uses ([code, name, group, subgroup, class, rare, mark])
<images folder>    the photos named in the documentation items (file names, or web-<id>-<n>.<ext>
                   for pictures given as web addresses, saved there by fetch_display_images.py)
<site folder>      the built viewer: writes data/displays.js and data/disp/*.jpg thumbnails

Prints the pictures it could not find.
"""
import sys, json, glob, os, re, hashlib
from pathlib import Path
from PIL import Image

ddir, forms_path, imgdir, site = map(Path, sys.argv[1:5])
THUMB = 420          # longest side, px

forms = {}
for c, n, g, s, cls, rare, mark in json.load(open(forms_path, encoding="utf-8")):
    forms.setdefault(c, [n, cls, rare, mark])

out_img = site / "data" / "disp"
out_img.mkdir(parents=True, exist_ok=True)
for old in out_img.glob("*.jpg"):
    old.unlink()

def split_names(by):
    out = []
    for b in by:
        out += [x.strip() for x in re.split(r"[,;]", b) if x.strip()]
    return out

missing, displays = [], []
for f in sorted(ddir.glob("*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
    j = json.load(open(f, encoding="utf-8"))
    d = j.get("data", j)
    items = []
    for k, it in enumerate(d.get("items", []), 1):
        src = (it.get("image") or "").strip()
        thumb = ""
        if src:
            if src.lower().startswith("http"):
                cands = sorted(imgdir.glob(f"web-{d['id']}-{k}.*"))
            else:
                cands = [imgdir / src] if (imgdir / src).exists() else []
            if cands:
                im = Image.open(cands[0]); im.thumbnail((THUMB, THUMB))
                if im.mode not in ("RGB", "L"):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.convert("RGBA").split()[-1]); im = bg
                name = f"{d['id']}-{k}.jpg"
                im.convert("RGB").save(out_img / name, quality=82, optimize=True)
                thumb = name
            else:
                missing.append((d["id"], k, src))
        items.append({"type": it.get("type", "photo"), "by": split_names(it.get("by", [])), "link": it.get("link", ""),
                      "thumb": thumb, "perm": it.get("perm", ""), "shows": it.get("shows"), "card": bool(it.get("card"))})
    keep = ["id", "date", "enddate", "time", "place", "country", "lat", "lon", "light", "cloud", "halos", "doubtful", "novel", "nfc", "nfp", "maxsim", "notes"]
    rec = {k: d.get(k) for k in keep}
    rec["items"] = items
    displays.append(rec)

used = sorted({c for d in displays for c in d["halos"]})
data = {"forms": {c: forms[c] for c in used if c in forms}, "unknown": [c for c in used if c not in forms], "displays": displays}
(site / "data" / "displays.js").write_text("window.FP_DISPLAYS=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
print(f"{len(displays)} displays, {sum(1 for d in displays for i in d['items'] if i['thumb'])} thumbnails -> {site / 'data'}")
for m in missing:
    print(f"  missing picture: display {m[0]} item {m[1]}: {m[2]}")
if data["unknown"]:
    print("  halo codes not in the list:", ", ".join(data["unknown"]))
