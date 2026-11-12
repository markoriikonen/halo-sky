"""
fetch_display_images.py  -  save the display pictures given as web addresses

Run:   python fetch_display_images.py

Saves each picture into ~/Downloads/Display images/ as web-<display>-<item>.<ext>,
which is the name the map's thumbnail builder looks for. Pictures already saved are skipped.
Claude refreshes the list below whenever new displays with web pictures are added.
"""
import urllib.request
from pathlib import Path

DEST = Path.home() / "Downloads" / "Display images"
PICTURES = [
    ("1", 1, "https://www.taivaanvahti.fi/images/uploads/202512/140318_d5db583811be0a5dc3b24090898faba6.jpg"),
    ("6", 1, "https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjHHrMK5DT6cUKrFiZGmLC-RpuA4GhMDOBQRkiMmj-v9I4AG_gkKJa5pIypKAhabEQ5A0NGHegD4l2tey7eQ50wHdERd1s-mf3dL3-HN2EGX5KJmhMUalb6xLfgPTmJBLp0QojavAbNLhtC/s1600/2.png"),
]

DEST.mkdir(parents=True, exist_ok=True)
for disp, item, url in PICTURES:
    ext = Path(url.split("?")[0]).suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    out = DEST / f"web-{disp}-{item}{ext}"
    if out.exists():
        print("have", out.name); continue
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (halo display thumbnails)"})
        out.write_bytes(urllib.request.urlopen(req, timeout=60).read())
        print("saved", out.name)
    except Exception as e:
        print("FAILED", disp, item, url, "-", e)
