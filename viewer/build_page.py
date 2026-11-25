"""
build_page.py  -  rewrite only the viewer page (index.html) from template.html, leaving the data files alone

Run:   python build_page.py <built viewer folder>

Use it after changing template.html when the data have not changed; build.py does the full build.
"""
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
out = Path(sys.argv[1])
import json, shutil
t = (here / "template.html").read_text(encoding="utf-8").replace("__LAND__", (here / "land.json").read_text())
# news: viewer/news.json (newest first) goes into the page; its photos (viewer/news/) are copied to data/news/
news = json.loads((here / "news.json").read_text(encoding="utf-8"))
news.sort(key=lambda it: it["date"], reverse=True)
for it in news:
    if len(it["text"]) > 1000: print(f"note: news '{it['title']}' is {len(it['text'])} characters; the limit is 1000")
    for ph in it.get("photos", []):
        src = here / "news" / ph["file"]
        if not src.exists(): sys.exit(f"news photo missing: {src}")
        (out / "data" / "news").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out / "data" / "news" / ph["file"])
# a news item tied to a display ("display": id) shows that country's flag when the display has a national first (faded when possible)
dj = out / "data" / "displays.js"
if dj.exists():
    s = dj.read_text(encoding="utf-8"); disp = {d["id"]: d for d in json.loads(s[s.index("=") + 1:].rstrip().rstrip(";"))["displays"]}
    for it in news:
        d = disp.get(str(it.get("display", "")))
        if d and d.get("cc") and (d.get("nfc") or d.get("nfp")):
            it["flag"] = {"cc": d["cc"], "country": d.get("country", ""), "possible": not d.get("nfc")}
t = t.replace("__NEWS__", json.dumps(news, ensure_ascii=False))
t = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
     '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + t + "\n</html>\n")
(out / "index.html").write_text(t, encoding="utf-8")
print(f"wrote {out / 'index.html'}")
