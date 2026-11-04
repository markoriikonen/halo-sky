"""Render the Beck et al. (2023) 1991-2020 Köppen-Geiger map into the viewer's Equal Earth projection.
Level 0: one world image (from the 0.1 deg map); levels 1-2: 1024 px tiles (from the 1 km map)."""
import numpy as np, tifffile, json, os, sys, re
from PIL import Image
OUT = '/tmp/claude-0/kgtiles'
W, H, SCALE, TX, TY = 960, 480, 175.12552615438148, 480.0, 240.0
A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = np.sqrt(3) / 2
leg = [l for l in open('/tmp/claude-0/kg/legend.txt', encoding='utf-8') if re.match(r'\s+\d+:', l)]
PAL = [(0, 0, 0)] * 31
CLS = {}
for l in leg:
    m = re.match(r'\s+(\d+):\s+(\S+)\s+(.+?)\s+\[(\d+) (\d+) (\d+)\]', l)
    k = int(m.group(1)); PAL[k] = tuple(int(m.group(i)) for i in (4, 5, 6)); CLS[k] = (m.group(2), m.group(3))
json.dump({k: [v[0], v[1], PAL[k]] for k, v in CLS.items()}, open(OUT + '/legend.json', 'w'), ensure_ascii=False)
palette = sum(PAL, ()) + (0, 0, 0) * (256 - 31)

def invert(x, y):
    X = (x - TX) / SCALE; Y = (TY - y) / SCALE
    l = Y.copy()
    for _ in range(12):
        l2 = l * l; l6 = l2 * l2 * l2
        f = l * (A1 + A2 * l2 + l6 * (A3 + A4 * l2)) - Y
        fp = A1 + 3 * A2 * l2 + l6 * (7 * A3 + 9 * A4 * l2)
        l = l - f / fp
    l2 = l * l; l6 = l2 * l2 * l2
    fp = A1 + 3 * A2 * l2 + l6 * (7 * A3 + 9 * A4 * l2)
    lam = M * X * fp / np.cos(l)
    s = np.clip(np.sin(l) / M, -1, 1)
    return np.degrees(lam), np.degrees(np.arcsin(s)), (np.abs(lam) <= np.pi) & (np.abs(np.sin(l) / M) <= 1)

def render(R, step, x0, y0, s, w, h):
    """R: raster (rows from 90N, cols from 180W) with cell size step deg; map-unit origin x0,y0; s px per map unit."""
    jj, ii = np.meshgrid(np.arange(w), np.arange(h))
    lon, lat, ok = invert(x0 + (jj + 0.5) / s, y0 + (ii + 0.5) / s)
    col = np.clip(((lon + 180) / step).astype(int), 0, R.shape[1] - 1)
    row = np.clip(((90 - lat) / step).astype(int), 0, R.shape[0] - 1)
    out = np.where(ok, R[row, col], 0).astype(np.uint8)
    return out

def save(a, path):
    im = Image.fromarray(a, mode='P'); im.putpalette(palette); im.info['transparency'] = 0
    im.save(path, optimize=True, transparency=0)

lev = sys.argv[1]
if lev == '0':
    R = tifffile.imread('/tmp/claude-0/kg/1991_2020/koppen_geiger_0p1.tif')
    a = render(R, 0.1, 0, 0, 4, W * 4, H * 4)
    save(a, OUT + '/kg0.png'); print('L0', os.path.getsize(OUT + '/kg0.png'))
else:
    s = {'1': 16, '2': 32}[lev]; T = 2048; span = T / s
    R = np.load('/tmp/claude-0/kg/kg1km.npy', mmap_mode='r')
    os.makedirs(f'{OUT}/kg{lev}', exist_ok=True)
    n = tot = 0; idx = []
    for ty in range(int(np.ceil(H / span))):
        for tx in range(int(np.ceil(W / span))):
            a = render(R, 1 / 120, tx * span, ty * span, s, T, T)
            if not a.any(): continue
            p = f'{OUT}/kg{lev}/{tx}_{ty}.png'; save(a, p); n += 1; tot += os.path.getsize(p); idx.append([tx, ty])
    json.dump({'span': span, 'tiles': idx}, open(f'{OUT}/kg{lev}.json', 'w'))
    print('L' + lev, n, 'tiles', round(tot / 1e6, 1), 'MB')
