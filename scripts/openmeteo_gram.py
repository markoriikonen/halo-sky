"""
openmeteo_gram.py  -  halo observer's gram from Open-Meteo pressure-level data

Run:   python openmeteo_gram.py pilot_Moquegua.json [more.json ...]
       (no arguments: renders every pilot_*.json in ~/Downloads/grams/openmeteo)

Cloud panel
  * altitude (true height from geopotential) x local time, 0-18 km
  * shading darkness = model cloud cover at that height (per pressure level,
    interpolated linearly between levels)
  * shading colour = phase regime from the model temperature at that height:
        warmer than 0 C        liquid
        0 to -15 C             supercooled / mixed
        -15 to -40 C           mostly ice
        colder than -40 C      ice (homogeneous nucleation)
  * isotherm lines 0, -15, -40 C (contoured, so inversions are handled)
  * terrain below the site elevation is masked
  * night is a slightly tinted background

Pilot-only strip underneath: ECMWF's own low / mid / high cloud cover, as a
cross-check of the per-level field. Note ECMWF's split is pressure-relative
(high = above ~0.45 x surface pressure), so at elevated sites its "mid" can
include cloud the panel shows at 7-10 km.

Needs numpy and matplotlib.
"""

import sys
import json
import datetime as dt
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb

LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]

Z_TOP_KM = 18.0
DZ_M     = 50.0                       # vertical resolution of the drawn field

CLOUD     = np.array(to_rgb("#3c3c3c"))   # colour of 100 % cloud cover
ISOTHERMS = [0.0, -15.0, -40.0]
SIGMA_BOUNDS = [0.8, 0.45]            # ECMWF low|mid and mid|high: pressure as a
                                      # fraction of surface pressure

BG        = np.array(to_rgb("#ffffff"))
SUN_DAY   = "#f2cf6b"                       # daylight bar colours
SUN_TWI   = "#a9b4c9"                       # civil twilight (sun 0 to -6 deg)
SUN_NIGHT = "#3d4559"
GROUND    = np.array(to_rgb("#d9cbb4"))
ALPHA_GAMMA = 0.8
EDGE_FADE_M = 600.0                   # an isolated cloudy level fades out within
                                      # this distance, however far the next level
                                      # is (None = plain linear interpolation)                     # <1 lifts thin cloud a little


def load(path):
    j = json.loads(Path(path).read_text(encoding="utf-8"))
    h = j["hourly"]
    times = [dt.datetime.fromisoformat(t) for t in h["time"]]
    z  = np.array([h[f"geopotential_height_{L}hPa"] for L in LEVELS], float)
    T  = np.array([h[f"temperature_{L}hPa"]        for L in LEVELS], float)
    cc = np.array([h[f"cloud_cover_{L}hPa"]        for L in LEVELS], float)
    surf = {k: np.array(h[k], float) for k in
            ("cloud_cover_low", "cloud_cover_mid", "cloud_cover_high", "is_day")}
    meta = j.get("_pilot", {})
    return dict(name=meta.get("name", Path(path).stem), model=meta.get("model", ""),
                lat=j["latitude"], lon=j["longitude"], elev=float(j["elevation"]),
                tz=j.get("timezone_abbreviation", ""), times=times,
                utc_off=float(j.get("utc_offset_seconds", 0)),
                pulled=meta.get("pulled_utc"),
                z=z, T=T, cc=cc, surf=surf,
                ps=np.array(h["surface_pressure"], float)
                   if "surface_pressure" in h else None)


def cloud_profile(zg, zl, cl):
    """Cloud cover on the height grid from the per-level values.
    Between two cloudy levels: linear interpolation (the deck spans the gap).
    Between a cloudy and a clear level: the cloud fades to zero within
    EDGE_FADE_M of the cloudy level, not across the whole gap, so a lone
    cloudy level is not drawn kilometres thick just because the levels are
    far apart."""
    if EDGE_FADE_M is None:
        return np.interp(zg, zl, cl, left=0.0, right=0.0)
    out = np.zeros_like(zg)
    H = EDGE_FADE_M
    # pad with clear levels below and above
    zl = np.concatenate(([zl[0] - 10 * H], zl, [zl[-1] + 10 * H]))
    cl = np.concatenate(([0.0], cl, [0.0]))
    for k in range(len(zl) - 1):
        za, zb, ca, cb = zl[k], zl[k + 1], cl[k], cl[k + 1]
        m = (zg >= za) & (zg < zb)
        if not m.any():
            continue
        z = zg[m]
        if ca > 0 and cb > 0:
            out[m] = ca + (cb - ca) * (z - za) / (zb - za)
        else:
            fa = ca * np.clip(1 - (z - za) / H, 0, 1)
            fb = cb * np.clip(1 - (zb - z) / H, 0, 1)
            out[m] = np.maximum(fa, fb)
    return out


def layer_bounds(d):
    """Heights (m) of the ECMWF low|mid and mid|high boundaries, hour by hour.
    Surface pressure is taken from the data if present, otherwise estimated
    by interpolating ln(p) against height to the site elevation."""
    n = len(d["times"])
    lnp = np.log(np.array(LEVELS, float))
    out = np.full((len(SIGMA_BOUNDS), n), np.nan)
    for i in range(n):
        zi = d["z"][:, i]
        ok = ~np.isnan(zi)
        if ok.sum() < 3:
            continue
        o = np.argsort(zi[ok])
        z_s, lp_s = zi[ok][o], lnp[ok][o]          # height up, ln p down
        if d.get("ps") is not None and not np.isnan(d["ps"][i]):
            lps = np.log(d["ps"][i])
        else:
            lps = np.interp(d["elev"], z_s, lp_s)
        for k, sig in enumerate(SIGMA_BOUNDS):
            target = lps + np.log(sig)              # ln(sigma * ps)
            # ln p decreases with height: interpolate on reversed arrays
            out[k, i] = np.interp(target, lp_s[::-1], z_s[::-1])
    return out


def to_grid(d):
    """Interpolate T and cloud cover onto a regular height grid, hour by hour."""
    zg = np.arange(0.0, Z_TOP_KM * 1000 + DZ_M, DZ_M)
    n  = len(d["times"])
    Tg  = np.full((len(zg), n), np.nan)
    ccg = np.zeros((len(zg), n))
    for i in range(n):
        zi, Ti, ci = d["z"][:, i], d["T"][:, i], d["cc"][:, i]
        ok = ~(np.isnan(zi) | np.isnan(Ti))
        if ok.sum() < 2:
            continue
        o = np.argsort(zi[ok])
        Tg[:, i] = np.interp(zg, zi[ok][o], Ti[ok][o])
        cc_ok = np.nan_to_num(ci[ok][o])
        ccg[:, i] = cloud_profile(zg, zi[ok][o], cc_ok)
    return zg, Tg, ccg


def sun_elevation(lat, lon, utc):
    """Solar elevation in degrees (NOAA approximation, ~0.5 deg accuracy).
    utc: array of datetime64 in UTC."""
    t = (utc - np.datetime64("2000-01-01T12:00")) / np.timedelta64(1, "D")
    g = np.radians((357.529 + 0.98560028 * t) % 360)
    q = (280.459 + 0.98564736 * t) % 360
    L = np.radians((q + 1.915 * np.sin(g) + 0.020 * np.sin(2 * g)) % 360)
    e = np.radians(23.439 - 0.00000036 * t)
    ra = np.arctan2(np.cos(e) * np.sin(L), np.cos(L))
    dec = np.arcsin(np.sin(e) * np.sin(L))
    gmst = (18.697374558 + 24.06570982441908 * t) % 24
    ha = np.radians(gmst * 15 + lon) - ra
    la = np.radians(lat)
    return np.degrees(np.arcsin(np.sin(la) * np.sin(dec) +
                                np.cos(la) * np.cos(dec) * np.cos(ha)))


def render(d, out_png):
    zg, Tg, ccg = to_grid(d)
    n = len(d["times"])

    # white background, ground below the site
    bg = BG * np.ones((len(zg), n, 1))
    below = zg < d["elev"]
    bg[below, :, :] = GROUND

    a = np.clip(ccg / 100.0, 0, 1) ** ALPHA_GAMMA
    a[below, :] = 0.0
    rgb = bg * (1 - a[..., None]) + CLOUD * a[..., None]

    x0 = 0.0
    x1 = float(n)                    # one unit per hour
    ext = (x0, x1, 0.0, Z_TOP_KM)

    n_days = n / 24
    long_span = n_days > 16                     # compact labels for long runs
    fig_w = max(12.0, n_days * (0.55 if long_span else 1.25))
    fig = plt.figure(figsize=(fig_w, 6.2), dpi=150)
    ax  = fig.add_axes([0.035, 0.24, 0.955, 0.625])
    axd = fig.add_axes([0.035, 0.872, 0.955, 0.022])     # daylight bar
    axs = fig.add_axes([0.035, 0.10, 0.955, 0.09])

    ax.imshow(rgb, origin="lower", aspect="auto", extent=ext,
              interpolation="bilinear")

    # daylight bar: sun elevation every 5 minutes
    t0_utc = np.datetime64(d["times"][0]) - np.timedelta64(int(d["utc_off"]), "s")
    mins = np.arange(0, n * 60, 5)
    elev = sun_elevation(d["lat"], d["lon"],
                         t0_utc + mins.astype("timedelta64[m]"))
    bar = np.where(elev > 0, 0, np.where(elev > -6, 1, 2))
    from matplotlib.colors import ListedColormap
    axd.imshow(bar[None, :], aspect="auto", extent=(x0, x1, 0, 1),
               cmap=ListedColormap([SUN_DAY, SUN_TWI, SUN_NIGHT]),
               vmin=0, vmax=2, interpolation="nearest")
    axd.set_xlim(x0, x1)
    axd.set_xticks([]); axd.set_yticks([])
    for sp in axd.spines.values():
        sp.set_visible(False)

    # ECMWF layer boundaries (low|mid, mid|high), dashed
    lb = layer_bounds(d) / 1000.0
    for k, lab in enumerate(("low | mid", "mid | high")):
        ax.plot(np.arange(n) + 0.5, lb[k],
                color="#8a8a8a", lw=0.7, ls=(0, (4, 3)))
        last = lb[k][~np.isnan(lb[k])]
        if len(last):
            ax.text(n - 0.5, last[-1] + 0.15, lab, ha="right", va="bottom",
                    fontsize=6, color="#777")

    # isotherms (contour handles inversions / multiple crossings)
    xc = np.arange(n) + 0.5
    T_masked = np.ma.masked_where(np.isnan(Tg) | below[:, None], Tg)
    cs = ax.contour(xc, zg / 1000.0, T_masked, levels=sorted(ISOTHERMS),
                    colors="#2b2b2b", linewidths=0.7, alpha=0.75,
                    linestyles="solid")
    ax.clabel(cs, fmt=lambda v: f"{v:.0f}°".replace("-", "−"),
              fontsize=6.5, inline=True, inline_spacing=2)

    # day boundaries and ticks
    t0 = d["times"][0]
    days = sorted({t.date() for t in d["times"]})
    for k, day in enumerate(days):
        x = (dt.datetime.combine(day, dt.time()) - t0).total_seconds() / 3600
        ax.axvline(x, color="#9a9a9a", lw=0.6, alpha=0.8)
        axs.axvline(x, color="#9a9a9a", lw=0.6, alpha=0.8)
        axd.axvline(x, color="#ffffff", lw=0.8)
        if long_span:
            lab = (day.strftime("%b %d").replace(" 0", " ")
                   if (day.day == 1 or k == 0) else str(day.day))
        else:
            lab = day.strftime("%a %d %b").replace(" 0", " ")
        axd.text(x + 12, 1.35, lab,
                 ha="center", va="bottom", fontsize=7.5, color="#333")
    # "now" marker: when the data was pulled (only if inside the plotted span)
    if d.get("pulled"):
        p = dt.datetime.fromisoformat(d["pulled"]).replace(tzinfo=None)
        xn = ((p - t0).total_seconds() + d["utc_off"]) / 3600
        if 0 < xn < n:
            for a_ in (ax, axd, axs):
                a_.axvline(xn, color="#c0392b", lw=0.9, ls=(0, (3, 2)))
            ax.text(xn + 0.4, Z_TOP_KM - 0.3, "now", color="#c0392b",
                    fontsize=6.5, va="top")

    tick_hours = (12,) if long_span else (6, 12, 18)
    ax.set_xticks([h for h in range(n) if d["times"][h].hour in tick_hours])
    ax.set_xticklabels([])
    ax.tick_params(axis="x", length=3, color="#bbb")
    ax.set_xlim(x0, x1)

    ax.set_ylim(0, Z_TOP_KM)
    ax.set_yticks(range(0, int(Z_TOP_KM) + 1, 2))
    ax.set_yticklabels([f"{k}" for k in range(0, int(Z_TOP_KM) + 1, 2)], fontsize=7)
    ax.set_ylabel("km", fontsize=7, labelpad=2)
    for s in ax.spines.values():
        s.set_color("#bbb")

    # pilot strip: ECMWF native low / mid / high
    strip = np.zeros((3, n, 3))
    for r, key in ((2, "cloud_cover_high"), (1, "cloud_cover_mid"),
                   (0, "cloud_cover_low")):
        aa = np.clip(np.nan_to_num(d["surf"][key]) / 100.0, 0, 1) ** ALPHA_GAMMA
        strip[r] = BG * (1 - aa[:, None]) + CLOUD * aa[:, None]
    axs.imshow(strip, origin="lower", aspect="auto", extent=(x0, x1, 0, 3),
               interpolation="nearest")
    axs.set_yticks([0.5, 1.5, 2.5])
    axs.set_yticklabels(["low", "mid", "high"], fontsize=6)
    axs.set_xticks([h for h in range(n) if d["times"][h].hour in tick_hours])
    axs.set_xticklabels(["" if long_span else f"{d['times'][h].hour:02d}"
                         for h in range(n)
                         if d["times"][h].hour in tick_hours], fontsize=6,
                        color="#666")
    axs.tick_params(axis="x", length=2, color="#bbb")
    axs.set_xlim(x0, x1)
    for s in axs.spines.values():
        s.set_color("#ccc")
    axs.text(1.0, -0.62, "pilot check: ECMWF native low / mid / high cloud cover",
             transform=axs.transAxes, ha="right", va="top", fontsize=6, color="#888")

    title = (f"{d['name']}   {d['lat']:.2f}, {d['lon']:.2f}, {d['elev']:.0f} m   "
             f"·   {d['model']}   ·   "
             f"{d['times'][0]:%d %b} – {d['times'][-1]:%d %b %Y}   "
             f"·   local time ({d['tz']})")
    fig.text(0.035, 0.965, title, fontsize=8.5, color="#222", va="top")

    fig.savefig(out_png)
    plt.close(fig)
    return out_png


def main():
    args = sys.argv[1:]
    if not args:
        folder = Path.home() / "Downloads" / "grams" / "openmeteo"
        args = sorted(str(p) for p in folder.glob("pilot_*.json"))
    for a in args:
        d = load(a)
        out = Path(a).with_name(Path(a).stem.replace("pilot_", "gram_") + ".png")
        render(d, out)
        print(f"  {d['name']}: {out}")


if __name__ == "__main__":
    main()
