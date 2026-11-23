"""
build_page.py  -  rewrite only the viewer page (index.html) from template.html, leaving the data files alone

Run:   python build_page.py <built viewer folder>

Use it after changing template.html when the data have not changed; build.py does the full build.
"""
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
out = Path(sys.argv[1])
t = (here / "template.html").read_text(encoding="utf-8").replace("__LAND__", (here / "land.json").read_text())
t = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
     '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + t + "\n</html>\n")
(out / "index.html").write_text(t, encoding="utf-8")
print(f"wrote {out / 'index.html'}")
